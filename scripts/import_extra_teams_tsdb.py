# -*- coding: utf-8 -*-
"""为新赛事(欧冠/英冠/荷甲/葡超/巴甲)球队补球员 + 球队资料(TheSportsDB 免费)

- 目标: 库内"没有任何球员"的球队(约164支)
- 每队: 搜索球队 -> 拉球员(免费档每队10人) -> 回填 球场/容量/成立年
- 限速 30/分钟(thesportsdb 模块内置 2.2s 间隔)

用法:
    python scripts/import_extra_teams_tsdb.py
    python scripts/import_extra_teams_tsdb.py --limit 20
"""
import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.thesportsdb import (  # noqa: E402
    DB_PATH, SKIP_POSITIONS, _age, _get, _parse_height, _parse_weight, search_team, _db,
)

import json  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    conn = _db()
    rows = conn.execute("""
        SELECT t.team_id, t.name, t.league_id, t.stadium
        FROM teams t
        WHERE t.team_id NOT IN (SELECT DISTINCT team_id FROM players)
        ORDER BY t.league_id, t.name""").fetchall()
    if args.limit:
        rows = rows[:args.limit]
    print(f"待补球队: {len(rows)} 支 (限速 2.2s/次, 预计 {len(rows)*2*2.2/60:.0f} 分钟)", flush=True)

    found = added = updated = 0
    no_match = []
    t0 = time.time()
    for i, r in enumerate(rows, 1):
        team = search_team(conn, r["name"])
        if not team:
            no_match.append(r["name"])
            print(f"[{i}/{len(rows)}] ✗ {r['name']} 未找到", flush=True)
            continue
        found += 1
        # 球队资料回填(仅补空)
        try:
            cap = int(team.get("intStadiumCapacity")) if team.get("intStadiumCapacity") else None
        except Exception:
            cap = None
        try:
            fye = int(team.get("intFormedYear")) if team.get("intFormedYear") else None
        except Exception:
            fye = None
        conn.execute("""
            UPDATE teams SET
                stadium  = COALESCE(NULLIF(stadium,''), ?),
                capacity = COALESCE(capacity, ?),
                founded  = COALESCE(founded, ?)
            WHERE team_id = ?""",
            (team.get("strStadium"), cap, fye, r["team_id"]))
        updated += 1

        # 球员
        pdata = _get("lookup_all_players.php", {"id": team.get("idTeam")})
        time.sleep(2.2)
        for p in (pdata or {}).get("player") or []:
            pos = (p.get("strPosition") or "").strip()
            if any(k in pos.lower() for k in SKIP_POSITIONS):
                continue
            name = p.get("strPlayer")
            if not name:
                continue
            if conn.execute("SELECT 1 FROM players WHERE team_id=? AND name=? LIMIT 1",
                            (r["team_id"], name)).fetchone():
                continue
            conn.execute("""
                INSERT INTO players (team_id, name, name_en, position, nationality,
                    age, height, weight, number, market_value, photo_url,
                    stats_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?)""",
                (r["team_id"], name, name, pos or None, p.get("strNationality"),
                 _age(p.get("dateBorn")), _parse_height(p.get("strHeight")),
                 _parse_weight(p.get("strWeight")),
                 int(p["strNumber"]) if (p.get("strNumber") or "").isdigit() else None,
                 p.get("strCutout") or p.get("strThumb"),
                 json.dumps({"idPlayer": p.get("idPlayer")}, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            added += 1
        conn.commit()
        if i % 10 == 0 or i == len(rows):
            print(f"[{i}/{len(rows)}] {r['name']:<20} 球员+{added} | "
                  f"已用时 {(time.time()-t0)/60:.1f} 分钟", flush=True)

    print("\n" + "=" * 62)
    print(f"完成: 处理 {len(rows)} 队 | 命中 {found} | 资料回填 {updated} | 新增球员 {added}")
    if no_match:
        print(f"未找到({len(no_match)}): {', '.join(no_match[:20])}")
    print("=" * 62)
    conn.close()


if __name__ == "__main__":
    main()
