"""用量统计数据访问层：小时桶 upsert 与聚合查询

【性能设计】监控面板的全站累计读 usage_summary 单行（O(1)）；
折线图 / 范围统计只对 usage_stats 小时桶做 GROUP BY（比原始日志小约三个数量级），
任何接口都不对 logs / chat_record 做全量求和。
"""

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

_EMPTY_SUMMARY = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "cache_tokens": 0}

# 支持的时间粒度（监控面板折线图横坐标）
GRANULARITIES = ("hour", "day", "week", "month")

# 时间粒度 → 桶截断表达式（MySQL）：把 stat_hour 归到该粒度的起点，统一格式化为字符串
_BUCKET_EXPR = {
    "hour": "DATE_FORMAT(stat_hour, '%Y-%m-%d %H:00')",
    "day": "DATE_FORMAT(stat_hour, '%Y-%m-%d')",
    # 周桶归到周一：先取日期再回退 WEEKDAY 天
    "week": "DATE_FORMAT(DATE_SUB(DATE(stat_hour), INTERVAL WEEKDAY(stat_hour) DAY), '%Y-%m-%d')",
    "month": "DATE_FORMAT(stat_hour, '%Y-%m-01')",
}


async def record_usage(
        db: AsyncSession,
        *,
        user_id: int,
        model_name: str,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_tokens: int = 0,
) -> None:
    """把一次调用用量累加到对应的 用户×模型×小时 桶（单语句原子 upsert，不 commit）"""
    stat_hour = datetime.now().replace(minute=0, second=0, microsecond=0)
    await db.execute(
        text("""
            INSERT INTO usage_stats (stat_hour, user_id, model_name, calls,
                                      prompt_tokens, completion_tokens, cache_tokens)
            VALUES (:stat_hour, :user_id, :model_name, 1,
                    :prompt_tokens, :completion_tokens, :cache_tokens)
            ON DUPLICATE KEY UPDATE
                calls = calls + 1,
                prompt_tokens = prompt_tokens + :prompt_tokens,
                completion_tokens = completion_tokens + :completion_tokens,
                cache_tokens = cache_tokens + :cache_tokens
        """),
        {
            "stat_hour": stat_hour, "user_id": user_id, "model_name": model_name,
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cache_tokens": cache_tokens,
        },
    )


async def bump_summary(
        db: AsyncSession,
        *,
        prompt_tokens: int = 0,
        completion_tokens: int = 0,
        cache_tokens: int = 0,
) -> None:
    """把一次调用用量累加到全站汇总行（id=1，单语句原子 upsert，不 commit）"""
    await db.execute(
        text("""
            INSERT INTO usage_summary (id, calls, prompt_tokens, completion_tokens, cache_tokens)
            VALUES (1, 1, :prompt_tokens, :completion_tokens, :cache_tokens)
            ON DUPLICATE KEY UPDATE
                calls = calls + 1,
                prompt_tokens = prompt_tokens + :prompt_tokens,
                completion_tokens = completion_tokens + :completion_tokens,
                cache_tokens = cache_tokens + :cache_tokens
        """),
        {
            "prompt_tokens": prompt_tokens, "completion_tokens": completion_tokens,
            "cache_tokens": cache_tokens,
        },
    )


async def get_summary(db: AsyncSession) -> dict:
    """读取全站累计用量（单行，无聚合计算）"""
    result = await db.execute(
        text("SELECT calls, prompt_tokens, completion_tokens, cache_tokens FROM usage_summary WHERE id = 1")
    )
    row = result.mappings().first()
    return dict(row) if row else dict(_EMPTY_SUMMARY)


async def query_user_series(
    db: AsyncSession,
    *,
    user_id: int,
    start: datetime,
    end: datetime,
    granularity: str = "day",
) -> list[dict]:
    """
    按时间粒度聚合当前用户的用量序列，返回每 桶×模型 一行：
    [{bucket: '2026-08-16', model_name: 'xxx', calls, prompt_tokens, ...}, ...]

    :param granularity: hour / day / week / month
    :param end: 排他上界（桶起点 < end）
    """
    bucket_expr = _BUCKET_EXPR.get(granularity, _BUCKET_EXPR["day"])
    result = await db.execute(
        text(f"""
            SELECT {bucket_expr} AS bucket, model_name,
                   SUM(calls) AS calls,
                   SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens,
                   SUM(cache_tokens) AS cache_tokens
            FROM usage_stats
            WHERE user_id = :user_id AND stat_hour >= :start AND stat_hour < :end
            GROUP BY bucket, model_name
            ORDER BY bucket, model_name
        """),
        {"user_id": user_id, "start": start, "end": end},
    )
    return [dict(r) for r in result.mappings().all()]


async def query_global_series(
    db: AsyncSession,
    *,
    start: datetime,
    end: datetime,
    granularity: str = "day",
) -> list[dict]:
    """全站口径的用量序列（不限用户），结构同 query_user_series；维护 Agent 趋势查询用"""
    bucket_expr = _BUCKET_EXPR.get(granularity, _BUCKET_EXPR["day"])
    result = await db.execute(
        text(f"""
            SELECT {bucket_expr} AS bucket, model_name,
                   SUM(calls) AS calls,
                   SUM(prompt_tokens) AS prompt_tokens,
                   SUM(completion_tokens) AS completion_tokens,
                   SUM(cache_tokens) AS cache_tokens
            FROM usage_stats
            WHERE stat_hour >= :start AND stat_hour < :end
            GROUP BY bucket, model_name
            ORDER BY bucket, model_name
        """),
        {"start": start, "end": end},
    )
    return [dict(r) for r in result.mappings().all()]


async def query_user_totals(
        db: AsyncSession,
        *,
        user_id: int,
        start: datetime,
        end: datetime,
) -> dict:
    """统计当前用户在时间范围内的累计用量（只扫该用户的小时桶行）"""
    result = await db.execute(
        text("""
            SELECT COALESCE(SUM(calls), 0) AS calls,
                   COALESCE(SUM(prompt_tokens), 0) AS prompt_tokens,
                   COALESCE(SUM(completion_tokens), 0) AS completion_tokens,
                   COALESCE(SUM(cache_tokens), 0) AS cache_tokens
            FROM usage_stats
            WHERE user_id = :user_id AND stat_hour >= :start AND stat_hour < :end
        """),
        {"user_id": user_id, "start": start, "end": end},
    )
    return dict(result.mappings().first())
