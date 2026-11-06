from datetime import datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import Index, Integer, String, Enum, DateTime, ForeignKey, Boolean, DECIMAL, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class UserTabel(BaseModel):
    """
    用户信息表ORM模型
    """
    __tablename__ = 'user'

    # 创建索引
    __table_args__ = (
        Index('username_UNIQUE', 'username'),
        Index('phone_UNIQUE', 'phone'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="用户ID")
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False, comment="用户名")
    password: Mapped[str] = mapped_column(String(255), nullable=False, comment="密码（加密存储）")
    nickname: Mapped[Optional[str]] = mapped_column(String(50), comment="昵称")
    phone: Mapped[Optional[str]] = mapped_column(String(20), unique=True, comment="手机号")
    # 访客标记：访客账号由 /user/guest 创建（随机用户名密码、令牌24小时），
    # 无权调用管理类接口，且会被惰性清理（见 crud/user.py 的 clean_expired_guests）
    is_guest: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"),
        comment="是否为访客账号"
    )
    is_admin: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False, server_default=text("0"),
        comment="是否为管理员"
    )
    # 余额与累计消费：DECIMAL 精确小数（金额不用 FLOAT，避免浮点误差），
    # 单位与模型定价一致（每百万 token 的价格）
    balance: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 6), nullable=False, default=0, server_default=text("0"),
        comment="账户余额"
    )
    used_quota: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 6), nullable=False, default=0, server_default=text("0"),
        comment="累计消费金额"
    )
    # 用户分组（与 llm_models.model_group 对应）：
    # free 只能调用 free 分组的模型；vip 可调用全部分组模型（管理员默认 vip）
    user_group: Mapped[str] = mapped_column(
        String(20), nullable=False, default="free", server_default=text("'free'"),
        comment="用户分组：free / vip"
    )
    status: Mapped[bool] = mapped_column(
        Integer, nullable=False, default=True, server_default=text("1"),
        comment="账号状态：0封禁 1正常"
    )
    last_login_time: Mapped[Optional[datetime]] = mapped_column(DateTime, comment="最后登录时间")

    def __repr__(self):
        return f"<User(id={self.id}, username='{self.username}', nickname='{self.nickname}')>"


class UserTokenTabel(BaseModel):
    """
    用户令牌表ORM模型
    """
    __tablename__ = 'user_token'

    # 创建索引
    __table_args__ = (
        Index('token_UNIQUE', 'token'),
        Index('fk_user_token_user_idx', 'user_id'),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="令牌ID")
    user_id: Mapped[int] = mapped_column(Integer, ForeignKey(UserTabel.id), nullable=False, comment="用户ID")
    token: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, comment="令牌值")
    expires_time: Mapped[datetime] = mapped_column(DateTime, nullable=False, comment="过期时间")

    def __repr__(self):
        return f"<UserToken(id={self.id}, user_id={self.user_id}, token='{self.token}')>"

