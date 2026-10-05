# -*- coding: utf-8 -*-
"""列出数据库表与关键表的行数/列(供参照稿面板接真数据用)。"""
import sqlite3
import sys
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
DB = Path(r"D:\AIfootball\data\database\football.db")
con = sqlite3.connect(str(DB))
ts = [r[0] for r in con.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
print("表(%d):" % len(ts), ", ".join(ts))
for t in ("standings", "top_scorers", "scorers", "team_stats", "player_stats",
          "predictions", "matches", "teams", "players", "leagues", "transfers"):
    if t in ts:
        cols = [c[1] for c in con.execute("PRAGMA table_info(%s)" % t)]
        n = con.execute("SELECT COUNT(*) FROM %s" % t).fetchone()[0]
        print("-- %s: %d 行" % (t, n))
        print("   列:", ", ".join(cols))
con.close()
