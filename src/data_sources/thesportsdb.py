# -*- coding: utf-8 -*-
"""TheSportsDB 数据源 (免费 key=3)

用途: 回填球队资料(球场/容量/成立年份) + 导入球员(姓名/位置/国籍/年龄/身高体重/号码/头像)
限制: 免费 key 每队仅返回 10 名球员; 速率 30 次/分钟

API: https://www.thesportsdb.com/api/v1/json/3/...
"""
import json
import os
import re
import sqlite3
import time
from datetime import datetime

import requests

BASE = "https://www.thesportsdb.com/api/v1/json"
KEY = "3"                      # 公开测试 key (免费)
SLEEP = 2.2                    # 限速: 约 27 次/分钟
DB_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__)))), "data", "database", "football.db")

# 库里简称 -> TheSportsDB 可搜到的名称
SEARCH_ALIAS = {
    "Man City": "Manchester City", "Man United": "Manchester United",
    "Nott'm Forest": "Nottingham Forest", "Wolves": "Wolverhampton Wanderers",
    "Tottenham": "Tottenham Hotspur", "Newcastle": "Newcastle United",
    "West Ham": "West Ham United", "Leeds": "Leeds United", "Hull": "Hull City",
    "Brighton": "Brighton and Hove Albion", "M'gladbach": "Borussia Monchengladbach",
    "Ath Madrid": "Atletico Madrid", "Ath Bilbao": "Athletic Bilbao",
    "La Coruna": "Deportivo La Coruna", "Sociedad": "Real Sociedad",
    "Betis": "Real Betis", "Espanol": "Espanyol", "Vallecano": "Rayo Vallecano",
    "Ein Frankfurt": "Eintracht Frankfurt", "Bayern Munich": "Bayern Munich",
    "Inter": "Inter Milan", "Milan": "AC Milan", "Roma": "AS Roma",
    "Atleti": "Atletico Madrid", "Eintracht Frankfurt": "Eintracht Frankfurt",
    # 修正错误匹配(女足/预备队/其他运动/同名俱乐部)
    "Ipswich": "Ipswich Town", "Alaves": "Deportivo Alaves",
    "La Coruna": "Deportivo de La Coruna", "Dortmund": "Borussia Dortmund",
    "Santander": "Racing Santander", "Psg": "Paris Saint-Germain",
    "Lille": "Lille OSC", "Nott'm Forest": "Nottingham Forest",
}
SKIP_POSITIONS = ("coach", "manager", "assistant", "physio", "director")

# 免费档按名搜不到的球队: 直接指定 TheSportsDB id
TEAM_ID_OVERRIDE = {
    "La Coruna": "133816",   # Deportivo de A Coruña
    "Psg": "133714",         # Paris Saint-Germain
}


def _db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _get(path, params=None, retries=3):
    url = f"{BASE}/{KEY}/{path}"
    for i in range(retries):
        try:
            r = requests.get(url, params=params or {}, timeout=25)
            if r.status_code == 200:
                return r.json()
            if r.status_code == 429:
                time.sleep(8)
                continue
        except Exception:
            time.sleep(3)
    return None


def _parse_height(s):
    """'1.72 m (5 ft 8 in)' -> 172.0 ; '172 cm' -> 172.0"""
    if not s:
        return None
    m = re.search(r"(\d+\.\d+)\s*m", s)
    if m:
        return round(float(m.group(1)) * 100, 1)
    m = re.search(r"(\d+)\s*cm", s)
    return float(m.group(1)) if m else None


def _parse_weight(s):
    if not s:
        return None
    m = re.search(r"(\d+\.?\d*)", s)
    return float(m.group(1)) if m else None


def _age(born):
    if not born:
        return None
    try:
        d = datetime.strptime(born[:10], "%Y-%m-%d")
        return int((datetime.now() - d).days // 365.25)
    except Exception:
        return None


TOP_LEAGUE_HINTS = ("Premier League", "La Liga", "Bundesliga", "Serie A",
                    "Ligue 1", "Championship", "LaLiga")


def _pick_team(teams):
    """从搜索结果中优选: 男足 + 足球 + 顶级联赛"""
    def ok(t):
        sport = (t.get("strSport") or "Soccer")
        gender = (t.get("strGender") or "Male")
        return sport == "Soccer" and gender == "Male"

    pool = [t for t in teams if ok(t)] or teams

    def score(t):
        s = 0
        lg = t.get("strLeague") or ""
        if any(k.lower() in lg.lower() for k in TOP_LEAGUE_HINTS):
            s += 3
        if t.get("strStadium"):
            s += 1
        return s

    return max(pool, key=score)


def search_team(conn, team_name):
    """按队名搜索 TheSportsDB 球队(优先 id 覆盖表, 其次别名/后缀回退, 并优选男足一线队)"""
    # 0) id 覆盖表(免费档按名搜不到的队)
    override = TEAM_ID_OVERRIDE.get(team_name)
    if override:
        data = _get("lookupteam.php", {"id": override})
        time.sleep(SLEEP)
        if data and data.get("teams"):
            return data["teams"][0]
    tried = []
    for cand in [SEARCH_ALIAS.get(team_name, team_name), team_name,
                 f"{team_name} FC"]:
        if cand in tried:
            continue
        tried.append(cand)
        data = _get("searchteams.php", {"t": cand})
        time.sleep(SLEEP)
        if data and data.get("teams"):
            picked = _pick_team(data["teams"])
            # 排除明显错类(非足球/非男足)
            if (picked.get("strSport") or "Soccer") == "Soccer" and \
               (picked.get("strGender") or "Male") == "Male":
                return picked
    return None


def import_teams_and_players(league_ids=(1, 2, 3, 4, 5), limit_teams=None,
                             only_missing_players=True, team_names=None,
                             overwrite_profile=False):
    """为当前赛季(2627)五大联赛球队回填资料并导入球员

    team_names: 仅处理这些队名(修正重导用)
    overwrite_profile: 覆盖已有球场资料(修正错误匹配用)
    """
    conn = _db()
    sql = """
        SELECT DISTINCT t.team_id, t.name, t.league_id, t.stadium
        FROM standings s JOIN teams t ON t.team_id = s.team_id
        WHERE s.season = '2627' AND s.league_id IN ({})
    """.format(",".join("?" for _ in league_ids))
    params = list(league_ids)
    if team_names:
        sql += " AND t.name IN ({})".format(",".join("?" for _ in team_names))
        params += list(team_names)
    sql += " ORDER BY s.league_id, t.name"
    rows = conn.execute(sql, params).fetchall()
    if limit_teams:
        rows = rows[:limit_teams]

    stat = {"teams": len(rows), "teams_found": 0, "teams_updated": 0,
            "players_added": 0, "no_match": [], "elapsed_s": 0}
    t0 = time.time()
    print(f"共 {len(rows)} 支球队待处理 (限速 {SLEEP}s/次)", flush=True)

    for i, r in enumerate(rows, 1):
        team = search_team(conn, r["name"])
        if not team:
            stat["no_match"].append(r["name"])
            print(f"[{i}/{len(rows)}] ✗ {r['name']} 未找到", flush=True)
            continue
        stat["teams_found"] += 1

        # 回填球队资料(仅补空)
        stadium = team.get("strStadium")
        capacity = team.get("intStadiumCapacity")
        founded = team.get("intFormedYear")
        try:
            cap = int(capacity) if capacity else None
        except Exception:
            cap = None
        try:
            fye = int(founded) if founded else None
        except Exception:
            fye = None
        cur = conn.execute("""
            UPDATE teams SET
                stadium = CASE WHEN ? THEN ? ELSE COALESCE(NULLIF(stadium,''), ?) END,
                capacity = CASE WHEN ? THEN ? ELSE COALESCE(capacity, ?) END,
                founded = CASE WHEN ? THEN ? ELSE COALESCE(founded, ?) END,
                manager = COALESCE(NULLIF(manager,''), ?)
            WHERE team_id = ?""",
            (overwrite_profile, stadium, stadium,
             overwrite_profile, cap, cap,
             overwrite_profile, fye, fye,
             team.get("strManager"), r["team_id"]))
        if cur.rowcount:
            stat["teams_updated"] += 1

        # 球员
        tid = team.get("idTeam")
        pdata = _get("lookup_all_players.php", {"id": tid})
        time.sleep(SLEEP)
        players = (pdata or {}).get("player") or []
        added = 0
        for p in players:
            pos = (p.get("strPosition") or "").strip()
            if any(k in pos.lower() for k in SKIP_POSITIONS):
                continue
            name = p.get("strPlayer")
            if not name:
                continue
            exists = conn.execute(
                "SELECT 1 FROM players WHERE team_id=? AND name=? LIMIT 1",
                (r["team_id"], name)).fetchone()
            if exists:
                continue
            conn.execute("""
                INSERT INTO players
                    (team_id, name, name_en, position, nationality, age, height,
                     weight, number, market_value, photo_url, stats_json, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, NULL, ?, ?, ?)""",
                (r["team_id"], name, name, pos or None, p.get("strNationality"),
                 _age(p.get("dateBorn")), _parse_height(p.get("strHeight")),
                 _parse_weight(p.get("strWeight")),
                 int(p["strNumber"]) if (p.get("strNumber") or "").isdigit() else None,
                 p.get("strCutout") or p.get("strThumb"),
                 json.dumps({"idPlayer": p.get("idPlayer"), "born": p.get("dateBorn")},
                            ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            added += 1
        stat["players_added"] += added
        conn.commit()
        print(f"[{i}/{len(rows)}] ✓ {r['name']} -> {team.get('strTeam')} | "
              f"球员+{added} | 累计 {stat['players_added']}", flush=True)

    stat["elapsed_s"] = round(time.time() - t0, 1)
    conn.close()
    return stat
