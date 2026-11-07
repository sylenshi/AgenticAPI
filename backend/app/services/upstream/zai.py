"""智谱（GLM Coding Plan）上游用量适配"""

import httpx

from app.services.upstream.base import http_error, network_error, ok, to_reset_at
from app.utils.json_utils import safe_get

USAGE_URL = "https://bigmodel.cn/api/monitor/usage/quota/limit"
# 不能带 type=2 参数（鉴权通过但 data 恒为空），默认请求即返回用量

# v2/v3 两种套餐的 limits 条目均以 unit 区分时间窗：3 = 5小时窗口、6 = 7天窗口（均无月度限额）
FIVE_HOUR_UNIT = 3
WEEKLY_UNIT = 6


def _window_used(item: dict) -> int:
    """已用量 = 限额总量 usage - 剩余量 remaining"""
    total = int(item.get("usage") or 0)
    remaining = int(item.get("remaining") or 0)
    return max(total - remaining, 0)


def fetch_zai_usage(operation_dict: dict, token_key: str = "ZAI_API_KEY") -> dict:
    """
    获取智谱 GLM Coding Plan 用量（5小时 + 7天两个窗口，无月限额）。
    同一接口按套餐版本返回两种结构，按 limits 条目类型自动识别：
    - v3：含 CREDIT_LIMIT 条目，带 usage/remaining 绝对值
    - v2：仅 TOKENS_LIMIT 条目，只带已用百分比（换算为 used=百分比 / total=100）
    :param token_key: API key 在运维配置中的键名，多账号时传入不同键（如 "ZAI_API_KEY_2"）；
        key 由 operations_service 从 .env 注入（长期有效，替代原浏览器 JWT 登录态）
    """
    # API key 鉴权固定为 "sk-" + key（key 本身不含 sk- 前缀，兼容误带前缀的粘贴）
    key = operation_dict.get(token_key, "")
    headers = {"Authorization": "sk-" + key.removeprefix("sk-")}

    try:
        resp = httpx.get(USAGE_URL, headers=headers, timeout=5)  # 避免卡死
        if resp.status_code != 200:
            return http_error(resp.status_code, resp.text)

        try:
            data = resp.json()
        except ValueError:
            # HTTP 200 但响应体不是 JSON（空 body / 网关错误页），按上游异常返回，不拖垮整个接口
            return http_error(resp.status_code, f"non-JSON response: {resp.text[:200]!r}")
        if not isinstance(data, dict):
            # 响应体是 JSON 数组等非对象结构，同样按上游异常返回
            return http_error(resp.status_code, f"unexpected payload type: {type(data).__name__}")
        # HTTP 200 但业务码非 200（如 token 失效）同样视为失败
        if data.get("code") != 200:
            return {"status": f"code:{data.get('code')}, msg:{str(data.get('msg'))[:200]}", "usage": {}, "raw": None}

        limits = safe_get(data, "data", "limits", default=[]) or []
        if not isinstance(limits, list):
            limits = []

        if any(x.get("type") == "CREDIT_LIMIT" for x in limits):
            # v3 套餐：按 unit 匹配时间窗，匹配不到时按返回顺序兜底（首个为 5 小时、次个为 7 天）
            credit = [x for x in limits if x.get("type") == "CREDIT_LIMIT"]
            five_hour = next((x for x in credit if x.get("unit") == FIVE_HOUR_UNIT), credit[0] if credit else {})
            weekly = next((x for x in credit if x.get("unit") == WEEKLY_UNIT), credit[1] if len(credit) > 1 else {})
            usage = {
                "zaiFiveHourUsed": _window_used(five_hour),
                "zaiFiveHourTotal": int(five_hour.get("usage") or 0),
                "zaiFiveHourResetAt": to_reset_at(five_hour.get("nextResetTime")),
                "zaiWeeklyUsed": _window_used(weekly),
                "zaiWeeklyTotal": int(weekly.get("usage") or 0),
                "zaiWeeklyResetAt": to_reset_at(weekly.get("nextResetTime")),
                "zaiMonthlyUsed": 0,
                "zaiMonthlyTotal": 0,
                "zaiMonthlyResetAt": None,
            }
        else:
            # v2 套餐：TOKENS_LIMIT 只给已用百分比，total 固定按 100 换算；
            # TIME_LIMIT（unit=5）是工具调用次数限制，不属于 token 用量，不展示
            five_hour = next((x for x in limits if x.get("type") == "TOKENS_LIMIT" and x.get("unit") == FIVE_HOUR_UNIT), {})
            weekly = next((x for x in limits if x.get("type") == "TOKENS_LIMIT" and x.get("unit") == WEEKLY_UNIT), {})
            usage = {
                "zaiFiveHourUsed": int(five_hour.get("percentage") or 0),
                "zaiFiveHourTotal": 100,
                "zaiFiveHourResetAt": to_reset_at(five_hour.get("nextResetTime")),
                "zaiWeeklyUsed": int(weekly.get("percentage") or 0),
                "zaiWeeklyTotal": 100,
                "zaiWeeklyResetAt": to_reset_at(weekly.get("nextResetTime")),
                "zaiMonthlyUsed": 0,
                "zaiMonthlyTotal": 0,
                "zaiMonthlyResetAt": None,
            }

        return ok(usage, data)
    except httpx.HTTPError as e:
        return network_error(e)
