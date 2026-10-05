# -*- coding: utf-8 -*-
"""积分榜重建 —— 直接用本库比赛结果计算, 彻底解决"缺行/排名重复/跳号"

优点:
  - 行数完整(所有出过场的球队都在)
  - 排名按 (积分, 净胜球, 进球, 队名) 严格递推, 不会出现并列跳号
  - 与比赛数据完全一致(不会出现"积分榜说 4 场、我们只有 3 场"的矛盾)

用法:
    python scripts/rebuild_standings.py            # 预演
    python scripts/rebuild_standings.py --apply    # 执行
"""
import argparse
import sqlite3
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"

# 完整赛季的期望场次(用于标注覆盖率, 不阻断重建)
EXPECTED = {1: 380, 2: 380, 3: 306, 4: 380, 5: 306, 6: None, 7: 552,
            8: 306, 9: 306, 10: 380}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    print(f"=== 积分榜重建({'执行' if args.apply else '预演'}) ===\n")

    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    total_leagues = total_rows = 0
    for lg in c.execute("""SELECT DISTINCT league_id, season FROM matches
                           WHERE status='FT' AND home_goals IS NOT NULL
                           ORDER BY league_id, season"""):
        lid, season = lg["league_id"], lg["season"]
        lname = c.execute("SELECT name FROM leagues WHERE league_id=?", (lid,)).fetchone()[0]
        rows = c.execute("""
            SELECT t.team_id, t.name,
                   COUNT(*) played,
                   SUM(CASE WHEN (m.home_team_id=t.team_id AND m.home_goals>m.away_goals)
                              OR (m.away_team_id=t.team_id AND m.away_goals>m.home_goals)
                            THEN 1 ELSE 0 END) won,
                   SUM(CASE WHEN m.home_goals=m.away_goals THEN 1 ELSE 0 END) drawn,
                   SUM(CASE WHEN (m.home_team_id=t.team_id AND m.home_goals<m.away_goals)
                              OR (m.away_team_id=t.team_id AND m.away_goals<m.home_goals)
                            THEN 1 ELSE 0 END) lost,
                   SUM(CASE WHEN m.home_team_id=t.team_id THEN m.home_goals
                            ELSE m.away_goals END) gf,
                   SUM(CASE WHEN m.home_team_id=t.team_id THEN m.away_goals
                            ELSE m.home_goals END) ga
            FROM matches m
            JOIN teams t ON t.team_id IN (m.home_team_id, m.away_team_id)
            WHERE m.league_id=? AND m.season=? AND m.status='FT'
              AND m.home_goals IS NOT NULL
            GROUP BY t.team_id""", (lid, season)).fetchall()
        if not rows:
            continue
        table = []
        for r in rows:
            gd = (r["gf"] or 0) - (r["ga"] or 0)
            pts = (r["won"] or 0) * 3 + (r["drawn"] or 0)
            table.append({"team_id": r["team_id"], "name": r["name"],
                          "played": r["played"], "won": r["won"], "draw": r["drawn"],
                          "lost": r["lost"], "gf": r["gf"] or 0, "ga": r["ga"] or 0,
                          "gd": gd, "points": pts})
        table.sort(key=lambda x: (-x["points"], -x["gd"], -x["gf"], x["name"]))
        n_matches = c.execute("""SELECT COUNT(*) FROM matches
                                 WHERE league_id=? AND season=? AND status='FT'""",
                              (lid, season)).fetchone()[0]
        exp = EXPECTED.get(lid)
        cover = f"{n_matches}/{exp}" if exp else f"{n_matches}/-"
        print(f"  {lname:<5} {season}: {len(table)} 支球队 | 比赛 {cover} | "
              f"榜首 {table[0]['name']} ({table[0]['points']}分)")
        if args.apply:
            # 近 5 场走势
            forms = {}
            for t in table:
                last = c.execute("""
                    SELECT CASE WHEN (m.home_team_id=? AND m.home_goals>m.away_goals)
                                  OR (m.away_team_id=? AND m.away_goals>m.home_goals) THEN 'W'
                                WHEN m.home_goals=m.away_goals THEN 'D' ELSE 'L' END res
                    FROM matches m
                    WHERE m.league_id=? AND m.season=? AND m.status='FT'
                      AND (m.home_team_id=? OR m.away_team_id=?)
                    ORDER BY m.date DESC LIMIT 5""",
                    (t["team_id"], t["team_id"], lid, season,
                     t["team_id"], t["team_id"])).fetchall()
                forms[t["team_id"]] = "".join(x["res"] for x in last)
            c.execute("DELETE FROM standings WHERE league_id=? AND season=?", (lid, season))
            for i, t in enumerate(table, 1):
                c.execute("""INSERT INTO standings
                    (league_id, season, team_id, rank, played, won, draw, lost,
                     goals_for, goals_against, goal_diff, points, form, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                    (lid, season, t["team_id"], i, t["played"], t["won"], t["draw"],
                     t["lost"], t["gf"], t["ga"], t["gd"], t["points"],
                     forms.get(t["team_id"], ""), now))
            total_leagues += 1
            total_rows += len(table)
    if args.apply:
        c.commit()
        print(f"\n已重建 {total_leagues} 个(联赛,赛季)组合, 共 {total_rows} 行")
        n = c.execute("SELECT COUNT(*) FROM standings").fetchone()[0]
        print(f"standings 总行数: {n}")
    else:
        print("\n(预演模式, 未写入; 加 --apply 执行)")
    c.close()


if __name__ == "__main__":
    main()
