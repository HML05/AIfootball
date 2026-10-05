"""特征工程 - 预测模型的核心，6大类40+维特征
特征分类:
1. Elo实力特征 (5维)
2. 近期状态特征 (12维)
3. 主客场特征 (6维)
4. 历史交锋特征 (4维)
5. 攻防效率特征 (6维)
6. 联赛排名特征 (3维)
"""
import pandas as pd
import numpy as np
from typing import Dict
from src.analysis.elo_rating import EloRating
from src.analysis.team_stats import TeamStats


class FeatureEngineer:
    """比赛预测特征工程"""

    def __init__(self, matches_df: pd.DataFrame, elo: EloRating = None):
        """
        Args:
            matches_df: 历史比赛数据（用于计算统计特征）
            elo: 已训练的Elo评级系统（如不提供则自动训练）
        """
        self.df = matches_df.copy()
        if "Date" in self.df.columns:
            self.df["Date"] = pd.to_datetime(self.df["Date"], errors="coerce")

        # 自动训练Elo
        if elo is None:
            self.elo = EloRating()
            self.elo.batch_update(self.df)
        else:
            self.elo = elo

        self.stats = TeamStats(self.df)
        self._league_avg_goals = None

    def build_features(self, home_team: str, away_team: str,
                       match_date=None) -> Dict:
        """为一场比赛构建完整特征向量

        Args:
            home_team: 主队名
            away_team: 客队名
            match_date: 比赛日期（用于时间相关特征）

        Returns:
            特征dict（约36维）
        """
        features = {}

        # === 1. Elo实力特征 (5维) ===
        home_elo = self.elo.get_rating(home_team)
        away_elo = self.elo.get_rating(away_team)
        features["home_elo"] = home_elo
        features["away_elo"] = away_elo
        features["elo_diff"] = home_elo - away_elo
        features["elo_expected_home_win"] = self.elo.expected_score(home_elo, away_elo, True)
        features["home_elo_advantage"] = home_elo + self.elo.home_advantage - away_elo

        # === 2. 近期状态特征 (12维) ===
        home_form_5 = self.stats.recent_form(home_team, 5)
        away_form_5 = self.stats.recent_form(away_team, 5)
        home_form_10 = self.stats.recent_form(home_team, 10)
        away_form_10 = self.stats.recent_form(away_team, 10)

        features["home_ppg_5"] = home_form_5["points_per_game"]
        features["away_ppg_5"] = away_form_5["points_per_game"]
        features["home_ppg_10"] = home_form_10["points_per_game"]
        features["away_ppg_10"] = away_form_10["points_per_game"]
        features["home_goals_for_5"] = home_form_5["avg_goals_for"]
        features["away_goals_for_5"] = away_form_5["avg_goals_for"]
        features["home_goals_against_5"] = home_form_5["avg_goals_against"]
        features["away_goals_against_5"] = away_form_5["avg_goals_against"]
        features["home_wins_5"] = home_form_5["wins"]
        features["away_wins_5"] = away_form_5["wins"]
        features["form_diff_ppg_5"] = home_form_5["points_per_game"] - away_form_5["points_per_game"]
        features["form_diff_goals_5"] = home_form_5["avg_goals_for"] - away_form_5["avg_goals_for"]

        # === 3. 主客场特征 (6维) ===
        home_ha = self.stats.home_away_record(home_team)
        away_ha = self.stats.home_away_record(away_team)

        home_home_total = max(home_ha["home_wins"] + home_ha["home_draws"] + home_ha["home_losses"], 1)
        away_away_total = max(away_ha["away_wins"] + away_ha["away_draws"] + away_ha["away_losses"], 1)

        features["home_home_win_rate"] = home_ha["home_wins"] / home_home_total
        features["away_away_win_rate"] = away_ha["away_wins"] / away_away_total
        features["home_home_goals_for_avg"] = home_ha["home_goals_for"] / home_home_total
        features["home_home_goals_against_avg"] = home_ha["home_goals_against"] / home_home_total
        features["away_away_goals_for_avg"] = away_ha["away_goals_for"] / away_away_total
        features["away_away_goals_against_avg"] = away_ha["away_goals_against"] / away_away_total

        # === 4. 历史交锋特征 (4维) ===
        h2h = self.stats.head_to_head(home_team, away_team, 10)
        features["h2h_home_wins"] = h2h["team_a_wins"]
        features["h2h_away_wins"] = h2h["team_b_wins"]
        features["h2h_draws"] = h2h["draws"]
        features["h2h_home_win_rate"] = h2h["team_a_win_rate"]

        # === 5. 攻防效率特征 (6维) ===
        features["home_attack_strength"] = self._attack_strength(home_team)
        features["away_attack_strength"] = self._attack_strength(away_team)
        features["home_defense_strength"] = self._defense_strength(home_team)
        features["away_defense_strength"] = self._defense_strength(away_team)
        # 预期进球估算 = 进攻强度 * 对手防守强度 * 联赛场均进球
        league_avg = self._get_league_avg_goals()
        features["expected_home_goals"] = features["home_attack_strength"] * features["away_defense_strength"] * league_avg
        features["expected_away_goals"] = features["away_attack_strength"] * features["home_defense_strength"] * league_avg

        # === 6. 联赛排名特征 (3维) ===
        try:
            table = TeamStats.compute_league_table(self.df)
            home_pos = table[table["team"] == home_team].index
            away_pos = table[table["team"] == away_team].index
            features["home_league_position"] = int(home_pos[0]) if len(home_pos) > 0 else 10
            features["away_league_position"] = int(away_pos[0]) if len(away_pos) > 0 else 10
        except Exception:
            features["home_league_position"] = 10
            features["away_league_position"] = 10
        features["position_diff"] = features["home_league_position"] - features["away_league_position"]

        return features

    def _get_league_avg_goals(self) -> float:
        """获取联赛场均进球（缓存）"""
        if self._league_avg_goals is None:
            league_stats = self.stats.league_goals_avg()
            self._league_avg_goals = league_stats["avg_goals_per_match"] / 2  # 每队场均
        return self._league_avg_goals or 1.35

    def _attack_strength(self, team: str) -> float:
        """进攻强度 = 球队场均进球 / 联赛每队场均进球"""
        team_goals = (self.df[self.df["HomeTeam"] == team]["FTHG"].sum() +
                       self.df[self.df["AwayTeam"] == team]["FTAG"].sum())
        matches = len(self.df[(self.df["HomeTeam"] == team) | (self.df["AwayTeam"] == team)])
        if matches == 0:
            return 1.0
        team_avg = team_goals / matches
        league_avg = self._get_league_avg_goals()
        return team_avg / league_avg if league_avg > 0 else 1.0

    def _defense_strength(self, team: str) -> float:
        """防守强度 = 球队场均失球 / 联赛每队场均失球（越低越好）"""
        team_conceded = (self.df[self.df["HomeTeam"] == team]["FTAG"].sum() +
                          self.df[self.df["AwayTeam"] == team]["FTHG"].sum())
        matches = len(self.df[(self.df["HomeTeam"] == team) | (self.df["AwayTeam"] == team)])
        if matches == 0:
            return 1.0
        team_avg = team_conceded / matches
        league_avg = self._get_league_avg_goals()
        return team_avg / league_avg if league_avg > 0 else 1.0

    def build_training_dataset(self, min_history: int = 50) -> tuple:
        """从历史比赛构建训练集
        关键: 必须按时间顺序，只用当前比赛之前的数据构建特征，防止数据泄露！

        Returns:
            (X DataFrame, y array, match_info list)
        """
        X_list, y_list, info_list = [], [], []

        df_sorted = self.df.sort_values("Date").reset_index(drop=True)
        total = len(df_sorted)

        for idx in range(total):
            row = df_sorted.iloc[idx]
            if pd.isna(row.get("FTR")):
                continue

            # 只用当前比赛之前的数据
            historical_df = df_sorted.iloc[:idx]
            if len(historical_df) < min_history:
                continue

            try:
                # 用历史数据重新训练Elo和统计
                hist_elo = EloRating()
                hist_elo.batch_update(historical_df)
                fe = FeatureEngineer(historical_df, hist_elo)
                features = fe.build_features(str(row["HomeTeam"]), str(row["AwayTeam"]))

                X_list.append(features)
                y_list.append({"H": 0, "D": 1, "A": 2}[row["FTR"]])
                info_list.append({
                    "date": str(row["Date"]),
                    "home": str(row["HomeTeam"]),
                    "away": str(row["AwayTeam"]),
                    "result": row["FTR"],
                })
            except Exception as e:
                continue

            # 进度提示（每100场）
            if (idx + 1) % 100 == 0:
                print(f"  已处理 {idx+1}/{total} 场比赛，有效样本 {len(X_list)}")

        X = pd.DataFrame(X_list)
        y = np.array(y_list)
        return X, y, info_list
