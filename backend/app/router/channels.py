"""渠道相关接口

【鉴权】渠道数据包含 api_key 等敏感凭证，全部接口需管理员；
公开页面（模型广场的渠道下拉框）使用 /channels/names 只拿渠道名
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.router.deps import get_db
from app.schemas.channel import ChannelSchema
from app.services import channel_service
from app.crud import log as log_crud
from app.utils.auth import get_current_admin
from app.utils.response import success_response

router = APIRouter(prefix="/channels", tags=["Channels"])


@router.get("/names")
async def get_channel_names(db: AsyncSession = Depends(get_db)):
    """获取全量渠道名列表（公开接口，只返回名称，供模型广场的渠道下拉框使用）"""
    names = await channel_service.list_channel_names(db)
    return success_response(message="获取渠道名列表成功", data=names)


@router.get("")
async def get_channels(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """获取全量渠道列表（需管理员，含密钥等敏感字段）"""
    data = await channel_service.list_channels(db)
    return success_response(message="获取渠道列表成功", data=data)


@router.post("")
async def add_channel(
        new_channel: ChannelSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """添加单个渠道（需管理员）"""
    channel_id = await channel_service.create_channel(db, new_channel)
    await log_crud.write_log(
        db, type="admin", action="create_channel", user_id=admin.id, username=admin.username,
        detail=f"新增了渠道 {new_channel.channel_name}",
    )
    return success_response(message="添加渠道成功", data={"channelId": channel_id})


@router.put("/{channel_name}")
async def put_channel(
        channel_name: str,
        update_data: ChannelSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """更新单个渠道数据（按路径中的 channel_name 定位，channel_name 本身不可更新）（需管理员）"""
    await channel_service.update_channel(db, channel_name, update_data)
    await log_crud.write_log(
        db, type="admin", action="update_channel", user_id=admin.id, username=admin.username,
        detail=f"修改了渠道 {channel_name} 的配置",
    )
    return success_response(message="渠道更新成功")


@router.delete("/{channel_name}")
async def delete_channel(
        channel_name: str,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """删除渠道（按路径中的 channel_name 删除）（需管理员）"""
    await channel_service.remove_channel(db, channel_name)
    await log_crud.write_log(
        db, type="admin", action="delete_channel", user_id=admin.id, username=admin.username,
        detail=f"删除了渠道 {channel_name}",
    )
    return success_response(message="渠道删除成功")
