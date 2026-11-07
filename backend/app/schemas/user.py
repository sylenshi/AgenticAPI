from datetime import datetime
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field


# 用户登录/注册请求模型（字段约束与前端表单校验规则保持一致）
class UserLoginSchema(BaseModel):
    username: str = Field(min_length=2, max_length=50, description="用户名")
    password: str = Field(min_length=6, max_length=100, description="密码")


# 用户自助修改资料请求（控制台-概览页使用，空字符串视为清空）
class UserProfileUpdateSchema(BaseModel):
    nickname: Optional[str] = Field(default=None, max_length=50, alias="nickname")
    phone: Optional[str] = Field(default=None, max_length=20, alias="phone")

    model_config = {"populate_by_name": True}


# 用户信息模型
class UserInfoSchema(BaseModel):
    id: int
    username: str
    nickname: Optional[str] = None
    phone: Optional[str] = None
    avatar: Optional[str] = None  # 预设头像URL（/avatars/avatar-N.png），None 时前端回退首字符
    is_guest: bool = Field(default=False, alias="isGuest")
    is_admin: bool = Field(default=False, alias="isAdmin")
    balance: Decimal = Field(default=0, alias="balance")
    used_quota: Decimal = Field(default=0, alias="usedQuota")
    user_group: str = Field(default="free", alias="userGroup")
    create_time: Optional[datetime] = Field(default=None, alias="createTime")
    last_login_time: Optional[datetime] = Field(default=None, alias="lastLoginTime")

    model_config = {
        "from_attributes": True,  # 允许从 ORM 模型属性填充字段
        "populate_by_name": True,  # 通过字段名填充模型字段
    }


# 用户请求响应模型
class UserAuthSchema(BaseModel):
    token: str
    user_info: UserInfoSchema = Field(...,alias = "userInfo")

    model_config = {
        "from_attributes": True, # 从模型属性填充字段
        "populate_by_name": True # 通过字段名填充模型字段
    }
