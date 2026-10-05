"""出站模型域工具（只读拨测）：C1 模型信息 / C2 单模型拨测 / C3 全量巡检

拨测走 probe_service 直发上游（免计费、不写 chat_record），与
model_service.test_model（真实中转、要扣费）是两套实现，后者不供 Agent 使用。
"""

import asyncio

from app.crud import model as model_crud
from app.services import probe_service
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
