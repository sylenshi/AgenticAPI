"""上游运维业务编排"""

import json

from app.core.config import (
    DATA_DIR,
    antigravity_ops_setting,
    zai_ops_setting,
)
from app.services.upstream import antigravity, stepfun, volcengine, zai
from app.utils.token_utils import get_token_expiry

OPS_JSON_PATH = DATA_DIR / "operations_config.json"
RESPONSE_DATA_DIR = DATA_DIR / "response_data"


def _load_ops_config() -> dict:
    """读取运维凭证配置"""
    with open(OPS_JSON_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_raw(name: str, data) -> None:
    """持久化保存此次请求结果，以供调试"""
    RESPONSE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    with open(RESPONSE_DATA_DIR / f"{name}_data.json", "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def get_operations(refresh_channel: str = "all") -> dict:
    """
    获取上游运维数据
    :param refresh_channel: 刷新的渠道，可选值为 "vol"、"stepfun"、"zai2"、"antigravity" 或 "all"
    """
    re_dict = {
        "status": {},
        "token_expiry": {},
        "vol_usage": {},
        "stepfun_usage": {},
        "zai2_usage": {},
        "antigravity_usage": {},
    }

    operation_dict = _load_ops_config()

    # 智谱（v2 套餐）的 API key：控制台"设置凭证"上传的 JSON 值优先，.env 兜底
    operation_dict["ZAI_API_KEY_2"] = (
            operation_dict.get("zai_api_key") or zai_ops_setting.ZAI_API_KEY_2
    )

    # Antigravity 的凭证在 .env（sub2api 管理员账号，登录换 JWT 查双池限额）
    operation_dict["antigravity_base_url"] = antigravity_ops_setting.ANTIGRAVITY_BASE_URL
    operation_dict["antigravity_admin_email"] = antigravity_ops_setting.ANTIGRAVITY_ADMIN_EMAIL
    operation_dict["antigravity_admin_password"] = antigravity_ops_setting.ANTIGRAVITY_ADMIN_PASSWORD
    operation_dict["antigravity_account_ids"] = antigravity_ops_setting.ANTIGRAVITY_ACCOUNT_IDS

    # 【1】火山方舟 Token Plan 用量
    if refresh_channel in ("vol", "all"):
        result = volcengine.fetch_vol_usage(operation_dict)
        re_dict["status"]["vol"] = result["status"]
        re_dict["vol_usage"] = result["usage"]
        if result["raw"] is not None:
            _save_raw("vol", result["raw"])

    # 【2】阶跃星辰 Step Plan 用量
    if refresh_channel in ("stepfun", "all"):
        result, current_token = stepfun.fetch_stepfun_usage(operation_dict, OPS_JSON_PATH)
        # 显式更新内存中的 token，确保后续 get_token_expiry 读到最新值
        operation_dict["stepfun_token"] = current_token
        re_dict["status"]["stepfun"] = result["status"]
        re_dict["stepfun_usage"] = result["usage"]
        if result["raw"] is not None:
            _save_raw("stepfun", result["raw"])

    # 【3】智谱 GLM Coding Plan 用量（v2 套餐，凭证为上传的 zai_api_key 或 .env 兜底）
    if refresh_channel in ("zai2", "all"):
        result = zai.fetch_zai_usage(operation_dict, token_key="ZAI_API_KEY_2")
        re_dict["status"]["zai2"] = result["status"]
        re_dict["zai2_usage"] = result["usage"]
        if result["raw"] is not None:
            _save_raw("zai2", result["raw"])

    # 【4】Antigravity（Gemini PRO）限额（数据源为本机 sub2api 容器的管理端 API，8080）。
    # sub2api 服务端自带 3 分钟缓存（上游失败负缓存 1 分钟），查询通常秒级返回，
    # 不再区分实时/缓存双速，单卡刷新与 "all" 走同一条路径。
    if refresh_channel in ("antigravity", "all"):
        result = antigravity.fetch_antigravity_usage(operation_dict)
        re_dict["status"]["antigravity"] = result["status"]
        re_dict["antigravity_usage"] = result["usage"]
        if result["raw"] is not None:
            _save_raw("antigravity", result["raw"])

    # 获取 token 过期时间
    re_dict["token_expiry"] = get_token_expiry(operation_dict)
    return re_dict


def upload_settings(
        brm_token: str,
        instance_id: str,
        step_token: str,
        step_webid: str,
        zai_api_key: str,
) -> dict:
    """更新上游运维凭证到 operations_config.json"""
    try:
        with open(OPS_JSON_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = {}  # 文件不存在 -> 装载空字典
        data["version"] = 1
        data["note"] = "TokenPlan 监控面板密钥存储文件。包含敏感登录态（Token/Cookie），请勿提交到 git/分享给他人。"

    # 长度大于5才可能是有效数据
    message = ""
    if len(brm_token) > 5:
        data["bohrclaw_token"] = brm_token
        message = message + "bohrclaw token已更新；"
    if len(instance_id) > 5:
        data["bohrclaw_instance"] = instance_id
        message = message + "bohr instance id已更新；"
    if len(step_token) > 5:
        data["stepfun_token"] = step_token
        message = message + "stepfun token已更新；"
    if len(step_webid) > 5:
        data["stepfun_webid"] = step_webid
        message = message + "stepfun webid已更新；"
    if len(zai_api_key) > 5:
        data["zai_api_key"] = zai_api_key
        message = message + "zai api key已更新；"

    # 保存文件
    with open(OPS_JSON_PATH, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=4, ensure_ascii=False)

    return {"message": message}
