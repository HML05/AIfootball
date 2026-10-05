# -*- coding: utf-8 -*-
"""把 Transfermarkt 转会数据合并进我们的 transfers 表

- 新增 source 列(qxz / transfermarkt) 区分来源
- TM 的 from/to 俱乐部 id 映射到我们的 team_id(能映射则填, 否则留空但保留队名)
- 幂等: 同(球员名, 转会日期, 转入球队) 不重复插入

用法: python scripts/merge_transfers.py
"""
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"


def main():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    cols = {r[1] for r in c.execute("PRAGMA table_info(transfers)")}
    if "source" not in cols:
        c.execute("ALTER TABLE transfers ADD COLUMN source TEXT")
    if "season" not in cols:
        c.execute("ALTER TABLE transfers ADD COLUMN season TEXT")
    c.execute("UPDATE transfers SET source='qxz' WHERE source IS NULL")
    c.commit()

    # club_id -> 我们的 team_id
    club2team = {str(r["club_id"]): r["team_id"] for r in
                 c.execute("SELECT club_id, team_id FROM tm_club_map")}
    existing = {(r["player_name"], str(r["transfer_date"]), r["to_team_name"])
                for r in c.execute("SELECT player_name, transfer_date, to_team_name "
                                   "FROM transfers WHERE source='transfermarkt'")}
    print(f"已有 TM 转会: {len(existing):,} | 自有(qxz)转会: "
          f"{c.execute(chr(83)+'ELECT COUNT(*) FROM transfers WHERE source=' + chr(39) + 'qxz' + chr(39)).fetchone()[0]:,}")

    rows = c.execute("""SELECT player_id, player_name, season_name, transfer_date,
                               from_team_id, from_team_name, to_team_id, to_team_name,
                               transfer_type, transfer_fee
                        FROM tm_transfers""").fetchall()
    print(f"TM 转会待导入: {len(rows):,}")

    batch, added = [], 0
    for r in rows:
        key = (r["player_name"], str(r["transfer_date"]), r["to_team_name"])
        if key in existing:
            continue
        existing.add(key)
        fee = None
        try:
            fee = float(str(r["transfer_fee"]).replace("€", "").replace(",", "")
                        .replace("m", "e6").replace("k", "e3") or 0)
        except Exception:
            fee = None
        batch.append((
            r["player_name"], r["from_team_name"], r["to_team_name"],
            str(r["transfer_date"])[:10], fee, r["transfer_type"],
            r["season_name"], "transfermarkt",
            club2team.get(str(r["from_team_id"])), club2team.get(str(r["to_team_id"])),
            "2026-09-10 21:00:00"))
        if len(batch) >= 5000:
            c.executemany("""INSERT INTO transfers (player_name, from_team_name,
                    to_team_name, transfer_date, transfer_fee, transfer_type, season,
                    source, from_team_id, to_team_id, created_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?)""", batch)
            added += len(batch)
            batch = []
            c.commit()
    if batch:
        c.executemany("""INSERT INTO transfers (player_name, from_team_name, to_team_name,
                transfer_date, transfer_fee, transfer_type, season, source,
                from_team_id, to_team_id, created_at) VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      batch)
        added += len(batch)
    c.commit()

    q = lambda s: c.execute(s).fetchone()[0]
    print(f"\n新增 TM 转会 {added:,} 条")
    print("transfers 总计:", q("SELECT COUNT(*) FROM transfers"))
    for r in c.execute("""SELECT source, COUNT(*) n FROM transfers GROUP BY source"""):
        print(f"   {r['source']}: {r['n']:,}")
    print("\n最近转会样例:")
    for r in c.execute("""SELECT player_name, transfer_date, from_team_name, to_team_name,
                                 transfer_type FROM transfers
                          WHERE source='transfermarkt'
                          ORDER BY transfer_date DESC LIMIT 8"""):
        print(f"   {str(r['transfer_date'])[:10]} {str(r['player_name'])[:22]:<22} "
              f"{str(r['from_team_name'])[:18]} → {str(r['to_team_name'])[:18]} "
              f"({r['transfer_type']})")
    c.close()


if __name__ == "__main__":
    main()
