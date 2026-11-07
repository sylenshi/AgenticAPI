// 用户相关类型定义

/** 用户信息（不含密码等敏感字段） */
export interface userInfoSchema {
    id: number;
    username: string;
    nickname: string | null;
    phone: string | null;
    /** 预设头像URL（/avatars/avatar-N.png）；null 表示未设置，导航栏回退显示首字符圆标 */
    avatar: string | null;
    isGuest: boolean;
    isAdmin: boolean;
    /** 注意：后端 Decimal 序列化为字符串（如 "0.000000"），保证金额精度不丢 */
    balance: string;
    usedQuota: string;
    userGroup: string;
    createTime: string | null;
    lastLoginTime: string | null;
}

/** 登录/注册成功后返回的数据：访问令牌 + 用户信息 */
export interface userAuthSchema {
    token: string;
    userInfo: userInfoSchema;
}
