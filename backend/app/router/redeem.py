"""兑换码接口：用户端兑换与记录（/redeem）+ 管理端生成/管理/监控（/admin/redeem-codes）"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import log as log_crud
from app.crud import redeem_code as redeem_crud
from app.router.deps import get_db
from app.schemas.redeem_code import (
    RedeemCodeSchema,
    RedeemGenerateSchema,
    RedeemRecordSchema,
    RedeemRequestSchema,
)
from app.utils.auth import get_current_admin, get_current_user
from app.utils.response import success_response

# 用户端：兑换与我的兑换记录（访客禁止兑换）
redeem_router = APIRouter(prefix="/redeem", tags=["Redeem"])
# 管理端：兑换码生成 / 管理 / 监控
admin_router = APIRouter(prefix="/admin/redeem-codes", tags=["Admin"])


def _normalize_page(page: int, page_size: int) -> tuple[int, int]:
    """分页参数归一化（与 /admin/users 约定一致）"""
    if page < 1:
        page = 1
    if page_size < 1 or page_size > 100:
        page_size = 10
    return page, page_size


# ═══════════════════════ 用户端 ═══════════════════════

@redeem_router.post("")
async def redeem_code(
        body: RedeemRequestSchema,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """兑换码核销充值：成功返回用户新余额（字符串保精度），前端即时更新展示"""
    if user.is_guest:
        raise HTTPException(status_code=403, detail="访客账号不支持兑换")
    try:
        amount, balance = await redeem_crud.redeem(db, user.id, user.username, body.code)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return success_response(message=f"兑换成功，余额 +{amount} 元", data={"balance": str(balance)})


@redeem_router.get("/records")
async def redeem_records(
        page: int = 1,
        pageSize: int = 10,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """我的兑换记录（已核销的码，按核销时间倒序）"""
    page, page_size = _normalize_page(page, pageSize)
    records, total = await redeem_crud.list_user_records(db, user.id, page, page_size)
    data = [RedeemRecordSchema.model_validate(r).model_dump(by_alias=True, mode="json") for r in records]
    return success_response(message="获取兑换记录成功", data={"list": data, "total": total})


# ═══════════════════════ 管理端 ═══════════════════════

@admin_router.post("/generate")
async def generate_codes(
        body: RedeemGenerateSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """批量生成兑换码（单次最多 100 张），返回全部码值供导出"""
    batch_no = (body.batch_no or "").strip() or redeem_crud.generate_batch_no()
    codes = await redeem_crud.generate_codes(db, body.count, body.amount, batch_no, (body.remark or "").strip() or None)
    await log_crud.write_log(
        db, type="admin", action="generate_redeem_codes", user_id=admin.id, username=admin.username,
        detail=f"生成了 {len(codes)} 张面值 {body.amount} 元的兑换码（批次 {batch_no}）",
    )
    return success_response(
        message=f"成功生成 {len(codes)} 张兑换码",
        data={"codes": [c.code for c in codes], "batchNo": batch_no},
    )


@admin_router.get("/stats")
async def redeem_stats(
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """兑换码监控统计（各状态数量 + 已核销总金额）"""
    return success_response(message="获取兑换码统计成功", data=await redeem_crud.code_stats(db))


@admin_router.get("")
async def list_codes(
        status: int | None = None,
        keyword: str = "",
        batchNo: str = "",
        page: int = 1,
        pageSize: int = 10,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """分页查询兑换码列表（可按状态 / 码值或使用人关键字 / 批次筛选）"""
    page, page_size = _normalize_page(page, pageSize)
    codes, total = await redeem_crud.query_codes(db, page, page_size, status, keyword, batchNo)
    data = [RedeemCodeSchema.model_validate(c).model_dump(by_alias=True, mode="json") for c in codes]
    return success_response(message="获取兑换码列表成功", data={"list": data, "total": total})


@admin_router.put("/{code_id}/disable")
async def disable_code(
        code_id: int,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """停用未使用的兑换码（已核销的码不可停用）"""
    rowcount = await redeem_crud.disable_code(db, code_id)
    if rowcount == 0:
        raise HTTPException(status_code=400, detail="仅未使用的兑换码可以停用")
    await log_crud.write_log(
        db, type="admin", action="disable_redeem_code", user_id=admin.id, username=admin.username,
        detail=f"停用了兑换码（id={code_id}）",
    )
    return success_response(message="兑换码已停用")
