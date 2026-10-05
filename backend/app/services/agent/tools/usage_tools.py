"""上游用量域工具（只读）：B1 TokenPlan 用量 / B2 凭证到期

直接在 Python 内调用 operations_service（无 db 依赖的同步纯函数，不走 HTTP 自调用）。
get_operations 是同步阻塞（内含网络请求），必须放线程池执行避免卡事件循环。
"""

import asyncio

from app.services.agent.registry import ToolContext, ToolDef, register
from app.services.operations_service import _load_ops_config, get_operations
from app.utils.token_utils import get_token_expiry

VALID_SCOPES = ("vol", "stepfun", "zai", "zai2", "cc", "antigravity", "all")


def _fmt_usage(usage: dict) -> dict:
    """压缩上游用量结构：只保留 5h/周/月窗口的已用/总额度/重置时间字段"""
    if not isinstance(usage, dict):
        return {"note": "无数据"}
    return usage  # 结构本身已是 {已用, 总额度, 重置时间} 形态，透传由截断器兜底


async def get_upstream_usage(ctx: ToolContext, args: dict) -> dict:
    """B1 上游 TokenPlan 用量查询（对应运维页数据源，antigravity 的 all 走缓存）"""
    scope = args.get("scope") or "all"
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope 仅支持 {'/'.join(VALID_SCOPES)}，收到：{scope}")
    # 同步网络函数放线程池（约 2~15s），60s 兜底由 ToolDef.timeout 控制
    data = await asyncio.to_thread(get_operations, scope)

    windows = {}
    for key, label in (("vol_usage", "火山方舟"), ("stepfun_usage", "阶跃星辰"),
                       ("zai_usage", "智谱账号一"), ("zai2_usage", "智谱账号二"),
                       ("cc_usage", "CommandCode"), ("antigravity_usage", "Antigravity")):
        windows[label] = _fmt_usage(data.get(key))
    return {
        "scope": scope,
        "requestStatus": data.get("status"),
        "usages": windows,
        "_summary": "上游额度用量已获取（详见各窗口 5小时/周/月数据）",
    }


async def get_token_expiry(ctx: ToolContext, args: dict) -> dict:
    """B2 上游凭证到期查询（JWT 解码），临期（≤7 天）标注提醒"""
    def _run() -> dict:
        operation_dict = _load_ops_config()
        return get_token_expiry(operation_dict)

    expiry = await asyncio.to_thread(_run)
    if not isinstance(expiry, dict):
        expiry = {}

    import datetime as _dt
    items = []
    soon = []
    for name, value in expiry.items():
        item = {"credential": name, "expiry": value}
        # 形如 "2026-10-12 03:00:00" 的字符串尝试解析临期判断
        try:
            expire_at = _dt.datetime.strptime(str(value)[:19], "%Y-%m-%d %H:%M:%S")
            days_left = (expire_at - _dt.datetime.now()).days
            item["daysLeft"] = days_left
            if 0 <= days_left <= 7:
                item["urgent"] = True
                soon.append(f"{name}（剩 {days_left} 天）")
        except (TypeError, ValueError):
            pass
        items.append(item)

    summary = "全部凭证有效期充足" if not soon else f"⚠ 临期凭证：{'、'.join(soon)}"
    return {"credentials": items, "_summary": summary}


def register_usage_tools() -> None:
    register(ToolDef(
        name="get_upstream_usage",
        description="查询上游 TokenPlan 用量（5小时/周/月窗口）：火山方舟/阶跃星辰/智谱×2/CommandCode/Antigravity，scope 可单查或 all。",
        parameters={"type": "object", "properties": {
            "scope": {"type": "string", "enum": list(VALID_SCOPES),
                      "description": "上游范围，默认 all（antigravity 的 all 读缓存秒回）"},
        }, "required": []},
        risk="L0", handler=get_upstream_usage, timeout=60,
    ))
    register(ToolDef(
        name="get_token_expiry",
        description="查询上游凭证（JWT）到期时间，临期 ≤7 天自动标注提醒。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_token_expiry, timeout=30,
    ))
