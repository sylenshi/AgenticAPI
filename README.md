# AgenticAPI

> LLM API 中转站平台 ｜ 当前版本 v0.14.0（2026-11-07）｜ 持续迭代中

基于 Agent 的 API 中转站：对外提供 OpenAI 兼容的大模型接口（密钥鉴权、分组权限、渠道轮询、按 token 计费），配套模型工坊 Playground 与站点维护 Agent（25 个白名单运维工具 + 容器沙箱）。前端 Vue3 + TypeScript，后端 FastAPI + Python（全异步），数据库 MySQL。

## 功能特性

- **核心中转**：`POST /v1/chat/completions`（OpenAI Chat 兼容，流式 / 非流式），`sk-` 密钥鉴权 → 模型 / 分组 / 余额校验 → 多渠道顺序轮询（失败自动切换）→ 按定价计费扣减 → 调用日志；`GET /v1/models` 返回当前用户可调用的模型列表
- **模型广场**：模型列表、搜索、分页；增删改含定价、渠道绑定、能力开关、模型映射（`upstreamName`，需管理员）
- **渠道管理**：上游渠道增删改查、启停、支持模型列表维护（需管理员）
- **用户体系**：注册 / 登录 / 访客模式（后端临时账号、令牌 24h、惰性清理），bcrypt 加密 + 不透明 Token；free / vip 分组权限（注册统一进 vip、访客固定 free），封禁与管理员体系
- **API 密钥**：每用户最多 5 个 `sk-` 密钥，控制台增删改查、启停
- **兑换码充值**：管理员批量生成（`AGC-` 前缀、四卡监控统计）、用户核销充值（单事务锁码，防并发重复核销）
- **监控面板**：对话数据（记录表行展开全文、管理员在线调阈值）、调用日志（管理员看全部 / 用户看自己）、数据看板（自由时间范围与粒度的折线图）；统计全走预聚合表，不做原始日志全量求和
- **模型工坊**：三栏 Playground（`/studio`），SSE 流式对话、思维链折叠、markdown 渲染、多图上传、语音输入、联网搜索（后端 agent 工具循环执行，失败自动降级普通对话）；**调用不计费**，会话 localStorage 按用户隔离
- **维护 Agent**（管理员，`/dashboard/agent`）：四阶段循环多轮驱动站内任意已启用模型（每轮独立计费），**25 个白名单运维工具**——需要密钥的上游操作（上游模型发现 / 候选模型试拨 / 密钥轮换）一律**后端代持密钥执行**，密钥不进对话上下文；**任务后台执行**（服务端托管，页面进出/刷新/断网不中断，重新进入自动回放+跟随）；写操作按右栏**审批三档位**管控（需要审批 / 部分审批 / 完全权限，档位 × 只读/可逆写/关键写查表；删除类两段式 dry-run + 删除类每会话 10 次、沙箱 30 次配额恒生效）；全链路密钥脱敏（`前3****后4`，密钥仅存于渠道配置本体，日志/消息/界面全掩码）、结果截断、双轨审计、40 轮 / 单任务成本上限（默认 ¥2，设置页可调）护栏，叫停自动小结并支持一键续跑；**会话记录一键导出**（Markdown，含工具调用与审批轨迹，排查归档用）；续轮渠道 failover；右栏上下文水位进度条；数据统计 / 清理由 data-governance 技能在沙箱内连库执行；内置 6 个运维技能、会话服务端持久化
- **容器沙箱**（v0.10.0，v0.11.0 支持连库）：`sandbox_exec` 在加固 Linux 容器内执行任意命令（curl / jq / python3+pymysql，可出公网），覆盖定制工具无法覆盖的长尾运维场景与数据治理脚本；弹卡与否由会话审批档位决定，全站共享单容器 + 懒启动 + 空闲自停，会话间目录隔离，非 root / 只读 rootfs / 资源限额；可选注入站内 MySQL 连接环境变量（`SANDBOX_MYSQL_HOST`，三种接入方式）
- **上游运维监控**：火山方舟 / 阶跃星辰 / 智谱 TokenPlan 用量监控与凭证管理（需管理员）
- **鉴权分级**：公开 / 需登录 / 需管理员三级；401 未认证（清登录态弹登录框）、403 已登录无权限（仅提示不登出）

## 核心中转链路

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

- **模型映射**：`upstreamName` 为空时与对外名相同、原样透传；配置后发往上游时替换、响应里还原，日志与统计始终记对外名
- **流式计费**：SSE 原样转发，自动附加 `include_usage` 在最后一个 chunk 获取用量
- **报文规范**：成功透传上游 JSON / SSE，失败返回 OpenAI 格式 `{"error": {message, type, code}}`（401 密钥无效 / 403 无权限 / 402 余额不足 / 404 模型不存在 / 502 全部渠道失败）
- **定价单位**：每百万 token；按次计费模型（`isRequestMode`）固定收 `perRequestPrice`

## 项目结构

```
AgenticAPI/
├── backend/
│   ├── app/
│   │   ├── core/         # 配置、数据库引擎与会话
│   │   ├── router/       # API 路由层（relay / studio / maintain_agent / user / keys / redeem / admin / monitor / channels / models / operations / site）
│   │   ├── schemas/      # Pydantic 请求/响应模型（驼峰别名映射）
│   │   ├── services/     # 业务逻辑层（relay_service 核心中转、agent/ 维护Agent 循环与 23 工具、sandbox_service 容器沙箱、studio_agent_service 工坊搜索循环、search_service 联网搜索、probe_service 拨测）
│   │   ├── crud/         # 数据访问层（原生 SQL）
│   │   ├── models/       # SQLAlchemy 表定义
│   │   ├── agent_skills/ # 维护 Agent 内置技能（Markdown SOP，frontmatter 元数据）
│   │   └── utils/        # 统一响应、全局异常处理器、认证与安全工具
│   ├── sandbox/          # 沙箱镜像 Dockerfile（运行时按指纹懒构建）
│   ├── .env.example      # 环境变量模板（含全部可选项说明）
│   └── requirements.txt
├── frontend/
│   └── src/
│       ├── api/          # axios 封装（统一解包、Bearer 附带、401 处理）与接口请求
│       ├── stores/       # Pinia 状态（登录态、渠道/模型列表、工坊会话）
│       ├── components/   # 通用组件（auth/ 注册登录访客弹窗，monitor/ 折线图，studio/ 工坊组件）
│       ├── views/        # 页面（模型广场 / 监控面板 / 工坊 / 控制台）
│       ├── composables/  # 组合式函数
│       ├── constants/    # 常量定义
│       ├── router/       # 路由（分级登录守卫）
│       └── types/        # TS 类型定义
├── docs/                 # 设计文档（接口规范、数据库设计、维护 Agent 文档、UI 规范等 4 份）+ changelog/（历次排查修复与版本演进记录）
├── deploy.bat            # 云端一键部署脚本（本地使用）
└── README.md
```

## 快速开始

### 环境要求

- Node.js ≥ 22（前端）、Python ≥ 3.12（后端）、MySQL（本机 3306 或按 `.env` 配置）

### 后端

```sh
cd backend
copy .env.example .env      # 按需修改 MySQL 连接；全部可选项见文件内注释
pip install -r requirements.txt
python -m uvicorn app.main:app --host 127.0.0.1 --port 2027
```

表结构启动时自动创建（只建不存在的表，已有表不自动加列）。可选能力（工坊语音 / 联网搜索 `STEPFUN_API_KEY`、会话起标题 `AGENT_TITLE_MODEL`、沙箱 7 项 `SANDBOX_*` 等）均在 `.env.example` 中有注释说明，不配置时对应功能自动降级或提示未配置。

### 前端

```sh
cd frontend
npm install
npm run dev        # http://localhost:5173，/api 代理到后端 2027，无需配跨域
npm run build      # 生产构建
```

> 生产部署形态：nginx 托管前端 dist + systemd 跑后端 + Docker MySQL（仅绑回环），HTTPS 对外。部署与回滚流程见本地 `deploy.md`（含服务器信息，不入库）。

## 接口规范

站内管理接口统一返回 `{code, message, data}`：成功时 HTTP 与业务码恒为 200，业务错误 / 422 / 数据库异常由全局异常处理器统一格式化，字段驼峰命名。

**例外**：`/v1/chat/completions`、`/v1/models`、`/studio/chat` 走 OpenAI 报文风格（调用方需按 OpenAI SDK 约定解析），失败返回 `{"error": {message, type, code}}`。

完整规范见 [`docs/后端API接口规范.md`](docs/后端API接口规范.md)。

## 文档索引

| 文档 | 内容 |
|---|---|
| [`docs/后端API接口规范.md`](docs/后端API接口规范.md) | 全部接口请求 / 响应示例与前端对接约定 |
| [`docs/数据库设计文档.md`](docs/数据库设计文档.md) | 全部表结构与设计说明 |
| [`docs/维护Agent设计文档.md`](docs/维护Agent设计文档.md) | 维护 Agent 设计与功能：循环与护栏、审批三档位与脱敏机制、25 个工具清单 |
| [`docs/前端UI构建规范.md`](docs/前端UI构建规范.md) | 前端视觉与组件规范 |
| [`docs/changelog/`](docs/changelog) | 历次全面排查的修复清单、遗留问题与维护 Agent 版本演进记录 |

## 规划中

- 自定义路由模型（按策略转发上游）
- 在线充值支付链路（兑换码已上线）
- MCP / Skills / CLI 连接管理，Agent 原生功能

## 版本记录

| 版本 | 日期 | 说明 |
|---|---|---|
| v0.14.0 | 2026-11-07 | 维护 Agent 安全用钥通道：需要密钥的上游操作改为后端代持密钥执行（Agent 只引用渠道名，密钥不进对话上下文/沙箱）——新增 `list_upstream_models`（代持密钥拉上游 /models 清单做模型发现，404 提示改走试拨）、`test_channel` 放宽为可试拨声明列表外候选模型（`notInDeclaredList` 标注）、恢复 `rotate_channel_key`（L2 审批卡只显尾 4 位，凭证到期可闭环）；工具 23→25（L0 15 / L1 3 / L2 7）；修正系统提示词与沙箱描述"拉上游模型清单用沙箱"的自相矛盾指引；新增会话记录一键导出（`GET /sessions/{id}/export` Markdown：正文/工具调用/结果/审批轨迹，右栏侧边栏按钮自动下载）；无需 DDL |
| v0.13.0 | 2026-11-07 | 维护 Agent 任务与请求解耦：`POST /maintain-agent/chat` 改为提交服务端托管的后台任务（立即返回，同会话并发 409），新增 `GET /sessions/{id}/stream` 订阅事件流（回放缓冲 + 实时跟随 + 15s 心跳防代理超时）与 `POST /sessions/{id}/stop` 停止端点，会话列表带 `running` 标记；页面进出 / 刷新 / 断网不再中断任务，重新进入会话自动回放+跟随续看进度；前端移除"切换会话自动停止"逻辑，停止按钮改为取消服务端任务；无需 DDL |
| v0.12.0 | 2026-11-07 | 维护 Agent 护栏与工具体系重构：护栏以单任务成本上限（默认 ¥2，设置页可调）替代累计 token 预算，轮数 24→40 且末段软提示软着陆，叫停发 task_paused 支持前端一键续跑；修复压缩兜底失效与续轮零容错（统一 `_open_round`：复用渠道 + 重试 + 跨渠道 failover）；工具体系删除 always_confirm 标记，原强审 5 工具按行为等价并入等级（create_channel / create_model / delete_skill / sandbox_exec → L2 关键写，save_skill → L1），执行上限改为按工具声明的会话配额（删除类 10 次、沙箱 30 次），阀门收敛为档位 × 等级一张查表；`agent_message` 加 `tool_name` 列（配额按工具名计数）；前端右栏下线风险等级图例、审批卡与帮助文案去内部分级话术，设置页新增单任务成本上限；需手动 DDL：`agent_message` 加 `tool_name` 列 |
| v0.11.0 | 2026-11-07 | 维护 Agent 三项改进：工具精简 36→23（下线 rotate_channel_key / get_redeem_stats / query_users / switch_model，合并上游用量与凭证到期，数据治理 8 工具改由 data-governance 技能 + 沙箱连库脚本承载，导出链路下线）；审批分级收敛为三档位（需要审批 / 部分审批 / 完全权限，L2 每会话 5 次上限恒生效）；右栏新增上下文水位进度条（round_end 新增 contextTokens）；沙箱可选桥接站内 MySQL（SANDBOX_MYSQL_HOST）+ 镜像加装 pymysql；需手动 DDL：`agent_session` 加 `approval_mode` 列 |
| v0.10.1 | 2026-11-07 | 第 1 次全面排查修复（后端 13 项 / 前端 16 项 / 数据库 12 项）：封禁令牌即时失效、拨测改 POST + 60s 频控、注册分组站点可配、404/405 与 OpenAI 路径报文统一、数据库唯一约束 / 索引补齐、时区统一 +08:00 等；完整清单见 `docs/changelog/` |
| v0.10.0 | 2026-11-05 | 维护 Agent 能力扩展（27 → 36 工具）：容器沙箱 `sandbox_exec`、渠道 / 模型 CRUD、联网搜索工具、密钥脱敏加固 |
| v0.9.0 | 2026-10-05 | 维护 Agent 上线：四阶段循环、27 白名单工具三级风险管控、审批卡、6 内置技能、会话服务端持久化 |
| v0.8.1 | 2026-10-03 | 注册分组策略调整：注册统一进 vip、访客固定 free |
| v0.8.0 | 2026-10-03 | 兑换码充值链路上线（生成 / 核销 / 监控，单事务防并发） |
| v0.7.4 | 2026-09-16 | 全站 UI 精修 + 响应式修复（纯视觉层） |
| v0.7.3 | 2026-09-16 | 下线深势 Coding Plan 用量监控（火山方舟查询链路保留） |
| v0.7.2 | 2026-09-16 | 新增 OpenAI 兼容模型列表接口 `GET /v1/models` |
| v0.7.1 | 2026-08-21 | 移除商汤 SenseNova 用量监控 |
| v0.7.0 | 2026-08-20 | 工坊联网搜索修复：后端 agent 工具循环真实执行搜索，多轮续写 |
| v0.6.0 | 2026-08-17 | 模型映射上线（`upstream_name` 请求替换 / 响应还原） |
| v0.5.0 | 2026-08-16 | 模型工坊上线（三栏 Playground，流式 / 图片 / 语音 / 联网搜索，不计费） |
| v0.4.0 | 2026-08-16 | 监控面板上线（对话数据 / 调用日志 / 数据看板，预聚合统计） |
| v0.3.1 | 2026-08-16 | 访客权限放开（与普通用户一致，`is_guest` 仅作标记） |
| v0.3.0 | 2026-08-16 | 核心中转链路上线（密钥鉴权 / 分组权限 / 计费 / 渠道轮询 / 流式透传） |
| v0.2.2 | 2026-08-16 | 修复访客弹窗无法打开（`defineModel` 未显式命名） |
| v0.2.1 | 2026-08-16 | 访客模式升级为方案 B（后端临时账号，24h 令牌） |
| v0.2.0 | 2026-08-16 | 用户体系落地（注册登录弹窗 / Token 持久化 / 路由守卫 / 鉴权分级） |
| v0.1.0 | 2026-08-16 | 首次整理：项目简介、结构说明、快速开始、统一响应规范 |

> 各版本完整变更细节见 `git log`。
