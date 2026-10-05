"""API路由 - 球队"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Optional
from src.database.crud import get_db, get_team_by_name, get_teams_by_league
from src.analysis.team_stats import TeamStats
from src.analysis.elo_rating import EloRating
import pandas as pd

router = APIRouter()


@router.get("/search")
async def search_team(name: str, db: Session = Depends(get_db)):
    """搜索球队"""
    team = get_team_by_name(db, name)
    if not team:
        raise HTTPException(status_code=404, detail=f"未找到球队: {name}")
    return {"id": team.team_id, "name": team.name, "name_en": team.name_en,
            "league_id": team.league_id, "manager": team.manager,
            "stadium": team.stadium, "elo_rating": team.elo_rating}


@router.get("/league/{league_id}")
async def list_teams_by_league(league_id: int, db: Session = Depends(get_db)):
    """获取联赛下所有球队"""
    teams = get_teams_by_league(db, league_id)
    return [{"id": t.team_id, "name": t.name, "short_name": t.short_name,
             "elo_rating": t.elo_rating} for t in teams]


@router.get("/{team_name}/form")
async def team_recent_form(team_name: str, matches: int = 10,
                           db: Session = Depends(get_db)):
    """球队近期战绩(真实数据, 供 UI 的"近 N 场走势"使用)

    返回: 每场结果(W/D/L)、比分、对手、日期, 以及汇总统计
    """
    import sqlite3
    from pathlib import Path
    dbp = Path(__file__).resolve().parent.parent.parent / "data" / "database" / "football.db"
    con = sqlite3.connect(str(dbp))
    con.row_factory = sqlite3.Row
    t = con.execute("SELECT team_id, name, elo_rating, stadium, capacity, founded, "
                    "manager, logo_url FROM teams WHERE name=?", (team_name,)).fetchone()
    if not t:
        con.close()
        raise HTTPException(status_code=404, detail=f"未找到球队: {team_name}")
    rows = con.execute("""
        SELECT date(m.date) d, l.name AS league,
               th.name AS home, ta.name AS away,
               m.home_goals hg, m.away_goals ag,
               CASE WHEN m.home_team_id=? THEN 'H' ELSE 'A' END AS venue
        FROM matches m
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        LEFT JOIN leagues l ON l.league_id = m.league_id
        WHERE (m.home_team_id=? OR m.away_team_id=?) AND m.status='FT'
              AND m.home_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?""",
        (t["team_id"], t["team_id"], t["team_id"], int(matches))).fetchall()
    con.close()

    games, w = [], 0
    d = l_ = 0
    for r in rows:
        if r["venue"] == "H":
            gf, ga = r["hg"], r["ag"]
        else:
            gf, ga = r["ag"], r["hg"]
        res = "W" if gf > ga else ("D" if gf == ga else "L")
        w += res == "W"
        d += res == "D"
        l_ += res == "L"
        games.append({"date": r["d"], "league": r["league"], "home": r["home"],
                      "away": r["away"], "score": f"{r['hg']}-{r['ag']}",
                      "venue": r["venue"], "result": res, "gf": gf, "ga": ga})
    form = "".join(g["result"] for g in games)
    return {"team": t["name"], "team_id": t["team_id"], "elo_rating": t["elo_rating"],
            "stadium": t["stadium"], "capacity": t["capacity"], "founded": t["founded"],
            "manager": t["manager"], "logo_url": t["logo_url"],
            "matches": len(games), "won": w, "drawn": d, "lost": l_,
            "goals_for": sum(g["gf"] for g in games),
            "goals_against": sum(g["ga"] for g in games),
            "form": form, "games": games}


@router.get("/{team_name}/players")
async def team_players(team_name: str, db: Session = Depends(get_db)):
    """获取球队球员列表"""
    team = get_team_by_name(db, team_name)
    if not team:
        raise HTTPException(status_code=404, detail="球队不存在")
    players = team.players
    return [{"id": p.player_id, "name": p.name, "position": p.position,
             "number": p.number, "nationality": p.nationality,
             "market_value": p.market_value} for p in players]
