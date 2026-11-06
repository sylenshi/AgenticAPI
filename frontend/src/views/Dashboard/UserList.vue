<!-- 控制台-用户：管理员管理所有用户（行内编辑 + 批量删除） -->

<template>
  <div class="userlist-page">
    <header class="page-head">
      <h2>用户管理</h2>
      <div class="filter-bar userlist-toolbar">
        <a-input v-model="keyword" placeholder="按用户名/昵称搜索" allow-clear :style="{width: 220}"
                 @press-enter="handleSearch" @clear="handleSearch"/>
        <a-button type="primary" @click="handleSearch">
          <template #icon>
            <icon-search/>
          </template>
          搜索
        </a-button>
        <a-button status="danger" :disabled="!selectedKeys.length" @click="handleBatchDelete()">
          批量删除（{{ selectedKeys.length }}）
        </a-button>
        <span class="userlist-total">共 {{ total }} 个用户</span>
      </div>
    </header>

    <!-- 用户列表（行内编辑余额/分组/管理员/状态）：白卡容器与密钥页统一 -->
    <div class="page-card">
      <a-table
          row-key="id"
          :data="users"
          :columns="columns"
          :loading="loading"
          :bordered="{wrapper: true}"
          :pagination="false"
          :row-selection="{type: 'checkbox', showCheckedAll: true, selectedRowKeys: selectedKeys}"
          :scroll="{x: 1600}"
          :row-class="record => record.isGuest ? 'guest-row' : ''"
          @selection-change="onSelectionChange"
      >
        <template #username="{ record }">
          {{ record.username }}<span v-if="record.isGuest" class="guest-mark">（访客）</span>
        </template>
        <template #nickname="{ record }">{{ record.nickname || '-' }}</template>
        <template #userGroup="{ record }">
          <a-select v-model="record.userGroup" size="small" :style="{width: 86}">
            <a-option value="free">free</a-option>
            <a-option value="vip">vip</a-option>
          </a-select>
        </template>
        <template #isAdmin="{ record }">
          <a-switch v-model="record.isAdmin" size="small"/>
        </template>
        <template #balance="{ record }">
          <a-input-number v-model="record.balance" size="small" :min="0" :step="0.01" :precision="2"
                          :style="{width: 110}" mode="button"/>
        </template>
        <template #usedQuota="{ record }">{{ record.usedQuota.toFixed(6) }}</template>
        <template #status="{ record }">
          <a-switch v-model="record.status" size="small"/>
        </template>
        <template #createTime="{ record }">{{ formatTime(record.createTime) }}</template>
        <template #lastLoginTime="{ record }">{{ formatTime(record.lastLoginTime) }}</template>
        <template #operations="{ record }">
          <a-button type="text" size="small" @click="handleSave(record)">保存</a-button>
          <a-button type="text" size="small" status="danger" @click="handleBatchDelete([record.id])">删除</a-button>
        </template>
      </a-table>

      <!-- 分页 -->
      <a-pagination
          v-if="total > pageSize"
          v-model:current="page"
          :total="total"
          :page-size="pageSize"
          :page-size-options="[10, 20, 50]"
          show-total show-jumper
          class="table-pagination"
          @change="load"
          @page-size-change="onPageSizeChange"
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import {onMounted, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import type {TableColumnData} from '@arco-design/web-vue'
import {getAdminUsers, updateAdminUser, deleteAdminUsers} from '@/api/admin'
import type {adminUserItem} from '@/api/admin'
import {getErrorMessage} from '@/api/request'
import {confirmDialog} from '@/utils/feedback'

const loading = ref(false)
const users = ref<adminUserItem[]>([])
const total = ref(0)
const keyword = ref('')
const page = ref(1)
const pageSize = ref(10)
const selectedKeys = ref<(string | number)[]>([])

const columns: TableColumnData[] = [
  {title: 'ID', dataIndex: 'id', width: 100, align: 'center'},
  {title: '用户名', slotName: 'username', width: 130, align: 'center'},
  {title: '昵称', slotName: 'nickname', width: 100, ellipsis: true, align: 'center'},
  {title: '分组', slotName: 'userGroup', width: 130, align: 'center'},
  {title: '管理员', slotName: 'isAdmin', width: 100, align: 'center'},
  {title: '余额', slotName: 'balance', width: 200, align: 'center'},
  {title: '累计消费', slotName: 'usedQuota', width: 200, align: 'right'},
  {title: '状态', slotName: 'status', width: 100, align: 'center'},
  {title: '注册时间', slotName: 'createTime', width: 170, align: 'center'},
  {title: '最后登录', slotName: 'lastLoginTime', width: 170, align: 'center'},
  {title: '操作', slotName: 'operations', width: 200, fixed: 'right', align: 'center'},
]

const formatTime = (time: string | null) => (time ? time.slice(0, 10) : '-')

function onSelectionChange(rowKeys: (string | number)[]) {
  selectedKeys.value = rowKeys
}

async function load() {
  loading.value = true
  try {
    const res = await getAdminUsers({keyword: keyword.value.trim(), page: page.value, pageSize: pageSize.value})
    users.value = res.data.list
    total.value = res.data.total
    selectedKeys.value = []
  } catch (err) {
    Message.error(getErrorMessage(err, '获取用户列表失败'))
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  load()
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  load()
}

// 保存单行修改（余额/分组/管理员/状态）
async function handleSave(row: adminUserItem) {
  if (row.balance < 0) {
    Message.warning('余额不能为负数')
    return
  }
  try {
    await updateAdminUser(row.id, {
      balance: row.balance,
      userGroup: row.userGroup,
      isAdmin: row.isAdmin,
      status: row.status,
    })
    Message.success(`用户 ${row.username} 信息已更新`)
    await load()
  } catch (err) {
    Message.error(getErrorMessage(err, '更新失败'))
  }
}

async function handleBatchDelete(ids?: number[]) {
  const targetIds = ids ?? (selectedKeys.value as number[])
  if (!targetIds.length) return
  const confirmed = await confirmDialog(
      `确定删除选中的 ${targetIds.length} 个用户吗？其登录令牌与API密钥会一并删除。`,
      '删除用户', '删除', true,
  )
  if (!confirmed) return
  try {
    const res = await deleteAdminUsers(targetIds)
    Message.success(`已删除 ${res.data.deleted} 个用户`)
    await load()
  } catch (err) {
    Message.error(getErrorMessage(err, '删除失败'))
  }
}

onMounted(load)
</script>

<style scoped>
.userlist-page {
  padding: var(--space-5) var(--space-6);
}

.userlist-toolbar {
  margin-bottom: var(--space-4);
}

.userlist-total {
  margin-left: auto;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

/* 行内编辑降噪：下拉/数字输入平时隐去边框，悬停或聚焦时恢复控件形态，
   降低 11 列表格里每行 3-4 个带边框控件的视觉噪音 */
.userlist-page :deep(.arco-table .arco-select-view-single),
.userlist-page :deep(.arco-table .arco-input-number .arco-input-wrapper) {
  border-color: transparent;
  background-color: transparent;
  transition: border-color var(--transition-fast), background-color var(--transition-fast);
}

.userlist-page :deep(.arco-table .arco-select-view-single:hover),
.userlist-page :deep(.arco-table .arco-select-view-single.arco-select-view-focus),
.userlist-page :deep(.arco-table .arco-input-number .arco-input-wrapper:hover),
.userlist-page :deep(.arco-table .arco-input-number .arco-input-wrapper.arco-input-focus) {
  border-color: var(--color-border);
  background-color: var(--color-white);
}

/* 访客行整行弱化 */
:deep(.guest-row) {
  color: var(--color-text-muted);
}

.guest-mark {
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}
</style>
