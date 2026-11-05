// 上游运维相关接口请求
import request from './request'
import type { cookieSettings } from '@/types'

/**
 * 获取上游运维数据
 * @param refreshChannel 刷新的渠道：vol / stepfun / zai2 / antigravity / all
 */
export function getOperations(refreshChannel: string = 'all') {
    return request.get('/operations/get', { params: { refresh_channel: refreshChannel } })
}

/** 上传上游运维凭证 */
export function uploadOperations(data: cookieSettings) {
    return request.post('/operations/upload', data)
}
