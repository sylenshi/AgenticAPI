"""StepSearch 联网搜索服务（阶跃星辰 MCP 端点）

供模型工坊的联网搜索工具循环（studio_agent_service）调用：上游模型把 web_search
当"客户端函数工具"，发出 tool_calls 后停下等结果，本服务负责把搜索真正执行掉。

接入方式说明：
- 阶跃 StepSearch 提供远程 MCP 端点（streamable HTTP），实测为无状态服务：
  不需要 initialize 握手，直接 POST tools/call 即可拿到结果，因此不引入 mcp
  SDK，用 httpx 手发 JSON-RPC 报文即可；
- 直接 REST 搜索接口 POST /v1/search 属开放平台单独计费体系，Step Plan 的
  Key 调用返回 402，故不走；
- 计费：每次调用 0.04 元，从 Step Plan 月度 Credit 扣，与标题生成共用 STEPFUN_API_KEY。
"""

import json

import httpx

from app.core.config import agent_setting

# StepSearch MCP 端点（web_search 工具）
SEARCH_MCP_URL = "https://api.stepfun.com/step_plan/v1/mcp/web_search/mcp"

# 最多取前 N 条结果（控制回传给模型的 token 量）
MAX_RESULTS = 8
# 单条结果正文截断长度
CONTENT_SNIPPET_LIMIT = 500


def search_available() -> bool:
    """联网搜索是否可用（未配置密钥时工坊直接降级为普通对话，不注入工具）"""
    return bool(agent_setting.STEPFUN_API_KEY)


async def web_search(query: str, timeout: int = 20,
                     max_results: int = MAX_RESULTS,
                     snippet_limit: int = CONTENT_SNIPPET_LIMIT) -> str:
    """
    执行一次联网搜索，把结果格式化成模型友好的文本（编号 + 标题 + URL + 时间 + 摘要）。

    max_results / snippet_limit 可调小以压缩回传体积（维护 Agent 工具侧用小配额，
    避免结果字节量超过工具结果 8KB 截断线被整体折叠；工坊走默认值不受影响）。

    任何失败都不抛异常，而是返回一段带说明的文本——让模型能感知"这次没搜到"
    并继续作答（降级），而不是把整条对话流打断。
    """
    if not search_available():
        return "搜索服务未配置（缺少 STEPFUN_API_KEY），请基于已有知识直接回答并说明未能联网核实。"
    if not query or not query.strip():
        return "搜索词为空，请直接回答。"

    rpc = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": "web_search", "arguments": {"query": query.strip()}},
    }
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            resp = await client.post(
                SEARCH_MCP_URL,
                json=rpc,
                headers={
                    "Authorization": f"Bearer {agent_setting.STEPFUN_API_KEY}",
                    # MCP streamable HTTP 约定：同时接受 JSON 与 SSE 两种响应格式
                    "Accept": "application/json, text/event-stream",
                },
            )
    except httpx.HTTPError as exc:
        print(f"[search] 请求异常: {exc.__class__.__name__}")
        return f"搜索请求失败（{exc.__class__.__name__}），请基于已有知识回答并说明未能联网核实。"

    if resp.status_code == 402:
        return "搜索服务额度不足（402），请基于已有知识回答并说明未能联网核实。"
    if resp.status_code != 200:
        print(f"[search] 调用失败 {resp.status_code}: {resp.text[:200]}")
        return f"搜索服务返回 {resp.status_code}，请基于已有知识回答并说明未能联网核实。"

    results = _parse_mcp_results(resp)
    if results is None:
        return "搜索服务返回异常（结果解析失败），请基于已有知识回答并说明未能联网核实。"
    if not results:
        return f"未搜索到与「{query}」相关的结果，请基于已有知识回答并说明。"
    return _format_results(query, results, max_results=max_results, snippet_limit=snippet_limit)


def _parse_mcp_results(resp: httpx.Response) -> list[dict] | None:
    """从 MCP 响应（JSON 或 SSE 两种载体）里取出搜索结果列表；异常返回 None"""
    payload: dict | None = None
    content_type = resp.headers.get("content-type") or ""
    if "text/event-stream" in content_type:
        for line in resp.text.splitlines():
            if not line.startswith("data:"):
                continue
            data = line[5:].strip()
            if not data:
                continue
            try:
                obj = json.loads(data)
            except Exception:
                continue
            if isinstance(obj, dict) and isinstance(obj.get("result"), dict):
                payload = obj
                break
    else:
        try:
            obj = json.loads(resp.text)
        except Exception:
            return None
        if isinstance(obj, dict):
            payload = obj

    if not isinstance(payload, dict) or not isinstance(payload.get("result"), dict):
        # JSON-RPC 层报错（invalid_api_key / 限流等）在此暴露到控制台
        err = payload.get("error") if isinstance(payload, dict) else None
        if err:
            print(f"[search] MCP 返回错误: {str(err)[:200]}")
        return None

    text = ""
    for block in payload["result"].get("content") or []:
        if isinstance(block, dict) and isinstance(block.get("text"), str) and block["text"]:
            text = block["text"]
            break
    if not text:
        return None
    try:
        data = json.loads(text)
    except Exception:
        return None
    results = data.get("results") if isinstance(data, dict) else None
    if not isinstance(results, list):
        return None
    return [r for r in results if isinstance(r, dict) and r.get("url")]


def _format_results(query: str, results: list[dict],
                    max_results: int = MAX_RESULTS,
                    snippet_limit: int = CONTENT_SNIPPET_LIMIT) -> str:
    """把结果列表排版成给模型看的纯文本（max_results / snippet_limit 可压缩体积）"""
    taken = results[:max_results]
    lines = [f"以下是「{query}」的联网搜索结果（共 {len(taken)} 条，按相关性排序）：", ""]
    for i, r in enumerate(taken, 1):
        title = (r.get("title") or "").strip() or "(无标题)"
        url = r.get("url") or ""
        date = str(r.get("time") or "")[:10]
        snippet = (r.get("snippet") or "").strip()
        content = (r.get("content") or "").strip()
        # snippet 与 content 高度重复时只保留更长的那个，避免双倍 token
        digest = content if len(content) > len(snippet) else snippet
        digest = digest[:snippet_limit]
        head = f"[{i}] {title}" + (f"（{date}）" if date else "") + f"\nURL: {url}"
        lines.append(head + (f"\n摘要: {digest}" if digest else ""))
        lines.append("")
    lines.append("请优先依据以上结果回答并在引用处标注来源编号（如 [1]）；若结果不足以回答，请如实说明。")
    return "\n".join(lines)
