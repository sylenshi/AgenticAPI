// 站点维护 Agent 相关类型（会话与消息服务端持久化，与工坊的 localStorage 模式不同）

/** 审批档位（v0.11.0 三档位，取代旧 autoApproveL1/enableL2 两开关） */
export type agentApprovalMode = 'confirm_all' | 'confirm_critical' | 'full'

/** 后端 agenticapi_agent 扩展事件（SSE 站内扩展字段的联合类型） */
export type agentStreamEvent =
    | { type: 'replay_start'; baseMessages: number; baseLastId?: number }
    | { type: 'task_inactive' }
    | { type: 'tool_start'; tool: string; digest?: string }
    | { type: 'tool_progress'; tool: string; done: number; total: number }
    | { type: 'sandbox_output'; tool: string; chunk: string }
    | { type: 'tool_end'; tool: string; ok: boolean; summary?: string }
    | { type: 'confirm_required'; approvalId: string; tool: string; args: Record<string, unknown>; impact: string; riskLevel: string; expiresIn: number }
    | { type: 'confirm_resolved'; approvalId: string; result: 'approved' | 'rejected' | 'timeout' }
    | { type: 'round_end'; round: number; usageSoFar: { promptTokens: number; completionTokens: number }; contextTokens?: number }
    | { type: 'task_paused'; reason: 'round_limit' | 'cost_limit'; round: number }

/** 消息内渲染的工具执行记录（tool_start/progress/end 聚合） */
export interface agentToolEvent {
    id: string
    tool: string
    status: 'running' | 'done' | 'failed'
    /** 参数摘要（tool_start 的 digest） */
    digest?: string
    /** 批测进度 */
    progress?: { done: number; total: number }
    /** 完成后的一句话结果摘要 */
    summary?: string
    /** 沙箱命令实时输出（sandbox_output 聚合，超长保尾部） */
    output?: string
}

/** 审批卡片状态（confirm_required 到 confirm_resolved 的生命周期） */
export interface agentConfirmState {
    approvalId: string
    tool: string
    args: Record<string, unknown>
    impact: string
    riskLevel: string
    status: 'pending' | 'approved' | 'rejected' | 'timeout'
    /** 倒计时秒数（展示用，事件创建时快照） */
    expiresIn?: number
    /** 到期绝对时间戳（Date.now() + expiresIn*1000，刷新回放后仍能准确倒数） */
    expiresAt?: number
}

/** 服务端会话 */
export interface agentSession {
    sessionId: number
    title: string
    modelName: string
    approvalMode: agentApprovalMode
    status?: string
    /** 是否有任务正在服务端执行（有则进入会话需订阅事件流续看进度） */
    running?: boolean
    updateTime?: string
}

/** 服务端消息行（GET /sessions/{id}/messages 返回） */
export interface agentServerMessage {
    id: number
    role: 'user' | 'assistant' | 'tool' | 'system'
    content: string | null
    toolCalls: { id: string; type: string; function: { name: string; arguments: string } }[] | null
    toolCallId: string | null
    riskLevel: string | null
    approvalStatus: string | null
    promptTokens: number
    completionTokens: number
    createTime: string
}
