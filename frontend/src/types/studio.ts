// 模型工坊相关类型（会话与参数只存浏览器 localStorage，不上服务端）

import type {agentConfirmState, agentDownload, agentToolEvent} from './agent'

/** 输入框里的图片附件（base64 data URL，随用户消息一起保存） */
export interface studioImage {
    id: string
    dataUrl: string
    mimeType: string
    fileName: string
}

/** 单条回复的 token 用量与耗时（流式结束后由最后一个 chunk 的 usage 回填） */
export interface studioUsage {
    promptTokens: number
    completionTokens: number
    elapsedMs: number
}

/** 联网搜索事件（后端 agent 工具循环期间推送，随消息持久化） */
export interface studioSearchEvent {
    query: string
    status: 'running' | 'done'
}

/** 对话消息 */
export interface studioMessage {
    id: string
    role: 'user' | 'assistant'
    content: string
    /** 思维链（推理模型流式返回） */
    reasoning?: string
    /** 用户消息携带的图片 */
    images?: studioImage[]
    /** 联网搜索记录（开启搜索开关时后端推送） */
    searches?: studioSearchEvent[]
    /** token 用量（回答完成后回填） */
    usage?: studioUsage
    /** 生成失败时的错误信息 */
    error?: string
    /** 维护 Agent 专属：工具执行记录（仅 /dashboard/agent 使用，工坊消息恒为空） */
    toolEvents?: agentToolEvent[]
    /** 维护 Agent 专属：审批卡片状态 */
    confirm?: agentConfirmState
    /** 维护 Agent 专属：导出文件下载卡片 */
    downloads?: agentDownload[]
    createTime: number
}

/** 会话 */
export interface studioSession {
    id: string
    title: string
    /** 最近一次生成使用的模型（展示用，实际发送取参数面板当前选择的模型） */
    modelName: string
    messages: studioMessage[]
    createTime: number
    updateTime: number
}

/** 参数面板的模型参数（随登录用户持久化到 localStorage） */
export interface studioParams {
    systemPrompt: string
    temperature: number
    topP: number
    maxTokens: number
}

export const DEFAULT_STUDIO_PARAMS: studioParams = {
    systemPrompt: '',
    temperature: 1.0,
    topP: 1.0,
    maxTokens: 4096,
}
