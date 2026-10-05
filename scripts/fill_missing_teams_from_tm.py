# -*- coding: utf-8 -*-
"""用 Transfermarkt 阵容补"仍无球员"的球队(精确数据, 非猜测)

对每支 0 球员且已映射 TM 俱乐部的球队:
  取该俱乐部最近赛季阵容 -> 写入我们的 players 表(含国籍/身高/惯用脚/身价/头像)

用法: python scripts/fill_missing_teams_from_tm.py
"""
import sqlite3
from pathlib import Path

BASE = Path(__file__).parent.parent
DB = BASE / "data" / "database" / "football.db"


def main():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    targets = c.execute("""
        SELECT t.team_id, t.name, m.club_id
        FROM teams t JOIN tm_club_map m ON m.team_id = t.team_id
        WHERE t.team_id NOT IN (SELECT DISTINCT team_id FROM players)""").fetchall()
    print(f"仍无球员且已映射 TM 的球队: {len(targets)} 支")

    added = 0
    for t in targets:
        # 该俱乐部最近赛季阵容
        latest = c.execute("SELECT MAX(season_start) FROM tm_player_seasons WHERE team_id=?",
                           (t["club_id"],)).fetchone()[0]
        if not latest:
            continue
        squad = c.execute("""
            SELECT p.player_id, p.player_name, p.position, p.main_position,
                   p.date_of_birth, p.citizenship, p.height, p.foot, p.image_url,
                   (SELECT value FROM tm_player_market_value v WHERE v.player_id=p.player_id
                    ORDER BY date_unix DESC LIMIT 1) AS mv
            FROM tm_players p
            JOIN tm_player_seasons s ON s.player_id = p.player_id
            WHERE s.team_id=? AND s.season_start=?
            GROUP BY p.player_id""", (t["club_id"], latest)).fetchall()
        n = 0
        for p in squad:
            dob = str(p["date_of_birth"] or "")[:4]
            age = (2026 - int(dob)) if dob.isdigit() else None
            exists = c.execute("SELECT 1 FROM players WHERE team_id=? AND name=? LIMIT 1",
                               (t["team_id"], p["player_name"])).fetchone()
            if exists:
                continue
            c.execute("""INSERT INTO players (team_id, name, name_en, position, nationality,
                            age, height, weight, number, market_value, photo_url,
                            stats_json, created_at, tm_player_id)
                         VALUES (?,?,?,?,?,?,?,NULL,NULL,?,?,?,?,?)""",
                      (t["team_id"], p["player_name"], p["player_name"],
                       p["main_position"] or p["position"], p["citizenship"], age,
                       p["height"], p["mv"], p["image_url"],
                       '{"source":"transfermarkt"}',
                       "2026-09-10 20:00:00", p["player_id"]))
            n += 1
        c.commit()
        added += n
        if n:
            print(f"  ✓ {t['name']:<18} +{n} 人 (TM {latest} 赛季)")

    print(f"\n共补入球员 {added} 名")
    q = lambda s: c.execute(s).fetchone()[0]
    print("players 总数:", q("SELECT COUNT(*) FROM players"))
    print("有球员的球队:", q("SELECT COUNT(DISTINCT team_id) FROM players"),
          "/", q("SELECT COUNT(*) FROM teams"))
    c.close()


if __name__ == "__main__":
    main()
