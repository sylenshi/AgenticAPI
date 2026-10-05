import { createRouter, createWebHistory } from 'vue-router'
import { Message } from '@arco-design/web-vue'
import {useUserStore} from '@/stores/user'
// 下面是第一级路由的组件
import Home from '@/views/home/index.vue'
import Models from '@/views/models/index.vue'
import Monitor from '@/views/monitor/index.vue'
import Studio from '@/views/studio/index.vue'
import Dashboard from '@/views/Dashboard/index.vue'
import Docs from '@/views/docs/index.vue'

// 下面是第二路由的组件
import Overview from '@/views/Dashboard/Overview.vue'
import Keys from '@/views/Dashboard/Keys.vue'
import Channels from '@/views/Dashboard/Channels.vue'
import UserList from '@/views/Dashboard/UserList.vue'
import RedemptionCodes from '@/views/Dashboard/RedemptionCodes.vue'
import Operations from '@/views/Dashboard/Operations.vue'
import Security from '@/views/Dashboard/Security.vue'
import AgentChat from '@/views/Dashboard/AgentChat.vue'

const router = createRouter({
    history: createWebHistory(), // 历史模式
    routes: [
        // 重定向首页到 /home
        {
            path: '/',
            redirect: '/home'
        },
        // 定义路由
        {
            name: 'Home',
            path: '/home',
            component: Home
        },
        {
            name: 'Models',
            path: '/models',
            component: Models
        },
        {
            name: 'Monitor',
            path: '/monitor',
            component: Monitor,
            // 监控面板展示个人数据与日志，需要登录后访问
            meta: { requiresAuth: true }
        },
        // 旧"路由模型"页已下线，保留跳转兼容旧链接
        {
            path: '/routes',
            redirect: '/monitor'
        },
        {
            name: 'Studio',
            path: '/studio',
            component: Studio,
            // 模型工坊对话走登录态调用（不计费但需登录），需要登录后访问
            meta: { requiresAuth: true }
        },
        // 定义 Dashboard 路由
        {
            name: 'Dashboard',
            path: '/dashboard',
            component: Dashboard,
            // 需要登录才能访问：子路由会继承这个标记（访客同样被拦截）
            meta: { requiresAuth: true },
            // 定义 Dashboard 子路由，也就是在后台控制台中展示的页面
            children: [
                // 重定向到 Overview 页面
                {
                    name: 'DashboardRedirect',
                    path: '',
                    redirect: '/dashboard/overview'
                },
                {
                    name: 'Overview',
                    path: 'overview',
                    component: Overview
                },
                {
                    name: 'Keys',
                    path: 'keys',
                    component: Keys
                },
                {
                    name: 'Channels',
                    path: 'channels',
                    component: Channels,
                    meta: { requiresAdmin: true }
                },
                {
                    name: 'UserList',
                    path: 'userlist',
                    component: UserList,
                    meta: { requiresAdmin: true }
                },
                {
                    name: 'RedemptionCodes',
                    path: 'redemptioncodes',
                    component: RedemptionCodes
                },
                {
                    name: 'Operations',
                    path: 'operations',
                    component: Operations,
                    meta: { requiresAdmin: true }
                },
                {
                    name: 'AgentChat',
                    path: 'agent',
                    component: AgentChat,
                    // 站点维护 Agent（对话式运维：白名单工具 + 人审阀门），仅管理员
                    meta: { requiresAdmin: true }
                },
                {
                    name: 'Security',
                    path: 'security',
                    component: Security
                }
            ]
        },
        {
            name: 'Docs',
            path: '/docs',
            component: Docs
        }
    ]
})

// 全局前置守卫：需要登录的页面分级准入
// - 未登录：唤起登录弹窗并中断跳转（登录成功后按 store 里记录的目标页跳回）
// - 管理页（requiresAdmin）：非管理员拦截（访客与普通用户同权限，均可进入概览/秘钥页）
async function ensureUserInfo(userStore: ReturnType<typeof useUserStore>) {
    // 刷新页面后 store 里只有令牌没有用户信息，先拉一次（令牌无效会被拦截器清理并弹登录框）
    if (userStore.token && !userStore.userInfo) {
        await userStore.fetchUserInfo().catch(() => undefined)
    }
    return userStore.userInfo
}

router.beforeEach(async (to) => {
    const userStore = useUserStore()
    // requiresAuth 由父路由声明，子路由自动继承（控制台与监控面板都需要登录）
    if (!to.meta.requiresAuth) return true

    if (!userStore.token) {
        userStore.openAuthDialog('login', to.fullPath)
        return false
    }

    const info = await ensureUserInfo(userStore)
    if (!info) return false // 令牌已失效，拦截器已清理登录态并弹出登录框

    if (to.meta.requiresAdmin && !info.isAdmin) {
        Message.warning('需要管理员权限')
        return false
    }
    return true
})

export default router