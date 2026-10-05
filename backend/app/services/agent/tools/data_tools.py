"""数据治理域工具（D1~D5）：chat_record / logs / usage_stats 的容量统计、导出、清理

数据库安全红线：
- 清理只走带条件分批 DELETE（每批 5000 行 + 批间 200ms 休止），禁 TRUNCATE/DROP；
- L2 两段式：dry_run=true 先 COUNT 预览（审批卡片可见），确认后再真删；
- backup_first：清理前自动全量导出受影响数据为 zip。
"""

import asyncio
import json
from datetime import datetime, timedelta

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import export_service
from app.services.agent.registry import ToolContext, ToolDef, register

DELETE_BATCH_SIZE = 5000
DELETE_BATCH_PAUSE = 0.2  # 批间休止（秒）：防长事务锁表与 binlog 洪峰


async def _table_stats(db: AsyncSession, table: str) -> dict:
    """单表容量统计：行数 / 存储占用 / 最早最晚记录 / 按月分布"""
    count = (await db.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()
    size = (await db.execute(text("""
        SELECT COALESCE(DATA_LENGTH + INDEX_LENGTH, 0), COALESCE(TABLE_ROWS, 0)
        FROM information_schema.TABLES
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = :t
    """), {"t": table})).first()
    bounds = (await db.execute(text(
        f"SELECT MIN(create_time), MAX(create_time) FROM {table}"))).first()
    monthly = (await db.execute(text(f"""
        SELECT DATE_FORMAT(create_time, '%Y-%m') AS month, COUNT(*) AS rows_
        FROM {table} GROUP BY month ORDER BY month
    """))).mappings().all()

    data_length = int(size[0]) if size else 0
    return {
        "table": table,
        "rows": count,
        "sizeBytes": data_length,
        "sizeText": f"{data_length / 1024 / 1024:.2f} MB" if data_length >= 1024 * 1024 else f"{data_length / 1024:.1f} KB",
        "earliest": str(bounds[0]) if bounds and bounds[0] else None,
        "latest": str(bounds[1]) if bounds and bounds[1] else None,
        "monthlyDistribution": [{"month": r["month"], "rows": r["rows_"]} for r in monthly],
    }


def _stats_summary(stats: dict) -> str:
    return (f"{stats['table']}：{stats['rows']} 行 / {stats['sizeText']}"
            + (f"，最早 {stats['earliest']}" if stats["earliest"] else ""))


async def get_table_stats_tool(ctx: ToolContext, args: dict, table: str) -> dict:
    stats = await _table_stats(ctx.db, table)
    stats["_summary"] = _stats_summary(stats)
    # 清理建议：超过 10 万行或 50MB 提示治理
    advice = []
    if stats["rows"] > 100_000:
        advice.append("行数超过 10 万，建议导出后清理历史数据（cleanup 系列工具，L2 需审批）")
    if stats["sizeBytes"] > 50 * 1024 * 1024:
        advice.append(f"存储占用 {stats['sizeText']} 超过 50MB，建议治理")
    stats["advice"] = advice
    return stats


async def export_table_tool(ctx: ToolContext, args: dict, table: str, label: str,
                            time_filter_field: str = "create_time") -> dict:
    """通用导出：时间范围过滤 → zip（一次性 token 下载），数据本体不进对话上下文"""
    conditions, params = [], {}
    start, end = args.get("start_time"), args.get("end_time")
    if start:
        conditions.append(f"{time_filter_field} >= :start")
        params["start"] = start
    if end:
        conditions.append(f"{time_filter_field} < :end")
        params["end"] = end
    where = " AND ".join(conditions)

    result = await export_service.export_table_to_zip(
        ctx.db, table=table, label=label, where_sql=where, params=params)
    await ctx.emit({"type": "download_ready", "url": result["downloadUrl"], "label": label,
                    "size": result["sizeText"], "expiresAt": result["expiresAt"]})
    result.pop("token")  # token 已编码在 URL，不重复暴露
    return result


async def _count_to_delete(db: AsyncSession, table: str, where: str, params: dict) -> int:
    return (await db.execute(
        text(f"SELECT COUNT(*) FROM {table} WHERE {where}"), params)).scalar_one()


async def _batch_delete(db: AsyncSession, table: str, where: str, params: dict) -> int:
    """分批 DELETE：每批 LIMIT 5000 + 批间休止，返回累计删除行数"""
    total = 0
    while True:
        result = await db.execute(text(
            f"DELETE FROM {table} WHERE id IN (SELECT id FROM ("
            f"SELECT id FROM {table} WHERE {where} LIMIT :batch) AS t)"
        ), {**params, "batch": DELETE_BATCH_SIZE})
        await db.commit()
        deleted = result.rowcount or 0
        total += deleted
        if deleted < DELETE_BATCH_SIZE:
            return total
        await asyncio.sleep(DELETE_BATCH_PAUSE)  # 休止：给复制/锁让路


def _parse_cutoff(args: dict) -> tuple[str | None, dict]:
    """解析清理条件：keep_days（保留近 N 天）或 keep_count（保留最近 N 条）→ (where, params)"""
    keep_days, keep_count = args.get("keep_days"), args.get("keep_count")
    if keep_days is not None and keep_count is not None:
        raise ValueError("keep_days 与 keep_count 只能二选一")
    if keep_days is not None:
        days = int(keep_days)
        if days < 1:
            raise ValueError(f"keep_days 至少为 1（全清请走管理页手工操作），收到 {days}")
        cutoff = datetime.now() - timedelta(days=days)
        return "create_time < :cutoff", {"cutoff": cutoff}
    if keep_count is not None:
        count = int(keep_count)
        if count < 0:
            raise ValueError("keep_count 不能为负数")
        return ("id < (SELECT COALESCE(MIN(id), 0) FROM ("
                "SELECT id FROM {table} ORDER BY id DESC LIMIT :keep) AS t)", {"keep": count})
    return None, {}


async def cleanup_table_tool(ctx: ToolContext, args: dict, table: str, label: str) -> dict:
    """
    通用清理（L2 两段式）：dry_run=true 返回预览；false 时先按需备份再分批真删。
    """
    dry_run = bool(args.get("dry_run", True))
    backup_first = bool(args.get("backup_first", True))
    where_tpl, params = _parse_cutoff(args)
    if where_tpl is None:
        raise ValueError("必须提供 keep_days（保留近 N 天）或 keep_count（保留最近 N 条）之一")

    where = where_tpl.format(table=table)

    if dry_run:
        count = await _count_to_delete(ctx.db, table, where, params)
        return {
            "dryRun": True,
            "table": table,
            "wouldDelete": count,
            "params": {k: str(v) for k, v in params.items()},
            "hint": "以上为预览。确认无误后请以 dry_run=false 重新调用（将再次弹出审批卡片）",
            "_summary": f"[dry-run] {label} 预计删除 {count} 行",
        }

    # ── 真删阶段：先备份（可选）→ 分批删除 → 复核统计 ──
    backup_info = None
    if backup_first:
        backup_info = await export_service.export_table_to_zip(
            ctx.db, table=table, label=f"{label}（清理前备份）", where_sql=where, params=params)
        await ctx.emit({"type": "download_ready", "url": backup_info["downloadUrl"],
                        "label": f"{label}·清理前备份", "size": backup_info["sizeText"],
                        "expiresAt": backup_info["expiresAt"]})

    deleted = await _batch_delete(ctx.db, table, where, params)
    remaining = (await ctx.db.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()

    result = {
        "dryRun": False,
        "table": table,
        "deleted": deleted,
        "remaining": remaining,
        "backup": backup_info,
        "optimizeHint": f"如需回收磁盘空间，可在管理端手工执行 OPTIMIZE TABLE {table}（不自动执行）",
        "_summary": f"{label} 实删 {deleted} 行，剩余 {remaining} 行"
                    + ("（已自动备份）" if backup_info else ""),
    }
    return result


# ── chat_record（D1/D2/D3）──

async def get_chat_record_stats(ctx: ToolContext, args: dict) -> dict:
    return await get_table_stats_tool(ctx, args, "chat_record")


async def export_chat_records(ctx: ToolContext, args: dict) -> dict:
    return await export_table_tool(ctx, args, "chat_record", "对话记录导出")


async def cleanup_chat_records(ctx: ToolContext, args: dict) -> dict:
    return await cleanup_table_tool(ctx, args, "chat_record", "对话记录")


# ── logs（D4）──

async def get_log_stats(ctx: ToolContext, args: dict) -> dict:
    stats = await get_table_stats_tool(ctx, args, "logs")
    # 附加：按 type 分布
    by_type = (await ctx.db.execute(text(
        "SELECT type, COUNT(*) AS c FROM logs GROUP BY type"))).mappings().all()
    stats["byType"] = {r["type"]: r["c"] for r in by_type}
    return stats


async def export_logs(ctx: ToolContext, args: dict) -> dict:
    result = await export_table_tool(ctx, args, "logs", "调用日志导出")
    return result


async def cleanup_logs(ctx: ToolContext, args: dict) -> dict:
    args.setdefault("keep_days", 90)
    return await cleanup_table_tool(ctx, args, "logs", "调用日志")


# ── usage_stats 聚合表（D5；usage_summary 是单行表不涉及清理）──

async def get_aggregate_stats(ctx: ToolContext, args: dict) -> dict:
    stats = await _table_stats(ctx.db, "usage_stats")
    stats["_summary"] = _stats_summary(stats)
    stats["note"] = "usage_summary 为单行汇总表，不涉及清理"
    return stats


async def cleanup_aggregate_stats(ctx: ToolContext, args: dict) -> dict:
    args.setdefault("keep_days", 180)  # 小时桶预聚合默认保留近 6 个月
    return await cleanup_table_tool(ctx, args, "usage_stats", "用量聚合表")


def register_data_tools() -> None:
    register(ToolDef(
        name="get_chat_record_stats",
        description="对话记录表 chat_record 容量统计：总行数/存储占用/按月分布/最早最晚记录，附清理建议。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_chat_record_stats, timeout=60,
    ))
    register(ToolDef(
        name="export_chat_records",
        description="导出对话记录为 zip（JSONL·gzip，一次性下载链接 24h 有效）。可按时间范围过滤。数据本体不进对话。",
        parameters={"type": "object", "properties": {
            "start_time": {"type": "string", "description": "起始时间（YYYY-MM-DD 或 YYYY-MM-DD HH:MM:SS，可选）"},
            "end_time": {"type": "string", "description": "结束时间（排他上界，可选）"},
        }, "required": []},
        risk="L1", handler=export_chat_records, timeout=120,
    ))
    register(ToolDef(
        name="cleanup_chat_records",
        description="清理对话记录（L2 高危·两段式·强制审批）：keep_days 或 keep_count 二选一；首次调用务必 dry_run=true 预览删除量，确认后 dry_run=false 真删（分批 5000 行）。默认清理前自动备份导出。",
        parameters={"type": "object", "properties": {
            "keep_days": {"type": "integer", "description": "保留最近 N 天（与 keep_count 二选一）"},
            "keep_count": {"type": "integer", "description": "保留最近 N 条（与 keep_days 二选一）"},
            "backup_first": {"type": "boolean", "description": "清理前自动导出备份，默认 true"},
            "dry_run": {"type": "boolean", "description": "true=仅预览删除量（默认），false=真删"},
        }, "required": []},
        risk="L2", handler=cleanup_chat_records, timeout=300,
    ))
    register(ToolDef(
        name="get_log_stats",
        description="调用日志表 logs 容量统计（行数/占用/按月/按 type 分布），附清理建议。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_log_stats, timeout=60,
    ))
    register(ToolDef(
        name="export_logs",
        description="导出调用日志为 zip（可按时间范围过滤），一次性下载链接。",
        parameters={"type": "object", "properties": {
            "start_time": {"type": "string", "description": "起始时间（可选）"},
            "end_time": {"type": "string", "description": "结束时间（可选）"},
        }, "required": []},
        risk="L1", handler=export_logs, timeout=120,
    ))
    register(ToolDef(
        name="cleanup_logs",
        description="清理调用日志（L2 高危·两段式·强制审批）：默认保留近 90 天（keep_days 可调）。",
        parameters={"type": "object", "properties": {
            "keep_days": {"type": "integer", "description": "保留最近 N 天，默认 90"},
            "keep_count": {"type": "integer", "description": "保留最近 N 条（与 keep_days 二选一）"},
            "backup_first": {"type": "boolean", "description": "清理前自动导出备份，默认 true"},
            "dry_run": {"type": "boolean", "description": "true=仅预览（默认），false=真删"},
        }, "required": []},
        risk="L2", handler=cleanup_logs, timeout=300,
    ))
    register(ToolDef(
        name="get_aggregate_stats",
        description="用量聚合表 usage_stats（小时桶）容量统计。",
        parameters={"type": "object", "properties": {}, "required": []},
        risk="L0", handler=get_aggregate_stats, timeout=60,
    ))
    register(ToolDef(
        name="cleanup_aggregate_stats",
        description="清理用量聚合表旧小时桶（L2 高危·两段式·强制审批）：默认保留近 180 天。",
        parameters={"type": "object", "properties": {
            "keep_days": {"type": "integer", "description": "保留最近 N 天，默认 180"},
            "backup_first": {"type": "boolean", "description": "清理前自动导出备份，默认 true"},
            "dry_run": {"type": "boolean", "description": "true=仅预览（默认），false=真删"},
        }, "required": []},
        risk="L2", handler=cleanup_aggregate_stats, timeout=300,
    ))
