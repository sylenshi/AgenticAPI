"""API 路由聚合"""

from fastapi import APIRouter

from app.router import channels, models, operations, user, keys, admin, redeem, relay, monitor, studio, site, maintain_agent

router = APIRouter()
router.include_router(site.router)  # 站点公开配置（对外中转地址等，前端展示用）
router.include_router(models.router)  # 和模型列表相关接口
router.include_router(channels.router)  # 和渠道列表相关接口
router.include_router(operations.router)  # 和上游渠道运维相关接口
router.include_router(user.router)  # 和用户登录注册相关接口
router.include_router(keys.router)  # 用户API密钥管理接口
router.include_router(redeem.redeem_router)  # 兑换码兑换与记录（用户端）
router.include_router(redeem.admin_router)  # 兑换码生成/管理/监控（管理端）
router.include_router(admin.router)  # 管理员用户管理接口
router.include_router(monitor.router)  # 监控面板接口（对话数据/调用日志/数据看板）
router.include_router(relay.router)  # 对外中转接口（OpenAI兼容）
router.include_router(studio.router)  # 模型工坊接口（对话式 Playground，流式 + 语音识别）
router.include_router(maintain_agent.router)  # 站点维护 Agent（对话式运维，SSE + 审批 + 会话管理）
