# AgenticAPI

> 文档版本：v0.9.0 ｜ 更新日期：2026-10-05 ｜ 状态：持续迭代中

## 背景

AgenticAPI 是一个基于 Agent 的 API 中转站平台，支持通过 Agent 来管理不同的 API 接口。

前端采用 Vue3 + TypeScript，后端使用 FastAPI + Python（全异步）开发，并为后续 Agent 原生功能提供支持。

其基础功能为向外提供大模型 API 接口的能力，后续可拓展支持 MCP、Skills、CLI 等连接管理功能。

## 功能特性

### 已实现

- **核心中转链路**：`POST /v1/chat/completions`（OpenAI Chat 兼容），API 密钥（sk-xxx）鉴权 → 模型/分组/余额校验 →
  多渠道顺序轮询转发（支持流式/非流式透传）→ 按模型定价计费扣减余额 → 记录调用日志；`GET /v1/models`（OpenAI Models
  兼容）返回当前密钥用户按分组权限可调用的模型列表（已过滤停用模型与渠道全停的模型）
- **模型广场**：模型列表展示、搜索、分页，模型的添加 / 编辑 / 删除（含定价、渠道绑定、能力开关、模型映射等配置，需管理员）
- **渠道管理**：上游渠道的增删改查、状态启停开关、支持模型列表维护（需管理员）
- **上游运维监控**：火山方舟 / 阶跃星辰 / 智谱 TokenPlan 用量监控与凭证管理（需管理员，火山方舟用量经深势 BohrClaw 平台接口查询）
- **用户体系（前后端）**：导航栏右上角注册 / 登录弹窗，bcrypt 密码加密，不透明
  Token（uuid4）签发与校验，登出即时失效；用户表含管理员、余额（DECIMAL）、用户分组（free/vip）、封禁状态等字段
  （正式注册统一进 **vip** 分组、可调全部分组模型，访客固定 **free** 分组、仅免费模型）
- **API 密钥管理**：每个用户最多 5 个 `sk-` 密钥，控制台-秘钥页面增删改查、启停
- **用户管理（管理员）**：控制台-用户页面分页搜索、修改余额 / 分组 / 管理员 / 状态、批量删除（联动清理令牌与密钥）
- **系统日志**：统一 `logs` 表记录 API 调用（token 用量/费用/耗时/渠道）、登录注册访客登出、管理员操作、密钥操作
- **监控面板（前后端）**：替代原"路由模型"页（`/monitor`，需登录），三个标签——对话数据（全站累计 token
  卡片、对话记录表：行展开查看输入/推理/输出全文，管理员可看全部用户并在线调整记录阈值）、调用日志（logs
  分页筛选：类型/关键字/模型/时间范围，管理员看全部、普通用户只看自己）、数据看板（时间范围+粒度自由选择、2×2 折线图：调用次数/输入/输出/缓存
  token，每模型一条线可选总计、手动刷新）；统计全部走预聚合表（`usage_stats` 小时桶 + `usage_summary` 单行汇总），不做原始日志全量求和
- **访客模式（方案 B：后端临时访客账号）**：`POST /user/guest` 自动创建随机访客账号（`is_guest=true` 仅作数据标记，令牌 24
  小时有效），权限与普通用户相同（可进控制台、管理密钥、修改资料）；过期访客惰性清理
- **模型工坊（对话式 Playground，前后端）**：三栏布局（会话侧边栏 / 对话窗口 / 参数面板，两侧可折叠），流式对话（SSE）支持思维链折叠展示、markdown
  渲染、token 用量与耗时、复制与重新生成、停止生成；会话本地存储（localStorage 按用户隔离，流式期间防抖落盘），支持新建 / 切换 /
  重命名 / 搜索 / 导出 Markdown / 删除 / 清空；参数面板含模型选择（按用户分组权限过滤）、System Prompt、temperature / top_p /
  max_tokens（上限随模型配置）；输入框支持多图上传与粘贴（≤5MB，视觉模型限定）、联网搜索开关（后端 agent 工具循环：模型发起
  web_search 调用后由后端执行阶跃 StepSearch 搜索并回传结果续写，前端实时显示搜索状态条；未配置 / 失败 / 上游不支持时自动降级为普通
  对话）、语音输入（MediaRecorder 录音 → 后端 ASR 代理 → 文本回填）；**工坊调用不计费**（跳过余额校验与扣款，日志
  cost 记 0，不写对话记录，token 照常进用量统计），分组权限与中转一致
- **接口鉴权分级**：公开（模型查询、渠道名列表）/ 需登录（密钥管理、资料修改、工坊对话与语音）/
  需管理员（模型增删改、渠道、运维、用户管理）；控制台概览/秘钥/兑换页对所有登录用户开放，管理页由前端路由守卫拦截非管理员
- **兑换码充值（前后端）**：管理员在控制台-兑换页批量生成兑换码（`AGC-` 前缀 + 去混淆字符集，单次 ≤100 张，
  支持批次/备注，生成结果一键复制）、分页筛选管理、停用未使用的码、四卡监控统计（发行/未使用/已使用/已核销金额）；
  普通用户输入兑换码即充值（访客禁止兑换），核销为单事务（SELECT FOR UPDATE 锁码防并发重复核销 → 状态机
  1未使用→2已使用 → `balance = balance + 面值` 原子加钱 → 同事务写日志），成功响应直接返回新余额、前端即时联动展示；
  页面双视图：所有登录用户可见兑换入口与「我的兑换记录」，管理区块仅管理员可见（生成/管理/监控）
- **维护 Agent（站点运维对话式 Agent，前后端）**：控制台「维护Agent」页（`/dashboard/agent`，仅管理员），三栏布局（会话侧栏 / 对话窗口 / 设置面板）；
  后端四阶段 agent 循环（排队→准备→执行→收尾）多轮调用站内任意已启用模型（可会话中切换，下一轮生效），每轮独立经中转链路计费（日志
  标注"维护Agent调用"、不写对话记录）；**27 个白名单运维工具**按风险三级管控——L0 只读（巡检/统计/拨测/用量）直接执行、L1
  低危写（渠道改配置/数据导出/技能增删）弹审批卡（可开会话级自动批准）、L2 高危（数据表清理，两阶段 dry-run 先行）强制审批 +
  每会话 ≤5 次 + 可整会话关闭（只读模式）；所有工具入参/出参递归**脱敏**（密钥只留 `前3****后4` 掩码）、结果截断 8KB、双轨审计（logs
  type=admin 流水 + `agent_message` 全轨迹含审批状态）；护栏：24 轮 / 200k token 上限、超长自动脱水压缩、截断防御（finish_reason=length
  拒绝工具调用）、审批 300s 超时、同会话并发 409；SSE 站内扩展事件 `agenticapi_agent`（工具进度 / 审批卡 / 模型切换 / 导出就绪）实时驱动前端；
  数据导出走一次性 token（24h 过期、仅一次）下载 zip；内置 6 个运维技能（巡检 / 数据治理 / 渠道排障 / 水位研判 / 新模型上线 / 故障复盘）+
  会话内可教学自定义技能（slug/大小/脱敏校验）；会话服务端持久化（近 30 天 + 每用户保留 50 个，惰性清理）
- **状态码语义**：401 = 未认证（前端清空登录态并弹登录框）；403 = 已登录但无权限（仅提示不登出）
- **接口规范**：站内管理接口统一响应格式 `{code, message, data}` + 全局异常处理器，规范文档见 [
  `backend/docs/API接口规范.md`](docs/API接口规范.md)；对外中转接口按 OpenAI 报文规范返回（成功透传上游、失败返回
  `{"error": {...}}`）

### 规划中

- 自定义路由模型（按策略转发上游）
- 在线充值支付链路（聚合支付 / 支付宝微信官方直连，兑换码已上线）
- MCP / Skills / CLI 连接管理，Agent 原生功能

## 技术栈

| 端   | 技术                                                                                                                                      |
|-----|-----------------------------------------------------------------------------------------------------------------------------------------|
| 前端  | Vue 3、TypeScript、Vite、Pinia、Vue Router、Arco Design Vue（字节跳动组件库，企业级 SaaS 亮色风格）、@lobehub/icons-static-svg（模型图标）、Axios、ECharts、markdown-it |
| 后端  | Python 3.12+、FastAPI、SQLAlchemy 2.0（asyncmy 异步驱动）、Pydantic、httpx                                                                        |
| 数据库 | MySQL                                                                                                                                   |

## 核心中转链路

对外提供 OpenAI Chat Completions 兼容接口，把请求透传到上游（同为 OpenAI 格式，暂不做格式转换，不支持 Anthropic / Responses
格式）：

```
调用方（OpenAI SDK / curl）
  │  Authorization: Bearer sk-xxx（用户在控制台创建的 API 密钥）
  ▼
POST /v1/chat/completions
  ├─ 1. 密钥鉴权：sk-xxx → api_key 表 → 用户（密钥禁用/账号封禁则拒绝）
  ├─ 2. 模型校验：模型存在且启用
  ├─ 3. 分组权限：free 用户只能调 free 分组模型，vip 可调全部
  ├─ 4. 余额校验：余额 ≤ 0 拒绝（402）
  ├─ 5. 渠道转发：按模型绑定的渠道顺序轮询，失败自动切下一个渠道；配置了 upstream_name 时，请求体 model 替换为上游名发往上游、响应里还原为对外名
  ├─ 6. 计费扣减：按 token 用量 × 模型定价（缓存命中按缓存价），SQL 原子扣减余额
  └─ 7. 调用日志：token 数量 / 费用 / 耗时 / 渠道写入 logs 表
```

- **模型映射**：模型可配置 `upstreamName`（实际请求上游用的模型名），为空时与对外名 `name` 相同、原样透传；配置后，请求发往上游时 `model` 字段替换为 `upstreamName`，响应（非流式顶层 / 流式每个 SSE 事件）里的 `model` 还原为对外名；日志与用量统计始终记对外名。
- **模型列表**：`GET /v1/models`（与中转同一套密钥鉴权）返回当前用户可调用的模型，OpenAI `{"object": "list", "data": [...]}` 格式；
  过滤口径与调用校验一致——模型启用 + 分组权限 + 至少绑定一个启用渠道，按名称排序；不计费、不校验余额，`upstreamName` / 渠道等内部配置不外泄。
- 流式（`stream: true`）与非流式都支持：SSE 原样转发，自动附加 `include_usage` 以在最后一个 chunk 获取用量计费；
- 报文规范：成功透传上游 JSON / SSE，失败返回 OpenAI 格式 `{"error": {message, type, code}}`（401 密钥无效 / 403 无权限 /
  402 余额不足 / 404 模型不存在 / 502 全部渠道失败）；
- 定价单位：每百万 token（与模型配置的 `inputPrice` / `cachePrice` / `outputPrice` 一致），缓存命中的 token
  按缓存价计、不重复收输入价；按次计费模型（`isRequestMode`）固定收 `perRequestPrice`。

## 用户体系与鉴权设计

整套流程一句话：**登录成功 → Token 存起来 → 每次请求自动带上 → 401 就踢回登录**。

### 后端（FastAPI）

| 环节                       | 实现                                                                                                 | 位置                              |
|--------------------------|----------------------------------------------------------------------------------------------------|---------------------------------|
| 注册 / 登录 / 访客 / 用户信息 / 登出 | `POST /user/register`、`POST /user/login`、`POST /user/guest`、`GET /user/info`、`DELETE /user/logout` | `backend/app/router/user.py`    |
| 密码加密                     | bcrypt（哈希存储，不可逆）                                                                                   | `backend/app/utils/security.py` |
| 令牌签发与校验                  | uuid4 随机串存 `user_token` 表，正式账号 30 天 / 访客 24 小时，重新登录即刷新                                             | `backend/app/crud/user.py`      |
| 接口保护                     | 依赖注入两级：`get_current_user`（需登录，访客与普通用户同权限）、`get_current_admin`（需管理员）                                | `backend/app/utils/auth.py`     |
| API 密钥管理                 | `GET/POST/PUT/DELETE /keys`，每用户最多 5 个，中转接口的访问凭证                                                    | `backend/app/router/keys.py`    |
| 兑换码（用户端）                | `POST /redeem` 核销充值（访客 403，返回新余额）、`GET /redeem/records` 我的兑换记录                                        | `backend/app/router/redeem.py`  |
| 兑换码（管理端）                | `POST /admin/redeem-codes/generate` 批量生成、`GET /admin/redeem-codes` 分页筛选、`GET /admin/redeem-codes/stats` 监控统计、`PUT /admin/redeem-codes/{id}/disable` 停用 | `backend/app/router/redeem.py`  |
| 用户管理（管理员）                | `GET/PUT/DELETE /admin/users`，分页搜索、改余额/分组/管理员/状态、批量删除                                              | `backend/app/router/admin.py`   |
| 系统日志                     | 统一写入口 `write_log`，记录 api / login / admin / user 四类                                                 | `backend/app/crud/log.py`       |

> 想给某个接口加登录要求，只需在参数里加一行 `_user=Depends(get_current_user)`（或更严格的 `get_current_regular_user`
> ），FastAPI 会在进入业务逻辑前完成校验。

### 前端（Vue3）

| 环节          | 实现                                                                       | 位置                                                                        |
|-------------|--------------------------------------------------------------------------|---------------------------------------------------------------------------|
| 令牌持久化       | localStorage（刷新不丢）+ Pinia（响应式状态）双层存放                                     | `frontend/src/stores/user.ts`                                             |
| 自动携带 Bearer | axios 请求拦截器统一附加请求头，业务代码无感                                                | `frontend/src/api/request.ts`                                             |
| 登录态失效处理     | 响应拦截器捕获 401，清空登录态并唤起登录弹窗                                                 | `frontend/src/api/request.ts`                                             |
| 注册 / 登录弹窗   | 导航栏右上角按钮触发，双模式切换，表单校验与后端字段约束一致                                           | `frontend/src/components/auth/AuthDialog.vue`                             |
| 访客模式        | 注意事项弹窗确认后调 `POST /user/guest` 创建临时账号，令牌 24 小时                            | `frontend/src/components/auth/GuestDialog.vue`                            |
| 页面级保护       | 控制台分级准入：未登录弹登录框，概览/秘钥页对所有登录用户（含访客）开放，管理页（`requiresAdmin`）仅管理员；侧边栏按角色过滤显示 | `frontend/src/router/index.ts`、`frontend/src/layouts/DashboardLayout.vue` |
| 概览页         | 个人基本信息（余额/累计消费/分组/注册与登录时间）、自助修改昵称手机号、兑换码充值入口占位                           | `frontend/src/views/Dashboard/Overview.vue`                               |
| 秘钥管理页       | 我的 API 密钥列表 / 创建（上限 5 个）/ 启停 / 删除                                        | `frontend/src/views/Dashboard/Keys.vue`                                   |
| 用户管理页（管理员）  | 分页搜索、行内编辑余额/分组/管理员/状态、批量删除                                               | `frontend/src/views/Dashboard/UserList.vue`                               |

### 访客模式（方案 B：后端临时访客账号）

点「访客」→ 弹注意事项 → 确认后后端创建 `guest_xxxx` 随机账号（随机密码不对外，无法用于登录），签发 **24 小时**
令牌，前端走与登录完全一致的令牌流程。访客**与普通用户权限相同**（可进入控制台、管理密钥、修改资料、调用中转接口），`is_guest`
字段仅作数据标记；管理类接口和页面仍区分管理员。过期/登出的访客账号在下一次创建访客时**惰性清理**（访客量大了可换定时任务）。

## 模型工坊设计

对话式 Playground，参考 Nexus「模型实验室」的交互结构用 Vue3 重新实现，走**站内接口 + 免费策略**：

```
前端（/studio，需登录）
  ├─ 左：会话侧边栏（新建/搜索/重命名/导出md/删除/清空）
  ├─ 中：对话窗口（流式渲染 + 思维链折叠 + 搜索状态条 + 用量统计）+ 输入框（图片/语音/联网搜索）
  └─ 右：参数面板（模型选择 / System Prompt / temperature / top_p / max_tokens）
        │  fetch + SSE 解析（不用 axios，报文为 OpenAI 风格）
        ▼
POST /studio/chat（get_current_user 登录鉴权）
  ├─ 组装消息：system_prompt 前置 + 过滤空消息 + 强制 stream
  ├─ 未开联网搜索：relay_service.chat_completions(..., api_key_id=None, source="studio")
  │    ├─ 复用：模型校验 / 分组权限 / 渠道轮询 / SSE 透传解析
  │    ├─ 跳过：余额校验、扣款（工坊免费）
  │    └─ 保留：调用日志（detail 标注"工坊"、cost=0）、用量统计（小时桶+汇总）
  │       不写 chat_record（监控页对话数据仅统计中转调用）
  └─ 开启联网搜索（配置了 STEPFUN_API_KEY）：studio_agent_service 工具循环
       ├─ 第 1 轮：带 web_search 函数工具请求上游，边转发 reasoning/content 增量边累积 tool_calls
       ├─ 命中 tool_calls → search_service 调阶跃 StepSearch MCP 端点（0.04 元/次计入
       │   Step Plan Credit）→ 消息追加 assistant(tool_calls) + tool(搜索结果) → 同渠道续轮
       ├─ 搜索起止通过站内扩展事件 {"agenticapi_search": {...}} 推送，前端渲染状态条
       ├─ finish_reason 不再是 tool_calls → 补聚合 usage + [DONE]，收尾（日志/统计，多轮 token 求和）
       └─ 兜底：最多 5 轮；未配置密钥不注入工具；上游 400/422 剥 tools 降级；搜索失败回错误
          文本让模型继续作答；非法 arguments 规范化后回传（兼容 ollama 等严格校验的上游）

POST /studio/asr（语音输入）
  └─ MediaRecorder 录音（webm/mp4，≤30s）→ base64 → 后端代理阶跃星辰
     stepaudio-2.5-asr（SSE 解析 transcript.text.done）→ 文本回填输入框
```

- **会话存储**：纯前端 localStorage（`agenticapi_studio_sessions_{userId}`），按用户隔离、上限 50 条、流式期间 500ms
  防抖落盘，后端零新表；参数与所选模型存 `agenticapi_studio_params_{userId}`；联网搜索状态条随消息一起持久化（刷新后仍显示"已联网搜索 N 次"）；
- **报文约定**：`/studio/chat` 与 `/v1` 中转接口一致走 OpenAI 风格（SSE 透传、错误 `{"error":{...}}`），是统一
  `{code,message,data}` 格式的例外；搜索状态事件 `{"agenticapi_search": {...}}` 为站内扩展字段，仅工坊前端消费；`/studio/asr` 为统一格式；
- **语音服务（可选）**：在后端 `.env` 配置 `STEPFUN_API_KEY=阶跃星辰密钥` 即可启用语音输入与联网搜索（同一把
  Key：语音走 ASR 代理，搜索走 StepSearch MCP 端点、0.04 元/次计入 Step Plan 月度 Credit），未配置时语音提示"语音服务未配置"、联网搜索自动降级为普通对话；
- **明确不做**（保持最小闭环）：多模型对比模式、TTS 朗读、Prompt 模板、消息编辑重发、追问建议自动生成（欢迎页保留 4 条静态提问卡片）。

## 项目结构

```
AgenticAPI/
├── backend/
│   ├── app/
│   │   ├── core/         # 配置、数据库引擎与会话
│   │   ├── router/       # API 路由层（channels / models / operations / user / keys / redeem / admin / monitor / relay / studio / site / maintain_agent）
│   │   ├── schemas/      # Pydantic 请求/响应模型（驼峰别名映射）
│   │   ├── services/     # 业务逻辑层（relay_service 核心中转、studio_agent_service 工坊搜索循环、search_service 联网搜索、agent_service 站内 Agent 能力、agent/ 维护Agent 循环与 27 工具、probe_service 渠道拨测、export_service 数据导出）
│   │   ├── crud/         # 数据访问层（原生 SQL）
│   │   ├── models/       # SQLAlchemy 表定义（user / user_token / api_key / redeem_code / logs / chat_record / usage_* / system_config / llm_* / agent_session / agent_message）
│   │   ├── agent_skills/ # 维护 Agent 内置技能（Markdown SOP，frontmatter 元数据）
│   │   └── utils/        # 统一响应、全局异常处理器、认证与安全工具等
│   ├── docs/             # 项目文档（API 接口规范等）
│   ├── .env              # 环境变量（MySQL 连接配置，不入库；可选 STEPFUN_API_KEY 开启工坊语音）
│   └── requirements.txt
└── frontend/
    └── src/
        ├── api/          # axios 封装（统一响应解包、Bearer 附带、401 处理）与接口请求（studio.ts 含 fetch SSE 流式解析）
        ├── stores/       # Pinia 状态（渠道列表、模型列表、用户登录态、工坊会话与参数）
        ├── components/   # 通用组件（auth/ 注册登录与访客弹窗，monitor/ 折线图，studio/ 工坊五件套）
        ├── views/        # 页面（模型广场 / 监控面板 / 工坊 / 控制台等）
        ├── router/       # 路由（含分级登录守卫）
        └── types/        # TS 类型定义
```

## 快速开始

### 环境要求

- Node.js ≥ 22（前端）
- Python ≥ 3.12（后端，依赖见 `backend/requirements.txt`）
- MySQL（本机 3306，或按 `.env` 配置）

### 后端

1. 在 `backend/` 下创建 `.env`（参考字段：`MYSQL_HOST` / `MYSQL_PORT` / `MYSQL_USER` / `MYSQL_PASSWORD` /
   `MYSQL_DATABASE` / `DEBUG`；可选 `STEPFUN_API_KEY` 配置后开启模型工坊的语音输入与联网搜索、`AGENT_TITLE_MODEL`
   开启会话自动起标题，不配则语音提示"语音服务未配置"、联网搜索自动降级为普通对话）；
2. 安装依赖并启动（表结构会在启动时自动创建）：

```sh
cd backend
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 2027
```

> **本机开发环境**：当前开发机使用 Miniconda 的 `agent` 虚拟环境（Python 3.12，依赖已安装），
> 启动前先 `conda activate agent` 再执行上面的 `python -m uvicorn ...` 即可，无需重复 `pip install`。

> **连接云端生产库调试（可选）**：云端 MySQL 只绑定服务器回环地址，公网不可直连。本地先开 SSH 隧道
> `ssh -N -L 13306:127.0.0.1:3306 sehwin`，再把 `backend/.env` 的 `MYSQL_PORT` 从 `3306`（本地库）改为
> `13306` 即可；两个端口互不冲突，本地库与云端库可并存、随时切换。注意：此模式下本地调试的读写会直接作用于生产数据。

> **本地与云端生产环境的差异**（云端部署于 `sehwin` 服务器 `/home/ubuntu/projects/AgenticAPI`，对外域名
> `platform.shienhao.cn`）：
>
> | 维度 | 本地开发 | 云端生产 |
> |---|---|---|
> | 数据库 | 本机 MySQL（`3306`，或隧道 `13306` 连云端） | Docker MySQL 8.0，仅绑服务器回环 `127.0.0.1:3306`，公网不可直连 |
> | 后端 | 手动 uvicorn（conda `agent` 环境），`DEBUG=True` | systemd 服务 `agenticapi.service`（conda `AgenticAPI` 环境），`DEBUG=False` |
> | 前端 | Vite 开发服务器 5173（`/api` 代理到 2027） | 仅部署 `npm run build` 产物 `dist`，nginx 托管并将 `/api` 反代到 2027 |
> | 对外暴露 | 无（全部只监听本机回环） | nginx + HTTPS（80 强制跳转 443） |
> | 数据 | 开发数据（本地库） | 生产数据（真实用户、密钥与计费） |
>
> **部署到云端（2026-09-22 起 Git 化）**：云端目录是 git 仓库（origin=GitHub），本地另配了 `prod` remote
> （`sehwin:projects/AgenticAPI`）经 SSH 直推，服务器不依赖 GitHub 网络。日常部署在项目根目录运行
> `deploy.bat`，一键完成：GitHub 备份推送 → 本地构建 → SSH 推送服务器代码 → 上传 `frontend/dist` →
> 仅当 `requirements.txt` 变化时安装依赖 → 重启服务 → 轮询验证（站点 200 / API 401）。
> 回滚：`ssh sehwin` 后 `cd ~/projects/AgenticAPI && git log` 找版本 → `git checkout <hash>` →
> `sudo systemctl restart agenticapi`。注意：服务器工作区须保持干净，勿直接在服务器上改代码；
> `backend/.env` 与 `backend/data/` 被 gitignore，独立于部署保留。

> **已有旧数据库的升级说明**：启动时的自动建表只创建不存在的表，不会给已存在的表加列。若你的 `user`
> 表是旧版本建的，需手动补齐缺失列（新装环境无需执行）：
>
> ```sql
> ALTER TABLE `user` ADD COLUMN is_guest TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为访客账号';
> ALTER TABLE `user` ADD COLUMN is_admin TINYINT(1) NOT NULL DEFAULT 0 COMMENT '是否为管理员';
> ALTER TABLE `user` ADD COLUMN balance DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '账户余额';
> ALTER TABLE `user` ADD COLUMN used_quota DECIMAL(12,6) NOT NULL DEFAULT 0 COMMENT '累计消费金额';
> ALTER TABLE `user` ADD COLUMN user_group VARCHAR(20) NOT NULL DEFAULT 'free' COMMENT '用户分组：free / vip';
> ALTER TABLE `user` ADD COLUMN status TINYINT(1) NOT NULL DEFAULT 1 COMMENT '账号状态：0封禁 1正常';
> ALTER TABLE `user` ADD COLUMN last_login_time DATETIME NULL COMMENT '最后登录时间';
> ```
>
> `api_key`、`logs` 两张新表由启动时的自动建表创建，无需手动处理。
>
> **v0.4.0 新增的表**（`chat_record` / `usage_stats` / `usage_summary` / `system_config`）同样由启动时的自动建表创建，
`logs` 表结构未改动，均无需手动 DDL。注意：聚合表与对话记录从本次部署后开始积累，此前的历史调用不会回填。
>
> **v0.6.0 新增的字段**：`llm_models` 表新增 `upstream_name` 列（模型映射，实际请求上游用的模型名，为空时用 `name`）。
> 已有库需手动执行：
>
> ```sql
> ALTER TABLE `llm_models` ADD COLUMN upstream_name VARCHAR(128) NULL COMMENT '实际请求上游用的模型名，为空时用 name';
> ```
>
> 新装环境由启动时的自动建表自动创建该列，无需手动处理。

### 前端

```sh
cd frontend
npm install
npm run dev        # 开发模式，http://localhost:5173
npm run build      # 生产构建
```

> 开发模式下 Vite 会把 `/api/*` 请求代理到后端 `http://localhost:2027`，无需额外配置跨域。

## 接口规范

所有接口统一返回 `{code, message, data}` 结构：成功时 HTTP 与业务码恒为
200；业务错误、参数校验失败（422）、数据库异常等由全局异常处理器统一格式化。字段使用驼峰命名。

**例外**：`/v1/chat/completions`（对外中转）、`/v1/models`（模型列表）与 `/studio/chat`（工坊对话）走 OpenAI 报文风格——成功透传上游
JSON / SSE 流或返回 OpenAI 结构（`/v1/models` 返回 `{"object": "list", "data": [...]}`），失败返回
`{"error": {message, type, code}}`，因为调用方需要按 OpenAI SDK 的约定解析（工坊前端用 fetch 手动解析 SSE，不经 axios 拦截器）。

完整规范（含各接口请求/响应示例与前端对接约定）见：[`backend/docs/API接口规范.md`](docs/API接口规范.md)

## 版本记录

| 版本     | 日期         | 说明                                                                                                                                                                                                                                                                                                                                                                                                                                                                              |
|--------|------------|---------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| v0.9.0 | 2026-10-05 | 站点维护 Agent 上线（控制台「维护Agent」页，仅管理员）：新增 `agent_session` / `agent_message` 两表（会话与全轨迹服务端持久化，含工具调用参数与审批状态变迁，近 30 天 + 每用户 50 会话惰性清理，启动自动建表）；后端四阶段 agent 循环（`app/services/agent/`）多轮驱动站内任意已启用模型（可中途切换、下一轮生效），每轮独立经中转链路计费（`_finalize_call` 新增 `source="agent"` 分支：扣费/写日志/进统计照常，唯一差异不写 `chat_record`）；**27 个白名单运维工具**三级风险管控——L0 只读 19 个直接执行，L1 低危写 5 个弹审批卡（会话级可开自动批准），L2 高危清理 3 个强制审批 + 两阶段 dry-run 先行 + 每会话 ≤5 次 + 可整会话关闭（只读模式）；工具全链路递归脱敏（键名/值形态双识别，密钥留 `前3****后4` 掩码，**库里与前端均无密钥原文**）+ 结果 8KB 截断 + logs type=admin 双轨审计；护栏：24 轮 / 200k token 上限、旧工具结果脱水 + 超限压缩、finish_reason=length 截断防御、审批 300s 超时、同会话并发 409、重启悬空 tool 消息修复；SSE 站内扩展事件 `agenticapi_agent`（tool_start/progress/end、confirm_required/resolved、model_switched、round_end、download_ready）；数据导出 zip + 一次性 token（24h 过期仅一次）；内置 6 个运维技能（`app/agent_skills/`）+ 会话内教学自定义技能（`DATA_DIR/agent_skills`，slug/32KB/脱敏校验，save/delete 均强制审批）；支撑服务新增 `probe_service`（渠道/模型直发拨测免计费）与 `export_service`（JSONL gzip zip 导出）；前端新增三栏对话页（会话侧栏/对话窗口/设置面板，模型选择按分组过滤）与 ToolStatusBar/ApprovalCard/DownloadCard 组件，fetch SSE 复用工坊解析骨架；本机 18 项冒烟全通过（含计费、审批、导出、模型切换、密钥零泄漏）；同步数据库设计文档（新增 5.12/5.13 节）。已知取舍：执行中不支持插话（同会话并发返回 409）；豆包 encrypted_content 加密片段仅内存跨轮、不持久化（重启丢失后自动剪除） |
| v0.8.1 | 2026-10-03 | 注册分组策略调整：正式注册用户统一进入 **vip** 分组（可调用全部分组模型），访客账号显式固定 **free** 分组（仅免费模型）；`create_user` 显式传 `user_group="vip"`、`create_guest_user` 显式传 `"free"`，`user_group` 列默认值保持 `free` 作最小权限兜底；存量用户不受影响，README/数据库设计文档同步 |
| v0.8.0 | 2026-10-03 | 兑换码充值链路上线：`redeem_code` 表（码值/面值/三态状态/批次/核销快照，唯一索引 + 批次/使用人索引，启动自动建表）+ 后端用户端（`POST /redeem` 核销、`GET /redeem/records` 记录）与管理端（`/admin/redeem-codes` 生成/分页/统计/停用）接口；核销单事务保证原子性（FOR UPDATE 锁码防并发重复核销 → 状态机 1→2 → 列表达式原子加余额 → 同事务写日志 `auto_commit=False`），访客 403 禁止兑换；前端控制台-兑换页开放给所有登录用户（侧边栏移出 adminPaths），双视图：兑换入口 + 我的兑换记录（全员）、四卡监控统计 + 生成/筛选/停用管理表格（仅管理员），生成结果码列表一键复制；概览页「余额充值」改为跳转兑换页（唯一兑换入口），兑换成功响应直接返回新余额前端即时联动；`docs/数据库设计文档.md` 同步 5.4 节。注意：`frontend/src/views` 下组件 `:style` 数字宽度（如 `{width: 200}`）在本机依赖组合下不生效（Vue 对象样式数字值不自动加 px，CSSOM 静默丢弃），本页已全部改为字符串 `'200px'`，其余页面存量写法待后续统一 |
| v0.7.4 | 2026-09-16 | 前端响应式修复 + 全站 UI 精修（纯视觉层，无逻辑/接口改动）。响应式：模型广场网格 `max-width: 1076px` 封顶居中（4×260 卡 + 3×12 间距，大屏恒每行 4 张，窄屏 auto-fill 自然降级）；控制台布局抽出 `.dashboard-container`（1280px 居中）统一覆盖概览/密钥/用户/渠道/运维五页。精修：全局细滚动条与 `::selection` 主色选中；焦点环/禁用文字色收敛为设计令牌（`--color-focus-ring` 等）；Arco 输入类聚焦柔光环、表格圆角裁剪、弹层遮罩轻毛玻璃；控制台统一 page-card 白卡骨架，密钥/渠道状态列改语义色圆点+文字，密钥 code 与行内编辑降噪，运维四卡按渠道加色脊线；模型卡 hover 升级（描边+投影+上浮）；顶栏毛玻璃；监控页筛选栏说明文字令牌化。监控 1440/文档 1024/首页 1080/工坊全宽保持不变 |
| v0.7.3 | 2026-09-16 | 下线深势科技 Coding Plan 用量监控：前端删除深势卡片、`bohrUsageData` 类型与 `refreshBohrUsage` 等刷新逻辑，监控卡片改为 2×2 布局（移除"敬请期待"占位卡）；后端删除 `services/upstream/bohr.py`、`/operations` 编排中的深势分支、`token_utils` 的 `coding_plan` 过期键与 schema 死字段，清理 `bohr_data.json` 调试快照；火山方舟用量查询不受影响（本就直接调用深势 BohrClaw 平台接口，`bohrclaw_token`/`bohrclaw_instance` 凭证链路完整保留）；全项目复查无深势监控残留 |
| v0.7.2 | 2026-09-16 | 新增 OpenAI 兼容模型列表接口 `GET /v1/models`：与 `/v1/chat/completions` 同一套 API 密钥鉴权，返回当前用户按分组权限可调用的模型（过滤口径与调用校验一致：模型启用 + free/vip 分组权限 + 至少绑定一个启用渠道，按名称排序，不泄露 `upstream_name` / 渠道等内部配置；不计费、不校验余额）；`relay` 路由抽出公共密钥鉴权函数供两个端点复用，原中转行为不变；无数据库改动；《API 调用文档》新增模型列表章节，同步更新接口规范例外清单与 README |
| v0.7.1 | 2026-08-21 | 移除商汤 SenseNova Coding Plan 用量监控：运维页第五张卡片改为占位卡（与第六张一致）；前端删除商汤卡片、凭证设置抽屉的商汤区块、`sensenovaUsageData`/`sensenovaModelUsage` 类型与 `refreshSensenovaUsage` 等刷新逻辑；后端移除 sensenova 上游适配（删除 `services/upstream/sensenova.py`、`data/response_data/sensenova_data.json`）、`/operations` 接口的 sensenova 编排与 `sensenovaToken`/`sensenovaAccountId` 凭证参数、`token_utils` 的商汤过期解析，清理 `operations_config.json` 中商汤字段；全项目复查无 sensenova/商汤 残留 |
| v0.7.0 | 2026-08-20 | 修复工坊联网搜索"一搜就结束任务"：根因是 web_search 以客户端函数工具透传，模型发出 tool_calls 后无人执行导致流中断。现由后端 `studio_agent_service` 实现 agent 工具循环——收到 tool_calls 后调阶跃 StepSearch MCP 端点真实执行搜索（新增 `search_service`，复用 STEPFUN_API_KEY，0.04 元/次计入 Step Plan Credit），结果以 role:tool 消息回传上游续写，对前端呈现为一条连续 SSE（多轮上限 5、方舟 encrypted_content 回传、非法 arguments 规范化、上游 400/422 与搜索失败均自动降级）；relay 抽出 `resolve_target` 供工坊循环复用，主链路行为不变；多轮 token 求和后统一进日志与用量统计（cost 仍为 0）；前端解析站内扩展事件 `agenticapi_search`，消息上方渲染搜索状态条（搜索中显示关键词 / 完成显示累计次数，随会话持久化）。已对全部 8 个上游渠道逐渠道实测通过 |
| v0.6.0 | 2026-08-17 | 模型映射上线：`llm_models` 表新增 `upstream_name` 字段（实际请求上游用的模型名，为空时回退 `name`、原样透传）；中转链路转发上游前按 `upstream_name` 替换请求体 `model`，响应里再把 `model` 还原为对外名（非流式替换顶层字段，流式逐个 SSE 事件替换，未配置映射时零开销）；模型工坊复用同一中转链路自动生效；前端模型新增/编辑表单加上游模型名输入；同步更新数据库设计、API 规范文档与旧库升级 SQL |
| v0.5.0 | 2026-08-16 | 模型工坊上线：三栏布局对话式 Playground（会话侧边栏/对话窗口/参数面板，两侧可折叠），SSE 流式对话（思维链折叠、markdown 渲染、token 用量、复制/重新生成/停止）；会话 localStorage 按用户隔离存储（流式防抖落盘、上限 50 条），支持新建/切换/重命名/搜索/导出 md/删除/清空；参数面板（模型按分组权限过滤、System Prompt、temperature/top_p/max_tokens 随模型上限钳制）；输入框多图上传与粘贴（≤5MB、视觉模型限定）、联网搜索（web_search 工具透传 + 失败降级重试）、语音输入（MediaRecorder + 阶跃 ASR 代理，需 .env 配 STEPFUN_API_KEY）；后端 `/studio/chat` 复用中转链路但**不计费**（日志 cost=0 标注工坊、不写对话记录、统计照常），`/studio/asr` 语音代理；中转服务新增 `source` 参数与可选 `api_key_id`，原中转行为不变 |
| v0.4.0 | 2026-08-16 | 监控面板上线（替换"路由模型"页）：对话数据（全站累计 token、对话记录表含输入/推理/输出全文，管理员可看全部用户并在线调整记录阈值，默认 5k token）、调用日志（logs 分页筛选，管理员全站/普通用户仅自己）、数据看板（时间范围与粒度自由选择、2×2 折线图分模型曲线+总计、手动刷新）；新增 `chat_record` / `usage_stats` / `usage_summary` / `system_config` 四张表，中转链路收尾统一为计费→日志→统计→条件记录对话（token 无条件记录，全文仅在模型 `is_log` 开启且未超阈值时落库）；前端引入 ECharts，路由守卫通用化（`requiresAuth` 对任意页面生效）                                                                                                                                  |
| v0.3.1 | 2026-08-16 | 访客权限放开：与普通用户一致（可进控制台、管理密钥、改资料），`is_guest` 仅作数据标记，管理接口仍区分管理员；概览页对所有用户开放：个人信息展示（余额/累计消费/分组/时间）、自助修改昵称手机号（新增 `PUT /user/profile`）、兑换码充值入口占位                                                                                                                                                                                                                                                                                                                                        |
| v0.3.0 | 2026-08-16 | 核心中转链路上线：OpenAI 兼容 `/v1/chat/completions`（API 密钥鉴权、分组权限、余额计费、渠道轮询、流式透传）；用户表扩展管理员/余额/分组/状态等字段；新增 `api_key`、`logs` 表；控制台新增秘钥管理页与用户管理页（管理员）；登录注册访客、密钥与管理员操作全部接入日志。详见《实现汇报-核心中转链路》                                                                                                                                                                                                                                                                                  |
| v0.2.2 | 2026-08-16 | 修复访客弹窗无法打开的问题：`defineModel` 未显式命名 `visible`，与父组件 `v-model:visible` 的 prop 名不匹配（不报错、类型检查也无法发现）；修复后经浏览器实测访客全链路（弹窗 → 创建账号 → 拦控制台 → 退出）                                                                                                                                                                                                                                                                                                                                             |
| v0.2.1 | 2026-08-16 | 访客模式升级为方案 B：新增 `POST /user/guest` 创建 24 小时临时访客账号，惰性清理过期访客；管理类接口改为要求正式账号（访客 403）；理顺状态码语义（401 未认证 / 403 无权限）；前端访客弹窗接通后端、路由守卫拦截访客进控制台                                                                                                                                                                                                                                                                                                                                              |
| v0.2.0 | 2026-08-16 | 用户体系落地：前端注册/登录弹窗与访客模式、Token 持久化与 Bearer 自动携带、路由登录守卫；后端接口鉴权分级（模型写操作/渠道/运维需登录，新增公开渠道名接口）；`user` 表新增 `is_guest` 预留字段；修复令牌续期与按令牌查用户两处缺陷                                                                                                                                                                                                                                                                                                                                             |
| v0.1.0 | 2026-08-16 | 首次整理：项目简介、结构说明、快速开始；全站接口统一响应规范落地（统一 200 业务码 + 全局异常处理器），新增 API 接口规范文档                                                                                                                                                                                                                                                                                                                                                                                                            |
