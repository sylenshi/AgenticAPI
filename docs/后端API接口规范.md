# 后端 API 接口规范文档

> 本文档描述后端所有 HTTP 接口的统一响应格式、异常处理机制、状态码约定以及前端对接方式。
> 对应实现代码：
> - 统一成功响应：`backend/app/utils/response.py`
> - 全局异常处理器：`backend/app/utils/exception.py`
> - 前端拦截器：`frontend/src/api/request.ts`

---

## 1. 统一响应格式

所有接口（无论成功还是失败）都返回如下 JSON 结构：

```json
{
  "code": 200,
  "message": "获取渠道列表成功",
  "data": {}
}
```

> **例外**：`/v1/chat/completions`（对外中转）、`/v1/models`（可用模型列表）与 `/studio/chat`（模型工坊对话）走 OpenAI 报文风格——成功透传上游 JSON / SSE
> 流或返回 OpenAI 结构（`/v1/models` 返回 `{"object": "list", "data": [...]}`），失败返回 `{"error": {message, type, code}}`，不套用本节格式。
> 该例外覆盖**这些路径上的全部失败**（含 401 未认证、路由未匹配 404、方法不允许 405），其他路径的 404/405 也统一走 `{code, message, data}` 格式。

| 字段        | 类型       | 说明                                                 |
|-----------|----------|----------------------------------------------------|
| `code`    | `int`    | 业务状态码。**成功时固定为 200**，失败时为对应的错误码（与 HTTP 状态码保持一致）    |
| `message` | `string` | 提示信息。成功时为成功描述；失败时为**可直接展示给用户的中文错误描述**              |
| `data`    | `any`    | 业务数据。成功时为接口返回的数据（查询结果 / 新增 id 等），失败时为 `null` 或调试信息 |

### 1.1 成功响应

- HTTP 状态码恒为 **200**，响应体 `code` 恒为 **200**。
- 业务数据一律放在 `data` 字段中，例如新增接口返回 `{"channelId": 3}`。
- 由 `success_response(message, data)` 统一构造（`app/utils/response.py`）。

```json
{
  "code": 200,
  "message": "添加渠道成功",
  "data": {
    "channelId": 3
  }
}
```

### 1.2 失败响应

- HTTP 状态码与响应体 `code` 保持一致（400 / 404 / 422 / 500 等）。
- `message` 为用户可读的中文错误描述，前端可直接用 `ElMessage` 展示。
- `data` 跟随后端 `.env` 的 `DEBUG` 开关：`DEBUG=true` 时可能携带调试信息（错误类型、堆栈、请求路径），生产模式（`DEBUG=false`）下为 `null`。

```json
{
  "code": 404,
  "message": "渠道 'xxx' 不存在",
  "data": null
}
```

---

## 2. 全局异常处理器

所有异常由 `app/utils/exception.py` 中的 `register_exception_handlers(app)` 在应用启动时统一注册（见 `app/main.py`），*
*业务代码只需抛异常，不需要在路由里手写 try/except 返回错误响应**。

| 异常类型                     | HTTP 状态码        | 典型场景                             | message 示例                              |
|--------------------------|-----------------|----------------------------------|-----------------------------------------|
| `RequestValidationError` | 422             | 请求参数不符合 Schema（缺字段、类型错误、非法 JSON） | `请求参数校验失败（channelName: Field required）` |
| `HTTPException`          | 400 / 404 / 自定义 | 业务逻辑主动抛出（重复创建、资源不存在等）            | `渠道名称 'xxx' 已存在`                        |
| `IntegrityError`         | 400             | 数据库完整性约束冲突（唯一键、外键等）              | `用户名已存在` / `数据约束冲突，请检查输入`               |
| `SQLAlchemyError`        | 500             | 其他数据库错误                          | `数据库操作失败，请稍后重试`                         |
| `Exception`              | 500             | 所有未捕获异常（兜底）                      | `服务器内部错误`                               |

### 2.1 业务错误的使用方式

业务层（service）通过抛出 `HTTPException` 表达业务错误，全局处理器会把它格式化为统一响应体：

```python
from fastapi import HTTPException

if await channel_crud.get_id_by_name(db, channel_name):
    raise HTTPException(status_code=400, detail=f"渠道名称 '{channel_name}' 已存在")
```

### 2.2 常用业务状态码约定

| 状态码 | 含义      | 使用场景                   |
|-----|---------|------------------------|
| 200 | 成功      | 所有成功请求                 |
| 400 | 业务规则错误  | 名称重复、引用的渠道不存在、未提供更新字段等 |
| 404 | 资源不存在   | 按名称更新/删除时目标不存在         |
| 422 | 参数校验失败  | 请求体不符合 Pydantic Schema |
| 500 | 服务器内部错误 | 数据库异常、未预期的运行时异常        |

---

## 3. 接口清单

**鉴权约定**：标注「需登录」或「需管理员」的接口必须在请求头携带 `Authorization: Bearer <token>`（令牌由登录/注册/访客接口返回，正式账号
30 天、访客 24 小时）。访客与普通用户权限相同（均可管理自己的密钥、修改资料）；仅「需管理员」的接口区分身份。状态码语义：

- **401 未认证**：没带令牌 / 格式错误 / 令牌无效或已过期 → 前端清空登录态并唤起登录弹窗；
- **403 无权限**：已登录但不是管理员，调用「需管理员」的接口 → 前端按普通业务错误提示，不动登录态。

### 3.1 渠道管理（`/channels`）

对应数据表 `llm_channels`，路由文件 `app/router/channels.py`，服务层 `app/services/channel_service.py`。
渠道数据包含 `apiKey` 等敏感凭证，除渠道名列表外全部接口需管理员。

| 方法     | 路径                         | 鉴权   | 说明                            |
|--------|----------------------------|------|-------------------------------|
| GET    | `/channels/names`          | 公开   | 获取全量渠道名列表（仅名称，供公开页面的下拉框使用）    |
| GET    | `/channels`                | 需管理员 | 获取全量渠道列表（含密钥）                 |
| POST   | `/channels`                | 需管理员 | 添加单个渠道                        |
| PUT    | `/channels/{channel_name}` | 需管理员 | 更新渠道（channel_name 为定位键，不可被更新） |
| DELETE | `/channels/{channel_name}` | 需管理员 | 删除渠道                          |

#### GET /channels/names

- 响应 `data`：渠道名字符串数组，如 `["DeepSeek官方渠道", "智谱AI官方渠道"]`。

#### GET /channels

- 请求示例：`GET /channels`
- 响应 `data`：渠道数组。`supportModels` 为字符串数组（入库时是 JSON 字符串，返回前已反序列化）。

```json
{
  "code": 200,
  "message": "获取渠道列表成功",
  "data": [
    {
      "channelName": "DeepSeek官方渠道",
      "baseUrl": "https://api.deepseek.com/v1/chat/completions",
      "apiKey": "sk-xxx",
      "supportModels": [
        "deepseek-v4-flash",
        "deepseek-chat"
      ],
      "status": true,
      "timeout": 30,
      "usedRatio": 0.0,
      "description": "深度求索官方直连渠道"
    }
  ]
}
```

#### POST /channels

- 请求体：`ChannelSchema`（驼峰别名），`channelName` 必填，其余字段可选（有默认值）。

```json
{
  "channelName": "新渠道",
  "baseUrl": "https://example.com/v1",
  "apiKey": "sk-xxx",
  "supportModels": [
    "model-a"
  ],
  "status": true,
  "timeout": 30,
  "usedRatio": 0,
  "description": null
}
```

- 成功响应：`data` 返回自增主键 `{"channelId": 3}`。
- 错误响应：渠道名重复 → 400 `渠道名称 '新渠道' 已存在`；缺 `channelName` → 422。

#### PUT /channels/{channel_name}

- 路径参数 `channel_name` 为定位键；请求体中只更新**出现的字段**（部分更新语义），且 `channelName` 字段本身不会被更新。
- 常见用法：表格内状态开关只传 `{"channelName": "...", "status": false}`。
- 错误响应：渠道不存在 → 404；未提供任何可更新字段 → 400。

#### DELETE /channels/{channel_name}

- 路径参数 `channel_name` 为定位键（URL 编码后传递，前端用 `encodeURIComponent`）。
- 错误响应：渠道不存在 → 404。

### 3.2 模型管理（`/models`）

对应数据表 `llm_models`，路由文件 `app/router/models.py`，服务层 `app/services/model_service.py`。
模型广场为公开页面，查询不需登录；增删改属于管理操作，需管理员。

| 方法     | 路径                          | 鉴权   | 说明                    |
|--------|-----------------------------|------|-----------------------|
| GET    | `/models`                   | 公开   | 获取全量模型列表              |
| POST   | `/models`                   | 需管理员 | 添加单个模型                |
| PUT    | `/models/{model_name}`      | 需管理员 | 更新模型（name 为定位键，不可被更新） |
| DELETE | `/models/{model_name}`      | 需管理员 | 删除模型                  |
| POST   | `/models/test/{model_name}` | 需登录  | 模型拨测（每用户 60s 冷却）     |

#### GET /models

- 响应 `data`：模型数组。`channels` 为字符串数组（引用渠道名，按顺序轮询）。
- **价格字段为字符串**：`perRequestPrice` / `inputPrice` / `cachePrice` / `outputPrice` 是 DECIMAL(12,4) 序列化后的字符串（如 `"2.5000"`），保证精度不丢；前端展示时自行 `Number()` 转换。

```json
{
  "code": 200,
  "message": "获取模型列表成功",
  "data": [
    {
      "name": "deepseek-v4-flash",
      "upstreamName": "deepseek-v4-flash-0731",
      "label": "低价免费模型",
      "description": "...",
      "modelGroup": "free",
      "isRequestMode": false,
      "perRequestPrice": 0,
      "inputPrice": 2.5,
      "cachePrice": 0.2,
      "outputPrice": 3.0,
      "isPin": false,
      "isLog": false,
      "status": true,
      "channels": [
        "DeepSeek官方渠道"
      ],
      "contextLength": 128000,
      "maxTokens": 8192,
      "supportVision": false,
      "icon": ""
    }
  ]
}
```

#### POST /models

- 请求体：`ModelSchema`（驼峰别名），`name` 必填，其余可选。`upstreamName` 可选，为空时回退到 `name`
  （对外名与上游名相同，请求/响应原样透传，不产生改写开销）。
- 入库默认值（未传时）：`label` 取 `name`、`modelGroup` 取 `"free"`、四个价格取 `0`、各布尔标志取 `false`、`status` 取 `true`、
  `upstreamName` 取 `null`。
- 成功响应：`data` 返回 `{"modelId": 40}`。
- 错误响应：模型名重复 → 400；`channels` 中包含不存在的渠道名 → 400 `以下渠道不存在: ['xxx']`。

#### PUT /models/{model_name}

- 路径参数 `model_name` 为定位键；请求体为部分更新语义，`name` 本身不可更新，`upstreamName` 可更新（传空字符串或 `null`
  可清除映射，回退到 `name`）。
- 错误响应：模型不存在 → 404；渠道校验失败 → 400。

#### DELETE /models/{model_name}

- 错误响应：模型不存在 → 404。

#### POST /models/test/{model_name}

- 模型拨测：走本站对外中转接口真实调用上游（正常计费、记录日志）。分组权限前置校验（free 用户仅 free 模型）。
- **频控**：每用户 60 秒冷却，冷却期内请求返回 429 `拨测过于频繁，请 60 秒后再试`。
- 成功响应：`message": "模型响应成功"`，`data: { ok, model, latencyMs, reply }`
- 错误响应：模型不存在 → 404；分组无权限 → 403；上游失败 → 502（detail 带真实原因）。

### 3.3 上游运维（`/operations`）

涉及上游平台的用量数据与凭证读写，全部接口需管理员。

| 方法   | 路径                                    | 鉴权   | 说明                                                                     |
|------|---------------------------------------|------|------------------------------------------------------------------------|
| GET  | `/operations/get?refresh_channel=all` | 需管理员 | 获取上游用量数据，`refresh_channel` 可选 `vol` / `stepfun` / `zai2` / `antigravity` / `all`       |
| POST | `/operations/upload`                  | 需管理员 | 更新上游运维凭证（Body 传 `brmToken` / `instanceId` / `stepToken` / `stepWebid` / `zaiApiKey`） |

同样返回统一格式，`data` 为各渠道用量与 token 过期时间明细。

### 3.4 用户（`/user`）

路由文件 `app/router/user.py`，数据访问层 `app/crud/user.py`。密码使用 bcrypt 加密存储；
令牌为不透明随机串（uuid4），存于 `user_token` 表，有效期正式账号 30 天 / 访客 24 小时，重新登录会刷新。

| 方法     | 路径               | 鉴权  | 说明                                                                 |
|--------|------------------|-----|--------------------------------------------------------------------|
| POST   | `/user/register` | 公开  | 用户注册（用户名 2-50 字符，密码 6-100 字符），成功即登录，返回 `data: { token, userInfo }` |
| POST   | `/user/login`    | 公开  | 用户登录，返回 `data: { token, userInfo }`                                |
| POST   | `/user/guest`    | 公开  | 访客模式：创建临时访客账号（随机用户名密码，`isGuest=true`）并签发 24 小时令牌；顺带惰性清理已过期的访客账号    |
| GET    | `/user/info`     | 需登录 | 获取当前登录用户信息（含余额、分组、注册/登录时间等）                                        |
| PUT    | `/user/profile`  | 需登录 | 修改自己的资料（昵称/手机号，空字符串视为清空），返回更新后的用户信息                                |
| DELETE | `/user/logout`   | 需登录 | 登出，删除服务端令牌（立即失效）                                                   |

`userInfo` 结构（不含密码等敏感字段；`balance` / `usedQuota` 为 DECIMAL 字符串）：

```json
{
  "id": 11,
  "username": "zcode_tester",
  "nickname": null,
  "phone": null,
  "isGuest": false,
  "isAdmin": false,
  "balance": "1.000000",
  "usedQuota": "0.000000",
  "userGroup": "vip",
  "createTime": "2026-11-06T23:57:06",
  "lastLoginTime": "2026-11-06T23:57:14"
}
```

- **注册策略（站点可配）**：正式注册的初始余额（`registerInitialBalance`）与默认分组（`registerUserGroup`，free / vip，默认 vip）
  由管理员在控制台-设置页调整（`/admin/settings`），仅对之后新创建的账号生效；访客固定 free 分组、初始余额独立配置（`guestInitialBalance`，建议 0）。
- **余额与免费模型**：`/v1` 调用前校验余额 ≤ 0 则拒绝（402）；**全零定价的免费模型豁免余额校验**（不产生扣费，0 余额账号也可调用）；
  付费模型在余额不足时返回 402 `账户余额不足，请联系管理员充值`。
- 注册错误：用户名已存在 → 400；字段长度不符 → 422。
- 登录错误：用户名或密码错误 → 401。
- `isGuest`：访客账号标记，仅作数据区分——访客与普通用户权限相同（可管理密钥、修改资料、调用中转接口），**访客不支持兑换码充值**；只有「需管理员」的接口会返回
  403 `需要管理员权限`。过期/登出的访客账号在下次创建访客时被清理（连带清理其维护 Agent 会话）。
- 账号被封禁（管理员置 `status=false`）后，存量令牌立即失效：所有需登录接口返回 403 `账号已被封禁，请联系管理员`。

---

### 3.5 监控面板（`/monitor`）

路由文件 `app/router/monitor.py`。数据来源三张新表：`chat_record`（对话记录）、`usage_stats`（用户×模型×小时 用量桶）、
`usage_summary`（全站累计单行）。
统计接口全部走预聚合表，不做原始日志全量求和。

| 方法  | 路径                   | 鉴权   | 说明                                                                                                                                      |
|-----|----------------------|------|-----------------------------------------------------------------------------------------------------------------------------------------|
| GET | `/monitor/summary`   | 需登录  | 全站累计用量，返回 `data: { calls, promptTokens, completionTokens, cacheTokens }`                                                                |
| GET | `/monitor/chats`     | 需登录  | 对话记录分页；查询参数 `page` / `pageSize` / `model`（模型名精确）/ `username`（用户名模糊，仅管理员生效）；管理员可查全部用户，普通用户强制只看自己                                         |
| GET | `/monitor/logs`      | 需登录  | 系统日志分页；查询参数 `page` / `pageSize` / `type`（api/login/admin/user）/ `keyword`（用户名/动作/详情模糊）/ `model` / `start` / `end`（闭开区间）；管理员看全部，普通用户只看自己 |
| GET | `/monitor/stats`     | 需登录  | 当前用户用量：查询参数 `start` / `end` / `granularity`（hour/day/week/month），返回 `data: { totals, buckets }`，`buckets` 每元素为某模型在某时间桶的累计               |

> 对话记录长度阈值的读写已迁移至 `/admin/settings`（`chatRecordMaxTokens`，值域 100 ~ 1000000），本模块不再提供 threshold 端点。

`chats` 返回的 `list` 元素结构（`inputContent` 已还原为 messages 数组）：

```json
{
  "id": 1,
  "userId": 11,
  "username": "zcode_tester",
  "modelName": "glm-4.7",
  "channelName": "volcengine",
  "inputContent": [
    {
      "role": "user",
      "content": "你好"
    }
  ],
  "reasoningContent": "用户在打招呼，应当……",
  "outputContent": "你好！有什么可以帮你？",
  "promptTokens": 12,
  "completionTokens": 34,
  "cacheTokens": 0,
  "cost": 0.00005,
  "durationMs": 812,
  "createTime": "2026-08-16T20:01:02"
}
```

记录规则（由中转链路 `_finalize_call` 保证）：

- token 数量**无条件**记入 `logs` / `usage_stats` / `usage_summary`，与模型 `is_log` 无关；
- 对话内容（输入/推理/输出全文）仅在模型 `is_log` 开启 **且** 输入+输出 token ≤ 阈值（`system_config` 表
  `chat_record_max_tokens`，默认 5000）时才写入 `chat_record`，避免落库超长文本。

### 3.6 模型工坊（`/studio`）

路由文件 `app/router/studio.py`。工坊为对话式 Playground：**不计费**（跳过余额校验与扣款，`logs` 中 `cost` 记 0、`detail`
标注"工坊调用"），分组权限与中转一致（free 用户仅 free 模型），不写 `chat_record`（监控页对话数据仅统计中转调用），token
照常进用量统计。会话与消息由前端 localStorage 存储，后端无会话接口。

#### POST /studio/chat（需登录，OpenAI 风格报文）

请求体（snake_case，对齐 `/v1` 中转约定）：

```json
{
  "model": "step-3.7-flash",
  "messages": [
    {
      "role": "user",
      "content": "你好"
    },
    {
      "role": "user",
      "content": [
        {
          "type": "image_url",
          "image_url": {
            "url": "data:image/png;base64,..."
          }
        },
        {
          "type": "text",
          "text": "这张图里是什么"
        }
      ]
    }
  ],
  "stream": true,
  "temperature": 1.0,
  "top_p": 1.0,
  "max_tokens": 4096,
  "system_prompt": "你是一个严谨的助手",
  "enable_search": false
}
```

- 仅支持流式（`stream` 强制为 true），成功返回 `text/event-stream`（透传上游 SSE chunk，末尾 `data: [DONE]`）；
- `system_prompt` 由后端拼到消息头；空消息会被过滤；`enable_search` 时注入 `web_search` function tool 透传上游（不支持
  tools 的渠道返回 400/422 时自动剥掉 tools 降级重试一次）；
- 失败返回 OpenAI 格式 `{"error": {message, type, code}}`（401 未登录 / 403 分组无权限 / 404 模型不存在 / 502 渠道全失败）。

#### POST /studio/asr（需登录，统一响应格式）

语音转文本，代理阶跃星辰 `stepaudio-2.5-asr`。请求体 `{ "audio": "<base64>", "format": "ogg" }`（`format` 可选 mp3/ogg 等，默认
mp3），成功返回：

```json
{
  "code": 200,
  "message": "语音识别成功",
  "data": {
    "text": "识别出的文本"
  }
}
```

未在后端 `.env` 配置 `STEPFUN_API_KEY` 时返回 503「语音服务未配置」；上游异常返回 502。

#### POST /studio/title（需登录，统一响应格式）

由首条用户消息概括会话标题（代理 StepFun，未配置 `AGENT_TITLE_MODEL` 时回退截断文案）。请求体 `{ "content": "..." }`，
返回 `data: { title, source }`（`source` 为 `model` / `fallback`）。

### 3.7 API 密钥（`/keys`）

路由文件 `app/router/keys.py`。用户在控制台-秘钥页管理自己的 `sk-` 密钥，**每个用户最多 5 个**。

| 方法     | 路径           | 鉴权  | 说明                     |
|--------|--------------|-----|------------------------|
| GET    | `/keys`      | 需登录 | 当前用户全部密钥（含 `key` 明文）    |
| POST   | `/keys`      | 需登录 | 创建密钥，请求体 `{ "name": "..." }`，超 5 个返回 400 |
| PUT    | `/keys/{id}` | 需登录 | 改名 / 启停（部分更新语义）         |
| DELETE | `/keys/{id}` | 需登录 | 删除自己的密钥                 |

`data` 元素结构：`{ id, name, key, status, createTime, lastUsedTime }`（驼峰）。增删改均写 user 日志。

### 3.8 兑换码（`/redeem`）

路由文件 `app/router/redeem.py`（用户端）。**访客禁止兑换**（403）。

| 方法  | 路径                | 鉴权  | 说明                                    |
|-----|-------------------|-----|---------------------------------------|
| POST | `/redeem`        | 需登录 | 核销兑换码充值，请求体 `{ "code": "AGC-..." }`，成功返回 `data: { balance }`（字符串） |
| GET  | `/redeem/records` | 需登录 | 我的兑换记录分页（`page` / `pageSize`）          |

核销错误：码不存在 / 已使用 / 已停用 → 400。核销为单事务：`SELECT ... FOR UPDATE` 锁码行防并发重复核销，日志与余额同事务提交。

### 3.9 管理员接口（`/admin/*`）

路由文件 `app/router/admin.py` 与 `app/router/redeem.py`（admin_router），全部需管理员。

| 方法     | 路径                                | 说明                                                     |
|--------|-----------------------------------|--------------------------------------------------------|
| GET    | `/admin/users`                    | 用户列表分页（`keyword` / `page` / `pageSize`），含余额、分组、状态等 |
| PUT    | `/admin/users/{id}`               | 修改用户（余额 / 分组 / 管理员 / 状态 / 昵称，部分更新；管理员必须 vip；不能改自己的管理员身份） |
| DELETE | `/admin/users`                    | 批量删除用户，请求体 `{ "ids": [...] }`（连带删除令牌、密钥与 Agent 会话；不能删自己） |
| GET    | `/admin/settings`                 | 站点设置当前值（见下）                                             |
| PUT    | `/admin/settings`                 | 更新站点设置（部分更新，先校验后写入，写 admin 日志）                          |
| GET    | `/admin/redeem-codes`             | 兑换码列表分页（`status` / `keyword` / `batchNo` / `page` / `pageSize`） |
| GET    | `/admin/redeem-codes/stats`       | 兑换码监控统计（四卡数据）                                            |
| POST   | `/admin/redeem-codes/generate`    | 批量生成（`count` ≤ 100、`amount`、`batchNo`、`remark`），返回全部码值  |
| PUT    | `/admin/redeem-codes/{id}/disable`| 停用单张未使用的码                                               |
| PUT    | `/admin/redeem-codes/batch-disable`| 批量停用（仅未使用生效），请求体 `{ "ids": [...] }`                    |
| DELETE | `/admin/redeem-codes`             | 物理销毁（未使用/已停用可销毁，已核销禁止），请求体 `{ "ids": [...] }`           |

`/admin/settings` 的 `data` 结构（驼峰；`PUT` 请求体传其中任意子集）：

```json
{
  "chatRecordMaxTokens": 5000,
  "agentDefaultModel": "",
  "agentEffectiveModel": "glm-5.3",
  "registerInitialBalance": 0,
  "guestInitialBalance": 0,
  "registerUserGroup": "vip"
}
```

- `agentDefaultModel` 传空串表示清除指定、恢复默认解析链（`.env` → 站内首个启用模型）；`agentEffectiveModel` 为只读的当前实际生效值。
- `chatRecordMaxTokens` 值域 100 ~ 1000000；`registerUserGroup` 仅接受 `free` / `vip`。

### 3.10 站点信息与上游运维

| 方法   | 路径                     | 鉴权   | 说明                                                         |
|------|------------------------|------|------------------------------------------------------------|
| GET  | `/site/info`           | 公开   | 站点公开信息（含对外中转接口地址 `publicBaseUrl` 等，前端据此拼接 Base URL）          |
| GET  | `/operations/get`      | 需管理员 | 上游用量数据，`refresh_channel` 可选 `vol` / `stepfun` / `zai2` / `antigravity` / `all` |
| POST | `/operations/upload`   | 需管理员 | 更新上游运维凭证（Body 传 `brmToken` / `instanceId` / `stepToken` / `stepWebid` / `zaiApiKey`） |

`/operations/get` 的 `data` 外层段名为蛇形（`status` / `vol_usage` / `stepfun_usage` / `zai2_usage` / `antigravity_usage`），
各段叶子键为驼峰；单渠道失败只影响自己的段（`status` 非 `"200"`），不影响其他渠道。

### 3.11 站内维护 Agent

`/maintain-agent/*` 系列接口（会话管理 / 对话 / 审批 / 导出，需管理员）属于站点维护 Agent 模块，
规范见 [`docs/维护Agent设计文档.md`](docs/维护Agent设计文档.md)，本文件不再展开。

---

## 4. 前端对接约定

前端在 `frontend/src/api/request.ts` 中通过 axios 拦截器统一处理，**业务代码无需感知响应体外壳与鉴权细节**：

1. 响应体 `code === 200` 时，拦截器把 `response.data` 替换为业务数据 `data`，业务代码直接使用 `res.data`；
2. `code !== 200` 或 HTTP 层报错（4xx / 5xx）时，转为 `Promise.reject(new Error(message))`，`message` 即后端的中文错误描述；
3. 视图层使用 `getErrorMessage(err, '兜底文案')` 提取错误信息展示（优先取后端 `message`）；
4. **请求拦截器**会在本地存有令牌时自动附加请求头 `Authorization: Bearer <token>`，业务代码不用手动传；
5. 收到 401（令牌缺失/无效/过期）时自动清空本地登录态并唤起登录弹窗（登录/注册接口自身的 401 不在此列，那是"密码错误"
   的业务失败）；403（管理员权限不足）按普通业务错误提示，不动登录态。

```ts
// 视图层示例
import {getErrorMessage} from '@/api/request'

addChannel(form)
    .then(() => ElMessage.success('添加渠道成功'))
    .catch(err => ElMessage.error(getErrorMessage(err, '添加渠道失败')))
```

> 注意：新代码不要再读取 `err.response?.data?.detail`（旧格式），统一走 `getErrorMessage`。

---

## 5. 后端开发约定（新增接口时遵守）

1. **成功响应**一律使用 `success_response(message=..., data=...)` 构造，禁止路由直接返回裸 dict / 裸列表 / 裸字符串；
2. **业务错误**在 service 层抛 `HTTPException(status_code=..., detail=中文提示)`，禁止在路由里手写 try/except 拼错误
   JSON；
3. **数据库异常**（`SQLAlchemyError` / `IntegrityError`）不要捕获后吞掉，让其冒泡给全局处理器；事务回滚由 `get_db`
   依赖统一完成，service 层只需在成功路径上 `commit()`；
4. 路径采用 RESTful 风格：资源名用名词复数（`/channels`），定位键放路径参数（`/channels/{channel_name}`），动作用 HTTP 方法区分（GET
   查 / POST 增 / PUT 改 / DELETE 删）；
5. 请求/响应字段使用驼峰别名（`channel_name` ↔ `channelName`），在 Schema 中通过 `Field(alias=...)` 映射。
