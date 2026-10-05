# -*- coding: utf-8 -*-
"""修正 TheSportsDB 错误匹配: 删除错队球员 + 用新别名重导 + 覆盖错误资料"""
import os
import sys
import sqlite3

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.thesportsdb import import_teams_and_players  # noqa: E402

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")

FIX_TEAMS = ["La Coruna", "Psg"]

conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row
print("清理错误球员前 players 总数:",
      conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
for name in FIX_TEAMS:
    row = conn.execute("SELECT team_id FROM teams WHERE name=?", (name,)).fetchone()
    if not row:
        continue
    n = conn.execute("DELETE FROM players WHERE team_id=?", (row["team_id"],)).rowcount
    if n:
        print(f"  删除 {name} 的错误球员 {n} 名")
conn.commit()
conn.close()

stat = import_teams_and_players(team_names=FIX_TEAMS, overwrite_profile=True)
print("\n修正完成:", {k: stat[k] for k in ("teams", "teams_found", "players_added", "elapsed_s")})
if stat["no_match"]:
    print("仍未匹配:", stat["no_match"])
