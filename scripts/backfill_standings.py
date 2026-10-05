# -*- coding: utf-8 -*-
"""C. 补历史赛季积分榜(football-data 免费)

用法:
    python scripts/backfill_standings.py                 # 默认补 2122~2526 五个赛季
    python scripts/backfill_standings.py --seasons 2425,2526
"""
import argparse
import os
import sqlite3
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.football_data_api import import_standings  # noqa: E402

# 库内赛季代码 -> football-data 赛季起始年
SEASON_MAP = {"2122": 2021, "2223": 2022, "2324": 2023,
              "2425": 2024, "2526": 2025, "2627": 2026}
DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2122,2223,2324,2425,2526")
    args = ap.parse_args()

    # 免费档限速 10 次/分钟 → 每次请求间隔 7 秒; 并带重试
    import time
    for code in [s.strip() for s in args.seasons.split(",") if s.strip()]:
        api_season = SEASON_MAP.get(code)
        if not api_season:
            print(f"跳过未知赛季 {code}")
            continue
        done = False
        for attempt in range(3):
            try:
                info = import_standings(season=code, api_season=api_season,
                                        pause=7.0)
                print(f"赛季 {code} (api={api_season}): {info['leagues']} 联赛 / {info['rows']} 行")
                done = True
                break
            except Exception as e:
                msg = str(e)
                print(f"赛季 {code} 第{attempt+1}次失败: {msg[:60]}")
                if "403" in msg:
                    print("   → 免费档不允许该赛季, 跳过")
                    break
                time.sleep(20)
        if not done:
            print(f"赛季 {code} 未完成")
        time.sleep(7)

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    print("\n库内积分榜分布:")
    for r in conn.execute("SELECT season, COUNT(*) n FROM standings GROUP BY season ORDER BY season"):
        print(f"  {r['season']}: {r['n']} 行")
    conn.close()


if __name__ == "__main__":
    main()
