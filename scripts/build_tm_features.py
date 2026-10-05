# -*- coding: utf-8 -*-
"""从 Transfermarkt 数据构建"球队-赛季"特征: 阵容总身价 + 伤病天数

输出: data/processed/tm_team_season.csv
      列: team_name(本库规范名), season(本库赛季码), squad_value, squad_size,
          injury_days, injured_players

用法: python scripts/build_tm_features.py
"""
import re
import sqlite3
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
DB = BASE / "data" / "database" / "football.db"
OUT = BASE / "data" / "processed" / "tm_team_season.csv"


def season_code(start_year: int) -> str:
    """2021 -> '2122'"""
    return f"{str(start_year)[2:]}{str(start_year + 1)[2:]}"


def parse_days(txt):
    m = re.search(r"(\d+)", str(txt or ""))
    return int(m.group(1)) if m else 0


def main():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row

    seasons = pd.read_sql_query(
        "SELECT team_id, season_start, player_id FROM tm_player_seasons "
        "WHERE season_start IS NOT NULL", c)
    # 同一球员同一赛季会有多条(不同赛事)记录 -> 去重, 否则身价被重复累加
    before = len(seasons)
    seasons = seasons.drop_duplicates(subset=["team_id", "season_start", "player_id"])
    print(f"赛季记录 {before:,} -> 去重后 {len(seasons):,}")
    values = pd.read_sql_query(
        "SELECT player_id, value_date, value FROM tm_player_market_value "
        "WHERE value IS NOT NULL", c)
    print(f"市值记录 {len(values):,}")

    seasons["cutoff"] = pd.to_datetime(
        (seasons["season_start"] + 1).astype(str) + "-06-30")
    values["d"] = pd.to_datetime(values["value_date"], errors="coerce")
    values = values.dropna(subset=["d"]).sort_values("d")
    seasons = seasons.sort_values("cutoff")

    merged = pd.merge_asof(seasons, values[["player_id", "d", "value"]],
                           left_on="cutoff", right_on="d", by="player_id",
                           direction="backward")
    # 身价缺失时按 5 万欧 (TM 最低值) 计, 避免整队被低估
    merged["value"] = merged["value"].fillna(50_000)
    agg = merged.groupby(["team_id", "season_start"]).agg(
        squad_value=("value", "sum"), squad_size=("player_id", "nunique")).reset_index()
    print(f"球队-赛季身价聚合: {len(agg):,} 行")

    # 伤病: 解析 'DD.MM.YYYY' -> 赛季归属 -> 关联当年所在俱乐部
    inj = pd.read_sql_query(
        "SELECT player_id, from_date, days_missed FROM tm_player_injuries", c)
    inj["dt"] = pd.to_datetime(inj["from_date"], errors="coerce")
    inj = inj.dropna(subset=["dt"])
    inj["season_start"] = inj["dt"].apply(lambda d: d.year - 1 if d.month < 7 else d.year)
    inj["days"] = inj["days_missed"].map(parse_days)
    inj = inj.merge(seasons, on=["player_id", "season_start"], how="inner")
    iagg = inj.groupby(["team_id", "season_start"]).agg(
        injury_days=("days", "sum"), injured_players=("player_id", "nunique")).reset_index()
    print(f"伤病记录 {len(inj):,} -> 球队-赛季聚合 {len(iagg):,} 行")

    out = agg.merge(iagg, on=["team_id", "season_start"], how="left")
    out["injury_days"] = out["injury_days"].fillna(0)
    out["injured_players"] = out["injured_players"].fillna(0)

    # club_id -> 本库队名
    cmap = {str(r["club_id"]): r["name"] for r in c.execute(
        "SELECT m.club_id, t.name FROM tm_club_map m JOIN teams t ON t.team_id=m.team_id")}
    out["club_id"] = out["team_id"].astype(str)
    out["team_name"] = out["club_id"].map(cmap)
    out = out.dropna(subset=["team_name"])
    out["season"] = out["season_start"].map(season_code)

    out = out[["team_name", "season", "season_start", "squad_value", "squad_size",
               "injury_days", "injured_players"]]
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n已写入 {OUT} | {len(out):,} 行, 覆盖 {out['team_name'].nunique()} 支球队")

    print("\n样例(阿森纳近 5 个赛季):")
    for r in out[out["team_name"] == "Arsenal"].sort_values("season_start").tail(5).itertuples():
        print(f"   {r.season}: 阵容 {r.squad_size} 人 | 总身价 "
              f"{r.squad_value/1e6:.0f}M€ | 伤病 {int(r.injury_days)} 天")
    c.close()


if __name__ == "__main__":
    main()
