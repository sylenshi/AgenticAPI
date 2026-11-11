<!-- 模型工坊：对话式 Playground
     布局：左侧会话侧边栏 + 中间对话窗口与输入框 + 右侧参数面板，两侧可折叠。
     ≥1201px 三栏常驻；769–1200px 参数面板默认收起；≤768px 双侧栏改抽屉、由顶部工具条唤出。
     对话走站内 /studio/chat 接口（登录、不计费），会话本地存储。 -->
<template>
    <div class="studio-page">
        <!-- 左：会话侧边栏 -->
        <div class="studio-aside left" :class="{collapsed: !sidebarOpen}">
            <SessionSidebar @close="sidebarOpen = false" />
        </div>

        <!-- 抽屉遮罩：仅窄屏双侧栏以覆盖层形式出现时生效 -->
        <div v-if="isNarrow && (sidebarOpen || panelOpen)" class="studio-mask" @click="closeDrawers"/>

        <!-- 中：对话区 -->
        <div class="studio-center">
            <!-- 会话标题条：折叠入口并入标题栏，取代原先贴在内容边缘的悬浮细条 -->
            <div class="studio-bar">
                <div class="bar-left">
                    <button class="bar-icon-btn" :title="sidebarOpen ? '收起会话列表' : '展开会话列表'"
                            @click="sidebarOpen = !sidebarOpen">
                        <icon-menu/>
                        <span class="bar-nav-label">会话</span>
                    </button>
                    <span class="bar-divider"></span>
                    <span class="bar-session" :title="studioStore.currentSession?.title">
                        {{ studioStore.currentSession?.title || '未命名会话' }}
                    </span>
                    <span class="bar-model">· {{ studioStore.selectedModelName || '未选择模型' }}</span>
                    <span class="bar-model-chip">{{ studioStore.selectedModelName || '未选择模型' }}</span>
                </div>
                <div class="bar-right">
                    <button class="bar-text-btn" :class="{active: panelOpen}"
                            @click="panelOpen = !panelOpen">
                        {{ panelOpen ? '收起参数' : '参数配置' }}
                    </button>
                </div>
            </div>

            <div class="studio-main">
                <WelcomePanel v-if="!studioStore.currentMessages.length"
                              :model-name="studioStore.selectedModelName"
                              @select="sendPrompt" @focus-panel="panelOpen = true" />
                <ChatMessages v-else :messages="studioStore.currentMessages"
                              :model-name="studioStore.selectedModelName"
                              :is-streaming="studioStore.isStreaming" @regenerate="handleRegenerate" />
            </div>

            <ChatInput :support-vision="supportVision" @send="handleSend" @stop="handleStop" />
        </div>

        <!-- 右：参数面板 -->
        <div class="studio-aside right" :class="{collapsed: !panelOpen}">
            <SettingsPanel />
        </div>
    </div>
</template>

<script setup lang="ts">
import {computed, ref, onMounted, onBeforeUnmount} from 'vue'
import {Message} from '@arco-design/web-vue'
import SessionSidebar from '@/components/studio/SessionSidebar.vue'
import SettingsPanel from '@/components/studio/SettingsPanel.vue'
import ChatMessages from '@/components/studio/ChatMessages.vue'
import ChatInput from '@/components/studio/ChatInput.vue'
import WelcomePanel from '@/components/studio/WelcomePanel.vue'
import {useStudioStore, genStudioId} from '@/stores/studio'
import {useModelListStore} from '@/stores/modelList'
import {streamStudioChat} from '@/api/studio'
import type {studioChatMessage, studioContentPart} from '@/api/studio'
import type {studioImage} from '@/types'

const studioStore = useStudioStore()
const modelListStore = useModelListStore()

const sidebarOpen = ref(true)
const panelOpen = ref(true)
const isNarrow = ref(false)

/** ═══════════ 视口自适应：窄屏把双侧栏变抽屉，中屏参数面板默认收起 ═══════════ */
let narrowQuery: MediaQueryList | null = null
let compactQuery: MediaQueryList | null = null
let viewportReady = false
let wasCompact = false

function syncViewport() {
    const narrow = narrowQuery?.matches ?? false
    const compact = compactQuery?.matches ?? false
    const crossing = narrow !== isNarrow.value || compact !== wasCompact
    // 首屏必须按视口初始化一次；此后只在断点跨越时重置，避免打断用户手动展开的状态
    const shouldReset = !viewportReady || crossing
    viewportReady = true
    isNarrow.value = narrow
    wasCompact = compact
    if (shouldReset) {
        sidebarOpen.value = !narrow
        panelOpen.value = !(narrow || compact)
    }
}

function closeDrawers() {
    sidebarOpen.value = false
    panelOpen.value = false
}

onMounted(() => {
    narrowQuery = window.matchMedia('(max-width: 768px)')
    compactQuery = window.matchMedia('(max-width: 1200px)')
    // 首屏即按视口给一次初始状态（默认 ref 为桌面展开）
    syncViewport()
    narrowQuery.addEventListener('change', syncViewport)
    compactQuery.addEventListener('change', syncViewport)
})

onBeforeUnmount(() => {
    narrowQuery?.removeEventListener('change', syncViewport)
    compactQuery?.removeEventListener('change', syncViewport)
})

// 当前所选模型是否支持图片输入（不支持时输入框禁用图片相关功能）
const supportVision = computed(() => {
    const model = modelListStore.totalModelList.find(m => m.name === studioStore.selectedModelName)
    return !!model?.supportVision
})

let abortController: AbortController | null = null

/** 组装发给后端的上下文：当前会话全部消息，带图用户消息转 OpenAI 多模态 parts（图片在前文本在后） */
function buildContextMessages(): studioChatMessage[] {
    const messages: studioChatMessage[] = []
    for (const msg of studioStore.currentMessages) {
        if (msg.role === 'user') {
            if (!msg.content.trim() && !msg.images?.length) continue
            if (msg.images?.length) {
                const parts: studioContentPart[] = msg.images.map(img => (
                    {type: 'image_url', image_url: {url: img.dataUrl}}
                ))
                if (msg.content.trim()) parts.push({type: 'text', text: msg.content})
                messages.push({role: 'user', content: parts})
            } else {
                messages.push({role: 'user', content: msg.content})
            }
        } else if (msg.content.trim()) {
            // 跳过空回复（生成中的占位、失败的空消息）
            messages.push({role: 'assistant', content: msg.content})
        }
    }
    return messages
}

/** 发起一轮生成：先插入 assistant 占位，再流式写入增量 */
async function runGeneration() {
    const session = studioStore.currentSession
    if (!session || studioStore.isStreaming) return

    // 兜底持久化：确保每次成功发起生成时，当前所选模型与参数必然落盘
    // （模型下拉的 change 事件在个别交互路径下可能漏触发，刷新后模型选择会回落）
    studioStore.persistParams()

    studioStore.addMessage({
        id: genStudioId(), role: 'assistant', content: '', reasoning: '', createTime: Date.now(),
    })
    studioStore.isStreaming = true
    const startTime = Date.now()
    abortController = new AbortController()

    try {
        await streamStudioChat(
            {
                model: studioStore.selectedModelName,
                messages: buildContextMessages(),
                temperature: studioStore.params.temperature,
                top_p: studioStore.params.topP,
                max_tokens: studioStore.params.maxTokens,
                system_prompt: studioStore.params.systemPrompt,
                enable_search: studioStore.enableSearch,
            },
            {
                onChunk: t => studioStore.appendToLastAssistant('content', t),
                onReasoning: t => studioStore.appendToLastAssistant('reasoning', t),
                onSearch: s => studioStore.updateLastAssistantSearch(s.query, s.status === 'start'),
                onUsage: u => studioStore.setLastAssistantUsage(u.promptTokens, u.completionTokens, Date.now() - startTime),
                onError: msg => studioStore.setLastAssistantError(msg),
            },
            abortController.signal,
        )
    } finally {
        studioStore.isStreaming = false
        abortController = null
        studioStore.flushSave()
    }
}

/** 发送用户消息（来自输入框 / 欢迎页建议卡片） */
function handleSend({text, images}: {text: string; images: studioImage[]}) {
    if (studioStore.isStreaming) return
    if (!studioStore.selectedModelName) {
        Message.warning('请先在参数面板选择模型')
        return
    }
    if (!studioStore.currentSession) studioStore.createSession()
    const session = studioStore.currentSession!
    session.modelName = studioStore.selectedModelName

    studioStore.addMessage({
        id: genStudioId(),
        role: 'user',
        content: text,
        images: images.length ? images : undefined,
        createTime: Date.now(),
    })
    void runGeneration()
}

/** 欢迎页建议卡片：点击直接作为消息发送 */
function sendPrompt(prompt: string) {
    handleSend({text: prompt, images: []})
}

/** 停止生成：中断请求，已生成的部分内容保留 */
function handleStop() {
    abortController?.abort()
}

/** 重新生成：移除最后一条回复后，基于同一上下文重发 */
async function handleRegenerate() {
    if (studioStore.isStreaming) return
    if (!studioStore.removeLastAssistant()) {
        Message.warning('没有可重新生成的回复')
        return
    }
    await runGeneration()
}
</script>

<style scoped>
.studio-page {
    display: flex;
    height: 100%;
    position: relative;
    background: var(--color-bg-layout);
}

.studio-aside {
    flex-shrink: 0;
    overflow: hidden;
    background: var(--color-white);
    transition: width var(--transition-base);
}

/* 桌面三栏：左侧面板与广场筛选栏共用令牌，中自适应 / 右 280，中间内容统一限宽 720 */
.studio-aside.left {
    width: var(--layout-panel-aside);
    border-right: 1px solid var(--color-border);
}

.studio-aside.right {
    width: 280px;
    border-left: 1px solid var(--color-border);
}

.studio-aside.collapsed {
    width: 0;
    border: none;
}

.studio-center {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    position: relative;
    background: var(--color-bg-layout);
}

/* 会话标题条：把折叠入口、当前模型、参数入口收进同一行，去掉悬浮补丁感 */
.studio-bar {
    flex-shrink: 0;
    height: 44px;
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    padding: 0 var(--space-5);
    background: var(--color-white);
    border-bottom: 1px solid var(--color-border);
}

.bar-left,
.bar-right {
    display: flex;
    align-items: center;
    gap: var(--space-2);
    min-width: 0;
}

.bar-icon-btn,
.bar-text-btn {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 0 6px;
    height: 28px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-secondary);
    font-family: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
    white-space: nowrap;
    transition: color var(--transition-fast), background-color var(--transition-fast);
}

.bar-icon-btn:hover,
.bar-text-btn:hover,
.bar-text-btn.active {
    color: var(--color-primary);
    background: var(--color-primary-lighter);
}

.bar-nav-label,
.bar-model-chip {
    display: none;
}

.bar-divider {
    width: 1px;
    height: 14px;
    background: var(--color-border);
    margin: 0 var(--space-1);
}

.bar-session {
    max-width: 240px;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--text-sm);
    font-weight: var(--font-medium);
    color: var(--color-text);
}

.bar-model {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.studio-main {
    flex: 1;
    min-height: 0;
}

.studio-mask {
    position: absolute;
    inset: 0;
    z-index: 20;
    background: var(--color-black);
    opacity: 0.32;
}

/* 中屏：侧栏收窄，避免中间对话列被压到 500px 以下 */
@media (max-width: 1200px) {
    .studio-aside.left { width: var(--layout-panel-aside-compact); }
    .studio-aside.right { width: 250px; }
    .bar-session { max-width: 160px; }
}

/* 窄屏：双侧栏改覆盖式抽屉，中间只留一条主内容列 */
@media (max-width: 768px) {
    .studio-aside {
        position: absolute;
        top: 0;
        bottom: 0;
        z-index: 25;
        width: min(84vw, 300px);
        box-shadow: var(--shadow-lg);
        transition: transform var(--transition-base);
    }

    .studio-aside.left { left: 0; }
    .studio-aside.right { right: 0; }

    .studio-aside.left.collapsed,
    .studio-aside.right.collapsed {
        width: min(84vw, 300px);
        border: none;
    }

    .studio-aside.left.collapsed { transform: translateX(-100%); }
    .studio-aside.right.collapsed { transform: translateX(100%); }

    .studio-bar { padding: 0 var(--space-3); }
    .bar-divider,
    .bar-session,
    .bar-model { display: none; }
    .bar-nav-label { display: inline; }
    .bar-model-chip {
        display: inline-block;
        max-width: 150px;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
        padding: 3px 8px;
        border-radius: var(--radius-sm);
        background: var(--color-primary-lighter);
        color: var(--color-primary);
        font-family: var(--font-mono);
        font-size: var(--text-xs);
    }
}
</style>
