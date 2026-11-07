"""维护 Agent 主循环：服务端托管的后台任务 + 会话事件总线（v0.13.0 任务解耦）

形态总览（详见根目录设计文档）：
- 大脑走本站中转链路（source="agent"：计费照常扣管理员余额、写 logs/统计，
  唯一差异是不写 chat_record——维护对话独立存储在 agent_message）；
- 手是白名单工具（registry），关键写操作过人审阀门（approvals）；
- 任务生命周期与 HTTP 请求解耦：POST /chat 只提交任务（服务端 asyncio Task 托管），
  页面经 GET /stream 订阅事件（回放缓冲 + 实时跟随 + 心跳保活）——页面进出、
  刷新、断网均不影响任务执行，重新进入自动续上；
- 事件格式复刻工坊模式：正文走 OpenAI 风格增量，站内扩展统一挂 agenticapi_agent 字段。

护栏（均按"单次任务"计，一条用户消息触发的完整循环）：
MAX_TOOL_ROUNDS 工具轮上限（末段软提示软着陆）/ AGENT_TASK_COST_LIMIT 任务成本上限
（system_config 可调）/ 工具会话配额（registry 声明）/ 审批 300s 超时 /
finish_reason=length 截断防御（残缺 tool_calls 一律不执行）。
护栏叫停时发 task_paused 事件，前端给出"继续任务"一键续跑。
"""

import asyncio
import json
import time
from collections import deque
from collections.abc import AsyncIterator
from decimal import Decimal

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import asyncSessionLocal
from app.crud import agent as agent_crud
from app.crud import channel as channel_crud
from app.crud import system_config as config_crud
from app.models.user import UserTabel
from app.services.agent import skills as skill_service
from app.services.agent.approvals import approval_manager
from app.services.agent.redact import redact
from app.services.agent.registry import ToolContext, ToolExecution, execute_tool, tools_payload_for
from app.services.relay_service import (
    RelayError, _finalize_call, _ordered_channels, _rewrite_sse_model, compute_cost, resolve_target,
)
from app.services.studio_agent_service import _process_line

MAX_TOOL_ROUNDS = 40            # 单次用户消息触发的工具循环轮数上限
SOFT_WARN_ROUNDS = 5            # 距轮数上限多少轮开始注入软提示（软着陆，不硬腰斩）
DEHYDRATE_KEEP_RECENT = 12      # 脱水窗口：最近 N 条消息不折叠
DEHYDRATE_MIN_CHARS = 600       # 短于该长度的 tool 结果不值得折叠
COMPACT_TRIGGER_RATIO = 0.7     # 估算 token 超过 context_length×70% 触发压缩
COMPACT_TARGET_RATIO = 0.6      # 压缩目标：折叠至 context_length×60% 以下
STREAM_HEARTBEAT_SECONDS = 15   # 订阅流空闲心跳间隔（防 nginx proxy_read_timeout 掐断）

# ── 任务托管：会话 → 后台任务 / 事件总线（防同会话并发跑两个循环）──
_TASKS: dict[int, asyncio.Task] = {}
_BUS: dict[int, "SessionEventBus"] = {}


class SessionEventBus:
    """单会话事件总线：任务侧发布，订阅流（GET /stream）回放 + 实时跟随。

    - publish 同时写入回放缓冲与各订阅者队列（同一对象，订阅侧可按对象身份去重）；
    - 任务结束 finish() 向所有订阅者投递 None 哨兵并清空缓冲（结束后历史走 DB 加载）；
    - 缓冲上限 deque(maxlen)：超长任务（如沙箱大量输出）只保最近事件，回放可能缺失最旧片段。
    """

    def __init__(self, base_messages: int, base_last_id: int = 0):
        self.base_messages = base_messages            # 任务启动前已持久化的消息数（前端裁剪历史用）
        self.base_last_id = base_last_id              # 任务启动前最后一行消息 id（前端按 id 裁剪，行数口径防气泡合并错位）
        self.buffer: deque[bytes] = deque(maxlen=2000)
        self._queues: list[asyncio.Queue] = []
        self.finished = False

    def publish(self, event: bytes) -> None:
        if self.finished:
            return
        self.buffer.append(event)
        for queue in self._queues:
            queue.put_nowait(event)

    def subscribe(self) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue()
        self._queues.append(queue)
        return queue

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        if queue in self._queues:
            self._queues.remove(queue)

    def finish(self) -> None:
        if self.finished:
            return
        self.finished = True
        for queue in self._queues:
            queue.put_nowait(None)
        self.buffer.clear()


def get_bus(session_id: int) -> SessionEventBus | None:
    """取会话事件总线（订阅端点用；None = 无任务可跟随）"""
    return _BUS.get(session_id)


def is_running(session_id: int) -> bool:
    """会话是否有执行中的任务（sessions 列表 running 标记用）"""
    task = _TASKS.get(session_id)
    return bool(task and not task.done())


def stop_task(session_id: int) -> bool:
    """取消会话执行中的任务（停止端点用）。返回是否确实取消了任务。"""
    task = _TASKS.get(session_id)
    if task and not task.done():
        task.cancel()
        return True
    return False


async def stop_task_and_wait(session_id: int, timeout: float = 10.0) -> bool:
    """停止会话任务并等待其退出（删除/清空会话前调用，确保不再有消息写入已删会话）。

    返回是否确实停止了执行中的任务；等待超时也返回（尽力而为，不阻塞删除流程）。
    """
    task = _TASKS.get(session_id)
    if not task or task.done():
        return False
    task.cancel()
    try:
        await asyncio.wait({task}, timeout=timeout)
    except Exception:  # 等待被打断不阻塞调用方
        pass
    return True


def start_task(session_id: int, user_id: int, content: str) -> None:
    """提交后台任务（调用方已完成会话归属校验）。同会话已有任务在跑时抛 RelayError(409)。

    总线在创建任务前预注册（base=-1 表示暂保留全部），消灭"任务已提交、订阅端却
    查不到总线而误判 task_inactive"的竞态窗口；_task_main 装配历史后回填真实裁剪线。
    """
    existing = _TASKS.get(session_id)
    if existing and not existing.done():
        raise RelayError(409, "当前会话正在执行任务，请等待完成、点停止或切换页面后再发送")
    bus = SessionEventBus(base_messages=-1)
    _BUS[session_id] = bus
    _TASKS[session_id] = asyncio.create_task(_task_main(session_id, user_id, content, bus))


async def stream_events(session_id: int, bus: SessionEventBus | None) -> AsyncIterator[bytes]:
    """订阅端点的 SSE 生成器：回放缓冲 → 实时跟随 → [DONE]；空闲期发心跳注释防代理超时。"""
    if bus is None or bus.finished:
        # 无任务可跟随：baseMessages=-1 表示"保留前端已加载的全部历史"，前端直接结束即可
        yield _agent_event({"type": "replay_start", "baseMessages": -1})
        yield _agent_event({"type": "task_inactive"})
        yield b"data: [DONE]\n\n"
        return
    queue = bus.subscribe()
    snapshot = list(bus.buffer)
    seen = {id(evt) for evt in snapshot}  # publish 把同一对象写入缓冲与队列，按身份去重
    try:
        yield _agent_event({"type": "replay_start", "baseMessages": bus.base_messages,
                            "baseLastId": bus.base_last_id})
        for evt in snapshot:
            yield evt
        while True:
            try:
                evt = await asyncio.wait_for(queue.get(), timeout=STREAM_HEARTBEAT_SECONDS)
            except asyncio.TimeoutError:
                yield b": ping\n\n"  # SSE 注释行，仅保活连接
                continue
            if evt is None:
                break
            if id(evt) in seen:
                continue
            yield evt
    finally:
        bus.unsubscribe(queue)
    yield b"data: [DONE]\n\n"


def _agent_event(data: dict) -> bytes:
    """站内扩展事件（前端解析模式复刻 agenticapi_search）"""
    return b"data: " + json.dumps({"agenticapi_agent": data}, ensure_ascii=False).encode() + b"\n"


def _error_event(message: str) -> bytes:
    return b"data: " + json.dumps(
        {"error": {"message": message, "type": "api_error"}}, ensure_ascii=False,
    ).encode() + b"\n"


def _redact_arguments(raw: str) -> str:
    """工具调用参数脱敏（存储/回显用）：JSON 解析后 redact 再序列化，
    解析失败过一遍形态掩码兜底（畸形参数常见于截断场景，残缺 JSON 里也可能嵌密钥）。
    执行路径始终用原始参数——本函数只影响落库与前端展示。
    （防 create_channel / sandbox_exec 命令中嵌入的密钥明文扩散到
    agent_message 与后续每一轮上游请求上下文）"""
    if not raw:
        return raw
    try:
        args = json.loads(raw)
        if isinstance(args, dict):
            return json.dumps(redact(args), ensure_ascii=False)
    except (TypeError, ValueError):
        return redact(raw)
    return raw


def build_system_prompt(session: dict) -> str:
    """system prompt：角色 + 安全规则 + 工具使用守则 + skill 目录（只注入目录不注入全文）"""
    mode = session.get("approval_mode") or "confirm_all"
    mode_desc = {
        "full": "完全权限：所有工具免审批直接执行（删除类等高危工具仍受每会话次数上限约束）",
        "confirm_critical": "部分审批：仅关键操作（删除渠道/模型/技能、新增渠道/模型、沙箱命令）弹审批卡，普通配置修改直行",
        "confirm_all": "需要审批：所有写操作都需管理员在审批卡片上确认",
    }[mode]
    return f"""你是 AgenticAPI 中转站的管理员运维维护 Agent，通过白名单工具对站点进行查询、拨测、数据治理、渠道/模型管理与巡检。

【安全规则（必须遵守）】
1. 只能调用系统提供的白名单工具；唯一例外是 sandbox_exec——在隔离容器沙箱内执行命令（是否弹审批由管理员设定的档位决定）；宿主机上没有任何命令执行能力；
2. 渠道密钥等敏感信息永远不会出现在工具结果里，也不要尝试获取或输出它们；需要密钥的上游操作一律通过引用渠道名的站内工具完成（后端代持密钥注入：list_upstream_models / test_channel / rotate_channel_key）；管理员在对话中提供的密钥仅可用于其明确要求的操作（如创建渠道、轮换密钥），不要复述密钥明文；沙箱连库脚本严禁查询 llm_channels.api_key、user.password 等凭证列；
3. 写操作的审批行为由当前会话档位决定（见下方会话状态）；被拒绝后不要原样重试，先调整方案或说明理由；
4. 删除类工具（delete_channel / delete_model）是两段式：第一次调用必须 dry_run=true 预览影响，向管理员展示预览并确认其同意后，再用 dry_run=false 真删；沙箱内数据清理同样先 COUNT 预览、分批删除（每批 ≤5000 行），严禁 TRUNCATE/DROP；
5. 不删除用户、不改用户余额——这些请引导管理员去对应管理页操作。

【工作守则】
- 工具失败会以 isError 数据返回：读错误信息修正参数后重试（如纠正渠道名拼写），或换一个途径；
- 批量操作前先小范围抽查（如 test_channel scope=one），确认没问题再扩大范围；
- 巡检/排障/治理等任务优先匹配下述技能目录，用 load_skill 读取 SOP 后按流程执行，偏离流程要说明理由；
- 沙箱（sandbox_exec）兜底两类场景：①无需密钥的 API 端点测试与脚本化诊断（管理员当场提供密钥的场景除外）；②站内数据统计/导出/清理（容器内已注入站内 MySQL 连接环境变量与 pymysql，按 data-governance 技能脚本执行）；渠道密钥永不进入沙箱——需要密钥的上游操作一律走站内工具（后端代持密钥执行）；定制工具能做的不要用沙箱做，命令保持简短幂等、输出大时用 head/tail/jq 截取；
- 发现上游还有哪些可接入模型：先用 list_upstream_models 拉上游 /models 清单对照差集；上游无 /models 路由（404，agent plan 专用端点常见）时，改用 test_channel 对候选模型名逐名试拨（scope=one，声明列表外的模型同样可拨）；
- 新上游上线标准链路：create_channel（管理员提供密钥）→ test_channel 拨测 → create_model（含定价）→ test_model 端到端验证，各步审批卡会呈现完整配置；
- 联网查证（上游故障公告/定价变更/报错信息）用 web_search；
- 任务被轮数/成本护栏叫停时，输出三段式小结：已完成事项 / 未完成事项 / 建议的续作步骤，管理员可一键继续；
- 回答使用中文，运维数据用简洁结构化格式（表格/列表），金额保留 4 位小数。

【技能目录（按需 load_skill 加载全文）】
{skill_service.catalog_text()}

【当前会话状态】
- 驱动模型：{session.get("model_name")}（切换驱动模型请让管理员使用页面顶部选择器，下一轮生效）
- 审批档位：{mode_desc}
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
    tool 结果替换为占位摘要；窗口外的超长 tool_calls 参数同样折叠为占位（参数也占
    上下文，大参数工具如 save_skill 草稿可达 32KB）。只缩内容、不删消息——
    tool_call/tool_result 配对关系完整保留（OpenAI 协议要求 assistant.tool_calls
    后必须跟齐 tool 消息，折叠只改 arguments 不动 id/type）。
    """
    cutoff = len(messages) - DEHYDRATE_KEEP_RECENT
    out: list[dict] = []
    for idx, msg in enumerate(messages):
        if idx < cutoff:
            if (msg.get("role") == "tool"
                    and len(msg.get("content") or "") > DEHYDRATE_MIN_CHARS):
                placeholder = f"[工具结果已折叠] {_extract_summary(msg.get('content') or '')}"
                out.append({**msg, "content": placeholder})
                continue
            calls = msg.get("tool_calls")
            if msg.get("role") == "assistant" and calls:
                args_len = sum(len(((tc or {}).get("function") or {}).get("arguments") or "")
                               for tc in calls)
                if args_len > DEHYDRATE_MIN_CHARS:
                    folded = [{**tc, "function": {**((tc or {}).get("function") or {}),
                                                  "arguments": "[历史调用参数已折叠，如需细节请重新调用工具获取]"}}
                              for tc in calls]
                    out.append({**msg, "tool_calls": folded})
                    continue
        out.append(msg)
    return out


def _msg_chars(messages: list[dict]) -> int:
    """消息字符量（content + tool_calls 参数）：token 估算与压缩判断共用口径"""
    total = 0
    for m in messages:
        total += len(str(m.get("content") or ""))
        for tc in (m.get("tool_calls") or []):
            total += len((((tc or {}).get("function") or {}).get("arguments")) or "")
    return total


def _estimate_tokens(messages: list[dict], last_prompt_tokens: int) -> int:
    """token 估算（采纳 pi 计账法）：最近官方 prompt_tokens + 其后新增消息字符数/4
    （tool_calls 参数计入字符量）。主循环只在首轮做全量估算，后续轮以
    last_prompt_tokens 为锚、仅传入上轮 prompt 之后新增的消息。"""
    return last_prompt_tokens + _msg_chars(messages) // 4


def _compact_messages(messages: list[dict], context_length: int) -> list[dict]:
    """
    压缩兜底（脱水后估算仍超窗）：沿 user 消息边界从最旧开始整轮折叠，
    直到估算 token 降到 context_length×COMPACT_TARGET_RATIO 以下
    （或只剩一个 user 轮不可再折）。切点永远对齐 user 消息边界，不拆散
    assistant.tool_calls ↔ tool 配对；折叠历史以一条代码生成的摘要消息替代
    （不追加模型调用，避免压缩本身失败把主任务拖死）。
    """
    msgs = messages
    target_chars = int(context_length * COMPACT_TARGET_RATIO * 4)  # token→字符粗换算（1 token≈4 字符）
    folded: list[dict] = []
    for _ in range(500):  # 防御性上限，正常折叠几轮即达标
        if _msg_chars(msgs) <= target_chars:
            break
        user_positions = [i for i, m in enumerate(msgs) if m.get("role") == "user"]
        if len(user_positions) < 2:
            break  # 只剩一个 user 轮（含最新输入），不可再折
        cut = user_positions[1]          # 折掉 system 之后最旧的完整一轮
        folded.extend(msgs[1:cut])
        msgs = [msgs[0]] + msgs[cut:]
    if not folded:
        return messages

    summary_lines = ["[较早的对话历史已折叠] 此前完成的主要动作："]
    for msg in folded:
        if msg.get("role") == "assistant" and msg.get("tool_calls"):
            names = [tc.get("function", {}).get("name") for tc in msg["tool_calls"]]
            summary_lines.append(f"- 调用过工具：{', '.join(n for n in names if n)}")
        elif msg.get("role") == "tool":
            summary_lines.append(f"- 工具结果摘要：{_extract_summary(msg.get('content') or '')[:120]}")
        elif msg.get("role") == "assistant":
            summary_lines.append(f"- 助手结论：{(msg.get('content') or '')[:120]}")
        elif msg.get("role") == "user":
            summary_lines.append(f"- 管理员指示：{(msg.get('content') or '')[:120]}")
    return [msgs[0], {"role": "user", "content": "\n".join(summary_lines[:60])}] + msgs[1:]


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


async def _task_main(session_id: int, user_id: int, content: str, bus: "SessionEventBus") -> None:
    """后台任务入口：自持 DB 会话（任务生命周期独立于请求），装配上下文后进入主循环。

    任何退出路径（正常结束 / 异常 / 取消 / 会话已删除）都保证：事件总线收尾
    （finish 幂等，投递结束哨兵）、未决审批置拒绝、_TASKS / _BUS 托管条目清理
    （异常任务的 traceback 会钉住整段会话历史，不清理则内存滞留）。
    """
    task = asyncio.current_task()
    try:
        async with asyncSessionLocal() as db:
            session = await agent_crud.get_session(db, session_id)
            user = await db.get(UserTabel, user_id)
            if session is None or user is None:
                return  # 会话/用户在任务排队期间被删除，静默退出（finally 统一收尾）

            # ── ① queue：修复中断历史 + 落库用户消息 + 装配历史 ──
            await repair_dangling_tool_calls(db, session_id)
            # 用户消息落库用脱敏版（库里/导出不留密钥明文）；LLM 上下文回填原文
            #（密钥轮换等场景模型需要读到管理员提供的明文钥，执行侧语义与 tool_calls 一致）
            await agent_crud.insert_message(db, session_id=session_id, role="user",
                                            content=redact(content))
            history: list[dict] = await agent_crud.list_messages(db, session_id)
            if history and history[-1]["role"] == "user":
                history[-1]["content"] = content

            session_dict = {
                "id": session_id,
                "model_name": session.model_name,
                "approval_mode": agent_crud.resolve_approval_mode(session),
            }
            # 任务启动前已持久化的消息裁剪线（行数 + 末行 id）：订阅流回放时前端据此
            # 裁掉已从 DB 加载的任务期消息避免重复渲染（id 口径不受气泡合并影响）
            bus.base_messages = len(history)
            bus.base_last_id = history[-1]["id"] if history else 0

            async def emit(event: dict) -> None:
                if event.get("type") == "sandbox_output" and isinstance(event.get("chunk"), str):
                    # 沙箱实时输出过脱敏再进总线（回放缓冲/订阅者的唯一入口，密钥闭环不留破口）
                    event = {**event, "chunk": redact(event["chunk"])}
                bus.publish(_agent_event(event))

            ctx = ToolContext(db=db, user=user, session=session_dict, emit=emit)
            counts = await agent_crud.count_tool_executions(db, session_id)
            legacy_l2 = counts.pop("_legacy_l2", 0)
            if legacy_l2:
                # tool_name 列上线前的旧 L2 记录只有 delete_channel / delete_model 两个来源，
                # 无法区分归属，保守起见同时计入两者的配额
                for name in ("delete_channel", "delete_model"):
                    counts[name] = counts.get(name, 0) + legacy_l2
            ctx.used_counts = counts

            try:
                await _execute(db, session_dict, user, content, history, ctx, bus)
            except Exception as exc:
                bus.publish(_error_event(f"任务异常终止：{exc.__class__.__name__}: {exc}"))
    except asyncio.CancelledError:
        # 停止端点 / 服务停机取消：下面 finally 完成总线收尾与审批清理，这里只放行取消
        raise
    finally:
        bus.finish()  # 幂等：投递结束哨兵并清空回放缓冲
        approval_manager.fail_all_in_session(session_id)
        if _TASKS.get(session_id) is task:
            _TASKS.pop(session_id, None)
        if _BUS.get(session_id) is bus:
            _BUS.pop(session_id, None)


async def _execute(db: AsyncSession, session_dict: dict, user: UserTabel, content: str,
                   history: list[dict], ctx: ToolContext, bus: SessionEventBus) -> None:
    """主循环（四阶段迭代 + 事件经总线发布）。任务级异常由 _task_main 统一收尾。"""
    session_id = session_dict["id"]

    # 任务成本护栏（单次任务口径；配置链 system_config → 默认值，管理员设置页可调）
    cost_limit = await config_crud.get_agent_task_cost_limit(db)
    cost_used = Decimal("0")

    usage_total = {"prompt": 0, "completion": 0}
    last_prompt_tokens = 0
    pending_msgs: list[dict] = []        # 上轮 prompt 之后新增的消息（token 估算增量，锚点更新后清空）
    epoch_model: dict | None = None      # 当前模型纪元（模型配置 dict）
    epoch_channels: list[str] = []
    channel: dict | None = None          # 续轮优先复用的当前渠道（失败才换）
    tools_degraded = False               # 上游 400/422 剥 tools 后本任务不再注入工具
    notices: list[str] = []              # 护栏触发的系统提示（追加为 user 消息，不落库）
    paused_reason: str | None = None     # 护栏叫停原因（round_limit / cost_limit），发 task_paused 用

    try:
        round_no = 0
        while True:
            round_no += 1
            force_final = False

            # ── 每轮重读会话行：管理员可在任务运行中切换模型 / 审批档位（下一轮生效）──
            fresh = await agent_crud.get_session(db, session_id)
            if fresh is None:
                bus.publish(_error_event("会话已被删除，任务终止"))
                break
            session_dict["model_name"] = fresh.model_name
            session_dict["approval_mode"] = agent_crud.resolve_approval_mode(fresh)

            # ── 轮次与成本护栏 ──
            if round_no > MAX_TOOL_ROUNDS:
                notices.append(f"已达到工具轮数上限（{MAX_TOOL_ROUNDS}），请立即停止调用工具，"
                               f"输出三段式收尾小结：①已完成事项 ②未完成事项 ③建议的续作步骤。")
                force_final = True
                paused_reason = paused_reason or "round_limit"
            elif round_no > MAX_TOOL_ROUNDS - SOFT_WARN_ROUNDS:
                notices.append(f"提示：本轮为第 {round_no}/{MAX_TOOL_ROUNDS} 轮，剩余轮次不多，"
                               f"请优先完成关键步骤、尽快收敛。")
            if cost_used > cost_limit:
                notices.append(f"本任务成本已达上限（{cost_limit} 元），请立即停止调用工具，"
                               f"输出三段式收尾小结：①已完成事项 ②未完成事项 ③建议的续作步骤。")
                force_final = True
                paused_reason = paused_reason or "cost_limit"

            # ── ② prepare：模型纪元检查 + 历史脱水 + 请求装配（唯一转换边界）──
            if epoch_model is None or epoch_model.get("name") != session_dict["model_name"]:
                try:
                    epoch_model, epoch_channels = await resolve_target(
                        db, {"model": session_dict["model_name"],
                             "messages": [{"role": "user", "content": "ping"}]},
                        user, source="agent")
                except RelayError as exc:
                    bus.publish(_error_event(f"模型解析失败：{exc.message}"))
                    break
                channel = None  # 新纪元重新选渠道
                tools_degraded = False  # 新模型重新探测工具支持（旧纪元的降级结论不延续）

            llm_messages = _history_to_llm(history)
            for notice in notices:
                llm_messages.append({"role": "user", "content": notice})
                pending_msgs.append({"role": "user", "content": notice})
            notices = []  # 提示只注入一次，避免后续轮次重复携带
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

            # 上下文超窗保护：估算 = 最近一轮官方 prompt_tokens（锚点，已含全部历史与 schema）
            #   + 其后新增内容字符（output / tool 结果 / 插话，tool_calls 参数计入）÷ 4；
            # 首轮锚点为 0、对装配后的消息全量估算。脱水后估算仍超 context_length×70% 时压缩兜底
            context_length = int(epoch_model.get("context_length") or 128_000)
            if last_prompt_tokens:
                est_tokens = last_prompt_tokens + _msg_chars(pending_msgs) // 4
            else:
                est_tokens = _estimate_tokens(llm_messages, 0)
            if est_tokens > context_length * COMPACT_TRIGGER_RATIO:
                llm_messages = _compact_messages(llm_messages, context_length)
                body["messages"] = llm_messages

            # ── 渠道选择：优先复用上一轮渠道（重试一次），失败按轮询顺序遍历其余渠道 ──
            #（首轮无偏好渠道即全量遍历；400/422 剥 tools 降级对 body 生效，续轮不再注入）
            channel, resp, client, err = await _open_round(
                db, epoch_model, epoch_channels, body,
                prefer_name=channel["channel_name"] if channel else None)
            if channel is None:
                bus.publish(_error_event(f"所有上游渠道调用失败：{err}"))
                break
            if include_tools and "tools" not in body and not tools_degraded:
                # 降级发生：上游不支持 tools，本任务后续轮次不再注入并提示模型
                tools_degraded = True
                history.append({"role": "user", "content":
                                "（系统提示：当前驱动模型不支持函数工具调用，本轮起仅可纯对话；"
                                "建议让管理员在页面顶部选择器切换到支持工具调用的模型后继续任务）"})

            # ── ③ execute：消费一轮上游 SSE，文本增量经总线发布 ──
            round_start = time.time()
            st = {"tool_calls": {}, "encrypted": "", "finish_reason": "",
                  "upstream_error": None, "round_usage": None}
            parts = {"reasoning": "", "output": ""}
            async for out in _forward_round(resp, client, st, parts, needs_mapping, model_name):
                bus.publish(out)

            round_usage = st["round_usage"] or {"prompt": 0, "completion": 0, "cached": 0}
            usage_total["prompt"] += round_usage["prompt"]
            usage_total["completion"] += round_usage["completion"]
            last_prompt_tokens = round_usage["prompt"] or last_prompt_tokens
            pending_msgs = []  # 锚点已更新至本轮 prompt，之后的输出/工具结果作为新增量重新累计

            # 任务成本累计（与 _finalize_call 同口径，护栏用；实际扣费仍由 _finalize_call 完成）
            try:
                round_cost, _, _, _ = compute_cost(epoch_model, {
                    "prompt_tokens": round_usage["prompt"],
                    "completion_tokens": round_usage["completion"],
                    "prompt_tokens_details": {"cached_tokens": round_usage["cached"]},
                })
                cost_used += round_cost
            except Exception:
                pass  # 成本估算失败不影响主流程（护栏退化为不触发）

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

            # ── 落库本轮 assistant 消息（tool_calls 参数脱敏：执行用原文，落库/回显/历史用掩码版）──
            assistant_tool_calls = [
                {"id": c["id"] or f"call_{round_no}_{n}", "type": "function",
                 "function": {"name": c["name"] or "",
                              "arguments": _redact_arguments(c["arguments"] or "{}")}}
                for n, c in enumerate(calls)
            ]
            await agent_crud.insert_message(
                db, session_id=session_id, role="assistant",
                content=parts["output"], tool_calls=assistant_tool_calls or None,
                prompt_tokens=round_usage["prompt"], completion_tokens=round_usage["completion"],
            )
            assistant_msg = {"role": "assistant", "content": parts["output"],
                             "tool_calls": assistant_tool_calls or None,
                             "_encrypted": st["encrypted"] or None}
            history.append(assistant_msg)
            pending_msgs.append(assistant_msg)

            bus.publish(_agent_event({"type": "round_end", "round": round_no,
                                      "usageSoFar": {"promptTokens": usage_total["prompt"],
                                                     "completionTokens": usage_total["completion"]},
                                      # 上下文水位口径：最近一轮官方 prompt_tokens ≈ 当前上下文真实占用
                                      #（usageSoFar 是累计消耗，含已被脱水的历史，不能当水位用）
                                      "contextTokens": last_prompt_tokens}))

            if not calls:
                break  # 纯文本作答 → 结束

            # ── 工具执行（事件经总线实时发布，审批卡片即时到达订阅端）──
            for n, c in enumerate(calls):
                call_id = assistant_tool_calls[n]["id"]
                tool_name = c["name"] or ""
                bus.publish(_agent_event({"type": "tool_start", "tool": tool_name,
                                          "digest": _redact_arguments(c["arguments"] or "")[:120]}))

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
                    execution = await execute_tool(ctx, tool_name, c["arguments"] or "{}")

                bus.publish(_agent_event({"type": "tool_end", "tool": tool_name, "ok": execution.ok,
                                          "summary": (execution.summary or "")[:200]}))

                await agent_crud.insert_message(
                    db, session_id=session_id, role="tool", content=execution.content,
                    tool_call_id=call_id, tool_name=(tool_name or "")[:64] or None,
                    risk_level=execution.risk,
                    approval_status=execution.approval_status,
                )
                tool_msg = {"role": "tool", "tool_call_id": call_id, "content": execution.content}
                history.append(tool_msg)
                pending_msgs.append(tool_msg)

            if force_final:
                break

        # ── ④ settle：合成总 usage + 收尾（护栏叫停时发 task_paused，前端给"继续任务"入口）──
        if paused_reason:
            bus.publish(_agent_event({"type": "task_paused", "reason": paused_reason,
                                      "round": round_no}))
        bus.publish(b"data: " + json.dumps({"choices": [], "usage": {
            "prompt_tokens": usage_total["prompt"],
            "completion_tokens": usage_total["completion"],
        }}, ensure_ascii=False).encode() + b"\n")
        bus.publish(b"data: [DONE]\n")
    finally:
        # 总线收尾（finish 投递结束哨兵）与未决审批置拒绝由 _task_main 的 finally 统一负责
        pass


async def _open_round(db: AsyncSession, model: dict, channel_names: list[str],
                      body: dict, prefer_name: str | None = None):
    """
    发起一轮上游请求（首轮与续轮统一入口）。

    - prefer_name 非空时优先复用该渠道（网络异常同渠道重试一次），仍失败按轮询
      顺序遍历其余渠道（failover）——长任务不再因单渠道一次抖动而中断；
    - 400/422 且请求带 tools 时先试探性剥 tools 同渠道重试：仅当剥除后立刻成功
      才确认"模型/渠道不支持函数工具"（调用方据 "tools" not in body 感知降级）；
      剥除后仍失败则还原 tools 再试下一渠道——400/422 也可能是超窗或参数被拒，
      不能让单渠道一次拒绝把整个任务误降级为纯对话。

    返回 (channel, resp, client, error)——error 非空表示所有渠道失败。
    """
    last_error = "无可用渠道"
    names = list(_ordered_channels(model["name"], channel_names))
    if prefer_name:
        if prefer_name in names:
            names.remove(prefer_name)
        names.insert(0, prefer_name)
    for channel_name in names:
        channel = await channel_crud.get_by_name(db, channel_name)
        if not channel or not channel.get("status"):
            last_error = f"渠道 {channel_name} 不存在或已停用"
            continue
        headers = {"Authorization": f"Bearer {channel['api_key']}"}
        timeout = httpx.Timeout(channel.get("timeout") or 30)
        popped_tools: dict | None = None  # 本渠道试探性剥除的 tools（失败还原用）
        for _attempt in range(2):  # 同渠道最多两次（网络抖动重试）；换渠道不重试
            client = httpx.AsyncClient(timeout=timeout)
            try:
                req = client.build_request("POST", channel["base_url"], json=body, headers=headers)
                resp = await client.send(req, stream=True)
            except httpx.HTTPError as exc:
                await client.aclose()
                if _attempt == 0:
                    continue
                last_error = f"渠道 {channel['channel_name']} 请求异常：{exc.__class__.__name__}"
                break
            if resp.status_code in (400, 422) and "tools" in body:
                detail = (await resp.aread())[:200]
                await resp.aclose()
                await client.aclose()
                popped_tools = body.pop("tools")  # 试探性剥除，同渠道重试
                print(f"[maintain-agent] 渠道 {channel['channel_name']} 对 tools 返回 {resp.status_code}：{detail!r}")
                continue
            if resp.status_code != 200:
                detail = (await resp.aread())[:200]
                await resp.aclose()
                await client.aclose()
                last_error = f"渠道 {channel['channel_name']} 返回 {resp.status_code}：{detail.decode('utf-8', 'ignore')}"
                break  # 换下一个渠道
            return channel, resp, client, None
        if popped_tools is not None and "tools" not in body:
            body["tools"] = popped_tools  # 还原：剥除后仍未成功，降级结论不随本渠道失效而成立
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
