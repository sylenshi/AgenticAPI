<!-- 工具执行状态条：running 旋转指示 / 进度 / 终态一句话摘要（成功绿点、失败红点） -->
<template>
  <div class="tool-status-bar">
    <div v-for="ev in events" :key="ev.id" class="tool-row" :class="ev.status">
      <span v-if="ev.status === 'running'" class="tool-spinner"></span>
      <span v-else class="status-dot" :class="ev.status"></span>
      <span class="tool-name">{{ ev.tool }}</span>
      <span v-if="ev.status === 'running' && ev.progress" class="tool-progress">
        {{ ev.progress.done }}/{{ ev.progress.total }}
      </span>
      <span v-else-if="ev.status === 'running'" class="tool-running-text">执行中…</span>
      <span v-else class="tool-summary" :title="ev.summary">{{ ev.summary }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type {agentToolEvent} from '@/types'

defineProps<{ events: agentToolEvent[] }>()
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
  background: var(--color-danger);
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
