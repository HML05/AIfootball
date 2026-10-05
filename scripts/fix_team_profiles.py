# -*- coding: utf-8 -*-
"""补球队资料剩余缺口(队徽/球场/容量/成立年)

优先用 Transfermarkt team_details 的队徽, 再用 TheSportsDB(免费)补球场/容量/成立年
用法: python scripts/fix_team_profiles.py
"""
import sqlite3
import sys
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
DB = BASE / "data" / "database" / "football.db"
EXT = BASE / "data" / "external"

from src.data_sources.thesportsdb import search_team, _db, SLEEP  # noqa: E402
import time  # noqa: E402


def main():
    c = _db()
    # 1) TM 队徽兜底
    logo = {}
    try:
        det = pd.read_csv(EXT / "team_details" / "team_details.csv", dtype=str,
                          on_bad_lines="skip")
        logo = dict(zip(det["club_id"].astype(str), det["logo_url"]))
    except Exception as e:
        print("team_details 读取失败", type(e).__name__)
    fixed_logo = 0
    for r in c.execute("""SELECT t.team_id, m.club_id FROM teams t
                          JOIN tm_club_map m ON m.team_id=t.team_id
                          WHERE t.logo_url IS NULL OR t.logo_url=''"""):
        url = logo.get(str(r["club_id"]))
        if url:
            c.execute("UPDATE teams SET logo_url=? WHERE team_id=?", (url, r["team_id"]))
            fixed_logo += 1
    c.commit()
    print(f"TM 队徽补: {fixed_logo}")

    # 2) TheSportsDB 补 球场/容量/成立年/队徽 (带国家校验, 避免同名误匹配)
    COUNTRY = {1: "England", 2: "Spain", 3: "Germany", 4: "Italy", 5: "France"}
    targets = c.execute("""SELECT t.team_id, t.name, t.league_id FROM teams t
        WHERE t.stadium IS NULL OR t.stadium='' OR t.capacity IS NULL
           OR t.founded IS NULL OR t.logo_url IS NULL OR t.logo_url=''""").fetchall()
    print(f"仍缺资料的球队: {len(targets)}")
    fixed = 0
    for t in targets:
        try:
            team = search_team(c, t["name"])
        except Exception:
            team = None
        if not team:
            print(f"   ✗ {t['name']} 未找到")
            continue
        want = COUNTRY.get(t["league_id"])
        got = (team.get("strCountry") or "").strip()
        if want and got and want not in got and got not in want:
            print(f"   ✗ {t['name']} 国家不符({got}) 跳过")
            continue
        cap = team.get("intStadiumCapacity")
        fye = team.get("intFormedYear")
        try:
            cap = int(cap) if cap else None
        except Exception:
            cap = None
        try:
            fye = int(fye) if fye else None
        except Exception:
            fye = None
        c.execute("""UPDATE teams SET
                logo_url = COALESCE(NULLIF(logo_url,''), ?),
                stadium  = COALESCE(NULLIF(stadium,''), ?),
                capacity = COALESCE(capacity, ?),
                founded  = COALESCE(founded, ?)
            WHERE team_id=?""",
            (team.get("strTeamBadge") or team.get("strTeamLogo"),
             team.get("strStadium"), cap, fye, t["team_id"]))
        c.commit()
        fixed += 1
        print(f"   ✓ {t['name']:<18} {team.get('strTeam')}")
    print(f"\nTheSportsDB 补: {fixed} 队")

    q = lambda s: c.execute(s).fetchone()[0]
    tot = q("SELECT COUNT(*) FROM teams")
    for col, label in [("logo_url", "队徽"), ("stadium", "球场"), ("capacity", "容量"),
                       ("founded", "成立年")]:
        n = c.execute(f"SELECT COUNT(*) FROM teams WHERE {col} IS NOT NULL AND {col}!=''").fetchone()[0]
        print(f"  {label}: {n}/{tot} (缺 {tot-n})")
    c.close()


if __name__ == "__main__":
    main()
