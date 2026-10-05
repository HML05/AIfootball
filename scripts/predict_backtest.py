# -*- coding: utf-8 -*-
"""历史回测: 用当前模型预测历史已完赛比赛, 立即回填赛果, 产出真实命中率

用法:
    python scripts/predict_backtest.py                      # 默认回测 2526 赛季
    python scripts/predict_backtest.py --from 2024-08-01 --to 2025-06-30
    python scripts/predict_backtest.py --limit 100          # 试跑
"""
import argparse
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.prediction_service import predict_backtest  # noqa: E402


def main():
    ap = argparse.ArgumentParser(description="历史回测")
    ap.add_argument("--from", dest="frm", default="2025-08-01")
    ap.add_argument("--to", dest="to", default="2026-06-30")
    ap.add_argument("--limit", type=int, default=None)
    args = ap.parse_args()

    print(f"回测区间: {args.frm} ~ {args.to}" + (f" (前{args.limit}场)" if args.limit else ""))
    t0 = time.time()
    info = predict_backtest(args.frm, args.to, limit=args.limit)
    print(f"\n完成: {info['predicted']} 场预测 (跳过 {info['skipped']}) | "
          f"命中 {info['hit']} | 命中率 {info['hit_rate']:.1%} | 耗时 {time.time()-t0:.0f}s")


if __name__ == "__main__":
    main()
