<!-- 维护 Agent 底部输入框：纯文本（无图片/语音）+ 发送/停止，输入法组词保护抄工坊 -->
<template>
  <div class="agent-input">
    <textarea ref="textareaRef" v-model="text" class="input-textarea"
              placeholder="向维护 Agent 下达指令，例如：测一下所有渠道连通性 / 出一份巡检报告 / 导出并清理三个月前的对话记录…"
              rows="2" :disabled="isStreaming"
              @input="autoResize" @keydown="handleKeydown"
              @compositionstart="handleCompositionStart" @compositionend="handleCompositionEnd"/>
    <div class="toolbar-row">
      <span class="input-hint">Enter 发送 · Shift+Enter 换行</span>
      <div class="toolbar-right">
        <a-button v-if="!isStreaming" type="primary" size="small" :disabled="!canSend" @click="trySend">
          <template #icon><icon-send/></template>
          发送
        </a-button>
        <a-button v-else status="danger" size="small" @click="emit('stop')">
          <template #icon><icon-record-stop/></template>
          停止
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'

const props = defineProps<{ isStreaming: boolean }>()
const emit = defineEmits<{ send: [text: string]; stop: [] }>()

const text = ref('')
const textareaRef = ref<HTMLTextAreaElement>()
let composing = false

const canSend = computed(() => !props.isStreaming && !!text.value.trim())

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 180) + 'px'
}

function handleKeydown(e: KeyboardEvent) {
  // 中文输入法组词中的 Enter 是选词，不触发发送
  if (e.key === 'Enter' && !e.shiftKey && !e.isComposing && !composing) {
    e.preventDefault()
    trySend()
  }
}

function handleCompositionStart() {
  composing = true
}

function handleCompositionEnd() {
  composing = false
}

function trySend() {
  if (!canSend.value) return
  emit('send', text.value)
  text.value = ''
  requestAnimationFrame(() => {
    const el = textareaRef.value
    if (el) el.style.height = 'auto'
  })
}
</script>

<style scoped>
.agent-input {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-white);
  padding: var(--space-2) var(--space-3);
}

.input-textarea {
  display: block;
  width: 100%;
  border: none;
  outline: none;
  resize: none;
  font-size: var(--text-sm);
  line-height: 1.7;
  color: var(--color-text);
  background: transparent;
  font-family: inherit;
}

.input-textarea::placeholder {
  color: var(--color-text-muted);
}

.toolbar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-top: var(--space-1);
}

.input-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}
</style>
