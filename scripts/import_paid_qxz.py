# -*- coding: utf-8 -*-
"""球小策付费批次导入(转会 / 主教练 / 赛前全景包 / 阵容)

全部带"预算上限"和 --dry-run 预演, 避免点数失控。

用法:
    python scripts/import_paid_qxz.py transfers  --budget 200 --dry-run
    python scripts/import_paid_qxz.py coaches    --budget 500
    python scripts/import_paid_qxz.py matchpacks --limit 30 --budget 1500
    python scripts/import_paid_qxz.py lineups    --limit 100 --budget 500
"""
import argparse
import json
import os
import sqlite3
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.data_sources.qiuxiaoce import QiuxiaoceClient  # noqa: E402
from scripts.import_squads_qxz import (build_team_map, lookup_team_id)  # noqa: E402

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB = os.path.join(BASE, "data", "database", "football.db")


def _conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def _ensure_tables(conn):
    conn.execute("""CREATE TABLE IF NOT EXISTS qxz_match_pack (
        match_id INTEGER PRIMARY KEY, fixture_id INTEGER, kickoff TEXT,
        payload TEXT, created_at TEXT)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS qxz_lineups (
        match_id INTEGER PRIMARY KEY, fixture_id INTEGER,
        payload TEXT, created_at TEXT)""")
    cols = {r[1] for r in conn.execute("PRAGMA table_info(transfers)")}
    if cols and "season" not in cols:
        conn.execute("ALTER TABLE transfers ADD COLUMN season TEXT")
    conn.commit()


def cmd_transfers(cli, args):
    """每队最近 50 条转会 (2点/队)"""
    conn = _conn()
    _ensure_tables(conn)
    tmap = build_team_map()
    teams = conn.execute("""SELECT DISTINCT t.team_id, t.name, t.league_id
        FROM standings s JOIN teams t ON t.team_id=s.team_id
        WHERE s.season='2627' ORDER BY t.name""").fetchall()
    est = len(teams) * 2
    print(f"计划: {len(teams)} 支球队 × 2点 ≈ {est} 点")
    if args.dry_run:
        return 0
    added = 0
    for i, t in enumerate(teams, 1):
        if cli.spent_points + 2 > args.budget:
            print(f"⏹ 达到预算 {args.budget} 点")
            break
        qid, how = lookup_team_id(cli, tmap, t["name"], t["league_id"])
        if not qid:
            continue
        d = cli._get("/transfers", {"team": qid}, cost=2)
        for tr in (d or {}).get("data", []):
            tin = (tr.get("team_in") or {}).get("team_name")
            tout = (tr.get("team_out") or {}).get("team_name")
            conn.execute("""
                INSERT INTO transfers (player_name, from_team_name, to_team_name,
                    transfer_date, transfer_fee, transfer_type, season, created_at)
                VALUES (?,?,?,?,NULL,?,?,?)""",
                (tr.get("player_name"),
                 tout if tr.get("direction") == "out" else tin,
                 tin if tr.get("direction") == "out" else tout,
                 tr.get("date"), tr.get("type"), str(tr.get("season")),
                 datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
            added += 1
        conn.commit()
        if i % 10 == 0:
            print(f"  [{i}/{len(teams)}] 累计转会 {added} 条 | 点数 ~{cli.spent_points}")
    print(f"完成: 新增转会 {added} 条 | 点数 ~{cli.spent_points}")
    conn.close()
    return 0


def cmd_coaches(cli, args):
    """从阵容接口提取主教练 (5点/队)"""
    conn = _conn()
    tmap = build_team_map()
    teams = conn.execute("""SELECT DISTINCT t.team_id, t.name, t.league_id
        FROM standings s JOIN teams t ON t.team_id=s.team_id
        WHERE s.season='2627' AND (t.manager IS NULL OR t.manager='')
        ORDER BY t.name""").fetchall()
    est = len(teams) * 5
    print(f"计划: {len(teams)} 支球队 × 5点 ≈ {est} 点")
    if args.dry_run:
        return 0
    got = 0
    for i, t in enumerate(teams, 1):
        if cli.spent_points + 5 > args.budget:
            print(f"⏹ 达到预算 {args.budget} 点")
            break
        qid, _ = lookup_team_id(cli, tmap, t["name"], t["league_id"])
        if not qid:
            continue
        sq = cli.team_squad(qid)
        coach = None
        for p in (sq or {}).get("data", []):
            pos = (p.get("position") or "").lower()
            if "coach" in pos or "manager" in pos:
                coach = p.get("name")
                break
        if not coach:
            coach = ((sq or {}).get("team") or {}).get("coach")
        if coach:
            conn.execute("UPDATE teams SET manager=? WHERE team_id=?",
                         (coach, t["team_id"]))
            conn.commit()
            got += 1
        print(f"  [{i}/{len(teams)}] {t['name']} -> {coach or '未找到'} | 点数 ~{cli.spent_points}")
    print(f"完成: 补主教练 {got} 队 | 点数 ~{cli.spent_points}")
    conn.close()
    return 0


def cmd_matchpacks(cli, args):
    """赛前全景包 (50点/场)

    注意: 距开赛较远时服务端只返回"基础快照"并退还点数;
    完整包通常在临近开赛(约24-36小时内)才生成 → 用 --max-hours-ahead 控制。
    """
    conn = _conn()
    _ensure_tables(conn)
    rows = conn.execute("""
        SELECT m.match_id, q.qxz_fixture_id, m.date, th.name h, ta.name a
        FROM qxz_fixture_map q JOIN matches m ON m.match_id=q.match_id
        JOIN teams th ON th.team_id=m.home_team_id
        JOIN teams ta ON ta.team_id=m.away_team_id
        WHERE m.status='NS' ORDER BY m.date""").fetchall()
    all_n = len(rows)
    now = datetime.now()
    if args.max_hours_ahead:
        rows = [r for r in rows
                if 0 <= (datetime.fromisoformat(r["date"]) - now).total_seconds() / 3600
                <= args.max_hours_ahead]
        print(f"时间过滤: {all_n} 场未开赛 → {len(rows)} 场在 {args.max_hours_ahead} 小时内开赛")
    if args.limit:
        rows = rows[:args.limit]
    est = len(rows) * 50
    print(f"计划: {len(rows)} 场 × 50点 ≈ {est} 点")
    for r in rows[:10]:
        print(f"   {r['date'][:16]} {r['h']} vs {r['a']}")
    if len(rows) > 10:
        print(f"   ... 其余 {len(rows)-10} 场")
    if args.dry_run:
        return 0
    ok = full_cnt = partial_cnt = refunded = 0
    for i, r in enumerate(rows, 1):
        if cli.spent_points + 50 > args.budget:
            print(f"⏹ 达到预算 {args.budget} 点")
            break
        d = cli.match_pack(r["qxz_fixture_id"])
        if not d:
            continue
        meta = d.get("meta") or {}
        is_full = bool(meta.get("is_full_pack"))
        rf = int(meta.get("credits_refunded") or 0)
        if rf:
            cli.spent_points -= rf            # 未就绪时服务端会退还点数
            refunded += rf
        conn.execute("INSERT OR REPLACE INTO qxz_match_pack VALUES (?,?,?,?,?)",
                     (r["match_id"], r["qxz_fixture_id"], r["date"],
                      json.dumps(d, ensure_ascii=False),
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        ok += 1
        full_cnt += is_full
        partial_cnt += (not is_full)
        print(f"  [{i}/{len(rows)}] {'✓ 完整' if is_full else '… 未就绪'} "
              f"{r['h']} vs {r['a']} | 估算净消耗 ~{cli.spent_points}"
              + (f" (退还{rf})" if rf else ""))
    print(f"完成: 抓取 {ok} 场 (完整 {full_cnt} / 未就绪 {partial_cnt}) | "
          f"退还 {refunded} 点 | 估算净消耗 ~{cli.spent_points}")
    conn.close()
    return 0


def cmd_lineups(cli, args):
    """已完赛比赛的阵容 (5点/场)"""
    conn = _conn()
    _ensure_tables(conn)
    rows = conn.execute("""
        SELECT m.match_id, q.qxz_fixture_id, m.date, th.name h, ta.name a
        FROM qxz_fixture_map q JOIN matches m ON m.match_id=q.match_id
        JOIN teams th ON th.team_id=m.home_team_id
        JOIN teams ta ON ta.team_id=m.away_team_id
        WHERE m.status='FT' ORDER BY m.date DESC""").fetchall()
    if args.limit:
        rows = rows[:args.limit]
    est = len(rows) * 5
    print(f"计划: {len(rows)} 场 × 5点 ≈ {est} 点")
    if args.dry_run:
        return 0
    ok = 0
    for i, r in enumerate(rows, 1):
        if cli.spent_points + 5 > args.budget:
            print(f"⏹ 达到预算 {args.budget} 点")
            break
        d = cli.fixture_lineups(r["qxz_fixture_id"])
        if not d:
            continue
        conn.execute("INSERT OR REPLACE INTO qxz_lineups VALUES (?,?,?,?)",
                     (r["match_id"], r["qxz_fixture_id"],
                      json.dumps(d, ensure_ascii=False),
                      datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()
        ok += 1
    print(f"完成: 抓取 {ok} 场阵容 | 点数 ~{cli.spent_points}")
    conn.close()
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("command", choices=["transfers", "coaches", "matchpacks", "lineups"])
    ap.add_argument("--budget", type=int, default=300)
    ap.add_argument("--limit", type=int, default=None)
    ap.add_argument("--max-hours-ahead", dest="max_hours_ahead", type=float, default=None,
                    help="只抓 N 小时内开赛的比赛(赛前包临近开赛才完整)")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cli = QiuxiaoceClient()
    cli.spent_points = 0
    {"transfers": cmd_transfers, "coaches": cmd_coaches,
     "matchpacks": cmd_matchpacks, "lineups": cmd_lineups}[args.command](cli, args)


if __name__ == "__main__":
    main()
