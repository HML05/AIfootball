# -*- coding: utf-8 -*-
"""用射门数据自建"代理 xG"(0 成本)

思路: 官方 xG 拿不到/太贵, 但我们有 9,026 场的射门/射正/角球/犯规/牌数据。
     用泊松回归拟合 "射门类统计 -> 进球数", 得到每场比赛双方的"期望进球"代理值。

产物:
  - models/proxy_xg.joblib  (模型系数, 供特征模块直接计算)
  - DB: matches.home_xg_proxy / away_xg_proxy
  - 校验: 与实际进球的 MAE; 与官方 xG(仅107场)的相关性

用法: python scripts/build_proxy_xg.py
"""
import json
import os
import sqlite3
import sys
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.linear_model import PoissonRegressor
from sklearn.metrics import mean_absolute_error

BASE = Path(__file__).parent.parent
sys.path.insert(0, str(BASE))
DB = BASE / "data" / "database" / "football.db"
DIV_INDEX = {"E0": 0, "SP1": 1, "D1": 2, "I1": 3, "F1": 4,
             "ELC": 5, "BSA": 6, "PPL": 7, "DED": 8, "CL": 9}

FEATURES = ["shots_for", "sot_for", "corners_for", "fouls_for", "cards_for",
            "shots_against", "sot_against", "is_home", "league_idx"]


def load_csv():
    df = pd.read_csv(BASE / "data" / "processed" / "all_matches.csv", encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "Date"])
    for c in ["HS", "AS", "HST", "AST", "HC", "AC", "HF", "AF", "HY", "AY", "HR", "AR"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")
    return df.sort_values("Date").reset_index(drop=True)


def to_long(df):
    """每场比赛转成两行(主队视角/客队视角)"""
    h = pd.DataFrame({
        "goals": df["FTHG"], "shots_for": df["HS"], "sot_for": df["HST"],
        "corners_for": df["HC"], "fouls_for": df["HF"],
        "cards_for": df["HY"].fillna(0) + 2 * df["HR"].fillna(0),
        "shots_against": df["AS"], "sot_against": df["AST"],
        "is_home": 1, "league_idx": df["Div"].map(DIV_INDEX).fillna(0),
    })
    a = pd.DataFrame({
        "goals": df["FTAG"], "shots_for": df["AS"], "sot_for": df["AST"],
        "corners_for": df["AC"], "fouls_for": df["AF"],
        "cards_for": df["AY"].fillna(0) + 2 * df["AR"].fillna(0),
        "shots_against": df["HS"], "sot_against": df["HST"],
        "is_home": 0, "league_idx": df["Div"].map(DIV_INDEX).fillna(0),
    })
    return pd.concat([h, a], ignore_index=True)


def main():
    df = load_csv()
    long = to_long(df).dropna(subset=["shots_for", "sot_for"])
    print(f"样本: {len(df)} 场 ({len(long)} 条球队-比赛)")

    # 时间切分: 前80%训练, 后20%验证
    cut = int(len(long) * 0.8)
    tr, te = long.iloc[:cut], long.iloc[cut:]
    model = PoissonRegressor(alpha=1e-3, max_iter=1000)
    model.fit(tr[FEATURES], tr["goals"])
    pred_te = model.predict(te[FEATURES])
    print(f"验证集 MAE: {mean_absolute_error(te['goals'], pred_te):.4f}  "
          f"(均值基线 {mean_absolute_error(te['goals'], np.full(len(te), tr['goals'].mean())):.4f})")
    print("系数:")
    for f, c in zip(FEATURES, model.coef_):
        print(f"   {f:<16} {c:+.4f}")

    # 重新用全量数据拟合(最终版)
    final = PoissonRegressor(alpha=1e-3, max_iter=1000).fit(long[FEATURES], long["goals"])
    joblib.dump({"model": final, "features": FEATURES}, str(BASE / "models" / "proxy_xg.joblib"))

    # 写回 DB: 主客双方代理 xG (to_long 前半是主队视角, 后半是客队视角)
    L = to_long(df)
    L = L.fillna(L.median(numeric_only=True))
    n = len(df)
    proxy_h = final.predict(L[FEATURES].iloc[:n])
    proxy_a = final.predict(L[FEATURES].iloc[n:])
    df = df.assign(xg_proxy_home=proxy_h, xg_proxy_away=proxy_a)

    conn = sqlite3.connect(str(DB))
    conn.row_factory = sqlite3.Row
    cols = {r[1] for r in conn.execute("PRAGMA table_info(matches)")}
    for c in ("home_xg_proxy", "away_xg_proxy"):
        if c not in cols:
            conn.execute(f"ALTER TABLE matches ADD COLUMN {c} REAL")
    conn.commit()

    lg_map = {r["name"]: r["league_id"] for r in
              conn.execute("SELECT league_id, name FROM leagues")}
    team_map = {}
    for r in conn.execute("SELECT team_id, name, league_id FROM teams"):
        team_map[(r["league_id"], r["name"])] = r["team_id"]

    upd = 0
    for _, r in df.iterrows():
        lid = lg_map.get(r["league"])
        if not lid:
            continue
        hid = team_map.get((lid, r["HomeTeam"]))
        aid = team_map.get((lid, r["AwayTeam"]))
        if not hid or not aid:
            continue
        cur = conn.execute(
            "UPDATE matches SET home_xg_proxy=?, away_xg_proxy=? "
            "WHERE league_id=? AND home_team_id=? AND away_team_id=? AND date LIKE ?",
            (round(float(r["xg_proxy_home"]), 3), round(float(r["xg_proxy_away"]), 3),
             lid, hid, aid, r["Date"].strftime("%Y-%m-%d") + "%"))
        upd += cur.rowcount
    conn.commit()
    print(f"\n写回 DB: 影响 {upd} 行")

    # 与官方 xG 的相关性(仅107场)
    pair = conn.execute("""SELECT home_xg, home_xg_proxy, away_xg, away_xg_proxy
                           FROM matches WHERE home_xg IS NOT NULL
                             AND home_xg_proxy IS NOT NULL""").fetchall()
    if pair:
        arr = np.array(pair, dtype=float)
        ch = np.corrcoef(arr[:, 0], arr[:, 1])[0, 1]
        ca = np.corrcoef(arr[:, 2], arr[:, 3])[0, 1]
        print(f"与官方 xG 相关性({len(pair)}场): 主队 {ch:.3f} | 客队 {ca:.3f}")
    print("覆盖:", conn.execute(
        "SELECT COUNT(*) FROM matches WHERE home_xg_proxy IS NOT NULL").fetchone()[0], "场")
    conn.close()

    with open(BASE / "models" / "proxy_xg_report.json", "w", encoding="utf-8") as f:
        json.dump({"samples": int(len(long)),
                   "mae_val": round(float(mean_absolute_error(te["goals"], pred_te)), 4),
                   "coef": {k: round(float(v), 4) for k, v in zip(FEATURES, final.coef_)},
                   "corr_official_xg": {
                       "home": round(float(ch), 3), "away": round(float(ca), 3)}
                   if pair else None}, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
