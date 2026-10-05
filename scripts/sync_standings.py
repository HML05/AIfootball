# -*- coding: utf-8 -*-
"""积分榜同步 (Football-Data.org)

拉取五大联赛当前赛季(2627)积分榜并整体替换入库。

用法:
    python scripts/sync_standings.py
"""
import os
import sys
import sqlite3
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from config.settings import settings                                # noqa: E402
from src.data_sources.football_data_api import import_standings     # noqa: E402

DB = Path(__file__).parent.parent / "data" / "database" / "football.db"
LEAGUE_ID_NAME = {1: "英超", 2: "西甲", 3: "德甲", 4: "意甲", 5: "法甲"}


def main():
    if not settings.FOOTBALL_DATA_TOKEN:
        print("❌ 未配置 FOOTBALL_DATA_TOKEN，无法同步积分榜")
        return 1
    print("正在同步五大联赛积分榜 (season 2627) ...")
    info = import_standings()
    print(f"完成: {info['leagues']} 个联赛 / {info['rows']} 行")

    # 展示当前库内积分榜
    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    for lid in range(1, 6):
        rows = conn.execute("""
            SELECT s.rank, t.name, s.played, s.won, s.draw, s.lost,
                   s.goals_for, s.goals_against, s.points
            FROM standings s JOIN teams t ON t.team_id = s.team_id
            WHERE s.league_id = ? AND s.season = '2627'
            ORDER BY s.rank LIMIT 5""", (lid,)).fetchall()
        print(f"\n【{LEAGUE_ID_NAME[lid]} 前5】")
        for r in rows:
            print(f"  {r['rank']}. {r['name']:<20} {r['played']}场 "
                  f"{r['won']}-{r['draw']}-{r['lost']} "
                  f"{r['goals_for']}:{r['goals_against']} 积分{r['points']}")
    conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
