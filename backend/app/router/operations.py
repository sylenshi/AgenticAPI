"""上游运维接口

【鉴权】涉及上游平台的用量数据与凭证读写，全部接口需管理员
"""

from fastapi import APIRouter, Body, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.services import operations_service
from app.crud import log as log_crud
from app.router.deps import get_db
from app.utils.auth import get_current_admin
from app.utils.response import success_response

router = APIRouter(prefix="/operations", tags=["Operations"])


@router.get("/get")
def get_operations(refresh_channel: str = "all", _admin=Depends(get_current_admin)):
    """
    获取上游运维数据（需管理员）
    :param refresh_channel: 刷新的渠道，可选值为 "vol"、"stepfun"、"zai2"、"antigravity" 或 "all"
    """
    data = operations_service.get_operations(refresh_channel)
    return success_response(message="获取运维数据成功", data=data)


@router.post("/upload")
async def upload_settings(
        brmToken: str = Body(None),
        instanceId: str = Body(None),
        stepToken: str = Body(None),
        stepWebid: str = Body(None),
        zaiApiKey: str = Body(None),
        admin=Depends(get_current_admin),
        db: AsyncSession = Depends(get_db),
):
    """更新上游运维凭证（需管理员）；智谱 key 上传后优先于 .env 兜底值（方便换号）"""
    data = operations_service.upload_settings(
        brmToken, instanceId, stepToken, stepWebid, zaiApiKey or ""
    )
    await log_crud.write_log(
        db, type="admin", action="upload_credentials", user_id=admin.id, username=admin.username,
        detail="更新了上游运维凭证",
    )
    return success_response(message="运维凭证更新成功", data=data)
