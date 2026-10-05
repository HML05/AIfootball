# -*- coding: utf-8 -*-
"""从 Understat 抓取五大联赛【每场官方 xG】并回填我们的 matches 表

数据来源: https://understat.com/main/getLeagueData/{league}/{season}  (免费, 无需 key)

用法:
    python scripts/import_understat_xg.py                 # 2021~2026 六个赛季
    python scripts/import_understat_xg.py --seasons 2024,2025
"""
import argparse
import os
import re
import sqlite3
import sys
import time
import unicodedata
from collections import defaultdict
from pathlib import Path

import requests

BASE = Path(__file__).parent.parent
DB = BASE / "data" / "database" / "football.db"
sys.path.insert(0, str(BASE))

H = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
     "X-Requested-With": "XMLHttpRequest"}
# Understat 联赛名 -> 我们的 league_id
UNDERSTAT = {"EPL": 1, "La_liga": 2, "Bundesliga": 3, "Serie_A": 4, "Ligue_1": 5}
# 赛季起始年 -> 我们的赛季码
SEASON_CODE = {2016: "1617", 2017: "1718", 2018: "1819", 2019: "1920", 2020: "2021",
               2021: "2122", 2022: "2223", 2023: "2324", 2024: "2425", 2025: "2526",
               2026: "2627"}

# Understat 全名 -> 我们库里的简称(名字差异较大者)
ALIAS = {
    "Manchester City": "Man City", "Manchester United": "Man United",
    "Wolverhampton Wanderers": "Wolves", "Nottingham Forest": "Nott'm Forest",
    "Brighton and Hove Albion": "Brighton", "Brighton & Hove Albion": "Brighton",
    "Tottenham Hotspur": "Tottenham", "West Ham United": "West Ham",
    "Newcastle United": "Newcastle", "Sheffield United": "Sheffield Utd",
    "Sheffield Wednesday": "Sheffield Wed", "Leeds United": "Leeds",
    "Hull City": "Hull", "Queens Park Rangers": "Qpr",
    "West Bromwich Albion": "West Brom", "Ipswich Town": "Ipswich",
    "Coventry City": "Coventry", "Norwich City": "Norwich",
    "Cardiff City": "Cardiff", "Swansea City": "Swansea",
    "Borussia Monchengladbach": "M'gladbach", "Borussia M.Gladbach": "M'gladbach",
    "Eintracht Frankfurt": "Ein Frankfurt", "Bayer Leverkusen": "Leverkusen",
    "VfB Stuttgart": "Stuttgart", "Borussia Dortmund": "Dortmund",
    "1899 Hoffenheim": "Hoffenheim", "TSG Hoffenheim": "Hoffenheim",
    "1. FC Koln": "FC Koln", "FC Cologne": "FC Koln", "FC Schalke 04": "Schalke 04",
    "Atletico Madrid": "Ath Madrid", "Athletic Club": "Ath Bilbao",
    "Real Betis": "Betis", "Real Sociedad": "Sociedad", "Celta Vigo": "Celta",
    "Deportivo La Coruna": "La Coruna", "RCD Espanyol": "Espanol",
    "Rayo Vallecano": "Vallecano", "Racing Santander": "Santander",
    "Paris Saint Germain": "Paris SG", "Paris Saint-Germain": "Paris SG",
    "Espanyol": "Espanol", "Hamburger SV": "Hamburg",
    "Greuther Fuerth": "Greuther Furth", "Saint-Etienne": "Saint-Etienne",
    "Olympique Lyonnais": "Lyon", "Olympique Marseille": "Marseille",
    "Stade Rennais": "Rennes", "Lille OSC": "Lille", "AS Monaco": "Monaco",
    "Inter": "Inter", "Internazionale": "Inter", "AC Milan": "Milan",
    "AS Roma": "Roma", "SSC Napoli": "Napoli", "Hellas Verona": "Verona",
}


def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def tokens(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    s = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in s.lower())
    drop = {"fc", "cf", "sc", "afc", "ac", "cd", "ud", "ss", "us", "as", "rc", "cn",
            "club", "1899", "1", "04", "05", "07", "09"}
    return {w for w in s.split() if w not in drop and len(w) > 2}


def fetch(league, season, retries=3):
    url = f"https://understat.com/main/getLeagueData/{league}/{season}"
    for i in range(retries):
        try:
            r = requests.get(url, headers=H, timeout=40)
            if r.status_code == 200:
                return r.json().get("dates", [])
        except Exception:
            time.sleep(3)
    return []


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2021,2022,2023,2024,2025,2026")
    args = ap.parse_args()
    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]

    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    cols = {r[1] for r in c.execute("PRAGMA table_info(matches)")}
    for col in ("home_xg", "away_xg"):
        if col not in cols:
            c.execute(f"ALTER TABLE matches ADD COLUMN {col} REAL")
    c.execute("""CREATE TABLE IF NOT EXISTS understat_xg (
        league_id INTEGER, season TEXT, match_date TEXT,
        home_name TEXT, away_name TEXT, home_xg REAL, away_xg REAL,
        home_goals INTEGER, away_goals INTEGER, matched_match_id INTEGER,
        PRIMARY KEY (league_id, season, match_date, home_name, away_name))""")

    # 我们的球队名(按联赛)
    our_teams = defaultdict(list)
    for r in c.execute("SELECT league_id, name FROM teams"):
        our_teams[r["league_id"]].append(r["name"])

    inserted = matched = 0
    total_games = 0
    for lg_name, lid in UNDERSTAT.items():
        for season in seasons:
            code = SEASON_CODE.get(season, str(season))
            games = fetch(lg_name, season)
            time.sleep(2)
            if not games:
                print(f"  {lg_name} {season}: 无数据")
                continue
            total_games += len(games)
            # 1) 队名映射: Understat -> 我们的队名
            tmap = {}
            for g in games:
                for side in ("h", "a"):
                    t = g[side]["title"]
                    if t in tmap:
                        continue
                    nt = norm(t)
                    cands = [o for o in our_teams[lid] if norm(o) == nt]
                    if not cands and t in ALIAS:
                        a = ALIAS[t]
                        cands = [o for o in our_teams[lid] if norm(o) == norm(a)]
                    if not cands:
                        tk = tokens(t)
                        scored = []
                        for o in our_teams[lid]:
                            ot = tokens(o)
                            if tk and ot and (tk <= ot or ot <= tk):
                                scored.append((abs(len(ot) - len(tk)), o))
                        scored.sort()
                        cands = [scored[0][1]] if scored else []
                    tmap[t] = cands[0] if cands else None
            # 2) 我们的比赛索引(日期±1 容错)
            rows = c.execute("""SELECT m.match_id, date(m.date) d, th.name h, ta.name a
                                FROM matches m
                                JOIN teams th ON th.team_id=m.home_team_id
                                JOIN teams ta ON ta.team_id=m.away_team_id
                                WHERE m.league_id=? AND m.season=?""",
                             (lid, code)).fetchall()
            idx = {}
            for r in rows:
                idx[(r["d"], norm(r["h"]), norm(r["a"]))] = r["match_id"]

            from datetime import datetime, timedelta

            def candidates(title):
                """该 Understat 队名可能对应的我们库队名(多候选, 应对库里同一队多名/拼写差异)"""
                out = []
                m = tmap.get(title)
                if m:
                    out.append(m)
                nt, tk = norm(title), tokens(title)
                for o in our_teams[lid]:
                    no, ot = norm(o), tokens(o)
                    if o in out:
                        continue
                    if no == nt or (tk and ot and (tk <= ot or ot <= tk)) or \
                       (tk & ot and nt[:5] == no[:5]):
                        out.append(o)
                return out[:6]

            for g in games:
                d0 = str(g["datetime"])[:10]
                hn, an = tmap.get(g["h"]["title"]), tmap.get(g["a"]["title"])
                xh, xa = g["xG"]["h"], g["xG"]["a"]
                c.execute("INSERT OR REPLACE INTO understat_xg VALUES (?,?,?,?,?,?,?,?,?,NULL)",
                          (lid, code, d0, g["h"]["title"], g["a"]["title"], xh, xa,
                           g["goals"]["h"], g["goals"]["a"]))
                inserted += 1
                if not hn or not an or xh is None:
                    continue
                mid = None
                for ch in candidates(g["h"]["title"]):
                    for ca in candidates(g["a"]["title"]):
                        for delta in (0, 1, -1):
                            dd = (datetime.fromisoformat(d0)
                                  + timedelta(days=delta)).date().isoformat()
                            mid = idx.get((dd, norm(ch), norm(ca)))
                            if mid:
                                break
                        if mid:
                            break
                    if mid:
                        break
                if mid:
                    c.execute("""UPDATE matches SET home_xg=?, away_xg=?
                                 WHERE match_id=? AND (home_xg IS NULL OR home_xg = 0)""",
                              (xh, xa, mid))
                    c.execute("UPDATE understat_xg SET matched_match_id=? WHERE league_id=? "
                              "AND season=? AND match_date=? AND home_name=? AND away_name=?",
                              (mid, lid, code, d0, g["h"]["title"], g["a"]["title"]))
                    matched += 1
            c.commit()
            print(f"  ✓ {lg_name} {season}({code}): Understat {len(games)} 场, "
                  f"累计回填 {matched} 场")

    print("\n" + "=" * 62)
    print(f"Understat 总计拉取 {total_games} 场 | 写入 understat_xg {inserted} 行 | "
          f"回填到 matches {matched} 场")
    n = c.execute("SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL").fetchone()[0]
    print(f"库内官方 xG 覆盖: {n} 场 (此前 108)")
    c.close()


if __name__ == "__main__":
    main()
