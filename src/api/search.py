"""检索接口 —— RAG 阶段 0: 自然语言/关键词落到真实数据, 每条结果带出处。

挂在 /api/ui 前缀下, 复用界面接口的登录闸门(未登录返回 401):
    GET /api/ui/search?q=皇马逆转&kind=match&limit=5
    GET /api/ui/search/stats
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from src.api.ui import require_ui_login
from src.search.query import IndexMissing, search as _search, try_stats

router = APIRouter(dependencies=[Depends(require_ui_login)])


@router.get("/search", summary="全文检索: 比赛 / 球队 / 球员 / 预测 / 文档")
def search(
    q: str = Query("", description="自然语言问题或关键词, 例如: 皇家马德里 逆转"),
    kind: str = Query("", description="限定类型: league/team/player/match/prediction/doc"),
    limit: int = Query(10, ge=1, le=50),
    offset: int = Query(0, ge=0),
):
    try:
        return _search(q, kind=kind or None, limit=limit, offset=offset)
    except IndexMissing as e:
        raise HTTPException(status_code=503, detail=str(e))


@router.get("/search/stats", summary="检索索引统计(语料规模 / 分词模式 / 构建时间)")
def stats():
    return try_stats()
