# -*- coding: utf-8 -*-
"""用球小策导入球队完整阵容(替代 TheSportsDB 的10人片段)

- team_id 映射优先取自本地赛程缓存(0点), 缺失才用 /teams?q= 检索(2点/队)
- 每个球队: /teams/{id}/squad (约5点) -> 覆盖该队球员 + 回填球队资料
- 带预算上限, 超限自动停止(避免点数失控)

用法:
    python scripts/import_squads_qxz.py --league 1              # 英超(20队)
    python scripts/import_squads_qxz.py --budget 400            # 五大联赛, 上限400点
"""
import argparse
import json
import os
import re
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.qiuxiaoce import QiuxiaoceClient   # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "database", "football.db")
CACHE = os.path.join(BASE, "data", "qxz_fixtures_cache.json")
SQUAD_COST = 5
SKIP_POS = ("coach", "manager")


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def build_team_map():
    """从赛程缓存里免费提取 英文名 -> 球小策team_id"""
    m = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            for fx in json.load(f):
                for side in ("home", "away"):
                    en, tid = fx.get(f"{side}_team_en"), fx.get(f"{side}_team_id")
                    if en and tid:
                        m[norm(en)] = tid
    return m


def name_variants(name):
    """队名的多种等价写法(本地名 + 别名表 + 去俱乐部词)"""
    from src.data_sources.thesportsdb import SEARCH_ALIAS
    from src.data_sources.football_data_api import _drop_club_tokens
    out = {norm(name)}
    if name in SEARCH_ALIAS:
        out.add(norm(SEARCH_ALIAS[name]))
    out.add(norm(_drop_club_tokens(name)))
    return {x for x in out if x}


COUNTRY_BY_LEAGUE = {1: "England", 2: "Spain", 3: "Germany", 4: "Italy", 5: "France"}

# 名称差异导致自动映射不到的球队: 直接指定球小策 team_id
QXZ_ID_OVERRIDE = {
    "Bayern Munich": 157,      # Bayern München
    "Ath Bilbao": 531,         # Athletic Club
    "1. Koln": 192,            # 1. FC Köln
    "M'gladbach": 163,         # Borussia Mönchengladbach
}


def lookup_team_id(cli, tmap, team_name, league_id):
    """先查覆盖表, 再查免费映射(含别名), 最后退回检索(带国家过滤)"""
    if team_name in QXZ_ID_OVERRIDE:
        return QXZ_ID_OVERRIDE[team_name], "override"
    for v in name_variants(team_name):
        if v in tmap:
            return tmap[v], "cache"
    data = cli.teams(q=team_name)
    want_country = COUNTRY_BY_LEAGUE.get(league_id)
    best = None
    for t in (data or {}).get("data", []):
        if t.get("national"):
            continue
        if "U21" in (t.get("name_en") or "") or "U19" in (t.get("name_en") or ""):
            continue
        if want_country and t.get("country") != want_country:
            continue
        if norm(t.get("name_en")) in name_variants(team_name):
            return t.get("team_id"), "search"
        if best is None:
            best = t.get("team_id")
    return (best, "search-fuzzy") if best else (None, None)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--league", type=int, default=None,
                    help="只导某联赛(1英超 2西甲 3德甲 4意甲 5法甲); 默认全部")
    ap.add_argument("--budget", type=int, default=400, help="点数上限")
    ap.add_argument("--only-missing", action="store_true",
                    help="只处理球员<20人的球队(避免重复扣点)")
    ap.add_argument("--force", default="", help="强制重导的队名, 逗号分隔")
    args = ap.parse_args()

    cli = QiuxiaoceClient()
    tmap = build_team_map()
    print(f"免费映射到球小策球队ID: {len(tmap)} 个英文名")
    force = {s.strip() for s in args.force.split(",") if s.strip()}

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    sql = """SELECT DISTINCT t.team_id, t.name, t.league_id
             FROM standings s JOIN teams t ON t.team_id = s.team_id
             WHERE s.season='2627'"""
    params = []
    if args.league:
        sql += " AND s.league_id = ?"
        params.append(args.league)
    rows = conn.execute(sql + " ORDER BY s.league_id, t.name", params).fetchall()

    done = players_added = players_replaced = 0
    unmapped = []
    for i, r in enumerate(rows, 1):
        if cli.spent_points + SQUAD_COST > args.budget:
            print(f"⏹ 达到点数上限({args.budget}), 已停止")
            break
        cur_players = conn.execute("SELECT COUNT(*) FROM players WHERE team_id=?",
                                   (r["team_id"],)).fetchone()[0]
        if args.only_missing and cur_players >= 20 and r["name"] not in force:
            continue
        qid, how = lookup_team_id(cli, tmap, r["name"], r["league_id"])
        if not qid:
            unmapped.append(r["name"])
            print(f"[{i}/{len(rows)}] ✗ {r['name']} 未找到球小策ID")
            continue

        sq = cli.team_squad(qid)
        if not sq or not sq.get("data"):
            print(f"[{i}/{len(rows)}] ✗ {r['name']} 阵容为空")
            continue

        # 覆盖该队球员: 先删旧(TheSportsDB 10人片段), 再插完整阵容
        conn.execute("DELETE FROM players WHERE team_id=?", (r["team_id"],))
        n = 0
        for p in sq["data"]:
            pos = (p.get("position") or "")
            if any(k in pos.lower() for k in SKIP_POS):
                continue
            conn.execute("""
                INSERT INTO players (team_id, name, name_en, position, nationality,
                    age, height, weight, number, market_value, photo_url,
                    stats_json, created_at)
                VALUES (?,?,?,?,?,?,?,?,?,NULL,?,?,?)""",
                (r["team_id"], p.get("name"), p.get("name"), pos or None, None,
                 p.get("age"), None, None, p.get("number"), p.get("photo"),
                 json.dumps({"qxz_id": p.get("id")}, ensure_ascii=False),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            n += 1
        # 球队资料(成立年/球场/容量)
        tm = sq.get("team", {}) or {}
        conn.execute("""UPDATE teams SET
                founded = COALESCE(?, founded),
                stadium = COALESCE(NULLIF(?, ''), stadium),
                capacity = COALESCE(?, capacity)
            WHERE team_id=?""",
            (tm.get("founded"), tm.get("venue_name"), tm.get("venue_capacity"),
             r["team_id"]))
        conn.commit()
        done += 1
        players_added += n
        players_replaced += 1
        print(f"[{i}/{len(rows)}] ✓ {r['name']} -> {tm.get('name_zh')} | 阵容 {n} 人 "
              f"| 累计点数 ~{cli.spent_points}")

    conn.close()
    print("\n" + "=" * 62)
    print(f"完成: 覆盖球队 {players_replaced} 支 | 写入球员 {players_added} 名 | "
          f"估算消耗 {cli.spent_points} 点")
    if unmapped:
        print(f"未映射球队({len(unmapped)}): {', '.join(unmapped[:15])}")
    print("=" * 62)


if __name__ == "__main__":
    main()
