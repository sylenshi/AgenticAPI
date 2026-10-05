# AgenticAPI 站点维护 Agent · 功能清单

> 文档版本：v1.0（设计稿，未实施） ｜ 日期：2026-10-05 ｜ 配套文档：[维护Agent设计文档.md](维护Agent设计文档.md)
>
> 入口：`/dashboard/agent`（仅管理员），对话框式维护助手。全部功能一次规划、一次实现，不做分期。

## 1. 背景与目标

站点已具备渠道管理、上游用量监控、模型拨测雏形、对话记录表等运维能力，但它们分散在各个管理页，操作者是"人"。本功能把这些能力下沉为**白名单工具**，由一个对话式 Agent 编排执行，让管理员用一句话完成"测一下所有渠道"、"导出并清理三个月前的对话记录"、"出一份站点巡检报告"这类复合运维任务。

三条产品红线（贯穿所有功能）：

1. **密钥不可见**：上游渠道密钥只存在于后端，工具注入使用，模型上下文与前端均不可见；
2. **无任意执行**：Agent 只有封闭的白名单工具，不提供 shell / 任意命令 / 文件系统通用工具；
3. **高危必人审**：所有破坏性操作必须经管理员确认后才执行，全过程审计落库。

计费口径（已决策）：Agent 大脑的模型调用**走管理员个人消费**（完全复用现有中转计费链路，按模型定价扣余额，额度管理员自定）；拨测类工具直发上游、免计费；查询/导出类工具只读无消耗。后续所有功能实现均以**复用已有链路为优先**。

## 2. 功能总览

| 域 | 功能点 | 读写 | 风险等级 | 对应工具（snake_case） |
|---|---|---|---|---|
| A 渠道管理 | A1 渠道信息查询 | 只读 | L0 | `list_channels` |
| A 渠道管理 | A2 渠道连通性测试（单模型抽查 / 全模型遍历） | 只读 | L0 | `test_channel` |
| A 渠道管理 | A3 渠道配置修改（启停/超时/描述/支持模型） | 写 | L1 | `update_channel` |
| A 渠道管理 | A4 渠道-模型绑定一致性检查 | 只读 | L0 | `check_binding_consistency` |
| B 上游用量 | B1 TokenPlan 用量查询（5h/周/月三窗口） | 只读 | L0 | `get_upstream_usage` |
| B 上游用量 | B2 上游凭证到期查询 | 只读 | L0 | `get_token_expiry` |
| C 出站模型 | C1 模型信息查询（定价/分组/渠道绑定） | 只读 | L0 | `get_model_info` |
| C 出站模型 | C2 单模型拨测（连通性 + 时延） | 只读 | L0 | `test_model` |
| C 出站模型 | C3 全量模型巡检（批量拨测 + 汇总报告） | 只读 | L0 | `test_all_models` |
| D 数据治理 | D1 对话记录容量统计 | 只读 | L0 | `get_chat_record_stats` |
| D 数据治理 | D2 对话记录导出（zip 下载链接） | 写文件 | L1 | `export_chat_records` |
| D 数据治理 | D3 对话记录清理（保留策略，两段式） | 写库 | L2 | `cleanup_chat_records` |
| D 数据治理 | D4 调用日志容量统计 / 导出 / 清理 | 读+写 | L0/L1/L2 | `get_log_stats` / `export_logs` / `cleanup_logs` |
| D 数据治理 | D5 聚合表容量统计 / 清理 | 读+写 | L0/L2 | `get_aggregate_stats` / `cleanup_aggregate_stats` |
| E 运营速查 | E1 站点概览（今日调用/消费/用户数/余额池） | 只读 | L0 | `get_site_overview` |
| E 运营速查 | E2 用量趋势（时间范围 + 粒度） | 只读 | L0 | `get_usage_trend` |
| E 运营速查 | E3 兑换码统计 | 只读 | L0 | `get_redeem_stats` |
| E 运营速查 | E4 用户查询（搜索/余额排行/封禁名单） | 只读 | L0 | `query_users` |
| F 系统功能 | F1 一键巡检报告（聚合 A2+C3+B1+D1） | 只读 | L0 | `generate_health_report` |
| F 系统功能 | F2 工具执行审计 | 内建 | — | （harness 内建，非工具） |
| F 系统功能 | F3 会话管理（服务端持久化/历史/继续） | 内建 | — | （harness 内建） |
| F 系统功能 | F4 模型切换（站内任意模型驱动） | 内建 | — | `switch_model`（工具形式暴露） |
| F 系统功能 | F5 Skills 按需加载 + 自定义教学保存 | 内建+写 | L0/L1 | `load_skill` / `list_skills` / `save_skill` / `delete_skill` |
| F 系统功能 | F6 危险命令人工审核 | 内建 | — | （harness 内建） |

风险等级定义（与设计文档第 8 节审批流对应）：

- **L0 只读**：无副作用，直接执行；
- **L1 低危写**：可恢复或仅产生文件（导出、渠道启停、改超时/描述），默认弹轻确认，管理员可在会话设置里开启"L1 自动批准"；
- **L2 高危写**：不可逆删除类（清理数据表），强制强确认弹窗 + 影响预览 + 工具内部两段式（dry-run 预览 → 确认后真删），且每会话执行次数上限 5 次。

## 3. 功能域明细

### A. 渠道管理域

**A1 渠道信息查询 `list_channels`**
返回全量渠道：`channel_name / base_url / status / timeout / used_ratio / description / support_models 列表 / 被哪些出站模型绑定`。密钥字段**永不返回**，仅返回 `apiKeyHint`（尾 4 位，如 `sk-****ab12`）。可按名称过滤。
背景：现有 `GET /channels` 给管理员返回的是明文 apiKey（`channel_service.py` 无脱敏），Agent 工具不复用该响应形状，独立实现脱敏层。

**A2 渠道连通性测试 `test_channel`**
参数：`channel_name`（必填）、`scope`（`one` 任选一个模型 / `all` 遍历该渠道全部支持模型）、`model_name`（scope=one 时可选指定）。
行为：后端注入渠道密钥，向 `base_url + /chat/completions` 直发一条极小探测请求（`max_tokens` 8~16、非流式、超时 10s），逐模型返回 `{模型名, ok, 时延 ms, HTTP 状态, 错误摘要}`；scope=all 时内部并发（信号量限 5）。
明确：测试**绕过中转计费链路**（不扣费、不写 chat_record），仅写一条 admin 审计日志。

**A3 渠道配置修改 `update_channel`**
可修改字段：`status`（启停）、`timeout`、`description`、`support_models`。定位键为 `channel_name`（与现有 PUT /channels 一致，名称本身不可改）。
L1 审批卡片展示变更 diff（字段级前后对比）。**不开放修改渠道密钥**——密钥更新走渠道管理页手工操作（避免密钥经过模型上下文）。

**A4 渠道-模型绑定一致性检查 `check_binding_consistency`**
背景：`llm_channels.support_models` 与 `llm_models.channels` 是双向 JSON 软引用、无外键约束（见数据库设计文档 5.6 节），人工维护极易不同步（渠道删了模型、模型换了渠道、单向引用、引用不存在的对象）。
行为：全表交叉比对两个方向，输出不一致清单（孤儿引用、单向绑定、指向已停用渠道/模型的绑定）与修复建议。只报告不自动修复（修复动作由管理员确认后走 A3 / 模型管理页）。

### B. 上游用量域（只读，对应现有 `/dashboard/operations` 页）

**B1 TokenPlan 用量查询 `get_upstream_usage`**
参数：`scope`（`vol / stepfun / zai / zai2 / cc / antigravity / all`）。
直接在 Python 内调用 `operations_service.get_operations()`（无 db 依赖的纯函数，不走 HTTP 自调用），返回各上游 5 小时 / 周 / 月三窗口的 `{已用, 总额度, 重置时间}` 与请求状态。`all` 时 antigravity 读缓存秒回，单渠道刷新走实时（与运维页同策略）。

**B2 上游凭证到期查询 `get_token_expiry`**
返回四类凭证（volcengine / stepfun / zai / zai2）JWT 解码出的过期时间，临期（≤7 天）由 Agent 主动标注提醒。

### C. 出站模型域

**C1 模型信息查询 `get_model_info`**
参数：`model_name`（可空 = 全部）。返回模型配置：定价（输入/缓存/输出/按次）、分组、渠道绑定列表（含 upstream_name 映射）、状态、is_log、context_length、max_tokens。管理员问"glm-4.7 定价多少、走的哪个渠道"即答。

**C2 单模型拨测 `test_model`**
按该模型绑定的渠道顺序逐个直发探测请求（渠道轮询逻辑与中转一致，但免计费、不落 chat_record），返回每个渠道的 `{ok, 时延, 错误}` 与最终结论（全部渠道失败 = 模型不可用）。
背景：现有 `model_service.test_model` 走真实中转链路（要扣费、要求调用者持 sk- 密钥、写业务日志），不适合 Agent 批量调用，Agent 用独立免计费实现。

**C3 全量模型巡检 `test_all_models`**
遍历所有启用的出站模型执行 C2，内部并发（限 5）+ 总超时 180s + 进度通过 SSE 事件实时上报。产出汇总：`总模型数 / 可用数 / 可用率 / 平均时延 / 失败清单（模型 × 渠道 × 错误）`。报告全文不超过截断阈值，明细大表自动转存导出文件返回下载链接。

### D. 数据治理域（防 MySQL 膨胀）

**D1 对话记录容量统计 `get_chat_record_stats`**
`chat_record` 总行数、预估存储占用（`information_schema.TABLES` 或 AVG_ROW_LENGTH × 行数）、按月（或按日，近 30 天）行数分布、最早/最新记录时间。Agent 据此给出清理建议。

**D2 对话记录导出 `export_chat_records`**
参数：时间范围（start/end）。行为：分批流式读取（避免一次性载入内存），写为 JSONL（gzip）打包 zip → 存 `backend/data/exports/{随机token}.zip` → 工具只返回 `{下载链接, 文件大小, 行数, 过期时间}`，**数据本体绝不进入对话上下文**。下载走独立 GET 端点（token 一次性校验 + 默认 24h 过期 + 过期文件启动时清理）。

**D3 对话记录清理 `cleanup_chat_records`（L2，两段式）**
参数：`keep_days`（保留最近 N 天）或 `keep_count`（保留最近 N 条），`backup_first`（默认 true：清理前自动执行 D2 全量导出）。
两段式：第一次调用 `dry_run=true` 返回"预计删除 N 行、时间切点、预计耗时"；管理员在审批卡片上看到该预览并确认后，第二次真实执行。执行为**分批 DELETE（每批 5000 行 + 批间 200ms 休止）**，防长事务锁表与 binlog 洪峰；完成后返回实删行数 + 优化建议（可选 `OPTIMIZE TABLE` 提示，不自动执行）。

**D4 调用日志治理 `get_log_stats` / `export_logs` / `cleanup_logs`**
与 D1~D3 完全同构，作用于 `logs` 表（同样只增不减、更易膨胀）。导出支持按 type 过滤；清理默认保留近 90 天。

**D5 聚合表治理 `get_aggregate_stats` / `cleanup_aggregate_stats`**
`usage_stats`（小时桶）容量统计与按月清理（保留近 N 月）。`usage_summary` 为单行表，不涉及清理。清理为 L2，同样两段式。

### E. 运营速查域（全部只读）

**E1 站点概览 `get_site_overview`**：今日/昨日调用量与消费、注册用户数与活跃数、全站余额池、访客占比。数据源：`usage_summary` + `logs` 聚合 + `user` 表 COUNT。
**E2 用量趋势 `get_usage_trend`**：参数时间范围 + 粒度（hour/day/week/month，复用 `usage_stats` 预聚合），返回每模型调用量 / token / 费用序列（回传对话的是摘要，如 Top5 模型）。
**E3 兑换码统计 `get_redeem_stats`**：发行/未使用/已使用/已核销金额四卡数据（复用现有 `/admin/redeem-codes/stats` service 层）。
**E4 用户查询 `query_users`**：按用户名搜索、余额排行 TopN、封禁用户列表。**只读**——改余额/封禁/删除用户仍走用户管理页（对话误操作成本过高，明确不开放）。

### F. 系统性功能（harness 内建能力）

**F1 一键巡检报告 `generate_health_report`**：一个聚合工具 + `site-inspection` skill 编排，串联 A2（渠道连通性）+ C3（模型巡检）+ B1/B2（用量与凭证）+ D1/D4（表容量），产出固定结构报告（总览评分 → 渠道健康 → 模型可用性 → 额度水位 → 存储水位 → 待办建议），markdown 渲染到对话。**仅由管理员对话主动触发**（说一句"出一份巡检报告"即按 skill SOP 执行），不做服务端定时巡检（已决策）。
**F2 工具执行审计**：每次工具执行（含被拒绝的）写 `logs`（type=admin, action=agent_tool, detail=工具名+参数摘要+结果摘要+操作者）；L1/L2 另在会话消息表记录审批轨迹。可回答"Agent 昨天都干了什么"。
**F3 会话管理**：服务端新表持久化（会话 + 消息含工具轨迹），支持历史会话列表、继续对话、删除会话、自动起标题（复用现有 `agent_service.agent_chat` 起标题逻辑）。保留策略（已决策）：每用户最多保留最近 **50 个**会话、仅保留近 **1 个月**，新建会话时后台惰性清理过期与超限会话（联动删消息，写 admin 日志）。
**F4 模型切换**：会话头部模型选择器 + `switch_model` 工具 + 自然语言切换（"换 glm-4.7 继续"），Agent 大脑可为站内任意模型，详见设计文档第 5 节。
**F5 Skills（内置 SOP 按需加载 + 自定义教学保存，已决策开放）**：内置运维 SOP（巡检 / 数据治理 / 渠道排障 / 水位研判 / 新模型上线检查 / 故障复盘），system prompt 只注入目录，`load_skill` 按需读取全文；管理员可在对话中把现场总结的经验固化为自定义 skill 加入技能池——`save_skill`（写 `data/agent_skills/`，同名覆盖更新）、`delete_skill`（仅可删自定义）、`list_skills`（池子全览）。写操作带 `always_confirm` 强制全文审批（不受"L1 自动批准"豁免）、name slug 校验防路径穿越、落盘前过脱敏过滤器、单文件 ≤32KB、内置 skill 物理隔离不可覆盖。详见设计文档第 7.3 节。
**F6 人工审核**：L1/L2 分级审批流（SSE 确认事件 + 审批端点 + 超时自动拒绝），详见设计文档第 8 节。

## 4. 明确不做的边界

| 不做的事 | 原因 |
|---|---|
| shell / 任意命令执行 / 通用文件系统工具 | 安全红线：工具封闭白名单，杜绝 prompt 注入演变成 RCE |
| 修改渠道密钥（apiKey） | 密钥不得经过模型上下文与前端 |
| 删除用户 / 模型 / 渠道等结构性删除 | 误删成本高，保留在管理页人工操作 |
| 修改用户余额 / 封禁 / 分组 | 资金与权限敏感，保留在用户管理页 |
| 修改模型定价 / 新建模型 | 低频且需人工斟酌，Agent 只读模型配置（A 域仅开放渠道属性修改） |
| 直接 `TRUNCATE` / `DROP` 任何表 | 只允许带条件分批 DELETE，可审计可中断 |
| 服务端定时巡检 / cron 定时任务 | 巡检仅由管理员对话触发（F1 skill SOP 编排），不做主动定时（已决策） |
| Agent 对话写 chat_record | 维护对话不属于业务中转，独立会话表存储 |

## 5. 验收口径（每项功能的完成定义）

1. 每个工具在真实站点数据上实测通过，返回 JSON 通过脱敏过滤器（递归抹除 `api_key/token/password/authorization` 字段）；
2. L0 工具结果序列化 ≤ 8KB（超出自动摘要化），导出类只回下载链接；
3. L2 工具全程留痕：审批记录（pending→approved/rejected/timeout）+ dry-run 预览 + 实删行数 + admin 日志，四者可在库中对齐；
4. 所有端点未登录 401、非管理员 403（沿用现有鉴权语义）；
5. 巡检报告在 ≥10 模型 / ≥5 渠道规模下一次生成成功且总耗时 ≤ 5 分钟（批测并发受控）；
6. 模型切换后同一会话可继续执行工具任务，上下文不丢失、不超窗（小窗口模型自动触发脱水，见设计文档第 9 节）；
7. 计费与清理符合既定决策：大脑调用如实扣管理员余额（logs cost 可对账）；超过 50 个或 30 天的会话在下次新建会话时被清理、消息联动删除且留有 admin 日志；
8. skill 教学保存链路安全：保存/删除必经全文审批卡片（开启 L1 自动批准也不例外）；非法 name（路径穿越、大写、超长）被拒；保存后下一轮目录可见、可加载；redact 过滤后落盘、大小超限拒绝。
