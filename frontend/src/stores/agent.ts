// 维护 Agent 会话与消息状态（服务端持久化为唯一事实源，前端只做展示态缓存）
import {defineStore} from 'pinia'
import {computed, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import {
    clearAgentSessions,
    createAgentSession,
    deleteAgentSession,
    listAgentMessages,
    listAgentSessions,
    resolveApproval,
    streamAgentChat,
    updateAgentSession,
} from '@/api/agent'
import {studioTitle} from '@/api/studio'
import {getErrorMessage} from '@/api/request'
import type {agentSession, agentStreamEvent, studioMessage} from '@/types'
import {genStudioId} from '@/stores/studio'

/** 服务端历史 → UI 消息（按时序逐轮还原：文本轮与工具轮各成一个气泡，保持先后顺序） */
function mapHistory(rows: {
    id: number
    role: string
    content: string | null
    toolCalls: { id: string; function: { name: string } }[] | null
    riskLevel: string | null
    approvalStatus: string | null
    createTime: string
}[]): studioMessage[] {
    const out: studioMessage[] = []
    for (const row of rows) {
        if (row.role === 'user') {
            out.push({
                id: `srv-${row.id}`, role: 'user', content: row.content || '',
                createTime: new Date(row.createTime).getTime(),
            })
        } else if (row.role === 'assistant') {
            // 每条 assistant 轮一个气泡：有正文的是文本轮；空正文的是工具调用轮，承接后续 tool 行
            out.push({
                id: `srv-${row.id}`, role: 'assistant', content: row.content || '',
                createTime: new Date(row.createTime).getTime(),
            })
        } else if (row.role === 'tool') {
            // 历史回放只有终态：挂到最近一个 assistant 气泡（即本轮工具轮）
            let summary = ''
            try {
                const parsed = JSON.parse(row.content || '{}')
                summary = parsed?._summary || parsed?.message || '已执行'
            } catch {
                summary = '已执行'
            }
            const toolName = findToolNameFor(rows, row.id)
            const target = out[out.length - 1]
            if (target && target.role === 'assistant') {
                target.toolEvents = target.toolEvents || []
                target.toolEvents.push({
                    id: `srv-tool-${row.id}`, tool: toolName, status: 'done',
                    summary: summary.slice(0, 200),
                })
            }
        }
    }
    // 过滤掉空且无工具事件的中间 assistant 轮，避免历史里出现空白气泡
    return out.filter(m => m.role !== 'assistant' || m.content || m.toolEvents?.length)
}

/** 从历史行里反查 tool 消息对应的工具名（往前找最近的 toolCalls） */
function findToolNameFor(rows: { id: number; role: string; content: string | null; toolCalls: { id: string; function: { name: string } }[] | null }[] | any[], toolMsgId: number): string {
    for (let i = rows.findIndex(r => r.id === toolMsgId); i >= 0; i--) {
        const calls = rows[i]?.toolCalls
        if (calls?.length) return calls[0].function.name || 'tool'
    }
    return 'tool'
}

export const useAgentStore = defineStore('agent', () => {
    /** 会话列表 */
    const sessions = ref<agentSession[]>([])
    const currentSessionId = ref<number | null>(null)
    /** 当前会话的 UI 消息（服务端历史的展示态 + 本轮流式增量） */
    const messages = ref<studioMessage[]>([])
    const isStreaming = ref(false)
    let abortController: AbortController | null = null

    const currentSession = computed(() =>
        sessions.value.find(s => s.sessionId === currentSessionId.value) || null)
    const currentModel = computed(() => currentSession.value?.modelName || '')

    /** ═══════════ 会话管理 ═══════════ */

    async function loadSessions() {
        try {
            const res = await listAgentSessions()
            sessions.value = res.data.list
        } catch (err) {
            Message.error(getErrorMessage(err, '会话列表加载失败'))
        }
    }

    async function createSession() {
        try {
            const res = await createAgentSession()
            sessions.value.unshift(res.data)
            await selectSession(res.data.sessionId)
            return res.data
        } catch (err) {
            Message.error(getErrorMessage(err, '新建会话失败'))
            return null
        }
    }

    async function selectSession(sessionId: number) {
        if (isStreaming.value) stop()
        currentSessionId.value = sessionId
        messages.value = []
        try {
            const res = await listAgentMessages(sessionId)
            messages.value = mapHistory(res.data.list)
        } catch (err) {
            Message.error(getErrorMessage(err, '会话消息加载失败'))
        }
    }

    async function removeSession(sessionId: number) {
        try {
            await deleteAgentSession(sessionId)
            sessions.value = sessions.value.filter(s => s.sessionId !== sessionId)
            if (currentSessionId.value === sessionId) {
                currentSessionId.value = null
                messages.value = []
                const first = sessions.value[0]
                if (first) await selectSession(first.sessionId)
            }
            Message.success('会话已删除')
        } catch (err) {
            Message.error(getErrorMessage(err, '删除会话失败'))
        }
    }

    /** 一键清空全部会话（服务端单事务删除，成功后本地整体复位） */
    async function clearSessions() {
        try {
            const res = await clearAgentSessions()
            stop()
            sessions.value = []
            currentSessionId.value = null
            messages.value = []
            Message.success(`已清空 ${res.data.removedSessions} 个会话（${res.data.removedMessages} 条消息）`)
        } catch (err) {
            Message.error(getErrorMessage(err, '会话清空失败'))
        }
    }

    async function patchSession(patch: Partial<{ title: string; modelName: string; autoApproveL1: boolean; enableL2: boolean }>) {
        if (!currentSession.value) return
        try {
            await updateAgentSession(currentSession.value.sessionId, patch)
            Object.assign(currentSession.value, patch)
        } catch (err) {
            Message.error(getErrorMessage(err, '会话设置更新失败'))
            await loadSessions() // 失败时回读服务端真值
        }
    }

    /** ═══════════ 发送与流式接收 ═══════════ */

    async function send(content: string) {
        if (!currentSession.value || isStreaming.value || !content.trim()) return
        const sessionId = currentSession.value.sessionId
        const sessionTitle = currentSession.value.title

        messages.value.push({
            id: genStudioId(), role: 'user', content: content.trim(),
            createTime: Date.now(),
        })

        // 一轮回复按「文本段 / 工具段」拆成多个 assistant 气泡，保持时序：
        // 文本与思维链写进当前气泡；工具调用开新气泡承接，工具结束后的正文再开新气泡
        function openBubble(): studioMessage {
            messages.value.push({
                id: genStudioId(), role: 'assistant', content: '',
                toolEvents: [], createTime: Date.now(),
            })
            // 必须从响应式数组读回代理再持有：直改 push 前的原始对象不触发重渲染
            const bubble = messages.value[messages.value.length - 1]
            if (!bubble) throw new Error('assistant 气泡创建失败')
            return bubble
        }

        let current = openBubble()
        isStreaming.value = true
        abortController = new AbortController()
        // 流式期间有效：被停止或切换了会话即失效
        const alive = () => isStreaming.value && currentSession.value?.sessionId === sessionId

        /** 文本/思维链落笔前的分段：当前气泡已承载过工具时新开一段 */
        function ensureTextBubble(): studioMessage {
            if (current.toolEvents?.length) current = openBubble()
            return current
        }

        /** 工具事件落笔前的分段：当前气泡已有正文/思维链时新开一段（同轮并行工具共用一个气泡） */
        function ensureToolBubble(): studioMessage {
            if (current.content || current.reasoning) current = openBubble()
            return current
        }

        function handleAgentEvent(ev: agentStreamEvent) {
            if (!alive()) return
            switch (ev.type) {
                case 'tool_start': {
                    const bubble = ensureToolBubble()
                    bubble.toolEvents = bubble.toolEvents || []
                    bubble.toolEvents.push({
                        id: genStudioId(), tool: ev.tool, status: 'running', digest: ev.digest,
                    })
                    break
                }
                case 'tool_progress': {
                    const events = current.toolEvents || []
                    const last = events[events.length - 1]
                    if (last && last.tool === ev.tool) last.progress = {done: ev.done, total: ev.total}
                    break
                }
                case 'tool_end': {
                    const events = current.toolEvents || []
                    for (let i = events.length - 1; i >= 0; i--) {
                        const item = events[i]
                        if (item && item.tool === ev.tool && item.status === 'running') {
                            item.status = ev.ok ? 'done' : 'failed'
                            item.summary = ev.summary
                            item.progress = undefined
                            break
                        }
                    }
                    break
                }
                case 'confirm_required': {
                    current.confirm = {
                        approvalId: ev.approvalId, tool: ev.tool, args: ev.args,
                        impact: ev.impact, riskLevel: ev.riskLevel,
                        status: 'pending', expiresIn: ev.expiresIn,
                    }
                    break
                }
                case 'confirm_resolved': {
                    for (const m of messages.value) {
                        if (m.confirm?.approvalId === ev.approvalId) {
                            m.confirm.status = ev.result
                        }
                    }
                    break
                }
                case 'model_switched': {
                    const session = sessions.value.find(s => s.sessionId === currentSessionId.value)
                    if (session) session.modelName = ev.to
                    Message.info(`驱动模型已切换：${ev.from} → ${ev.to}`)
                    break
                }
                case 'round_end': {
                    if (!current.usage) {
                        current.usage = {
                            promptTokens: ev.usageSoFar.promptTokens,
                            completionTokens: ev.usageSoFar.completionTokens,
                            elapsedMs: Date.now() - current.createTime,
                        }
                    }
                    break
                }
                case 'download_ready': {
                    current.downloads = current.downloads || []
                    current.downloads.push({url: ev.url, label: ev.label, size: ev.size, expiresAt: ev.expiresAt})
                    break
                }
            }
        }

        try {
            await streamAgentChat(sessionId, content.trim(), {
                onChunk: (text) => {
                    if (!alive()) return
                    const bubble = ensureTextBubble()
                    bubble.content += text
                },
                onReasoning: (text) => {
                    if (!alive()) return
                    const bubble = ensureTextBubble()
                    bubble.reasoning = (bubble.reasoning || '') + text
                },
                onUsage: (usage) => {
                    if (!alive()) return
                    current.usage = {
                        promptTokens: usage.promptTokens,
                        completionTokens: usage.completionTokens,
                        elapsedMs: Date.now() - current.createTime,
                    }
                },
                onAgentEvent: handleAgentEvent,
                onError: (msg) => {
                    if (alive()) current.error = msg
                },
            }, abortController.signal)
        } finally {
            // 清理本轮完全空的气泡（如出错前未收到任何内容；有任一有效载荷的都保留）
            messages.value = messages.value.filter(m =>
                m.role !== 'assistant' || m.content || m.reasoning || m.toolEvents?.length ||
                m.confirm || m.downloads?.length || m.error || m.usage)
            isStreaming.value = false
            abortController = null
            // 首次对话后自动起标题（复用工坊标题接口）
            if (sessionTitle === '新会话' && currentSession.value) {
                try {
                    const res = await studioTitle(content.trim())
                    const title = res.data?.title
                    if (title && title !== '新对话') await patchSession({title})
                } catch {
                    // 标题失败不打扰
                }
            }
        }
    }

    function stop() {
        abortController?.abort()
        abortController = null
        isStreaming.value = false
    }

    /** ═══════════ 审批 ═══════════ */

    async function approve(approvalId: string, approved: boolean) {
        try {
            await resolveApproval(approvalId, approved)
            // 终态由 confirm_resolved 事件回填；这里先把按钮置为不可点
            for (const m of messages.value) {
                if (m.confirm?.approvalId === approvalId) {
                    m.confirm.status = approved ? 'approved' : 'rejected'
                }
            }
        } catch (err) {
            Message.error(getErrorMessage(err, '审批提交失败'))
        }
    }

    return {
        sessions, currentSessionId, messages, isStreaming,
        currentSession, currentModel,
        loadSessions, createSession, selectSession, removeSession, clearSessions, patchSession,
        send, stop, approve,
    }
})
