<!-- 站点设置（仅管理员）：监控记录阈值 / 维护 Agent 默认模型 / 注册与访客初始余额 -->

<template>
  <div class="settings-page">
    <header class="page-head">
      <h2>设置</h2>
      <p class="page-head-desc">
        站点运行配置，保存后立即生效：阈值与 Agent 模型对后续请求/新会话生效，初始金额只影响之后新注册的账号
      </p>
    </header>

    <div class="settings-content">
      <!-- 监控配置 -->
      <div class="page-card settings-card">
        <h3 class="settings-card-title">监控配置</h3>
        <div class="settings-row">
          <span class="settings-label">对话记录阈值</span>
          <a-input-number
              v-model="form.chatRecordMaxTokens" :min="100" :max="1000000" :step="500"
              mode="button" :style="{width: '160px'}"
          />
          <span class="settings-tip">输入+输出 token 合计不超过该值的调用才记录对话内容（对所有开启日志的模型生效）</span>
        </div>
      </div>

      <!-- 维护 Agent 配置 -->
      <div class="page-card settings-card">
        <h3 class="settings-card-title">维护 Agent</h3>
        <div class="settings-row">
          <span class="settings-label">默认模型</span>
          <a-select
              v-model="form.agentDefaultModel" :options="modelOptions"
              placeholder="未指定（跟随默认解析链）" allow-clear allow-search
              :style="{width: '300px'}"
          />
        </div>
        <p class="settings-tip settings-tip-block">
          新会话的默认驱动模型，会话中途仍可随时切换；未指定时按
          <template v-if="effectiveModel">.env → 站内首个启用模型解析，当前实际生效：<b>{{ effectiveModel }}</b></template>
          <template v-else>.env → 站内首个启用模型解析</template>
        </p>
      </div>

      <!-- 用户注册配置 -->
      <div class="page-card settings-card">
        <h3 class="settings-card-title">用户注册</h3>
        <div class="settings-row">
          <span class="settings-label">正式注册初始余额</span>
          <a-input-number
              v-model="form.registerInitialBalance" :min="0" :max="100000" :precision="2" :step="1"
              mode="button" :style="{width: '160px'}"
          />
        </div>
        <div class="settings-row">
          <span class="settings-label">正式注册用户分组</span>
          <a-select v-model="form.registerUserGroup" :style="{width: '160px'}">
            <a-option value="vip">vip（可调用全部分组模型）</a-option>
            <a-option value="free">free（仅免费分组模型）</a-option>
          </a-select>
          <span class="settings-tip">新注册账号的默认模型分组；访客固定为 free 不受此项影响</span>
        </div>
        <div class="settings-row">
          <span class="settings-label">访客初始余额</span>
          <a-input-number
              v-model="form.guestInitialBalance" :min="0" :max="100000" :precision="2" :step="1"
              mode="button" :style="{width: '160px'}"
          />
          <span class="settings-tip">访客账号可被批量创建，金额过大有被刷风险，建议保持 0 或小额</span>
        </div>
        <p class="settings-tip settings-tip-block">仅对此后新创建的账号生效，存量用户余额与分组不变</p>
      </div>

      <div class="settings-footer">
        <a-button type="primary" :loading="saving" :disabled="!hasChanges" @click="save">保存设置</a-button>
        <span v-if="!hasChanges" class="settings-tip">暂无未保存的修改</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, reactive, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import {getModels} from '@/api/models'
import {getErrorMessage} from '@/api/request'
import {getSiteSettings, updateSiteSettings} from '@/api/settings'

const loading = ref(false)
const saving = ref(false)
// Agent 按解析链实际生效的模型（只读展示；configured 为空时它就是兜底结果）
const effectiveModel = ref('')

// 表单与初始快照（保存时对比快照，只提交变化的字段）
const form = reactive({
  chatRecordMaxTokens: 5000,
  agentDefaultModel: '',
  registerInitialBalance: 0,
  guestInitialBalance: 0,
  registerUserGroup: 'vip',
})
let snapshot = {...form}

const hasChanges = computed(() =>
    form.chatRecordMaxTokens !== snapshot.chatRecordMaxTokens
    || (form.agentDefaultModel ?? '') !== snapshot.agentDefaultModel
    || form.registerInitialBalance !== snapshot.registerInitialBalance
    || form.guestInitialBalance !== snapshot.guestInitialBalance
    || form.registerUserGroup !== snapshot.registerUserGroup,
)

// 默认模型下拉：站内启用模型（管理员视角全量列表，按名称排序）
// 展示模型名（name）——label 字段存的是供应商名，不适合在这里当选项文本
const modelOptions = ref<{ label: string; value: string }[]>([])

async function loadModels() {
  try {
    const res = await getModels()
    modelOptions.value = res.data
        .filter(m => m.status)
        .map(m => ({label: m.name, value: m.name}))
        .sort((a, b) => a.label.localeCompare(b.label))
  } catch {
    // 模型列表加载失败不阻塞设置页（下拉为空仍可保存其他配置项）
  }
}

async function loadSettings() {
  loading.value = true
  try {
    const res = await getSiteSettings()
    form.chatRecordMaxTokens = res.data.chatRecordMaxTokens
    form.agentDefaultModel = res.data.agentDefaultModel
    form.registerInitialBalance = res.data.registerInitialBalance
    form.guestInitialBalance = res.data.guestInitialBalance
    form.registerUserGroup = res.data.registerUserGroup === 'free' ? 'free' : 'vip'
    effectiveModel.value = res.data.agentEffectiveModel
    snapshot = {...form}
  } catch (err) {
    Message.error(getErrorMessage(err, '获取设置失败'))
  } finally {
    loading.value = false
  }
}

async function save() {
  saving.value = true
  try {
    // 只提交变化字段（allow-clear 后是 undefined，转为空串 = 清除指定恢复默认链）
    const payload: Record<string, string | number> = {}
    if (form.chatRecordMaxTokens !== snapshot.chatRecordMaxTokens) payload.chatRecordMaxTokens = form.chatRecordMaxTokens
    if ((form.agentDefaultModel ?? '') !== snapshot.agentDefaultModel) payload.agentDefaultModel = form.agentDefaultModel ?? ''
    if (form.registerInitialBalance !== snapshot.registerInitialBalance) payload.registerInitialBalance = form.registerInitialBalance
    if (form.guestInitialBalance !== snapshot.guestInitialBalance) payload.guestInitialBalance = form.guestInitialBalance
    if (form.registerUserGroup !== snapshot.registerUserGroup) payload.registerUserGroup = form.registerUserGroup
    await updateSiteSettings(payload)
    Message.success('设置已保存')
    await loadSettings()
  } catch (err) {
    Message.error(getErrorMessage(err, '设置保存失败'))
  } finally {
    saving.value = false
  }
}

onMounted(() => {
  loadSettings()
  loadModels()
})
</script>

<style scoped>
.settings-page {
  padding: var(--space-5) var(--space-6);
}

.settings-card {
  padding: var(--space-5) var(--space-6);
  margin-bottom: var(--space-4);
}

.settings-card-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin: 0 0 var(--space-4);
}

.settings-row {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  margin-bottom: var(--space-3);
}

.settings-row:last-of-type {
  margin-bottom: 0;
}

.settings-label {
  flex-shrink: 0;
  min-width: 140px;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.settings-tip {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.settings-tip-block {
  margin: var(--space-2) 0 0;
}

.settings-footer {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}
</style>
