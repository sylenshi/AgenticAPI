"""站点维护 Agent 接口（全部需管理员权限）

- POST /maintain-agent/chat：SSE 流式对话（OpenAI 风格报文，复刻工坊 /studio/chat 模式，
  站内扩展事件挂 agenticapi_agent 字段）——不走统一 {code,message,data} 格式；
- POST /maintain-agent/approve：审批决议（confirm_required 卡片的批准/拒绝）；
- GET/POST/PATCH/DELETE /maintain-agent/sessions*：会话管理（统一响应格式）；
- GET /maintain-agent/exports/{token}：导出文件下载（一次性 token + 24h 过期）。
"""

import time

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import agent_setting
from app.crud import agent as agent_crud
from app.crud import log as log_crud
from app.crud import model as model_crud
from app.crud import system_config as config_crud
from app.router.deps import get_db
from app.schemas.agent import AgentApproveSchema, AgentChatSchema, AgentSessionCreateSchema, AgentSessionUpdateSchema
from app.services import export_service
from app.services.agent import maintain_loop
from app.services.agent.approvals import approval_manager
from app.services.relay_service import RelayError
from app.utils.auth import get_current_admin
from app.utils.response import success_response

router = APIRouter(prefix="/maintain-agent", tags=["MaintainAgent"])

# 默认大脑模型解析链的配置键与内置兜底（链：system_config → .env → 站内首个启用模型）
AGENT_DEFAULT_MODEL_KEY = "agent_default_model"


async def _resolve_default_model(db: AsyncSession) -> str:
    """解析会话默认驱动模型：system_config.agent_default_model → .env AGENT_MAINTENANCE_MODEL → 首个启用模型"""
    configured = await config_crud.get_value(db, AGENT_DEFAULT_MODEL_KEY)
    for candidate in (configured, agent_setting.AGENT_MAINTENANCE_MODEL):
        if candidate and candidate.strip():
            model = await model_crud.get_by_name(db, candidate.strip())
            if model and model.get("status"):
                return candidate.strip()
    models = [m for m in await model_crud.get_all(db) if m.get("status")]
    if not models:
        raise HTTPException(status_code=503, detail="站内没有启用中的模型，无法创建维护Agent会话")
    return models[0]["name"]


async def _get_own_session(db: AsyncSession, session_id: int, admin) -> "object":
    """取属于当前管理员的会话，不存在/越权统一 404（不泄露存在性）"""
    session = await agent_crud.get_session(db, session_id)
    if not session or session.user_id != admin.id:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.post("/sessions")
async def create_session(body: AgentSessionCreateSchema, db: AsyncSession = Depends(get_db),
                         admin=Depends(get_current_admin)):
    """新建会话（先执行惰性清理：超 50 个或超 30 天的旧会话联动删除）"""
    await agent_crud.gc_sessions(db, admin.id, username=admin.username)
    model_name = await _resolve_default_model(db)
    session = await agent_crud.create_session(
        db, user_id=admin.id, model_name=model_name, title=body.title or "新会话")
    return success_response(message="会话创建成功", data={
        "sessionId": session.id, "title": session.title, "modelName": session.model_name,
        "autoApproveL1": bool(session.auto_approve_l1), "enableL2": bool(session.enable_l2),
        "createTime": str(session.create_time),
    })


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """会话列表（最近优先）"""
    sessions = await agent_crud.list_sessions(db, admin.id)
    return success_response(message="ok", data={"list": [
        {"sessionId": s["id"], "title": s["title"], "modelName": s["model_name"],
         "autoApproveL1": bool(s["auto_approve_l1"]), "enableL2": bool(s["enable_l2"]),
         "status": s["status"], "updateTime": str(s["update_time"])}
        for s in sessions
    ]})


@router.get("/sessions/{session_id}/messages")
async def list_messages(session_id: int, db: AsyncSession = Depends(get_db),
                        admin=Depends(get_current_admin)):
    """会话消息（含工具与审批轨迹，历史回放用）"""
    await _get_own_session(db, session_id, admin)
    rows = await agent_crud.list_messages(db, session_id)
    return success_response(message="ok", data={"list": [
        {"id": r["id"], "role": r["role"], "content": r["content"],
         "toolCalls": r["tool_calls"], "toolCallId": r["tool_call_id"],
         "riskLevel": r["risk_level"], "approvalStatus": r["approval_status"],
         "promptTokens": r["prompt_tokens"], "completionTokens": r["completion_tokens"],
         "createTime": str(r["create_time"])}
        for r in rows
    ]})


@router.patch("/sessions/{session_id}")
async def update_session(session_id: int, body: AgentSessionUpdateSchema,
                         db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """更新会话设置：标题 / 驱动模型 / L1 自动批准 / L2 开关"""
    await _get_own_session(db, session_id, admin)
    update: dict = {}
    if body.title is not None:
        update["title"] = body.title.strip() or "新会话"
    if body.model_name is not None:
        model = await model_crud.get_by_name(db, body.model_name.strip())
        if not model or not model.get("status"):
            raise HTTPException(status_code=404, detail=f"模型 {body.model_name} 不存在或已停用")
        update["model_name"] = body.model_name.strip()
    if body.auto_approve_l1 is not None:
        update["auto_approve_l1"] = 1 if body.auto_approve_l1 else 0
    if body.enable_l2 is not None:
        update["enable_l2"] = 1 if body.enable_l2 else 0
    if update:
        await agent_crud.update_session(db, session_id, update)
    return success_response(message="会话已更新", data={"updatedFields": list(update.keys())})


@router.delete("/sessions/{session_id}")
async def delete_session(session_id: int, db: AsyncSession = Depends(get_db),
                         admin=Depends(get_current_admin)):
    """删除会话（联动删除消息）"""
    await _get_own_session(db, session_id, admin)
    removed_messages = await agent_crud.delete_session(db, session_id)
    await log_crud.write_log(
        db, type="admin", action="agent_session_delete", user_id=admin.id, username=admin.username,
        detail=f"删除维护Agent会话 {session_id}（联动删除消息 {removed_messages} 条）")
    return success_response(message="会话已删除", data={"removedMessages": removed_messages})


@router.post("/chat")
async def agent_chat(body: AgentChatSchema, db: AsyncSession = Depends(get_db),
                     admin=Depends(get_current_admin)):
    """维护 Agent 对话（SSE 流式）。报文 OpenAI 风格（同工坊），错误返回 {"error": {...}}"""
    session = await _get_own_session(db, body.session_id, admin)
    try:
        return await maintain_loop.run_chat(db, session, admin, body.content.strip())
    except RelayError as exc:
        maintain_loop.release_session(session.id)
        return exc.to_response()


@router.post("/approve")
async def approve(body: AgentApproveSchema, db: AsyncSession = Depends(get_db),
                  admin=Depends(get_current_admin)):
    """审批决议：approve 端点校验审批归属当前管理员（防伪）"""
    result = approval_manager.resolve(body.approval_id, user_id=admin.id, approved=body.approved)
    if result is None:
        raise HTTPException(status_code=404, detail="审批不存在、已处理或不属于当前管理员")
    await log_crud.write_log(
        db, type="admin", action="agent_approval", user_id=admin.id, username=admin.username,
        detail=f"审批 {body.approval_id} 决议：{result}")
    return success_response(message="ok", data={"approvalId": body.approval_id, "result": result})


@router.get("/exports/{token}")
async def download_export(token: str, db: AsyncSession = Depends(get_db),
                          admin=Depends(get_current_admin)):
    """导出文件下载（一次性 token，消费即失效；文件本体 24h 过期惰性清理）"""
    path = export_service.consume_export(token)
    if not path:
        raise HTTPException(status_code=404, detail="下载链接无效、已使用或已过期（24h）")
    await log_crud.write_log(
        db, type="admin", action="agent_export_download", user_id=admin.id, username=admin.username,
        detail=f"下载导出文件 {path.name}")
    return FileResponse(path, filename=f"agenticapi-export-{time.strftime('%Y%m%d-%H%M%S')}.zip",
                        media_type="application/zip")
