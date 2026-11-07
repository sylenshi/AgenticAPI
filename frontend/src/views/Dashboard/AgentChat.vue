<!-- 站点维护 Agent 对话页（仅管理员）：对话窗口（复用工坊消息组件）+ 右侧合并面板（会话/设置/帮助） -->
<template>
  <div class="agent-page">
    <!-- 对话窗口（主区） -->
    <section class="agent-chat">
      <template v-if="agentStore.currentSession">
        <header class="chat-header">
          <div class="chat-title">
            <h3>{{ agentStore.currentSession.title }}</h3>
            <span class="chat-model-tag">{{ agentStore.currentModel }}</span>
          </div>
          <div class="chat-header-actions">
            <a-tooltip content="导出当前会话记录（Markdown，含工具调用与审批轨迹），任务执行中也可导出">
              <a-button type="outline" size="small" :loading="exporting" @click="exportSession">
                <template #icon><icon-download/></template>
                导出会话
              </a-button>
            </a-tooltip>
            <a-select :model-value="agentStore.currentModel" size="small"
                      :style="{width: '280px'}" placeholder="切换驱动模型（下一轮生效）"
                      :disabled="busy"
                      @change="(v: any) => agentStore.patchSession({modelName: String(v)})">
              <a-option v-for="m in availableModels" :key="m.name" :value="m.name">
                {{ m.name }}
              </a-option>
            </a-select>
          </div>
        </header>

        <!-- 有会话但还没有消息：给引导空态，会话区不再整块留白 -->
        <ChatMessages v-if="agentStore.messages.length" :messages="agentStore.messages"
                      :is-streaming="agentStore.isStreaming" @approve-tool="onApprove"/>
        <div v-else class="chat-empty chat-empty-session">
          <icon-robot class="empty-icon"/>
          <h3>新会话已就绪</h3>
          <p>在下方输入框描述运维目标即可开始，例如：<br>「巡检全部渠道并把异常的停用」「统计 logs 表占用并清理 90 天前的日志」</p>
        </div>
        <!-- 护栏叫停后的断点续跑入口（Agent 已输出小结，一键以预置指令继续） -->
        <div v-if="continueOffer" class="continue-bar">
          <span class="continue-text">
            {{ agentStore.pausedReason === 'cost_limit' ? '任务已达成本上限，Agent 已小结收尾' : '任务已达轮数上限，Agent 已小结收尾' }}
          </span>
          <a-button type="primary" size="small" @click="continueTask">继续任务</a-button>
        </div>
        <AgentInput :is-streaming="busy"
                    @send="(text) => agentStore.send(text)" @stop="agentStore.stop()"/>
      </template>

      <!-- 无会话时的空态引导 -->
      <div v-else class="chat-empty">
        <icon-robot class="empty-icon"/>
        <h3>站点维护 Agent</h3>
        <p>用一句话完成复合运维：测渠道、巡检模型、查额度水位、统计并清理数据表。<br>
          写操作是否需要你确认由右侧「审批档位」决定，删除类高危操作默认必弹。</p>
        <a-button type="primary" @click="agentStore.createSession()">开始新会话</a-button>
      </div>
    </section>

    <!-- 右栏：会话 / 设置 / 说明（原左栏会话栏合并至此，整页保持三列：导航 + 对话 + 本面板） -->
    <aside class="agent-panel">
      <div class="panel-section">
        <div class="panel-title">会话</div>
        <div class="session-actions">
          <a-button type="primary" size="small" @click="agentStore.createSession()">
            <template #icon><icon-plus/></template>
            新建会话
          </a-button>
          <a-button type="outline" size="small" status="danger" @click="confirmClear">
            <template #icon><icon-delete/></template>
            清空
          </a-button>
        </div>
        <!-- 透明滚动容器：只露出最近 3 条会话，更早的在容器内滚动查找 -->
        <div class="session-list-scroll">
          <div class="session-list">
            <div v-for="s in agentStore.sessions" :key="s.sessionId"
                 class="session-item" :class="{active: s.sessionId === agentStore.currentSessionId}"
                 @click="agentStore.selectSession(s.sessionId)">
              <div class="session-title">{{ s.title }}</div>
              <button class="session-delete" title="删除会话"
                      @click.stop="confirmRemove(s.sessionId)">×</button>
            </div>
            <div v-if="!agentStore.sessions.length && !loading" class="session-empty">
              暂无会话，点击上方新建
            </div>
          </div>
        </div>
      </div>

      <div class="panel-section">
        <div class="panel-title">审批档位</div>
        <a-select :model-value="agentStore.currentSession?.approvalMode || 'confirm_all'" size="small"
                  :style="{width: '100%'}"
                  @change="(v: any) => agentStore.patchSession({approvalMode: String(v)})">
          <a-option value="confirm_all">需要审批</a-option>
          <a-option value="confirm_critical">部分审批</a-option>
          <a-option value="full">完全权限</a-option>
        </a-select>
        <div class="panel-desc approval-mode-desc">{{ approvalModeDesc }}</div>
      </div>

      <div class="panel-section">
        <div class="panel-title">上下文水位</div>
        <template v-if="contextLength">
          <a-progress :percent="contextPercent" size="small" :show-text="false" :status="contextStatus"/>
          <div class="context-text">
            {{ formatTokens(agentStore.contextTokens || 0) }} / {{ formatTokens(contextLength) }} tokens
            （{{ Math.round(contextPercent * 100) }}%）
          </div>
        </template>
        <div v-else class="panel-desc">当前驱动模型未配置上下文窗口长度，暂无水位读数</div>
      </div>

      <div class="panel-section">
        <div class="panel-title">帮助</div>
        <div class="help-actions">
          <a-button type="outline" size="small" @click="usageVisible = true">
            <template #icon><icon-bulb/></template>
            提示
          </a-button>
          <a-button type="outline" size="small" status="warning" @click="safetyVisible = true">
            <template #icon><icon-safe/></template>
            安全
          </a-button>
        </div>
      </div>
    </aside>

    <!-- 使用提示 / 安全提示弹窗（markdown 渲染） -->
    <a-modal v-model:visible="usageVisible" title="使用提示" :width="560" :footer="false">
      <div class="help-md" v-html="usageHtml"></div>
    </a-modal>
    <a-modal v-model:visible="safetyVisible" title="安全提示" :width="560" :footer="false">
      <div class="help-md" v-html="safetyHtml"></div>
    </a-modal>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import MarkdownIt from 'markdown-it'
import ChatMessages from '@/components/studio/ChatMessages.vue'
import AgentInput from '@/components/agent/AgentInput.vue'
import {useAgentStore} from '@/stores/agent'
import {useModelListStore} from '@/stores/modelList'
import {exportAgentSession} from '@/api/agent'
import {getErrorMessage} from '@/api/request'
import {confirmDialog} from '@/utils/feedback'

const agentStore = useAgentStore()
const modelListStore = useModelListStore()
const loading = ref(false)
/** 会话导出进行中（导出当前会话记录为 Markdown 下载） */
const exporting = ref(false)
/** 使用提示 / 安全提示弹窗开关 */
const usageVisible = ref(false)
const safetyVisible = ref(false)

// 帮助弹窗内容（markdown）：html:false 转义原文标签防 XSS，与工坊消息渲染同一配置
const md = new MarkdownIt({breaks: true})
const usageHtml = md.render(`
### 对话与计费
- **大脑模型**：由当前会话选定的模型驱动，每次调用按站点定价计入**你的管理员余额**（免费模型不扣费）；调用流水可在「监控面板 → 调用日志」按关键字 *维护Agent* 对账
- **随时换脑**：右上角选择器可切换站内任意启用模型，**下一轮生效**，上下文不丢失
- **成本护栏**：一条指令触发的完整任务累计费用达到「设置页 → 单任务成本上限」（默认 2 元）后，Agent 自动小结收尾，对话下方出现**继续任务**按钮，一键接着跑（轮数、成本均按任务重新计算）

### 怎么下达任务
- 一句话描述目标即可，无需拆步骤：\`出一份巡检报告\`、\`测一遍所有渠道\`、\`统计 logs 表占用并清理 90 天前的日志\`
- 复合任务它会自己规划多步：\`检查所有模型可用性，然后告诉我哪些渠道有问题\`
- **模型发现**：让它拉上游模型清单对照差集（\`看看火山方舟上游还有哪些模型可以接入\`）；上游没有清单接口时，它会逐名试拨验证候选模型；上游凭证到期，把新密钥发到对话里让它轮换即可

### 内置技能（SOP）
- 已内置六个运维 SOP：**站点巡检 / 数据治理 / 渠道排障 / 额度水位研判 / 新模型上线 / 故障复盘**，自然语言即可触发
- **教它新技能**：口述内容让它保存（"记住一个叫 xxx 的技能：……"）；保存前会弹审批卡展示完整草稿

### 数据治理（沙箱连库）
- 数据统计 / 清理由它在**容器沙箱**内跑数据库脚本完成（技能：data-governance）；先统计与预览，你确认后才分批删除
- 大数据全量导出沙箱拿不出来（输出上限 64KB），需要时登服务器用 mysqldump
`)
const safetyHtml = md.render(`
### 操作确认（共 25 个白名单工具）
| 类型 | 范围 | 执行方式 |
| --- | --- | --- |
| **只读**（15 个） | 巡检 / 统计 / 拨测 / 查询 / 上游模型发现 | 直接执行，不打扰 |
| **普通写**（3 个） | 修改渠道 / 模型配置、保存技能 | 按审批档位确认或直行 |
| **关键操作**（7 个） | 删除渠道 / 模型 / 技能、新增渠道 / 模型、沙箱命令、密钥轮换 | 默认必弹确认卡 |

### 审批档位（右侧面板可切换）
- **需要审批**（默认）：所有写操作都弹审批卡
- **部分审批**：仅关键操作（删除、新增渠道/模型、沙箱命令）弹卡，普通配置修改直行
- **完全权限**：全部直接执行（风险自担，审计照常）

### 硬性护栏
- 删除渠道 / 模型 / 技能每会话**最多 10 次**、沙箱命令每会话**最多 30 次**（任何档位都生效）；审批卡片 **300 秒**未操作自动按拒绝处理
- 删除渠道 / 模型走**两段式**：先预览影响 → 你批准后才真删
- 单任务上限 40 轮工具调用、成本达到设置页上限（默认 2 元）自动小结收尾，可一键继续

### 密钥与审计
- 渠道密钥**全程递归脱敏**：界面与对话记录只显示掩码（如 \`sk-1****wxyz\`），密钥仅存于渠道配置本体，日志 / 消息 / 审计全掩码；需要密钥的上游操作由后端代持密钥执行，密钥不进入对话上下文
- **双轨留痕**：每次工具调用（参数 + 结果摘要）与每次审批决定（批准 / 拒绝 / 超时）均写入审计日志，可在「监控面板 → 调用日志」按管理员筛选追溯
- 宿主机侧没有 shell 与通用文件访问；唯一例外是容器沙箱 \`sandbox_exec\`（隔离加固，数据库凭证以环境变量注入，输出经脱敏）
`)

/** 模型选择器数据：站内启用中的出站模型（管理员 vip 全量可用） */
const availableModels = computed(() =>
    (modelListStore.totalModelList || []).filter(m => (m as any).status !== 0))

/** ═══════════ 审批档位（三档位 × 只读/普通写/关键操作查表）═══════════ */
const approvalModeDesc = computed(() => ({
  confirm_all: '需要审批：所有写操作（含沙箱命令）都弹审批卡',
  confirm_critical: '部分审批：仅关键操作（删除、新增渠道/模型、沙箱命令）弹卡，普通配置修改直行',
  full: '完全权限：全部直接执行，无需确认（删除与沙箱命令仍受每会话次数上限约束）',
}[agentStore.currentSession?.approvalMode || 'confirm_all']))

/** ═══════════ 任务占用（本地订阅中，或该会话服务端有任务在跑）═══════════ */
const busy = computed(() => agentStore.isStreaming || !!agentStore.currentSession?.running)

/** ═══════════ 护栏叫停后的断点续跑 ═══════════ */
const continueOffer = computed(() => !!agentStore.pausedReason && !agentStore.isStreaming)
function continueTask() {
  agentStore.send('继续执行未完成的任务，从上次小结中的"建议的续作步骤"接着做。')
}

/** ═══════════ 上下文水位（17.1：窗口上限 × 最近一轮 prompt_tokens）═══════════ */
const currentModelInfo = computed(() =>
    availableModels.value.find(m => m.name === agentStore.currentModel))
const contextLength = computed(() => (currentModelInfo.value as any)?.contextLength || 0)
const contextPercent = computed(() => {
  const used = agentStore.contextTokens || 0
  return contextLength.value > 0 ? Math.min(1, used / contextLength.value) : 0
})
const contextStatus = computed(() => {
  if (contextPercent.value >= 0.9) return 'danger'
  if (contextPercent.value >= 0.7) return 'warning'
  return 'normal'
})
/** token 读数千分位（无读数时显示 0） */
function formatTokens(n: number): string {
  return Math.round(n || 0).toLocaleString()
}

onMounted(async () => {
  loading.value = true
  await agentStore.loadSessions()
  // 默认选中最近会话（没有则不自动创建，展示空态引导）
  const first = agentStore.sessions[0]
  if (first) {
    await agentStore.selectSession(first.sessionId)
  }
  loading.value = false
})

async function onApprove(payload: { approvalId: string; approved: boolean }) {
  await agentStore.approve(payload.approvalId, payload.approved)
  Message[payload.approved ? 'success' : 'info'](
      payload.approved ? '已批准，工具继续执行' : '已拒绝本次操作')
}

async function confirmRemove(sessionId: number) {
    // 任务占用中的会话禁止删除：服务端任务会继续往已删除的会话 id 写消息（表无外键拦不住），留下孤儿数据
    if (busy.value && sessionId === agentStore.currentSessionId) {
        Message.warning('当前会话有任务在执行，请先停止再删除')
        return
    }
  const ok = await confirmDialog('删除该会话将联动删除全部消息记录，不可恢复。', '删除会话', '删除', true)
  if (ok) agentStore.removeSession(sessionId)
}

/** 一键清空：任务占用中禁用（任务回写目标会话会被删掉），空列表无可清项 */
async function confirmClear() {
    if (busy.value) {
        Message.warning('当前会话有任务在执行，请先停止再清空')
        return
    }
  if (!agentStore.sessions.length) {
    Message.info('当前没有可清空的会话')
    return
  }
  const ok = await confirmDialog(
      `将删除全部 ${agentStore.sessions.length} 个会话及所有消息记录，不可恢复。`, '清空会话', '清空', true)
  if (ok) await agentStore.clearSessions()
}

/** ═══════════ 导出当前会话记录（Markdown：正文/工具调用/结果/审批轨迹，排查与归档用）═══════════ */
async function exportSession() {
  const sessionId = agentStore.currentSessionId
  if (!sessionId || exporting.value) return
  exporting.value = true
  try {
    const res = await exportAgentSession(sessionId)
    const {filename, content} = res.data
    const blob = new Blob([content], {type: 'text/markdown;charset=utf-8'})
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename || `维护Agent会话-${sessionId}.md`
    a.click()
    URL.revokeObjectURL(url)
    Message.success('会话记录已导出')
  } catch (err) {
    Message.error(getErrorMessage(err, '会话导出失败'))
  } finally {
    exporting.value = false
  }
}
</script>

<style scoped>
.agent-page {
  display: flex;
  gap: var(--space-4);
  height: calc(100vh - var(--layout-header-height));
  padding: var(--space-4);
  box-sizing: border-box;
  min-width: 0;
}

/* ── 会话列表（右栏卡片内）：固定条目高度 + 滚轮容器，恰好露出最近 3 条，更早的滚动查找 ── */
.session-actions {
  display: flex;
  flex-direction: row;
  gap: var(--space-2);
}

/* 新建会话占满剩余宽度，清空按内容自适应收窄 */
.session-actions > :first-child {
  flex: 1 1 0;
  min-width: 0;
}

.session-list-scroll {
  margin-top: var(--space-2);
  /* 与 .session-item 固定高 36px 联动：3 条 + 2 个 4px 间距（滚动条为全局细灰样式） */
  max-height: calc(36px * 3 + 4px * 2);
  overflow-y: auto;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  position: relative;
  height: 36px;
  box-sizing: border-box;
  display: flex;
  align-items: center;
  padding: 0 26px 0 10px;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-white);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.session-item:hover {
  border-color: var(--color-primary-light);
}

.session-item.active {
  border-color: var(--color-primary);
  background: var(--color-primary-lighter);
}

.session-title {
  flex: 1;
  min-width: 0;
  font-size: var(--text-sm);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-delete {
  position: absolute;
  top: 50%;
  right: 6px;
  transform: translateY(-50%);
  display: none;
  border: none;
  background: none;
  color: var(--color-text-muted);
  font-size: 14px;
  cursor: pointer;
  line-height: 1;
}

.session-item:hover .session-delete {
  display: block;
}

.session-delete:hover {
  color: var(--color-error);
}

.session-empty {
  font-size: var(--text-xs);
  color: var(--color-text-muted);
  text-align: center;
  padding: var(--space-4) 0;
}

/* ── 中栏：对话窗口 ── */
.agent-chat {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-white);
  padding: var(--space-3) var(--space-4);
  gap: var(--space-2);
  min-height: 0;
}

.chat-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-3);
  padding-bottom: var(--space-2);
  border-bottom: 1px solid var(--color-border);
}

/* 头部右侧操作区：导出会话 + 模型选择器（导出不随任务占用禁用，执行中恰是排查导出场景） */
.chat-header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  flex-shrink: 0;
}

.chat-title {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  min-width: 0;
}

.chat-title h3 {
  margin: 0;
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.chat-model-tag {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--color-primary);
  background: var(--color-primary-lighter);
  padding: 1px 8px;
  border-radius: var(--radius-sm);
  flex-shrink: 0;
}

.chat-empty {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  gap: var(--space-3);
  color: var(--color-text-secondary);
  text-align: center;
}

.chat-empty h3 {
  margin: 0;
  font-size: var(--text-lg);
  color: var(--color-text);
}

.chat-empty p {
  margin: 0;
  font-size: var(--text-sm);
  line-height: 1.9;
}

.empty-icon {
  font-size: 44px;
  color: var(--color-primary-light);
}

/* ── 右栏：设置面板 ── */
.agent-panel {
  width: 240px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  overflow-y: auto;
}

.panel-section {
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  background: var(--color-white);
  padding: var(--space-3);
}

.panel-title {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin-bottom: var(--space-3);
}

.panel-row {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: var(--space-2) 0;
}

.panel-row + .panel-row {
  border-top: 1px solid var(--color-gray-100);
}

.panel-label {
  display: flex;
  flex-direction: column;
  gap: 1px;
  font-size: var(--text-sm);
  color: var(--color-text);
}

.panel-desc {
  font-size: 11px;
  color: var(--color-text-muted);
}

/* 审批档位说明：独占一行，与下拉拉开 6px 间距 */
.approval-mode-desc {
  margin-top: 6px;
  line-height: 1.5;
}

/* 上下文水位读数行：进度条下方的已用/上限明细 */
.context-text {
  margin-top: 4px;
  font-size: 11px;
  color: var(--color-text-secondary);
  font-variant-numeric: tabular-nums;
}

/* ── 断点续跑入口条：护栏叫停后出现在输入框上方 ── */
.continue-bar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
  padding: 8px 12px;
  border: 1px solid var(--color-warning);
  border-radius: var(--radius-md);
  background: var(--color-warning-light);
}

.continue-text {
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.help-actions {
  display: flex;
  flex-direction: row;
  gap: var(--space-2);
}

/* 两个按钮各占一半宽，恒一行排布（子组件根元素继承本组件 scope 属性） */
.help-actions > * {
  flex: 1 1 0;
  min-width: 0;
}

/* 帮助弹窗 markdown 渲染（v-html 内容不吃 scoped，需 :deep 穿透） */
.help-md {
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  line-height: 1.8;
}

.help-md :deep(h3) {
  font-size: var(--text-sm);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin: 14px 0 6px;
}

.help-md :deep(h3:first-child) {
  margin-top: 2px;
}

.help-md :deep(ul) {
  margin: 4px 0;
  padding-left: 1.3em;
}

.help-md :deep(li) {
  margin: 4px 0;
}

.help-md :deep(code) {
  font-family: var(--font-mono);
  font-size: 12px;
  background: var(--color-gray-100);
  border-radius: var(--radius-sm);
  padding: 1px 5px;
}

.help-md :deep(strong) {
  color: var(--color-text);
}

.help-md :deep(em) {
  color: var(--color-text);
  font-style: normal;
  border-bottom: 1px dashed var(--color-border);
}

.help-md :deep(table) {
  border-collapse: collapse;
  margin: 8px 0;
  width: 100%;
}

.help-md :deep(th),
.help-md :deep(td) {
  border: 1px solid var(--color-border);
  padding: 5px 8px;
  font-size: 12px;
  text-align: left;
}

.help-md :deep(th) {
  background: var(--color-gray-100);
  color: var(--color-text);
  font-weight: var(--font-medium);
}

/* 窄屏：右侧合并面板整体收起，对话区独占（简单响应式） */
@media (max-width: 1100px) {
  .agent-panel { display: none; }
}
</style>
