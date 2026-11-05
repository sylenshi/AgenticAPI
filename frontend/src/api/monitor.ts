// 监控面板相关接口请求
import request from './request'
import type { chatRecordSchema, logItemSchema, pagedResult, siteSummarySchema, userStatsSchema } from '@/types'

/** 全站累计用量（读后端单行汇总表） */
export function getSiteSummary() {
    return request.get<siteSummarySchema>('/monitor/summary')
}

/** 对话记录分页：管理员可传 username 查全部用户，普通用户后端强制只看自己 */
export function getChatRecords(params: { page: number; pageSize: number; model?: string; username?: string }) {
    return request.get<pagedResult<chatRecordSchema>>('/monitor/chats', { params })
}

/** 系统日志分页：管理员看全部，普通用户后端强制只看自己；时间为闭开区间 [start, end) */
export function getMonitorLogs(params: {
    page: number
    pageSize: number
    type?: string
    keyword?: string
    model?: string
    start?: string
    end?: string
}) {
    return request.get<pagedResult<logItemSchema>>('/monitor/logs', { params })
}

/** 当前用户时间范围内的用量：累计值 + 按粒度分桶的每模型序列 */
export function getUserStats(params: { start: string; end: string; granularity: string }) {
    return request.get<userStatsSchema>('/monitor/stats', { params })
}
