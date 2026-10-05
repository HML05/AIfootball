"""数据初始化脚本
功能:
1. 创建数据库表
2. 从 football-data.co.uk 下载五大联赛历史数据
3. 初始化联赛和球队基础数据
4. 计算初始Elo评级

用法: python scripts/init_data.py
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
from pathlib import Path
from config.settings import settings
from src.database.crud import init_db, get_db, create_league, create_team, get_league_by_name
from src.database.models import League, Team
from src.data_sources.football_data_co_uk import FootballDataUK
from src.analysis.elo_rating import EloRating

# 五大联赛基础信息
TOP5_LEAGUES = [
    {"name": "英超", "name_en": "Premier League", "country": "英格兰", "season": "2026-27"},
    {"name": "西甲", "name_en": "La Liga", "country": "西班牙", "season": "2026-27"},
    {"name": "德甲", "name_en": "Bundesliga", "country": "德国", "season": "2026-27"},
    {"name": "意甲", "name_en": "Serie A", "country": "意大利", "season": "2026-27"},
    {"name": "法甲", "name_en": "Ligue 1", "country": "法国", "season": "2026-27"},
]

# 用于训练的历史赛季（近5个赛季）
TRAINING_SEASONS = ["2122", "2223", "2324", "2425", "2526", "2627"]


def step1_init_database():
    """步骤1: 初始化数据库表"""
    print("=" * 60)
    print("步骤1: 初始化数据库")
    print("=" * 60)
    init_db()
    print(f"数据库已初始化: {settings.DATABASE_URL}")
    print()


def step2_init_leagues():
    """步骤2: 初始化五大联赛"""
    print("=" * 60)
    print("步骤2: 初始化五大联赛")
    print("=" * 60)
    with get_db() as db:
        for league_info in TOP5_LEAGUES:
            existing = get_league_by_name(db, league_info["name"])
            if existing:
                print(f"  已存在: {league_info['name']}")
            else:
                create_league(db, **league_info)
                print(f"  已创建: {league_info['name']}")
    print()


def step3_download_match_data():
    """步骤3: 下载五大联赛比赛数据"""
    print("=" * 60)
    print("步骤3: 下载五大联赛比赛数据")
    print("=" * 60)

    data_source = FootballDataUK(cache_dir=settings.RAW_DATA_DIR)
    all_matches = []

    for league_info in TOP5_LEAGUES:
        league_name = league_info["name"]
        print(f"\n  下载 {league_name} 数据...")

        for season in TRAINING_SEASONS:
            try:
                df = data_source.fetch_season(league_name, season, use_cache=True)
                if len(df) > 0:
                    all_matches.append(df)
                    print(f"    {season}赛季: {len(df)} 场比赛")
            except Exception as e:
                print(f"    {season}赛季: 跳过 ({e})")

    if all_matches:
        combined = pd.concat(all_matches, ignore_index=True)
        output_path = settings.DATA_DIR / "processed" / "all_matches.csv"
        combined.to_csv(output_path, index=False, encoding="utf-8-sig")
        print(f"\n  合计: {len(combined)} 场比赛")
        print(f"  已保存到: {output_path}")
    else:
        print("  警告: 未下载到任何比赛数据")

    print()
    return all_matches


def step4_init_teams_from_data():
    """步骤4: 从比赛数据中提取球队并入库"""
    print("=" * 60)
    print("步骤4: 从比赛数据提取球队信息")
    print("=" * 60)

    processed_path = settings.DATA_DIR / "processed" / "all_matches.csv"
    if not processed_path.exists():
        print("  跳过: 未找到处理后的数据")
        return

    df = pd.read_csv(processed_path, encoding="utf-8-sig")

    with get_db() as db:
        for league_info in TOP5_LEAGUES:
            league_name = league_info["name"]
            league = get_league_by_name(db, league_name)
            if not league:
                continue

            league_df = df[df["league"] == league_name]
            teams = set(league_df["HomeTeam"].dropna().tolist() +
                       league_df["AwayTeam"].dropna().tolist())

            print(f"  {league_name}: {len(teams)} 支球队")

            for team_name in sorted(teams):
                existing = db.query(Team).filter(
                    (Team.name == team_name) & (Team.league_id == league.league_id)
                ).first()
                if not existing:
                    create_team(db, league_id=league.league_id,
                              name=team_name, name_en=team_name,
                              short_name=team_name[:4])
    print()


def step5_compute_elo():
    """步骤5: 计算初始Elo评级"""
    print("=" * 60)
    print("步骤5: 计算Elo评级")
    print("=" * 60)

    processed_path = settings.DATA_DIR / "processed" / "all_matches.csv"
    if not processed_path.exists():
        print("  跳过: 未找到处理后的数据")
        return

    df = pd.read_csv(processed_path, encoding="utf-8-sig")
    df["Date"] = pd.to_datetime(df["Date"], errors="coerce")

    elo = EloRating()
    elo.batch_update(df)

    # 保存Elo评级
    ranking = elo.get_ranking()
    elo_path = settings.DATA_DIR / "processed" / "elo_ratings.csv"
    ranking.to_csv(elo_path, index=False, encoding="utf-8-sig")

    print(f"  已计算 {len(ranking)} 支球队的Elo评级")
    print(f"  已保存到: {elo_path}")
    print("\n  Top 10 球队:")
    for i, row in ranking.head(10).iterrows():
        print(f"    {i}. {row['team']}: {row['elo_rating']:.0f}")

    # 更新数据库中的Elo评级
    with get_db() as db:
        for _, row in ranking.iterrows():
            team = db.query(Team).filter(Team.name == row["team"]).first()
            if team:
                team.elo_rating = row["elo_rating"]
        db.commit()
    print("\n  数据库Elo评级已更新")
    print()


def main():
    """主函数"""
    print("\n" + "=" * 60)
    print("  足球数据分析系统 - 数据初始化")
    print("=" * 60 + "\n")

    try:
        step1_init_database()
        step2_init_leagues()
        step3_download_match_data()
        step4_init_teams_from_data()
        step5_compute_elo()

        print("=" * 60)
        print("  数据初始化完成!")
        print("=" * 60)
        print("\n下一步:")
        print("  1. 训练预测模型: python scripts/train_model.py")
        print("  2. 启动后端服务: uvicorn src.main:app --reload")
        print("  3. 启动前端: streamlit run frontend/app.py")
        print()

    except Exception as e:
        print(f"\n初始化失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
