# 根据Token获取用户信息
from fastapi import Depends, HTTPException, Request
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.crud.user import get_user_by_token


# 状态码语义约定（前端拦截器按此分流）：
# - 401 未认证：没带令牌/令牌无效或过期 → 前端清空登录态并唤起登录弹窗
# - 403 无权限：已登录但身份不够（如访客调用管理接口）→ 前端按普通业务错误提示
#
# HTTPBearer 默认对"未携带令牌"抛403，这里改成401，保持上面的语义干净
class BearerAuth(HTTPBearer):
    """Bearer令牌解析器：请求头缺失或不是"Bearer xxx"格式时，统一返回401"""

    # 参数必须保留 request: Request 类型注解，FastAPI 靠它识别"这是请求对象"而不是查询参数
    async def __call__(self, request: Request) -> HTTPAuthorizationCredentials | None:
        try:
            return await super().__call__(request)
        except HTTPException as exc:
            if exc.status_code == 403:
                raise HTTPException(status_code=401, detail="未提供有效的访问令牌")
            raise


bearer_scheme = BearerAuth()


async def get_current_user(
        db: AsyncSession = Depends(get_db),
        credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
):
    """
    根据访问令牌查询用户信息（访客、正式账号权限相同）

    【用法】接口想要求登录，就在参数里加一行 user=Depends(get_current_user)，
    框架会在进入接口逻辑前自动完成令牌校验，校验失败直接返回401
    """
    user = await get_user_by_token(db, credentials.credentials)
    if not user:
        raise HTTPException(status_code=401, detail="无效或已过期的访问令牌")
    return user


async def get_current_admin(admin=Depends(get_current_user)):
    """
    仅限管理员的依赖：渠道/模型管理、用户管理等管理类接口使用

    已登录但不是管理员（含访客、普通用户）→ 403 无权限
    """
    if not admin.is_admin:
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return admin
