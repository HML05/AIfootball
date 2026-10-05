# -*- coding: utf-8 -*-
"""深度学习分支实验 —— 与 XGBoost 在同一 walk-forward 协议下对比

协议与 scripts/walkforward_compare.py 完全一致，保证可比性：
    训练集 < cutoff(默认 2025-08-01)，测试集 >= cutoff（完全不参与训练）
    特征与 v7 相同（126 维：v2 + 官方 xG + Transfermarkt 身价/伤病）

对比对象：
    XGB-v2        90 维，样本外 50.03%（docs/模型评估报告.md）
    XGB-v7        126 维
    DL-MLP        126 维表格特征的多层感知机（同输入对照）
    DL-GRU        126 维 + 主客队近 10 场序列的 GRU 孪生编码器
    集成          概率平均

防泄漏与防作弊：
    - 序列只用该场比赛之前的比赛（dl_features 里按时间顺序 deque 快照）
    - 早停用的验证集取自**训练期末尾**，绝不触碰测试集
    - 标准化统计量只在训练集上拟合

用法：
    python scripts/train_dl.py                      # 完整实验(3 个随机种子)
    python scripts/train_dl.py --quick              # 快速冒烟(1 种子 20 轮)
    python scripts/train_dl.py --seeds 5 --epochs 200
"""
import argparse
import json
import os
import sys
import time
import warnings
from collections import Counter
from pathlib import Path

warnings.filterwarnings("ignore")

import numpy as np
import pandas as pd
import torch
import torch.nn as nn
import xgboost as xgb
from sklearn.metrics import accuracy_score, f1_score, log_loss
from sklearn.preprocessing import StandardScaler

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))

from src.prediction import vector_features_v2 as v2                      # noqa: E402
from src.prediction.dl_features import (SEQ_DIM, build_sequence_dataset,  # noqa: E402
                                        fit_sequence_scaler, scale_sequences,
                                        stack_sequences)
from src.prediction.dl_model import build_model, count_params            # noqa: E402

LABELS = ["主胜", "平局", "客胜"]
XGB_PARAMS = dict(objective="multi:softprob", num_class=3, n_estimators=300,
                  max_depth=5, learning_rate=0.05, subsample=0.8,
                  colsample_bytree=0.8, reg_alpha=0.1, reg_lambda=1.0,
                  random_state=42, eval_metric="mlogloss")
SEQ_LEN = 10


# --------------------------------------------------------------------------
# 指标（与 walkforward_compare.py 保持一致）
# --------------------------------------------------------------------------
def metrics(y, proba, pred):
    return {
        "acc": float(accuracy_score(y, pred)),
        "f1_macro": float(f1_score(y, pred, average="macro")),
        "logloss": float(log_loss(y, proba, labels=[0, 1, 2])),
        "draw_recall": float((pred[y == 1] == 1).mean()) if (y == 1).sum() else 0.0,
        "pred_dist": {LABELS[k]: int(v) for k, v in sorted(Counter(pred).items())},
    }


# --------------------------------------------------------------------------
# PyTorch 训练
# --------------------------------------------------------------------------
def fit_torch(kind, tab_tr, seq_tr, y_tr, tab_te, seq_te, seed,
              epochs=120, batch=256, lr=1e-3, wd=1e-4, patience=12,
              val_frac=0.12, class_weight=False, dropout=0.3, verbose=False,
              save=True):
    """训练一个深度学习模型，返回测试集概率

    seq_tr/seq_te: (h_seq, h_len, a_seq, a_len) 或 None(MLP 不需要)
    """
    torch.manual_seed(seed)
    np.random.seed(seed)
    torch.set_num_threads(max(1, (os.cpu_count() or 4) - 1))

    n = len(y_tr)
    n_val = max(400, int(n * val_frac))
    tr_idx = np.arange(0, n - n_val)      # 数据按时间升序 -> 末尾做验证
    va_idx = np.arange(n - n_val, n)

    # 标准化：只用训练段拟合
    sc = StandardScaler().fit(tab_tr[tr_idx])
    Xtr = sc.transform(tab_tr[tr_idx]).astype(np.float32)
    Xva = sc.transform(tab_tr[va_idx]).astype(np.float32)
    Xte = sc.transform(tab_te).astype(np.float32)

    use_seq = seq_tr is not None
    if use_seq:
        h_va, hl_va, a_va, al_va = [x[va_idx] for x in seq_tr]
        h_trx, hl_trx, a_trx, al_trx = [x[tr_idx] for x in seq_tr]
        h_te, hl_te, a_te, al_te = seq_te
        mu, sd = fit_sequence_scaler([h_trx, a_trx], [hl_trx, al_trx])
        h_trx = scale_sequences(h_trx, hl_trx, mu, sd)
        a_trx = scale_sequences(a_trx, al_trx, mu, sd)
        h_va = scale_sequences(h_va, hl_va, mu, sd)
        a_va = scale_sequences(a_va, al_va, mu, sd)
        h_te = scale_sequences(h_te, hl_te, mu, sd)
        a_te = scale_sequences(a_te, al_te, mu, sd)

    def tf(a):
        return torch.tensor(a, dtype=torch.float32)

    def ti(a):
        return torch.tensor(a, dtype=torch.int64)

    if use_seq:
        tr_pack = [tf(Xtr), tf(h_trx), ti(hl_trx), tf(a_trx), ti(al_trx)]
        va_pack = [tf(Xva), tf(h_va), ti(hl_va), tf(a_va), ti(al_va)]
        te_pack = [tf(Xte), tf(h_te), ti(hl_te), tf(a_te), ti(al_te)]
        kw = dict(seq_dim=SEQ_DIM, hidden=32, tab_hidden=64, head=64, dropout=dropout)
    else:
        tr_pack = [tf(Xtr)]
        va_pack = [tf(Xva)]
        te_pack = [tf(Xte)]
        kw = dict(hidden=128, dropout=dropout)

    model = build_model("gru" if use_seq else "mlp", tab_tr.shape[1], **kw)
    opt = torch.optim.AdamW(model.parameters(), lr=lr, weight_decay=wd)
    sched = torch.optim.lr_scheduler.ReduceLROnPlateau(opt, mode="min",
                                                       factor=0.5, patience=5)

    ytr_t = torch.tensor(y_tr[tr_idx], dtype=torch.long)
    yva_t = torch.tensor(y_tr[va_idx], dtype=torch.long)
    if class_weight:
        cnt = np.bincount(y_tr[tr_idx], minlength=3).astype(float)
        w = torch.tensor(len(tr_idx) / (3 * np.maximum(cnt, 1)), dtype=torch.float32)
        crit = nn.CrossEntropyLoss(weight=w)
    else:
        crit = nn.CrossEntropyLoss()

    best = {"loss": float("inf"), "epoch": -1, "state": None}
    rng = np.random.default_rng(seed)
    for ep in range(1, epochs + 1):
        model.train()
        perm = rng.permutation(len(tr_idx))
        for s in range(0, len(perm), batch):
            b = perm[s:s + batch]
            opt.zero_grad()
            out = model(*[x[b] for x in tr_pack])
            loss = crit(out, ytr_t[b])
            loss.backward()
            nn.utils.clip_grad_norm_(model.parameters(), 5.0)
            opt.step()

        model.eval()
        with torch.no_grad():
            logits = model(*va_pack)
            vl = float(crit(logits, yva_t))
        sched.step(vl)
        if vl < best["loss"] - 1e-5:
            best = {"loss": vl, "epoch": ep,
                    "state": {k: t.detach().clone() for k, t in model.state_dict().items()}}
        elif ep - best["epoch"] >= patience:
            break

    model.load_state_dict(best["state"])
    model.eval()
    with torch.no_grad():
        proba = torch.softmax(model(*te_pack), dim=1).numpy()

    info = {"params": count_params(model), "best_epoch": best["epoch"],
            "best_val_logloss": round(best["loss"], 4), "epochs_run": ep}

    # 保存 GRU 模型及其标准化参数，供推理复用
    if save and use_seq:
        torch.save({"state_dict": best["state"], "model_kwargs": kw,
                    "tab_dim": int(tab_tr.shape[1]), "seq_dim": SEQ_DIM,
                    "seq_len": SEQ_LEN,
                    "tab_mean": sc.mean_.tolist(), "tab_scale": sc.scale_.tolist(),
                    "seq_mu": mu.tolist(), "seq_sd": sd.tolist()},
                   BASE / "models" / "dl_gru.pt")
    elif save:
        torch.save({"state_dict": best["state"], "model_kwargs": kw,
                    "tab_dim": int(tab_tr.shape[1]),
                    "tab_mean": sc.mean_.tolist(), "tab_scale": sc.scale_.tolist()},
                   BASE / "models" / "dl_mlp.pt")

    return proba, info, model


def xgb_proba(X, y, dates, cutoff):
    tr = dates < cutoff
    m = xgb.XGBClassifier(**XGB_PARAMS)
    m.fit(X[tr], y[tr], verbose=False)
    p = m.predict_proba(X[~tr])
    return p, int(tr.sum()), int((~tr).sum())


def report(name, y, dates, cutoff, proba, extra=None):
    te = dates >= cutoff
    pred = proba.argmax(axis=1)
    m = metrics(y[te], proba, pred)
    base = float((y[te] == 0).mean())
    m.update({"model": name, "baseline_home": base,
              "edge_vs_baseline": m["acc"] - base})
    if extra:
        m.update(extra)
    return m


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cutoff", default="2025-08-01")
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--epochs", type=int, default=120)
    ap.add_argument("--seq-len", type=int, default=10)
    ap.add_argument("--quick", action="store_true")
    args = ap.parse_args()
    if args.quick:
        args.seeds, args.epochs = 1, 20

    cutoff = pd.Timestamp(args.cutoff)
    t_start = time.time()
    print("=" * 74)
    print(f"深度学习分支实验 | 严格样本外 walk-forward (训练 < {cutoff.date()})")
    print("=" * 74)

    df = v2.load_matches(with_xg=True)
    X7, y, dates, divs, leagues, mids = v2.build_features_v2(
        df, use_official_xg=True, use_tm=True, return_ids=True)
    X2, y2, dates2, _, _ = v2.build_features_v2(df)
    assert (y == y2).all() and (dates == dates2).all(), "两套特征样本顺序必须一致"
    dates = pd.to_datetime(dates)

    global SEQ_LEN
    SEQ_LEN = args.seq_len
    print(f"样本 {len(y):,} 场 | v7 特征 {X7.shape[1]} 维 | 序列长度 {SEQ_LEN}")
    print(f"训练 {int((dates < cutoff).sum()):,} 场 | 测试 {int((dates >= cutoff).sum()):,} 场")

    t0 = time.time()
    seq_map = build_sequence_dataset(df, n=SEQ_LEN)
    seq_all = stack_sequences(seq_map, mids, n=SEQ_LEN)
    print(f"序列构造完成: {time.time() - t0:.1f}s | "
          f"形状 {seq_all[0].shape} | 平均主队历史 {seq_all[1].mean():.1f} 场")

    tr = np.asarray(dates < cutoff)
    te = np.asarray(dates >= cutoff)
    seq_tr = tuple(x[tr] for x in seq_all)
    seq_te = tuple(x[te] for x in seq_all)
    Xtr7, Xte7 = X7.values[tr], X7.values[te]
    Xtr2, Xte2 = X2.values[tr], X2.values[te]

    results = []

    # ---- XGBoost 参照 ----
    xgb_probs = {}
    for name, Xtr_, Xte_ in [("XGB-v2 (90维)", Xtr2, Xte2),
                             ("XGB-v7 (126维)", Xtr7, Xte7)]:
        t0 = time.time()
        m = xgb.XGBClassifier(**XGB_PARAMS)
        m.fit(Xtr_, y[tr], verbose=False)
        p = m.predict_proba(Xte_)
        xgb_probs[name] = p
        results.append(report(name, y, dates, cutoff, p,
                              {"secs": round(time.time() - t0, 1)}))
        print(f"  {name}: acc={results[-1]['acc']:.2%}")

    p_xgb2, p_xgb7 = xgb_probs["XGB-v2 (90维)"], xgb_probs["XGB-v7 (126维)"]

    # ---- 深度学习 ----
    dl_proba = {}
    for kind, use_seq in [("DL-MLP (126维表格)", False), ("DL-GRU (表格+序列)", True)]:
        t0 = time.time()
        probs, infos = [], []
        for s in range(args.seeds):
            sd = 42 + s * 7
            p, info, _ = fit_torch(kind, Xtr7, seq_tr if use_seq else None, y[tr],
                                   Xte7, seq_te if use_seq else None, seed=sd,
                                   epochs=args.epochs)
            probs.append(p)
            infos.append(info)
            acc_s = accuracy_score(y[te], p.argmax(axis=1))
            print(f"  {kind} seed{sd}: acc={acc_s:.2%} "
                  f"val={info['best_val_logloss']} ep={info['best_epoch']}")
        mean_p = np.mean(probs, axis=0)
        dl_proba[kind] = mean_p
        accs = [accuracy_score(y[te], p.argmax(axis=1)) for p in probs]
        results.append(report(kind, y, dates, cutoff, mean_p, {
            "features": int(X7.shape[1]), "seq_len": SEQ_LEN if use_seq else 0,
            "seeds": args.seeds, "params": infos[0]["params"],
            "acc_per_seed": [round(a, 4) for a in accs],
            "acc_std": round(float(np.std(accs)), 4),
            "secs": round(time.time() - t0, 1),
        }))
        # 单种子指标（最接近"一次训练"的真实水平）
        results.append(report(kind + " (单种子)", y, dates, cutoff, probs[0]))
        print(f"  -> {kind} 多种子平均 acc={results[-2]['acc']:.2%} "
              f"(单种子 {results[-1]['acc']:.2%}, 种子间标准差 {np.std(accs):.2%})")

    # ---- 集成 ----
    combos = [
        ("集成 XGB-v2 + XGB-v7 (v9)", (p_xgb2 + p_xgb7) / 2),
        ("集成 XGB-v7 + DL-GRU", (p_xgb7 + dl_proba["DL-GRU (表格+序列)"]) / 2),
        ("集成 XGB-v2 + XGB-v7 + DL-GRU",
         (p_xgb2 + p_xgb7 + dl_proba["DL-GRU (表格+序列)"]) / 3),
    ]
    for name, p in combos:
        results.append(report(name, y, dates, cutoff, p))

    # ---- 汇总 ----
    print("\n" + "=" * 74)
    print(f"{'方案':<34}{'准确率':>9}{'宏F1':>9}{'LogLoss':>10}{'平局召回':>10}")
    print("-" * 74)
    for m in sorted(results, key=lambda r: -r["acc"]):
        print(f"{m['model']:<34}{m['acc']:>8.2%}{m['f1_macro']:>9.4f}"
              f"{m['logloss']:>10.4f}{m['draw_recall']:>10.1%}")
    print("-" * 74)
    base = float((y[te] == 0).mean())
    print(f"基线(全押主胜) {base:.2%} | 测试集 {int(te.sum()):,} 场 | "
          f"总耗时 {time.time() - t_start:.0f}s")

    out = BASE / "models" / "dl_report.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump({"cutoff": args.cutoff, "seq_len": SEQ_LEN, "seeds": args.seeds,
                   "epochs": args.epochs, "n_train": int(tr.sum()),
                   "n_test": int(te.sum()), "baseline_home": base,
                   "results": results}, f, ensure_ascii=False, indent=1)
    print(f"已保存: {out}")


if __name__ == "__main__":
    main()
