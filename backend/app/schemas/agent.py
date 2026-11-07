"""维护 Agent 请求 Schema（管理端接口，遵循站内驼峰别名规范）"""

from pydantic import BaseModel, Field

# 审批档位合法值（与 crud.agent.APPROVAL_MODES 一致）
APPROVAL_MODE_VALUES = ("confirm_all", "confirm_critical", "full")


class AgentSessionCreateSchema(BaseModel):
    """新建会话"""

    title: str = Field(default="新会话", max_length=128, description="会话标题")


class AgentSessionUpdateSchema(BaseModel):
    """更新会话设置（标题 / 模型 / 审批档位）"""

    title: str | None = Field(default=None, max_length=128)
    model_name: str | None = Field(default=None, max_length=128,
                                   alias="modelName", description="切换驱动模型")
    approval_mode: str | None = Field(default=None, alias="approvalMode",
                                      description="审批档位：confirm_all 需要审批 / "
                                                  "confirm_critical 部分审批 / full 完全权限")

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
