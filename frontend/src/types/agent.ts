// 站点维护 Agent 相关类型（会话与消息服务端持久化，与工坊的 localStorage 模式不同）

/** 后端 agenticapi_agent 扩展事件（SSE 站内扩展字段的联合类型） */
export type agentStreamEvent =
    | { type: 'tool_start'; tool: string; digest?: string }
    | { type: 'tool_progress'; tool: string; done: number; total: number }
    | { type: 'tool_end'; tool: string; ok: boolean; summary?: string }
    | { type: 'confirm_required'; approvalId: string; tool: string; args: Record<string, unknown>; impact: string; riskLevel: string; expiresIn: number }
    | { type: 'confirm_resolved'; approvalId: string; result: 'approved' | 'rejected' | 'timeout' }
    | { type: 'model_switched'; from: string; to: string }
    | { type: 'round_end'; round: number; usageSoFar: { promptTokens: number; completionTokens: number } }
    | { type: 'download_ready'; url: string; label: string; size: string; expiresAt: string }

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
}

/** 审批卡片状态（confirm_required 到 confirm_resolved 的生命周期） */
export interface agentConfirmState {
    approvalId: string
    tool: string
    args: Record<string, unknown>
    impact: string
    riskLevel: string
    status: 'pending' | 'approved' | 'rejected' | 'timeout'
    /** 倒计时秒数（展示用） */
    expiresIn?: number
}

/** 导出文件下载卡片 */
export interface agentDownload {
    url: string
    label: string
    size: string
    expiresAt: string
}

/** 服务端会话 */
export interface agentSession {
    sessionId: number
    title: string
    modelName: string
    autoApproveL1: boolean
    enableL2: boolean
    status?: string
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
