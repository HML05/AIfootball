# -*- coding: utf-8 -*-
"""向量化特征 v2 —— 在 v1 基础上加入"未被使用"的免费数据特征

新增特征来源(all_matches.csv 本来就有, 之前完全没用):
- 射门/射正/角球/犯规/黄红牌: 各队近5场、近10场的均值与差值
- 射正转化率(进球/射正)、射门压制(自己射门 vs 对手射门)
- 休息天数、7天内比赛密度(赛程负荷)
- 历史交锋(H2H): 交锋次数、主队历史胜率、场均进球
- 联赛标识(五大联赛差异)

仍然严格无未来信息: 所有统计 shift(1) 后使用; Elo 逐场递推。
"""
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.parent.parent

DIV_INDEX = {"E0": 0, "SP1": 1, "D1": 2, "I1": 3, "F1": 4,
             "ELC": 5, "BSA": 6, "PPL": 7, "DED": 8, "CL": 9}

_PROXY = None
_TM = None


def _tm_table():
    """Transfermarkt 球队-赛季特征(阵容身价/伤病天数), 见 scripts/build_tm_features.py"""
    global _TM
    if _TM is None:
        p = BASE / "data" / "processed" / "tm_team_season.csv"
        _TM = {}
        if p.exists():
            df = pd.read_csv(p, encoding="utf-8-sig")
            for r in df.itertuples():
                nn = "".join(ch for ch in str(r.team_name).lower() if ch.isalnum())
                _TM[(nn, str(r.season))] = (float(r.squad_value or 0),
                                            float(r.injury_days or 0))
    return _TM


def _proxy_model():
    """代理 xG 模型(由射门类统计预测进球, 见 scripts/build_proxy_xg.py)"""
    global _PROXY
    if _PROXY is None:
        p = BASE / "models" / "proxy_xg.joblib"
        if not p.exists():
            return None
        _PROXY = joblib.load(str(p))
    return _PROXY


def load_matches(csv_path=None, with_xg=False) -> pd.DataFrame:
    """加载训练集; with_xg=True 时合并官方 xG(来自 Understat, 见 scripts/export_match_xg.py)"""
    p = Path(csv_path) if csv_path else BASE / "data" / "processed" / "all_matches.csv"
    df = pd.read_csv(p, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    df["result"] = df["FTR"].map({"H": 0, "D": 1, "A": 2})
    if with_xg:
        xp = BASE / "data" / "processed" / "match_xg.csv"
        if xp.exists():
            xg = pd.read_csv(xp, encoding="utf-8-sig")
            xg["Date"] = pd.to_datetime(xg["date"], errors="coerce")
            m = df.merge(xg[["Date", "home", "away", "home_xg", "away_xg"]],
                         left_on=["Date", "HomeTeam", "AwayTeam"],
                         right_on=["Date", "home", "away"], how="left")
            m = m.drop(columns=["home", "away"])
            df = m.rename(columns={"home_xg": "HomeXG", "away_xg": "AwayXG"})
    return df


def _numify(df, cols):
    for c in cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    return df


def build_features_v2(df: pd.DataFrame, return_ids=False, use_proxy_xg=False,
                      use_tm=False, use_official_xg=False):
    df = df.copy()
    df["match_id"] = range(len(df))
    stat_cols = ["HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC", "HY", "AY", "HR", "AR"]
    df = _numify(df, stat_cols)
    if use_official_xg:
        df = _numify(df, ["HomeXG", "AwayXG"])

    # ---------- 长表(球队-比赛视角) ----------
    def side(dfx, home: bool):
        d = pd.DataFrame({
            "match_id": dfx["match_id"], "Date": dfx["Date"],
            "team": dfx["HomeTeam"] if home else dfx["AwayTeam"],
            "is_home": 1 if home else 0,
            "goals_for": dfx["FTHG"] if home else dfx["FTAG"],
            "goals_against": dfx["FTAG"] if home else dfx["FTHG"],
            # 官方 xG(Understat): 本场自身表现, 无未来信息
            "xg_for": (dfx["HomeXG"] if home else dfx["AwayXG"])
                      if "HomeXG" in dfx.columns else np.nan,
            "xg_against": (dfx["AwayXG"] if home else dfx["HomeXG"])
                          if "HomeXG" in dfx.columns else np.nan,
            "shots_for": dfx["HS"] if home else dfx["AS"],
            "shots_against": dfx["AS"] if home else dfx["HS"],
            "sot_for": dfx["HST"] if home else dfx["AST"],
            "sot_against": dfx["AST"] if home else dfx["HST"],
            "corners_for": dfx["HC"] if home else dfx["AC"],
            "corners_against": dfx["AC"] if home else dfx["HC"],
            "fouls_for": dfx["HF"] if home else dfx["AF"],
            "fouls_against": dfx["AF"] if home else dfx["HF"],
            "cards_against": (dfx["AY"].fillna(0) + 2 * dfx["AR"].fillna(0)) if home
                             else (dfx["HY"].fillna(0) + 2 * dfx["HR"].fillna(0)),
            "cards_for": (dfx["HY"].fillna(0) + 2 * dfx["HR"].fillna(0)) if home
                         else (dfx["AY"].fillna(0) + 2 * dfx["AR"].fillna(0)),
        })
        d["win"] = np.where(d["goals_for"] > d["goals_against"], 1, 0)
        d["draw"] = np.where(d["goals_for"] == d["goals_against"], 1, 0)
        d["loss"] = np.where(d["goals_for"] < d["goals_against"], 1, 0)
        d["points"] = d["win"] * 3 + d["draw"]
        return d

    tm = pd.concat([side(df, True), side(df, False)], ignore_index=True)
    tm = tm.sort_values(["team", "Date"]).reset_index(drop=True)

    # ---- 代理 xG: 用射门类统计预测"期望进球"(本场自身表现, 非未来信息) ----
    pm = _proxy_model() if use_proxy_xg else None
    if pm is not None:
        feats = pm["features"]
        Xp = pd.DataFrame({
            "shots_for": tm["shots_for"], "sot_for": tm["sot_for"],
            "corners_for": tm["corners_for"], "fouls_for": tm["fouls_for"],
            "cards_for": tm["cards_for"], "shots_against": tm["shots_against"],
            "sot_against": tm["sot_against"], "is_home": tm["is_home"],
            "league_idx": tm["match_id"].map(lambda _: 0),
        })
        Xp = Xp[feats].fillna(0)
        tm["xg_proxy_for"] = pm["model"].predict(Xp)
        Xq = Xp.copy()
        # 对手视角: for/against 互换, is_home 取反
        Xq["shots_for"], Xq["shots_against"] = Xp["shots_against"], Xp["shots_for"]
        Xq["sot_for"], Xq["sot_against"] = Xp["sot_against"], Xp["sot_for"]
        Xq["corners_for"] = tm["corners_against"]
        Xq["fouls_for"] = tm["fouls_against"]
        Xq["cards_for"] = tm["cards_against"]
        Xq["is_home"] = 1 - Xp["is_home"]
        tm["xg_proxy_against"] = pm["model"].predict(Xq[feats].fillna(0))

    # 参与累计/滚动的列(代理 xG / 官方 xG 按开关参与)
    if pm is not None:
        xg_cols = ["xg_proxy_for", "xg_proxy_against"]
        xg_label = "xg_proxy"
    elif use_official_xg:
        xg_cols = ["xg_for", "xg_against"]
        xg_label = "xg"
    else:
        xg_cols, xg_label = [], None
    roll_cols = ["points", "goals_for", "goals_against", "shots_for", "shots_against",
                 "sot_for", "sot_against", "corners_for", "corners_against", "cards_for"]
    roll_cols += xg_cols

    # 休息天数 / 赛程负荷(只用本场之前的信息)
    def _load(g):
        g = g.sort_values("Date").copy()
        g["rest_days"] = g["Date"].diff().dt.days
        g["cong7"] = g.set_index("Date")["match_id"].rolling("7D").count().values - 1
        return g

    tm = tm.groupby("team", group_keys=False)[tm.columns.tolist()].apply(_load)
    tm = tm.sort_values(["team", "Date"]).reset_index(drop=True)

    g = tm.groupby("team")
    base_roll = ["points", "goals_for", "goals_against", "shots_for", "shots_against",
                 "sot_for", "sot_against", "corners_for", "corners_against", "cards_for"] + xg_cols
    for c in ["win", "draw", "loss"] + roll_cols:
        tm[f"cum_{c}"] = g[c].shift(1).groupby(tm["team"]).cumsum()
    tm["cum_matches"] = g.cumcount()
    for w in (5, 10):
        for c in roll_cols + ["win"]:
            tm[f"last{w}_{c}"] = g[c].transform(
                lambda x, w=w: x.shift(1).rolling(w, min_periods=1).sum())
    tm["last5_sot_conv"] = tm["last5_goals_for"] / tm["last5_sot_for"].replace(0, np.nan)
    for c in ("rest_days", "cong7"):
        tm[f"prev_{c}"] = g[c].shift(1)

    cum_cols = ["win", "draw", "points", "goals_for", "goals_against",
                "shots_for", "shots_against", "sot_for", "sot_against",
                "corners_for", "corners_against", "cards_for"] + xg_cols
    keep = (["match_id", "team", "cum_matches"] +
            [f"cum_{c}" for c in cum_cols] +
            [f"last{w}_{c}" for w in (5, 10)
             for c in roll_cols + ["win"]] +
            ["last5_sot_conv", "prev_rest_days", "prev_cong7"])
    hf = tm[tm["is_home"] == 1][keep].add_prefix("home_")
    hf = hf.rename(columns={"home_match_id": "match_id", "home_team": "HomeTeam"})
    af = tm[tm["is_home"] == 0][keep].add_prefix("away_")
    af = af.rename(columns={"away_match_id": "match_id", "away_team": "AwayTeam"})
    r = df.merge(hf, on=["match_id", "HomeTeam"], how="left") \
          .merge(af, on=["match_id", "AwayTeam"], how="left")

    # ---------- Elo 逐场递推 ----------
    elo, he_list, ae_list = {}, [], []
    for _, row in df.iterrows():
        h, a = row["HomeTeam"], row["AwayTeam"]
        he, ae = elo.get(h, 1500.0), elo.get(a, 1500.0)
        he_list.append(he); ae_list.append(ae)
        exp_h = 1.0 / (1.0 + 10 ** ((ae - (he + 65.0)) / 400.0))
        actual_h = 1.0 if row["FTR"] == "H" else (0.5 if row["FTR"] == "D" else 0.0)
        delta = 32.0 * (1.0 + 0.1 * abs(row["FTHG"] - row["FTAG"])) * (actual_h - exp_h)
        elo[h], elo[a] = he + delta, ae - delta
    r["home_elo"], r["away_elo"] = he_list, ae_list

    # ---------- 历史交锋(H2H) ----------
    hist = {}
    h2h_cnt, h2h_hr, h2h_avg = [], [], []
    for _, row in df.iterrows():
        key = tuple(sorted([row["HomeTeam"], row["AwayTeam"]]))
        prev = hist.get(key, [])
        h2h_cnt.append(len(prev))
        if prev:
            wins = sum(1 for (hg, ag, hteam) in prev
                       if (hteam == row["HomeTeam"] and hg > ag) or
                          (hteam != row["HomeTeam"] and ag > hg))
            draws = sum(1 for (hg, ag, _) in prev if hg == ag)
            h2h_hr.append(wins / len(prev))
            h2h_avg.append(sum(hg + ag for hg, ag, _ in prev) / len(prev))
        else:
            h2h_hr.append(0.5); h2h_avg.append(2.6)
        hist.setdefault(key, []).append((row["FTHG"], row["FTAG"], row["HomeTeam"]))
    r["h2h_count"] = h2h_cnt
    r["h2h_home_win_rate"] = h2h_hr
    r["h2h_avg_goals"] = h2h_avg
    r["league_idx"] = r["Div"].map(DIV_INDEX).fillna(0)

    # ---------- 组装特征 ----------
    F = pd.DataFrame(index=r.index)
    F["home_elo"], F["away_elo"] = r["home_elo"], r["away_elo"]
    F["elo_diff"] = r["home_elo"] - r["away_elo"]
    F["elo_expected_home"] = 1.0 / (1.0 + 10 ** ((r["away_elo"] - (r["home_elo"] + 65.0)) / 400.0))
    F["home_elo_advantage"] = r["home_elo"] + 65.0 - r["away_elo"]

    for w in (5, 10):
        for c in ["points", "goals_for", "goals_against", "win"]:
            F[f"home_{c}_{w}"] = r[f"home_last{w}_{c}"] / w
            F[f"away_{c}_{w}"] = r[f"away_last{w}_{c}"] / w
    for c in ["shots_for", "shots_against", "sot_for", "sot_against",
              "corners_for", "corners_against", "cards_for"]:
        F[f"home_{c}_5"] = r[f"home_last5_{c}"] / 5
        F[f"away_{c}_5"] = r[f"away_last5_{c}"] / 5
        F[f"diff_{c}_5"] = F[f"home_{c}_5"] - F[f"away_{c}_5"]
    F["home_sot_conv_5"] = r["home_last5_sot_conv"]
    F["away_sot_conv_5"] = r["away_last5_sot_conv"]
    F["home_sot_rate_5"] = r["home_last5_sot_for"] / r["home_last5_shots_for"].replace(0, np.nan)
    F["away_sot_rate_5"] = r["away_last5_sot_for"] / r["away_last5_shots_for"].replace(0, np.nan)
    F["home_shot_dominance_5"] = (r["home_last5_shots_for"] - r["home_last5_shots_against"]) / 5
    F["away_shot_dominance_5"] = (r["away_last5_shots_for"] - r["away_last5_shots_against"]) / 5
    F["diff_shot_dominance_5"] = F["home_shot_dominance_5"] - F["away_shot_dominance_5"]
    F["home_rest_days"] = r["home_prev_rest_days"]
    F["away_rest_days"] = r["away_prev_rest_days"]
    F["rest_diff"] = F["home_rest_days"] - F["away_rest_days"]
    F["home_cong7"] = r["home_prev_cong7"]
    F["away_cong7"] = r["away_prev_cong7"]
    F["h2h_count"] = r["h2h_count"]
    F["h2h_home_win_rate"] = r["h2h_home_win_rate"]
    F["h2h_avg_goals"] = r["h2h_avg_goals"]
    F["league_idx"] = r["league_idx"]

    for c in (["win", "points", "goals_for", "goals_against", "sot_for", "sot_against"]
              + xg_cols):
        F[f"home_cum_{c}"] = r[f"home_cum_{c}"]
        F[f"away_cum_{c}"] = r[f"away_cum_{c}"]
    F["home_total_matches"] = r["home_cum_matches"]
    F["away_total_matches"] = r["away_cum_matches"]
    F["home_total_win_rate"] = r["home_cum_win"] / r["home_cum_matches"].replace(0, 1)
    F["away_total_win_rate"] = r["away_cum_win"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_goals_for"] = r["home_cum_goals_for"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_goals_for"] = r["away_cum_goals_for"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_goals_against"] = r["home_cum_goals_against"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_goals_against"] = r["away_cum_goals_against"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_sot_for"] = r["home_cum_sot_for"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_sot_for"] = r["away_cum_sot_for"] / r["away_cum_matches"].replace(0, 1)
    F["home_avg_sot_against"] = r["home_cum_sot_against"] / r["home_cum_matches"].replace(0, 1)
    F["away_avg_sot_against"] = r["away_cum_sot_against"] / r["away_cum_matches"].replace(0, 1)
    lg_avg = (r["FTHG"].mean() + r["FTAG"].mean()) / 2
    F["home_attack_strength"] = F["home_avg_goals_for"] / lg_avg
    F["away_attack_strength"] = F["away_avg_goals_for"] / lg_avg
    F["home_defense_strength"] = F["home_avg_goals_against"] / lg_avg
    F["away_defense_strength"] = F["away_avg_goals_against"] / lg_avg
    F["expected_home_goals"] = F["home_attack_strength"] * F["away_defense_strength"] * lg_avg
    F["expected_away_goals"] = F["away_attack_strength"] * F["home_defense_strength"] * lg_avg
    F["sot_strength_home"] = F["home_avg_sot_for"] - F["away_avg_sot_against"]
    F["sot_strength_away"] = F["away_avg_sot_for"] - F["home_avg_sot_against"]

    # ---- xG 特征(代理 xG 或官方 xG, 二者按开关其一启用) ----
    if xg_label:
        for c in xg_cols:
            F[f"home_{c}_5"] = r[f"home_last5_{c}"] / 5
            F[f"away_{c}_5"] = r[f"away_last5_{c}"] / 5
            F[f"home_{c}_10"] = r[f"home_last10_{c}"] / 10
            F[f"away_{c}_10"] = r[f"away_last10_{c}"] / 10
        F[f"diff_{xg_label}_for_5"] = F[f"home_{xg_label}_for_5"] - F[f"away_{xg_label}_for_5"]
        F[f"diff_{xg_label}_ag_5"] = (F[f"home_{xg_label}_against_5"]
                                      - F[f"away_{xg_label}_against_5"])
        F["home_xg_net_5"] = F[f"home_{xg_label}_for_5"] - F[f"home_{xg_label}_against_5"]
        F["away_xg_net_5"] = F[f"away_{xg_label}_for_5"] - F[f"away_{xg_label}_against_5"]
        F["diff_xg_net_5"] = F["home_xg_net_5"] - F["away_xg_net_5"]
        hm = r["home_cum_matches"].replace(0, 1)
        am = r["away_cum_matches"].replace(0, 1)
        F["home_xg_net_cum"] = (r[f"home_cum_{xg_label}_for"]
                                - r[f"home_cum_{xg_label}_against"]) / hm
        F["away_xg_net_cum"] = (r[f"away_cum_{xg_label}_for"]
                                - r[f"away_cum_{xg_label}_against"]) / am
        F["diff_xg_net_cum"] = F["home_xg_net_cum"] - F["away_xg_net_cum"]
        if xg_label == "xg":
            # 官方 xG 额外: 近 5 场 xG 与进球差(把握机会能力) + 场均 xG 差
            F["home_xg_overperf_5"] = F["home_goals_for_5"] - F["home_xg_for_5"]
            F["away_xg_overperf_5"] = F["away_goals_for_5"] - F["away_xg_for_5"]
            F["diff_xg_overperf_5"] = (F["home_xg_overperf_5"]
                                       - F["away_xg_overperf_5"])
            F["home_xg_per_match"] = F["home_cum_xg_for"] / hm
            F["away_xg_per_match"] = F["away_cum_xg_for"] / am
            F["diff_xg_per_match"] = F["home_xg_per_match"] - F["away_xg_per_match"]
            F["home_xga_per_match"] = F["home_cum_xg_against"] / hm
            F["away_xga_per_match"] = F["away_cum_xg_against"] / am
            F["diff_xga_per_match"] = (F["home_xga_per_match"]
                                       - F["away_xga_per_match"])

    # ---- Transfermarkt 特征(阵容身价 / 伤病天数) ----
    if use_tm:
        tm = _tm_table()
        if tm:
            nz = lambda s: "".join(ch for ch in str(s).lower() if ch.isalnum())
            hv, av, hi, ai = [], [], [], []
            for h, a, season in zip(r["HomeTeam"], r["AwayTeam"], r["season"]):
                vh, ih = tm.get((nz(h), str(season)), (0.0, 0.0))
                va, ia = tm.get((nz(a), str(season)), (0.0, 0.0))
                hv.append(vh); av.append(va); hi.append(ih); ai.append(ia)
            F["home_squad_value"] = np.log10(np.array(hv) + 1)
            F["away_squad_value"] = np.log10(np.array(av) + 1)
            F["squad_value_diff"] = F["home_squad_value"] - F["away_squad_value"]
            F["squad_value_ratio"] = np.array(hv) / (np.array(hv) + np.array(av) + 1)
            F["home_injury_days"] = np.array(hi) / 100.0
            F["away_injury_days"] = np.array(ai) / 100.0
            F["injury_days_diff"] = F["home_injury_days"] - F["away_injury_days"]
    F = F.fillna(0)

    mask = (r["home_cum_matches"] >= 10).values
    out = (F[mask].reset_index(drop=True), r["result"].values[mask],
           r["Date"].values[mask], r["Div"].values[mask],
           r["league"].values[mask])
    if return_ids:
        return out + (r["match_id"].values[mask],)
    return out


def append_dummy_fixtures(df: pd.DataFrame, fixtures):
    """把待预测比赛作为"占位行"追加到历史数据末尾(用同样的特征路径计算)

    fixtures: [{"home":..., "away":..., "date": "YYYY-MM-DD"}, ...]
    返回 (新df, 占位行的起始 match_id)
    """
    offset = len(df)
    rows = []
    for f in fixtures:
        row = {c: 0 for c in df.columns}
        row.update({
            "Date": pd.to_datetime(f["date"]),
            "HomeTeam": f["home"], "AwayTeam": f["away"],
            "FTHG": 0, "FTAG": 0, "FTR": "D",
            "Div": f.get("div", df["Div"].iloc[-1]),
            "league": f.get("league", df["league"].iloc[-1]),
        })
        rows.append(row)
    add = pd.DataFrame(rows)[df.columns.tolist()]
    return pd.concat([df, add], ignore_index=True), offset
