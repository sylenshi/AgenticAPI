// 模型相关接口请求
import request from './request'
import type { modelInfoSchema } from '@/types'

/** 获取全量模型列表 */
export function getModels() {
    return request.get<modelInfoSchema[]>('/models')
}

/** 添加单个模型 */
export function addModel(data: Partial<modelInfoSchema>) {
    return request.post<{ modelId: number }>('/models', data)
}

/** 更新单个模型（按 name 定位，name 本身不可更新） */
export function updateModel(modelName: string, data: Partial<modelInfoSchema>) {
    return request.put(`/models/${encodeURIComponent(modelName)}`, data)
}

/** 删除模型（按 name 删除） */
export function deleteModel(modelName: string) {
    return request.delete(`/models/${encodeURIComponent(modelName)}`)
}
/** 拨测模型（POST，规范 §3.2；后端有每用户 60s 冷却；单独放宽超时与后端 180s 拨测超时对齐，覆盖全局 axios 的 30s） */
export function testModel(modelName: string) {
    return request.post(`/models/test/${encodeURIComponent(modelName)}`, null, {timeout: 200000})
}

