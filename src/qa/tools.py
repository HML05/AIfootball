"""问答编排用的结构化工具 —— 纯函数, 不依赖 langchain。

设计要点（见 docs/智能问答说明.md）:
  * 只查 SQLite 主库, 所有数字都来自库里, 不做任何推测;
  * 每个工具回传 sources（表名 + 主键 + 前端可跳转路由）, 供答案做引用溯源;
  * 统一返回结构 {"tool","ok","summary","data","sources"}, 可直接 JSON 序列化。

老的 src/agent/tools.py 是 langchain @tool 版本（且把 market_value 当「万欧元」打印, 是错的）,
本模块是它的替代实现: 同样的六个能力, 但纯函数、可单测、可被 /api/ui/ask 直接调用。
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from src.search.indexer import load_aliases, main_db_path

# ---------------------------------------------------------------- 基础设施


def _connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{main_db_path()}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _rows(con: sqlite3.Connection, sql: str, params: tuple = ()) -> list[dict]:
    return [dict(r) for r in con.execute(sql, params).fetchall()]


def _one(con: sqlite3.Connection, sql: str, params: tuple = ()) -> dict | None:
    r = con.execute(sql, params).fetchone()
    return dict(r) if r else None


def money(v: Any) -> str:
    """market_value 是原始欧元（如 10000000.0）, 统一按中文习惯格式化。"""
    try:
        x = float(v)
    except (TypeError, ValueError):
        return "—"
    if x <= 0:
        return "—"
    if x >= 1e8:
        return f"{x / 1e8:.2f} 亿欧"
    if x >= 1e4:
        return f"{x / 1e4:.0f} 万欧"
    return f"{x:.0f} 欧"


def season_label(code: Any) -> str:
    """赛季码 '2627' / '2122' → '2026/27' / '2021/22'。"""
    s = str(code or "")
    if len(s) == 4 and s.isdigit():
        return f"20{s[:2]}/{s[2:]}"
    return s or "—"


def _int(v: Any) -> str:
    """player_radar 里的出场数/分钟等是浮点（55.0）, 显示时取整；缺失给 —。"""
    try:
        return str(int(round(float(v))))
    except (TypeError, ValueError):
        return "—"


def _round(v: Any, nd: int = 2) -> str:
    """小数字段（每90分钟参与进球等）保留 2 位, 去掉多余的 0。"""
    try:
        return f"{round(float(v), nd):g}"
    except (TypeError, ValueError):
        return "—"


def _ok(tool: str, summary: str, data: dict, sources: list[dict]) -> dict:
    return {"tool": tool, "ok": True, "summary": summary, "data": data, "sources": sources}


def _fail(tool: str, reason: str) -> dict:
    return {"tool": tool, "ok": False, "summary": reason, "data": {}, "sources": []}


def _days(a: Any, b: Any) -> int:
    """两个日期字符串相差几天（解析失败返回 999）。"""
    from datetime import datetime
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return abs((datetime.strptime(str(a)[:19], fmt) - datetime.strptime(str(b)[:19], fmt)).days)
        except ValueError:
            continue
    return 999


def _dedupe(rows: list[dict], window: int = 3) -> list[dict]:
    """比赛表里存在同一场次被采集成两条（日期差 1 天、比分相同）的重复行。

    展示"近 N 场"时必须折叠, 否则会出现「同一天对同一对手、同样比分」重复两遍。
    判定: 相同主客队 + 相同比分 + 日期相差 <= window 天 → 视为同一条。
    """
    out: list[dict] = []
    for r in rows:
        dup = False
        for k in out:
            if (k["home_team_id"] == r["home_team_id"] and k["away_team_id"] == r["away_team_id"]
                    and k["home_goals"] == r["home_goals"] and k["away_goals"] == r["away_goals"]
                    and _days(k["date"], r["date"]) <= window):
                dup = True
                break
        if not dup:
            out.append(r)
    return out


# ---------------------------------------------------------------- 名称解析

_TEAM_CACHE: list[dict] | None = None
_PLAYER_CACHE: list[dict] | None = None
_LEAGUE_CACHE: list[dict] | None = None


def teams_index() -> list[dict]:
    """全部球队 + 中文别名, 用于把「皇马」「Real Madrid」都解析到同一支球队。"""
    global _TEAM_CACHE
    if _TEAM_CACHE is None:
        aliases = load_aliases()
        with _connect() as con:
            rows = _rows(con, """
                SELECT t.team_id, t.name, t.name_en, t.short_name, t.league_id, t.elo_rating,
                       l.name AS league_name, l.name_en AS league_name_en
                FROM teams t LEFT JOIN leagues l ON l.league_id = t.league_id
            """)
        for r in rows:
            names: list[str] = []
            for key in (r.get("name"), r.get("name_en")):
                if key and key in aliases:
                    names.extend(aliases[key])
            r["alias"] = names
            r["names"] = [x for x in [r.get("name"), r.get("name_en"), r.get("short_name"), *names] if x]
        _TEAM_CACHE = rows
    return _TEAM_CACHE


def players_index() -> list[dict]:
    global _PLAYER_CACHE
    if _PLAYER_CACHE is None:
        with _connect() as con:
            _PLAYER_CACHE = _rows(con, """
                SELECT p.player_id, p.name, p.name_en, p.position, p.team_id, t.name AS team_name
                FROM players p LEFT JOIN teams t ON t.team_id = p.team_id
            """)
    return _PLAYER_CACHE


def leagues_index() -> list[dict]:
    global _LEAGUE_CACHE
    if _LEAGUE_CACHE is None:
        with _connect() as con:
            _LEAGUE_CACHE = _rows(con, "SELECT league_id, name, name_en, country, season FROM leagues")
    return _LEAGUE_CACHE


def _match_names(cands: list[dict], ref: Any, keys: tuple[str, ...]) -> list[dict]:
    """先精确（忽略大小写）再包含匹配。"""
    if isinstance(ref, int) or (isinstance(ref, str) and ref.isdigit()):
        rid = int(ref)
        for c in cands:
            if c.get("team_id") == rid or c.get("player_id") == rid or c.get("league_id") == rid:
                return [c]
    text = str(ref or "").strip().lower()
    if not text:
        return []
    exact = [c for c in cands if any(str(c.get(k) or "").strip().lower() == text for k in keys)]
    if exact:
        return exact[:3]
    pool: list[dict] = []
    for c in cands:
        names = c.get("names") if keys == ("names",) else [c.get(k) for k in keys] + list(c.get("alias") or [])
        for n in names:
            n = str(n or "").strip().lower()
            if n and (n in text or text in n):
                pool.append(c)
                break
    return pool[:3]


def find_team(ref: Any) -> dict | None:
    hits = _match_names(teams_index(), ref, ("name", "name_en", "short_name", "alias"))
    return hits[0] if hits else None


def find_player(ref: Any) -> dict | None:
    hits = _match_names(players_index(), ref, ("name", "name_en"))
    return hits[0] if hits else None


def find_league(ref: Any) -> dict | None:
    hits = _match_names(leagues_index(), ref, ("name", "name_en"))
    return hits[0] if hits else None


# ---------------------------------------------------------------- 工具 1: 球队资料


def team_info(team: Any) -> dict:
    t = find_team(team)
    if not t:
        return _fail("team_info", f"库里没有找到球队「{team}」")
    with _connect() as con:
        squad = _one(con, """
            SELECT COUNT(*) AS n, COALESCE(SUM(market_value), 0) AS value_total,
                   ROUND(AVG(age), 1) AS age_avg
            FROM players WHERE team_id = ?
        """, (t["team_id"],))
        st = _one(con, """
            SELECT season, rank, played, won, draw, lost, goals_for, goals_against, points, form
            FROM standings WHERE team_id = ? ORDER BY season DESC LIMIT 1
        """, (t["team_id"],))
    parts = [f"{t['name']}（{t.get('league_name') or '—'}）"]
    if t.get("name_en"):
        parts.append(f"英文名 {t['name_en']}")
    if t.get("manager"):
        parts.append(f"主教练 {t['manager']}")
    if t.get("stadium"):
        parts.append(f"主场 {t['stadium']}" + (f"（容量 {t['capacity']:,}）" if t.get("capacity") else ""))
    if t.get("founded"):
        parts.append(f"成立于 {t['founded']}")
    if t.get("elo_rating"):
        parts.append(f"Elo {float(t['elo_rating']):.0f}")
    if squad:
        parts.append(f"阵容 {squad['n']} 人, 总身价 {money(squad['value_total'])}, 平均年龄 {squad['age_avg']}")
    if st:
        parts.append(
            f"{season_label(st['season'])} 赛季 {st['rank']} 名: {st['played']} 场 "
            f"{st['won']}胜{st['draw']}平{st['lost']}负, 进{st['goals_for']}失{st['goals_against']}, "
            f"{st['points']} 分, 近况 {st['form'] or '—'}"
        )
    return _ok("team_info", "; ".join(parts), {"team": t, "squad": squad, "standing": st},
               [{"table": "teams", "id": t["team_id"], "label": t["name"], "url": f"/teams/{t['team_id']}",
                 "ref": f"team:{t['team_id']}"}])


# ---------------------------------------------------------------- 工具 2: 近期战绩


def team_form(team: Any, n: int = 5) -> dict:
    t = find_team(team)
    if not t:
        return _fail("team_form", f"库里没有找到球队「{team}」")
    keep = max(1, min(int(n), 15))
    with _connect() as con:
        rows = _rows(con, """
            SELECT m.match_id, m.date, m.home_team_id, m.away_team_id,
                   m.home_goals, m.away_goals, m.home_xg, m.away_xg,
                   th.name AS home, ta.name AS away, l.name AS league
            FROM matches m
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            LEFT JOIN leagues l ON l.league_id = m.league_id
            WHERE (m.home_team_id = ? OR m.away_team_id = ?)
              AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
            ORDER BY m.date DESC LIMIT ?
        """, (t["team_id"], t["team_id"], keep * 2 + 2))
    rows = _dedupe(rows)[:keep]
    if not rows:
        return _fail("team_form", f"库里没有 {t['name']} 的已完赛记录")
    items, wins, draws, losses, gf, ga = [], 0, 0, 0, 0, 0
    for r in rows:
        is_home = r["home_team_id"] == t["team_id"]
        mine, theirs = (r["home_goals"], r["away_goals"]) if is_home else (r["away_goals"], r["home_goals"])
        res = "W" if mine > theirs else ("D" if mine == theirs else "L")
        wins += res == "W"
        draws += res == "D"
        losses += res == "L"
        gf += mine
        ga += theirs
        items.append({
            "match_id": r["match_id"], "date": r["date"], "league": r["league"],
            "home": r["home"], "away": r["away"], "score": f"{r['home_goals']}-{r['away_goals']}",
            "venue": "主" if is_home else "客", "opponent": r["away"] if is_home else r["home"],
            "result": res, "xg": (r["home_xg"], r["away_xg"]),
        })
    summary = (f"{t['name']} 近 {len(items)} 场: {wins}胜{draws}平{losses}负, "
               f"进 {gf} 失 {ga}; " +
               "、".join(f"{i['date'][:10]} {i['venue']}vs{i['opponent']} {i['score']}{i['result']}" for i in items[:5]))
    return _ok("team_form", summary, {"team": t["name"], "items": items,
                                      "record": {"w": wins, "d": draws, "l": losses, "gf": gf, "ga": ga}},
               [{"table": "matches", "id": i["match_id"], "label": f"{i['home']} {i['score']} {i['away']}",
                 "url": f"/matches/{i['match_id']}", "ref": f"match:{i['match_id']}"} for i in items[:5]]
               + [{"table": "teams", "id": t["team_id"], "label": t["name"], "url": f"/teams/{t['team_id']}",
                   "ref": f"team:{t['team_id']}"}])


# ---------------------------------------------------------------- 工具 3: 交锋记录


def head_to_head(team_a: Any, team_b: Any, n: int = 10) -> dict:
    a, b = find_team(team_a), find_team(team_b)
    if not a or not b:
        missing = team_a if not a else team_b
        return _fail("head_to_head", f"库里没有找到球队「{missing}」")
    if a["team_id"] == b["team_id"]:
        return _fail("head_to_head", "需要两支不同的球队")
    with _connect() as con:
        rows = _rows(con, """
            SELECT m.match_id, m.date, m.home_team_id, m.away_team_id, m.home_goals, m.away_goals,
                   m.home_xg, m.away_xg, th.name AS home, ta.name AS away, l.name AS league
            FROM matches m
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            LEFT JOIN leagues l ON l.league_id = m.league_id
            WHERE ((m.home_team_id = ? AND m.away_team_id = ?) OR (m.home_team_id = ? AND m.away_team_id = ?))
              AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
            ORDER BY m.date DESC LIMIT ?
        """, (a["team_id"], b["team_id"], b["team_id"], a["team_id"], max(1, min(int(n), 30)) * 2 + 2))
    rows = _dedupe(rows)[:max(1, min(int(n), 30))]
    if not rows:
        return _fail("head_to_head", f"库里没有 {a['name']} vs {b['name']} 的已完赛记录")
    aw = d = bw = 0
    items = []
    for r in rows:
        a_is_home = r["home_team_id"] == a["team_id"]
        a_goals, b_goals = (r["home_goals"], r["away_goals"]) if a_is_home else (r["away_goals"], r["home_goals"])
        res = "W" if a_goals > b_goals else ("D" if a_goals == b_goals else "L")
        aw += res == "W"
        d += res == "D"
        bw += res == "L"
        items.append({"match_id": r["match_id"], "date": r["date"], "league": r["league"],
                      "home": r["home"], "away": r["away"], "score": f"{r['home_goals']}-{r['away_goals']}",
                      "result_for_a": res})
    summary = (f"{a['name']} vs {b['name']} 近 {len(items)} 次交锋: {a['name']} {aw}胜{d}平{bw}负; " +
               "、".join(f"{i['date'][:10]} {i['home']} {i['score']} {i['away']}" for i in items[:5]))
    return _ok("head_to_head", summary,
               {"team_a": a["name"], "team_b": b["name"], "items": items,
                "record": {"a_wins": aw, "draws": d, "b_wins": bw}},
               [{"table": "matches", "id": i["match_id"], "label": f"{i['home']} {i['score']} {i['away']}",
                 "url": f"/matches/{i['match_id']}", "ref": f"match:{i['match_id']}"} for i in items[:5]])


# ---------------------------------------------------------------- 工具 4: 积分榜


def league_table(league: Any, limit: int = 10, season: str | None = None) -> dict:
    lg = find_league(league)
    if not lg:
        return _fail("league_table", f"库里没有找到联赛「{league}」")
    limit = max(1, min(int(limit), 30))
    with _connect() as con:
        if not season:
            row = _one(con, "SELECT MAX(season) AS s FROM standings WHERE league_id = ?", (lg["league_id"],))
            season = (row or {}).get("s")
        if not season:
            return _fail("league_table", f"{lg['name']} 还没有积分榜数据")
        rows = _rows(con, """
            SELECT s.rank, s.played, s.won, s.draw, s.lost, s.goals_for, s.goals_against,
                   s.goal_diff, s.points, s.form, s.season, t.name AS team, t.team_id
            FROM standings s JOIN teams t ON t.team_id = s.team_id
            WHERE s.league_id = ? AND s.season = ?
            ORDER BY s.rank LIMIT ?
        """, (lg["league_id"], season, limit))
    if not rows:
        return _fail("league_table", f"{lg['name']} {season_label(season)} 赛季没有积分榜数据")
    lines = [f"{r['rank']}. {r['team']} {r['points']}分（{r['played']}场 {r['won']}胜{r['draw']}平{r['lost']}负 "
             f"净胜{r['goal_diff']:+d}）" for r in rows]
    summary = f"{lg['name']} {season_label(season)} 赛季积分榜前 {len(rows)}: " + "; ".join(lines)
    return _ok("league_table", summary,
               {"league": lg["name"], "season": season, "seasonLabel": season_label(season), "rows": rows},
               [{"table": "leagues", "id": lg["league_id"], "label": f"{lg['name']} {season_label(season)} 积分榜",
                 "url": f"/leagues/{lg['league_id']}?season={season}", "ref": f"league:{lg['league_id']}"}])


# ---------------------------------------------------------------- 工具 5: 预测


def match_prediction(home: Any, away: Any) -> dict:
    h, a = find_team(home), find_team(away)
    if not h or not a:
        missing = home if not h else away
        return _fail("match_prediction", f"库里没有找到球队「{missing}」")
    if h["team_id"] == a["team_id"]:
        return _fail("match_prediction", "需要两支不同的球队")
    with _connect() as con:
        upcoming = _one(con, """
            SELECT m.match_id, m.date, m.status, m.season, m.home_team_id, m.away_team_id,
                   th.name AS home, ta.name AS away, l.name AS league,
                   p.pred_id, p.model_version, p.pred_home_win, p.pred_draw, p.pred_away_win, p.pred_result,
                   p.created_at, p.actual_result, p.hit, p.is_backtest
            FROM matches m
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            LEFT JOIN leagues l ON l.league_id = m.league_id
            LEFT JOIN predictions p ON p.match_id = m.match_id
            WHERE ((m.home_team_id = ? AND m.away_team_id = ?) OR (m.home_team_id = ? AND m.away_team_id = ?))
              AND m.home_goals IS NULL
            ORDER BY m.date ASC LIMIT 1
        """, (h["team_id"], a["team_id"], a["team_id"], h["team_id"]))
        played = _one(con, """
            SELECT m.match_id, m.date, m.status, m.season, m.home_team_id, m.away_team_id,
                   m.home_goals, m.away_goals,
                   th.name AS home, ta.name AS away, l.name AS league,
                   p.pred_id, p.model_version, p.pred_home_win, p.pred_draw, p.pred_away_win, p.pred_result,
                   p.created_at, p.actual_result, p.hit, p.is_backtest
            FROM matches m
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            LEFT JOIN leagues l ON l.league_id = m.league_id
            JOIN predictions p ON p.match_id = m.match_id
            WHERE ((m.home_team_id = ? AND m.away_team_id = ?) OR (m.home_team_id = ? AND m.away_team_id = ?))
              AND m.home_goals IS NOT NULL
            ORDER BY m.date DESC LIMIT 1
        """, (h["team_id"], a["team_id"], a["team_id"], h["team_id"]))
    row = upcoming or played
    if not row:
        return _fail("match_prediction", f"库里没有 {h['name']} vs {a['name']} 的比赛（也没有已落库的预测）")
    if row.get("pred_home_win") is None:
        return _fail("match_prediction",
                     f"{row['home']} vs {row['away']}（{str(row['date'])[:10]}）在库里, 但还没有模型预测记录")
    hashed = {"H": "主胜", "D": "平局", "A": "客胜"}
    parts = [f"{row['home']} vs {row['away']}（{str(row['date'])[:10]} · {row.get('league') or '—'} · "
             f"{'未开赛' if upcoming else '已完赛'}）"]
    parts.append(f"模型 {row['model_version']}: 主胜 {row['pred_home_win'] * 100:.1f}% / "
                 f"平局 {row['pred_draw'] * 100:.1f}% / 客胜 {row['pred_away_win'] * 100:.1f}%, "
                 f"倾向 {hashed.get(row['pred_result'], row['pred_result'])}")
    if row.get("home_goals") is not None:
        parts.append(f"实际比分 {row['home_goals']}-{row['away_goals']}"
                     + (f", 预测{'命中' if row.get('hit') else '未命中'}" if row.get("hit") is not None else ""))
    if row.get("created_at"):
        parts.append(f"预测生成于 {row['created_at']}")
    srcs = [{"table": "matches", "id": row["match_id"],
             "label": f"{row['home']} vs {row['away']}（{str(row['date'])[:10]}）",
             "url": f"/matches/{row['match_id']}", "ref": f"match:{row['match_id']}"}]
    if row.get("pred_id"):
        # 引用要指向真正的预测行（predictions 的主键是 pred_id, 不是 match_id）
        srcs.append({"table": "predictions", "id": row["pred_id"],
                     "label": f"预测记录 {row['model_version']}（{row['home']} vs {row['away']}）",
                     "url": f"/matches/{row['match_id']}", "ref": f"prediction:{row['pred_id']}"})
    return _ok("match_prediction", "; ".join(parts),
               {"match": row, "is_upcoming": bool(upcoming),
                "probabilities": {"home": row["pred_home_win"], "draw": row["pred_draw"], "away": row["pred_away_win"]}},
               srcs)


# ---------------------------------------------------------------- 工具 6: 球员


def player_info(player: Any) -> dict:
    p = find_player(player)
    if not p:
        return _fail("player_info", f"库里没有找到球员「{player}」")
    with _connect() as con:
        full = _one(con, """
            SELECT p.*, t.name AS team_name, l.name AS league_name
            FROM players p
            LEFT JOIN teams t ON t.team_id = p.team_id
            LEFT JOIN leagues l ON l.league_id = t.league_id
            WHERE p.player_id = ?
        """, (p["player_id"],))
        radar = _one(con, "SELECT * FROM player_radar WHERE player_id = ?", (p["player_id"],))
        seasons: list[dict] = []
        tm_id = (full or {}).get("tm_player_id")
        if tm_id:
            seasons = _rows(con, """
                SELECT season_start, season_name, team_name, competition_name,
                       SUM(appearances) AS apps, SUM(goals) AS goals, SUM(assists) AS assists
                FROM tm_player_seasons WHERE player_id = ?
                GROUP BY season_start, season_name, team_name, competition_name
                ORDER BY season_start DESC LIMIT 5
            """, (str(tm_id),))
    full = full or {}
    parts = [f"{full.get('name') or p['name']}"
             + (f"（{full.get('name_en')}）" if full.get("name_en") else "")]
    bits = []
    if full.get("position"):
        bits.append(str(full["position"]))
    if full.get("age"):
        bits.append(f"{full['age']} 岁")
    if full.get("nationality"):
        bits.append(str(full["nationality"]))
    if full.get("foot"):
        bits.append(f"{full['foot']} 脚")
    if bits:
        parts.append(" / ".join(bits))
    if full.get("team_name"):
        parts.append(f"效力 {full['team_name']}（{full.get('league_name') or '—'}）")
    parts.append(f"身价 {money(full.get('market_value'))}")
    if radar:
        parts.append(f"近 {_int(radar.get('apps'))} 场出场 {_int(radar.get('minutes'))} 分钟, "
                     f"{_int(radar.get('goals'))} 球 {_int(radar.get('assists'))} 助攻, "
                     f"每90分钟参与 {_round(radar.get('involve_p90'))}, 身价分位 {_int(radar.get('s_value'))}")
    if seasons:
        top = seasons[0]
        where = " ".join(x for x in (top["team_name"], top["competition_name"]) if x)
        parts.append(f"最近赛季 {top['season_name']} {where}: "
                     f"{_int(top['apps'])} 场 {_int(top['goals'])} 球 {_int(top['assists'])} 助攻")
    return _ok("player_info", "; ".join(parts),
               {"player": full, "radar": radar, "seasons": seasons},
               [{"table": "players", "id": p["player_id"], "label": full.get("name") or p["name"],
                 "url": f"/players/{p['player_id']}", "ref": f"player:{p['player_id']}"}]
               + ([{"table": "teams", "id": full["team_id"], "label": full["team_name"],
                    "url": f"/teams/{full['team_id']}", "ref": f"team:{full['team_id']}"}]
                  if full.get("team_id") else []))


TOOLS = {
    "team_info": team_info,
    "team_form": team_form,
    "head_to_head": head_to_head,
    "league_table": league_table,
    "match_prediction": match_prediction,
    "player_info": player_info,
}


def describe() -> list[dict]:
    """给 /api/ui/ask/status 与文档用的工具清单。"""
    return [
        {"name": "team_info", "zh": "球队资料", "args": ["球队名"], "desc": "联赛/主教练/主场/成立/阵容身价/最近赛季排名"},
        {"name": "team_form", "zh": "近期战绩", "args": ["球队名", "场次"], "desc": "最近 N 场比分与胜平负"},
        {"name": "head_to_head", "zh": "交锋记录", "args": ["球队A", "球队B"], "desc": "两队历史交锋比分与胜负统计"},
        {"name": "league_table", "zh": "积分榜", "args": ["联赛名", "条数"], "desc": "最新赛季积分榜前 N"},
        {"name": "match_prediction", "zh": "比赛预测", "args": ["主队", "客队"], "desc": "库里已落库的模型预测概率（未预测则如实说明）"},
        {"name": "player_info", "zh": "球员资料", "args": ["球员名"], "desc": "位置/年龄/身价/出场进球与身价分位"},
    ]


def db_path() -> Path:
    return main_db_path()
