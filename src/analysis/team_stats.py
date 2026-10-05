"""球队统计分析 - 近期状态、主客场战绩、历史交锋"""
import pandas as pd
import numpy as np
from typing import Dict, Optional


class TeamStats:
    """球队统计分析"""

    def __init__(self, matches_df: pd.DataFrame):
        """
        Args:
            matches_df: 包含 HomeTeam, AwayTeam, FTHG, FTAG, FTR, Date 等列
        """
        self.df = matches_df.copy()
        if "Date" in self.df.columns:
            self.df["Date"] = pd.to_datetime(self.df["Date"], errors="coerce")

    def recent_form(self, team: str, n: int = 5) -> Dict:
        """计算球队近n场状态

        Returns:
            包含胜平负、进球失球、积分、场均数据的dict
        """
        # 主队视角
        home = self.df[self.df["HomeTeam"] == team].copy()
        home["team_goals"] = home["FTHG"]
        home["opp_goals"] = home["FTAG"]
        home["is_home"] = True
        home["result"] = home["FTR"].map({"H": "W", "D": "D", "A": "L"})

        # 客队视角
        away = self.df[self.df["AwayTeam"] == team].copy()
        away["team_goals"] = away["FTAG"]
        away["opp_goals"] = away["FTHG"]
        away["is_home"] = False
        away["result"] = away["FTR"].map({"H": "L", "D": "D", "A": "W"})

        all_matches = pd.concat([home, away])
        all_matches = all_matches[all_matches["result"].notna()]
        all_matches = all_matches.sort_values("Date", ascending=False)

        recent = all_matches.head(n)
        if len(recent) == 0:
            return {"team": team, "matches": 0, "wins": 0, "draws": 0,
                    "losses": 0, "goals_for": 0, "goals_against": 0,
                    "points": 0, "points_per_game": 0,
                    "avg_goals_for": 0, "avg_goals_against": 0,
                    "form_string": ""}

        points = recent["result"].map({"W": 3, "D": 1, "L": 0}).sum()
        form_string = "".join(recent["result"].tolist())

        return {
            "team": team,
            "matches": len(recent),
            "wins": int((recent["result"] == "W").sum()),
            "draws": int((recent["result"] == "D").sum()),
            "losses": int((recent["result"] == "L").sum()),
            "goals_for": int(recent["team_goals"].sum()),
            "goals_against": int(recent["opp_goals"].sum()),
            "points": int(points),
            "points_per_game": round(points / len(recent), 2),
            "avg_goals_for": round(recent["team_goals"].mean(), 2),
            "avg_goals_against": round(recent["opp_goals"].mean(), 2),
            "form_string": form_string,
            "home_wins": int((recent[recent["is_home"]]["result"] == "W").sum()),
            "away_wins": int((recent[~recent["is_home"]]["result"] == "W").sum()),
        }

    def home_away_record(self, team: str) -> Dict:
        """主客场战绩"""
        home = self.df[(self.df["HomeTeam"] == team) & self.df["FTR"].notna()]
        away = self.df[(self.df["AwayTeam"] == team) & self.df["FTR"].notna()]

        return {
            "home_played": len(home),
            "home_wins": int((home["FTR"] == "H").sum()),
            "home_draws": int((home["FTR"] == "D").sum()),
            "home_losses": int((home["FTR"] == "A").sum()),
            "home_goals_for": int(home["FTHG"].sum()),
            "home_goals_against": int(home["FTAG"].sum()),
            "home_points": int((home["FTR"] == "H").sum() * 3 + (home["FTR"] == "D").sum()),
            "away_played": len(away),
            "away_wins": int((away["FTR"] == "A").sum()),
            "away_draws": int((away["FTR"] == "D").sum()),
            "away_losses": int((away["FTR"] == "H").sum()),
            "away_goals_for": int(away["FTAG"].sum()),
            "away_goals_against": int(away["FTHG"].sum()),
            "away_points": int((away["FTR"] == "A").sum() * 3 + (away["FTR"] == "D").sum()),
        }

    def head_to_head(self, team_a: str, team_b: str, n: int = 10) -> Dict:
        """历史交锋记录"""
        h2h = self.df[
            ((self.df["HomeTeam"] == team_a) & (self.df["AwayTeam"] == team_b)) |
            ((self.df["HomeTeam"] == team_b) & (self.df["AwayTeam"] == team_a))
        ].copy()
        h2h = h2h[h2h["FTR"].notna()].sort_values("Date", ascending=False).head(n)

        a_wins = int(((h2h["HomeTeam"] == team_a) & (h2h["FTR"] == "H")).sum() +
                      ((h2h["AwayTeam"] == team_a) & (h2h["FTR"] == "A")).sum())
        b_wins = int(((h2h["HomeTeam"] == team_b) & (h2h["FTR"] == "H")).sum() +
                      ((h2h["AwayTeam"] == team_b) & (h2h["FTR"] == "A")).sum())
        draws = int((h2h["FTR"] == "D").sum())

        # 近期交锋趋势
        recent_results = []
        for _, row in h2h.iterrows():
            if row["HomeTeam"] == team_a:
                recent_results.append("W" if row["FTR"] == "H" else
                                      ("D" if row["FTR"] == "D" else "L"))
            else:
                recent_results.append("W" if row["FTR"] == "A" else
                                      ("D" if row["FTR"] == "D" else "L"))

        return {
            "team_a": team_a, "team_b": team_b,
            "team_a_wins": a_wins, "team_b_wins": b_wins, "draws": draws,
            "total": len(h2h),
            "team_a_win_rate": round(a_wins / len(h2h), 4) if len(h2h) > 0 else 0,
            "recent_form_a": "".join(recent_results),
        }

    def get_all_teams(self) -> list:
        """获取数据中所有球队名"""
        teams = set(self.df["HomeTeam"].dropna().tolist() +
                    self.df["AwayTeam"].dropna().tolist())
        return sorted(list(teams))

    def league_goals_avg(self) -> Dict:
        """联赛场均进球统计"""
        finished = self.df[self.df["FTR"].notna()]
        total_goals = finished["FTHG"].sum() + finished["FTAG"].sum()
        return {
            "matches": len(finished),
            "total_goals": int(total_goals),
            "avg_goals_per_match": round(total_goals / len(finished), 2) if len(finished) > 0 else 0,
            "avg_home_goals": round(finished["FTHG"].mean(), 2),
            "avg_away_goals": round(finished["FTAG"].mean(), 2),
            "home_win_rate": round((finished["FTR"] == "H").mean(), 4),
            "draw_rate": round((finished["FTR"] == "D").mean(), 4),
            "away_win_rate": round((finished["FTR"] == "A").mean(), 4),
        }
