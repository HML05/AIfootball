# -*- coding: utf-8 -*-
"""把 matches.stats_json 里的技术统计解析成独立列(0 成本, 纯本地)

新增列: ht_home/ht_away, home_shots/away_shots, home_sot/away_sot,
        home_fouls/away_fouls, home_corners/away_corners,
        home_yellow/away_yellow, home_red/away_red
用法: python scripts/parse_match_stats.py
"""
import json
import os
import sqlite3

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")

NEW_COLS = {
    "ht_home": "INTEGER", "ht_away": "INTEGER",
    "home_shots": "REAL", "away_shots": "REAL",
    "home_sot": "REAL", "away_sot": "REAL",
    "home_fouls": "REAL", "away_fouls": "REAL",
    "home_corners": "REAL", "away_corners": "REAL",
    "home_yellow": "REAL", "away_yellow": "REAL",
    "home_red": "REAL", "away_red": "REAL",
}

CSV_MAP = {
    "ht_home": "half_time_home_goals", "ht_away": "half_time_away_goals",
    "home_shots": "home_shots", "away_shots": "away_shots",
    "home_sot": "home_shots_on_target", "away_sot": "away_shots_on_target",
    "home_fouls": "home_fouls", "away_fouls": "away_fouls",
    "home_corners": "home_corners", "away_corners": "away_corners",
    "home_yellow": "home_yellow_cards", "away_yellow": "away_yellow_cards",
    "home_red": "home_red_cards", "away_red": "away_red_cards",
}

QXZ_MAP = {
    "home_shots": ("home_stats", "Total Shots"),
    "away_shots": ("away_stats", "Total Shots"),
    "home_sot": ("home_stats", "Shots on Goal"),
    "away_sot": ("away_stats", "Shots on Goal"),
    "home_fouls": ("home_stats", "Fouls"),
    "away_fouls": ("away_stats", "Fouls"),
    "home_corners": ("home_stats", "Corner Kicks"),
    "away_corners": ("away_stats", "Corner Kicks"),
    "home_yellow": ("home_stats", "Yellow Cards"),
    "away_yellow": ("away_stats", "Yellow Cards"),
    "home_red": ("home_stats", "Red Cards"),
    "away_red": ("away_stats", "Red Cards"),
}


def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


conn = sqlite3.connect(DB)
conn.row_factory = sqlite3.Row

cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
added = []
for c, t in NEW_COLS.items():
    if c not in cols:
        conn.execute(f"ALTER TABLE matches ADD COLUMN {c} {t}")
        added.append(c)
conn.commit()
print("新增列:", added or "(已存在)")

rows = conn.execute("SELECT match_id, stats_json FROM matches "
                    "WHERE stats_json IS NOT NULL AND stats_json != ''").fetchall()
upd = 0
for r in rows:
    try:
        d = json.loads(r["stats_json"])
    except Exception:
        continue
    vals = {}
    if "home_stats" in d or "away_stats" in d:          # 球小策格式
        for col, (side, key) in QXZ_MAP.items():
            vals[col] = _f((d.get(side) or {}).get(key))
    else:                                                # CSV 格式
        for col, key in CSV_MAP.items():
            vals[col] = _f(d.get(key))
    sets = ", ".join(f"{c}=?" for c in NEW_COLS if vals.get(c) is not None)
    args = [vals[c] for c in NEW_COLS if vals.get(c) is not None]
    if sets:
        conn.execute(f"UPDATE matches SET {sets} WHERE match_id=?", args + [r["match_id"]])
        upd += 1
conn.commit()

q = lambda s: conn.execute(s).fetchone()[0]
print(f"\n解析写入: {upd} 场")
for c in ("home_shots", "home_sot", "home_corners", "home_yellow", "ht_home"):
    print(f"  {c:<14} 非空 {q(f'SELECT COUNT(*) FROM matches WHERE {c} IS NOT NULL')}")
# 用射门数据校验 xG 缺失情况
print("\n有射门数据的比赛:", q("SELECT COUNT(*) FROM matches WHERE home_shots IS NOT NULL"),
      "| 有 xG 的:", q("SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL"))
conn.close()
