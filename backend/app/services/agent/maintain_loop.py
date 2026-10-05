"""维护 Agent 主循环：四阶段（queue → prepare → execute → settle）+ SSE 事件总线

形态总览（详见根目录设计文档）：
- 大脑走本站中转链路（source="agent"：计费照常扣管理员余额、写 logs/统计，
  唯一差异是不写 chat_record——维护对话独立存储在 agent_message）；
- 手是白名单工具（registry），高危操作过人审阀门（approvals）；
- SSE 复刻工坊模式：正文走 OpenAI 风格增量，站内扩展统一挂 agenticapi_agent 字段。

护栏：MAX_TOOL_ROUNDS 工具轮上限 / 会话 token 预算 / L2 每会话 5 次 /
审批 300s 超时 / finish_reason=length 截断防御（残缺 tool_calls 一律不执行）。
"""

import asyncio
import json
import time
from collections.abc import AsyncIterator

import httpx
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import agent as agent_crud
from app.crud import channel as channel_crud
from app.models.user import UserTabel
from app.services.agent import skills as skill_service
from app.services.agent.approvals import approval_manager
from app.services.agent.registry import ToolContext, ToolExecution, execute_tool, tools_payload_for
from app.services.relay_service import (
    RelayError, _finalize_call, _ordered_channels, _rewrite_sse_model, resolve_target,
)
from app.services.studio_agent_service import _process_line

MAX_TOOL_ROUNDS = 24            # 单次用户消息触发的工具循环轮数上限
SESSION_TOKEN_BUDGET = 200_000  # 会话累计 token 预算（超出后 Agent 汇报并停止）
DEHYDRATE_KEEP_RECENT = 12      # 脱水窗口：最近 N 条消息不折叠
DEHYDRATE_MIN_CHARS = 600       # 短于该长度的 tool 结果不值得折叠
COMPACT_TRIGGER_RATIO = 0.7     # 估算 token 超过 context_length×70% 触发压缩

# 正在执行任务的会话（防同会话并发跑两个循环）
_RUNNING: set[int] = set()


def _agent_event(data: dict) -> bytes:
    """站内扩展事件（前端解析模式复刻 agenticapi_search）"""
    return b"data: " + json.dumps({"agenticapi_agent": data}, ensure_ascii=False).encode() + b"\n"


def _error_event(message: str) -> bytes:
    return b"data: " + json.dumps(
        {"error": {"message": message, "type": "api_error"}}, ensure_ascii=False,
    ).encode() + b"\n"


def build_system_prompt(session: dict) -> str:
    """system prompt：角色 + 安全规则 + 工具使用守则 + skill 目录（只注入目录不注入全文）"""
    l2_state = "开启" if session.get("enable_l2") else "关闭（只读模式，L2 工具不可用）"
    return f"""你是 AgenticAPI 中转站的管理员运维维护 Agent，通过白名单工具对站点进行查询、拨测、数据治理与巡检。

【安全规则（必须遵守）】
1. 只能调用系统提供的白名单工具，没有 shell、没有任意命令、没有通用文件访问；
2. 渠道密钥等敏感信息永远不会出现在工具结果里，也不要尝试获取或输出它们；
3. L1/L2 写操作需要管理员在审批卡片上确认；被拒绝后不要原样重试，先调整方案或说明理由；
4. 清理类（cleanup_*）工具是两段式：第一次调用必须 dry_run=true 预览删除量，向管理员展示预览并确认其同意后，再用 dry_run=false 真删；
5. 不修改渠道密钥、不删除用户/模型/渠道、不改用户余额——这些请引导管理员去对应管理页操作。

【工作守则】
- 工具失败会以 isError 数据返回：读错误信息修正参数后重试（如纠正渠道名拼写），或换一个途径；
- 批量操作前先小范围抽查（如 test_channel scope=one），确认没问题再扩大范围；
- 巡检/排障/治理等任务优先匹配下述技能目录，用 load_skill 读取 SOP 后按流程执行，偏离流程要说明理由；
- 回答使用中文，运维数据用简洁结构化格式（表格/列表），金额保留 4 位小数。

【技能目录（按需 load_skill 加载全文）】
{skill_service.catalog_text()}

【当前会话状态】
- 驱动模型：{session.get("model_name")}（可用 switch_model 工具切换为站内任意模型）
- L2 高危工具：{l2_state}
- 管理员已知晓所有操作会被审计记录。"""


def _history_to_llm(rows: list[dict]) -> list[dict]:
    """DB 消息行 → 标准 OpenAI 报文（user/assistant/tool；encrypted_content 仅内存态保留）"""
    messages: list[dict] = []
    for row in rows:
        role = row["role"]
        if role == "assistant":
            msg: dict = {"role": "assistant", "content": row.get("content") or ""}
            if row.get("tool_calls"):
                msg["tool_calls"] = row["tool_calls"]
            if row.get("_encrypted"):
                msg["encrypted_content"] = row["_encrypted"]
            messages.append(msg)
        elif role == "tool":
            messages.append({"role": "tool", "tool_call_id": row.get("tool_call_id") or "",
                             "content": row.get("content") or ""})
        else:  # user / system
            messages.append({"role": role, "content": row.get("content") or ""})
    return messages


def _extract_summary(content: str) -> str:
    """从工具结果 JSON 里取 _summary 字段（脱水占位用），解析失败退化为截断文本"""
    try:
        obj = json.loads(content)
        if isinstance(obj, dict):
            for key in ("_summary", "message"):
                if isinstance(obj.get(key), str) and obj[key].strip():
                    return obj[key][:200]
    except (TypeError, ValueError):
        pass
    return (content or "")[:200]


def dehydrate(messages: list[dict]) -> list[dict]:
    """
    脱水（主策略，每轮 prepare 阶段执行）：距最新消息超过 DEHYDRATE_KEEP_RECENT 条的
    tool 结果替换为占位摘要。只缩内容、不删消息——tool_call/tool_result 配对关系
    完整保留（OpenAI 协议要求 assistant.tool_calls 后必须跟齐 tool 消息）。
    """
    cutoff = len(messages) - DEHYDRATE_KEEP_RECENT
    out: list[dict] = []
    for idx, msg in enumerate(messages):
        if (msg.get("role") == "tool" and idx < cutoff
                and len(msg.get("content") or "") > DEHYDRATE_MIN_CHARS):
            placeholder = f"[工具结果已折叠] {_extract_summary(msg.get('content') or '')}"
            out.append({**msg, "content": placeholder})
        else:
            out.append(msg)
    return out


def _estimate_tokens(messages: list[dict], last_prompt_tokens: int) -> int:
    """token 估算（采纳 pi 计账法）：最近官方 prompt_tokens + 其后新增消息字符数/4"""
    chars = sum(len(str(m.get("content") or "")) for m in messages)
    return last_prompt_tokens + chars // 4


def _compact_messages(messages: list[dict], context_length: int) -> list[dict]:
    """
    压缩兜底（脱水后仍超窗）：保留 system + 最近消息（切点对齐到 user 消息边界，
    不拆散工具配对），更早历史以一条代码生成的摘要消息替代（不追加模型调用，
    避免压缩本身失败把主任务拖死）。
    """
    budget_messages = max(int(context_length * COMPACT_TRIGGER_RATIO * 3), 24)  # 粗算：3 token/消息下限
    keep = messages[-budget_messages:]
    dropped = messages[1:-budget_messages] if len(messages) > budget_messages + 1 else []
    if not dropped or not keep:
        return messages

    # 切点对齐：keep 的第一条必须是 user，避免拆散 assistant.tool_calls ↔ tool 配对
    for idx, msg in enumerate(keep):
        if msg.get("role") == "user":
            keep = keep[idx:]
            break
    if not keep:
        return messages

    summary_lines = ["[较早的对话历史已折叠] 此前完成的主要动作："]
    for msg in dropped:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            names = [tc.get("function", {}).get("name") for tc in msg["tool_calls"]]
            summary_lines.append(f"- 调用过工具：{', '.join(n for n in names if n)}")
        elif msg.get("role") == "tool":
            summary_lines.append(f"- 工具结果摘要：{_extract_summary(msg.get('content') or '')[:120]}")
        elif msg.get("role") == "assistant":
            summary_lines.append(f"- 助手结论：{(msg.get('content') or '')[:120]}")
    return [messages[0], {"role": "user", "content": "\n".join(summary_lines[:60])}] + keep


async def repair_dangling_tool_calls(db: AsyncSession, session_id: int) -> int:
    """
    历史修复：assistant.tool_calls 后缺失对应 tool 消息（进程重启等中断造成）时，
    补插 isError 占位 tool 消息——否则续轮请求会被上游 400 拒绝。返回修复条数。
    """
    rows = await agent_crud.list_messages(db, session_id)
    answered = {r["tool_call_id"] for r in rows if r["role"] == "tool" and r.get("tool_call_id")}
    repaired = 0
    for row in rows:
        if row["role"] != "assistant" or not row.get("tool_calls"):
            continue
        for call in row["tool_calls"]:
            call_id = (call or {}).get("id")
            if call_id and call_id not in answered:
                await agent_crud.insert_message(
                    db, session_id=session_id, role="tool",
                    content=json.dumps(
                        {"isError": True, "message": "该工具调用因服务重启未执行完成，请重新发起。"},
                        ensure_ascii=False),
                    tool_call_id=call_id, approval_status="timeout",
                )
                repaired += 1
    return repaired


async def run_chat(db: AsyncSession, session, user: UserTabel, content: str) -> StreamingResponse:
    """
    维护 Agent 对话入口（SSE）。session 为 AgentSessionTable 行。

    - 同会话防并发：执行中的会话再发消息抛 RelayError(409)（OpenAI 风格报文）；
    - 启动时修复中断历史（悬挂 tool_calls 补占位结果）。
    """
    if session.id in _RUNNING:
        raise RelayError(409, "当前会话正在执行任务，请等待完成或点停止后再发送")
    _RUNNING.add(session.id)
    try:
        await repair_dangling_tool_calls(db, session.id)
        return StreamingResponse(_run(db, session, user, content), media_type="text/event-stream")
    except Exception:
        _RUNNING.discard(session.id)
        raise


async def _run(db: AsyncSession, session, user: UserTabel, content: str) -> AsyncIterator[bytes]:
    """主循环生成器：四阶段循环 + 事件总线（列表队列解耦 emit 与 yield）"""
    session_id = session.id
    session_dict = {
        "id": session_id,
        "model_name": session.model_name,
        "auto_approve_l1": bool(session.auto_approve_l1),
        "enable_l2": bool(session.enable_l2),
    }

    # ── ① queue：落库用户消息，装配历史 ──
    await agent_crud.insert_message(db, session_id=session_id, role="user", content=content)
    history: list[dict] = await agent_crud.list_messages(db, session_id)

    event_queue: list[dict] = []

    async def emit(event: dict) -> None:
        event_queue.append(event)

    ctx = ToolContext(db=db, user=user, session=session_dict, emit=emit)
    ctx.l2_used = await agent_crud.count_l2_executed(db, session_id)

    usage_total = {"prompt": 0, "completion": 0}
    last_prompt_tokens = 0
    epoch_model: dict | None = None      # 当前模型纪元（模型配置 dict）
    epoch_channels: list[str] = []
    channel: dict | None = None          # 续轮复用的当前渠道（纪元内不换）
    headers: dict = {}
    tools_degraded = False               # 上游 400/422 剥 tools 后本任务不再注入工具
    notices: list[str] = []              # 护栏触发的系统提示（追加为 user 消息，不落库）

    try:
        round_no = 0
        while True:
            round_no += 1
            force_final = False

            # ── 预算与轮次护栏 ──
            if round_no > MAX_TOOL_ROUNDS:
                notices = [f"已达到工具轮数上限（{MAX_TOOL_ROUNDS}），请基于已有信息直接总结汇报，不要再调用工具。"]
                force_final = True
            if usage_total["prompt"] + usage_total["completion"] > SESSION_TOKEN_BUDGET:
                notices = [f"会话 token 预算（{SESSION_TOKEN_BUDGET}）已耗尽，请立即总结当前结论并结束。"]
                force_final = True

            # ── ② prepare：模型纪元检查 + 历史脱水 + 请求装配（唯一转换边界）──
            if epoch_model is None or epoch_model.get("name") != session_dict["model_name"]:
                try:
                    epoch_model, epoch_channels = await resolve_target(
                        db, {"model": session_dict["model_name"],
                             "messages": [{"role": "user", "content": "ping"}]},
                        user, source="agent")
                except RelayError as exc:
                    yield _error_event(f"模型解析失败：{exc.message}")
                    break
                channel = None  # 新纪元重新选渠道

            llm_messages = _history_to_llm(history)
            for notice in notices:
                llm_messages.append({"role": "user", "content": notice})
            llm_messages = dehydrate(llm_messages)
            llm_messages.insert(0, {"role": "system", "content": build_system_prompt(session_dict)})

            model_name = epoch_model["name"]
            upstream_name = (epoch_model.get("upstream_name") or "").strip()
            needs_mapping = bool(upstream_name) and upstream_name != model_name
            include_tools = None if (force_final or tools_degraded) else tools_payload_for(session_dict)
            body = {
                "model": upstream_name or model_name,
                "messages": llm_messages,
                "stream": True,
                "stream_options": {"include_usage": True},
            }
            if include_tools:
                body["tools"] = include_tools

            # 上下文超窗保护：脱水后估算仍超 context_length×70% 时压缩兜底
            context_length = int(epoch_model.get("context_length") or 128_000)
            if _estimate_tokens(llm_messages, last_prompt_tokens) > context_length * COMPACT_TRIGGER_RATIO:
                llm_messages = _compact_messages(llm_messages, context_length)
                body["messages"] = llm_messages

            # ── 渠道选择：纪元首轮遍历（含 400/422 剥 tools 降级），续轮复用 ──
            if channel is None:
                channel, resp, client, err = await _first_round(
                    db, epoch_model, epoch_channels, body)
                if channel is None:
                    yield _error_event(f"所有上游渠道调用失败：{err}")
                    break
                if include_tools and "tools" not in body:
                    # 降级发生：上游不支持 tools，本任务后续轮次不再注入并提示模型
                    tools_degraded = True
                    history.append({"role": "user", "content":
                                    "（系统提示：当前驱动模型不支持函数工具调用，本轮起仅可纯对话；"
                                    "建议用 switch_model 切换到支持工具调用的模型后继续任务）"})
                headers = {"Authorization": f"Bearer {channel['api_key']}"}
            else:
                client = httpx.AsyncClient(timeout=httpx.Timeout(channel.get("timeout") or 30))
                try:
                    req = client.build_request("POST", channel["base_url"], json=body, headers=headers)
                    resp = await client.send(req, stream=True)
                except httpx.HTTPError as exc:
                    yield _error_event(f"续轮请求失败（{exc.__class__.__name__}），请重发任务")
                    break
                if resp.status_code != 200:
                    detail = (await resp.aread())[:200]
                    await resp.aclose()
                    await client.aclose()
                    yield _error_event(f"续轮请求返回 {resp.status_code}：{detail!r}")
                    break

            # ── ③ execute：消费一轮上游 SSE，转发文本增量 ──
            round_start = time.time()
            st = {"tool_calls": {}, "encrypted": "", "finish_reason": "",
                  "upstream_error": None, "round_usage": None}
            parts = {"reasoning": "", "output": ""}
            async for out in _forward_round(resp, client, st, parts, needs_mapping, model_name):
                yield out

            round_usage = st["round_usage"] or {"prompt": 0, "completion": 0, "cached": 0}
            usage_total["prompt"] += round_usage["prompt"]
            usage_total["completion"] += round_usage["completion"]
            last_prompt_tokens = round_usage["prompt"] or last_prompt_tokens

            # ── 计费收尾（每轮一次，source="agent"：扣管理员余额/写日志/统计，不写 chat_record）──
            try:
                await _finalize_call(
                    db, user=user, model=epoch_model, channel_name=channel["channel_name"],
                    api_key_id=None, start_ms=round_start,
                    usage={"prompt_tokens": round_usage["prompt"],
                           "completion_tokens": round_usage["completion"],
                           "prompt_tokens_details": {"cached_tokens": round_usage["cached"]}},
                    conversation={"input": body["messages"], "reasoning": parts["reasoning"],
                                  "output": parts["output"]},
                    is_stream=True, source="agent",
                )
            except Exception as exc:
                print(f"[maintain-agent] 本轮计费收尾失败: {exc.__class__.__name__}: {exc}")

            if st["upstream_error"]:
                break

            calls = [st["tool_calls"][i] for i in sorted(st["tool_calls"])]
            truncated = st["finish_reason"] == "length"

            # ── 落库本轮 assistant 消息（含 tool_calls 原文）──
            assistant_tool_calls = [
                {"id": c["id"] or f"call_{round_no}_{n}", "type": "function",
                 "function": {"name": c["name"] or "", "arguments": c["arguments"] or "{}"}}
                for n, c in enumerate(calls)
            ]
            await agent_crud.insert_message(
                db, session_id=session_id, role="assistant",
                content=parts["output"], tool_calls=assistant_tool_calls or None,
                prompt_tokens=round_usage["prompt"], completion_tokens=round_usage["completion"],
            )
            history.append({"role": "assistant", "content": parts["output"],
                            "tool_calls": assistant_tool_calls or None,
                            "_encrypted": st["encrypted"] or None})

            yield _agent_event({"type": "round_end", "round": round_no,
                                "usageSoFar": {"promptTokens": usage_total["prompt"],
                                               "completionTokens": usage_total["completion"]}})

            if not calls:
                break  # 纯文本作答 → 结束

            # ── 工具执行（事件队列随执行实时排空，保证审批卡片先于等待到达前端）──
            for n, c in enumerate(calls):
                call_id = assistant_tool_calls[n]["id"]
                tool_name = c["name"] or ""
                yield _agent_event({"type": "tool_start", "tool": tool_name,
                                    "digest": (c["arguments"] or "")[:120]})

                if truncated:
                    # 截断防御：length 截断的残缺调用一律判失败不执行
                    execution = ToolExecution(
                        ok=False,
                        content=json.dumps(
                            {"isError": True,
                             "message": "模型输出被截断（finish_reason=length），本次工具调用参数可能不完整，已拒绝执行。请重新发起。"},
                            ensure_ascii=False),
                        summary="已拒绝（输出截断防御）", risk="L0", approval_status="none")
                else:
                    task = asyncio.create_task(execute_tool(ctx, tool_name, c["arguments"] or "{}"))
                    while True:
                        await asyncio.wait({task}, timeout=0.1)
                        while event_queue:
                            yield _agent_event(event_queue.pop(0))
                        if task.done():
                            break
                    execution = task.result()

                yield _agent_event({"type": "tool_end", "tool": tool_name, "ok": execution.ok,
                                    "summary": (execution.summary or "")[:200]})

                await agent_crud.insert_message(
                    db, session_id=session_id, role="tool", content=execution.content,
                    tool_call_id=call_id, risk_level=execution.risk,
                    approval_status=execution.approval_status,
                )
                history.append({"role": "tool", "tool_call_id": call_id, "content": execution.content})

            if force_final:
                break

        # ── ④ settle：合成总 usage + 收尾 ──
        yield b"data: " + json.dumps({"choices": [], "usage": {
            "prompt_tokens": usage_total["prompt"],
            "completion_tokens": usage_total["completion"],
        }}, ensure_ascii=False).encode() + b"\n"
        yield b"data: [DONE]\n"
    finally:
        _RUNNING.discard(session_id)
        approval_manager.fail_all_in_session(session_id)  # 未决审批置拒绝，防协程悬挂


async def _first_round(db: AsyncSession, model: dict, channel_names: list[str], body: dict):
    """
    纪元首轮：按轮询顺序尝试渠道，400/422 且带 tools 时剥 tools 降级重试一次
    （不支持函数工具的模型退化为纯对话；工坊同款成熟降级）。返回
    (channel, resp, client, error)——error 非空表示所有渠道失败。
    """
    last_error = "无可用渠道"
    for channel_name in _ordered_channels(model["name"], channel_names):
        channel = await channel_crud.get_by_name(db, channel_name)
        if not channel or not channel.get("status"):
            last_error = f"渠道 {channel_name} 不存在或已停用"
            continue
        headers = {"Authorization": f"Bearer {channel['api_key']}"}
        timeout = httpx.Timeout(channel.get("timeout") or 30)
        for attempt in (body, {k: v for k, v in body.items() if k != "tools"}):
            client = httpx.AsyncClient(timeout=timeout)
            try:
                req = client.build_request("POST", channel["base_url"], json=attempt, headers=headers)
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as exc:
                await client.aclose()
                return None, None, None, f"渠道 {channel['channel_name']} 请求异常：{exc.__class__.__name__}"
            if resp.status_code in (400, 422) and "tools" in attempt:
                detail = (await resp.aread())[:200]
                await resp.aclose()
                await client.aclose()
                body.pop("tools", None)  # 降级：剥掉工具（对 body 生效，续轮不再注入）
                print(f"[maintain-agent] 渠道 {channel['channel_name']} 对 tools 返回 {resp.status_code}：{detail!r}")
                continue
            if resp.status_code != 200:
                detail = (await resp.aread())[:200]
                await resp.aclose()
                await client.aclose()
                last_error = f"渠道 {channel['channel_name']} 返回 {resp.status_code}：{detail.decode('utf-8', 'ignore')}"
                break  # 换下一个渠道
            return channel, resp, client, None
    return None, None, None, last_error


async def _forward_round(resp, client, st: dict, parts: dict,
                         needs_mapping: bool, model_name: str) -> AsyncIterator[bytes]:
    """消费一轮上游 SSE：文本增量转发，tool_calls/usage/finish_reason 只记录（复用工坊解析器）"""
    line_buf = b""
    try:
        async for chunk in resp.aiter_bytes():
            line_buf += chunk
            while b"\n" in line_buf:
                line, line_buf = line_buf.split(b"\n", 1)
                out = _process_line(line, st, parts, needs_mapping, model_name)
                if out is not None:
                    yield out
        if line_buf:
            out = _process_line(line_buf, st, parts, needs_mapping, model_name)
            if out is not None:
                yield out
    finally:
        await resp.aclose()
        await client.aclose()
