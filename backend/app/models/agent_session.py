"""站点维护 Agent 会话表：一次完整的管理员-维护Agent对话

会话记录驱动模型（可中途切换，见 session_tools.switch_model）与两个安全开关；
消息本体在 agent_message 表，删除会话时联动删除。
保留策略：每用户最近 50 个 + 近 30 天，新建会话时惰性清理（crud/agent.py）。
"""

from sqlalchemy import Boolean, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentSessionTable(BaseModel):
    """维护 Agent 会话表 ORM 模型"""

    __tablename__ = "agent_session"

    __table_args__ = (
        Index("idx_agent_session_user", "user_id"),
        {"comment": "站点维护Agent会话表"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True, comment="会话ID")
    user_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="管理员用户ID（快照，无外键）")
    title: Mapped[str] = mapped_column(String(128), nullable=False, default="新会话",
                                       server_default="新会话", comment="会话标题（agent_service 自动生成）")
    model_name: Mapped[str] = mapped_column(String(128), nullable=False, comment="当前驱动模型（站内出站模型名）")
    # L1 自动批准：开启后低危写工具跳过审批卡片（always_confirm 工具不受此豁免）
    auto_approve_l1: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                   server_default="0", comment="L1 工具自动批准开关")
    # 关闭后 L2 高危工具不注入 tools（只读模式会话）
    enable_l2: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default="1", comment="L2 高危工具启用开关")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active",
                                        server_default="active", comment="会话状态：active / archived")

    def __repr__(self):
        return f"<AgentSession(id={self.id}, user_id={self.user_id}, model='{self.model_name}')>"
