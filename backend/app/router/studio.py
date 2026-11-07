"""模型工坊接口（对话式 Playground，需登录、不计费）

- POST /studio/chat：SSE 流式对话，内部复用中转链路（渠道轮询 / 日志 / 用量统计），
  但不扣余额、不写对话记录；报文走 OpenAI 风格（成功透传上游 SSE，失败返回 {"error": {...}}），
  与 /v1 中转接口一致，不套用站内统一 {code, message, data} 格式
- POST /studio/asr：语音转文本，代理阶跃星辰 StepFun ASR（统一响应格式）
"""

import json
import re
import traceback

from app.core.config import agent_setting
from app.services import agent_service, search_service, studio_agent_service
import httpx
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.router.deps import get_db
from app.schemas.studio import StudioAsrSchema, StudioChatSchema, StudioTitleSchema
from app.services import relay_service
from app.services.relay_service import RelayError
from app.utils.auth import get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/studio", tags=["Studio"])


def _unhandled_error() -> JSONResponse:
    """未预期异常兜底：工坊对话走 OpenAI 报文风格，堆栈细节只进服务端日志"""
    print(f"[studio] /studio/chat 未预期异常: {traceback.format_exc()}")
    return RelayError(500, "服务器内部错误", "api_error").to_response()

# 联网搜索工具定义：透传给上游。上游模型把它当"客户端函数工具"（发出 tool_calls
# 后停下等结果），实际执行在后端 studio_agent_service 的工具循环里完成
WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for current information, news, or facts.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query to look up on the web"}
            },
            "required": ["query"],
        },
    },
}


def _build_chat_payload(body: StudioChatSchema) -> dict:
    """把工坊请求组装为中转链路的透传 payload"""
    messages: list[dict] = []
    if body.system_prompt.strip():
        messages.append({"role": "system", "content": body.system_prompt.strip()})
    for m in body.messages:
        content = m.content
        # 跳过空消息（前端流式截断后可能残留空 assistant 占位）
        if isinstance(content, str) and not content.strip():
            continue
        if isinstance(content, list) and not content:
            continue
        messages.append({"role": m.role, "content": content})

    payload: dict = {"model": body.model, "messages": messages, "stream": True}
    if body.temperature is not None:
        payload["temperature"] = body.temperature
    if body.top_p is not None:
        payload["top_p"] = body.top_p
    if body.max_tokens is not None:
        payload["max_tokens"] = body.max_tokens
    if body.enable_search:
        payload["tools"] = [WEB_SEARCH_TOOL]
    return payload


@router.post("/chat")
async def studio_chat(body: StudioChatSchema, db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """
    工坊对话（仅支持流式）。鉴权走站内登录令牌，模型分组权限与中转一致
    （free 用户仅 free 模型，vip 全部），调用不计费。

    联网搜索开启且搜索服务可用（配置了 STEPFUN_API_KEY）时，走后端 agent 工具循环
    （studio_agent_service）：模型发出的 web_search 调用由后端执行 StepSearch 并把结果
    回传上游续写，前端看到的是一条连续的 SSE；搜索服务未配置时不注入工具，干净降级
    为普通对话。
    """
    payload = _build_chat_payload(body)
    if not payload["messages"]:
        return RelayError(400, "消息列表不能为空").to_response()

    if body.enable_search:
        if not search_service.search_available():
            payload.pop("tools", None)  # 未配置搜索密钥：剥掉工具，普通对话
        else:
            try:
                return await studio_agent_service.chat_with_search(db, payload, user)
            except RelayError as exc:
                return exc.to_response()
            except Exception:
                return _unhandled_error()

    try:
        return await relay_service.chat_completions(db, payload, user, None, source="studio")
    except RelayError as exc:
        # 降级重试：开启联网搜索但搜索服务不可用时上游渠道报错，剥掉 tools 再试一次
        if body.enable_search and ("400" in exc.message or "422" in exc.message):
            payload.pop("tools", None)
            try:
                return await relay_service.chat_completions(db, payload, user, None, source="studio")
            except RelayError as retry_exc:
                return retry_exc.to_response()
            except Exception:
                return _unhandled_error()
        return exc.to_response()
    except Exception:
        return _unhandled_error()


@router.post("/asr")
async def studio_asr(body: StudioAsrSchema, user=Depends(get_current_user)):
    """语音转文本：前端录音 base64 上传，代理 StepFun ASR 返回识别文本"""
    if not agent_setting.STEPFUN_API_KEY:
        raise HTTPException(status_code=503, detail="语音服务未配置，请在后端 .env 中设置 STEPFUN_API_KEY")

    audio = body.audio
    # 兼容前端直接传 data URL 的情况（data:audio/webm;base64,xxxx）
    if audio.startswith("data:") and "," in audio:
        audio = audio.split(",", 1)[1]

    payload = {
        "audio": {
            "data": audio,
            "input": {
                "transcription":
                    {
                        "model": "stepaudio-2.5-asr", # 模型名称
                        "language": "zh", # 语言
                        "enable_itn": True # 是否开启 ITN 功能
                    },
                "format": {"type": body.format or "mp3"},
            },
        }
    }
    try:
        async with httpx.AsyncClient(timeout=60) as client:
            resp = await client.post(
                agent_setting.ASR_BASE_URL, json=payload,
                headers={"Accept": "text/event-stream", "Authorization": f"Bearer {agent_setting.STEPFUN_API_KEY}"},
            )
    except httpx.HTTPError:
        raise HTTPException(status_code=502, detail="语音识别服务请求失败")

    if resp.status_code != 200:
        raise HTTPException(status_code=502, detail=f"语音识别上游返回 {resp.status_code}")

    # 解析 SSE：取 type == "transcript.text.done" 事件的最终识别文本
    final_text = ""
    for line in resp.text.splitlines():
        if not line.startswith("data:"):
            continue
        data = line[5:].strip()
        if not data:
            continue
        try:
            event = json.loads(data)
        except Exception:
            continue
        if isinstance(event, dict) and event.get("type") == "transcript.text.done" and event.get("text"):
            final_text = event["text"]
            break
    return success_response(message="语音识别成功", data={"text": final_text})


TITLE_SYSTEM_PROMPT = (
    "你是一个对话标题生成专家。请根据用户消息的核心意图，生成一个极简的中文名词短语作为标题。\n\n"
    "【核心规则】\n"
    "1. 字数限制：严格控制在 2-8 个字，极致精简；\n"
    "2. 语言规范：技术术语/专有名词保留英文原文（如 SQL, React, K8s），其余使用中文；\n"
    "3. 内容聚焦：必须概括「核心话题」或「任务目标」，禁止使用“问题/咨询/求助/如何”等泛化词；\n"
    "4. 输出格式：仅输出纯文本标题，严禁包含引号、句号、换行符或任何解释性文字。\n\n"
    "【参考示例】\n"
    "输入：我想系统学习SQL，从零基础到能写复杂查询，有什么学习路径和建议\n"
    "输出：SQL学习路径\n"
    "输入：帮我通俗地讲讲 Python 装饰器是什么，怎么用\n"
    "输出：Python装饰器\n"
    "输入：报错 TypeError: 'NoneType' object is not subscriptable 怎么解决\n"
    "输出：NoneType报错排查\n"
    "输入：帮我把这段英文邮件改写得更加商务和礼貌\n"
    "输出：邮件商务润色"
)

# 标题安全上限：模型偶尔超出口径时不切词，交前端 CSS 按显示宽度裁剪
TITLE_MAX_LENGTH = 30


def _sanitize_title(raw: str) -> str:
    """清洗模型输出（去首尾空白/引号/书名号、“标题：”前缀、末尾标点），超长仅做安全上限不精细切词"""
    t = raw.strip()
    # 首尾包裹字符：空白、中英文引号、书名号（strip 参数是字符集合，双边生效）
    t = t.strip(" \t\"'“”‘’「『《》』」")
    # 模型偶尔不听话，带出「标题：xxx」前缀
    t = re.sub(r'^(标题|title)[:：]\s*', '', t, flags=re.IGNORECASE)
    # 末尾标点
    t = re.sub(r'[。．.!！?？~…]+$', '', t)
    # 压掉内部换行与连续空白，避免标题里带换行
    t = re.sub(r'\s+', ' ', t).strip()
    return t[:TITLE_MAX_LENGTH]


@router.post("/title")
async def studio_title(body: StudioTitleSchema, user=Depends(get_current_user)):
    """把首条用户消息概括为 10 字宽度左右的短标题；未配置或调用失败时回退原文截断方案"""
    if not agent_setting.STEPFUN_API_KEY or not agent_setting.AGENT_TITLE_MODEL:
        raise HTTPException(
            status_code=503,
            detail="标题生成服务未配置，请在后端 .env 中设置 STEPFUN_API_KEY / AGENT_TITLE_MODEL",
        )

    text = body.content.strip()
    if not text:
        return success_response(message="ok", data={"title": "新对话"})

    result = await agent_service.agent_chat(
        [{"role": "system", "content": TITLE_SYSTEM_PROMPT},
         {"role": "user", "content": text}],
        model=agent_setting.AGENT_TITLE_MODEL,
        max_tokens=2048, temperature=0.2, timeout=30, reasoning_effort="medium",
    )

    if result:
        return success_response(message="ok", data={
            "title": _sanitize_title(result["content"]) or "新对话",
            "source": "model",  # 显式标明：模型生成
            "reasoning": result["reasoning"][:200],  # 调试载荷，截断防响应体膨胀
        })

    # 双保险：agent 失败回退老的截断方案，前端拿到什么都能直接用
    return success_response(message="ok", data={
        "title": re.sub(r"\s+", " ", text)[:TITLE_MAX_LENGTH] or "新对话",
        "source": "fallback",  # 显式标明：走了兜底
        "reasoning": "",
    })
