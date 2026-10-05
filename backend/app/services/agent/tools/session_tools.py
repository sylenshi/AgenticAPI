"""会话域工具：F4 模型切换（站内任意模型驱动，管理员 vip 全模型可用）

切换立即写 agent_session.model_name，下一轮请求生效；主循环在轮间隙检测
会话模型变化并重解析渠道（模型纪元切换）。
"""

from app.crud import agent as agent_crud
from app.crud import model as model_crud
from app.services.agent.registry import ToolContext, ToolDef, register


async def switch_model(ctx: ToolContext, args: dict) -> dict:
    """切换当前会话的驱动模型（下一轮请求生效），上下文原样复用（标准 OpenAI 报文）"""
    model_name = (args.get("model_name") or "").strip()
    if not model_name:
        raise ValueError("model_name 不能为空")
    model = await model_crud.get_by_name(ctx.db, model_name)
    if not model or not model.get("status"):
        raise ValueError(f"模型 {model_name} 不存在或已停用，可用模型可用 get_model_info 查询")

    old_model = ctx.session.get("model_name")
    if model_name == old_model:
        return {"ok": True, "from": old_model, "to": model_name, "changed": False,
                "_summary": f"当前会话已在使用 {model_name}，无需切换"}

    await agent_crud.update_session(ctx.db, ctx.session["id"], {"model_name": model_name})
    ctx.session["model_name"] = model_name  # 主循环轮间隙检测到变化后重解析渠道
    await ctx.emit({"type": "model_switched", "from": old_model, "to": model_name})
    return {
        "ok": True, "from": old_model, "to": model_name, "changed": True,
        "contextLength": model.get("context_length"),
        "_summary": f"驱动模型已切换：{old_model} → {model_name}（下一轮生效）",
    }


def register_session_tools() -> None:
    register(ToolDef(
        name="switch_model",
        description="切换当前会话的驱动模型为站内任意出站模型（下一轮请求生效）。当任务需要更强推理/更大窗口/工具调用能力时使用。",
        parameters={"type": "object", "properties": {
            "model_name": {"type": "string", "description": "目标模型名（可用 get_model_info 查询全部）"},
        }, "required": ["model_name"]},
        risk="L0", handler=switch_model,
    ))
