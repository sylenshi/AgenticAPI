"""兑换码相关 Schema"""

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class RedeemRequestSchema(BaseModel):
    """用户兑换请求"""
    code: str = Field(min_length=1, max_length=64, description="兑换码")


class RedeemGenerateSchema(BaseModel):
    """管理员批量生成兑换码请求"""
    count: int = Field(ge=1, le=100, description="生成数量（1~100）")
    amount: Decimal = Field(gt=0, max_digits=12, decimal_places=6, description="每张面值（元）")
    batch_no: str | None = Field(default=None, max_length=32, alias="batchNo", description="批次号，留空自动生成")
    remark: str | None = Field(default=None, max_length=255, description="备注")

    model_config = {"populate_by_name": True}


class RedeemCodeSchema(BaseModel):
    """兑换码信息响应（管理员列表用）"""
    id: int
    code: str
    amount: Decimal
    status: int = Field(default=1, description="状态：0已停用 1未使用 2已使用")
    batch_no: str = Field(default="", alias="batchNo")
    remark: str | None = Field(default=None)
    used_by: int | None = Field(default=None, alias="usedBy")
    used_username: str | None = Field(default=None, alias="usedUsername")
    used_time: datetime | None = Field(default=None, alias="usedTime")
    create_time: datetime | None = Field(default=None, alias="createTime")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }


class RedeemRecordSchema(BaseModel):
    """用户兑换记录响应"""
    id: int
    code: str
    amount: Decimal
    used_time: datetime | None = Field(default=None, alias="usedTime")

    model_config = {
        "from_attributes": True,
        "populate_by_name": True,
    }
