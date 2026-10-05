"""API-Football (RapidAPI) 实时数据源
免费层: 100 requests/day
注册: https://rapidapi.com/api-sports/api/api-football
"""
import requests
from typing import Dict, List, Optional
from config.settings import settings


class ApiFootball:
    """API-Football 数据源 - 实时比分、球队/球员详情、转会"""

    BASE_URL = "https://api-football-v1.p.rapidapi.com/v3"

    # 五大联赛ID (API-Football内部ID)
    LEAGUE_IDS = {
        "英超": 39, "西甲": 140, "德甲": 78, "意甲": 135, "法甲": 61,
    }

    def __init__(self, api_key: Optional[str] = None,
                 host: Optional[str] = None):
        self.api_key = api_key or settings.API_FOOTBALL_KEY
        self.host = host or settings.API_FOOTBALL_HOST
        if not self.api_key or self.api_key == "your_api_football_key_here":
            raise ValueError("请在 .env 中配置 API_FOOTBALL_KEY")
        self.headers = {
            "X-RapidAPI-Key": self.api_key,
            "X-RapidAPI-Host": self.host,
        }

    def _request(self, endpoint: str, params: dict = None) -> List[Dict]:
        """统一请求方法"""
        resp = requests.get(f"{self.BASE_URL}/{endpoint}",
                           headers=self.headers, params=params or {}, timeout=30)
        resp.raise_for_status()
        data = resp.json()
        if data.get("errors"):
            raise RuntimeError(f"API错误: {data['errors']}")
        return data.get("response", [])

    # ============ 实时比分 ============

    def get_live_scores(self) -> List[Dict]:
        """获取所有正在进行的比赛"""
        return self._request("fixtures", {"live": "all"})

    def get_live_by_league(self, league_name: str) -> List[Dict]:
        """获取指定联赛的实时比赛"""
        league_id = self.LEAGUE_IDS.get(league_name)
        if not league_id:
            raise ValueError(f"不支持的联赛: {league_name}")
        return self._request("fixtures", {"live": league_id})

    # ============ 赛程 ============

    def get_fixtures_by_date(self, date: str, league: str = None) -> List[Dict]:
        """获取指定日期的赛程
        date格式: YYYY-MM-DD
        """
        params = {"date": date}
        if league:
            params["league"] = self.LEAGUE_IDS[league]
            params["season"] = 2026
        return self._request("fixtures", params)

    def get_fixtures_by_team(self, team_id: int, season: int = 2026,
                              last: int = None, next: int = None) -> List[Dict]:
        """获取球队赛程"""
        params = {"team": team_id, "season": season}
        if last:
            params["last"] = last
        if next:
            params["next"] = next
        return self._request("fixtures", params)

    # ============ 球队 ============

    def get_team_info(self, team_id: int) -> Dict:
        """获取球队详细信息"""
        resp = self._request("teams", {"id": team_id})
        return resp[0] if resp else {}

    def get_team_squad(self, team_id: int) -> List[Dict]:
        """获取球队阵容（球员列表）"""
        return self._request("players/squads", {"team": team_id})

    def get_team_stats(self, team_id: int, league: str, season: int = 2026) -> Dict:
        """获取球队赛季统计"""
        league_id = self.LEAGUE_IDS.get(league, league)
        resp = self._request("teams/statistics",
                            {"team": team_id, "league": league_id, "season": season})
        return resp[0] if resp else {}

    # ============ 球员 ============

    def get_player_info(self, player_id: int, season: int = 2026) -> Dict:
        """获取球员赛季统计"""
        resp = self._request("players", {"id": player_id, "season": season})
        return resp[0] if resp else {}

    def search_players(self, name: str) -> List[Dict]:
        """搜索球员"""
        return self._request("players", {"search": name})

    # ============ 转会 ============

    def get_transfers(self, team_id: int = None, player_id: int = None) -> List[Dict]:
        """获取转会信息"""
        params = {}
        if team_id:
            params["team"] = team_id
        if player_id:
            params["player"] = player_id
        return self._request("transfers", params)

    # ============ 积分榜 ============

    def get_standings(self, league: str, season: int = 2026) -> List[Dict]:
        """获取联赛积分榜"""
        league_id = self.LEAGUE_IDS.get(league, league)
        resp = self._request("standings", {"league": league_id, "season": season})
        return resp[0]["league"]["standings"][0] if resp and resp[0].get("league") else []


# =====================================================================
# 以下为完整客户端(ApiFootballClient) —— 支持直连 API-Sports / RapidAPI,
# 含限速、每日配额管理、响应缓存、断点续传所需的基础能力。
# 用于补齐: 裁判 / 阵容 / 事件 / 球员体重·国籍 / 主教练 / 伤停 / 历史积分榜
# =====================================================================
import gzip                                                     # noqa: E402
import hashlib                                                  # noqa: E402
import json                                                     # noqa: E402
import os                                                       # noqa: E402
import sys                                                      # noqa: E402
import time                                                     # noqa: E402
from datetime import datetime, timezone                         # noqa: E402
from pathlib import Path                                        # noqa: E402

import requests                                                 # noqa: E402

BASE_DIR = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = BASE_DIR / "data" / "external" / "af_cache"
QUOTA_FILE = BASE_DIR / "data" / "af_quota.json"

# 我们的联赛名 -> API-Football 联赛 id
AF_LEAGUES = {
    "英超": 39, "西甲": 140, "德甲": 78, "意甲": 135, "法甲": 61,
    "欧冠": 2, "英冠": 40, "荷甲": 88, "葡超": 94, "巴甲": 71,
}
# 赛季起始年 -> 我们的赛季码
AF_SEASON_CODE = {2016: "1617", 2017: "1718", 2018: "1819", 2019: "1920", 2020: "2021",
                  2021: "2122", 2022: "2223", 2023: "2324", 2024: "2425",
                  2025: "2526", 2026: "2627"}


class QuotaExceeded(RuntimeError):
    """当日预算用完(主动停止, 不是 API 报错)"""


class ApiFootballClient:
    """API-Football 完整客户端

    直连:   https://v3.football.api-sports.io     header x-apisports-key
    RapidAPI: https://api-football-v1.p.rapidapi.com/v3
    """

    def __init__(self, api_key: str = None, mode: str = None, base: str = None,
                 min_interval: float = None, daily_budget: int = None,
                 cache: bool = True, verbose: bool = True):
        key = api_key or getattr(settings, "API_SPORTS_KEY", "") or \
            os.getenv("API_SPORTS_KEY", "")
        rapid_key = getattr(settings, "API_FOOTBALL_KEY", "") or \
            os.getenv("API_FOOTBALL_KEY", "")
        self.mode = mode or ("direct" if key else "rapidapi")
        self.min_interval = (min_interval if min_interval is not None else
                             float(getattr(settings, "AF_MIN_INTERVAL", 6.0)))
        self.daily_budget = (daily_budget if daily_budget is not None else
                             int(getattr(settings, "AF_DAILY_BUDGET", 7000)))
        self.cache = cache
        self.verbose = verbose
        self._last_call = 0.0
        self.session = requests.Session()

        if self.mode == "direct":
            self.base = (base or getattr(settings, "API_SPORTS_BASE",
                                         "https://v3.football.api-sports.io")).rstrip("/")
            if not key:
                raise ValueError("缺少 API_SPORTS_KEY: 请在 .env 中配置 "
                                 "(https://dashboard.api-football.com 免费注册获取)")
            self.session.headers.update({"x-apisports-key": key})
        else:
            self.base = (base or "https://api-football-v1.p.rapidapi.com/v3").rstrip("/")
            if not rapid_key:
                raise ValueError("缺少 API_FOOTBALL_KEY(RapidAPI)")
            self.session.headers.update({
                "x-rapidapi-key": rapid_key,
                "x-rapidapi-host": getattr(settings, "API_FOOTBALL_HOST",
                                           "api-football-v1.p.rapidapi.com"),
            })

        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        self.used = self._load_quota()

    # ---------------- 配额 ----------------
    @staticmethod
    def _today() -> str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")

    def _load_quota(self) -> int:
        try:
            return int(json.loads(QUOTA_FILE.read_text(encoding="utf-8")).get(self._today(), 0))
        except Exception:
            return 0

    def _save_quota(self):
        try:
            QUOTA_FILE.parent.mkdir(parents=True, exist_ok=True)
            data = {}
            if QUOTA_FILE.exists():
                data = json.loads(QUOTA_FILE.read_text(encoding="utf-8"))
            data[self._today()] = self.used
            QUOTA_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=1),
                                  encoding="utf-8")
        except Exception:
            pass

    def remaining(self) -> int:
        return max(0, self.daily_budget - self.used)

    # ---------------- 请求 ----------------
    def _cache_path(self, path: str, params: dict) -> Path:
        raw = path + "?" + json.dumps(params or {}, sort_keys=True, ensure_ascii=False)
        h = hashlib.md5(raw.encode("utf-8")).hexdigest()[:16]
        return CACHE_DIR / f"{path.strip('/').replace('/', '_')}_{h}.json.gz"

    def _get(self, path: str, params: dict = None, retries: int = 3,
             use_cache: bool = True) -> dict:
        cp = self._cache_path(path, params or {})
        if use_cache and self.cache and cp.exists():
            try:
                with gzip.open(cp, "rt", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass

        if self.used >= self.daily_budget:
            raise QuotaExceeded(f"今日请求已达预算 {self.daily_budget}(已用 {self.used})")

        url = f"{self.base}/{path.lstrip('/')}"
        last_err = None
        for attempt in range(retries):
            gap = time.time() - self._last_call
            if gap < self.min_interval:
                time.sleep(self.min_interval - gap)
            try:
                r = self.session.get(url, params=params, timeout=40)
                self._last_call = time.time()
                self.used += 1
                self._save_quota()
            except Exception as e:
                last_err = e
                time.sleep(2 * (attempt + 1))
                continue

            if r.status_code == 429 or r.status_code >= 500:
                last_err = f"HTTP {r.status_code}"
                time.sleep(3 * (attempt + 1))
                continue
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}: {r.text[:200]}")

            data = r.json()
            if data.get("errors"):
                raise RuntimeError(f"API 错误: {data['errors']}")
            if self.verbose:
                print(f"    [{path}] results={data.get('results')} | "
                      f"今日已用 {self.used}/{self.daily_budget}", flush=True)
            if self.cache:
                try:
                    with gzip.open(cp, "wt", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                except Exception:
                    pass
            return data

        raise RuntimeError(f"请求失败(重试{retries}次): {path} {params} | {last_err}")

    # ---------------- 业务接口 ----------------
    def status(self) -> dict:
        return self._get("status", use_cache=False).get("response", {})

    def leagues(self, league_id: int = None, season: int = None) -> list:
        p = {}
        if league_id:
            p["id"] = league_id
        if season:
            p["season"] = season
        return self._get("leagues", p).get("response", [])

    def league_coverage(self, league_id: int, season: int) -> dict:
        """返回 {coverage: {...}} —— 决定该联赛该赛季能补哪些数据"""
        for item in self.leagues(league_id, season):
            for s in item.get("seasons", []):
                if str(s.get("year")) == str(season):
                    return {"league": item.get("league"), "country": item.get("country"),
                            "season": season, "coverage": s.get("coverage", {})}
        return {}

    def fixtures(self, league_id: int, season: int, **kw) -> list:
        p = {"league": league_id, "season": season}
        p.update(kw)
        return self._get("fixtures", p).get("response", [])

    def fixture_lineups(self, fixture_id) -> list:
        return self._get("fixtures/lineups", {"fixture": fixture_id}).get("response", [])

    def fixture_events(self, fixture_id) -> list:
        return self._get("fixtures/events", {"fixture": fixture_id}).get("response", [])

    def fixture_statistics(self, fixture_id) -> list:
        return self._get("fixtures/statistics", {"fixture": fixture_id}).get("response", [])

    def fixture_players(self, fixture_id) -> list:
        return self._get("fixtures/players", {"fixture": fixture_id}).get("response", [])

    def players(self, team_id: int, season: int) -> list:
        """球队阵容(含身高/体重/国籍/照片/赛季统计)"""
        return self._get("players", {"team": team_id, "season": season}).get("response", [])

    def coachs(self, team_id: int) -> list:
        return self._get("coachs", {"team": team_id}).get("response", [])

    def injuries(self, league_id: int = None, season: int = None,
                 fixture_id=None, team_id=None) -> list:
        p = {}
        for k, v in (("league", league_id), ("season", season),
                     ("fixture", fixture_id), ("team", team_id)):
            if v:
                p[k] = v
        return self._get("injuries", p).get("response", [])

    def standings(self, league_id: int, season: int) -> list:
        return self._get("standings", {"league": league_id, "season": season}).get("response", [])

    def transfers(self, team_id: int = None, player_id: int = None) -> list:
        p = {}
        if team_id:
            p["team"] = team_id
        if player_id:
            p["player"] = player_id
        return self._get("transfers", p).get("response", [])

