<!-- 站点维护 Agent 对话页（仅管理员）：会话侧栏 + 对话窗口（复用工坊消息组件）+ 右侧设置面板 -->
<template>
  <div class="agent-page">
    <!-- 左栏：会话列表 -->
    <aside class="agent-sessions">
      <a-button type="primary" size="small" long @click="agentStore.createSession()">
        <template #icon><icon-plus/></template>
        新建会话
      </a-button>
      <div class="session-list">
        <div v-for="s in agentStore.sessions" :key="s.sessionId"
             class="session-item" :class="{active: s.sessionId === agentStore.currentSessionId}"
             @click="agentStore.selectSession(s.sessionId)">
          <div class="session-title">{{ s.title }}</div>
          <div class="session-meta">{{ s.modelName }}</div>
          <button class="session-delete" title="删除会话"
                  @click.stop="confirmRemove(s.sessionId)">×</button>
        </div>
        <div v-if="!agentStore.sessions.length && !loading" class="session-empty">
          暂无会话，点击上方新建
        </div>
      </div>
    </aside>

    <!-- 中栏：对话窗口 -->
    <section class="agent-chat">
      <template v-if="agentStore.currentSession">
        <header class="chat-header">
          <div class="chat-title">
            <h3>{{ agentStore.currentSession.title }}</h3>
            <span class="chat-model-tag">{{ agentStore.currentModel }}</span>
          </div>
          <a-select :model-value="agentStore.currentModel" size="small"
                    :style="{width: '220px'}" placeholder="切换驱动模型（下一轮生效）"
                    :disabled="agentStore.isStreaming"
                    @change="(v: any) => agentStore.patchSession({modelName: String(v)})">
            <a-option v-for="m in availableModels" :key="m.name" :value="m.name">
              {{ m.label || m.name }}
              <span class="model-group-tag">{{ m.modelGroup }}</span>
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

    <!-- 右栏：会话设置与说明 -->
    <aside class="agent-panel">
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
          <div class="risk-item"><span class="risk-dot l0"></span>L0 只读——直接执行</div>
          <div class="risk-item"><span class="risk-dot l1"></span>L1 低危写——审批卡片（可自动批准）</div>
          <div class="risk-item"><span class="risk-dot l2"></span>L2 高危写——强审批 + 两段式 dry-run</div>
        </div>
      </div>

      <div class="panel-section">
        <div class="panel-title">使用提示</div>
        <ul class="panel-tips">
          <li>大脑模型走你的个人账户计费，随时可切换站内任意模型</li>
          <li>清理数据表务必先看 dry-run 预览再批准真删</li>
          <li>巡检 / 排障 / 治理有内置 SOP，直接说"出一份巡检报告"</li>
          <li>渠道密钥永不展示；所有操作写入审计日志</li>
        </ul>
      </div>
    </aside>
  </div>
</template>

<script setup lang="ts">
import {computed, onMounted, ref} from 'vue'
import {Message} from '@arco-design/web-vue'
import ChatMessages from '@/components/studio/ChatMessages.vue'
import AgentInput from '@/components/agent/AgentInput.vue'
import {useAgentStore} from '@/stores/agent'
import {useModelListStore} from '@/stores/modelList'
import {confirmDialog} from '@/utils/feedback'

const agentStore = useAgentStore()
const modelListStore = useModelListStore()
const loading = ref(false)

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
  const ok = await confirmDialog('删除该会话将联动删除全部消息记录，不可恢复。', '删除会话', '删除', true)
  if (ok) agentStore.removeSession(sessionId)
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

/* ── 左栏：会话侧栏 ── */
.agent-sessions {
  width: 220px;
  flex-shrink: 0;
  display: flex;
  flex-direction: column;
  gap: var(--space-3);
  min-height: 0;
}

.session-list {
  flex: 1;
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 4px;
}

.session-item {
  position: relative;
  padding: 8px 12px;
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
  font-size: var(--text-sm);
  color: var(--color-text);
  padding-right: 18px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-meta {
  font-size: 11px;
  color: var(--color-text-muted);
  font-family: var(--font-mono);
  margin-top: 2px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-delete {
  position: absolute;
  top: 6px;
  right: 8px;
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

.model-group-tag {
  font-size: 11px;
  color: var(--color-text-muted);
  margin-left: 6px;
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
.risk-dot.l2 { background: var(--color-danger); }

.panel-tips {
  margin: 0;
  padding-left: 1.2em;
  font-size: var(--text-xs);
  color: var(--color-text-secondary);
  line-height: 1.9;
}

/* 窄屏：右侧面板收纳到底部（简单响应式） */
@media (max-width: 1100px) {
  .agent-panel { display: none; }
}

@media (max-width: 860px) {
  .agent-sessions { display: none; }
}
</style>
