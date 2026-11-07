"""递归脱敏过滤器：工具结果进入模型上下文 / 前端 / 消息表前的唯一一道闸

密钥闭环红线：渠道密钥仅存在于后端内存与 llm_channels 表，任何工具返回值
必须经过 redact() 后才能流向三处出口（模型上下文、前端、agent_message 落库）。
匹配规则：键名（不区分大小写）命中敏感词，或字符串值形如长密钥（sk- / Bearer 开头）；
v0.10.0 起补充子串级匹配——长文本（如沙箱命令）内嵌的 sk-/Bearer 凭证同样掩码；
v0.11.0 补充 mysql://user:pass@ 连接串掩码（沙箱 MySQL 桥接后可能出现在命令/输出里，
注入容器的 MYSQL_PASSWORD 经键名 password 规则天然命中）；
v0.14.1 修复两处误伤：max_tokens 等业务统计字段键名豁免；已是 "****" 掩码形态的值
（如 apiKeyHint 尾 4 位提示）不再二次处理。
"""

import re

# 键名命中即脱敏（小写比较）：覆盖常见密钥/凭证字段命名（MYSQL_PASSWORD 含 password 命中）
SENSITIVE_KEY_PATTERNS = (
    "api_key", "apikey", "api-key",
    "token", "access_token", "refresh_token",
    "password", "authorization", "auth", "cookie", "secret",
)

# 键名豁免（精确匹配，小写比较）：形似敏感词但实为业务统计字段（v0.14.1 修复误伤）
# —— "token" 子串会命中 max_tokens / prompt_tokens 等纯数值字段，把它们整成 "****"
SENSITIVE_KEY_EXEMPTS = frozenset({
    "max_tokens", "maxtokens",
    "prompt_tokens", "prompttokens",
    "completion_tokens", "completiontokens",
    "cached_tokens", "cachedtokens",
    "total_tokens", "totaltokens",
})

# 字符串值形态脱敏：长随机串凭证（sk-xxx / Bearer xxx / x-api-key 形态）
_SECRET_VALUE_RE = re.compile(r"^(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+\S{8,}|[A-Za-z0-9_\-]{32,})$")

# 子串级密钥形态（v0.10.0）：长文本内嵌的凭证只匹配高置信前缀（sk- / Bearer），
# 不做 32 位随机串子串匹配——避免误伤命令里的长文件名/URL 路径段
_SECRET_SUB_RE = re.compile(r"(sk-[A-Za-z0-9_\-]{8,}|Bearer\s+[A-Za-z0-9_\-.=/+]{8,})")

# mysql:// / mysql+asyncmy:// 连接串中嵌入的密码段（v0.11.0）
_MYSQL_URI_RE = re.compile(r"(mysql(?:\+asyncmy)?://[^:/@\s]+:)([^@\s/]+)(@)")


def _is_sensitive_key(key: str) -> bool:
    k = str(key).lower()
    if k in SENSITIVE_KEY_EXEMPTS:
        return False
    return any(p in k for p in SENSITIVE_KEY_PATTERNS)


def _mask_value(value: str) -> str:
    """密钥值只留尾 4 位提示（如 sk-****ab12），太短的值直接全遮"""
    value = str(value)
    if len(value) <= 8:
        return "****"
    return f"{value[:3]}****{value[-4:]}" if value[:3].isascii() else f"****{value[-4:]}"


def _is_bearer_like(token: str) -> bool:
    """Bearer 后的 token 段是否形似凭证：含数字，或长度 ≥24。
    纯英文短词（如说明性文本 "Bearer authentication"）不是凭证，避免误伤。"""
    return any(ch.isdigit() for ch in token) or len(token) >= 24


def _mask_substring_match(match: re.Match) -> str:
    """子串级掩码。Bearer 分支加判别：token 段无数字且长度 <24 的纯英文词不是凭证。"""
    text = match.group(0)
    if text.startswith("Bearer") and not _is_bearer_like(text[6:].strip()):
        return text
    return _mask_value(text)


def redact(data):
    """
    递归脱敏：dict 按键名匹配，list/tuple 逐项下钻，字符串按密钥形态匹配。
    返回同结构的新对象（不修改入参）；不可序列化类型原样返回。
    """
    if isinstance(data, dict):
        out = {}
        for key, value in data.items():
            if isinstance(value, str) and value.startswith("****"):
                out[key] = value  # 已是掩码形态（如 apiKeyHint 尾 4 位提示），不再二次处理
            elif _is_sensitive_key(key) and isinstance(value, str) and value:
                out[key] = _mask_value(value)
            elif _is_sensitive_key(key) and value is not None and not isinstance(value, (dict, list)):
                out[key] = _mask_value(str(value))
            else:
                out[key] = redact(value)
        return out
    if isinstance(data, (list, tuple)):
        drained = [redact(item) for item in data]
        return drained if isinstance(data, list) else tuple(drained)
    if isinstance(data, str):
        stripped = data.strip()
        if _SECRET_VALUE_RE.match(stripped):
            # 整串命中：Bearer 分支同样过判别（纯英文短词不掩码），sk-/长随机串维持高置信
            if not (stripped.startswith("Bearer") and not _is_bearer_like(stripped[6:].strip())):
                return _mask_value(stripped)
        if _MYSQL_URI_RE.search(data):
            data = _MYSQL_URI_RE.sub(lambda m: f"{m.group(1)}****{m.group(3)}", data)
        if _SECRET_SUB_RE.search(data):
            return _SECRET_SUB_RE.sub(_mask_substring_match, data)
        return data
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
