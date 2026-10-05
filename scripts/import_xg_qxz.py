# -*- coding: utf-8 -*-
"""用球小策补齐已完赛比赛的技术统计(xG/射门/控球...) -> matches.home_xg/away_xg/stats_json

用法:
    python scripts/import_xg_qxz.py --budget 100     # 按点数上限抓取(约5点/场)
"""
import argparse
import json
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.qiuxiaoce import QiuxiaoceClient  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "database", "football.db")
COST = 5


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--budget", type=int, default=100)
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    cli = QiuxiaoceClient()
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    conn.execute("""CREATE TABLE IF NOT EXISTS qxz_fixture_map (
        match_id INTEGER PRIMARY KEY, qxz_fixture_id INTEGER, kickoff TEXT,
        home_en TEXT, away_en TEXT, league TEXT, mapped_at TEXT)""")
    rows = conn.execute("""
        SELECT m.match_id, q.qxz_fixture_id, m.date, th.name h, ta.name a
        FROM qxz_fixture_map q
        JOIN matches m ON m.match_id = q.match_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        WHERE m.status='FT' AND m.home_xg IS NULL
        ORDER BY m.date DESC""").fetchall()
    if args.limit:
        rows = rows[:args.limit]
    print(f"待补 xG 的已完赛比赛: {len(rows)} 场 (预算 {args.budget} 点)")

    ok = 0
    for i, r in enumerate(rows, 1):
        if cli.spent_points + COST > args.budget:
            print(f"⏹ 达到预算上限({args.budget}点), 停止")
            break
        d = cli.fixture_stats(r["qxz_fixture_id"])
        if not d:
            print(f"[{i}/{len(rows)}] ✗ {r['h']} vs {r['a']} 无数据")
            continue
        fx = d.get("fixture", {})
        hid, aid = fx.get("home_team_id"), fx.get("away_team_id")
        xg = {}
        for item in d.get("data", []):
            tid = item.get("team_id")
            st = item.get("stats", {})
            try:
                val = float(st.get("expected_goals"))
            except (TypeError, ValueError):
                val = None
            xg[tid] = (val, st)
        xh = xg.get(hid, (None, {}))[0]
        xa = xg.get(aid, (None, {}))[0]
        conn.execute("""UPDATE matches SET home_xg=?, away_xg=?, stats_json=?
                        WHERE match_id=?""",
                     (xh, xa, json.dumps({
                         "home_stats": xg.get(hid, (None, {}))[1],
                         "away_stats": xg.get(aid, (None, {}))[1],
                         "referee": fx.get("referee"), "venue": fx.get("venue_name"),
                     }, ensure_ascii=False), r["match_id"]))
        conn.commit()
        ok += 1
        print(f"[{i}/{len(rows)}] ✓ {r['h']} vs {r['a']}  xG {xh} : {xa} "
              f"| 累计点数 ~{cli.spent_points}")

    conn.close()
    print("\n" + "=" * 60)
    print(f"完成: 补 {ok} 场 xG | 估算消耗 {cli.spent_points} 点")
    conn = sqlite3.connect(DB)
    print("库内 xG 覆盖:", conn.execute(
        "SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL").fetchone()[0], "场")
    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
