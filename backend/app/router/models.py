"""模型相关接口

【鉴权】模型广场是公开页面，GET 列表不要求登录；
增删改属于管理操作，需管理员权限（访客/普通用户均403）
"""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.router.deps import get_db
from app.schemas.model import ModelSchema
from app.services import model_service
from app.crud import log as log_crud
from app.utils.auth import get_current_admin, get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/models", tags=["Models"])


@router.get("")
async def get_models(db: AsyncSession = Depends(get_db)):
    """获取全量模型列表（公开）"""
    data = await model_service.list_models(db)
    return success_response(message="获取模型列表成功", data=data)


@router.post("")
async def add_model(
        new_model: ModelSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """添加单个模型（需管理员）"""
    model_id = await model_service.create_model(db, new_model)
    await log_crud.write_log(
        db, type="admin", action="create_model", user_id=admin.id, username=admin.username,
        detail=f"新增了模型 {new_model.name}",
    )
    return success_response(message="添加模型成功", data={"modelId": model_id})


@router.post("/test/{model_name}")
async def test_model(
        model_name: str,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """模型拨测（POST，规范 §3.2；每用户 60s 冷却防无限触发真实上游调用），
    无需管理员权限，普通用户可调用，走公网接口，正常扣费、记录日志。
    分组权限在服务层前置校验：free 用户只能拨 free 分组模型，vip 可拨全部"""

    response = await model_service.test_model(db, model_name, user)

    return success_response(message="模型响应成功", data=response)


@router.put("/{model_name}")
async def put_model(
        model_name: str,
        update_data: ModelSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """更新单个模型数据（按路径中的 name 定位，name 本身不可更新）（需管理员）"""
    await model_service.update_model(db, model_name, update_data)
    await log_crud.write_log(
        db, type="admin", action="update_model", user_id=admin.id, username=admin.username,
        detail=f"修改了模型 {model_name} 的配置",
    )
    return success_response(message="模型更新成功")


@router.delete("/{model_name}")
async def delete_model(
        model_name: str,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """删除模型（按路径中的 name 删除）（需管理员）"""
    await model_service.remove_model(db, model_name)
    await log_crud.write_log(
        db, type="admin", action="delete_model", user_id=admin.id, username=admin.username,
        detail=f"删除了模型 {model_name}",
    )
    return success_response(message="模型删除成功")
