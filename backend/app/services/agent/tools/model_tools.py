"""出站模型域工具：C1 模型信息 / C2 单模型拨测 / C3 全量巡检
+ C4 新增 / C5 配置修改 / C6 删除（v0.10.0）

拨测走 probe_service 直发上游（免计费、不写 chat_record），与
model_service.test_model（真实中转、要扣费）是两套实现，后者不供 Agent 使用。
C4~C6 复用管理页 model_service（重名/渠道存在性校验、NOT NULL 默认值一致）。
"""

import asyncio

from fastapi import HTTPException

from app.crud import channel as channel_crud
from app.crud import model as model_crud
from app.schemas.model import ModelSchema
from app.services import model_service, probe_service
from app.services.agent.registry import ToolContext, ToolDef, register
from app.utils.json_utils import parse_json_list


def _model_brief(m: dict, channel_status: dict[str, bool] | None = None) -> dict:
    """模型配置摘要（定价单位：元/百万token；按次计费看 perRequestPrice）"""
    return {
        "name": m["name"],
        "label": m.get("label") or "",
        "modelGroup": m.get("model_group"),
        "status": bool(m.get("status")),
        "isRequestMode": bool(m.get("is_request_mode")),
        "perRequestPrice": float(m.get("per_request_price") or 0),
        "inputPrice": float(m.get("input_price") or 0),
        "cachePrice": float(m.get("cache_price") or 0),
        "outputPrice": float(m.get("output_price") or 0),
        "channels": parse_json_list(m.get("channels")),
        "upstreamName": (m.get("upstream_name") or "") or None,
        "contextLength": m.get("context_length"),
        "maxTokens": m.get("max_tokens"),
        "isLog": bool(m.get("is_log")),
    }


async def get_model_info(ctx: ToolContext, args: dict) -> dict:
    """C1 模型信息查询：定价 / 分组 / 渠道绑定（含 upstream_name 映射）"""
    model_name = (args.get("model_name") or "").strip()
    models = await model_crud.get_all(ctx.db)
    if model_name:
        target = next((m for m in models if m["name"] == model_name), None)
        if not target:
            raise ValueError(f"模型 {model_name} 不存在，可用模型见全量列表（model_name 留空查询）")
        matched = [target]
    else:
        matched = models

    briefs = [_model_brief(m) for m in matched]
    return {
        "total": len(briefs),
        "models": briefs,
        "_summary": f"共 {len(briefs)} 个模型" + (f"（筛选：{model_name}）" if model_name else "（全量）"),
    }


async def test_model(ctx: ToolContext, args: dict) -> dict:
    """C2 单模型拨测：按绑定渠道顺序逐个直发探测，返回逐渠道结果与最终结论"""
    model_name = (args.get("model_name") or "").strip()
    if not model_name:
        raise ValueError("model_name 不能为空")
    result = await probe_service.probe_model(ctx.db, model_name)
    return result


async def test_all_models(ctx: ToolContext, args: dict) -> dict:
    """C3 全量模型巡检：遍历所有启用出站模型拨测（并发限 5），进度实时上报"""
    models = [m for m in await model_crud.get_all(ctx.db) if m.get("status")]
    if not models:
        return {"total": 0, "_summary": "站内没有启用中的出站模型"}

    semaphore = asyncio.Semaphore(5)
    results: list[dict] = []
    done_count = 0

    async def _one(m: dict) -> dict:
        nonlocal done_count
        async with semaphore:
            result = await probe_service.probe_model(ctx.db, m["name"])
        done_count += 1
        await ctx.emit({"type": "tool_progress", "tool": "test_all_models",
                        "done": done_count, "total": len(models)})
        return result

    results = await asyncio.gather(*[_one(m) for m in models])

    ok_results = [r for r in results if r.get("ok")]
    latencies = [r["latencyMs"] for r in ok_results if r.get("latencyMs") is not None]
    failures = [
        {"model": r["model"], "detail": r["results"]}
        for r in results if not r.get("ok")
    ]
    avg = round(sum(latencies) / len(latencies)) if latencies else None
    rate = round(len(ok_results) / len(results) * 100) if results else 0
    return {
        "total": len(results),
        "okCount": len(ok_results),
        "failCount": len(failures),
        "availability": f"{rate}%",
        "avgLatencyMs": avg,
        "failures": failures,
        "_summary": f"巡检 {len(results)} 个模型：可用 {len(ok_results)}（{rate}%），"
                    f"平均时延 {avg}ms" + (f"，失败 {len(failures)} 个" if failures else ""),
    }


async def _create_model_preview(ctx: ToolContext, args: dict) -> str:
    """C4 审批卡预览：完整新模型配置（定价是计费依据，必须过目）"""
    if args.get("is_request_mode"):
        pricing = f"按次计费 {args.get('per_request_price', 0)} 元/次"
    else:
        pricing = (f"输入 {args.get('input_price', 0)} / 缓存 {args.get('cache_price', 0)} / "
                   f"输出 {args.get('output_price', 0)} 元/百万token")
    return (f"将新增出站模型「{args.get('name')}」（分组 {args.get('model_group', 'free')}）：\n"
            f"· 定价：{pricing}\n"
            f"· 绑定渠道：{args.get('channels')}\n"
            f"· 上游名映射：{args.get('upstream_name') or '（无，对外名即上游名）'}\n"
            f"· 上下文 {args.get('context_length', '（默认）')} / max_tokens {args.get('max_tokens', '（默认）')}\n"
            f"· 状态：{'启用' if args.get('status', True) else '停用'} ｜ 对话记录：{'开' if args.get('is_log') else '关'}")


async def create_model(ctx: ToolContext, args: dict) -> dict:
    """C4 新增出站模型（L1 强制审批）：新上游上线入口，定价直接决定计费所以必须人审"""
    name = (args.get("name") or "").strip()
    group = (args.get("model_group") or "").strip()
    channels = args.get("channels")
    if not name:
        raise ValueError("name 不能为空")
    if group not in ("free", "vip"):
        raise ValueError(f"model_group 仅支持 free / vip，收到：{group}")
    if not isinstance(channels, list) or not channels or not all(isinstance(c, str) and c.strip() for c in channels):
        raise ValueError("channels 必须为非空字符串数组（模型至少绑定一个渠道，否则不可调用）")
    for price in ("input_price", "output_price", "cache_price", "per_request_price"):
        if args.get(price) is not None and float(args[price]) < 0:
            raise ValueError(f"{price} 不能为负数")

    # 渠道存在性提前校验（service 层也会校验，提前给出更聚焦的错误）
    existing = await channel_crud.get_existing_names(ctx.db, [c.strip() for c in channels])
    missing = [c for c in channels if c.strip() not in existing]
    if missing:
        raise ValueError(f"以下渠道不存在：{missing}。请先 create_channel 或改绑已有渠道")

    fields = {k: v for k, v in {
        "name": name, "model_group": group, "channels": [c.strip() for c in channels],
        "upstream_name": (args.get("upstream_name") or "").strip() or None,
        "label": args.get("label"), "description": args.get("description"),
        "is_request_mode": args.get("is_request_mode"),
        "per_request_price": args.get("per_request_price"),
        "input_price": args.get("input_price"), "cache_price": args.get("cache_price"),
        "output_price": args.get("output_price"),
        "context_length": args.get("context_length"), "max_tokens": args.get("max_tokens"),
        "support_vision": args.get("support_vision"),
        "status": args.get("status", True), "is_log": args.get("is_log"),
    }.items() if v is not None}
    try:
        model_id = await model_service.create_model(ctx.db, ModelSchema(**fields))
    except HTTPException as exc:
        raise ValueError(f"创建模型失败：{exc.detail}")
    return {
        "ok": True, "model": name, "modelId": model_id,
        "hint": f"建议下一步：test_model(model_name='{name}') 拨测验证端到端可用",
        "_summary": f"模型「{name}」已创建（id={model_id}，绑定 {len(channels)} 个渠道）",
    }


# update_model 可修改字段 → 展示名映射（diff 预览用）
_UPDATABLE_FIELDS = {
    "label": "显示名", "model_group": "分组", "upstream_name": "上游名映射",
    "is_request_mode": "按次计费模式", "per_request_price": "按次价格",
    "input_price": "输入价", "cache_price": "缓存价", "output_price": "输出价",
    "channels": "绑定渠道", "status": "状态", "context_length": "上下文窗口",
    "max_tokens": "max_tokens", "support_vision": "视觉能力", "is_log": "对话记录",
    "description": "描述", "icon": "图标",
}


async def _update_model_preview(ctx: ToolContext, args: dict) -> str:
    """C5 审批卡预览：字段级前后 diff（照抄 update_channel 预览模式）"""
    model = await model_crud.get_by_name(ctx.db, (args.get("name") or "").strip())
    if not model:
        return f"模型 {args.get('name')} 不存在（执行会被拒绝）"
    changes = []
    for key, label in _UPDATABLE_FIELDS.items():
        if key in args and args[key] is not None:
            old = model.get(key)
            if key == "channels":
                old = parse_json_list(old)
            changes.append(f"{label}：{old!r} → {args[key]!r}")
    return (f"修改模型「{model['name']}」：\n" + "\n".join(f"· {c}" for c in changes)
            if changes else "无实际变更字段")


async def update_model(ctx: ToolContext, args: dict) -> dict:
    """C5 模型配置修改（L1）：定价 / 分组 / 渠道绑定 / 能力开关等，name 不可改"""
    name = (args.get("name") or "").strip()
    if not name:
        raise ValueError("name 不能为空")

    fields = {k: v for k, v in args.items()
              if k in _UPDATABLE_FIELDS and v is not None}
    if not fields:
        raise ValueError(f"至少提供一项要修改的字段：{', '.join(_UPDATABLE_FIELDS)}")
    if "channels" in fields:
        if not isinstance(fields["channels"], list) or not all(isinstance(c, str) for c in fields["channels"]):
            raise ValueError("channels 必须为字符串数组")
        existing = await channel_crud.get_existing_names(ctx.db, fields["channels"])
        missing = [c for c in fields["channels"] if c not in existing]
        if missing:
            raise ValueError(f"以下渠道不存在：{missing}")
    if "model_group" in fields and fields["model_group"] not in ("free", "vip"):
        raise ValueError(f"model_group 仅支持 free / vip，收到：{fields['model_group']}")

    try:
        await model_service.update_model(ctx.db, name, ModelSchema(**fields))
    except HTTPException as exc:
        raise ValueError(f"更新模型失败：{exc.detail}")
    return {
        "ok": True, "model": name, "updatedFields": list(fields.keys()),
        "_summary": f"模型「{name}」已更新字段：{', '.join(fields.keys())}",
    }


async def _delete_model_preview(ctx: ToolContext, args: dict) -> str:
    """C6 审批卡预览：模型配置 + 渠道侧 support_models 反向引用"""
    name = (args.get("name") or "").strip()
    model = await model_crud.get_by_name(ctx.db, name)
    if not model:
        return f"模型 {name} 不存在（执行会被拒绝）"
    referring = []
    for c in await channel_crud.get_all(ctx.db):
        if name in parse_json_list(c.get("support_models")):
            referring.append(c["channel_name"])
    lines = [f"将删除出站模型「{name}」（分组 {model.get('model_group')}，"
             f"状态{'启用' if model.get('status') else '停用'}，绑定渠道 {parse_json_list(model.get('channels'))}）"]
    if referring:
        lines.append(f"⚠ 有 {len(referring)} 个渠道的 support_models 仍声明此模型：{', '.join(referring)}"
                     "（删除后成为孤儿声明，建议 update_channel 同步清理）")
    else:
        lines.append("无渠道声明此模型，删除无联动影响。")
    if not args.get("dry_run"):
        lines.append("（本次为真删）")
    return "\n".join(lines)


async def delete_model(ctx: ToolContext, args: dict) -> dict:
    """C6 删除出站模型（L2 两阶段）：dry_run=true 预览，确认后 dry_run=false 真删"""
    name = (args.get("name") or "").strip()
    if "dry_run" not in args or not isinstance(args["dry_run"], bool):
        raise ValueError("dry_run 必须显式传 true / false（首次预览传 true）")
    dry_run = args["dry_run"]

    model = await model_crud.get_by_name(ctx.db, name)
    if not model:
        raise ValueError(f"模型 {name} 不存在，可用模型见 get_model_info 结果")
    referring = [c["channel_name"] for c in await channel_crud.get_all(ctx.db)
                 if name in parse_json_list(c.get("support_models"))]

    if dry_run:
        return {
            "dryRun": True, "model": name,
            "modelGroup": model.get("model_group"),
            "channels": parse_json_list(model.get("channels")),
            "channelsDeclaring": referring,
            "_summary": (f"[dry-run] 删除模型「{name}」预览："
                         + (f"{len(referring)} 个渠道的 support_models 将出现孤儿声明" if referring
                            else "无渠道侧联动影响")),
        }

    try:
        await model_service.remove_model(ctx.db, name)
    except HTTPException as exc:
        raise ValueError(f"删除模型失败：{exc.detail}")
    return {
        "ok": True, "model": name,
        "orphanChannelDeclarations": referring,
        "_summary": (f"模型「{name}」已删除"
                     + (f"；注意：渠道 {', '.join(referring)} 的支持列表仍声明此模型（孤儿声明）" if referring else "")),
    }


def register_model_tools() -> None:
    register(ToolDef(
        name="get_model_info",
        description="查询单个或全部出站模型配置：定价（输入/缓存/输出/按次）、分组、渠道绑定（含上游名映射）、上下文窗口、状态。model_name 留空 = 全量。",
        parameters={"type": "object", "properties": {
            "model_name": {"type": "string", "description": "模型名（可选，留空查全部）"},
        }, "required": []},
        risk="L0", handler=get_model_info,
    ))
    register(ToolDef(
        name="test_model",
        description="单模型拨测：按绑定渠道顺序直发探测（免计费），返回每个渠道的 ok/时延/错误 与最终结论（全部渠道失败 = 模型不可用）。",
        parameters={"type": "object", "properties": {
            "model_name": {"type": "string", "description": "出站模型名"},
        }, "required": ["model_name"]},
        risk="L0", handler=test_model, timeout=120,
    ))
    register(ToolDef(
        name="test_all_models",
        description="全量模型巡检：遍历所有启用出站模型批量拨测（并发受限，进度实时上报），产出可用率/平均时延/失败清单汇总。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=test_all_models, timeout=300,
    ))
    register(ToolDef(
        name="create_model",
        description=("新增出站模型（关键写操作，直接决定对外计费）：新上游上线的完整入口，需绑定已存在渠道"
                     "（先 create_channel）。定价单位为元/百万token（is_request_mode=true 时按次计费），"
                     "审批卡展示完整定价。创建后建议 test_model 拨测。"),
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "对外模型名（唯一，调用方使用）"},
            "model_group": {"type": "string", "enum": ["free", "vip"], "description": "分组：free 免费模型 / vip 付费模型"},
            "channels": {"type": "array", "items": {"type": "string"}, "description": "绑定的渠道名列表（非空，按序轮询）"},
            "input_price": {"type": "number", "description": "输入价（元/百万token）"},
            "output_price": {"type": "number", "description": "输出价（元/百万token）"},
            "cache_price": {"type": "number", "description": "缓存命中价（元/百万token，默认 0）"},
            "is_request_mode": {"type": "boolean", "description": "按次计费模式（默认 false 按token）"},
            "per_request_price": {"type": "number", "description": "按次价格（元/次，is_request_mode=true 时必填）"},
            "upstream_name": {"type": "string", "description": "实际请求上游用的模型名（映射，为空则与对外名相同）"},
            "label": {"type": "string", "description": "展示名（默认同 name）"},
            "context_length": {"type": "integer", "description": "上下文窗口（token）"},
            "max_tokens": {"type": "integer", "description": "单次最大输出（token）"},
            "support_vision": {"type": "boolean", "description": "是否视觉模型（默认 false）"},
            "status": {"type": "boolean", "description": "初始状态（默认启用）"},
            "is_log": {"type": "boolean", "description": "是否记录对话全文（默认 false）"},
        }, "required": ["name", "model_group", "channels", "input_price", "output_price"]},
        risk="L2", handler=create_model, preview=_create_model_preview,
    ))
    register(ToolDef(
        name="update_model",
        description="修改出站模型配置（可逆写操作）：定价（输入/缓存/输出/按次）、分组、渠道绑定、上游名映射、上下文窗口、启停等。模型名不可改。审批卡展示字段级前后 diff。",
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "模型名（定位键）"},
            "label": {"type": "string"}, "model_group": {"type": "string", "enum": ["free", "vip"]},
            "upstream_name": {"type": "string"},
            "is_request_mode": {"type": "boolean"}, "per_request_price": {"type": "number"},
            "input_price": {"type": "number"}, "cache_price": {"type": "number"}, "output_price": {"type": "number"},
            "channels": {"type": "array", "items": {"type": "string"}},
            "status": {"type": "boolean"}, "context_length": {"type": "integer"}, "max_tokens": {"type": "integer"},
            "support_vision": {"type": "boolean"}, "is_log": {"type": "boolean"},
            "description": {"type": "string"}, "icon": {"type": "string"},
        }, "required": ["name"]},
        risk="L1", handler=update_model, preview=_update_model_preview,
    ))
    register(ToolDef(
        name="delete_model",
        description=("删除出站模型（不可逆删除，两阶段）：首次必须 dry_run=true 预览（含哪些渠道的 support_models "
                     "仍声明此模型的孤儿影响），向管理员展示预览并确认同意后，再 dry_run=false 真删。"),
        parameters={"type": "object", "properties": {
            "name": {"type": "string", "description": "模型名（定位键）"},
            "dry_run": {"type": "boolean", "description": "true=预览影响（首次必传），false=真删（需管理员确认预览后）"},
        }, "required": ["name", "dry_run"]},
        risk="L2", handler=delete_model, preview=_delete_model_preview, session_limit=10,
    ))
