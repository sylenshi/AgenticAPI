"""Antigravity（Google Gemini PRO）上游限额适配

数据源是同机回环的 sub2api 容器管理端 API（订阅转 API 网关，端口 8080）：
- POST {base}/api/v1/auth/login                  → 管理员邮箱+密码换 JWT（24h 有效，登录接口限流，
                                                    故 token 模块级缓存 23h 内复用，401 时强制重登一次）
- POST {base}/api/v1/admin/accounts/usage/batch  → 批量查询账号用量（body: {"account_ids": [...]};
                                                    sub2api 服务端自带 3 分钟缓存，上游失败负缓存 1 分钟）
鉴权：Authorization: Bearer {JWT}。

sub2api 用账号自己的凭证实时向上游查 retrieveUserQuotaSummary，按模型分组返回配额窗口
（antigravity_quota_groups）：gemini 组 = Gemini 池、3p 组 = Claude 池，每组各有
5h / weekly 两个窗口（上游无月度窗口），utilization 为 0~1 的已用占比，resets_at 为 UTC ISO 串。

因此本适配器返回 4 个数据点：Gemini 池与 Claude 池的 5 小时 / 周度，
已用量 = utilization * 100（百分比语义，Total 恒为 100，与其他卡同一展示语言）。
sub2api 自带缓存，本地不再区分 live/cache 双速，查询失败时如实报错。
"""

import time
from typing import Any, Optional

import httpx

from app.services.upstream.base import http_error, network_error, ok, to_reset_at

# 管理端 JWT 缓存：上游 24h 过期、登录接口限流 20 次/分，23h 内复用避免频繁登录
_jwt_cache: dict = {"token": "", "issued_at": 0.0}
_JWT_TTL_SECONDS = 23 * 3600

# antigravity_quota_groups 里的两个池子 key：gemini=Gemini 池，3p=Claude 池
_POOLS = ("gemini", "3p")
_WINDOWS = ("5h", "weekly")


def _login(base_url: str, email: str, password: str, force: bool = False) -> str:
    """登录 sub2api 管理端换 JWT；token 模块级缓存，23h 内复用（上游 24h 过期）"""
    if (not force and _jwt_cache["token"]
            and time.time() - _jwt_cache["issued_at"] < _JWT_TTL_SECONDS):
        return _jwt_cache["token"]
    resp = httpx.post(
        f"{base_url}/api/v1/auth/login",
        json={"email": email, "password": password},
        timeout=10,
    )
    resp.raise_for_status()
    token = ((resp.json().get("data") or {}).get("access_token"))
    if not token:
        raise ValueError("登录响应缺少 access_token")
    _jwt_cache["token"] = token
    _jwt_cache["issued_at"] = time.time()
    return token


def _post_usage(base_url: str, token: str, account_ids: list) -> httpx.Response:
    """批量查询账号用量（sub2api 服务端有 3 分钟缓存；缓存过期时它需经 VPN 实时查
    Google，25s 超时给前端 30s 的 axios 预算留余量）。不在此处 raise_for_status，
    让调用方先处理 401 重登再统一判错。"""
    return httpx.post(
        f"{base_url}/api/v1/admin/accounts/usage/batch",
        headers={"Authorization": f"Bearer {token}"},
        json={"account_ids": account_ids},
        timeout=25,
    )


def _pick_group(groups: Any, key: str) -> Optional[dict]:
    """按分组 key 取模型组（gemini=Gemini 池，3p=Claude 池）"""
    if not isinstance(groups, list):
        return None
    for g in groups:
        if isinstance(g, dict) and g.get("key") == key:
            return g
    return None


def _pick_window(group: Optional[dict], window: str) -> Optional[dict]:
    """从模型组里取指定窗口的配额（window: "5h" / "weekly"）"""
    if not group:
        return None
    windows = group.get("windows")
    if not isinstance(windows, list):
        return None
    for w in windows:
        if isinstance(w, dict) and w.get("window") == window:
            return w
    return None


def _reset_at(value: Any) -> Optional[str]:
    """上游 resets_at 是带 Z 后缀的 UTC ISO 串，先归一化再复用公共转换"""
    if isinstance(value, str) and value.endswith("Z"):
        value = value[:-1] + "+00:00"
    return to_reset_at(value)


def _window_fields(window: Optional[dict]) -> dict:
    """配额窗口 → 其他卡片同款的 Used/Total/ResetAt 三件套；窗口缺失时 Total=0，
    前端据此显示「无对应窗口限额」"""
    if not window:
        return {"Used": 0, "Total": 0, "ResetAt": None}
    util = window.get("utilization")
    used = round(max(0.0, min(1.0, util)) * 100, 2) if isinstance(util, (int, float)) else 0
    return {"Used": used, "Total": 100, "ResetAt": _reset_at(window.get("resets_at"))}


def fetch_antigravity_usage(operation_dict: dict) -> dict:
    """获取 Antigravity 双池限额：Gemini 池与 Claude 池各 5 小时 / 周度共 4 个窗口

    :param operation_dict: 运维配置（antigravity_base_url / antigravity_admin_email /
        antigravity_admin_password / antigravity_account_ids，由 operations_service 从 .env 注入）
    """
    base_url = (operation_dict.get("antigravity_base_url") or "http://127.0.0.1:8080").rstrip("/")
    email = operation_dict.get("antigravity_admin_email", "")
    password = operation_dict.get("antigravity_admin_password", "")
    if not email or not password:
        return {
            "status": "config:ANTIGRAVITY_ADMIN_EMAIL / ANTIGRAVITY_ADMIN_PASSWORD 未配置（backend/.env）",
            "usage": {}, "raw": None,
        }
    account_ids = []
    for s in str(operation_dict.get("antigravity_account_ids") or "1").split(","):
        s = s.strip()
        if s:
            account_ids.append(int(s) if s.isdigit() else s)
    if not account_ids:
        account_ids = [1]

    try:
        token = _login(base_url, email, password)
        resp = _post_usage(base_url, token, account_ids)
        if resp.status_code == 401:  # token 失效（上游重启/换密）→ 强制重登一次再试
            token = _login(base_url, email, password, force=True)
            resp = _post_usage(base_url, token, account_ids)
        resp.raise_for_status()

        try:
            payload = resp.json()
        except ValueError:
            raise ValueError(f"non-JSON response: {resp.text[:200]!r}")
        usage_map = (payload.get("data") or {}).get("usage") if isinstance(payload, dict) else None
        if not isinstance(usage_map, dict) or not usage_map:
            raise ValueError("sub2api 未返回账号用量（data.usage 为空）")

        # 多账号时聚合出各池各窗口利用率最高的那份数据（保守展示最紧的额度）
        best: dict = {}  # (pool, window) -> window dict
        for account in usage_map.values():
            groups = account.get("antigravity_quota_groups") if isinstance(account, dict) else None
            for pool in _POOLS:
                group = _pick_group(groups, pool)
                for window in _WINDOWS:
                    w = _pick_window(group, window)
                    if w is None:
                        continue
                    cur = best.get((pool, window))
                    if cur is None or (w.get("utilization") or 0) > (cur.get("utilization") or 0):
                        best[(pool, window)] = w

        if not best:
            return {"status": "code:200, msg:sub2api 未返回分组配额", "usage": {}, "raw": None}

        gemini_five = _window_fields(best.get(("gemini", "5h")))
        gemini_weekly = _window_fields(best.get(("gemini", "weekly")))
        claude_five = _window_fields(best.get(("3p", "5h")))
        claude_weekly = _window_fields(best.get(("3p", "weekly")))

        usage = {
            # Gemini 池
            "agFiveHourUsed": gemini_five["Used"],
            "agFiveHourTotal": gemini_five["Total"],
            "agFiveHourResetAt": gemini_five["ResetAt"],
            "agWeeklyUsed": gemini_weekly["Used"],
            "agWeeklyTotal": gemini_weekly["Total"],
            "agWeeklyResetAt": gemini_weekly["ResetAt"],
            # Claude 池
            "agClaudeFiveHourUsed": claude_five["Used"],
            "agClaudeFiveHourTotal": claude_five["Total"],
            "agClaudeFiveHourResetAt": claude_five["ResetAt"],
            "agClaudeWeeklyUsed": claude_weekly["Used"],
            "agClaudeWeeklyTotal": claude_weekly["Total"],
            "agClaudeWeeklyResetAt": claude_weekly["ResetAt"],
        }
        # raw 只保留窗口数据做调试快照，避免把 token 等账号敏感字段落盘
        raw = {
            "account_ids": account_ids,
            "windows": {
                f"{pool}:{window}": best.get((pool, window))
                for pool in _POOLS for window in _WINDOWS
            },
        }
        return ok(usage, raw)
    except httpx.HTTPStatusError as e:
        return http_error(e.response.status_code, e.response.text)
    except httpx.HTTPError as e:
        return network_error(e)
    except ValueError as e:
        return {"status": f"code:200, msg:sub2api 响应异常: {e}", "usage": {}, "raw": None}
