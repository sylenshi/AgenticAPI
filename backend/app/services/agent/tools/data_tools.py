"""数据治理域内部函数（v0.11.0：8 个数据治理工具下线，改由 data-governance 技能 +
容器沙箱内 pymysql 脚本承担统计 / 导出 / 清理，见 backend/app/agent_skills/data-governance.md）

本模块仅保留一键巡检（generate_health_report）依赖的 _table_stats 容量统计内核。
原分批 DELETE / zip 导出等能力随工具一并下线（export_service 已删除）；
沙箱侧脚本的安全约束（禁 TRUNCATE/DROP、分批删除、凭证列禁查）由技能 SOP 承载。
"""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


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
