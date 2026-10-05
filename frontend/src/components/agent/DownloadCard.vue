<!-- 导出文件下载卡片：一次性链接（24h 过期），点击新窗口下载 -->
<template>
  <div class="download-card">
    <icon-download class="download-icon"/>
    <div class="download-info">
      <div class="download-label">{{ download.label }}</div>
      <div class="download-meta">{{ download.size }} · {{ download.expiresAt }} 前有效 · 链接一次性</div>
    </div>
    <a-button size="mini" type="outline" @click="handleDownload">下载 zip</a-button>
  </div>
</template>

<script setup lang="ts">
import {API_BASE} from '@/api/request'
import {useUserStore} from '@/stores/user'
import type {agentDownload} from '@/types'

const props = defineProps<{ download: agentDownload }>()

function handleDownload() {
    // 导出端点带 Bearer 鉴权，直接 window.open 无法带头；用 fetch 拿 blob 再触发保存
    const userStore = useUserStore()
    fetch(`${API_BASE}${props.download.url}`, {
        headers: userStore.token ? {Authorization: `Bearer ${userStore.token}`} : {},
    }).then(async resp => {
        if (!resp.ok) throw new Error(`下载失败（${resp.status}）`)
        const blob = await resp.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = `agenticapi-export-${Date.now()}.zip`
        a.click()
        URL.revokeObjectURL(url)
    }).catch(() => {
        window.open(`${API_BASE}${props.download.url}`, '_blank')
    })
}
</script>

<style scoped>
.download-card {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  background: var(--color-white);
  margin-bottom: var(--space-2);
  font-size: var(--text-xs);
}

.download-icon {
  color: var(--color-primary);
  font-size: 16px;
  flex-shrink: 0;
}

.download-info {
  min-width: 0;
  flex: 1;
}

.download-label {
  font-weight: var(--font-medium);
  color: var(--color-text);
}

.download-meta {
  color: var(--color-text-muted);
  margin-top: 1px;
}
</style>
