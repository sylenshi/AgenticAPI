# AgenticAPI 站点维护 Agent · 设计与功能文档

> 文档版本：v1.2（v1.0 实施于 v0.9.0；v1.1 增补审批式容器沙箱与渠道/模型 CRUD，实施于 v0.10.0；v1.2 合并原设计文档与功能清单并精简）｜ 日期：2026-11-05

## 1. 形态概述

**"白名单工具 + 服务端工具循环 + 人审阀门 + 站内模型即 Provider"的对话式运维 Agent**，入口 `/dashboard/agent`（仅管理员）。

把分散在各管理页的运维能力（渠道管理、用量监控、模型拨测、数据治理等）下沉为**白名单工具**，由对话式 Agent 编排执行——管理员一句话完成"测一下所有渠道"、"导出并清理三个月前的对话记录"、"出一份巡检报告"这类复合任务。

四条核心特征：

- **大脑可插拔**：驱动模型可切换为站内任意已启用模型（走中转链路，天然享受渠道轮询容错），会话中途可换；
- **手是白名单 + 一个审批式沙箱**：36 个封闭注册的工具，宿主机上无 shell、无任意命令、无通用文件访问；唯一长尾出口是 `sandbox_exec`——隔离容器内执行、每条命令强制审批；
- **高危有阀门**：L1/L2 写操作必须经管理员审批卡确认，L2 另有 dry-run 两段式第二道闸；
- **全程留痕**：会话消息（含工具与审批轨迹）服务端持久化，工具执行另写 `logs` 审计。

```mermaid
flowchart LR
    FE["前端 /dashboard/agent<br/>对话窗口 + 模型选择器 + 审批卡片"]
    API["POST /maintain-agent/chat (SSE)<br/>POST /maintain-agent/approve"]
    LOOP["Maintain Loop<br/>四阶段循环 + 事件总线"]
    TOOLS["工具执行器<br/>白名单注册表 + 脱敏 + 分级审批"]
    BRAIN["模型大脑<br/>站内任意模型·可切换"]
    DB[("MySQL<br/>agent_session / agent_message")]
    FE -->|Bearer 管理员令牌| API --> LOOP
    LOOP <--> BRAIN
    LOOP --> TOOLS --> DB
    LOOP -->|SSE 事件流| FE
    TOOLS -->|导出文件| FILES["backend/data/exports/*.zip"]
```

核心机制借鉴了成熟 Coding Agent Harness 的四阶段循环、Error as Data（错误回传模型自愈）、输出截断时拒绝执行工具、Skills 目录按需加载、执行中插话排队等设计，并按运维场景改造；两点关键差异——模型侧从"固定 Provider"改为"站内模型即 Provider"，工具侧坚持封闭白名单、不引入宿主机通用工具（容器沙箱是唯一受控例外）。

三条产品红线（贯穿所有功能，详见第 9 节）：

1. **密钥不可见**：上游密钥只在后端内存与库表中，模型上下文、前端、落库三处均为掩码版；
2. **无未审批的 shell**：宿主侧封闭白名单，任意命令仅存在于隔离容器且每条强制审批；
3. **高危必人审**：破坏性操作必须管理员确认，全过程审计落库。

## 2. Agent 循环与护栏

主循环四阶段（`maintain_loop`），执行期间管理员的新消息入队、下一轮合并（插话不中断）：

| 阶段 | 职责 |
|---|---|
| ① queue | 消费新消息与执行期间的插话，合并为 user 消息 |
| ② prepare | 请求装配（唯一转换边界）：读会话当前模型与窗口 → 历史脱水检查 → 注入 system prompt（角色 + 安全规则 + 工具目录 + skill 目录）与 tools 白名单 |
| ③ execute | 流式调用模型（SSE 透传给前端）；收到 tool_calls 则走工具执行器，结果以 role:tool 回传进入下一轮 |
| ④ settle | 本轮 usage 计账、消息落库；检查轮次 / token 预算 / L2 次数，决定继续或 `[DONE]` 收尾 |

护栏参数：

| 护栏 | 默认值 | 说明 |
|---|---|---|
| 单次工具循环轮数 | 24 | 防死循环烧 token |
| 单工具超时 | 30s（批测类自声明 180s） | 超时返回 isError 回传模型 |
| 会话 token 预算 | 200k（会话可调） | 超预算 Agent 汇报后停止 |
| L2 每会话执行上限 | 5 次 | 超出拒绝并提示走管理页 |
| 审批等待超时 | 300s | 超时自动拒绝 |

关键防御机制：

- **截断防御**：`finish_reason == "length"`（输出被截断）时，本轮全部 tool_calls 判失败不执行——防残缺参数触发危险操作；
- **Error as Data**：任何失败（参数错、超时、上游 5xx、审批被拒）不中断 SSE、不抛异常，统一包装 `{isError: true, message}` 回传模型，由模型自我修正（如纠正渠道名拼写）或向管理员求助；仅会话级致命错误（数据库失联）走 SSE error 收尾。

## 3. 模型接入与计费

Agent 大脑的每次请求**不走独立 LLM SDK，而走本站中转链路**（`relay_service` 扩展 `source="agent"` 分支）：模型校验、渠道轮询容错、模型名映射、计费、用量统计与普通中转完全一致，**唯一差异是不写 chat_record**（维护对话独立存储，避免混进业务监控页）。

模型切换三途径：前端选择器（下一轮生效）/ 对模型说"换 glm-4.7 继续"（`switch_model` 工具，推送 `model_switched` 事件）/ 默认模型解析链（system_config → `.env` → 内置推荐值）。切换时若上下文超出目标模型窗口 70% 则先脱水压缩；目标模型不支持 function calling 时剥掉 tools 降级为纯对话并提示。

计费口径：

- **Agent 大脑调用**：完全复用中转计费链路，按模型定价扣**管理员个人余额**、cost 如实写 logs（不做免计费豁免，余额不足时链路自然 402，Agent 提示管理员）；
- **拨测类工具**：直发上游免计费（不经中转，消耗可忽略）；
- **查询 / 导出类工具**：只读，无模型消耗。

## 4. 工具系统与审批阀门

### 4.1 注册表与执行流水线

每个工具是注册表中的一个声明式条目（schema + 风险等级 + 超时 + handler），主循环不感知具体工具；扩展新工具只挂注册表，不改主循环。发给模型的 tools 按场景裁剪（会话可关 L2 进"只读模式"）。

每次工具调用必经的执行流水线：

```
解析 tool_calls → 截断防御 → 参数 Schema 校验（失败回传可行动原因）
  → 风险阀门（L0 直行 / L1·L2 进审批）→ 执行
  → 结果脱敏 redact() → 截断（≤8KB，摘要式）
  → role:tool 回传 + agent_message 落库 + logs 审计 + SSE 事件
```

### 4.2 风险分级

| 级别 | 定义 | 交互 |
|---|---|---|
| L0 | 只读 / 无副作用 | 直接执行，SSE 状态条可见 |
| L1 | 低危写：可恢复或仅产生文件 | 审批卡，可被会话级"L1 自动批准"跳过 |
| L2 | 高危写：不可逆删除 | 强制审批 + 工具内部 dry-run 两段式 + 每会话 ≤5 次 |

两个补充规则：

- **always_confirm 强制人审**：部分 L1 工具（`save_skill` / `delete_skill` / `sandbox_exec` / `create_channel` / `rotate_channel_key` / `create_model`）的写入内容影响大或不可示人，即使开了"L1 自动批准"也必须走审批卡；
- **L2 两段式**：首次调用 `dry_run=true` 只做影响预览（如"预计删除 123,456 行"、删除渠道会产生哪些孤儿引用），管理员在审批卡上看到预览并批准后，第二次 `dry_run=false` 才真执行。

审批实现要点：审批状态内存 Event + 同步落库（`agent_message.approval_status`）；服务重启后未决审批一律置 timeout；approve 端点校验审批归属当前管理员；被拒结果以 isError 回传模型且同参调用做一轮冷却。分级阀门是**代码强制路径**（handler 入口第一行检查），与模型是否"听话"无关，不依赖 prompt 约束。

## 5. Skills 机制（按需加载的运维 SOP）

- 存放两处合并加载：`backend/app/agent_skills/*.md`（内置，随代码部署）+ `backend/data/agent_skills/*.md`（管理员自定义，覆盖同名内置）；
- 格式：frontmatter（name / description / triggers）+ 正文 SOP；**system prompt 只注入目录**（每条一行），全文由 `load_skill`（L0）按需读取，控制每轮固定 token 开销；
- 触发：模型按目录 description / triggers 自行匹配，或管理员显式指定；Skill 全文进入上下文后作为软约束（可按实际情况跳步，偏离需说明理由）。

6 个内置 Skill：

| Skill | 内容要点 |
|---|---|
| `site-inspection` | 巡检编排：渠道连通 → 模型巡检 → 额度水位 → 存储水位 → 评分卡报告 |
| `data-governance` | 数据治理：容量统计 → 导出 → 备份校验 → dry-run 预览 → 清理 → 复核 |
| `channel-troubleshooting` | 渠道排障：复现 → 归因（连通 / 凭证 / 额度 / 映射）→ 处置建议 |
| `quota-watchdog` | 额度水位研判：三窗口解读、预警阈值（80% 橙 / 95% 红）、临期提醒 |
| `model-onboarding` | 新模型上线检查单：定价 → 渠道绑定 → 拨测 → 上线文案 |
| `incident-review` | 故障复盘：时间范围 → logs 检索 → 时间线 → 根因 → 改进项 |

自定义教学保存：管理员可让 Agent 把现场总结的经验固化为新 skill（`save_skill` / `delete_skill` / `list_skills`）。安全约束——写操作 always_confirm 强制全文审批；落盘前过 `redact()`；name 强制 slug 校验防路径穿越；单文件 ≤32KB；仅可写 `data/agent_skills/` 单目录，内置 skill 物理隔离不可覆盖；保存 / 删除各写一条 admin 日志。

## 6. 上下文管理

运维会话历史短（通常 ≤24 轮），压力主要来自**工具结果**（全量巡检报告、日志明细）。两级策略：

1. **脱水（主策略）**：已被消费的隔轮工具结果（距最新消息 >4 轮）替换为一句话占位摘要，tool_call 与 tool_result 成对替换；
2. **压缩（兜底）**：估算 token 超过当前模型窗口 70% 时，把脱水后的早期历史交当前模型生成结构化摘要（Goal / Progress / Key Decisions / Next Steps）替换原历史；切换小窗口模型时立即检查。

导出文件是泄压阀：大结果类工具（巡检明细、日志导出）落地为 zip，上下文只留链接与摘要。

## 7. 数据持久化

两张表（完整字段见[数据库设计文档](数据库设计文档.md) 5.12 / 5.13 节，启动自动建表）：

- **`agent_session`**：会话（所属用户、标题、当前模型、L1 自动批准与 L2 开关、状态）；
- **`agent_message`**：全轨迹消息（role / content / tool_calls / 风险等级 / 审批状态 / token 用量）。**落库的是 redact() 之后的版本**，库里不存密钥原文；导出文件不进消息表，只在 content 里留下载链接。

审计双轨：`agent_message`（会话视角完整轨迹）+ `logs`（type=admin 全站审计流，含审批状态变迁）。

会话保留策略：每用户最多保留**最近 50 个**、仅保留**近 30 天**；新建会话时后台惰性清理（联动删消息，写 admin 日志），不引入定时任务。

## 8. SSE 协议（事件清单）

正文走 OpenAI 风格增量（`choices[0].delta.content / reasoning_content`），站内扩展统一挂 `agenticapi_agent` 字段：

| 事件 | 载荷要点 | 前端渲染 |
|---|---|---|
| `tool_start` | `{tool, digest}` | 工具状态条（"正在测试渠道 zai …"） |
| `tool_progress` | `{tool, done, total}` | 批测进度（18/30 模型） |
| `tool_end` | `{tool, ok, summary}` | 状态条转结果（成功绿 / 失败红 + 摘要） |
| `confirm_required` | `{approvalId, tool, args, impact, riskLevel, expiresIn}` | **审批卡**：参数 + 影响预览 + 倒计时 + 批准/拒绝 |
| `confirm_resolved` | `{approvalId, result}` | 卡片置灰标注结果 |
| `model_switched` | `{from, to}` | 模型联动 + 轻提示 |
| `round_end` | `{round, usageSoFar}` | 用量脚注 |
| `download_ready` | `{url, label, size, expiresAt}` | 下载卡片 |
| `sandbox_output` | `{tool, chunk}` | 沙箱实时输出（折叠控制台） |
| `dehydrated` | `{tool, summary}` | 折叠占位提示（长会话） |

错误语义：会话级致命错误返回 `data: {"error": {…}}` + `[DONE]` 收尾；401 复用前端现有拦截逻辑。

## 9. 安全红线

1. **密钥闭环**：渠道密钥仅存在于后端内存与 `llm_channels` 表；所有工具返回值经 `redact()` 递归脱敏（键名匹配 `api_key/token/password/authorization/cookie` 的字段替换为尾 4 位掩码，长文本内嵌的 `sk-…` / `Bearer …` 子串同样掩码）后才进模型上下文、前端、消息表——三处同源同过滤器；`agent_message.tool_calls` 落库与历史回显用脱敏版（执行仍用原文）；
2. **封闭工具面**：宿主机侧无 shell、无通用文件读写、无 SQL 直通（每个 handler 是显式函数，参数经校验）。prompt 注入最坏只能诱导模型调白名单工具，L2 仍有人审；`sandbox_exec` 是唯一任意命令入口——容器隔离 + 每条强制审批；
3. **鉴权**：`/maintain-agent/*` 全部 `get_current_admin`；approve 校验审批归属；导出 token 一次性 + 24h 过期；
4. **审计**：工具执行、审批变迁、模型切换全落库（双轨）；
5. **数据库安全**：清理只走带条件分批 DELETE（每批 5000 行 + 批间休止），禁 TRUNCATE / DROP；dry-run 用 COUNT 预览；
6. **资源护栏**：轮次 / 单工具超时 / token 预算 / L2 次数四重上限；批测并发信号量限 5；
7. **截断防御**：模型输出被截断时其工具调用一律拒绝执行。

## 10. 容器沙箱（v1.1）

`sandbox_exec` 在隔离 Linux 容器内执行任意命令（镜像 python:3.12-slim + curl / jq / httpx，可出公网），覆盖定制工具无法覆盖的长尾场景：给定 base_url/key/model 直发验证、拉上游 `/v1/models` 对比定价、脚本化批量诊断。

| 维度 | 设计 |
|---|---|
| 容器模型 | 全站共享单容器；会话间以 `/workspace/s{会话id}` 工作目录隔离；容器停止即清空（无持久化诉求） |
| 生命周期 | 懒启动（首个获批命令触发镜像按指纹懒构建，Dockerfile 或任一镜像源配置变化自动重建）→ 空闲 900s 自动 `docker stop`（保留容器与镜像，下次秒级拉起） |
| 驱动 | docker CLI 子进程（零新依赖，Windows 本机与 Linux 云端行为一致）；`SANDBOX_DOCKER_CMD` 可配 `sudo -n docker` |
| 隔离加固 | 独立网桥、非 root、`--cap-drop ALL` + `no-new-privileges`、只读 rootfs + tmpfs、内存 / CPU / pids 限额、不挂载宿主路径与密钥；生产 MySQL 绑宿主回环，容器网络层不可直达 |
| 执行语义 | 命令经容器内 `timeout` 包裹；stdout/stderr 流式经 `sandbox_output` 事件推前端（节流 + 保尾部 64KB）；最终结果过 `redact()` + 8KB 截断 |
| 审批 | L1 + always_confirm：每条命令必弹审批卡（展示完整命令），不受"L1 自动批准"影响，不占 L2 配额，只读会话仍可用 |
| 配置 | `SANDBOX_*` 共 9 项全部可选有默认值（见 `backend/.env.example`）；换 `SANDBOX_BASE_IMAGE` / `SANDBOX_PIP_INDEX_URL` / `SANDBOX_APT_MIRROR` 任意一项自动触发镜像重建 |

`sandbox_status`（L0）查询 Docker 可用性 / 镜像就绪 / 容器状态 / 空闲时长。

残余风险：沙箱可访问公网任意地址（功能需求本身）；容器与宿主共享内核（Docker 隔离级别，非 VM）；审批卡是最终人闸，管理员需阅读命令再批准。

## 11. 前端交互

三栏布局：会话侧栏（新建 / 搜索 / 重命名 / 删除）+ 对话窗口（消息流、工具状态条、审批卡、下载卡片、沙箱折叠控制台、输入框 + 停止按钮）+ 右侧面板（模型选择器、skill 目录、会话设置：L1 自动批准 / L2 开关）。

实现要点：消息列表复用工坊 `ChatMessages.vue`（纯展示组件）；输入框新写 `AgentInput.vue`；SSE 解析复用工坊解析骨架并泛化，新增 `agenticapi_agent` 事件分发；审批批准 / 拒绝调 `POST /maintain-agent/approve`；下载卡片走导出端点。

## 12. 功能清单（36 工具 + 内建能力）

按域分组的全部工具（等级与第 4.2 节分级对应；明细一句话说明，参数以注册表 schema 为准）：

### A. 渠道管理

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| A1 渠道查询 | `list_channels` | L0 | 全量渠道信息与绑定关系，密钥只回尾 4 位 |
| A2 渠道连通测试 | `test_channel` | L0 | 注入密钥直发极小探测请求，单模型抽查或全模型遍历（并发限 5），免计费 |
| A3 渠道配置修改 | `update_channel` | L1 | 启停 / 超时 / 描述 / 支持模型；审批卡展示字段级 diff；**不改密钥**（走管理页） |
| A4 绑定一致性检查 | `check_binding_consistency` | L0 | 渠道-模型双向软引用交叉比对，输出不一致清单与修复建议，只报告不修复 |
| A5 新增渠道 | `create_channel` | L1+强审 | 新上游接入；密钥仅入参→落库瞬时存在，审批卡只显尾 4 位 |
| A6 密钥轮换 | `rotate_channel_key` | L1+强审 | 换渠道密钥，其他配置不变；全程脱敏 |
| A7 删除渠道 | `delete_channel` | L2 两段式 | dry-run 预览反向绑定影响（孤儿引用），确认后真删 |

### B. 上游用量

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| B1 用量查询 | `get_upstream_usage` | L0 | 各上游 TokenPlan 5h / 周 / 月三窗口用量与重置时间（复用 operations_service） |
| B2 凭证到期查询 | `get_token_expiry` | L0 | 各上游凭证过期时间，临期（≤7 天）主动标注提醒 |

### C. 出站模型

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| C1 模型查询 | `get_model_info` | L0 | 定价 / 分组 / 渠道绑定（含映射）/ 状态 / 窗口 |
| C2 单模型拨测 | `test_model` | L0 | 按绑定渠道顺序逐个直发探测（免计费），返回每渠道结论 |
| C3 全量巡检 | `test_all_models` | L0 | 遍历全部启用模型拨测（并发限 5、总超时 180s、进度实时上报），汇总可用率 + 失败清单，大表明细转导出文件 |
| C4 新增模型 | `create_model` | L1+强审 | 含定价四件与渠道绑定；定价决定计费，审批卡展示完整配置 |
| C5 模型配置修改 | `update_model` | L1 | 字段级 diff 预览；模型名不可改；可解绑 / 改绑渠道 |
| C6 删除模型 | `delete_model` | L2 两段式 | dry-run 展示渠道侧孤儿声明影响，确认后真删 |

新上游标准上线链路：`create_channel` → `test_channel` → `create_model` → `test_model`。

### D. 数据治理

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| D1 对话记录容量统计 | `get_chat_record_stats` | L0 | 行数 / 存储占用 / 按月分布 / 最早最新时间 + 清理建议 |
| D2 对话记录导出 | `export_chat_records` | L1 | 分批流式读 → JSONL gzip zip 落 `data/exports/`，只回下载链接（一次性 token，24h 过期），数据本体不进上下文 |
| D3 对话记录清理 | `cleanup_chat_records` | L2 两段式 | 按保留天数 / 条数清理；默认先自动全量备份；分批 DELETE（每批 5000 + 休止）防锁表 |
| D4 调用日志治理 | `get_log_stats` / `export_logs` / `cleanup_logs` | L0/L1/L2 | 与 D1~D3 同构，作用于 `logs` 表，默认保留近 90 天 |
| D5 聚合表治理 | `get_aggregate_stats` / `cleanup_aggregate_stats` | L0/L2 | `usage_stats` 小时桶按月清理，同样两段式 |

### E. 运营速查（全部只读）

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| E1 站点概览 | `get_site_overview` | L0 | 今日 / 昨日调用与消费、用户数与活跃、全站余额池 |
| E2 用量趋势 | `get_usage_trend` | L0 | 时间范围 + 粒度的每模型调用量 / token / 费用序列（回传 Top5 摘要） |
| E3 兑换码统计 | `get_redeem_stats` | L0 | 发行 / 未使用 / 已使用 / 已核销金额四卡 |
| E4 用户查询 | `query_users` | L0 | 搜索 / 余额排行 / 封禁名单；**只读**，改用户走管理页 |

### F. 系统内建（harness 能力，非独立工具为主）

- **F1 一键巡检**：`generate_health_report`（L0）聚合 A2 + C3 + B1/B2 + D1/D4，按 `site-inspection` skill SOP 产出评分卡报告；仅由管理员对话触发，**不做定时巡检**；
- **F2 工具执行审计**：内建——每次执行（含被拒）写 admin 日志，可回答"Agent 昨天都干了什么"；
- **F3 会话管理**：内建——服务端持久化、历史列表、继续对话、删除、自动起标题（复用现有起标题逻辑）；
- **F4 模型切换**：`switch_model` 工具 + 前端选择器（第 3 节）；
- **F5 Skills**：`load_skill` / `list_skills` / `save_skill` / `delete_skill`（第 5 节）。

### G. 容器沙箱

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| G1 沙箱命令执行 | `sandbox_exec` | L1+强审 | 隔离容器内执行任意命令，每条强制审批（设计见第 10 节） |
| G2 沙箱状态查询 | `sandbox_status` | L0 | Docker 可用性 / 镜像就绪 / 容器状态 / 空闲时长 |

### W. 联网搜索

| 功能 | 工具 | 等级 | 说明 |
|---|---|---|---|
| W1 联网搜索 | `web_search` | L0 | 复用工坊 StepSearch 通道（0.04 元/次），查上游公告 / 定价 / 报错；未配密钥返回降级提示 |

### 明确不做的边界

| 不做的事 | 原因 |
|---|---|
| 宿主机 shell / 任意命令 / 通用文件访问 | 安全红线；唯一例外是隔离容器内的 `sandbox_exec`（每条强制审批） |
| 删除用户 / 改余额 / 封禁 / 分组 | 资金与权限敏感，保留在用户管理页（渠道 / 模型删除已按 L2 开放） |
| TRUNCATE / DROP 任何表 | 只允许带条件分批 DELETE，可审计可中断 |
| 服务端定时巡检 / cron | 巡检仅由管理员对话触发（已决策） |
| Agent 对话写 chat_record | 维护对话不属于业务中转，独立会话表存储 |
| 沙箱文件持久化 / 每会话独立容器 | 共享单容器 + 自停清空，控制服务器资源占用 |

## 13. 验收口径

1. 每个工具在真实站点数据上实测通过，返回 JSON 过脱敏过滤器；
2. L0 结果 ≤8KB（超出自动摘要化），导出类只回下载链接；
3. L2 全程留痕：审批记录 + dry-run 预览 + 实删行数 + admin 日志四者可在库中对齐；
4. 所有端点未登录 401、非管理员 403；
5. 巡检报告在 ≥10 模型 / ≥5 渠道规模下一分钟级生成（批测并发受控）；
6. 模型切换后同会话可继续执行工具任务，上下文不丢不超窗；
7. 计费可对账（logs cost 如实）；超限会话在下次新建时被清理且留日志；
8. skill 教学保存安全链路：必经全文审批（开自动批准也不例外）、非法 name 被拒、redact 后落盘、超限拒绝。

## 14. 决策记录

| # | 决策 | 备注 |
|---|---|---|
| 1 | Agent 大脑调用走管理员个人消费，完全复用中转计费链路，不做豁免 | 后续功能一律以复用已有链路为优先 |
| 2 | 会话保留：每用户最近 50 个 + 近 30 天，新建时惰性清理，不做定时任务 | 不设"自查自清理"工具 |
| 3 | 开放 skills 教学保存（save/delete/list），带 always_confirm 等安全约束 | 第 5 节 |
| 4 | 不做定时巡检，巡检仅管理员对话触发 | F1 |
| 5 | 引入审批式容器沙箱，红线"无 shell"修订为"无未审批的 shell"；全站共享单容器 + 懒启动 + 空闲自停 | 第 10 节 |
| 6 | 开放渠道 / 模型 CRUD（L1 强审 / L2 两段式）；用户与余额仍不可由 Agent 操作 | 第 12 节 A5~A7 / C4~C6 |
| 7 | 新增 web_search 只读工具，复用 StepSearch 通道 | W1 |
| 8 | tool_calls 参数落库 / 回显 / 审批卡全部使用脱敏版，执行用原文 | 第 9 节 |

开放问题：模型"支持工具调用"名单目前用内置名单 + 运行时降级探测，后续可考虑给 `llm_models` 加 `supports_tools` 布尔列（需手动 DDL）。

## 15. 代码结构

| 位置 | 职责 |
|---|---|
| `app/services/agent/maintain_loop.py` | 四阶段主循环 + SSE 事件总线 |
| `app/services/agent/registry.py` | 工具注册表 + 执行器流水线（校验 / 阀门 / 截断 / 审计） |
| `app/services/agent/tools/` | 按域分文件的工具 handler（channel / usage / model / data / ops / session / skill / sandbox） |
| `app/services/agent/{skills,approvals,redact}.py` | skill 加载器、审批管理器、脱敏过滤器 |
| `app/services/{probe_service,export_service,sandbox_service}.py` | 拨测、zip 导出、容器沙箱 |
| `app/router/maintain_agent.py` | chat(SSE) / approve / sessions / exports 端点 |
| `app/models/agent_{session,message}.py` | 两张表（启动自动建表） |
| `app/agent_skills/*.md` | 6 个内置 SOP |
| `backend/sandbox/Dockerfile` | 沙箱镜像（运行时按指纹懒构建） |
| 前端 `views/Dashboard/AgentChat.vue` + `components/agent/*` + `api/agent.ts` + `stores/agent.ts` | 三栏对话页与组件 |
