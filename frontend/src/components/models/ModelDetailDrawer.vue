<!-- 模型详情抽屉：详情（只读）/ 示例 / 配置（仅管理员）三个标签 -->
<!-- 保存与删除只抛事件，接口调用与列表刷新由父级（模型广场页面）处理 -->

<template>
  <a-drawer
      v-model:visible="visible"
      :title="`模型详情：${model?.name || ''}`"
      :width="620"
      :mask-closable="true"
      unmount-on-close
  >
    <a-tabs v-model:active-key="activeDetailTab">
      <!-- ═══════════ 标签1：详情（只读展示，所有用户可见） ═══════════ -->
      <a-tab-pane key="detail" title="详情">
        <a-descriptions :column="2" bordered size="medium">
          <a-descriptions-item label="模型名称" :span="2">
            <span class="detail-model-name">
              <LobeIcon :name="model?.icon" :fallback="model?.name" :size="18"/>
              {{ model?.name }}
            </span>
          </a-descriptions-item>
          <a-descriptions-item label="标签">{{ model?.label || '-' }}</a-descriptions-item>
          <a-descriptions-item label="分组">{{ model?.modelGroup }}</a-descriptions-item>
          <a-descriptions-item label="状态">
            <a-tag :color="model?.status ? 'green' : 'red'" size="small">
              {{ model?.status ? '启用' : '停用' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="支持视觉">
            <a-tag :color="model?.supportVision ? 'green' : 'gray'" size="small">
              {{ model?.supportVision ? '支持' : '不支持' }}
            </a-tag>
          </a-descriptions-item>
          <a-descriptions-item label="上下文长度">{{ formatNumber(model?.contextLength) }}</a-descriptions-item>
          <a-descriptions-item label="最大输出">{{ formatNumber(model?.maxTokens) }}</a-descriptions-item>
          <a-descriptions-item label="计费模式" :span="2">
            {{ model?.isRequestMode ? '按次计费' : '按 Token 计费' }}
          </a-descriptions-item>
          <!-- 按计费模式展示价格 -->
          <a-descriptions-item v-if="model?.isRequestMode" label="每请求价格" :span="2">
            {{ model?.perRequestPrice }} 元/次
          </a-descriptions-item>
          <template v-else>
            <a-descriptions-item label="输入价格">{{ model?.inputPrice }} 元/1M</a-descriptions-item>
            <a-descriptions-item label="缓存价格">{{ model?.cachePrice }} 元/1M</a-descriptions-item>
            <a-descriptions-item label="输出价格" :span="2">{{ model?.outputPrice }} 元/1M
            </a-descriptions-item>
          </template>
          <a-descriptions-item label="模型描述" :span="2">{{ model?.description || '-' }}</a-descriptions-item>
        </a-descriptions>
      </a-tab-pane>

      <!-- ═══════════ 标签2：示例（接入信息 + curl/Python 调用示例，所有用户可见） ═══════════ -->
      <a-tab-pane key="example" title="示例">
        <ModelExamplePanel :model="model"/>
      </a-tab-pane>

      <!-- ═══════════ 标签3：配置（仅管理员可见） ═══════════ -->
      <a-tab-pane v-if="userStore.isAdmin" key="config" title="配置">
        <ModelConfigForm :form="configForm" :channel-name-list="channelNameList"/>
      </a-tab-pane>
    </a-tabs>

    <!-- 底部操作按钮（保存/删除针对的是"配置"标签，仅管理员可见） -->
    <template #footer>
      <div v-if="userStore.isAdmin" class="drawer-footer">
        <a-button status="danger" @click="emit('delete', model?.name || '')">删除模型</a-button>
        <div class="drawer-footer-spacer"></div>
        <a-button @click="visible = false">取消更改</a-button>
        <a-button type="primary" @click="handleSave">保存配置</a-button>
      </div>
    </template>
  </a-drawer>
</template>

<script setup lang="ts">
import {reactive, ref, watch} from 'vue'
import {Message} from '@arco-design/web-vue'
import {useUserStore} from '@/stores/user'
import {createEmptyModelForm} from '@/utils/model'
import LobeIcon from '@/components/common/LobeIcon.vue'
import ModelExamplePanel from '@/components/models/ModelExamplePanel.vue'
import ModelConfigForm from '@/components/models/ModelConfigForm.vue'
import type {modelInfoSchema} from '@/types'

const props = defineProps<{
  model: modelInfoSchema | null
  channelNameList: string[]
}>()

const emit = defineEmits<{
  save: [form: modelInfoSchema]
  delete: [modelName: string]
}>()

const visible = defineModel<boolean>('visible', {default: false})

const userStore = useUserStore()

// 当前激活的标签页：detail / example / config
const activeDetailTab = ref('detail')

// 配置表单数据（"配置"标签使用）
const configForm = reactive<modelInfoSchema>(createEmptyModelForm())

// 打开抽屉时：回到"详情"标签，并把当前模型配置回填到表单（确保数字字段类型正确）
watch(visible, (visible) => {
  if (!visible) return
  activeDetailTab.value = 'detail'
  const model = props.model
  if (!model) return
  Object.assign(configForm, {
    name: model.name ?? '',
    upstreamName: model.upstreamName ?? '',
    modelGroup: model.modelGroup ?? '',
    label: model.label ?? '',
    icon: model.icon ?? '',
    channels: [...(model.channels ?? [])],
    isRequestMode: model.isRequestMode ?? false,
    perRequestPrice: Number(model.perRequestPrice) || 0,
    inputPrice: Number(model.inputPrice) || 0,
    cachePrice: Number(model.cachePrice) || 0,
    outputPrice: Number(model.outputPrice) || 0,
    isPin: model.isPin ?? false,
    isLog: model.isLog ?? false,
    status: model.status ?? false,
    supportVision: model.supportVision ?? false,
    contextLength: Number(model.contextLength) || 128,
    maxTokens: Number(model.maxTokens) || 4196,
    description: model.description ?? '',
  })
})

// 保存配置：表单快照抛给父级调接口（父级按模型名定位更新）
function handleSave() {
  if (!configForm.name) {
    Message.error('未选择模型')
    return
  }
  emit('save', {...configForm})
}

// 数字加千分位（上下文长度、最大输出这类大数字更易读）
const formatNumber = (value: any) => {
  const num = parseInt(value)
  return Number.isFinite(num) ? num.toLocaleString() : '-'
}
</script>

<style scoped>
.drawer-footer {
  display: flex;
  justify-content: flex-end;
  gap: var(--space-2);
}

.drawer-footer-spacer {
  flex: 1;
}

/* 详情里的模型名（图标 + 名称） */
.detail-model-name {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  font-weight: var(--font-medium);
}
</style>
