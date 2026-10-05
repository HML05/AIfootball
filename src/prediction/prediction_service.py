# -*- coding: utf-8 -*-
"""预测落库服务: 对未来未开赛比赛跑 XGBoost 预测并写入 predictions 表"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from config.settings import settings
from src.analysis.elo_rating import EloRating
from src.prediction.feature_engineer import FeatureEngineer

BASE = Path(__file__).parent.parent.parent
DB_PATH = BASE / "data" / "database" / "football.db"


def _db():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def _ensure(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS predictions (
            pred_id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER,
            model_version TEXT,
            pred_home_win REAL, pred_draw REAL, pred_away_win REAL,
            pred_result TEXT,
            actual_result TEXT,
            features_json TEXT,
            created_at TEXT)
    """)
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_pred_match ON predictions(match_id)")
    # 轻量迁移: 命中标记 / 是否历史回测
    cols = {r[1] for r in conn.execute("PRAGMA table_info(predictions)")}
    if "hit" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN hit INTEGER")
    if "is_backtest" not in cols:
        conn.execute("ALTER TABLE predictions ADD COLUMN is_backtest INTEGER DEFAULT 0")


def _num(v):
    try:
        return float(v)
    except Exception:
        return 0.0


def _load_engineers():
    path = settings.DATA_DIR / "processed" / "all_matches.csv"
    df = pd.read_csv(path, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "Date"])
    df = df.sort_values("Date").reset_index(drop=True)
    elo = EloRating()
    elo.batch_update(df)
    fe = FeatureEngineer(df, elo)
    model_path = settings.MODEL_DIR / "xgb_match_predictor.joblib"
    data = joblib.load(str(model_path))
    model = data["model"]
    feature_names = data["features"]
    return fe, model, feature_names


def predict_upcoming_v2(days: int = 3, league_ids=(1, 2, 3, 4, 5)) -> dict:
    """v2 模型预测(90维特征: 含射门/射正/角球/牌/休息/交锋/联赛)

    与训练使用完全相同的特征计算路径: 把待预测比赛作为占位行追加到历史数据尾部,
    一次性算出全部特征(Elo 逐场递推, 统计 shift(1))。
    """
    from src.prediction import vector_features_v2 as v2
    bundle_path = settings.MODEL_DIR / "xgb_v2.joblib"
    if not bundle_path.exists():
        raise FileNotFoundError("未找到 models/xgb_v2.joblib, 请先运行 scripts/train_v2.py")
    bundle = joblib.load(str(bundle_path))
    model, fnames = bundle["model"], bundle["features"]

    now = datetime.now()
    start, end = now.date(), (now + timedelta(days=days)).date()
    conn = _db()
    _ensure(conn)
    conn.commit()
    sql = """SELECT m.match_id, th.name AS h, ta.name AS a, m.date,
                    l.name AS league, m.match_id AS mid
             FROM matches m
             JOIN teams th ON th.team_id = m.home_team_id
             JOIN teams ta ON ta.team_id = m.away_team_id
             JOIN leagues l ON l.league_id = m.league_id
             WHERE m.status='NS' AND date(m.date) BETWEEN ? AND ?
               AND m.league_id IN ({})""".format(",".join("?" for _ in league_ids))
    rows = conn.execute(sql, (start.isoformat(), end.isoformat()) + league_ids).fetchall()
    if not rows:
        conn.close()
        return {"matches": 0, "predicted": 0, "skipped": 0, "model": "v2"}

    fixtures = [{"home": r["h"], "away": r["a"], "date": r["date"][:10],
                 "league": r["league"]} for r in rows]
    df = v2.load_matches()
    new_df, offset = v2.append_dummy_fixtures(df, fixtures)
    X, y, dates, divs, leagues, ids = v2.build_features_v2(new_df, return_ids=True)

    sel = ids >= offset
    Xd, idd = X[sel], ids[sel]
    pos_of = {int(i) - offset: k for k, i in enumerate(idd)}
    ok = skip = 0
    if len(Xd):
        proba = model.predict_proba(Xd)
        for k, r in enumerate(rows):
            pos = pos_of.get(k)
            if pos is None:
                skip += 1
                continue
            p = proba[pos]
            pred_result = ["H", "D", "A"][int(np.argmax(p))]
            # 用真实特征值快照(便于复盘)
            feats_json = json.dumps(
                {c: _num(Xd.iloc[pos][c]) for c in Xd.columns}, ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO predictions "
                "(match_id, model_version, pred_home_win, pred_draw, pred_away_win,"
                " pred_result, actual_result, features_json, created_at, hit, is_backtest)"
                " VALUES (?,?,?,?,?,?,NULL,?,?,NULL,0)",
                (r["match_id"], "v2", _num(p[0]), _num(p[1]), _num(p[2]),
                 pred_result, feats_json,
                 now.strftime("%Y-%m-%d %H:%M:%S")))
            ok += 1
            if ok <= 5:
                print(f"  ✓ {r['h']} vs {r['a']} → {pred_result} "
                      f"(主{p[0]:.2f}/平{p[1]:.2f}/客{p[2]:.2f})")
    conn.commit()
    conn.close()
    return {"matches": len(rows), "predicted": ok, "skipped": skip, "model": "v2"}


def predict_upcoming_ensemble(days: int = 3, league_ids=(1, 2, 3, 4, 5)) -> dict:
    """集成预测: v2(90 维) + v7(官方 xG + TM 阵容身价/伤病, 126 维) 概率加权平均

    样本外(1,817 场)表现: 准确率 50.14% / LogLoss 1.0338 —— 当前最优组合
      v2 单独 50.03% / 1.0525 | v7 单独 49.70% / 1.0292
    """
    from src.prediction import vector_features_v2 as v2

    bpath = settings.MODEL_DIR / "ensemble_v2_v7.joblib"
    if not bpath.exists():
        raise FileNotFoundError("未找到 models/ensemble_v2_v7.joblib, 请先运行 scripts/train_v7.py")
    b = joblib.load(str(bpath))
    m2, m7 = b["model_v2"], b["model_v7"]
    w2 = float(b.get("weight_v2", 0.5))
    f2, f7 = list(b["features_v2"]), list(b["features_v7"])

    now = datetime.now()
    start, end = now.date(), (now + timedelta(days=days)).date()
    conn = _db()
    _ensure(conn)
    conn.commit()
    sql = """SELECT m.match_id, th.name AS h, ta.name AS a, m.date,
                    l.name AS league
             FROM matches m
             JOIN teams th ON th.team_id = m.home_team_id
             JOIN teams ta ON ta.team_id = m.away_team_id
             JOIN leagues l ON l.league_id = m.league_id
             WHERE m.status='NS' AND date(m.date) BETWEEN ? AND ?
               AND m.league_id IN ({})""".format(",".join("?" for _ in league_ids))
    rows = conn.execute(sql, (start.isoformat(), end.isoformat()) + tuple(league_ids)).fetchall()
    if not rows:
        conn.close()
        return {"matches": 0, "predicted": 0, "skipped": 0, "model": "v2+v7"}

    fixtures = [{"home": r["h"], "away": r["a"], "date": r["date"][:10],
                 "league": r["league"]} for r in rows]
    df = v2.load_matches(with_xg=True)                 # 含官方 xG 的历史
    new_df, offset = v2.append_dummy_fixtures(df, fixtures)
    X2, _, _, _, _, ids = v2.build_features_v2(new_df, return_ids=True,
                                               use_official_xg=False)
    X7, _, _, _, _, _ = v2.build_features_v2(new_df, return_ids=True,
                                             use_official_xg=True, use_tm=True)

    sel = ids >= offset
    X2d = X2[sel][f2]
    X7d = X7[sel][f7]
    pos_of = {int(i) - offset: k for k, i in enumerate(ids[sel])}
    ok = skip = 0
    if len(X2d):
        p2 = m2.predict_proba(X2d)
        p7 = m7.predict_proba(X7d)
        proba = w2 * p2 + (1.0 - w2) * p7
        for k, r in enumerate(rows):
            pos = pos_of.get(k)
            if pos is None:
                skip += 1
                continue
            p = proba[pos]
            pred_result = ["H", "D", "A"][int(np.argmax(p))]
            feats_json = json.dumps(
                {**{f"v2_{c}": _num(X2d.iloc[pos][c]) for c in X2d.columns},
                 **{f"v7_{c}": _num(X7d.iloc[pos][c]) for c in X7d.columns}},
                ensure_ascii=False)
            conn.execute(
                "INSERT OR REPLACE INTO predictions "
                "(match_id, model_version, pred_home_win, pred_draw, pred_away_win,"
                " pred_result, actual_result, features_json, created_at, hit, is_backtest)"
                " VALUES (?,?,?,?,?,?,NULL,?,?,NULL,0)",
                (r["match_id"], "v2+v7", _num(p[0]), _num(p[1]), _num(p[2]),
                 pred_result, feats_json, now.strftime("%Y-%m-%d %H:%M:%S")))
            ok += 1
            if ok <= 5:
                print(f"  ✓ {r['h']} vs {r['a']} → {pred_result} "
                      f"(主{p[0]:.2f}/平{p[1]:.2f}/客{p[2]:.2f}) [v2+v7]")
    conn.commit()
    conn.close()
    return {"matches": len(rows), "predicted": ok, "skipped": skip, "model": "v2+v7"}


def predict_upcoming(days: int = 3, league_ids=(1, 2, 3, 4, 5)) -> dict:
    """优先集成(v2+v7) → 退回 v2 → 退回 v1"""
    try:
        return predict_upcoming_ensemble(days=days, league_ids=league_ids)
    except FileNotFoundError:
        pass
    try:
        return predict_upcoming_v2(days=days, league_ids=league_ids)
    except FileNotFoundError:
        pass
    now = datetime.now()
    start, end = now.date(), (now + timedelta(days=days)).date()
    fe, model, feature_names = _load_engineers()
    conn = _db()
    _ensure(conn)
    conn.commit()

    sql = """SELECT m.match_id, th.name AS h, ta.name AS a, m.date
             FROM matches m
             JOIN teams th ON th.team_id = m.home_team_id
             JOIN teams ta ON ta.team_id = m.away_team_id
             WHERE m.status = 'NS' AND date(m.date) BETWEEN ? AND ?
               AND m.league_id IN ({})""".format(
        ",".join("?" for _ in league_ids))
    rows = conn.execute(sql, (start.isoformat(), end.isoformat()) + league_ids).fetchall()

    ok, skip = 0, 0
    for r in rows:
        try:
            feats = fe.build_features(r["h"], r["a"])
            X = pd.DataFrame([feats])
            for col in feature_names:
                if col not in X.columns:
                    X[col] = 0.0
            X = X[feature_names]
            proba = model.predict_proba(X)[0]
            idx = int(np.argmax(proba))
            pred_result = ["H", "D", "A"][idx]
            feats_json = json.dumps({k: _num(v) for k, v in feats.items()},
                                    ensure_ascii=False, default=str)
            conn.execute(
                "INSERT OR REPLACE INTO predictions "
                "(match_id, model_version, pred_home_win, pred_draw, pred_away_win, "
                " pred_result, actual_result, features_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, NULL, ?, ?)",
                (r["match_id"], "v1.0", _num(proba[0]), _num(proba[1]), _num(proba[2]),
                 pred_result, feats_json, now.strftime("%Y-%m-%d %H:%M:%S")))
            ok += 1
            if ok <= 3:
                print(f"  ✓ {r['h']} vs {r['a']} → {pred_result} "
                      f"(胜{proba[0]:.2f}/平{proba[1]:.2f}/负{proba[2]:.2f})")
        except Exception as e:
            skip += 1
            print(f"  ✗ {r['h']} vs {r['a']} 跳过: {type(e).__name__}")

    conn.commit()
    conn.close()
    return {"matches": len(rows), "predicted": ok, "skipped": skip}


def backfill_results() -> dict:
    """把已完赛比赛的实际赛果回填到 predictions.actual_result, 并计算命中"""
    conn = _db()
    _ensure(conn)
    rows = conn.execute("""
        SELECT p.pred_id, p.pred_result, m.home_goals hg, m.away_goals ag
        FROM predictions p JOIN matches m ON m.match_id = p.match_id
        WHERE p.actual_result IS NULL AND m.status = 'FT'
          AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL""").fetchall()
    n = 0
    for r in rows:
        hg, ag = r["hg"], r["ag"]
        actual = "H" if hg > ag else ("D" if hg == ag else "A")
        hit = 1 if actual == r["pred_result"] else 0
        conn.execute("UPDATE predictions SET actual_result=?, hit=? WHERE pred_id=?",
                     (actual, hit, r["pred_id"]))
        n += 1
    conn.commit()
    conn.close()
    return {"backfilled": n}


def review_stats(league_id=None, include_backtest=True) -> dict:
    """复盘统计: 总体命中率 / 分联赛 / 分预测类型 / 最近明细"""
    conn = _db()
    _ensure(conn)
    bt = "" if include_backtest else " AND (p.is_backtest IS NULL OR p.is_backtest=0)"
    lg = "" if league_id is None else " AND m.league_id = ?"
    args = () if league_id is None else (league_id,)

    total = conn.execute(f"""
        SELECT COUNT(*) FROM predictions p JOIN matches m ON m.match_id=p.match_id
        WHERE p.actual_result IS NOT NULL{bt}{lg}""", args).fetchone()[0]
    hit = conn.execute(f"""
        SELECT COUNT(*) FROM predictions p JOIN matches m ON m.match_id=p.match_id
        WHERE p.actual_result IS NOT NULL AND p.hit=1{bt}{lg}""", args).fetchone()[0]

    by_league = [dict(r) for r in conn.execute(f"""
        SELECT l.name AS league, COUNT(*) AS n, SUM(p.hit) AS hit
        FROM predictions p JOIN matches m ON m.match_id=p.match_id
        JOIN leagues l ON l.league_id=m.league_id
        WHERE p.actual_result IS NOT NULL{bt}
        GROUP BY m.league_id ORDER BY n DESC""")]

    by_pred = [dict(r) for r in conn.execute(f"""
        SELECT p.pred_result AS pred, COUNT(*) AS n, SUM(p.hit) AS hit
        FROM predictions p JOIN matches m ON m.match_id=p.match_id
        WHERE p.actual_result IS NOT NULL{bt}
        GROUP BY p.pred_result""")]

    pending = conn.execute("""
        SELECT COUNT(*) FROM predictions p JOIN matches m ON m.match_id=p.match_id
        WHERE m.status = 'NS'""").fetchone()[0]

    recent = [dict(r) for r in conn.execute(f"""
        SELECT m.date, l.name AS league, th.name AS home, ta.name AS away,
               p.pred_result, p.actual_result, p.hit,
               m.home_goals, m.away_goals
        FROM predictions p JOIN matches m ON m.match_id=p.match_id
        JOIN leagues l ON l.league_id=m.league_id
        JOIN teams th ON th.team_id=m.home_team_id
        JOIN teams ta ON ta.team_id=m.away_team_id
        WHERE p.actual_result IS NOT NULL{bt}
        ORDER BY m.date DESC LIMIT 20""")]

    conn.close()
    return {"total": total, "hit": hit,
            "hit_rate": round(hit / total, 4) if total else None,
            "pending": pending, "by_league": by_league,
            "by_pred": by_pred, "recent": recent}


def predict_backtest(date_from, date_to, limit=None,
                     league_ids=(1, 2, 3, 4, 5), model_version="v1.0-backtest") -> dict:
    """历史回测: 对区间内已完赛比赛预测, 并立即回填实际赛果"""
    fe, model, feature_names = _load_engineers()
    conn = _db()
    _ensure(conn)
    sql = """SELECT m.match_id, th.name AS h, ta.name AS a, m.date,
                    m.home_goals hg, m.away_goals ag
             FROM matches m
             JOIN teams th ON th.team_id = m.home_team_id
             JOIN teams ta ON ta.team_id = m.away_team_id
             WHERE m.status='FT' AND date(m.date) BETWEEN ? AND ?
               AND m.league_id IN ({})
             ORDER BY m.date""".format(",".join("?" for _ in league_ids))
    rows = conn.execute(sql, (date_from, date_to) + league_ids).fetchall()
    if limit:
        rows = rows[:limit]
    ok = skip = hit = 0
    for r in rows:
        try:
            feats = fe.build_features(r["h"], r["a"])
            X = pd.DataFrame([feats])
            for col in feature_names:
                if col not in X.columns:
                    X[col] = 0.0
            X = X[feature_names]
            proba = model.predict_proba(X)[0]
            pred_result = ["H", "D", "A"][int(np.argmax(proba))]
            actual = "H" if r["hg"] > r["ag"] else ("D" if r["hg"] == r["ag"] else "A")
            is_hit = 1 if actual == pred_result else 0
            hit += is_hit
            conn.execute(
                "INSERT OR REPLACE INTO predictions "
                "(match_id, model_version, pred_home_win, pred_draw, pred_away_win,"
                " pred_result, actual_result, features_json, created_at, hit, is_backtest)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,1)",
                (r["match_id"], model_version, _num(proba[0]), _num(proba[1]),
                 _num(proba[2]), pred_result, actual,
                 json.dumps({k: _num(v) for k, v in feats.items()}, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S"), is_hit))
            ok += 1
        except Exception as e:
            skip += 1
            if skip <= 3:
                print(f"  ✗ {r['h']} vs {r['a']}: {type(e).__name__}")
    conn.commit()
    conn.close()
    return {"matches": len(rows), "predicted": ok, "skipped": skip,
            "hit": hit, "hit_rate": round(hit / ok, 4) if ok else None}


if __name__ == "__main__":
    info = predict_upcoming()
    print(f"\n完成后: 共 {info['matches']} 场, 成功预测 {info['predicted']}, 跳过 {info['skipped']}")
