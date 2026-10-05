# -*- coding: utf-8 -*-
"""预测复盘: 回填赛果 + 输出命中率统计

用法:
    python scripts/review_predictions.py
"""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.prediction_service import backfill_results, review_stats  # noqa: E402

HEAD = {"H": "主胜", "D": "平局", "A": "客胜"}


def main():
    bf = backfill_results()
    print(f"赛后回填: {bf['backfilled']} 条预测已写入实际赛果")
    s = review_stats()
    print("=" * 62)
    print(f"已结算预测: {s['total']} 条 | 命中 {s['hit']} | "
          f"命中率 {'%.1f%%' % (s['hit_rate'] * 100) if s['hit_rate'] is not None else 'N/A'}")
    print(f"待结算(未开赛): {s['pending']} 条")
    if s["by_league"]:
        print("\n分联赛:")
        for r in s["by_league"]:
            rate = (r["hit"] or 0) / r["n"] if r["n"] else 0
            print(f"  {r['league']:<6} {r['n']:>5} 场  命中 {r['hit']:>5}  {rate:.1%}")
    if s["by_pred"]:
        print("\n分预测类型:")
        for r in s["by_pred"]:
            rate = (r["hit"] or 0) / r["n"] if r["n"] else 0
            print(f"  预测{HEAD.get(r['pred'], r['pred']):<4} {r['n']:>5} 场  "
                  f"命中 {r['hit']:>5}  {rate:.1%}")
    if s["recent"]:
        print("\n最近结算明细:")
        for r in s["recent"][:10]:
            mark = "✓" if r["hit"] else "✗"
            print(f"  {mark} {r['date'][:10]} {r['league']:<5} {r['home']} "
                  f"{r['home_goals']}-{r['away_goals']} {r['away']} | "
                  f"预测{HEAD.get(r['pred_result'])} 实际{HEAD.get(r['actual_result'])}")
    print("=" * 62)


if __name__ == "__main__":
    main()
