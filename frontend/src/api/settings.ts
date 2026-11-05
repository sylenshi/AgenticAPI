// 站点设置接口请求（控制台-设置页，仅管理员）
import request from './request'

/** 站点设置当前值（后端带默认兜底；agentEffectiveModel 为按解析链实际生效的模型） */
export interface siteSettingsSchema {
    chatRecordMaxTokens: number
    agentDefaultModel: string
    agentEffectiveModel: string
    registerInitialBalance: number
    guestInitialBalance: number
}

/** 可更新字段（部分更新语义：只传变化的字段） */
export type siteSettingsUpdate = Partial<Pick<
    siteSettingsSchema, 'chatRecordMaxTokens' | 'agentDefaultModel' | 'registerInitialBalance' | 'guestInitialBalance'
>>

/** 读取站点设置 */
export function getSiteSettings() {
    return request.get<siteSettingsSchema>('/admin/settings')
}

/** 更新站点设置（仅传入字段生效；agentDefaultModel 传空串表示清除指定、恢复默认解析链） */
export function updateSiteSettings(data: siteSettingsUpdate) {
    return request.put<null>('/admin/settings', data)
}
