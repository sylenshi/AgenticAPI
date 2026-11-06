# API 调用文档

> 面向本站用户：如何获取 API 密钥，并通过 OpenAI 兼容接口调用本站接入的大模型。

## 简介

本站对外提供 **OpenAI Chat Completions 兼容**的中转接口与 **OpenAI Models 兼容**的模型列表接口：你可以在 Cherry Studio、ChatBox、LobeChat
等第三方 AI 工具中把本站当作一个 "OpenAI" 来配置，也可以用 OpenAI 官方 SDK / curl 直接调用，
用本站密钥（`sk-` 开头）访问站内接入的所有模型。

> **关于接口地址**：本文以线上部署地址 `https://platform.shienhao.cn` 为例（本地部署时对应 `http://localhost:2027`）。
> 站点部署到公网后，请以站内实际展示的地址为准（控制台-秘钥页、模型广场的模型详情面板都会自动展示当前真实地址），
> 若使用本地部署，把下文中的 `https://platform.shienhao.cn` 替换为 `http://localhost:2027` 即可。

## 快速开始

调用接口只需三步：

1. **注册并登录**：点击导航栏右上角「注册」创建账号（也可以用「访客」体验，访客同样可以调用接口）；
2. **创建 API 密钥**：进入「控制台 → 秘钥」页面，填写备注名创建密钥（`sk-` 开头，每个账号最多 5 个）；
3. **发起调用**：按下文示例，携带 `Authorization: Bearer sk-xxx` 请求
   `POST https://platform.shienhao.cn/v1/chat/completions`。

## 接入信息

在第三方工具或代码中接入本站，只需要三项信息：

| 项目      | 值                                  | 说明                                          |
|---------|------------------------------------|---------------------------------------------|
| Base URL | `https://platform.shienhao.cn/v1`         | OpenAI 兼容基地址，部署后替换为实际地址                |
| API Key  | `sk-xxxxxxxx`                      | 在「控制台 → 秘钥」页创建                          |
| 模型名称    | 如 `glm-4.7`                        | 见模型广场，或调 `GET /v1/models` 获取你可用的模型，调用时填在 `model` 字段 |

## 调用示例

### curl（非流式）

```sh
curl https://platform.shienhao.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的API密钥" \
  -d '{
    "model": "glm-4.7",
    "messages": [
      {"role": "user", "content": "你好，请介绍一下你自己"}
    ],
    "max_tokens": 1024
  }'
```

### curl（流式）

加 `"stream": true` 即为流式响应（SSE，逐块返回），建议加 `-N` 关闭 curl 缓冲实时查看：

```sh
curl -N https://platform.shienhao.cn/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "Authorization: Bearer sk-你的API密钥" \
  -d '{
    "model": "glm-4.7",
    "messages": [{"role": "user", "content": "给我讲个故事"}],
    "stream": true
  }'
```

流式响应为标准 SSE 格式，每个事件形如 `data: {...}`，以 `data: [DONE]` 结束：

```
data: {"id":"...","object":"chat.completion.chunk","model":"glm-4.7","choices":[{"index":0,"delta":{"role":"assistant","content":"你"},"finish_reason":null}]}

data: {"id":"...","object":"chat.completion.chunk","model":"glm-4.7","choices":[{"index":0,"delta":{},"finish_reason":"stop"}],"usage":{"prompt_tokens":10,"completion_tokens":20,"total_tokens":30}}

data: [DONE]
```

> 本站会自动为流式请求附加 `include_usage`，因此最后一个 chunk 会携带 `usage` 用量信息，方便你统计 token 消耗。

### Python（OpenAI SDK）

```python
# pip install openai
from openai import OpenAI

client = OpenAI(
    base_url="https://platform.shienhao.cn/v1",   # 部署后替换为实际地址
    api_key="sk-你的API密钥",
)

# 非流式
response = client.chat.completions.create(
    model="glm-4.7",
    messages=[{"role": "user", "content": "你好，请介绍一下你自己"}],
    max_tokens=1024,
)
print(response.choices[0].message.content)
print(response.usage)   # token 用量
```

流式只需加 `stream=True`：

```python
stream = client.chat.completions.create(
    model="glm-4.7",
    messages=[{"role": "user", "content": "给我讲个故事"}],
    stream=True,
)
for chunk in stream:
    delta = chunk.choices[0].delta
    if delta.content:
        print(delta.content, end="", flush=True)
```

### Node.js（OpenAI SDK）

```js
// npm install openai
import OpenAI from "openai";

const client = new OpenAI({
  baseURL: "https://platform.shienhao.cn/v1",   // 部署后替换为实际地址
  apiKey: "sk-你的API密钥",
});

const response = await client.chat.completions.create({
  model: "glm-4.7",
  messages: [{ role: "user", content: "你好，请介绍一下你自己" }],
});

console.log(response.choices[0].message.content);
```

### 视觉模型（图片理解）

支持视觉能力的模型（模型广场中标有视觉能力）使用 OpenAI 多模态消息格式，图片以 URL 或 base64 传入：

```python
response = client.chat.completions.create(
    model="支持视觉的模型名",
    messages=[{
        "role": "user",
        "content": [
            {"type": "text", "text": "这张图片里有什么？"},
            {"type": "image_url", "image_url": {"url": "https://example.com/image.png"}},
        ],
    }],
)
print(response.choices[0].message.content)
```

## 接入第三方 AI 工具

Cherry Studio、ChatBox、LobeChat、沉浸式翻译等支持自定义 OpenAI 接口的工具均可接入：

1. 在工具的模型服务商设置中选择「自定义 / OpenAI 兼容」类型；
2. **API 地址**填 `https://platform.shienhao.cn/v1`（部署后替换为实际地址）；
3. **API 密钥**填你的 `sk-` 密钥；
4. 添加模型：若工具支持「获取模型列表 / 自动发现」，会通过 `GET /v1/models` 自动拉取你可用的模型；
   否则手动添加，模型名填模型广场中展示的名称（如 `glm-4.7`）。

## 模型列表接口（GET /v1/models）

返回**当前密钥所属用户可调用**的模型列表，OpenAI Models 兼容格式，直接把 `data[].id` 作为
`model` 字段的值即可调用。列表已按你的分组权限过滤（`free` 用户仅返回免费模型，`vip` 返回全部），
已停用的模型与渠道全部停用的模型不会出现，按模型名排序。

```sh
curl https://platform.shienhao.cn/v1/models \
  -H "Authorization: Bearer sk-你的API密钥"
```

响应示例：

```json
{
  "object": "list",
  "data": [
    {"id": "glm-4.7", "object": "model", "created": 1755369600, "owned_by": "agenticapi"},
    {"id": "step-3.7", "object": "model", "created": 1755369601, "owned_by": "agenticapi"}
  ]
}
```

OpenAI SDK 同样支持：

```python
models = client.models.list()
for m in models.data:
    print(m.id)   # 模型名，可直接用于 chat.completions 的 model 参数
```

> 鉴权与错误格式同 `/v1/chat/completions`：密钥无效返回 401，账号被封禁返回 403。
> 查询列表不校验余额、不产生费用。

## 请求参数

请求体为 OpenAI Chat Completions 格式，常用参数如下（透传给上游，最终以模型自身能力为准）：

| 参数            | 类型      | 必填 | 说明                                              |
|---------------|---------|----|---------------------------------------------------|
| `model`       | string  | 是 | 模型名称，见模型广场或 `GET /v1/models` 返回的列表     |
| `messages`    | array   | 是 | 对话消息数组，`role` 支持 `system` / `user` / `assistant` |
| `stream`      | boolean | 否 | 是否流式返回，默认 `false`                          |
| `max_tokens`  | integer | 否 | 最大生成 token 数（不超过模型配置的上限）              |
| `temperature` | number  | 否 | 采样温度                                           |
| `top_p`       | number  | 否 | 核采样参数                                         |

> 部分模型额外支持思维链、工具调用等参数，只要上游模型支持，请求体会原样透传。

## 响应说明

- **非流式**：返回标准 OpenAI JSON 结构，`choices[0].message.content` 为回答内容，`usage` 为 token 用量；
- **流式**：SSE 逐块返回增量内容（`delta.content`），以 `data: [DONE]` 结束，最后一个 chunk 携带 `usage`；
- **模型映射**：若某模型配置了上游模型映射，请求与响应中始终使用对外模型名（`model` 字段所见即所得），映射过程对你透明；
- **计费依据**：以响应中的 `usage`（`prompt_tokens` / `completion_tokens`）按模型定价计费。

## 错误码

失败时返回 OpenAI 格式错误体：`{"error": {"message": "...", "type": "...", "code": ...}}`。

| HTTP 状态码 | error.type             | 常见原因                          |
|-----------|------------------------|---------------------------------|
| 400       | invalid_request_error  | 请求体不是合法 JSON / 缺少 `model` 字段 |
| 401       | invalid_request_error  | 未提供或无效的 API 密钥             |
| 402       | insufficient_quota     | 账户余额不足                       |
| 403       | access_denied          | 账号被封禁 / 用户分组无权调用该模型     |
| 404       | invalid_request_error  | 模型不存在或已停用                  |
| 502       | api_error              | 模型未绑定可用渠道 / 所有上游渠道调用失败  |

## 计费与余额

- **计费方式**：按 token 用量计费，单价为**每百万 token** 价格（输入 / 输出 / 缓存命中分别计价，见模型广场各模型详情）；缓存命中的 token 按缓存价计收，不重复收输入价；标记为按次计费的模型每次调用收取固定费用；
- **余额不足**：余额小于等于 0 时调用会被拒绝（402），请在「控制台 → 概览」查看余额与累计消费；
- **分组权限**：`free` 分组用户只能调用模型广场中标记为免费的模型，`vip` 分组可调用全部模型；
- **密钥管理**：每个账号最多 5 个密钥，可在「控制台 → 秘钥」页随时启用 / 禁用 / 删除，禁用的密钥立即失效。

## 常见问题

**Q：调用返回 401？**
检查请求头是否为 `Authorization: Bearer sk-xxx`（也可以不带 `Bearer ` 前缀直接传密钥）；确认密钥未被禁用或删除。

**Q：调用返回 402？**
账户余额不足，登录后在「控制台 → 概览」查看余额。

**Q：调用返回 404？**
`model` 字段的值与模型广场中的模型名不一致，或该模型已下架。

**Q：调用返回 502？**
该模型的上游渠道全部故障，可稍后重试；持续失败请联系站点管理员。

**Q：流式响应怎么没有 usage？**
usage 在最后一个 chunk 中返回（本站已自动附加 `include_usage`）；如果你的解析逻辑在收到 `finish_reason` 后就中断了连接，会拿不到最后的 usage，请读到 `data: [DONE]` 为止。

**Q：在哪里看我的调用记录和消费？**
登录后进入「监控面板」查看调用日志与用量统计；每次调用的 token 数、费用、耗时都会记录。
