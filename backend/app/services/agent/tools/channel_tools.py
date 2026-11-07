"""渠道管理域工具：A1 查询 / A2 连通性测试 / A3 配置修改 / A4 绑定一致性检查
+ A5 新增 / A6 删除 + A8 上游模型发现 / A9 密钥轮换（v0.14.0）

v0.14.0 安全用钥通道：需要密钥的上游操作不再依赖"管理员给钥"，统一为
"Agent 引用渠道名 → 后端代持密钥执行 → 结果脱敏返回"。A8 拉上游 /models、
A9 恢复密钥轮换（v0.11.0 曾下线为"走管理页"，但凭证到期类运维因此无法闭环）；
A2 同步放宽为可试拨声明列表之外的候选模型。

密钥红线：A1 返回的渠道信息永不携带 api_key，仅 apiKeyHint（尾 4 位）；
A2/A8 的密钥注入发生在 probe_service 内部；A5/A9 的 api_key 仅在入参→service
落库路径上瞬时存在，审批卡与 agent_message 均为脱敏版本（registry 管线），
工具返回值只带尾 4 位提示。
"""

import json

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import channel as channel_crud
from app.crud import model as model_crud
from app.schemas.channel import ChannelSchema
from app.services import channel_service
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
    """A2 渠道连通性测试：scope=one 试拨一个模型（可指定声明列表之外的候选名）/ all 遍历支持模型（密钥后端注入，免计费）"""
    channel_name = (args.get("channel_name") or "").strip()
    scope = args.get("scope") or "one"
    if scope not in ("one", "all"):
        raise ValueError(f"scope 仅支持 one / all，收到：{scope}")
    model_name = (args.get("model_name") or "").strip()

    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        raise ValueError(f"渠道 {channel_name} 不存在，可用渠道名见 list_channels 结果")

    support = parse_json_list(channel.get("support_models"))
    not_declared = False
    if scope == "one":
        target = model_name if model_name else (support[0] if support else "")
        if not target:
            raise ValueError(f"渠道 {channel_name} 未配置支持模型，也未指定 model_name，无法抽查")
        # v0.14.0：允许试拨声明列表之外的候选模型（上游是否支持某模型的唯一可靠验证法），显式标注
        not_declared = bool(support) and target not in support
        models = [target]
    else:
        models = support
        if not models:
            raise ValueError(f"渠道 {channel_name} 未配置支持模型，无法遍历")

    result = await probe_service.probe_channel(ctx.db, channel_name, models)
    ok = result.get("okCount", 0)
    total = result.get("probed", 0)
    if not_declared:
        result["notInDeclaredList"] = True
    result["_summary"] = (f"渠道 {channel_name} 拨测 {total} 个模型：可用 {ok} / 失败 {total - ok}"
                          + ("（目标不在渠道声明列表，属候选试拨）" if not_declared else ""))
    return result


async def list_upstream_models(ctx: ToolContext, args: dict) -> dict:
    """A8 上游模型清单发现：后端代持密钥 GET {base}/models，返回上游模型 ID 列表（免计费）"""
    channel_name = (args.get("channel_name") or "").strip()
    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        raise ValueError(f"渠道 {channel_name} 不存在，可用渠道名见 list_channels 结果")

    result = await probe_service.list_upstream_models(channel["base_url"], channel.get("api_key") or "")
    if result.get("ok"):
        ids = result.get("models") or []
        result["models"] = ids[:200]
        if len(ids) > 200:
            result["truncated"] = True
        # 附渠道声明列表便于对照差集（声明了但上游没有 → 需清理；上游有但未声明 → 接入候选）
        result["declaredSupportModels"] = parse_json_list(channel.get("support_models"))
        result["_summary"] = f"渠道 {channel_name} 上游共 {result['total']} 个模型（{result['latencyMs']}ms）"
    else:
        result["_summary"] = f"拉取上游模型清单失败（HTTP {result.get('status')}），原因与建议见 error 字段"
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
    """A3 渠道配置修改（L1）：启停 / 超时 / 描述 / 支持模型；名称不可改，密钥变更用 rotate_channel_key"""
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
    await ctx.db.commit()  # update_by_name 不提交，显式收口（不依赖后续审计写日志隐式提交）
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


async def _create_channel_preview(ctx: ToolContext, args: dict) -> str:
    """A5 审批卡预览：完整配置摘要，密钥只留尾 4 位"""
    support = args.get("support_models") or []
    key = args.get("api_key") or ""
    hint = f"****{key[-4:]}" if len(key) >= 8 else "（无效过短密钥，执行会被拒绝）"
    return (f"将新增上游渠道「{args.get('channel_name')}」：\n"
            f"· base_url：{args.get('base_url')}\n"
            f"· 密钥：{hint}（明文不展示）\n"
            f"· 支持模型：{len(support)} 个\n"
            f"· 超时：{args.get('timeout', 30)}s ｜ 状态：{'启用' if args.get('status', True) else '停用'}\n"
            f"· 描述：{args.get('description') or '（空）'}")


async def create_channel(ctx: ToolContext, args: dict) -> dict:
    """A5 新增渠道（L2 关键写）：复用管理页 service 校验（重名 400 → ValueError）"""
    channel_name = (args.get("channel_name") or "").strip()
    base_url = (args.get("base_url") or "").strip()
    api_key = (args.get("api_key") or "").strip()
    support = args.get("support_models")
    timeout = args.get("timeout", 30)

    if not channel_name:
        raise ValueError("channel_name 不能为空")
    if not base_url.startswith(("http://", "https://")):
        raise ValueError(f"base_url 需以 http:// 或 https:// 开头，收到：{base_url}")
    if len(api_key) < 8:
        raise ValueError("api_key 至少 8 个字符（上游密钥一般远长于此，疑似传错）")
    if not isinstance(support, list) or not support or not all(isinstance(m, str) and m.strip() for m in support):
        raise ValueError("support_models 必须为非空字符串数组（至少一个上游模型名）")
    if not 5 <= int(timeout) <= 600:
        raise ValueError(f"timeout 需在 5~600 秒之间，收到 {timeout}")

    schema = ChannelSchema(
        channel_name=channel_name, base_url=base_url, api_key=api_key,
        support_models=[m.strip() for m in support], status=bool(args.get("status", True)),
        timeout=int(timeout), description=args.get("description") or None,
    )
    try:
        channel_id = await channel_service.create_channel(ctx.db, schema)
    except HTTPException as exc:
        raise ValueError(f"创建渠道失败：{exc.detail}")
    return {
        "ok": True, "channel": channel_name, "channelId": channel_id,
        "hint": f"建议下一步：test_channel(channel_name='{channel_name}', scope='one') 验证连通性",
        "_summary": f"渠道「{channel_name}」已创建（id={channel_id}，支持 {len(support)} 个模型）",
    }


async def _delete_channel_preview(ctx: ToolContext, args: dict) -> str:
    """A7 审批卡预览：渠道信息 + 反向绑定影响（删除会产生孤儿引用的模型清单）"""
    channel_name = (args.get("channel_name") or "").strip()
    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        return f"渠道 {channel_name} 不存在（执行会被拒绝）"
    bound = (await _model_bindings(ctx.db)).get(channel_name, [])
    lines = [f"将删除上游渠道「{channel_name}」（base_url={channel['base_url']}，"
             f"状态{'启用' if channel.get('status') else '停用'}）"]
    if bound:
        lines.append(f"⚠ 有 {len(bound)} 个出站模型绑定此渠道：{', '.join(bound[:10])}"
                     + ("…" if len(bound) > 10 else ""))
        lines.append("删除后这些模型将出现孤儿渠道引用（拨测/调用时该渠道报不存在），"
                     "建议先用 update_model 解绑或改绑。")
    else:
        lines.append("无出站模型绑定此渠道，删除无联动影响。")
    if not args.get("dry_run"):
        lines.append("（本次为真删）")
    return "\n".join(lines)


async def delete_channel(ctx: ToolContext, args: dict) -> dict:
    """A7 删除渠道（L2 两阶段）：dry_run=true 预览影响，确认后 dry_run=false 真删"""
    channel_name = (args.get("channel_name") or "").strip()
    if "dry_run" not in args or not isinstance(args["dry_run"], bool):
        raise ValueError("dry_run 必须显式传 true / false（首次预览传 true）")
    dry_run = args["dry_run"]

    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        raise ValueError(f"渠道 {channel_name} 不存在，可用渠道见 list_channels 结果")
    bound = (await _model_bindings(ctx.db)).get(channel_name, [])

    if dry_run:
        return {
            "dryRun": True, "channel": channel_name,
            "baseUrl": channel["base_url"], "status": bool(channel.get("status")),
            "supportModels": parse_json_list(channel.get("support_models")),
            "boundModels": bound,
            "orphanWarning": (f"删除后 {len(bound)} 个出站模型将产生孤儿渠道引用：{', '.join(bound)}"
                              if bound else "无绑定影响"),
            "_summary": f"[dry-run] 删除渠道「{channel_name}」预览：绑定影响 {len(bound)} 个模型",
        }

    try:
        await channel_service.remove_channel(ctx.db, channel_name)
    except HTTPException as exc:
        raise ValueError(f"删除渠道失败：{exc.detail}")
    return {
        "ok": True, "channel": channel_name, "boundModelsLeft": bound,
        "_summary": (f"渠道「{channel_name}」已删除"
                     + (f"；注意：{len(bound)} 个模型仍有对它的绑定引用，建议尽快解绑" if bound else "")),
    }


async def _rotate_key_preview(ctx: ToolContext, args: dict) -> str:
    """A9 审批卡预览：新旧密钥均只显尾 4 位，明文不落卡"""
    channel_name = (args.get("channel_name") or "").strip()
    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    new_key = args.get("api_key") or ""
    new_hint = f"****{new_key[-4:]}" if len(new_key) >= 8 else "（过短无效，执行会被拒绝）"
    if not channel:
        return f"渠道 {channel_name} 不存在（执行会被拒绝）"
    return (f"将更新渠道「{channel_name}」的上游密钥（凭证到期/轮换）：\n"
            f"· 旧密钥：{_key_hint(channel.get('api_key'))}\n"
            f"· 新密钥：{new_hint}（明文不展示）\n"
            f"· 渠道 base_url：{channel['base_url']}")


async def rotate_channel_key(ctx: ToolContext, args: dict) -> dict:
    """A9 更新渠道密钥（L2）：管理员在对话中提供新钥，新钥仅入参→落库瞬时存在（与 A5 create_channel 同路径）"""
    channel_name = (args.get("channel_name") or "").strip()
    new_key = (args.get("api_key") or "").strip()
    if len(new_key) < 8:
        raise ValueError("api_key（新密钥）至少 8 个字符，疑似传错")
    channel = await channel_crud.get_by_name(ctx.db, channel_name)
    if not channel:
        raise ValueError(f"渠道 {channel_name} 不存在，可用渠道名见 list_channels 结果")

    await channel_crud.update_by_name(ctx.db, channel_name, {"api_key": new_key})
    await ctx.db.commit()  # update_by_name 不提交，密钥轮换是 L2 关键操作，显式收口
    return {
        "ok": True, "channel": channel_name,
        "newKeyHint": _key_hint(new_key),
        "hint": f"建议下一步：test_channel(channel_name='{channel_name}', scope='one') 验证新密钥连通性",
        "_summary": f"渠道「{channel_name}」密钥已更新（新钥尾 4 位 {_key_hint(new_key)}）",
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
        description=("对指定上游渠道做连通性拨测：scope=one 试拨一个模型——model_name 可传渠道声明列表之外的任意候选名"
                     "（验证上游是否支持某模型的唯一可靠手段，结果带 notInDeclaredList 标注），scope=all 遍历全部支持模型。"
                     "密钥由后端代持注入，免计费，返回逐模型 {ok, 时延ms, HTTP状态, 错误}。"),
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（见 list_channels）"},
            "scope": {"type": "string", "enum": ["one", "all"], "description": "one=试拨单模型，all=遍历全部支持模型"},
            "model_name": {"type": "string", "description": "scope=one 时可指定模型名（声明列表内外均可，列表外属候选试拨；默认取支持列表第一个）"},
        }, "required": ["channel_name"]},
        risk="L0", handler=test_channel, timeout=180,
    ))
    register(ToolDef(
        name="list_upstream_models",
        description=("拉取指定渠道上游的 /models 模型清单（后端代持密钥调用，免计费），返回上游可用模型 ID 全列表"
                     "与渠道当前声明列表，便于对照差集发现可接入的新模型。404=上游无 /models 路由（agent plan 等"
                     "专用端点常见），此时改用 test_channel 对候选模型逐名试拨。"),
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（见 list_channels）"},
        }, "required": ["channel_name"]},
        risk="L0", handler=list_upstream_models, timeout=60,
    ))
    register(ToolDef(
        name="update_channel",
        description="修改渠道配置（可逆写操作）：启用/停用 status、超时 timeout（秒）、描述、支持模型列表 support_models。渠道名不可改；密钥变更用 rotate_channel_key（关键操作）。",
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
    register(ToolDef(
        name="create_channel",
        description=("新增上游渠道（关键写操作，影响计费与流量）：接入新上游的入口。需要 channel_name / base_url（OpenAI 兼容端点）/"
                     "/ api_key / support_models（该渠道支持的上游模型名列表）。创建后建议 test_channel 拨测验证。"
                     "密钥只在审批与落库路径上瞬时存在，任何返回与卡片都不展示明文。"),
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（唯一，定位键）"},
            "base_url": {"type": "string", "description": "上游 OpenAI 兼容端点（http/https 开头）"},
            "api_key": {"type": "string", "description": "上游 API 密钥（≥8 字符，审批卡仅显示尾4位）"},
            "support_models": {"type": "array", "items": {"type": "string"},
                               "description": "该渠道支持的上游模型名列表（非空）"},
            "timeout": {"type": "integer", "description": "上游请求超时秒数（5~600，默认 30）"},
            "status": {"type": "boolean", "description": "初始状态（默认启用）"},
            "description": {"type": "string", "description": "渠道描述（可选，≤200字）"},
        }, "required": ["channel_name", "base_url", "api_key", "support_models"]},
        risk="L2", handler=create_channel, preview=_create_channel_preview,
    ))
    register(ToolDef(
        name="delete_channel",
        description=("删除上游渠道（不可逆删除，两阶段）：首次必须 dry_run=true 预览（含哪些出站模型绑定此渠道的孤儿引用影响），"
                     "向管理员展示预览并确认同意后，再 dry_run=false 真删。有模型绑定时建议先 update_model 解绑。"),
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（定位键）"},
            "dry_run": {"type": "boolean", "description": "true=预览影响（首次必传），false=真删（需管理员确认预览后）"},
        }, "required": ["channel_name", "dry_run"]},
        risk="L2", handler=delete_channel, preview=_delete_channel_preview, session_limit=10,
    ))
    register(ToolDef(
        name="rotate_channel_key",
        description=("更新指定渠道的上游 API 密钥（关键写操作）：上游凭证到期/轮换时使用。管理员在对话中提供新密钥，"
                     "新钥仅在入参→落库路径瞬时存在，审批卡与任何返回只显示尾 4 位。更新后立即 test_channel 验证连通性。"),
        parameters={"type": "object", "properties": {
            "channel_name": {"type": "string", "description": "渠道名（定位键）"},
            "api_key": {"type": "string", "description": "新的上游 API 密钥（≥8 字符，任何展示只留尾 4 位）"},
        }, "required": ["channel_name", "api_key"]},
        risk="L2", handler=rotate_channel_key, preview=_rotate_key_preview,
    ))
