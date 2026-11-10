<!-- 工坊右侧参数面板：模型 / 生成参数 / 系统提示词 / 本次会话用量
     标签以中文为主、英文降为等宽备注；只保留一条滑块，避免满格蓝色原生控件抢过对话区。 -->
<template>
    <div class="settings-panel">
        <div class="panel-head">
            <span class="panel-title">参数配置</span>
            <button class="panel-reset" @click="resetParams">重置</button>
        </div>

        <div class="panel-group">
            <div class="group-title">模型</div>
            <a-select v-model="studioStore.selectedModelName" placeholder="请选择一个模型" allow-clear allow-search
                      @change="studioStore.persistParams()">
                <a-optgroup v-for="group in modelGroups" :key="group.label" :label="group.label">
                    <a-option v-for="model in group.models" :key="model.name" :value="model.name"
                              :label="model.name || model.label">
                        <div class="model-option">
                            <span class="model-option-name">{{ model.name || model.label }}</span>
                        </div>
                    </a-option>
                </a-optgroup>
            </a-select>
            <div v-if="!allowedModels.length" class="panel-hint">暂无可用模型</div>
        </div>

        <div class="panel-group">
            <div class="group-title">生成参数</div>

            <div class="param-row">
                <div class="param-label">
                    <span>温度</span><span class="param-en">Temperature</span>
                </div>
                <span class="param-value">{{ studioStore.params.temperature.toFixed(1) }}</span>
            </div>
            <a-slider v-model="studioStore.params.temperature" :min="0" :max="2" :step="0.1"
                      :show-tooltip="false" @change="studioStore.persistParams()"/>
            <div class="param-scale"><span>0</span><span>2</span></div>

            <div class="param-row with-input">
                <div class="param-label">
                    <span>核采样</span><span class="param-en">Top P</span>
                </div>
                <a-input-number v-model="studioStore.params.topP" :min="0" :max="1" :step="0.05"
                                :precision="2" size="small" @change="studioStore.persistParams()"/>
            </div>

            <div class="param-row with-input">
                <div class="param-label">
                    <span>最大输出</span><span class="param-en">Max Tokens</span>
                </div>
                <a-input-number v-model="studioStore.params.maxTokens" :min="1" :max="maxTokensLimit"
                                :step="256" size="small" @change="studioStore.persistParams()"/>
            </div>
            <div class="panel-hint">当前模型上限 {{ maxTokensLimit.toLocaleString() }}</div>
        </div>

        <div class="panel-group">
            <div class="param-row">
                <div class="param-label">
                    <span>系统提示词</span><span class="param-en">System Prompt</span>
                </div>
            </div>
            <a-textarea v-model="studioStore.params.systemPrompt" :max-length="2000" show-word-limit
                        :auto-size="{minRows: 3, maxRows: 8}"
                        placeholder="例如：你是一名严谨的后端工程师，回答需给出依据。"
                        @change="studioStore.persistParams()"/>
        </div>

        <div class="panel-group">
            <div class="group-title">本次会话</div>
            <div class="usage-row">
                <span>{{ sessionIn }} in</span>
                <span>{{ sessionOut }} out</span>
                <span>{{ sessionElapsed }} s</span>
            </div>
            <div class="context-label">累计 tokens / 单次上限（估算）</div>
            <div class="context-bar">
                <div class="context-fill" :style="{width: contextPercent + '%'}"></div>
            </div>
            <div class="context-value">{{ sessionTotal.toLocaleString() }} / {{ maxTokensLimit.toLocaleString() }}</div>
        </div>

        <div class="panel-note">参数仅对当前会话生效</div>
    </div>
</template>

<script setup lang="ts">
import {computed, watch} from 'vue'
import {useStudioStore} from '@/stores/studio'
import {useUserStore} from '@/stores/user'
import {useModelListStore} from '@/stores/modelList'
import {DEFAULT_STUDIO_PARAMS} from '@/types'

const studioStore = useStudioStore()
const userStore = useUserStore()
const modelListStore = useModelListStore()

// 可用模型：启用中 + 当前用户分组有权调用（与后端中转的分组校验一致：free 用户仅 free 模型）
const allowedModels = computed(() =>
    modelListStore.totalModelList.filter(m =>
        m.status && (m.modelGroup === 'free' || userStore.userInfo?.userGroup === 'vip'),
    ),
)

// 按 free / vip 分组展示
const modelGroups = computed(() => {
    const groups: Array<{label: string; models: typeof allowedModels.value}> = []
    for (const group of ['free', 'vip']) {
        const models = allowedModels.value.filter(m => m.modelGroup === group)
        if (models.length) {
            groups.push({label: group === 'free' ? '免费模型' : 'VIP 模型', models})
        }
    }
    return groups
})

// max_tokens 上限：取当前所选模型配置，未配置或未选模型时给一个通用上限
const maxTokensLimit = computed(() => {
    const model = allowedModels.value.find(m => m.name === studioStore.selectedModelName)
    return model?.maxTokens && model.maxTokens > 0 ? model.maxTokens : 32768
})

/** 本次会话累计用量：仅取已回填 usage 的助手消息，用于面板内的轻量概览 */
const sessionMessages = computed(() => studioStore.currentSession?.messages ?? [])
const sessionIn = computed(() => sessionMessages.value.reduce((sum, m) => sum + (m.usage?.promptTokens ?? 0), 0))
const sessionOut = computed(() => sessionMessages.value.reduce((sum, m) => sum + (m.usage?.completionTokens ?? 0), 0))
const sessionElapsed = computed(() =>
    (sessionMessages.value.reduce((sum, m) => sum + (m.usage?.elapsedMs ?? 0), 0) / 1000).toFixed(1),
)
const sessionTotal = computed(() => sessionIn.value + sessionOut.value)
const contextPercent = computed(() => Math.min(100, Math.round(sessionTotal.value / maxTokensLimit.value * 100)))

// 模型列表加载后 / 切换用户后：当前选择无效时回落到第一个可用模型
// （同时监听用户 id：登录信息晚于模型列表到达时，store 重载可能把选择清空，需要重新兜底）
watch(
    [allowedModels, () => userStore.userInfo?.id],
    () => {
        const first = allowedModels.value[0]?.name
        if (first && !allowedModels.value.some(m => m.name === studioStore.selectedModelName)) {
            studioStore.selectedModelName = first
            studioStore.persistParams()
        }
    },
    {immediate: true},
)

function resetParams() {
    studioStore.params.systemPrompt = DEFAULT_STUDIO_PARAMS.systemPrompt
    studioStore.params.temperature = DEFAULT_STUDIO_PARAMS.temperature
    studioStore.params.topP = DEFAULT_STUDIO_PARAMS.topP
    studioStore.params.maxTokens = DEFAULT_STUDIO_PARAMS.maxTokens
    studioStore.persistParams()
}
</script>

<style scoped>
.settings-panel {
    height: 100%;
    overflow-y: auto;
    padding: var(--space-4);
    background: var(--color-white);
}

.panel-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding-bottom: var(--space-3);
    margin-bottom: var(--space-4);
    border-bottom: 1px solid var(--color-border);
}

.panel-title {
    font-size: var(--text-sm);
    font-weight: var(--font-semibold);
    color: var(--color-text);
}

.panel-reset {
    padding: 2px 6px;
    border: none;
    border-radius: var(--radius-sm);
    background: transparent;
    color: var(--color-primary);
    font-family: inherit;
    font-size: var(--text-xs);
    cursor: pointer;
}

.panel-reset:hover {
    background: var(--color-primary-lighter);
}

.panel-group {
    margin-bottom: var(--space-5);
}

.group-title {
    margin-bottom: var(--space-2);
    font-size: var(--text-xs);
    font-weight: var(--font-medium);
    color: var(--color-text-muted);
}

.param-row {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
    margin-bottom: 6px;
}

.param-row.with-input {
    margin-top: var(--space-3);
    margin-bottom: 0;
}

/* 数值输入行空间有限：中文标签不压缩，英文备注让位，避免中文被挤成竖排 */
.param-row.with-input .param-label {
    flex-shrink: 0;
    white-space: nowrap;
}

.param-row.with-input .param-en {
    display: none;
}

.param-label {
    display: flex;
    align-items: baseline;
    gap: var(--space-2);
    min-width: 0;
    font-size: var(--text-sm);
    color: var(--color-text);
}

.param-en {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    white-space: nowrap;
}

.param-value {
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text);
    font-variant-numeric: tabular-nums;
}

.param-scale {
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

.panel-hint {
    margin-top: var(--space-1);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

/* 滑块降权：细轨道 + 小圆点，避免两条满格蓝条压过对话区 */
.panel-group :deep(.arco-slider) {
    margin: 0;
}

.panel-group :deep(.arco-slider-road),
.panel-group :deep(.arco-slider-bar) {
    height: 3px;
}

.panel-group :deep(.arco-slider-road) {
    background: var(--color-gray-100);
}

.panel-group :deep(.arco-slider-button) {
    width: 12px;
    height: 12px;
    border: 2px solid var(--color-primary);
    background: var(--color-white);
}

.usage-row {
    display: flex;
    justify-content: space-between;
    font-family: var(--font-mono);
    font-size: var(--text-xs);
    color: var(--color-text-secondary);
    font-variant-numeric: tabular-nums;
}

.context-label,
.context-value {
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

.context-label {
    margin-top: var(--space-3);
}

.context-value {
    margin-top: 4px;
    font-family: var(--font-mono);
    font-variant-numeric: tabular-nums;
}

.context-bar {
    height: 6px;
    margin-top: 6px;
    border-radius: var(--radius-sm);
    background: var(--color-gray-100);
    overflow: hidden;
}

.context-fill {
    height: 100%;
    border-radius: var(--radius-sm);
    background: var(--color-violet);
    transition: width var(--transition-base);
}

.panel-note {
    padding-top: var(--space-3);
    border-top: 1px solid var(--color-border);
    font-size: var(--text-xs);
    color: var(--color-text-muted);
}

/* 下拉选项：名称单行省略 */
.model-option {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: var(--space-2);
}

.model-option-name {
    overflow: hidden;
    text-overflow: ellipsis;
    white-space: nowrap;
}

.model-option-desc {
    flex-shrink: 1;
    max-width: 150px;
    font-size: var(--text-xs);
    color: var(--color-text-muted);
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
}
</style>
