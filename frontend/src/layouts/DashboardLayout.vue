<!-- 控制台布局外壳：侧边栏 + 主内容插槽（火山引擎控制台风格：白侧栏 + 浅灰内容区） -->

<template>
  <div class="dashboard-layout">
    <!-- 侧边栏 -->
    <aside class="sidebar">
      <div class="sidebar-header">
        <h2 class="sidebar-title">控制台</h2>
      </div>
      <nav class="sidebar-nav" aria-label="控制台导航">
        <RouterLink
            v-for="item in visibleDashItems"
            :key="item.id"
            :to="item.to"
            class="sidebar-nav-link"
            :class="{ active: isActive(item.to) }"
        >
          <component :is="item.icon" class="sidebar-nav-icon"/>
          <span>{{ item.name }}</span>
        </RouterLink>
      </nav>
    </aside>

    <!-- 主内容区域 -->
    <main class="dashboard-main">
      <!-- 内容列：宽度封顶居中（大屏下控制台内容不再无限拉伸，两侧留灰底呼吸） -->
      <div class="dashboard-container">
        <slot/>
      </div>
    </main>
  </div>
</template>

<script setup lang="ts">
import {computed} from 'vue'
import {useRoute} from 'vue-router'
import {dashItems} from '@/constants/nav'
import {useUserStore} from '@/stores/user'

const route = useRoute()
const userStore = useUserStore()

const isActive = (path: string) => {
  return route.path === path
}

// 按角色过滤侧边栏：
// - 概览/秘钥/兑换：所有登录用户可见（访客与普通用户同权限，兑换页内管理区块按角色分支）
// - 渠道/运营/用户：仅管理员可见
// - 安全：功能尚未实现，暂时隐藏
const visibleDashItems = computed(() => {
  const adminPaths = ['/dashboard/channels', '/dashboard/operations', '/dashboard/userlist', '/dashboard/security']
  return dashItems.filter(item => {
    if (item.to === '/dashboard/overview' || item.to === '/dashboard/keys' || item.to === '/dashboard/redemptioncodes') return true
    if (adminPaths.includes(item.to)) return userStore.isAdmin
    return false
  })
})
</script>

<style scoped>
.dashboard-layout {
  display: flex;
  height: 100%;
}

/* 侧边栏：白底 + 圆角菜单项，激活态浅蓝底主色字（火山引擎控制台风格） */
.sidebar {
  width: var(--layout-sidebar-width);
  background-color: var(--color-white);
  border-right: 1px solid var(--color-border);
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.sidebar-header {
  padding: var(--space-4) var(--space-4) var(--space-3);
}

.sidebar-title {
  font-size: var(--text-base);
  font-weight: var(--font-semibold);
  color: var(--color-text);
  margin: 0;
}

.sidebar-nav {
  flex: 1;
  padding: 0 var(--space-2) var(--space-3);
  overflow-y: auto;
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.sidebar-nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-2) var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  text-decoration: none;
  border-radius: var(--radius-md);
  transition: all var(--transition-fast);
}

.sidebar-nav-link:hover {
  color: var(--color-text);
  background-color: var(--color-gray-100);
}

.sidebar-nav-link.active {
  color: var(--color-primary);
  background-color: var(--color-primary-lighter);
  font-weight: var(--font-medium);
}

.sidebar-nav-icon {
  font-size: 16px;
}

/* 主内容区域：浅灰画布，页面自行放置白卡 */
.dashboard-main {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  background-color: var(--color-bg-layout);
}

/* 内容列：全站统一 1280px 封顶 + 居中，覆盖所有控制台子页 */
.dashboard-container {
  max-width: 1280px;
  margin-left: auto;
  margin-right: auto;
}

@media (max-width: 768px) {
  .sidebar {
    width: 56px;
  }

  /* 窄屏收起为纯图标侧栏 */
  .sidebar-title,
  .sidebar-nav-link span {
    display: none;
  }

  .sidebar-nav-link {
    justify-content: center;
    padding: var(--space-2);
  }
}
</style>
