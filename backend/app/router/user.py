"""用户相关接口"""

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.status import HTTP_401_UNAUTHORIZED

from app.router.deps import get_db
from app.schemas.user import (
    UserLoginSchema, UserInfoSchema, UserAuthSchema, UserProfileUpdateSchema,
)
from app.crud.user import (
    create_user,
    create_guest_user,
    clean_expired_guests,
    get_user_by_username,
    get_user_by_id,
    update_user_by_id,
    generate_user_token,
    authenticate_user,
    delete_user_token,
    touch_last_login,
)
from app.crud import log as log_crud
from app.utils.auth import get_current_user, bearer_scheme
from app.utils.response import success_response

router = APIRouter(prefix="/user", tags=["User"])


@router.post("/register")
async def register(user_data: UserLoginSchema, request: Request, db: AsyncSession = Depends(get_db)):
    """
    用户注册逻辑：验证用户名和密码是否符合要求，注册用户并返回访问令牌
    （注册成功即视为登录，前端无需再调一次登录接口）
    """
    # 先验证用户是否存在
    existing_user = await get_user_by_username(db, user_data.username)
    # 如果用户已经存在，返回错误信息
    if existing_user:
        raise HTTPException(status_code=400, detail="用户名已存在")
    # 如果用户不存在，创建用户
    user = await create_user(db, user_data)
    # 生成用户令牌
    token = await generate_user_token(db, user.id)
    await touch_last_login(db, user.id)
    await log_crud.write_log(
        db, type="login", action="register", user_id=user.id, username=user.username,
        detail=f"新用户注册（ip={request.client.host if request.client else 'unknown'}）",
    )
    # 返回成功响应
    response_data = UserAuthSchema(token=token, userInfo=UserInfoSchema.model_validate(user))
    return success_response(message="注册成功", data=response_data)


@router.post("/login")
async def login(user_data: UserLoginSchema, request: Request, db: AsyncSession = Depends(get_db)):
    """
    用户登录逻辑：验证用户名和密码是否匹配，返回访问令牌
    """
    # 验证用户是否存在
    user = await authenticate_user(db, user_data)
    if not user:
        raise HTTPException(status_code=HTTP_401_UNAUTHORIZED, detail="用户名或密码错误")
    # 被封禁的账号禁止登录
    if not user.status:
        raise HTTPException(status_code=403, detail="账号已被封禁，请联系管理员")
    # 如果用户存在，生成用户令牌
    token = await generate_user_token(db, user.id)
    await touch_last_login(db, user.id)
    await log_crud.write_log(
        db, type="login", action="login", user_id=user.id, username=user.username,
        detail=f"用户登录（ip={request.client.host if request.client else 'unknown'}）",
    )
    # 返回成功响应
    response_data = UserAuthSchema(token=token, userInfo=UserInfoSchema.model_validate(user))
    return success_response(message="登录成功", data=response_data)


@router.post("/guest")
async def guest_login(db: AsyncSession = Depends(get_db)):
    """
    访客模式：创建临时访客账号并签发短有效期令牌（24小时）

    - 访客无需用户名密码，账号由后端自动生成（is_guest=True），24小时后令牌过期
    - 访客可浏览公开内容，但管理类接口会返回403
    - 顺带清理已过期的访客账号（惰性清理，见 crud/user.py 的说明）
    """
    cleaned = await clean_expired_guests(db)
    if cleaned:
        print(f"[guest] 已清理 {cleaned} 个过期访客账号")
    user = await create_guest_user(db)
    token = await generate_user_token(db, user.id, expires_days=1)
    await touch_last_login(db, user.id)
    await log_crud.write_log(
        db, type="login", action="guest", user_id=user.id, username=user.username,
        detail="创建临时访客账号",
    )
    response_data = UserAuthSchema(token=token, userInfo=UserInfoSchema.model_validate(user))
    return success_response(message="访客模式开启成功", data=response_data)


@router.get("/info")
async def get_user_info(user=Depends(get_current_user)):
    """
    获取当前登录用户信息（需携带 Authorization: Bearer <token>）

    【注意】get_current_user 返回的是 UserTabel ORM 对象，不是 Schema，
    返回给前端前要用 UserInfoSchema.model_validate() 转换并过滤字段（比如不会带出密码）
    """
    return success_response(message="获取用户信息成功", data=UserInfoSchema.model_validate(user))


@router.put("/profile")
async def update_profile(body: UserProfileUpdateSchema, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    """
    修改自己的资料（昵称/手机号，控制台-概览页使用）
    """
    update_dict = body.model_dump(exclude_unset=True)
    if not update_dict:
        raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")
    # 空字符串视为清空该字段
    for field in ("nickname", "phone"):
        if field in update_dict:
            update_dict[field] = (update_dict[field] or "").strip() or None

    await update_user_by_id(db, user.id, update_dict)
    await log_crud.write_log(
        db, type="user", action="update_profile", user_id=user.id, username=user.username,
        detail=f"修改了自己的资料（{'、'.join(update_dict.keys())}）",
    )
    refreshed = await get_user_by_id(db, user.id)
    return success_response(message="资料更新成功", data=UserInfoSchema.model_validate(refreshed))


@router.delete("/logout")
async def logout(
        user=Depends(get_current_user),
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
        db: AsyncSession = Depends(get_db),
):
    """
    登出逻辑：删除服务端的令牌记录，令牌立即失效
    （同时校验令牌有效性，避免拿任意字符串刷接口）
    """
    await log_crud.write_log(
        db, type="login", action="logout", user_id=user.id, username=user.username,
        detail="用户登出",
    )
    await delete_user_token(db, credentials.credentials)
    return success_response(message="登出成功")
