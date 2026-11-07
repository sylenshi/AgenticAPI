# 前端 UI构建规范文档

> 适用范围：`frontend/` 目录下所有页面与组件。本规范是全局约定，新增页面、改造旧页面、以及让 AI 生成界面时，都应以本文档为准。
>
> 风格定位：**企业级 SaaS 控制台**（对齐字节跳动 Arco Design / 火山引擎的亮色风格），整体追求"工程产品的精确感"，克制、紧凑、信息密度优先，**避免"AI 生成感"的营销页套路**（详见第 12 节）。
>
> **2026-11 改版**：控制台页中文换用自托管 MiSans VF（**首页与顶栏品牌字保持改版前字体不变**）、表格行高与视觉重做、补齐按钮/标签/输入等高频 Arco 组件覆写、统一断点与弹层窄屏兜底。本文档已同步代码现状。

---

## 1. 基本原则

1. **只用 Arco Design Vue 一个组件库**。禁止引入 Element Plus、Ant Design、Naive UI 等其他组件库；禁止用原生 HTML 元素复刻已有组件（不要手写下拉框、弹窗、分页器）。
2. **只做亮色主题**，不考虑暗色切换。颜色一律引用 CSS 变量（见第 3 节），禁止在页面里写死十六进制色值（阴影 rgba、装饰性渐变除外）。
3. **紧凑密度基调**。控制台类页面以信息密度优先：表格 13px、控件默认 32px 高、卡片内边距 12–20px。不要为了"透气"放大留白。
4. **主色只承载交互语义**。蓝色（`--color-primary`）只用于可点击/可操作的元素；数据的区分度靠扩展强调色与中性色完成（见第 4 节），避免整页一片蓝。
5. **三层 CSS 架构**：全局令牌 → 共享页面模式 → 页面局部 scoped 样式。哪层写什么见第 10 节。
6. **字体只用三个角色令牌**（`--font-sans` / `--font-display` / `--font-mono`），规则见第 3 节字体系统。

---

## 2. 技术栈与组件约定

| 项 | 约定 |
| --- | --- |
| 组件库 | `@arco-design/web-vue`（全量引入，`app.use(ArcoVue)` + `ArcoVueIcon`，zh-CN locale 由 `App.vue` 的 `a-config-provider` 提供） |
| 图标 | 通用图标用 Arco 图标组件（`icon-search`、`icon-plus`…，已全局注册）；**模型品牌图标用 `@/components/common/LobeIcon.vue`**（见第 8 节） |
| 字体 | `@fontsource-variable/public-sans`、`@fontsource-variable/manrope`、`@fontsource-variable/jetbrains-mono` 自托管（见第 3 节） |
| 提示反馈 | 轻提示用 `Message.success/error/warning`（从 `@arco-design/web-vue` 导入）；确认弹窗用 `confirmDialog()`（`@/utils/feedback`），**不要**自己拼 a-modal 做确认框 |
| 表格 | 一律 `a-table`：columns 定义放 script、单元格用 `slotName` + 同名具名插槽（**现状未用 `#cell`**）、`:bordered="{wrapper: true}"`、`:pagination="false"` + 独立 `a-pagination`（套 `.table-pagination` 类）；列多时须配 `:scroll="{x: …}"` |
| 弹层 | 对话框 `a-modal`（表单类用 `:footer="false"` 自绘或 `#footer`）；侧边详情/配置用 `a-drawer`（`v-model:visible`、`unmount-on-close`） |
| 表单 | `a-form` + `layout="vertical"`；校验用 Arco rules（`{required, message}` / `validator(value, cb)`） |

**组件尺寸规则**：默认尺寸（medium，32px）。工具栏/表格旁的次要操作可用 `size="small"`，图标按钮可用 `size="mini"`；`size="large"` 只允许出现在首页 Hero 主行动点。

---

## 3. 设计令牌（`src/styles/variables.css`）

### 颜色

| 令牌 | 值 | 用途 |
| --- | --- | --- |
| `--color-primary` | `#165dff` | 主操作：主按钮、链接、选中态、可交互强调 |
| `--color-primary-lighter` | `#e8f3ff` | 选中底色、Hover 浅底 |
| `--color-success` / `-light` | `#00b42a` / `#e8ffea` | 成功、启用、免费分组 |
| `--color-warning` / `-light` | `#ff7d00` / `#fff7e8` | 警告、阈值告警 |
| `--color-error` / `-light` | `#f53f3f` / `#ffece8` | 错误、停用、删除 |
| `--color-violet` / `-lighter` | `#722ed1` / `#f5e8ff` | 扩展强调色（工坊、次级区分） |
| `--color-cyan` / `-lighter` | `#14c9c9` / `#e8fffb` | 扩展强调色 |
| `--color-gold` / `-lighter` | `#f7ba1e` / `#fffce8` | 扩展强调色 |
| `--color-vermilion` / `-lighter` | `#f77234` / `#ffece8` | 扩展强调色（VIP 等） |

中性色用 `--color-gray-50…900`（Arco gray 阶）：文字 `--color-text`（gray-900）/ `--color-text-secondary`（gray-700）/ `--color-text-muted`（gray-500）；边框 `--color-border`（gray-200）；内容区底 `--color-bg-layout`（gray-100）。

### 字体系统（三角色）

网络字体在 `styles/index.css` 顶部通过 `@fontsource-variable/*` 包自托管引入——**随构建打包、不走 CDN（国内直连可用）**，按 unicode-range 子集切分，浏览器只下载实际用到的 latin 子集（三套合计约 89KB）。

| 令牌 | 字体链 | 用途 |
| --- | --- | --- |
| `--font-sans` | **Public Sans Variable**（拉丁）→ **MiSans VF**（中文，自托管）→ HarmonyOS Sans SC → MiSans → PingFang SC → Microsoft YaHei → system-ui | 控制台页正文、表单、表格、Arco 组件（首页/顶栏例外） |
| `--font-display` | **Playfair Display Variable**（拉丁）→ **Noto Serif SC / 思源宋体**（中文） | 品牌字（顶栏 "AgenticAPI"）、首页 Hero 与分屏大标题（保留改版前衬线气质） |
| `--font-mono` | **JetBrains Mono Variable** → ui-monospace → Consolas | 代码、API 密钥、模型价格、统计数值、眉题、屏码 |

规则：

- **控制台页中文统一走 MiSans VF**（`misans` 包，可变字重 150-700，56 个 unicode-range 分片按需加载）；**首页与顶栏品牌字例外**：在 `.home-page` 作用域重定义 `--font-sans` / `--font-display`，保留改版前的系统字体与衬线展示字。拉丁网络字体在前、中文字体在后，浏览器按字符逐个回落。
- **新增字体必须走 @fontsource 包 + variables.css 令牌**；禁止引 CDN 字体链接（Google Fonts 等）、禁止在页面里写裸 `font-family` 字符串。
- **所有数字加 `font-variant-numeric: tabular-nums`**（表格已在 arco-overrides 全局开启，其余数字元素在样式里显式声明），等宽对齐是控制台质感的关键。
- 展示字体（display）只用于品牌与落地页大标题；控制台内的页面标题（`.page-head h1`）用正文 sans，保持后台风。

### 字号

- 页面主标题 22px（`--text-page-title`）、卡片标题 14–16px、正文 14px、辅助 12–13px、表格 13px / 行高 20px / 单元格上下 padding 4px（≈28px 行高，已在 arco-overrides 全局覆写）。

### 圆角 / 阴影 / 间距

- 圆角：控件 2px（`--radius-sm`）、小卡片 4px、卡片/弹层 6–8px。**禁止 12px 以上的大圆角**（那是不紧凑的"营销卡片"风格）。
- 阴影克制：静止用 `--shadow-sm` 或不用（边框负责分隔），悬停最多 `--shadow-sm/md`。
- 间距一律用 `--space-*`（4px 步进）；页面容器水平 padding 24px、垂直 20px。

---

## 4. 配色使用规则（避免整页一蓝）

1. **蓝色 = 可交互**；**扩展色 = 区分**。同屏出现多张统计卡、多组标签、多条曲线时，用不同强调色区分，而不是全部 primary。
2. **统计卡彩色脊线**：`.stat-card` 支持 `--stat-accent`，预设类 `stat-accent-green / -orange / -violet / -cyan / -gold`（不设则默认主色）。一组卡按序轮换配色，数值色 `stat-value-brand` 跟随脊线色。
3. **标签色按名字散列**：无语义的标签（模型标签、渠道名等）用 `tagColorByName(name)`（`@/utils/colors`）取色——同名永远同色，列表天然多彩且稳定。**有语义的标签不用它**：免费=`green`、VIP=`orangered`、停用=`red`、管理员=`arcoblue`、访客=`gray`。
4. **图表色板**：`@/components/monitor/LineChart.vue` 的 `PALETTE`（蓝/绿/橙/红/青/紫…），新增图表直接复用，不要自造色板。
5. 状态优先用**小色点**（6px 圆点 `.dot dot-green` 之类）或 a-tag，不要为大块信息加彩色背景。

---

## 5. 布局骨架

- 顶部导航 `AppHeader`：56px（`--layout-header-height`），白底 + 底部边框，吸顶。
- 控制台 `DashboardLayout`：左侧白底侧栏 176px（`--layout-sidebar-width`），菜单项 = Arco 图标 + 文字（窄屏收为纯图标时保留 `title`），激活态 = `--color-primary-lighter` 底 + 主色文字；内容区底色 `--color-bg-layout`。
- 页面容器：`height: 100%; overflow-y: auto; padding: var(--space-5) var(--space-6);`。
- 新增控制台页面：在 `src/constants/nav.ts` 的 `dashItems` 注册（含 `icon` 字段，用 Arco 图标名）。
- **断点约定**：`≤768px` 为窄屏、`≥769px` 为桌面（不再混用 767/768，避免导航展开与侧栏收起在 768px 同时生效）；抽屉/弹窗宽度不要写死大于 `calc(100vw - 32px)`。

---

## 6. 共享页面模式（`src/styles/components.css`）

这些类多页面复用，**优先使用而不是在页面里重写**：

| 类名 | 用途 |
| --- | --- |
| `.page-head` + `.page-head-desc` | 页面标题区（h1/h2 22px/bold + 一句描述，标题独占首行；放进 header 的工具栏排其下方） |
| `.stat-cards` / `.stat-card` / `.stat-label` / `.stat-value` | 统计卡（auto-fit 自适应列数，3/4 张都无需页面反写；`stat-accent-*` 上色；数值 24px 等宽） |
| `.filter-bar` | 浅色工具条（浅底 + 边框 + 6px 圆角，输入 + 查询按钮自动换行） |
| `.page-card` | 控制台白卡容器（边框 + 6px 圆角 + 16/20px 内边距 + 轻阴影） |
| `.table-pagination` | 表格下方分页器（右对齐） |

典型结构：

```vue
<header class="page-head">
  <h1>页面名</h1>
  <p class="page-head-desc">一句话说明</p>
</header>
<div class="filter-bar">…筛选控件 + 查询按钮…</div>
<a-table … :pagination="false"/>
<a-pagination … class="table-pagination"/>
```

---

## 7. Arco 全局覆写（`src/styles/arco-overrides.css`）

已全局生效、**页面里不要再重复设置**：

- 表格：13px、表头 12px/600 浅灰底 + 下边框、单元格 padding 4/12px + 行高 20px（≈28px 行高）、行间细分隔线、hover 极浅蓝（`--color-row-hover`）、`tabular-nums`；表格内按钮/标签压到 24px/18px，避免撑高行。
- 表单项间距 12px；描述列表 13px/6px 紧凑内边距。
- 弹窗标题 16px/600；抽屉体 padding 16/20px；弹层圆角 8px + 遮罩 3px 模糊；`.arco-drawer/.arco-modal` 有 `max-width: calc(100vw - 32px)` 窄屏兜底。
- 按钮 / 标签 / 输入类：2px 圆角、`--font-sans`、500 字重、`:active` 按压 + `:focus-visible` 焦点环（此前这些高频组件沿用 Arco 默认外观，与令牌割裂）。

需要新的全局覆写时加在这个文件并注明原因；页面级微调用 scoped 样式。

---

## 8. 模型图标（LobeIcon）

```vue
import LobeIcon from '@/components/common/LobeIcon.vue'
<LobeIcon :name="model.icon" :fallback="model.name" :size="24"/>
```

- `name` 取数据库 `models.icon` 字段：lobehub 图标名（`Qwen`、`OpenAI`、`Claude.Color` 点号语法取色版优先），也支持 http(s) 图片链接。
- 加载失败或为空时显示 `fallback` 首字母灰底圆标，**不会报错**。
- 图标按需懒加载（`import.meta.glob` 分包），不要整包引入。
- 模型卡片图标容器：38px 灰底方块（`--color-gray-100`），图标 24px。
- 管理端配置模型时提供"图标名输入 + 实时预览"（参考模型广场配置抽屉的 `icon-field`）。

---

## 8.5 导航栏用户头像与下拉菜单（AppHeader）

- **头像**（v0.15.0）：已登录显示预设头像图（`userInfo.avatar`，前端静态资源 `/avatars/avatar-N.png` 共 6 张，`a-avatar` 32px 圆形 + `object-fit: cover` 裁剪，视觉高度与左侧 36px 品牌 logo 协调）；`avatar` 为 null（存量老账号）回退显示展示名首字符主色圆标，两种形态共用 `.user-avatar` 基础样式。
- **下拉菜单**（`a-dropdown trigger="click"`）：三项 —— ①「余额 X.XX 元」（`icon-safe`，数字 `tabular-nums`、`formatAmount` 两位小数，点击跳 `/dashboard/overview`）；②「切换头像」（`icon-swap`，点击调 `PUT /user/avatar` 随机换一张，无需确认弹窗）；③ 分隔线 +「退出登录」（`icon-export`，保留红色确认弹窗）。菜单展开时调一次 `fetchUserInfo()` 刷新余额实时值。

---

## 9. 对话消息与 Markdown 排版（模型工坊）

工坊对话窗口（`components/studio/ChatMessages.vue`）是全站唯一的富 markdown 渲染场景，排版规则集中在其 `.markdown-body` 的 `:deep` 规则里，**新增渲染需求扩展这里，不要另起炉灶**：

- **气泡基调**：正文 13–14px、行高 1.7–1.8、内边距 10–14px；用户气泡 `--color-primary-lighter` 底、右下角收小圆角，AI 气泡 `--color-gray-100` 底、左上角收小圆角。
- **标题不做层级跳跃**：AI 输出的 `# ~ ######` 统一压在 14–17px、semibold——绝不让浏览器默认的 2em 大标题出现。
- **统一垂直节奏**：段落/列表/代码块/表格/引用块一律 10px 上下间距；`:first-child` / `:last-child` 清零外边距，避免气泡首尾出现空隙。
- **列表**：去掉浏览器默认 1em 边距，缩进 1.5em、行间距 3px。
- **表格**：`display: block` 使宽表可横向滚动；表头浅灰底，数字 `tabular-nums`。
- **代码**：代码块 12px 等宽、深色底（gray-800）；行内代码 12px、浅灰底（gray-200）。
- **思维链块**：`warning-light` 底 + 半透明橙描边 + 可折叠头部，正文 12px/1.8 行高，限高 220px 内部滚动。
- **消息底部**：token 用量行用 `--font-mono` 11px，与正文之间加细分割线；操作按钮悬停气泡时才显现。

---

## 10. CSS 三层架构

```
src/styles/
├── variables.css      # 第 1 层：设计令牌（颜色/字体/字号/间距，只放变量不放规则）
├── arco-overrides.css # 第 2 层：对 Arco 组件的全局微调
├── reset.css / layout.css / typography.css
├── components.css     # 第 3 层：通用组件类 + 跨页面共享模式（.page-head/.stat-cards/…）
└── index.css          # 汇总入口：顶部先 @fontsource 网络字体，再按序引上述模块
                         （index.css 在 main.ts 中于 arco.css 之后引入）
```

判断规则：

- **只在 ≥2 个页面出现的结构** → 提升到 `components.css` 共享模式。
- **只有本页面有的样式** → 组件内 `<style scoped>`，且必须引用令牌变量。
- **禁止**：页面里写死色值/字号 px（应引用变量）、复制另一页的大段 CSS、用 `!important` 覆盖 Arco（应加到 arco-overrides.css）。

---

## 11. 反馈与状态

- 操作结果：`Message.success/error(...)`，文案说结果不说过程（"配置保存成功"）。
- 危险操作（删除、停用）：`confirmDialog(content, title, okText, true)` 红色确认。
- 加载中：表格用 `:loading`，按钮用 `:loading`；不要用遮罩全屏loading。
- 空状态：`a-empty` + 一句引导文案（如"没有匹配的模型"）。

---

## 12. 反"AI 味"守则（Do / Don't）

| Don't（AI 生成感） | Do（本站做法） |
| --- | --- |
| 渐变大标题、彩色 glow 文字 | 深色实字标题，最多一个关键词用主色（**首页 Hero 例外**：保留原有三色渐变关键词，按产品要求不动） |
| 胶囊徽章 + 火焰图标开场 | 小字号宽字距等宽眉题（`AGENTIC API · …`） |
| 三张一排的"功能卡 + 彩色圆角图标"网格 | 用真实产品 UI 模拟（模型卡、对话面板、图表、代码块）展示能力 |
| 大圆角 + 大阴影的浮空卡片 | 小圆角、边框分隔、几乎无阴影 |
| emoji / 装饰性图形 | Arco 线性图标、状态色点 |
| 全页同一种蓝色 | 主色交互 + 扩展色区分 + 散列标签色 |
| 假数据摆成完美三列 | 等宽数字、真实接口数据、未加载就空态 |
| 全站一种默认字体 | 三字体角色：正文 Public Sans / 展示 Manrope / 等宽 JetBrains Mono |

---

## 13. 首页特殊规范（六屏整页滑动）

首页 `src/views/home/index.vue` 是全站唯一的全屏滑动页面：

- 六屏结构：Hero → 模型广场 → 模型工坊 → 监控面板 → 控制台 → 开发文档（深色收尾）。每屏一个强调色（蓝/蓝/紫/绿/橙/深色）。
- 字体：大标题（Hero/分屏）用 `--font-display`；眉题、屏码、指标数值用 `--font-mono`。
- 交互：滚轮 / 触摸滑动 / ↑↓与PageUp/PageDown 键 / 右侧圆点导航（悬停出名称）/ 左下角 `01 / 06` 屏码。翻页由 JS 劫持（700ms 锁防连触）。
- **≤768px 自动退化为普通纵向滚动**（桌面判定用 `min-width: 769px`，避免与侧栏 `max-width: 768px` 在 768px 同时生效），圆点与屏码隐藏；焦点在输入框/弹窗内时键盘不翻页。
- 新增分屏：加一个 `.slide`（配 `slide-eyebrow/title/desc` + 产品 UI 模拟），并把标题加进 `sections` 数组即可，导航自动生效。

---

*本规范与 `frontend/public/docs/styles-guide.md`（对外文档样式指南）相互独立；对内改 UI 以本文档为准。*
