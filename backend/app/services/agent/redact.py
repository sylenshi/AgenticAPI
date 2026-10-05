"""递归脱敏过滤器：工具结果进入模型上下文 / 前端 / 消息表前的唯一一道闸

密钥闭环红线：渠道密钥仅存在于后端内存与 llm_channels 表，任何工具返回值
必须经过 redact() 后才能流向三处出口（模型上下文、前端、agent_message 落库）。
匹配规则：键名（不区分大小写）命中敏感词，或字符串值形如长密钥（sk- / Bearer 开头）。
"""

import re

# 键名命中即脱敏（小写比较）：覆盖常见密钥/凭证字段命名
SENSITIVE_KEY_PATTERNS = (
    "api_key", "apikey", "api-key",
    "token", "access_token", "refresh_token",
    "password", "authorization", "auth", "cookie", "secret",
)

# 字符串值形态脱敏：长随机串凭证（sk-xxx / Bearer xxx / x-api-key 形态）
_SECRET_VALUE_RE = re.compile(r"^(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S{8,}|[A-Za-z0-9_\-]{32,})$")


def _is_sensitive_key(key: str) -> bool:
    k = str(key).lower()
    return any(p in k for p in SENSITIVE_KEY_PATTERNS)


def _mask_value(value: str) -> str:
    """密钥值只留尾 4 位提示（如 sk-****ab12），太短的值直接全遮"""
    value = str(value)
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}" if value[:3].isascii() else f"****{value[-4:]}"


def redact(data):
    """
    递归脱敏：dict 按键名匹配，list/tuple 逐项下钻，字符串按密钥形态匹配。
    返回同结构的新对象（不修改入参）；不可序列化类型原样返回。
    """
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if _is_sensitive_key(key) and isinstance(value, str) and value:
                out[key] = _mask_value(value)
            elif _is_sensitive_key(key) and value is not None and not isinstance(value, (dict, list)):
                out[key] = _mask_value(str(value))
            else:
                out[key] = redact(value)
        return out
    if isinstance(data, (list, tuple)):
        drained = [redact(item) for item in data]
        return drained if isinstance(data, list) else tuple(drained)
    if isinstance(data, str) and _SECRET_VALUE_RE.match(data.strip()):
        return _mask_value(data.strip())
    return data


def redact_text(text: str, extra_secrets: list[str] | None = None) -> str:
    """
    纯文本脱敏：把已知密钥明文（extra_secrets，如渠道 api_key）替换为尾 4 位提示。
    自定义 skill 落盘前用它兜底清除上下文里可能残留的密钥。
    """
    for secret in extra_secrets or []:
        if secret and len(secret) > 8 and secret in text:
            text = text.replace(secret, _mask_value(secret))
    return text
