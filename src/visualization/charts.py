"""可视化模块 - 球员雷达图、球队对比图、趋势图
使用Plotly生成交互式HTML图表，可嵌入前端
"""
import plotly.graph_objects as go
import pandas as pd
from typing import Dict, List, Optional


class PlayerRadarChart:
    """球员能力雷达图"""

    # 八大能力维度
    DIMENSIONS = ["速度", "射门", "传球", "盘带", "防守", "体力", "力量", "视野"]

    def __init__(self):
        pass

    def generate(self, player_name: str, stats: Dict[str, float],
                 compare_player: str = None, compare_stats: Dict = None,
                 title: str = None) -> str:
        """生成球员能力雷达图HTML

        Args:
            player_name: 球员名
            stats: 能力值dict {维度: 0-100分值}
            compare_player: 对比球员名（可选）
            compare_stats: 对比球员能力值
            title: 图表标题

        Returns:
            HTML字符串（可直接嵌入前端）
        """
        fig = go.Figure()

        # 主球员
        values = [stats.get(d, 50) for d in self.DIMENSIONS]
        fig.add_trace(go.Scatterpolar(
            r=values + [values[0]],
            theta=self.DIMENSIONS + [self.DIMENSIONS[0]],
            fill="toself",
            name=player_name,
            line_color="#2F6F4F",
            fillcolor="rgba(47,111,79,0.25)",
            line_width=2,
        ))

        # 对比球员
        if compare_player and compare_stats:
            comp_values = [compare_stats.get(d, 50) for d in self.DIMENSIONS]
            fig.add_trace(go.Scatterpolar(
                r=comp_values + [comp_values[0]],
                theta=self.DIMENSIONS + [self.DIMENSIONS[0]],
                fill="toself",
                name=compare_player,
                line_color="#1F6FB2",
                fillcolor="rgba(31,111,178,0.15)",
                line_width=2,
            ))

        fig.update_layout(
            polar=dict(
                radialaxis=dict(visible=True, range=[0, 100], tickfont=dict(size=10)),
                angularaxis=dict(tickfont=dict(size=12)),
            ),
            showlegend=True,
            title=dict(text=title or f"{player_name} 能力雷达图", x=0.5),
            height=500,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    @staticmethod
    def compute_player_stats_from_data(player_data: Dict) -> Dict[str, float]:
        """从球员原始统计数据计算八大能力维度分值（0-100）
        这是一个简化的映射，实际项目中可根据详细统计调整
        """
        # 示例映射逻辑，实际需根据数据字段调整
        goals = player_data.get("goals", 0)
        assists = player_data.get("assists", 0)
        passes = player_data.get("passes", 0)
        tackles = player_data.get("tackles", 0)
        dribbles = player_data.get("dribbles", 0)
        shots = player_data.get("shots", 0)

        return {
            "速度": min(100, 60 + player_data.get("speed_bonus", 0)),
            "射门": min(100, 40 + goals * 3 + shots * 0.5),
            "传球": min(100, 40 + assists * 4 + passes * 0.02),
            "盘带": min(100, 45 + dribbles * 0.8),
            "防守": min(100, 30 + tackles * 1.5),
            "体力": min(100, 50 + player_data.get("minutes", 0) / 100),
            "力量": min(100, 50 + player_data.get("aerial_wins", 0)),
            "视野": min(100, 45 + assists * 3 + passes * 0.01),
        }


class TeamComparisonChart:
    """球队多维度对比图"""

    def compare_basic_stats(self, team_a: str, team_b: str,
                             stats_a: Dict, stats_b: Dict) -> str:
        """基础数据对比柱状图"""
        categories = ["场均进球", "场均失球", "场均射门", "场均射正",
                      "场均控球率", "场均角球", "场均犯规", "场均黄牌"]
        values_a = [stats_a.get(c, 0) for c in categories]
        values_b = [stats_b.get(c, 0) for c in categories]

        fig = go.Figure(data=[
            go.Bar(name=team_a, x=categories, y=values_a,
                   marker_color="#2F6F4F", text=values_a, textposition="outside"),
            go.Bar(name=team_b, x=categories, y=values_b,
                   marker_color="#C44536", text=values_b, textposition="outside"),
        ])
        fig.update_layout(
            barmode="group",
            title=dict(text=f"{team_a} vs {team_b} 数据对比", x=0.5),
            height=450,
            xaxis_tickangle=-30,
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def compare_radar(self, team_a: str, team_b: str,
                      stats_a: Dict, stats_b: Dict) -> str:
        """球队能力雷达图对比"""
        dimensions = ["进攻", "防守", "中场控制", "主场优势", "近期状态", "阵容深度"]
        values_a = [stats_a.get(d, 50) for d in dimensions]
        values_b = [stats_b.get(d, 50) for d in dimensions]

        fig = go.Figure()
        fig.add_trace(go.Scatterpolar(
            r=values_a + [values_a[0]], theta=dimensions + [dimensions[0]],
            fill="toself", name=team_a, line_color="#2F6F4F",
            fillcolor="rgba(47,111,79,0.2)",
        ))
        fig.add_trace(go.Scatterpolar(
            r=values_b + [values_b[0]], theta=dimensions + [dimensions[0]],
            fill="toself", name=team_b, line_color="#C44536",
            fillcolor="rgba(196,69,54,0.15)",
        ))
        fig.update_layout(
            polar=dict(radialaxis=dict(range=[0, 100])),
            title=dict(text=f"{team_a} vs {team_b} 能力对比", x=0.5),
            height=480,
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")


class TrendChart:
    """趋势图"""

    def team_form_trend(self, team_name: str, matches_df: pd.DataFrame,
                         n: int = 10) -> str:
        """球队近期状态趋势图（积分+进球）"""
        from src.analysis.team_stats import TeamStats
        stats = TeamStats(matches_df)

        # 获取近n场比赛的逐场数据
        home = matches_df[matches_df["HomeTeam"] == team_name].copy()
        home["team_goals"] = home["FTHG"]
        home["opp_goals"] = home["FTAG"]
        home["points"] = home["FTR"].map({"H": 3, "D": 1, "A": 0})

        away = matches_df[matches_df["AwayTeam"] == team_name].copy()
        away["team_goals"] = away["FTAG"]
        away["opp_goals"] = away["FTHG"]
        away["points"] = away["FTR"].map({"H": 0, "D": 1, "A": 3})

        all_matches = pd.concat([home, away]).sort_values("Date").tail(n)

        if len(all_matches) == 0:
            return f"<p>暂无 {team_name} 的比赛数据</p>"

        dates = all_matches["Date"].dt.strftime("%m-%d").tolist()
        goals = all_matches["team_goals"].tolist()
        conceded = all_matches["opp_goals"].tolist()
        points = all_matches["points"].tolist()
        cum_points = [sum(points[:i+1]) for i in range(len(points))]

        fig = go.Figure()
        fig.add_trace(go.Bar(name="进球", x=dates, y=goals, marker_color="#2F6F4F"))
        fig.add_trace(go.Bar(name="失球", x=dates, y=conceded, marker_color="#C44536"))
        fig.add_trace(go.Scatter(name="累计积分", x=dates, y=cum_points,
                                 mode="lines+markers", line=dict(color="#D4A017", width=2),
                                 yaxis="y2"))

        fig.update_layout(
            title=dict(text=f"{team_name} 近{len(all_matches)}场状态趋势", x=0.5),
            barmode="group",
            height=420,
            yaxis=dict(title="进球/失球"),
            yaxis2=dict(title="累计积分", overlaying="y", side="right"),
            legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")

    def prediction_probability_chart(self, home_team: str, away_team: str,
                                      probs: Dict) -> str:
        """预测概率分布图"""
        fig = go.Figure(go.Bar(
            x=[f"{home_team}(主胜)", "平局", f"{away_team}(客胜)"],
            y=[probs["home_win"], probs["draw"], probs["away_win"]],
            marker_color=["#2F6F4F", "#888888", "#C44536"],
            text=[f"{probs['home_win']:.1%}", f"{probs['draw']:.1%}", f"{probs['away_win']:.1%}"],
            textposition="outside",
        ))
        fig.update_layout(
            title=dict(text=f"{home_team} vs {away_team} 预测概率", x=0.5),
            yaxis=dict(title="概率", range=[0, 1], tickformat=".0%"),
            height=380,
            showlegend=False,
        )
        return fig.to_html(full_html=False, include_plotlyjs="cdn")
