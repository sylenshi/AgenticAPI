"""管理员用户管理接口（控制台-用户页面使用，需管理员权限）+ 站点设置接口（控制台-设置页）"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud import log as log_crud
from app.crud import model as model_crud
from app.crud import system_config as config_crud
from app.crud import user as user_crud
from app.router.deps import get_db
from app.router.maintain_agent import _resolve_default_model as resolve_default_model
from app.schemas.admin import ALLOWED_GROUPS, AdminUserBatchDeleteSchema, AdminUserUpdateSchema, SettingsUpdateSchema
from app.utils.auth import get_current_admin
from app.utils.pagination import normalize_page
from app.utils.response import success_response

router = APIRouter(prefix="/admin", tags=["Admin"])


def _user_dict(user) -> dict:
    """ORM 对象转驼峰字典"""
    return {
        "id": user.id,
        "username": user.username,
        "nickname": user.nickname,
        "phone": user.phone,
        "isGuest": user.is_guest,
        "isAdmin": user.is_admin,
        "balance": float(user.balance),
        "usedQuota": float(user.used_quota),
        "userGroup": user.user_group,
        "status": user.status,
        "lastLoginTime": user.last_login_time,
        "createTime": user.create_time,
    }


@router.get("/users")
async def list_users(
        keyword: str = "",
        page: int = 1,
        pageSize: int = 10,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """分页查询用户列表（可按用户名/昵称模糊搜索）"""
    page, pageSize = normalize_page(page, pageSize)
    users, total = await user_crud.list_users(db, keyword.strip(), page, pageSize)
    return success_response(message="获取用户列表成功", data={"list": [_user_dict(u) for u in users], "total": total})


@router.put("/users/{user_id}")
async def update_user(
        user_id: int,
        body: AdminUserUpdateSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """修改用户信息（余额 / 分组 / 管理员 / 状态 / 昵称）"""
    target = await user_crud.get_user_by_id(db, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="用户不存在")

    update_dict = body.model_dump(exclude_unset=True, exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")

    # 分组取值校验
    if "user_group" in update_dict and update_dict["user_group"] not in ALLOWED_GROUPS:
        raise HTTPException(status_code=400, detail=f"分组只能是 {' / '.join(ALLOWED_GROUPS)}")

    # 不变量：管理员必须是 vip 分组（vip 才能调用全部分组的模型）
    if update_dict.get("is_admin") is True:
        update_dict["user_group"] = "vip"

    # 不允许修改自己的管理员身份（防止误操作把自己降权后没人能管理用户）
    if user_id == admin.id and "is_admin" in update_dict and target.is_admin:
        raise HTTPException(status_code=400, detail="不能修改自己的管理员身份")

    changed = "、".join(update_dict.keys())
    rowcount = await user_crud.update_user_by_id(db, user_id, update_dict)
    if rowcount == 0:
        raise HTTPException(status_code=404, detail="用户不存在")
    await log_crud.write_log(
        db, type="admin", action="update_user", user_id=admin.id, username=admin.username,
        detail=f"修改了用户 {target.username} 的信息（{changed}）",
    )
    return success_response(message="用户信息更新成功")


@router.delete("/users")
async def delete_users(
        body: AdminUserBatchDeleteSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """批量删除用户（连带删除其登录令牌与API密钥；不能删除自己）"""
    ids = body.ids
    if admin.id in ids:
        raise HTTPException(status_code=400, detail="不能删除自己")

    deleted = await user_crud.delete_users(db, ids)
    await log_crud.write_log(
        db, type="admin", action="delete_users", user_id=admin.id, username=admin.username,
        detail=f"批量删除了 {deleted} 个用户（ids={ids}）",
    )
    return success_response(message=f"已删除 {deleted} 个用户", data={"deleted": deleted})


@router.get("/settings")
async def get_settings(
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """读取站点设置当前值（Agent 默认模型附带当前实际生效值，阈值/金额带默认兜底）"""
    agent_configured = await config_crud.get_value(db, config_crud.AGENT_DEFAULT_MODEL_KEY) or ""
    try:
        agent_effective = await resolve_default_model(db)
    except HTTPException:
        agent_effective = ""  # 站内暂无启用模型时无生效值，设置页仍可打开
    data = {
        "chatRecordMaxTokens": await config_crud.get_chat_record_threshold(db),
        "agentDefaultModel": agent_configured,
        "agentEffectiveModel": agent_effective,
        "agentTaskCostLimit": float(await config_crud.get_agent_task_cost_limit(db)),
        "registerInitialBalance": float(await config_crud.get_initial_balance(db, config_crud.REGISTER_INITIAL_BALANCE_KEY)),
        "guestInitialBalance": float(await config_crud.get_initial_balance(db, config_crud.GUEST_INITIAL_BALANCE_KEY)),
        "registerUserGroup": await config_crud.get_register_user_group(db),
    }
    return success_response(message="获取设置成功", data=data)


@router.put("/settings")
async def update_settings(
        body: SettingsUpdateSchema,
        db: AsyncSession = Depends(get_db),
        admin=Depends(get_current_admin),
):
    """更新站点设置（部分更新语义，仅传入字段生效；先全部校验再写入，写审计日志）"""
    updates = body.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")

    # 先校验后写入：模型名必须存在且启用（空串 = 清除指定、恢复默认解析链，放行）
    model_name = updates.get("agent_default_model")
    if model_name is not None and model_name.strip():
        name = model_name.strip()
        model = await model_crud.get_by_name(db, name)
        if not model or not model.get("status"):
            raise HTTPException(status_code=400, detail=f"模型 {name} 不存在或未启用")

    detail_parts = []
    if "chat_record_max_tokens" in updates:
        await config_crud.set_value(db, config_crud.CHAT_RECORD_MAX_TOKENS_KEY, str(updates["chat_record_max_tokens"]))
        detail_parts.append(f"记录阈值={updates['chat_record_max_tokens']} token")
    if model_name is not None:
        name = model_name.strip()
        await config_crud.set_value(db, config_crud.AGENT_DEFAULT_MODEL_KEY, name)
        detail_parts.append(f"Agent默认模型={name or '(恢复默认链)'}")
    if "agent_task_cost_limit" in updates:
        await config_crud.set_value(db, config_crud.AGENT_TASK_COST_LIMIT_KEY, str(updates["agent_task_cost_limit"]))
        detail_parts.append(f"Agent任务成本上限={updates['agent_task_cost_limit']} 元")
    for field, key, label in (
        ("register_initial_balance", config_crud.REGISTER_INITIAL_BALANCE_KEY, "注册初始余额"),
        ("guest_initial_balance", config_crud.GUEST_INITIAL_BALANCE_KEY, "访客初始余额"),
    ):
        if field in updates:
            await config_crud.set_value(db, key, str(updates[field]))
            detail_parts.append(f"{label}={updates[field]}")
    if "register_user_group" in updates:
        group = updates["register_user_group"]
        if group not in ALLOWED_GROUPS:
            raise HTTPException(status_code=400, detail=f"注册分组只能是 {' / '.join(ALLOWED_GROUPS)}")
        await config_crud.set_value(db, config_crud.REGISTER_USER_GROUP_KEY, group)
        detail_parts.append(f"注册分组={group}")

    await log_crud.write_log(
        db, type="admin", action="update_settings", user_id=admin.id, username=admin.username,
        detail=f"更新站点设置：{'、'.join(detail_parts)}",
    )
    return success_response(message="设置已更新")
