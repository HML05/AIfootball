"""API路由 - 比赛"""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from typing import Optional
from datetime import datetime, timedelta
from src.database.crud import (get_db, get_matches_by_league_season,
                                 get_upcoming_matches, create_match)

router = APIRouter()


@router.get("/league/{league_id}/season/{season}")
async def list_matches(league_id: int, season: str, db: Session = Depends(get_db)):
    """获取联赛赛季所有比赛"""
    matches = get_matches_by_league_season(db, league_id, season)
    return [{"id": m.match_id, "date": m.date.isoformat() if m.date else None,
             "home_team": m.home_team.name if m.home_team else None,
             "away_team": m.away_team.name if m.away_team else None,
             "home_goals": m.home_goals, "away_goals": m.away_goals,
             "status": m.status, "matchday": m.matchday} for m in matches]


@router.get("/upcoming")
async def upcoming_matches(league_id: Optional[int] = None,
                           days: int = Query(7, ge=1, le=30),
                           db: Session = Depends(get_db)):
    """获取未来N天的赛程"""
    matches = get_upcoming_matches(db, league_id, days)
    return [{"id": m.match_id, "date": m.date.isoformat() if m.date else None,
             "home_team": m.home_team.name if m.home_team else None,
             "away_team": m.away_team.name if m.away_team else None,
             "status": m.status} for m in matches]


@router.get("/live")
async def live_scores():
    """获取实时比分（从API-Football获取）"""
    return {"note": "调用 ApiFootball.get_live_scores() 获取实时比分",
            "status": "需要配置API_FOOTBALL_KEY"}
