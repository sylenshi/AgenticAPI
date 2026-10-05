"""工具注册表与执行器流水线（唯一扩展点）

每次工具调用必经的流水线：
  JSON 参数解析 → 必填字段校验 → 风险阀门（L0 直行 / L1·L2 审批）
  → asyncio 超时执行 → redact() 递归脱敏 → 8KB 摘要式截断 → logs 审计。

风险分级：
- L0 只读：直接执行；
- L1 低危写：审批卡片，会话开启 auto_approve_l1 时可跳过（always_confirm 工具除外）；
- L2 高危写：强制审批 + 会话内执行上限 5 次（enable_l2 关闭时工具不注入）。

Error as Data：任何失败都不抛异常给主循环，统一返回 {isError: true, message}。
注册方向：registry 只定义框架（本文件不 import 任何工具域）；各工具域模块
import ToolDef/register 完成注册，tools/__init__.py 聚合触发——无循环依赖。
"""

import asyncio
import json
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import log as log_crud
from app.services.agent.approvals import approval_manager
from app.services.agent.redact import redact

# 结果序列化上限：超出做"摘要式截断"（保留首尾条目 + 计数），明细走导出文件
RESULT_MAX_BYTES = 8 * 1024
# L2 工具每会话执行上限
L2_PER_SESSION_LIMIT = 5


class ApprovalRejected(Exception):
    """管理员拒绝/超时：携带 verdict（rejected / timeout）供落库审批轨迹"""

    def __init__(self, verdict: str, message: str):
        super().__init__(message)
        self.verdict = verdict


@dataclass
class ToolContext:
    """一次会话流内的工具执行上下文（由主循环构造）"""
    db: AsyncSession
    user: Any                      # 管理员 UserTabel（含 id/username/is_admin）
    session: dict                  # {id, model_name, auto_approve_l1, enable_l2}
    emit: Callable[[dict], Awaitable[None]]  # SSE 事件回调（tool_progress / model_switched 等）
    l2_used: int = 0               # 本会话已执行的 L2 次数（含历史，主循环预填）
    extra_secrets: list = field(default_factory=list)  # 已知密钥明文（redact_text 兜底用）


@dataclass
class ToolDef:
    """声明式工具注册项"""
    name: str
    description: str
    parameters: dict               # OpenAI function calling 的 JSON Schema
    risk: str                      # L0 / L1 / L2
    handler: Callable
    timeout: int = 30              # 自声明超时（秒），批测类 180~300
    always_confirm: bool = False   # 强制人审（不受 L1 自动批准豁免）
    preview: Callable | None = None  # async (ctx, args) -> str 审批卡片影响预览


@dataclass
class ToolExecution:
    """执行器输出：主循环据此回传模型并落库"""
    ok: bool
    content: str        # 回传模型的 JSON 文本（已脱敏/截断）
    summary: str        # 一句话摘要（tool_end 事件 + 脱水占位用）
    risk: str = "L0"
    approval_status: str = "none"


# 全局注册表：各工具域模块在 import 时调用 register() 填充
TOOL_REGISTRY: dict[str, ToolDef] = {}


def register(tool: ToolDef) -> None:
    """注册一个工具（同名覆盖，供测试与扩展）"""
    TOOL_REGISTRY[tool.name] = tool


def _ensure_tools_loaded() -> None:
    """确保工具域已 import（触发注册）。放在函数内惰性执行，避免注册表框架反向依赖工具域。"""
    import app.services.agent.tools  # noqa: F401


def _error(message: str, risk: str = "L0", approval_status: str = "none") -> ToolExecution:
    payload = {"isError": True, "message": message}
    return ToolExecution(ok=False, content=json.dumps(payload, ensure_ascii=False),
                         summary=f"失败：{message[:120]}", risk=risk, approval_status=approval_status)


def truncate_result(result: Any) -> str:
    """结果序列化 + 摘要式截断：超过 8KB 时保留列表首尾条目与计数信息"""
    def _dumps(obj) -> str:
        return json.dumps(obj, ensure_ascii=False, default=str)

    text = _dumps(result)
    if len(text.encode("utf-8")) <= RESULT_MAX_BYTES:
        return text

    # 列表型明细截断：保留前 3 后 2 条 + 计数说明（报错结论通常在末尾，尾部优先保留）
    if isinstance(result, dict):
        for key in ("results", "failures", "list", "items"):
            value = result.get(key)
            if isinstance(value, list) and len(value) > 5:
                head, tail = value[:3], value[-2:]
                trimmed = dict(result)
                trimmed[key] = head + [f"[…已截断：中间 {len(value) - 5} 条省略，明细可请求导出文件…]"] + tail
                trimmed["truncated"] = True
                new_text = _dumps(trimmed)
                if len(new_text.encode("utf-8")) <= RESULT_MAX_BYTES:
                    return new_text
        # 仍然超限：退化为摘要对象
        fallback: dict = {"truncated": True,
                          "message": "结果过大已整体折叠，请改用导出类工具或缩小查询范围"}
        if isinstance(result.get("_summary"), str):
            fallback["_summary"] = result["_summary"]
        return _dumps(fallback)

    # 字符串/其他：保头尾
    keep = (RESULT_MAX_BYTES // 2) - 100
    return text[:keep] + f"\n[…中间截断，原文 {len(text)} 字符…]\n" + text[-keep:]


def _make_summary(sanitized: Any) -> str:
    """从脱敏结果里提炼一句话摘要（tool_end 事件与脱水占位共用）"""
    if isinstance(sanitized, dict):
        for key in ("_summary", "message", "error"):
            value = sanitized.get(key)
            if isinstance(value, str) and value.strip():
                return value[:200]
        if "ok" in sanitized:
            return "执行成功" if sanitized["ok"] else "执行失败"
    return str(sanitized)[:200]


async def _validate_required(tool: ToolDef, args: dict) -> str | None:
    """按 JSON Schema 的 required 声明做必填校验，返回错误信息（None = 通过）"""
    for key in tool.parameters.get("required", []):
        if key not in args or args[key] in (None, "", []):
            expected = tool.parameters.get("properties", {}).get(key, {}).get("type", "?")
            return f"缺少必填参数 {key}（类型 {expected}），请补全后重试"
    return None


async def _run_with_gate(ctx: ToolContext, tool: ToolDef, args: dict) -> Any:
    """风险阀门 + 超时执行（不含参数校验与序列化）"""
    if tool.risk == "L2" and not ctx.session.get("enable_l2"):
        raise PermissionError("本会话已关闭 L2 高危工具（只读模式），如需执行请在右侧面板打开 L2 开关")

    if tool.risk == "L2" and ctx.l2_used >= L2_PER_SESSION_LIMIT:
        raise PermissionError(
            f"本会话 L2 高危操作已达上限（{L2_PER_SESSION_LIMIT} 次），请改走管理页操作或新建会话")

    # 是否需要审批卡片：L2 恒审；L1 默认审，会话开启自动批准可跳过（always_confirm 除外）
    need_approval = tool.risk == "L2" or tool.always_confirm or not ctx.session.get("auto_approve_l1")

    if tool.risk != "L0" and need_approval:
        impact = ""
        if tool.preview:
            try:
                impact = await tool.preview(ctx, args)
            except Exception as exc:
                impact = f"（预览生成失败：{exc.__class__.__name__}）"
        pending = approval_manager.create(
            session_id=ctx.session["id"], user_id=ctx.user.id,
            tool=tool.name, args=args, risk=tool.risk, impact=impact,
        )
        await ctx.emit({"type": "confirm_required", **pending.to_event_payload()})
        verdict = await approval_manager.wait(pending)
        await ctx.emit({"type": "confirm_resolved", "approvalId": pending.id, "result": verdict})
        if verdict != "approved":
            message = {
                "rejected": "管理员拒绝了本次操作。请调整方案或向管理员说明必要性，不要立即原样重试。",
                "timeout": "审批超时（300s）自动拒绝。请重新发起并等待管理员批准。",
            }[verdict]
            raise ApprovalRejected(verdict, message)

    return await asyncio.wait_for(tool.handler(ctx, args), timeout=tool.timeout)


async def execute_tool(ctx: ToolContext, name: str, arguments_raw: str) -> ToolExecution:
    """工具执行总入口。任何失败都以 isError 数据返回（Error as Data），不抛异常。"""
    _ensure_tools_loaded()

    tool = TOOL_REGISTRY.get(name)
    if not tool:
        return _error(f"未知工具 {name}，可用工具见系统提示词目录")

    try:
        args = json.loads(arguments_raw) if arguments_raw and arguments_raw.strip() else {}
        if not isinstance(args, dict):
            return _error(f"工具 {name} 的 arguments 必须是 JSON 对象，收到：{type(args).__name__}")
    except json.JSONDecodeError as exc:
        return _error(f"工具 {name} 的 arguments 不是合法 JSON（{exc.msg}，位置 {exc.pos}），请修正后重试",
                      risk=tool.risk)

    missing = await _validate_required(tool, args)
    if missing:
        return _error(f"工具 {name}：{missing}", risk=tool.risk)

    approval_status = "none"
    try:
        result = await _run_with_gate(ctx, tool, args)
        if tool.risk == "L2":
            ctx.l2_used += 1
            approval_status = "approved"
    except ApprovalRejected as exc:
        return _error(str(exc), risk=tool.risk, approval_status=exc.verdict)
    except PermissionError as exc:
        return _error(str(exc), risk=tool.risk)
    except asyncio.TimeoutError:
        return _error(f"工具 {name} 执行超时（{tool.timeout}s），请缩小范围后重试（如分批测试）", risk=tool.risk)
    except ValueError as exc:  # 参数语义错误：可行动反馈
        return _error(f"工具 {name}：{exc}", risk=tool.risk)
    except Exception as exc:  # 兜底：未知异常也转为数据
        return _error(f"工具 {name} 执行失败：{exc.__class__.__name__}: {exc}"[:500], risk=tool.risk)

    sanitized = redact(result if result is not None else {"ok": True})
    content = truncate_result(sanitized)
    summary = _make_summary(sanitized)

    # 审计：每次工具执行写一条 admin 日志（审批拒绝的轨迹已在 agent_message 表，不重复写）
    try:
        args_digest = json.dumps(redact(args), ensure_ascii=False, default=str)[:200]
        await log_crud.write_log(
            db=ctx.db, type="admin", action="agent_tool",
            user_id=ctx.user.id, username=ctx.user.username,
            detail=f"[{tool.risk}] {name}({args_digest}) → {summary}",
        )
    except Exception:
        pass  # 审计写失败不影响工具结果回传

    return ToolExecution(ok=True, content=content, summary=summary,
                         risk=tool.risk, approval_status=approval_status)


def tools_payload_for(session: dict) -> list[dict]:
    """按会话设置裁剪注入模型的 tools 列表（enable_l2 关闭 = 只读模式，不注入 L2）"""
    _ensure_tools_loaded()
    payload = []
    for tool in TOOL_REGISTRY.values():
        if tool.risk == "L2" and not session.get("enable_l2"):
            continue
        payload.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description,
                "parameters": tool.parameters,
            },
        })
    return payload
