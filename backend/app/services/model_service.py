"""模型业务逻辑层"""

import json
import time
from fastapi import HTTPException
import httpx
from sqlalchemy.ext.asyncio import AsyncSession
from app.crud import channel as channel_crud
from app.crud import model as model_crud
from app.models.user import UserTabel
from app.schemas.model import ModelSchema
from app.utils.json_utils import parse_json_list
from app.crud import user as user_crud
from app.core.config import server_setting


async def _validate_channels(db: AsyncSession, names: list[str]) -> None:
    """校验 channels 中的每个渠道名都存在于 llm_channels 表"""
    if not names:
        return
    valid = await channel_crud.get_existing_names(db, names)
    invalid = [n for n in names if n not in valid]
    if invalid:
        raise HTTPException(status_code=400, detail=f"以下渠道不存在: {invalid}")


async def list_models(db: AsyncSession) -> list[dict]:
    """获取全量模型列表，channels 解析为真正的数组返回前端"""
    models = await model_crud.get_all(db)
    result = []
    for model in models:
        d = dict(model)
        d["channels"] = parse_json_list(d.get("channels"))
        result.append(ModelSchema(**d).model_dump(by_alias=True, mode="json"))
    return result


async def create_model(db: AsyncSession, new_model: ModelSchema) -> int:
    """添加单个模型，返回新增记录的自增主键 id

    业务错误（模型名重复、渠道不存在等）抛 HTTPException，由全局异常处理器统一格式化；
    数据库错误抛 SQLAlchemyError，同样由全局异常处理器捕获，
    回滚交由 get_db 依赖的 except 分支完成，这里无需 try/except。
    """
    model = new_model.model_dump()

    # upstream_name 入库前去首尾空白：只允许真名或空，纯空白视为未配置
    if model.get("upstream_name") is not None:
        model["upstream_name"] = model["upstream_name"].strip()

    # 插入前检查 name 是否已存在，避免数据库抛唯一性异常导致 500
    if await model_crud.get_id_by_name(db, model["name"]):
        raise HTTPException(status_code=400, detail=f"模型 '{model['name']}' 已存在")

    # NOT NULL 列的入库默认值（crud 层用原生 SQL 插入，ORM 的 default 不会生效）
    if not model.get("label"):
        model["label"] = model["name"]
    model["model_group"] = model.get("model_group") or "free"
    for price in ("per_request_price", "input_price", "cache_price", "output_price"):
        if model.get(price) is None:
            model[price] = 0
    for flag in ("is_request_mode", "is_pin", "is_log", "support_vision"):
        if model.get(flag) is None:
            model[flag] = False
    if model.get("status") is None:
        model["status"] = True

    # channels：校验渠道是否都存在，再把数组序列化为 JSON 字符串存库
    if model.get("channels") is not None:
        await _validate_channels(db, model["channels"])
        model["channels"] = json.dumps(model["channels"], ensure_ascii=False)

    res_id = await model_crud.insert(db, model)
    await db.commit()

    if not res_id:
        raise HTTPException(status_code=500, detail="添加模型失败")
    return res_id


async def update_model(db: AsyncSession, model_name: str, update_data: ModelSchema) -> None:
    """更新单个模型数据（按 name 定位，name 本身不能更新）"""
    if not model_name or not model_name.strip():
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    model_name = model_name.strip()

    if not await model_crud.get_id_by_name(db, model_name):
        raise HTTPException(status_code=404, detail=f"模型 '{model_name}' 不存在")

    # 过滤掉未传字段，同时排除 name 字段（定位键不可更新）
    update_dict = update_data.model_dump(exclude_unset=True, exclude={"name"})
    if not update_dict:
        raise HTTPException(status_code=400, detail="未提供任何需要更新的字段")

    # upstream_name 入库前去首尾空白：只允许真名或空，纯空白视为未配置
    if "upstream_name" in update_dict and update_dict["upstream_name"] is not None:
        update_dict["upstream_name"] = update_dict["upstream_name"].strip()

    # channels：校验渠道是否都存在，再把数组序列化为 JSON 字符串存库
    if "channels" in update_dict and update_dict["channels"] is not None:
        await _validate_channels(db, update_dict["channels"])
        update_dict["channels"] = json.dumps(update_dict["channels"], ensure_ascii=False)

    await model_crud.update_by_name(db, model_name, update_dict)
    await db.commit()


async def remove_model(db: AsyncSession, model_name: str) -> None:
    """删除模型"""
    if not model_name or not model_name.strip():
        raise HTTPException(status_code=400, detail="模型名称不能为空")
    model_name = model_name.strip()

    if not await model_crud.get_id_by_name(db, model_name):
        raise HTTPException(status_code=404, detail=f"模型名称 '{model_name}' 不存在")

    rowcount = await model_crud.delete_by_name(db, model_name)
    await db.commit()

    if rowcount == 0:
        raise HTTPException(status_code=500, detail="删除模型失败，未影响任何记录")


# 拨测每用户冷却（内存频控，单进程部署下有效）：拨测是真实上游调用，防无限触发
PROBE_COOLDOWN_SECONDS = 60
_probe_last_ts: dict[int, float] = {}


async def test_model(db: AsyncSession, model_name: str, user: UserTabel) -> dict:
    """
    模型拨测：走本站对外中转接口，与真实调用方同链路（正常计费、记录日志）。
    地址取自 backend/.env 的 PUBLIC_BASE_URL，部署到公网后无需改代码。

    分组权限前置校验（与中转一致）：free 分组模型人人可拨，vip 分组模型仅 vip
    用户可拨——避免把无权调用伪装成"渠道异常"返回给用户。
    """
    model = await model_crud.get_by_name(db, model_name)
    if not model or not model.get("status"):
        raise HTTPException(status_code=404, detail=f"模型 {model_name} 不存在或已停用")
    if model.get("model_group") != "free" and user.user_group != "vip":
        raise HTTPException(status_code=403, detail=f"当前用户分组（{user.user_group}）无权拨测模型 {model_name}")

    api_key = await user_crud.get_api_key_by_user_id(db, user.id)
    if not api_key:
        raise HTTPException(status_code=400, detail="用户未绑定API密钥")

    # 冷却检查在真正发起上游调用前：失败/成功都计一次，防止拿拨测当免费生成接口刷
    now_ts = time.time()
    last_ts = _probe_last_ts.get(user.id)
    if last_ts is not None and now_ts - last_ts < PROBE_COOLDOWN_SECONDS:
        raise HTTPException(status_code=429, detail=f"拨测过于频繁，请 {PROBE_COOLDOWN_SECONDS} 秒后再试")
    _probe_last_ts[user.id] = now_ts

    url = f"{server_setting.RELAY_BASE_URL}/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key.key}",
        "Content-Type": "application/json",
    }
    payload = {
        "model": model_name,
        "messages": [
            {"role": "user", "content": "请简单回复'OK'"}
        ],
        # 拨测只验通不通，限制输出长度控制成本（推理模型的思考 token 也计入该上限）
        "max_tokens": 512,
        "stream": False
    }

    # 超时与渠道侧配置（timeout=180s）对齐：慢模型（长思考/长排队）不至于被拨测误报
    start = time.perf_counter()
    try:
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(url, headers=headers, json=payload)
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"模型拨测失败: {e.__class__.__name__}")
    latency_ms = int((time.perf_counter() - start) * 1000)

    if response.status_code != 200:
        # 提取中转/上游的错误信息（OpenAI 格式 {"error":{"message"}}），
        # 让 402 余额不足、上游 4xx 等真实原因直接呈现，而不是笼统的"渠道异常"
        detail = f"模型响应失败（HTTP {response.status_code}）"
        try:
            err = (response.json() or {}).get("error") or {}
            if err.get("message"):
                detail = f"{detail}：{err['message']}"
        except Exception:
            pass
        raise HTTPException(status_code=502, detail=detail)

    # 解析出回复摘要与耗时，供前端在卡片上直观展示拨测结果
    data = response.json()
    reply = ""
    choices = data.get("choices") or []
    if choices and isinstance(choices[0], dict):
        reply = (choices[0].get("message") or {}).get("content") or ""
    return {
        "ok": True,
        "model": model_name,
        "latencyMs": latency_ms,
        "reply": str(reply).strip()[:50],
    }
