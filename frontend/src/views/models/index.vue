<!-- 模型广场页面：筛选侧栏 + 卡片网格 + 详情/添加抽屉的编排层 -->
<!-- 各区块的实现拆分在 components/models/ 下：ModelFilterAside / ModelCard / ModelDetailDrawer / ModelAddDrawer -->
<!-- 改版：页头左对齐、已选筛选条件显示在主内容区、网格不再硬封顶 4 列；≤768px 筛选侧栏改抽屉。 -->

<template>
  <div class="models-page">
    <!-- 【左侧筛选侧栏】搜索 / 分组 / 标签 / 能力筛选；管理员可在顶部添加模型 -->
    <ModelFilterAside
        v-model:collapsed="filterCollapsed"
        v-model:sort-field="sortField"
        v-model:sort-order="sortOrder"
        v-model:keyword="pageInfo.currentModelName"
        v-model:group="filterState.group"
        v-model:labels="filterState.labels"
        v-model:vision-only="filterState.visionOnly"
        :is-admin="userStore.isAdmin"
        :group-options="groupOptions"
        :label-options="labelOptions"
        :result-count="filteredModelNumber"
        :total-count="totalModelNumber"
        @add="addModelDrawerVisible = true"
        @close="filterCollapsed = true"
    />

    <!-- 抽屉遮罩：仅窄屏筛选面板以覆盖层形式出现时生效 -->
    <div v-if="isNarrow && !filterCollapsed" class="models-mask" @click="filterCollapsed = true"/>

    <!-- 【右侧主内容】标题、筛选状态、卡片网格、翻页器 -->
    <div class="models-content">
      <header class="page-head models-head">
        <h1>模型广场</h1>
        <p class="page-head-desc">
          本站已启用 <span class="models-count">{{ totalModelNumber }}</span> 个模型，含
          <span class="models-count models-count-free">{{ freeModelNumber }}</span> 个免费模型
        </p>
      </header>

      <!-- 筛选状态条：结果数 + 已选条件（可逐个清除）+ 筛选面板入口 -->
      <div class="models-toolbar">
        <span class="toolbar-count">{{ filteredModelNumber }} 个结果</span>
        <div class="active-chips">
          <button v-for="chip in activeFilterChips" :key="chip.key" class="filter-chip"
                  :title="`清除「${chip.label}」`" @click="chip.clear()">
            {{ chip.label }} <span class="chip-x">×</span>
          </button>
          <span v-if="!activeFilterChips.length" class="chips-empty">未设置筛选条件</span>
        </div>
        <button class="filter-entry" :class="{active: !filterCollapsed}"
                @click="filterCollapsed = !filterCollapsed">
          {{ filterCollapsed ? '展开筛选' : '收起筛选' }}
          <span v-if="activeFilterCount" class="filter-entry-count">{{ activeFilterCount }}</span>
        </button>
      </div>

      <!-- 【页面主体】模型卡片网格 -->
      <div class="model-list">
        <ModelCard
            v-for="model in currentPageModels"
            :key="model.name"
            :model="model"
            @detail="openModelDetail"
        />
      </div>

      <!-- 【翻页器】过滤结果分页展示 -->
      <div v-if="filteredModelNumber > 0" class="models-pagination">
        <a-pagination
            :total="filteredModelNumber"
            v-model:current="pageInfo.currentPageNum"
            v-model:page-size="pageInfo.currentPageSize"
            :page-size-options="[12, 16, 20, 24]"
            show-total
            show-page-size
        />
      </div>
      <a-empty v-else class="models-empty" description="没有匹配的模型"/>


      <!-- 模型详情侧边栏：详情 / 示例 / 配置（保存与删除事件由本页面处理） -->
      <ModelDetailDrawer
          v-model:visible="configDrawerVisible"
          :model="currentModel"
          :channel-name-list="channelNameList"
          @save="handleSaveConfig"
          @delete="handleDeleteModel"
      />

      <!-- 添加模型侧边栏 -->
      <ModelAddDrawer
          v-model:visible="addModelDrawerVisible"
          :channel-name-list="channelNameList"
          @add="handleAddModel"
      />
    </div>
  </div>
</template>

<script setup lang="ts">

import {reactive, ref, computed, watch, onMounted, onBeforeUnmount} from 'vue'
import {Message} from '@arco-design/web-vue'
import {addModel, updateModel, deleteModel} from '@/api/models'
import {getErrorMessage} from '@/api/request'
import {useModelListStore} from '@/stores/modelList'
import {useChannelListStore} from '@/stores/channelList'
import {useUserStore} from '@/stores/user'
import {confirmDialog} from '@/utils/feedback'
import {splitLabel} from '@/utils/model'
import {storeToRefs} from 'pinia'
import ModelFilterAside from '@/components/models/ModelFilterAside.vue'
import ModelCard from '@/components/models/ModelCard.vue'
import ModelDetailDrawer from '@/components/models/ModelDetailDrawer.vue'
import ModelAddDrawer from '@/components/models/ModelAddDrawer.vue'
import type {modelInfoSchema, modelSortField, modelSortOrder} from '@/types'

/** ═══════════ 从pinia中获取全量的模型状态 ═══════════ */
const modelList = useModelListStore()
const {totalModelList, totalModelNumber, freeModelNumber} = storeToRefs(modelList)

/** ═══════════ 从pinia中获取全量的渠道状态 ═══════════ */
const channelList = useChannelListStore()
const {channelNameList} = storeToRefs(channelList)

/** ═══════════ 当前登录用户状态（区分管理员/普通用户） ═══════════ */
const userStore = useUserStore()

/** ═══════════ 筛选与分页状态（侧栏组件通过 v-model 双向绑定这些状态） ═══════════ */

// 当前页面的模型信息
const pageInfo = reactive({
  currentPageNum: 1,
  currentPageSize: 12,
  currentModelName: ""
})

// 侧栏折叠开关（桌面默认展开；窄屏由视口同步为收起）
const filterCollapsed = ref(false)

// 筛选状态
const filterState = reactive({
  group: 'all' as string,     // all / free / vip / 其他分组
  labels: [] as string[],     // 多选标签
  visionOnly: false,          // 仅视觉模型
})

// 当前激活的筛选条件数（含关键字搜索，决定入口角标）
const activeFilterCount = computed(() => {
  let n = 0
  if (pageInfo.currentModelName.trim()) n++
  if (filterState.group !== 'all') n++
  n += filterState.labels.length
  if (filterState.visionOnly) n++
  return n
})

// 已选筛选条件：直接显示在主内容区，点击 chip 即清除对应条件
const activeFilterChips = computed(() => {
  const chips: Array<{key: string; label: string; clear: () => void}> = []
  const kw = pageInfo.currentModelName.trim()
  if (kw) {
    chips.push({key: 'keyword', label: `名称：${kw}`, clear: () => { pageInfo.currentModelName = '' }})
  }
  if (filterState.group !== 'all') {
    chips.push({key: 'group', label: `分组：${filterState.group}`, clear: () => { filterState.group = 'all' }})
  }
  filterState.labels.forEach(label => {
    chips.push({
      key: `label-${label}`,
      label,
      clear: () => { filterState.labels = filterState.labels.filter(l => l !== label) },
    })
  })
  if (filterState.visionOnly) {
    chips.push({key: 'vision', label: '仅视觉模型', clear: () => { filterState.visionOnly = false }})
  }
  return chips
})

/** ═══════════ 视口同步：窄屏把筛选侧栏改成抽屉 ═══════════ */
const isNarrow = ref(false)
let narrowQuery: MediaQueryList | null = null
let viewportReady = false

function syncViewport() {
  const narrow = narrowQuery?.matches ?? false
  if (!viewportReady || narrow !== isNarrow.value) {
    viewportReady = true
    isNarrow.value = narrow
    filterCollapsed.value = narrow
  }
}

// 根据筛选状态过滤后的模型列表
const filteredModelList = computed(() => {
  return totalModelList.value.filter(m => {
    // ① 名称关键字
    const kw = pageInfo.currentModelName.trim().toLowerCase()
    if (kw && !m.name.toLowerCase().includes(kw)) return false
    // ② 分组
    if (filterState.group !== 'all' && m.modelGroup !== filterState.group) return false
    // ③ 标签（选中的标签至少命中一个）
    if (filterState.labels.length > 0) {
      const tags = splitLabel(m.label)
      if (!filterState.labels.some(l => tags.includes(l))) return false
    }
    // ④ 能力
    if (filterState.visionOnly && !m.supportVision) return false
    return true
  })
})

// 分组/标签下拉选项从全量数据动态聚合，不写死
const groupOptions = computed(() => {
  const groups = [...new Set(totalModelList.value.map(m => m.modelGroup))]
  return [{value: 'all', label: '全部分组'}, ...groups.map(g => ({value: g, label: g}))]
})

const labelOptions = computed(() => {
  const set = new Set<string>()
  totalModelList.value.forEach(m => splitLabel(m.label).forEach(l => set.add(l)))
  return [...set]
})

/** ═══════════ 排序相关（置顶永远第一优先级，与排序规则无关） ═══════════ */

const sortField = ref<modelSortField>('name')
const sortOrder = ref<modelSortOrder>('asc')

// 取指定维度的价格；按次计费模型没有分维度价格，统一以每次价格参与排序
function priceOf(m: modelInfoSchema, field: 'inputPrice' | 'outputPrice' | 'cachePrice'): number {
  // 如果是按次计费模型，返回每次价格
  if (m.isRequestMode) {
    return Number(m.perRequestPrice) || 0
  }
  return Number(m[field]) || 0
}

// 筛选 + 排序后的展示列表
const displayModelList = computed(() => {
  const list = [...filteredModelList.value]  // 拷贝一份再排：sort 是原地操作，直接排会污染 store 里的数据
  return list.sort((a, b) => {
    if (a.isPin !== b.isPin) return a.isPin ? -1 : 1
    const field = sortField.value
    const dir = sortOrder.value === 'asc' ? 1 : -1
    if (field === 'name') return dir * a.name.localeCompare(b.name, 'zh-CN')
    return dir * (priceOf(a, field) - priceOf(b, field))
  })
})

// 当前页的模型数量（过滤后的总数）
const filteredModelNumber = computed(() => filteredModelList.value.length)

// 当前页的模型列表（分页切片，数据源是排好序的展示列表）
const currentPageModels = computed(() => {
  const start = (pageInfo.currentPageNum - 1) * pageInfo.currentPageSize
  const end = start + pageInfo.currentPageSize
  return displayModelList.value.slice(start, end)
})

// 过滤结果变少时收拢页码，避免停留在超出范围的空页
watch(filteredModelNumber, (total) => {
  const maxPage = Math.max(1, Math.ceil(total / pageInfo.currentPageSize))
  if (pageInfo.currentPageNum > maxPage) {
    pageInfo.currentPageNum = maxPage
  }
})

// 任何筛选/搜索/排序变化时回到第一页（多数操作不改变总数，上面的 watch 不会触发）
watch([sortField, sortOrder, () => pageInfo.currentModelName,
      () => filterState.group, () => filterState.labels, () => filterState.visionOnly],
    () => {
      pageInfo.currentPageNum = 1
    })

/** ═══════════ 抽屉相关：状态在本页面，表单细节在抽屉组件内部 ═══════════ */

// 详情抽屉相关状态
const configDrawerVisible = ref(false)  // 详情抽屉是否可见
const currentModel = ref<modelInfoSchema | null>(null)  // 当前正在选中的模型是哪一个

// 添加模型弹窗相关状态
const addModelDrawerVisible = ref(false)

// 打开模型详情抽屉
const openModelDetail = (model: modelInfoSchema) => {
  currentModel.value = model
  configDrawerVisible.value = true
}

// 保存配置：详情抽屉抛出的表单快照，按模型名调更新接口
const handleSaveConfig = (form: modelInfoSchema) => {
  const modelName = currentModel.value?.name
  if (!modelName) {
    Message.error('未选择模型')
    return
  }
  updateModel(modelName, form).then(
      () => {
        configDrawerVisible.value = false
        modelList.loadTotalModels() // 刷新当前页的模型列表
        Message.success('配置保存成功')
      }
  ).catch(err => {
    console.error(err)
    Message.error(getErrorMessage(err, '配置保存失败'))
  })
}

// 添加模型：添加抽屉抛出的表单快照直接落库
const handleAddModel = (form: modelInfoSchema) => {
  addModel(form).then(
      () => {
        addModelDrawerVisible.value = false
        modelList.loadTotalModels()
        Message.success('模型添加成功')
      }
  ).catch(err => {
    console.error(err)
    Message.error(getErrorMessage(err, '模型添加失败'))
  })
}

// 删除模型（先确认再调接口）
const handleDeleteModel = async (modelName: string) => {
  if (!modelName) {
    Message.error('未选择模型')
    return
  }

  const confirmed = await confirmDialog(
      `确定要删除模型 "${modelName}" 吗？此操作不可恢复。`,
      '删除确认',
      '确定删除',
      true,
  )
  if (!confirmed) return

  try {
    await deleteModel(modelName)
    configDrawerVisible.value = false
    modelList.loadTotalModels()
    Message.success('模型删除成功')
  } catch (err) {
    console.error(err)
    Message.error(getErrorMessage(err, '模型删除失败'))
  }
}

// 页面加载时拉取渠道列表，供抽屉内渠道下拉多选使用；同时初始化视口状态
onMounted(() => {
  narrowQuery = window.matchMedia('(max-width: 768px)')
  syncViewport()
  narrowQuery.addEventListener('change', syncViewport)
  channelList.loadTotalChannels()
})

onBeforeUnmount(() => {
  narrowQuery?.removeEventListener('change', syncViewport)
})


</script>

<style scoped>
/* ── 页面骨架：左筛选侧栏 + 右内容列，各自独立滚动 ── */
.models-page {
  display: flex;
  height: 100%;
  overflow: hidden;
  position: relative;
}

/* ── 右侧主内容列（滚动与内边距） ── */
.models-content {
  flex: 1;
  min-width: 0;
  height: 100%;
  overflow-y: auto;
  padding: var(--space-5) var(--space-6) var(--space-6);
  background: var(--color-bg-layout);
}

/* ── 页面头：左对齐，与控制台其它页一致 ── */
.models-head {
  display: flex;
  flex-direction: column;
  align-items: flex-start;
  gap: var(--space-1);
  text-align: left;
  margin-bottom: var(--space-4);
}

.models-head h1 {
  margin: 0;
  font-size: var(--text-page-title);
  font-weight: var(--font-semibold);
}

.models-count {
  color: var(--color-primary);
  font-weight: var(--font-semibold);
}

.models-count-free {
  color: var(--color-success);
}

/* ── 筛选状态条 ── */
.models-toolbar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-wrap: wrap;
  padding: var(--space-2) var(--space-3);
  margin-bottom: var(--space-4);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-white);
}

.toolbar-count {
  font-family: var(--font-mono);
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  white-space: nowrap;
}

.active-chips {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-wrap: wrap;
  flex: 1;
  min-width: 0;
}

.chips-empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
}

.filter-chip {
  display: inline-flex;
  align-items: center;
  gap: 4px;
  max-width: 180px;
  padding: 2px 6px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-sm);
  background: var(--color-bg-subtle);
  color: var(--color-text-secondary);
  font-family: inherit;
  font-size: var(--text-xs);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  cursor: pointer;
}

.filter-chip:hover {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

.chip-x {
  color: var(--color-text-muted);
}

.filter-entry {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 4px 10px;
  border: 1px solid transparent;
  border-radius: var(--radius-sm);
  background: var(--color-primary-lighter);
  color: var(--color-primary);
  font-family: inherit;
  font-size: var(--text-xs);
  white-space: nowrap;
  cursor: pointer;
}

.filter-entry.active {
  border-color: var(--color-primary-light);
}

.filter-entry-count {
  min-width: 16px;
  padding: 0 4px;
  border-radius: var(--radius-full);
  background: var(--color-primary);
  color: var(--color-on-primary);
  font-family: var(--font-mono);
  font-variant-numeric: tabular-nums;
}

/* ── 卡片网格：不再写死 1076px 四列封顶，大屏自然增列、窄屏自然降列 ── */
.model-list {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(240px, 1fr));
  gap: var(--space-3);
  max-width: 1440px;
  margin-left: auto;
  margin-right: auto;
}

/* ── 翻页器 ── */
.models-pagination {
  display: flex;
  justify-content: center;
  margin-top: var(--space-5);
}

.models-empty {
  padding: var(--space-12) 0;
}

.models-mask {
  position: absolute;
  inset: 0;
  z-index: 20;
  background: var(--color-black);
  opacity: 0.32;
}

@media (max-width: 768px) {
  .models-content {
    padding: var(--space-4);
  }

  .models-head h1 {
    font-size: var(--text-lg);
  }

  .model-list {
    grid-template-columns: minmax(0, 1fr);
  }

  .filter-entry {
    margin-left: auto;
  }
}
</style>
