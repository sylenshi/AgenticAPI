/* 用户登录状态管理
 *
 * Token 的存放分两层，各司其职：
 * - localStorage：持久化，刷新页面 / 重开浏览器后仍然在，这是"保持登录"的实现方式
 * - pinia（本文件）：内存中的响应式状态，导航栏等组件能实时感知登录/登出
 *
 * 另外统一管理全局唯一的登录/注册弹窗（导航栏按钮和路由守卫都会触发它）
 */
import {defineStore} from 'pinia'
import {ref, computed} from 'vue'
import {Message} from '@arco-design/web-vue'
import {
    login as loginApi,
    register as registerApi,
    logout as logoutApi,
    guestLogin as guestLoginApi,
    getUserInfo,
} from '@/api/user'
import type {userInfoSchema} from '@/types'

// localStorage 中存放令牌的键名
const TOKEN_KEY = 'agenticapi_token'

// 弹窗模式：登录 / 注册
export type authDialogMode = 'login' | 'register'

export const useUserStore = defineStore('user', () => { // 当前pinia的ID，必填项
    // 访问令牌（创建 store 时从 localStorage 恢复，实现刷新后仍处于登录态）
    const token = ref<string>(localStorage.getItem(TOKEN_KEY) || '')
    // 当前用户信息（仅内存，刷新后由 App.vue 调 fetchUserInfo 重新拉取）
    const userInfo = ref<userInfoSchema | null>(null)

    // 是否已登录（持有令牌即视为登录，令牌有效性由后端校验）
    const isLoggedIn = computed(() => !!token.value)

    // 是否管理员（控制台管理页面的显示与路由准入）
    const isAdmin = computed(() => !!userInfo.value?.isAdmin)

    // 展示名：优先昵称，其次用户名
    const displayName = computed(() => userInfo.value?.nickname || userInfo.value?.username || '已登录用户')


    /** ═══════════ 登录 / 注册 / 登出 ═══════════ */

    // 登录：成功后保存令牌和用户信息
    async function loginAction(data: { username: string; password: string }) {
        const res = await loginApi(data)
        setToken(res.data.token)
        userInfo.value = res.data.userInfo
        return res.data.userInfo
    }

    // 注册：后端注册成功即登录，直接保存返回的令牌
    async function registerAction(data: { username: string; password: string }) {
        const res = await registerApi(data)
        setToken(res.data.token)
        userInfo.value = res.data.userInfo
        return res.data.userInfo
    }

    // 访客模式：后端创建临时账号（24小时令牌），走和登录一致的令牌流程
    async function guestAction() {
        const res = await guestLoginApi()
        setToken(res.data.token)
        userInfo.value = res.data.userInfo
        return res.data.userInfo
    }

    // 登出：删除服务端令牌（令牌立即失效），并清空本地登录态
    async function logoutAction() {
        try {
            await logoutApi()
        } catch (error) {
            // 服务端令牌可能已过期，本地登录态照常清掉即可，不用提示错误
            console.warn('服务端登出接口调用失败:', error)
        } finally {
            clearLoginState()
        }
    }

    // 校验令牌并回填用户信息（应用启动时调用一次）
    async function fetchUserInfo() {
        if (!token.value) return
        try {
            const res = await getUserInfo()
            userInfo.value = res.data
        } catch (error) {
            // 令牌无效或已过期时请求拦截器会统一清理登录态，这里无需重复处理
            console.warn('获取用户信息失败:', error)
        }
    }


    /** ═══════════ 令牌读写（本地持久化） ═══════════ */

    function setToken(newToken: string) {
        token.value = newToken
        localStorage.setItem(TOKEN_KEY, newToken)
    }

    function clearLoginState() {
        token.value = ''
        userInfo.value = null
        localStorage.removeItem(TOKEN_KEY)
    }

    // 多标签页同步：storage 事件只在“其他标签页”写入时触发，本页写入不会收到
    // 他页登出 → 本页同步清登录态；他页登录/切换账号 → 本页采纳新令牌并重拉用户信息
    window.addEventListener('storage', (e) => {
        if (e.key !== TOKEN_KEY) return
        const newToken = e.newValue || ''
        if (newToken === token.value) return
        if (!newToken) {
            token.value = ''
            userInfo.value = null
        } else {
            token.value = newToken
            fetchUserInfo()
        }
    })


    /** ═══════════ 全局登录/注册弹窗 ═══════════ */

    const authDialogVisible = ref(false)
    const authDialogMode = ref<authDialogMode>('login')
    // 登录成功后要跳回的页面（路由守卫拦截时记录，比如用户未登录直接访问 /dashboard）
    const redirectAfterLogin = ref('')

    function openAuthDialog(mode: authDialogMode = 'login', redirect = '') {
        authDialogMode.value = mode
        redirectAfterLogin.value = redirect
        authDialogVisible.value = true
    }

    function closeAuthDialog() {
        authDialogVisible.value = false
    }

    // 取出并清空"登录后跳转目标"（登录成功后调用一次）
    function consumeRedirectAfterLogin() {
        const target = redirectAfterLogin.value
        redirectAfterLogin.value = ''
        return target
    }


    /** ═══════════ 登录态失效（供请求拦截器调用） ═══════════ */

    // 令牌缺失/无效/过期（后端返回 401/403）时：清空登录态并唤起登录弹窗
    function handleUnauthorized() {
        clearLoginState()
        if (!authDialogVisible.value) {
            Message.warning('请先登录')
            openAuthDialog('login')
        }
    }

    // 返回状态与方法
    return {
        token,
        userInfo,
        isLoggedIn,
        isAdmin,
        displayName,
        loginAction,
        registerAction,
        guestAction,
        logoutAction,
        fetchUserInfo,
        openAuthDialog,
        closeAuthDialog,
        consumeRedirectAfterLogin,
        handleUnauthorized,
        authDialogVisible,
        authDialogMode,
    }
})
