# -*- coding: utf-8 -*-
"""向量化特征构建(无未来信息) + 日期/联赛保留

与 scripts/train_model_fast.py 同源, 但额外返回 日期 与 联赛,
用于"按时间切分"的严格样本外回测 / 步进式训练。

要点:
- Elo 逐场递推(只用该场之前的信息)
- 各项统计均用 shift(1)/expanding, 不含当场及未来数据
"""
import os
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.parent.parent


def load_matches(csv_path=None) -> pd.DataFrame:
    p = Path(csv_path) if csv_path else BASE / "data" / "processed" / "all_matches.csv"
    df = pd.read_csv(p, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["result"] = df["FTR"].map({"H": 0, "D": 1, "A": 2})
    return df


def build_features(df: pd.DataFrame):
    """返回 (features_df, y, dates, leagues, leagues_cn)"""
    df = df.copy()
    df["match_id"] = range(len(df))

    home_df = df[["match_id", "Date", "HomeTeam", "FTHG", "FTAG", "FTR"]].copy()
    home_df["team"] = home_df["HomeTeam"]
    home_df["is_home"] = 1
    home_df["goals_for"] = home_df["FTHG"]
    home_df["goals_against"] = home_df["FTAG"]
    home_df["win"] = (home_df["FTR"] == "H").astype(int)
    home_df["draw"] = (home_df["FTR"] == "D").astype(int)
    home_df["loss"] = (home_df["FTR"] == "A").astype(int)
    home_df["points"] = home_df["win"] * 3 + home_df["draw"]

    away_df = df[["match_id", "Date", "AwayTeam", "FTHG", "FTAG", "FTR"]].copy()
    away_df["team"] = away_df["AwayTeam"]
    away_df["is_home"] = 0
    away_df["goals_for"] = away_df["FTAG"]
    away_df["goals_against"] = away_df["FTHG"]
    away_df["win"] = (away_df["FTR"] == "A").astype(int)
    away_df["draw"] = (away_df["FTR"] == "D").astype(int)
    away_df["loss"] = (away_df["FTR"] == "H").astype(int)
    away_df["points"] = away_df["win"] * 3 + away_df["draw"]

    tm = pd.concat([home_df, away_df], ignore_index=True)
    tm = tm.sort_values(["team", "Date"]).reset_index(drop=True)
    g = tm.groupby("team")

    for col in ["win", "draw", "loss", "points", "goals_for", "goals_against"]:
        tm[f"cum_{col}"] = g[col].shift(1).groupby(tm["team"]).cumsum().fillna(0)
    tm["cum_matches"] = g.cumcount()

    for w in (5, 10):
        for col in ["points", "goals_for", "goals_against", "win"]:
            tm[f"last{w}_{col}"] = g[col].transform(
                lambda x: x.shift(1).rolling(window=w, min_periods=1).sum()).fillna(0)

    hm = tm[tm["is_home"] == 1]
    aw = tm[tm["is_home"] == 0]
    for col in ["win", "draw", "loss", "goals_for", "goals_against"]:
        tm.loc[tm["is_home"] == 1, f"home_cum_{col}"] = \
            hm[col].shift(1).groupby(hm["team"]).cumsum().fillna(0)
        tm.loc[tm["is_home"] == 0, f"away_cum_{col}"] = \
            aw[col].shift(1).groupby(aw["team"]).cumsum().fillna(0)

    # Elo 逐场递推
    elo, home_elo, away_elo = {}, [], []
    for _, row in df.iterrows():
        h, a = row["HomeTeam"], row["AwayTeam"]
        he, ae = elo.get(h, 1500.0), elo.get(a, 1500.0)
        home_elo.append(he); away_elo.append(ae)
        adv, k = 65.0, 32.0
        exp_h = 1.0 / (1.0 + 10 ** ((ae - (he + adv)) / 400.0))
        actual_h = 1.0 if row["FTR"] == "H" else (0.5 if row["FTR"] == "D" else 0.0)
        delta = k * (1.0 + 0.1 * abs(row["FTHG"] - row["FTAG"])) * (actual_h - exp_h)
        elo[h], elo[a] = he + delta, ae - delta
    df["home_elo"], df["away_elo"] = home_elo, away_elo

    cols = ["match_id", "team", "cum_matches", "cum_win", "cum_draw", "cum_loss",
            "cum_points", "cum_goals_for", "cum_goals_against",
            "last5_points", "last5_goals_for", "last5_goals_against", "last5_win",
            "last10_points", "last10_goals_for", "last10_goals_against", "last10_win"]
    hf = tm[tm["is_home"] == 1][cols].copy().add_prefix("home_")
    hf = hf.rename(columns={"home_match_id": "match_id", "home_team": "HomeTeam"})
    af = tm[tm["is_home"] == 0][cols].copy().add_prefix("away_")
    af = af.rename(columns={"away_match_id": "match_id", "away_team": "AwayTeam"})

    r = df.merge(hf, on=["match_id", "HomeTeam"], how="left") \
          .merge(af, on=["match_id", "AwayTeam"], how="left")

    F = pd.DataFrame()
    F["home_elo"], F["away_elo"] = r["home_elo"], r["away_elo"]
    F["elo_diff"] = r["home_elo"] - r["away_elo"]
    F["elo_expected_home"] = 1.0 / (1.0 + 10 ** ((r["away_elo"] - (r["home_elo"] + 65.0)) / 400.0))
    F["home_elo_advantage"] = r["home_elo"] + 65.0 - r["away_elo"]
    F["home_ppg_5"] = r["home_last5_points"] / 5.0
    F["away_ppg_5"] = r["away_last5_points"] / 5.0
    F["home_ppg_10"] = r["home_last10_points"] / 10.0
    F["away_ppg_10"] = r["away_last10_points"] / 10.0
    F["home_goals_for_5"] = r["home_last5_goals_for"] / 5.0
    F["away_goals_for_5"] = r["away_last5_goals_for"] / 5.0
    F["home_goals_against_5"] = r["home_last5_goals_against"] / 5.0
    F["away_goals_against_5"] = r["away_last5_goals_against"] / 5.0
    F["home_wins_5"] = r["home_last5_win"]
    F["away_wins_5"] = r["away_last5_win"]
    F["form_diff_ppg_5"] = F["home_ppg_5"] - F["away_ppg_5"]
    F["form_diff_goals_5"] = F["home_goals_for_5"] - F["away_goals_for_5"]
    F["home_total_matches"] = r["home_cum_matches"]
    F["away_total_matches"] = r["away_cum_matches"]
    F["home_total_win_rate"] = r["home_cum_win"] / r["home_cum_matches"].replace(0, 1)
    F["away_total_win_rate"] = r["away_cum_win"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_goals_for"] = r["home_cum_goals_for"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_goals_for"] = r["away_cum_goals_for"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_goals_against"] = r["home_cum_goals_against"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_goals_against"] = r["away_cum_goals_against"] / r["away_cum_matches"].replace(0, 1)
    lg_avg = (r["FTHG"].mean() + r["FTAG"].mean()) / 2
    F["home_attack_strength"] = F["home_avg_goals_for"] / lg_avg
    F["away_attack_strength"] = F["away_avg_goals_for"] / lg_avg
    F["home_defense_strength"] = F["home_avg_goals_against"] / lg_avg
    F["away_defense_strength"] = F["away_avg_goals_against"] / lg_avg
    F["expected_home_goals"] = F["home_attack_strength"] * F["away_defense_strength"] * lg_avg
    F["expected_away_goals"] = F["away_attack_strength"] * F["home_defense_strength"] * lg_avg
    F = F.fillna(0)

    mask = (r["home_cum_matches"] >= 10).values
    return (F[mask].reset_index(drop=True), r["result"].values[mask],
            r["Date"].values[mask], r["Div"].values[mask],
            r["league"].values[mask] if "league" in r.columns else r["Div"].values[mask])
