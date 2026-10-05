"""优化版模型训练脚本 - 向量化特征工程
将O(n²)的逐场特征计算优化为O(n)的向量化计算
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
import xgboost as xgb
from sklearn.metrics import accuracy_score, log_loss, classification_report, confusion_matrix
import joblib
import json
from pathlib import Path
from config.settings import settings


def load_and_prepare_data():
    """加载并准备比赛数据"""
    df = pd.read_csv(settings.DATA_DIR / "processed" / "all_matches.csv", encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
    df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR", "Date"])
    df = df.sort_values("Date").reset_index(drop=True)

    # 结果编码
    df["result"] = df["FTR"].map({"H": 0, "D": 1, "A": 2})

    print(f"已加载 {len(df)} 场比赛")
    print(f"时间范围: {df['Date'].min().strftime('%Y-%m-%d')} ~ {df['Date'].max().strftime('%Y-%m-%d')}")
    print(f"结果分布: 主胜={np.sum(df['result']==0)}, 平局={np.sum(df['result']==1)}, 客胜={np.sum(df['result']==2)}")
    return df


def build_features_vectorized(df):
    """向量化构建特征 - O(n)复杂度

    核心思路: 用expanding窗口计算每支球队到每场比赛之前的累计统计,
    然后用merge的方式为主队和客队分别匹配特征, 避免逐场循环。
    """
    print("\n构建向量化特征...")

    # 为每场比赛分配唯一ID
    df = df.copy()
    df["match_id"] = range(len(df))

    # === 构建球队-比赛维度的长表 ===
    # 主队视角
    home_df = df[["match_id", "Date", "HomeTeam", "FTHG", "FTAG", "FTR"]].copy()
    home_df["team"] = home_df["HomeTeam"]
    home_df["is_home"] = 1
    home_df["goals_for"] = home_df["FTHG"]
    home_df["goals_against"] = home_df["FTAG"]
    home_df["win"] = (home_df["FTR"] == "H").astype(int)
    home_df["draw"] = (home_df["FTR"] == "D").astype(int)
    home_df["loss"] = (home_df["FTR"] == "A").astype(int)
    home_df["points"] = home_df["win"] * 3 + home_df["draw"]

    # 客队视角
    away_df = df[["match_id", "Date", "AwayTeam", "FTHG", "FTAG", "FTR"]].copy()
    away_df["team"] = away_df["AwayTeam"]
    away_df["is_home"] = 0
    away_df["goals_for"] = away_df["FTAG"]
    away_df["goals_against"] = away_df["FTHG"]
    away_df["win"] = (away_df["FTR"] == "A").astype(int)
    away_df["draw"] = (away_df["FTR"] == "D").astype(int)
    away_df["loss"] = (away_df["FTR"] == "H").astype(int)
    away_df["points"] = away_df["win"] * 3 + away_df["draw"]

    # 合并
    team_matches = pd.concat([home_df, away_df], ignore_index=True)
    team_matches = team_matches.sort_values(["team", "Date"]).reset_index(drop=True)

    # === 计算累计统计（到每场比赛之前） ===
    # 用groupby + shift + expanding实现"只用历史数据"
    g = team_matches.groupby("team")

    # 累计场次、胜平负、积分、进球失球（shift(1)确保不用当前比赛）
    for col in ["win", "draw", "loss", "points", "goals_for", "goals_against"]:
        team_matches[f"cum_{col}"] = g[col].shift(1).groupby(team_matches["team"]).cumsum()
        team_matches[f"cum_{col}"] = team_matches[f"cum_{col}"].fillna(0)

    team_matches["cum_matches"] = g.cumcount()  # 之前的比赛场次数

    # 近5场和近10场统计（用rolling + shift）
    for window in [5, 10]:
        for col in ["points", "goals_for", "goals_against", "win"]:
            team_matches[f"last{window}_{col}"] = g[col].transform(
                lambda x: x.shift(1).rolling(window=window, min_periods=1).sum()
            )
            team_matches[f"last{window}_{col}"] = team_matches[f"last{window}_{col}"].fillna(0)

    # 主客场累计统计
    home_g = team_matches[team_matches["is_home"] == 1].groupby("team")
    away_g = team_matches[team_matches["is_home"] == 0].groupby("team")

    for col in ["win", "draw", "loss", "goals_for", "goals_against"]:
        team_matches.loc[team_matches["is_home"] == 1, f"home_cum_{col}"] = \
            home_g[col].shift(1).groupby(team_matches[team_matches["is_home"] == 1]["team"]).cumsum().fillna(0)
        team_matches.loc[team_matches["is_home"] == 0, f"away_cum_{col}"] = \
            away_g[col].shift(1).groupby(team_matches[team_matches["is_home"] == 0]["team"]).cumsum().fillna(0)

    # === 计算Elo评级（简化版，向量化） ===
    # 用迭代方式计算Elo（必须按时间顺序）
    print("  计算Elo评级...")
    elo_ratings = {}  # team -> rating
    home_elo_list = []
    away_elo_list = []

    for _, row in df.iterrows():
        home = row["HomeTeam"]
        away = row["AwayTeam"]
        home_elo = elo_ratings.get(home, 1500.0)
        away_elo = elo_ratings.get(away, 1500.0)
        home_elo_list.append(home_elo)
        away_elo_list.append(away_elo)

        # 更新Elo
        home_adv = 65.0
        k = 32.0
        exp_home = 1.0 / (1.0 + 10 ** ((away_elo - (home_elo + home_adv)) / 400.0))
        if row["FTR"] == "H":
            actual_home = 1.0
        elif row["FTR"] == "D":
            actual_home = 0.5
        else:
            actual_home = 0.0
        goal_diff = abs(row["FTHG"] - row["FTAG"])
        k_mult = 1.0 + 0.1 * goal_diff
        delta = k * k_mult * (actual_home - exp_home)
        elo_ratings[home] = home_elo + delta
        elo_ratings[away] = away_elo - delta

    df["home_elo"] = home_elo_list
    df["away_elo"] = away_elo_list

    # === 为主队和客队匹配特征 ===
    print("  匹配球队特征...")
    # 只保留需要的列
    feature_cols = [
        "match_id", "team", "cum_matches", "cum_win", "cum_draw", "cum_loss",
        "cum_points", "cum_goals_for", "cum_goals_against",
        "last5_points", "last5_goals_for", "last5_goals_against", "last5_win",
        "last10_points", "last10_goals_for", "last10_goals_against", "last10_win",
    ]

    # 主队特征
    home_features = team_matches[team_matches["is_home"] == 1][feature_cols].copy()
    home_features = home_features.add_prefix("home_")
    home_features = home_features.rename(columns={"home_match_id": "match_id", "home_team": "HomeTeam"})

    # 客队特征
    away_features = team_matches[team_matches["is_home"] == 0][feature_cols].copy()
    away_features = away_features.add_prefix("away_")
    away_features = away_features.rename(columns={"away_match_id": "match_id", "away_team": "AwayTeam"})

    # 合并
    result = df.merge(home_features, on=["match_id", "HomeTeam"], how="left")
    result = result.merge(away_features, on=["match_id", "AwayTeam"], how="left")

    # === 构建最终特征 ===
    features = pd.DataFrame()

    # 1. Elo特征
    features["home_elo"] = result["home_elo"]
    features["away_elo"] = result["away_elo"]
    features["elo_diff"] = result["home_elo"] - result["away_elo"]
    features["elo_expected_home"] = 1.0 / (1.0 + 10 ** ((result["away_elo"] - (result["home_elo"] + 65.0)) / 400.0))
    features["home_elo_advantage"] = result["home_elo"] + 65.0 - result["away_elo"]

    # 2. 近期状态特征
    features["home_ppg_5"] = result["home_last5_points"] / 5.0
    features["away_ppg_5"] = result["away_last5_points"] / 5.0
    features["home_ppg_10"] = result["home_last10_points"] / 10.0
    features["away_ppg_10"] = result["away_last10_points"] / 10.0
    features["home_goals_for_5"] = result["home_last5_goals_for"] / 5.0
    features["away_goals_for_5"] = result["away_last5_goals_for"] / 5.0
    features["home_goals_against_5"] = result["home_last5_goals_against"] / 5.0
    features["away_goals_against_5"] = result["away_last5_goals_against"] / 5.0
    features["home_wins_5"] = result["home_last5_win"]
    features["away_wins_5"] = result["away_last5_win"]
    features["form_diff_ppg_5"] = features["home_ppg_5"] - features["away_ppg_5"]
    features["form_diff_goals_5"] = features["home_goals_for_5"] - features["away_goals_for_5"]

    # 3. 累计统计特征
    features["home_total_matches"] = result["home_cum_matches"]
    features["away_total_matches"] = result["away_cum_matches"]
    features["home_total_win_rate"] = result["home_cum_win"] / result["home_cum_matches"].replace(0, 1)
    features["away_total_win_rate"] = result["away_cum_win"] / result["away_cum_matches"].replace(0, 1)
    features["home_avg_goals_for"] = result["home_cum_goals_for"] / result["home_cum_matches"].replace(0, 1)
    features["away_avg_goals_for"] = result["away_cum_goals_for"] / result["away_cum_matches"].replace(0, 1)
    features["home_avg_goals_against"] = result["home_cum_goals_against"] / result["home_cum_matches"].replace(0, 1)
    features["away_avg_goals_against"] = result["away_cum_goals_against"] / result["away_cum_matches"].replace(0, 1)

    # 4. 攻防效率
    league_avg_goals = (result["FTHG"].mean() + result["FTAG"].mean()) / 2
    features["home_attack_strength"] = features["home_avg_goals_for"] / league_avg_goals
    features["away_attack_strength"] = features["away_avg_goals_for"] / league_avg_goals
    features["home_defense_strength"] = features["home_avg_goals_against"] / league_avg_goals
    features["away_defense_strength"] = features["away_avg_goals_against"] / league_avg_goals
    features["expected_home_goals"] = features["home_attack_strength"] * features["away_defense_strength"] * league_avg_goals
    features["expected_away_goals"] = features["away_attack_strength"] * features["home_defense_strength"] * league_avg_goals

    # 5. 主客场特征（如果有）
    if "home_home_cum_win" in result.columns:
        home_home_total = (result["home_home_cum_win"] + result["home_home_cum_draw"] + result["home_home_cum_loss"]).replace(0, 1)
        features["home_home_win_rate"] = result["home_home_cum_win"] / home_home_total
        away_away_total = (result["away_away_cum_win"] + result["away_away_cum_draw"] + result["away_away_cum_loss"]).replace(0, 1)
        features["away_away_win_rate"] = result["away_away_cum_win"] / away_away_total
    else:
        features["home_home_win_rate"] = 0.4
        features["away_away_win_rate"] = 0.3

    # 填充NaN
    features = features.fillna(0)

    # 标签
    labels = result["result"].values

    # 过滤掉前100场（数据太少特征不可靠）
    valid_mask = result["home_cum_matches"] >= 10
    features = features[valid_mask].reset_index(drop=True)
    labels = labels[valid_mask]

    print(f"特征构建完成: {len(features)} 样本, {features.shape[1]} 维特征")
    print(f"特征列表: {list(features.columns)}")

    # 保存特征
    features_with_label = features.copy()
    features_with_label["label"] = labels
    features_with_label.to_csv(settings.DATA_DIR / "processed" / "training_features.csv",
                                index=False, encoding="utf-8-sig")
    print(f"特征已保存: {settings.DATA_DIR / 'processed' / 'training_features.csv'}")

    return features, labels


def train_model(X, y):
    """训练XGBoost模型"""
    print("\n训练XGBoost模型...")

    # 时间序列分割（最后20%作为测试集）
    split_idx = int(len(X) * 0.8)
    X_train, X_test = X.iloc[:split_idx], X.iloc[split_idx:]
    y_train, y_test = y[:split_idx], y[split_idx:]

    print(f"训练集: {len(X_train)}, 测试集: {len(X_test)}")

    model = xgb.XGBClassifier(
        objective="multi:softprob",
        num_class=3,
        n_estimators=300,
        max_depth=5,
        learning_rate=0.05,
        subsample=0.8,
        colsample_bytree=0.8,
        reg_alpha=0.1,
        reg_lambda=1.0,
        random_state=42,
        eval_metric="mlogloss",
        early_stopping_rounds=50,
    )

    model.fit(X_train, y_train, eval_set=[(X_test, y_test)], verbose=False)

    # 评估
    y_pred = model.predict(X_test)
    y_proba = model.predict_proba(X_test)
    accuracy = accuracy_score(y_test, y_pred)
    logloss = log_loss(y_test, y_proba)
    conf_matrix = confusion_matrix(y_test, y_pred)

    # 各类别准确率
    class_acc = {}
    for i, label in enumerate(["主胜", "平局", "客胜"]):
        mask = y_test == i
        if mask.sum() > 0:
            class_acc[label] = round(accuracy_score(y_test[mask], y_pred[mask]), 4)

    print(f"\n训练完成!")
    print(f"  测试集准确率: {accuracy:.2%}")
    print(f"  测试集LogLoss: {logloss:.4f}")
    print(f"  各类别准确率: {class_acc}")
    print(f"  混淆矩阵:")
    print(f"    实际\\预测  主胜  平局  客胜")
    print(f"    主胜      {conf_matrix[0][0]:4d}  {conf_matrix[0][1]:4d}  {conf_matrix[0][2]:4d}")
    print(f"    平局      {conf_matrix[1][0]:4d}  {conf_matrix[1][1]:4d}  {conf_matrix[1][2]:4d}")
    print(f"    客胜      {conf_matrix[2][0]:4d}  {conf_matrix[2][1]:4d}  {conf_matrix[2][2]:4d}")

    # 特征重要性
    importance = sorted(zip(X.columns, model.feature_importances_), key=lambda x: x[1], reverse=True)
    print(f"\n  Top 10 重要特征:")
    for i, (feat, imp) in enumerate(importance[:10]):
        print(f"    {i+1}. {feat}: {imp:.6f}")

    # 保存模型
    model_path = settings.MODEL_DIR / "xgb_match_predictor.joblib"
    joblib.dump({
        "model": model,
        "features": list(X.columns),
        "label_map": {0: "主胜", 1: "平局", 2: "客胜"},
        "train_date": pd.Timestamp.now().isoformat(),
        "train_samples": len(X_train),
        "test_samples": len(X_test),
        "accuracy": accuracy,
    }, model_path)
    print(f"\n  模型已保存: {model_path}")

    # 保存特征重要性
    with open(settings.MODEL_DIR / "feature_importance.json", "w", encoding="utf-8") as f:
        json.dump([{"feature": k, "importance": round(float(v), 6)} for k, v in importance],
                  f, ensure_ascii=False, indent=2)

    # 保存评估结果
    with open(settings.MODEL_DIR / "evaluation_result.json", "w", encoding="utf-8") as f:
        json.dump({
            "accuracy": round(accuracy, 4),
            "log_loss": round(logloss, 4),
            "class_accuracy": class_acc,
            "confusion_matrix": conf_matrix.tolist(),
            "top_features": [{"feature": k, "importance": round(float(v), 6)} for k, v in importance[:10]],
        }, f, ensure_ascii=False, indent=2)

    return model


def main():
    print("\n" + "=" * 60)
    print("  足球比赛预测模型 - 优化版训练脚本（向量化）")
    print("=" * 60 + "\n")

    try:
        df = load_and_prepare_data()
        X, y = build_features_vectorized(df)
        model = train_model(X, y)

        print("\n" + "=" * 60)
        print("  模型训练完成!")
        print("=" * 60)
        print(f"\n模型文件: {settings.MODEL_DIR / 'xgb_match_predictor.joblib'}")
        print("\n下一步:")
        print("  1. 启动后端: uvicorn src.main:app --reload")
        print("  2. 启动前端: streamlit run frontend/app.py")
        print()

    except Exception as e:
        print(f"\n训练失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
