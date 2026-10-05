# -*- coding: utf-8 -*-
"""通过 Reep ID 桥接, 用 Transfermarkt 档案增强我们的球员

链路: 我们球员的 api-football id(来自球小策) -> reep_id -> transfermarkt id -> tm_players 档案
填充: 国籍 / 身高 / 惯用脚 / 身价 / tm_player_id

用法: python scripts/enrich_players_via_reep.py
"""
import json
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).resolve().parent.parent
REEP = BASE / "data" / "external" / "reep"
DB = BASE / "data" / "database" / "football.db"


def main():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row

    print("1) 读取 bridges ...")
    br = pd.read_csv(REEP / "bridges.csv.gz", dtype=str, compression="gzip")
    api = br[(br["provider"] == "api_football") & (br["namespace"] == "player")]
    tm = br[(br["provider"] == "transfermarkt") & (br["namespace"].isin(["spieler", "player"]))]
    api2reep = dict(zip(api["external_id"], api["reep_id"]))
    reep2tm = dict(zip(tm["reep_id"], tm["external_id"]))
    api2tm = {}
    for aid, rid in api2reep.items():
        t = reep2tm.get(rid)
        if t:
            api2tm[aid] = t
    print(f"   api_football->transfermarkt 映射: {len(api2tm):,}")

    print("2) 读取 TM 档案与最新身价 ...")
    prof = {r["player_id"]: dict(r) for r in c.execute(
        "SELECT player_id, player_name, citizenship, height, foot FROM tm_players")}
    mkt = {}
    for r in c.execute("""SELECT player_id, value FROM tm_player_market_value v
                          WHERE value_date = (SELECT MAX(value_date) FROM tm_player_market_value x
                                              WHERE x.player_id = v.player_id)"""):
        mkt[r["player_id"]] = r["value"]
    print(f"   档案 {len(prof):,} | 有市值 {len(mkt):,}")

    print("3) 增强我们的球员 ...")
    rows = c.execute("SELECT player_id, name, stats_json FROM players").fetchall()
    updated = skipped = 0
    by_field = {"nationality": 0, "height": 0, "foot": 0, "market_value": 0}
    samples = []
    for r in rows:
        try:
            d = json.loads(r["stats_json"] or "{}")
        except Exception:
            d = {}
        aid = d.get("qxz_id")
        if not aid:
            continue
        tmid = api2tm.get(str(aid))
        if not tmid:
            skipped += 1
            continue
        p = prof.get(tmid)
        if not p:
            skipped += 1
            continue
        vals = {"nationality": p.get("citizenship"), "height": p.get("height"),
                "foot": p.get("foot"), "market_value": mkt.get(tmid)}
        sets, args = [], []
        for k, v in vals.items():
            if v not in (None, ""):
                sets.append(f"{k} = COALESCE(NULLIF({k},''), ?, {k})" if k != "height"
                            else "height = COALESCE(height, ?)")
                args.append(v)
                by_field[k] += 1
        if sets:
            args.append(r["player_id"])
            c.execute(f"UPDATE players SET {', '.join(sets)}, tm_player_id=? WHERE player_id=?",
                      args[:-1] + [tmid, args[-1]])
            updated += 1
            if len(samples) < 8:
                samples.append((r["name"], p["player_name"], p.get("citizenship"),
                                p.get("height"), vals["market_value"]))
    c.commit()

    print(f"\n增强球员 {updated:,} 名 (无法桥接 {skipped:,})")
    for k, v in by_field.items():
        print(f"   填充 {k:<14} {v:,}")
    print("\n样例:")
    for s in samples:
        mv = f"{float(s[4])/1e6:.1f}M€" if s[4] else "—"
        print(f"   {s[0]:<16} -> {s[1]:<24} {s[2]} | {s[3]}cm | {mv}")

    q = lambda s: c.execute(s).fetchone()[0]
    p_tot = q("SELECT COUNT(*) FROM players")
    print("\n== 增强后覆盖 ==")
    for col, label in [("nationality", "国籍"), ("height", "身高"), ("foot", "惯用脚"),
                       ("market_value", "身价")]:
        n = c.execute(f"SELECT COUNT(*) FROM players WHERE {col} IS NOT NULL AND {col} != ''").fetchone()[0]
        print(f"   {label:<4} {n}/{p_tot} ({n/p_tot:.0%})")
    c.close()


if __name__ == "__main__":
    main()
