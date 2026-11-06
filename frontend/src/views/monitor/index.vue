<!-- 监控面板：对话数据 / 调用日志 / 数据看板 -->
<template>
  <div class="monitor-page">
    <!-- 【页面顶部】标题与说明 -->
    <header class="page-head monitor-head">
      <h1>监控面板</h1>
      <p class="page-head-desc">全站用量、对话记录、调用日志与个人数据看板</p>
    </header>

    <div class="monitor-body">
      <a-tabs v-model:active-key="activeTab" lazy-load @change="handleTabChange">
        <!-- ══════════ 标签一：对话数据 ══════════ -->
        <a-tab-pane key="chats" title="对话数据">
          <!-- 全站累计 token 卡片 -->
          <div class="stat-cards">
            <div v-for="card in siteCards" :key="card.label" class="stat-card" :class="card.tone">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-value stat-value-brand">{{ formatNumber(card.value) }}</div>
            </div>

          </div>

          <!-- 对话记录筛选栏 -->
          <div class="filter-bar">
            <a-space>
              <a-input
                  v-if="userStore.isAdmin"
                  v-model="chatFilter.username" placeholder="用户名筛选" allow-clear :style="{width: 160}"
                  @press-enter="searchChats" @clear="searchChats"
              />
              <a-input
                  v-model="chatFilter.model" placeholder="模型名筛选" allow-clear :style="{width: 180}"
                  @press-enter="searchChats" @clear="searchChats"
              />
              <a-button type="primary" @click="searchChats">
                <template #icon>
                  <icon-search/>
                </template>
                查询
              </a-button>
            </a-space>
            <p class="filter-tip">注：由于部分上游渠道不返回缓存 tokens 数量，因此缓存 tokens 的统计数量存在偏差</p>
          </div>

          <!-- 对话记录表格（行展开查看全文） -->
          <a-table
              :data="chatList" :loading="chatLoading" :columns="chatColumns" row-key="id"
              :bordered="{wrapper: true}" :pagination="false" :scroll="{x: 920}"
          >
            <template #time="{ record }">{{ formatTime(record.createTime) }}</template>
            <template #cost="{ record }">{{ record.cost?.toFixed?.(6) ?? record.cost }}</template>
            <template #duration="{ record }">{{ formatDuration(record.durationMs) }}</template>
            <!-- 新增：详情操作列 -->
            <template #detail="{ record }">
              <a-button type="text" size="small" @click="openChatDetail(record)">查看</a-button>
            </template>
          </a-table>
          <a-drawer
              v-model:visible="chatDetailVisible"
              :title="`对话详情${selectedChat?.modelName ? '：' + selectedChat.modelName : ''}`"
              :width="620"
              :mask-closable="true"
              unmount-on-close
          >
            <template v-if="selectedChat">
              <!-- 概要信息，方便对照 -->
              <a-descriptions :column="2" size="small" bordered style="margin-bottom: var(--space-3)">
                <a-descriptions-item label="时间">{{ formatTime(selectedChat.createTime) }}</a-descriptions-item>
                <a-descriptions-item label="用户">{{ selectedChat.username }}</a-descriptions-item>
                <a-descriptions-item label="模型">{{ selectedChat.modelName }}</a-descriptions-item>
                <a-descriptions-item label="输入/输出/缓存">
                  {{ selectedChat.promptTokens }} / {{ selectedChat.completionTokens }} / {{ selectedChat.cacheTokens }}
                </a-descriptions-item>
                <a-descriptions-item label="费用">{{ selectedChat.cost?.toFixed?.(6) }}</a-descriptions-item>
                <a-descriptions-item label="耗时">{{ formatDuration(selectedChat.durationMs) }}</a-descriptions-item>
              </a-descriptions>

              <div class="chat-detail">
                <div class="chat-block">
                  <div class="chat-block-title">输入内容</div>
                  <pre class="chat-block-text">{{ formatMessages(selectedChat.inputContent) }}</pre>
                </div>
                <div v-if="selectedChat.reasoningContent" class="chat-block">
                  <div class="chat-block-title">推理内容</div>
                  <pre class="chat-block-text">{{ selectedChat.reasoningContent }}</pre>
                </div>
                <div class="chat-block">
                  <div class="chat-block-title">输出内容</div>
                  <pre class="chat-block-text">{{ selectedChat.outputContent || '（空）' }}</pre>
                </div>
              </div>
            </template>
          </a-drawer>
          <a-pagination
              v-model:current="chatPage"
              v-model:page-size="chatPageSize"
              :total="chatTotal" :page-size-options="[5, 10, 20]"
              show-total show-page-size show-jumper class="table-pagination"
          />
        </a-tab-pane>

        <!-- ══════════ 标签二：调用日志 ══════════ -->
        <a-tab-pane key="logs" title="调用日志">
          <!-- 日志筛选栏 -->
          <div class="filter-bar">
            <a-space>
              <a-select v-model="logFilter.type" placeholder="日志类型" allow-clear :style="{width: 130}"
                        @change="searchLogs">
                <a-option label="API调用" value="api"/>
                <a-option label="登录注册" value="login"/>
                <a-option label="管理员操作" value="admin"/>
                <a-option label="用户操作" value="user"/>
              </a-select>
              <a-input
                  v-model="logFilter.keyword" placeholder="用户名 / 动作 / 详情" allow-clear :style="{width: 200}"
                  @press-enter="searchLogs" @clear="searchLogs"
              />
              <a-input
                  v-model="logFilter.model" placeholder="模型名" allow-clear :style="{width: 150}"
                  @press-enter="searchLogs" @clear="searchLogs"
              />
              <a-range-picker
                  v-model="logTimeRange" show-time format="YYYY-MM-DD HH:mm:ss"
                  :style="{width: 'min(390px, 100%)'}"
              />
              <a-button type="primary" @click="searchLogs">查询</a-button>
              <a-button @click="resetLogFilter">重置</a-button>
            </a-space>
          </div>

          <!-- 日志表格 -->
          <a-table
              :data="logList" :loading="logLoading" :columns="logColumns" row-key="id"
              :bordered="{wrapper: true}" :pagination="false" :scroll="{x: 1120}"
          >
            <template #time="{ record }">{{ formatTime(record.createTime) }}</template>
            <template #type="{ record }">
              <a-tag :color="logTypeTag[record.type] ?? 'gray'" size="small">
                {{ logTypeName[record.type] ?? record.type }}
              </a-tag>
            </template>
            <template #tokens="{ record }">
              {{ record.promptTokens }} / {{ record.completionTokens }} / {{ record.cacheTokens }}
            </template>
            <template #cost="{ record }">{{ record.cost ? record.cost.toFixed(6) : '-' }}</template>
            <template #duration="{ record }">{{ formatDuration(record.durationMs) }}</template>
          </a-table>
          <a-pagination
              v-model:current="logPage"
              v-model:page-size="logPageSize"
              :total="logTotal" :page-size-options="[10, 20, 50]"
              show-total show-page-size show-jumper class="table-pagination"
          />
        </a-tab-pane>

        <!-- ══════════ 标签三：数据看板 ══════════ -->
        <a-tab-pane key="stats" title="数据看板">
          <!-- 时间范围 / 粒度 / 刷新 -->
          <div class="filter-bar">
            <a-space>
              <a-range-picker
                  v-model="statsTimeRange" show-time format="YYYY-MM-DD HH:mm:ss"
                  :shortcuts="rangeShortcuts" :style="{width: 'min(390px, 100%)'}"
              />
              <a-select v-model="granularity" :style="{width: 110}">
                <a-option label="按小时" value="hour"/>
                <a-option label="按天" value="day"/>
                <a-option label="按周" value="week"/>
                <a-option label="按月" value="month"/>
              </a-select>
              <a-button type="primary" :loading="statsLoading" @click="loadStats">
                <template #icon>
                  <icon-refresh/>
                </template>
                刷新
              </a-button>
            </a-space>
            <p class="filter-tip">展示当前用户在所选时间范围内的用量，点击刷新获取最新数据</p>
          </div>


          <!-- 范围累计卡片 -->
          <div class="stat-cards">
            <div v-for="card in userCards" :key="card.label" class="stat-card" :class="card.tone">
              <div class="stat-label">{{ card.label }}</div>
              <div class="stat-value stat-value-brand">{{ formatNumber(card.value) }}</div>
            </div>
          </div>

          <template v-if="hasStatsData">
            <!-- 曲线维度选择：按模型拆分 + 可选总计 -->
            <div class="filter-bar">
              <span class="model-filter-label">曲线维度：</span>
              <a-select
                  v-model="selectedModels" multiple allow-clear :max-tag-count="3"
                  placeholder="选择要对比的模型" :style="{width: 280}"
              >
                <a-option v-for="m in availableModels" :key="m" :value="m" :label="m"/>
              </a-select>
              <a-checkbox v-model="showTotal">显示总计曲线</a-checkbox>
            </div>

            <!-- 2×2 折线图 -->
            <div class="charts-grid">
              <div v-for="chart in metricCharts" :key="chart.title" class="chart-cell">
                <div class="chart-title">{{ chart.title }}</div>
                <LineChart :x-data="chartTimes" :series="chart.series" :unit="chart.unit"/>
              </div>
            </div>
          </template>
          <a-empty v-else-if="!statsLoading" description="所选时间范围内暂无调用数据" class="stats-empty"/>
        </a-tab-pane>
      </a-tabs>
    </div>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, reactive, ref, watch} from 'vue'
import {Message} from '@arco-design/web-vue'
import type {TableColumnData} from '@arco-design/web-vue'
import LineChart from '@/components/monitor/LineChart.vue'
import {getErrorMessage} from '@/api/request'
import {
  getChatRecords, getMonitorLogs, getSiteSummary, getUserStats,
} from '@/api/monitor'
import {useUserStore} from '@/stores/user'
import type {chatRecordSchema, lineSeriesSchema, logItemSchema, siteSummarySchema, userStatsSchema} from '@/types'

const userStore = useUserStore()

// ══════════ 标签切换与懒加载 ══════════
const activeTab = ref('chats')
const loadedTabs = reactive(new Set<string>())

function handleTabChange(key: string | number | undefined) {
  loadTab(String(key))
}

function loadTab(name: string) {
  if (loadedTabs.has(name)) return
  loadedTabs.add(name)
  if (name === 'chats') {
    loadSummary()
    loadChats()
  } else if (name === 'logs') {
    loadLogs()
  } else if (name === 'stats') {
    loadStats()
  }
}

onMounted(() => loadTab(activeTab.value))

// ══════════ 通用格式化工具 ══════════
function formatNumber(n: number | null | undefined): string {
  return (n ?? 0).toLocaleString('zh-CN')
}

/** ISO 时间 → "YYYY-MM-DD HH:mm:ss" */
function formatTime(iso: string | null): string {
  return iso ? iso.replace('T', ' ').slice(0, 19) : '-'
}

function formatDuration(ms: number | null): string {
  if (ms == null) return '-'
  return ms >= 1000 ? `${(ms / 1000).toFixed(1)}s` : `${ms}ms`
}

/** Date / 选择器字符串 → 后端可解析的 "YYYY-MM-DD HH:mm:ss" 参数 */
function toParam(d: Date | string): string {
  if (typeof d === 'string') return d.replace('T', ' ').slice(0, 19)
  const p = (n: number) => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${p(d.getMonth() + 1)}-${p(d.getDate())} ${p(d.getHours())}:${p(d.getMinutes())}:${p(d.getSeconds())}`
}

/** messages 数组 → 可读文本（content 可能是非字符串的多模态结构，统一序列化） */
function formatMessages(messages: chatRecordSchema['inputContent']): string {
  if (!messages || !messages.length) return '（无输入内容）'
  return messages
      .map((m) => `[${m.role}] ${typeof m.content === 'string' ? m.content : JSON.stringify(m.content)}`)
      .join('\n\n')
}

// ══════════ 标签一：对话数据 ══════════
const siteSummary = ref<siteSummarySchema>({calls: 0, promptTokens: 0, completionTokens: 0, cacheTokens: 0})
const siteCards = computed(() => [
  {label: '全站累计输入 tokens', value: siteSummary.value.promptTokens, tone: ''},
  {label: '全站累计缓存 tokens', value: siteSummary.value.cacheTokens, tone: 'stat-accent-gold'},
  {label: '全站累计输出 tokens', value: siteSummary.value.completionTokens, tone: 'stat-accent-cyan'},

])

// 列定义放在 computed 里：管理员登录信息异步回填后"用户"列能正确出现
const chatColumns = computed<TableColumnData[]>(() => [
  {title: '时间', slotName: 'time', width: 230},
  ...(userStore.isAdmin
      ? [{title: '用户', dataIndex: 'username', width: 110, ellipsis: true, tooltip: true}]
      : []),
  {title: '模型', dataIndex: 'modelName', width: 150, ellipsis: true, tooltip: true, align: 'center'},
  {title: '输入tokens', dataIndex: 'promptTokens', width: 100, align: 'center'},
  {title: '输出tokens', dataIndex: 'completionTokens', width: 100, align: 'center'},
  {title: '缓存tokens', dataIndex: 'cacheTokens', width: 100, align: 'center'},
  {title: '详情', slotName: 'detail', width: 80, align: 'center', fixed: 'right'},  // 新增
]);

async function loadSummary() {
  try {
    const res = await getSiteSummary()
    siteSummary.value = res.data
  } catch (err) {
    Message.error(getErrorMessage(err, '获取全站用量失败'))
  }
}

// ── 对话记录列表（服务端分页） ──
const chatList = ref<chatRecordSchema[]>([])
const chatTotal = ref(0)
const chatPage = ref(1)
const chatPageSize = ref(5)
const chatLoading = ref(false)
const chatFilter = reactive({username: '', model: ''})

async function loadChats() {
  chatLoading.value = true
  try {
    const res = await getChatRecords({
      page: chatPage.value,
      pageSize: chatPageSize.value,
      model: chatFilter.model.trim() || undefined,
      username: chatFilter.username.trim() || undefined,
    })
    chatList.value = res.data.list
    chatTotal.value = res.data.total
  } catch (err) {
    Message.error(getErrorMessage(err, '获取对话记录失败'))
  } finally {
    chatLoading.value = false
  }
}

function searchChats() {
  chatPage.value = 1
  loadChats()
}

watch([chatPage, chatPageSize], loadChats)


const chatDetailVisible = ref(false)
const selectedChat = ref<chatRecordSchema | null>(null)

function openChatDetail(record: chatRecordSchema) {
  selectedChat.value = record
  chatDetailVisible.value = true
}

// ══════════ 标签二：调用日志 ══════════
const logList = ref<logItemSchema[]>([])
const logTotal = ref(0)
const logPage = ref(1)
const logPageSize = ref(10)
const logLoading = ref(false)
const logFilter = reactive({type: '', keyword: '', model: ''})
// 时间范围选择器返回的值可能是 Date 或格式化字符串，清空时为 undefined，两种都交给 toParam 处理
const logTimeRange = ref<[Date, Date] | [string, string] | undefined>(undefined)

const logTypeName: Record<string, string> = {api: 'API调用', login: '登录注册', admin: '管理员操作', user: '用户操作'}
const logTypeTag: Record<string, string> = {
  api: 'arcoblue', login: 'green', admin: 'orange', user: 'gray',
}

const logColumns: TableColumnData[] = [
  {title: '时间', slotName: 'time', width: 230, align: 'center'},
  {title: '类型', slotName: 'type', width: 100, align: 'center'},
  {title: '用户', dataIndex: 'username', width: 180, ellipsis: true, tooltip: true, align: 'center'},
  {title: '动作', dataIndex: 'action', width: 400, ellipsis: true, tooltip: true, align: 'center'},
  {title: '详情', dataIndex: 'detail', width: 230, ellipsis: true, tooltip: true, align: 'center'},
  {title: '模型', dataIndex: 'modelName', width: 130, ellipsis: true, tooltip: true, align: 'center'},
  {title: '渠道', dataIndex: 'channelName', width: 100, ellipsis: true, tooltip: true, align: 'center'},
  {title: '输入/输出/缓存', slotName: 'tokens', width: 200, align: 'center'},
  {title: '费用', slotName: 'cost', width: 150, align: 'center'},
  {title: '耗时', slotName: 'duration', width: 90, align: 'center'},
]

async function loadLogs() {
  logLoading.value = true
  try {
    const res = await getMonitorLogs({
      page: logPage.value,
      pageSize: logPageSize.value,
      type: logFilter.type || undefined,
      keyword: logFilter.keyword.trim() || undefined,
      model: logFilter.model.trim() || undefined,
      start: logTimeRange.value ? toParam(logTimeRange.value[0]) : undefined,
      end: logTimeRange.value ? toParam(logTimeRange.value[1]) : undefined,
    })
    logList.value = res.data.list
    logTotal.value = res.data.total
  } catch (err) {
    Message.error(getErrorMessage(err, '获取日志失败'))
  } finally {
    logLoading.value = false
  }
}

function searchLogs() {
  logPage.value = 1
  loadLogs()
}

function resetLogFilter() {
  logFilter.type = ''
  logFilter.keyword = ''
  logFilter.model = ''
  logTimeRange.value = undefined
  searchLogs()
}

watch([logPage, logPageSize], loadLogs)

// ══════════ 标签三：数据看板 ══════════
type metricField = 'calls' | 'promptTokens' | 'completionTokens' | 'cacheTokens'

const statsData = ref<userStatsSchema | null>(null)
const statsLoading = ref(false)
// 默认展示最近 7 天，按天聚合
const statsTimeRange = ref<[Date, Date] | [string, string]>([
  new Date(Date.now() - 7 * 24 * 3600 * 1000),
  new Date(),
])
const granularity = ref('day')
const selectedModels = ref<string[]>([])
const showTotal = ref(true)

const rangeShortcuts = [
  {
    label: '今天', value: (): [Date, Date] => {
      const end = new Date();
      const start = new Date(end);
      start.setHours(0, 0, 0, 0);
      return [start, end]
    }
  },
  {label: '近24小时', value: (): [Date, Date] => [new Date(Date.now() - 24 * 3600 * 1000), new Date()]},
  {label: '近7天', value: (): [Date, Date] => [new Date(Date.now() - 7 * 24 * 3600 * 1000), new Date()]},
  {label: '近30天', value: (): [Date, Date] => [new Date(Date.now() - 30 * 24 * 3600 * 1000), new Date()]},
]

const userCards = computed(() => [
  {label: '输入 tokens', value: statsData.value?.totals.promptTokens ?? 0, tone: ''},
  {label: '输出 tokens', value: statsData.value?.totals.completionTokens ?? 0, tone: 'stat-accent-cyan'},
  {label: '缓存 tokens', value: statsData.value?.totals.cacheTokens ?? 0, tone: 'stat-accent-gold'},
])

const hasStatsData = computed(() => (statsData.value?.buckets.length ?? 0) > 0)

/** x 轴：全部桶时间的有序去重列表 */
const chartTimes = computed(() => {
  const times = [...new Set((statsData.value?.buckets ?? []).map((b) => b.time))]
  return times.sort()
})

/** 出现过用量的模型列表（供曲线维度选择） */
const availableModels = computed(() => [
  ...new Set((statsData.value?.buckets ?? []).map((b) => b.modelName)),
])

/** 组装某一指标的曲线：每个选中模型一条，可选总计一条（前端按桶求和） */
function buildSeries(field: metricField): lineSeriesSchema[] {
  const buckets = statsData.value?.buckets ?? []
  const series: lineSeriesSchema[] = []
  for (const modelName of selectedModels.value) {
    const valueByTime = new Map(
        buckets.filter((b) => b.modelName === modelName).map((b) => [b.time, b[field]]),
    )
    series.push({name: modelName, data: chartTimes.value.map((t) => valueByTime.get(t) ?? 0)})
  }
  if (showTotal.value) {
    const totals = new Map<string, number>()
    for (const b of buckets) totals.set(b.time, (totals.get(b.time) ?? 0) + b[field])
    series.push({name: '总计', data: chartTimes.value.map((t) => totals.get(t) ?? 0)})
  }
  return series
}

const metricCharts = computed(() => [
  {title: '调用次数', unit: '次', series: buildSeries('calls')},
  {title: '输入 token', unit: 'token', series: buildSeries('promptTokens')},
  {title: '输出 token', unit: 'token', series: buildSeries('completionTokens')},
  {title: '缓存 token', unit: 'token', series: buildSeries('cacheTokens')},
])

async function loadStats() {
  if (!statsTimeRange.value) return
  statsLoading.value = true
  try {
    const res = await getUserStats({
      start: toParam(statsTimeRange.value[0]),
      end: toParam(statsTimeRange.value[1]),
      granularity: granularity.value,
    })
    statsData.value = res.data
  } catch (err) {
    Message.error(getErrorMessage(err, '获取用量统计失败'))
  } finally {
    statsLoading.value = false
  }
}

// 时间范围或粒度变化后自动重新查询（手动刷新按钮用于获取最新数据）
watch([statsTimeRange, granularity], loadStats)
</script>

<style scoped>
.monitor-page {
  height: 100%;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6) var(--space-6);
  max-width: 1440px;
  margin: 0 auto;
}

.monitor-head {
  text-align: center;
  margin-bottom: var(--space-2);
}

.monitor-head h1 {
  margin: 0 0 var(--space-1);
  font-size: var(--text-2xl);
  font-weight: var(--font-bold);
}

.monitor-body {
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-xl);
  padding: var(--space-4) var(--space-5);
}

.model-filter-label {
  color: var(--color-text-secondary);
  font-size: var(--text-sm);
}

/* 筛选栏内的提示行：独占一行（filter-bar 是 flex 换行容器），底距交给 filter-bar 自身 */
.filter-bar .filter-tip {
  flex-basis: 100%;
  margin-bottom: 0;
}

/* ── 对话记录展开区 ── */
.chat-detail {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-4);
}

.chat-block-title {
  font-weight: var(--font-semibold);
  color: var(--color-primary);
  margin-bottom: var(--space-1);
}

.chat-block-text {
  margin: 0;
  padding: var(--space-3);
  background: var(--color-gray-50);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  white-space: pre-wrap;
  word-break: break-word;
  max-height: 180px;
  overflow-y: auto;
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  line-height: 1.6;
}

/* ── 2×2 图表网格 ── */
.charts-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: var(--space-4);
}

.chart-cell {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  padding: var(--space-3);
  background: var(--color-white);
}

.chart-title {
  font-weight: var(--font-semibold);
  margin-bottom: var(--space-2);
}

.stats-empty {
  padding: var(--space-12) 0;
}

@media (max-width: 900px) {
  .charts-grid {
    grid-template-columns: 1fr;
  }
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}
</style>
