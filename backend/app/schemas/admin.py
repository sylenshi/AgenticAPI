"""管理员用户管理相关 Schema"""

from decimal import Decimal

from pydantic import BaseModel, Field

# 允许的用户分组（与 llm_models.model_group 的分组体系对应）
ALLOWED_GROUPS = ("free", "vip")


class AdminUserUpdateSchema(BaseModel):
    """管理员修改用户信息（部分更新语义，至少传一个字段）"""
    nickname: str | None = Field(default=None, max_length=50, alias="nickname")
    balance: Decimal | None = Field(default=None, ge=0, alias="balance")
    user_group: str | None = Field(default=None, alias="userGroup")
    is_admin: bool | None = Field(default=None, alias="isAdmin")
    status: bool | None = Field(default=None, alias="status")

    model_config = {"populate_by_name": True}


class AdminUserBatchDeleteSchema(BaseModel):
    """管理员批量删除用户请求"""
    ids: list[int] = Field(min_length=1, alias="ids")

    model_config = {"populate_by_name": True}


class SettingsUpdateSchema(BaseModel):
    """站点设置更新（部分更新语义，至少传一个字段；均可在控制台-设置页调整）

    alias 与设置页前端提交字段（camelCase，同 GET 响应）对齐；
    agent_default_model 传空串表示清除指定、恢复默认解析链（.env → 首个启用模型）
    """
    chat_record_max_tokens: int | None = Field(default=None, ge=100, le=1_000_000, alias="chatRecordMaxTokens")
    agent_default_model: str | None = Field(default=None, max_length=128, alias="agentDefaultModel")
    agent_task_cost_limit: Decimal | None = Field(default=None, ge=0, le=100_000, alias="agentTaskCostLimit")
    register_initial_balance: Decimal | None = Field(default=None, ge=0, le=100_000, alias="registerInitialBalance")
    guest_initial_balance: Decimal | None = Field(default=None, ge=0, le=100_000, alias="guestInitialBalance")
    register_user_group: str | None = Field(default=None, alias="registerUserGroup")

    model_config = {"populate_by_name": True}
