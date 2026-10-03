"""兑换码表数据访问层"""

import secrets
from datetime import datetime
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud.log import write_log
from app.models.redeem_code import RedeemCodeTable
from app.models.user import UserTabel

# 兑换码单次生成上限
MAX_GENERATE_COUNT = 100
# 码值字符集：去掉易混淆的 0/O/1/I（码值统一大写）
CODE_ALPHABET = "23456789ABCDEFGHJKLMNPQRSTUVWXYZ"


def generate_redeem_code() -> str:
    """生成单个兑换码：AGC- 前缀 + 3 组 5 位随机串（32^15 组合，碰撞概率可忽略）"""
    body = "-".join(
        "".join(secrets.choice(CODE_ALPHABET) for _ in range(5))
        for _ in range(3)
    )
    return f"AGC-{body}"


def generate_batch_no() -> str:
    """自动批次号：B + 日期 + 4 位随机（如 B20261003A1B2）"""
    return f"B{datetime.now():%Y%m%d}{secrets.token_hex(2).upper()}"


async def generate_codes(
        db: AsyncSession, count: int, amount: Decimal, batch_no: str, remark: str | None
) -> list[RedeemCodeTable]:
    """批量生成兑换码（status 默认 1 未使用），返回生成的记录列表"""
    codes = [
        RedeemCodeTable(code=generate_redeem_code(), amount=amount, batch_no=batch_no, remark=remark)
        for _ in range(count)
    ]
    db.add_all(codes)
    await db.commit()
    return codes


async def query_codes(
        db: AsyncSession,
        page: int = 1,
        page_size: int = 10,
        status: int | None = None,
        keyword: str = "",
        batch_no: str = "",
) -> tuple[list[RedeemCodeTable], int]:
    """分页查询兑换码列表（可按状态 / 码值或使用人关键字 / 批次筛选），返回 (码列表, 总数)"""
    conditions = []
    if status is not None:
        conditions.append(RedeemCodeTable.status == status)
    if keyword.strip():
        kw = f"%{keyword.strip()}%"
        conditions.append(
            or_(RedeemCodeTable.code.like(kw), RedeemCodeTable.used_username.like(kw))
        )
    if batch_no.strip():
        conditions.append(RedeemCodeTable.batch_no.like(f"%{batch_no.strip()}%"))

    count_result = await db.execute(
        select(func.count()).select_from(RedeemCodeTable).where(*conditions)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(RedeemCodeTable)
        .where(*conditions)
        .order_by(RedeemCodeTable.id.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def list_user_records(
        db: AsyncSession, user_id: int, page: int = 1, page_size: int = 10
) -> tuple[list[RedeemCodeTable], int]:
    """分页查询用户的兑换记录（已核销的码，按核销时间倒序）"""
    conditions = [RedeemCodeTable.used_by == user_id, RedeemCodeTable.status == 2]

    count_result = await db.execute(
        select(func.count()).select_from(RedeemCodeTable).where(*conditions)
    )
    total = count_result.scalar_one()

    result = await db.execute(
        select(RedeemCodeTable)
        .where(*conditions)
        .order_by(RedeemCodeTable.used_time.desc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    )
    return list(result.scalars().all()), total


async def code_stats(db: AsyncSession) -> dict:
    """兑换码监控统计：各状态计数 + 已核销总金额（一条分组聚合）"""
    result = await db.execute(
        select(RedeemCodeTable.status, func.count(), func.sum(RedeemCodeTable.amount))
        .group_by(RedeemCodeTable.status)
    )
    stats = {
        "totalCount": 0, "unusedCount": 0, "usedCount": 0,
        "disabledCount": 0, "usedAmount": Decimal("0"),
    }
    for status, count, amount_sum in result.all():
        stats["totalCount"] += count
        if status == 0:
            stats["disabledCount"] = count
        elif status == 1:
            stats["unusedCount"] = count
        elif status == 2:
            stats["usedCount"] = count
            stats["usedAmount"] = amount_sum or Decimal("0")
    return stats


async def disable_code(db: AsyncSession, code_id: int) -> int:
    """停用未使用的兑换码（已使用/已停用的码不受影响），返回受影响行数"""
    result = await db.execute(
        update(RedeemCodeTable)
        .where(RedeemCodeTable.id == code_id, RedeemCodeTable.status == 1)
        .values(status=0)
    )
    await db.commit()
    return result.rowcount


async def redeem(db: AsyncSession, user_id: int, username: str, code: str) -> tuple[Decimal, Decimal]:
    """
    核销兑换码并充值余额，返回 (面值, 用户新余额)。

    单事务保证原子性：锁定码行（FOR UPDATE 防并发重复核销）→ 状态校验 →
    置为已使用 → 余额原子增加（与 deduct_balance 对称的列表达式写法）→
    同事务写日志（auto_commit=False）→ 一次提交。
    状态校验失败抛 ValueError（文案可直接作为 HTTP 400 的 detail）。
    """
    normalized = code.strip().upper()
    # 锁定目标码行：并发核销同一张码时，后到的事务会等待并读到已核销状态
    result = await db.execute(
        select(RedeemCodeTable).where(RedeemCodeTable.code == normalized).with_for_update()
    )
    record = result.scalars().one_or_none()
    if not record:
        raise ValueError("兑换码不存在，请检查输入")
    if record.status == 2:
        raise ValueError("该兑换码已被使用")
    if record.status == 0:
        raise ValueError("该兑换码已停用")

    record.status = 2
    record.used_by = user_id
    record.used_username = username
    record.used_time = datetime.now()

    await db.execute(
        update(UserTabel)
        .where(UserTabel.id == user_id)
        .values(balance=UserTabel.balance + record.amount)
    )
    await write_log(
        db, type="user", action="redeem_code", user_id=user_id, username=username,
        detail=f"兑换码「{record.code}」充值 {record.amount} 元", cost=record.amount, auto_commit=False,
    )
    await db.commit()

    balance_result = await db.execute(select(UserTabel.balance).where(UserTabel.id == user_id))
    return record.amount, balance_result.scalar_one()
