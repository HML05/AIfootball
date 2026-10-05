"""真实数据接口（只读）—— 供 React 前端（webui）使用

设计要点
- 只读 SQLite 连接（URI mode=ro）：多进程共享同一库，绝不加写锁
- 重聚合结果走进程内 TTL 缓存，保证页面秒开
- 中英文成对返回（name / nameEn），前端按语言直接取值，不再走 i18n 字典
- 列表接口统一分页：{items, total, page, size, pages}
- 数据事实：matches 12,698 / players 4,745 / teams 240 / leagues 10 /
  tm_player_seasons 370,362 / tm_player_market_value 901,429 /
  tm_player_injuries 94,160 / transfers 170,663 / tm_transfers 176,100 /
  predictions 1,803 / model_metrics 11 / standings 812 / understat_xg 10,660
"""
from __future__ import annotations

import datetime as _dt
import math
import sqlite3
import time
import urllib.request
from pathlib import Path
from typing import Any, Callable

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from fastapi.responses import Response
from sqlalchemy.orm import Session

from config.settings import settings
from src.api.auth import current_user as _session_user
from src.database.crud import get_db

# 登录闸门: /api/ui/* 默认要求 Authorization: Bearer <token>
#   例外 1: settings.UI_REQUIRE_AUTH=False 时整体放行(本地调试)
#   例外 2: /logo/{team_id} —— 队徽是 <img src> 直连, 浏览器不会带请求头, 必须公开
def require_ui_login(request: Request,
                     authorization: str | None = Header(default=None),
                     db: Session = Depends(get_db)):
    if not settings.UI_REQUIRE_AUTH or "/logo/" in request.url.path or "/public/" in request.url.path:
        return None
    if _session_user(db, authorization) is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期",
                            headers={"WWW-Authenticate": "Bearer"})
    return None


router = APIRouter(dependencies=[Depends(require_ui_login)])

DB_PATH = settings.BASE_DIR / "data" / "database" / "football.db"
CREST_DIR = settings.DATA_DIR / "cache" / "crests"


# ============ 基础工具 ============

def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB_PATH.as_posix()}?mode=ro", uri=True, timeout=15)
    con.row_factory = sqlite3.Row
    return con


def rows(sql: str, params: tuple = ()) -> list[dict]:
    con = _connect()
    try:
        return [dict(r) for r in con.execute(sql, params).fetchall()]
    finally:
        con.close()


def one(sql: str, params: tuple = ()) -> dict:
    r = rows(sql, params)
    return r[0] if r else {}


_CACHE: dict[str, tuple[float, Any]] = {}


def _crest_index() -> dict[str, str]:
    """外网队徽 URL -> 本地代理 URL（离线可用 + 磁盘缓存，避免前端直连外网）。"""
    idx = _CACHE.get(("__crest_index__", (), ()))
    if idx and time.time() - idx[0] < 3600:
        return idx[1]
    m = {r["logo_url"]: f"/api/ui/logo/{r['team_id']}"
         for r in rows("SELECT team_id, logo_url FROM teams WHERE logo_url IS NOT NULL AND logo_url <> ''")}
    _CACHE[("__crest_index__", (), ())] = (time.time(), m)
    return m


def _swap_crests(obj: Any) -> Any:
    """把所有外网队徽 URL 换成 /api/ui/logo/<id>（前端一行不用改）。"""
    if isinstance(obj, dict):
        return {k: _swap_crests(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_swap_crests(v) for v in obj]
    if isinstance(obj, str) and obj.startswith("http"):
        return _crest_index().get(obj, obj)
    return obj


def cached(ttl: int = 300) -> Callable:
    """进程内 TTL 缓存（键 = 函数名 + 参数）"""
    def deco(fn: Callable):
        def wrapper(*args, **kwargs):
            key = (fn.__name__, args, tuple(sorted(kwargs.items())))
            now = time.time()
            hit = _CACHE.get(key)
            if hit and now - hit[0] < ttl:
                return hit[1]
            val = _swap_crests(fn(*args, **kwargs))
            _CACHE[key] = (now, val)
            return val
        wrapper.__name__ = fn.__name__
        return wrapper
    return deco


def _season_label(code: str | None) -> str:
    """'2627' -> '2026/27'；'23/24' 原样返回"""
    if not code:
        return ""
    s = str(code)
    if "/" in s:
        return s
    if len(s) == 4 and s.isdigit():
        return f"20{s[:2]}/{s[2:]}"
    return s


# 本系统的联赛 -> Transfermarkt 赛事名（两边命名并不一致: 'La Liga' vs 'LaLiga'，
# 'UEFA Champions League' vs 'Champions League'，巴西 'Série A' 与意大利 'Serie A' 只差重音）
def _season_summary(r: dict | None) -> dict:
    """把汇总行换算成「只算已完赛」的场均口径（未开赛的场次不能计入分母）"""
    r = r or {}
    n = r.get("n") or 0
    ft = r.get("ft") or 0
    xg_n = r.get("xg_n") or 0
    return {
        "n": n, "ft": ft, "upcoming": max(0, n - ft),
        "goals_pg": round((r.get("goals") or 0) / ft, 2) if ft else None,
        "xg_pg": round((r.get("xg") or 0) / xg_n, 2) if xg_n else None,
        "mn": r.get("mn"), "mx": r.get("mx"),
    }


_MATCH_AGG = ("SELECT COUNT(*) n, SUM(status='FT') ft,"
              "       SUM(CASE WHEN status='FT' THEN home_goals+away_goals END) goals,"
              "       SUM(CASE WHEN status='FT' THEN home_xg+away_xg END) xg,"
              "       SUM(CASE WHEN status='FT' AND home_xg IS NOT NULL THEN 1 ELSE 0 END) xg_n,"
              "       MIN(date) mn, MAX(date) mx FROM matches")


# leagues.country 只有中文，界面英文时需要英文国名
_COUNTRY_EN = {
    "英格兰": "England", "西班牙": "Spain", "德国": "Germany", "意大利": "Italy",
    "法国": "France", "欧洲": "Europe", "荷兰": "Netherlands", "葡萄牙": "Portugal",
    "巴西": "Brazil",
}


_TM_COMPETITIONS: dict[int, list[str]] = {
    1: ["Premier League"],
    2: ["LaLiga", "La Liga"],
    3: ["Bundesliga"],
    4: ["Serie A"],
    5: ["Ligue 1"],
    6: ["Champions League"],
    7: ["Championship"],
    8: ["Eredivisie"],
    9: ["Primeira Liga", "Liga Portugal", "Liga NOS"],
    10: ["Série A"],
}


def _tm_competitions(league: dict) -> list[str]:
    lg_id = league.get("league_id")
    if lg_id in _TM_COMPETITIONS:
        return _TM_COMPETITIONS[lg_id]
    name = (league.get("name_en") or "").strip()
    return [n for n in {name, name.replace(" ", "")} if n]


def _tm_seasons(names: list[str]) -> list[str]:
    """这些赛事在 tm_player_seasons 里真实存在的赛季，按时间倒序。

    注意: 不能用 MAX(season_name) —— '99/00' 按字符串大于 '24/25'，
    会把 1999/2000 的射手榜当成最新赛季（真实踩过的坑）。
    """
    if not names:
        return []
    ph = ",".join("?" * len(names))
    return [r["season_name"] for r in rows(
        f"SELECT season_name, MAX(season_start) ss FROM tm_player_seasons "
        f"WHERE competition_name IN ({ph}) GROUP BY season_name ORDER BY ss DESC", tuple(names))]


def _season_code_to_tm(season: str | None) -> str:
    """界面赛季码 -> Transfermarkt 赛季名: '2627' -> '26/27'（不适用则空串）"""
    s = (season or "").strip()
    return f"{s[:2]}/{s[2:]}" if len(s) == 4 and s.isdigit() else ""


def _tm_season_label(name: str | None) -> str:
    """Transfermarkt 赛季名 -> 显示标签。'25/26' 原样；'2025'（巴西日历年）不加 '20' 前缀"""
    s = (name or "").strip()
    if not s:
        return ""
    if "/" in s or s[:2] in ("19", "20"):
        return s
    return _season_label(s)


_POS_MAP = {    "Goalkeeper": "GK", "Keeper": "GK",
    "Defender": "DF", "Centre-Back": "DF", "Left-Back": "DF", "Right-Back": "DF", "Full-back": "DF",
    "Midfielder": "MF", "Midfield": "MF", "Central Midfield": "MF", "Defensive Midfield": "MF",
    "Attacking Midfield": "MF", "Left Midfield": "MF", "Right Midfield": "MF",
    "Attacker": "FW", "Attack": "FW", "Forward": "FW", "Centre-Forward": "FW", "Striker": "FW",
    "Left Wing": "FW", "Right Wing": "FW", "Right Winger": "FW", "Left Winger": "FW", "Winger": "FW",
}
_POS_LABEL = {"GK": ("门将", "Goalkeeper"), "DF": ("后卫", "Defender"),
              "MF": ("中场", "Midfielder"), "FW": ("前锋", "Forward"), "": ("未知", "Unknown")}


def _pos_group(pos: str | None) -> str:
    return _POS_MAP.get((pos or "").strip(), "")


def _fmt_value(v: float | None) -> str:
    """身价（欧元）-> 可读字符串"""
    if not v:
        return "—"
    if v >= 1_000_000:
        return f"{v / 1_000_000:.0f}M€" if v % 1_000_000 == 0 else f"{v / 1_000_000:.1f}M€"
    if v >= 1_000:
        return f"{v / 1000:.0f}K€"
    return f"{v:.0f}€"


def _r2(v: float | None, digits: int = 2) -> float | None:
    """四舍五入；None/NaN 原样返回 None（前端按「—」兜底）。"""
    if v is None:
        return None
    try:
        f = float(v)
    except (TypeError, ValueError):
        return None
    if f != f:  # NaN
        return None
    return round(f, digits)


def _logo(team_id: Any) -> str | None:
    r = one("SELECT logo_url FROM teams WHERE team_id=?", (team_id,)) if team_id is not None else {}
    url = (r or {}).get("logo_url") or ""
    return url or None


LEAGUE_ORDER = [1, 2, 3, 4, 5, 7, 8, 9, 10, 6]  # 五大联赛优先，欧冠殿后


# ============ 数据资产盘点 ============

@cached(600)
def table_counts() -> list[dict]:
    names = [r["name"] for r in rows(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    out = []
    for n in names:
        cnt = one(f'SELECT COUNT(*) n FROM "{n}"').get("n", 0)
        out.append({"name": n, "rows": cnt})
    return out


_TABLE_GROUPS = {
    "matches": ("赛事", "Matches"), "leagues": ("联赛", "Leagues"), "teams": ("球队", "Teams"),
    "players": ("球员", "Players"), "player_radar": ("球员画像", "Player profiles"),
    "team_radar": ("球队画像", "Team profiles"), "standings": ("积分榜", "Standings"),
    "predictions": ("预测", "Predictions"), "model_metrics": ("模型评估", "Model metrics"),
    "model_calibration": ("概率校准", "Calibration"), "model_confusion": ("混淆矩阵", "Confusion"),
    "feature_importance": ("特征重要性", "Feature importance"),
    "league_stats": ("联赛统计", "League stats"), "understat_xg": ("官方 xG", "Official xG"),
    "transfers": ("转会", "Transfers"), "tm_transfers": ("转会(国际)", "Transfers (TM)"),
    "tm_player_market_value": ("身价走势", "Market value history"),
    "tm_player_seasons": ("赛季数据", "Season stats"),
    "tm_player_injuries": ("伤停", "Injuries"),
    "tm_players": ("球员档案", "Player archive"), "tm_team_seasons": ("球队赛季", "Team seasons"),
    "auth_users": ("账号", "Accounts"), "auth_sessions": ("会话", "Sessions"),
}


def _group_of(name: str) -> tuple[str, str]:
    if name in _TABLE_GROUPS:
        return _TABLE_GROUPS[name]
    if name.startswith("tm_"):
        return ("Transfermarkt", "Transfermarkt")
    if name.startswith("af_"):
        return ("API-Football", "API-Football")
    if name.startswith("qxz"):
        return ("球小智", "QiuXiaoZhi")
    if name.startswith("auth"):
        return ("账号体系", "Auth")
    return ("其它", "Other")


# ============ 首页 ============

@cached(300)
def _core_counts() -> dict:
    m = one("SELECT COUNT(*) n, SUM(status='FT') ft, SUM(status='NS') ns, MIN(date) mn, MAX(date) mx FROM matches")
    finished_max = one("SELECT MAX(date) mx FROM matches WHERE status='FT'").get("mx") or ""
    total_records = sum(t["rows"] for t in table_counts())
    return {
        "matches": m.get("n") or 0,
        "finished": m.get("ft") or 0,
        "upcoming": m.get("ns") or 0,
        "first_date": m.get("mn") or "",
        "last_date": m.get("mx") or "",
        "now": finished_max,
        "players": one("SELECT COUNT(*) n FROM players").get("n", 0),
        "teams": one("SELECT COUNT(*) n FROM teams").get("n", 0),
        "leagues": one("SELECT COUNT(*) n FROM leagues").get("n", 0),
        "records": total_records,
        "tables": len(table_counts()),
    }


@cached(300)
def _best_model() -> dict:
    best = one("SELECT * FROM model_metrics ORDER BY acc DESC LIMIT 1")
    return best or {}


@cached(300)
def _month_series(limit: int = 12) -> list[dict]:
    """最近 limit 个月的入库量（只到「数据当前月」，不含未来赛程月份）"""
    now_month = (_core_counts()["now"] or "")[:7] or "9999-99"
    data = rows("SELECT substr(date,1,7) m, COUNT(*) n, SUM(status='FT') ft FROM matches "
                "WHERE substr(date,1,7) <= ? GROUP BY m ORDER BY m", (now_month,))
    return data[-limit:]


@cached(300)
def _top_scorers(limit: int = 7) -> list[dict]:
    # tm_player_seasons 里最新一个「完整赛季」（跨年制 '24/25' 这类，行数 > 8000）
    season = one("SELECT season_name s FROM tm_player_seasons GROUP BY season_name "
                 "HAVING COUNT(*) > 8000 ORDER BY MAX(season_start) DESC LIMIT 1").get("s") or "23/24"
    data = rows(
        "SELECT s.player_id, MAX(s.team_name) team_name, SUM(s.goals) goals, SUM(s.assists) assists,"
        "       SUM(s.appearances) apps, SUM(s.minutes) minutes,"
        "       MAX(p.player_name) player_name, MAX(p.image_url) image_url, MAX(p.position) position,"
        "       MAX(s.competition_name) competition_name "
        "FROM tm_player_seasons s LEFT JOIN tm_players p ON p.player_id = s.player_id "
        "WHERE s.season_name = ? AND s.goals > 0 "
        "GROUP BY s.player_id ORDER BY goals DESC, apps ASC LIMIT ?", (season, limit))
    out = []
    for i, r in enumerate(data, 1):
        out.append({
            "rank": i,
            "name": r["player_name"] or r["player_id"],
            "team": r["team_name"] or "",
            "league": r["competition_name"] or "",
            "goals": r["goals"], "assists": r["assists"], "apps": r["apps"],
            "minutes": r["minutes"], "photo": r["image_url"], "position": r["position"] or "",
        })
    return {"season": _season_label(season), "seasonCode": season, "items": out}


@cached(120)
def _focus_match() -> dict:
    """下一场有预测的未开赛比赛"""
    r = one(
        "SELECT m.match_id, m.date, m.home_team_id, m.away_team_id, m.status,"
        "       l.name lg, l.name_en lg_en, m.season,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo "
        "FROM matches m "
        "JOIN leagues l ON l.league_id = m.league_id "
        "JOIN teams th ON th.team_id = m.home_team_id "
        "JOIN teams ta ON ta.team_id = m.away_team_id "
        "JOIN predictions p ON p.match_id = m.match_id "
        "WHERE m.status = 'NS' AND p.actual_result IS NULL "
        "ORDER BY m.date LIMIT 1")
    if not r:
        r = one(
            "SELECT m.match_id, m.date, l.name lg, l.name_en lg_en, m.season, m.home_team_id, m.away_team_id,"
            "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo "
            "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
            "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
            "WHERE m.status='NS' ORDER BY m.date LIMIT 1")
    if not r:
        return {}
    pred = one("SELECT * FROM predictions WHERE match_id=? ORDER BY pred_id DESC LIMIT 1", (r["match_id"],))
    segs = []
    if pred:
        for key, label, label_en, field in (("home", "主胜", "Home", "pred_home_win"),
                                            ("draw", "平局", "Draw", "pred_draw"),
                                            ("away", "客胜", "Away", "pred_away_win")):
            segs.append({"key": key, "label": label, "labelEn": label_en,
                         "pct": round((pred.get(field) or 0) * 100, 1)})
    top = max(segs, key=lambda s: s["pct"]) if segs else None
    return {
        "matchId": r["match_id"], "date": r["date"], "status": r["status"],
        "league": r["lg"], "leagueEn": r["lg_en"], "season": _season_label(r["season"]),
        "home": {"name": r["h"], "nameEn": r["h_en"], "logo": r["h_logo"], "id": r["home_team_id"]},
        "away": {"name": r["a"], "nameEn": r["a_en"], "logo": r["a_logo"], "id": r["away_team_id"]},
        "segments": segs,
        "pick": top["label"] if top else "", "pickEn": top["labelEn"] if top else "",
        "conf": top["pct"] if top else 0, "model": (pred or {}).get("model_version", ""),
    }


@cached(120)
def _next_fixtures(limit: int = 6) -> list[dict]:
    return rows(
        "SELECT m.match_id, m.date, m.home_team_id, m.away_team_id, l.name lg, l.name_en lg_en,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo,"
        "       p.pred_home_win, p.pred_draw, p.pred_away_win, p.pred_result, p.model_version "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "LEFT JOIN predictions p ON p.match_id=m.match_id "
        "WHERE m.status='NS' ORDER BY m.date LIMIT ?", (limit,))


@cached(120)
def _recent_matches(limit: int = 8) -> list[dict]:
    return rows(
        "SELECT m.match_id, m.date, m.home_goals, m.away_goals, m.home_xg, m.away_xg, l.name lg, l.name_en lg_en,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "WHERE m.status='FT' ORDER BY m.date DESC LIMIT ?", (limit,))


@cached(120)
def _league_country(league_id: int) -> str:
    r = one("SELECT country FROM leagues WHERE league_id=?", (league_id,))
    return (r or {}).get("country") or ""


def _league_cards() -> list[dict]:
    stats = rows(
        "SELECT ls.league_id, ls.league, ls.season, ls.matches, ls.goals_pg, ls.xg_pg,"
        "       ls.home_win_pct, ls.draw_pct, ls.away_win_pct, l.name_en "
        "FROM league_stats ls JOIN leagues l ON l.league_id = ls.league_id "
        "WHERE ls.season = (SELECT MAX(season) FROM league_stats WHERE league_id = ls.league_id)")
    cnt = {r["league_id"]: r["n"] for r in rows(
        "SELECT league_id, COUNT(*) n FROM matches GROUP BY league_id")}
    team_cnt = {r["league_id"]: r["n"] for r in rows(
        "SELECT league_id, COUNT(*) n FROM ("
        "  SELECT league_id, home_team_id AS tid FROM matches"
        "  UNION SELECT league_id, away_team_id FROM matches) GROUP BY league_id")}
    season_team_cnt = {r["league_id"]: r["n"] for r in rows(
        "SELECT league_id, COUNT(*) n FROM ("
        "  SELECT league_id, home_team_id AS tid FROM matches WHERE season='2627'"
        "  UNION SELECT league_id, away_team_id FROM matches WHERE season='2627') GROUP BY league_id")}
    out = []
    for s in stats:
        lid = s["league_id"]
        top3 = rows(
            "SELECT s.rank, t.name, t.name_en, s.points, s.played, s.form, t.logo_url "
            "FROM standings s JOIN teams t ON t.team_id = s.team_id "
            "WHERE s.league_id=? AND s.season='2627' ORDER BY s.rank LIMIT 3", (lid,))
        out.append({
            "id": lid, "name": s["league"], "nameEn": s["name_en"] or s["league"],
            "country": _league_country(lid),
            "countryEn": _COUNTRY_EN.get(_league_country(lid), _league_country(lid)),
            "season": _season_label(s["season"]), "matches": cnt.get(lid, 0),
            "teams": season_team_cnt.get(lid, 0) or team_cnt.get(lid, 0),
            "goalsPg": s["goals_pg"], "xgPg": s["xg_pg"],
            "homeWinPct": s["home_win_pct"], "drawPct": s["draw_pct"], "awayWinPct": s["away_win_pct"],
            "top3": [{"rank": t["rank"], "team": t["name"], "teamEn": t["name_en"],
                      "points": t["points"], "played": t["played"], "form": t["form"],
                      "logo": t["logo_url"]} for t in top3],
        })
    order = {lid: i for i, lid in enumerate(LEAGUE_ORDER)}
    out.sort(key=lambda x: order.get(x["id"], 99))
    return out


@cached(120)
def _update_log() -> list[dict]:
    core = _core_counts()
    mv = one("SELECT COUNT(*) n, MAX(value_date) mx FROM tm_player_market_value")
    ts = one("SELECT COUNT(*) n, MAX(transfer_date) mx FROM tm_transfers")
    inj = one("SELECT COUNT(*) n, SUM(games_missed) g FROM tm_player_injuries")
    sea = one("SELECT COUNT(*) n FROM tm_player_seasons")
    best = _best_model()
    pred = one("SELECT COUNT(*) n, SUM(hit) h FROM predictions WHERE actual_result IS NOT NULL")
    hit_rate = round((pred.get("h") or 0) / pred["n"] * 100, 1) if pred.get("n") else 0
    now = (core["now"] or "")[:10]

    def item(i, ts_, level, title, title_en, desc, desc_en, done=True):
        return {"id": i, "ts": ts_, "level": level, "title": title, "titleEn": title_en,
                "desc": desc, "descEn": desc_en, "done": done}

    return [
        item("sync", core["last_date"], "sync", "赛程同步完成", "Fixtures synchronized",
             f"{core['matches']:,} 场赛程入库 · 已完赛 {core['finished']:,} 场",
             f"{core['matches']:,} fixtures · {core['finished']:,} finished"),
        item("value", mv.get("mx") or "", "value", "身价数据同步", "Market values synced",
             f"{mv.get('n', 0):,} 条身价记录 · 覆盖 {core['players']:,} 名球员档案",
             f"{mv.get('n', 0):,} value records"),
        item("transfer", ts.get("mx") or "", "transfer", "转会数据入库", "Transfers ingested",
             f"{ts.get('n', 0):,} 笔转会 · 最新 {ts.get('mx', '')}",
             f"{ts.get('n', 0):,} transfers"),
        item("season", now, "season", "赛季数据补全", "Season stats completed",
             f"{sea.get('n', 0):,} 条球员赛季数据（进球/助攻/出场）",
             f"{sea.get('n', 0):,} player-season rows"),
        item("injury", now, "injury", "伤停数据入库", "Injuries ingested",
             f"{inj.get('n', 0):,} 条伤停 · 累计缺席 {int(inj.get('g') or 0):,} 场",
             f"{inj.get('n', 0):,} injury records"),
        item("retrain", now, "retrain", "模型评估刷新", "Model metrics refreshed",
             f"{best.get('model', '')} · 准确率 {best.get('acc', 0)}%（样本外 {best.get('test_n', 0):,} 场）",
             f"{best.get('model', '')} · acc {best.get('acc', 0)}%"),
        item("predict", now, "predict", "预测样本回测", "Predictions backtested",
             f"{pred.get('n', 0):,} 条已评估预测 · 命中率 {hit_rate}%",
             f"{pred.get('n', 0):,} evaluated · hit {hit_rate}%"),
    ]


@cached(120)
def _calendar() -> dict:
    """以数据最新比赛日为「今天」，取之后 6 个有赛程的日子"""
    core = _core_counts()
    base = (core["now"] or "")[:10]
    fixtures = rows(
        "SELECT m.match_id, m.date, m.status, l.name lg, l.name_en lg_en,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo,"
        "       p.pred_result, p.pred_home_win, p.pred_draw, p.pred_away_win, p.model_version "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "LEFT JOIN predictions p ON p.match_id=m.match_id "
        "WHERE m.status='NS' AND substr(m.date,1,10) > ? ORDER BY m.date LIMIT 400", (base,))
    if not fixtures:
        return {"month": "", "days": [], "hours": [], "events": []}
    days: list[str] = []
    for f in fixtures:
        d = f["date"][:10]
        if d not in days:
            days.append(d)
        if len(days) == 6:
            break
    win = [f for f in fixtures if f["date"][:10] in days]
    hours = sorted({int(f["date"][11:13]) for f in win})
    if len(hours) > 5:
        # 保留场次最多的 5 个时段
        freq: dict[int, int] = {}
        for f in win:
            freq[int(f["date"][11:13])] = freq.get(int(f["date"][11:13]), 0) + 1
        hours = sorted(sorted(freq, key=lambda h: -freq[h])[:5])
    events = []
    for f in win[:10]:
        d = f["date"][:10]
        hour = int(f["date"][11:13])
        near = min(hours, key=lambda h: abs(h - hour))
        probs = [f["pred_home_win"] or 0, f["pred_draw"] or 0, f["pred_away_win"] or 0]
        conf = round(max(probs) * 100, 1) if any(probs) else 0
        events.append({
            "id": str(f["match_id"]),
            "title": f"{f['h']} vs {f['a']}",
            "subtitle": (f"{f['lg']} · 预测 {f['pred_result'] or '—'} · 置信度 {conf}%"
                         if f["pred_result"] else f"{f['lg']} · {f['date'][11:16]}"),
            "startDay": days.index(d), "span": 1, "startHour": near,
            "theme": "dark" if len(events) == 0 else "light",
            "logos": [f["h_logo"], f["a_logo"]],
            "time": f["date"][11:16], "matchId": f["match_id"],
        })
    return {
        "month": days[0][:7].replace("-", " / "),
        "baseDate": base,
        "days": [{"d": d, "date": d} for d in days],
        "hours": hours,
        "events": events,
    }


@router.get("/home")
def home():
    """首页概览：全部为库内真实数据"""
    core = _core_counts()
    best = _best_model()
    months = _month_series(12)
    prev = months[-2]["n"] if len(months) > 1 else 0
    cur = months[-1]["n"] if months else 0
    delta = round((cur - prev) / prev * 100, 1) if prev else 0
    scorers = _top_scorers(7)
    leagues = _league_cards()
    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "brand": {"name": "FootballAI", "sub": "足球数据分析与 AI 预测系统", "subEn": "Football analytics & AI prediction"},
        "dataNow": core["now"],
        "stats": {
            "matches": {"label": "收录比赛", "labelEn": "Matches", "value": core["matches"],
                        "sub": f"已完赛 {core['finished']:,} 场", "subEn": f"{core['finished']:,} finished"},
            "players": {"label": "球员样本", "labelEn": "Players", "value": core["players"],
                        "sub": f"含身价 {(one('SELECT COUNT(*) n FROM players WHERE market_value IS NOT NULL')['n']):,} 名",
                        "subEn": "with market value"},
            "accuracy": {"label": "预测准确率", "labelEn": "Accuracy", "value": best.get("acc", 0),
                         "decimals": 2, "suffix": "%",
                         "sub": f"{best.get('model', '')} · 样本外 {best.get('test_n', 0):,}",
                         "subEn": "out-of-sample"},
            "models": {"label": "模型版本", "labelEn": "Models",
                       "value": one("SELECT COUNT(*) n FROM model_metrics")["n"],
                       "sub": "v1 ~ v9 对比", "subEn": "v1 ~ v9"},
            "teams": {"label": "收录球队", "labelEn": "Teams", "value": core["teams"],
                      "sub": f"Elo 覆盖 {one('SELECT COUNT(*) n FROM teams WHERE elo_rating IS NOT NULL')['n']} 支",
                      "subEn": "with Elo"},
            "leagues": {"label": "联赛", "labelEn": "Leagues", "value": core["leagues"],
                        "sub": "6 个赛季", "subEn": "6 seasons"},
            "records": {"label": "待赛赛程", "labelEn": "Upcoming", "value": core["upcoming"],
                        "sub": f"至 {str(core['last_date'])[:10]}", "subEn": f"until {str(core['last_date'])[:10]}"},
            "ingest": {"label": "本月入库", "labelEn": "Ingested this month", "value": cur,
                       "delta": delta, "sub": months[-1]["m"] if months else "", "subEn": ""},
        },
        "hero": _focus_match(),
        "topScorers": scorers,
        "focusMatch": _focus_match(),
        "leagueCards": leagues,
        "recent": _recent_matches(8),
        "upcoming": _next_fixtures(6),
        "calendar": _calendar(),
        "updateLog": _update_log(),
        "trend": {"labels": [m["m"] for m in months], "values": [m["n"] for m in months],
                  "finished": [m["ft"] or 0 for m in months], "unit": "场", "unitEn": "matches"},
        "coverage": {
            "matches": core["matches"], "finished": core["finished"], "upcoming": core["upcoming"],
            "xofficial": one("SELECT COUNT(*) n FROM understat_xg")["n"],
            "predictions": one("SELECT COUNT(*) n FROM predictions")["n"],
            "rangeFrom": core["first_date"], "rangeTo": core["last_date"],
        },
    }


# ============ 管理后台 ============

@router.get("/admin")
def admin():
    core = _core_counts()
    months = _month_series(12)
    counts = {t["name"]: t["rows"] for t in table_counts()}

    def delta_of() -> float:
        if len(months) < 2:
            return 0.0
        prev, cur = months[-2]["n"], months[-1]["n"]
        return round((cur - prev) / prev * 100, 1) if prev else 0.0

    hit = one("SELECT COUNT(*) n, SUM(hit) h FROM predictions WHERE actual_result IS NOT NULL AND hit IS NOT NULL")
    hit_rate = round((hit.get("h") or 0) / hit["n"] * 100, 1) if hit.get("n") else 0
    d = delta_of()
    modules = [
        {"id": "matches", "value": core["matches"], "unit": "场", "unitEn": "matches",
         "delta": f"{'+' if d >= 0 else ''}{d}%",
         "sub": f"本月 {months[-1]['n'] if months else 0} 场", "subEn": "this month"},
        {"id": "players", "value": core["players"], "unit": "名", "unitEn": "players",
         "delta": f"含身价 {one('SELECT COUNT(*) n FROM players WHERE market_value IS NOT NULL')['n']:,}",
         "sub": "球探画像 / 身价覆盖", "subEn": "profiles & market value"},
        {"id": "events", "value": counts.get("tm_player_market_value", 0), "unit": "条", "unitEn": "records",
         "delta": "身价走势", "sub": "Transfermarkt 身价历史", "subEn": "market value history"},
        {"id": "predictions", "value": counts.get("predictions", 0), "unit": "条", "unitEn": "predictions",
         "delta": f"命中 {hit_rate}%", "sub": f"已评估 {hit.get('n') or 0:,} 条", "subEn": "evaluated"},
    ]

    distribution = [
        {"key": "matches", "label": "赛事数据", "labelEn": "Matches",
         "count": counts.get("matches", 0) + counts.get("standings", 0) + counts.get("understat_xg", 0)},
        {"key": "players", "label": "球员数据", "labelEn": "Players",
         "count": counts.get("players", 0) + counts.get("player_radar", 0) + counts.get("tm_players", 0)},
        {"key": "season", "label": "赛季/球队", "labelEn": "Season & teams",
         "count": counts.get("tm_player_seasons", 0) + counts.get("tm_team_seasons", 0)},
        {"key": "transfers", "label": "转会/身价", "labelEn": "Transfers & value",
         "count": counts.get("transfers", 0) + counts.get("tm_transfers", 0)},
    ]

    pipeline = [
        {"key": "value", "label": "身价走势", "labelEn": "Market value history",
         "value": counts.get("tm_player_market_value", 0)},
        {"key": "season", "label": "球员赛季数据", "labelEn": "Player seasons",
         "value": counts.get("tm_player_seasons", 0)},
        {"key": "transfers", "label": "转会记录", "labelEn": "Transfers",
         "value": counts.get("tm_transfers", 0)},
        {"key": "injuries", "label": "伤停记录", "labelEn": "Injuries",
         "value": counts.get("tm_player_injuries", 0)},
        {"key": "predictions", "label": "预测样本", "labelEn": "Predictions",
         "value": counts.get("predictions", 0)},
    ]

    # 总进球数分布（真实：按 FT 比赛的双方进球和分档）
    bands = rows(
        "SELECT CASE WHEN (home_goals+away_goals) <= 1 THEN '0-1' "
        "            WHEN (home_goals+away_goals) = 2 THEN '2' "
        "            WHEN (home_goals+away_goals) = 3 THEN '3' "
        "            WHEN (home_goals+away_goals) = 4 THEN '4' "
        "            WHEN (home_goals+away_goals) = 5 THEN '5' ELSE '6+' END band,"
        "       COUNT(*) count FROM matches WHERE status='FT' "
        "GROUP BY band ORDER BY MIN(home_goals+away_goals)")
    order = {"0-1": 0, "2": 1, "3": 2, "4": 3, "5": 4, "6+": 5}
    bands.sort(key=lambda b: order.get(b["band"], 9))

    models = rows("SELECT * FROM model_metrics ORDER BY acc DESC")
    for i, m in enumerate(models):
        m["status"] = "production" if i == 0 else ("challenger" if i <= 2 else "baseline")
        m["name"] = m["model"]
        m["nameEn"] = m["model"]
        m["trainedAt"] = "样本外 1,817 场"

    tables = sorted(table_counts(), key=lambda t: -t["rows"])[:14]
    for t in tables:
        zh, en = _group_of(t["name"])
        t["group"], t["groupEn"] = zh, en

    checks = [
        {"name": "xG 覆盖", "nameEn": "xG coverage", "status": "ok",
         "note": f"官方 xG {counts.get('understat_xg', 0):,} 场", "noteEn": "official xG"},
        {"name": "缺失 xG", "nameEn": "Missing xG", "status": "warn",
         "note": f"{core['matches'] - counts.get('understat_xg', 0):,} 场无官方 xG",
         "noteEn": "no official xG"},
        {"name": "身价缺失", "nameEn": "Missing market value", "status": "warn",
         "note": f"{core['players'] - one('SELECT COUNT(*) n FROM players WHERE market_value IS NOT NULL')['n']:,} 名球员",
         "noteEn": "players without value"},
        {"name": "预测覆盖", "nameEn": "Prediction coverage", "status": "ok",
         "note": f"{counts.get('predictions', 0):,} 条 / {core['upcoming']:,} 场待赛",
         "noteEn": "predictions"},
        {"name": "转会数据", "nameEn": "Transfers", "status": "ok",
         "note": f"{counts.get('tm_transfers', 0):,} 笔（Transfermarkt）", "noteEn": "Transfermarkt"},
        {"name": "伤停数据", "nameEn": "Injuries", "status": "ok",
         "note": f"{counts.get('tm_player_injuries', 0):,} 条", "noteEn": "records"},
    ]

    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "dataNow": core["now"],
        "modules": modules,
        "trend": {"labels": [m["m"] for m in months], "values": [m["n"] for m in months],
                  "caption": f"{months[0]['m'] if months else ''} ~ {months[-1]['m'] if months else ''}",
                  "unit": "场", "unitEn": "matches"},
        "distribution": distribution,
        "pipeline": pipeline,
        "goalBands": bands,
        "models": models,
        "tableGroups": [{"group": _group_of(t["name"])[0], "groupEn": _group_of(t["name"])[1],
                         "name": t["name"], "rows": t["rows"]} for t in tables],
        "dbTables": {"total": core["tables"], "records": core["records"], "items": tables},
        "checks": checks,
        "counts": counts,
        "leagueStats": _league_cards(),
    }


# ============ 列表接口（分页） ============

def _page_meta(total: int, page: int, size: int) -> dict:
    return {"total": total, "page": page, "size": size, "pages": max(1, math.ceil(total / size))}


@router.get("/leagues")
def list_leagues():
    items = _league_cards()
    core = _core_counts()
    return {
        "items": items,
        # KPI 口径：比赛/球队按库内去重（不是各联赛求和），避免与首页数字打架
        "totals": {
            "leagues": len(items),
            "matches": core["matches"],
            "teams": core["teams"],
            "players": core["players"],
            "goalsPg": round(sum((i["goalsPg"] or 0) * (i["matches"] or 0) for i in items)
                             / max(1, sum(i["matches"] or 0 for i in items)), 2),
        },
    }


@router.get("/leagues/{league_id}")
def league_detail(league_id: int, season: str = "2627"):
    lg = one("SELECT * FROM leagues WHERE league_id=?", (league_id,))
    if not lg:
        raise HTTPException(status_code=404, detail="联赛不存在")
    standings = rows(
        "SELECT s.*, t.name, t.name_en, t.logo_url FROM standings s JOIN teams t ON t.team_id=s.team_id "
        "WHERE s.league_id=? AND s.season=? ORDER BY s.rank", (league_id, season))
    history = rows("SELECT * FROM league_stats WHERE league_id=? ORDER BY season", (league_id,))
    for h in history:
        h["seasonLabel"] = _season_label(h["season"])
    comps = _tm_competitions(lg)
    want = _season_code_to_tm(season)
    avail = _tm_seasons(comps)
    scorers_season = want if want and want in avail else (avail[0] if avail else "")
    scorers = []
    if scorers_season and comps:
        ph = ",".join("?" * len(comps))
        scorers = rows(
            "SELECT s.player_id, MAX(p.player_name) player_name, MAX(s.team_name) team_name,"
            "       MAX(s.competition_name) competition_name, SUM(s.goals) goals, SUM(s.assists) assists,"
            "       SUM(s.appearances) appearances, SUM(s.minutes) minutes, MAX(p.image_url) image_url "
            f"FROM tm_player_seasons s LEFT JOIN tm_players p ON p.player_id=s.player_id "
            f"WHERE s.competition_name IN ({ph}) AND s.season_name = ? "
            "GROUP BY s.player_id ORDER BY goals DESC LIMIT 10",
            tuple(comps + [scorers_season]))
    teams = rows(
        "SELECT tr.*, t.logo_url, t.elo_rating FROM team_radar tr JOIN teams t ON t.name=tr.team "
        "WHERE tr.league_id=? ORDER BY tr.ppg DESC", (league_id,))
    # 赛季口径 vs 全量口径：season 参数只作用于 matches/standings/league_stats，team_radar 是全量预计算表
    season_row = rows(f"{_MATCH_AGG} WHERE league_id=? AND season=?", (league_id, season))
    form = rows(f"{_MATCH_AGG} WHERE league_id=?", (league_id,))
    return {
        "league": {"id": lg["league_id"], "name": lg["name"], "nameEn": lg["name_en"],
                   "country": lg["country"], "countryEn": _COUNTRY_EN.get(lg["country"], lg["country"] or ""),
                   "season": _season_label(lg["season"])},
        "season": season,
        "seasons": [s["season"] for s in rows(
            "SELECT DISTINCT season FROM standings WHERE league_id=? ORDER BY season DESC", (league_id,))],
        "standings": standings,
        "history": history,
        "scorers": scorers,
        "scorersSeason": {"code": scorers_season, "label": _tm_season_label(scorers_season)},
        "teams": teams[:24],
        "teamsScope": "all-time",
        "summary": _season_summary(season_row[0] if season_row else {}),
        "seasonStats": next((r for r in rows(
            "SELECT * FROM league_stats WHERE league_id=? AND season=?", (league_id, season))), None),
        "allTime": _season_summary(form[0] if form else {}),
    }


TEAM_SORTS = {"elo": "t.elo_rating", "ppg": "tr.ppg", "xg": "tr.xg_pg", "xga": "tr.xga_pg",
              "value": "tr.squad_value", "age": "tr.avg_age", "goals": "tr.goals_pg",
              "matches": "tr.matches", "name": "tr.team"}


@router.get("/teams")
def list_teams(q: str = "", league: int | None = None, sort: str = "elo", dir: str = "desc",
               page: int = 1, size: int = 25):
    size = max(1, min(size, 200))
    page = max(1, page)
    where, params = ["1=1"], []
    if q:
        where.append("(tr.team LIKE ? OR t.name_en LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if league:
        where.append("tr.league_id = ?")
        params.append(league)
    w = " AND ".join(where)
    key = TEAM_SORTS.get(sort, "t.elo_rating")
    direction = "ASC" if dir.lower() == "asc" else "DESC"
    total = one(f"SELECT COUNT(*) n FROM team_radar tr JOIN teams t ON t.name = tr.team WHERE {w}", tuple(params))["n"]
    # 筛选范围内的全量口径（KPI 用；与分页无关，避免「当前页」口径误导）
    agg = one(
        f"SELECT AVG(tr.goals_pg) avg_goals, AVG(tr.conceded_pg) avg_conceded,"
        f"       SUM(tr.squad_value) squad_value, MAX(t.elo_rating) max_elo "
        f"FROM team_radar tr JOIN teams t ON t.name = tr.team WHERE {w}", tuple(params))
    top_elo = one(
        f"SELECT tr.team team, t.elo_rating elo FROM team_radar tr JOIN teams t ON t.name = tr.team "
        f"WHERE {w} AND t.elo_rating IS NOT NULL ORDER BY t.elo_rating DESC LIMIT 1", tuple(params))
    aggregates = {
        "scope": "filtered",
        "n": total,
        "avgGoalsPg": _r2(agg.get("avg_goals")),
        "avgConcededPg": _r2(agg.get("avg_conceded")),
        "maxElo": _r2(agg.get("max_elo"), 1),
        "maxEloTeam": (top_elo or {}).get("team"),
        "squadValue": agg.get("squad_value") or 0,
        "valueText": _fmt_value(agg.get("squad_value")),
    }
    items = rows(
        f"SELECT tr.*, t.team_id, t.name_en, t.logo_url, t.elo_rating, t.stadium, t.manager,"
        f"       l.name league_name, l.name_en league_name_en "
        f"FROM team_radar tr JOIN teams t ON t.name = tr.team "
        f"LEFT JOIN leagues l ON l.league_id = tr.league_id "
        f"WHERE {w} ORDER BY {key} {direction} NULLS LAST LIMIT ? OFFSET ?",
        tuple(params + [size, (page - 1) * size]))
    for t in items:
        t["valueText"] = _fmt_value(t.get("squad_value"))
        t["radar"] = {"attack": t.get("s_attack"), "defense": t.get("s_defense"),
                      "dominance": t.get("s_dominance"), "discipline": t.get("s_discipline"),
                      "value": t.get("s_value"), "experience": t.get("s_experience"),
                      "stability": t.get("s_stability")}
    top = rows(
        f"SELECT tr.*, t.name_en, t.team_id, t.logo_url, t.elo_rating,"
        f"       l.name league_name, l.name_en league_name_en "
        f"FROM team_radar tr JOIN teams t ON t.name = tr.team "
        f"LEFT JOIN leagues l ON l.league_id = tr.league_id "
        f"WHERE {w} ORDER BY {key} {direction} NULLS LAST LIMIT 5", tuple(params))
    for t in top:
        t["valueText"] = _fmt_value(t.get("squad_value"))
        t["radar"] = {"attack": t.get("s_attack"), "defense": t.get("s_defense"),
                      "dominance": t.get("s_dominance"), "discipline": t.get("s_discipline"),
                      "value": t.get("s_value"), "experience": t.get("s_experience"),
                      "stability": t.get("s_stability")}
    return {"items": items, "aggregates": aggregates, "top5": top, **_page_meta(total, page, size)}


PLAYER_SORTS = {"value": "p.market_value", "age": "p.age", "name": "p.name_en", "number": "p.number"}


@router.get("/players")
def list_players(q: str = "", group: str = "", team: int | None = None, league: int | None = None,
                 sort: str = "value", dir: str = "desc", page: int = 1, size: int = 30):
    size = max(1, min(size, 200))
    page = max(1, page)
    where, params = ["1=1"], []
    if q:
        where.append("(p.name LIKE ? OR p.name_en LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if team:
        where.append("p.team_id = ?")
        params.append(team)
    if league:
        where.append("t.league_id = ?")
        params.append(league)
    if group == "GK":
        where.append("(p.position LIKE '%Goalkeeper%' OR p.position LIKE '%Keeper%')")
    elif group == "DF":
        where.append("(p.position LIKE '%Defen%' OR p.position LIKE '%Back%')")
    elif group == "MF":
        where.append("(p.position LIKE '%Midfield%' OR p.position='Midfielder')")
    elif group == "FW":
        where.append("(p.position LIKE '%Attack%' OR p.position LIKE '%Forward%' OR p.position LIKE '%Wing%' "
                     "OR p.position='Striker')")
    w = " AND ".join(where)
    key = PLAYER_SORTS.get(sort, "p.market_value")
    direction = "ASC" if dir.lower() == "asc" else "DESC"
    base = (f"FROM players p LEFT JOIN teams t ON t.team_id = p.team_id "
            f"LEFT JOIN leagues l ON l.league_id = t.league_id WHERE {w}")
    total = one(f"SELECT COUNT(*) n {base}", tuple(params))["n"]
    # 筛选范围内的全量口径（KPI 用；与分页无关）
    agg = one(
        f"SELECT SUM(CASE WHEN p.market_value > 0 THEN 1 ELSE 0 END) with_value,"
        f"       AVG(CASE WHEN p.age BETWEEN 15 AND 45 THEN p.age END) avg_age,"
        f"       SUM(CASE WHEN p.age IS NOT NULL AND (p.age < 15 OR p.age > 45) THEN 1 ELSE 0 END) age_dirty,"
        f"       MAX(CASE WHEN p.market_value > 0 THEN p.market_value END) top_value {base}", tuple(params))
    top_row = one(
        f"SELECT p.name, p.name_en, p.market_value {base} "
        f"AND p.market_value > 0 ORDER BY p.market_value DESC LIMIT 1", tuple(params))
    aggregates = {
        "scope": "filtered",
        "n": total,
        "withValue": agg.get("with_value") or 0,
        "avgAge": _r2(agg.get("avg_age"), 1),
        "ageSampleDirty": agg.get("age_dirty") or 0,
        "topValue": agg.get("top_value"),
        "topValueText": _fmt_value(agg.get("top_value")),
        "topValueName": (top_row or {}).get("name"),
        "topValueNameEn": (top_row or {}).get("name_en"),
    }
    items = rows(
        f"SELECT p.player_id, p.name, p.name_en, p.position, p.nationality, p.age, p.height, p.number,"
        f"       p.market_value, p.photo_url, p.foot, t.name team, t.name_en team_en, t.logo_url team_logo,"
        f"       t.team_id, l.name league, l.name_en league_en "
        f"{base} ORDER BY {key} {direction} NULLS LAST LIMIT ? OFFSET ?",
        tuple(params + [size, (page - 1) * size]))
    for p in items:
        p["group"] = _pos_group(p.get("position"))
        p["valueText"] = _fmt_value(p.get("market_value"))
    return {"items": items, "aggregates": aggregates, **_page_meta(total, page, size)}


@router.get("/teams/{team_id}")
def team_detail(team_id: int):
    t = one("SELECT t.*, l.name lg, l.name_en lg_en FROM teams t "
            "LEFT JOIN leagues l ON l.league_id=t.league_id WHERE t.team_id=?", (team_id,))
    if not t:
        raise HTTPException(status_code=404, detail="球队不存在")
    radar = one("SELECT * FROM team_radar WHERE team_id=?", (team_id,))
    standing = one("SELECT * FROM standings WHERE team_id=? ORDER BY season DESC LIMIT 1", (team_id,))
    seasons = rows(
        "SELECT m.season, COUNT(*) played, SUM(m.status='FT') ft,"
        "       SUM(CASE WHEN (m.home_team_id=? AND m.home_goals>m.away_goals)"
        "                 OR (m.away_team_id=? AND m.away_goals>m.home_goals) THEN 1 ELSE 0 END) won,"
        "       SUM(CASE WHEN m.status='FT' AND m.home_goals=m.away_goals THEN 1 ELSE 0 END) drawn,"
        "       SUM(CASE WHEN m.status='FT' AND ((m.home_team_id=? AND m.home_goals<m.away_goals)"
        "                 OR (m.away_team_id=? AND m.away_goals<m.home_goals)) THEN 1 ELSE 0 END) lost,"
        "       SUM(CASE WHEN m.home_team_id=? THEN m.home_goals ELSE m.away_goals END) goals_for,"
        "       SUM(CASE WHEN m.home_team_id=? THEN m.away_goals ELSE m.home_goals END) goals_against,"
        "       AVG(CASE WHEN m.home_team_id=? THEN m.home_xg ELSE m.away_xg END) xg_pg "
        "FROM matches m WHERE m.home_team_id=? OR m.away_team_id=? "
        "GROUP BY m.season ORDER BY m.season DESC LIMIT 6",
        (team_id,) * 9)
    out_seasons = []
    for s in seasons:
        out_seasons.append({
            "season": _season_label(s["season"]), "seasonCode": s["season"],
            "played": s["played"], "ft": s["ft"], "won": s["won"], "drawn": s["drawn"], "lost": s["lost"],
            "goalsFor": s["goals_for"], "goalsAgainst": s["goals_against"], "xgPg": _r2(s["xg_pg"]),
        })
    squad = rows(
        "SELECT player_id, name, name_en, position, age, number, market_value, photo_url, foot "
        "FROM players WHERE team_id=? ORDER BY (market_value IS NULL), market_value DESC LIMIT 12", (team_id,))
    for p in squad:
        p["group"] = _pos_group(p.get("position"))
        p["valueText"] = _fmt_value(p.get("market_value"))
    groups = one("SELECT SUM(group_name='GK') gk, SUM(group_name='DF') df,"
                 "       SUM(group_name='MF') mf, SUM(group_name='FW') fw, COUNT(*) n FROM ("
                 "  SELECT CASE"
                 "    WHEN position LIKE '%Goalkeeper%' OR position LIKE '%Keeper%' THEN 'GK'"
                 "    WHEN position LIKE '%Defen%' OR position LIKE '%Back%' THEN 'DF'"
                 "    WHEN position LIKE '%Midfield%' OR position='Midfielder' THEN 'MF'"
                 "    WHEN position LIKE '%Attack%' OR position LIKE '%Forward%' OR position LIKE '%Wing%'"
                 "         OR position='Striker' THEN 'FW' ELSE 'GK' END AS group_name"
                 "  FROM players WHERE team_id=?)", (team_id,)) or {}
    return {
        "team": {"id": t["team_id"], "name": t["name"], "nameEn": t["name_en"],
                 "shortName": t.get("short_name"), "logo": t["logo_url"], "elo": _r2(t.get("elo_rating"), 1),
                 "stadium": t.get("stadium"), "capacity": t.get("capacity"), "manager": t.get("manager"),
                 "founded": t.get("founded"),
                 "league": {"id": t["league_id"], "name": t["lg"], "nameEn": t["lg_en"]}},
        "radar": None if not radar else {
            "attack": radar.get("s_attack"), "defense": radar.get("s_defense"),
            "dominance": radar.get("s_dominance"), "discipline": radar.get("s_discipline"),
            "value": radar.get("s_value"), "experience": radar.get("s_experience"),
            "stability": radar.get("s_stability")},
        "metrics": None if not radar else {
            "matches": radar.get("matches"), "goalsPg": _r2(radar.get("goals_pg")),
            "concededPg": _r2(radar.get("conceded_pg")), "shotsPg": _r2(radar.get("shots_pg")),
            "shotDiffPg": _r2(radar.get("shot_diff_pg")), "cardsPg": _r2(radar.get("cards_pg")),
            "xgPg": _r2(radar.get("xg_pg")), "xgaPg": _r2(radar.get("xga_pg")),
            "ppg": _r2(radar.get("ppg")), "avgAge": _r2(radar.get("avg_age"), 1),
            "squadValue": radar.get("squad_value"), "valueText": _fmt_value(radar.get("squad_value")),
        },
        "standing": standing,
        "seasons": out_seasons,
        "recent": _form_rows(team_id, 8),
        "upcoming": rows(
            "SELECT m.match_id, m.date, m.status, l.name lg, l.name_en lg_en,"
            "       th.name h, th.name_en h_en, th.logo_url h_logo, th.team_id h_id,"
            "       ta.name a, ta.name_en a_en, ta.logo_url a_logo, ta.team_id a_id,"
            "       p.pred_home_win, p.pred_draw, p.pred_away_win, p.pred_result, p.model_version "
            "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
            "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
            "LEFT JOIN predictions p ON p.match_id=m.match_id "
            "WHERE m.status='NS' AND (m.home_team_id=? OR m.away_team_id=?) ORDER BY m.date LIMIT 5",
            (team_id, team_id)),
        "squad": squad,
        "squadGroups": {"GK": groups.get("gk") or 0, "DF": groups.get("df") or 0,
                        "MF": groups.get("mf") or 0, "FW": groups.get("fw") or 0,
                        "total": groups.get("n") or 0},
    }


@router.get("/players/{player_id}")
def player_detail(player_id: int):
    p = one("SELECT p.*, t.name team, t.name_en team_en, t.logo_url team_logo, t.team_id, "
            "l.name league, l.name_en league_en FROM players p "
            "LEFT JOIN teams t ON t.team_id=p.team_id LEFT JOIN leagues l ON l.league_id=t.league_id "
            "WHERE p.player_id=?", (player_id,))
    if not p:
        raise HTTPException(status_code=404, detail="球员不存在")
    radar = one("SELECT * FROM player_radar WHERE player_id=?", (player_id,))
    seasons = rows("SELECT * FROM tm_player_seasons WHERE player_id=(SELECT tm_player_id FROM players WHERE player_id=?) "
                   "ORDER BY season_start DESC LIMIT 12", (player_id,))
    return {"player": p, "radar": radar, "seasons": seasons}


MATCH_SORTS = {"date": "m.date", "goals": "(m.home_goals+m.away_goals)", "xg": "(m.home_xg+m.away_xg)",
               "league": "l.name"}

_MATCH_SELECT = (
    "SELECT m.match_id, m.date, m.season, m.matchday, m.status, m.home_goals, m.away_goals,"
    "       m.home_xg, m.away_xg, l.name lg, l.name_en lg_en,"
    "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo")


def _days_apart(d1: Any, d2: Any) -> int:
    try:
        a = _dt.datetime.fromisoformat(str(d1).replace(" ", "T"))
        b = _dt.datetime.fromisoformat(str(d2).replace(" ", "T"))
        return abs((a - b).days)
    except Exception:
        return 999


def _has_xg(r: dict) -> bool:
    return (r.get("home_xg") is not None) or (r.get("away_xg") is not None)


def _form_rows(team_id: int, limit: int = 6) -> list[dict]:
    """球队最近若干场已完赛（跨赛事），带该队视角的 W/D/L。

    库内存在「同一场比赛被两次入库」的行（见 scripts/dup_matches.py）：同对阵、同比分、
    相隔 ≤3 天。这里按此规则去重，并优先保留带 xG 的那条，避免近期战绩里同一场出现两次。
    """
    rs = rows(
        "SELECT m.match_id, m.date, m.season, m.home_goals, m.away_goals, m.home_team_id, m.away_team_id,"
        "       m.home_xg, m.away_xg, l.name lg, l.name_en lg_en,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "WHERE m.status='FT' AND (m.home_team_id=? OR m.away_team_id=?) "
        "ORDER BY m.date DESC LIMIT ?", (team_id, team_id, max(limit * 3, 12)))
    out: list[dict] = []
    for r in rs:
        home = r["home_team_id"] == team_id
        gf = r["home_goals"] if home else r["away_goals"]
        ga = r["away_goals"] if home else r["home_goals"]
        res = "D" if gf == ga else ("W" if gf > ga else "L")
        row = {**r, "isHome": home, "gf": gf, "ga": ga, "result": res}
        dup_idx = None
        for i, prev in enumerate(out):
            if (prev["home_team_id"] == r["home_team_id"] and prev["away_team_id"] == r["away_team_id"]
                    and prev["home_goals"] == r["home_goals"] and prev["away_goals"] == r["away_goals"]
                    and _days_apart(prev["date"], r["date"]) <= 3):
                dup_idx = i
                break
        if dup_idx is None:
            out.append(row)
        elif _has_xg(row) and not _has_xg(out[dup_idx]):
            out[dup_idx] = row
        if len(out) >= limit:
            break
    return out[:limit]


@router.get("/matches/{match_id}")
def match_detail(match_id: int):
    m = one(
        "SELECT m.*, l.name lg, l.name_en lg_en, l.country country,"
        "       th.name h, th.name_en h_en, th.logo_url h_logo, th.stadium h_stadium,"
        "       th.elo_rating h_elo, th.manager h_manager,"
        "       ta.name a, ta.name_en a_en, ta.logo_url a_logo, ta.stadium a_stadium,"
        "       ta.elo_rating a_elo, ta.manager a_manager "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "WHERE m.match_id=?", (match_id,))
    if not m:
        raise HTTPException(status_code=404, detail="比赛不存在")
    hid, aid = m["home_team_id"], m["away_team_id"]

    def _standing(tid: int):
        return one("SELECT rank, played, won, draw, lost, goals_for, goals_against, goal_diff, points, form "
                   "FROM standings WHERE team_id=? AND season=? AND league_id=?",
                   (tid, m["season"], m["league_id"])) or None

    pred = one("SELECT * FROM predictions WHERE match_id=? ORDER BY pred_id DESC LIMIT 1", (match_id,))
    pred_out = None
    if pred:
        segs = []
        for key, label, label_en, field in (("home", "主胜", "Home", "pred_home_win"),
                                            ("draw", "平局", "Draw", "pred_draw"),
                                            ("away", "客胜", "Away", "pred_away_win")):
            segs.append({"key": key, "label": label, "labelEn": label_en,
                         "pct": round((pred.get(field) or 0) * 100, 1)})
        top = max(segs, key=lambda s: s["pct"])
        pred_out = {
            "predId": pred["pred_id"], "model": pred["model_version"],
            "segments": segs, "pick": pred["pred_result"], "pickLabel": top["label"],
            "pickLabelEn": top["labelEn"], "conf": top["pct"],
            "actual": pred["actual_result"], "hit": pred["hit"],
            "isBacktest": pred["is_backtest"], "createdAt": pred["created_at"],
        }

    h2h = []
    meet = rows(
        "SELECT m.match_id, m.date, m.home_goals, m.away_goals, m.home_team_id, m.away_team_id,"
        "       l.name lg, l.name_en lg_en, th.name h, ta.name a "
        "FROM matches m JOIN leagues l ON l.league_id=m.league_id "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        "WHERE m.status='FT' AND ((m.home_team_id=? AND m.away_team_id=?) OR (m.home_team_id=? AND m.away_team_id=?)) "
        "  AND m.match_id <> ? "
        "ORDER BY m.date DESC LIMIT 8", (hid, aid, aid, hid, match_id))
    hw = dw = aw = 0
    for r in meet:
        # 以本场主队（hid）视角计胜负
        gf = r["home_goals"] if r["home_team_id"] == hid else r["away_goals"]
        ga = r["away_goals"] if r["home_team_id"] == hid else r["home_goals"]
        if gf == ga:
            dw += 1
            res = "D"
        elif gf > ga:
            hw += 1
            res = "W"
        else:
            aw += 1
            res = "L"
        h2h.append({**r, "resultForHome": res})
    stats = []
    for label, label_en, hk, ak in (("射门", "Shots", "home_shots", "away_shots"),
                                    ("射正", "On target", "home_sot", "away_sot"),
                                    ("角球", "Corners", "home_corners", "away_corners"),
                                    ("犯规", "Fouls", "home_fouls", "away_fouls"),
                                    ("黄牌", "Yellow", "home_yellow", "away_yellow"),
                                    ("红牌", "Red", "home_red", "away_red")):
        hv, av = m.get(hk), m.get(ak)
        if hv is None and av is None:
            continue
        stats.append({"label": label, "labelEn": label_en, "home": hv, "away": av})
    return {
        "matchId": m["match_id"], "date": m["date"], "status": m["status"],
        "season": _season_label(m["season"]), "seasonCode": m["season"], "matchday": m["matchday"],
        "league": {"id": m["league_id"], "name": m["lg"], "nameEn": m["lg_en"],
                   "country": m["country"], "countryEn": _COUNTRY_EN.get(m["country"], m["country"])},
        "home": {"id": hid, "name": m["h"], "nameEn": m["h_en"], "logo": m["h_logo"],
                 "stadium": m["h_stadium"], "manager": m["h_manager"], "elo": _r2(m["h_elo"], 1),
                 "standing": _standing(hid), "form": _form_rows(hid, 5)},
        "away": {"id": aid, "name": m["a"], "nameEn": m["a_en"], "logo": m["a_logo"],
                 "stadium": m["a_stadium"], "manager": m["a_manager"], "elo": _r2(m["a_elo"], 1),
                 "standing": _standing(aid), "form": _form_rows(aid, 5)},
        "score": {"home": m["home_goals"], "away": m["away_goals"],
                  "htHome": m["ht_home"], "htAway": m["ht_away"]},
        "xg": {"home": _r2(m["home_xg"]), "away": _r2(m["away_xg"]),
               "proxyHome": _r2(m["home_xg_proxy"]), "proxyAway": _r2(m["away_xg_proxy"])},
        "stats": stats,
        "prediction": pred_out,
        "h2h": {"items": h2h, "meetings": len(h2h), "homeWins": hw, "draws": dw, "awayWins": aw},
    }


@router.get("/matches")
def list_matches(q: str = "", league: int | None = None, season: str = "", status: str = "",
                 page: int = 1, size: int = 30, sort: str = "date", dir: str = "desc"):
    size = max(1, min(size, 200))
    page = max(1, page)
    where, params = ["1=1"], []
    if q:
        where.append("(th.name LIKE ? OR ta.name LIKE ?)")
        params += [f"%{q}%", f"%{q}%"]
    if league:
        where.append("m.league_id = ?")
        params.append(league)
    if season:
        where.append("m.season = ?")
        params.append(season)
    if status:
        where.append("m.status = ?")
        params.append(status)
    w = " AND ".join(where)
    key = MATCH_SORTS.get(sort, "m.date")
    direction = "ASC" if dir.lower() == "asc" else "DESC"
    base = (f"FROM matches m JOIN leagues l ON l.league_id=m.league_id "
            f"JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
            f"LEFT JOIN predictions p ON p.match_id=m.match_id WHERE {w}")
    total = one(f"SELECT COUNT(*) n {base}", tuple(params))["n"]
    items = rows(
        f"SELECT m.match_id, m.date, m.season, m.matchday, m.status, m.home_goals, m.away_goals,"
        f"       m.home_xg, m.away_xg, l.name lg, l.name_en lg_en,"
        f"       th.name h, th.name_en h_en, th.logo_url h_logo, ta.name a, ta.name_en a_en, ta.logo_url a_logo,"
        f"       p.pred_result, p.pred_home_win, p.pred_draw, p.pred_away_win, p.hit, p.model_version "
        f"{base} ORDER BY {key} {direction} LIMIT ? OFFSET ?", tuple(params + [size, (page - 1) * size]))
    stats = one(
        "SELECT SUM(status='FT') ft, SUM(home_goals>away_goals) hw, SUM(home_goals=away_goals) dr,"
        "       SUM(home_goals<away_goals) aw, AVG(home_goals+away_goals) goals_pg,"
        "       COUNT(*) n FROM matches m "
        "JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id "
        f"WHERE {w} AND m.status='FT'", tuple(params))
    return {"items": items, "stats": stats, **_page_meta(total, page, size)}


@router.get("/predictions")
def list_predictions(model: str = "", result: str = "", page: int = 1, size: int = 25):
    size = max(1, min(size, 200))
    page = max(1, page)
    where, params = ["1=1"], []
    if model:
        where.append("p.model_version = ?")
        params.append(model)
    if result:
        where.append("p.pred_result = ?")
        params.append(result)
    w = " AND ".join(where)
    base = (f"FROM predictions p JOIN matches m ON m.match_id=p.match_id "
            f"JOIN leagues l ON l.league_id=m.league_id "
            f"JOIN teams th ON th.team_id=m.home_team_id JOIN teams ta ON ta.team_id=m.away_team_id WHERE {w}")
    total = one(f"SELECT COUNT(*) n {base}", tuple(params))["n"]
    items = rows(
        f"SELECT p.pred_id, p.match_id, p.model_version, p.pred_home_win, p.pred_draw, p.pred_away_win,"
        f"       p.pred_result, p.actual_result, p.hit, p.is_backtest, p.created_at,"
        f"       m.date, l.name lg, l.name_en lg_en, th.name h, th.logo_url h_logo,"
        f"       ta.name a, ta.logo_url a_logo, m.home_goals, m.away_goals, m.status "
        f"{base} ORDER BY m.date DESC LIMIT ? OFFSET ?", tuple(params + [size, (page - 1) * size]))
    models = rows("SELECT * FROM model_metrics ORDER BY acc DESC")
    for i, mm in enumerate(models):
        mm["status"] = "production" if i == 0 else ("challenger" if i <= 2 else "baseline")
    hit = one("SELECT COUNT(*) n, SUM(hit) h FROM predictions WHERE actual_result IS NOT NULL AND hit IS NOT NULL")
    return {
        "items": items,
        "models": models,
        "calibration": rows("SELECT * FROM model_calibration ORDER BY outcome, predicted"),
        "confusion": rows("SELECT * FROM model_confusion"),
        "featureImportance": rows("SELECT * FROM feature_importance ORDER BY importance DESC LIMIT 16"),
        "versions": rows("SELECT model_version, COUNT(*) n FROM predictions GROUP BY model_version ORDER BY n DESC"),
        "hitRate": round((hit.get("h") or 0) / hit["n"] * 100, 1) if hit.get("n") else 0,
        "evaluated": hit.get("n") or 0,
        **_page_meta(total, page, size),
    }


@router.get("/models")
def model_registry():
    models = rows("SELECT * FROM model_metrics ORDER BY acc DESC")
    for i, m in enumerate(models):
        m["status"] = "production" if i == 0 else ("challenger" if i <= 2 else "baseline")
    return {
        "items": models,
        "calibration": rows("SELECT * FROM model_calibration ORDER BY outcome, predicted"),
        "confusion": rows("SELECT * FROM model_confusion"),
        "featureImportance": rows("SELECT * FROM feature_importance ORDER BY importance DESC LIMIT 20"),
    }


@router.get("/transfers")
def list_transfers(q: str = "", season: str = "", page: int = 1, size: int = 30, min_fee: int = 0):
    size = max(1, min(size, 200))
    page = max(1, page)
    where, params = ["1=1"], []
    if q:
        where.append("(player_name LIKE ? OR from_team_name LIKE ? OR to_team_name LIKE ?)")
        params += [f"%{q}%", f"%{q}%", f"%{q}%"]
    if season:
        where.append("season_name = ?")
        params.append(season)
    if min_fee:
        where.append("CAST(NULLIF(transfer_fee,'') AS INTEGER) >= ?")
        params.append(min_fee)
    w = " AND ".join(where)
    total = one(f"SELECT COUNT(*) n FROM tm_transfers WHERE {w}", tuple(params))["n"]
    items = rows(
        f"SELECT player_id, player_name, season_name, transfer_date, from_team_name, to_team_name,"
        f"       transfer_type, value_at_transfer, transfer_fee FROM tm_transfers WHERE {w} "
        f"ORDER BY CAST(NULLIF(transfer_fee,'') AS INTEGER) DESC, transfer_date DESC LIMIT ? OFFSET ?",
        tuple(params + [size, (page - 1) * size]))
    return {
        "items": items,
        # 用真实日期排序（season_name 字符串排序会把 '99/00' 排到最前）
        "seasons": [r["season_name"] for r in rows(
            "SELECT season_name, MAX(transfer_date) d FROM tm_transfers "
            "GROUP BY season_name ORDER BY d DESC LIMIT 20")],
        "top": rows(
            "SELECT player_name, from_team_name, to_team_name, transfer_fee, season_name, transfer_date "
            "FROM tm_transfers WHERE transfer_fee <> '' AND CAST(transfer_fee AS INTEGER) > 0 "
            "ORDER BY CAST(transfer_fee AS INTEGER) DESC LIMIT 10"),
        **_page_meta(total, page, size),
    }


@router.get("/reports")
def reports():
    core = _core_counts()
    counts = {t["name"]: t["rows"] for t in table_counts()}
    months = _month_series(36)
    leagues = _league_cards()
    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "core": core,
        "tables": sorted(table_counts(), key=lambda t: -t["rows"]),
        "months": months,
        "leagues": leagues,
        "sources": [
            {"name": "football-data.org", "nameEn": "football-data.org", "records": counts.get("matches", 0),
             "detail": "赛程 · 比分 · 积分榜", "detailEn": "fixtures, results, standings"},
            {"name": "Understat（官方 xG）", "nameEn": "Understat (official xG)", "records": counts.get("understat_xg", 0),
             "detail": "五大联赛 xG", "detailEn": "xG for top 5 leagues"},
            {"name": "Transfermarkt", "nameEn": "Transfermarkt", "records": counts.get("tm_player_market_value", 0),
             "detail": "身价走势 · 转会 · 伤停", "detailEn": "market value, transfers, injuries"},
            {"name": "球小智", "nameEn": "QiuXiaoZhi", "records": counts.get("transfers", 0),
             "detail": "中文转会与赔率", "detailEn": "Chinese transfers"},
            {"name": "API-Football", "nameEn": "API-Football",
             "records": sum(v for k, v in counts.items() if k.startswith("af_")),
             "detail": "备用事件源（当前为空）", "detailEn": "fallback (empty)"},
        ],
        "quality": {
            "matchWithXg": counts.get("understat_xg", 0),
            "matchTotal": core["matches"],
            "playerWithValue": one("SELECT COUNT(*) n FROM players WHERE market_value IS NOT NULL")["n"],
            "playerTotal": core["players"],
            "injuries": counts.get("tm_player_injuries", 0),
            "marketValueRows": counts.get("tm_player_market_value", 0),
        },
    }


@router.get("/live")
def live():
    """实时比分：数据源当前无实时推送，返回最近完赛与待赛"""
    recent = _recent_matches(12)
    upcoming = _next_fixtures(10)
    last_day = (_core_counts()["now"] or "")[:10]
    return {
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "source": "football-data.org",
        "wsEndpoint": "/ws/live-scores",
        "recent": recent,
        "upcoming": upcoming,
        "lastDay": last_day,
        "lastDayCount": one("SELECT COUNT(*) n FROM matches WHERE substr(date,1,10)=?", (last_day,))["n"],
    }


# ============ 队徽代理（离线可用 + 磁盘缓存） ============

_PLACEHOLDER_CREST = (
    '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64">'
    '<circle cx="32" cy="32" r="31" fill="#EDE7D9" stroke="#DCD5C4" stroke-width="2"/>'
    '<text x="32" y="43" font-family="Inter, Segoe UI, Arial, sans-serif" font-size="27"'
    ' font-weight="600" text-anchor="middle" fill="#948D7C">{ch}</text></svg>'
)


def _placeholder_crest(team_id: int, lang: str = "zh") -> Response:
    """没有队徽的球队 → 返回一枚字母占位徽（200），避免前端出现破图。"""
    r = one("SELECT name, name_en FROM teams WHERE team_id=?", (team_id,)) or {}
    name = (r.get("name_en") if lang == "en" else r.get("name")) or r.get("name") or r.get("name_en") or "?"
    ch = "".join(c for c in str(name) if c.isalnum())[:2].upper() or "?"
    body = _PLACEHOLDER_CREST.replace("{ch}", ch)
    return Response(content=body.encode(), media_type="image/svg+xml",
                    headers={"Cache-Control": "public, max-age=604800"})


# ============ 登录页公开信息 ============

@router.get("/public/summary", summary="登录页用: 品牌与数据规模(公开)")
def public_summary():
    """未登录状态下使用：只给品牌名与规模数字，不含任何比赛/球队/球员明细。

    放在 /api/ui/public/* 下 —— 见 require_ui_login 的放行规则。
    """
    core = _core_counts()
    best = _best_model()
    return {
        "brand": {"name": "FootballAI", "sub": "足球数据分析与 AI 预测系统",
                  "subEn": "Football analytics & AI prediction"},
        "dataNow": core["now"],
        "generatedAt": time.strftime("%Y-%m-%d %H:%M:%S"),
        "matches": core["matches"], "finished": core["finished"], "upcoming": core["upcoming"],
        "players": core["players"], "teams": core["teams"], "leagues": core["leagues"],
        "accuracy": best.get("acc", 0), "model": best.get("model", ""),
        "accuracySamples": best.get("test_n", 0),
    }


@router.get("/logo/{team_id}")
def team_logo(team_id: int):
    r = one("SELECT logo_url FROM teams WHERE team_id=?", (team_id,))
    url = (r or {}).get("logo_url")
    if not url:
        return _placeholder_crest(team_id)
    CREST_DIR.mkdir(parents=True, exist_ok=True)
    suffix = Path(url).suffix or ".png"
    path = CREST_DIR / f"{team_id}{suffix}"
    if not path.exists():
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=8) as resp:
                path.write_bytes(resp.read())
        except Exception:  # 网络不可用时退回占位徽（原来是 502 → 前端破图）
            return _placeholder_crest(team_id)
    media = {"png": "image/png", "svg": "image/svg+xml", "jpg": "image/jpeg",
             "jpeg": "image/jpeg", "webp": "image/webp"}.get(suffix.lstrip(".").lower(), "image/png")
    return Response(content=path.read_bytes(), media_type=media,
                    headers={"Cache-Control": "public, max-age=604800"})
