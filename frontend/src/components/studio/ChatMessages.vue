<!-- 工坊中间对话窗口：消息渲染（markdown / 思维链 / 图片 / 用量）+ 自动吸底 -->
<template>
    <div class="chat-messages-wrap">
        <!-- 滚动区 -->
        <div ref="scrollRef" class="chat-scroll" @scroll="handleScroll">
            <div class="messages-inner">
                <div v-for="(msg, index) in messages" :key="msg.id" class="message-row" :class="msg.role">
                    <!-- 用户消息：右侧气泡 -->
                    <div v-if="msg.role === 'user'" class="bubble user-bubble">
                        <div v-if="msg.images?.length" class="bubble-images">
                            <!-- a-image 自带点击放大预览 -->
                            <a-image v-for="img in msg.images" :key="img.id" :src="img.dataUrl"
                                     :alt="img.fileName" width="96" height="96" class="bubble-image"
                                     footer-position="outer"/>
                        </div>
                        <div v-if="msg.content" class="bubble-text">{{ msg.content }}</div>
                    </div>

                    <!-- 助手消息：左侧 markdown 渲染 -->
                    <div v-else class="bubble assistant-bubble">
                        <!-- 维护 Agent：工具执行状态条（running/进度/终态摘要） -->
                        <ToolStatusBar v-if="msg.toolEvents?.length" :events="msg.toolEvents"/>

                        <!-- 维护 Agent：审批卡片（L1/L2 写操作人审，工坊消息恒无此字段） -->
                        <ApprovalCard v-if="msg.confirm" :confirm="msg.confirm"
                                      @resolve="(approved: boolean) => handleApprove(msg, approved)"/>

                        <!-- 维护 Agent：导出文件下载卡片 -->
                        <DownloadCard v-for="dl in msg.downloads" :key="dl.url" :download="dl"/>

                        <!-- 联网搜索状态条：搜索中显示关键词，完成后显示累计次数 -->
                        <div v-if="msg.searches?.length" class="search-status" :class="{searching: searchingQuery(msg) !== null}">
                            <span v-if="searchingQuery(msg) !== null" class="search-spinner"></span>
                            <icon-search v-else class="search-icon"/>
                            <span v-if="searchingQuery(msg) !== null" class="search-text">
                                正在联网搜索：{{ searchingQuery(msg) }}…
                            </span>
                            <span v-else class="search-text">已联网搜索 {{ msg.searches.length }} 次</span>
                        </div>

                        <!-- 思维链（可折叠，默认展开） -->
                        <div v-if="msg.reasoning" class="reasoning-block">
                            <div class="reasoning-header" @click="toggleReasoning(msg.id)">
                                <icon-right class="reasoning-arrow" :class="{collapsed: collapsedReasoning.has(msg.id)}"/>
                                <span> 🧠 思考中 ...</span>
                            </div>
                            <pre v-show="!collapsedReasoning.has(msg.id)" class="reasoning-text">{{ msg.reasoning }}</pre>
                        </div>

                        <!-- 正文：空且流式中显示光标占位 -->
                        <div v-if="msg.content" class="markdown-body" v-html="renderMarkdown(msg.content)"></div>
                        <span v-else-if="isStreaming && index === messages.length - 1" class="stream-cursor"></span>

                        <!-- 错误提示 -->
                        <div v-if="msg.error" class="message-error">⚠ {{ msg.error }}</div>

                        <!-- 用量与操作 -->
                        <div v-if="msg.content || msg.error" class="message-footer">
                            <span v-if="msg.usage" class="message-usage">
                                输入tokens：{{ msg.usage.promptTokens }}  || 输出tokens：{{ msg.usage.completionTokens }} tokens
                                 || 耗时 {{ (msg.usage.elapsedMs / 1000).toFixed(1) }}s
                            </span>
                            <span v-else></span>
                            <span class="message-actions">
                                <a-button type="text" size="mini" title="复制" @click="handleCopy(msg.content)">
                                    <template #icon><icon-copy/></template>
                                </a-button>
                                <a-button v-if="msg.content && index === messages.length - 1 && !isStreaming"
                                          type="text" size="mini" title="重新生成" @click="emit('regenerate')">
                                    <template #icon><icon-refresh/></template>
                                </a-button>
                            </span>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 回到底部悬浮按钮（在滚动区外，覆盖在下方） -->
        <transition name="fade">
            <button v-if="showScrollBtn" class="scroll-bottom-btn" title="回到底部"
                    @click="scrollToBottom(true)">
                <icon-down/>
            </button>
        </transition>
    </div>
</template>

<script setup lang="ts">
import {nextTick, ref, reactive, watch, computed} from 'vue'
import {Message} from '@arco-design/web-vue'
import MarkdownIt from 'markdown-it'
import type {studioMessage} from '@/types'
import ToolStatusBar from '@/components/agent/ToolStatusBar.vue'
import ApprovalCard from '@/components/agent/ApprovalCard.vue'
import DownloadCard from '@/components/agent/DownloadCard.vue'

const props = defineProps<{
    messages: studioMessage[]
    isStreaming: boolean
}>()

const emit = defineEmits<{
    regenerate: []
    /** 维护 Agent 审批卡片按钮（工坊不会触发：其消息没有 confirm 字段） */
    approveTool: [payload: { approvalId: string; approved: boolean }]
}>()

// markdown 渲染器（默认 html:false 会转义原文标签，防 XSS）
const md = new MarkdownIt({breaks: true})
function renderMarkdown(text: string): string {
    try {
        return md.render(text)
    } catch {
        return ''
    }
}

/** ═══════════ 思维链折叠（默认展开，手动收起后保持收起） ═══════════ */
const collapsedReasoning = reactive(new Set<string>())
function toggleReasoning(id: string) {
    if (collapsedReasoning.has(id)) {
        collapsedReasoning.delete(id)
    } else {
        collapsedReasoning.add(id)
    }
}

/** ═══════════ 联网搜索状态 ═══════════ */
/** 返回正在搜索的关键词；不在搜索中返回 null（用于状态条切换展示形态） */
function searchingQuery(msg: studioMessage): string | null {
    const running = msg.searches?.find(s => s.status === 'running')
    return running ? running.query : null
}

/** ═══════════ 维护 Agent 审批转发（向上冒泡给页面调审批端点） ═══════════ */
function handleApprove(msg: studioMessage, approved: boolean) {
    if (msg.confirm) {
        emit('approveTool', {approvalId: msg.confirm.approvalId, approved})
    }
}

/** ═══════════ 复制 ═══════════ */
async function handleCopy(text: string) {
    try {
        await navigator.clipboard.writeText(text)
        Message.success('已复制')
    } catch {
        Message.error('复制失败')
    }
}

/** ═══════════ 自动吸底：流式输出时贴底滚动，用户上滚则停止跟随 ═══════════ */
const scrollRef = ref<HTMLElement>()
const stickToBottom = ref(true)
const showScrollBtn = ref(false)

// 新消息 / 流式增量到达时，若仍贴底则继续跟随滚动
const lastMessage = computed(() => props.messages[props.messages.length - 1])
watch(
    () => [props.messages.length, lastMessage.value?.content, lastMessage.value?.reasoning],
    () => {
        if (stickToBottom.value) nextTick(() => scrollToBottom(false))
    },
)

// 切换会话时重置为贴底
watch(() => props.messages, () => {
    stickToBottom.value = true
    nextTick(() => scrollToBottom(false))
})

function scrollToBottom(smooth: boolean) {
    const el = scrollRef.value
    if (!el) return
    el.scrollTo({top: el.scrollHeight, behavior: smooth ? 'smooth' : 'auto'})
}

function handleScroll() {
    const el = scrollRef.value
    if (!el) return
    const distance = el.scrollHeight - el.scrollTop - el.clientHeight
    stickToBottom.value = distance < 80
    showScrollBtn.value = distance > 200
}
</script>

<style scoped>
.chat-messages-wrap {
    position: relative;
    height: 100%;
    display: flex;
    flex-direction: column;
    min-height: 0;
}

.chat-scroll {
    flex: 1;
    overflow-y: auto;
    padding: var(--space-4) 0;
}

.messages-inner {
    max-width: 780px;
    margin: 0 auto;
    padding: 0 var(--space-5);
}

.message-row {
    display: flex;
    margin-bottom: var(--space-5);
}

.message-row.user {
    justify-content: flex-end;
}

.message-row.assistant {
    justify-content: flex-start;
}

.bubble {
    border-radius: var(--radius-lg);
    padding: 10px 14px;
    max-width: 85%;
    font-size: var(--text-sm);
    line-height: 1.7;
    word-break: break-word;
}

.user-bubble {
    background: var(--color-primary-lighter);
    border-bottom-right-radius: var(--radius-sm);
    white-space: pre-wrap;
}

.bubble-images {
    display: flex;
    flex-wrap: wrap;
    gap: var(--space-2);
    margin-bottom: var(--space-2);
}

.bubble-image {
    border-radius: var(--radius-md);
    object-fit: cover;
}

.assistant-bubble {
    background: var(--color-gray-100);
    border-top-left-radius: var(--radius-sm);
    width: 100%;
}

/* 联网搜索状态条：搜索中带旋转指示，完成后显示累计次数 */
.search-status {
    display: flex;
    align-items: center;
    gap: 6px;
    margin-bottom: var(--space-3);
    padding: 5px 10px;
    border: 1px solid var(--color-primary-light);
    border-radius: var(--radius-md);
    background: var(--color-primary-lighter);
    color: var(--color-primary);
    font-size: var(--text-xs);
    line-height: 1.6;
}

.search-text {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.search-icon {
    font-size: 13px;
    flex-shrink: 0;
}

.search-spinner {
    flex-shrink: 0;
    width: 12px;
    height: 12px;
    border: 2px solid var(--color-primary-light);
    border-top-color: var(--color-primary);
    border-radius: 50%;
    animation: search-spin 0.8s linear infinite;
}

@keyframes search-spin {
    to { transform: rotate(360deg); }
}

/* 思维链折叠块 */
.reasoning-block {
    margin-bottom: var(--space-3);
    border: 1px solid rgba(255, 125, 0, 0.25);
    border-radius: var(--radius-md);
    background: var(--color-warning-light);
    overflow: hidden;
}

.reasoning-header {
    display: flex;
    align-items: center;
    gap: var(--space-1);
    padding: 6px 10px;
    font-size: var(--text-xs);
    color: var(--color-accent-dark);
    cursor: pointer;
    user-select: none;
}

.reasoning-arrow {
    font-size: 12px;
    transition: transform var(--transition-fast);
}

.reasoning-arrow.collapsed {
    transform: rotate(0deg);
}

.reasoning-arrow:not(.collapsed) {
    transform: rotate(90deg);
}

.reasoning-text {
    margin: 0;
    padding: 8px 12px 10px;
    font-family: inherit;
    font-size: var(--text-xs);
    line-height: 1.8;
    color: var(--color-text-secondary);
    white-space: pre-wrap;
    word-break: break-word;
    max-height: 220px;
    overflow-y: auto;
    border-top: 1px solid rgba(255, 125, 0, 0.2);
}

/* ═══════════ markdown 正文：完整排版规范 ═══════════
   AI 输出的 markdown 里什么都可能有（大标题、嵌套列表、表格、代码块），
   全部收进统一的 13px 基调，任何块级元素都不吃浏览器默认样式。 */
.markdown-body {
    font-size: 13px;
    line-height: 1.8;
    color: var(--color-text);
}

/* 段落：段间距 10px，首尾不吃外边距（否则气泡上下会显得空一半） */
.markdown-body :deep(p) {
    margin: 0 0 10px;
}

.markdown-body :deep(:first-child) {
    margin-top: 0;
}

.markdown-body :deep(:last-child) {
    margin-bottom: 0;
}

/* 标题：不做层级跳跃，全部压在 14-17px 内 */
.markdown-body :deep(h1),
.markdown-body :deep(h2),
.markdown-body :deep(h3),
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) {
    margin: 14px 0 8px;
    font-weight: var(--font-semibold);
    line-height: 1.5;
    color: var(--color-text);
}

.markdown-body :deep(h1) { font-size: 17px; }
.markdown-body :deep(h2) { font-size: 16px; }
.markdown-body :deep(h3) { font-size: 15px; }
.markdown-body :deep(h4),
.markdown-body :deep(h5),
.markdown-body :deep(h6) { font-size: 14px; }

/* 列表：统一缩进与行距，去掉浏览器默认的 1em 上下边距 */
.markdown-body :deep(ul),
.markdown-body :deep(ol) {
    margin: 0 0 10px;
    padding-left: 1.5em;
}

.markdown-body :deep(li) {
    margin: 3px 0;
}

.markdown-body :deep(li > ul),
.markdown-body :deep(li > ol) {
    margin: 3px 0;
}

/* 行内代码 / 代码块 */
.markdown-body :deep(code) {
    font-family: var(--font-mono);
}

.markdown-body :deep(:not(pre) > code) {
    padding: 1px 5px;
    background: var(--color-gray-200);
    border-radius: var(--radius-sm);
    font-size: 12px;
    color: var(--color-text);
}

.markdown-body :deep(pre) {
    margin: 10px 0;
    padding: 10px 14px;
    background: var(--color-gray-800);
    color: var(--color-gray-100);
    border-radius: var(--radius-md);
    overflow-x: auto;
    font-size: 12px;
    line-height: 1.75;
}

.markdown-body :deep(pre code) {
    background: transparent;
    padding: 0;
}

/* 表格：块级化以便横向滚动；表头浅灰，行距收紧 */
.markdown-body :deep(table) {
    display: block;
    width: max-content;
    max-width: 100%;
    overflow-x: auto;
    border-collapse: collapse;
    margin: 10px 0;
}

.markdown-body :deep(th),
.markdown-body :deep(td) {
    border: 1px solid var(--color-border);
    padding: 5px 12px;
    font-size: 12.5px;
    line-height: 1.7;
    font-variant-numeric: tabular-nums;
}

.markdown-body :deep(th) {
    background: var(--color-gray-50);
    font-weight: var(--font-medium);
    color: var(--color-text-secondary);
}

/* 引用块 / 分割线 / 链接 / 图片 */
.markdown-body :deep(blockquote) {
    margin: 10px 0;
    padding: 6px 14px;
    border-left: 3px solid var(--color-gray-300);
    border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
    background: var(--color-gray-50);
    color: var(--color-text-secondary);
}

.markdown-body :deep(blockquote > p) {
    margin: 4px 0;
}

.markdown-body :deep(hr) {
    margin: 14px 0;
    border: none;
    border-top: 1px solid var(--color-border);
}

.markdown-body :deep(a) {
    color: var(--color-primary);
    text-underline-offset: 2px;
}

.markdown-body :deep(strong) {
    font-weight: var(--font-semibold);
}

.markdown-body :deep(img) {
    max-width: 100%;
    border-radius: var(--radius-md);
}

/* 流式光标 */
.stream-cursor {
    display: inline-block;
    width: 7px;
    height: 15px;
    vertical-align: text-bottom;
    background: var(--color-text-secondary);
    animation: cursor-blink 1s infinite;
}

@keyframes cursor-blink {
    50% { opacity: 0; }
}

.message-error {
    margin-top: var(--space-2);
    padding: 6px 10px;
    border-radius: var(--radius-md);
    background: var(--color-error-light);
    color: var(--color-error);
    font-size: var(--text-xs);
    line-height: 1.7;
}

/* 消息底部：用量 + 操作，与正文用细分割线隔开 */
.message-footer {
    display: flex;
    justify-content: space-between;
    align-items: center;
    margin-top: var(--space-3);
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-gray-200);
}

.message-usage {
    font-family: var(--font-mono);
    font-size: 11px;
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
}

.message-actions {
    opacity: 0;
    transition: opacity 0.15s;
}

.assistant-bubble:hover .message-actions {
    opacity: 1;
}

/* 回到底部按钮（覆盖在滚动区下边缘中间） */
.scroll-bottom-btn {
    position: absolute;
    bottom: 12px;
    left: 50%;
    transform: translateX(-50%);
    width: 36px;
    height: 36px;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    border-radius: 50%;
    border: 1px solid var(--color-border);
    background: var(--color-white);
    box-shadow: var(--shadow-md);
    cursor: pointer;
    font-size: 14px;
    color: var(--color-text-secondary);
    z-index: 5;
}

.scroll-bottom-btn:hover {
    color: var(--color-primary);
    border-color: var(--color-primary);
}

.fade-enter-active,
.fade-leave-active {
    transition: opacity 0.2s;
}

.fade-enter-from,
.fade-leave-to {
    opacity: 0;
}
</style>
