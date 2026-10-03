<!-- 控制台-兑换码：所有用户可兑换充值、查看自己的兑换记录；管理员可生成/管理/监控兑换码 -->

<template>
  <div class="redeem-page">
    <header class="page-head">
      <h2>兑换码</h2>
      <p class="page-head-desc">
        输入兑换码即可充值余额，余额用于调用中转接口时按量计费（输入/缓存/输出 token 分别计价，详见模型广场各模型定价）。
      </p>
    </header>

    <!-- 兑换卡（所有登录用户） -->
    <div class="page-card">
      <div class="redeem-row">
        <a-input v-model="code" placeholder="输入兑换码，如 AGC-XXXXX-XXXXX-XXXXX" :max-length="64" allow-clear
                 :style="{width: '340px'}" @press-enter="handleRedeem"/>
        <a-button type="primary" :loading="redeeming" :disabled="userStore.userInfo?.isGuest" @click="handleRedeem">
          <template #icon>
            <icon-gift/>
          </template>
          兑换
        </a-button>
        <span class="redeem-balance">当前余额 <b>{{ userStore.userInfo?.balance ?? '-' }}</b> 元</span>
      </div>
      <p v-if="userStore.userInfo?.isGuest" class="redeem-tip">
        访客账号不支持兑换，请注册正式账号后再兑换充值。
      </p>
    </div>

    <!-- 管理员：兑换码监控统计 -->
    <div v-if="userStore.isAdmin" class="stat-cards">
      <div class="stat-card stat-accent-violet">
        <div class="stat-label">累计发行（张）</div>
        <div class="stat-value">{{ stats?.totalCount ?? '-' }}</div>
      </div>
      <div class="stat-card stat-accent-green">
        <div class="stat-label">未使用（张）</div>
        <div class="stat-value">{{ stats?.unusedCount ?? '-' }}</div>
      </div>
      <div class="stat-card stat-accent-cyan">
        <div class="stat-label">已使用（张）</div>
        <div class="stat-value">{{ stats?.usedCount ?? '-' }}</div>
      </div>
      <div class="stat-card stat-accent-orange">
        <div class="stat-label">已核销金额（元）</div>
        <div class="stat-value">{{ stats ? stats.usedAmount.toFixed(2) : '-' }}</div>
      </div>
    </div>

    <!-- 管理员：兑换码管理 -->
    <div v-if="userStore.isAdmin" class="page-card">
      <div class="filter-bar manage-toolbar">
        <a-select v-model="filterStatus" placeholder="全部状态" :style="{width: '120px'}" @change="handleSearch">
          <a-option :value="undefined">全部状态</a-option>
          <a-option :value="1">未使用</a-option>
          <a-option :value="2">已使用</a-option>
          <a-option :value="0">已停用</a-option>
        </a-select>
        <a-input v-model="keyword" placeholder="按码值/使用人搜索" allow-clear :style="{width: '200px'}"
                 @press-enter="handleSearch" @clear="handleSearch"/>
        <a-input v-model="batchNo" placeholder="按批次筛选" allow-clear :style="{width: '170px'}"
                 @press-enter="handleSearch" @clear="handleSearch"/>
        <a-button type="primary" @click="handleSearch">
          <template #icon>
            <icon-search/>
          </template>
          查询
        </a-button>
        <a-button type="primary" @click="openGenerate">
          <template #icon>
            <icon-plus/>
          </template>
          生成兑换码
        </a-button>
        <span class="manage-total">共 {{ total }} 张</span>
      </div>

      <a-table
          row-key="id"
          :data="codes"
          :columns="columns"
          :loading="loading"
          :bordered="{wrapper: true}"
          :pagination="false"
          size="small"
          column-resizable
          class="redeem-table"
      >
        <template #code="{ record }">
          <a-typography-text code copyable>{{ record.code }}</a-typography-text>
        </template>
        <template #amount="{ record }">{{ Number(record.amount).toFixed(2) }}</template>
        <template #status="{ record }">
          <span class="status-cell" :class="statusClass(record.status)">
            <span class="status-dot"/>
            {{ statusText(record.status) }}
          </span>
        </template>
        <template #remark="{ record }">{{ record.remark || '-' }}</template>
        <template #usedUsername="{ record }">{{ record.usedUsername || '-' }}</template>
        <template #usedTime="{ record }">{{ formatTime(record.usedTime) }}</template>
        <template #createTime="{ record }">{{ formatTime(record.createTime) }}</template>
        <template #operations="{ record }">
          <a-button v-if="record.status === 1" type="text" size="small" status="danger"
                    @click="handleDisable(record)">停用
          </a-button>
          <span v-else class="op-placeholder">-</span>
        </template>
      </a-table>

      <a-pagination
          v-if="total > pageSize"
          v-model:current="page"
          :total="total"
          :page-size="pageSize"
          :page-size-options="[10, 20, 50]"
          show-total show-jumper
          class="table-pagination"
          @change="loadCodes"
          @page-size-change="onPageSizeChange"
      />
    </div>

    <!-- 我的兑换记录（所有登录用户） -->
    <div class="page-card">
      <h3 class="card-title">我的兑换记录</h3>
      <a-table
          v-if="records.length"
          :data="records"
          :columns="recordColumns"
          :loading="recordsLoading"
          :bordered="{wrapper: true}"
          :pagination="false"
          size="small"
          column-resizable
          class="redeem-table"
      >
        <template #code="{ record }">
          <a-typography-text code copyable>{{ record.code }}</a-typography-text>
        </template>
        <template #amount="{ record }">+{{ Number(record.amount).toFixed(2) }} 元</template>
        <template #usedTime="{ record }">{{ formatTime(record.usedTime) }}</template>
      </a-table>
      <a-empty v-else-if="!recordsLoading" description="还没有兑换记录，兑换后会展示在这里"/>
      <a-pagination
          v-if="recordsTotal > recordsPageSize"
          v-model:current="recordsPage"
          :total="recordsTotal"
          :page-size="recordsPageSize"
          show-total
          class="table-pagination"
          @change="loadRecords"
      />
    </div>

    <!-- 生成兑换码弹窗（管理员）：表单 → 生成结果（码列表 + 一键复制） -->
    <a-modal v-model:visible="generateVisible" :title="generateResult ? '生成成功' : '生成兑换码'" :width="480"
             :footer="false" unmount-on-close @close="closeGenerate">
      <template v-if="!generateResult">
        <a-form :model="generateForm" layout="vertical" class="generate-form">
          <div class="generate-form-row">
            <a-form-item label="数量（张）" class="generate-form-item">
              <a-input-number v-model="generateForm.count" :min="1" :max="100" :precision="0" :style="{width: '100%'}"/>
            </a-form-item>
            <a-form-item label="每张面值（元）" class="generate-form-item">
              <a-input-number v-model="generateForm.amount" :min="0.01" :step="1" :precision="2" :style="{width: '100%'}"/>
            </a-form-item>
          </div>
          <a-form-item label="批次号（选填，留空自动生成）">
            <a-input v-model="generateForm.batchNo" placeholder="如 ZZ20261001" :max-length="32" allow-clear/>
          </a-form-item>
          <a-form-item label="备注（选填）">
            <a-input v-model="generateForm.remark" placeholder="如：十月活动发放" :max-length="255" allow-clear/>
          </a-form-item>
        </a-form>
        <div class="generate-actions">
          <a-button @click="generateVisible = false">取消</a-button>
          <a-button type="primary" :loading="generating" @click="handleGenerate">
            生成（{{ generateForm.count || 0 }} 张 × {{ generateForm.amount || 0 }} 元）
          </a-button>
        </div>
      </template>
      <template v-else>
        <p class="generate-tip">
          批次 <b>{{ generateResult.batchNo }}</b>，共 {{ generateResult.codes.length }} 张，请妥善保存（仅本次展示，可稍后在列表中复制）。
        </p>
        <div class="generate-codes">
          <a-typography-text v-for="c in generateResult.codes" :key="c" code copyable>{{ c }}</a-typography-text>
        </div>
        <div class="generate-actions">
          <a-button type="outline" @click="copyAllCodes">
            <template #icon>
              <icon-copy/>
            </template>
            复制全部
          </a-button>
          <a-button type="primary" @click="generateVisible = false">完成</a-button>
        </div>
      </template>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import {onMounted, reactive, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import type {TableColumnData} from '@arco-design/web-vue'
import {
  disableRedeemCode,
  generateRedeemCodes,
  getRedeemCodes,
  getRedeemRecords,
  getRedeemStats,
  redeemCode,
} from '@/api/redemption'
import type {redeemCodeItem, redeemRecordItem, redeemStats} from '@/api/redemption'
import {getErrorMessage} from '@/api/request'
import {useUserStore} from '@/stores/user'
import {confirmDialog, copyText} from '@/utils/feedback'

const userStore = useUserStore()

// ═══════════════ 兑换（所有登录用户） ═══════════════
const code = ref('')
const redeeming = ref(false)

async function handleRedeem() {
  const value = code.value.trim()
  if (!value) {
    Message.warning('请输入兑换码')
    return
  }
  redeeming.value = true
  try {
    const res = await redeemCode(value)
    // 在线变更余额：直接写 store，概览页与导航等处即时联动
    if (userStore.userInfo) {
      userStore.userInfo.balance = res.data.balance
    }
    Message.success('兑换成功')
    code.value = ''
    recordsPage.value = 1
    await loadRecords()
  } catch (err) {
    Message.error(getErrorMessage(err, '兑换失败'))
  } finally {
    redeeming.value = false
  }
}

// ═══════════════ 我的兑换记录（所有登录用户） ═══════════════
const records = ref<redeemRecordItem[]>([])
const recordsTotal = ref(0)
const recordsPage = ref(1)
const recordsPageSize = 10
const recordsLoading = ref(false)

const recordColumns: TableColumnData[] = [
  {title: '兑换码', slotName: 'code', minWidth: 240},
  {title: '面值', slotName: 'amount', width: 140, align: 'right'},
  {title: '兑换时间', slotName: 'usedTime', width: 180},
]

async function loadRecords() {
  recordsLoading.value = true
  try {
    const res = await getRedeemRecords({page: recordsPage.value, pageSize: recordsPageSize})
    records.value = res.data.list
    recordsTotal.value = res.data.total
  } catch (err) {
    Message.error(getErrorMessage(err, '获取兑换记录失败'))
  } finally {
    recordsLoading.value = false
  }
}

// ═══════════════ 管理员：监控统计 + 码管理 ═══════════════
const stats = ref<redeemStats | null>(null)
const codes = ref<redeemCodeItem[]>([])
const total = ref(0)
const page = ref(1)
const pageSize = ref(10)
const loading = ref(false)
const filterStatus = ref<number | undefined>(undefined)
const keyword = ref('')
const batchNo = ref('')

const columns: TableColumnData[] = [
  {title: 'ID', dataIndex: 'id', width: 60, align: 'center'},
  {title: '兑换码', slotName: 'code', width: 230},
  {title: '面值（元）', slotName: 'amount', width: 90, align: 'right'},
  {title: '状态', slotName: 'status', width: 110, align: 'center'},
  {title: '批次', dataIndex: 'batchNo', width: 110, ellipsis: true},
  {title: '备注', slotName: 'remark', width: 110, ellipsis: true},
  {title: '使用人', slotName: 'usedUsername', width: 100, ellipsis: true},
  {title: '核销时间', slotName: 'usedTime', width: 160},
  {title: '生成时间', slotName: 'createTime', width: 160},
  {title: '操作', slotName: 'operations', width: 80, align: 'center', fixed: 'right'},
]

// 三态状态映射：未使用绿 / 已使用灰 / 已停用红（is-on/is-off 为全局语义类，is-used 为本页扩展）
const statusClass = (status: number) => (status === 1 ? 'is-on' : status === 2 ? 'is-used' : 'is-off')
const statusText = (status: number) => (status === 1 ? '未使用' : status === 2 ? '已使用' : '已停用')

const formatTime = (time: string | null) => (time ? time.replace('T', ' ').slice(0, 16) : '-')

async function loadStats() {
  try {
    const res = await getRedeemStats()
    stats.value = res.data
  } catch (err) {
    Message.error(getErrorMessage(err, '获取兑换码统计失败'))
  }
}

async function loadCodes() {
  loading.value = true
  try {
    const res = await getRedeemCodes({
      page: page.value,
      pageSize: pageSize.value,
      status: filterStatus.value,
      keyword: keyword.value.trim(),
      batchNo: batchNo.value.trim(),
    })
    codes.value = res.data.list
    total.value = res.data.total
  } catch (err) {
    Message.error(getErrorMessage(err, '获取兑换码列表失败'))
  } finally {
    loading.value = false
  }
}

function handleSearch() {
  page.value = 1
  loadCodes()
}

function onPageSizeChange(size: number) {
  pageSize.value = size
  page.value = 1
  loadCodes()
}

async function handleDisable(item: redeemCodeItem) {
  const confirmed = await confirmDialog(
      `确定停用兑换码「${item.code}」吗？停用后不可再被兑换。`,
      '停用兑换码', '停用', true,
  )
  if (!confirmed) return
  try {
    await disableRedeemCode(item.id)
    Message.success('兑换码已停用')
    await Promise.all([loadCodes(), loadStats()])
  } catch (err) {
    Message.error(getErrorMessage(err, '停用失败'))
  }
}

// ═══════════════ 生成兑换码弹窗 ═══════════════
const generateVisible = ref(false)
const generating = ref(false)
const generateForm = reactive({count: 10, amount: 10, batchNo: '', remark: ''})
const generateResult = ref<{ codes: string[]; batchNo: string } | null>(null)

function openGenerate() {
  generateResult.value = null
  generateVisible.value = true
}

function closeGenerate() {
  // 生成过码才需要刷新列表与统计（纯浏览关闭不动数据）
  if (generateResult.value) {
    handleSearch()
    loadStats()
  }
  generateResult.value = null
}

async function handleGenerate() {
  if (!generateForm.count || generateForm.count < 1) {
    Message.warning('请填写生成数量')
    return
  }
  if (!generateForm.amount || generateForm.amount <= 0) {
    Message.warning('请填写每张面值')
    return
  }
  generating.value = true
  try {
    const res = await generateRedeemCodes({
      count: generateForm.count,
      amount: generateForm.amount,
      batchNo: generateForm.batchNo.trim() || undefined,
      remark: generateForm.remark.trim() || undefined,
    })
    generateResult.value = res.data
    Message.success('兑换码生成成功')
  } catch (err) {
    Message.error(getErrorMessage(err, '生成失败'))
  } finally {
    generating.value = false
  }
}

function copyAllCodes() {
  if (generateResult.value) {
    copyText(generateResult.value.codes.join('\n'), '已复制全部兑换码')
  }
}

onMounted(() => {
  loadRecords()
  if (userStore.isAdmin) {
    loadStats()
    loadCodes()
  }
})
</script>

<style scoped>
.redeem-page {
  padding: var(--space-5) var(--space-6);
}

/* 兑换卡：输入 + 按钮 + 余额提示 */
.redeem-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.redeem-balance {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.redeem-balance b {
  color: var(--color-success);
  font-weight: var(--font-semibold);
}

.redeem-tip {
  margin: var(--space-3) 0 0;
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

/* 管理员工具栏 */
.manage-toolbar {
  margin-bottom: var(--space-4);
}

.manage-total {
  margin-left: auto;
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

/* 表格单元格内容不折行（时间/短数字列保持一行；长文本列已有 ellipsis 不受影响） */
.redeem-table :deep(.arco-table-td) {
  white-space: nowrap;
}

/* 已使用状态点（灰）：is-on 绿 / is-off 红来自全局 components.css */
.status-cell.is-used .status-dot {
  background-color: var(--color-gray-400);
}

.op-placeholder {
  color: var(--color-text-muted);
}

/* 兑换码展示：mono 等宽 + 圆角灰底内衬（与秘钥页一致） */
.redeem-page :deep(code) {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 2px 8px;
  background-color: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
}

/* 生成弹窗 */
.generate-form-row {
  display: flex;
  gap: var(--space-3);
}

.generate-form-item {
  flex: 1;
}

.generate-actions {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
  margin-top: var(--space-4);
}

.generate-tip {
  margin: 0 0 var(--space-3);
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

.generate-codes {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-2);
  max-height: 280px;
  overflow-y: auto;
  padding: var(--space-3);
  background-color: var(--color-gray-50);
  border-radius: var(--radius-md);
}
</style>
