"""football-data.co.uk 免费CSV数据源
已实测可用: https://www.football-data.co.uk/mmz4281/<赛季码>/<联赛码>.csv
"""
import pandas as pd
import requests
from pathlib import Path
from typing import List, Optional
from config.settings import settings


class FootballDataUK:
    """football-data.co.uk 数据源 - 免费、免注册、历史数据丰富"""

    BASE_URL = "https://www.football-data.co.uk/mmz4281"

    # 五大联赛代码映射
    LEAGUE_CODES = {
        "英超": "E0", "英冠": "E1",
        "西甲": "SP1", "西乙": "SP2",
        "德甲": "D1", "德乙": "D2",
        "意甲": "I1", "意乙": "I2",
        "法甲": "F1", "法乙": "F2",
    }

    # 可用赛季（近10个赛季）
    AVAILABLE_SEASONS = ["1617", "1718", "1819", "1920", "2021",
                         "2122", "2223", "2324", "2425", "2526", "2627"]

    def __init__(self, cache_dir: Optional[Path] = None):
        self.cache_dir = cache_dir or settings.RAW_DATA_DIR
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def fetch_season(self, league: str, season: str = "2627",
                     use_cache: bool = True) -> pd.DataFrame:
        """获取指定联赛指定赛季的比赛数据

        Args:
            league: 联赛中文名（如 "英超"）
            season: 赛季码，如 "2627" 表示 2026-27 赛季
            use_cache: 是否使用本地缓存

        Returns:
            清洗后的比赛数据DataFrame
        """
        code = self.LEAGUE_CODES.get(league)
        if not code:
            raise ValueError(f"不支持的联赛: {league}，支持: {list(self.LEAGUE_CODES.keys())}")

        url = f"{self.BASE_URL}/{season}/{code}.csv"
        cache_file = self.cache_dir / f"{code}_{season}.csv"

        # 优先读缓存
        if use_cache and cache_file.exists():
            df = pd.read_csv(cache_file, encoding="utf-8-sig")
            return self._clean_data(df, league, season)

        # 下载
        try:
            resp = requests.get(url, timeout=30)
            resp.raise_for_status()
            cache_file.write_bytes(resp.content)
            df = pd.read_csv(cache_file, encoding="utf-8-sig")
            return self._clean_data(df, league, season)
        except requests.RequestException as e:
            raise ConnectionError(f"下载 {league} {season} 数据失败: {e}")

    def fetch_multiple_seasons(self, league: str, seasons: List[str]) -> pd.DataFrame:
        """获取多个赛季数据（用于模型训练）"""
        frames = []
        for s in seasons:
            try:
                df = self.fetch_season(league, s)
                frames.append(df)
            except Exception as e:
                print(f"警告: 跳过 {league} {s} - {e}")
        if not frames:
            return pd.DataFrame()
        return pd.concat(frames, ignore_index=True)

    def fetch_all_top5_leagues(self, season: str = "2627") -> dict:
        """获取五大联赛当前赛季数据"""
        result = {}
        for league in ["英超", "西甲", "德甲", "意甲", "法甲"]:
            try:
                result[league] = self.fetch_season(league, season)
            except Exception as e:
                print(f"{league} 获取失败: {e}")
        return result

    def _clean_data(self, df: pd.DataFrame, league: str, season: str) -> pd.DataFrame:
        """数据清洗：统一字段、处理缺失值"""
        # 核心字段
        core_cols = ["Div", "Date", "Time", "HomeTeam", "AwayTeam",
                     "FTHG", "FTAG", "FTR", "HTHG", "HTAG", "HTR",
                     "HS", "AS", "HST", "AST", "HF", "AF", "HC", "AC",
                     "HY", "AY", "HR", "AR"]
        # xG字段（新赛季可能有）
        xg_cols = [c for c in df.columns if "xG" in c or "xg" in c.lower()]
        cols = [c for c in core_cols + xg_cols if c in df.columns]
        df = df[cols].copy()

        # 统一日期格式（football-data.co.uk 用 dd/mm/yyyy）
        if "Date" in df.columns:
            df["Date"] = pd.to_datetime(df["Date"], format="%d/%m/%Y", errors="coerce")

        df["league"] = league
        df["season"] = season
        df["league_code"] = self.LEAGUE_CODES.get(league, "")

        # 去除空行
        df = df.dropna(subset=["HomeTeam", "AwayTeam"])
        return df.reset_index(drop=True)

    @staticmethod
    def compute_league_table(matches_df: pd.DataFrame) -> pd.DataFrame:
        """从比赛数据计算积分榜"""
        teams = {}
        for _, row in matches_df.iterrows():
            if pd.isna(row.get("FTR")):
                continue
            home, away = row["HomeTeam"], row["AwayTeam"]
            hg, ag = int(row["FTHG"]), int(row["FTAG"])

            for team in [home, away]:
                if team not in teams:
                    teams[team] = {"played": 0, "wins": 0, "draws": 0,
                                   "losses": 0, "goals_for": 0, "goals_against": 0,
                                   "points": 0}

            teams[home]["played"] += 1
            teams[away]["played"] += 1
            teams[home]["goals_for"] += hg
            teams[home]["goals_against"] += ag
            teams[away]["goals_for"] += ag
            teams[away]["goals_against"] += hg

            if hg > ag:
                teams[home]["wins"] += 1
                teams[home]["points"] += 3
                teams[away]["losses"] += 1
            elif hg < ag:
                teams[away]["wins"] += 1
                teams[away]["points"] += 3
                teams[home]["losses"] += 1
            else:
                teams[home]["draws"] += 1
                teams[away]["draws"] += 1
                teams[home]["points"] += 1
                teams[away]["points"] += 1

        table = pd.DataFrame.from_dict(teams, orient="index")
        table["goal_diff"] = table["goals_for"] - table["goals_against"]
        table = table.sort_values(["points", "goal_diff", "goals_for"],
                                   ascending=[False, False, False]).reset_index()
        table = table.rename(columns={"index": "team"})
        table.index = table.index + 1
        return table
