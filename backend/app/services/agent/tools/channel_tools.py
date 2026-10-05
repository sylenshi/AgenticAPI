"""渠道管理域工具：A1 查询 / A2 连通性测试 / A3 配置修改 / A4 绑定一致性检查

密钥红线：A1 返回的渠道信息永不携带 api_key，仅 apiKeyHint（尾 4 位）；
A2 的密钥注入发生在 probe_service 内部。
"""

import json

from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import channel as channel_crud
from app.crud import model as model_crud
from app.services.agent.registry import ToolContext, ToolDef, register
from app.services import probe_service
from app.utils.json_utils import parse_json_list


def _key_hint(api_key: str | None) -> str:
    """密钥尾 4 位提示（sk-****ab12 形态），永不返回明文"""
    if not api_key or len(api_key) < 8:
        return "****"
    return f"****{api_key[-4:]}"


async def _model_bindings(db: AsyncSession) -> dict[str, list[str]]:
    """反向索引：渠道名 → 绑定了它的出站模型名列表（llm_models.channels 解析）"""
    bindings: dict[str, list[str]] = {}
    for model in await model_crud.get_all(db):
        for channel_name in parse_json_list(model.get("channels")):
            bindings.setdefault(channel_name, []).append(model["name"])
    return bindings


async def list_channels(ctx: ToolContext, args: dict) -> dict:
    """A1 渠道信息查询（脱敏版，不复用 GET /channels 的明文响应形状）"""
    keyword = (args.get("name_keyword") or "").strip()
    bindings = await _model_bindings(ctx.db)
    channels = []
    for c in await channel_crud.get_all(ctx.db):
        if keyword and keyword not in (c.get("channel_name") or ""):
            continue
        channels.append({
            "channelName": c["channel_name"],
            "baseUrl": c["base_url"],
            "apiKeyHint": _key_hint(c.get("api_key")),
            "status": bool(c.get("status")),
            "timeout": c.get("timeout"),
            "usedRatio": float(c.get("used_ratio") or 0),
            "description": c.get("description") or "",
            "supportModels": parse_json_list(c.get("support_models")),
            "boundModels": bindings.get(c["channel_name"], []),
        })
    ok_count = sum(1 for c in channels if c["status"])
    return {
        "total": len(channels),
        "enabled": ok_count,
        "disabled": len(channels) - ok_count,
        "channels": channels,
        "_summary": f"共 {len(channels)} 个渠道（启用 {ok_count} / 停用 {len(channels) - ok_count}），密钥已脱敏",
    }


async def test_channel(ctx: ToolContext, args: dict) -> dict:
    """A2 渠道连通性测试：scope=one 抽一个模型 / all 遍历全部支持模型（密钥后端注入，免计费）"""
    channel_name = (args.get("channel_name") or "").strip()
    scope = args.get("scope") or "one"
    if scope not in ("one", "all"):
        raise ValueError(f"scope 仅支持 one / all，收到：{scope}")
    model_name = (args.get("model_name") or "").strip()

    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        raise ValueError(f"渠道 {channel_name} 不存在，可用渠道名见 list_channels 结果")

    support = parse_json_list(channel.get("support_models"))
    if scope == "one":
        target = model_name if model_name else (support[0] if support else "")
        if not target:
            raise ValueError(f"渠道 {channel_name} 未配置支持模型，无法抽查")
        if support and target not in support:
            raise ValueError(f"模型 {target} 不在渠道 {channel_name} 的支持列表 {support} 中")
        models = [target]
    else:
        models = support
        if not models:
            raise ValueError(f"渠道 {channel_name} 未配置支持模型，无法遍历")

    result = await probe_service.probe_channel(ctx.db, channel_name, models)
    ok = result.get("okCount", 0)
    total = result.get("probed", 0)
    result["_summary"] = f"渠道 {channel_name} 拨测 {total} 个模型：可用 {ok} / 失败 {total - ok}"
    return result


async def _update_channel_preview(ctx: ToolContext, args: dict) -> str:
    """A3 审批卡片预览：字段级前后 diff"""
    channel = await channel_crud.get_by_name(ctx.db, (args.get("channel_name") or "").strip())
    if not channel:
        return f"渠道 {args.get('channel_name')} 不存在（执行会被拒绝）"
    changes = []
    if "status" in args and args["status"] is not None:
        changes.append(f"状态：{bool(channel.get('status'))} → {bool(args['status'])}"
                       f"（{'启用' if args['status'] else '停用'}）")
    if "timeout" in args and args["timeout"] is not None:
        changes.append(f"超时：{channel.get('timeout')}s → {args['timeout']}s")
    if "description" in args and args["description"] is not None:
        changes.append(f"描述：{channel.get('description') or '（空）'} → {args['description']}")
    if "support_models" in args and args["support_models"] is not None:
        old = parse_json_list(channel.get("support_models"))
        changes.append(f"支持模型：{old} → {args['support_models']}")
    return f"修改渠道 {channel['channel_name']}：\n" + "\n".join(f"· {c}" for c in changes) \
        if changes else "无实际变更字段"


async def update_channel(ctx: ToolContext, args: dict) -> dict:
    """A3 渠道配置修改（L1）：启停 / 超时 / 描述 / 支持模型；名称与密钥不可改（密钥走管理页）"""
    channel_name = (args.get("channel_name") or "").strip()
    update: dict = {}
    if "status" in args and args["status"] is not None:
        update["status"] = 1 if args["status"] else 0
    if "timeout" in args and args["timeout"] is not None:
        timeout = int(args["timeout"])
        if not 5 <= timeout <= 600:
            raise ValueError(f"timeout 需在 5~600 秒之间，收到 {timeout}")
        update["timeout"] = timeout
    if "description" in args and args["description"] is not None:
        update["description"] = str(args["description"])[:200]
    if "support_models" in args and args["support_models"] is not None:
        models = args["support_models"]
        if not isinstance(models, list) or not all(isinstance(m, str) for m in models):
            raise ValueError("support_models 必须是字符串数组（模型名列表）")
        update["support_models"] = json.dumps(models, ensure_ascii=False)
    if not update:
        raise ValueError("至少提供一项要修改的字段：status / timeout / description / support_models")

    existing = await channel_crud.get_by_name(ctx.db, channel_name)
    if not existing:
        raise ValueError(f"渠道 {channel_name} 不存在")

    await channel_crud.update_by_name(ctx.db, channel_name, update)
    return {
        "ok": True,
        "channel": channel_name,
        "updatedFields": list(update.keys()),
        "_summary": f"渠道 {channel_name} 已更新字段：{', '.join(update.keys())}",
    }


async def check_binding_consistency(ctx: ToolContext, args: dict) -> dict:
    """A4 渠道-模型绑定一致性检查：双向 JSON 软引用交叉比对，只报告不修复"""
    channels = await channel_crud.get_all(ctx.db)
    models = await model_crud.get_all(ctx.db)

    channel_support: dict[str, set] = {}   # 渠道 → 其 support_models 声明
    for c in channels:
        channel_support[c["channel_name"]] = set(parse_json_list(c.get("support_models")))
    model_channels: dict[str, set] = {}    # 模型 → 其 channels 声明
    for m in models:
        model_channels[m["name"]] = set(parse_json_list(m.get("channels")))

    all_channel_names = set(channel_support)
    all_model_names = set(model_channels)
    issues: list[str] = []

    # 方向一：渠道声明支持某模型，但模型未绑定该渠道（单向引用）
    for cname, models_declared in channel_support.items():
        for mname in models_declared:
            if mname not in all_model_names:
                issues.append(f"渠道「{cname}」支持模型「{mname}」，但该模型不存在于 llm_models（孤儿引用）")
            elif cname not in model_channels[mname]:
                issues.append(f"渠道「{cname}」声明支持「{mname}」，但该模型的 channels 未包含此渠道（单向绑定）")

    # 方向二：模型绑定渠道，但渠道的 support_models 未声明该模型
    for mname, channels_declared in model_channels.items():
        for cname in channels_declared:
            if cname not in all_channel_names:
                issues.append(f"模型「{mname}」绑定渠道「{cname}」，但该渠道不存在于 llm_channels（孤儿引用）")
            elif mname not in channel_support[cname]:
                issues.append(f"模型「{mname}」绑定渠道「{cname}」，但渠道支持列表未包含该模型（单向绑定）")

    # 附加：绑定到停用渠道/模型的告警
    disabled_channels = {c["channel_name"] for c in channels if not c.get("status")}
    for m in models:
        if not m.get("status"):
            continue
        bound = parse_json_list(m.get("channels"))
        if bound and set(bound) <= disabled_channels:
            issues.append(f"启用中的模型「{m['name']}」全部渠道均已停用（实际不可调用）")

    return {
        "checkedChannels": len(channels),
        "checkedModels": len(models),
        "issueCount": len(issues),
        "issues": issues,
        "_summary": f"绑定一致性检查完成：{'全部一致' if not issues else f'发现 {len(issues)} 处不一致'}",
    }


def register_channel_tools() -> None:
    register(ToolDef(
        name="list_channels",
        description="获取上游渠道列表（含状态/超时/支持模型/被哪些出站模型绑定）。密钥永不返回，仅尾4位提示。可按名称过滤。",
        parameters={"type": "object", "properties": {
            "name_keyword": {"type": "string", "description": "渠道名过滤关键字（可选）"},
        }, "required": []},
        risk="L0", handler=list_channels,
    ))
    register(ToolDef(
        name="test_channel",
        description="对指定上游渠道做连通性拨测：scope=one 抽查一个模型（可指定），scope=all 遍历全部支持模型。直发探测请求，免计费，返回逐模型 {ok, 时延ms, HTTP状态, 错误}。",
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（见 list_channels）"},
            "scope": {"type": "string", "enum": ["one", "all"], "description": "one=抽查单模型，all=遍历全部支持模型"},
            "model_name": {"type": "string", "description": "scope=one 时可指定模型名（默认取支持列表第一个）"},
        }, "required": ["channel_name"]},
        risk="L0", handler=test_channel, timeout=180,
    ))
    register(ToolDef(
        name="update_channel",
        description="修改渠道配置（L1 写操作，需审批）：启用/停用 status、超时 timeout（秒）、描述、支持模型列表 support_models。渠道名与密钥不可改。",
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（定位键）"},
            "status": {"type": "boolean", "description": "启用 true / 停用 false"},
            "timeout": {"type": "integer", "description": "上游请求超时秒数（5~600）"},
            "description": {"type": "string", "description": "渠道描述（≤200字）"},
            "support_models": {"type": "array", "items": {"type": "string"}, "description": "支持的上游模型名列表"},
        }, "required": ["channel_name"]},
        risk="L1", handler=update_channel, preview=_update_channel_preview,
    ))
    register(ToolDef(
        name="check_binding_consistency",
        description="检查渠道 support_models 与模型 channels 双向软引用的一致性（孤儿引用/单向绑定/停用渠道），只报告不修复。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=check_binding_consistency,
    ))
