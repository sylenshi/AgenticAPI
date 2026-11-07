"""站点维护 Agent 会话表：一次完整的管理员-维护Agent对话

会话记录驱动模型（切换走前端选择器，下一轮生效）与审批档位；
消息本体在 agent_message 表，删除会话时联动删除。
保留策略：每用户最近 50 个 + 近 30 天，新建会话时惰性清理（crud/agent.py）。

v0.11.0：审批分级由"L1 自动批准 + L2 开关"两开关简化为三档位 approval_mode
（confirm_all 需要审批 / confirm_critical 部分审批 / full 完全权限）；
旧列 auto_approve_l1 / enable_l2 保留仅作兼容（读取回退用，不再写入），
已有库需手动 ALTER 加 approval_mode 列（见 deploy.md）。
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
    # 审批档位：confirm_all=全部写操作弹审批 / confirm_critical=仅 L2+强审名单弹卡 / full=全免审批
    approval_mode: Mapped[str] = mapped_column(String(20), nullable=False, default="confirm_all",
                                               server_default="confirm_all", comment="审批档位")
    # ── 以下两列为 v0.11.0 前的旧开关，仅保留做兼容回退，代码不再写入 ──
    auto_approve_l1: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False,
                                                   server_default="0", comment="[旧] L1 自动批准开关（已由 approval_mode 取代）")
    enable_l2: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True,
                                            server_default="1", comment="[旧] L2 高危工具开关（已由 approval_mode 取代）")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active",
                                        server_default="active", comment="会话状态：active / archived")

    def __repr__(self):
        return f"<AgentSession(id={self.id}, user_id={self.user_id}, model='{self.model_name}')>"
