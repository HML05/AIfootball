# -*- coding: utf-8 -*-
"""球小策数据接入 + football-data 补齐近期赛果

步骤:
  1. football-data 补齐 9/3 以来赛果 (免费)
  2. 发现球小策五大联赛 league_id 并保存
  3. 拉取五大联赛赛程, 建立 球小策fixture_id <-> 本地match_id 映射表
  4. 验证技术统计接口(取一场已完赛比赛看 xG 等字段)
"""
import json
import os
import re
import sqlite3
import sys
import time
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.qiuxiaoce import QiuxiaoceClient
from src.data_sources.football_data_api import import_matches

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "database", "football.db")
LEAGUE_MAP_FILE = os.path.join(BASE, "data", "qxz_league_map.json")

OUR_LEAGUES = {"英超", "西甲", "德甲", "意甲", "法甲"}


def norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def step1_backfill():
    print("=" * 62)
    print("【1】football-data 补齐 9/3 以来赛果 (免费)")
    print("=" * 62)
    # 免费档限制单次日期跨度<=10天, 所以拆成"过去段 + 未来段"两次调用
    today = date(2026, 9, 10)
    for label, start, days in [("过去段(补赛果)", date(2026, 9, 3), 8),
                               ("未来段(赛程)", today, 7)]:
        try:
            info = import_matches(days=days, date_from=start)
            print(f"  {label} {start}~{start + timedelta(days=days - 1)}: "
                  f"返回 {info['fetched']} | 新增 {info['inserted']} | 更新 {info['updated']}")
        except Exception as e:
            print(f"  {label} 失败: {e}")
    conn = sqlite3.connect(DB)
    print("  FT 总数:", conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status='FT'").fetchone()[0])
    print("  FT 最新:", conn.execute(
        "SELECT MAX(date) FROM matches WHERE status='FT'").fetchone()[0])
    print("  未开赛(NS):", conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status='NS'").fetchone()[0])
    conn.close()


def step2_map_leagues(cli):
    print("\n" + "=" * 62)
    print("【2】发现球小策五大联赛 league_id")
    print("=" * 62)
    if os.path.exists(LEAGUE_MAP_FILE):
        with open(LEAGUE_MAP_FILE, encoding="utf-8") as f:
            found = json.load(f)
    else:
        found = {}
    if len(found) < len(OUR_LEAGUES):
        d = date(2026, 9, 11)
        for i in range(5):
            ds = (d + timedelta(days=i)).isoformat()
            data = cli.fixtures(date=ds)
            for fx in (data or {}).get("data", []):
                nm = fx.get("league_name")
                if nm in OUR_LEAGUES and nm not in found:
                    found[nm] = fx.get("league_id")
            if len(found) == len(OUR_LEAGUES):
                break
    # 仍缺的联赛: 用联赛检索兜底
    for nm in OUR_LEAGUES - set(found):
        data = cli.leagues(q=nm)
        blob = json.dumps(data or {}, ensure_ascii=False)
        m = re.search(r'"(?:league_id|id)"\s*:\s*(\d+)', blob)
        if m:
            found[nm] = int(m.group(1))
            print(f"  (检索补齐) {nm} -> {found[nm]}")
    with open(LEAGUE_MAP_FILE, "w", encoding="utf-8") as f:
        json.dump(found, f, ensure_ascii=False, indent=1)
    print("  联赛ID映射:", found)
    return found


def step3_map_fixtures(cli, league_map):
    print("\n" + "=" * 62)
    print("【3】建立 球小策fixture_id <-> 本地match_id 映射")
    print("=" * 62)
    from src.data_sources.thesportsdb import SEARCH_ALIAS   # 复用队名别名表
    conn = sqlite3.connect(DB)
    conn.execute("""CREATE TABLE IF NOT EXISTS qxz_fixture_map (
        match_id INTEGER PRIMARY KEY,
        qxz_fixture_id INTEGER,
        kickoff TEXT, home_en TEXT, away_en TEXT, league TEXT,
        mapped_at TEXT)""")
    conn.commit()

    rows = conn.execute("""
        SELECT m.match_id, m.date, th.name h, ta.name a, l.name lg
        FROM matches m JOIN teams th ON th.team_id=m.home_team_id
        JOIN teams ta ON ta.team_id=m.away_team_id
        JOIN leagues l ON l.league_id=m.league_id
        WHERE date(m.date) BETWEEN '2026-09-05' AND '2026-09-20'""").fetchall()
    print(f"  本地待映射比赛: {len(rows)} 场")

    # 远端赛程: 本地缓存12小时, 避免重复扣点
    cache_file = os.path.join(BASE, "data", "qxz_fixtures_cache.json")
    remote = []
    if os.path.exists(cache_file) and \
            (time.time() - os.path.getmtime(cache_file)) < 12 * 3600:
        with open(cache_file, encoding="utf-8") as f:
            remote = json.load(f)
        print(f"  使用本地缓存赛程 {len(remote)} 场 (0点)")
    else:
        for lg, lid in league_map.items():
            data = cli.fixtures(league=lid, season=2026,
                                **{"from": "2026-09-05", "to": "2026-09-20"})
            items = (data or {}).get("data", [])
            print(f"    {lg}(id={lid}): {len(items)} 场")
            remote += items
        with open(cache_file, "w", encoding="utf-8") as f:
            json.dump(remote, f, ensure_ascii=False)

    def variants(name):
        """队名的多种写法(含别名)"""
        out = {norm(name)}
        al = SEARCH_ALIAS.get(name)
        if al:
            out.add(norm(al))
        return {x for x in out if x}

    idx = {}          # (日期, 主队norm, 客队norm) -> fixture_id
    for fx in remote:
        d0 = fx["date"][:10]
        hset, aset = variants(fx.get("home_team_en")), variants(fx.get("away_team_en"))
        for h in hset:
            for a in aset:
                idx[(d0, h, a)] = fx["fixture_id"]

    def find(dstr, h, a):
        for hh in variants(h):
            for aa in variants(a):
                for dd in (dstr, (date.fromisoformat(dstr) + timedelta(days=1)).isoformat(),
                           (date.fromisoformat(dstr) - timedelta(days=1)).isoformat()):
                    if (dd, hh, aa) in idx:
                        return idx[(dd, hh, aa)]
        # 退化: 只要主客队都能对应上(不限日期)
        for k, v in idx.items():
            if any(hh in k[1] or k[1] in hh for hh in variants(h)) and \
               any(aa in k[2] or k[2] in aa for aa in variants(a)):
                return v
        return None

    mapped = 0
    for mid, d, h, a, lg in rows:
        fid = find(d[:10], h, a)
        if fid:
            conn.execute(
                "INSERT OR REPLACE INTO qxz_fixture_map VALUES (?,?,?,?,?,?,?)",
                (mid, fid, d, h, a, lg, datetime.now().isoformat(timespec="seconds")))
            mapped += 1
    conn.commit()
    print(f"  映射成功: {mapped} / {len(rows)}  ({mapped/max(len(rows),1):.0%})")
    conn.close()
    return mapped


def step4_stats_test(cli):
    print("\n" + "=" * 62)
    print("【4】验证技术统计接口(xG)")
    print("=" * 62)
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    row = conn.execute("""
        SELECT m.match_id, q.qxz_fixture_id, th.name h, ta.name a, m.status
        FROM qxz_fixture_map q JOIN matches m ON m.match_id=q.match_id
        JOIN teams th ON th.team_id=m.home_team_id
        JOIN teams ta ON ta.team_id=m.away_team_id
        WHERE m.status='FT' LIMIT 1""").fetchone()
    if not row:
        print("  暂无已完赛的映射比赛(未来赛程还没踢), 用今日总览里的一场完赛比赛测试")
        dg = cli.digest()
        ft = [m for m in (dg or {}).get("matches", []) if m.get("status") == "FT"][:1]
        if ft:
            print(f"  测试比赛: {ft[0]['home_team']} vs {ft[0]['away_team']} "
                  f"(fixture_id={ft[0]['fixture_id']})")
            st = cli.fixture_stats(ft[0]["fixture_id"])
            print("  返回:", json.dumps(st, ensure_ascii=False)[:600] if st else "无数据")
    else:
        print(f"  测试比赛: {row['h']} vs {row['a']} (fixture_id={row['qxz_fixture_id']})")
        st = cli.fixture_stats(row["qxz_fixture_id"])
        print("  返回:", json.dumps(st, ensure_ascii=False)[:600] if st else "无数据")
    conn.close()


if __name__ == "__main__":
    cli = QiuxiaoceClient()
    step1_backfill()
    lmap = step2_map_leagues(cli)
    step3_map_fixtures(cli, lmap)
    step4_stats_test(cli)
    print("\n" + "=" * 62)
    print(f"本次消耗点数(估算): {cli.spent_points} 点")
    print("=" * 62)
