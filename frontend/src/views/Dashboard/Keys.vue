<!-- 控制台-密钥：用户管理自己的中转 API 密钥 -->

<template>
  <div class="keys-page">
    <header class="page-head">
      <h2>API 密钥</h2>
      <p class="page-head-desc">
        调用中转接口时，请在请求头携带 Authorization: Bearer sk-xxx。
        接口地址为 POST {{ siteStore.chatCompletionsUrl }}（OpenAI Chat 兼容格式）。
      </p>
    </header>

    <div class="page-card">
      <!-- 创建密钥 -->
      <div class="create-row">
        <a-input v-model="newName" placeholder="密钥备注名，如：我的测试脚本" :max-length="50" allow-clear
                 :style="{width: 320}" @press-enter="handleCreate"/>
        <a-button type="primary" :loading="creating" :disabled="keys.length >= MAX_KEYS" @click="handleCreate">
          <template #icon>
            <icon-plus/>
          </template>
          创建密钥（{{ keys.length }}/{{ MAX_KEYS }}）
        </a-button>
      </div>

      <!-- 密钥列表 -->
      <a-table
          v-if="keys.length"
          :data="keys"
          :columns="columns"
          row-key="id"
          :bordered="{wrapper: true}"
          :pagination="false"
          :scroll="{x: 720}"
          class="keys-table"
          column-resizable
          size="small"
      >
        <template #name="{ record }">
          {{ record.name }}
        </template>
        <template #key="{ record }">
          <a-typography-text code copyable>{{ record.key }}</a-typography-text>
        </template>
        <template #status="{ record }">
          <a-tooltip :content="record.status ? '点击禁用' : '点击启用'" position="top">
            <a-switch size="small" :model-value="!!record.status" @change="handleToggle(record)"/>
          </a-tooltip>
        </template>
        <template #createTime="{ record }">{{ formatTime(record.createTime) }}</template>
        <template #lastUsedTime="{ record }">
          {{ record.lastUsedTime ? formatTime(record.lastUsedTime) : '未使用' }}
        </template>
        <template #operations="{ record }">
          <a-button type="text" size="small" status="danger" @click="handleDelete(record)">删除</a-button>
        </template>
      </a-table>
      <a-empty v-else description="还没有密钥，先创建一个吧" class="keys-empty"/>
    </div>
  </div>
</template>

<script setup lang="ts">
import {onMounted, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import type {TableColumnData} from '@arco-design/web-vue'
import {getKeys, createKey, updateKey, deleteKey} from '@/api/keys'
import type {apiKeyItem} from '@/api/keys'
import {getErrorMessage} from '@/api/request'
import {useSiteStore} from '@/stores/site'
import {confirmDialog} from '@/utils/feedback'

// 对外中转接口地址（来自站点配置，随部署地址自动变化）
const siteStore = useSiteStore()

const MAX_KEYS = 5
const keys = ref<apiKeyItem[]>([])
const newName = ref('')
const creating = ref(false)

const columns: TableColumnData[] = [
  {title: 'ID', dataIndex: 'id', width: 64},
  {title: '备注名', dataIndex: 'name', minWidth: 100},
  {title: '密钥', slotName: 'key', minWidth: 240},
  {title: '状态', slotName: 'status', width: 90, align: 'center'},
  {title: '创建时间', slotName: 'createTime', width: 170},
  {title: '最后使用', slotName: 'lastUsedTime', width: 170},
  {title: '操作', slotName: 'operations', width: 130},
]

const formatTime = (time: string | null) => (time ? time.slice(0, 10) : '-')

async function load() {
  try {
    const res = await getKeys()
    keys.value = res.data
  } catch (err) {
    Message.error(getErrorMessage(err, '获取密钥列表失败'))
  }
}

async function handleCreate() {
  const name = newName.value.trim()
  if (!name) {
    Message.warning('请填写密钥备注名')
    return
  }
  creating.value = true
  try {
    await createKey({name})
    Message.success('密钥创建成功')
    newName.value = ''
    await load()
  } catch (err) {
    Message.error(getErrorMessage(err, '密钥创建失败'))
  } finally {
    creating.value = false
  }
}

async function handleToggle(item: apiKeyItem) {
  try {
    await updateKey(item.id, {status: !item.status})
    Message.success(item.status ? '已禁用' : '已启用')
    await load()
  } catch (err) {
    Message.error(getErrorMessage(err, '操作失败'))
  }
}

async function handleDelete(item: apiKeyItem) {
  const confirmed = await confirmDialog(
      `确定删除密钥「${item.name}」吗？删除后使用该密钥的调用会立即失效。`,
      '删除密钥', '删除', true,
  )
  if (!confirmed) return
  try {
    await deleteKey(item.id)
    Message.success('密钥已删除')
    await load()
  } catch (err) {
    Message.error(getErrorMessage(err, '删除失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.keys-page {
  padding: var(--space-5) var(--space-6);
}

.create-row {
  display: flex;
  gap: var(--space-3);
  margin-bottom: var(--space-4);
}

.keys-table {
  margin-top: var(--space-2);
}

/* 密钥展示：mono 等宽 + 圆角灰底内衬，替代 Arco code 默认的方角样式 */
.keys-table :deep(code) {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 2px 8px;
  background-color: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

.keys-empty {
  padding: var(--space-10) 0;
}
</style>
