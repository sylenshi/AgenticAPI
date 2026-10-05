"""审批管理器：L1/L2 工具的人审阀门

机制：执行器在执行危险工具前创建 PendingApproval（asyncio.Event 挂起当前协程），
前端收到 SSE confirm_required 事件渲染审批卡片，管理员点批准/拒绝调用
POST /maintain-agent/approve → resolve() 置位 Event，执行器恢复继续/中止。

- 超时 300s 自动拒绝（rejected_by_timeout），结果以 isError 回传模型；
- 审批归属校验：approve 端点必须校验 approval 属于当前管理员的会话；
- 进程重启后内存登记表丢失：未决审批永久挂起的协程随连接断开消亡，
  agent_message 里的 pending 状态在下次加载会话时统一改判 timeout。
"""

import asyncio
import secrets
import time

APPROVAL_TIMEOUT_SECONDS = 300


class PendingApproval:
    """一次待审批的工具调用"""

    def __init__(self, *, session_id: int, user_id: int, tool: str, args: dict,
                 risk: str, impact: str):
        self.id = f"apr_{secrets.token_hex(8)}"
        self.session_id = session_id
        self.user_id = user_id
        self.tool = tool
        self.args = args
        self.risk = risk
        self.impact = impact
        self.event = asyncio.Event()
        self.result: str | None = None  # approved / rejected / timeout
        self.created_at = time.time()

    @property
    def expires_in(self) -> int:
        return max(0, int(APPROVAL_TIMEOUT_SECONDS - (time.time() - self.created_at)))

    def to_event_payload(self) -> dict:
        """SSE confirm_required 事件载荷"""
        return {
            "approvalId": self.id,
            "tool": self.tool,
            "args": self.args,
            "impact": self.impact,
            "riskLevel": self.risk,
            "expiresIn": self.expires_in,
        }


class ApprovalManager:
    """进程内审批登记表（单例使用）"""

    def __init__(self):
        self._pending: dict[str, PendingApproval] = {}

    def create(self, **kwargs) -> PendingApproval:
        pending = PendingApproval(**kwargs)
        self._pending[pending.id] = pending
        return pending

    async def wait(self, pending: PendingApproval) -> str:
        """挂起等待管理员决议，返回 approved / rejected / timeout"""
        try:
            await asyncio.wait_for(pending.event.wait(), timeout=APPROVAL_TIMEOUT_SECONDS)
        except asyncio.TimeoutError:
            pending.result = "timeout"
        self._pending.pop(pending.id, None)
        return pending.result or "timeout"

    def resolve(self, approval_id: str, *, user_id: int, approved: bool) -> str | None:
        """
        处理审批决议，返回结果状态；无权/不存在返回 None。

        :param user_id: 当前操作的管理员 id，必须与审批归属一致（防伪）
        """
        pending = self._pending.get(approval_id)
        if not pending or pending.user_id != user_id:
            return None
        pending.result = "approved" if approved else "rejected"
        pending.event.set()
        return pending.result

    def fail_all_in_session(self, session_id: int) -> None:
        """会话流中断（客户端断开）时，把该会话所有未决审批置为拒绝，避免协程悬挂"""
        for pending in list(self._pending.values()):
            if pending.session_id == session_id:
                pending.result = "rejected"
                pending.event.set()
                self._pending.pop(pending.id, None)


approval_manager = ApprovalManager()
