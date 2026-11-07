<!-- 上游 TokenPlan 用量监控 -->

<template>
  <div class="operations-page">
    <!-- 页面标题与操作 -->
    <header class="page-head">
      <h2>上游 <span class="highlight">TokenPlan</span> 用量监控</h2>
      <div class="action-bar">
        <a-button :loading="loading" @click="refreshAllUsage">
          <template #icon><icon-refresh/></template>
          全部刷新
        </a-button>
        <a-button @click="settingsVisible = true">
          <template #icon><icon-settings/></template>
          设置凭证
        </a-button>
      </div>
    </header>

    <!-- 数据展示区域：每张卡一条品牌色左脊线区分渠道（与统计卡同一设计语言） -->
    <div class="data-sections">
      <!-- 火山方舟 Agent Plan -->
      <div class="plan-card plan-card-vol">
        <div class="plan-card-head">
          <div class="plan-card-title">
            <span>火山方舟 Agent Plan</span>
            <a-tag size="small" color="arcoblue">Small订阅 × 2</a-tag>
          </div>
          <a-button type="text" size="small" @click="refreshVolUsage">
            <template #icon><icon-sync/></template>
            刷新
          </a-button>
        </div>
        <a class="plan-link" href="https://www.volcengine.com/activity/agentplan" target="_blank">
          官方订阅链接<icon-launch/>
        </a>
        <div v-if="volUsage.status !== 'ok'" class="error-text">{{ volUsage.status }}</div>
        <template v-else>
          <plan-usage :usage="volUsage"/>
        </template>
      </div>

      <!-- 阶跃星辰 Step Plan -->
      <div class="plan-card plan-card-step">
        <div class="plan-card-head">
          <div class="plan-card-title">
            <span>阶跃星辰 Step Plan</span>
            <a-tag size="small" color="purple">Mini订阅</a-tag>
          </div>
          <a-button type="text" size="small" @click="refreshStepUsage">
            <template #icon><icon-sync/></template>
            刷新
          </a-button>
        </div>
        <a class="plan-link" href="https://platform.stepfun.com/step-plan" target="_blank">
          官方订阅链接<icon-launch/>
        </a>
        <div v-if="stepUsage.status !== 'ok'" class="error-text">{{ stepUsage.status }}</div>
        <template v-else>
          <plan-usage :usage="stepUsage"/>
        </template>
      </div>

      <!-- 智谱 Coding Plan（v2 套餐，上游仅返回百分比） -->
      <div class="plan-card plan-card-zai2">
        <div class="plan-card-head">
          <div class="plan-card-title">
            <span>智谱Coding Plan</span>
            <a-tag size="small" color="blue">v2 Lite</a-tag>
          </div>
          <a-button type="text" size="small" @click="refreshZai2Usage">
            <template #icon><icon-sync/></template>
            刷新
          </a-button>
        </div>
        <a class="plan-link" href="https://open.bigmodel.cn" target="_blank">
          官方订阅链接<icon-launch/>
        </a>
        <div v-if="zai2Usage.status !== 'ok'" class="error-text">{{ zai2Usage.status }}</div>
        <template v-else>
          <plan-usage :usage="zai2Usage"/>
        </template>
      </div>

      <!-- Antigravity（Google Gemini PRO）：限额来自本机 Antigravity-Manager 容器的管理 API，
           取 Gemini 模型组的 5 小时 + 周度窗口，与其他卡同一展示语言 -->
      <div class="plan-card plan-card-ag">
        <div class="plan-card-head">
          <div class="plan-card-title">
            <span>Antigravity</span>
            <a-tag size="small" color="green">Gemini PRO</a-tag>
          </div>
          <a-button type="text" size="small" :loading="agLoading" @click="refreshAgUsage">
            <template #icon><icon-sync/></template>
            刷新
          </a-button>
        </div>
        <a class="plan-link" href="https://antigravity.google" target="_blank">
          官方订阅链接<icon-launch/>
        </a>
        <div v-if="agUsage.status !== 'ok'" class="error-text">{{ agUsage.status }}</div>
        <template v-else>
          <plan-usage :usage="agUsage"/>
        </template>
      </div>

      <!-- 占位空卡已移除：新增上游渠道时直接追加 plan-card 即可 -->

    </div>

    <!-- 设置凭证抽屉（替代原自绘侧边栏） -->
    <a-drawer v-model:visible="settingsVisible" title="设置凭证" :width="440" unmount-on-close>
      <a-form :model="settings" layout="vertical">
        <!-- 火山方舟 -->
        <div class="settings-section">
          <h4>火山方舟 BohrClaw</h4>
          <a-form-item label="brmToken">
            <a-input-password v-model="settings.brmToken" placeholder="粘贴 brmToken（JWT）" @change="saveSettings"/>
          </a-form-item>
          <a-form-item label="实例 ID">
            <a-input v-model="settings.instanceId" placeholder="粘贴 ArkClaw Seat 实例 ID（如 ci-xxx）" @change="saveSettings"/>
          </a-form-item>
        </div>

        <a-divider/>

        <!-- 阶跃星辰 -->
        <div class="settings-section">
          <h4>阶跃星辰 Step Plan</h4>
          <a-form-item label="Oasis-Token">
            <a-input-password v-model="settings.stepToken" placeholder="浏览器 Cookie 里的 Oasis-Token 值" @change="saveSettings"/>
          </a-form-item>
          <a-form-item label="Oasis-Webid">
            <a-input v-model="settings.stepWebid" placeholder="可不填" @change="saveSettings"/>
          </a-form-item>
        </div>

        <a-divider/>

        <!-- 智谱 -->
        <div class="settings-section">
          <h4>智谱 Coding Plan</h4>
          <a-form-item label="API Key">
            <a-input-password v-model="settings.zaiApiKey" placeholder="粘贴 v2 套餐 API Key（换号后上传即生效，优先于 .env 兜底）" @change="saveSettings"/>
          </a-form-item>
        </div>
      </a-form>

      <template #footer>
        <div class="drawer-footer">
          <a-button @click="settingsVisible = false">关闭</a-button>
          <a-button type="primary" @click="uploadSettings">保存到服务器</a-button>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import {ref, reactive, onMounted, defineComponent, h} from 'vue'
import {Message} from '@arco-design/web-vue'
import {Progress} from '@arco-design/web-vue'
import {getOperations, uploadOperations} from '@/api/operations'
import {getErrorMessage} from '@/api/request'
import {cssVar} from '@/utils/colors'
import type {
  cookieSettings,
  volUsageData,
  stepfunUsageData,
  zai2UsageData,
  antigravityUsageData
} from '@/types'

/* ═══════════════════════ 用量卡片公共部分（5小时/周/月进度条） ═══════════════════════ */

interface planWindow {
  used: number
  quota: number
  resetAt?: string | null
}

/** 单个时间窗的用量进度条：统一按百分比展示（保留 1 位小数），无限额时显示提示文字 */
const planWindowRow = defineComponent({
  props: {
    label: {type: String, required: true},
    window: {type: Object as () => planWindow, required: true},
  },
  setup(props) {
    return () => {
      if (!props.window.quota) {
        return h('div', {class: 'plan-row plan-row-none'}, `无${props.label}限额`)
      }
      // v2 套餐后端给 百分比/100，其余给绝对值，used/quota 比值公式对两者通用
      const percentText = ((props.window.used / props.window.quota) * 100).toFixed(1)
      const percent = Math.min(1, (props.window.used / props.window.quota) * 1)
      return h('div', {class: 'plan-row'}, [
        h('div', {class: 'plan-row-head'}, [
          // 左侧：窗口标签 + 重置时间（上游给了才显示）；右侧：用量百分比统一对齐
          h('div', {class: 'plan-row-meta'}, [
            h('span', {class: 'plan-row-label'}, props.label),
            ...(props.window.resetAt
                ? [h('span', {class: 'plan-row-reset'}, `${props.window.resetAt} 重置`)]
                : []),
          ]),
          h('span', {class: 'plan-row-value'}, `已用 ${percentText}%`),
        ]),
        h(Progress, {
          size: 'small' as const,
          showText: false,
          percent,
          // 用量超过 80% 转橙色、95% 转红色预警（Progress 的 color 直接写到 SVG stroke 属性，
          // 不接受 var()，所以经 cssVar() 取设计令牌的实值）
          color: percent >= 0.95 ? cssVar('--color-error') : percent >= 0.8 ? cssVar('--color-warning') : undefined,
        }),
      ])
    }
  },
})

/** 一个订阅计划的用量展示（三行进度条） */
const planUsage = defineComponent({
  props: {
    usage: {type: Object as () => {fiveHour: planWindow; weekly: planWindow; monthly: planWindow}, required: true},
  },
  setup(props) {
    return () => h('div', {class: 'plan-rows'}, [
      h(planWindowRow, {label: '5小时', window: props.usage.fiveHour}),
      h(planWindowRow, {label: '周度', window: props.usage.weekly}),
      h(planWindowRow, {label: '月度', window: props.usage.monthly}),
    ])
  },
})

/* ═══════════════════════ 状态 ═══════════════════════ */

const LS_SETTINGS = 'tokenplan_settings'
const settingsVisible = ref(false) // 凭证设置抽屉
const loading = ref(false) // 是否正在加载数据
const settings = ref<cookieSettings>({
  brmToken: '',
  instanceId: '',
  stepToken: '',
  stepWebid: '',
  zaiApiKey: '',
})

/* ═══════════════════════ 下面存储用量数据 ═══════════════════════ */
const volUsage = reactive<volUsageData>({
  status: "请刷新用量",
  fiveHour: {
    used: 0,
    quota: 0,
  },
  weekly: {
    used: 0,
    quota: 0,
  },
  monthly: {
    used: 0,
    quota: 0,
  },
})
const stepUsage = reactive<stepfunUsageData>({
  status: "请刷新用量",
  fiveHour: {
    used: 0,
    quota: 0,
  },
  weekly: {
    used: 0,
    quota: 0,
  },
  monthly: {
    used: 0,
    quota: 0,
  },
})
const zai2Usage = reactive<zai2UsageData>({
  status: "请刷新用量",
  fiveHour: {
    used: 0,
    quota: 0,
  },
  weekly: {
    used: 0,
    quota: 0,
  },
  monthly: {
    used: 0,
    quota: 0,
  },
})
const agUsage = reactive<antigravityUsageData>({
  status: "请刷新用量",
  fiveHour: {
    used: 0,
    quota: 0,
  },
  weekly: {
    used: 0,
    quota: 0,
  },
  monthly: {
    used: 0,
    quota: 0,
  },
})
const agLoading = ref(false) // Antigravity 实时拉取中（经 VPN 现查 Google，约 15s）

/* ═══════════════════════ 初始化 ═══════════════════════ */

// 从 localStorage 加载设置
const loadSettings = () => {
  try {
    const raw = localStorage.getItem(LS_SETTINGS)
    if (raw) {
      const parsed = JSON.parse(raw)
      settings.value = {...settings.value, ...parsed}
    }
  } catch {
    // ignore
  }
}


/* ═══════════════════════ 设置面板 ═══════════════════════ */

// 输入过程中静默写入 localStorage，避免逐字符弹 Toast；提示统一在"保存到服务器"后给出
const saveSettings = () => {
  localStorage.setItem(LS_SETTINGS, JSON.stringify(settings.value))
}

// 将更新后的设置上传到后端
const uploadSettings = () => {
  uploadOperations({
    brmToken: settings.value.brmToken,
    instanceId: settings.value.instanceId,
    stepToken: settings.value.stepToken,
    stepWebid: settings.value.stepWebid,
    zaiApiKey: settings.value.zaiApiKey,
  }).then(() => {
    Message.success('设置已上传')
  }).catch(err => {
    console.error(err)
    Message.error(getErrorMessage(err, '设置上传失败'))
  })
}


/* ═══════════════════════ 刷新数据 ═══════════════════════ */

const refreshVolUsage = () => {
  getOperations('vol').then(res => {
    if (res.data.status.vol === "200") {
      volUsage.status = "ok"
      volUsage.fiveHour.used = res.data.vol_usage.volFiveHourUsed
      volUsage.weekly.used = res.data.vol_usage.volWeeklyUsed
      volUsage.monthly.used = res.data.vol_usage.volMonthlyUsed
      volUsage.fiveHour.quota = res.data.vol_usage.volFiveHourTotal
      volUsage.weekly.quota = res.data.vol_usage.volWeeklyTotal
      volUsage.monthly.quota = res.data.vol_usage.volMonthlyTotal
      volUsage.fiveHour.resetAt = res.data.vol_usage.volFiveHourResetAt ?? null
      volUsage.weekly.resetAt = res.data.vol_usage.volWeeklyResetAt ?? null
      volUsage.monthly.resetAt = res.data.vol_usage.volMonthlyResetAt ?? null
    } else {
      volUsage.status = "数据刷新错误: " + res.data.status.vol
    }
  }).catch(err => {
    console.error(err)
    volUsage.status = getErrorMessage(err, '数据刷新失败')
  })
}

const refreshStepUsage = () => {
  getOperations('stepfun').then(res => {
    if (res.data.status.stepfun === "200") {
      stepUsage.status = "ok"
      stepUsage.fiveHour.used = res.data.stepfun_usage.stepfunFiveHourUsed
      stepUsage.weekly.used = res.data.stepfun_usage.stepfunWeeklyUsed
      stepUsage.monthly.used = res.data.stepfun_usage.stepfunMonthlyUsed
      stepUsage.fiveHour.quota = res.data.stepfun_usage.stepfunFiveHourTotal
      stepUsage.weekly.quota = res.data.stepfun_usage.stepfunWeeklyTotal
      stepUsage.monthly.quota = res.data.stepfun_usage.stepfunMonthlyTotal
      stepUsage.fiveHour.resetAt = res.data.stepfun_usage.stepfunFiveHourResetAt ?? null
      stepUsage.weekly.resetAt = res.data.stepfun_usage.stepfunWeeklyResetAt ?? null
      stepUsage.monthly.resetAt = res.data.stepfun_usage.stepfunMonthlyResetAt ?? null
    } else {
      stepUsage.status = "数据刷新错误: " + res.data.status.stepfun
    }
  }).catch(err => {
    console.error(err)
    stepUsage.status = getErrorMessage(err, '数据刷新失败')
  })
}

const refreshZai2Usage = () => {
  getOperations('zai2').then(res => {
    if (res.data.status.zai2 === "200") {
      zai2Usage.status = "ok"
      zai2Usage.fiveHour.used = res.data.zai2_usage.zaiFiveHourUsed
      zai2Usage.weekly.used = res.data.zai2_usage.zaiWeeklyUsed
      zai2Usage.monthly.used = res.data.zai2_usage.zaiMonthlyUsed
      zai2Usage.fiveHour.quota = res.data.zai2_usage.zaiFiveHourTotal
      zai2Usage.weekly.quota = res.data.zai2_usage.zaiWeeklyTotal
      zai2Usage.monthly.quota = res.data.zai2_usage.zaiMonthlyTotal
      zai2Usage.fiveHour.resetAt = res.data.zai2_usage.zaiFiveHourResetAt ?? null
      zai2Usage.weekly.resetAt = res.data.zai2_usage.zaiWeeklyResetAt ?? null
      zai2Usage.monthly.resetAt = res.data.zai2_usage.zaiMonthlyResetAt ?? null
    } else {
      zai2Usage.status = "数据刷新错误: " + res.data.status.zai2
    }
  }).catch(err => {
    console.error(err)
    zai2Usage.status = getErrorMessage(err, '数据刷新失败')
  })
}

// 把后端返回的 Antigravity 用量写入卡片状态（单卡刷新与全部刷新共用）
const applyAgUsage = (u: any) => {
  agUsage.status = "ok"
  agUsage.fiveHour.used = u.agFiveHourUsed ?? 0
  agUsage.fiveHour.quota = u.agFiveHourTotal ?? 0
  agUsage.fiveHour.resetAt = u.agFiveHourResetAt ?? null
  agUsage.weekly.used = u.agWeeklyUsed ?? 0
  agUsage.weekly.quota = u.agWeeklyTotal ?? 0
  agUsage.weekly.resetAt = u.agWeeklyResetAt ?? null
  agUsage.monthly.used = u.agMonthlyUsed ?? 0
  agUsage.monthly.quota = u.agMonthlyTotal ?? 0
  agUsage.monthly.resetAt = u.agMonthlyResetAt ?? null
}

const refreshAgUsage = () => {
  agLoading.value = true
  getOperations('antigravity').then(res => {
    if (res.data.status.antigravity === "200") {
      applyAgUsage(res.data.antigravity_usage)
    } else {
      // 卡片已有数据时静默失败（实时拉取失败会回落缓存，不打断展示），否则显示错误
      if (agUsage.status !== 'ok') {
        agUsage.status = "数据刷新错误: " + res.data.status.antigravity
      }
    }
  }).catch(err => {
    console.error(err)
    if (agUsage.status !== 'ok') {
      agUsage.status = getErrorMessage(err, '数据刷新失败')
    }
  }).finally(() => {
    agLoading.value = false
  })
}

const refreshAllUsage = () => {
  loading.value = true
  getOperations('all').then(res => {
    // vol
    if (res.data.status.vol === "200") {
      volUsage.status = "ok"
      volUsage.fiveHour.used = res.data.vol_usage.volFiveHourUsed
      volUsage.weekly.used = res.data.vol_usage.volWeeklyUsed
      volUsage.monthly.used = res.data.vol_usage.volMonthlyUsed
      volUsage.fiveHour.quota = res.data.vol_usage.volFiveHourTotal
      volUsage.weekly.quota = res.data.vol_usage.volWeeklyTotal
      volUsage.monthly.quota = res.data.vol_usage.volMonthlyTotal
      volUsage.fiveHour.resetAt = res.data.vol_usage.volFiveHourResetAt ?? null
      volUsage.weekly.resetAt = res.data.vol_usage.volWeeklyResetAt ?? null
      volUsage.monthly.resetAt = res.data.vol_usage.volMonthlyResetAt ?? null
    } else {
      volUsage.status = "数据刷新错误: " + res.data.status.vol
    }
    // stepfun
    if (res.data.status.stepfun === "200") {
      stepUsage.status = "ok"
      stepUsage.fiveHour.used = res.data.stepfun_usage.stepfunFiveHourUsed
      stepUsage.weekly.used = res.data.stepfun_usage.stepfunWeeklyUsed
      stepUsage.monthly.used = res.data.stepfun_usage.stepfunMonthlyUsed
      stepUsage.fiveHour.quota = res.data.stepfun_usage.stepfunFiveHourTotal
      stepUsage.weekly.quota = res.data.stepfun_usage.stepfunWeeklyTotal
      stepUsage.monthly.quota = res.data.stepfun_usage.stepfunMonthlyTotal
      stepUsage.fiveHour.resetAt = res.data.stepfun_usage.stepfunFiveHourResetAt ?? null
      stepUsage.weekly.resetAt = res.data.stepfun_usage.stepfunWeeklyResetAt ?? null
      stepUsage.monthly.resetAt = res.data.stepfun_usage.stepfunMonthlyResetAt ?? null
    } else {
      stepUsage.status = "数据刷新错误: " + res.data.status.stepfun
    }
    // zai2
    if (res.data.status.zai2 === "200") {
      zai2Usage.status = "ok"
      zai2Usage.fiveHour.used = res.data.zai2_usage.zaiFiveHourUsed
      zai2Usage.weekly.used = res.data.zai2_usage.zaiWeeklyUsed
      zai2Usage.monthly.used = res.data.zai2_usage.zaiMonthlyUsed
      zai2Usage.fiveHour.quota = res.data.zai2_usage.zaiFiveHourTotal
      zai2Usage.weekly.quota = res.data.zai2_usage.zaiWeeklyTotal
      zai2Usage.monthly.quota = res.data.zai2_usage.zaiMonthlyTotal
      zai2Usage.fiveHour.resetAt = res.data.zai2_usage.zaiFiveHourResetAt ?? null
      zai2Usage.weekly.resetAt = res.data.zai2_usage.zaiWeeklyResetAt ?? null
      zai2Usage.monthly.resetAt = res.data.zai2_usage.zaiMonthlyResetAt ?? null
    } else {
      zai2Usage.status = "数据刷新错误: " + res.data.status.zai2
    }
    // antigravity
    if (res.data.status.antigravity === "200") {
      applyAgUsage(res.data.antigravity_usage)
    } else {
      agUsage.status = "数据刷新错误: " + res.data.status.antigravity
    }
  }).catch(err => {
    console.error(err)
    Message.error(getErrorMessage(err, '数据刷新失败'))
  }).finally(() => {
    loading.value = false
  })
}

// 页面刚加载的时候刷新全部数据；Antigravity 缓存秒回后再后台补一次实时拉取（约 15s）
onMounted(() => {
  refreshAllUsage()
  loadSettings()
  refreshAgUsage()
})

</script>

<style scoped>
.operations-page {
  padding: var(--space-5) var(--space-6);
}

.highlight {
  color: var(--color-primary);
}

.action-bar {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  margin-top: var(--space-3);
}

/* 订阅计划卡片 */
.data-sections {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: var(--space-4);
}

@media (max-width: 1024px) {
  .data-sections {
    grid-template-columns: repeat(2, 1fr);
  }
}

@media (max-width: 640px) {
  .data-sections {
    grid-template-columns: 1fr;
  }
}

.plan-card {
  min-height: 160px;
  background-color: var(--color-white);
  border: 1px solid var(--color-border);
  /* 渠道身份脊线：与统计卡同一设计语言，每张卡通过修饰类指定强调色 */
  border-left: 3px solid var(--plan-accent, var(--color-primary));
  border-radius: var(--radius-xl);
  padding: var(--space-4) var(--space-5);
  transition: box-shadow var(--transition-fast);
}

.plan-card:hover {
  box-shadow: var(--shadow-md);
}

/* 各渠道强调色：火山主蓝 / 阶跃紫 / 智谱 v2 金 / Antigravity 绿 */
.plan-card-vol { --plan-accent: var(--color-primary); }
.plan-card-step { --plan-accent: var(--color-violet); }
.plan-card-zai2 { --plan-accent: var(--color-gold); }
.plan-card-ag { --plan-accent: var(--color-success); }

/* 占位空卡：四周虚线示意预留位，左侧品牌色脊线与其他卡保持一致（实线） */
.plan-card--empty {
  border-style: dashed;
  border-left-style: solid;
  display: flex;
  align-items: center;
  justify-content: center;
}

.plan-empty-hint {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

.plan-card-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.plan-card-title {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
}

.plan-link {
  display: inline-flex;
  align-items: center;
  gap: 2px;
  font-size: var(--text-xs);
  color: var(--color-primary);
  text-decoration: none;
  margin: var(--space-1) 0 var(--space-2);
}

.plan-link:hover {
  text-decoration: underline;
}

/* 用量行（进度条），由渲染函数生成 */
:deep(.plan-rows) {
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  margin-top: var(--space-2);
}

:deep(.plan-row-head) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: var(--space-1);
}

:deep(.plan-row-meta) {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
}

:deep(.plan-row-reset) {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  font-variant-numeric: tabular-nums;
}

:deep(.plan-row-label) {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

:deep(.plan-row-value) {
  font-size: var(--text-xs);
  color: var(--color-text);
  font-variant-numeric: tabular-nums;
}

:deep(.plan-row-none) {
  font-size: var(--text-sm);
  color: var(--color-text-muted);
}

/* 凭证设置抽屉 */
.settings-section h4 {
  margin: 0 0 var(--space-3);
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text-secondary);
}

.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.error-text {
  font-size: var(--text-sm);
  /* status 初始值"请刷新用量"并非错误，用中性色避免整页红字 */
  color: var(--color-text-secondary);
  padding: var(--space-4) 0;
}
</style>
