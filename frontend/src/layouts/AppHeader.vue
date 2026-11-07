<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Message } from '@arco-design/web-vue'
// 顶栏小尺寸主标：由 src/assets/brand/logosmall.png 生成（首屏节点用 logo.png）
import logoImage from '@/assets/images/logo-icon.png'
import { navItems } from '@/constants/nav'
import { useUserStore } from '@/stores/user'
import { confirmDialog } from '@/utils/feedback'
import { formatAmount } from '@/utils/format'
import AuthDialog from '@/components/auth/AuthDialog.vue'
import GuestDialog from '@/components/auth/GuestDialog.vue'

// 监听路由变化，更新激活的导航项
const route = useRoute()
const router = useRouter()
const activeIndex = ref(0)
const updateActiveIndex = () => {
  const currentPath = route.path
  const index = navItems.findIndex(item => {
    // 精确匹配
    if (item.to === currentPath) return true
    // 前缀匹配：当前路径以导航路径开头，且导航路径是 /dashboard 这种有子路由的情况
    return (item.to !== '/' && currentPath.startsWith(item.to + '/'));
  })
  if (index !== -1) {
    activeIndex.value = index
  }
}
watch(() => route.path, updateActiveIndex, {immediate: true})

/** ═══════════ 登录态与弹窗 ═══════════ */

// 用户登录状态（注册/登录弹窗的状态也在 store 里，AuthDialog 直接读写）
const userStore = useUserStore()

// 访客注意事项弹窗（局部状态即可，只有这里会打开它）
const guestDialogVisible = ref(false)

// 当前用户头像URL（预设6选1，后端下发；空值回退显示首字符圆标）
const avatarUrl = computed(() => userStore.userInfo?.avatar || '')

// 余额展示（下拉菜单）：金额为字符串下发，统一走 formatAmount 保精度，缺值按 0.00 展示
const balanceText = computed(() => formatAmount(userStore.userInfo?.balance, 2, '0.00'))

// 登出：确认后删除服务端令牌；若正处在控制台等需登录页面，则回到首页
const handleLogout = async () => {
  const confirmed = await confirmDialog('确定退出登录吗？', '退出登录', '退出登录', true)
  if (!confirmed) return

  await userStore.logoutAction()
  Message.success('已退出登录')
  if (route.path.startsWith('/dashboard')) {
    router.push('/home')
  }
}

// 切换头像：后端从预设 6 张中随机换一张（与当前不同），返回的用户信息回填后导航栏即时更新
const handleUpdateAvatar = async () => {
  try {
    await userStore.updateAvatarAction()
    Message.success('头像已切换')
  } catch (error) {
    // 失败提示由请求层统一弹出，这里无需重复处理
    console.warn('切换头像失败:', error)
  }
}

// 下拉菜单展开时刷新一次用户信息：余额随调用/兑换实时变化，展开即见最新值
const handleDropdownVisibleChange = (visible: boolean) => {
  if (visible) void userStore.fetchUserInfo()
}

// 已登录用户下拉菜单：余额跳转概览、切换头像、退出登录
const handleUserCommand = (key: string | number | Record<string, unknown> | undefined) => {
  const command = String(key)
  if (command === 'balance') {
    router.push('/dashboard/overview')
  } else if (command === 'avatar') {
    void handleUpdateAvatar()
  } else if (command === 'logout') {
    void handleLogout()
  }
}
</script>


<template>
  <!-- 【导航栏】最顶部导航栏区域 -->
  <header class="app-header">
    <div class="header-inner container flex-between">
      <!-- 【导航栏左侧】品牌与LOGO -->
      <RouterLink class="header-brand" to="/home">
        <img class="brand-logo-img" :src="logoImage" alt="AgenticAPI Logo"/>
        <span class="brand-text">Agentic<span class="brand-accent">API</span></span>
      </RouterLink>

      <!-- 【导航栏居中】导航菜单 -->
      <nav class="header-nav" aria-label="主导航">
        <ul class="nav-list">
          <li v-for="(item, index) in navItems" :key="item.id">
            <RouterLink :to="item.to" class="nav-link" :class="{ active: activeIndex === index }">
              {{ item.label }}
            </RouterLink>
          </li>
        </ul>
      </nav>

      <!-- 【导航栏右侧】未登录显示 访客/登录/注册，已登录显示 用户下拉 -->
      <div class="header-actions">
        <template v-if="!userStore.isLoggedIn">
          <a-button type="text" size="small" @click="guestDialogVisible = true">访客</a-button>
          <a-button size="small" @click="userStore.openAuthDialog('login')">登录</a-button>
          <a-button type="primary" size="small" @click="userStore.openAuthDialog('register')">免费注册</a-button>
        </template>


        <template v-else>
          <a-dropdown trigger="click" @select="handleUserCommand" @popup-visible-change="handleDropdownVisibleChange">

            <a class="user-entry" href="javascript:void(0)">
              <!-- 有预设头像显示图片（overflow:hidden 由 Arco avatar 自带，裁成圆形），否则回退首字符 -->
              <a-avatar v-if="avatarUrl" :size="32" class="user-avatar user-avatar-img">
                <img :src="avatarUrl" alt="头像"/>
              </a-avatar>
              <a-avatar v-else :size="32" class="user-avatar">{{ userStore.displayName.charAt(0) }}</a-avatar>
              <span class="user-name" :title="userStore.displayName">{{ userStore.displayName }}</span>
              <icon-down class="user-arrow"/>
            </a>

            <template #content>
              <a-doption value="balance" class="user-balance-option">
                <template #icon><icon-safe/></template>
                余额 {{ balanceText }} 元
              </a-doption>
              <a-doption value="avatar">
                <template #icon><icon-swap/></template>
                切换头像
              </a-doption>
              <a-doption value="logout" class="user-logout-option">
                <template #icon><icon-export/></template>
                退出登录
              </a-doption>
            </template>
          </a-dropdown>
        </template>
      </div>
    </div>
  </header>

  <!-- 全局登录/注册弹窗与访客注意事项弹窗 -->
  <AuthDialog/>
  <GuestDialog v-model:visible="guestDialogVisible"/>
</template>


<style scoped>
.app-header {
  position: sticky;
  top: 0;
  z-index: 50;
  height: var(--layout-header-height);
  /* 顶栏与首页保持改版前的字体：品牌字走 --font-display，导航走系统字体链 */
  --font-sans: 'Public Sans Variable', 'Public Sans', 'HarmonyOS Sans SC', 'MiSans', 'PingFang SC', 'Microsoft YaHei', system-ui, -apple-system, 'Segoe UI', Arial, sans-serif;
  font-family: var(--font-sans);
  letter-spacing: normal;
  /* 毛玻璃：半透明白底 + 背景模糊，内容从栏下滚过时有景深（克制档） */
  background-color: rgba(255, 255, 255, 0.85);
  -webkit-backdrop-filter: saturate(180%) blur(8px);
  backdrop-filter: saturate(180%) blur(8px);
  border-bottom: 1px solid var(--color-border);
}

/* 不支持 backdrop-filter 的浏览器退回实底，保证可读性 */
@supports not ((backdrop-filter: blur(1px)) or (-webkit-backdrop-filter: blur(1px))) {
  .app-header {
    background-color: var(--color-white);
  }
}

.header-inner {
  height: 100%;
}

/* 品牌区 */
.header-brand {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  text-decoration: none;
  color: var(--color-text);
  font-weight: var(--font-bold);
  transition: opacity var(--transition-fast);
}

.header-brand:hover {
  opacity: 0.85;
}

.brand-logo-img {
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  object-fit: contain;
}

/* 品牌字：英文展示衬线 Playfair Display（纯英文品牌名直接命中字体栈首个），
   800 字重醒目，"API" 用品牌色点亮 */
.brand-text {
  font-family: var(--font-display);
  font-size: var(--text-xl);
  font-weight: 800;
  letter-spacing: -0.01em;
  color: var(--color-text);
}

.brand-accent {
  color: var(--color-primary);
}

/* 导航菜单：贴齐底部高度，激活态用主色 + 底部指示条 */
.header-nav {
  display: none;
  align-self: stretch;
}

@media (min-width: 769px) {
  .header-nav {
    display: flex;
  }
}

.nav-list {
  display: flex;
  align-items: stretch;
  gap: var(--space-1);
  list-style: none;
  margin: 0;
  padding: 0;
  height: 100%;
}

.nav-list li {
  display: flex;
  align-items: stretch;
}

.nav-link {
  position: relative;
  display: flex;
  align-items: center;
  padding: 0 var(--space-3);
  font-size: var(--text-sm);
  color: var(--color-text-secondary);
  text-decoration: none;
  transition: color var(--transition-fast);
}

.nav-link::after {
  content: '';
  position: absolute;
  left: var(--space-2);
  right: var(--space-2);
  bottom: 0;
  height: 2px;
  border-radius: 1px;
  background-color: transparent;
  transition: background-color var(--transition-fast);
}

.nav-link:hover {
  color: var(--color-primary);
}

.nav-link.active {
  color: var(--color-primary);
  font-weight: var(--font-medium);
}

.nav-link.active::after {
  background-color: var(--color-primary);
}

/* 右侧操作 */
.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-2);
}

/* 已登录：用户下拉入口 */
.user-entry {
  display: inline-flex;
  align-items: center;
  gap: var(--space-2);
  padding: var(--space-1) var(--space-2);
  border-radius: var(--radius-full);
  text-decoration: none;
  color: var(--color-text);
  transition: background-color var(--transition-fast);
}

.user-entry:hover {
  background-color: var(--color-gray-100);
}

.user-avatar {
  background-color: var(--color-primary);
  color: var(--color-on-primary);
  font-size: 13px;
  font-weight: var(--font-semibold);
}

/* 图片头像：img 撑满圆框裁剪（Arco avatar 自带 overflow:hidden 兜底） */
.user-avatar-img img {
  width: 100%;
  height: 100%;
  object-fit: cover;
}

/* 下拉菜单：余额数字等宽对齐（UI 规范数字口径） */
.user-balance-option {
  font-variant-numeric: tabular-nums;
}

/* 退出登录与上方两项（余额/换头像）之间加分隔线 */
.user-logout-option {
  margin-top: 4px;
  border-top: 1px solid var(--color-border);
}

.user-name {
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  font-size: var(--text-base);
  font-weight: var(--font-medium);
}

.user-arrow {
  color: var(--color-text-muted);
  font-size: 13px;
}
</style>
