<!-- 工坊底部输入框：文本 + 图片附件（选择/粘贴/拖入）+ 语音输入 + 联网搜索开关 + 发送/停止 -->
<template>
  <div class="chat-input" @dragover.prevent @drop.prevent="handleDrop">
    <!-- 图片附件预览 -->
    <div v-if="images.length" class="attachment-row">
      <div v-for="img in images" :key="img.id" class="attachment-item">
        <img :src="img.dataUrl" :alt="img.fileName"/>
        <button class="attachment-remove" title="移除" @click="removeImage(img.id)">×</button>
      </div>
    </div>

    <!-- 录音中提示条 -->
    <div v-if="recording" class="recording-bar">
      <span class="recording-dot"></span>
      录音中 {{ recordingSeconds }}s（最长 30s）
      <a-button size="mini" type="outline" status="danger" @click="stopRecording">结束并识别</a-button>
    </div>
    <div v-else-if="transcribing" class="recording-bar transcribing">语音识别中…</div>

    <!-- 文本输入区 -->
    <textarea ref="textareaRef" v-model="text" class="input-textarea"
              :placeholder="placeholder" rows="2"
              :disabled="studioStore.isStreaming"
              @input="autoResize" @keydown="handleKeydown" @paste="handlePaste"
              @compositionstart="handleCompositionStart" @compositionend="handleCompositionEnd"/>

    <!-- 工具栏 -->
    <div class="toolbar-row">
      <div class="toolbar-left">
        <a-tooltip :content="supportVision ? '上传图片（最多3张，不超过1MB）' : '当前模型不支持视觉输入，请切换到视觉模型'"
                   position="top">
          <a-button type="text" size="small" :disabled="!supportVision || studioStore.isStreaming"
                    @click="fileInputRef?.click()">
            <template #icon>
              <icon-image/>
            </template>
            上传图片
          </a-button>
        </a-tooltip>
        <input ref="fileInputRef" type="file" accept="image/*" multiple hidden @change="handleFileChange"/>

        <a-tooltip content="语音输入（仅支持中文输入，不超过30s）" position="top">
          <a-button type="text" size="small" :status="recording ? 'danger' : undefined"
                    :disabled="studioStore.isStreaming || transcribing" @click="toggleRecording">
            <template #icon>
              <icon-voice/>
            </template>
            语音输入
          </a-button>
        </a-tooltip>


        <a-tooltip content="联网搜索" position="top">
          <a-button type="text" size="small" class="search-toggle" :class="{active: studioStore.enableSearch}"
                    :disabled="studioStore.isStreaming"
                    @click="studioStore.enableSearch = !studioStore.enableSearch">
            <template #icon>
              <icon-search/>
            </template>
            联网搜索
            <span v-if="studioStore.enableSearch" class="search-label">已开启</span>
          </a-button>
        </a-tooltip>
      </div>

      <div class="toolbar-right">
        <span class="input-hint">按 Enter 发送</span>
        <a-button v-if="!studioStore.isStreaming" type="primary" size="small" :disabled="!canSend"
                  @click="trySend">
          <template #icon>
            <icon-send/>
          </template>
          发送
        </a-button>
        <a-button v-else status="danger" size="small" @click="emit('stop')">
          <template #icon>
            <icon-record-stop/>
          </template>
          停止
        </a-button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {ref, computed, onBeforeUnmount} from 'vue'
import {Message} from '@arco-design/web-vue'
import {useStudioStore, genStudioId} from '@/stores/studio'
import {studioAsr} from '@/api/studio'
import type {studioImage} from '@/types'
import {getErrorMessage} from '@/api/request'

const props = defineProps<{
  /** 当前所选模型是否支持图片输入 */
  supportVision: boolean
}>()

const emit = defineEmits<{
  send: [payload: { text: string; images: studioImage[] }]
  stop: []
}>()

const studioStore = useStudioStore()

const text = ref('')
const images = ref<studioImage[]>([])
const textareaRef = ref<HTMLTextAreaElement>()
const fileInputRef = ref<HTMLInputElement>()

const placeholder = computed(() =>
    props.supportVision ? '请在此输入发送消息，支持图片、语音、联网搜索等…' : '请在此输入发送消息，支持语音、联网搜索等…',
)

const canSend = computed(() =>
    !studioStore.isStreaming && (!!text.value.trim() || images.value.length > 0),
)

/** ═══════════ 文本输入：自适应高度 + 快捷键（含输入法组词保护） ═══════════ */

let composing = false

function autoResize() {
  const el = textareaRef.value
  if (!el) return
  el.style.height = 'auto'
  el.style.height = Math.min(el.scrollHeight, 200) + 'px'
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
  emit('send', {text: text.value, images: [...images.value]})
  text.value = ''
  images.value = []
  nextTickResize()
}

function nextTickResize() {
  requestAnimationFrame(() => {
    const el = textareaRef.value
    if (el) el.style.height = 'auto'
  })
}

/** ═══════════ 图片附件：选择 / 粘贴 / 拖入，最多 3 张、单张 ≤ 1MB（与 tooltip 文案一致） ═══════════ */

const MAX_IMAGE_SIZE = 1 * 1024 * 1024
// 会话含图片 dataUrl 会全量落 localStorage，多图/大图会把 5MB 存储配额撑爆
const MAX_IMAGE_COUNT = 3

function addImageFiles(files: Iterable<File>) {
  const valid = [...files].filter(f => f.type.startsWith('image/'))
  let slots = MAX_IMAGE_COUNT - images.value.length
  if (slots <= 0) {
    Message.warning(`最多上传 ${MAX_IMAGE_COUNT} 张图片`)
    return
  }
  for (const file of valid) {
    if (slots <= 0) {
      Message.warning(`最多上传 ${MAX_IMAGE_COUNT} 张图片，多余的已跳过`)
      break
    }
    if (file.size > MAX_IMAGE_SIZE) {
      Message.warning(`图片 ${file.name} 超过 1MB，已跳过`)
      continue
    }
    slots -= 1
    const reader = new FileReader()
    reader.onload = () => {
      images.value.push({
        id: genStudioId(),
        dataUrl: String(reader.result),
        mimeType: file.type,
        fileName: file.name,
      })
    }
    reader.readAsDataURL(file)
  }
}

function handleFileChange(e: Event) {
  const input = e.target as HTMLInputElement
  if (input.files) addImageFiles(input.files)
  input.value = '' // 允许重复选择同一文件
}

function handlePaste(e: ClipboardEvent) {
  const files: File[] = []
  for (const item of e.clipboardData?.items || []) {
    if (item.kind === 'file') {
      const file = item.getAsFile()
      if (file) files.push(file)
    }
  }
  if (files.length) {
    e.preventDefault()
    addImageFiles(files)
  }
}

function handleDrop(e: DragEvent) {
  if (e.dataTransfer?.files?.length) addImageFiles(e.dataTransfer.files)
}

function removeImage(id: string) {
  images.value = images.value.filter(img => img.id !== id)
}

/** ═══════════ 语音输入：MediaRecorder 录音（≤30s）→ 后端 ASR → 文本回填 ═══════════ */

const recording = ref(false)
const transcribing = ref(false)
const recordingSeconds = ref(0)
let mediaRecorder: MediaRecorder | null = null
let audioChunks: Blob[] = []
let recordTimer: ReturnType<typeof setInterval> | null = null
let audioMimeType = ''

async function toggleRecording() {
  if (recording.value) {
    stopRecording()
  } else {
    await startRecording()
  }
}

async function startRecording() {
  let stream: MediaStream
  try {
    stream = await navigator.mediaDevices.getUserMedia({audio: true})
  } catch {
    Message.error('无法访问麦克风，请检查浏览器权限')
    return
  }

  // 浏览器兼容：优先 webm（映射为 ogg），否则 mp4（映射为 mp3）
  audioMimeType = typeof MediaRecorder.isTypeSupported === 'function' && MediaRecorder.isTypeSupported('audio/webm')
      ? 'audio/webm'
      : 'audio/mp4'
  try {
    mediaRecorder = new MediaRecorder(stream, {mimeType: audioMimeType})
  } catch {
    mediaRecorder = new MediaRecorder(stream)
  }
  audioChunks = []
  mediaRecorder.ondataavailable = (e) => {
    if (e.data.size > 0) audioChunks.push(e.data)
  }
  mediaRecorder.onstop = () => {
    stream.getTracks().forEach(track => track.stop())
    void transcribe(new Blob(audioChunks, {type: mediaRecorder?.mimeType || audioMimeType}))
  }
  mediaRecorder.start()

  recording.value = true
  recordingSeconds.value = 0
  recordTimer = setInterval(() => {
    recordingSeconds.value += 1
    if (recordingSeconds.value >= 30) stopRecording() // 最长 30 秒自动结束
  }, 1000)
}

function stopRecording() {
  if (recordTimer !== null) {
    clearInterval(recordTimer)
    recordTimer = null
  }
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.stop()
  }
  recording.value = false
}

async function transcribe(blob: Blob) {
  transcribing.value = true
  try {
    const base64 = await blobToBase64(blob)
    const format = audioMimeType.includes('webm') ? 'ogg' : 'mp3'
    const res = await studioAsr(base64, format)
    const recognized = (res.data?.text || '').trim()
    if (recognized) {
      text.value = text.value ? text.value + recognized : recognized
      autoResize()
    } else {
      Message.warning('未识别到语音内容')
    }
  } catch (err) {
    Message.error(getErrorMessage(err, '语音识别失败'))
  } finally {
    transcribing.value = false
  }
}

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onload = () => resolve(String(reader.result).split(',')[1] || '')
    reader.onerror = () => reject(new Error('录音读取失败'))
    reader.readAsDataURL(blob)
  })
}

// 离开页面时清理录音状态
onBeforeUnmount(() => {
  if (recordTimer !== null) clearInterval(recordTimer)
  if (mediaRecorder?.state === 'recording') {
    mediaRecorder.onstop = null
    mediaRecorder.stop()
  }
})
</script>

<style scoped>
.chat-input {
  border-top: 1px solid var(--color-border);
  background: var(--color-white);
  padding: var(--space-2) var(--space-4) var(--space-2);
}

/* 附件预览 */
.attachment-row {
  display: flex;
  flex-wrap: wrap;
  gap: var(--space-2);
  margin-bottom: var(--space-2);
}

.attachment-item {
  position: relative;
  width: 64px;
  height: 64px;
}

.attachment-item img {
  width: 100%;
  height: 100%;
  object-fit: cover;
  border-radius: var(--radius-md);
  border: 1px solid var(--color-border);
}

.attachment-remove {
  position: absolute;
  top: -6px;
  right: -6px;
  width: 18px;
  height: 18px;
  border-radius: 50%;
  border: none;
  background: var(--color-error);
  color: var(--color-white);
  font-size: 12px;
  line-height: 18px;
  cursor: pointer;
}

/* 录音提示条（颜色/圆角一律引用设计令牌，禁止写死十六进制色值） */
.recording-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 8px;
  padding: 4px 12px;
  border-radius: var(--radius-md);
  background: var(--color-warning-light);
  color: var(--color-warning);
  font-size: 14px;
}

.recording-bar.transcribing {
  background: var(--color-success-light);
  color: var(--color-success);
}

.recording-dot {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--color-warning);
  animation: recording-pulse 1s infinite;
}

.recording-bar.transcribing .recording-dot {
  background: var(--color-success);
}

@keyframes recording-pulse {
  50% {
    opacity: 0.3;
  }
}

/* 文本输入区 */
.input-textarea {
  display: block;
  width: 100%;
  max-width: 780px;
  margin: 0 auto;
  box-sizing: border-box;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  font-family: inherit;
  line-height: 1.6;
  resize: none;
  outline: none;
  max-height: 200px;
  transition: border-color var(--transition-fast);
}

.input-textarea:focus {
  border-color: var(--color-primary);
}

.input-textarea:disabled {
  background: var(--color-gray-50);
  cursor: not-allowed;
}

/* 工具栏 */
.toolbar-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  max-width: 780px;
  margin: var(--space-1) auto 0;
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: 2px;
}

.search-toggle.active {
  color: var(--color-primary);
}

.search-label {
  margin-left: var(--space-1);
  font-size: var(--text-xs);
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.input-hint {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* 窄屏兜底（规范 §5）：三栏布局下中间聊天区可能被压到 400px 以下，
   隐藏"按 Enter 发送"提示并允许工具栏换行，避免与发送按钮互相挤压 */
@media (max-width: 960px) {
  .input-hint {
    display: none;
  }

  .toolbar-row {
    flex-wrap: wrap;
    row-gap: var(--space-1);
  }
}
</style>
