"""数据导出服务：chat_record / logs 等大表导出为 zip 下载文件

上下文压力的泄压阀：导出类工具只把 {下载链接, 文件大小, 行数, 过期时间} 回传给
模型，数据本体绝不进入对话上下文。

- 分批流式读取（id 游标递进，每批 1000 行），避免一次性载入内存；
- JSONL（gzip）打包 zip，存放 backend/data/exports/{token}.zip；
- token 一次性 + 24h 过期：下载即失效；每次导出前顺带清理过期文件（惰性清理）。
"""

import gzip
import io
import json
import secrets
import time
import zipfile
from datetime import datetime, timedelta
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import DATA_DIR

EXPORTS_DIR = DATA_DIR / "exports"
EXPORT_TTL_HOURS = 24
BATCH_SIZE = 1000

# token → 文件信息（进程内登记表；重启丢失只是文件不可下载，无数据风险）
_exports: dict[str, dict] = {}


def _serialize_row(row: dict) -> str:
    """一行转 JSONL：datetime/Decimal 等类型安全序列化"""
    return json.dumps(row, ensure_ascii=False, default=str, separators=(",", ":"))


def cleanup_expired() -> int:
    """删除超过 TTL 的导出文件与登记项（每次导出前惰性执行），返回清理数量"""
    if not EXPORTS_DIR.exists():
        return 0
    now = time.time()
    removed = 0
    for path in EXPORTS_DIR.glob("*.zip"):
        try:
            if now - path.stat().st_mtime > EXPORT_TTL_HOURS * 3600:
                path.unlink()
                removed += 1
        except OSError:
            continue
    for token in [t for t, info in _exports.items() if now - info["created_at"] > EXPORT_TTL_HOURS * 3600]:
        _exports.pop(token, None)
    return removed


def consume_export(token: str) -> Path | None:
    """校验并消费一次性下载 token，返回文件路径；无效/过期/已用返回 None"""
    info = _exports.get(token)
    if not info:
        return None
    _exports.pop(token, None)  # 一次性：登记即删，无论后续文件读取是否成功
    if time.time() - info["created_at"] > EXPORT_TTL_HOURS * 3600:
        return None
    path: Path = info["path"]
    return path if path.is_file() else None


async def export_table_to_zip(
    db: AsyncSession,
    *,
    table: str,
    label: str,
    where_sql: str = "",
    params: dict | None = None,
) -> dict:
    """
    按条件导出一张表为 zip（JSONL·gzip），返回登记信息（含下载 token）。

    :param where_sql: 不含 WHERE 关键字的条件串（空 = 全量）
    :param label: 下载文件展示名（如 "对话记录 2026-01-01~2026-07-01"）
    """
    cleanup_expired()
    params = params or {}
    where = f"WHERE {where_sql}" if where_sql else ""

    EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
    token = secrets.token_hex(16)
    zip_path = EXPORTS_DIR / f"{token}.zip"
    total_rows = 0
    last_id = 0

    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
        buf = io.StringIO()
        # id 游标递进分批读取，防大表一次性载入内存
        while True:
            result = await db.execute(
                text(f"""
                    SELECT * FROM {table} {where} AND id > :last_id
                    ORDER BY id ASC LIMIT :limit
                """ if where else f"""
                    SELECT * FROM {table} WHERE id > :last_id
                    ORDER BY id ASC LIMIT :limit
                """),
                {**params, "last_id": last_id, "limit": BATCH_SIZE},
            )
            rows = [dict(r) for r in result.mappings().all()]
            if not rows:
                break
            for row in rows:
                buf.write(_serialize_row(row) + "\n")
            total_rows += len(rows)
            last_id = rows[-1]["id"]
            if len(rows) < BATCH_SIZE:
                break
        # 空结果也产出合法 zip（内含空 JSONL），保持"导出成功"语义可验证
        zf.writestr(f"{table}.jsonl", gzip.compress(buf.getvalue().encode("utf-8")))

    size_bytes = zip_path.stat().st_size
    expires_at = datetime.now() + timedelta(hours=EXPORT_TTL_HOURS)
    _exports[token] = {"path": zip_path, "created_at": time.time()}

    return {
        "downloadUrl": f"/maintain-agent/exports/{token}",
        "label": label,
        "rows": total_rows,
        "sizeBytes": size_bytes,
        "sizeText": f"{size_bytes / 1024:.1f} KB" if size_bytes < 1024 * 1024 else f"{size_bytes / 1024 / 1024:.2f} MB",
        "expiresAt": expires_at.strftime("%Y-%m-%d %H:%M"),
        "token": token,
        # 一句话摘要：脱水时占位用
        "_summary": f"已导出 {label}（{total_rows} 行，{size_bytes / 1024:.1f} KB）",
    }
