// 通用展示格式化工具

/**
 * 金额展示格式化：千分位 + 固定小数位（默认 2 位，与首页宣传位的 ¥128.40 风格一致）
 * 后端 DECIMAL 以字符串下发（如 "9877.647381"），这里只负责展示精度，原始精度可通过 title 保留
 * @param value 数字或字符串金额，空值 / 非法值返回占位符
 */
export function formatAmount(value: number | string | null | undefined, digits = 2, placeholder = '-'): string {
  const num = typeof value === 'string' ? Number(value) : value
  if (value === null || value === undefined || value === '' || Number.isNaN(num as number)) {
    return placeholder
  }
  return (num as number).toLocaleString('zh-CN', {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  })
}
