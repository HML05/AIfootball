"""Elo评级系统 - 衡量球队实力的核心指标
基于国际象棋Elo算法，适配足球比赛（含主场优势、净胜球加成）
"""
from typing import Dict, Optional
import pandas as pd


class EloRating:
    """球队Elo评级系统"""

    def __init__(self, initial_rating: float = 1500.0,
                 home_advantage: float = 65.0,
                 k_factor: float = 32.0):
        """
        Args:
            initial_rating: 初始评级（新球队默认值）
            home_advantage: 主场优势加成（Elo分数）
            k_factor: K系数，控制评级变化幅度
        """
        self.ratings: Dict[str, float] = {}
        self.initial_rating = initial_rating
        self.home_advantage = home_advantage
        self.k_factor = k_factor
        self.history: list = []  # 评级变化历史

    def get_rating(self, team: str) -> float:
        """获取球队当前Elo评级"""
        return self.ratings.get(team, self.initial_rating)

    def set_rating(self, team: str, rating: float):
        """设置球队评级"""
        self.ratings[team] = rating

    def expected_score(self, rating_a: float, rating_b: float,
                       is_home_a: bool = True) -> float:
        """计算A队预期胜率（0-1）

        Args:
            rating_a: A队评级
            rating_b: B队评级
            is_home_a: A队是否为主场

        Returns:
            A队预期胜率
        """
        ra = rating_a + (self.home_advantage if is_home_a else 0)
        rb = rating_b
        return 1.0 / (1.0 + 10 ** ((rb - ra) / 400.0))

    def update_after_match(self, home_team: str, away_team: str,
                           home_goals: int, away_goals: int) -> dict:
        """比赛后更新Elo评级

        Returns:
            更新详情dict
        """
        # 实际结果
        if home_goals > away_goals:
            actual_home, actual_away = 1.0, 0.0
        elif home_goals < away_goals:
            actual_home, actual_away = 0.0, 1.0
        else:
            actual_home = actual_away = 0.5

        # 赛前评级
        pre_home = self.get_rating(home_team)
        pre_away = self.get_rating(away_team)

        # 预期结果
        exp_home = self.expected_score(pre_home, pre_away, True)
        exp_away = 1.0 - exp_home

        # 净胜球加成（赢越多，K越大，变化越大）
        goal_diff = abs(home_goals - away_goals)
        k_multiplier = 1.0 + 0.1 * goal_diff  # 每多净胜1球，K增加10%

        # 评级变化
        delta_home = self.k_factor * k_multiplier * (actual_home - exp_home)
        delta_away = self.k_factor * k_multiplier * (actual_away - exp_away)

        # 更新
        self.ratings[home_team] = pre_home + delta_home
        self.ratings[away_team] = pre_away + delta_away

        # 记录历史
        record = {
            "home_team": home_team, "away_team": away_team,
            "home_goals": home_goals, "away_goals": away_goals,
            "pre_home_elo": round(pre_home, 2),
            "pre_away_elo": round(pre_away, 2),
            "post_home_elo": round(self.ratings[home_team], 2),
            "post_away_elo": round(self.ratings[away_team], 2),
            "delta_home": round(delta_home, 2),
            "delta_away": round(delta_away, 2),
            "expected_home_win": round(exp_home, 4),
        }
        self.history.append(record)
        return record

    def batch_update(self, matches_df: pd.DataFrame):
        """批量更新（必须按时间顺序）

        Args:
            matches_df: 包含 HomeTeam, AwayTeam, FTHG, FTAG, Date 列的DataFrame
        """
        df = matches_df.sort_values("Date").reset_index(drop=True)
        for _, row in df.iterrows():
            if pd.notna(row.get("FTHG")) and pd.notna(row.get("FTAG")):
                self.update_after_match(
                    str(row["HomeTeam"]), str(row["AwayTeam"]),
                    int(row["FTHG"]), int(row["FTAG"])
                )

    def get_ranking(self, top_n: int = None) -> pd.DataFrame:
        """获取Elo排名"""
        df = pd.DataFrame([
            {"team": team, "elo_rating": round(rating, 1)}
            for team, rating in self.ratings.items()
        ])
        df = df.sort_values("elo_rating", ascending=False).reset_index(drop=True)
        df.index = df.index + 1
        if top_n:
            df = df.head(top_n)
        return df

    def predict_match(self, home_team: str, away_team: str) -> dict:
        """基于Elo预测比赛胜率"""
        home_elo = self.get_rating(home_team)
        away_elo = self.get_rating(away_team)
        exp_home = self.expected_score(home_elo, away_elo, True)

        # 简化的平局概率估算（Elo只直接给出主胜概率，这里用经验公式）
        # 实力越接近，平局概率越高
        elo_diff = abs(home_elo + self.home_advantage - away_elo)
        draw_prob = max(0.15, 0.30 - elo_diff / 2000)  # 15%-30%

        home_win = exp_home * (1 - draw_prob)
        away_win = (1 - exp_home) * (1 - draw_prob)

        # 归一化
        total = home_win + draw_prob + away_win
        return {
            "home_win": round(home_win / total, 4),
            "draw": round(draw_prob / total, 4),
            "away_win": round(away_win / total, 4),
            "home_elo": round(home_elo, 1),
            "away_elo": round(away_elo, 1),
            "elo_diff": round(home_elo - away_elo, 1),
        }
