// 站点维护 Agent 接口封装
//
// v0.13.0 任务解耦：对话是"提交任务（POST /chat，立即返回 JSON）+ 订阅事件流
// （GET /sessions/{id}/stream，SSE：回放缓冲 + 实时跟随 + 心跳）"——任务在服务端
// 托管执行，页面进出/刷新均不影响任务，重新进入自动续看。事件格式与工坊同款
// （OpenAI 风格增量，站内扩展挂 agenticapi_agent 字段），fetch 逐行解析不走 axios。
import request, {API_BASE} from './request'
import {useUserStore} from '@/stores/user'
import type {agentServerMessage, agentSession, agentStreamEvent} from '@/types'

/** 流式回调 */
export interface agentStreamCallbacks {
    /** 正文增量 */
    onChunk?: (text: string) => void
    /** 思维链增量 */
    onReasoning?: (text: string) => void
    /** 维护 Agent 站内扩展事件（工具/审批/回放/轮次…） */
    onAgentEvent?: (ev: agentStreamEvent) => void
    /** 最后合成的 token 用量 */
    onUsage?: (usage: { promptTokens: number; completionTokens: number }) => void
    onDone?: () => void
    onError?: (message: string) => void
}

/** 提交维护任务：服务端后台执行，立即返回（同会话已有任务在跑时后端 409） */
export function startAgentChat(sessionId: number, content: string) {
    return request.post<{ sessionId: number }>('/maintain-agent/chat', {sessionId, content})
}

/** 停止执行中的任务 */
export function stopAgentTask(sessionId: number) {
    return request.post<{ stopped: boolean }>(`/maintain-agent/sessions/${sessionId}/stop`)
}

/**
 * 订阅会话任务事件流：GET /maintain-agent/sessions/{id}/stream。
 * 服务端先回放任务缓冲（replay_start.baseMessages 供前端裁剪已加载的历史）再实时跟随，
 * 空闲期发 ": ping" 心跳注释行（解析时跳过）。页面离开时 abort 即可，不影响服务端任务。
 */
export async function streamAgentEvents(
    sessionId: number,
    callbacks: agentStreamCallbacks,
    signal?: AbortSignal,
): Promise<void> {
    const userStore = useUserStore()

    let resp: Response
    try {
        resp = await fetch(`${API_BASE}/maintain-agent/sessions/${sessionId}/stream`, {
            method: 'GET',
            headers: userStore.token ? {Authorization: `Bearer ${userStore.token}`} : {},
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
        callbacks.onError?.(`订阅失败（${resp.status}）`)
        return
    }

    const reader = resp.body!.getReader()
    const decoder = new TextDecoder()
    let buf = ''

    const handleLine = (line: string) => {
        if (!line.startsWith('data:')) return  // 跳过心跳注释行与空行
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
        // 维护 Agent 扩展事件（工具/审批/回放/轮次/暂停）
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

/** 导出会话全量记录（服务端拼 Markdown：正文/工具调用/结果/审批轨迹），返回文件名与内容供前端触发下载 */
export function exportAgentSession(sessionId: number) {
    return request.get<{ filename: string; content: string }>(`/maintain-agent/sessions/${sessionId}/export`)
}

export function updateAgentSession(sessionId: number, patch: Partial<{
    title: string
    modelName: string
    approvalMode: string
}>) {
    return request.patch<{ updatedFields: string[] }>(`/maintain-agent/sessions/${sessionId}`, patch)
}

export function deleteAgentSession(sessionId: number) {
    return request.delete<{ removedMessages: number }>(`/maintain-agent/sessions/${sessionId}`)
}

/** 一键清空当前用户全部会话（联动删除消息，单事务） */
export function clearAgentSessions() {
    return request.delete<{ removedSessions: number; removedMessages: number }>('/maintain-agent/sessions')
}

/** 审批决议（confirm_required 卡片的批准/拒绝按钮） */
export function resolveApproval(approvalId: string, approved: boolean) {
    return request.post<{ approvalId: string; result: string }>('/maintain-agent/approve', {
        approvalId,
        approved,
    })
}
