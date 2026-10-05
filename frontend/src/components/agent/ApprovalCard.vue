<!-- 审批卡片：工具名 + 风险等级标签 + 参数 + 影响预览 + 倒计时 + 批准/拒绝（L2 高危为 danger 语义） -->
<template>
  <div class="approval-card" :class="[`risk-${confirm.riskLevel.toLowerCase()}`, confirm.status]">
    <div class="approval-head">
      <span class="risk-tag" :class="confirm.riskLevel.toLowerCase()">{{ confirm.riskLevel }}</span>
      <span class="approval-tool">{{ confirm.tool }}</span>
      <span v-if="confirm.status === 'pending'" class="approval-countdown">{{ countdown }}s 后自动拒绝</span>
      <span v-else class="approval-verdict" :class="confirm.status">
        {{ verdictText }}
      </span>
    </div>

    <!-- 参数（折叠长 JSON） -->
    <div class="approval-section">
      <div class="section-label">参数</div>
      <pre class="approval-args">{{ argsText }}</pre>
    </div>

    <!-- 影响预览（save_skill 的完整草稿也在这里展示） -->
    <div v-if="confirm.impact" class="approval-section">
      <div class="section-label">影响预览</div>
      <pre class="approval-impact">{{ confirm.impact }}</pre>
    </div>

    <div v-if="confirm.status === 'pending'" class="approval-actions">
      <a-button size="small" @click="emit('resolve', false)">拒绝</a-button>
      <a-button size="small" type="primary"
                :status="confirm.riskLevel === 'L2' ? 'warning' : 'normal'"
                @click="emit('resolve', true)">批准执行</a-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import {computed, onBeforeUnmount, ref, watch} from 'vue'
import type {agentConfirmState} from '@/types'

const props = defineProps<{ confirm: agentConfirmState }>()
const emit = defineEmits<{ resolve: [approved: boolean] }>()

const argsText = computed(() => {
    try {
        return JSON.stringify(props.confirm.args, null, 2)
    } catch {
        return String(props.confirm.args)
    }
})

const verdictText = computed(() => ({
    approved: '已批准',
    rejected: '已拒绝',
    timeout: '已超时',
    pending: '',
}[props.confirm.status] ?? ''))

/** 倒计时（每秒递减；审批等待 300s 超时） */
const countdown = ref(props.confirm.expiresIn ?? 300)
let timer: number | undefined

watch(() => props.confirm.status, (status) => {
    if (status !== 'pending' && timer) {
        window.clearInterval(timer)
        timer = undefined
    }
})
if (props.confirm.status === 'pending') {
    timer = window.setInterval(() => {
        countdown.value = Math.max(0, countdown.value - 1)
    }, 1000)
}
onBeforeUnmount(() => {
    if (timer) window.clearInterval(timer)
})
</script>

<style scoped>
.approval-card {
  border: 1px solid var(--color-warning);
  border-left-width: 3px;
  border-radius: var(--radius-md);
  background: var(--color-warning-light);
  padding: var(--space-3);
  margin-bottom: var(--space-3);
  font-size: var(--text-xs);
}

.approval-card.risk-l2 {
  border-color: var(--color-danger);
  background: var(--color-error-light);
}

.approval-card.approved {
  opacity: 0.75;
}

.approval-card.rejected,
.approval-card.timeout {
  opacity: 0.6;
}

.approval-head {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.risk-tag {
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  font-weight: var(--font-semibold);
  font-size: 11px;
  background: var(--color-warning);
  color: var(--color-white);
}

.risk-tag.l2 {
  background: var(--color-danger);
}

.approval-tool {
  font-family: var(--font-mono);
  font-weight: var(--font-medium);
  color: var(--color-text);
}

.approval-countdown {
  margin-left: auto;
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.approval-verdict {
  margin-left: auto;
  font-weight: var(--font-medium);
}

.approval-verdict.approved { color: var(--color-success); }
.approval-verdict.rejected { color: var(--color-danger); }
.approval-verdict.timeout { color: var(--color-text-muted); }

.approval-section {
  margin-bottom: var(--space-2);
}

.section-label {
  color: var(--color-text-muted);
  margin-bottom: 2px;
}

.approval-args,
.approval-impact {
  margin: 0;
  padding: 6px 10px;
  background: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  font-family: var(--font-mono);
  font-size: 11.5px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 220px;
  overflow-y: auto;
}

.approval-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-2);
}
</style>
