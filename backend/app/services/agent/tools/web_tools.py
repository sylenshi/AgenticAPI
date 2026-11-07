"""联网搜索域工具：W1 web_search（复用模型工坊的 StepSearch 通道）

与工坊的差异：工坊是模型自主发起 tool_calls 的客户端函数工具循环；维护
Agent 这边是白名单服务端工具，模型显式调用本工具执行搜索。同一把
STEPFUN_API_KEY（0.04 元/次计入 Step Plan 月度 Credit），未配置时返回可行动
的降级提示。
"""

from app.services import search_service
from app.services.agent.registry import ToolContext, ToolDef, register

# 回传模型的结果截断（工具结果最终仍会过 registry 的 8KB 截断管线）
# 注意截断器按字节（8KB）计而这里按字符计：中文 3 字节/字符，故源头上用小配额
# （6 条 × 220 字摘要 ≈ 最坏 6.5KB 字节），避免超限被整体折叠（v0.14.1 修复）
RESULT_MAX_CHARS = 6000
QUERY_MAX_CHARS = 200
# Agent 工具侧的搜索配额（工坊调用走 search_service 默认值 8 条 × 500 字，不受影响）
AGENT_MAX_RESULTS = 6
AGENT_SNIPPET_LIMIT = 220


async def web_search_tool(ctx: ToolContext, args: dict) -> dict:
    """W1 联网搜索：查上游故障公告 / 模型定价变更 / 报错信息"""
    query = (args.get("query") or "").strip()
    if not query:
        raise ValueError("query 不能为空")
    if len(query) > QUERY_MAX_CHARS:
        raise ValueError(f"query 过长（{len(query)} 字符，上限 {QUERY_MAX_CHARS}），请精简搜索词")

    if not search_service.search_available():
        raise ValueError("联网搜索未配置（后端 .env 缺少 STEPFUN_API_KEY），"
                         "请基于已有知识回答并向管理员说明无法联网核实")

    result = await search_service.web_search(
        query, max_results=AGENT_MAX_RESULTS, snippet_limit=AGENT_SNIPPET_LIMIT)
    return {
        "query": query,
        "result": result[:RESULT_MAX_CHARS],
        "_summary": f"已搜索「{query}」（结果 {len(result)} 字符）",
    }


def register_web_tools() -> None:
    register(ToolDef(
        name="web_search",
        description="联网搜索（阶跃 StepSearch，按次计费 0.04 元）：查上游服务商故障公告、模型定价与发布动态、报错信息。返回编号列表（标题+URL+摘要）。",
        parameters={"type": "object", "properties": {
            "query": {"type": "string", "description": f"搜索词（≤{QUERY_MAX_CHARS} 字符）"},
        }, "required": ["query"]},
        risk="L0", handler=web_search_tool, timeout=40,
    ))
