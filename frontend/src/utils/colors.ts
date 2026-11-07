// 稳定的字符串配色：同一个名字（模型标签 / 用户名 / 渠道名）永远拿到同一个颜色，
// 让列表天然带上色彩区分度，而不是整页清一色的蓝色。
// 颜色集合取自 Arco 的彩色标签色名，避开 gray 系（保留给"无状态"语义）。
const HUES = [
  'arcoblue',
  'green',
  'cyan',
  'purple',
  'orange',
  'pinkpurple',
  'lime',
  'gold',
  'magenta',
  'orangered',
] as const

/** 把任意字符串散列成固定的下标（djb2 变体，分布均匀且实现简单） */
function hashIndex(input: string): number {
  let hash = 5381
  for (let i = 0; i < input.length; i++) {
    hash = ((hash << 5) + hash + input.charCodeAt(i)) | 0
  }
  return Math.abs(hash)
}

/** 按名字取一个稳定的 Arco 标签色名，用于 a-tag 的 color 属性 */
export function tagColorByName(name: string): string {
  if (!name) return 'gray'
  return HUES[hashIndex(name) % HUES.length] ?? 'gray'
}

/** 读取根元素上的 CSS 设计令牌值（供不接受 var() 的 SVG 属性等场景使用，如 Arco Progress 的 color） */
export function cssVar(name: string): string {
  return getComputedStyle(document.documentElement).getPropertyValue(name).trim()
}
