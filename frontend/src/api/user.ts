// 用户认证相关接口请求
import request from './request'
import type { userInfoSchema, userAuthSchema } from '@/types'

/** 注册（注册成功即登录，直接返回令牌和用户信息） */
export function register(data: { username: string; password: string }) {
    return request.post<userAuthSchema>('/user/register', data)
}

/** 登录 */
export function login(data: { username: string; password: string }) {
    return request.post<userAuthSchema>('/user/login', data)
}

/** 访客模式：后端创建临时访客账号（24小时有效），返回令牌走正常登录流程 */
export function guestLogin() {
    return request.post<userAuthSchema>('/user/guest')
}

/** 获取当前登录用户信息（需携带 Bearer 令牌，由请求拦截器自动附加） */
export function getUserInfo() {
    return request.get<userInfoSchema>('/user/info')
}

/** 修改自己的资料（昵称/手机号，概览页使用） */
export function updateProfile(data: { nickname?: string; phone?: string }) {
    return request.put<userInfoSchema>('/user/profile', data)
}

/** 切换头像：后端从预设 6 张中随机换一张（与当前不同），返回更新后的用户信息 */
export function updateAvatar() {
    return request.put<userInfoSchema>('/user/avatar')
}

/** 登出（删除服务端令牌，令牌立即失效） */
export function logout() {
    return request.delete<null>('/user/logout')
}
