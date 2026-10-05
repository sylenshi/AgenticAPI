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
          <a-select :model-value="agentStore.currentModel" size="small"
                    :style="{width: '280px'}" placeholder="切换驱动模型（下一轮生效）"
                    :disabled="agentStore.isStreaming"
                    @change="(v: any) => agentStore.patchSession({modelName: String(v)})">
            <a-option v-for="m in availableModels" :key="m.name" :value="m.name">
              {{ m.name }}
            </a-option>
          </a-select>
        </header>

        <ChatMessages :messages="agentStore.messages" :is-streaming="agentStore.isStreaming"
                      @approve-tool="onApprove"/>
        <AgentInput :is-streaming="agentStore.isStreaming"
                    @send="(text) => agentStore.send(text)" @stop="agentStore.stop()"/>
      </template>

      <!-- 无会话时的空态引导 -->
      <div v-else class="chat-empty">
        <icon-robot class="empty-icon"/>
        <h3>站点维护 Agent</h3>
        <p>用一句话完成复合运维：测渠道、巡检模型、查额度水位、导出并清理数据表。<br>
          高危操作（L2 清理）会弹出审批卡片，经你确认后才会执行。</p>
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
        <div class="panel-title">会话设置</div>
        <div class="panel-row">
          <div class="panel-label">
            <span>L1 自动批准</span>
            <span class="panel-desc">低危写操作免审批</span>
          </div>
          <a-switch :model-value="agentStore.currentSession?.autoApproveL1" size="small"
                    @change="(v: any) => agentStore.patchSession({autoApproveL1: !!v})"/>
        </div>
        <div class="panel-row">
          <div class="panel-label">
            <span>L2 高危工具</span>
            <span class="panel-desc">关闭即只读模式</span>
          </div>
          <a-switch :model-value="agentStore.currentSession?.enableL2" size="small"
                    @change="(v: any) => agentStore.patchSession({enableL2: !!v})"/>
        </div>
      </div>

      <div class="panel-section">
        <div class="panel-title">风险等级</div>
        <div class="risk-legend">
          <div class="risk-item"><span class="risk-dot l0"></span>L0 只读工具</div>
          <div class="risk-item"><span class="risk-dot l1"></span>L1 低危工具</div>
          <div class="risk-item"><span class="risk-dot l2"></span>L2 高危工具</div>
        </div>
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
import {confirmDialog} from '@/utils/feedback'

const agentStore = useAgentStore()
const modelListStore = useModelListStore()
const loading = ref(false)
/** 使用提示 / 安全提示弹窗开关 */
const usageVisible = ref(false)
const safetyVisible = ref(false)

// 帮助弹窗内容（markdown）：html:false 转义原文标签防 XSS，与工坊消息渲染同一配置
const md = new MarkdownIt({breaks: true})
const usageHtml = md.render(`
### 对话与计费
- **大脑模型**：由当前会话选定的模型驱动，每次调用按站点定价计入**你的管理员余额**（免费模型不扣费）；调用流水可在「监控面板 → 调用日志」按关键字 *维护Agent* 对账
- **随时换脑**：右上角选择器可切换站内任意启用模型，**下一轮生效**，上下文不丢失

### 怎么下达任务
- 一句话描述目标即可，无需拆步骤：\`出一份巡检报告\`、\`测一遍所有渠道\`、\`glm-5.3 最近一周调用趋势怎么样\`
- 复合任务它会自己规划多步：\`检查所有模型可用性，然后告诉我哪些渠道有问题\`

### 内置技能（SOP）
- 已内置六个运维 SOP：**站点巡检 / 数据治理 / 渠道排障 / 额度水位研判 / 新模型上线 / 故障复盘**，自然语言即可触发
- **教它新技能**：口述内容让它保存（"记住一个叫 xxx 的技能：……"）；保存与删除都弹审批卡片，**开启 L1 自动批准也不豁免**

### 数据导出与清理
- 导出（对话记录 / 日志 / 统计表）返回**一次性下载链接**：24 小时有效、仅可下载一次，请及时保存
- 清理走**两段式**：先 dry-run 预览将删的行数与时间范围 → 你批准后才真删；可先导出备份再清理
`)
const safetyHtml = md.render(`
### 工具风险分级（共 27 个白名单工具）
| 等级 | 范围 | 执行方式 |
| --- | --- | --- |
| **L0 只读**（19 个） | 巡检 / 统计 / 拨测 / 查询 / 切模型 | 直接执行，不打扰 |
| **L1 低危写**（5 个） | 渠道改配置 / 数据导出 / 技能保存删除 | 弹审批卡片，可开**会话级自动批准** |
| **L2 高危写**（3 个） | 数据表清理（日志 / 对话记录 / 统计） | **强制人工审批**，无法自动批准 |

### 硬性护栏
- L2 每会话**最多 5 次**真删；审批卡片 **300 秒**未操作自动按拒绝处理
- 关闭右侧「L2 高危工具」即进入**只读模式**：高危工具根本不会注入给模型，它"不知道"有这些工具
- 单轮对话上限 24 次工具调用、上下文 200k token，超限自动收敛结束

### 密钥与审计
- 渠道密钥**全程递归脱敏**：界面只显示掩码（如 \`sk-1****wxyz\`），数据库与前端均不存密钥原文
- **双轨留痕**：每次工具调用（参数 + 结果摘要）与每次审批决定（批准 / 拒绝 / 超时）均写入审计日志，可在「监控面板 → 调用日志」按管理员筛选追溯
- 它没有 shell、没有任意命令执行、没有通用文件访问，只能调用上表中的白名单工具
`)

/** 模型选择器数据：站内启用中的出站模型（管理员 vip 全量可用） */
const availableModels = computed(() =>
    (modelListStore.totalModelList || []).filter(m => (m as any).status !== 0))

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
  // 生成中的会话禁止删除：SSE 流会继续往已删除的会话 id 写消息（表无外键拦不住），留下孤儿数据
  if (agentStore.isStreaming && sessionId === agentStore.currentSessionId) {
    Message.warning('当前会话正在生成，请先停止再删除')
    return
  }
  const ok = await confirmDialog('删除该会话将联动删除全部消息记录，不可恢复。', '删除会话', '删除', true)
  if (ok) agentStore.removeSession(sessionId)
}

/** 一键清空：生成中禁用（流式回写目标会话会被删掉），空列表无可清项 */
async function confirmClear() {
  if (agentStore.isStreaming) {
    Message.warning('请先停止当前生成，再清空会话')
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
  color: var(--color-danger);
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

.risk-legend {
  display: flex;
  flex-direction: column;
  gap: var(--space-2);
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
}

.risk-dot {
  display: inline-block;
  width: 8px;
  height: 8px;
  border-radius: 50%;
  margin-right: 8px;
  transform: translateY(-0.5px);
}

.risk-dot.l0 { background: var(--color-success); }
.risk-dot.l1 { background: var(--color-warning); }
.risk-dot.l2 { background: var(--color-error); }

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
