"""智能问答接口（RAG 阶段 1）—— 自然语言问题 → 库内事实 + 可溯源答案。

挂在 /api/ui 前缀下, 复用界面接口的登录闸门（未登录 401）:
    POST /api/ui/ask          {"question": "皇马和巴萨谁赢", "top_k": 5, "use_llm": true}
    GET  /api/ui/ask/status   能力与模式（是否已配 LLM key、有哪些工具、索引规模）

没有 LLM_API_KEY 时不报错: 返回 mode="retrieval" 的检索摘要（见 src/qa/orchestrator.py）。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from src.api.ui import require_ui_login
from src.qa import orchestrator
from src.search.query import IndexMissing

router = APIRouter(dependencies=[Depends(require_ui_login)])


class AskBody(BaseModel):
    question: str = Field("", description="自然语言问题, 例如「皇马和巴萨谁赢」「英超积分榜」")
    top_k: int = Field(5, ge=1, le=20, description="检索片段条数")
    use_llm: bool = Field(True, description="是否调用大模型（没有 key 时自动降级为检索摘要）")
    kind: str | None = Field(None, description="限定检索类型: league/team/player/match/prediction/doc")


@router.post("/ask", summary="智能问答: 意图识别 + 查库/检索 + 带引用作答")
def ask(body: AskBody):
    return orchestrator.ask(body.question, top_k=body.top_k, use_llm=body.use_llm, kind=body.kind)


@router.get("/ask", summary="智能问答（GET 便于 curl 调试）")
def ask_get(
    q: str = Query("", description="自然语言问题"),
    top_k: int = Query(5, ge=1, le=20),
    use_llm: bool = Query(True),
    kind: str | None = Query(None),
):
    return orchestrator.ask(q, top_k=top_k, use_llm=use_llm, kind=kind)


@router.get("/ask/status", summary="问答能力状态（是否配置 LLM / 工具清单 / 索引规模）")
def status():
    try:
        return orchestrator.status()
    except IndexMissing as e:  # 索引缺失不该让状态接口 500
        return {"llm_ready": False, "detail": str(e)}
