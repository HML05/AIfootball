# -*- coding: utf-8 -*-
"""导入球队资料 + 球员 (TheSportsDB 免费源)

用法:
    python scripts/import_players_tsdb.py                 # 五大联赛(约7-10分钟)
    python scripts/import_players_tsdb.py --limit 4        # 先试4支队
    python scripts/import_players_tsdb.py --league 1       # 只导英超
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.thesportsdb import import_teams_and_players  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="TheSportsDB 球队/球员导入")
    ap.add_argument("--league", type=int, default=None, help="只导某个联赛(1英超 2西甲 3德甲 4意甲 5法甲)")
    ap.add_argument("--limit", type=int, default=None, help="只处理前N支球队(调试用)")
    args = ap.parse_args()

    leagues = (args.league,) if args.league else (1, 2, 3, 4, 5)
    stat = import_teams_and_players(league_ids=leagues, limit_teams=args.limit)

    print("\n" + "=" * 60)
    print(f"完成: 处理 {stat['teams']} 队 | 命中 {stat['teams_found']} | "
          f"资料回填 {stat['teams_updated']} | 新增球员 {stat['players_added']} | "
          f"耗时 {stat['elapsed_s']}s")
    if stat["no_match"]:
        print("未匹配到的球队:", ", ".join(stat["no_match"][:20]))
    conn = sqlite3.connect(os.path.join(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__))), "data", "database", "football.db"))
    print("players 表总行数:", conn.execute("SELECT COUNT(*) FROM players").fetchone()[0])
    print("有球场资料的球队:", conn.execute(
        "SELECT COUNT(*) FROM teams WHERE stadium IS NOT NULL AND stadium != ''").fetchone()[0])
    conn.close()
    print("=" * 60)


if __name__ == "__main__":
    main()
