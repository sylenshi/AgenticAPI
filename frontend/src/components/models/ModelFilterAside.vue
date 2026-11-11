<!-- 模型广场左侧筛选侧栏：排序/搜索/分组/标签/能力，全部双向绑定到父级筛选状态；管理员顶部可添加模型
     视觉：面板标题栏 + 带序号的分组 + 组间细线 + 激活指示徽标 + 底部结果统计，与工坊侧栏共用同一套节奏。 -->
<template>
  <aside class="filter-aside" :class="{collapsed}">
    <div class="filter-aside-inner">
      <!-- 面板标题栏：桌面常驻，窄屏额外出现关闭按钮 -->
      <div class="panel-head">
        <div class="panel-head-left">
          <span class="panel-title">筛选</span>
          <span v-if="activeFilterCount" class="panel-count">{{ activeFilterCount }} 项生效</span>
        </div>
        <div class="panel-head-right">
          <button class="panel-reset" :disabled="!hasActiveFilter" @click="resetFilters">重置</button>
          <button class="panel-close" title="关闭筛选" @click="emit('close')">
            <icon-close/>
          </button>
        </div>
      </div>

      <!-- 添加模型属于管理操作，仅管理员可见（与工坊侧栏顶部主按钮同款） -->
      <div v-if="isAdmin" class="filter-add">
        <a-button type="primary" long @click="emit('add')">
          <template #icon><icon-plus/></template>
          添加模型
        </a-button>
      </div>

      <!-- 01 搜索 -->
      <div class="filter-section" :class="{active: searchCount > 0}">
        <div class="filter-head">
          <div class="filter-head-left"><span class="section-index">01</span><span class="filter-section-title">搜索</span></div>
          <span v-if="searchCount" class="section-active"><i class="section-dot"/>{{ searchCount }}</span>
        </div>
        <a-input v-model="keyword" placeholder="搜索模型名称" allow-clear>
          <template #prefix><icon-search/></template>
        </a-input>
      </div>

      <!-- 02 排序：价格按输入/输出/缓存分维度，默认排序时方向不可用 -->
      <div class="filter-section">
        <div class="filter-head">
          <div class="filter-head-left"><span class="section-index">02</span><span class="filter-section-title">排序</span></div>
        </div>
        <div class="filter-sort">
          <a-select v-model="sortField" :options="sortFieldOptions"/>
          <a-radio-group v-model="sortOrder" type="button" size="small" :disabled="sortField === 'name'">
            <a-radio value="asc">升序</a-radio>
            <a-radio value="desc">降序</a-radio>
          </a-radio-group>
        </div>
      </div>

      <!-- 03 分组 -->
      <div class="filter-section" :class="{active: groupCount > 0}">
        <div class="filter-head">
          <div class="filter-head-left"><span class="section-index">03</span><span class="filter-section-title">分组</span></div>
          <span v-if="groupCount" class="section-active"><i class="section-dot"/>{{ groupCount }}</span>
        </div>
        <a-select v-model="group" :options="groupOptions" placeholder="全部分组"/>
      </div>

      <!-- 04 标签 -->
      <div class="filter-section" :class="{active: labelCount > 0}">
        <div class="filter-head">
          <div class="filter-head-left"><span class="section-index">04</span><span class="filter-section-title">标签</span></div>
          <span v-if="labelCount" class="section-active"><i class="section-dot"/>{{ labelCount }}</span>
        </div>
        <a-select v-model="labels" multiple allow-clear :max-tag-count="3" placeholder="选择标签">
          <a-option v-for="l in labelOptions" :key="l" :value="l" :label="l"/>
        </a-select>
      </div>

      <!-- 05 能力：状态色点 + 开关，替代裸复选框 -->
      <div class="filter-section" :class="{active: abilityCount > 0}">
        <div class="filter-head">
          <div class="filter-head-left"><span class="section-index">05</span><span class="filter-section-title">能力</span></div>
          <span v-if="abilityCount" class="section-active"><i class="section-dot"/>{{ abilityCount }}</span>
        </div>
        <div class="ability-row">
          <span class="ability-label"><i class="ability-dot"/>仅视觉模型</span>
          <a-switch v-model="visionOnly" size="small"/>
        </div>
      </div>

      <!-- 底部：结果统计 + 带计数的一键清空 -->
      <div class="filter-footer">
        <span class="filter-result">{{ resultCount }} / {{ totalCount }} 个模型</span>
        <a-button long class="filter-clear-btn" :disabled="!hasActiveFilter" @click="resetFilters">
          <template #icon><icon-refresh/></template>
          清空筛选{{ activeFilterCount ? `（${activeFilterCount}）` : '' }}
        </a-button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {computed} from 'vue'
import type {modelSortField, modelSortOrder} from '@/types'

/** ═══════════ 父级传入的选项、权限与结果统计 ═══════════ */
defineProps<{
  isAdmin: boolean
  groupOptions: Array<{ value: string; label: string }>
  labelOptions: string[]
  resultCount: number
  totalCount: number
}>()

const emit = defineEmits<{ add: []; close: [] }>()

/** ═══════════ 筛选状态：全部 defineModel，父级持有并用于过滤计算 ═══════════ */
const collapsed = defineModel<boolean>('collapsed', {default: false})
const keyword = defineModel<string>('keyword', {default: ''})
const group = defineModel<string>('group', {default: 'all'})
const labels = defineModel<string[]>('labels', {default: () => []})
const visionOnly = defineModel<boolean>('visionOnly', {default: false})
const sortField = defineModel<modelSortField>('sortField', {default: 'name'})
const sortOrder = defineModel<modelSortOrder>('sortOrder', {default: 'asc'})

const sortFieldOptions = [
  {value: 'name', label: '按名称'},
  {value: 'inputPrice', label: '按输入价格'},
  {value: 'outputPrice', label: '按输出价格'},
  {value: 'cachePrice', label: '按缓存价格'},
]

// 各分组当前生效的条件数，用于分组标题右侧的激活徽标与控件描边
const searchCount = computed(() => keyword.value.trim() ? 1 : 0)
const groupCount = computed(() => group.value !== 'all' ? 1 : 0)
const labelCount = computed(() => labels.value.length)
const abilityCount = computed(() => visionOnly.value ? 1 : 0)

// 当前激活的筛选条件数（排序不计入，决定清空按钮可用与角标）
const activeFilterCount = computed(() =>
    searchCount.value + groupCount.value + labelCount.value + abilityCount.value,
)
const hasActiveFilter = computed(() => activeFilterCount.value > 0)

// 一键清空筛选（含搜索关键字），通过 defineModel 同步回父级
function resetFilters() {
  keyword.value = ''
  group.value = 'all'
  labels.value = []
  visionOnly.value = false
}
</script>

<style scoped>
/* ── 侧栏（折叠动画照抄工坊 .studio-aside 模式） ── */
.filter-aside {
  flex-shrink: 0;
  width: var(--layout-panel-aside);
  border-right: 1px solid var(--color-border);
  background: var(--color-white);
  overflow: hidden; /* 收起过程中把内容裁掉 */
  transition: width var(--transition-base);
}

.filter-aside.collapsed {
  width: 0;
  border-right: none;
}

/* 内层固定宽度：外层做宽度动画时表单不被挤压变形 */
.filter-aside-inner {
  display: flex;
  flex-direction: column;
  width: var(--layout-panel-aside);
  height: 100%;
  overflow-y: auto;
  box-sizing: border-box;
}

/* ── 面板标题栏 ── */
.panel-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-shrink: 0;
  height: 44px;
  padding: 0 var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.panel-head-left,
.panel-head-right {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.panel-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.panel-count {
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-lighter);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}

.panel-reset {
  padding: 2px 0;
  border: none;
  background: transparent;
  color: var(--color-primary);
  font-family: inherit;
  font-size: var(--text-xs);
  cursor: pointer;
}

.panel-reset:disabled {
  color: var(--color-text-disabled);
  cursor: not-allowed;
}

.panel-close {
  display: none;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border: none;
  border-radius: var(--radius-sm);
  background: transparent;
  color: var(--color-text-secondary);
  cursor: pointer;
}

.panel-close:hover {
  background: var(--color-gray-100);
}

/* ── 管理操作区 ── */
.filter-add {
  padding: var(--space-3);
  background: var(--color-bg-subtle);
  border-bottom: 1px solid var(--color-border);
}

/* ── 分组：细线分隔 + 序号 + 激活指示 ── */
.filter-section {
  padding: var(--space-3);
  border-bottom: 1px solid var(--color-border);
}

.filter-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 20px;
  margin-bottom: var(--space-2);
}

.filter-head-left {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

.section-index {
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--color-text-muted);
}

.filter-section-title {
  font-size: var(--text-xs);
  font-weight: var(--font-medium);
  color: var(--color-text);
}

.section-active {
  display: inline-flex;
  align-items: center;
  gap: 5px;
  padding: 2px 6px;
  border-radius: var(--radius-sm);
  background: var(--color-primary-lighter);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--color-primary);
  font-variant-numeric: tabular-nums;
}

.section-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-primary);
}

/* 生效分组的控件加主色描边，一眼看出是哪组在筛 */
.filter-section.active :deep(.arco-select-view-single),
.filter-section.active :deep(.arco-select-view-multiple),
.filter-section.active :deep(.arco-input-wrapper) {
  border-color: var(--color-primary);
}

.filter-section :deep(.arco-select-view-single),
.filter-section :deep(.arco-select-view-multiple) {
  width: 100%;
}

.filter-sort {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

/* 能力行：状态色点 + 开关 */
.ability-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  min-height: 28px;
}

.ability-label {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text);
}

.ability-dot {
  width: 5px;
  height: 5px;
  border-radius: 50%;
  background: var(--color-cyan);
}

/* ── 底部：结果统计 + 清空 ── */
.filter-footer {
  margin-top: auto;
  padding: var(--space-3);
  background: var(--color-bg-subtle);
  border-top: 1px solid var(--color-border);
}

.filter-result {
  display: block;
  margin-bottom: var(--space-2);
  font-family: var(--font-mono);
  font-size: var(--text-2xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

.filter-clear-btn {
  border-color: var(--color-primary);
  color: var(--color-primary);
}

/* 中屏：侧栏略收窄，给卡片网格留出至少两列的宽度 */
@media (min-width: 769px) and (max-width: 1100px) {
  .filter-aside,
  .filter-aside-inner {
    width: var(--layout-panel-aside-compact);
  }
}

/* 窄屏：筛选侧栏改覆盖式抽屉，由主内容区的「展开筛选」按钮唤出 */
@media (max-width: 768px) {
  .filter-aside {
    position: absolute;
    top: 0;
    bottom: 0;
    left: 0;
    z-index: 25;
    width: min(84vw, 300px);
    background: var(--color-white);
    border-right: 1px solid var(--color-border);
    box-shadow: var(--shadow-lg);
    transition: transform var(--transition-base);
  }

  .filter-aside.collapsed {
    width: min(84vw, 300px);
    transform: translateX(-100%);
    border-right: none;
  }

  .filter-aside-inner {
    width: 100%;
  }

  .panel-close {
    display: inline-flex;
  }
}
</style>
