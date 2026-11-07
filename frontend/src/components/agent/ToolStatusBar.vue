<!-- 工具执行状态条：running 旋转指示 / 进度 / 终态一句话摘要（成功绿点、失败红点）；
     沙箱命令带实时输出时行下挂可折叠控制台（运行中展开自动滚动，终态折叠可再展开） -->
<template>
  <div class="tool-status-bar">
    <template v-for="ev in events" :key="ev.id">
      <div class="tool-row" :class="ev.status">
        <span v-if="ev.status === 'running'" class="tool-spinner"></span>
        <span v-else class="status-dot" :class="ev.status"></span>
        <span class="tool-name">{{ ev.tool }}</span>
        <span v-if="ev.status === 'running' && ev.progress" class="tool-progress">
          {{ ev.progress.done }}/{{ ev.progress.total }}
        </span>
        <span v-else-if="ev.status === 'running'" class="tool-running-text">执行中…</span>
        <span v-else class="tool-summary" :title="ev.summary">{{ ev.summary }}</span>
        <button v-if="ev.output && ev.status !== 'running'" class="output-toggle"
                @click="toggle(ev.id)">
          {{ expanded.has(ev.id) ? '收起输出' : '查看输出' }}
        </button>
      </div>
      <div v-if="ev.output && (ev.status === 'running' || expanded.has(ev.id))"
           :ref="el => setConsoleRef(ev.id, el)" class="output-console">
        <pre>{{ ev.output }}</pre>
      </div>
    </template>
  </div>
</template>

<script setup lang="ts">
import {nextTick, ref, watch} from 'vue'
import type {agentToolEvent} from '@/types'

const props = defineProps<{ events: agentToolEvent[] }>()

/** 展开态（终态行点击「查看输出」切换；运行中恒展开） */
const expanded = ref(new Set<string>())
const consoleEls = new Map<string, HTMLElement>()

function toggle(id: string) {
    const next = new Set(expanded.value)
    if (next.has(id)) next.delete(id)
    else next.add(id)
    expanded.value = next
}

function setConsoleRef(id: string, el: unknown) {
    if (el instanceof HTMLElement) consoleEls.set(id, el)
    else consoleEls.delete(id)
}

/** 运行中的控制台输出增长时贴底跟随（终态展开不自动滚动，尊重用户翻阅） */
watch(
    () => props.events.map(e => `${e.id}:${e.status}:${e.output?.length ?? 0}`).join('|'),
    () => nextTick(() => {
        for (const ev of props.events) {
            if (ev.status !== 'running' || !ev.output) continue
            const el = consoleEls.get(ev.id)
            if (el) el.scrollTop = el.scrollHeight
        }
    }),
)
</script>

<style scoped>
.tool-status-bar {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: var(--space-3);
}

.tool-row {
  display: flex;
  align-items: baseline;
  gap: 8px;
  padding: 4px 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-gray-50);
  font-size: var(--text-xs);
  line-height: 1.6;
  min-width: 0;
}

.tool-name {
  font-family: var(--font-mono);
  color: var(--color-text-secondary);
  flex-shrink: 0;
}

.tool-progress {
  font-variant-numeric: tabular-nums;
  color: var(--color-primary);
  flex-shrink: 0;
}

.tool-running-text {
  color: var(--color-text-muted);
}

.tool-summary {
  color: var(--color-text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.output-toggle {
  margin-left: auto;
  flex-shrink: 0;
  border: none;
  background: none;
  padding: 0 2px;
  font-size: var(--text-xs);
  color: var(--color-primary);
  cursor: pointer;
}

.output-toggle:hover {
  text-decoration: underline;
}

/* 沙箱输出控制台：滚动 + 自动换行的等宽块（样式口径与思维链折叠块一致） */
.output-console {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-gray-50);
  padding: 8px 10px;
  max-height: 220px;
  overflow-y: auto;
}

.output-console pre {
  margin: 0;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.55;
  color: var(--color-text-secondary);
  white-space: pre-wrap;
  word-break: break-all;
}

.status-dot {
  width: 7px;
  height: 7px;
  border-radius: 50%;
  flex-shrink: 0;
  transform: translateY(-1px);
}

.status-dot.done {
  background: var(--color-success);
}

.status-dot.failed {
  background: var(--color-error);
}

.tool-spinner {
  flex-shrink: 0;
  width: 11px;
  height: 11px;
  border: 2px solid var(--color-primary-light);
  border-top-color: var(--color-primary);
  border-radius: 50%;
  animation: tool-spin 0.8s linear infinite;
  transform: translateY(1px);
  align-self: center;
}

@keyframes tool-spin {
  to { transform: translateY(1px) rotate(360deg); }
}
</style>
