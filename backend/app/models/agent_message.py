"""站点维护 Agent 消息表：会话完整轨迹（含工具调用与审批轨迹）

审计双轨的一轨（另一轨是 logs 的 type=admin 流水）：
- assistant 消息的 tool_calls 列记录模型发起的调用（含参数原文）；
- tool 消息记录执行结果（落库的是 redact() 之后的版本，库里不存密钥）、
  风险等级与审批状态变迁（pending / approved / rejected / timeout）。
"""

from sqlalchemy import BigInteger, Index, Integer, String, Text
from sqlalchemy.dialects.mysql import JSON
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import BaseModel


class AgentMessageTable(BaseModel):
    """维护 Agent 消息表 ORM 模型"""

    __tablename__ = "agent_message"

    __table_args__ = (
        Index("idx_agent_message_session", "session_id", "id"),
        {"comment": "站点维护Agent消息表（含工具与审批轨迹）"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="消息ID")
    session_id: Mapped[int] = mapped_column(Integer, nullable=False, comment="所属会话ID（无外键，删会话联动删消息）")
    role: Mapped[str] = mapped_column(String(16), nullable=False, comment="角色：user / assistant / tool / system")
    content: Mapped[str | None] = mapped_column(Text, comment="消息正文（user/assistant 文本，tool 为结果 JSON）")
    # assistant 发起的工具调用数组：[{id, type, function: {name, arguments}}]
    tool_calls: Mapped[list | None] = mapped_column(JSON, comment="assistant 发起的工具调用（含参数）")
    tool_call_id: Mapped[str | None] = mapped_column(String(64), comment="tool 消息回指的调用ID")
    risk_level: Mapped[str | None] = mapped_column(String(4), comment="工具风险等级：L0 / L1 / L2")
    approval_status: Mapped[str | None] = mapped_column(String(16), default="none",
                                                        server_default="none",
                                                        comment="审批状态：none / pending / approved / rejected / timeout")
    prompt_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输入token数（assistant 消息）")
    completion_tokens: Mapped[int] = mapped_column(Integer, nullable=False, default=0, comment="输出token数（assistant 消息）")

    def __repr__(self):
        return f"<AgentMessage(id={self.id}, session_id={self.session_id}, role='{self.role}')>"
