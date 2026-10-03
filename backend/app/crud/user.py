import secrets
import uuid
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional

from sqlalchemy import delete, func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud import api_key as api_key_crud
from app.models import UserTokenTabel
from app.models.api_key import ApiKeyTable
from app.models.user import UserTabel
from app.schemas.user import UserLoginSchema
from app.utils.security import hash_password, verify_password


# 根据用户名查询用户信息
async def get_user_by_username(db: AsyncSession, username: str) -> Optional[UserTabel]:
    """
    根据用户名查询用户信息
    """
    query = select(UserTabel).where(UserTabel.username == username)
    result = await db.execute(query)
    return result.scalars().first()


# 创建用户
async def create_user(db: AsyncSession, user_data: UserLoginSchema) -> UserTabel:
    """
    创建用户
    """
    # 先密码加密
    hashed_password = hash_password(user_data.password)
    # 再创建用户（正式注册统一进 vip 分组，可调用全部分组模型；访客走 create_guest_user 进 free）
    user = UserTabel(
        username=user_data.username,
        password=hashed_password,
        user_group="vip",
    )
    db.add(user)  # 这里不使用await，因为add方法是同步的
    await db.commit()
    await db.refresh(user)  # 刷新用户信息，确保密码被加密存储
    return user


# 生成用户令牌Token
async def generate_user_token(db: AsyncSession, user_id: int, expires_days: int = 30) -> str:
    """
    生成用户令牌Token
    :param expires_days: 令牌有效天数，正式账号默认30天，访客账号传1天
    """
    # 生成令牌
    token = str(uuid.uuid4())
    # 过期时间
    expires_time = datetime.now() + timedelta(days=expires_days)
    # 查询当前用户是否存在token
    query = select(UserTokenTabel).where(UserTokenTabel.user_id == user_id)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()
    if user_token:
        # 已有令牌时，令牌值和过期时间必须一起刷新：
        # 只换令牌不续期的话，重新登录拿到的新令牌会带着旧的过期时间，一出生就是过期的
        user_token.token = token
        user_token.expires_time = expires_time
    else:
        # 如果不存在token，创建新token
        user_token = UserTokenTabel(
            user_id=user_id,
            token=token,
            expires_time=expires_time
        )
        db.add(user_token)
    await db.commit()
    return token


# 删除用户令牌（登出时调用，令牌立即失效）
async def delete_user_token(db: AsyncSession, token: str) -> None:
    """
    删除用户令牌
    """
    query = select(UserTokenTabel).where(UserTokenTabel.token == token)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()
    if user_token:
        await db.delete(user_token)
        await db.commit()


async def authenticate_user(db: AsyncSession, user_data: UserLoginSchema) -> Optional[UserTabel]:
    """
    认证用户：验证用户名和密码是否匹配
    """
    user = await get_user_by_username(db, user_data.username)
    # 如果用户不存在，返回None
    if not user:
        return None
    # 验证密码是否匹配
    if not verify_password(user_data.password, user.password):
        return None
    return user


async def get_user_by_token(db: AsyncSession, token: str) -> Optional[UserTabel]:
    """
    根据访问令牌查询用户信息
    """
    query = select(UserTokenTabel).where(UserTokenTabel.token == token)
    result = await db.execute(query)
    user_token = result.scalar_one_or_none()
    # 如果token不存在或过期，返回None
    if not user_token or user_token.expires_time < datetime.now():
        return None
    # 如果存在token，查询用户信息
    query = select(UserTabel).where(UserTabel.id == user_token.user_id)
    result = await db.execute(query)
    # scalars()把行结果转成ORM对象序列，取单条用 one_or_none()
    return result.scalars().one_or_none()


async def get_api_key_by_user_id(db: AsyncSession, user_id: int) -> Optional[ApiKeyTable]:
    """
    获取一个当前用户的API KEY，没有就创建一个。
    优先返回启用状态的密钥：拨测等自调用场景若拿到禁用密钥，中转只会回 401，
    表现为"渠道异常"的误报。
    """
    query = select(ApiKeyTable).where(ApiKeyTable.user_id == user_id)
    result = await db.execute(query)
    keys = result.scalars().all()
    if not keys:
        return await api_key_crud.create_key(db, user_id, name="默认密钥")
    for k in keys:
        if k.status:
            return k
    return keys[0]


# 创建访客账号：随机用户名/密码（访客自己也不知道密码，所以无法拿它去登录），is_guest=True
async def create_guest_user(db: AsyncSession) -> UserTabel:
    """
    创建临时访客账号
    """
    suffix = uuid.uuid4().hex[:8]  # 随机后缀，保证用户名不重复
    user = UserTabel(
        username=f"guest_{suffix}",
        password=hash_password(secrets.token_urlsafe(16)),
        nickname=f"访客{suffix[:4]}",  # 导航栏展示用，比guest_xxxx友好
        is_guest=True,
        user_group="free",  # 访客显式固定 free 分组（仅免费模型），与正式注册的 vip 区分
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return user


# 清理过期访客账号：没有有效令牌（已过期或已登出）的访客，连人带令牌一起删
# 【策略】惰性清理：每次创建新访客时顺带执行，省掉引入定时任务的复杂度（访客量大了再换成定时任务）
async def clean_expired_guests(db: AsyncSession) -> int:
    """
    清理过期访客账号，返回清理数量
    """
    now = datetime.now()
    # 左连接查出所有访客及其令牌过期时间（没有令牌行的访客过期时间为None，同样视为可清理）
    result = await db.execute(
        select(UserTabel.id, UserTokenTabel.expires_time)
        .outerjoin(UserTokenTabel, UserTokenTabel.user_id == UserTabel.id)
        .where(UserTabel.is_guest.is_(True))
    )
    dead_ids = [
        user_id
        for user_id, expires_time in result.all()
        if expires_time is None or expires_time < now
    ]
    if not dead_ids:
        return 0
    # 先删令牌行再删用户行（user_token.user_id 有外键约束指向 user.id）
    await db.execute(delete(UserTokenTabel).where(UserTokenTabel.user_id.in_(dead_ids)))
    await db.execute(delete(UserTabel).where(UserTabel.id.in_(dead_ids)))
    await db.commit()
    return len(dead_ids)


# 更新最后登录时间（登录/注册/访客创建时调用）
async def touch_last_login(db: AsyncSession, user_id: int) -> None:
    """
    更新用户最后登录时间
    """
    await db.execute(
        update(UserTabel).where(UserTabel.id == user_id).values(last_login_time=datetime.now())
    )
    await db.commit()


# 扣减余额并累计消费（中转调用成功后计费；SQL 原子自减，避免并发读到旧值）
async def deduct_balance(db: AsyncSession, user_id: int, cost: Decimal) -> None:
    """
    扣减用户余额，累加累计消费
    """
    await db.execute(
        update(UserTabel)
        .where(UserTabel.id == user_id)
        .values(balance=UserTabel.balance - cost, used_quota=UserTabel.used_quota + cost)
    )
    await db.commit()


# ═══════════════════════ 管理员用户管理 ═══════════════════════

async def get_user_by_id(db: AsyncSession, user_id: int) -> Optional[UserTabel]:
    """
    按ID查询用户
    """
    result = await db.execute(select(UserTabel).where(UserTabel.id == user_id))
    return result.scalars().one_or_none()


async def list_users(
        db: AsyncSession, keyword: str = "", page: int = 1, pageSize: int = 10
) -> tuple[list[UserTabel], int]:
    """
    分页查询用户列表（可按用户名/昵称模糊搜索），返回 (用户列表, 总数)
    """
    conditions = []
    if keyword:
        conditions.append(
            or_(UserTabel.username.like(f"%{keyword}%"), UserTabel.nickname.like(f"%{keyword}%"))
        )
    count_result = await db.execute(select(func.count()).select_from(UserTabel).where(*conditions))
    total = count_result.scalar_one()

    result = await db.execute(
        select(UserTabel)
        .where(*conditions)
        .order_by(UserTabel.id.asc())
        .offset((page - 1) * pageSize)
        .limit(pageSize)
    )
    return list(result.scalars().all()), total


async def update_user_by_id(db: AsyncSession, user_id: int, update_dict: dict) -> int:
    """
    管理员按ID更新用户字段，返回受影响行数
    """
    result = await db.execute(
        update(UserTabel).where(UserTabel.id == user_id).values(**update_dict)
    )
    await db.commit()
    return result.rowcount


async def delete_users(db: AsyncSession, user_ids: list[int]) -> int:
    """
    批量删除用户：连带删除其登录令牌与API密钥（外键约束要求先删子表），返回删除的用户数
    """
    if not user_ids:
        return 0
    await db.execute(delete(UserTokenTabel).where(UserTokenTabel.user_id.in_(user_ids)))
    await db.execute(delete(ApiKeyTable).where(ApiKeyTable.user_id.in_(user_ids)))
    result = await db.execute(delete(UserTabel).where(UserTabel.id.in_(user_ids)))
    await db.commit()
    return result.rowcount
