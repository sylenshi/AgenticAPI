"""运营速查域工具（E1~E4）+ F1 一键巡检报告：全部只读

数据源复用既有口径：usage_summary 单行 / logs 聚合 / usage_stats 预聚合 /
redeem_crud.code_stats / user 表 COUNT——不对原始大表做全量扫描。
"""

import asyncio
from datetime import datetime, timedelta

from sqlalchemy import text

from app.crud import redeem_code as redeem_crud
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


async def get_redeem_stats(ctx: ToolContext, args: dict) -> dict:
    """E3 兑换码统计（复用管理端 /admin/redeem-codes/stats 的 service 层口径）"""
    stats = await redeem_crud.code_stats(ctx.db)
    if isinstance(stats, dict):
        stats["_summary"] = "兑换码监控统计已获取（发行/未使用/已使用/核销金额）"
    return stats


async def query_users(ctx: ToolContext, args: dict) -> dict:
    """E4 用户查询（只读）：搜索 / 余额排行 / 封禁名单。改余额封禁请走用户管理页。"""
    keyword = (args.get("keyword") or "").strip()
    order_by = args.get("order_by") or "id"
    banned_only = bool(args.get("banned_only"))
    limit = min(int(args.get("limit") or 10), 50)
    if order_by not in ("id", "balance"):
        raise ValueError("order_by 仅支持 id / balance")

    conditions, params = [], {}
    if keyword:
        conditions.append("(username LIKE :kw OR nickname LIKE :kw)")
        params["kw"] = f"%{keyword}%"
    if banned_only:
        conditions.append("status = 0")
    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    order = "balance DESC" if order_by == "balance" else "id DESC"

    rows = (await ctx.db.execute(text(f"""
        SELECT id, username, nickname, user_group, is_admin, is_guest, status,
               balance, used_quota, last_login_time, create_time
        FROM user {where} ORDER BY {order} LIMIT :limit
    """), {**params, "limit": limit})).mappings().all()
    total = (await ctx.db.execute(text(f"SELECT COUNT(*) FROM user {where}"), params)).scalar_one()

    return {
        "total": total,
        "returned": len(rows),
        "users": [{**dict(r), "balance": f"{float(r['balance']):.4f}",
                   "used_quota": f"{float(r['used_quota']):.4f}"} for r in rows],
        "_summary": f"用户查询：命中 {total} 条（展示 {len(rows)}，排序 {order_by}）"
                    + ("，仅封禁用户" if banned_only else ""),
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
        name="get_redeem_stats",
        description="兑换码统计：发行量/未使用/已使用/已核销金额四卡数据。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_redeem_stats,
    ))
    register(ToolDef(
        name="query_users",
        description="用户查询（只读）：按用户名/昵称搜索、余额排行、封禁名单。修改余额/封禁请走用户管理页。",
        parameters={"type": "object", "properties": {
            "keyword": {"type": "string", "description": "用户名/昵称模糊搜索（可选）"},
            "order_by": {"type": "string", "enum": ["id", "balance"], "description": "排序键，默认 id"},
            "banned_only": {"type": "boolean", "description": "仅看封禁用户，默认 false"},
            "limit": {"type": "integer", "description": "返回条数上限（默认 10，最大 50）"},
        }, "required": []},
        risk="L0", handler=query_users,
    ))
    register(ToolDef(
        name="generate_health_report",
        description="一键站点巡检报告：渠道连通抽查 + 模型可用性快探 + 上游额度水位 + 凭证到期 + 存储水位，输出健康度评分。耗时约 1~2 分钟。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=generate_health_report, timeout=300,
    ))
