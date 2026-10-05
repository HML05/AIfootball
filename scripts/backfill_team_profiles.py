# -*- coding: utf-8 -*-
"""补球队资料(球场/成立年/队徽) —— football-data 免费赛事球队接口

对五大联赛 + 欧冠/英冠/荷甲/葡超/巴甲 各调用一次 (10 次请求), 把队徽/球场写入 teams。
用法: python scripts/backfill_team_profiles.py
"""
import os
import re
import sqlite3
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.football_data_api import (  # noqa: E402
    FootballDataClient, _drop_club_tokens, _norm, _TEAM_ALIAS,
)

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")
COMPS = ["PL", "PD", "BL1", "SA", "FL1", "CL", "ELC", "DED", "PPL", "BSA"]


def main():
    client = FootballDataClient()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row

    nn = {_norm(r["name"]): r["team_id"] for r in
          conn.execute("SELECT team_id, name FROM teams")}
    updated = created = 0
    for code in COMPS:
        try:
            teams = client.get_competition_teams(code)
        except Exception as e:
            print(f"  {code} 拉取失败: {str(e)[:60]}")
            continue
        time.sleep(6.5)                      # 免费档限速 10 次/分钟
        for t in teams:
            name = t.get("shortName") or t.get("name")
            if not name:
                continue
            cand = _norm(_drop_club_tokens(name))
            tid = nn.get(_norm(name)) or nn.get(cand)
            if tid is None and _TEAM_ALIAS.get(cand):
                tid = nn.get(_norm(_TEAM_ALIAS[cand]))
            league_row = conn.execute(
                "SELECT league_id FROM leagues ORDER BY league_id LIMIT 1").fetchone()
            if tid is None:
                clean = _drop_club_tokens(name).title()
                cur = conn.execute(
                    "INSERT INTO teams (league_id, name, name_en, short_name, "
                    "elo_rating, created_at) VALUES (?,?,?,?,1500.0,datetime('now'))",
                    (league_row["league_id"], clean, t.get("name"), clean[:12]))
                tid = cur.lastrowid
                nn[_norm(clean)] = tid
                created += 1
            conn.execute("""
                UPDATE teams SET
                    logo_url = COALESCE(NULLIF(?, ''), logo_url),
                    stadium  = COALESCE(NULLIF(?, ''), stadium),
                    founded  = COALESCE(?, founded),
                    name_en  = COALESCE(NULLIF(?, ''), name_en)
                WHERE team_id = ?""",
                (t.get("crest"), t.get("venue"), t.get("founded"),
                 t.get("name"), tid))
            updated += 1
        conn.commit()
        print(f"  {code}: {len(teams)} 队处理完成")

    q = lambda s: conn.execute(s).fetchone()[0]
    print(f"\n更新 {updated} 队, 新建 {created} 队")
    print("  队徽:", q("SELECT COUNT(*) FROM teams WHERE logo_url IS NOT NULL AND logo_url!=''"),
          "/", q("SELECT COUNT(*) FROM teams"))
    print("  球场:", q("SELECT COUNT(*) FROM teams WHERE stadium IS NOT NULL AND stadium!=''"))
    print("  成立年:", q("SELECT COUNT(*) FROM teams WHERE founded IS NOT NULL"))
    conn.close()


if __name__ == "__main__":
    main()
