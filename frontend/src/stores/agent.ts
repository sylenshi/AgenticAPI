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
    startAgentChat,
    stopAgentTask,
    streamAgentEvents,
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
            let output: string | undefined
            try {
                const parsed = JSON.parse(row.content || '{}')
                summary = parsed?._summary || parsed?.message || '已执行'
                // 沙箱命令回放：保留 stdout 尾段，刷新后仍可展开查看输出
                if (typeof parsed?.stdout === 'string' && parsed.stdout) {
                    const stderr = typeof parsed?.stderr === 'string' && parsed.stderr
                        ? `\n[stderr]\n${parsed.stderr}` : ''
                    const text = `${parsed.stdout}${stderr}`
                    output = text.length > 4096 ? `[…前面已截断…]\n${text.slice(-4096)}` : text
                }
            } catch {
                summary = '已执行'
            }
            const toolName = findToolNameFor(rows, row.id)
            const target = out[out.length - 1]
            if (target && target.role === 'assistant') {
                target.toolEvents = target.toolEvents || []
                target.toolEvents.push({
                    id: `srv-tool-${row.id}`, tool: toolName, status: 'done',
                    summary: summary.slice(0, 200), output,
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
    /** 当前上下文占用（最近一轮 prompt_tokens，round_end 更新；切会话时从历史最后一条 assistant 消息恢复） */
    const contextTokens = ref<number | null>(null)
    /** 护栏叫停原因（task_paused 事件置位；"继续任务"按钮入口，发送后清空） */
    const pausedReason = ref<'round_limit' | 'cost_limit' | null>(null)
    let abortController: AbortController | null = null
    /** 当前订阅事件流的会话（跟随任务；切换会话只断订阅，服务端任务继续跑） */
    let subscribedSessionId: number | null = null

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
        // 离开旧会话只断开事件订阅，服务端任务继续跑（v0.13.0 任务解耦）
        if (abortController) {
            abortController.abort()
            abortController = null
        }
        subscribedSessionId = null
        isStreaming.value = false
        currentSessionId.value = sessionId
        messages.value = []
        contextTokens.value = null
        pausedReason.value = null
        try {
            const res = await listAgentMessages(sessionId)
            if (currentSessionId.value !== sessionId) return  // 等待期间已切走：过期响应直接丢弃
            messages.value = mapHistory(res.data.list)
            // 恢复上下文水位：最后一条带 prompt_tokens 的 assistant 消息 ≈ 当前上下文占用
            for (let i = res.data.list.length - 1; i >= 0; i--) {
                const row = res.data.list[i]
                if (row && row.role === 'assistant' && row.promptTokens > 0) {
                    contextTokens.value = row.promptTokens
                    break
                }
            }
            // 该会话有任务在服务端执行：订阅事件流，回放+跟随续看进度
            const session = sessions.value.find(s => s.sessionId === sessionId)
            if (session?.running) await followTask(sessionId)
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
            contextTokens.value = null
            Message.success(`已清空 ${res.data.removedSessions} 个会话（${res.data.removedMessages} 条消息）`)
        } catch (err) {
            Message.error(getErrorMessage(err, '会话清空失败'))
        }
    }

    async function patchSession(patch: Partial<{ title: string; modelName: string; approvalMode: string }>) {
        if (!currentSession.value) return
        try {
            await updateAgentSession(currentSession.value.sessionId, patch)
            Object.assign(currentSession.value, patch)
        } catch (err) {
            Message.error(getErrorMessage(err, '会话设置更新失败'))
            await loadSessions() // 失败时回读服务端真值
        }
    }

    /** ═══════════ 提交任务与事件流跟随（v0.13.0 任务解耦）═══════════ */

    async function send(content: string): Promise<boolean> {
        if (!currentSession.value || isStreaming.value || !content.trim()) return false
        const sessionId = currentSession.value.sessionId
        const sessionTitle = currentSession.value.title
        pausedReason.value = null  // 新任务开始，撤下"继续任务"入口

        messages.value.push({
            id: genStudioId(), role: 'user', content: content.trim(),
            createTime: Date.now(),
        })

        // 提交后台任务（服务端托管执行，页面随时可以离开）
        try {
            await startAgentChat(sessionId, content.trim())
        } catch (err) {
            Message.error(getErrorMessage(err, '任务启动失败'))
            messages.value.pop()  // 回滚乐观插入的用户气泡
            return false
        }
        // 任务已在服务端启动：本地置 running（会话列表标记 + 切走再切回可自动续订）
        const session = sessions.value.find(s => s.sessionId === sessionId)
        if (session) session.running = true
        // 提交在途期间用户可能已切换会话：只在仍在原会话时才跟随渲染，防事件流挂错会话
        if (currentSessionId.value === sessionId) await followTask(sessionId)

        // 首次对话后自动起标题（复用工坊标题接口；同样防在途切换写错会话）
        if (sessionTitle === '新会话' && currentSessionId.value === sessionId) {
            try {
                const res = await studioTitle(content.trim())
                const title = res.data?.title
                if (title && title !== '新对话') await patchSession({title})
            } catch {
                // 标题失败不打扰
            }
        }
        return true
    }

    /**
     * 订阅会话任务事件流并渲染：服务端先回放任务缓冲（replay_start.baseMessages 供
     * 裁剪已从 DB 加载的任务期消息，避免重复渲染），再实时跟随到任务结束。
     * 切换会话/离开页面只 abort 订阅，不影响服务端任务；重新进入经 selectSession 续看。
     */
    async function followTask(sessionId: number) {
        if (subscribedSessionId === sessionId && isStreaming.value) return  // 已在跟随
        if (abortController) {  // 切换订阅目标：断开旧流
            abortController.abort()
            abortController = null
        }
        subscribedSessionId = sessionId
        isStreaming.value = true
        const controller = new AbortController()
        abortController = controller
        // 订阅期间有效：被停止或切换了会话即失效
        const alive = () => isStreaming.value && subscribedSessionId === sessionId

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

        /** 文本/思维链落笔前的分段：当前气泡已承载过工具时新开一段 */
        function ensureTextBubble(): studioMessage {
            if (current.toolEvents?.length) current = openBubble()
            return current
        }

        /** 工具事件落笔前的分段：当前气泡已有正文/思维链/审批卡时新开一段
         *（同轮并行工具共用一个气泡；审批卡各自独占气泡，防连续审批时前卡被覆盖） */
        function ensureToolBubble(): studioMessage {
            if (current.content || current.reasoning || current.confirm) current = openBubble()
            return current
        }

        function handleAgentEvent(ev: agentStreamEvent) {
            if (!alive()) return
            switch (ev.type) {
                case 'replay_start': {
                    // baseLastId = 任务启动前最后一行消息 id：srv- 气泡仅保留 id ≤ baseLastId
                    //（UI 气泡数 ≤ 服务端行数，行数口径会截不掉任务期气泡导致重复渲染；
                    // 本地乐观插入的非 srv 气泡保留），任务期已落库的消息随后由回放重放。
                    // -1 仍表示保留全部已加载历史（无任务跟随）
                    if (ev.baseMessages >= 0) {
                        const lastId = ev.baseLastId ?? Number.MAX_SAFE_INTEGER
                        messages.value = messages.value.filter(m =>
                            !m.id.startsWith('srv-') || Number(m.id.slice(4)) <= lastId)
                    }
                    break
                }
                case 'task_inactive': {
                    break  // 无任务可跟随：流即将 [DONE] 收尾，无需处理
                }
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
                case 'sandbox_output': {
                    // 沙箱命令实时输出：追加到同名 running 工具事件（超长保尾部，与服务端累计口径一致）
                    const events = current.toolEvents || []
                    for (let i = events.length - 1; i >= 0; i--) {
                        const item = events[i]
                        if (item && item.tool === ev.tool && item.status === 'running') {
                            const merged = (item.output || '') + ev.chunk
                            item.output = merged.length > 65536
                                ? `[…前面已截断…]\n${merged.slice(-65536)}`
                                : merged
                            break
                        }
                    }
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
                    const bubble = ensureToolBubble()
                    bubble.confirm = {
                        approvalId: ev.approvalId, tool: ev.tool, args: ev.args,
                        impact: ev.impact, riskLevel: ev.riskLevel,
                        status: 'pending', expiresIn: ev.expiresIn,
                        // 绝对到期时间：刷新回放后倒计时仍按真实剩余时间倒数
                        expiresAt: Date.now() + ev.expiresIn * 1000,
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
                case 'round_end': {
                    if (!current.usage) {
                        current.usage = {
                            promptTokens: ev.usageSoFar.promptTokens,
                            completionTokens: ev.usageSoFar.completionTokens,
                            elapsedMs: Date.now() - current.createTime,
                        }
                    }
                    // 上下文水位：最近一轮 prompt_tokens ≈ 当前上下文占用（usageSoFar 是累计消耗口径）
                    if (ev.contextTokens && ev.contextTokens > 0) contextTokens.value = ev.contextTokens
                    break
                }
                case 'task_paused': {
                    // 护栏（轮数/成本）叫停：Agent 已输出收尾小结，流结束后展示"继续任务"按钮
                    pausedReason.value = ev.reason
                    break
                }
            }
        }

        let endedCleanly = false
        try {
            await streamAgentEvents(sessionId, {
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
                onDone: () => {
                    endedCleanly = true  // [DONE] 干净收尾 = 服务端任务已结束
                },
            }, controller.signal)
        } finally {
            // 仅当本订阅仍是当前订阅时才清理状态（切换会话后旧流的收尾不得覆盖新订阅）
            if (abortController === controller) {
                // 清理本轮完全空的气泡（如出错前未收到任何内容；有任一有效载荷的都保留）
                messages.value = messages.value.filter(m =>
                    m.role !== 'assistant' || m.content || m.reasoning || m.toolEvents?.length ||
                    m.confirm || m.error || m.usage)
                isStreaming.value = false
                abortController = null
                subscribedSessionId = null
                // 任务干净收尾才解除占用标记：断网/异常时保留 running（任务仍在服务端执行，
                // 重新进入会话经 selectSession 自动续订），页面 busy 状态与真实占用一致
                if (endedCleanly) {
                    const session = sessions.value.find(s => s.sessionId === sessionId)
                    if (session) session.running = false
                }
            }
        }
    }

    /** 停止：取消服务端任务 + 断开订阅（任务取消后悬挂 tool_calls 由后端下次加载时修复） */
    async function stop() {
        const sessionId = currentSessionId.value
        abortController?.abort()
        abortController = null
        isStreaming.value = false
        subscribedSessionId = null
        if (sessionId != null) {
            const session = sessions.value.find(s => s.sessionId === sessionId)
            if (session) session.running = false
            try {
                await stopAgentTask(sessionId)
            } catch {
                // 任务可能已自然结束，忽略
            }
        }
    }

    /** 断开事件订阅但不停止服务端任务（页面卸载时调用；重进经 selectSession 自动续订） */
    function disconnect() {
        abortController?.abort()
        abortController = null
        isStreaming.value = false
        subscribedSessionId = null
    }

    /** ═══════════ 审批 ═══════════ */

    async function approve(approvalId: string, approved: boolean): Promise<boolean> {
        try {
            await resolveApproval(approvalId, approved)
            // 终态由 confirm_resolved 事件回填；这里先把按钮置为不可点
            for (const m of messages.value) {
                if (m.confirm?.approvalId === approvalId) {
                    m.confirm.status = approved ? 'approved' : 'rejected'
                }
            }
            return true
        } catch (err) {
            Message.error(getErrorMessage(err, '审批提交失败'))
            return false  // 失败不吞信号：页面据此跳过"已批准"成功提示
        }
    }

    return {
        sessions, currentSessionId, messages, isStreaming, contextTokens, pausedReason,
        currentSession, currentModel,
        loadSessions, createSession, selectSession, removeSession, clearSessions, patchSession,
        send, stop, disconnect, approve,
    }
})
