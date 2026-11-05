"""JWT / Token 解析工具"""

import base64
import json
from datetime import datetime


def decode_jwt_payload(token: str) -> dict:
    """解码 JWT 的 payload 部分（第二段），失败返回空 dict"""
    try:
        payload_b64 = token.split(".")[1]
        payload_b64 += "=" * (4 - len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(payload_b64).decode())
    except Exception:
        return {}


def get_token_expiry(operation_dict: dict) -> dict:
    """
    获取3个渠道的token/凭证过期时间
    返回格式：{"volcengine": "...", "stepfun": "...", "zai2": "..."}
    """
    expiry_dict = {}

    # 【1】火山方舟（凭证为深势 BohrClaw 平台的 JWT，查询走其接口）
    vol_token = operation_dict.get("bohrclaw_token", "")
    payload = decode_jwt_payload(vol_token)
    exp = payload.get("exp")
    if exp:
        exp_dt = datetime.fromtimestamp(exp).isoformat()
        expiry_dict["volcengine"] = exp_dt
    else:
        expiry_dict["volcengine"] = None

    # 【2】阶跃星辰（access_token...refresh_token 格式，返回 refresh_token 的过期时间）
    step_token = operation_dict.get("stepfun_token", "")
    try:
        refresh_token = step_token.split("...")[1]
        payload = decode_jwt_payload(refresh_token)
        exp = payload.get("exp")
        expiry_dict["stepfun"] = datetime.fromtimestamp(exp).isoformat() if exp else None
    except Exception:
        expiry_dict["stepfun"] = None

    # 【3】智谱（ZAI_API_KEY_2，非 JWT 且长期有效，恒返回 None）
    zai2_payload = decode_jwt_payload(operation_dict.get("ZAI_API_KEY_2", ""))
    exp = zai2_payload.get("exp")
    expiry_dict["zai2"] = datetime.fromtimestamp(exp).isoformat() if exp else None

    return expiry_dict
