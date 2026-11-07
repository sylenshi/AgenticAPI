// 上游运维相关接口请求
import request from './request'
import type { cookieSettings } from '@/types'

/** 火山方舟用量段（叶子键仅在对应 status === "200" 时保证存在） */
export interface volUsageDetail {
    volFiveHourUsed: number
    volWeeklyUsed: number
    volMonthlyUsed: number
    volFiveHourTotal: number
    volWeeklyTotal: number
    volMonthlyTotal: number
    volFiveHourResetAt: string | null
    volWeeklyResetAt: string | null
    volMonthlyResetAt: string | null
}

/** 阶跃星辰用量段 */
export interface stepfunUsageDetail {
    stepfunFiveHourUsed: number
    stepfunWeeklyUsed: number
    stepfunMonthlyUsed: number
    stepfunFiveHourTotal: number
    stepfunWeeklyTotal: number
    stepfunMonthlyTotal: number
    stepfunFiveHourResetAt: string | null
    stepfunWeeklyResetAt: string | null
    stepfunMonthlyResetAt: string | null
}

/** 智谱 Coding Plan 用量段（zai2 段叶子键用 zai 前缀） */
export interface zaiUsageDetail {
    zaiFiveHourUsed: number
    zaiWeeklyUsed: number
    zaiMonthlyUsed: number
    zaiFiveHourTotal: number
    zaiWeeklyTotal: number
    zaiMonthlyTotal: number
    zaiFiveHourResetAt: string | null
    zaiWeeklyResetAt: string | null
    zaiMonthlyResetAt: string | null
}

/** Antigravity 用量段 */
export interface agUsageDetail {
    agFiveHourUsed: number
    agWeeklyUsed: number
    agMonthlyUsed: number
    agFiveHourTotal: number
    agWeeklyTotal: number
    agMonthlyTotal: number
    agFiveHourResetAt: string | null
    agWeeklyResetAt: string | null
    agMonthlyResetAt: string | null
}

/** GET /operations/get 响应 data：外层段名为后端现状的蛇形，叶子键为驼峰 */
export interface operationsData {
    status: { vol: string; stepfun: string; zai2: string; antigravity: string }
    vol_usage: volUsageDetail
    stepfun_usage: stepfunUsageDetail
    zai2_usage: zaiUsageDetail
    antigravity_usage: agUsageDetail
}

/**
 * 获取上游运维数据
 * @param refreshChannel 刷新的渠道：vol / stepfun / zai2 / antigravity / all
 */
export function getOperations(refreshChannel: string = 'all') {
    return request.get<operationsData>('/operations/get', { params: { refresh_channel: refreshChannel } })
}

/** 上传上游运维凭证 */
export function uploadOperations(data: cookieSettings) {
    return request.post('/operations/upload', data)
}
