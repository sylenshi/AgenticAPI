"""维护 Agent 会话/消息数据访问层

保留策略（惰性清理，先例：访客账号清理）：每用户最多保留最近 50 个会话、
仅保留近 30 天创建的会话；新建会话时触发，联动删除过期/超限会话的消息，
清理动作写一条 admin 日志（action=agent_session_gc）。
"""

from datetime import datetime, timedelta

from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import log as log_crud
from app.models.agent_message import AgentMessageTable
from app.models.agent_session import AgentSessionTable

# 保留策略常量
MAX_SESSIONS_PER_USER = 50
SESSION_KEEP_DAYS = 30

# 审批档位合法值（v0.11.0 三档位，取代旧 auto_approve_l1 / enable_l2 两开关）
APPROVAL_MODES = ("confirm_all", "confirm_critical", "full")


def resolve_approval_mode(session) -> str:
    """解析会话审批档位：approval_mode 列优先；旧数据列缺失/空值时由旧开关推导。

    兼容 ORM 行与原生查询 dict 两种载体（get_session 返回 ORM 行、list_sessions 返回 dict）。
    推导规则：旧 auto_approve_l1=True → confirm_critical（部分审批），否则 confirm_all（需要审批）。
    """
    mode = (session.get("approval_mode") if isinstance(session, dict)
            else getattr(session, "approval_mode", None)) or ""
    if mode in APPROVAL_MODES:
        return mode
    legacy = (session.get("auto_approve_l1") if isinstance(session, dict)
              else getattr(session, "auto_approve_l1", 0))
    return "confirm_critical" if legacy else "confirm_all"


async def insert_message(
    db: AsyncSession,
    *,
    session_id: int,
    role: str,
    content: str | None = None,
    tool_calls: list | None = None,
    tool_call_id: str | None = None,
    tool_name: str | None = None,
    risk_level: str | None = None,
    approval_status: str | None = None,
    prompt_tokens: int = 0,
    completion_tokens: int = 0,
) -> int:
    """追加一条会话消息，返回自增 id（工具结果传入的 content 必须是 redact() 之后的版本）"""
    row = AgentMessageTable(
        session_id=session_id,
        role=role,
        content=content,
        tool_calls=tool_calls,
        tool_call_id=tool_call_id,
        tool_name=tool_name,
        risk_level=risk_level,
        approval_status=approval_status,
        prompt_tokens=prompt_tokens,
        completion_tokens=completion_tokens,
    )
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row.id


async def list_messages(db: AsyncSession, session_id: int) -> list[dict]:
    """按 id 升序取会话全部消息（历史装配与前端回放共用）。

    tool_calls 是 JSON 列：asyncmy 原生查询返回字符串，这里统一解析为 list。
    """
    import json

    result = await db.execute(
        text("SELECT * FROM agent_message WHERE session_id = :sid ORDER BY id ASC"),
        {"sid": session_id},
    )
    rows = []
    for row in result.mappings().all():
        record = dict(row)
        if isinstance(record.get("tool_calls"), str):
            try:
                record["tool_calls"] = json.loads(record["tool_calls"])
            except (TypeError, ValueError):
                record["tool_calls"] = None
        rows.append(record)
    return rows


async def count_tool_executions(db: AsyncSession, session_id: int) -> dict[str, int]:
    """按工具名统计会话内已执行成功的次数（会话配额计数口径）。

    返回 dict：tool_name → 次数；另有特殊键 "_legacy_l2" 承接 tool_name 列上线前的
    旧 L2 记录（彼时只有 delete_channel / delete_model 两工具，由调用方并入二者计数）。
    成功口径 = 非 isError 结果（isError 结果由异常路径产生，不会到达配额累加）。
    """
    result = await db.execute(
        text("""
            SELECT
              COALESCE(tool_name, '_legacy_l2') AS tool_key,
              COUNT(*) AS cnt
            FROM agent_message
            WHERE session_id = :sid AND role = 'tool'
              AND (tool_name IS NOT NULL OR (risk_level = 'L2' AND approval_status = 'approved'))
              AND content NOT LIKE '%"isError": true%'
            GROUP BY tool_key
        """),
        {"sid": session_id},
    )
    return {r["tool_key"]: int(r["cnt"]) for r in result.mappings().all()}


async def get_session(db: AsyncSession, session_id: int) -> AgentSessionTable | None:
    result = await db.execute(
        select(AgentSessionTable).where(AgentSessionTable.id == session_id)
    )
    return result.scalars().one_or_none()


async def list_sessions(db: AsyncSession, user_id: int) -> list[dict]:
    """用户维度的会话列表（最近优先）"""
    result = await db.execute(
        text("""
            SELECT id, user_id, title, model_name, approval_mode, auto_approve_l1, enable_l2, status,
                   create_time, update_time
            FROM agent_session WHERE user_id = :uid ORDER BY id DESC
        """),
        {"uid": user_id},
    )
    return [dict(r) for r in result.mappings().all()]


async def create_session(db: AsyncSession, *, user_id: int, model_name: str,
                         title: str = "新会话") -> AgentSessionTable:
    """新建会话（调用方负责先跑惰性清理 + 默认模型解析）"""
    row = AgentSessionTable(user_id=user_id, model_name=model_name, title=title)
    db.add(row)
    await db.commit()
    await db.refresh(row)
    return row


async def update_session(db: AsyncSession, session_id: int, update_dict: dict) -> None:
    """按会话 id 动态更新字段（标题 / 模型 / 开关）"""
    if not update_dict:
        return
    set_clause = ", ".join(f"{k} = :{k}" for k in update_dict)
    await db.execute(
        text(f"UPDATE agent_session SET {set_clause} WHERE id = :sid"),
        {**update_dict, "sid": session_id},
    )
    await db.commit()


async def delete_session(db: AsyncSession, session_id: int) -> int:
    """删除会话并联动删除消息，返回删除的消息数"""
    result = await db.execute(
        text("DELETE FROM agent_message WHERE session_id = :sid"),
        {"sid": session_id},
    )
    msg_count = result.rowcount
    await db.execute(text("DELETE FROM agent_session WHERE id = :sid"), {"sid": session_id})
    await db.commit()
    return msg_count


async def delete_all_sessions(db: AsyncSession, user_id: int, *, username: str) -> tuple[int, int]:
    """一键清空：删除用户全部会话及消息（单事务）并写 admin 日志，返回 (会话数, 消息数)"""
    msg_result = await db.execute(
        text("""
            DELETE am FROM agent_message am
            JOIN agent_session s ON am.session_id = s.id
            WHERE s.user_id = :uid
        """),
        {"uid": user_id},
    )
    msg_count = msg_result.rowcount or 0
    ses_result = await db.execute(
        text("DELETE FROM agent_session WHERE user_id = :uid"), {"uid": user_id})
    ses_count = ses_result.rowcount or 0
    await db.commit()
    if ses_count or msg_count:
        await log_crud.write_log(
            db, type="admin", action="agent_session_clear", user_id=user_id, username=username,
            detail=f"一键清空维护Agent会话 {ses_count} 个（联动删除消息 {msg_count} 条）",
        )
    return ses_count, msg_count


async def gc_sessions(db: AsyncSession, user_id: int, *, username: str) -> int:
    """
    惰性清理当前用户的过期/超限会话，返回删除的会话数。

    规则：create_time 早于 30 天前的会话删除；剩余会话只保留最近 50 个。
    先例：访客账号惰性清理——不引入后台定时任务，新建会话时顺带执行。
    """
    cutoff = datetime.now() - timedelta(days=SESSION_KEEP_DAYS)
    result = await db.execute(
        text("""
            SELECT id FROM agent_session
            WHERE user_id = :uid AND (create_time < :cutoff OR id NOT IN (
                SELECT id FROM (
                    SELECT id FROM agent_session WHERE user_id = :uid
                    ORDER BY id DESC LIMIT :max_keep
                ) AS keep_ids
            ))
        """),
        {"uid": user_id, "cutoff": cutoff, "max_keep": MAX_SESSIONS_PER_USER},
    )
    dead_ids = [r["id"] for r in result.mappings().all()]
    if not dead_ids:
        return 0

    placeholders = ",".join(str(i) for i in dead_ids)
    msg_result = await db.execute(
        text(f"DELETE FROM agent_message WHERE session_id IN ({placeholders})")
    )
    msg_count = msg_result.rowcount
    await db.execute(text(f"DELETE FROM agent_session WHERE id IN ({placeholders})"))
    await db.commit()

    await log_crud.write_log(
        db, type="admin", action="agent_session_gc", user_id=user_id, username=username,
        detail=f"惰性清理过期/超限维护Agent会话 {len(dead_ids)} 个（联动删除消息 {msg_count} 条）",
    )
    return len(dead_ids)
