# -*- coding: utf-8 -*-
"""补新赛事积分榜(欧冠/英冠/荷甲/葡超/巴甲) —— football-data 免费

用法: python scripts/backfill_extra_standings.py
"""
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.football_data_api import FootballDataClient, _match_team  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")

COMPS = {"CL": "欧冠", "ELC": "英冠", "DED": "荷甲", "PPL": "葡超", "BSA": "巴甲"}
SEASON_CODE = "2627"
API_SEASON = 2026


def main():
    client = FootballDataClient()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS standings (
        id INTEGER PRIMARY KEY AUTOINCREMENT, league_id INTEGER, season TEXT,
        team_id INTEGER, rank INTEGER, played INTEGER, won INTEGER, draw INTEGER,
        lost INTEGER, goals_for INTEGER, goals_against INTEGER, goal_diff INTEGER,
        points INTEGER, form TEXT, updated_at TEXT)""")

    lg_map = {r["name"]: r["league_id"] for r in
              conn.execute("SELECT league_id, name FROM leagues")}
    total = 0
    for code, cn in COMPS.items():
        lid = lg_map.get(cn)
        if not lid:
            print(f"跳过 {cn}(库内无该联赛行)")
            continue
        try:
            table = client.get_standings(code, season=API_SEASON)
        except Exception as e:
            print(f"{cn}({code}) 拉取失败: {str(e)[:60]}")
            time.sleep(7)
            continue
        time.sleep(7)                     # 免费档 10 次/分钟
        if not table:
            print(f"{cn}({code}): 无数据")
            continue
        conn.execute("DELETE FROM standings WHERE league_id=? AND season=?",
                     (lid, SEASON_CODE))
        for row in table:
            team = row.get("team", {}) or {}
            name = team.get("shortName") or team.get("name")
            if not name:
                continue
            tid = _match_team(conn, lid, name, team.get("name"))
            conn.execute("""
                INSERT INTO standings (league_id, season, team_id, rank, played, won,
                    draw, lost, goals_for, goals_against, goal_diff, points, form, updated_at)
                VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (lid, SEASON_CODE, tid, row.get("position"),
                 row.get("playedGames", 0), row.get("won", 0), row.get("draw", 0),
                 row.get("lost", 0), row.get("goalsFor", 0), row.get("goalsAgainst", 0),
                 row.get("goalDifference", 0), row.get("points", 0), row.get("form"),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        total += len(table)
        print(f"✓ {cn}({code}): {len(table)} 行")

    print(f"\n合计写入 {total} 行")
    print("库内积分榜分布:")
    for r in conn.execute("""SELECT l.name, s.season, COUNT(*) n FROM standings s
                             JOIN leagues l ON l.league_id=s.league_id
                             GROUP BY s.league_id, s.season ORDER BY l.league_id"""):
        print(f"  {r['name']:<5} {r['season']}: {r['n']} 行")
    conn.close()


if __name__ == "__main__":
    main()
