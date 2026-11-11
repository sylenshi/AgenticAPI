<!-- 工坊左侧会话侧边栏：新建 / 搜索 / 时间分组 / 切换 / 重命名 / 导出 / 删除 / 清空
     视觉：头部与底部浅底分层、分组等宽计数、选中项主色脊线、模型系列色点；窄屏抽屉带标题栏。 -->
<template>
    <div class="session-sidebar">
        <!-- 窄屏抽屉标题栏：桌面隐藏，close 由父级用于收起抽屉 -->
        <div class="drawer-head">
            <div class="drawer-head-left">
                <span class="drawer-title">会话</span>
                <span class="drawer-count">{{ studioStore.sessions.length }}</span>
            </div>
            <button class="drawer-close" title="关闭会话列表" @click="emit('close')">
                <icon-close/>
            </button>
        </div>

        <div class="sidebar-header">
            <a-button type="primary" long :disabled="studioStore.isStreaming"
                      @click="studioStore.createSession()">
                <template #icon><icon-plus/></template>
                新对话
            </a-button>
            <a-input v-model="keyword" placeholder="搜索标题或内容" allow-clear>
                <template #prefix><icon-search/></template>
            </a-input>
            <div class="sidebar-meta">会话保存在本机</div>
        </div>

        <div class="session-list">
            <div v-if="!filteredSessions.length" class="session-empty">
                {{ keyword.trim() ? '没有匹配的会话' : '暂无会话' }}
            </div>

            <section v-for="group in sessionGroups" :key="group.key" class="session-group">
                <div class="group-head">
                    <span class="group-name">{{ group.label }}</span>
                    <span class="group-count">{{ group.items.length }}</span>
                </div>

                <div v-for="session in group.items" :key="session.id"
                     class="session-item" :class="{active: session.id === studioStore.currentSessionId}"
                     @click="studioStore.switchSession(session.id)">
                    <span class="session-spine"/>
                    <div class="session-info">
                        <div class="session-title" :title="session.title">{{ session.title }}</div>
                        <div class="session-meta">
                            <span class="model-dot" :class="modelDotClass(session.modelName)"/>
                            <span class="session-model">{{ session.modelName || '未选择模型' }}</span>
                            <span class="session-time">{{ formatTime(session.updateTime) }}</span>
                        </div>
                    </div>
                    <div class="session-actions" @click.stop>
                        <a-tooltip content="重命名" position="top">
                            <a-button type="text" size="small" @click="openRename(session)">
                                <template #icon><icon-edit/></template>
                            </a-button>
                        </a-tooltip>
                        <a-tooltip content="导出 Markdown" position="top">
                            <a-button type="text" size="small" @click="handleExport(session)">
                                <template #icon><icon-download/></template>
                            </a-button>
                        </a-tooltip>
                        <a-tooltip content="删除" position="top">
                            <a-button type="text" size="small" @click="handleDelete(session)">
                                <template #icon><icon-delete/></template>
                            </a-button>
                        </a-tooltip>
                    </div>
                </div>
            </section>
        </div>

        <div class="sidebar-footer">
            <span class="footer-count">{{ studioStore.sessions.length }} 个会话</span>
            <button class="footer-clear" :disabled="!studioStore.sessions.length"
                    @click="handleClearAll">清空全部会话</button>
        </div>

        <!-- 重命名弹窗（Arco 无 prompt 弹窗，用小 modal + input 实现） -->
        <a-modal v-model:visible="renameVisible" title="重命名" :width="380" :mask-closable="false"
                 @before-ok="confirmRename" @close="renameValue = ''">
            <a-form :model="{title: renameValue}" layout="vertical">
                <a-form-item label="会话标题" required>
                    <a-input v-model="renameValue" placeholder="输入新的会话标题" @press-enter="confirmRename"/>
                </a-form-item>
            </a-form>
        </a-modal>
    </div>
</template>

<script setup lang="ts">
import {ref, computed} from 'vue'
import {Message} from '@arco-design/web-vue'
import {useStudioStore} from '@/stores/studio'
import {confirmDialog} from '@/utils/feedback'
import type {studioSession} from '@/types'

const emit = defineEmits<{ close: [] }>()
const studioStore = useStudioStore()

// 搜索关键字：匹配会话标题或任意消息内容（不区分大小写）
const keyword = ref('')
const filteredSessions = computed(() => {
    const kw = keyword.value.trim().toLowerCase()
    if (!kw) return studioStore.sessions
    return studioStore.sessions.filter(s =>
        s.title.toLowerCase().includes(kw) ||
        s.messages.some(m => m.content.toLowerCase().includes(kw)),
    )
})

interface sessionGroup {
    key: string
    label: string
    items: studioSession[]
}

/** 按 今天 / 昨天 / 更早 分组；搜索结果不分组，避免分组标题与命中项对不上 */
const sessionGroups = computed<sessionGroup[]>(() => {
    const list = filteredSessions.value
    if (!list.length) return []
    if (keyword.value.trim()) return [{key: 'search', label: '搜索结果', items: list}]

    const today = new Date()
    today.setHours(0, 0, 0, 0)
    const todayMs = today.getTime()
    const yesterdayMs = todayMs - 86400000
    const todayItems: studioSession[] = []
    const yesterdayItems: studioSession[] = []
    const earlierItems: studioSession[] = []
    for (const session of list) {
        const t = session.updateTime
        if (t >= todayMs) todayItems.push(session)
        else if (t >= yesterdayMs) yesterdayItems.push(session)
        else earlierItems.push(session)
    }
    const groups: sessionGroup[] = [
        {key: 'today', label: '今天', items: todayItems},
        {key: 'yesterday', label: '昨天', items: yesterdayItems},
        {key: 'earlier', label: '更早', items: earlierItems},
    ]
    return groups.filter(group => group.items.length > 0)
})

function formatTime(timestamp: number): string {
    const d = new Date(timestamp)
    const pad = (n: number) => String(n).padStart(2, '0')
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (timestamp >= today.getTime()) return `${pad(d.getHours())}:${pad(d.getMinutes())}`
    if (timestamp >= today.getTime() - 86400000) return '昨天'
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** 模型系列色点：按名称稳定散列到扩展强调色，同一模型始终同色 */
const dotVariants = ['dot-violet', 'dot-cyan', 'dot-gold', 'dot-vermilion', 'dot-blue']
function modelDotClass(name?: string): string {
    if (!name) return 'dot-empty'
    let hash = 0
    for (const ch of name) hash = (hash * 31 + ch.charCodeAt(0)) >>> 0
    return dotVariants[hash % dotVariants.length] ?? 'dot-empty'
}

/** ═══════════ 重命名：小弹窗 + 校验非空 ═══════════ */
const renameVisible = ref(false)
const renameValue = ref('')
const renameTarget = ref<studioSession | null>(null)

function openRename(session: studioSession) {
    renameTarget.value = session
    renameValue.value = session.title
    renameVisible.value = true
}

// before-ok 返回 false 时弹窗不关闭
function confirmRename(): boolean {
    const value = renameValue.value.trim()
    if (!value) {
        Message.warning('标题不能为空')
        return false
    }
    if (renameTarget.value) studioStore.renameSession(renameTarget.value.id, value)
    renameValue.value = ''
    return true
}

async function handleDelete(session: studioSession) {
    const confirmed = await confirmDialog(`确定删除会话「${session.title}」吗？`, '删除会话', '删除', true)
    if (!confirmed) return
    studioStore.deleteSession(session.id)
    Message.success('会话已删除')
}

async function handleClearAll() {
    const confirmed = await confirmDialog('确定清空全部会话吗？该操作不可恢复', '清空会话', '清空', true)
    if (!confirmed) return
    studioStore.clearAllSessions()
    Message.success('已清空全部会话')
}

/** 导出会话为 Markdown 文件（本地生成，不请求后端） */
function handleExport(session: studioSession) {
    const lines = [`# ${session.title}`, '']
    for (const msg of session.messages) {
        if (msg.role === 'user') {
            lines.push(`## 用户`, '', msg.content, '')
            if (msg.images?.length) {
                lines.push(`（附图 ${msg.images.length} 张）`, '')
            }
        } else {
            if (msg.reasoning) {
                lines.push('<details><summary>思维过程</summary>', '', msg.reasoning, '', '</details>', '')
            }
            lines.push(`## 助手`, '', msg.content, '')
        }
    }
    const blob = new Blob([lines.join('\n')], {type: 'text/markdown;charset=utf-8'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = `${session.title.replace(/[\\/:*?"<>|]/g, '_')}.md`
    a.click()
    URL.revokeObjectURL(url)
}
</script>

<style scoped>
.session-sidebar {
    display: flex;
    flex-direction: column;
    height: 100%;
    background: var(--color-white);
}

/* ── 窄屏抽屉标题栏：桌面隐藏 ── */
.drawer-head {
    display: none;
}

.drawer-head-left {
    display: flex;
    align-items: center;
    gap: var(--space-2);
}

.drawer-title {
    font-size: var(--text-sm);
    font-weight: var(--font-semibold);
    color: var(--color-text);
}

.drawer-count {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
}

.drawer-close {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 28px;
    height: 28px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-text-secondary);
    font-size: var(--text-base);
    cursor: pointer;
}

.drawer-close:hover {
    background: var(--color-gray-100);
}

/* ── 头部浅底区 ── */
.sidebar-header {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
    padding: var(--space-3);
    background: var(--color-bg-subtle);
    border-bottom: 1px solid var(--color-border);
}

.sidebar-meta {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
}

/* ── 分组列表 ── */
.session-list {
    flex: 1;
    min-height: 0;
    overflow-y: auto;
    padding: var(--space-2);
}

.session-empty {
    padding: var(--space-6) 0;
    text-align: center;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
}

.session-group + .session-group {
    margin-top: var(--space-2);
    padding-top: var(--space-2);
    border-top: 1px solid var(--color-border);
}

.group-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    height: 26px;
    padding: 0 var(--space-2);
}

.group-name {
    font-size: var(--text-xs);
    font-weight: var(--font-medium);
    letter-spacing: 0.6px;
    color: var(--color-text-secondary);
}

.group-count {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    min-width: 20px;
    height: 16px;
    padding: 0 5px;
    border-radius: var(--radius-sm);
    background: var(--color-gray-100);
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
}

/* ── 会话项：左侧 3px 脊线槽保证选中/未选中文字左缘对齐 ── */
.session-item {
    display: flex;
    align-items: center;
    min-height: 52px;
    border-radius: var(--radius-md);
    overflow: hidden;
    cursor: pointer;
    transition: background-color var(--transition-fast);
}

.session-item:hover {
    background: var(--color-gray-50);
}

.session-item.active {
    background: var(--color-primary-lighter);
}

.session-spine {
    flex-shrink: 0;
    align-self: stretch;
    width: 3px;
    background: transparent;
}

.session-item.active .session-spine {
    background: var(--color-primary);
}

.session-info {
    flex: 1;
    min-width: 0;
    padding: var(--space-2) var(--space-1) var(--space-2) 9px;
}

.session-title {
    font-size: var(--text-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    color: var(--color-text);
}

.session-item.active .session-title {
    color: var(--color-primary);
    font-weight: var(--font-medium);
}

.session-meta {
    display: flex;
    align-items: center;
    gap: 6px;
    min-width: 0;
    margin-top: 4px;
}

.model-dot {
    flex-shrink: 0;
    width: 5px;
    height: 5px;
    border-radius: 50%;
}

.dot-violet { background: var(--color-violet); }
.dot-cyan { background: var(--color-cyan); }
.dot-gold { background: var(--color-gold); }
.dot-vermilion { background: var(--color-vermilion); }
.dot-blue { background: var(--color-primary); }
.dot-empty { background: var(--color-gray-300); }

.session-model {
    min-width: 0;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.session-time {
    flex-shrink: 0;
    margin-left: auto;
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
}

.session-actions {
    display: none;
    flex-shrink: 0;
    padding-right: var(--space-1);
}

.session-item:hover .session-actions {
    display: flex;
}

/* ── 底部：统计 + 降权的清空操作 ── */
.sidebar-footer {
    display: flex;
    align-items: center;
    justify-content: space-between;
    flex-shrink: 0;
    height: 40px;
    padding: 0 var(--space-3);
    background: var(--color-bg-subtle);
    border-top: 1px solid var(--color-border);
}

.footer-count {
    font-family: var(--font-mono);
    font-size: var(--text-2xs);
    color: var(--color-text-muted);
    font-variant-numeric: tabular-nums;
}

.footer-clear {
    padding: 4px 0;
    border: none;
    background: transparent;
    color: var(--color-text-muted);
    font-family: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
    transition: color var(--transition-fast);
}

.footer-clear:hover:not(:disabled) {
    color: var(--color-error);
}

.footer-clear:disabled {
    opacity: 0.5;
    cursor: not-allowed;
}

@media (max-width: 768px) {
    .drawer-head {
        display: flex;
        align-items: center;
        justify-content: space-between;
        flex-shrink: 0;
        height: 44px;
        padding: 0 var(--space-4);
        border-bottom: 1px solid var(--color-border);
    }
}
</style>
