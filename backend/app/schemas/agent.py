"""维护 Agent 请求 Schema（管理端接口，遵循站内驼峰别名规范）"""

from pydantic import BaseModel, Field


class AgentSessionCreateSchema(BaseModel):
    """新建会话"""

    title: str = Field(default="新会话", max_length=128, description="会话标题")


class AgentSessionUpdateSchema(BaseModel):
    """更新会话设置（标题 / 模型 / 安全开关）"""

    title: str | None = Field(default=None, max_length=128)
    model_name: str | None = Field(default=None, max_length=128,
                                   alias="modelName", description="切换驱动模型")
    auto_approve_l1: bool | None = Field(default=None, alias="autoApproveL1",
                                         description="L1 自动批准开关")
    enable_l2: bool | None = Field(default=None, alias="enableL2",
                                   description="L2 高危工具开关")

    model_config = {"populate_by_name": True}


class AgentChatSchema(BaseModel):
    """对话请求（响应为 SSE 流，OpenAI 风格报文）"""

    session_id: int = Field(alias="sessionId", description="会话ID")
    content: str = Field(min_length=1, max_length=16000, description="用户消息文本")

    model_config = {"populate_by_name": True}


class AgentApproveSchema(BaseModel):
    """审批决议"""

    approval_id: str = Field(alias="approvalId", max_length=64)
    approved: bool = Field(description="true=批准 false=拒绝")

    model_config = {"populate_by_name": True}
