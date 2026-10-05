# -*- coding: utf-8 -*-
"""深度学习分支 - 序列特征构建

为每场比赛构造「主队近 N 场」和「客队近 N 场」的时序序列，供 GRU 编码器使用。

严格无未来信息：第 i 场比赛的序列只包含该场比赛**之前**的比赛，
通过按时间顺序遍历 + deque 快照实现，不使用 shift 之外的任何未来统计。

序列每一步的特征(12 维，全部来自"那一场"比赛本身):
    0 goals_for      进球
    1 goals_against  失球
    2 points/3       积分(胜3平1负0)
    3 shots_for      射门
    4 shots_against  被射门
    5 sot_for        射正
    6 sot_against    被射正
    7 corners_for    角球
    8 cards          红黄牌加权(黄1红2)
    9 is_home        是否主场
   10 xg_for         预期进球(官方 Understat，缺失为 0)
   11 xg_against     预期失球
"""
from collections import defaultdict, deque

import numpy as np
import pandas as pd

SEQ_DIM = 12
SEQ_COLS = ["goals_for", "goals_against", "points", "shots_for", "shots_against",
            "sot_for", "sot_against", "corners_for", "cards", "is_home",
            "xg_for", "xg_against"]


def _col(df, name, default=0.0):
    if name in df.columns:
        return pd.to_numeric(df[name], errors="coerce").fillna(default).to_numpy(dtype=float)
    return np.full(len(df), default, dtype=float)


def build_sequence_dataset(df: pd.DataFrame, n: int = 10):
    """构造序列样本

    Args:
        df: 与 vector_features_v2.load_matches(with_xg=True) 相同的比赛表，
            必须已按 Date 升序排列；行号即 match_id
        n:  序列长度(取最近 n 场)

    Returns:
        dict[mid] = (home_seq, home_len, away_seq, away_len)
        home_seq/away_seq: float32 (n, SEQ_DIM)，左边补零，越靠后越新
    """
    df = df.reset_index(drop=True)

    ftgh, ftag = _col(df, "FTHG"), _col(df, "FTAG")
    hs, as_ = _col(df, "HS"), _col(df, "AS")
    hst, ast = _col(df, "HST"), _col(df, "AST")
    hc, ac = _col(df, "HC"), _col(df, "AC")
    hy, ay = _col(df, "HY"), _col(df, "AY")
    hr, ar = _col(df, "HR"), _col(df, "AR")
    hxg = _col(df, "HomeXG") if "HomeXG" in df.columns else _col(df, "HxG")
    axg = _col(df, "AwayXG") if "AwayXG" in df.columns else _col(df, "AxG")

    teams_h = df["HomeTeam"].astype(str).to_numpy()
    teams_a = df["AwayTeam"].astype(str).to_numpy()

    hist = defaultdict(lambda: deque(maxlen=n))
    out = {}

    for i in range(len(df)):
        h, a = teams_h[i], teams_a[i]

        def snapshot(team):
            seq = np.zeros((n, SEQ_DIM), dtype=np.float32)
            past = hist[team]
            k = len(past)
            if k:
                seq[n - k:] = np.asarray(past, dtype=np.float32)
            return seq, k

        hs_seq, hs_len = snapshot(h)
        as_seq, as_len = snapshot(a)
        out[i] = (hs_seq, hs_len, as_seq, as_len)

        # 本场结束后才写入历史 —— 保证序列只看得到过去
        ph = 3.0 if ftgh[i] > ftag[i] else (1.0 if ftgh[i] == ftag[i] else 0.0)
        pa = 3.0 if ftag[i] > ftgh[i] else (1.0 if ftgh[i] == ftag[i] else 0.0)
        hist[h].append([ftgh[i], ftag[i], ph / 3.0, hs[i], as_[i], hst[i], ast[i],
                        hc[i], hy[i] + 2 * hr[i], 1.0, hxg[i], axg[i]])
        hist[a].append([ftag[i], ftgh[i], pa / 3.0, as_[i], hs[i], ast[i], hst[i],
                        ac[i], ay[i] + 2 * ar[i], 0.0, axg[i], hxg[i]])

    return out


def stack_sequences(seq_map, match_ids, n: int = 10):
    """把 dict 形式的序列整理成模型输入张量

    Returns:
        h_seq (M, n, SEQ_DIM), h_len (M,), a_seq (M, n, SEQ_DIM), a_len (M,)
    """
    m = len(match_ids)
    h_seq = np.zeros((m, n, SEQ_DIM), dtype=np.float32)
    a_seq = np.zeros((m, n, SEQ_DIM), dtype=np.float32)
    h_len = np.zeros(m, dtype=np.int64)
    a_len = np.zeros(m, dtype=np.int64)
    for j, mid in enumerate(match_ids):
        hs, hl, as_, al = seq_map[int(mid)]
        h_seq[j], h_len[j] = hs, hl
        a_seq[j], a_len[j] = as_, al
    return h_seq, h_len, a_seq, a_len


def fit_sequence_scaler(seqs, lengths):
    """只用训练集统计量做标准化

    Args:
        seqs:    [(M, n, F), ...] 序列数组列表
        lengths: [(M,), ...]      对应的有效长度列表
    Returns:
        mu, sd: (F,) 的均值与标准差
    """
    steps = []
    for seq, ln in zip(seqs, lengths):
        n = seq.shape[1]
        valid = np.arange(n)[None, :] >= (n - np.asarray(ln)[:, None])  # (M, n)
        if valid.any():
            steps.append(seq[valid])
    if not steps:
        return np.zeros(SEQ_DIM, dtype=np.float32), np.ones(SEQ_DIM, dtype=np.float32)
    allsteps = np.concatenate(steps, axis=0)
    mu = allsteps.mean(axis=0).astype(np.float32)
    sd = allsteps.std(axis=0).astype(np.float32)
    sd[sd < 1e-6] = 1.0
    return mu, sd


def scale_sequences(seq, lengths, mu, sd):
    """标准化；padding 位置保持 0，避免污染 GRU 的 pack 结果"""
    out = np.zeros_like(seq, dtype=np.float32)
    for i in range(seq.shape[0]):
        ln = int(lengths[i])
        if ln > 0:
            out[i, -ln:] = (seq[i, -ln:] - mu) / sd
    return out
