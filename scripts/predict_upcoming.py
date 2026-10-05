# -*- coding: utf-8 -*-
"""对未来比赛批量生成 XGBoost 预测并落库

用法:
    python scripts/predict_upcoming.py                 # 默认预测未来3天
    python scripts/predict_upcoming.py --days 7        # 未来7天
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.prediction.prediction_service import predict_upcoming  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="预测并落库")
    parser.add_argument("--days", type=int, default=3, help="预测未来几天(默认3)")
    args = parser.parse_args()
    info = predict_upcoming(days=args.days)
    print(f"完成: 共 {info['matches']} 场, 成功预测 {info['predicted']}, 跳过 {info['skipped']}")
    print("预测已写入 predictions 表。")


if __name__ == "__main__":
    main()
