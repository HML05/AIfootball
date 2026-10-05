# -*- coding: utf-8 -*-
"""赛程同步脚本

自动选择数据源:
  - 配置了 FOOTBALL_DATA_TOKEN → 用 Football-Data.org 拉取真实赛程/比分 (推荐, 免费100次/天)
  - 未配置 → 演示模式: 用 2627 赛季球队生成确定性未来赛程(status=NS)

用法:
    python scripts/sync_fixtures.py                 # 同步未来3天
    python scripts/sync_fixtures.py --days 7        # 未来7天
    python scripts/sync_fixtures.py --clear         # 清除演示赛程
"""
import argparse
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings                      # noqa: E402
from src.data_sources.demo_fixtures import (             # noqa: E402
    generate_fixtures, clear_demo_fixtures,
)
from src.data_sources.football_data_api import import_matches  # noqa: E402

MARKER_HINT = "data/demo_fixtures.json"


def _count_ns():
    import sqlite3
    from pathlib import Path
    db = Path(__file__).parent.parent / "data" / "database" / "football.db"
    conn = sqlite3.connect(str(db))
    total = conn.execute("SELECT COUNT(*) FROM matches WHERE status='NS'").fetchone()[0]
    today = datetime.now().date().isoformat()
    today_ns = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status='NS' AND date(date)=?",
        (today,)).fetchone()[0]
    live = conn.execute("SELECT COUNT(*) FROM matches WHERE status IN ('1H','2H','HT')").fetchone()[0]
    ft = conn.execute("SELECT COUNT(*) FROM matches WHERE status='FT'").fetchone()[0]
    conn.close()
    return total, today_ns, live, ft


def main():
    parser = argparse.ArgumentParser(description="赛程同步")
    parser.add_argument("--days", type=int, default=3, help="同步未来几天(默认3)")
    parser.add_argument("--clear", action="store_true", help="清除演示赛程")
    args = parser.parse_args()

    if args.clear:
        removed = clear_demo_fixtures()
        print(f"已清除演示赛程 {removed} 场 (标记文件: {MARKER_HINT})")
        return

    token = settings.FOOTBALL_DATA_TOKEN
    print("=" * 60)
    if token:
        print("  赛程同步 - 真实数据源 (Football-Data.org)")
        print("=" * 60)
        print(f"生成窗口: 未来 {args.days} 天 (今天起)")
        print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        removed = clear_demo_fixtures()
        if removed:
            print(f"已先清除演示赛程 {removed} 场")
        info = import_matches(days=args.days)
        print(f"\nAPI 返回: {info['fetched']} 场 | 新增 {info['inserted']} | 更新 {info['updated']}")
    else:
        print("  赛程同步 - 演示模式（未配置 FOOTBALL_DATA_TOKEN，无需 API）")
        print("=" * 60)
        print(f"生成窗口: 未来 {args.days} 天 (今天起)")
        print(f"当前时间: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
        print("=" * 60)
        info = generate_fixtures(days=args.days)
        print(f"\n本次新生成: {info['created']} 场 (status=NS, 幂等)")
        print(f"演示数据标记: {MARKER_HINT} (可 --clear 清除)")
        print("\n提示: 配置 FOOTBALL_DATA_TOKEN 后将自动改用真实数据源")

    total, today_ns, live, ft = _count_ns()
    print(f"\n当前库内: 未开赛(NS) {total} 场 | 其中【今天】{today_ns} 场 | "
          f"进行中 {live} 场 | 已完赛(FT) {ft} 场")


if __name__ == "__main__":
    main()
