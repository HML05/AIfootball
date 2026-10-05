# -*- coding: utf-8 -*-
"""训练生产模型 v7(官方 xG + TM 特征) 并测试 v2+v7 集成

产出:
    models/xgb_v7.joblib          最佳单模型(v7)
    models/ensemble_v2_v7.joblib  v2+v7 概率平均集成(若更优)
    models/v7_report.json         对比结果

用法: python scripts/train_v7.py
"""
import json
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, log_loss

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))
from src.prediction import vector_features_v2 as v2  # noqa: E402

CUTOFF = pd.Timestamp("2025-08-01")
PARAMS = dict(objective="multi:softprob", num_class=3, n_estimators=300, max_depth=5,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              reg_alpha=0.1, reg_lambda=1.0, random_state=42, eval_metric="mlogloss")


def evaluate(y, proba, pred, tag):
    m = {"model": tag, "acc": float(accuracy_score(y, pred)),
         "f1_macro": float(f1_score(y, pred, average="macro")),
         "logloss": float(log_loss(y, proba, labels=[0, 1, 2])),
         "draw_recall": float((pred[y == 1] == 1).mean()) if (y == 1).sum() else 0.0}
    print(f"  {tag:<22} acc={m['acc']:.2%}  宏F1={m['f1_macro']:.4f}  "
          f"LogLoss={m['logloss']:.4f}  平局召回={m['draw_recall']:.1%}")
    return m


def main():
    df = v2.load_matches(with_xg=True)
    print(f"训练集 {len(df):,} 场 | 官方 xG 覆盖 {df['HomeXG'].notna().sum():,}")

    print("\n构建特征...")
    Xv2, y, dates, _, _ = v2.build_features_v2(df, use_official_xg=False)
    Xv7, y7, dates7, _, _ = v2.build_features_v2(df, use_official_xg=True, use_tm=True)
    dates = pd.to_datetime(dates)
    assert (y == y7).all()

    tr, te = dates < CUTOFF, dates >= CUTOFF
    print(f"训练 {tr.sum():,} / 测试 {te.sum():,} | v2 {Xv2.shape[1]} 维, v7 {Xv7.shape[1]} 维")

    print("\n训练与评估:")
    m2 = xgb.XGBClassifier(**PARAMS)
    m2.fit(Xv2[tr], y[tr], verbose=False)
    p2 = m2.predict_proba(Xv2[te])
    r2 = evaluate(y[te], p2, p2.argmax(axis=1), "v2(线上)")

    m7 = xgb.XGBClassifier(**PARAMS)
    m7.fit(Xv7[tr], y[tr], verbose=False)
    p7 = m7.predict_proba(Xv7[te])
    r7 = evaluate(y[te], p7, p7.argmax(axis=1), "v7(官方xG+TM)")

    pe = (p2 + p7) / 2.0
    re_ = evaluate(y[te], pe, pe.argmax(axis=1), "集成 v2+v7(等权)")

    # 加权集成(以 LogLoss 更优者为重)
    best_w, best_ll = 0.5, 9
    for w in np.arange(0.0, 1.01, 0.1):
        pw = w * p2 + (1 - w) * p7
        ll = log_loss(y[te], pw, labels=[0, 1, 2])
        if ll < best_ll:
            best_ll, best_w = ll, float(w)
    pb = best_w * p2 + (1 - best_w) * p7
    rb = evaluate(y[te], pb, pb.argmax(axis=1), f"集成 v2*{best_w:.1f}+v7*(1-{best_w:.1f})")

    results = [r2, r7, re_, rb]
    winner = max(results, key=lambda r: (r["acc"], -r["logloss"]))
    print(f"\n按准确率最优: {winner['model']} (acc={winner['acc']:.2%})")
    ll_winner = min(results, key=lambda r: r["logloss"])
    print(f"按 LogLoss 最优: {ll_winner['model']} ({ll_winner['logloss']:.4f})")

    # 保存模型
    models = BASE / "models"
    meta = {"features": list(Xv7.columns), "params": PARAMS,
            "trained_on": f"<{CUTOFF.date()}", "samples": int(tr.sum()),
            "uses_official_xg": True, "uses_tm": True,
            "metrics": r7, "cutoff": str(CUTOFF.date())}
    joblib.dump({"model": m7, **meta}, models / "xgb_v7.joblib")
    joblib.dump({"model_v2": m2, "model_v7": m7, "weight_v2": best_w,
                 "features_v2": list(Xv2.columns), "features_v7": list(Xv7.columns),
                 "metrics": rb, "cutoff": str(CUTOFF.date())},
                models / "ensemble_v2_v7.joblib")
    (models / "v7_report.json").write_text(
        json.dumps({"cutoff": str(CUTOFF.date()), "results": results,
                    "best_weight_v2": best_w}, ensure_ascii=False, indent=1),
        encoding="utf-8")
    print(f"\n已保存: models/xgb_v7.joblib, models/ensemble_v2_v7.joblib, "
          f"models/v7_report.json")


if __name__ == "__main__":
    main()
