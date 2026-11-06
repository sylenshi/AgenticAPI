<!-- 模型示例面板：接入信息卡片（Base URL / API Key / 模型名称，供第三方 AI 工具接入）+ curl/Python 调用示例 -->
<!-- 随抽屉 unmount-on-close 每次打开重新挂载：密钥拉取与语言选择自然回到初始态 -->

<template>
  <div class="model-example-panel">
    <p class="example-tip">
      在 Cherry Studio、ChatBox、LobeChat 等第三方 AI 工具中填入下方接入信息即可使用
      {{ model?.name }}；本站接口兼容 OpenAI 格式，也可直接复制调用示例运行。
    </p>

    <!-- 接入信息：第三方工具只认这三项，逐项复制即可 -->
    <div class="access-card">
      <div class="access-row">
        <span class="access-label">Base URL</span>
        <span class="access-value" :title="relayBaseUrl">{{ relayBaseUrl }}</span>
        <a-button class="access-copy" type="text" size="mini"
                  @click="copyText(relayBaseUrl, 'Base URL 已复制')">
          <template #icon>
            <icon-copy/>
          </template>
        </a-button>
      </div>
      <div class="access-row">
        <span class="access-label">API Key</span>
        <span class="access-value" :class="{'is-placeholder': !userApiKey}" :title="displayApiKey">
          {{ displayApiKey }}
        </span>
        <a-button class="access-copy" type="text" size="mini" :disabled="!userApiKey"
                  @click="copyText(userApiKey, 'API Key 已复制')">
          <template #icon>
            <icon-copy/>
          </template>
        </a-button>
      </div>
      <div class="access-row">
        <span class="access-label">模型名称</span>
        <span class="access-value" :title="model?.name">{{ model?.name }}</span>
        <a-button class="access-copy" type="text" size="mini"
                  @click="copyText(model?.name || '', '模型名称已复制')">
          <template #icon>
            <icon-copy/>
          </template>
        </a-button>
      </div>
    </div>
    <p class="access-hint">{{ apiKeyHint }}</p>

    <!-- 调用示例：curl / Python 切换，请求体 JSON 格式化缩进 -->
    <a-radio-group v-model="exampleLang" type="button" size="small" class="example-lang">
      <a-radio value="curl">curl</a-radio>
      <a-radio value="python">Python</a-radio>
    </a-radio-group>
    <pre class="example-code">{{ exampleCode }}</pre>

    <div class="example-actions">
      <a-button size="small" @click="copyExampleCode">
        <template #icon>
          <icon-copy/>
        </template>
        复制示例
      </a-button>
    </div>
    <!-- 模型连通性拨测已移到模型广场卡片右上角的闪电按钮（原"测试连接"入口） -->
  </div>
</template>

<script setup lang="ts">
import {computed, ref} from 'vue'
import {getKeys} from '@/api/keys'
import {useSiteStore} from '@/stores/site'
import {useUserStore} from '@/stores/user'
import {copyText} from '@/utils/feedback'
import type {modelInfoSchema} from '@/types'

const props = defineProps<{
  model: modelInfoSchema | null
}>()

const userStore = useUserStore()

/** ═══════════ 接入信息 ═══════════ */

// 对外中转接口的基地址：来自站点配置（后端 .env 的 PUBLIC_BASE_URL，随部署地址自动变化）
const siteStore = useSiteStore()
const relayBaseUrl = computed(() => siteStore.relayBaseUrl)

// 当前用户第一个启用的密钥：面板挂载时拉取（登录用户自动填入接入信息与调用示例）
const userApiKey = ref('')
const loadUserApiKey = async () => {
  userApiKey.value = ''
  if (!userStore.isLoggedIn) return
  try {
    const res = await getKeys()
    const keys = res.data || []
    userApiKey.value = (keys.find(k => k.status) || keys[0])?.key || ''
  } catch {
    // 拉取失败不影响示例展示，代码里回退到占位密钥
  }
}
loadUserApiKey()

// 调用示例里使用的密钥：无真实密钥时用占位符
const exampleApiKey = computed(() => userApiKey.value || 'sk-你的API密钥')

// 接入信息卡片里的密钥展示值与提示语（区分未登录 / 已登录无密钥）
const displayApiKey = computed(() => userApiKey.value || 'sk-未自动填入（见下方提示）')
const apiKeyHint = computed(() => {
  if (userApiKey.value) return '已自动填入你第一个处于启用状态的 API 密钥，请注意保密。'
  if (!userStore.isLoggedIn) return '登录后这里会自动填入你的 API 密钥（在控制台-密钥页创建）。'
  return '你还没有 API 密钥，到控制台-密钥页创建后会自动填入这里。'
})

/** ═══════════ 调用示例生成 ═══════════ */

// 视觉模型使用 OpenAI 的多模态消息结构，普通模型用纯文本消息
function buildExampleMessages(model: modelInfoSchema) {
  return model.supportVision
      ? [{
        role: 'user',
        content: [
          {type: 'text', text: '这张图片里有什么？'},
          {type: 'image_url', image_url: {url: 'https://example.com/image.png'}},
        ],
      }]
      : [{role: 'user', content: '你好，请介绍一下你自己'}]
}

// max_tokens 取模型上限与 1024 的较小值，避免示例一跑就顶到上限
function exampleMaxTokens(model: modelInfoSchema): number {
  return Math.min(Number(model.maxTokens) || 1024, 1024)
}

// curl 示例：请求体 JSON 按两空格缩进格式化，便于阅读
const exampleCurl = computed(() => {
  const model = props.model
  if (!model) return ''
  const body = JSON.stringify({
    model: model.name,
    messages: buildExampleMessages(model),
    max_tokens: exampleMaxTokens(model),
  }, null, 2)
  return `curl ${relayBaseUrl}/chat/completions \\\n  -H "Content-Type: application/json" \\\n  -H "Authorization: Bearer ${exampleApiKey.value}" \\\n  -d '${body}'`
})

// Python 示例：OpenAI SDK，把 base_url 指向本站即可无缝切换
const examplePython = computed(() => {
  const model = props.model
  if (!model) return ''
  // 消息部分的 Python 字面量（紧凑风格，比 JSON 全展开更易读；双引号字面量两边通用）
  const messages = model.supportVision
      ? `[
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "这张图片里有什么？"},
                {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
            ],
        },
    ]`
      : `[
        {"role": "user", "content": "你好，请介绍一下你自己"},
    ]`
  return `# pip install openai
from openai import OpenAI

client = OpenAI(
    base_url="${relayBaseUrl}",
    api_key="${exampleApiKey.value}",
)

response = client.chat.completions.create(
    model="${model.name}",
    messages=${messages},
    max_tokens=${exampleMaxTokens(model)},
)

print(response.choices[0].message.content)`
})

// 示例语言切换：curl / python
const exampleLang = ref<'curl' | 'python'>('curl')
const exampleCode = computed(() => exampleLang.value === 'curl' ? exampleCurl.value : examplePython.value)

// 复制当前语言的调用示例
const copyExampleCode = () => {
  copyText(exampleCode.value, '示例已复制')
}
</script>

<style scoped>
.example-tip {
  margin: 0 0 12px;
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.7;
}

/* 接入信息卡片：Base URL / API Key / 模型名称 三行，逐项复制 */
.access-card {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
}

.access-row {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: 6px 8px 6px 12px;
}

.access-row + .access-row {
  border-top: 1px solid var(--color-border);
}

.access-row:hover {
  background-color: var(--color-gray-50);
}

.access-label {
  flex-shrink: 0;
  width: 64px;
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-muted);
}

.access-value {
  flex: 1;
  min-width: 0;
  font-family: var(--font-mono);
  font-size: var(--text-sm);
  color: var(--color-text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

/* 占位密钥（未登录/无密钥时）置灰，与真实值区分 */
.access-value.is-placeholder {
  color: var(--color-text-muted);
}

.access-copy {
  flex-shrink: 0;
}

.access-hint {
  margin: var(--space-2) 0 var(--space-4);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

/* 示例语言切换与操作按钮 */
.example-lang {
  margin-bottom: var(--space-2);
}

.example-actions {
  display: flex;
  gap: 8px;
}

.example-code {
  padding: 12px;
  margin: 0 0 12px;
  background: var(--color-gray-800);
  color: var(--color-gray-100);
  border-radius: var(--radius-lg);
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.7;
  overflow-x: auto;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
