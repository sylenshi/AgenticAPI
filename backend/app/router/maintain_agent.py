"""站点维护 Agent 接口（全部需管理员权限）

- POST /maintain-agent/chat：提交后台任务（立即返回 JSON；同会话已有任务在跑返回 409）——
  任务生命周期与服务端托管，与 HTTP 请求解耦（v0.13.0）；
- GET /maintain-agent/sessions/{id}/stream：SSE 订阅任务事件（回放缓冲 + 实时跟随 + 心跳）；
- POST /maintain-agent/sessions/{id}/stop：取消执行中的任务；
- POST /maintain-agent/approve：审批决议（confirm_required 卡片的批准/拒绝）；
- GET/POST/PATCH/DELETE /maintain-agent/sessions*：会话管理（统一响应格式）。
（v0.11.0：导出下载端点随数据治理工具下线而删除）
"""

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import agent_setting
from app.crud import agent as agent_crud
from app.crud import log as log_crud
from app.crud import model as model_crud
from app.crud import system_config as config_crud
from app.router.deps import get_db
from app.schemas.agent import AgentApproveSchema, AgentChatSchema, AgentSessionCreateSchema, AgentSessionUpdateSchema
from app.services.agent import maintain_loop
from app.services.agent.approvals import approval_manager
from app.services.relay_service import RelayError
from app.utils.auth import get_current_admin
from app.utils.response import success_response

router = APIRouter(prefix="/maintain-agent", tags=["MaintainAgent"])

# 默认大脑模型解析链（system_config.agent_default_model → .env AGENT_MAINTENANCE_MODEL → 站内首个启用模型）
# 配置键 AGENT_DEFAULT_MODEL_KEY 统一登记在 config_crud（设置页 GET/PUT /admin/settings 共用）


async def _resolve_default_model(db: AsyncSession) -> str:
    """解析会话默认驱动模型：system_config.agent_default_model → .env AGENT_MAINTENANCE_MODEL → 首个启用模型"""
    configured = await config_crud.get_value(db, config_crud.AGENT_DEFAULT_MODEL_KEY)
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
        "approvalMode": agent_crud.resolve_approval_mode(session),
        "createTime": str(session.create_time),
    })


@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """会话列表（最近优先；running 标记供前端识别有任务在跑、需要订阅事件流）"""
    sessions = await agent_crud.list_sessions(db, admin.id)
    return success_response(message="ok", data={"list": [
        {"sessionId": s["id"], "title": s["title"], "modelName": s["model_name"],
         "approvalMode": agent_crud.resolve_approval_mode(s),
         "status": s["status"], "running": maintain_loop.is_running(s["id"]),
         "updateTime": str(s["update_time"])}
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
    """更新会话设置：标题 / 驱动模型 / 审批档位"""
    await _get_own_session(db, session_id, admin)
    update: dict = {}
    if body.title is not None:
        update["title"] = body.title.strip() or "新会话"
    if body.model_name is not None:
        model = await model_crud.get_by_name(db, body.model_name.strip())
        if not model or not model.get("status"):
            raise HTTPException(status_code=404, detail=f"模型 {body.model_name} 不存在或已停用")
        update["model_name"] = body.model_name.strip()
    if body.approval_mode is not None:
        if body.approval_mode not in agent_crud.APPROVAL_MODES:
            raise HTTPException(status_code=400, detail=f"无效的审批档位：{body.approval_mode}")
        update["approval_mode"] = body.approval_mode
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


@router.delete("/sessions")
async def clear_sessions(db: AsyncSession = Depends(get_db), admin=Depends(get_current_admin)):
    """一键清空当前管理员的全部会话（联动删除消息，单事务，写审计日志）"""
    ses_count, msg_count = await agent_crud.delete_all_sessions(db, admin.id, username=admin.username)
    return success_response(message="会话已清空",
                            data={"removedSessions": ses_count, "removedMessages": msg_count})


@router.post("/chat")
async def agent_chat(body: AgentChatSchema, db: AsyncSession = Depends(get_db),
                     admin=Depends(get_current_admin)):
    """提交维护任务：服务端托管后台执行，立即返回；页面经 /stream 订阅事件跟随"""
    session = await _get_own_session(db, body.session_id, admin)
    try:
        maintain_loop.start_task(session.id, admin.id, body.content.strip())
    except RelayError as exc:
        raise HTTPException(status_code=exc.status_code, detail=exc.message)
    return success_response(message="任务已开始", data={"sessionId": session.id})


@router.get("/sessions/{session_id}/stream")
async def agent_stream(session_id: int, db: AsyncSession = Depends(get_db),
                       admin=Depends(get_current_admin)):
    """订阅会话任务事件（SSE）：回放缓冲 + 实时跟随 + 15s 心跳保活；无任务时立即收尾"""
    await _get_own_session(db, session_id, admin)
    bus = maintain_loop.get_bus(session_id)
    return StreamingResponse(
        maintain_loop.stream_events(session_id, bus), media_type="text/event-stream")


@router.post("/sessions/{session_id}/stop")
async def agent_stop(session_id: int, db: AsyncSession = Depends(get_db),
                     admin=Depends(get_current_admin)):
    """停止执行中的任务（任务取消后悬挂的 tool_calls 在下次加载会话时补占位修复）"""
    await _get_own_session(db, session_id, admin)
    stopped = maintain_loop.stop_task(session_id)
    if stopped:
        await log_crud.write_log(
            db, type="admin", action="agent_task_stop", user_id=admin.id, username=admin.username,
            detail=f"手动停止维护Agent任务（会话 {session_id}）")
    return success_response(message="任务已停止" if stopped else "当前没有执行中的任务",
                            data={"stopped": stopped})


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
