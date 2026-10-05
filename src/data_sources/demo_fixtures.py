# -*- coding: utf-8 -*-
"""演示模式赛程生成器 (Demo Fixtures)

无 API-Football Key 时，用数据库中已有的当前赛季(2627)球队，
按日期生成确定性(伪随机)的"未来赛程"写入 matches 表(status=NS)，
让界面能看到"今天/明天/未来几天"的比赛。

- 同一日期再次运行不会重复插入(幂等)
- 所有插入记录都写入 data/demo_fixtures.json 标记文件，
  之后可用 clear_demo_fixtures() 一键清除，不影响历史真实数据
- 配置真实 API Key 后，接入真实同步即可，演示数据可随时清掉
"""
import json
import os
import random
import sqlite3
from datetime import datetime, timedelta

BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DB_PATH = os.path.join(BASE, "data", "database", "football.db")
MARKER_PATH = os.path.join(BASE, "data", "demo_fixtures.json")
SEASON = "2627"          # 当前赛季
TIME_POOL = ["12:30", "14:00", "15:00", "16:30", "17:30",
             "18:00", "19:30", "20:00", "20:30", "21:00", "22:00"]
MATCHES_PER_LEAGUE_PER_DAY = 5


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _current_teams(conn, league_id: int):
    """取该联赛当前赛季(2627)已出场球队; 不足则退回联赛全部球队"""
    rows = conn.execute("""
        SELECT DISTINCT t.team_id FROM matches m
        JOIN teams t ON t.team_id IN (m.home_team_id, m.away_team_id)
        WHERE m.league_id = ? AND m.season = ?
    """, (league_id, SEASON)).fetchall()
    ids = [r["team_id"] for r in rows]
    if len(ids) < 12:
        ids = [r["team_id"] for r in conn.execute(
            "SELECT team_id FROM teams WHERE league_id = ?", (league_id,))]
    return sorted(set(ids))


def _exists(conn, league_id, date_str, home_id, away_id) -> bool:
    row = conn.execute("""
        SELECT 1 FROM matches
        WHERE league_id = ? AND date = ? AND home_team_id = ? AND away_team_id = ?
        LIMIT 1
    """, (league_id, date_str, home_id, away_id)).fetchone()
    return row is not None


def _load_marker():
    if os.path.exists(MARKER_PATH):
        with open(MARKER_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def _save_marker(records):
    with open(MARKER_PATH, "w", encoding="utf-8") as f:
        json.dump(records, f, ensure_ascii=False, indent=1)


def generate_fixtures(days: int = 3, start_date=None) -> dict:
    """生成未来 days 天的演示赛程。返回统计信息。"""
    now = datetime.now()
    start = start_date or now.date()
    conn = _conn()
    created = 0
    marker = _load_marker()

    leagues = conn.execute("SELECT league_id FROM leagues ORDER BY league_id").fetchall()

    for lg in leagues:
        lid = lg["league_id"]
        teams = _current_teams(conn, lid)
        if len(teams) < 2:
            continue
        for offset in range(days):
            day = start + timedelta(days=offset)
            day_str = day.isoformat()
            rng = random.Random(f"demo-{lid}-{day_str}")
            shuffled = rng.sample(teams, min(len(teams), MATCHES_PER_LEAGUE_PER_DAY * 2))
            pairs = []
            for i in range(0, len(shuffled) - 1, 2):
                pairs.append((shuffled[i], shuffled[i + 1]))
                if len(pairs) >= MATCHES_PER_LEAGUE_PER_DAY:
                    break
            times = sorted(rng.sample(TIME_POOL, min(len(pairs), len(TIME_POOL))))
            for (home_id, away_id), hm in zip(pairs[:len(times)], times):
                date_str = f"{day_str} {hm}:00"
                # 今天的比赛只生成仍未开球的场次(留 45 分钟余量)
                if offset == 0:
                    kick = datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S")
                    if kick <= now + timedelta(minutes=45):
                        continue
                sig = {"league_id": lid, "date": date_str,
                       "home_team_id": home_id, "away_team_id": away_id}
                if _exists(conn, lid, date_str, home_id, away_id):
                    # 已存在: 若为NS且未标记, 补记(保证 clear 能清除)
                    row = conn.execute(
                        "SELECT status FROM matches WHERE league_id=? AND date=? "
                        "AND home_team_id=? AND away_team_id=?",
                        (lid, date_str, home_id, away_id)).fetchone()
                    if row and row["status"] == "NS" and sig not in marker:
                        marker.append(sig)
                    continue
                conn.execute("""
                    INSERT INTO matches
                        (league_id, season, matchday, date, home_team_id, away_team_id,
                         home_goals, away_goals, status, created_at)
                    VALUES (?, ?, NULL, ?, ?, ?, NULL, NULL, 'NS', ?)
                """, (lid, SEASON, date_str, home_id, away_id,
                      now.strftime("%Y-%m-%d %H:%M:%S")))
                marker.append(sig)
                created += 1

    conn.commit()
    conn.close()

    # 统计
    stats = _count_by_status_and_day()
    _save_marker(marker)
    return {"created": created, **stats}


def clear_demo_fixtures() -> int:
    """删除所有由演示模式生成的记录(status=NS 且命中标记文件)"""
    marker = _load_marker()
    if not marker:
        return 0
    conn = _conn()
    removed = 0
    for rec in marker:
        cur = conn.execute("""
            DELETE FROM matches
            WHERE league_id = ? AND date = ? AND home_team_id = ? AND away_team_id = ?
              AND status = 'NS'
        """, (rec["league_id"], rec["date"], rec["home_team_id"], rec["away_team_id"]))
        removed += cur.rowcount
    conn.commit()
    conn.close()
    _save_marker([])
    return removed


def _count_by_status_and_day() -> dict:
    """统计: 全部NS / 今日NS / 明日NS / 每联赛NS数"""
    conn = _conn()
    today = datetime.now().date().isoformat()
    tomorrow = (datetime.now().date() + timedelta(days=1)).isoformat()
    total_ns = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status = 'NS'").fetchone()[0]
    today_ns = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status='NS' AND date(date) = ?",
        (today,)).fetchone()[0]
    tomorrow_ns = conn.execute(
        "SELECT COUNT(*) FROM matches WHERE status='NS' AND date(date) = ?",
        (tomorrow,)).fetchone()[0]
    by_league = {r["name"]: r["n"] for r in conn.execute("""
        SELECT l.name AS name, COUNT(*) AS n FROM matches m
        JOIN leagues l ON m.league_id = l.league_id
        WHERE m.status = 'NS' GROUP BY m.league_id""")}
    conn.close()
    return {"total_ns": total_ns, "today_ns": today_ns,
            "tomorrow_ns": tomorrow_ns, "by_league": by_league}


if __name__ == "__main__":
    info = generate_fixtures()
    print("生成完成:", info)
