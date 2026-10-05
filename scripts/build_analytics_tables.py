# -*- coding: utf-8 -*-
"""构建可视化分析数据表(供 UI 直接查询出图)

产出表:
  team_radar        球队 7 维能力(0-100, 同联赛内百分位)
  league_stats      各联赛各赛季: 场均进球/胜平负占比/场均 xG
  model_metrics     各模型版本样本外指标(准确率/宏F1/LogLoss/平局召回)
  model_confusion   部署模型在测试集上的混淆矩阵
  model_calibration 概率校准曲线(预测概率 vs 实际频率)
  feature_importance 特征重要性 Top N

用法: python scripts/build_analytics_tables.py
"""
import json
import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import xgboost as xgb
from sklearn.metrics import confusion_matrix

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"
sys.path.insert(0, str(BASE))
from src.prediction import vector_features_v2 as v2  # noqa: E402

CUTOFF = pd.Timestamp("2025-08-01")
LABELS = ["主胜", "平局", "客胜"]
PARAMS = dict(objective="multi:softprob", num_class=3, n_estimators=300, max_depth=5,
              learning_rate=0.05, subsample=0.8, colsample_bytree=0.8,
              reg_alpha=0.1, reg_lambda=1.0, random_state=42, eval_metric="mlogloss")


def pct(s):
    return s.rank(pct=True).mul(100).round(0)


def build_team_radar(c):
    """球队 7 维: 进攻/防守/射门压制/纪律/身价/经验/稳定性"""
    print("① 球队雷达数据 ...")
    rows = []
    for r in c.execute("""SELECT team_id, name, league_id FROM teams"""):
        tid = r["team_id"]
        m = c.execute("""
            SELECT COUNT(*) n,
                   SUM(CASE WHEN m.home_team_id=? THEN m.home_goals ELSE m.away_goals END) gf,
                   SUM(CASE WHEN m.home_team_id=? THEN m.away_goals ELSE m.home_goals END) ga,
                   SUM(CASE WHEN m.home_team_id=? THEN m.home_shots ELSE m.away_shots END) sf,
                   SUM(CASE WHEN m.home_team_id=? THEN m.away_shots ELSE m.home_shots END) sa,
                   SUM(CASE WHEN m.home_team_id=? THEN m.home_yellow+m.home_red
                            ELSE m.away_yellow+m.away_red END) cards,
                   SUM(CASE WHEN m.home_team_id=? THEN m.home_xg ELSE m.away_xg END) xg,
                   SUM(CASE WHEN m.home_team_id=? THEN m.away_xg ELSE m.home_xg END) xga,
                   SUM(CASE WHEN (m.home_team_id=? AND m.home_goals>m.away_goals)
                              OR (m.away_team_id=? AND m.away_goals>m.home_goals) THEN 3
                            WHEN m.home_goals=m.away_goals THEN 1 ELSE 0 END) pts
            FROM matches m
            WHERE (m.home_team_id=? OR m.away_team_id=?) AND m.status='FT'
              AND m.home_goals IS NOT NULL""",
            (tid,) * 11).fetchone()
        n = m["n"] or 0
        if n < 5:
            continue
        squad = c.execute("""SELECT AVG(age) a, AVG(market_value) mv, COUNT(*) cnt
                             FROM players WHERE team_id=?""", (tid,)).fetchone()
        tm = c.execute("""SELECT SUM(v.value) total, COUNT(*) n FROM tm_club_map mc
            JOIN tm_player_seasons s ON s.team_id = mc.club_id
            JOIN tm_player_market_value v ON v.player_id = s.player_id
            WHERE mc.team_id=? AND v.value_date = (
                SELECT MAX(value_date) FROM tm_player_market_value x WHERE x.player_id=v.player_id)
              AND s.season_start = (SELECT MAX(season_start) FROM tm_player_seasons y
                                    WHERE y.team_id = mc.club_id)""", (tid,)).fetchone()
        rows.append({
            "team_id": tid, "team": r["name"], "league_id": r["league_id"], "matches": n,
            "goals_pg": round((m["gf"] or 0) / n, 2),
            "conceded_pg": round((m["ga"] or 0) / n, 2),
            "shots_pg": round((m["sf"] or 0) / n, 2),
            "shot_diff_pg": round(((m["sf"] or 0) - (m["sa"] or 0)) / n, 2),
            "cards_pg": round((m["cards"] or 0) / n, 2),
            "xg_pg": round((m["xg"] or 0) / n, 2) if m["xg"] else None,
            "xga_pg": round((m["xga"] or 0) / n, 2) if m["xga"] else None,
            "ppg": round((m["pts"] or 0) / n, 2),
            "avg_age": round(squad["a"], 1) if squad and squad["a"] else None,
            "market_value": squad["mv"] if squad else None,
            "squad_value": (tm["total"] if tm else None),
        })
    df = pd.DataFrame(rows)
    print(f"   {len(df)} 支球队(>=5 场)")
    # 同联赛内百分位
    for col, out, invert in [("goals_pg", "s_attack", False),
                             ("conceded_pg", "s_defense", True),
                             ("shot_diff_pg", "s_dominance", False),
                             ("cards_pg", "s_discipline", True),
                             ("squad_value", "s_value", False),
                             ("avg_age", "s_experience", False),
                             ("ppg", "s_stability", False)]:
        g = df.groupby("league_id")[col]
        df[out] = g.transform(lambda s: 100 - pct(s) if invert else pct(s))
    df["s_value"] = df.groupby("league_id")["squad_value"].transform(
        lambda s: pct(s.fillna(0)))
    return df[["team_id", "team", "league_id", "matches", "goals_pg", "conceded_pg",
               "shots_pg", "shot_diff_pg", "cards_pg", "xg_pg", "xga_pg", "ppg",
               "avg_age", "squad_value", "s_attack", "s_defense", "s_dominance",
               "s_discipline", "s_value", "s_experience", "s_stability"]]


def build_league_stats(c):
    """联赛-赛季: 场均进球/胜平负占比/场均 xG"""
    print("② 联赛统计 ...")
    rows = []
    for r in c.execute("""SELECT l.league_id, l.name league, m.season,
               COUNT(*) n,
               AVG(m.home_goals + m.away_goals) goals,
               AVG(CASE WHEN m.home_goals>m.away_goals THEN 1.0 ELSE 0 END) home_win,
               AVG(CASE WHEN m.home_goals=m.away_goals THEN 1.0 ELSE 0 END) draw,
               AVG(CASE WHEN m.home_goals<m.away_goals THEN 1.0 ELSE 0 END) away_win,
               AVG(m.home_xg + m.away_xg) xg,
               AVG(CASE WHEN m.home_goals>m.away_goals THEN 1.0 ELSE 0 END) * 100 hw_pct
        FROM matches m JOIN leagues l ON l.league_id=m.league_id
        WHERE m.status='FT' AND m.home_goals IS NOT NULL
        GROUP BY m.league_id, m.season"""):
        rows.append({"league_id": r["league_id"], "league": r["league"], "season": r["season"],
                     "matches": r["n"],
                     "goals_pg": round(r["goals"] or 0, 2),
                     "xg_pg": round(r["xg"], 2) if r["xg"] else None,
                     "home_win_pct": round((r["home_win"] or 0) * 100, 1),
                     "draw_pct": round((r["draw"] or 0) * 100, 1),
                     "away_win_pct": round((r["away_win"] or 0) * 100, 1)})
    return pd.DataFrame(rows)


def build_model_tables(c):
    """模型指标 / 混淆矩阵 / 校准曲线 / 特征重要性"""
    print("③ 模型评估数据(需训练两次模型, 约 1 分钟) ...")
    df = v2.load_matches(with_xg=True)
    X2, y, dates, _, _ = v2.build_features_v2(df, use_official_xg=False)
    X7, _, _, _, _ = v2.build_features_v2(df, use_official_xg=True, use_tm=True)
    dates = pd.to_datetime(dates)
    tr, te = dates < CUTOFF, dates >= CUTOFF
    m2 = xgb.XGBClassifier(**PARAMS).fit(X2[tr], y[tr], verbose=False)
    m7 = xgb.XGBClassifier(**PARAMS).fit(X7[tr], y[tr], verbose=False)
    p2, p7 = m2.predict_proba(X2[te]), m7.predict_proba(X7[te])
    pe = (p2 + p7) / 2.0
    yte = y[te]

    from sklearn.metrics import accuracy_score, f1_score, log_loss
    metrics = []
    for tag, p in (("v2 新特征", p2), ("v7 官方xG+TM", p7), ("v9 集成 v2+v7", pe)):
        pred = p.argmax(axis=1)
        metrics.append({"model": tag, "acc": round(accuracy_score(yte, pred) * 100, 2),
                        "f1_macro": round(f1_score(yte, pred, average="macro"), 4),
                        "logloss": round(log_loss(yte, p, labels=[0, 1, 2]), 4),
                        "draw_recall": round(float((pred[yte == 1] == 1).mean()) * 100, 1),
                        "test_n": int(te.sum())})
    # 历史对比(walkforward_compare.json)
    wf = BASE / "models" / "walkforward_compare.json"
    if wf.exists():
        for r in json.loads(wf.read_text(encoding="utf-8")).get("results", []):
            metrics.append({"model": r["model"], "acc": round(r["acc"] * 100, 2),
                            "f1_macro": round(r["f1_macro"], 4),
                            "logloss": round(r["logloss"], 4),
                            "draw_recall": round(r["draw_recall"] * 100, 1),
                            "test_n": r.get("test")})

    pred_e = pe.argmax(axis=1)
    cm = confusion_matrix(yte, pred_e, labels=[0, 1, 2])
    conf = pd.DataFrame(cm, index=LABELS, columns=LABELS).reset_index(names="actual")
    conf = conf.melt(id_vars="actual", var_name="predicted", value_name="count")

    # 校准曲线: 每个类别按预测概率分箱, 比较"预测均值"与"实际频率"
    cal = []
    for k, lab in enumerate(LABELS):
        s = pd.DataFrame({"p": pe[:, k], "hit": (yte == k).astype(int)})
        s["bin"] = pd.cut(s["p"], bins=np.arange(0, 1.01, 0.1), include_lowest=True)
        g = s.groupby("bin", observed=True).agg(pred=("p", "mean"), actual=("hit", "mean"),
                                                n=("hit", "size")).reset_index()
        for _, row in g.iterrows():
            cal.append({"outcome": lab, "predicted": round(row["pred"], 3),
                        "actual": round(row["actual"], 3), "n": int(row["n"])})

    # 特征重要性(v7)
    imp = pd.DataFrame({"feature": list(X7.columns),
                        "importance": m7.feature_importances_})
    imp = imp.sort_values("importance", ascending=False).head(40).reset_index(drop=True)
    # 去重: 与本次实测同名/同义的沿用本次值(去掉历史 JSON 里的冗余版本)
    met = pd.DataFrame(metrics)
    met["model"] = met["model"].replace({"v7 v2+官方xG+TM": "v7 官方xG+TM"})
    met = met.drop_duplicates(subset="model", keep="first").reset_index(drop=True)
    return met, conf, pd.DataFrame(cal), imp


def main():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    tr = build_team_radar(c)
    ls = build_league_stats(c)
    metrics, conf, cal, imp = build_model_tables(c)
    for name, df in (("team_radar", tr), ("league_stats", ls),
                     ("model_metrics", metrics), ("model_confusion", conf),
                     ("model_calibration", cal), ("feature_importance", imp)):
        df.to_sql(name, c, if_exists="replace", index=False)
        print(f"   写入 {name}: {len(df):,} 行")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tr_team ON team_radar(team_id)")
    c.commit()

    print("\n球队雷达示例(英超前 5):")
    for r in tr[tr["league_id"] == 1].nlargest(5, "s_stability").itertuples():
        print(f"   {r.team:<14} 进攻{r.s_attack:.0f} 防守{r.s_defense:.0f} "
              f"压制{r.s_dominance:.0f} 纪律{r.s_discipline:.0f} 身价{r.s_value:.0f} "
              f"经验{r.s_experience:.0f} 稳定{r.s_stability:.0f}")
    print("\n模型指标:")
    print(metrics[["model", "acc", "f1_macro", "logloss", "draw_recall"]].to_string(index=False))
    c.close()


if __name__ == "__main__":
    main()
