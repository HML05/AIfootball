# -*- coding: utf-8 -*-
"""修复 TM 导入的三个质量问题:
1) tm_player_market_value.date_unix 转成整数(原为 NULL, 导致时间排序失效)
2) season_name('24/25') -> season_start(整数), 修正赛季排序
3) tm_transfers 补 player_name(join tm_players)

用法: python scripts/fix_tm_import.py
"""
import os
import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
EXT = BASE / "data" / "external"
DB = BASE / "data" / "database" / "football.db"


def season_start(s):
    """'24/25' -> 2024 ; 兼容 '2024' 形式"""
    s = str(s or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})$", s)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy <= 40 else 1900 + yy
    m = re.match(r"^(\d{4})", s)
    return int(m.group(1)) if m else None


def main():
    c = sqlite3.connect(DB)
    print("1) 修复市值 date_unix ...")
    mv = pd.read_csv(EXT / "player_market_value" / "player_market_value.csv",
                     encoding="utf-8", on_bad_lines="skip")
    mv["player_id"] = mv["player_id"].astype(str)
    mv["date_unix"] = pd.to_numeric(
        mv["date_unix"].astype(str).str.replace(r"[^0-9]", "", regex=True),
        errors="coerce").astype("Int64")
    mv["value"] = pd.to_numeric(
        mv["value"].astype(str).str.replace(r"[^0-9.]", "", regex=True), errors="coerce")
    mv = mv.dropna(subset=["date_unix"])
    mv.to_sql("tm_player_market_value", c, if_exists="replace", index=False)
    c.execute("CREATE INDEX IF NOT EXISTS idx_tmmv_pid ON tm_player_market_value(player_id)")
    print(f"   写入 {len(mv):,} 行 | 非空日期 {mv['date_unix'].notna().sum():,}")

    print("2) 修正赛季排序(新增 season_start) ...")
    for table, season_col in (("tm_player_seasons", "season_name"),
                              ("tm_team_seasons", "season_id")):
        cols = {r[1] for r in c.execute(f"PRAGMA table_info({table})")}
        if "season_start" not in cols:
            c.execute(f"ALTER TABLE {table} ADD COLUMN season_start INTEGER")
        rows = c.execute(f"SELECT rowid, {season_col} FROM {table}").fetchall()
        upd = [(season_start(s), rid) for rid, s in rows]
        c.executemany(f"UPDATE {table} SET season_start=? WHERE rowid=?", upd)
        print(f"   {table}: 更新 {len(upd):,} 行")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tmps_season ON tm_player_seasons(team_id, season_start)")

    print("3) 转会表补 player_name ...")
    cols = {r[1] for r in c.execute("PRAGMA table_info(tm_transfers)")}
    if "player_name" not in cols:
        c.execute("ALTER TABLE tm_transfers ADD COLUMN player_name TEXT")
    c.execute("""UPDATE tm_transfers SET player_name = (
                    SELECT player_name FROM tm_players p
                    WHERE p.player_id = tm_transfers.player_id)""")
    c.commit()

    q = lambda s: c.execute(s).fetchone()[0]
    print("\n修复后校验:")
    mx = q("SELECT MAX(date_unix) FROM tm_player_market_value")
    from datetime import datetime, timezone
    print("   最新市值日期:",
          datetime.fromtimestamp(int(mx), tz=timezone.utc).strftime("%Y-%m-%d") if mx else "-")
    print("   转会带球员名:", q("SELECT COUNT(*) FROM tm_transfers WHERE player_name IS NOT NULL"))
    print("   阿森纳最近赛季:",
          q("""SELECT MAX(season_start) FROM tm_player_seasons
               WHERE team_id=(SELECT club_id FROM tm_club_map WHERE team_id=1)"""))

    # 抽样: 阿森纳最近赛季阵容
    cid = q("SELECT club_id FROM tm_club_map WHERE team_id=1")
    ss = q(f"SELECT MAX(season_start) FROM tm_player_seasons WHERE team_id='{cid}'")
    print(f"\n== 阿森纳 {ss} 赛季 TM 阵容(按市值, 前10) ==")
    for r in c.execute("""
        SELECT p.player_name, p.citizenship, p.height, p.position,
               (SELECT value FROM tm_player_market_value v WHERE v.player_id=p.player_id
                ORDER BY date_unix DESC LIMIT 1) mv
        FROM tm_players p
        JOIN tm_player_seasons s ON s.player_id=p.player_id
        WHERE s.team_id=? AND s.season_start=?
        GROUP BY p.player_id ORDER BY mv DESC LIMIT 10""", (cid, ss)):
        mv = f"{float(r[4])/1e6:.0f}M€" if r[4] else "—"
        print(f"   {r[0]:<24} {str(r[1])[:14]:<14} {r[2]}cm {str(r[3])[:20]:<20} {mv}")
    c.close()


if __name__ == "__main__":
    main()
