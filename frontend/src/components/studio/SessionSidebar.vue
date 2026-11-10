<!-- 工坊左侧会话侧边栏：新建 / 搜索 / 切换 / 重命名 / 导出 / 删除 / 清空 -->
<template>
    <div class="session-sidebar">
        <div class="sidebar-header">
            <a-button type="primary" long :disabled="studioStore.isStreaming"
                      @click="studioStore.createSession()">
                <template #icon><icon-plus/></template>
                新对话
            </a-button>
        </div>

        <div class="sidebar-search">
            <a-input v-model="keyword" placeholder="搜索标题或内容" allow-clear>
                <template #prefix><icon-search/></template>
            </a-input>
        </div>

        <div class="session-list">

            <div v-if="!filteredSessions.length" class="session-empty">暂无会话</div>

            <div v-for="session in filteredSessions" :key="session.id"
                 class="session-item" :class="{active: session.id === studioStore.currentSessionId}"
                 @click="studioStore.switchSession(session.id)">
                <div class="session-info">
                    <div class="session-title" :title="session.title">{{ session.title }}</div>
                    <div class="session-meta">{{ session.modelName || '未选择模型' }} · {{ formatTime(session.updateTime) }}</div>
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
                        <a-button type="text" size="small" status="danger" @click="handleDelete(session)">
                            <template #icon><icon-delete/></template>
                        </a-button>
                    </a-tooltip>
                </div>
            </div>
        </div>

        <div class="sidebar-footer">
            <a-button type="text" status="danger" size="small" long :disabled="!studioStore.sessions.length"
                      @click="handleClearAll">清空全部会话</a-button>
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

function formatTime(timestamp: number): string {
    const d = new Date(timestamp)
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`
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
            lines.push(`## 🧑 用户`, '', msg.content, '')
            if (msg.images?.length) {
                lines.push(`（附图 ${msg.images.length} 张）`, '')
            }
        } else {
            if (msg.reasoning) {
                lines.push('<details><summary>思维过程</summary>', '', msg.reasoning, '', '</details>', '')
            }
            lines.push('## 🤖 助手', '', msg.content, '')
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

.sidebar-header {
    padding: var(--space-3);
}

.sidebar-search {
    padding: 0 var(--space-3) var(--space-2);
}

.session-list {
    flex: 1;
    overflow-y: auto;
    padding: 0 var(--space-2);
}

.session-empty {
    padding: var(--space-6) 0;
    text-align: center;
    color: var(--color-text-muted);
    font-size: var(--text-sm);
}

.session-item {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 4px;
    padding: var(--space-2);
    border-radius: var(--radius-md);
    cursor: pointer;
    transition: background-color var(--transition-fast);
}

.session-item:hover {
    background: var(--color-gray-100);
}

.session-item.active {
    background: var(--color-primary-lighter);
}

.session-info {
    flex: 1;
    min-width: 0;
}

.session-title {
    font-size: var(--text-sm);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.session-item.active .session-title {
    color: var(--color-primary);
    font-weight: var(--font-medium);
}

.session-meta {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}

.session-actions {
    display: none;
    flex-shrink: 0;
}

.session-item:hover .session-actions {
    display: flex;
}

.sidebar-footer {
    padding: var(--space-2) var(--space-3);
    border-top: 1px solid var(--color-border);
    text-align: center;
}
</style>
