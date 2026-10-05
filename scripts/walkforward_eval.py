# -*- coding: utf-8 -*-
"""严格样本外回测 (walk-forward)

在 cutoff 之前的数据上训练, 只回测 cutoff 之后的比赛 —— 完全无未来信息。
同时给出基线对比(全押主胜)与 per-league 命中率。

用法:
    python scripts/walkforward_eval.py                        # 默认: 训练<=2025-07-31, 回测 2526 赛季
    python scripts/walkforward_eval.py --cutoff 2024-08-01
"""
import argparse
import json
import os
import sys
from collections import Counter
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, confusion_matrix, log_loss, f1_score

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.prediction.vector_features import load_matches, build_features  # noqa: E402

BASE = Path(__file__).parent.parent
LABELS = ["主胜", "平局", "客胜"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2025-08-01",
                    help="训练集截止日期(不含): 之前的用于训练")
    ap.add_argument("--save", action="store_true", help="保存模型与评估结果")
    args = ap.parse_args()

    df = load_matches()
    X, y, dates, divs, leagues = build_features(df)
    dates = pd.to_datetime(dates)
    cutoff = pd.Timestamp(args.cutoff)

    tr = dates < cutoff
    te = dates >= cutoff
    print(f"总样本 {len(X)} | 训练 {tr.sum()} (至 {cutoff.date()}) | 回测 {te.sum()} "
          f"({dates[te].min().date()} ~ {dates[te].max().date()})")

    model = xgb.XGBClassifier(
        objective="multi:softprob", num_class=3, n_estimators=300, max_depth=5,
        learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
        reg_alpha=0.1, reg_lambda=1.0, random_state=42, eval_metric="mlogloss",
    )
    model.fit(X[tr], y[tr], verbose=False)

    proba = model.predict_proba(X[te])
    pred = proba.argmax(axis=1)
    acc = accuracy_score(y[te], pred)
    ll = log_loss(y[te], proba, labels=[0, 1, 2])
    f1m = f1_score(y[te], pred, average="macro")
    base_home = (y[te] == 0).mean()

    print("\n" + "=" * 62)
    print("【严格样本外结果】")
    print(f"  准确率      : {acc:.2%}")
    print(f"  宏平均F1    : {f1m:.4f}")
    print(f"  LogLoss     : {ll:.4f}")
    print(f"  基线(全押主胜): {base_home:.2%}   提升: {acc - base_home:+.2%}")
    print("\n  混淆矩阵 (行=实际, 列=预测):")
    cm = confusion_matrix(y[te], pred, labels=[0, 1, 2])
    print("            " + "".join(f"{l:>8}" for l in LABELS))
    for i, l in enumerate(LABELS):
        print(f"    {l:<6}" + "".join(f"{v:>8}" for v in cm[i]))
    per_class = []
    for i, l in enumerate(LABELS):
        m = y[te] == i
        r = (pred[m] == i).mean() if m.sum() else 0
        per_class.append((l, int(m.sum()), f"{r:.1%}"))
    print("\n  分类别召回: " + " | ".join(f"{l} {n}场 {r}" for l, n, r in per_class))

    print("\n  分联赛命中率:")
    for lg in pd.unique(leagues[te]):
        m = leagues[te] == lg
        if m.sum():
            print(f"    {lg:<6} {m.sum():>4} 场  {accuracy_score(y[te][m], pred[m]):.1%}")

    print("\n  预测分布: " + str({LABELS[k]: v for k, v in
                                sorted(Counter(pred).items())}))

    if args.save:
        mpath = BASE / "models" / "xgb_walkforward.joblib"
        import joblib
        joblib.dump({"model": model, "features": list(X.columns),
                     "cutoff": args.cutoff, "accuracy": acc}, str(mpath))
        res = {"cutoff": args.cutoff, "train": int(tr.sum()), "test": int(te.sum()),
               "accuracy": round(acc, 4), "macro_f1": round(f1m, 4),
               "log_loss": round(ll, 4), "baseline_home": round(float(base_home), 4),
               "per_class": per_class, "confusion": cm.tolist(),
               "pred_dist": {LABELS[k]: v for k, v in sorted(Counter(pred).items())}}
        with open(BASE / "models" / "walkforward_eval.json", "w", encoding="utf-8") as f:
            json.dump(res, f, ensure_ascii=False, indent=1)
        print(f"\n已保存: {mpath} 与 models/walkforward_eval.json")
    print("=" * 62)


if __name__ == "__main__":
    main()
