#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""数据查看小工具 - 命令行快速浏览项目数据

用法示例:
    python scripts/view_data.py db                          # 数据库各表行数概览
    python scripts/view_data.py raw                         # 原始CSV文件列表
    python scripts/view_data.py leagues                     # 五大联赛信息
    python scripts/view_data.py teams --league 英超         # 某联赛球队
    python scripts/view_data.py elo --top 15                # Elo排行榜
    python scripts/view_data.py matches --league 英超 --season 2526 --limit 20
    python scripts/view_data.py matches --team Arsenal --result D --limit 10
    python scripts/view_data.py matches --from 2026-01-01 --to 2026-12-31
"""
import argparse
import csv
import os
import sqlite3
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RAW_DIR = os.path.join(BASE, "data", "raw")
PROC_DIR = os.path.join(BASE, "data", "processed")
MATCHES_CSV = os.path.join(PROC_DIR, "all_matches.csv")
ELO_CSV = os.path.join(PROC_DIR, "elo_ratings.csv")
DB_PATH = os.path.join(BASE, "data", "database", "football.db")

# 联赛名 <-> 代码
LEAGUE_CODE = {"英超": "E0", "西甲": "SP1", "德甲": "D1", "意甲": "I1", "法甲": "F1"}
CODE_LEAGUE = {v: k for k, v in LEAGUE_CODE.items()}
FTR_TEXT = {"H": "主胜", "D": "平局", "A": "客胜"}


def _normalize_console():
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def _load_matches():
    with open(MATCHES_CSV, encoding="utf-8-sig", errors="replace") as f:
        return list(csv.DictReader(f))


def _fuzzy_league(key):
    """支持中文名或代码(E0/SP1/...)"""
    if not key:
        return None
    if key in LEAGUE_CODE:
        return key
    if key in CODE_LEAGUE:
        return CODE_LEAGUE[key]
    raise SystemExit(f"未知联赛: {key}（可用: {', '.join(LEAGUE_CODE)} 或 E0/SP1/D1/I1/F1）")


# ==================== 各命令 ====================

def cmd_db(args):
    if not os.path.exists(DB_PATH):
        sys.exit(f"数据库不存在: {DB_PATH}")
    con = sqlite3.connect(DB_PATH)
    print(f"数据库: {DB_PATH}")
    print(f"{'表':<12} {'行数':>8}  说明")
    print("-" * 52)
    for t, desc in [("leagues", "联赛"), ("teams", "球队"), ("players", "球员"),
                    ("matches", "比赛"), ("transfers", "转会"), ("predictions", "预测记录")]:
        n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"{t:<12} {n:>8}  {desc}")
    # 比赛状态分布
    print()
    print("matches 状态分布:")
    for status, n in con.execute(
            "SELECT status, COUNT(*) FROM matches GROUP BY status ORDER BY 2 DESC"):
        print(f"  {status:<6} {n}")
    con.close()


def cmd_raw(args):
    files = sorted(f for f in os.listdir(RAW_DIR) if f.endswith(".csv"))
    print(f"raw 目录: {RAW_DIR}  ({len(files)} 个文件)")
    print(f"{'文件':<14} {'行数(含表头)':>10}  说明")
    print("-" * 60)
    for fn in files:
        with open(os.path.join(RAW_DIR, fn), encoding="utf-8-sig", errors="replace") as f:
            n = sum(1 for _ in f)
        code, season = fn.replace(".csv", "").split("_")
        league = CODE_LEAGUE.get(code, code)
        print(f"{fn:<14} {n:>10}  {league} {season[:2]}/{season[2:]}")


def cmd_leagues(args):
    if not os.path.exists(DB_PATH):
        sys.exit("数据库不存在")
    con = sqlite3.connect(DB_PATH)
    print(f"{'ID':<4} {'联赛':<8} {'英文名':<20} {'国家':<6} {'当前赛季'}")
    for r in con.execute("SELECT league_id,name,name_en,country,season FROM leagues ORDER BY league_id"):
        print(f"{r[0]:<4} {r[1]:<8} {r[2]:<20} {r[3]:<6} {r[4]}")
    con.close()


def cmd_teams(args):
    league = _fuzzy_league(args.league) if args.league else None
    if not os.path.exists(DB_PATH):
        sys.exit("数据库不存在")
    con = sqlite3.connect(DB_PATH)
    sql = ("SELECT t.name, t.name_en, l.name, t.elo_rating FROM teams t "
           "JOIN leagues l ON t.league_id = l.league_id")
    params = ()
    if league:
        sql += " WHERE l.name = ?"
        params = (league,)
    sql += " ORDER BY l.league_id, t.elo_rating DESC"
    rows = con.execute(sql, params).fetchall()
    print(f"{'队名':<22} {'英文名':<22} {'联赛':<6} {'Elo'}")
    print("-" * 60)
    for name, name_en, lname, elo in rows:
        print(f"{name:<22} {name_en:<22} {lname:<6} {elo:.1f}")
    print(f"\n共 {len(rows)} 支球队")
    con.close()


def cmd_elo(args):
    if not os.path.exists(ELO_CSV):
        sys.exit(f"Elo文件不存在: {ELO_CSV}")
    with open(ELO_CSV, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    if not rows:
        sys.exit("Elo文件为空")
    top = args.top or len(rows)
    print(f"Elo 评级 Top {min(top, len(rows))} / 共 {len(rows)} 支球队")
    print(f"{'排名':<5} {'球队':<24} {'Elo':>8}")
    print("-" * 42)
    for i, r in enumerate(rows[:top], 1):
        team = r.get("team") or r.get("Team") or ""
        elo = r.get("elo_rating") or r.get("rating") or ""
        print(f"{i:<5} {team:<24} {float(elo):>8.1f}")


def cmd_matches(args):
    league = _fuzzy_league(args.league) if args.league else None
    code = LEAGUE_CODE[league] if league else None
    rows = _load_matches()
    total = len(rows)

    def keep(r):
        if code and r.get("Div") != code:
            return False
        if args.season and r.get("season") != args.season:
            return False
        if args.team:
            t = args.team.lower()
            if t not in (r.get("HomeTeam") or "").lower() and t not in (r.get("AwayTeam") or "").lower():
                return False
        if args.result:
            m = {"主胜": "H", "平局": "D", "客胜": "A", "H": "H", "D": "D", "A": "A"}
            want = m.get(args.result)
            if not want or r.get("FTR") != want:
                return False
        if args.from_date and (r.get("Date") or "") < args.from_date:
            return False
        if args.to_date and (r.get("Date") or "") > args.to_date:
            return False
        return True

    out = [r for r in rows if keep(r)]
    # 排序: 日期升序
    out.sort(key=lambda r: r.get("Date") or "")
    limit = args.limit or len(out)
    out = out[:limit]

    has_xg = any((r.get("HxG") or "") != "" for r in out)
    head = f"{'日期':<11} {'联赛':<5} {'主队':<16} {'客队':<16} {'比分':>5} {'结果':<4} {'赛季'}"
    if has_xg:
        head += f" {'主xG':>6} {'客xG':>6}"
    print(head)
    print("-" * (len(head) if has_xg else 76))
    for r in out:
        score = f"{r.get('FTHG')}-{r.get('FTAG')}"
        line = (f"{(r.get('Date') or '')[:10]:<11} {CODE_LEAGUE.get(r.get('Div'), r.get('Div')):<5} "
                f"{(r.get('HomeTeam') or ''):<16} {(r.get('AwayTeam') or ''):<16} "
                f"{score:>5} {FTR_TEXT.get(r.get('FTR'), ''):<4} {r.get('season')}")
        if has_xg:
            hx = r.get("HxG") or ""
            ax = r.get("AxG") or ""
            line += f" {hx:>6} {ax:>6}"
        print(line)
    print(f"\n筛选结果: 显示 {len(out)} / {len([r for r in rows if keep(r)])} 场 (共 {total} 场)")
    if not out:
        print("提示: 无匹配结果，可去掉部分筛选条件")


# ==================== 参数解析 ====================

def build_parser():
    p = argparse.ArgumentParser(
        prog="view_data", description="足球数据查看小工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True, metavar="命令")

    sub.add_parser("db", help="数据库各表行数概览")
    sub.add_parser("raw", help="原始CSV文件列表")
    sub.add_parser("leagues", help="联赛信息")

    pt = sub.add_parser("teams", help="球队列表")
    pt.add_argument("--league", help="联赛: 英超/西甲/德甲/意甲/法甲 或代码")

    pe = sub.add_parser("elo", help="Elo排行榜")
    pe.add_argument("--top", type=int, default=10, help="显示前N名")

    pm = sub.add_parser("matches", help="按条件筛选比赛")
    pm.add_argument("--league", help="联赛: 英超/西甲/德甲/意甲/法甲 或代码")
    pm.add_argument("--season", help="赛季代码, 如 2526")
    pm.add_argument("--team", help="球队名(模糊匹配主客队)")
    pm.add_argument("--result", help="赛果: H/D/A 或 主胜/平局/客胜")
    pm.add_argument("--from-date", dest="from_date", help="起始日期 YYYY-MM-DD")
    pm.add_argument("--to-date", dest="to_date", help="截止日期 YYYY-MM-DD")
    pm.add_argument("--limit", type=int, default=20, help="最多显示行数")
    return p


def main():
    _normalize_console()
    args = build_parser().parse_args()
    {
        "db": cmd_db, "raw": cmd_raw, "leagues": cmd_leagues,
        "teams": cmd_teams, "elo": cmd_elo, "matches": cmd_matches,
    }[args.cmd](args)


if __name__ == "__main__":
    main()
