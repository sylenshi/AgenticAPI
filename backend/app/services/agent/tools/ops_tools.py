"""运营速查域工具（E1~E2）+ F1 一键巡检报告：全部只读
（v0.11.0 精简：兑换码统计 / 用户查询下线，走监控页与用户管理页）

数据源复用既有口径：usage_summary 单行 / logs 聚合 / usage_stats 预聚合 /
user 表 COUNT——不对原始大表做全量扫描。
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import text

from app.crud import usage_stats as stats_crud
from app.services.agent.registry import ToolContext, ToolDef, register
from app.services.agent.tools.data_tools import _table_stats
from app.services import probe_service
from app.services.operations_service import get_operations


async def get_site_overview(ctx: ToolContext, args: dict) -> dict:
    """E1 站点概览：今日/昨日调用量与消费、用户数、余额池、访客占比"""
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    async def _day_range(start: datetime, end: datetime) -> dict:
        row = (await ctx.db.execute(text("""
            SELECT COUNT(*) AS calls, COALESCE(SUM(cost), 0) AS cost,
                   COALESCE(SUM(prompt_tokens), 0) AS pt, COALESCE(SUM(completion_tokens), 0) AS ct
            FROM logs WHERE type = 'api' AND create_time >= :s AND create_time < :e
        """), {"s": start, "e": end})).mappings().first()
        return {"calls": row["calls"], "cost": f"{float(row['cost']):.4f}",
                "promptTokens": row["pt"], "completionTokens": row["ct"]}

    today_stats, yesterday_stats, users_row, summary = await asyncio.gather(
        _day_range(today, today + timedelta(days=1)),
        _day_range(yesterday, today),
        ctx.db.execute(text("""
            SELECT COUNT(*) AS total, SUM(is_guest) AS guests, SUM(is_admin) AS admins,
                   SUM(status = 0) AS banned, COALESCE(SUM(balance), 0) AS pool
            FROM user
        """)),
        stats_crud.get_summary(ctx.db),
    )
    users = users_row.mappings().first()
    return {
        "today": today_stats,
        "yesterday": yesterday_stats,
        "siteTotal": {"calls": summary["calls"],
                      "promptTokens": summary["prompt_tokens"],
                      "completionTokens": summary["completion_tokens"]},
        "users": {"total": users["total"], "guests": int(users["guests"] or 0),
                  "admins": int(users["admins"] or 0), "banned": int(users["banned"] or 0)},
        "balancePool": f"{float(users['pool']):.2f}",
        "_summary": (f"今日 {today_stats['calls']} 次调用 / 消费 {today_stats['cost']} 元；"
                     f"用户 {users['total']}（访客 {int(users['guests'] or 0)}）；"
                     f"余额池 {float(users['pool']):.2f}"),
    }


async def get_usage_trend(ctx: ToolContext, args: dict) -> dict:
    """E2 用量趋势：时间范围 + 粒度聚合（复用 usage_stats 小时桶预聚合，全站口径）"""
    granularity = args.get("granularity") or "day"
    if granularity not in stats_crud.GRANULARITIES:
        raise ValueError(f"granularity 仅支持 {'/'.join(stats_crud.GRANULARITIES)}，收到：{granularity}")
    end = datetime.now()
    start = end - timedelta(days=args.get("days", 7))
    if start >= end:
        raise ValueError("时间范围无效：start 必须早于 end")

    series = await stats_crud.query_global_series(
        ctx.db, start=start, end=end, granularity=granularity)
    # 回传摘要：调用量 Top5 模型（全序列太大时由截断器兜底）
    by_model: dict[str, dict] = {}
    for row in series:
        acc = by_model.setdefault(row["model_name"], {"calls": 0, "promptTokens": 0, "completionTokens": 0})
        acc["calls"] += row["calls"]
        acc["promptTokens"] += row["prompt_tokens"]
        acc["completionTokens"] += row["completion_tokens"]
    top5 = sorted(by_model.items(), key=lambda kv: kv[1]["calls"], reverse=True)[:5]
    return {
        "granularity": granularity,
        "start": str(start), "end": str(end),
        "buckets": len({r["bucket"] for r in series}),
        "seriesRows": series,
        "topModels": [{"model": name, **st} for name, st in top5],
        "_summary": f"趋势已获取（{granularity} 粒度，{len(series)} 行序列，Top5 模型已摘要）",
    }


async def generate_health_report(ctx: ToolContext, args: dict) -> dict:
    """
    F1 一键巡检报告：渠道连通（每渠道抽查一个模型）+ 模型可用性（逐模型首渠道快探）
    + 上游额度（缓存口径）+ 凭证到期 + 存储水位。仅由管理员对话触发，无定时任务。
    """
    from app.crud import channel as channel_crud
    from app.crud import model as model_crud
    from app.utils.json_utils import parse_json_list

    # 并发拉取四路数据（额度查询是同步网络函数，放线程池）
    channels = [c for c in await channel_crud.get_all(ctx.db) if c.get("status")]
    models = [m for m in await model_crud.get_all(ctx.db) if m.get("status")]

    semaphore = asyncio.Semaphore(5)

    async def _probe_channel(c: dict) -> dict:
        async with semaphore:
            support = parse_json_list(c.get("support_models"))
            if not support:
                return {"channel": c["channel_name"], "ok": False, "error": "未配置支持模型"}
            from app.crud import model as m_crud
            target = support[0]
            m = await m_crud.get_by_name(ctx.db, target)
            upstream = ((m or {}).get("upstream_name") or "").strip() or target
            r = await probe_service.probe_once(c["base_url"], c["api_key"], upstream)
            return {"channel": c["channel_name"], "model": target, **r}

    async def _probe_model(m: dict) -> dict:
        async with semaphore:
            return await probe_service.probe_model_first_channel(ctx.db, m)

    channel_results, model_results, ops = await asyncio.gather(
        asyncio.gather(*[_probe_channel(c) for c in channels]),
        asyncio.gather(*[_probe_model(m) for m in models]),
        asyncio.to_thread(get_operations, "all"),
    )
    chat_stats = await _table_stats(ctx.db, "chat_record")
    log_stats = await _table_stats(ctx.db, "logs")

    ch_ok = sum(1 for r in channel_results if r.get("ok"))
    m_ok = sum(1 for r in model_results if r.get("ok"))
    latencies = [r["latencyMs"] for r in model_results if r.get("ok") and r.get("latencyMs") is not None]
    avg_latency = round(sum(latencies) / len(latencies)) if latencies else None

    # 简明评分卡
    score_parts = []
    score_parts.append(round(ch_ok / len(channel_results) * 30) if channel_results else 30)
    score_parts.append(round(m_ok / len(model_results) * 50) if model_results else 50)
    size_penalty = 20 if (chat_stats["rows"] > 100_000 or log_stats["rows"] > 200_000) else (
        12 if (chat_stats["rows"] > 50_000 or log_stats["rows"] > 100_000) else 0)
    score_parts.append(20 - size_penalty)
    score = min(100, sum(score_parts))

    return {
        "score": score,
        "channels": {"total": len(channel_results), "ok": ch_ok, "fail": len(channel_results) - ch_ok,
                     "results": channel_results},
        "models": {"total": len(model_results), "ok": m_ok, "fail": len(model_results) - m_ok,
                   "avgLatencyMs": avg_latency,
                   "failures": [r for r in model_results if not r.get("ok")]},
        "upstreamUsage": {k: ops.get(k) for k in
                          ("vol_usage", "stepfun_usage", "zai_usage", "zai2_usage", "cc_usage",
                           "antigravity_usage")},
        "tokenExpiry": ops.get("token_expiry"),
        "storage": {"chatRecord": {"rows": chat_stats["rows"], "size": chat_stats["sizeText"]},
                    "logs": {"rows": log_stats["rows"], "size": log_stats["sizeText"]}},
        "_summary": f"巡检完成：健康度 {score}/100（渠道 {ch_ok}/{len(channel_results)}、"
                    f"模型 {m_ok}/{len(model_results)}、平均时延 {avg_latency}ms）",
    }


def register_ops_tools() -> None:
    register(ToolDef(
        name="get_site_overview",
        description="站点概览：今日/昨日调用量与消费、注册用户数与访客数、全站余额池、累计用量。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_site_overview, timeout=60,
    ))
    register(ToolDef(
        name="get_usage_trend",
        description="用量趋势（全站口径，小时桶预聚合）：按粒度统计每模型调用量/token，返回 Top5 模型摘要与明细序列。",
        parameters={"type": "object", "properties": {
            "days": {"type": "integer", "description": "最近 N 天（默认 7）"},
            "granularity": {"type": "string", "enum": ["hour", "day", "week", "month"], "description": "粒度，默认 day"},
        }, "required": []},
        risk="L0", handler=get_usage_trend, timeout=60,
    ))
    register(ToolDef(
        name="generate_health_report",
        description="一键站点巡检报告：渠道连通抽查 + 模型可用性快探 + 上游额度水位 + 凭证到期 + 存储水位，输出健康度评分。耗时约 1~2 分钟。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=generate_health_report, timeout=300,
    ))
