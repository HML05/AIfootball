# -*- coding: utf-8 -*-
"""Football-Data.org 数据源 (免费, 100次/天)

覆盖五大联赛的 赛程 / 实时比分 / 赛果 / 积分榜。
- /v4/matches?dateFrom&dateTo 一次请求可拉全部联赛的比赛(非常省配额)
- /v4/competitions/{code}/standings 积分榜

状态映射: SCHEDULED/TIMED -> NS  LIVE -> 1H  PAUSED -> HT  FINISHED -> FT
"""
import os
import sqlite3
import unicodedata
from datetime import datetime, timedelta

import requests

from config.settings import settings

BASE = "https://api.football-data.org/v4"

# football-data 联赛代码 -> 项目 leagues 表 league_id (1英超 2西甲 3德甲 4意甲 5法甲)
COMP_LEAGUE = {"PL": 1, "PD": 2, "BL1": 3, "SA": 4, "FL1": 5}
STATUS_MAP = {
    "SCHEDULED": "NS", "TIMED": "NS", "LIVE": "1H",
    "PAUSED": "HT", "FINISHED": "FT", "CANCELED": "CANCL", "POSTPONED": "PSTP",
}

_CLUB_TOKENS = {"fc", "cf", "sc", "afc", "ac", "cd", "ud", "de", "ss", "us",
                "as", "rc", "cn", "tsg", "club", "calcio", "deportivo", "sport",
                "football", "formation", "kv", "ifk", "bk", "ik", "sk"}
# 别名: (去词后的规范化名) -> (库内规范名)
_TEAM_ALIAS = {
    "staderennais": "Rennes", "hullcity": "Hull", "tsghoffenheim": "Hoffenheim",
    # 西甲
    "barca": "Barcelona", "atleti": "Ath Madrid", "atleticomadrid": "Ath Madrid",
    "athletic": "Ath Bilbao", "athleticclub": "Ath Bilbao",
    "deportivo": "La Coruna", "deportivolacoruna": "La Coruna",
    # 英超
    "manchestercity": "Man City", "manchesterunited": "Man United",
    "tottenhamhotspur": "Tottenham", "westhamunited": "West Ham",
    "newcastleunited": "Newcastle", "wolverhamptonwanderers": "Wolves",
    "nottinghamforest": "Nott'm Forest", "leedsunited": "Leeds",
    "brightonhovealbion": "Brighton",
    # 德甲
    "bayernmunchen": "Bayern Munich", "bayernmunich": "Bayern Munich",
    "borussiamonchengladbach": "M'gladbach", "borussiamgladbach": "M'gladbach",
}


def _norm(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def _drop_club_tokens(name: str) -> str:
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    words = [w for w in s.lower().split() if w not in _CLUB_TOKENS]
    return " ".join(words)


def _match_team(conn, league_id, name, alt_name=None):
    """按规范化名称在库内找 team_id; 找不到则新建(避免重复建)
    name: 首选名(短名或全名); alt_name: 备选全名/短名, 首选失败时再试
    """

    def _try(n):
        if not n:
            return None
        # 精确
        row = conn.execute("SELECT team_id FROM teams WHERE league_id=? AND name=?",
                           (league_id, n)).fetchone()
        if row:
            return row["team_id"]
        # 别名
        alias = _TEAM_ALIAS.get(_norm(_drop_club_tokens(n)))
        if alias:
            row = conn.execute("SELECT team_id FROM teams WHERE league_id=? AND name=?",
                               (league_id, alias)).fetchone()
            if row:
                return row["team_id"]
        # 归一化精确 / 互相包含
        rows = conn.execute("SELECT team_id, name FROM teams WHERE league_id=?",
                            (league_id,)).fetchall()
        nn_db = {}
        for r in rows:
            nn_db[_norm(r["name"])] = r["team_id"]
        cand = _norm(_drop_club_tokens(n))
        if cand in nn_db:
            return nn_db[cand]
        for k, tid in nn_db.items():
            if cand and k and (cand in k or k in cand):
                return tid
        return None

    tid = _try(name) or _try(alt_name)
    if tid:
        return tid
    # 都没匹配: 新建(用首选名的去词干净名)
    clean = _drop_club_tokens(name).title()
    cur = conn.execute(
        "INSERT INTO teams (league_id, name, name_en, short_name, elo_rating, created_at) "
        "VALUES (?, ?, ?, ?, 1500.0, ?)",
        (league_id, clean, name, clean[:12], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return cur.lastrowid


class FootballDataClient:
    def __init__(self, token: str = None):
        self.token = token or settings.FOOTBALL_DATA_TOKEN
        if not self.token:
            raise ValueError("未配置 FOOTBALL_DATA_TOKEN")

    def _headers(self):
        return {"X-Auth-Token": self.token}

    def get_matches(self, date_from: str, date_to: str) -> list:
        """拉取日期区间内所有比赛(含多联赛)"""
        r = requests.get(f"{BASE}/matches", headers=self._headers(),
                         params={"dateFrom": date_from, "dateTo": date_to}, timeout=30)
        r.raise_for_status()
        return r.json().get("matches", [])

    def get_standings(self, comp_code: str, season: int = None) -> list:
        """指定联赛积分榜(season 为赛季起始年, 如 2025 表示 2025-26)"""
        params = {"season": season} if season else {}
        r = requests.get(f"{BASE}/competitions/{comp_code}/standings",
                         headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        data = r.json().get("standings", [])
        return data[0].get("table", []) if data else []

    def get_competition_matches(self, comp_code: str, season: int = None) -> list:
        """某赛事整赛季比赛(用于导入欧战/杯赛历史)"""
        params = {"season": season} if season else {}
        r = requests.get(f"{BASE}/competitions/{comp_code}/matches",
                         headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("matches", [])

    def get_competition_teams(self, comp_code: str, season: int = None) -> list:
        """某赛事的参赛球队(含队徽/球场/成立年)"""
        params = {"season": season} if season else {}
        r = requests.get(f"{BASE}/competitions/{comp_code}/teams",
                         headers=self._headers(), params=params, timeout=30)
        r.raise_for_status()
        return r.json().get("teams", [])


# ---------- 入库相关(直接用 sqlite3, 幂等) ----------

def _db():
    db = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "data", "database", "football.db")
    conn = sqlite3.connect(db)
    conn.row_factory = sqlite3.Row
    return conn


def _upsert_match(conn, league_id, season, date_str, score_h, score_a,
                  status, home_id, away_id, matchday=None):
    exist = conn.execute(
        "SELECT match_id FROM matches WHERE league_id=? AND date=? "
        "AND home_team_id=? AND away_team_id=?",
        (league_id, date_str, home_id, away_id)).fetchone()
    if exist:
        conn.execute(
            "UPDATE matches SET status=?, home_goals=?, away_goals=?, matchday=? "
            "WHERE match_id=?",
            (status, score_h, score_a, matchday, exist["match_id"]))
        return "updated"
    conn.execute(
        "INSERT INTO matches (league_id, season, matchday, date, home_team_id, "
        "away_team_id, home_goals, away_goals, status, created_at) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (league_id, season, matchday, date_str, home_id, away_id,
         score_h, score_a, status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return "inserted"


def _cleanup_recent(conn):
    """删除本次同步产生的未开赛记录 + 无任何比赛引用的孤儿球队(避免重复队)"""
    cutoff = (datetime.now() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
    n_mat = conn.execute("DELETE FROM matches WHERE status='NS' AND created_at >= ?",
                         (cutoff,)).rowcount
    n_team = conn.execute(
        "DELETE FROM teams WHERE team_id NOT IN "
        "(SELECT home_team_id FROM matches UNION SELECT away_team_id FROM matches)").rowcount
    return n_mat, n_team


def import_matches(days: int = 7, date_from=None, cleanup: bool = True) -> dict:
    """拉取 future days 天(含当天)的五大联赛比赛入库。返回统计。

    cleanup=False 用于分窗口拉取(如30天赛程), 避免后一窗口删掉前一窗口刚写的行。
    """
    now = datetime.now()
    start = date_from or now.date()
    end = start + timedelta(days=days - 1)
    client = FootballDataClient()

    raw = client.get_matches(start.isoformat(), end.isoformat())
    conn = _db()
    removed_mat, removed_team = _cleanup_recent(conn) if cleanup else (0, 0)
    inserted = updated = 0

    for m in raw:
        comp = m.get("competition", {}).get("code")
        lid = COMP_LEAGUE.get(comp)
        if not lid:
            continue  # 只处理五大联赛
        utc = m.get("utcDate")
        if not utc:
            continue
        dt = datetime.fromisoformat(utc.replace("Z", "+00:00")).astimezone()
        local = dt + timedelta(hours=8)
        date_str = local.strftime("%Y-%m-%d %H:%M")
        season = str(local.year)[2:] + str((local.year + 1) % 100).zfill(2)
        status = STATUS_MAP.get(m.get("status"), "NS")
        home_name = (m.get("homeTeam", {}).get("shortName")
                     or m.get("homeTeam", {}).get("name"))
        away_name = (m.get("awayTeam", {}).get("shortName")
                     or m.get("awayTeam", {}).get("name"))
        home_full = m.get("homeTeam", {}).get("name")
        away_full = m.get("awayTeam", {}).get("name")
        home_id = _match_team(conn, lid, home_name, home_full)
        away_id = _match_team(conn, lid, away_name, away_full)
        ft = m.get("score", {}).get("fullTime", {}) or {}
        score_h, score_a = ft.get("home"), ft.get("away")
        if status == "NS":
            score_h = score_a = None
        res = _upsert_match(conn, lid, season, date_str, score_h, score_a,
                            status, home_id, away_id, m.get("matchday"))
        inserted += res == "inserted"
        updated += res == "updated"

    conn.commit()
    conn.close()
    return {"fetched": len(raw), "inserted": inserted, "updated": updated,
            "cleaned_matches": removed_mat, "cleaned_teams": removed_team}


# ---------- 积分榜 ----------

def _ensure_standings_table(conn):
    conn.execute("""
        CREATE TABLE IF NOT EXISTS standings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER, season TEXT, team_id INTEGER,
            rank INTEGER, played INTEGER, won INTEGER, draw INTEGER, lost INTEGER,
            goals_for INTEGER, goals_against INTEGER, goal_diff INTEGER,
            points INTEGER, form TEXT, updated_at TEXT)
    """)


def import_standings(season: str = "2627", league_ids=None,
                     api_season: int = None, pause: float = 0.0) -> dict:
    """拉取五大联赛积分榜并整体替换入库。

    season: 库内赛季代码(如 "2627"); api_season: football-data 的赛季起始年(如 2026)
    pause: 每个联赛请求之间的间隔秒数(免费档限速 10 次/分钟)
    """
    client = FootballDataClient()
    conn = _db()
    _ensure_standings_table(conn)
    synced = 0
    rows_total = 0
    for code, lid in COMP_LEAGUE.items():
        if league_ids and lid not in league_ids:
            continue
        if pause and synced:
            import time
            time.sleep(pause)
        try:
            table = client.get_standings(code, season=api_season)
        except Exception as e:
            print(f"⚠️ 积分榜 {code} 拉取失败: {e}")
            continue
        if not table:
            continue
        conn.execute("DELETE FROM standings WHERE league_id=? AND season=?",
                     (lid, season))
        for row in table:
            team = row.get("team", {}) or {}
            full_name = team.get("name")
            short_name = team.get("shortName")
            name = full_name or short_name
            if not name:
                continue
            tid = _match_team(conn, lid, name,
                              short_name if short_name != name else None)
            # 回填队徽(football-data 自带 crest, 免费)
            crest = team.get("crest")
            if crest:
                conn.execute(
                    "UPDATE teams SET logo_url=? WHERE team_id=? "
                    "AND (logo_url IS NULL OR logo_url='')", (crest, tid))
            conn.execute("""
                INSERT INTO standings
                    (league_id, season, team_id, rank, played, won, draw, lost,
                     goals_for, goals_against, goal_diff, points, form, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (lid, season, tid, row.get("position"),
                  row.get("playedGames", 0), row.get("won", 0),
                  row.get("draw", 0), row.get("lost", 0),
                  row.get("goalsFor", 0), row.get("goalsAgainst", 0),
                  row.get("goalDifference", 0), row.get("points", 0),
                  row.get("form"), datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            rows_total += 1
        synced += 1
    # 清理孤儿队: 不在任何比赛、也不在积分榜里的队(昵称/空名残留)直接删
    conn.execute(
        "DELETE FROM teams WHERE team_id NOT IN "
        "(SELECT home_team_id FROM matches UNION SELECT away_team_id FROM matches "
        " UNION SELECT team_id FROM standings)")
    conn.commit()
    conn.close()
    return {"leagues": synced, "rows": rows_total}
