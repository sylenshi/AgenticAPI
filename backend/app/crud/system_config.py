"""系统配置表数据访问层（键值对，管理员可在控制台-设置页在线调整）

所有配置键统一在此登记，读写走 GET/PUT /admin/settings：
- chat_record_max_tokens：对话记录长度阈值，输入+输出 token 超过该值的调用不落库对话内容
- agent_default_model：维护 Agent 默认大脑模型（解析链：本配置 → .env → 站内首个启用模型）
- register_initial_balance：正式注册用户的初始余额（默认 0）
- guest_initial_balance：访客账号的初始余额（默认 0，与正式注册独立配置）
"""

from decimal import Decimal

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

# 对话记录长度阈值的配置键：输入+输出 token 超过该值的调用不落库对话内容
CHAT_RECORD_MAX_TOKENS_KEY = "chat_record_max_tokens"
CHAT_RECORD_MAX_TOKENS_DEFAULT = 5000

# 维护 Agent 默认大脑模型的配置键（空值 = 未指定，走 .env / 首个启用模型兜底链）
AGENT_DEFAULT_MODEL_KEY = "agent_default_model"

# 注册初始余额的配置键（正式注册与访客各一个，互相独立）
REGISTER_INITIAL_BALANCE_KEY = "register_initial_balance"
GUEST_INITIAL_BALANCE_KEY = "guest_initial_balance"
INITIAL_BALANCE_DEFAULT = Decimal("0")


async def get_value(db: AsyncSession, key: str, default: str | None = None) -> str | None:
    """按配置键读取配置值，不存在返回 default"""
    result = await db.execute(
        text("SELECT config_value FROM system_config WHERE config_key = :key LIMIT 1"),
        {"key": key},
    )
    row = result.mappings().first()
    return row["config_value"] if row else default


async def set_value(db: AsyncSession, key: str, value: str) -> None:
    """写入配置值（不存在则插入，存在则覆盖）"""
    await db.execute(
        text(
            """
            INSERT INTO system_config (config_key, config_value)
            VALUES (:key, :value)
            ON DUPLICATE KEY UPDATE config_value = VALUES(config_value)
            """
        ),
        {"key": key, "value": value},
    )
    await db.commit()


async def get_chat_record_threshold(db: AsyncSession) -> int:
    """读取对话记录长度阈值（输入+输出 token 上限），未配置或值非法时返回默认 5000"""
    value = await get_value(db, CHAT_RECORD_MAX_TOKENS_KEY)
    try:
        return max(int(value), 0)
    except (TypeError, ValueError):
        return CHAT_RECORD_MAX_TOKENS_DEFAULT


async def get_initial_balance(db: AsyncSession, key: str) -> Decimal:
    """读取初始余额类配置（注册/访客），未配置或值非法时返回 0；两位小数封顶（与余额 DECIMAL 精度对齐）"""
    value = await get_value(db, key)
    try:
        return max(Decimal(value).quantize(Decimal("0.01")), INITIAL_BALANCE_DEFAULT)
    except (TypeError, ValueError, ArithmeticError):
        return INITIAL_BALANCE_DEFAULT
