# -*- coding: utf-8 -*-
"""构建球员雷达图数据表 player_radar

数据来源:
  - tm_player_seasons  : 最近赛季的 出场/进球/助攻/分钟/黄牌/红牌
  - tm_player_market_value : 最新身价
  - players            : 年龄/身高/体重/位置

7 个维度(0-100, 按同位置组的百分位):
  进球能力 / 助攻能力 / 进攻参与 / 出场稳定性 / 纪律性 / 身价价值 / 比赛经验

用法: python scripts/build_player_radar.py
产物: 表 player_radar（UI 可直接 SELECT）
"""
import sqlite3
from pathlib import Path

import pandas as pd

DB = Path(__file__).resolve().parent.parent / "data" / "database" / "football.db"


def pos_group(p):
    s = str(p or "").lower()
    if "goal" in s or "keeper" in s:
        return "GK"
    if "defend" in s or "back" in s:
        return "DF"
    if "midfield" in s:
        return "MF"
    if "attack" in s or "forward" in s or "winger" in s or "striker" in s:
        return "FW"
    return "OT"


def pct(series):
    """百分位 0-100(同组内)"""
    return series.rank(pct=True).mul(100).round(0)


def main():
    c = sqlite3.connect(str(DB))
    print("读取球员与 TM 赛季数据 ...")
    players = pd.read_sql_query("""
        SELECT player_id, team_id, name, name_en, position, age, height, weight,
               number, photo_url, market_value, tm_player_id, nationality, foot
        FROM players""", c)
    print(f"  球员 {len(players):,}")

    # 每个 TM 球员的近 3 个赛季汇总(样本更稳, 避免只有 3 场就评能力)
    seas = pd.read_sql_query("""
        SELECT s.player_id, s.season_start, s.appearances, s.goals, s.assists,
               s.minutes, s.yellow_cards, s.red_cards
        FROM tm_player_seasons s
        WHERE s.season_start >= (SELECT MAX(season_start) - 2 FROM tm_player_seasons)""", c)
    agg = seas.groupby("player_id").agg(
        apps=("appearances", "sum"), goals=("goals", "sum"),
        assists=("assists", "sum"), minutes=("minutes", "sum"),
        yellow=("yellow_cards", "sum"), red=("red_cards", "sum"),
        season_start=("season_start", "max")).reset_index()
    print(f"  有 TM 赛季数据的球员 {len(agg):,} (近 3 赛季汇总)")

    df = players.merge(agg, left_on="tm_player_id", right_on="player_id",
                       how="left", suffixes=("", "_tm"))
    # 身价兜底: players.market_value 缺失时用 TM 最新市值
    mv = pd.read_sql_query("""
        SELECT player_id, value FROM tm_player_market_value v
        WHERE value_date = (SELECT MAX(value_date) FROM tm_player_market_value x
                            WHERE x.player_id = v.player_id)""", c)
    df = df.merge(mv, left_on="tm_player_id", right_on="player_id",
                  how="left", suffixes=("", "_mv"))
    df["mv"] = df["market_value"].fillna(df["value"])

    df["apps"] = df["apps"].fillna(0)
    df["minutes"] = df["minutes"].fillna(0)
    df["goals"] = df["goals"].fillna(0)
    df["assists"] = df["assists"].fillna(0)
    df["cards"] = df["yellow"].fillna(0) + 2 * df["red"].fillna(0)
    n90 = (df["minutes"] / 90.0).clip(lower=0.5)
    df["goals_p90"] = (df["goals"] / n90).round(3)
    df["assists_p90"] = (df["assists"] / n90).round(3)
    df["involve_p90"] = (df["goals_p90"] + df["assists_p90"]).round(3)
    df["minutes_share"] = (df["minutes"] / (df["apps"].clip(lower=1) * 90)).clip(0, 1.2).round(3)
    df["cards_p90"] = (df["cards"] / n90).round(3)
    df["grp"] = df["position"].map(pos_group)

    print("计算百分位 ...")
    df["s_goals"] = df.groupby("grp")["goals_p90"].transform(pct)
    df["s_assists"] = df.groupby("grp")["assists_p90"].transform(pct)
    df["s_involve"] = df.groupby("grp")["involve_p90"].transform(pct)
    df["s_minutes"] = df.groupby("grp")["minutes_share"].transform(pct)
    df["s_discipline"] = df.groupby("grp")["cards_p90"].transform(lambda s: 100 - pct(s))
    df["s_value"] = df.groupby("grp")["mv"].transform(lambda s: pct(s.fillna(0)))
    df["s_experience"] = df.groupby("grp")["age"].transform(lambda s: pct(s.fillna(0)))

    # 门将: 进球/助攻维度无意义 -> 置 0, 用出场/纪律/身价/经验/体格 体现
    gk = df["grp"] == "GK"
    df.loc[gk, ["s_goals", "s_assists", "s_involve"]] = 0

    out = df[["player_id", "team_id", "name", "name_en", "position", "grp",
              "age", "height", "weight", "nationality", "foot", "number",
              "photo_url", "mv", "apps", "minutes", "goals", "assists", "cards",
              "goals_p90", "assists_p90", "involve_p90", "minutes_share", "cards_p90",
              "s_goals", "s_assists", "s_involve", "s_minutes", "s_discipline",
              "s_value", "s_experience"]].rename(
        columns={"mv": "market_value", "grp": "pos_group"})
    out.to_sql("player_radar", c, if_exists="replace", index=False)
    c.execute("CREATE INDEX IF NOT EXISTS idx_radar_pid ON player_radar(player_id)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_radar_team ON player_radar(team_id)")
    c.commit()

    print(f"\n表 player_radar 写入 {len(out):,} 行")
    print("有比赛数据的球员:", int((out["minutes"] > 0).sum()))
    print("\n示例(巴萨, 按身价):")
    for r in out[out["team_id"] == c.execute(
            "SELECT team_id FROM teams WHERE name='Barcelona'").fetchone()[0]] \
            .sort_values("market_value", ascending=False).head(6).itertuples():
        print(f"   {str(r.name):<16} {r.pos_group} | 进球{r.s_goals:.0f} 助攻{r.s_assists:.0f} "
              f"参与{r.s_involve:.0f} 出场{r.s_minutes:.0f} 纪律{r.s_discipline:.0f} "
              f"身价{r.s_value:.0f} 经验{r.s_experience:.0f} | {r.goals}球{r.assists}助/{r.apps}场")
    c.close()


if __name__ == "__main__":
    main()
