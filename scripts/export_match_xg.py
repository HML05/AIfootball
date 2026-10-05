# -*- coding: utf-8 -*-
"""把数据库里的官方 xG 导出为训练用文件, 供 v6 特征使用

输出: data/processed/match_xg.csv  (date, home, away, home_xg, away_xg, league, season)
用法: python scripts/export_match_xg.py
"""
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"
OUT = BASE / "data" / "processed" / "match_xg.csv"
ALL = BASE / "data" / "processed" / "all_matches.csv"


def main():
    c = sqlite3.connect(str(DB))
    df = pd.read_sql_query("""
        SELECT date(m.date) AS date, th.name AS home, ta.name AS away,
               m.home_xg, m.away_xg, l.name AS league, m.season
        FROM matches m
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        JOIN leagues l ON l.league_id = m.league_id
        WHERE m.home_xg IS NOT NULL AND m.away_xg IS NOT NULL""", c)
    c.close()
    print(f"数据库中有官方 xG 的比赛: {len(df):,}")
    df.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"已写入 {OUT}")

    # 核对与训练集(all_matches.csv)的重合度
    if ALL.exists():
        a = pd.read_csv(ALL, encoding="utf-8-sig")
        a["date"] = pd.to_datetime(a["Date"], errors="coerce").dt.date.astype(str)
        key_all = set(zip(a["date"], a["HomeTeam"], a["AwayTeam"]))
        key_xg = set(zip(df["date"], df["home"], df["away"]))
        hit = len(key_all & key_xg)
        print(f"训练集总场次: {len(a):,} | 其中匹配到官方 xG: {hit:,} ({hit/max(len(a),1):.1%})")
        print(f"按联赛统计:")
        merged = a.copy()
        merged["has_xg"] = [k in key_xg for k in key_all]
        # key_all 是 set, 顺序与 a 不同 -> 用列表重算
        keys_list = list(zip(a["date"], a["HomeTeam"], a["AwayTeam"]))
        merged["has_xg"] = [k in key_xg for k in keys_list]
        if "league" in a.columns:
            print(merged.groupby("league")["has_xg"].agg(["sum", "count"]).to_string())


if __name__ == "__main__":
    main()
