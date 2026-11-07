<!-- 控制台-兑换码：管理员统计与码管理在前；兑换输入与我的记录（所有用户）合并为一张卡在后 -->

<template>
  <div class="redeem-page">
    <header class="page-head">
      <h2>兑换码</h2>
      <p class="page-head-desc">
        输入兑换码即可充值余额，余额用于调用中转接口时按量计费（输入/缓存/输出 token 分别计价，详见模型广场各模型定价）。
      </p>
    </header>

    <!-- 管理员：兑换码监控统计（固定 4 张指标，页底覆盖全局 3 列网格为 4 列） -->
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

    <!-- 管理员：兑换码管理（筛选居左；共 X 张与生成兑换码靠右，创建动作与筛选分离） -->
    <div v-if="userStore.isAdmin" class="page-card">
      <h3 class="card-title">兑换码管理</h3>
      <div class="filter-bar manage-toolbar">
        <a-select v-model="filterStatus" placeholder="全部状态" allow-clear :style="{width: '120px'}"
                  @change="handleSearch" @clear="handleSearch">
          <a-option :value="1">未使用</a-option>
          <a-option :value="2">已使用</a-option>
          <a-option :value="0">已停用</a-option>
        </a-select>
        <a-input v-model="keyword" placeholder="按码值/使用人搜索" allow-clear :style="{width: '200px'}"
                 @press-enter="handleSearch" @clear="handleSearch"/>
        <a-input v-model="batchNo" placeholder="按批次筛选" allow-clear :style="{width: '170px'}"
                 @press-enter="handleSearch" @clear="handleSearch"/>
        <a-button @click="handleSearch">
          <template #icon>
            <icon-search/>
          </template>
          查询
        </a-button>
        <span class="manage-total">共 {{ total }} 张</span>
        <a-button type="primary" @click="openGenerate">
          <template #icon>
            <icon-plus/>
          </template>
          生成兑换码
        </a-button>
      </div>

      <!-- 批量操作条：勾选后浮现（已核销的码在行选择中禁选，见 row-selection.selectable） -->
      <div v-if="selectedKeys.length" class="batch-bar">
        <span class="batch-count">已选 {{ selectedKeys.length }} 张</span>
        <a-button size="small" @click="handleBatchDisable">批量停用</a-button>
        <a-button size="small" status="danger" @click="handleBatchDestroy">批量销毁</a-button>
        <a-link class="batch-clear" @click="selectedKeys = []">取消选择</a-link>
      </div>

      <a-table
          row-key="id"
          :data="codes"
          :columns="columns"
          :loading="loading"
          :bordered="{wrapper: true}"
          :pagination="false"
          :scroll="{x: 1200}"
          size="small"
          column-resizable
          :row-selection="{type: 'checkbox', showCheckedAll: true}"
          :selected-keys="selectedKeys"
          @selection-change="onSelectionChange"
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
          <template v-if="record.status === 1">
            <a-button type="text" size="small" status="danger" @click="handleDisable(record)">停用</a-button>
            <a-button type="text" size="small" status="danger" @click="handleDestroy(record)">销毁</a-button>
          </template>
          <a-button v-else-if="record.status === 0" type="text" size="small" status="danger"
                    @click="handleDestroy(record)">销毁
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
          show-total show-jumper show-page-size
          class="table-pagination"
          @change="loadCodes"
          @page-size-change="onPageSizeChange"
      />
    </div>

    <!-- 兑换与我的记录（所有登录用户）：同一用户流程合并为一张卡，放在管理区块之后 -->
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
        <span class="redeem-balance">当前余额 <b :title="userStore.userInfo?.balance">{{ formatAmount(userStore.userInfo?.balance, 2, '-') }}</b> 元</span>
      </div>
      <p v-if="userStore.userInfo?.isGuest" class="redeem-tip">
        访客账号不支持兑换，请注册正式账号后再兑换充值。
      </p>
      <a-divider class="redeem-divider"/>
      <h3 class="card-title">我的兑换记录</h3>
      <a-table
          v-if="records.length"
          :data="records"
          :columns="recordColumns"
          :loading="recordsLoading"
          :bordered="{wrapper: true}"
          :pagination="false"
          :scroll="{x: 900}"
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
          :page-size-options="[10, 20, 50]"
          show-total show-page-size
          class="table-pagination"
          @change="loadRecords"
          @page-size-change="onRecordsPageSizeChange"
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
  destroyRedeemCodes,
  disableRedeemCode,
  disableRedeemCodes,
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
import {formatAmount} from '@/utils/format'

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
const recordsPageSize = ref(10)
const recordsLoading = ref(false)

const recordColumns: TableColumnData[] = [
  {title: '兑换码', slotName: 'code', minWidth: 240},
  {title: '面值', slotName: 'amount', width: 140, align: 'right'},
  {title: '兑换时间', slotName: 'usedTime', width: 180},
]

async function loadRecords() {
  recordsLoading.value = true
  try {
    const res = await getRedeemRecords({page: recordsPage.value, pageSize: recordsPageSize.value})
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
  // 不设 ID 列（码值即业务标识）：9 列合计 1160px，1280px 内容列内完整放下，不再横向滚动
  {title: '兑换码', slotName: 'code', width: 230},
  {title: '面值（元）', slotName: 'amount', width: 90, align: 'right'},
  {title: '状态', slotName: 'status', width: 110, align: 'center'},
  {title: '批次', dataIndex: 'batchNo', width: 110, ellipsis: true},
  {title: '备注', slotName: 'remark', width: 110, ellipsis: true},
  {title: '使用人', slotName: 'usedUsername', width: 100, ellipsis: true},
  {title: '核销时间', slotName: 'usedTime', width: 145},
  {title: '生成时间', slotName: 'createTime', width: 145},
  {title: '操作', slotName: 'operations', width: 120, align: 'center', fixed: 'right'},
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

function onRecordsPageSizeChange(size: number) {
  recordsPageSize.value = size
  recordsPage.value = 1
  loadRecords()
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

// ═══════════════ 勾选批量操作 + 单张销毁 ═══════════════
// 行勾选状态（已核销的码不可勾选：销毁会连带抹掉用户兑换记录，后端亦有兜底校验）
const selectedKeys = ref<(string | number)[]>([])

function onSelectionChange(keys: (string | number)[]) {
  // 剔除当前页的已核销码（表头全选也会经过这里）；不在当前页的已勾选项保留（跨页批量）
  selectedKeys.value = keys.filter(k => {
    const row = codes.value.find(c => c.id === Number(k))
    return !row || row.status !== 2
  })
}

async function handleDestroy(item: redeemCodeItem) {
  const confirmed = await confirmDialog(
      `确定销毁兑换码「${item.code}」吗？销毁后该码从数据库移除、不可恢复，累计发行统计随之减少。`,
      '销毁兑换码', '销毁', true,
  )
  if (!confirmed) return
  try {
    await destroyRedeemCodes([item.id])
    Message.success('兑换码已销毁')
    await Promise.all([loadCodes(), loadStats()])
  } catch (err) {
    Message.error(getErrorMessage(err, '销毁失败'))
  }
}

async function handleBatchDisable() {
  const ids = selectedKeys.value.map(Number)
  if (!ids.length) return
  // 前端预检：勾选里没有未使用状态的码时直接提示（后端仍会兜底校验）
  const unusedCount = codes.value.filter(c => ids.includes(c.id) && c.status === 1).length
  if (!unusedCount) {
    Message.warning('所选兑换码中没有未使用状态的码，无需停用')
    return
  }
  const confirmed = await confirmDialog(
      `确定批量停用所选 ${ids.length} 张兑换码吗？仅其中 ${unusedCount} 张未使用的会被停用。`,
      '批量停用', '停用', true,
  )
  if (!confirmed) return
  try {
    const res = await disableRedeemCodes(ids)
    Message.success(`已停用 ${res.data.disabled} 张兑换码`)
    selectedKeys.value = []
    await Promise.all([loadCodes(), loadStats()])
  } catch (err) {
    Message.error(getErrorMessage(err, '批量停用失败'))
  }
}

async function handleBatchDestroy() {
  const ids = selectedKeys.value.map(Number)
  if (!ids.length) return
  const confirmed = await confirmDialog(
      `确定销毁所选 ${ids.length} 张兑换码吗？销毁后从数据库移除、不可恢复，累计发行统计随之减少（已核销的码不可勾选，不受影响）。`,
      '批量销毁', '销毁', true,
  )
  if (!confirmed) return
  try {
    const res = await destroyRedeemCodes(ids)
    Message.success(`已销毁 ${res.data.destroyed} 张兑换码`)
    selectedKeys.value = []
    await Promise.all([loadCodes(), loadStats()])
  } catch (err) {
    Message.error(getErrorMessage(err, '批量销毁失败'))
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

/* 相邻内容卡之间留间距（全局 .page-card 不带 margin，同概览页做法） */
.page-card + .page-card {
  margin-top: var(--space-4);
}

/* 卡内小节标题（同概览页 card-title 约定；全局 typography.css 版本无下边距） */
.card-title {
  margin: 0 0 var(--space-3);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

/* 统计卡列数由全局 auto-fit 栅格决定，本页不再反写 */

/* 兑换输入行与记录小节的分隔 */
.redeem-divider {
  margin: var(--space-4) 0;
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

/* 批量操作条：勾选行后浮现于表格上方 */
.batch-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
  padding: var(--space-2) var(--space-3);
  background-color: var(--color-primary-lighter);
  border-radius: var(--radius-md);
}

.batch-count {
  color: var(--color-text);
  font-size: var(--text-sm);
  font-weight: var(--font-medium);
}

.batch-clear {
  margin-left: auto;
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

/* 兑换码展示：mono 等宽 + 圆角灰底内衬（与密钥页一致；显式不折行，避免末字符掉行） */
.redeem-page :deep(code) {
  font-family: var(--font-mono);
  font-size: 12px;
  padding: 1px 6px;
  background-color: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  white-space: nowrap;
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
