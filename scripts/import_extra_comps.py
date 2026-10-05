# -*- coding: utf-8 -*-
"""D. 导入 football-data 免费档里的其他赛事(欧冠/英冠/荷甲/葡超/巴甲)

- 自动建 leagues 行
- 队名"全局匹配"(先在整个 teams 表里找, 找不到才在该赛事下新建), 避免与五大联赛重复
- 按赛季导入比赛(赛程+赛果)

用法:
    python scripts/import_extra_comps.py --seasons 2526,2627
"""
import argparse
import os
import sqlite3
import sys
import time
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.football_data_api import (  # noqa: E402
    FootballDataClient, STATUS_MAP, _db, _norm, _drop_club_tokens, _TEAM_ALIAS,
)

# 免费档可用但尚未导入的赛事: code -> (中文名, 英文名, 国家/地区)
EXTRA_COMPS = {
    "CL": ("欧冠", "UEFA Champions League", "欧洲"),
    "ELC": ("英冠", "Championship", "英格兰"),
    "DED": ("荷甲", "Eredivisie", "荷兰"),
    "PPL": ("葡超", "Primeira Liga", "葡萄牙"),
    "BSA": ("巴甲", "Campeonato Brasileiro Série A", "巴西"),
}
SEASON_YEAR = {"2425": 2024, "2526": 2025, "2627": 2026}


def ensure_league(conn, name, name_en, country):
    row = conn.execute("SELECT league_id FROM leagues WHERE name=?", (name,)).fetchone()
    if row:
        return row["league_id"]
    cur = conn.execute(
        "INSERT INTO leagues (name, name_en, country, season, created_at) "
        "VALUES (?, ?, ?, '2026-27', ?)",
        (name, name_en, country, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    return cur.lastrowid


def find_team_global(conn, name, fallback_league_id):
    """匹配球队(严格版, 避免跨联赛错配)

    历史 bug: 旧版用 "子串包含" 匹配, 导致 AZ -> Lazio(l-az-io)、NAC -> Monaco(mo-nac-o)、
    Inter(巴西国际) -> Inter(意甲)、Braga -> Bragantino 等严重错配。
    现规则: ① 精确同名 ② 本赛事内精确 ③ 别名表 ④ 词元集合完全相等 ⑤ 才新建
    """
    if not name:
        return None
    # ① 全库精确同名
    row = conn.execute("SELECT team_id FROM teams WHERE name=?", (name,)).fetchone()
    if row:
        return row["team_id"]
    cand = _norm(_drop_club_tokens(name))
    if not cand:
        return None
    # ② 本赛事内精确
    row = conn.execute("SELECT team_id FROM teams WHERE league_id=? AND name=?",
                       (fallback_league_id, name)).fetchone()
    if row:
        return row["team_id"]
    # ③ 别名表
    alias = _TEAM_ALIAS.get(cand)
    if alias:
        row = conn.execute("SELECT team_id FROM teams WHERE name=?", (alias,)).fetchone()
        if row:
            return row["team_id"]
    # ④ 归一化精确 / 词元集合完全相等(不放宽为子串!)
    nn = {_norm(r["name"]): r["team_id"]
          for r in conn.execute("SELECT team_id, name FROM teams")}
    if cand in nn:
        return nn[cand]
    tok = set(_drop_club_tokens(name).lower().split())
    if tok:
        for k, tid in nn.items():
            ktok = set(k.split())
            if tok == ktok and any(len(w) >= 5 for w in tok):
                return tid
    # ⑤ 仍找不到 -> 新建(挂在本赛事下)
    clean = _drop_club_tokens(name).title()
    cur = conn.execute(
        "INSERT INTO teams (league_id, name, name_en, short_name, elo_rating, created_at) "
        "VALUES (?, ?, ?, ?, 1500.0, ?)",
        (fallback_league_id, clean, name, clean[:12],
         datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
    print(f"     [新建球队] {clean}  <- 源名 {name!r}")
    return cur.lastrowid


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seasons", default="2627")
    ap.add_argument("--comps", default=",".join(EXTRA_COMPS.keys()))
    args = ap.parse_args()

    client = FootballDataClient()
    conn = _db()
    total_new = 0
    for code in [c.strip() for c in args.comps.split(",") if c.strip()]:
        if code not in EXTRA_COMPS:
            continue
        cn, en, country = EXTRA_COMPS[code]
        lid = ensure_league(conn, cn, en, country)
        conn.commit()
        for season in [s.strip() for s in args.seasons.split(",") if s.strip()]:
            year = SEASON_YEAR.get(season)
            if not year:
                continue
            try:
                matches = client.get_competition_matches(code, season=year)
            except Exception as e:
                print(f"  {cn} {season} 拉取失败: {str(e)[:60]}")
                continue
            time.sleep(6)                      # 免费档限速
            new = 0
            for m in matches:
                utc = m.get("utcDate")
                if not utc:
                    continue
                local = datetime.fromisoformat(utc.replace("Z", "+00:00")) + timedelta(hours=8)
                date_str = local.strftime("%Y-%m-%d %H:%M")
                status = STATUS_MAP.get(m.get("status"), "NS")
                hn = (m.get("homeTeam", {}).get("shortName")
                      or m.get("homeTeam", {}).get("name"))
                an = (m.get("awayTeam", {}).get("shortName")
                      or m.get("awayTeam", {}).get("name"))
                hid = find_team_global(conn, hn, lid)
                aid = find_team_global(conn, an, lid)
                ft = (m.get("score", {}) or {}).get("fullTime", {}) or {}
                hg, ag = ft.get("home"), ft.get("away")
                if status == "NS":
                    hg = ag = None
                ex = conn.execute(
                    "SELECT match_id FROM matches WHERE league_id=? AND date=? "
                    "AND home_team_id=? AND away_team_id=?",
                    (lid, date_str, hid, aid)).fetchone()
                if ex:
                    conn.execute("UPDATE matches SET status=?, home_goals=?, away_goals=? "
                                 "WHERE match_id=?", (status, hg, ag, ex["match_id"]))
                else:
                    conn.execute(
                        "INSERT INTO matches (league_id, season, matchday, date, "
                        "home_team_id, away_team_id, home_goals, away_goals, status, created_at) "
                        "VALUES (?,?,?,?,?,?,?,?,?,?)",
                        (lid, season, m.get("matchday"), date_str, hid, aid, hg, ag,
                         status, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
                    new += 1
            conn.commit()
            total_new += new
            print(f"  {cn}({code}) {season}: 返回 {len(matches)} 场, 新增 {new} 场")

    print(f"\n合计新增: {total_new} 场")
    print("\n库内各联赛比赛数:")
    for r in conn.execute("""
        SELECT l.name, COUNT(*) n FROM matches m JOIN leagues l ON l.league_id=m.league_id
        GROUP BY m.league_id ORDER BY n DESC"""):
        print(f"  {r['name']:<6} {r['n']}")
    conn.close()


if __name__ == "__main__":
    main()
