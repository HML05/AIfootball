"""API路由 - AI Agent对话"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import Optional
import pandas as pd

router = APIRouter()

# 全局Agent实例
_agent = None


class ChatRequest(BaseModel):
    message: str
    session_id: Optional[str] = None


class MatchAnalysisRequest(BaseModel):
    home_team: str
    away_team: str


@router.post("/chat")
async def agent_chat(req: ChatRequest):
    """与AI Agent对话"""
    global _agent
    if _agent is None:
        raise HTTPException(status_code=503,
            detail="AI Agent未初始化，请先配置LLM API密钥并启动Agent")
    try:
        response = _agent.chat(req.message)
        return {"response": response, "session_id": req.session_id}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Agent错误: {str(e)}")


@router.post("/analyze-match")
async def analyze_match(req: MatchAnalysisRequest):
    """深度分析一场比赛"""
    global _agent
    if _agent is None:
        raise HTTPException(status_code=503, detail="AI Agent未初始化")
    try:
        response = _agent.analyze_match(req.home_team, req.away_team)
        return {"home_team": req.home_team, "away_team": req.away_team,
                "analysis": response}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/clear-memory")
async def clear_memory():
    """清除Agent对话记忆"""
    global _agent
    if _agent:
        _agent.clear_memory()
        return {"status": "success", "message": "对话记忆已清除"}
    return {"status": "no_agent"}
