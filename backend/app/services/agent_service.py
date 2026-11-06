"""Agent 能力服务：站内功能直连大模型的内部调用层

与中转链路（relay_service）完全独立——不经 llm_models / llm_channels 表，
不做渠道轮询、不计费、不写日志 / 用量统计 / 对话记录。
专供站内功能使用：会话自动起标题，后续的视觉理解 / 图片生成 / TTS 等
能力也在此文件内扩展，供应商凭证统一读 agent_setting。
StepFun 对话端点为 OpenAI 兼容格式，非流式调用。
"""

import httpx

from app.core.config import agent_setting


async def agent_chat(
        messages: list[dict],
        model: str,
        max_tokens: int = 512,
        temperature: float = 0.7,
        timeout: int = 30,
        reasoning_effort: str = "medium",
) -> dict | None:
    """
    Agent 通用单轮对话（OpenAI 兼容）：返回首个 choice 的文本内容。

    :param model: 模型名，由调用方从 agent_setting 的 AGENT_*_MODEL 取默认值传入
    失败（未配置 / 网络 / 非 200 / 响应异常）一律返回 None，由调用方自行兜底，
    不抛异常——agent 能力属于"锦上添花"，绝不能影响主流程。
    """
    if not agent_setting.STEPFUN_API_KEY:
        return None
    body = {
        "model": model,
        "messages": messages,
        "stream": False,  # 非流式调用，这样更简单
        "max_tokens": max_tokens,
        "temperature": temperature,
        "reasoning_effort": reasoning_effort,
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                agent_setting.AGENT_BASE_URL, json=body,
                headers={"Authorization": f"Bearer {agent_setting.STEPFUN_API_KEY}"},
            )
    except httpx.HTTPError as exc:
        print(f"[agent] 请求异常: {exc.__class__.__name__}")  # 超时/断连不再静默
        return None
    if resp.status_code != 200:
        print(f"[agent] 调用失败 {resp.status_code}: {resp.text[:200]}")
        return None
    try:
        choice = (resp.json().get("choices") or [{}])[0]
        message = choice.get("message") or {}
        content = message.get("content")
        # StepFun 的思维链字段两个名字都发（实测响应里 reasoning / reasoning_content 并存），优先取后者
        reasoning = message.get("reasoning_content") or message.get("reasoning") or ""
    except Exception as exc:
        print(f"[agent] 响应解析失败: {exc.__class__.__name__}")
        return None
    if isinstance(content, str) and content.strip():
        return {"content": content.strip(), "reasoning": reasoning}
        # content 为空：推理模型思维链烧光 max_tokens 时 finish_reason 会是 length
    print(f"[agent] content 为空 finish_reason={choice.get('finish_reason')}")
    return None
