<!-- 工坊空会话欢迎页：当前模型身份 + 4 条纯文字提问建议（点击直接发送）
     按 UI 规范 §12 去营销化：不用 emoji、装饰性大图标、彩色圆角卡与 hover 上浮阴影。 -->
<template>
    <div class="welcome-panel">
        <div class="welcome-inner">
            <div class="welcome-eyebrow">MODEL STUDIO / PLAYGROUND</div>
            <h1 class="welcome-title">从一句提示词开始</h1>
            <p class="welcome-desc">选择模型、设定生成参数，直接发起调试。请求内容与用量会记录在当前会话中。</p>

            <!-- 当前模型身份条：把「我现在在调哪个模型」放到首屏重心 -->
            <div class="identity-card">
                <div class="identity-icon">{{ modelInitial }}</div>
                <div class="identity-info">
                    <div class="identity-name">{{ modelName || '未选择模型' }}</div>
                    <div class="identity-meta">
                        {{ modelName ? '当前会话模型  ·  参数在右侧面板调整' : '请先在参数面板选择一个模型' }}
                    </div>
                </div>
                <button class="identity-action" @click="emit('focusPanel')">切换模型 ›</button>
            </div>

            <div class="suggest-head">试试这样问</div>
            <div class="suggest-list">
                <button v-for="(item, index) in suggestions" :key="item" class="suggest-row"
                        :disabled="!modelName" @click="emit('select', item)">
                    <span class="suggest-index">{{ String(index + 1).padStart(2, '0') }}</span>
                    <span class="suggest-text">{{ item }}</span>
                    <span class="suggest-arrow">→</span>
                </button>
            </div>

            <div class="welcome-foot">当前会话暂无用量  ·  上下文 0</div>
        </div>
    </div>
</template>

<script setup lang="ts">
import {computed} from 'vue'

const props = defineProps<{
    /** 当前是否已选择模型（未选择时建议置灰） */
    modelName: string
}>()

// 保留原有 select 语义；新增 focusPanel 供窄屏跳到参数面板
const emit = defineEmits<{
    select: [prompt: string]
    focusPanel: []
}>()

// 静态提问建议（不做 LLM 动态生成，避免额外开销）；文案贴合 API 调试场景
const suggestions = [
    '用 Python 写一个带重试的 API 请求封装',
    '把这段报错定位到具体原因并给出修复顺序',
    '比较两个模型在长文本摘要任务上的差异',
    '设计一份模型调用的成本估算表',
]

const modelInitial = computed(() => (props.modelName.trim()[0] || '—').toUpperCase())
</script>

<style scoped>
.welcome-panel {
    height: 100%;
    overflow-y: auto;
    display: flex;
    align-items: center;
    justify-content: center;
    padding: var(--space-6) var(--space-5);
}

/* 与消息列、输入区共用 720px 内容轴 */
.welcome-inner {
    width: 100%;
    max-width: var(--layout-studio-content);
}

.welcome-eyebrow {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    letter-spacing: 1px;
    color: var(--color-text-muted);
}

.welcome-title {
    margin: var(--space-3) 0 var(--space-2);
    font-size: var(--text-xl);
    font-weight: var(--font-semibold);
    color: var(--color-text);
    line-height: 1.4;
}

.welcome-desc {
    margin: 0 0 var(--space-6);
    font-size: var(--text-sm);
    line-height: 1.6;
    color: var(--color-text-secondary);
}

.identity-card {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    padding: var(--space-3);
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-white);
}

.identity-icon {
    flex-shrink: 0;
    width: 38px;
    height: 38px;
    display: flex;
    align-items: center;
    justify-content: center;
    border-radius: var(--radius-md);
    background: var(--color-gray-100);
    color: var(--color-text-secondary);
    font-family: var(--font-mono);
    font-size: var(--text-base);
    font-weight: var(--font-medium);
}

.identity-info {
    flex: 1;
    min-width: 0;
}

.identity-name {
    font-size: var(--text-sm);
    font-weight: var(--font-medium);
    color: var(--color-text);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.identity-meta {
    margin-top: 2px;
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.identity-action {
    flex-shrink: 0;
    padding: 4px 6px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-primary);
    font-family: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
}

.identity-action:hover {
    background: var(--color-primary-lighter);
}

.suggest-head {
    margin: var(--space-6) 0 var(--space-2);
    font-size: var(--text-xs);
    font-weight: var(--font-medium);
    color: var(--color-text-secondary);
}

.suggest-list {
    display: flex;
    flex-direction: column;
    gap: var(--space-2);
}

.suggest-row {
    display: flex;
    align-items: center;
    gap: var(--space-3);
    width: 100%;
    height: 42px;
    padding: 0 var(--space-3);
    text-align: left;
    border: 1px solid var(--color-border);
    border-radius: var(--radius-lg);
    background: var(--color-white);
    font-family: inherit;
    cursor: pointer;
    transition: border-color var(--transition-fast), background-color var(--transition-fast);
}

.suggest-row:hover:not(:disabled) {
    border-color: var(--color-primary);
    background: var(--color-bg-subtle);
}

.suggest-row:disabled {
    cursor: not-allowed;
    opacity: 0.55;
}

.suggest-index {
    flex-shrink: 0;
    width: 22px;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

.suggest-text {
    flex: 1;
    min-width: 0;
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
    font-size: var(--text-sm);
    color: var(--color-text);
}

.suggest-arrow {
    flex-shrink: 0;
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

.welcome-foot {
    margin-top: var(--space-4);
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

@media (max-width: 768px) {
    .welcome-panel { padding: var(--space-5) var(--space-4); }
    .welcome-title { font-size: var(--text-lg); }
    .welcome-desc { margin-bottom: var(--space-5); }
    .identity-action { display: none; }
    .suggest-head { margin-top: var(--space-5); }
    .suggest-text { font-size: var(--text-xs); }
}
</style>
