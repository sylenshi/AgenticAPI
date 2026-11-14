// 用量窗口：resetAt 为配额重置时间（后端已格式化为 "YYYY-MM-DD HH:MM"），上游未返回时为 null，前端不展示
interface usageWindow {
    used: number; quota: number; resetAt?: string | null
}

// 火山方舟渠道的用量数据
export interface volUsageData {
    status: string;
    fiveHour: usageWindow
    weekly: usageWindow
    monthly: usageWindow
}

// 阶跃星辰渠道的用量数据
export interface stepfunUsageData {
    status: string;
    fiveHour: usageWindow
    weekly: usageWindow
    monthly: usageWindow
}

// 智谱渠道（v2 套餐）的用量数据：上游仅返回已用百分比，used/total 为 百分比/100
export interface zai2UsageData {
    status: string;
    fiveHour: usageWindow
    weekly: usageWindow
    monthly: usageWindow
}

// Antigravity（Google Gemini PRO 订阅，经 sub2api 网关查询）的限额数据：上游按模型分两个池子
// （gemini = Gemini 池、3p = Claude 池），每池各有 5 小时 + 周度两个窗口（utilization 已由后端
// 换算为已用百分比，Total 恒为 100），上游无月度窗口
export interface antigravityPoolUsage {
    fiveHour: usageWindow
    weekly: usageWindow
}

export interface antigravityUsageData {
    status: string;
    gemini: antigravityPoolUsage
    claude: antigravityPoolUsage
}

// 数据接口定义，向后端发送凭证信息
// 注：智谱 key 上传后存服务端 operations_config.json，优先于后端 .env 兜底值（方便换号）
export interface cookieSettings {
    brmToken: string
    instanceId: string
    stepToken: string
    stepWebid: string
    zaiApiKey: string
}
