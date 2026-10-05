"""AI Agent工具链 - LangChain Tool定义
Agent通过这些工具获取真实数据，避免LLM编造信息
"""
from langchain.tools import tool
from typing import Optional
from src.prediction.predictor import MatchPredictor
from src.prediction.feature_engineer import FeatureEngineer
from src.analysis.team_stats import TeamStats
from src.analysis.elo_rating import EloRating
from src.database.crud import (get_team_by_name, get_player_by_name,
                                 get_upcoming_matches, get_db)
import pandas as pd


class FootballAgentTools:
    """足球分析Agent可用的工具集"""

    def __init__(self, matches_df: pd.DataFrame,
                 predictor: Optional[MatchPredictor] = None,
                 elo: Optional[EloRating] = None):
        """
        Args:
            matches_df: 历史比赛数据
            predictor: 已加载的预测模型（可选，没有则用Elo预测）
            elo: 已训练的Elo系统（可选）
        """
        self.matches_df = matches_df
        self.team_stats = TeamStats(matches_df)
        self.elo = elo or EloRating()
        if elo is None:
            self.elo.batch_update(matches_df)
        self.predictor = predictor
        self.feature_engineer = FeatureEngineer(matches_df, self.elo)

    @tool
    def get_team_info(self, team_name: str) -> str:
        """获取球队基本信息，包括主教练、主场、成立时间、Elo评级、联赛排名等。
        输入: 球队中文名（如 '曼城'、'阿森纳'）"""
        # 先查数据库
        try:
            with get_db() as db:
                team = get_team_by_name(db, team_name)
                if team:
                    return f"""球队: {team.name} ({team.name_en or 'N/A'})
主教练: {team.manager or '未知'}
主场: {team.stadium or '未知'} (容量{team.capacity or '未知'})
成立: {team.founded or '未知'}年
Elo评级: {team.elo_rating or self.elo.get_rating(team_name):.0f}"""
        except Exception:
            pass

        # 数据库没有则用计算数据
        elo = self.elo.get_rating(team_name)
        form = self.team_stats.recent_form(team_name, 5)
        return f"""球队: {team_name}
Elo评级: {elo:.0f}
近5场: {form['wins']}胜{form['draws']}平{form['losses']}负
近5场积分: {form['points']} (场均{form['points_per_game']})
近5场进球: {form['goals_for']} (场均{form['avg_goals_for']})
近5场失球: {form['goals_against']} (场均{form['avg_goals_against']})"""

    @tool
    def get_team_recent_form(self, team_name: str, matches: int = 5) -> str:
        """获取球队近期比赛状态，包括近N场胜平负、进球失球、场均积分、主客场表现。
        输入: 球队中文名, 场次(默认5)"""
        form = self.team_stats.recent_form(team_name, matches)
        if form["matches"] == 0:
            return f"未找到 {team_name} 的近期比赛数据"
        return f"""{team_name} 近{form['matches']}场状态:
战绩: {form['wins']}胜{form['draws']}平{form['losses']}负
进球: {form['goals_for']} (场均{form['avg_goals_for']})
失球: {form['goals_against']} (场均{form['avg_goals_against']})
积分: {form['points']} (场均{form['points_per_game']})
近期走势: {form['form_string']} (W=胜 D=平 L=负，从左到右由近到远)"""

    @tool
    def get_player_info(self, player_name: str) -> str:
        """获取球员基本信息和赛季统计，包括位置、年龄、国籍、身价、进球助攻等。
        输入: 球员中文名（如 '哈兰德'、'萨拉赫'）"""
        try:
            with get_db() as db:
                player = get_player_by_name(db, player_name)
                if player:
                    return f"""球员: {player.name} ({player.name_en or 'N/A'})
球队: {player.team.name if player.team else '未知'}
位置: {player.position or '未知'}
国籍: {player.nationality or '未知'}
年龄: {player.age or '未知'}岁
身高: {player.height or '未知'}cm
身价: {player.market_value or '未知'}万欧元
赛季统计: {player.stats_json or '暂无详细统计'}"""
        except Exception:
            pass
        return f"未找到球员 {player_name} 的详细信息，请确认球员名称是否正确。"

    @tool
    def predict_match(self, home_team: str, away_team: str) -> str:
        """预测比赛结果，返回胜平负概率、置信度和关键影响因素。
        输入: 主队名, 客队名（如 '曼城', '阿森纳'）"""
        try:
            features = self.feature_engineer.build_features(home_team, away_team)

            if self.predictor:
                result = self.predictor.predict_with_explanation(features)
                pred = result["prediction"]
                probs = pred["probabilities"]
                explanation = result["explanation"]

                pos_factors = "\n".join([
                    f"  +{f['feature']}: SHAP={f['shap_value']} (值={f['feature_value']})"
                    for f in explanation["top_positive_factors"][:5]
                ])
                neg_factors = "\n".join([
                    f"  {f['feature']}: SHAP={f['shap_value']} (值={f['feature_value']})"
                    for f in explanation["top_negative_factors"][:5]
                ])

                return f"""比赛预测: {home_team}(主) vs {away_team}(客)
预测结果: {pred['prediction']} (置信度{pred['confidence']:.1%})
概率分布:
  主胜: {probs['home_win']:.1%}
  平局: {probs['draw']:.1%}
  客胜: {probs['away_win']:.1%}

支持预测的关键因素:
{pos_factors or '  无'}

不利因素:
{neg_factors or '  无'}

注意: 足球比赛存在偶然性，预测仅供参考。"""
            else:
                # 没有训练模型时用Elo预测
                elo_pred = self.elo.predict_match(home_team, away_team)
                return f"""比赛预测(Elo基准): {home_team}(主) vs {away_team}(客)
Elo评级: 主队{elo_pred['home_elo']:.0f} vs 客队{elo_pred['away_elo']:.0f} (差{elo_pred['elo_diff']:.0f})
概率分布:
  主胜: {elo_pred['home_win']:.1%}
  平局: {elo_pred['draw']:.1%}
  客胜: {elo_pred['away_win']:.1%}
预测结果: {'主胜' if elo_pred['home_win'] > max(elo_pred['draw'], elo_pred['away_win']) else '平局' if elo_pred['draw'] > elo_pred['away_win'] else '客胜'}

注意: 此为Elo基准模型预测，训练XGBoost模型后可获得更精准预测。"""

        except Exception as e:
            return f"预测失败: {str(e)}。请确认球队名称是否正确。"

    @tool
    def get_head_to_head(self, team_a: str, team_b: str, matches: int = 10) -> str:
        """获取两支球队的历史交锋记录，包括胜平负统计和近期交锋趋势。
        输入: 球队A名, 球队B名, 场次(默认10)"""
        h2h = self.team_stats.head_to_head(team_a, team_b, matches)
        return f"""{team_a} vs {team_b} 历史交锋(近{h2h['total']}场):
{team_a}胜: {h2h['team_a_wins']}场 ({h2h['team_a_win_rate']:.1%})
{team_b}胜: {h2h['team_b_wins']}场
平局: {h2h['draws']}场
{team_a}近期交锋走势: {h2h['recent_form_a']} (W=胜 D=平 L=负)"""

    @tool
    def get_league_standings(self, league_name: str = "英超") -> str:
        """获取联赛当前积分榜。
        输入: 联赛名（如 '英超'、'西甲'、'德甲'、'意甲'、'法甲'）"""
        try:
            league_df = self.matches_df[self.matches_df["league"] == league_name]
            if len(league_df) == 0:
                return f"未找到 {league_name} 的数据"
            table = TeamStats.compute_league_table(league_df)
            lines = [f"{league_name} 积分榜:"]
            for i, row in table.head(10).iterrows():
                lines.append(f"  {i}. {row['team']}: {row['points']}分 "
                           f"({row['wins']}胜{row['draws']}平{row['losses']}负 "
                           f"净胜球{row['goal_diff']})")
            return "\n".join(lines)
        except Exception as e:
            return f"获取积分榜失败: {e}"

    def get_tools(self):
        """获取所有工具列表"""
        return [
            self.get_team_info,
            self.get_team_recent_form,
            self.get_player_info,
            self.predict_match,
            self.get_head_to_head,
            self.get_league_standings,
        ]
