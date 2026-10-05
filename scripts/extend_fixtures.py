# -*- coding: utf-8 -*-
"""B. 扩展未来赛程窗口到 30 天(football-data 免费, 单次上限10天 → 分窗口拉取)

用法: python scripts/extend_fixtures.py --days 30
"""
import argparse
import os
import sys
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.football_data_api import import_matches  # noqa: E402


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=30)
    ap.add_argument("--from", dest="frm", default=None, help="起始日期 YYYY-MM-DD")
    args = ap.parse_args()

    start = date.fromisoformat(args.frm) if args.frm else date.today()
    total_new = total_upd = 0
    offset = 0
    first = True
    while offset < args.days:
        span = min(10, args.days - offset)
        d0 = start + timedelta(days=offset)
        try:
            info = import_matches(days=span, date_from=d0, cleanup=first)
            print(f"  窗口 {d0} ~ {d0 + timedelta(days=span - 1)}: "
                  f"返回 {info['fetched']} | 新增 {info['inserted']} | 更新 {info['updated']}")
            total_new += info["inserted"]
            total_upd += info["updated"]
        except Exception as e:
            print(f"  窗口 {d0} 失败: {e}")
        first = False
        offset += span
    print(f"\n合计: 新增 {total_new} 场, 更新 {total_upd} 场")

    import sqlite3
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "database", "football.db")
    conn = sqlite3.connect(db)
    ns = conn.execute("SELECT COUNT(*) FROM matches WHERE status='NS'").fetchone()[0]
    rng = conn.execute("SELECT MIN(date), MAX(date) FROM matches WHERE status='NS'").fetchone()
    print(f"库内未开赛: {ns} 场 | 覆盖 {rng[0][:10]} ~ {rng[1][:10]}")
    conn.close()


if __name__ == "__main__":
    main()
