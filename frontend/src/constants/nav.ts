// 全局导航常量

// 顶部主导航项
export interface navItem {
    id: string
    label: string
    to: string
}

// 控制台侧边导航项（icon 为 Arco 图标组件名）
export interface dashItem {
    id: number
    name: string
    to: string
    icon: string
}

export const navItems: navItem[] = [
    {id: '001', label: '首页', to: '/home'},
    {id: '002', label: '模型广场', to: '/models'},
    {id: '003', label: '模型工坊', to: '/studio'},
    {id: '004', label: '监控面板', to: '/monitor'},
    {id: '005', label: '控制台', to: '/dashboard'},
    {id: '006', label: '文档', to: '/docs'},
]

export const dashItems: dashItem[] = [
    {id: 1, name: '概览', to: '/dashboard/overview', icon: 'icon-dashboard'},
    {id: 2, name: '秘钥', to: '/dashboard/keys', icon: 'icon-safe'},
    {id: 3, name: '渠道', to: '/dashboard/channels', icon: 'icon-swap'},
    {id: 4, name: '运营', to: '/dashboard/operations', icon: 'icon-computer'},
    {id: 5, name: '用户', to: '/dashboard/userlist', icon: 'icon-user-group'},
    {id: 6, name: '兑换', to: '/dashboard/redemptioncodes', icon: 'icon-gift'},
    {id: 7, name: '安全', to: '/dashboard/security', icon: 'icon-settings'},
    {id: 8, name: '维护Agent', to: '/dashboard/agent', icon: 'icon-robot'},
]
