#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""build_console.py — 生成 docs/console/index.html（真实数据控制台）

参照实现: tools/console_template.html（用户提供的 indexFT.html：166 KB 自包含控制台，
14 个页面 + 图标/图表/动效 + ?page= 深链语义）。
本脚本把该文件的「演示数据层」整块替换为从 data/database/football.db 直读的真实数据，
并对少量写死在视图里的演示数值做定点替换（每处都断言唯一命中，命中失败即报错）。

用法:
    python scripts/build_console.py [--no-assets]
"""
from __future__ import annotations

import argparse
import io
import json
import math
import re
import socket
import sqlite3
import sys
import unicodedata
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
DB = ROOT / "data" / "database" / "football.db"
TPL = ROOT / "tools" / "console_template.html"
OUT_DIR = ROOT / "docs" / "console"
CREST_DIR = OUT_DIR / "assets" / "crests"
LEAGUE_DIR = OUT_DIR / "assets" / "leagues"

# ---------------------------------------------------------------- 基础工具

POS_ZH = {"Goalkeeper": "门将", "Defender": "后卫", "Midfielder": "中场",
          "Attacker": "前锋", "Forward": "前锋", " goalkeeper": "门将"}

NATION_ZH = {
    "Spain": "西班牙", "France": "法国", "England": "英格兰", "Germany": "德国",
    "Italy": "意大利", "Brazil": "巴西", "Argentina": "阿根廷", "Portugal": "葡萄牙",
    "Netherlands": "荷兰", "Belgium": "比利时", "Norway": "挪威", "Egypt": "埃及",
    "Poland": "波兰", "Croatia": "克罗地亚", "Denmark": "丹麦", "Sweden": "瑞典",
    "Nigeria": "尼日利亚", "Senegal": "塞内加尔", "Morocco": "摩洛哥", "Japan": "日本",
    "Korea Republic": "韩国", "Uruguay": "乌拉圭", "Colombia": "哥伦比亚", "Mexico": "墨西哥",
    "United States": "美国", "Scotland": "苏格兰", "Wales": "威尔士", "Ireland": "爱尔兰",
    "Austria": "奥地利", "Switzerland": "瑞士", "Turkey": "土耳其", "Greece": "希腊",
    "Serbia": "塞尔维亚", "Czechia": "捷克", "Ukraine": "乌克兰", "Georgia": "格鲁吉亚",
    "Algeria": "阿尔及利亚", "Ghana": "加纳", "Ivory Coast": "科特迪瓦", "Cameroon": "喀麦隆",
    "Chile": "智利", "Peru": "秘鲁", "Paraguay": "巴拉圭", "Ecuador": "厄瓜多尔",
    "Canada": "加拿大", "Australia": "澳大利亚", "Slovakia": "斯洛伐克", "Hungary": "匈牙利",
    "Romania": "罗马尼亚", "Bulgaria": "保加利亚", "Finland": "芬兰", "Iceland": "冰岛",
}

# 仅用于图表系列配色的 UI 调色板（非数据，徽标与主色仍取自真实 logo）
# 与登录页 docs/console/login.html 的暖橙语言一致：暖橙为主 + 冷蓝/金/石墨为辅，
# 不再用霓虹绿/品红/紫这类撞色（配合 tools/patch_console_skin.py 的浅色主题）。
PALETTE = ["#2f86e0", "#2aa3c9", "#c8871a", "#5b6f8c", "#d0453c", "#63a8e8",
           "#86c9d8", "#3a6f9e", "#8a7f6a", "#93a6bb", "#1f6fc4", "#b8c2cc"]

# slug -> 中文队名（build_teams 填充，供生成中文快讯文案用）
TEAM_NAME: dict[str, str] = {}


def slug(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = re.sub(r"[^a-zA-Z0-9]+", "-", s).strip("-").lower()
    return s or "x"


def connect() -> sqlite3.Connection:
    con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def q(con, sql, args=()):
    return con.execute(sql, args).fetchall()


def one(con, sql, args=()):
    r = con.execute(sql, args).fetchone()
    return r


def js(obj) -> str:
    return json.dumps(obj, ensure_ascii=False, separators=(",", ":"))


def col_js(rows, h=180, w=520, color=None):
    """生成 columnChart(对象数组) 的 JS 源码（模板的 columnChart 只吃 {label,value,display,color} 对象）。"""
    items = []
    for lab, val, disp in rows:
        c = color or "var(--accent)"
        items.append("{label:%s,value:%s,display:%s,color:%s}" % (js(str(lab)), js(val), js(str(disp)), js(c)))
    return "columnChart([%s],{height:%s,width:%s})" % (",".join(items), h, w)


def norm100(values, inverse=False):
    """把真实值线性归一化到 0-100（跨联赛/跨球队可比）。"""
    vals = [v for v in values if isinstance(v, (int, float))]
    if not vals:
        return [0 for _ in values]
    lo, hi = min(vals), max(vals)
    out = []
    for v in values:
        if not isinstance(v, (int, float)):
            out.append(0)
            continue
        x = 50.0 if hi == lo else (v - lo) / (hi - lo) * 100.0
        out.append(round(100 - x if inverse else x, 1))
    return out


def probe(port: int, path: str = "/") -> bool:
    # 服务在线判定：能拿到 HTTP 响应即算在线（4xx 也说明服务进程活着），只有连不上才算离线
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=4) as r:
            return r.status < 500
    except urllib.error.HTTPError:
        return True
    except Exception:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=2.5):
                return True
        except Exception:
            return False


def download(url: str, dest: Path) -> bool:
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 console-build"})
        with urllib.request.urlopen(req, timeout=20) as r:
            data = r.read()
        if len(data) < 200:
            return False
        dest.write_bytes(data)
        return True
    except Exception:
        return False


def valid_png(p: Path) -> bool:
    """缓存文件必须是真正的 PNG（早期版本曾把 SVG/错误页写进 .png）。"""
    try:
        with p.open("rb") as f:
            return f.read(8) == b"\x89PNG\r\n\x1a\n"
    except Exception:
        return False


def badge_png(name: str, color: str, sub: str = "") -> bytes:
    """无 logo 时的占位徽标 PNG（明确是生成的图形，不是拿别人队徽冒充）。"""
    txt = ((sub or name) or "?").strip()[:3].upper()
    size = 72
    im = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    d.rounded_rectangle((3, 3, size - 3, size - 3), 16, fill=(18, 27, 23, 235), outline=color, width=2)
    d.ellipse((size / 2 - 13, size / 2 - 13, size / 2 + 13, size / 2 + 13), outline=color, width=1)
    font = None
    for cand in ("C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"):
        try:
            font = ImageFont.truetype(cand, 26 if len(txt) < 3 else 21)
            break
        except Exception:
            continue
    if font is None:
        font = ImageFont.load_default(size=24)
    d.text((size / 2, size / 2 + 1), txt, font=font, fill=(233, 241, 236, 255), anchor="mm")
    buf = io.BytesIO()
    im.save(buf, format="PNG")
    return buf.getvalue()


def badge_svg(name: str, color: str, sub: str = "") -> str:
    """无 logo 时的占位徽标（明确是生成的图形，不是拿别人队徽冒充）。"""
    txt = (sub or name)[:4]
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 64 64">'
        f'<rect width="64" height="64" rx="14" fill="{color}" opacity="0.16"/>'
        f'<rect x="1.5" y="1.5" width="61" height="61" rx="13" fill="none" stroke="{color}" stroke-width="1.5" opacity="0.5"/>'
        f'<text x="32" y="39" font-family="Segoe UI,Microsoft YaHei,sans-serif" font-size="20" font-weight="700" '
        f'fill="{color}" text-anchor="middle">{txt}</text></svg>'
    )


# ---------------------------------------------------------------- 数据构建

def build_meta(con):
    # auth_* 是登录认证表(存口令哈希与会话令牌), 不进控制台的统计与表清单
    tables = [t for t in q(con, "SELECT name FROM sqlite_master WHERE type='table' "
                                 "AND name NOT LIKE 'sqlite_%'")
              if not t["name"].startswith("auth_")]
    total = 0
    nonempty = 0
    for t in tables:
        n = one(con, f'SELECT COUNT(*) c FROM "{t["name"]}"')["c"]
        total += n
        nonempty += 1 if n else 0
    db_mb = round(DB.stat().st_size / 1024 / 1024, 1)
    newest = one(con, "SELECT MAX(date) d FROM matches")["d"]
    return {"tables": len(tables), "rows": total, "nonempty": nonempty,
            "db_mb": db_mb, "newest_match": newest}


def build_services(meta):
    svc = [
        {"name": "API 服务", "port": 8000, "url": "http://127.0.0.1:8000/docs", "path": "/health"},
        {"name": "用户端", "port": 8501, "url": "http://127.0.0.1:8501/", "path": "/"},
        {"name": "管理后台", "port": 8502, "url": "http://127.0.0.1:8502/", "path": "/"},
        {"name": "本控制台", "port": 8591, "url": "http://127.0.0.1:8591/", "path": "/"},
    ]
    out = []
    for s in svc:
        ok = probe(s["port"], s["path"])
        out.append({"name": s["name"], "port": s["port"], "status": "ok" if ok else "warn",
                    "note": "已连接" if ok else "未响应"})
    return out


def build_leagues(con):
    rows = q(con, """
        SELECT l.league_id, l.name, l.name_en, l.country, l.season,
               (SELECT COUNT(*) FROM matches m WHERE m.league_id = l.league_id) nm,
               (SELECT COUNT(*) FROM standings s WHERE s.league_id = l.league_id
                  AND s.season = (SELECT MAX(season) FROM standings s2 WHERE s2.league_id = l.league_id)) ns
        FROM leagues l
    """)
    rows = sorted(rows, key=lambda r: -r["nm"])
    stats = {}
    for r in q(con, "SELECT * FROM league_stats"):
        cur = stats.get(r["league_id"])
        if cur is None or str(r["season"]) > str(cur["season"]):
            stats[r["league_id"]] = dict(r)
    dims = [("场均进球", "goals_pg"), ("场均 xG", "xg_pg"), ("主胜率", "home_win_pct"),
            ("平局率", "draw_pct"), ("客胜率", "away_win_pct"), ("场次规模", "matches")]
    raw = {k: [stats.get(r["league_id"], {}).get(k) for r in rows] for _, k in dims}
    norm = {k: norm100(v) for k, v in raw.items()}
    out = {}
    for i, r in enumerate(rows):
        s = slug(r["name_en"] or r["name"])
        style = {}
        for label, key in dims:
            v = raw[key][i]
            style[label] = round(v, 2) if isinstance(v, (int, float)) else 0
        out[s] = {"name": r["name"], "en": r["name_en"] or r["name"], "country": r["country"] or "—",
                  "crest": s, "league_id": r["league_id"], "matches": r["nm"], "standings_rows": r["ns"],
                  "style": style, "_norm": {label: norm[key][i] for label, key in dims}}
    return out, rows


def build_standings(con, leagues, team_slug):
    out = {}
    for s, info in leagues.items():
        rows = q(con, """
            SELECT team_id, rank, played, won, draw, lost, goals_for, goals_against, points, form
            FROM standings
            WHERE league_id = ? AND season = (SELECT MAX(season) FROM standings s2 WHERE s2.league_id = ?)
            ORDER BY rank
        """, (info["league_id"], info["league_id"]))
        arr = []
        for r in rows:
            sl = team_slug.get(r["team_id"])
            if not sl:
                continue
            arr.append([sl, r["won"], r["draw"], r["lost"], r["goals_for"], r["goals_against"]])
        if arr:
            out[s] = arr
    return out


def build_teams(con, extra_ids):
    teams = q(con, "SELECT team_id, league_id, name, name_en, short_name, logo_url, elo_rating, stadium, manager FROM teams")
    by_id = {t["team_id"]: t for t in teams}
    ids = set(extra_ids)
    rows = q(con, """
        SELECT s.team_id FROM standings s
        WHERE s.season = (SELECT MAX(season) FROM standings s2 WHERE s2.league_id = s.league_id)
    """)
    ids |= {r["team_id"] for r in rows}
    ids = {i for i in ids if i in by_id}

    # 近 5 场（真实）
    hist = q(con, """
        SELECT home_team_id h, away_team_id a, home_goals hg, away_goals ag, date
        FROM matches WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL
        ORDER BY date DESC
    """)
    form = {}
    for m in hist:
        for tid, gf, ga in ((m["h"], m["hg"], m["ag"]), (m["a"], m["ag"], m["hg"])):
            if tid not in ids:
                continue
            lst = form.setdefault(tid, [])
            if len(lst) < 5:
                lst.append("W" if gf > ga else ("D" if gf == ga else "L"))
    # 赛季均场（真实：team_radar）
    radar = {r["team_id"]: dict(r) for r in q(con, "SELECT * FROM team_radar")}

    out, tslug = {}, {}
    used = {}
    for tid in sorted(ids):
        t = by_id[tid]
        base = slug(t["name_en"] or t["name"])
        s = base
        n = 2
        while s in used:
            s = f"{base}-{n}"
            n += 1
        used[s] = tid
        tslug[tid] = s
        short = (t["short_name"] or "").strip() or "".join(w[0] for w in (t["name_en"] or t["name"]).split()[:3]).upper()
        TEAM_NAME[s] = t["name"]
        tr = radar.get(tid, {})
        out[s] = {
            "name": t["name"], "en": t["name_en"] or t["name"], "short": short[:5],
            "crest": s, "elo": round(t["elo_rating"]) if t["elo_rating"] else 0,
            "team_id": tid, "league_id": t["league_id"],
            "logo": t["logo_url"], "stadium": t["stadium"], "manager": t["manager"],
            "form": form.get(tid, []),
            "season": {k: (round(tr.get(k), 2) if isinstance(tr.get(k), (int, float)) else None)
                       for k in ("matches", "goals_pg", "conceded_pg", "shots_pg", "xg_pg", "xga_pg", "ppg", "squad_value")},
            "radar": {k: (round(tr[k], 1) if isinstance(tr.get(k), (int, float)) else 0) for k in
                      ("s_attack", "s_defense", "s_dominance", "s_discipline", "s_value", "s_experience")},
        }
    return out, tslug


def build_players(con, team_slug, limit=18):
    rows = q(con, """
        SELECT pr.*, t.name tname, t.name_en ten FROM player_radar pr
        LEFT JOIN teams t ON t.team_id = pr.team_id
        WHERE pr.market_value IS NOT NULL AND pr.market_value > 0
        ORDER BY pr.market_value DESC LIMIT ?
    """, (limit,))
    out, used = [], {}
    for r in rows:
        base = slug(r["name_en"] or r["name"])
        s = base
        n = 2
        while s in used:
            s = f"{base}-{n}"
            n += 1
        used[s] = r["player_id"]
        out.append({
            "slug": s, "name": r["name"], "en": r["name_en"] or r["name"],
            "team": team_slug.get(r["team_id"], ""), "teamName": r["tname"] or "",
            "pos": POS_ZH.get((r["position"] or "").strip(), r["position"] or "—"),
            "pos_group": r["pos_group"] or "", "age": r["age"],
            "nation": NATION_ZH.get(r["nationality"] or "", r["nationality"] or "—"),
            "value": round((r["market_value"] or 0) / 1e6, 1),
            "apps": r["apps"] or 0, "minutes": r["minutes"] or 0,
            "goals": r["goals"] or 0, "assists": r["assists"] or 0, "cards": r["cards"] or 0,
            "attrs": {
                "进球": r["s_goals"], "助攻": r["s_assists"], "参与": r["s_involve"],
                "出场": r["s_minutes"], "纪律": r["s_discipline"], "身价": r["s_value"],
            },
            "attrList": [
                round(r["s_goals"] or 0, 1), round(r["s_assists"] or 0, 1), round(r["s_involve"] or 0, 1),
                round(r["s_minutes"] or 0, 1), round(r["s_discipline"] or 0, 1), round(r["s_value"] or 0, 1),
            ],
            "market_value_eur": r["market_value"],
        })
    return out


def build_upcoming(con, team_slug, leagues, limit=8):
    rows = q(con, """
        SELECT p.pred_home_win ph, p.pred_draw pd, p.pred_away_win pa, p.pred_result pr,
               p.model_version mv, p.created_at pc, m.match_id, m.date, m.matchday,
               m.home_team_id hid, m.away_team_id aid, l.league_id lid, l.name lname,
               m.home_xg hx, m.away_xg ax
        FROM predictions p
        JOIN matches m ON m.match_id = p.match_id
        JOIN leagues l ON l.league_id = m.league_id
        WHERE p.actual_result IS NULL
        ORDER BY m.date LIMIT ?
    """, (limit,))
    lg = {}
    for s, info in leagues.items():
        lg[info["league_id"]] = s
    out = []
    for r in rows:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a:
            continue
        out.append({
            "league": lg.get(r["lid"], ""), "home": h, "away": a,
            "date": (r["date"] or "")[:10], "time": (r["date"] or "")[11:16],
            "round": f"第 {r['matchday']} 轮" if r["matchday"] else "",
            "prob": [round((r["ph"] or 0) * 100), round((r["pd"] or 0) * 100), round((r["pa"] or 0) * 100)],
            "conf": round(max(r["ph"] or 0, r["pd"] or 0, r["pa"] or 0), 4),
            "result": {"H": "主胜", "D": "平局", "A": "客胜"}.get((r["pr"] or "").upper(), r["pr"] or "—"),
            "model": r["mv"], "pred_at": (r["pc"] or "")[:16],
            "home_xg": r["hx"], "away_xg": r["ax"],
        })
    return out


def build_match(con, team_slug, leagues):
    cands = q(con, """
        SELECT m.*, l.name lname, l.league_id lid FROM matches m
        JOIN leagues l ON l.league_id = m.league_id
        WHERE m.stats_json IS NOT NULL AND m.home_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT 400
    """)
    best, best_n = None, -1
    for m in cands:
        try:
            sj = json.loads(m["stats_json"])
        except Exception:
            continue
        hs = {k: v for k, v in (sj.get("home_stats") or {}).items() if v not in (None, "")}
        as_ = {k: v for k, v in (sj.get("away_stats") or {}).items() if v not in (None, "")}
        n = len(set(hs) & set(as_))
        if n > best_n:
            best, best_n = (m, sj, hs, as_), n
    if not best:
        return None, None
    m, sj, hs, as_ = best
    h, a = team_slug.get(m["home_team_id"]), team_slug.get(m["away_team_id"])
    if not h or not a:
        return None, None

    def fnum(d, key):
        v = d.get(key)
        if v is None or v == "":
            return None
        try:
            return float(str(v).replace("%", "").strip())
        except Exception:
            return None

    def passes_pct(d, side):
        p = fnum(d, "Passes %")
        if p is not None:
            return p
        tot, acc = fnum(d, "Total passes"), fnum(d, "Passes accurate")
        if tot and acc:
            return round(acc / tot * 100, 1)
        return None

    specs = [
        ("控球率", fnum(hs, "Ball Possession"), fnum(as_, "Ball Possession"), "%", 0),
        ("射门", fnum(hs, "Total Shots"), fnum(as_, "Total Shots"), "", 0),
        ("射正", fnum(hs, "Shots on Goal"), fnum(as_, "Shots on Goal"), "", 0),
        ("射偏", fnum(hs, "Shots off Goal"), fnum(as_, "Shots off Goal"), "", 0),
        ("被封堵", fnum(hs, "Blocked Shots"), fnum(as_, "Blocked Shots"), "", 0),
        ("预期进球 xG", m["home_xg"], m["away_xg"], "", 2),
        ("传球成功率", passes_pct(hs, "h"), passes_pct(as_, "a"), "%", 0),
        ("角球", fnum(hs, "Corner Kicks"), fnum(as_, "Corner Kicks"), "", 0),
        ("犯规", fnum(hs, "Fouls"), fnum(as_, "Fouls"), "", 0),
        ("越位", fnum(hs, "Offsides"), fnum(as_, "Offsides"), "", 0),
        ("黄牌", fnum(hs, "Yellow Cards"), fnum(as_, "Yellow Cards"), "", 0),
        ("门将扑救", fnum(hs, "Goalkeeper Saves"), fnum(as_, "Goalkeeper Saves"), "", 0),
    ]
    stats = [{"label": lb, "home": hv, "away": av, "unit": u, "fixed": fx}
             for lb, hv, av, u, fx in specs if hv is not None and av is not None]

    def lineups(tid):
        rows = q(con, """
            SELECT name, number, position, minutes FROM player_radar
            WHERE team_id = ? AND minutes IS NOT NULL ORDER BY minutes DESC LIMIT 11
        """, (tid,))
        return [[str(r["number"]) if r["number"] else "—", r["name"]] for r in rows]

    def injuries(tid):
        rows = q(con, """
            SELECT p.name, i.injury_reason, i.from_date, i.end_date, i.days_missed, i.season_name
            FROM tm_player_injuries i JOIN players p ON p.tm_player_id = i.player_id
            WHERE p.team_id = ? ORDER BY i.from_date DESC LIMIT 5
        """, (tid,))
        return rows

    lg = next((s for s, i in leagues.items() if i["league_id"] == m["league_id"]), "")
    match = {
        "league": lg, "round": f"第 {m['matchday']} 轮" if m["matchday"] else "—",
        "date": m["date"], "venue": m["venue"] or "—", "referee": m["referee"] or "—",
        "home": h, "away": a, "score": [m["home_goals"], m["away_goals"]], "status": "FT",
        "match_id": m["match_id"], "stats": stats, "events": [],
        "lineups": {"home": {"formation": "—", "xi": lineups(m["home_team_id"])},
                    "away": {"formation": "—", "xi": lineups(m["away_team_id"])}},
        "injuries": [],
        "extra": {},
    }
    for tid, s in ((m["home_team_id"], h), (m["away_team_id"], a)):
        tname = one(con, "SELECT name FROM teams WHERE team_id = ?", (tid,))["name"]
        for r in injuries(tid):
            try:
                miss = f"缺阵 {int(round(float(r['days_missed'])))} 天"
            except (TypeError, ValueError):
                miss = "缺阵天数未记录"
            span = f"{r['from_date']} → {r['end_date'] or '—'}"
            match["injuries"].append([s, tname, r["name"],
                                      f"{r['injury_reason'] or '—'} · {span}", miss])
    for key in ("expected_goals", "goals_prevented"):
        hv, av = fnum(hs, key), fnum(as_, key)
        if hv is not None and av is not None:
            match["extra"][key] = [hv, av]
    return match, sj


def build_predictions(con):
    """真实复盘样本（带实际结果的回测预测）+ 真实 Brier。"""
    rows = q(con, """
        SELECT p.pred_home_win ph, p.pred_draw pd, p.pred_away_win pa, p.pred_result pr,
               p.actual_result ar, p.hit hit, p.is_backtest bt, p.model_version mv,
               m.match_id, m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid
        FROM predictions p JOIN matches m ON m.match_id = p.match_id
        WHERE p.actual_result IS NOT NULL
        ORDER BY m.date DESC
    """)
    n = len(rows)
    hits = sum(1 for r in rows if r["hit"])
    brier = 0.0
    ll = 0.0
    for r in rows:
        y = {"H": (1, 0, 0), "D": (0, 1, 0), "A": (0, 0, 1)}.get((r["ar"] or "").upper())
        if not y:
            continue
        p = [r["ph"] or 0, r["pd"] or 0, r["pa"] or 0]
        s = sum(p) or 1
        p = [x / s for x in p]
        brier += sum((pi - yi) ** 2 for pi, yi in zip(p, y))
        ll += -math.log(max(p[y.index(1)], 1e-9))
    brier = round(brier / n, 4) if n else 0
    ll = round(ll / n, 4) if n else 0
    return {"n": n, "hits": hits, "acc": round(hits / n * 100, 2) if n else 0,
            "brier": brier, "logloss": ll, "rows": rows}


def build_review_rows(con, preds, team_slug, limit=6):
    out = []
    for r in preds["rows"][:limit]:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a:
            continue
        pmap = {"H": "主胜", "D": "平局", "A": "客胜"}
        out.append([(r["date"] or "")[:10], h, a, f"{r['hg']}-{r['ag']}",
                    pmap.get((r["pr"] or "").upper(), r["pr"] or "—"),
                    pmap.get((r["ar"] or "").upper(), r["ar"] or "—"),
                    bool(r["hit"]), round(max(r["ph"] or 0, r["pd"] or 0, r["pa"] or 0), 4)])
    return out


def build_modules(con, meta):
    def c(table):
        return one(con, f'SELECT COUNT(*) n FROM "{table}"')["n"]
    return [
        {"name": "球队", "value": c("teams"), "unit": "支", "delta": 0, "icon": "shield"},
        {"name": "球员", "value": c("player_radar"), "unit": "名", "delta": 0, "icon": "user"},
        {"name": "比赛", "value": c("matches"), "unit": "场", "delta": 0, "icon": "ball"},
        {"name": "转会记录", "value": c("transfers"), "unit": "条", "delta": 0, "icon": "activity"},
        {"name": "预测样本", "value": c("predictions"), "unit": "条", "delta": 0, "icon": "target"},
        {"name": "数据表", "value": meta["tables"], "unit": "张", "delta": 0, "icon": "database"},
    ]


def build_topics(con):
    """真实「数据浏览」10 个主题：取自 frontend/admin.py 的 tab 定义 + 每主题引用的真实表。"""
    src = (ROOT / "frontend" / "admin.py").read_text(encoding="utf-8")
    tabs = []
    m = re.search(r"st\.tabs\(\s*\[([\s\S]*?)\]\s*\)", src)
    if m:
        tabs = re.findall(r't\("([^"]+)"', m.group(1))
    blocks = re.split(r"\n\s*with tab_\w+:", src)
    icons = ["target", "ball", "user", "check", "trophy", "layers", "shield", "database", "spark", "grid"]
    ids = ["today", "matches", "players", "review", "standings", "tm", "squad", "cover", "pre", "tables"]
    known = {r["name"] for r in q(con, "SELECT name FROM sqlite_master WHERE type='table'")}
    out = []
    for i, name in enumerate(tabs):
        block = blocks[i + 1] if i + 1 < len(blocks) else ""
        used = sorted({t for t in re.findall(r"(?:FROM|JOIN)\s+([a-z_][a-z0-9_]*)", block) if t in known})
        out.append({"id": ids[i] if i < len(ids) else f"t{i}", "name": name,
                    "tables": len(used), "charts": len(used), "tableList": used,
                    "icon": icons[i] if i < len(icons) else "grid"})
    return out


def build_tables(con):
    names = [r["name"] for r in q(con, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name")]
    # 登录认证表不进控制台(会带出口令哈希与会话令牌)
    names = [n for n in names if not n.startswith("auth_")]
    out = []
    for n in names:
        rows = one(con, f'SELECT COUNT(*) c FROM "{n}"')["c"]
        cols = [r["name"] for r in q(con, f'PRAGMA table_info("{n}")')]
        # 表内首行真实数据（最多 2 行），供后台「数据库管理」直读展示
        sample = []
        for r in q(con, f'SELECT * FROM "{n}" LIMIT 2'):
            vals = []
            for c in cols:
                v = r[c]
                if v is None:
                    vals.append("—")
                elif isinstance(v, (int, float)) and not isinstance(v, bool):
                    vals.append(v)
                else:
                    s = str(v)
                    vals.append(s if len(s) <= 26 else s[:24] + "…")
            sample.append(vals)
        out.append({"name": n, "rows": rows, "cols": cols, "sample": sample})
    out.sort(key=lambda x: -x["rows"])
    return out


def build_models(con, preds):
    rows = q(con, "SELECT * FROM model_metrics")
    deployed = "v9 集成 v2+v7"
    out = []
    for r in rows:
        name = r["model"]
        out.append({
            "id": slug(name.replace("v", "v ")), "name": name,
            "algo": "XGBoost · " + re.sub(r"^v\d+\s*", "", name).strip() or "XGBoost",
            "acc": (r["acc"] or 0) / 100, "logloss": r["logloss"], "f1": r["f1_macro"],
            "draw_recall": r["draw_recall"], "test_n": r["test_n"],
            "brier": preds["brier"],
            "status": "production" if name == deployed else ("baseline" if name.startswith("v1 ") else "challenger"),
            "trained": f"{r['test_n']} 场样本外",
        })
    out.sort(key=lambda m: -m["acc"])
    return out


def build_update_log(con):
    def mx(sql):
        r = one(con, sql)
        return list(r)[0] if r else None
    items = []
    last_match = mx("SELECT MAX(date) FROM matches WHERE home_goals IS NOT NULL")
    n_match = one(con, "SELECT COUNT(*) n FROM matches WHERE home_goals IS NOT NULL")["n"]
    items.append({"ts": last_match, "level": "ok", "title": "比赛结果与统计入库",
                  "desc": f"本地库累计完赛 {n_match:,} 场，最新一场 {last_match}"})
    r = mx("SELECT MAX(transfer_date) FROM transfers")
    n = one(con, "SELECT COUNT(*) n FROM transfers")["n"]
    items.append({"ts": r, "level": "ok", "title": "Transfermarkt 转会记录同步",
                  "desc": f"累计 {n:,} 条转会记录，最新 {r}"})
    r = mx("SELECT MAX(value_date) FROM tm_player_market_value")
    n = one(con, "SELECT COUNT(*) n FROM tm_player_market_value")["n"]
    items.append({"ts": r, "level": "ok", "title": "球员身价序列更新",
                  "desc": f"{n:,} 条身价快照，最新 {r}"})
    r = one(con, "SELECT MAX(from_date) f FROM tm_player_injuries")["f"]
    n = one(con, "SELECT COUNT(*) n FROM tm_player_injuries")["n"]
    items.append({"ts": r, "level": "ok", "title": "伤病记录更新",
                  "desc": f"{n:,} 条伤病记录，最新起始日 {r}"})
    r = one(con, "SELECT MAX(created_at) c FROM predictions")["c"]
    n = one(con, "SELECT COUNT(*) n FROM predictions")["n"]
    items.append({"ts": (r or "")[:16], "level": "ok", "title": "预测批次写入",
                  "desc": f"predictions 共 {n:,} 条，最近写入 {r}"})
    return items


def build_gallery(con, team_slug, upcoming):
    """真实图表画廊：每张图的数据都由 SQL 现取，调模板自带的图表函数渲染。"""
    g = []

    # 1 球队 Elo 排名（真实 teams.elo_rating）
    top = q(con, "SELECT name, elo_rating FROM teams WHERE elo_rating IS NOT NULL ORDER BY elo_rating DESC LIMIT 10")
    g.append({"topic": "strength", "title": "球队 Elo 排名", "sub": "Top 10 · 真实库",
              "svg": col_js([(r["name"][:6], round(r["elo_rating"] - 1500), round(r["elo_rating"])) for r in top])})

    # 2 各联赛场均进球（真实 league_stats）
    ls = q(con, """SELECT league, season, goals_pg FROM league_stats
                   WHERE season = (SELECT MAX(season) FROM league_stats) AND goals_pg IS NOT NULL
                   ORDER BY goals_pg DESC LIMIT 8""")
    g.append({"topic": "standings", "title": "各联赛场均进球", "sub": f"赛季 {ls[0]['season'] if ls else '—'}",
              "svg": col_js([(r["league"][:4], round(r["goals_pg"], 2), round(r["goals_pg"], 2)) for r in ls])})

    # 3 射手榜（真实 player_radar.goals）
    sc = q(con, "SELECT name, goals FROM player_radar WHERE goals IS NOT NULL ORDER BY goals DESC LIMIT 8")
    g.append({"topic": "player", "title": "射手榜", "sub": "本赛季进球 · 真实库",
              "svg": col_js([(r["name"][:5], r["goals"], r["goals"]) for r in sc])})

    # 4 身价分档（真实分档计数）
    buckets = q(con, """SELECT CASE
            WHEN market_value >= 100000000 THEN '≥1亿€'
            WHEN market_value >= 50000000 THEN '5000万-1亿'
            WHEN market_value >= 20000000 THEN '2000-5000万'
            WHEN market_value >= 5000000 THEN '500-2000万'
            ELSE '<500万' END b, COUNT(*) n
        FROM player_radar WHERE market_value IS NOT NULL GROUP BY b ORDER BY MIN(market_value) DESC""")
    colors = ["#2f86e0", "#2aa3c9", "#c8871a", "#5b6f8c", "#b8c2cc"]
    g.append({"topic": "player", "title": "身价分档人数", "sub": "player_radar.market_value",
              "svg": "donut(" + js([{"label": r["b"], "value": r["n"], "color": colors[i % 5]}
                                    for i, r in enumerate(buckets)]) + ",170)"})

    # 5 胜平负占比（真实完赛结果）
    res = one(con, """SELECT SUM(home_goals > away_goals) h, SUM(home_goals = away_goals) d,
                             SUM(home_goals < away_goals) a
                      FROM matches WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL""")
    g.append({"topic": "result", "title": "胜平负占比", "sub": "全部完赛场次",
              "svg": "donut(" + js([{"label": "主胜", "value": res["h"], "color": "var(--accent)"},
                                    {"label": "平", "value": res["d"], "color": "#b8c2cc"},
                                    {"label": "客胜", "value": res["a"], "color": "var(--blue)"}]) + ",170)"})

    # 6 月度入库（真实 matches.date）
    mo = q(con, """SELECT substr(date,1,7) m, COUNT(*) n FROM matches
                   WHERE date >= date((SELECT MAX(date) FROM matches), '-390 day')
                   GROUP BY m ORDER BY m DESC LIMIT 12""")
    mo = list(reversed(mo))
    g.append({"topic": "matches", "title": "近 12 月比赛入库量", "sub": "matches.date 实测",
              "svg": "areaChart(" + js([r["n"] for r in mo]) + ",{labels:" + js([r["m"][2:] for r in mo]) +
                     ",height:180,width:520})"})

    # 7 联赛指标热力（真实 league_stats）
    lh = q(con, """SELECT league, goals_pg, xg_pg, home_win_pct, draw_pct, away_win_pct FROM league_stats
                   WHERE season = (SELECT MAX(season) FROM league_stats) AND goals_pg IS NOT NULL
                   ORDER BY goals_pg DESC LIMIT 6""")
    matrix = [[round(r[k] or 0, 2) for k in ("goals_pg", "xg_pg", "home_win_pct", "draw_pct", "away_win_pct")]
              for r in lh]
    g.append({"topic": "standings", "title": "联赛指标热力", "sub": "场均进球 / xG / 胜负率",
              "svg": "heatmap(" + js(matrix) + "," + js([r["league"][:4] for r in lh]) +
                     "," + js(["场均进球", "场均xG", "主胜%", "平局%", "客胜%"]) + ")"})

    # 8 防守强度（真实 team_radar.s_defense）
    df = q(con, "SELECT team, s_defense FROM team_radar WHERE s_defense IS NOT NULL ORDER BY s_defense DESC LIMIT 8")
    g.append({"topic": "defense", "title": "防守强度 Top 8", "sub": "team_radar 百分位",
              "svg": col_js([(r["team"][:6], round(r["s_defense"]), round(r["s_defense"])) for r in df])})

    # 9 伤病类型（真实 tm_player_injuries）
    inj = q(con, """SELECT injury_reason r, COUNT(*) n FROM tm_player_injuries
                    WHERE injury_reason IS NOT NULL GROUP BY r ORDER BY n DESC LIMIT 8""")
    g.append({"topic": "injury", "title": "伤病类型分布", "sub": "tm_player_injuries",
              "svg": col_js([(r["r"][:7], r["n"], r["n"]) for r in inj], color="var(--amber)")})

    # 10 模型准确率（真实 model_metrics）
    mm = q(con, "SELECT model, acc FROM model_metrics ORDER BY acc DESC LIMIT 8")
    g.append({"topic": "model", "title": "各模型样本外准确率", "sub": "model_metrics",
              "svg": col_js([(r["model"][:6], round(r["acc"], 2), round(r["acc"], 2)) for r in mm])})

    # 11 未来场次预测概率（真实 predictions）
    if upcoming:
        g.append({"topic": "model", "title": "未来场次主胜概率", "sub": f"{len(upcoming)} 场 · v2+v7 预测",
                  "svg": col_js([(u["home"][:5], u["prob"][0], f"{u['prob'][0]}%") for u in upcoming[:8]])})

    # 12 积分榜前列积分（真实 standings）
    st = q(con, """SELECT t.name, s.points FROM standings s JOIN teams t ON t.team_id = s.team_id
                   WHERE s.season = (SELECT MAX(season) FROM standings)
                   ORDER BY s.points DESC LIMIT 8""")
    g.append({"topic": "standings", "title": "积分榜前列积分", "sub": "最新赛季 standings",
              "svg": "areaChart(" + js([r["points"] for r in st]) +
                     ",{labels:" + js([r["name"][:4] for r in st]) + ",height:170,width:520})"})
    return g


def build_overview(con, meta, services):
    tables = [t["name"] for t in q(con, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")]
    empty_n = sum(1 for t in tables if one(con, f'SELECT COUNT(*) c FROM "{t}"')["c"] == 0)
    n_models = one(con, "SELECT COUNT(*) c FROM model_metrics")["c"]
    n_pred = one(con, "SELECT COUNT(*) c FROM predictions")["c"]
    n_future = one(con, "SELECT COUNT(*) c FROM predictions WHERE actual_result IS NULL")["c"]
    port_txt = " / ".join("{}{}".format(s["port"], "✓" if s["status"] == "ok" else "✗") for s in services)
    checks = [
        ["SQLite 数据库", "ok", f"{meta['db_mb']} MB · 只读挂载"],
        ["数据表完整度", "ok" if empty_n == 0 else "warn", f"{meta['nonempty']}/{meta['tables']} 张有数据"],
        ["比赛数据截止", "ok", str(meta["newest_match"])[:10]],
        ["模型评估记录", "ok", f"{n_models} 个方案"],
        ["预测批次", "ok", f"{n_pred} 条（含 {n_future} 条未来场次）"],
        ["服务端口探测", "ok" if all(s["status"] == "ok" for s in services) else "warn", port_txt],
    ]
    groups = [
        ("身价 · 转会 · 赛季", ["tm_player_market_value", "tm_player_seasons", "transfers"], "var(--accent)"),
        ("球员 · 阵容 · 伤病", ["player_radar", "players", "tm_player_injuries"], "#17539a"),
        ("比赛 · xG · 预测", ["matches", "understat_xg", "predictions", "standings"], "var(--blue)"),
    ]
    seen = {t for _, ts, _ in groups for t in ts}
    rest = [t["name"] for t in q(con, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'") if t["name"] not in seen]

    def cnt(ts):
        return sum(one(con, f'SELECT COUNT(*) c FROM "{t}"')["c"] for t in ts)
    segs = [{"label": lab, "value": cnt(ts), "color": col} for lab, ts, col in groups]
    segs.append({"label": "其他数据", "value": cnt(rest), "color": "#b8c2cc"})
    months = q(con, """SELECT substr(date,1,7) m, COUNT(*) n FROM matches
                       WHERE date >= (SELECT MAX(date) FROM matches) - 370 GROUP BY m ORDER BY m""")
    trend = [r["n"] for r in months]
    labels = [r["m"][2:] for r in months]
    return {"checks": checks, "segs": segs, "trend": trend, "trend_labels": labels,
            "total": sum(s["value"] for s in segs)}


def build_api_samples():
    """真实 API：从运行中的服务 8000 拉 openapi 与实际响应。"""
    try:
        with urllib.request.urlopen("http://127.0.0.1:8000/openapi.json", timeout=4) as r:
            spec = json.loads(r.read().decode("utf-8"))
    except Exception:
        return []
    picks = []
    for path, ops in spec.get("paths", {}).items():
        if "get" not in ops:
            continue
        desc = (ops["get"].get("summary") or ops["get"].get("description") or "").strip()
        params = [p for p in ops["get"].get("parameters", []) if p.get("required")]
        url = "http://127.0.0.1:8000" + path
        if params:
            if params[0].get("name") in ("limit", "n"):
                url += f"?{params[0]['name']}=3"
            else:
                continue
        try:
            with urllib.request.urlopen(url, timeout=8) as r:
                data = json.loads(r.read().decode("utf-8"))
        except Exception:
            continue
        txt = json.dumps(data, ensure_ascii=False)
        if len(txt) > 1400:
            if isinstance(data, list):
                data = data[:2]
            elif isinstance(data, dict):
                data = {k: (v[:2] if isinstance(v, list) else v) for k, v in list(data.items())[:6]}
        picks.append({"m": "GET", "p": path, "desc": desc or path, "res": data})
        if len(picks) >= 6:
            break
    return picks


# ---------------------------------------------------------------- 组装 JS

def build_js(con) -> tuple[str, dict]:
    meta = build_meta(con)
    services = build_services(meta)
    leagues, league_rows = build_leagues(con)

    # 先确定需要哪些球队 → 再生成 slug 表
    top_player_team_ids = [r["team_id"] for r in q(con, """
        SELECT team_id FROM player_radar WHERE market_value IS NOT NULL ORDER BY market_value DESC LIMIT 18""")]
    up_fixture_team_ids = [x for r in q(con, """
        SELECT m.home_team_id h, m.away_team_id a FROM predictions p JOIN matches m ON m.match_id = p.match_id
        WHERE p.actual_result IS NULL LIMIT 8""") for x in (r["h"], r["a"])]
    best_match = q(con, """
        SELECT m.home_team_id h, m.away_team_id a FROM matches m
        WHERE m.stats_json IS NOT NULL AND m.home_goals IS NOT NULL ORDER BY m.date DESC LIMIT 40""")
    md_ids = [x for r in best_match for x in (r["h"], r["a"])]
    # 实时比分(最近完赛) 与 历史交锋 用到的球队也必须进球队宇宙，否则视图取值会 undefined
    live_ids = [x for r in q(con, """
        SELECT m.home_team_id h, m.away_team_id a FROM matches m
        WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT 12""") for x in (r["h"], r["a"])]
    h2h_pool = q(con, """
        SELECT m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid,
               l.league_id lid
        FROM matches m JOIN leagues l ON l.league_id = m.league_id
        WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT 240""")
    h2h_ids = [x for r in h2h_pool for x in (r["hid"], r["aid"])]

    teams, team_slug = build_teams(con, set(top_player_team_ids) | set(up_fixture_team_ids) |
                                   set(md_ids) | set(live_ids) | set(h2h_ids))
    standings = build_standings(con, leagues, team_slug)
    players = build_players(con, team_slug)
    upcoming = build_upcoming(con, team_slug, leagues)
    match, sj = build_match(con, team_slug, leagues)
    preds = build_predictions(con)
    review = build_review_rows(con, preds, team_slug)
    modules = build_modules(con, meta)
    topics = build_topics(con)
    tables = build_tables(con)
    models = build_models(con, preds)
    ulog = build_update_log(con)
    gallery = build_gallery(con, team_slug, upcoming)
    overview = build_overview(con, meta, services)
    api_samples = build_api_samples()

    league_crest = {s: s for s in leagues}
    ticker, kpis, bars = build_home_extras(con, meta, preds, models, team_slug, leagues)

    parts = [
        "/* 徽标：优先真实 logo（构建时缓存到 assets/crests/<slug>.png）；缺 logo 的用生成式占位 PNG */",
        "window.ASSETS = {",
        "  crest: function (slug) { return 'assets/crests/' + slug + '.png'; },",
        "  league: function (slug) { return 'assets/leagues/' + slug + '.png'; },",
        "  logo: " + js({s: teams[s]["logo"] for s in teams if teams[s].get("logo")}) + ",",
        "};",
    ]
    parts += [
        "window.PAGES = " + js(PAGES) + ";",
        "window.SERVICES = " + js(services) + ";",
        "window.LEAGUES = " + js({s: {k: v for k, v in info.items()} for s, info in leagues.items()}) + ";",
        "window.TEAMS = " + js(teams) + ";",
        "window.STANDINGS = " + js(standings) + ";",
        "window.PLAYERS = " + js(players) + ";",
        "window.UPCOMING = " + js(upcoming) + ";",
        "window.MATCH = " + js(match) + ";",
        "window.MODULES = " + js(modules) + ";",
        "window.TOPICS = " + js(topics) + ";",
        "window.TABLES = " + js(tables) + ";",
        "window.MODELS = " + js(models) + ";",
        "window.UPDATE_LOG = " + js(ulog) + ";",
        "window.GALLERY = " + js([{k: v for k, v in g.items() if k != "svg"} for g in gallery]) + ";",
        "window.REVIEW = " + js(review) + ";",
        "window.PRED_STATS = " + js({k: preds[k] for k in ("n", "hits", "acc", "brier", "logloss")}) + ";",
        "window.OVERVIEW = " + js(overview) + ";",
        "window.API_SAMPLES = " + js(api_samples) + ";",
        "window.LIVE = " + js(build_live(con, team_slug, leagues)) + ";",
        "window.RECENT = " + js(build_recent(con, team_slug, leagues)) + ";",
        "window.H2H_DATA = " + js(_h2h_rows(h2h_pool, team_slug, leagues)) + ";",
        "window.FIRST_LEAGUE = " + js(next(iter(leagues))) + ";",
        "window.LIVE_STATS = " + js(build_live_stats(con, meta)) + ";",
        "window.PRED_MAP = " + js(build_pred_map(con, team_slug, leagues)) + ";",
        "window.PRED_MAP_SIZE = " + js(len(build_pred_map(con, team_slug, leagues))) + ";",
        "window.AGENT_KB = " + js(build_agent_kb(con, team_slug, leagues, preds, models)) + ";",        "/* 历史交锋：从真实完赛记录里筛出两队之间最近 4 场 */",
        "window.h2h = function (a, b) {",
        "  return (window.H2H_DATA || []).filter(function (r) {",
        "    return (r[2] === a && r[5] === b) || (r[2] === b && r[5] === a);",
        "  }).slice(0, 4);",
        "};",
        "window.MATCH_EXTRA = " + js(match["extra"] if match else {}) + ";",
        "window.HOME_KPIS = " + js(kpis) + ";",
        "window.TREND_BARS = " + js(bars) + ";",
        "window.SOURCE_META = " + js({
            "db": "data/database/football.db", "dbMb": meta["db_mb"], "tables": meta["tables"],
            "rows": meta["rows"], "newestMatch": meta["newest_match"],
            "builtBy": "scripts/build_console.py",
        }) + ";",
        "window.APP_META = " + js({
            "generatedBy": "build_console.py",
            "note": "全部数值由构建脚本从本地 SQLite 直读生成（matches/predictions/model_metrics/…），"
                    "未使用演示数据；队徽为各队真实 logo（数据源字段），缺失者用生成式占位图形。",
        }) + ";",
    ]
    return "\n".join(parts), {
        "meta": meta, "services": services, "leagues": leagues, "teams": teams, "standings": standings,
        "players": players, "upcoming": upcoming, "match": match, "preds": preds, "modules": modules,
        "topics": topics, "tables": tables, "models": models, "ulog": ulog, "gallery": gallery,
        "overview": overview, "api": api_samples, "review": review,
        "ticker": ticker, "kpis": kpis, "bars": bars,
    }


def lambda_map(teams):
    return {s: teams[s]["crest"] for s in teams}


def build_home_extras(con, meta, preds, models, team_slug, leagues):
    """首页快讯 / KPI / 趋势柱 —— 全部取真实值。"""
    lg = {r["league_id"]: r["name"] for r in q(con, "SELECT league_id, name FROM leagues")}
    recent = q(con, """
        SELECT m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid, m.league_id lid
        FROM matches m WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT 6""")
    ticker = []
    for r in recent:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a:
            continue
        ticker.append([lg.get(r["lid"], ""), "%s %d-%d %s" % (TEAM_NAME.get(h, h), r["hg"], r["ag"], TEAM_NAME.get(a, a)),
                       (r["date"] or "")[:10]])
    prod = next((m for m in models if m["status"] == "production"), models[0] if models else None)
    n_match = one(con, "SELECT COUNT(*) c FROM matches WHERE home_goals IS NOT NULL")["c"]
    kpis = [
        {"l": "完赛比赛", "v": n_match, "u": "场", "d": f"本地库累计 · 截止 {str(meta['newest_match'])[:10]}", "up": True},
        {"l": "球员样本", "v": one(con, "SELECT COUNT(*) c FROM player_radar")["c"], "u": "名",
         "d": "含能力百分位与身价", "up": True},
        {"l": "样本外准确率", "v": prod["acc"] * 100 if prod else 0, "u": "%",
         "d": f"{prod['name'] if prod else ''} · 严格样本外", "up": True, "fixed": 2},
        {"l": "数据表", "v": meta["tables"], "u": "张", "d": f"{meta['rows']:,} 行记录", "up": True},
    ]
    months = q(con, """SELECT substr(date,1,7) m, COUNT(*) n FROM matches
                       WHERE date >= date((SELECT MAX(date) FROM matches), '-175 day')
                       GROUP BY m ORDER BY m DESC LIMIT 6""")
    months = list(reversed(months))
    bars = [{"label": r["m"][5:] + "月", "value": r["n"], "display": str(r["n"])} for r in months]
    return ticker, kpis, bars


def build_live(con, team_slug, leagues, limit=8):
    rows = q(con, """
        SELECT m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid,
               l.league_id lid, l.name lname, m.attendance_dummy
        FROM matches m JOIN leagues l ON l.league_id = m.league_id
        WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?
    """ if False else """
        SELECT m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid,
               l.league_id lid, l.name lname
        FROM matches m JOIN leagues l ON l.league_id = m.league_id
        WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?
    """, (limit,))
    lg = {info["league_id"]: s for s, info in leagues.items()}
    out = []
    for r in rows:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a:
            continue
        out.append({"league": lg.get(r["lid"], ""), "home": h, "away": a, "hs": r["hg"], "as": r["ag"],
                    "min": 90, "events": (r["date"] or "")[:16], "date": (r["date"] or "")[:16]})
    return out


def build_recent(con, team_slug, leagues, limit=6):
    """实时比分页「最近完场」：真实完赛记录。"""
    rows = q(con, """
        SELECT m.date, m.home_goals hg, m.away_goals ag, m.home_team_id hid, m.away_team_id aid,
               l.league_id lid
        FROM matches m JOIN leagues l ON l.league_id = m.league_id
        WHERE m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
        ORDER BY m.date DESC LIMIT ?
    """, (limit,))
    lg = {info["league_id"]: s for s, info in leagues.items()}
    out = []
    for r in rows:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a:
            continue
        out.append({"date": (r["date"] or "")[:16], "league": lg.get(r["lid"], ""),
                    "home": h, "away": a, "hs": r["hg"], "as": r["ag"]})
    return out


def _h2h_rows(pool, team_slug, leagues):
    """历史交锋池：[日期, 联赛slug, 主队slug, 主队进球, 客队进球, 客队slug]。"""
    lg = {info["league_id"]: s for s, info in leagues.items()}
    out = []
    for r in pool:
        h, a = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not a or not lg.get(r["lid"]):
            continue
        out.append([(r["date"] or "")[:10], lg[r["lid"]], h, r["hg"], r["ag"], a])
    return out


def build_live_stats(con, meta):
    """实时比分页顶部四个指标：真实完赛数 / 数据截止日 / 当日场次 / 数据源。"""
    newest = meta.get("newest_match") or ""
    day = (newest or "")[:10]
    today = 0
    if day:
        r = one(con, "SELECT COUNT(*) c FROM matches WHERE substr(date, 1, 10) = ?", (day,))
        today = r["c"] if r else 0
    fin = one(con, "SELECT COUNT(*) c FROM matches WHERE home_goals IS NOT NULL AND away_goals IS NOT NULL")
    return {"newest": day, "today": today, "finished": fin["c"] if fin else 0, "source": "football-data.org"}


def build_pred_map(con, team_slug, leagues):
    """未赛场次的真实模型输出：{'home|away': {p:[主,平,客], model, conf, created, date, league}}。"""
    rows = q(con, """
        SELECT p.pred_home_win h, p.pred_draw d, p.pred_away_win a, p.model_version mv,
               p.created_at ca, m.date dt, m.home_team_id hid, m.away_team_id aid, l.league_id lid
        FROM predictions p JOIN matches m ON m.match_id = p.match_id
        JOIN leagues l ON l.league_id = m.league_id
        WHERE p.actual_result IS NULL
        ORDER BY m.date
    """)
    lg = {info["league_id"]: s for s, info in leagues.items()}
    out = {}
    for r in rows:
        h, aw = team_slug.get(r["hid"]), team_slug.get(r["aid"])
        if not h or not aw:
            continue
        hv, dv, av = r["h"] or 0, r["d"] or 0, r["a"] or 0
        out[f"{h}|{aw}"] = {
            "p": [round(hv * 100, 1), round(dv * 100, 1), round(av * 100, 1)],
            "model": r["mv"] or "", "conf": round(max(hv, dv, av), 4),
            "created": (r["ca"] or "")[:16], "date": (r["dt"] or "")[:16], "league": lg.get(r["lid"], ""),
        }
    return out


def build_agent_kb(con, team_slug, leagues, preds, models):
    """AI 分析页的问答知识库：全部字段取自真实库，供 agentReply() 直接引用。"""
    lg = {info["league_id"]: s for s, info in leagues.items()}
    fx = one(con, """
        SELECT p.pred_home_win h, p.pred_draw d, p.pred_away_win a, p.model_version mv,
               m.date dt, m.home_team_id hid, m.away_team_id aid
        FROM predictions p JOIN matches m ON m.match_id = p.match_id
        WHERE p.actual_result IS NULL ORDER BY m.date LIMIT 1
    """)
    A = B = None
    probs = None
    if fx:
        A, B = team_slug.get(fx["hid"]), team_slug.get(fx["aid"])
        probs = [round((fx["h"] or 0) * 100, 1), round((fx["d"] or 0) * 100, 1), round((fx["a"] or 0) * 100, 1)]

    def team_bits(slug):
        t = one(con, "SELECT name, elo_rating e, league_id lid FROM teams WHERE team_id = ?",
                (next((k for k, v in team_slug.items() if v == slug), None),))
        r = one(con, "SELECT goals_pg, conceded_pg, xg_pg, ppg, squad_value FROM team_radar WHERE team_id = ?",
                (next((k for k, v in team_slug.items() if v == slug), None),))
        if not t:
            return None
        return {"name": t["name"], "elo": t["e"], "league": (lg.get(t["lid"], "") or "").replace("-", " "),
                "gf": r["goals_pg"], "ga": r["conceded_pg"], "xg": r["xg_pg"], "ppg": r["ppg"]} if r else \
               {"name": t["name"], "elo": t["e"], "league": "", "gf": None, "ga": None, "xg": None, "ppg": None}

    a1, a2 = team_bits(A), team_bits(B)
    top = q(con, """
        SELECT p.name, p.name_en, p.market_value mv, r.apps, r.goals, r.assists, r.minutes, t.name tn
        FROM player_radar r JOIN players p ON p.player_id = r.player_id
        LEFT JOIN teams t ON t.team_id = p.team_id
        ORDER BY r.goals DESC LIMIT 2
    """)
    inj = one(con, "SELECT COUNT(*) c FROM tm_player_injuries")["c"]
    inj_a = 0
    if A:
        inj_a = one(con, """
            SELECT COUNT(*) c FROM tm_player_injuries i
            JOIN players p ON p.tm_player_id = i.player_id WHERE p.team_id = ?
        """, (next((k for k, v in team_slug.items() if v == A), None),))["c"]
    tb = one(con, "SELECT COUNT(*) c FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'")["c"]
    row_total = sum(one(con, f'SELECT COUNT(*) c FROM "{r["name"]}"')["c"]
                    for r in q(con, "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"))
    prod = next((m for m in models if m["status"] == "production"), models[0] if models else {})

    def pct(v):
        return f"{v}%"

    opening_q = f"帮我对比{a1['name']}和{a2['name']}，并给出这场比赛的模型输出。" if a1 and a2 else "系统里现在有哪些数据？"
    opening_a = ""
    if a1 and a2 and probs:
        opening_a = (f"我调用了<b>球队数据</b>与<b>比赛预测</b>两个工具。{a1['name']} Elo {a1['elo']}，场均进球 "
                     f"{a1['gf']}、场均失球 {a1['ga']}、场均 xG {a1['xg']}；{a2['name']} Elo {a2['elo']}，场均进球 "
                     f"{a2['gf']}、场均失球 {a2['ga']}、场均 xG {a2['xg']}。模型（{fx['mv']}）对 {fx['dt'][:16]} 这场比赛输出 "
                     f"<b>{a1['name']}胜 {pct(probs[0])} · 平 {pct(probs[1])} · {a2['name']}胜 {pct(probs[2])}</b>，"
                     f"部署模型样本外准确率 {round((prod.get('acc') or 0) * 100, 2)}%。")
    else:
        opening_a = (f"我调用了<b>数据查询</b>工具。当前库内 {tb} 张表、{row_total:,} 行记录，覆盖比赛、球队、球员、"
                     f"预测与模型评估；未赛 fixture 的模型输出 {len([1]) if probs else 0} 条。")
    player_a = ""
    if len(top) >= 2:
        p1, p2 = top[0], top[1]
        player_a = (f"已检索球员库（player_radar × players）。{p1['name']}（{p1['tn']}）出 {p1['apps']} 场，"
                    f"{p1['goals']} 球 {p1['assists']} 助攻，身价 €{round((p1['mv'] or 0) / 1e6, 1)}M；"
                    f"{p2['name']}（{p2['tn']}）出 {p2['apps']} 场，{p2['goals']} 球 {p2['assists']} 助攻，"
                    f"身价 €{round((p2['mv'] or 0) / 1e6, 1)}M。")
    predict_a = ""
    if a1 and a2 and probs:
        predict_a = (f"已运行 {fx['mv']}。{a1['name']} vs {a2['name']}（{fx['dt'][:16]}）："
                     f"<b>{pct(probs[0])} / {pct(probs[1])} / {pct(probs[2])}</b>。"
                     f"该模型在 model_metrics 中的记录与部署模型 {prod.get('name', '')} 的样本外准确率 "
                     f"{round((prod.get('acc') or 0) * 100, 2)}%、LogLoss {prod.get('logloss')} 可对照查看。"
                     f"注意：模型只输出胜平负三路概率，不输出比分分布与大小球。")
    inj_a_name = a1["name"] if a1 else ""
    injury_a = (f"已查询 tm_player_injuries（共 {inj} 条伤病记录，按 tm_player_id 映射到本库球员）。"
                f"{inj_a_name} 下可匹配到 {inj_a} 条伤病记录。" if A else f"已查询 tm_player_injuries，共 {inj} 条记录。")
    default_a = (f"已用<b>数据查询</b>工具在 {tb} 张数据表（{row_total:,} 行）中检索。可以直接问我：某队近期状态、"
                 f"两名球员对比、某场比赛的模型输出或伤病记录。")
    chips = []
    if a1 and a2:
        chips = [f"对比 {a1['name']} 与 {a2['name']}", f"{top[0]['name']} 的赛季数据" if top else "球员数据",
                 f"{a1['name']} vs {a2['name']} 的模型输出", f"{a1['name']} 有哪些伤病记录"]
    placeholder = f"问点什么，例如：{chips[0]}？" if chips else "问点什么，例如：库里有多少场比赛？"
    return {"opening": {"q": opening_q, "a": opening_a, "tools": ["球队数据", "比赛预测"]},
            "team": opening_a, "player": player_a, "predict": predict_a, "injury": injury_a,
            "default": default_a, "chips": chips, "placeholder": placeholder}


PAGES = [
    {"slug": "home", "label": "首页概览", "port": 8501, "group": "用户端",     "desc": "英雄版块 · 关键指标 · 核心功能 · 数据分布", "icon": "home"},
    {"slug": "leagues", "label": "联赛数据", "port": 8501, "group": "用户端",
     "desc": "积分榜 · 球队实力 Elo · 各赛事技术风格", "icon": "trophy"},
    {"slug": "teams", "label": "球队分析", "port": 8501, "group": "用户端",
     "desc": "双队对比 · 能力雷达 · 近期状态 · 历史交锋", "icon": "shield"},
    {"slug": "players", "label": "球员分析", "port": 8501, "group": "用户端",
     "desc": "球员检索 · 能力雷达 · 伤病转会 · 身价走势", "icon": "user"},
    {"slug": "match", "label": "比赛详情", "port": 8501, "group": "用户端",
     "desc": "技术统计 · 阵容名单 · 伤停 · 数据来源", "icon": "ball"},
    {"slug": "predict", "label": "比赛预测", "port": 8501, "group": "用户端",
     "desc": "单场预测 · 批量预测 · 历史预测复盘", "icon": "target"},
    {"slug": "agent", "label": "AI 智能分析", "port": 8501, "group": "用户端",
     "desc": "自然语言问答 · 6 个数据工具 · 深度分析报告", "icon": "spark"},
    {"slug": "live", "label": "实时比分", "port": 8501, "group": "用户端",
     "desc": "最近完赛 · 比分与统计 · 服务状态", "icon": "activity"},
    {"slug": "overview", "label": "数据概览", "port": 8502, "group": "管理后台",
     "desc": "模块数据量 · 数据分布 · 系统状态检查", "icon": "grid"},
    {"slug": "browse", "label": "数据浏览", "port": 8502, "group": "管理后台",
     "desc": "10 个数据主题 · 真实图表画廊", "icon": "layers"},
    {"slug": "api", "label": "API 接口测试", "port": 8502, "group": "管理后台",
     "desc": "RESTful 接口在线调试与响应查看", "icon": "plug"},
    {"slug": "database", "label": "数据库管理", "port": 8502, "group": "管理后台",
     "desc": "33 张数据表 · 字段结构 · 行数统计", "icon": "database"},
    {"slug": "update", "label": "数据更新控制", "port": 8502, "group": "管理后台",
     "desc": "数据源状态 · 最近写入 · 更新日志", "icon": "refresh"},
    {"slug": "models", "label": "模型管理", "port": 8502, "group": "管理后台",
     "desc": "样本外评估 · 混淆矩阵 · 校准曲线 · 特征重要度", "icon": "cpu"},
]


# ---------------------------------------------------------------- 登录闸门
# 打开控制台先登录: 左边账号密码, 右边扫码(手机确认后电脑自动进入)。
# 令牌由后端 /api/auth 签发, 存在 localStorage.fauth; 「真实系统」按钮会把
# 令牌一并带给 Streamlit 端, 那边再向后端核对一次。

GATE_CSS = r"""
/* ---------------- 登录闸门(由 build_console.py 注入) ---------------- */
.gate{position:fixed;inset:0;z-index:120;display:flex;align-items:center;justify-content:center;
  padding:26px;overflow:auto;background:
    radial-gradient(760px 420px at 78% -12%, rgba(47,134,224,.12), transparent 62%),
    radial-gradient(560px 380px at -6% 108%, rgba(63,124,168,.10), transparent 64%),
    var(--bg)}
.gate[hidden]{display:none}   /* 覆盖上面的 display:flex, 否则隐藏后仍会挡住点击 */
.gate-inner{width:100%;max-width:880px;margin:auto}
.gate-brand{display:flex;align-items:center;gap:12px;margin-bottom:20px}
.gate-brand .m{width:38px;height:38px;border-radius:11px;background:var(--accent);color:var(--accent-ink);
  display:flex;align-items:center;justify-content:center;font-size:20px;font-weight:800;flex:none}
.gate-brand b{font-size:16px;font-weight:700}
.gate-brand small{display:block;font:500 10px/1.6 var(--font-mono);letter-spacing:.2em;
  color:var(--text-3);text-transform:uppercase}
.gate-msg{margin:0;font-size:13px;line-height:1.85;color:var(--text-2)}
.gate-msg.is-err{color:var(--red)}
.gate-foot{margin-top:16px;font:500 10.5px/1.8 var(--font-mono);color:var(--text-3);letter-spacing:.06em}
.gate-foot a{color:var(--accent);text-decoration:none;border-bottom:1px solid rgba(47,134,224,.35)}
.gate-foot a:hover{border-bottom-color:var(--accent)}
.who{display:inline-flex;align-items:center;gap:9px;height:34px;padding:0 10px;
  border:1px solid var(--line);border-radius:var(--radius-pill);background:var(--panel-2)}
.who b{font-size:12.5px;font-weight:600}
.who i{font-style:normal;font:500 10px/1 var(--font-mono);letter-spacing:.1em;color:var(--text-3);text-transform:uppercase}
.who-out{border:0;background:transparent;color:var(--text-3);font:600 11.5px/1 inherit;cursor:pointer;padding:0 4px}
.who-out:hover{color:var(--red)}
"""

GATE_HTML = r"""
<div class="gate" id="gate">
  <div class="gate-inner">
    <div class="gate-brand">
      <span class="m">&#9917;</span>
      <span><b>足球数据分析与 AI 预测系统 · 控制台</b><small>Checking your session</small></span>
    </div>
    <p class="gate-msg" id="gMsg">正在检查登录状态…</p>
    <div class="gate-foot" id="gFoot">没有自动跳转？<a href="login.html" id="gToLogin">前往登录页 login.html</a></div>
  </div>
</div>
"""

GATE_JS = r"""
<script>/* 登录闸门: 控制台只负责会话检查; 登录界面已换成用户新做的 login.html(同源, localStorage.fauth 互通) */
(function () {
  var HOST = location.hostname;
  var API = (HOST === '127.0.0.1' || HOST === 'localhost' || HOST === '')
    ? 'http://127.0.0.1:8000' : ('http://' + HOST + ':8000');
  var KEY = 'fauth';
  var gate = document.getElementById('gate');
  var msg = document.getElementById('gMsg');

  function saved() { try { return JSON.parse(localStorage.getItem(KEY) || 'null'); } catch (e) { return null; } }
  function token() { var s = saved(); return (s && s.token) ? s.token : ''; }
  function dropToken() { try { localStorage.removeItem(KEY); } catch (e) {} }

  // 未登录/会话失效 -> 整页交给登录页; 登录成功后由 login.html 按 ?next= 回到这里(带原 #hash)
  function selfName() { return location.pathname.replace(/^.*\//, '') || 'index.html'; }
  function toLogin(why) {
    var next = selfName() + location.hash;
    location.replace('login.html?next=' + encodeURIComponent(next) + (why ? '&why=' + why : ''));
  }

  // 会话通过后的唯一出口: 账号密码与扫码两条路径都汇到这里
  function enter(user) {
    gate.hidden = true;
    var box = document.getElementById('whoBox');
    if (!box) return;
    box.hidden = false;
    document.getElementById('whoName').textContent = user.display_name || user.username;
    document.getElementById('whoRole').textContent = (user.role === 'admin') ? 'ADMIN' : 'USER';
    document.getElementById('whoOut').onclick = function () {
      fetch(API + '/api/auth/logout', {method: 'POST',
        headers: {'Authorization': 'Bearer ' + token()}}).catch(function () {});
      dropToken();
      location.replace('login.html');
    };
  }

  function showGate(text, isErr) {
    gate.hidden = false;
    if (text) { msg.textContent = text; msg.className = 'gate-msg' + (isErr ? ' is-err' : ''); }
    // 「前往登录页」始终带着本页作为回跳目标, 免得管理员在后台被拦下后点过去又落到用户端
    var link = document.getElementById('gToLogin');
    if (link) { link.href = 'login.html?next=' + encodeURIComponent(selfName() + location.hash); }
  }

  (function boot() {
    var t = token();
    if (!t) { toLogin(''); return; }
    fetch(API + '/api/auth/me', {headers: {'Authorization': 'Bearer ' + t}})
      .then(function (r) { if (!r.ok) throw new Error('bad'); return r.json(); })
      .then(function (j) {
        if (j && j.user) { enter(j.user); return; }
        dropToken();
        toLogin('expired');
      })
      .catch(function () {
        // 接口没起来时不要把人推到登录页再卡一次: 就地说明原因
        showGate('连不上接口 ' + API + '（请先运行 scripts\\start_all.ps1 启动服务）', true);
      });
  })();
})();
</script>
"""


# ---------------------------------------------------------------- 模板替换

def data_block_bounds(tpl: str):
    start = tpl.index("window.ASSETS = {")
    # 数据块起点前是 <script> 注释头
    head = tpl.rindex("<script>", 0, start)
    end = tpl.index("</script>", start)
    return head, end


def apply_patches(tpl: str, info: dict, js_block: str) -> str:
    data = info
    total = data["overview"]["total"]
    patches = []

    def rep(old, new, label, count=1):
        patches.append((old, new, label, count))

    # 1) 数据层整块替换
    head, end = data_block_bounds(tpl)
    tpl = (tpl[:head] +
           "<script>/* ============================================================\n"
           "   数据层 — 真实数据（由 scripts/build_console.py 从本地 SQLite 直读生成）\n"
           "   覆盖：联赛 / 球队 / 积分榜 / 球员 / 预测 / 比赛详情 / 数据表 / 模型评估\n"
           "   ============================================================ */\n" +
           js_block + "\n</script>" + tpl[end + len("</script>"):])

    # 2) 顶栏「演示数据」徽标 → 真实数据
    rep('<span class="demo-badge" title="界面为演示原型，分析数值为示例数据">演示数据</span>',
        '<span class="demo-badge is-real" title="本页所有数值均由 scripts/build_console.py 从本地 SQLite 直读生成">真实数据</span>',
        "顶栏徽标")

    # 3) 真实总量替换演示总量
    rep("${fmtInt(1940000)}", "${fmtInt(window.SOURCE_META.rows)}", "总量副标题")
    rep("(s.value / 1940000 * 100)", "(s.value / window.SOURCE_META.rows * 100)", "总量比例")

    # 4) 演示口径说明 → 真实数据来源
    rep("伤停信息为演示数据，接口来自伤病记录表 injuries。",
        "伤停取自 tm_player_injuries（Transfermarkt 伤病记录，按 tm_player_id 映射到本队）。", "伤停口径")

    # 5) 概览页硬编码检查项 / 数据分布 / 趋势 → 真实值
    rep("""      const checks = [
        ['数据源连接', 'ok', '3/3 在线'],
        ['数据库连接池', 'ok', '12 / 20 使用中'],
        ['外部 API 配额', 'warn', '剩余 38%'],
        ['模型服务', 'ok', 'v4 · 延迟 42ms'],
        ['定时同步任务', 'ok', '下次 06:00'],
        ['磁盘占用', 'ok', '128 GB / 512 GB']
      ];""",
        "      const checks = window.OVERVIEW.checks;", "概览检查项")
    rep("""      const segs = [
        { label: '比赛事件', value: 964000, color: 'var(--accent)' },
        { label: '传球数据', value: 620000, color: '#3a6f9e' },
        { label: '球员统计', value: 145600, color: 'var(--blue)' },
        { label: '其他数据', value: 210400, color: '#cbd5df' }
      ];""",
        "      const segs = window.OVERVIEW.segs;", "概览数据分布")
    rep("""${areaChart([38, 41, 45, 44, 52, 49, 58, 61, 57, 68, 74, 82], { labels: ['W1', '', '', 'W4', '', '', 'W7', '', '', 'W10', '', 'W12'], he""",
        """${areaChart(window.OVERVIEW.trend, { labels: window.OVERVIEW.trend_labels, he""", "概览入库趋势")
    rep("<span class=\"sub\">近 12 周 · 万条</span>", "<span class=\"sub\">近 12 月 · 场（matches.date 实测）</span>", "趋势副标题")

    # 5b) 球队指标 metrics() → 真实 team_radar（原实现用 Elo 反推，属合成值）
    start = tpl.index("  function metrics(slug) {")
    end = tpl.index("  function teamLine(slug) {")
    real_metrics = """  function metrics(slug) {
    const t = T[slug] || {};
    const s = standingOf(slug);
    const se = t.season || {};
    const r = t.radar || {};
    const p = (s ? s.row[1] + s.row[2] + s.row[3] : 0) || se.matches || 0;
    const gfP = se.goals_pg != null ? se.goals_pg : (s && p ? +(s.row[4] / p).toFixed(2) : 0);
    const gaP = se.conceded_pg != null ? se.conceded_pg : (s && p ? +(s.row[5] / p).toFixed(2) : 0);
    return {
      gfP: gfP, gaP: gaP, p: p,
      ppg: se.ppg != null ? se.ppg : 0,
      shots: se.shots_pg != null ? se.shots_pg : 0,
      xgF: se.xg_pg != null ? se.xg_pg : 0,
      xgA: se.xga_pg != null ? se.xga_pg : 0,
      squadValue: se.squad_value != null ? se.squad_value / 1e6 : 0,
      radar: {
        进攻: r.s_attack || 0, 防守: r.s_defense || 0, 统治力: r.s_dominance || 0,
        纪律: r.s_discipline || 0, 身价: r.s_value || 0, 经验: r.s_experience || 0
      }
    };
  }

"""
    tpl = tpl[:start] + real_metrics + tpl[end:]

    # 5c) 雷达维度标签 → 真实 team_radar / player_radar 维度
    rep("radar(['进攻', '防守', '控球', '定位球', '体能', '经验']",
        "radar(['进攻', '防守', '统治力', '纪律', '身价', '经验']", "球队雷达标签", count=0)
    rep("['进攻', '防守', '控球', '定位球', '体能', '经验']",
        "['进攻', '防守', '统治力', '纪律', '身价', '经验']", "球队雷达标签(数组)")
    rep("['射门', '传球', '盘带', '防守', '速度', '身体']",
        "['进球', '助攻', '参与', '出场', '纪律', '身价']", "球员雷达标签")

    # 5d) 首页 hero：预测比分 → 真实模型倾向；场均指标 → 真实值
    rep("<span class=\"tag g\">预测比分 ${m.score}</span>",
        "<span class=\"tag g\">模型倾向 ${m.result}</span>", "hero 模型倾向")
    rep("""              <dt>场均进球</dt><dd>${hm.gfP.toFixed(2)} / ${am.gfP.toFixed(2)}</dd>
              <dt>场均失球</dt><dd>${hm.gaP.toFixed(2)} / ${am.gaP.toFixed(2)}</dd>
              <dt>xG 预期进球</dt><dd>${hm.xgF} / ${am.xgF}</dd>
              <dt>传球成功率</dt><dd>${hm.passAcc.toFixed(0)}% / ${am.passAcc.toFixed(0)}%</dd>""",
        """              <dt>场均进球</dt><dd>${Number(hm.gfP).toFixed(2)} / ${Number(am.gfP).toFixed(2)}</dd>
              <dt>场均失球</dt><dd>${Number(hm.gaP).toFixed(2)} / ${Number(am.gaP).toFixed(2)}</dd>
              <dt>场均 xG</dt><dd>${Number(hm.xgF).toFixed(2)} / ${Number(am.xgF).toFixed(2)}</dd>
              <dt>场均积分</dt><dd>${Number(hm.ppg).toFixed(2)} / ${Number(am.ppg).toFixed(2)}</dd>""", "hero 均场指标")

    # 5e) 首页快讯 → 真实最近完赛
    s0 = tpl.index("  const HOME_TICKER = [")
    e0 = tpl.index("  ];", s0) + 4
    tick = [t for t in data.get("ticker", [])]
    tpl = tpl[:s0] + "  const HOME_TICKER = " + js(tick) + ";\n" + tpl[e0:]

    # 5f) 首页 KPI → 真实规模与模型指标
    rep("""      const kpis = [
        { l: '收录比赛', v: 12840, u: '场', d: '+5.8% 本月', up: true },
        { l: '球员样本', v: 5200, u: '名', d: '+3.4% 本月', up: true },
        { l: '预测准确率', v: 55.1, u: '%', d: '+0.6pp 环比', up: true, fixed: 1 },
        { l: '在线模型', v: 4, u: '个', d: 'v4 生产中', up: true }
      ];""",
        "      const kpis = window.HOME_KPIS;", "首页 KPI")

    # 5g) 首页入库趋势柱状 → 真实月度场次
    rep("""              ${columnChart([
                { label: '10月', value: 62, display: '62' },
                { label: '11月', value: 71, display: '71' },
                { label: '12月', value: 58, display: '58' },
                { label: '1月', value: 84, display: '84' },
                { label: '2月', value: 92, display: '92' },
                { label: '3月', value: 96, display: '96' }
              ], { width: 560, height: 210 })}""",
        "              ${columnChart(window.TREND_BARS, { width: 560, height: 210 })}", "首页趋势图")
    rep("<h3>数据入库趋势</h3><span class=\"sub\">近 6 个月 · 万条</span>",
        "<h3>数据入库趋势</h3><span class=\"sub\">近 6 个月 · 场（matches.date 实测）</span>", "首页趋势副标题")

    # 5h) fixtureRow：演示比分 → 真实模型倾向
    rep("'<span class=\"mono\" style=\"font-weight:600;flex:none;padding:0 6px\">' + m.score + '</span>' +",
        "'<span class=\"tag g\" style=\"flex:none;margin:0 6px\">' + m.result + '</span>' +", "fixtureRow 倾向")

    # 6) 数据浏览画廊 → 真实图表
    start = tpl.index("  const GALLERY = [")
    end = tpl.index("  function galleryGrid(topic)")
    real_gallery = "  const GALLERY = [\n" + "\n".join(
        "    { topic: %s, title: %s, sub: %s, svg: () => %s}," % (js(g["topic"]), js(g["title"]), js(g["sub"]), g["svg"])
        for g in data["gallery"]) + "\n  ];\n"
    tpl = tpl[:start] + real_gallery + tpl[end:]
    rep("全部 · ${GALLERY.length} 张", "全部 · ${GALLERY.length} 张真实图表", "画廊 chips")

    # 7) 历史复盘 → 真实回测行
    start = tpl.index("  function historyReview() {")
    end = tpl.index("  window.VIEWS.predict = {")
    real_review = """  function historyReview() {
    const rows = window.REVIEW;
    const S = window.PRED_STATS;
    const hits = rows.filter(r => r[6]).length;
    return `<div class="od-stack" style="--od-gap:16px">
      <div class="grid cols-4">
        <div class="panel"><div class="stat"><span class="stat-label">回测样本</span><span class="stat-value">${count(S.n)}</span><span class="stat-foot dim">predictions 有实际结果</span></div></div>
        <div class="panel"><div class="stat"><span class="stat-label">命中率</span><span class="stat-value">${count(S.acc, 2)}<span class="unit">%</span></span><span class="stat-foot dim">含训练期重叠，仅作参考</span></div></div>
        <div class="panel"><div class="stat"><span class="stat-label">Brier 分数</span><span class="stat-value">${S.brier}</span><span class="stat-foot dim">全量回测实算 · 越低越好</span></div></div>
        <div class="panel"><div class="stat"><span class="stat-label">对数损失</span><span class="stat-value">${S.logloss}</span><span class="stat-foot dim">同批次实算 LogLoss</span></div></div>
      </div>
      <div class="panel">
        <div class="panel-head"><h3>近期复盘</h3><span class="sub">预测 vs 实际 · 本页 ${hits}/${rows.length} 命中</span></div>
        <div class="panel-body flush table-wrap">
          <table class="tbl"><thead><tr><th>日期</th><th>对阵</th><th class="num">比分</th><th>预测</th><th>实际</th><th>结果</th><th class="num">最高概率</th></tr></thead>
          <tbody>${rows.map(r => `<tr>
            <td class="dim mono">${r[0].slice(5)}</td>
            <td><div class="team-cell">${T[r[1]].name}<span class="dim">vs</span>${T[r[2]].name}</div></td>
            <td class="num mono">${r[3]}</td>
            <td><span class="tag">${r[4]}</span></td>
            <td><span class="tag">${r[5]}</span></td>
            <td><span class="tag ${r[6] ? 'g' : 'r'}">${r[6] ? '命中' : '未中'}</span></td>
            <td class="num">${r[7].toFixed(2)}</td>
          </tr>`).join('')}</tbody></table>
        </div>
      </div>
    </div>`;
  }

"""
    tpl = tpl[:start] + real_review + tpl[end:]

    # 8) 单场/批量预测默认场次 → 真实未来场次
    first = data["upcoming"][0] if data["upcoming"] else {"home": "", "away": ""}
    rep("singlePrediction('man-city', 'arsenal')",
        f"singlePrediction({js(first['home'])}, {js(first['away'])})", "预测默认场次", count=2)

    # 9) 模型详情：真实混淆矩阵 / 校准 / 特征 / 显著性
    start = tpl.index("  function modelDetail(m) {")
    end = tpl.index("  window.VIEWS.models = {")
    con = connect()
    cm_rows = q(con, "SELECT actual, predicted, count FROM model_confusion")
    labels = ["主胜", "平", "客胜"]
    cm = [[0] * 3 for _ in range(3)]
    for r in cm_rows:
        try:
            i, j = labels.index(r["actual"]), labels.index(r["predicted"])
            cm[i][j] = r["count"]
        except ValueError:
            pass
    cal = q(con, "SELECT outcome, predicted, actual, n FROM model_calibration")
    bins = [{"pred": round(r["predicted"], 3), "actual": round(r["actual"], 3), "count": r["n"]} for r in cal]
    feats = q(con, "SELECT feature, importance FROM feature_importance ORDER BY importance DESC LIMIT 8")
    con.close()
    prod = next((m for m in data["models"] if m["status"] == "production"), data["models"][0])
    real_detail = """  function modelDetail(m) {
    const bins = %s;
    const cm = %s;
    const feats = %s;
    return `
      <div class="od-stack" style="--od-gap:16px">
        <div class="grid cols-4">
          <div class="panel"><div class="stat"><span class="stat-label">样本外准确率</span><span class="stat-value">${(m.acc * 100).toFixed(2)}<span class="unit">%%</span></span><span class="stat-foot dim">${m.test_n} 场样本外</span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">LogLoss</span><span class="stat-value">${m.logloss.toFixed(4)}</span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">平局召回</span><span class="stat-value">${m.draw_recall.toFixed(1)}<span class="unit">%%</span></span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">Macro F1</span><span class="stat-value">${m.f1.toFixed(4)}</span></div></div>
        </div>
        <div class="split">
          <div class="panel">
            <div class="panel-head"><h3>混淆矩阵</h3><span class="sub">主胜 / 平 / 客胜 · %s 场</span></div>
            <div class="panel-body">${confusion(cm, ['主胜', '平', '客胜'])}
              <div class="hintline" style="margin-top:12px">对角线为正确预测；平局（中列）误分最多，是分类难点。</div></div>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>校准曲线</h3><span class="sub">预测概率 vs 实际频率 · model_calibration</span></div>
            <div class="panel-body">${calibChart(bins)}</div>
          </div>
        </div>
        <div class="split">
          <div class="panel">
            <div class="panel-head"><h3>特征重要度</h3><span class="sub">feature_importance · Top 8</span></div>
            <div class="panel-body od-stack" style="--od-gap:14px">
              ${feats.map(f => meter(f[0], (f[1] / feats[0][1]) * 100, { display: (f[1] * 100).toFixed(2) + '%%' })).join('')}
            </div>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>部署口径</h3><span class="sub">当前线上模型</span></div>
            <div class="panel-body od-stack" style="--od-gap:14px">
              <div class="kv">
                <dt>部署模型</dt><dd>%s</dd>
                <dt>样本外准确率</dt><dd>%.2f%%</dd>
                <dt>LogLoss</dt><dd>%.4f</dd>
                <dt>预测写入</dt><dd>predictions 表（含未来场次）</dd>
              </div>
              <div class="hintline">模型指标来自 model_metrics（11 个方案，各 %s 场样本外）；回测 Brier %.4f 由 predictions 实际结果实算。</div>
            </div>
          </div>
        </div>
      </div>`;
  }

""" % (js(bins), js(cm), js([[f["feature"], round(f["importance"], 5)] for f in feats]),
       f"{prod['test_n']}", prod["name"], prod["acc"] * 100, prod["logloss"], f"{prod['test_n']}",
       data["preds"]["brier"])
    tpl = tpl[:start] + real_detail + tpl[end:]

    # 10) API 测试页 → 真实接口与真实响应（构建时从 127.0.0.1:8000 实拉）
    samples = data["api"]
    if not samples:
        samples = [{"m": "GET", "p": "/openapi.json",
                    "desc": "构建时 8000 端口未响应 —— 请先启动 API 服务再重新构建",
                    "res": {"hint": "python scripts/build_console.py"}}]
        print("  [warn] API 服务 8000 未响应，接口样例使用占位说明")
    s0 = tpl.index("  const ENDPOINTS = [")
    e0 = tpl.index("];", s0) + 2
    api_js = "  const ENDPOINTS = [\n" + "\n".join(
        "    { m: %s, p: %s, desc: %s, res: () => (%s) }," % (js(a["m"]), js(a["p"]), js(a["desc"]), js(a["res"]))
        for a in samples) + "\n  ];"
    tpl = tpl[:s0] + api_js + tpl[e0:]

    # 11) 球队分析 compareView：演示指标 → 真实 team_radar / 真实历史交锋
    rep("""    const rows = [
      ['场均进球', hm.gfP.toFixed(2), am.gfP.toFixed(2)],
      ['场均失球', hm.gaP.toFixed(2), am.gaP.toFixed(2)],
      ['控球率', hm.poss.toFixed(1) + '%', am.poss.toFixed(1) + '%'],
      ['预期进球 xG', hm.xgF, am.xgF],
      ['场均射门', hm.shots, am.shots],
      ['传球成功率', hm.passAcc.toFixed(0) + '%', am.passAcc.toFixed(0) + '%']
    ];""",
        """    const rows = [
      ['场均进球', hm.gfP.toFixed(2), am.gfP.toFixed(2)],
      ['场均失球', hm.gaP.toFixed(2), am.gaP.toFixed(2)],
      ['场均 xG', hm.xgF.toFixed(2), am.xgF.toFixed(2)],
      ['场均射门', hm.shots.toFixed(1), am.shots.toFixed(1)],
      ['场均积分', hm.ppg.toFixed(2), am.ppg.toFixed(2)],
      ['球队身价（M€）', hm.squadValue.toFixed(1), am.squadValue.toFixed(1)]
    ];""", "球队对比指标")

    rep("""    const h2h = [
      ['2025-11-02', 'premier-league', away, 1, 1, home],
      ['2025-04-06', 'premier-league', home, 2, 0, away],
      ['2024-12-14', 'premier-league', away, 2, 2, home],
      ['2024-05-19', 'premier-league', home, 1, 2, away]
    ];""",
        "    const h2h = window.h2h(home, away);", "历史交锋")

    rep("standingOf(s) ? standingOf(s).league : 'premier-league'",
        "standingOf(s) ? standingOf(s).league : window.FIRST_LEAGUE", "联赛兜底键", count=2)

    rep("""                <dt>进攻</dt><dd>${hm.radar.进攻} / ${am.radar.进攻}</dd>
                <dt>防守</dt><dd>${hm.radar.防守} / ${am.radar.防守}</dd>
                <dt>经验</dt><dd>${hm.radar.经验} / ${am.radar.经验}</dd>""",
        """                <dt>进攻</dt><dd>${hm.radar.进攻} / ${am.radar.进攻}</dd>
                <dt>防守</dt><dd>${hm.radar.防守} / ${am.radar.防守}</dd>
                <dt>统治力</dt><dd>${hm.radar.统治力} / ${am.radar.统治力}</dd>
                <dt>身价</dt><dd>${hm.radar.身价} / ${am.radar.身价}</dd>""", "雷达旁指标")

    top2 = sorted(data["teams"].items(), key=lambda kv: -(kv[1].get("elo") or 0))[:2]
    rep("compareView('man-city', 'liverpool')",
        f"compareView({js(top2[0][0])}, {js(top2[1][0])})", "球队对比默认对")

    # 12) 实时比分页 → 真实完赛记录（原实现含演示 KPI、演示比分与假比分推进）
    start = tpl.index("  window.VIEWS.live = {")
    end = tpl.index("})();", start)
    real_live = """  window.VIEWS.live = {
    html() {
      const S = window.LIVE_STATS || {};
      return `<div class="view">
        <div class="grid cols-4 rise" style="--i:0">
          <div class="panel"><div class="stat"><span class="stat-label">最近完赛</span><span class="stat-value">${count(window.LIVE.length)}<span class="unit">场</span></span><span class="stat-foot"><span class="dot"></span>库内最新记录</span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">数据截止</span><span class="stat-value" style="font-size:18px">${S.newest || '—'}</span><span class="stat-foot dim">matches.date 最大值</span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">当日赛事</span><span class="stat-value">${count(S.today || 0)}<span class="unit">场</span></span><span class="stat-foot dim">同一比赛日全部场次</span></div></div>
          <div class="panel"><div class="stat"><span class="stat-label">比赛数据源</span><span class="stat-value" style="font-size:18px">${S.source || '—'}</span><span class="stat-foot dim">football-data.org</span></div></div>
        </div>
        <div class="panel rise" style="--i:1">
          <div class="panel-head"><h3>最近完赛</h3><span class="sub">按开球时间倒序 · 真实比分</span></div>
          <div class="rows" id="liveRows">
            ${window.LIVE.map((m, i) => liveRow(m, i)).join('')}
          </div>
        </div>
        <div class="split rise" style="--i:2">
          <div class="panel">
            <div class="panel-head"><h3>服务状态</h3><span class="sub">端口探测 · 构建时实测</span></div>
            <div class="panel-body">
              ${window.SERVICES.map(s => `<div class="check">
                <span class="ci ${s.status === 'ok' || s.status === 'live' ? 'ok' : 'warn'}">${ico('check')}</span>
                <div class="grow"><b style="font-size:13px">${s.name}</b><div class="dim" style="font-size:11.5px">端口 ${s.port}</div></div>
                <span class="cv">${s.note}</span></div>`).join('')}
            </div>
          </div>
          <div class="panel">
            <div class="panel-head"><h3>最近完场</h3><span class="sub">全部联赛 · 最新 ${window.RECENT.length} 场</span></div>
            <div class="rows">
              ${window.RECENT.map(r => `
                <div class="row-item">
                  <span class="mono dim" style="width:92px;flex:none">${r.date}</span>
                  <div class="team-cell grow" style="min-width:0;justify-content:flex-end;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${T[r.home].name}${crest(r.home, 'crest')}</div>
                  <span class="mono" style="font-weight:650;padding:0 8px;flex:none">${r.hs} : ${r.as}</span>
                  <div class="team-cell grow" style="min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${crest(r.away, 'crest')}${T[r.away].name}</div>
                  <span class="tag b" style="flex:none;margin-left:8px">${(L[r.league] || {}).name || ''}</span>
                </div>`).join('')}
            </div>
          </div>
        </div>
      </div>`;
    }
  };
  function liveRow(m, i) {
    const l = L[m.league] || { name: '' };
    return `<div class="row-item">
      <span class="tag b" style="flex:none">${l.name}</span>
      <div class="team-cell grow" style="min-width:0;justify-content:flex-end;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${T[m.home].name}${crest(m.home, 'crest')}</div>
      <span class="mono" style="font-weight:700;font-size:16px;padding:0 12px;flex:none">${m.hs} : ${m.as}</span>
      <div class="team-cell grow" style="min-width:0;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${crest(m.away, 'crest')}${T[m.away].name}</div>
      <span class="dim" style="flex:none;max-width:200px;font-size:12px;text-align:right;white-space:nowrap;overflow:hidden;text-overflow:ellipsis">${m.events}</span>
      <span class="tag" style="flex:none;width:64px;justify-content:center">完场</span>
    </div>`;
  }
"""
    tpl = tpl[:start] + real_live + tpl[end:]

    # 13) 单场预测：用真实模型输出替换演示推算（原实现用 Elo/场均反推概率 + 泊松热图）
    start = tpl.index("  function singlePrediction(home, away) {")
    end = tpl.index("  function batchPrediction() {")
    real_single = """  function singlePrediction(home, away) {
    const hm = metrics(home), am = metrics(away);
    const pm = (window.PRED_MAP || {})[home + '|' + away] || null;
    const probs = pm ? pm.p : null;
    const labels = [T[home].name + ' 胜', '平局', T[away].name + ' 胜'];
    const M = (window.MODELS || []).filter(m => m.status === 'production')[0] || (window.MODELS || [])[0] || {};
    const pick = probs ? ['主胜', '平局', '客胜'][probs.indexOf(Math.max.apply(null, probs))] : '—';
    return `
      <div class="split">
        <div class="panel">
          <div class="panel-head"><h3>胜平负预测</h3><span class="sub">${pm ? (pm.model + ' · 置信度 ' + pm.conf.toFixed(2)) : '该对阵没有模型输出'}</span></div>
          <div class="panel-body od-stack" style="--od-gap:20px">
            ${probs ? probBlock(probs, labels)
              : '<div class="hintline">predictions 表只覆盖已写入预测的场次（当前 ' + (window.PRED_MAP_SIZE || 0) + ' 场未赛 fixture）。可在「批量预测」标签查看全部有输出的对阵。</div>'}
            <div class="divider"></div>
            <div class="kv">
              <dt>模型版本</dt><dd>${pm ? pm.model : '—'}</dd>
              <dt>模型倾向</dt><dd>${pick}</dd>
              <dt>比赛时间</dt><dd>${pm ? pm.date : '—'}</dd>
              <dt>预测写入</dt><dd>${pm ? pm.created : '—'}</dd>
            </div>
          </div>
        </div>
        <div class="panel">
          <div class="panel-head"><h3>${M.name || '部署模型'} · 样本外表现</h3><span class="sub">model_metrics · ${M.test_n || 0} 场测试集</span></div>
          <div class="panel-body od-stack" style="--od-gap:16px">
            <div class="grid cols-2" style="gap:12px">
              <div class="tool-card"><span class="ti">${ico('target')}</span><b>准确率</b><span style="font-size:20px" class="mono accent">${M.acc != null ? (M.acc * 100).toFixed(2) + '%' : '—'}</span></div>
              <div class="tool-card"><span class="ti">${ico('activity')}</span><b>LogLoss</b><span style="font-size:20px" class="mono">${M.logloss != null ? M.logloss.toFixed(4) : '—'}</span></div>
              <div class="tool-card"><span class="ti">${ico('cpu')}</span><b>Macro F1</b><span style="font-size:20px" class="mono">${M.f1 != null ? M.f1.toFixed(4) : '—'}</span></div>
              <div class="tool-card"><span class="ti">${ico('ball')}</span><b>平局召回</b><span style="font-size:20px" class="mono">${M.draw_recall != null ? M.draw_recall.toFixed(1) + '%' : '—'}</span></div>
            </div>
            <div class="hintline">模型只输出胜平负三路概率；比分分布、大小球、双方进球不在当前模型输出内，本页不再展示这些派生指标。两队场均进球 ${Number(hm.gfP).toFixed(2)} / ${Number(am.gfP).toFixed(2)}、场均失球 ${Number(hm.gaP).toFixed(2)} / ${Number(am.gaP).toFixed(2)}、场均 xG ${Number(hm.xgF).toFixed(2)} / ${Number(am.xgF).toFixed(2)} 均取自 team_radar。</div>
          </div>
        </div>
      </div>`;
  }
"""
    tpl = tpl[:start] + real_single + tpl[end:]

    # 14) AI 分析页：演示问答 → 真实库事实
    rep("""                <div class="msg user"><span class="who">我</span><div class="bubble">帮我对比曼城和阿森纳近期的进攻效率，并给出周日比赛的建议。</div></div>
                <div class="msg ai"><span class="who">AI</span><div class="bubble">
                  我调用了<b>球队数据</b>与<b>比赛预测</b>两个工具。曼城近 5 场 4 胜 1 平，场均进球 2.31；阿森纳防守端场均失球仅 0.89。模型给出 <b>曼城胜 46% · 平 27% · 阿森纳胜 27%</b>，预测比分 2-1。
                  <div class="tools"><span class="tag g">球队数据</span><span class="tag g">比赛预测</span></div>
                </div></div>""",
        """                <div class="msg user"><span class="who">我</span><div class="bubble">${KB.opening.q}</div></div>
                <div class="msg ai"><span class="who">AI</span><div class="bubble">${KB.opening.a}
                  <div class="tools">${KB.opening.tools.map(t => '<span class="tag g">' + t + '</span>').join('')}</div>
                </div></div>""", "AI 开场对话")

    rep("""  window.VIEWS.agent = {
    html() {
      return `<div class="view">""",
        """  window.VIEWS.agent = {
    html() {
      const KB = window.AGENT_KB;
      return `<div class="view">""", "AI 视图取知识库")

    rep('<input class="input" id="chatInput" placeholder="问点什么，例如：姆巴佩和哈兰德谁更强？" autocomplete="off">',
        '<input class="input" id="chatInput" placeholder="${window.AGENT_KB.placeholder}" autocomplete="off">',
        "AI 输入框提示")

    rep("${['对比曼城与阿森纳', '哈兰德近期状态', '周日曼城比赛预测', '阿森纳有哪些伤员'].map(q => `<button class=\"chip\" data-ask=\"${q}\">${q}</button>`).join('')}",
        "${window.AGENT_KB.chips.map(q => `<button class=\"chip\" data-ask=\"${q}\">${q}</button>`).join('')}",
        "AI 快捷提问")

    start = tpl.index("  function agentReply(text) {")
    end = tpl.index("  window.VIEWS.agent = {")
    real_agent = """  function agentReply(text) {
    const q = text, KB = window.AGENT_KB || {};
    if (/伤|停赛|缺阵|报销/.test(q)) return { tools: ['伤病信息'], body: KB.injury };
    if (/球员|身价|射手|进球榜|谁更强|姆巴佩|哈兰德/.test(q)) return { tools: ['球员检索'], body: KB.player };
    if (/预测|胜率|概率|比分|模型/.test(q)) return { tools: ['比赛预测'], body: KB.predict };
    if (/球队|对比|elo|状态|积分|联赛/i.test(q)) return { tools: ['球队数据', '比赛预测'], body: KB.team };
    return { tools: ['数据查询'], body: KB.default };
  }
"""
    tpl = tpl[:start] + real_agent + tpl[end:]

    # 15) 首页「近期预测」副标题 → 真实模型版本与场次数
    rep('<div class="panel-head"><h3>近期预测</h3><span class="sub">集成模型 v4 · 示例</span>',
        '<div class="panel-head"><h3>近期预测</h3><span class="sub">${(window.UPCOMING[0] || {}).model || \'模型输出\'} · ${window.UPCOMING.length} 场未赛</span>',
        "首页近期预测副标题")

    # 16) 数据库管理：示例行 → 实表首行数据
    start = tpl.index("  function tableDetail(t) {")
    end = tpl.index("  window.VIEWS.database = {")
    real_tabledetail = """  function tableDetail(t) {
    const rows = (t.sample && t.sample.length) ? t.sample : [];
    return `
      <div class="panel">
        <div class="panel-head"><h3>${t.name}</h3><span class="sub">${t.cols.length} 字段 · ${fmtInt(t.rows)} 行</span>
          <div class="head-actions"><span class="tag">SQLite 直读</span></div></div>
        <div class="panel-body od-stack" style="--od-gap:16px">
          <span class="section-label">字段结构</span>
          <div class="schema-cols">
            ${t.cols.map((c, i) => `<div class="schema-col">
              ${i === 0 ? '<span class="pk">' + ico('key') + '</span>' : '<span class="dim" style="width:16px"></span>'}
              <b style="font-weight:550">${c}</b>
              <span class="ty">${i === 0 ? 'INTEGER PK' : (c.includes('id') ? 'INTEGER FK' : (['elo', 'value', 'fee'].includes(c) ? 'NUMERIC' : (c.includes('date') || c.includes('ts') ? 'TIMESTAMP' : 'TEXT')))}</span>
            </div>`).join('')}
          </div>
          <span class="section-label">表内首行（构建时从该表直读，最多 2 行）</span>
          <div class="table-wrap">
            <table class="tbl" style="min-width:520px"><thead><tr>${t.cols.map(c => '<th>' + c + '</th>').join('')}</tr></thead>
              <tbody>${rows.map(r => '<tr>' + r.map(v => '<td class="' + (typeof v === 'number' ? 'num' : '') + '">' + v + '</td>').join('') + '</tr>').join('')}</tbody></table>
          </div>
        </div>
      </div>`;
  }
"""
    tpl = tpl[:start] + real_tabledetail + tpl[end:]

    # 17) 「真实系统」按钮：侧边浏览器内 window.open 可能被拦截 → 回退为当前标签跳转
    rep("""  realBtn.addEventListener('click', () => {
    const w = window.open(realUrl, '_blank', 'noopener');
    if (!w) { realBtn.textContent = '已被浏览器拦截'; setTimeout(() => { realBtn.innerHTML = '<span>真实系统</span>'; }, 1600); }
  });""",
        """  realBtn.addEventListener('click', () => {
    let url = realUrl;
    // 把当前登录令牌带给真实系统(Streamlit 端会向后端核对一次)
    try {
      const s = JSON.parse(localStorage.getItem('fauth') || 'null');
      if (s && s.token) url += (url.indexOf('?') >= 0 ? '&' : '?') + 'auth_token=' + encodeURIComponent(s.token);
    } catch (e) {}
    let w = null;
    try { w = window.open(url, '_blank', 'noopener'); } catch (e) { w = null; }
    if (!w) {
      // 沙箱/侧边栏环境可能拦截新窗口，此时在当前标签内直接打开真实系统页面
      realBtn.textContent = '正在打开…';
      location.href = url;
    }
  });""", "真实系统按钮回退")

    # 18) API 页「查看文档」→ 真实 Swagger 文档地址
    rep("""<button class="btn btn-ghost">${ico('code')}查看文档</button>""",
        """<button class="btn btn-ghost" onclick="location.href='http://127.0.0.1:8000/docs'">${ico('code')}查看文档</button>""",
        "API 文档按钮")

    # 19) 内联 SVG favicon（避免浏览器请求 /favicon.ico 404）
    fav = ("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'%3E"
           "%3Crect width='32' height='32' rx='8' fill='%230a0f0c'/%3E"
           "%3Cpath d='M16 5.5l9 5.2v10.6l-9 5.2-9-5.2V10.7z' fill='none' stroke='%2335c98d' stroke-width='1.8'/%3E"
           "%3Cpath d='M16 11.5l4.4 7.6H11.6z' fill='%2335c98d'/%3E%3C/svg%3E")
    rep("<title>足球数据分析与 AI 预测系统 · 控制台</title>",
        "<title>足球数据分析与 AI 预测系统 · 控制台</title>\n<link rel=\"icon\" href=\"" + fav + "\">",
        "内联 favicon")

    # 20) 登录闸门: 打开控制台先登录(账号密码 + 扫码), 令牌存 localStorage.fauth
    rep("</style>\n</head>", GATE_CSS + "</style>\n</head>", "登录页样式")
    rep('<div class="scrim" id="scrim" hidden></div>',
        '<div class="scrim" id="scrim" hidden></div>' + GATE_HTML, "登录页结构")
    rep("</body>\n</html>", GATE_JS + "</body>\n</html>", "登录页逻辑")

    # 21) 顶栏: 当前登录用户 + 退出
    rep("""        <button class="btn btn-ghost" id="realBtn" title="在本地已运行的真实系统中打开当前页面">
          <span>真实系统</span>
        </button>""",
        """        <span class="who" id="whoBox" hidden>
          <b id="whoName"></b><i id="whoRole"></i>
          <button class="who-out" id="whoOut" title="退出登录">退出</button>
        </span>
        <button class="btn btn-ghost" id="realBtn" title="在本地已运行的真实系统中打开当前页面">
          <span>真实系统</span>
        </button>""", "顶栏用户区")

    out = tpl
    for old, new, label, cnt in patches:
        found = out.count(old)
        if cnt == 0:
            continue
        if found != cnt:
            raise SystemExit(f"[patch] {label}: 期望 {cnt} 处，实际 {found} 处")
        out = out.replace(old, new)
    return out


# ---- 作用域拆分: 用户端(index.html) / 管理后台(admin.html) ----
# 以前 14 个页面挤在同一个控制台里, 用户端 8 页与后台 6 页混在同一条侧栏; 现在各自
# 独立成一页, 侧栏只列本作用域的页面, 右上角一键互相切换。
SCOPES = [
    dict(group="用户端", out="index.html", title="用户端控制台",
         brand="用户端 CONSOLE", other="admin.html", other_label="管理后台", admin_only=False),
    dict(group="管理后台", out="admin.html", title="管理后台控制台",
         brand="管理后台 ADMIN", other="index.html", other_label="用户端", admin_only=True),
]


def scope_html(full: str, sc: dict) -> str:
    """把完整控制台裁剪成单个作用域: 只保留本作用域的导航, 并加作用域守卫与切换入口。"""
    pages = [p for p in PAGES if p["group"] == sc["group"]]
    if not pages:
        raise SystemExit(f"[scope] {sc['group']} 没有页面")
    slugs = [p["slug"] for p in pages]
    out = full

    def rep(old: str, new: str, label: str) -> None:
        nonlocal out
        found = out.count(old)
        if found != 1:
            raise SystemExit(f"[scope] {label}: 期望 1 处, 实际 {found} 处")
        out = out.replace(old, new)

    rep("window.PAGES = " + js(PAGES) + ";",
        "window.PAGES = " + js(pages) + ";", "页面清单")
    rep("  const PAGES = window.PAGES;",
        "  const PAGES = window.PAGES;\n  const SCOPE_SLUGS = " + js(slugs) + ";",
        "作用域白名单")
    # 守卫放进 go(): 导航点击 / hashchange / 首次进入 三条路径都会经过它
    rep("  function go(slug, push) {",
        "  function go(slug, push) {\n    if (!SCOPE_SLUGS.includes(slug)) slug = SCOPE_SLUGS[0];",
        "作用域守卫")
    rep("<title>足球数据分析与 AI 预测系统 · 控制台</title>",
        f"<title>足球数据分析与 AI 预测系统 · {sc['title']}</title>", "标题")
    rep("<small>FOOTBALL INTELLIGENCE</small>",
        f"<small>{sc['brand']}</small>", "品牌副标题")
    rep('        <button class="btn btn-ghost" id="realBtn"',
        '        <a class="btn btn-ghost" id="scopeBtn" href="' + sc["other"] +
        '" title="切换到' + sc["other_label"] + '控制台">' + sc["other_label"] + ' ↗</a>\n'
        '        <button class="btn btn-ghost" id="realBtn"', "切换入口")
    if sc.get("admin_only"):
        # 后台控制台只放管理员进: enter() 是账号密码与扫码两条登录路径的唯一出口。
        # 真实系统 8502 本身就要求 role=admin, 这里保持一致, 避免普通账号在控制台里
        # 直接看到后台的真实数据。
        rep("  function enter(user) {",
            "  function enter(user) {\n"
            "    if (!user || user.role !== 'admin') {\n"
            "      showGate('这个控制台需要管理员账号（当前登录：' + "
            "((user && (user.display_name || user.username)) || '未知') + '）', true);\n"
            "      var lk = document.getElementById('gToLogin');\n"
            "      if (lk) { lk.href = 'login.html?next=' +\n"
            "        encodeURIComponent(selfName() + location.hash) + '&why=role'; }\n"
            "      return;\n"
            "    }", "管理员校验")
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--no-assets", action="store_true")
    args = ap.parse_args()
    if not TPL.exists():
        raise SystemExit(f"缺少模板 {TPL}")
    tpl = TPL.read_text(encoding="utf-8")
    con = connect()
    js_block, info = build_js(con)
    con.close()
    html = apply_patches(tpl, info, js_block)
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    for sc in SCOPES:
        page = scope_html(html, sc)
        (OUT_DIR / sc["out"]).write_text(page, encoding="utf-8")
        n = len([p for p in PAGES if p["group"] == sc["group"]])
        print(f"写出 {OUT_DIR / sc['out']} ({len(page.encode('utf-8')):,} B) · "
              f"{sc['group']} {n} 页")
    print(f"  联赛 {len(info['leagues'])} · 球队 {len(info['teams'])} · 积分榜 {len(info['standings'])} 组 · "
          f"球员 {len(info['players'])} · 预测 {len(info['upcoming'])} · 表 {len(info['tables'])} · "
          f"模型 {len(info['models'])} · 画廊 {len(info['gallery'])} 张 · API 样例 {len(info['api'])}")
    print(f"  DB 总量 {info['overview']['total']:,} 行 / {info['meta']['tables']} 表 / {info['meta']['db_mb']} MB")

    if args.no_assets:
        return
    CREST_DIR.mkdir(parents=True, exist_ok=True)
    LEAGUE_DIR.mkdir(parents=True, exist_ok=True)
    jobs = []
    for s, t in info["teams"].items():
        dest = CREST_DIR / f"{s}.png"
        if t.get("logo") and not valid_png(dest):
            jobs.append((t["logo"], dest))
    ok = 0
    with ThreadPoolExecutor(max_workers=16) as ex:
        for r in ex.map(lambda j: download(*j), jobs):
            ok += 1 if r else 0
    print(f"  真实队徽下载 {ok}/{len(jobs)}")
    # 缺 logo（或下载失败/缓存损坏）的用生成式占位 PNG，保证每个 slug 都有可加载的图片
    made = 0
    for s, t in info["teams"].items():
        dest = CREST_DIR / f"{s}.png"
        if valid_png(dest):
            continue
        color = PALETTE[abs(hash(s)) % len(PALETTE)]
        dest.write_bytes(badge_png(t["name"], color, t.get("short") or t["name"]))
        made += 1
    lg_made = 0
    for s, l in info["leagues"].items():
        dest = LEAGUE_DIR / f"{s}.png"
        color = PALETTE[abs(hash(s)) % len(PALETTE)]
        dest.write_bytes(badge_png(l["name"], color, l.get("en") or l["name"]))
        lg_made += 1
    # 清掉早期版本留下的 .svg 占位（避免同 slug 两份资源）
    stale = list(CREST_DIR.glob("*.svg")) + list(LEAGUE_DIR.glob("*.svg"))
    for f in stale:
        f.unlink()
    print(f"  生成式占位徽标 {made} 队 + {lg_made} 联赛（清理 {len(stale)} 个旧 .svg）")


if __name__ == "__main__":
    main()
