"""对外中转接口（OpenAI 兼容）

这是给外部调用方（OpenAI SDK / curl / 第三方应用）用的入口，
用 API 密钥（sk-xxx）鉴权，与站内 Bearer 登录令牌是两套凭证。
"""

import json
import traceback

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud import api_key as api_key_crud
from app.models.api_key import ApiKeyTable
from app.models.user import UserTabel
from app.router.deps import get_db
from app.services import relay_service
from app.services.relay_service import RelayError

router = APIRouter(prefix="/v1", tags=["Relay"])


async def _authenticate_api_key(db: AsyncSession, request: Request) -> tuple[ApiKeyTable, UserTabel]:
    """
    API 密钥鉴权（/v1 各端点共用）：解析 Authorization 头 → 校验密钥 → 校验账号状态。

    :return: (密钥对象, 用户对象)，校验失败时抛 RelayError（路由层转为 OpenAI 格式响应）
    """
    # 兼容不带 Bearer 前缀的写法
    auth = request.headers.get("authorization", "")
    if auth.lower().startswith("bearer "):
        api_key = auth[7:].strip()
    else:
        api_key = auth.strip()

    if not api_key:
        raise RelayError(401, "未提供 API 密钥", "invalid_request_error")

    row = await api_key_crud.get_valid_key_with_user(db, api_key)
    if not row:
        raise RelayError(401, "无效的 API 密钥", "invalid_request_error")
    key_obj, user = row

    if not user.status:
        raise RelayError(403, "账号已被封禁", "access_denied")
    return key_obj, user


@router.get("/models")
async def list_models(request: Request, db: AsyncSession = Depends(get_db)):
    """
    OpenAI Models 兼容接口：返回当前密钥用户可调用的模型列表

    - 鉴权：与 /v1/chat/completions 相同（Authorization: Bearer sk-xxx）
    - 列表口径：模型启用 + 用户分组有权限（free 用户仅 free 模型，vip 全部）+
      至少绑定一个启用渠道，保证列出的模型都可实际调用
    """
    try:
        _, user = await _authenticate_api_key(db, request)
    except RelayError as exc:
        return exc.to_response()
    try:
        return await relay_service.list_models_for_user(db, user)
    except RelayError as exc:
        return exc.to_response()
    except Exception:
        print(f"[relay] /v1/models 未预期异常: {traceback.format_exc()}")
        return RelayError(500, "服务器内部错误", "api_error").to_response()


@router.post("/chat/completions")
async def chat_completions(request: Request, db: AsyncSession = Depends(get_db)):
    """
    OpenAI Chat Completions 兼容中转接口

    - 鉴权：Authorization: Bearer sk-xxx（API 密钥，在控制台-秘钥页面创建）
    - 报文：成功时透传上游 JSON / SSE，失败时返回 OpenAI 格式 {"error": {...}}
    """
    # ── API 密钥鉴权 ──
    try:
        key_obj, user = await _authenticate_api_key(db, request)
    except RelayError as exc:
        return exc.to_response()

    # ── 解析请求体（原样透传，不做格式转换） ──
    try:
        payload = json.loads(await request.body())
    except Exception:
        return RelayError(400, "请求体不是合法的 JSON", "invalid_request_error").to_response()
    if not isinstance(payload, dict):
        return RelayError(400, "请求体必须是 JSON 对象", "invalid_request_error").to_response()

    # ── 中转主流程（模型/分组/余额校验 → 渠道轮询转发 → 计费日志） ──
    try:
        return await relay_service.chat_completions(db, payload, user, key_obj.id)
    except RelayError as exc:
        return exc.to_response()
    except Exception:
        # 未预期异常也保持 OpenAI 报文契约，细节只进服务端日志
        print(f"[relay] /v1/chat/completions 未预期异常: {traceback.format_exc()}")
        return RelayError(500, "服务器内部错误", "api_error").to_response()
