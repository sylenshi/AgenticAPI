"""兑换码表：管理员批量生成，用户核销后按面值充值余额（零支付通道的充值方式）"""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import DECIMAL, BigInteger, DateTime, Index, Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column
from app.models.base import BaseModel


class RedeemCodeTable(BaseModel):
    """兑换码表 ORM 模型"""

    __tablename__ = "redeem_code"
    __table_args__ = (
        Index("uk_redeem_code", "code"),
        Index("idx_redeem_batch", "batch_no"),
        Index("idx_redeem_used_by", "used_by"),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True, comment="兑换码ID")
    # 对外发放的码值，AGC- 前缀 + 去混淆字符集随机串（区别于登录令牌与 sk- 密钥）
    code: Mapped[str] = mapped_column(String(64), nullable=False, comment="兑换码值")
    # 面值单位与 user.balance 一致（元），DECIMAL 精确小数
    amount: Mapped[Decimal] = mapped_column(
        DECIMAL(12, 6), nullable=False, comment="面值（元，核销后充值到余额的金额）"
    )
    status: Mapped[int] = mapped_column(
        Integer, nullable=False, default=1, server_default=text("1"),
        comment="状态：0已停用 1未使用 2已使用"
    )
    batch_no: Mapped[str] = mapped_column(
        String(32), nullable=False, default="", server_default=text("''"),
        comment="批次号（同一次生成的标识）"
    )
    remark: Mapped[str | None] = mapped_column(String(255), comment="备注")
    # 核销快照：对齐 logs 惯例不建外键、冗余用户名，用户被删除后兑换记录仍可读
    used_by: Mapped[int | None] = mapped_column(Integer, comment="核销用户ID（软关联 user.id）")
    used_username: Mapped[str | None] = mapped_column(String(50), comment="核销用户名快照")
    used_time: Mapped[datetime | None] = mapped_column(DateTime, comment="核销时间")

    def __repr__(self):
        return f"<RedeemCode(id={self.id}, code='{self.code}', amount={self.amount}, status={self.status})>"
