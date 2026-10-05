# -*- coding: utf-8 -*-
"""赛前包窗口检查/提醒

赛前全景包只在临近开赛(约 24–36 小时内)才会生成完整版;
距开赛较远时服务端只返回基础快照(并退还点数)。

本脚本列出未来比赛的开赛时间、距现在小时数、是否已进入可抓窗口, 并给出建议命令。

用法:
    python scripts/check_matchpack_window.py
    python scripts/check_matchpack_window.py --window 36
"""
import argparse
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--window", type=float, default=36, help="可抓窗口(小时)")
    ap.add_argument("--credits", type=int, default=50, help="单场点数")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    rows = conn.execute("""
        SELECT m.match_id, m.date, l.name lg, th.name h, ta.name a,
               q.qxz_fixture_id,
               (SELECT COUNT(*) FROM qxz_match_pack p WHERE p.match_id=m.match_id) packed
        FROM matches m
        JOIN leagues l ON l.league_id = m.league_id
        JOIN teams th ON th.team_id = m.home_team_id
        JOIN teams ta ON ta.team_id = m.away_team_id
        LEFT JOIN qxz_fixture_map q ON q.match_id = m.match_id
        WHERE m.status='NS' AND m.league_id IN (1,2,3,4,5)
        ORDER BY m.date LIMIT 40""").fetchall()
    bal = None
    try:
        import requests
        from config.settings import settings
        r = requests.get(f"{settings.QIXIAOCE_BASE}/quota",
                         headers={"X-API-Key": settings.QIXIAOCE_API_KEY}, timeout=15)
        bal = (r.json().get("credits") or {}).get("remaining")
    except Exception:
        pass
    conn.close()

    now = datetime.now()
    print(f"当前时间: {now:%Y-%m-%d %H:%M}   可抓窗口: {args.window:.0f} 小时内   "
          f"余额: {bal if bal is not None else '未知'} 点")
    print("=" * 76)
    ready = []
    for r in rows:
        try:
            kick = datetime.fromisoformat(r["date"])
        except Exception:
            continue
        hours = (kick - now).total_seconds() / 3600
        mapped = "有" if r["qxz_fixture_id"] else "无"
        packed = "已抓" if r["packed"] else "未抓"
        flag = "✅ 可抓" if (0 <= hours <= args.window and r["qxz_fixture_id"]
                            and not r["packed"]) else ""
        if flag:
            ready.append(r)
        print(f"{r['date'][:16]}  {r['lg']:<4} {r['h'][:14]:<14} vs {r['a'][:14]:<14} "
              f"| {hours:6.1f}h | 映射{mapped} | {packed} {flag}")
    print("=" * 76)
    if ready:
        need = len(ready) * args.credits
        print(f"现在可以抓取 {len(ready)} 场完整赛前包, 需要 {need} 点"
              + (f"（余额 {bal}，{'足够' if bal and bal >= need else '不足'}）" if bal is not None else ""))
        print("\n建议命令:")
        print(f"  python scripts/import_paid_qxz.py matchpacks "
              f"--max-hours-ahead {args.window:.0f} --budget {max(need, 50)}")
    else:
        nxt = rows[0]["date"][:16] if rows else "-"
        print("当前没有进入可抓窗口的比赛（服务端此时只返回基础快照并退点）。")
        print(f"最近一场: {nxt} —— 建议在该场比赛前 {args.window:.0f} 小时内再运行本脚本。")


if __name__ == "__main__":
    main()
