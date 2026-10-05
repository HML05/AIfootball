# -*- coding: utf-8 -*-
"""深度学习分支 —— 稳健性与泄漏检验

回答两个会被追问的问题：

1. 「深度学习比 XGBoost 高 2 个点，是不是运气？」
   -> 换 3 个时间切点各跑一遍（2024-08-01 / 2025-02-01 / 2025-08-01），看结论是否稳定；
      并对同一切点的两两差异做 McNemar 检验（配对，同一批测试比赛）。

2. 「是不是有数据泄漏？」
   -> 标签置换检验：把训练集标签随机打乱后重新训练，
      若管线里存在未来信息，模型在测试集上仍会明显高于基线；
      正常情况应退化到「全押主胜」基线附近。

用法：
    python scripts/dl_robustness.py
    python scripts/dl_robustness.py --cutoffs 2024-08-01,2025-02-01,2025-08-01 --seeds 3
"""
import argparse
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import accuracy_score, log_loss

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
sys.path.insert(0, str(BASE / "scripts"))

import train_dl as T                                                    # noqa: E402
from src.prediction import vector_features_v2 as v2                      # noqa: E402
from src.prediction.dl_features import (build_sequence_dataset,         # noqa: E402
                                        stack_sequences)

DEFAULT_CUTOFFS = ["2024-08-01", "2025-02-01", "2025-08-01"]


def mcnemar(y_true, pred_a, pred_b):
    """配对 McNemar 检验：a 与 b 在同一批测试样本上的差异是否显著

    返回 (b, c, p_value)，b=仅 a 对，c=仅 b 对
    """
    a_ok, b_ok = (pred_a == y_true), (pred_b == y_true)
    b = int(np.sum(a_ok & ~b_ok))
    c = int(np.sum(~a_ok & b_ok))
    n = b + c
    if n == 0:
        return b, c, 1.0
    try:
        from scipy.stats import binomtest
        p = float(binomtest(b, n, 0.5, alternative="two-sided").pvalue)
    except Exception:                       # 没有 scipy 时用正态近似
        from math import erfc, sqrt
        z = abs(b - c) / sqrt(n)
        p = float(erfc(z / sqrt(2)))
    return b, c, p


def fit_xgb(Xtr, ytr, Xte):
    return xgb.XGBClassifier(**T.XGB_PARAMS).fit(Xtr, ytr, verbose=False).predict_proba(Xte)


def evaluate_cutoff(cutoff, X2, X7, y, dates, seq_all, seeds, epochs, save_models):
    tr = np.asarray(dates < cutoff)
    te = np.asarray(dates >= cutoff)
    seq_tr = tuple(x[tr] for x in seq_all)
    seq_te = tuple(x[te] for x in seq_all)
    Xtr2, Xte2 = X2.values[tr], X2.values[te]
    Xtr7, Xte7 = X7.values[tr], X7.values[te]
    meta = {"cutoff": str(cutoff.date()), "n_train": int(tr.sum()), "n_test": int(te.sum())}

    print(f"\n{'-' * 74}\n切点 {cutoff.date()} | 训练 {tr.sum():,} 场 | 测试 {te.sum():,} 场\n{'-' * 74}")

    p2 = fit_xgb(Xtr2, y[tr], Xte2)
    p7 = fit_xgb(Xtr7, y[tr], Xte7)
    res = [T.report("XGB-v2", y, dates, cutoff, p2, dict(meta)),
           T.report("XGB-v7", y, dates, cutoff, p7, dict(meta))]

    probs_mlp, probs_gru = [], []
    for s in range(seeds):
        sd = 42 + s * 7
        pm, _, _ = T.fit_torch("mlp", Xtr7, None, y[tr], Xte7, None, seed=sd,
                               epochs=epochs, save=False)
        pg, _, _ = T.fit_torch("gru", Xtr7, seq_tr, y[tr], Xte7, seq_te, seed=sd,
                               epochs=epochs, save=(save_models and s == 0))
        probs_mlp.append(pm)
        probs_gru.append(pg)
        print(f"  seed{sd}: MLP {accuracy_score(y[te], pm.argmax(1)):.2%} | "
              f"GRU {accuracy_score(y[te], pg.argmax(1)):.2%}")

    m_mlp, m_gru = np.mean(probs_mlp, 0), np.mean(probs_gru, 0)
    res.append(T.report("DL-MLP", y, dates, cutoff, m_mlp,
                        dict(meta, seeds=seeds,
                             acc_std=round(float(np.std(
                                 [accuracy_score(y[te], p.argmax(1)) for p in probs_mlp])), 4))))
    res.append(T.report("DL-GRU", y, dates, cutoff, m_gru,
                        dict(meta, seeds=seeds,
                             acc_std=round(float(np.std(
                                 [accuracy_score(y[te], p.argmax(1)) for p in probs_gru])), 4))))
    res.append(T.report("集成 XGB-v2+v7 (v9)", y, dates, cutoff, (p2 + p7) / 2, dict(meta)))
    res.append(T.report("集成 XGB-v7+DL-GRU", y, dates, cutoff, (p7 + m_gru) / 2, dict(meta)))

    # 显著性检验（同一批测试比赛，配对比较）
    yte = y[te]
    for a_name, a_p, b_name, b_p in [
        ("DL-MLP", m_mlp, "XGB-v2", p2),
        ("DL-GRU", m_gru, "XGB-v2", p2),
        ("DL-MLP", m_mlp, "XGB-v7", p7),
    ]:
        b, c, pval = mcnemar(yte, a_p.argmax(1), b_p.argmax(1))
        print(f"  McNemar {a_name} vs {b_name}: 仅{a_name}对={b} 仅{b_name}对={c} p={pval:.3f}"
              f" {'(显著)' if pval < 0.05 else '(不显著)'}")
        for r in res:
            if r["model"] == a_name:
                r.setdefault("mcnemar", {})[b_name] = {"only_a": b, "only_b": c,
                                                       "p_value": round(pval, 4)}
    return res


def leakage_test(X7, y, dates, cutoff, epochs, seeds=1):
    """标签置换检验：打乱训练标签后，测试集表现应退化到基线附近"""
    tr = np.asarray(dates < cutoff)
    te = np.asarray(dates >= cutoff)
    Xtr, Xte = X7.values[tr], X7.values[te]
    rng = np.random.default_rng(0)
    y_shuf = y[tr].copy()
    rng.shuffle(y_shuf)

    probs = []
    for s in range(seeds):
        p, _, _ = T.fit_torch("mlp", Xtr, None, y_shuf, Xte, None, seed=42 + s * 7,
                              epochs=epochs, save=False)
        probs.append(p)
    p = np.mean(probs, 0)
    acc = accuracy_score(y[te], p.argmax(1))
    ll = log_loss(y[te], p, labels=[0, 1, 2])
    base = float((y[te] == 0).mean())
    print(f"\n{'-' * 74}\n泄漏检验（打乱训练标签，切点 {cutoff.date()}）\n{'-' * 74}")
    print(f"  打乱标签后测试集: 准确率 {acc:.2%} | LogLoss {ll:.4f} | "
          f"基线 {base:.2%} | 随机猜测 LogLoss {np.log(3):.4f}")
    print("  判读: 准确率应≈基线、LogLoss 应≈1.05+；若仍高达 50% 则说明管线存在泄漏")
    return {"acc": float(acc), "logloss": float(ll), "baseline": base}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoffs", default=",".join(DEFAULT_CUTOFFS))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--seq-len", type=int, default=10)
    ap.add_argument("--skip-leak", action="store_true")
    args = ap.parse_args()

    cutoffs = [pd.Timestamp(c.strip()) for c in args.cutoffs.split(",")]
    T.SEQ_LEN = args.seq_len
    canonical = max(cutoffs)          # 最新切点作为正式模型并存盘

    t0 = time.time()
    print("=" * 74)
    print("深度学习分支 —— 多切点稳健性 + 泄漏检验")
    print("=" * 74)

    df = v2.load_matches(with_xg=True)
    X7, y, dates, divs, leagues, mids = v2.build_features_v2(
        df, use_official_xg=True, use_tm=True, return_ids=True)
    X2, y2, dates2, _, _ = v2.build_features_v2(df)
    assert (y == y2).all() and (dates == dates2).all()
    dates = pd.to_datetime(dates)
    seq_all = stack_sequences(build_sequence_dataset(df, n=args.seq_len), mids,
                              n=args.seq_len)
    print(f"样本 {len(y):,} 场 | v7 {X7.shape[1]} 维 | 序列 {args.seq_len} | "
          f"种子数 {args.seeds}")

    all_results = []
    for cut in cutoffs:
        all_results += evaluate_cutoff(cut, X2, X7, y, dates, seq_all,
                                       args.seeds, args.epochs, save_models=(cut == canonical))

    # ---- 跨切点汇总 ----
    names = ["XGB-v2", "XGB-v7", "DL-MLP", "DL-GRU", "集成 XGB-v2+v7 (v9)", "集成 XGB-v7+DL-GRU"]
    print("\n" + "=" * 74)
    print("跨切点汇总（准确率）")
    print("=" * 74)
    print(f"{'方案':<26}" + "".join(f"{str(c.date()):>13}" for c in cutoffs) + f"{'均值':>10}")
    print("-" * 74)
    summary = {}
    for n in names:
        accs = [r["acc"] for r in all_results if r["model"] == n]
        if not accs:
            continue
        summary[n] = {"accs": [round(a, 4) for a in accs],
                      "mean_acc": round(float(np.mean(accs)), 4)}
        row = f"{n:<26}" + "".join(f"{a:>12.2%} " for a in accs)
        print(row + f"{np.mean(accs):>9.2%}")
    print("-" * 74)
    for cut in cutoffs:
        base = float((y[np.asarray(dates >= cut)] == 0).mean())
        print(f"  切点 {cut.date()} 基线(全押主胜) {base:.2%}")

    leak = None
    if not args.skip_leak:
        leak = leakage_test(X7, y, dates, canonical, args.epochs)

    out = BASE / "models" / "dl_robustness.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"cutoffs": [str(c.date()) for c in cutoffs], "seeds": args.seeds,
                   "epochs": args.epochs, "summary": summary,
                   "results": all_results, "leakage_test": leak}, f,
                  ensure_ascii=False, indent=1)
    print(f"\n已保存: {out}  (总耗时 {time.time() - t0:.0f}s)")


if __name__ == "__main__":
    main()
