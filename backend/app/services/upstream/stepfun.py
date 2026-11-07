"""阶跃星辰（Step Plan）上游用量适配"""

import json
import time
from pathlib import Path

import httpx

from app.services.upstream.base import http_error, network_error, ok
from app.utils.json_utils import safe_get
from app.utils.token_utils import decode_jwt_payload

REFRESH_URL = (
    "https://platform.stepfun.com/passport/proto.api.passport.v1.PassportService/RefreshToken"
)
USAGE_URL = "https://platform.stepfun.com/api/step.openapi.devcenter.Dashboard/QueryStepPlanRateLimit"


def refresh_stepfun_token(operation_dict: dict, ops_json_path: Path) -> str:
    """
    检查阶跃星辰 Access Token 是否过期，过期则调用刷新接口获取新 token，
    并将新 token 持久化到 operations_config.json 中。
    返回拼接好的完整 token 字符串（access_token...refresh_token）。
    """
    stepfun_token = operation_dict.get("stepfun_token", "")

    if not stepfun_token:
        return stepfun_token

    parts = stepfun_token.split("...")
    if len(parts) != 2:
        return stepfun_token

    access_token = parts[0]

    # 解码 Access Token 的 payload，检查是否过期
    payload = decode_jwt_payload(access_token)
    exp = payload.get("exp") or 0
    now = time.time()
    # 如果距离过期不足 5 分钟，提前刷新
    need_refresh = exp - now < 300

    if not need_refresh:
        return stepfun_token

    # 调用刷新接口
    refresh_headers = {
        "accept": "*/*",
        "content-type": "application/json",
        "oasis-appid": "10300",
        "oasis-platform": "web",
        "oasis-webid": operation_dict.get("stepfun_webid", ""),
        "Oasis-Token": stepfun_token,
    }

    try:
        resp = httpx.post(REFRESH_URL, headers=refresh_headers, data="{}", timeout=30)
        if resp.status_code == 200:
            result = resp.json()
            new_access = result.get("accessToken", {}).get("raw", "")
            new_refresh = result.get("refreshToken", {}).get("raw", "")
            if new_access and new_refresh:
                new_token = new_access + "..." + new_refresh
                operation_dict["stepfun_token"] = new_token
                with open(ops_json_path, "w", encoding="utf-8") as f:
                    json.dump(operation_dict, f, ensure_ascii=False, indent=4)
                return new_token
    except Exception:
        pass

    # 刷新失败，返回旧 token 让调用方自行处理
    return stepfun_token


def fetch_stepfun_usage(operation_dict: dict, ops_json_path: Path) -> tuple[dict, str]:
    """
    获取阶跃星辰 Step Plan 用量（先检查并刷新 token）
    返回 (result_dict, current_token)，调用方应据此更新内存中的 operation_dict
    """
    stepfun_token = refresh_stepfun_token(operation_dict, ops_json_path)

    headers = {
        "accept": "*/*",
        "connect-protocol-version": "1",
        "content-type": "application/json",
        "oasis-appid": "10300",
        "oasis-platform": "web",
        "oasis-webid": operation_dict.get("stepfun_webid", ""),
        "Oasis-Token": stepfun_token,
    }

    try:
        resp = httpx.post(USAGE_URL, headers=headers, timeout=5)
        if resp.status_code != 200:
            return http_error(resp.status_code, resp.text), stepfun_token

        data = resp.json()
        credit_buckets = safe_get(data, "plan_credit_rate_limit", "credit_buckets")
        # 上游报文结构变化（字段缺失 / 空列表）时按"Error as Data"只打红本渠道，不打翻整个 /operations/get
        if not isinstance(credit_buckets, list) or not credit_buckets:
            return http_error(200, "stepfun 响应缺少 credit_buckets 数据"), stepfun_token
        bucket = credit_buckets[0] if isinstance(credit_buckets[0], dict) else {}
        total = int(safe_get(bucket, "credit_total") or 0)
        residual = int(safe_get(bucket, "credit_residual") or 0)
        usage = {
            "stepfunFiveHourUsed": 0,
            "stepfunFiveHourTotal": 0,
            "stepfunFiveHourResetAt": None,  # 阶跃该接口不返回任何重置时间
            "stepfunWeeklyUsed": 0,
            "stepfunWeeklyTotal": 0,
            "stepfunWeeklyResetAt": None,
            "stepfunMonthlyUsed": total - residual,
            "stepfunMonthlyTotal": total,
            "stepfunMonthlyResetAt": None,
        }
        return ok(usage, data), stepfun_token
    except httpx.HTTPError as e:
        return network_error(e), stepfun_token
    except Exception as e:  # noqa: BLE001  # 解析类异常同样降级为该渠道错误数据
        return http_error(200, f"stepfun 响应解析失败: {type(e).__name__}: {e}"), stepfun_token
