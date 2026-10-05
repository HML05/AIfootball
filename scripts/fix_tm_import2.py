# -*- coding: utf-8 -*-
"""TM 导入收尾修复(精简版): 赛季排序字段 + 转会球员名 + 索引

用法: python scripts/fix_tm_import2.py
"""
import re
import sqlite3
import time
from pathlib import Path

DB = Path(__file__).parent.parent / "data" / "database" / "football.db"


def season_start(s):
    s = str(s or "").strip()
    m = re.match(r"^(\d{2})/(\d{2})$", s)
    if m:
        yy = int(m.group(1))
        return 2000 + yy if yy <= 40 else 1900 + yy
    m = re.match(r"^(\d{4})", s)
    return int(m.group(1)) if m else None


def main():
    c = sqlite3.connect(str(DB))
    c.execute("PRAGMA journal_mode=WAL")
    t0 = time.time()

    print("1) tm_player_seasons.season_start")
    rows = c.execute("SELECT rowid, season_name FROM tm_player_seasons").fetchall()
    upd = [(season_start(s), rid) for rid, s in rows]
    for i in range(0, len(upd), 50000):
        c.executemany("UPDATE tm_player_seasons SET season_start=? WHERE rowid=?",
                      upd[i:i + 50000])
        c.commit()
    print(f"   {len(upd):,} 行 | {time.time()-t0:.0f}s")

    print("2) tm_team_seasons.season_start")
    cols = {r[1] for r in c.execute("PRAGMA table_info(tm_team_seasons)")}
    if "season_start" not in cols:
        c.execute("ALTER TABLE tm_team_seasons ADD COLUMN season_start INTEGER")
        c.commit()
    rows = c.execute("SELECT rowid, season_id FROM tm_team_seasons").fetchall()
    upd = [(season_start(s), rid) for rid, s in rows]
    c.executemany("UPDATE tm_team_seasons SET season_start=? WHERE rowid=?", upd)
    c.commit()
    print(f"   {len(upd):,} 行")

    print("3) tm_transfers.player_name (UPDATE...FROM)")
    cols = {r[1] for r in c.execute("PRAGMA table_info(tm_transfers)")}
    if "player_name" not in cols:
        c.execute("ALTER TABLE tm_transfers ADD COLUMN player_name TEXT")
        c.commit()
    c.execute("""UPDATE tm_transfers SET player_name = p.player_name
                 FROM tm_players p WHERE p.player_id = tm_transfers.player_id""")
    c.commit()
    print("   完成")

    print("4) 索引")
    for sql in ("CREATE INDEX IF NOT EXISTS idx_tmmv_pid ON tm_player_market_value(player_id)",
                "CREATE INDEX IF NOT EXISTS idx_tmps_team_season ON tm_player_seasons(team_id, season_start)",
                "CREATE INDEX IF NOT EXISTS idx_tmtr_from ON tm_transfers(from_team_id)",
                "CREATE INDEX IF NOT EXISTS idx_tmtr_to ON tm_transfers(to_team_id)",
                "CREATE INDEX IF NOT EXISTS idx_tminj_pid ON tm_player_injuries(player_id)"):
        c.execute(sql)
    c.commit()

    q = lambda s: c.execute(s).fetchone()[0]
    print("\n校验:")
    print("  赛季起始年非空:", q("SELECT COUNT(*) FROM tm_player_seasons WHERE season_start IS NOT NULL"))
    print("  转会带球员名:", q("SELECT COUNT(*) FROM tm_transfers WHERE player_name IS NOT NULL"))
    from datetime import datetime, timezone
    mx = q("SELECT MAX(date_unix) FROM tm_player_market_value")
    print("  最新市值日期:", datetime.fromtimestamp(int(mx), tz=timezone.utc).strftime("%Y-%m-%d"))

    cid = q("SELECT club_id FROM tm_club_map WHERE team_id=1")
    ss = q(f"SELECT MAX(season_start) FROM tm_player_seasons WHERE team_id='{cid}'")
    print(f"\n== 阿森纳 {ss}/{str(ss+1)[2:]} 赛季 TM 阵容(按市值前10) ==")
    for r in c.execute("""
        SELECT p.player_name, p.citizenship, p.height, p.position, p.foot,
               (SELECT value FROM tm_player_market_value v WHERE v.player_id=p.player_id
                ORDER BY date_unix DESC LIMIT 1) mv
        FROM tm_players p JOIN tm_player_seasons s ON s.player_id=p.player_id
        WHERE s.team_id=? AND s.season_start=?
        GROUP BY p.player_id ORDER BY mv DESC LIMIT 10""", (cid, ss)):
        mv = f"{float(r[5])/1e6:.0f}M€" if r[5] else "—"
        print(f"   {r[0]:<24} {str(r[1])[:14]:<14} {r[2]}cm {str(r[3])[:20]:<20} {mv}")
    print(f"\n总耗时 {time.time()-t0:.0f}s")
    c.close()


if __name__ == "__main__":
    main()
