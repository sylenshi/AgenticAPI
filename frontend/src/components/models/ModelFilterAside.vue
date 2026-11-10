<!-- 模型广场左侧筛选侧栏：排序/搜索/分组/标签/能力筛选，全部双向绑定到父级筛选状态；管理员顶部可添加模型 -->

<template>
  <aside class="filter-aside" :class="{collapsed}">
    <div class="filter-aside-inner">
      <!-- 添加模型属于管理操作，仅管理员可见（与工坊侧栏顶部主按钮同款） -->
      <div v-if="isAdmin" class="filter-add">
        <a-button type="primary" long @click="emit('add')">
          <template #icon>
            <icon-plus/>
          </template>
          添加模型
        </a-button>
      </div>

      <!-- 排序：价格按输入/输出/缓存分维度，默认排序时方向不可用 -->
      <div class="filter-section">
        <div class="filter-section-title">排序</div>
        <div class="filter-sort">
          <a-select v-model="sortField" :options="sortFieldOptions"/>
          <a-radio-group v-model="sortOrder" type="button" size="small" :disabled="sortField === 'name'">
            <a-radio value="asc">升序</a-radio>
            <a-radio value="desc">降序</a-radio>
          </a-radio-group>
        </div>
      </div>

      <!-- 搜索 -->
      <div class="filter-section">
        <div class="filter-section-title">搜索</div>
        <a-input-search
            v-model="keyword"
            placeholder="搜索模型名称"
            allow-clear
            search-button
        />
      </div>

      <!-- 分组 -->
      <div class="filter-section">
        <div class="filter-section-title">分组</div>
        <a-select v-model="group" :options="groupOptions" placeholder="全部分组"/>
      </div>

      <!-- 标签 -->
      <div class="filter-section">
        <div class="filter-section-title">标签</div>
        <a-select
            v-model="labels"
            multiple
            allow-clear
            :max-tag-count="3"
            placeholder="选择标签"
        >
          <a-option v-for="l in labelOptions" :key="l" :value="l" :label="l"/>
        </a-select>
      </div>

      <!-- 能力 -->
      <div class="filter-section">
        <div class="filter-section-title">能力</div>
        <a-checkbox v-model="visionOnly">仅视觉模型</a-checkbox>
      </div>

      <!-- 底部：一键清空 -->
      <div class="filter-footer">
        <a-button long :disabled="!hasActiveFilter" @click="resetFilters">
          <template #icon>
            <icon-refresh/>
          </template>
          清空筛选{{ activeFilterCount ? `（${activeFilterCount}）` : '' }}
        </a-button>
      </div>
    </div>
  </aside>
</template>

<script setup lang="ts">
import {computed} from 'vue'
import type {modelSortField, modelSortOrder} from '@/types'

/** ═══════════ 父级传入的选项与权限 ═══════════ */
const props = defineProps<{
  isAdmin: boolean
  groupOptions: Array<{ value: string; label: string }>
  labelOptions: string[]
}>()

const emit = defineEmits<{ add: [] }>()

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

// 当前激活的筛选条件数（含关键字搜索，决定清空按钮可用与角标）
const activeFilterCount = computed(() => {
  let n = 0
  if (keyword.value.trim()) n++
  if (group.value !== 'all') n++
  n += labels.value.length
  if (visionOnly.value) n++
  return n
})
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
  width: 210px;
  border-right: 1px solid var(--color-border);
  overflow: hidden; /* 收起过程中把内容裁掉 */
  transition: width 0.25s ease;
}

.filter-aside.collapsed {
  width: 0;
  border-right: none;
}

/* 内层固定宽度：外层做宽度动画时表单不被挤压变形 */
.filter-aside-inner {
  display: flex;
  flex-direction: column;
  gap: var(--space-4);
  width: 210px;
  height: 100%;
  overflow-y: auto;
  padding: var(--space-4);
  box-sizing: border-box;
}

.filter-section-title {
  margin-bottom: var(--space-2);
  font-size: var(--text-xs);
  font-weight: var(--font-semibold);
  color: var(--color-text-muted);
}

.filter-footer {
  margin-top: auto; /* 无滚动时贴底 */
}

/* 侧栏内排序区：字段 + 方向纵向排列，下拉撑满侧栏宽 */
.filter-sort {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
}

.filter-section :deep(.arco-select-view-single),
.filter-section :deep(.arco-select-view-multiple) {
  width: 100%;
}

/* 中屏：侧栏略收窄，给卡片网格留出至少两列的宽度 */
@media (min-width: 769px) and (max-width: 1100px) {
  .filter-aside,
  .filter-aside-inner {
    width: 190px;
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
}
</style>
