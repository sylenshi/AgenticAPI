<!-- 渠道配置管理 -->

<template>
  <div class="channels-page">
    <!-- 【顶部操作栏】标题、搜索框、操作按钮 -->
    <header class="page-head">
      <h2>渠道配置</h2>
      <div class="action-bar">
        <a-input v-model="searchKeyword" placeholder="搜索渠道名称" allow-clear class="search-box">
          <template #prefix>
            <icon-search/>
          </template>
        </a-input>
        <div class="action-buttons">
          <a-button :loading="loading" @click="fetchChannels">
            <template #icon>
              <icon-refresh/>
            </template>
            刷新
          </a-button>
          <a-button type="primary" @click="openAddDrawer">
            <template #icon>
              <icon-plus/>
            </template>
            添加渠道
          </a-button>
        </div>
      </div>
    </header>

    <!-- 【渠道列表】表格展示：白卡容器与其他控制台页统一 -->
    <div class="page-card">
      <a-table
          :data="filteredChannels"
          :loading="loading"
          :columns="columns"
          row-key="channelName"
          :bordered="{wrapper: true}"
          :pagination="false"
          :scroll="{x: 900}"
          size="small"
      >
        <template #status="{ record }">
          <!-- 单向绑定，切换时调接口，成功后才更新本地状态 -->
          <a-switch :model-value="record.status"
                    @change="(val: string | number | boolean) => handleStatusChange(record, Boolean(val))"/>
        </template>
        <template #operations="{ record }">
          <a-button type="text" size="small" @click="openEditDrawer(record)">编辑</a-button>
        </template>
      </a-table>
    </div>

    <!-- 【新增/编辑抽屉】复用同一表单，通过 dialogMode 区分 -->
    <a-drawer
        v-model:visible="drawerVisible"
        :title="drawerTitle"
        :width="520"
        :mask-closable="true"
        unmount-on-close
    >
      <a-form :model="channelForm" layout="vertical">
        <!-- 基本信息 -->
        <div class="config-section">
          <h5>基本信息</h5>
          <a-form-item label="渠道名称">
            <!-- 编辑模式下渠道名称不可修改（后端不允许更新 channel_name） -->
            <a-input
                v-model="channelForm.channelName"
                :disabled="dialogMode === 'edit'"
                placeholder="例如: openai-main"
            />
          </a-form-item>
          <a-form-item label="Base URL">
            <a-input v-model="channelForm.baseUrl" placeholder="例如: https://api.openai.com/v1"/>
          </a-form-item>
          <a-form-item label="API Key">
            <a-input-password v-model="channelForm.apiKey" placeholder="sk-..." allow-clear/>
          </a-form-item>
          <a-form-item label="支持模型">
            <div class="tag-input-wrap">
              <a-tag
                  v-for="(m, i) in channelForm.supportModels"
                  :key="i"
                  closable
                  size="small"
                  @close="channelForm.supportModels.splice(i, 1)"
              >{{ m }}
              </a-tag>
              <div class="tag-input-row">
                <a-input
                    v-model="newModelInput"
                    size="small"
                    placeholder="输入模型名后回车或点 + 添加"
                    :style="{width: 220}"
                    @press-enter="addModelTag"
                />
                <a-button size="small" @click="addModelTag">
                  <template #icon>
                    <icon-plus/>
                  </template>
                </a-button>
              </div>
            </div>
          </a-form-item>
          <a-form-item label="描述">
            <a-textarea v-model="channelForm.description" placeholder="渠道备注信息" :max-length="200"
                        :auto-size="{minRows: 2, maxRows: 4}"/>
          </a-form-item>
        </div>

        <a-divider/>

        <!-- 运行参数 -->
        <div class="config-section">
          <h5>运行参数</h5>
          <a-form-item label="状态">
            <a-switch v-model="channelForm.status"/>
            <span class="switch-hint">{{ channelForm.status ? '启用' : '禁用' }}</span>
          </a-form-item>
          <a-form-item label="超时（秒）">
            <a-input-number v-model="channelForm.timeout" :min="1" :max="600" :step="5" mode="button"/>
          </a-form-item>
        </div>
      </a-form>

      <!-- 底部操作按钮 -->
      <template #footer>
        <div class="drawer-footer">
          <a-button
              v-if="dialogMode === 'edit'"
              type="text"
              status="danger"
              @click="handleDelete(channelForm)"
          >删除渠道
          </a-button>
          <div class="drawer-footer-actions">
            <a-button @click="drawerVisible = false">取消</a-button>
            <a-button type="primary" :loading="submitting" @click="handleSubmit">
              {{ dialogMode === 'add' ? '添加' : '保存' }}
            </a-button>
          </div>
        </div>
      </template>
    </a-drawer>
  </div>
</template>

<script setup lang="ts">
import {ref, reactive, computed, onMounted} from 'vue'
import {Message} from '@arco-design/web-vue'
import type {TableColumnData} from '@arco-design/web-vue'
import {getChannels, addChannel, updateChannel, deleteChannel} from '@/api/channels'
import {getErrorMessage} from '@/api/request'
import {confirmDialog} from '@/utils/feedback'
import type {channelInfoSchema} from '@/types'

/** ═══════════ 列表与筛选 ═══════════ */

const columns: TableColumnData[] = [
  {title: '渠道名称', dataIndex: 'channelName', width: 150},
  {title: '状态', slotName: 'status', width: 80, align: 'center'},
  {title: 'Base URL', dataIndex: 'baseUrl', minWidth: 220, ellipsis: true, tooltip: true},
  {title: '支持模型', dataIndex: 'supportModels', minWidth: 180, ellipsis: true, tooltip: true},
  {title: '超时(秒)', dataIndex: 'timeout', width: 100, align: 'center'},
  {title: '操作', slotName: 'operations', width: 130, align: 'center'},
]

const loading = ref(false)              // 表格加载状态
const searchKeyword = ref('')           // 搜索关键字
const channels = ref<channelInfoSchema[]>([])  // 全量渠道列表

// 按渠道名称过滤
const filteredChannels = computed(() => {
  const kw = searchKeyword.value.trim().toLowerCase()
  if (!kw) return channels.value
  return channels.value.filter(c => c.channelName.toLowerCase().includes(kw))
})

// 获取全量渠道列表
const fetchChannels = () => {
  loading.value = true
  getChannels()
      .then(res => {
        channels.value = res.data
      })
      .catch(err => {
        console.error(err)
        Message.error(getErrorMessage(err, '获取渠道列表失败'))
      })
      .finally(() => {
        loading.value = false
      })
}


/** ═══════════ 新增 / 编辑 ═══════════ */

const drawerVisible = ref(false)                    // 抽屉是否可见
const dialogMode = ref<'add' | 'edit'>('add')       // 当前抽屉模式
const submitting = ref(false)                       // 提交中状态

// 表单数据（新增/编辑共用；描述在表单里按字符串处理，提交时一并传给后端）
type channelFormSchema = Omit<channelInfoSchema, 'description'> & { description: string }
const channelForm = reactive<channelFormSchema>({
  channelName: '',
  baseUrl: '',
  apiKey: '',
  supportModels: [],
  status: true,
  timeout: 30,
  usedRatio: 0,
  description: '',
})

// 抽屉标题随模式变化
const drawerTitle = computed(() =>
    dialogMode.value === 'add' ? '添加新渠道' : `编辑渠道：${channelForm.channelName}`
)

// 重置表单为默认值
const resetForm = () => {
  Object.assign(channelForm, {
    channelName: '',
    baseUrl: '',
    apiKey: '',
    supportModels: [],
    status: true,
    timeout: 30,
    usedRatio: 0,
    description: '',
  })
}

// 支持模型的逐个添加：输入框 + 加号按钮，回车也可添加
const newModelInput = ref('')
const addModelTag = () => {
  const v = newModelInput.value.trim()
  if (!v) return
  // 去重，避免重复添加同一模型名
  if (!channelForm.supportModels.includes(v)) {
    channelForm.supportModels.push(v)
  }
  newModelInput.value = ''
}

// 打开新增抽屉
const openAddDrawer = () => {
  dialogMode.value = 'add'
  resetForm()
  drawerVisible.value = true
}

// 打开编辑抽屉，并回填当前行数据
const openEditDrawer = (row: channelInfoSchema) => {
  dialogMode.value = 'edit'
  Object.assign(channelForm, {
    channelName: row.channelName ?? '',
    baseUrl: row.baseUrl ?? '',
    apiKey: row.apiKey ?? '',
    // 拷贝数组：supportModels 直接引用行数据的话，抽屉里的增删会原地改到表格行
    supportModels: [...(row.supportModels ?? [])],
    status: row.status ?? true,
    timeout: Number(row.timeout) || 30,
    usedRatio: Number(row.usedRatio) || 0,
    description: row.description ?? '',
  })
  drawerVisible.value = true
}

// 提交表单：根据模式调用新增或更新接口
const handleSubmit = () => {
  if (!channelForm.channelName.trim()) {
    Message.error('渠道名称不能为空')
    return
  }
  submitting.value = true
  if (dialogMode.value === 'add') {
    // 新增：POST 全量字段
    addChannel({...channelForm})
        .then(() => {
          Message.success('添加渠道成功')
          drawerVisible.value = false
          fetchChannels()
        })
        .catch(err => {
          console.error(err)
          Message.error(getErrorMessage(err, '添加渠道失败'))
        })
        .finally(() => {
          submitting.value = false
        })
  } else {
    // 更新：PUT 全量字段（按 channelName 定位，且 channelName 不会被更新）
    updateChannel(channelForm.channelName, {...channelForm})
        .then(() => {
          Message.success('保存配置成功')
          drawerVisible.value = false
          fetchChannels()
        })
        .catch(err => {
          console.error(err)
          Message.error(getErrorMessage(err, '保存配置失败'))
        })
        .finally(() => {
          submitting.value = false
        })
  }
}

/** ═══════════ 状态快速切换 ═══════════ */

// 表格内 switch 切换状态：只更新 status 字段，失败时重新拉取列表以恢复真实状态
const handleStatusChange = (row: channelInfoSchema, val: boolean) => {
  updateChannel(row.channelName, {
    channelName: row.channelName,
    status: val,
  })
      .then(() => {
        row.status = val
        Message.success('状态已更新')
      })
      .catch(err => {
        console.error(err)
        Message.error(getErrorMessage(err, '状态更新失败'))
        fetchChannels()
      })
}

/** ═══════════ 删除 ═══════════ */

const handleDelete = async (row: channelInfoSchema) => {
  const confirmed = await confirmDialog(
      `确定要删除渠道 "${row.channelName}" 吗？此操作不可恢复。`,
      '删除确认', '确定删除', true,
  )
  if (!confirmed) return
  // 删除接口通过路径参数传渠道名
  try {
    await deleteChannel(row.channelName)
    Message.success('渠道删除成功')
    drawerVisible.value = false
    fetchChannels()
  } catch (err) {
    console.error(err)
    Message.error(getErrorMessage(err, '渠道删除失败'))
  }
}

/** ═══════════ 初始化 ═══════════ */

onMounted(() => {
  fetchChannels()
})
</script>

<style scoped>
.channels-page {
  padding: var(--space-5) var(--space-6);
}

/* 顶部操作栏 */
.action-bar {
  display: flex;
  align-items: center;
  gap: var(--space-3);
}

.search-box {
  flex: 1;
  max-width: 320px;
  margin-left: auto;
}

.action-buttons {
  display: flex;
  gap: var(--space-2);
}

/* 抽屉表单 */
.config-section {
  margin-bottom: var(--space-2);
}

.config-section h5 {
  margin: 0 0 var(--space-3);
  color: var(--color-text);
  font-weight: var(--font-semibold);
  font-size: var(--text-sm);
}

.unit {
  margin-left: var(--space-2);
  color: var(--color-text-muted);
  font-size: var(--text-xs);
}

.switch-hint {
  margin-left: var(--space-2);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
}

.tag-input-wrap {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: var(--space-1);
  width: 100%;
}

.tag-input-row {
  display: flex;
  gap: var(--space-1);
  align-items: center;
}

.drawer-footer {
  display: flex;
  justify-content: space-between;
  gap: var(--space-2);
}


.drawer-footer-actions {
  display: flex;
  gap: var(--space-2);
}
</style>
