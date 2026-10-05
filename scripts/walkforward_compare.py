# -*- coding: utf-8 -*-
"""v1 vs v2 模型对比 (严格样本外 walk-forward)

v1: Elo + 状态 + 攻防 (无射门/角球/牌/休息/交锋/联赛)
v2: v1 + 射门/射正/角球/红黄牌/休息天数/赛程负荷/历史交锋/联赛标识
    + 类别权重(缓解平局盲区)
    + 平局阈值调优(在训练期末尾的验证段上选, 不碰测试集)

用法:
    python scripts/walkforward_compare.py --cutoff 2025-08-01
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
from sklearn.metrics import accuracy_score, confusion_matrix, f1_score, log_loss

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.prediction import vector_features as v1  # noqa: E402
from src.prediction import vector_features_v2 as v2  # noqa: E402

BASE = Path(__file__).parent.parent
LABELS = ["主胜", "平局", "客胜"]
PARAMS = dict(objective="multi:softprob", num_class=3, n_estimators=300, max_depth=5,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              reg_alpha=0.1, reg_lambda=1.0, random_state=42, eval_metric="mlogloss")


def metrics(y, proba, pred):
    return {
        "acc": accuracy_score(y, pred),
        "f1_macro": f1_score(y, pred, average="macro"),
        "logloss": log_loss(y, proba, labels=[0, 1, 2]),
        "draw_recall": float((pred[y == 1] == 1).mean()) if (y == 1).sum() else 0.0,
        "pred_dist": {LABELS[k]: int(v) for k, v in sorted(Counter(pred).items())},
    }


def tune_threshold_cv(Xtr, ytr, seed=42, n_splits=3):
    """在训练数据内部用时间序列CV选出平局阈值(不碰测试集)"""
    from sklearn.model_selection import TimeSeriesSplit
    tscv = TimeSeriesSplit(n_splits=n_splits)
    ths = []
    for tr_idx, va_idx in tscv.split(Xtr):
        m = xgb.XGBClassifier(**PARAMS)
        Xa = Xtr.iloc[tr_idx] if hasattr(Xtr, "iloc") else Xtr[tr_idx]
        Xb = Xtr.iloc[va_idx] if hasattr(Xtr, "iloc") else Xtr[va_idx]
        cnt = np.bincount(ytr[tr_idx], minlength=3).astype(float)
        w = len(tr_idx) / (3 * np.maximum(cnt, 1))
        m.fit(Xa, ytr[tr_idx], sample_weight=w[ytr[tr_idx]], verbose=False)
        pv = m.predict_proba(Xb)
        best = (-1, 0.33)
        for t in np.arange(0.18, 0.50, 0.01):
            p = np.where(pv[:, 1] >= t, 1,
                         np.argmax(np.delete(pv, 1, axis=1), axis=1) * 2)
            p = np.where(p == 2, 2, p)
            f1 = f1_score(ytr[va_idx], p, average="macro")
            if f1 > best[0]:
                best = (f1, float(t))
        ths.append(best[1])
    return round(float(np.mean(ths)), 3) if ths else 0.33


def fit_eval(name, X, y, dates, cutoff, use_weights, tune_draw):
    tr = dates < cutoff
    te = dates >= cutoff
    Xtr, ytr = X[tr], y[tr]
    model = xgb.XGBClassifier(**PARAMS)
    if use_weights:
        cnt = np.bincount(ytr, minlength=3).astype(float)
        w = len(ytr) / (3 * np.maximum(cnt, 1))
        model.fit(Xtr, ytr, sample_weight=w[ytr], verbose=False)
    else:
        model.fit(Xtr, ytr, verbose=False)

    th = 0.5
    if tune_draw:
        th = tune_threshold_cv(Xtr, ytr)

    proba = model.predict_proba(X[te])
    if tune_draw:
        p = np.where(proba[:, 1] >= th, 1,
                     np.argmax(np.delete(proba, 1, axis=1), axis=1) * 2)
        pred = np.where(p == 2, 2, p)
    else:
        pred = proba.argmax(axis=1)

    m = metrics(y[te], proba, pred)
    m.update({"model": name, "features": X.shape[1], "train": int(tr.sum()),
              "test": int(te.sum()), "weights": use_weights, "draw_threshold": th})
    return m, pred, y[te], proba


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2025-08-01")
    args = ap.parse_args()
    cutoff = pd.Timestamp(args.cutoff)

    df = v1.load_matches()
    df_xg = v2.load_matches(with_xg=True)      # 含官方 xG(Understat) 的训练集
    results = []
    print("=" * 66)
    print(f"严格样本外对比 (训练 < {cutoff.date()})")
    print("=" * 66)
    print(f"训练集: 基础 {len(df):,} 场 | 含官方 xG {df_xg['HomeXG'].notna().sum():,} 场")

    for name, mod, weights, tune, proxy, tm, official in [
        ("v1 基线(当前线上特征)", v1, False, False, False, False, False),
        ("v2 新特征", v2, False, False, False, False, False),
        ("v3 v2+代理xG", v2, False, False, True, False, False),
        ("v4 v2+TM身价/伤病", v2, False, False, False, True, False),
        ("v5 v2+代理xG+TM", v2, False, False, True, True, False),
        ("v6 v2+官方xG", v2, False, False, False, False, True),
        ("v7 v2+官方xG+TM", v2, False, False, False, True, True),
        ("v8 v2+官方xG+权重+阈值", v2, True, True, False, False, True),
        ("v2 + 类别权重", v2, True, False, False, False, False),
        ("v2 + 权重 + 平局阈值CV", v2, True, True, False, False, False),
    ]:
        builder = getattr(mod, "build_features", None) or mod.build_features_v2
        if getattr(mod, "__name__", "").endswith("vector_features_v2"):
            data = df_xg if official else df
            X, y, dates, divs, leagues = builder(data, use_proxy_xg=proxy, use_tm=tm,
                                                 use_official_xg=official)
        else:
            X, y, dates, divs, leagues = builder(df)
        dates = pd.to_datetime(dates)
        m, pred, ytest, proba = fit_eval(name, X, y, dates, cutoff, weights, tune)
        base = (ytest == 0).mean()
        m["baseline_home"] = float(base)
        m["edge_vs_baseline"] = float(m["acc"] - base)
        results.append(m)
        print(f"\n【{name}】特征 {m['features']} 维 | 训练 {m['train']} / 测试 {m['test']}")
        print(f"  准确率 {m['acc']:.2%} (基线 {base:.2%}, 优势 {m['edge_vs_baseline']:+.2%})")
        print(f"  宏F1 {m['f1_macro']:.4f} | LogLoss {m['logloss']:.4f} | "
              f"平局召回 {m['draw_recall']:.1%} | 阈值 {m['draw_threshold']}")
        print(f"  预测分布 {m['pred_dist']}")

    print("\n" + "=" * 66)
    print("汇总(按准确率排序):")
    for m in sorted(results, key=lambda x: -x["acc"]):
        print(f"  {m['model']:<24} acc={m['acc']:.2%}  宏F1={m['f1_macro']:.4f}  "
              f"平局召回={m['draw_recall']:>5.1%}  LogLoss={m['logloss']:.4f}")

    out = BASE / "models" / "walkforward_compare.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"cutoff": args.cutoff, "results": results}, f,
                  ensure_ascii=False, indent=1)
    print(f"\n已保存: {out}")


if __name__ == "__main__":
    main()
