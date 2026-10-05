"""API路由 - 联赛"""
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from src.database.crud import get_db, get_all_leagues, create_league
from src.database.models import League
from pydantic import BaseModel

router = APIRouter()


class LeagueCreate(BaseModel):
    name: str
    name_en: str = ""
    country: str = ""
    season: str = ""
    logo_url: str = ""


@router.get("/", response_model=List[dict])
async def list_leagues(db: Session = Depends(get_db)):
    """获取所有联赛"""
    leagues = get_all_leagues(db)
    return [{"id": l.league_id, "name": l.name, "name_en": l.name_en,
             "country": l.country, "season": l.season} for l in leagues]


@router.post("/")
async def add_league(league: LeagueCreate, db: Session = Depends(get_db)):
    """添加联赛"""
    new_league = create_league(db, **league.dict())
    return {"id": new_league.league_id, "name": new_league.name}
