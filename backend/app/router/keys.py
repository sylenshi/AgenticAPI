"""用户 API 密钥管理接口（控制台-秘钥页面使用，需正式账号）"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import api_key as api_key_crud
from app.crud import log as log_crud
from app.router.deps import get_db
from app.schemas.api_key import ApiKeyCreateSchema, ApiKeyUpdateSchema, ApiKeySchema
from app.utils.auth import get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/keys", tags=["Keys"])


@router.get("")
async def list_keys(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """获取当前用户的全部 API 密钥"""
    keys = await api_key_crud.list_by_user(db, user.id)
    data = [ApiKeySchema.model_validate(k).model_dump(by_alias=True, mode="json") for k in keys]
    return success_response(message="获取密钥列表成功", data=data)


@router.post("")
async def create_key(
        body: ApiKeyCreateSchema,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """创建 API 密钥（每个用户最多 5 个）"""
    key = await api_key_crud.create_key(db, user.id, body.name.strip())
    if not key:
        raise HTTPException(status_code=400, detail=f"每个用户最多创建 {api_key_crud.MAX_KEYS_PER_USER} 个密钥")
    await log_crud.write_log(
        db, type="user", action="create_key", user_id=user.id, username=user.username,
        detail=f"创建了 API 密钥「{key.name}」",
    )
    data = ApiKeySchema.model_validate(key).model_dump(by_alias=True, mode="json")
    return success_response(message="密钥创建成功", data=data)


@router.put("/{key_id}")
async def update_key(
        key_id: int,
        body: ApiKeyUpdateSchema,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """更新自己的密钥（改名 / 启停）"""
    update_dict = body.model_dump(exclude_unset=True, exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")
    rowcount = await api_key_crud.update_key(db, user.id, key_id, update_dict)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="密钥不存在")
    await log_crud.write_log(
        db, type="user", action="update_key", user_id=user.id, username=user.username,
        detail=f"修改了 API 密钥（id={key_id}）",
    )
    return success_response(message="密钥更新成功")


@router.delete("/{key_id}")
async def delete_key(
        key_id: int,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """删除自己的密钥"""
    rowcount = await api_key_crud.delete_key(db, user.id, key_id)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="密钥不存在")
    await log_crud.write_log(
        db, type="user", action="delete_key", user_id=user.id, username=user.username,
        detail=f"删除了 API 密钥（id={key_id}）",
    )
    return success_response(message="密钥删除成功")
