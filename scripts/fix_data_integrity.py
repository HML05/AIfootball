# -*- coding: utf-8 -*-
"""数据完整性修复

修复三类问题(对应 UI 截图中的"数据缺失/错乱/错误"):
  ① 重复/脏球队行  -> 合并到规范队(迁移球员/比赛/积分榜/TM映射后删除)
  ② 积分榜排名错乱  -> 忽略源 rank, 按 (积分, 净胜球, 进球) 重排 1..N
  ③ Elo 未计算      -> 用全库比赛(含英冠/欧冠等)递推重算, 写回 teams.elo_rating

用法:
    python scripts/fix_data_integrity.py            # 预演
    python scripts/fix_data_integrity.py --apply    # 执行
"""
import argparse
import sqlite3
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"

# 脏队名 -> 规范名(仅当规范名存在时合并)
MERGE = {
    "Espanyol": "Espanol", "Rayo Vallecano": "Vallecano",
    "Real Sociedad": "Sociedad", "Olympique Lyon": "Lyon",
    "Angers Sco": "Angers", "Schalke": "Schalke 04",
    "": "La Coruna",                    # 空名(球场为 Riazor)
    "1. Koln": "FC Koln",               # 同一俱乐部两行
    "Psg": "Paris SG",                  # 同一俱乐部两行
    "Wolverhampton": "Wolves", "Nottingham": "Nott'm Forest",
    "Brighton Hove": "Brighton", "Bayern": "Bayern Munich",
    "Hsv": "Hamburg", "Bremen": "Werder Bremen", "Frankfurt": "Ein Frankfurt",
    "Atleti": "Ath Madrid",
    "Ipswich Town": "Ipswich", "Coventry City": "Coventry",
    "Leicester City": "Leicester", "Real Betis": "Betis",
    "Como 1907": "Como", "Nac": "NAC Breda", "Az": "AZ Alkmaar",
}


def recompute_elo(c, apply=False, k=20.0, hfa=65.0):
    """用全部已完赛比赛递推 Elo(跨赛事统一池), 返回 team_id -> elo"""
    rows = c.execute("""
        SELECT m.date, m.home_team_id h, m.away_team_id a,
               m.home_goals hg, m.away_goals ag
        FROM matches m
        WHERE m.status='FT' AND m.home_goals IS NOT NULL AND m.away_goals IS NOT NULL
          AND m.home_team_id IS NOT NULL AND m.away_team_id IS NOT NULL
        ORDER BY m.date""").fetchall()
    elo = {}
    for r in rows:
        h, a = r["h"], r["a"]
        eh, ea = elo.get(h, 1500.0), elo.get(a, 1500.0)
        exp_h = 1.0 / (1.0 + 10 ** ((ea - (eh + hfa)) / 400.0))
        actual = 1.0 if r["hg"] > r["ag"] else (0.5 if r["hg"] == r["ag"] else 0.0)
        delta = k * (1.0 + 0.15 * abs(r["hg"] - r["ag"])) * (actual - exp_h)
        elo[h], elo[a] = eh + delta, ea - delta
    if apply:
        c.executemany("UPDATE teams SET elo_rating=? WHERE team_id=?",
                      [(round(v, 1), k2) for k2, v in elo.items()])
    return elo


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    tag = "执行" if args.apply else "预演"
    print(f"=== 数据完整性修复({tag}) ===\n")

    # ---------- ① 合并脏球队 ----------
    print("① 重复/脏球队合并")
    by_name = {r["name"]: r["team_id"] for r in c.execute("SELECT team_id, name FROM teams")}
    merged = 0
    for dup, canon in MERGE.items():
        did, cid = by_name.get(dup), by_name.get(canon)
        if did is None or cid is None:
            if dup == "" or did is not None:
                print(f"   跳过 {dup!r} -> {canon!r} (规范名不存在)" if cid is None
                      else f"   跳过 {dup!r} (不存在)")
            continue
        stats = {}
        for label, sql in [("球员", "players"), ("积分榜", "standings"),
                           ("TM映射", "tm_club_map")]:
            key = "team_id"
            stats[label] = c.execute(f"SELECT COUNT(*) FROM {sql} WHERE {key}=?", (did,)).fetchone()[0]
        n_home = c.execute("SELECT COUNT(*) FROM matches WHERE home_team_id=?", (did,)).fetchone()[0]
        n_away = c.execute("SELECT COUNT(*) FROM matches WHERE away_team_id=?", (did,)).fetchone()[0]
        print(f"   合并 {dup!r} -> {canon!r} | 球员{stats['球员']} 比赛{n_home + n_away} "
              f"积分榜{stats['积分榜']} TM映射{stats['TM映射']}")
        if args.apply:
            c.execute("UPDATE players SET team_id=? WHERE team_id=?", (cid, did))
            c.execute("UPDATE matches SET home_team_id=? WHERE home_team_id=?", (cid, did))
            c.execute("UPDATE matches SET away_team_id=? WHERE away_team_id=?", (cid, did))
            c.execute("UPDATE standings SET team_id=? WHERE team_id=?", (cid, did))
            c.execute("INSERT OR IGNORE INTO tm_club_map "
                      "(team_id, club_id, tm_name, tm_country, tm_competition, tm_logo, method) "
                      "SELECT ?, club_id, tm_name, tm_country, tm_competition, tm_logo, 'merged' "
                      "FROM tm_club_map WHERE team_id=?", (cid, did))
            c.execute("DELETE FROM tm_club_map WHERE team_id=?", (did,))
            c.execute("DELETE FROM teams WHERE team_id=?", (did,))
        merged += 1
    if args.apply:
        c.commit()
    print(f"   共合并 {merged} 支")

    # ---------- ② 积分榜排名重排 ----------
    print("\n② 积分榜排名重排(按 积分/净胜球/进球)")
    fixed = 0
    for r in c.execute("""SELECT league_id, season FROM standings
                          GROUP BY league_id, season"""):
        rows = c.execute("""SELECT id, team_id, points, goal_diff, goals_for, rank
                            FROM standings WHERE league_id=? AND season=?""",
                         (r["league_id"], r["season"])).fetchall()
        order = sorted(rows, key=lambda x: (-(x["points"] or 0), -(x["goal_diff"] or 0),
                                            -(x["goals_for"] or 0), x["team_id"]))
        if [x["rank"] for x in order] != list(range(1, len(order) + 1)):
            fixed += 1
            if args.apply:
                for i, x in enumerate(order, 1):
                    c.execute("UPDATE standings SET rank=? WHERE id=?", (i, x["id"]))
    if args.apply:
        c.commit()
    print(f"   重排了 {fixed} 个(联赛,赛季)组合")

    # ---------- ③ 缺失球队检测 ----------
    print("\n③ 积分榜缺行检测(比赛里有、积分榜里没有的球队)")
    miss_total = 0
    for r in c.execute("""SELECT league_id, season FROM matches
                          WHERE status='FT' GROUP BY league_id, season"""):
        played = {x[0] for x in c.execute("""
            SELECT DISTINCT home_team_id FROM matches
            WHERE league_id=? AND season=? AND status='FT'
            UNION SELECT DISTINCT away_team_id FROM matches
            WHERE league_id=? AND season=? AND status='FT'""",
            (r["league_id"], r["season"], r["league_id"], r["season"]))}
        have = {x[0] for x in c.execute(
            "SELECT team_id FROM standings WHERE league_id=? AND season=?",
            (r["league_id"], r["season"]))}
        missing = played - have
        if missing:
            miss_total += len(missing)
            names = [c.execute("SELECT name FROM teams WHERE team_id=?", (m,)).fetchone()[0]
                     for m in missing]
            lname = c.execute("SELECT name FROM leagues WHERE league_id=?",
                              (r["league_id"],)).fetchone()[0]
            print(f"   {lname} {r['season']}: 缺 {names}")

    # ---------- ④ Elo 重算 ----------
    print("\n④ Elo 重算(全库比赛递推, 跨赛事)")
    elo = recompute_elo(c, apply=args.apply)
    print(f"   计算了 {len(elo)} 支球队; 原默认值(1500)球队数: "
          f"{c.execute('SELECT COUNT(*) FROM teams WHERE elo_rating=1500').fetchone()[0]}")
    if args.apply:
        print(f"   示例: Arsenal={elo.get(1, 0):.0f}  "
              f"Real Madrid={elo.get(52, 0):.0f}")
    c.close()
    if not args.apply:
        print("\n(预演模式, 未修改数据库; 加 --apply 执行)")


if __name__ == "__main__":
    main()
