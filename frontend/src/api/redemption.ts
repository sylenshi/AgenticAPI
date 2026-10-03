// 兑换码接口请求：用户端兑换与记录 + 管理端生成/管理/监控
import request from './request'

/** 管理端一条兑换码 */
export interface redeemCodeItem {
    id: number;
    code: string;
    /** 后端 Decimal 序列化为字符串（如 "10.000000"），保精度 */
    amount: string;
    /** 0 已停用 / 1 未使用 / 2 已使用 */
    status: number;
    batchNo: string;
    remark: string | null;
    usedBy: number | null;
    usedUsername: string | null;
    usedTime: string | null;
    createTime: string | null;
}

/** 用户端一条兑换记录 */
export interface redeemRecordItem {
    id: number;
    code: string;
    amount: string;
    usedTime: string | null;
}

/** 兑换码监控统计 */
export interface redeemStats {
    totalCount: number;
    unusedCount: number;
    usedCount: number;
    disabledCount: number;
    usedAmount: number;
}

/** 兑换码核销（成功返回用户新余额，字符串保精度） */
export function redeemCode(code: string) {
    return request.post<{ balance: string }>('/redeem', {code})
}

/** 我的兑换记录（已核销的码，按核销时间倒序） */
export function getRedeemRecords(params: { page: number; pageSize: number }) {
    return request.get<{ list: redeemRecordItem[]; total: number }>('/redeem/records', {params})
}

/** 批量生成兑换码（管理员，单次最多 100 张） */
export function generateRedeemCodes(data: { count: number; amount: number; batchNo?: string; remark?: string }) {
    return request.post<{ codes: string[]; batchNo: string }>('/admin/redeem-codes/generate', data)
}

/** 分页查询兑换码列表（管理员） */
export function getRedeemCodes(params: {
    page: number;
    pageSize: number;
    status?: number;
    keyword?: string;
    batchNo?: string;
}) {
    return request.get<{ list: redeemCodeItem[]; total: number }>('/admin/redeem-codes', {params})
}

/** 兑换码监控统计（管理员） */
export function getRedeemStats() {
    return request.get<redeemStats>('/admin/redeem-codes/stats')
}

/** 停用未使用的兑换码（管理员） */
export function disableRedeemCode(codeId: number) {
    return request.put(`/admin/redeem-codes/${codeId}/disable`)
}
