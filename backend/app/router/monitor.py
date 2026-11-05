"""监控面板接口（监控页使用，需登录）

- 对话数据：全站累计 token、对话记录分页（管理员可看全部用户）
- 调用日志：logs 表分页筛选（管理员看全部，普通用户只看自己）
- 数据看板：当前用户时间范围内的用量累计与分桶序列（走预聚合表，无全量求和）

对话记录长度阈值已迁移至控制台-设置页（GET/PUT /admin/settings），本路由不再提供
"""

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.crud import chat_record as chat_crud
from app.crud import log as log_crud
from app.crud import usage_stats as stats_crud
from app.router.deps import get_db
from app.utils.auth import get_current_admin, get_current_user
from app.utils.response import success_response

router = APIRouter(prefix="/monitor", tags=["Monitor"])


def _chat_dict(row: dict) -> dict:
    """chat_record 行转驼峰字典（inputContent 已在 CRUD 层还原为 messages 数组）"""
    return {
        "id": row["id"],
        "userId": row["user_id"],
        "username": row["username"],
        "modelName": row["model_name"],
        "channelName": row["channel_name"],
        "inputContent": row["input_content"],
        "reasoningContent": row["reasoning_content"],
        "outputContent": row["output_content"],
        "promptTokens": row["prompt_tokens"],
        "completionTokens": row["completion_tokens"],
        "cacheTokens": row["cache_tokens"],
        "cost": float(row["cost"] or 0),
        "durationMs": row["duration_ms"],
        "createTime": row["create_time"],
    }


def _log_dict(row: dict) -> dict:
    """logs 行转驼峰字典"""
    return {
        "id": row["id"],
        "type": row["type"],
        "userId": row["user_id"],
        "username": row["username"],
        "action": row["action"],
        "detail": row["detail"],
        "modelName": row["model_name"],
        "channelName": row["channel_name"],
        "promptTokens": row["prompt_tokens"],
        "completionTokens": row["completion_tokens"],
        "cacheTokens": row["cache_tokens"],
        "cost": float(row["cost"] or 0),
        "durationMs": row["duration_ms"],
        "createTime": row["create_time"],
    }


def _normalize_page(page: int, pageSize: int) -> tuple[int, int]:
    """归一化分页参数"""
    if page < 1:
        page = 1
    if pageSize < 1 or pageSize > 100:
        pageSize = 10
    return page, pageSize


@router.get("/summary")
async def get_site_summary(db: AsyncSession = Depends(get_db), user=Depends(get_current_user)):
    """全站累计用量（读 usage_summary 单行，O(1) 无聚合计算）"""
    summary = await stats_crud.get_summary(db)
    data = {
        "calls": summary["calls"],
        "promptTokens": summary["prompt_tokens"],
        "completionTokens": summary["completion_tokens"],
        "cacheTokens": summary["cache_tokens"],
    }
    return success_response(message="获取全站用量成功", data=data)


@router.get("/chats")
async def list_chat_records(
        page: int = 1,
        pageSize: int = 10,
        model: str = "",
        username: str = "",
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """
    分页查询对话记录：管理员可查全部用户（可按用户名模糊筛选），普通用户只看自己。

    :param model: 模型名精确筛选
    :param username: 用户名模糊筛选（仅管理员生效）
    """
    page, pageSize = _normalize_page(page, pageSize)
    records, total = await chat_crud.list_records(
        db,
        user_id=None if user.is_admin else user.id,
        username_keyword=username.strip() if user.is_admin else "",
        model_name=model.strip(),
        page=page, page_size=pageSize,
    )
    data = {"list": [_chat_dict(r) for r in records], "total": total}
    return success_response(message="获取对话记录成功", data=data)


@router.get("/logs")
async def list_logs(
        page: int = 1,
        pageSize: int = 10,
        type: str = "",
        keyword: str = "",
        model: str = "",
        start: datetime | None = None,
        end: datetime | None = None,
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """
    分页查询系统日志：管理员看全部用户的日志，普通用户只看自己的。

    :param type: 日志类型筛选（api / login / admin / user）
    :param keyword: 用户名 / 动作 / 详情 模糊搜索
    :param start / end: 时间范围，闭开区间 [start, end)
    """
    page, pageSize = _normalize_page(page, pageSize)
    logs, total = await log_crud.query_logs(
        db,
        user_id=None if user.is_admin else user.id,
        log_type=type.strip(),
        keyword=keyword.strip(),
        model_name=model.strip(),
        start=start,
        end=end,
        page=page, page_size=pageSize,
    )
    data = {"list": [_log_dict(r) for r in logs], "total": total}
    return success_response(message="获取日志成功", data=data)


@router.get("/stats")
async def get_user_stats(
        start: datetime,
        end: datetime,
        granularity: str = "day",
        db: AsyncSession = Depends(get_db),
        user=Depends(get_current_user),
):
    """
    当前用户在 [start, end) 内的用量：范围累计 + 按粒度分桶的每模型序列。
    前端按桶把各模型相加即可得到"总计"曲线，无需额外请求。
    """
    if granularity not in stats_crud.GRANULARITIES:
        raise HTTPException(status_code=400, detail=f"granularity 只能是 {' / '.join(stats_crud.GRANULARITIES)}")
    if start >= end:
        raise HTTPException(status_code=400, detail="start 必须早于 end")
    # 限制桶数量，防止"小时粒度查一年"这类请求拖垮聚合查询
    span_hours = (end - start).total_seconds() / 3600
    max_hours = {"hour": 24 * 62, "day": 24 * 3650, "week": 24 * 3650 * 7, "month": 24 * 3650 * 31}
    if span_hours > max_hours[granularity]:
        raise HTTPException(status_code=400, detail="时间范围过大，请缩短范围或换用更粗的粒度")

    totals = await stats_crud.query_user_totals(db, user_id=user.id, start=start, end=end)
    buckets = await stats_crud.query_user_series(db, user_id=user.id, start=start, end=end, granularity=granularity)
    data = {
        "totals": {
            "calls": totals["calls"],
            "promptTokens": totals["prompt_tokens"],
            "completionTokens": totals["completion_tokens"],
            "cacheTokens": totals["cache_tokens"],
        },
        "buckets": [
            {
                "time": b["bucket"],
                "modelName": b["model_name"],
                "calls": b["calls"],
                "promptTokens": b["prompt_tokens"],
                "completionTokens": b["completion_tokens"],
                "cacheTokens": b["cache_tokens"],
            }
            for b in buckets
        ],
    }
    return success_response(message="获取用量统计成功", data=data)
