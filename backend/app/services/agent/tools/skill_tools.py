"""技能域工具：F5 load / list / save / delete（教学保存已决策开放）

save_skill / delete_skill 带 always_confirm：写入内容影响后续所有会话（技能池
全局共享），即使会话开启"L1 自动批准"也强制走审批卡片，且卡片展示完整草稿。
"""

from app.crud import channel as channel_crud
from app.services.agent import skills
from app.services.agent.registry import ToolContext, ToolDef, register


async def load_skill(ctx: ToolContext, args: dict) -> dict:
    """按需读取 skill 全文（system prompt 只注入目录，控制固定 token 开销）"""
    name = (args.get("name") or "").strip()
    content = skills.load_skill(name)
    if content is None:
        available = ", ".join(s.name for s in skills.list_skills())
        raise ValueError(f"skill {name or '(空)'} 不存在。可用技能：{available}")
    return {"name": name, "content": content,
            "_summary": f"已加载 skill「{name}」全文（{len(content)} 字符）"}


async def list_skills(ctx: ToolContext, args: dict) -> dict:
    """列出技能池全部条目（内置/自定义来源、描述、triggers、更新时间）"""
    items = [{
        "name": s.name, "description": s.description, "triggers": s.triggers,
        "source": s.source, "updateTime": s.update_time,
    } for s in skills.list_skills()]
    builtin = sum(1 for i in items if i["source"] == "builtin")
    return {"total": len(items), "builtin": builtin, "custom": len(items) - builtin,
            "skills": items,
            "_summary": f"技能池共 {len(items)} 个（内置 {builtin} / 自定义 {len(items) - builtin}）"}


async def _save_skill_preview(ctx: ToolContext, args: dict) -> str:
    """审批卡片必须展示待写入的完整草稿（设计文档 7.3 安全约束 1）"""
    content = args.get("content") or ""
    return (f"将写入自定义 skill「{args.get('name')}」（{len(content)} 字符）：\n"
            f"描述：{args.get('description')}\n"
            f"触发词：{args.get('triggers') or '（无）'}\n"
            f"─────── 草稿全文 ───────\n{content}")


async def save_skill(ctx: ToolContext, args: dict) -> dict:
    """把现场总结的 SOP 固化为自定义 skill（redact 兜底 + slug 校验 + 32KB 上限）"""
    name = (args.get("name") or "").strip()
    description = (args.get("description") or "").strip()
    triggers = (args.get("triggers") or "").strip()
    content = args.get("content") or ""

    # extra_secrets：当前全部渠道密钥明文——上下文残留密钥时落盘前替换为尾4位提示
    ctx.extra_secrets = [c.get("api_key") for c in await channel_crud.get_all(ctx.db)
                         if c.get("api_key")]
    path = skills.save_skill(name=name, description=description, triggers=triggers,
                             content=content, extra_secrets=ctx.extra_secrets)
    return {"ok": True, "name": name, "path": str(path.relative_to(path.parents[2])) if len(path.parents) >= 3 else path.name,
            "bytes": path.stat().st_size,
            "_summary": f"自定义 skill「{name}」已保存（下一轮起目录可见，任何会话可加载）"}


async def _delete_skill_preview(ctx: ToolContext, args: dict) -> str:
    name = (args.get("name") or "").strip()
    existing = skills.load_skill(name)
    if existing is None:
        return f"skill「{name}」不存在（执行会被拒绝）"
    source = "自定义" if any(s.name == name and s.source == "custom" for s in skills.list_skills()) else "内置"
    return f"将删除{source} skill「{name}」（{len(existing)} 字符）。内置 skill 不可删除。"


async def delete_skill(ctx: ToolContext, args: dict) -> dict:
    """删除自定义 skill（内置 skill 物理隔离在代码包内，不可删）"""
    name = (args.get("name") or "").strip()
    deleted = skills.delete_skill(name)
    if not deleted:
        builtin = any(s.name == name and s.source == "builtin" for s in skills.list_skills())
        if builtin:
            raise ValueError(f"skill「{name}」是内置技能，不可删除（如需覆盖语义请用 save_skill 保存同名自定义版）")
        raise ValueError(f"自定义 skill「{name}」不存在，可用 list_skills 查看技能池")
    return {"ok": True, "name": name, "_summary": f"自定义 skill「{name}」已删除"}


def register_skill_tools() -> None:
    register(ToolDef(
        name="load_skill",
        description="读取指定 skill 的完整 SOP 正文（目录见系统提示词，按需加载以节省上下文）。",
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "skill 名称（见目录）"},
        }, "required": ["name"]},
        risk="L0", handler=load_skill,
    ))
    register(ToolDef(
        name="list_skills",
        description="列出技能池全部条目（内置/自定义、描述、触发词、更新时间）。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=list_skills,
    ))
    register(ToolDef(
        name="save_skill",
        description="把运维经验固化为自定义 skill 加入技能池（强制全文审批）：name 需为小写字母/数字/连字符的 slug；content 为 SOP 正文（Markdown，≤32KB）；同名覆盖更新。",
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "skill 名（slug：^[a-z0-9][a-z0-9-]{1,63}$）"},
            "description": {"type": "string", "description": "一句话用途描述（目录展示与触发匹配用）"},
            "triggers": {"type": "string", "description": "触发关键词（逗号分隔，可选）"},
            "content": {"type": "string", "description": "SOP 正文（Markdown：步骤/判据/报告模板）"},
        }, "required": ["name", "description", "content"]},
        risk="L1", handler=save_skill, always_confirm=True, preview=_save_skill_preview,
    ))
    register(ToolDef(
        name="delete_skill",
        description="删除指定自定义 skill（内置 skill 不可删；强制审批）。",
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "要删除的自定义 skill 名"},
        }, "required": ["name"]},
        risk="L1", handler=delete_skill, always_confirm=True, preview=_delete_skill_preview,
    ))
