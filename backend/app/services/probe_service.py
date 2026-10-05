"""渠道直发拨测服务（免计费）

与中转链路的区别：不经 resolve_target / 计费 / chat_record，后端直接注入渠道密钥
向 base_url 发一条极小探测请求（max_tokens 16、非流式、10s 超时），只写一条 admin
审计日志。用于维护 Agent 的渠道连通性测试（A2）与出站模型拨测（C2/C3）。

注意：本服务是渠道密钥的合法存在地之一——密钥仅在本模块内部注入请求头，
任何返回值不得携带密钥（返回结构里只有时延/状态码/错误摘要）。
"""

import asyncio
import time

import httpx
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import channel as channel_crud
from app.crud import model as model_crud

PROBE_TIMEOUT_SECONDS = 10
PROBE_MAX_TOKENS = 16
# 批测并发上限：避免一次性打爆上游（设计护栏）
PROBE_CONCURRENCY = 5


async def probe_once(base_url: str, api_key: str, model_name: str,
                     timeout: int = PROBE_TIMEOUT_SECONDS) -> dict:
    """
    对一个 (渠道, 模型) 组合直发一条探测请求，返回 {ok, latencyMs, status, error}。
    绝不抛异常——拨测失败本身就是有效结果（Error as Data）。
    """
    payload = {
        "model": model_name,
        "messages": [{"role": "user", "content": "ping"}],
        "max_tokens": PROBE_MAX_TOKENS,
        "stream": False,
    }
    start = time.time()
    try:
        async with httpx.AsyncClient(timeout=httpx.Timeout(timeout)) as client:
            resp = await client.post(
                base_url, json=payload,
                headers={"Authorization": f"Bearer {api_key}"},
            )
        latency_ms = int((time.time() - start) * 1000)
        if resp.status_code == 200:
            return {"ok": True, "latencyMs": latency_ms, "status": 200, "error": ""}
        # 错误摘要只保留前 160 字符，避免上游长报文撑爆工具结果
        try:
            err = str(resp.json().get("error", {}).get("message") or resp.text)[:160]
        except Exception:
            err = resp.text[:160]
        return {"ok": False, "latencyMs": latency_ms, "status": resp.status_code, "error": err}
    except httpx.HTTPError as exc:
        latency_ms = int((time.time() - start) * 1000)
        return {"ok": False, "latencyMs": latency_ms, "status": 0, "error": f"{exc.__class__.__name__}: {exc}"[:160]}
    except Exception as exc:  # 未知异常也包装为失败结果，不中断批测
        return {"ok": False, "latencyMs": 0, "status": 0, "error": f"{exc.__class__.__name__}"[:160]}


async def probe_channel(db: AsyncSession, channel_name: str, model_names: list[str]) -> dict:
    """
    对指定渠道的若干模型并发拨测（并发受限），返回汇总结果。
    model_names 为空时自动取渠道 support_models 全量。
    """
    channel = await channel_crud.get_by_name(db, channel_name)
    if not channel:
        return {"isError": True, "message": f"渠道 {channel_name} 不存在"}
    if not channel.get("status"):
        return {"isError": True, "message": f"渠道 {channel_name} 已停用，请先启用再测试"}

    if not model_names:
        import json
        try:
            model_names = json.loads(channel.get("support_models") or "[]")
        except (TypeError, ValueError):
            model_names = []
    if not model_names:
        return {"isError": True, "message": f"渠道 {channel_name} 未配置支持模型"}

    # 站内模型名 → 上游名映射（与中转链路同规则：upstream_name 优先）
    upstream_names: dict[str, str] = {}
    for name in model_names:
        model = await model_crud.get_by_name(db, name)
        upstream = (model or {}).get("upstream_name") or ""
        upstream_names[name] = upstream.strip() or name

    semaphore = asyncio.Semaphore(PROBE_CONCURRENCY)

    async def _one(name: str) -> dict:
        async with semaphore:
            result = await probe_once(
                channel["base_url"], channel["api_key"], upstream_names[name],
                timeout=min(channel.get("timeout") or 30, 30),
            )
            return {"model": name, **result}

    results = await asyncio.gather(*[_one(n) for n in model_names])
    ok_count = sum(1 for r in results if r["ok"])
    latencies = [r["latencyMs"] for r in results if r["ok"]]
    return {
        "channel": channel_name,
        "probed": len(results),
        "okCount": ok_count,
        "failCount": len(results) - ok_count,
        "avgLatencyMs": round(sum(latencies) / len(latencies)) if latencies else None,
        "results": results,
    }


async def probe_model(db: AsyncSession, model_name: str) -> dict:
    """
    出站模型拨测：按模型绑定的渠道顺序逐个直发探测（渠道顺序轮询与中转一致），
    任一渠道成功即视为模型可用；全部失败输出逐渠道错误明细。
    """
    from app.services.relay_service import _ordered_channels
    from app.utils.json_utils import parse_json_list

    model = await model_crud.get_by_name(db, model_name)
    if not model:
        return {"isError": True, "message": f"模型 {model_name} 不存在"}
    channel_names = parse_json_list(model.get("channels"))
    if not channel_names:
        return {"isError": True, "message": f"模型 {model_name} 未绑定渠道"}

    upstream_name = (model.get("upstream_name") or "").strip() or model_name
    results = []
    for channel_name in _ordered_channels(model_name, channel_names):
        channel = await channel_crud.get_by_name(db, channel_name)
        if not channel or not channel.get("status"):
            results.append({"channel": channel_name, "ok": False, "latencyMs": 0,
                            "status": 0, "error": "渠道不存在或已停用"})
            continue
        result = await probe_once(
            channel["base_url"], channel["api_key"], upstream_name,
            timeout=min(channel.get("timeout") or 30, 30),
        )
        results.append({"channel": channel_name, **result})
        if result["ok"]:
            break  # 与中转语义一致：渠道顺序失败切换，任一成功即返回

    ok = any(r["ok"] for r in results)
    ok_latency = [r["latencyMs"] for r in results if r["ok"]]
    return {
        "model": model_name,
        "ok": ok,
        "latencyMs": ok_latency[0] if ok_latency else None,
        "triedChannels": len(results),
        "results": results,
        "_summary": f"模型 {model_name} {'可用' if ok else '不可用'}"
                    + (f"（时延 {ok_latency[0]}ms）" if ok_latency else ""),
    }


async def probe_model_first_channel(db: AsyncSession, model: dict) -> dict:
    """巡检用的快速拨测：只探模型第一个启用渠道（全量遍历见 test_all_models）"""
    from app.utils.json_utils import parse_json_list

    model_name = model.get("name")
    for channel_name in parse_json_list(model.get("channels")):
        channel = await channel_crud.get_by_name(db, channel_name)
        if not channel or not channel.get("status"):
            continue
        upstream = (model.get("upstream_name") or "").strip() or model_name
        result = await probe_once(
            channel["base_url"], channel["api_key"], upstream,
            timeout=min(channel.get("timeout") or 30, 30),
        )
        return {"model": model_name, "channel": channel_name, **result}
    return {"model": model_name, "channel": "", "ok": False, "latencyMs": 0,
            "status": 0, "error": "无启用的绑定渠道"}
