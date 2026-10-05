// 站点维护 Agent 接口封装
//
// 对话接口与工坊同款：SSE 流式 + OpenAI 风格报文（站内扩展事件挂 agenticapi_agent
// 字段），不走 axios 封装，用 fetch 逐行解析；会话/审批等管理接口是普通统一格式。
import request, {API_BASE} from './request'
import {useUserStore} from '@/stores/user'
import type {agentServerMessage, agentSession, agentStreamEvent} from '@/types'

/** 流式回调 */
export interface agentStreamCallbacks {
    /** 正文增量 */
    onChunk?: (text: string) => void
    /** 思维链增量 */
    onReasoning?: (text: string) => void
    /** 维护 Agent 站内扩展事件（工具/审批/模型切换/下载…） */
    onAgentEvent?: (ev: agentStreamEvent) => void
    /** 最后合成的 token 用量 */
    onUsage?: (usage: { promptTokens: number; completionTokens: number }) => void
    onDone?: () => void
    onError?: (message: string) => void
}

/**
 * 维护 Agent 流式对话：POST /maintain-agent/chat，解析 SSE 增量并回调。
 * 解析模式复刻工坊 streamStudioChat（跨 chunk 行缓冲 + agenticapi_* 扩展分发）。
 */
export async function streamAgentChat(
    sessionId: number,
    content: string,
    callbacks: agentStreamCallbacks,
    signal?: AbortSignal,
): Promise<void> {
    const userStore = useUserStore()

    let resp: Response
    try {
        resp = await fetch(`${API_BASE}/maintain-agent/chat`, {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                ...(userStore.token ? {Authorization: `Bearer ${userStore.token}`} : {}),
            },
            body: JSON.stringify({sessionId, content}),
            signal,
        })
    } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
            callbacks.onDone?.()
            return
        }
        callbacks.onError?.('网络错误，请稍后重试')
        return
    }

    const contentType = resp.headers.get('content-type') || ''
    if (!resp.ok || !contentType.includes('text/event-stream')) {
        if (resp.status === 401) {
            userStore.handleUnauthorized()
            callbacks.onError?.('请先登录')
            return
        }
        let message = `请求失败（${resp.status}）`
        try {
            const data = await resp.json()
            message = data?.error?.message || message
        } catch {
            // 非 JSON 响应体保留默认提示
        }
        callbacks.onError?.(message)
        return
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    const handleLine = (line: string) => {
        if (!line.startsWith('data:')) return
        const data = line.slice(5).trim()
        if (!data || data === '[DONE]') return
        let obj: any
        try {
            obj = JSON.parse(data)
        } catch {
            return
        }
        if (!obj || typeof obj !== 'object') return
        // 流内错误事件
        if (obj.error?.message) {
            callbacks.onError?.(obj.error.message)
            return
        }
        // 维护 Agent 扩展事件（工具/审批/模型切换/轮次/下载）
        if (obj.agenticapi_agent) {
            const ev = obj.agenticapi_agent
            if (ev && typeof ev === 'object' && typeof ev.type === 'string') {
                callbacks.onAgentEvent?.(ev as agentStreamEvent)
            }
            return
        }
        // usage 与正文增量可能同块出现，独立处理
        if (obj.usage?.prompt_tokens != null) {
            callbacks.onUsage?.({
                promptTokens: obj.usage.prompt_tokens,
                completionTokens: obj.usage.completion_tokens ?? 0,
            })
        }
        const delta = obj.choices?.[0]?.delta
        if (delta) {
            if (typeof delta.content === 'string' && delta.content) {
                callbacks.onChunk?.(delta.content)
            }
            const reasoning = delta.reasoning_content ?? delta.thinking ?? delta.reasoning
            if (typeof reasoning === 'string' && reasoning) {
                callbacks.onReasoning?.(reasoning)
            }
        }
    }

    try {
        for (; ;) {
            const {done, value} = await reader.read()
            if (done) break
            buf += decoder.decode(value, {stream: true})
            const lines = buf.split('\n')
            buf = lines.pop() || ''
            lines.forEach(handleLine)
        }
        if (buf) handleLine(buf)
        callbacks.onDone?.()
    } catch (err) {
        if (err instanceof Error && err.name === 'AbortError') {
            callbacks.onDone?.()
            return
        }
        callbacks.onError?.('连接中断，请重试')
    }
}

/** 会话管理（统一响应格式，axios 拦截器已解包 data） */

export function createAgentSession(title?: string) {
    return request.post<agentSession>('/maintain-agent/sessions', {title})
}

export function listAgentSessions() {
    return request.get<{ list: agentSession[] }>('/maintain-agent/sessions')
}

export function listAgentMessages(sessionId: number) {
    return request.get<{ list: agentServerMessage[] }>(`/maintain-agent/sessions/${sessionId}/messages`)
}

export function updateAgentSession(sessionId: number, patch: Partial<{
    title: string
    modelName: string
    autoApproveL1: boolean
    enableL2: boolean
}>) {
    return request.patch<{ updatedFields: string[] }>(`/maintain-agent/sessions/${sessionId}`, patch)
}

export function deleteAgentSession(sessionId: number) {
    return request.delete<{ removedMessages: number }>(`/maintain-agent/sessions/${sessionId}`)
}

/** 审批决议（confirm_required 卡片的批准/拒绝按钮） */
export function resolveApproval(approvalId: string, approved: boolean) {
    return request.post<{ approvalId: string; result: string }>('/maintain-agent/approve', {
        approvalId,
        approved,
    })
}
