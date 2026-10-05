# -*- coding: utf-8 -*-
"""API-Football 分阶段回填 —— 补齐 裁判/阵容/事件/球员体重·国籍/主教练/伤停

设计要点:
  - 分阶段(fixtures/players/coaches/injuries/lineups/events), 可单独跑
  - 配额感知: 达到每日预算自动停止并保存进度, 第二天接着跑(断点续传)
  - 精确匹配: 我们球员的 qxz_id 即 API-Football 球员 id -> 按 ID 补字段, 无需猜
  - 幂等: 所有写入用 INSERT OR REPLACE / COALESCE, 重复运行不产生脏数据

用法:
    python scripts/import_af_backfill.py --dry-run                 # 预估请求数
    python scripts/import_af_backfill.py --phase fixtures          # 先拉赛程+裁判
    python scripts/import_af_backfill.py --phase players           # 球员档案(体重/国籍/身高)
    python scripts/import_af_backfill.py --phase coaches           # 主教练
    python scripts/import_af_backfill.py --phase injuries          # 伤停
    python scripts/import_af_backfill.py --phase lineups --limit 500
    python scripts/import_af_backfill.py --phase events  --limit 500
    python scripts/import_af_backfill.py --phase all               # 按顺序一直跑到配额用完
"""
import argparse
import json
import re
import sqlite3
import sys
import unicodedata
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE))

from src.data_sources.api_football import (AF_LEAGUES, AF_SEASON_CODE,  # noqa: E402
                                           ApiFootballClient, QuotaExceeded)

DB = BASE / "data" / "database" / "football.db"
PROGRESS = BASE / "data" / "af_backfill_progress.json"


# ---------------------------------------------------------------- 工具
def norm(s):
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


ALIAS = {                     # API-Football 名 -> 我们库名
    "Manchester City": "Man City", "Manchester United": "Man United",
    "Wolverhampton Wanderers": "Wolves", "Nottingham Forest": "Nott'm Forest",
    "Brighton and Hove Albion": "Brighton", "Tottenham Hotspur": "Tottenham",
    "West Ham United": "West Ham", "Newcastle United": "Newcastle",
    "Sheffield United": "Sheffield Utd", "Sheffield Wednesday": "Sheffield Wed",
    "Leeds United": "Leeds", "Hull City": "Hull", "Queens Park Rangers": "Qpr",
    "West Bromwich Albion": "West Brom", "Ipswich Town": "Ipswich",
    "Coventry City": "Coventry", "Norwich City": "Norwich",
    "Borussia Monchengladbach": "M'gladbach", "Eintracht Frankfurt": "Ein Frankfurt",
    "Bayer Leverkusen": "Leverkusen", "VfB Stuttgart": "Stuttgart",
    "Borussia Dortmund": "Dortmund", "1899 Hoffenheim": "Hoffenheim",
    "1. FC Koln": "FC Koln", "Atletico Madrid": "Ath Madrid",
    "Athletic Club": "Ath Bilbao", "Real Betis": "Betis", "Real Sociedad": "Sociedad",
    "Celta Vigo": "Celta", "Deportivo La Coruna": "La Coruna",
    "RCD Espanyol": "Espanol", "Rayo Vallecano": "Vallecano",
    "Paris Saint Germain": "Paris SG", "Olympique Lyonnais": "Lyon",
    "Olympique Marseille": "Marseille", "Stade Rennais": "Rennes",
    "Lille OSC": "Lille", "AS Monaco": "Monaco", "AC Milan": "Milan",
    "AS Roma": "Roma", "SSC Napoli": "Napoli", "Hellas Verona": "Verona",
}


def load_progress() -> dict:
    try:
        return json.loads(PROGRESS.read_text(encoding="utf-8"))
    except Exception:
        return {}


def save_progress(p: dict):
    PROGRESS.parent.mkdir(parents=True, exist_ok=True)
    PROGRESS.write_text(json.dumps(p, ensure_ascii=False, indent=1), encoding="utf-8")


def db():
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    return c


def ensure_schema(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS af_fixtures (
        fixture_id INTEGER PRIMARY KEY, league_id INTEGER, season TEXT, date TEXT,
        home_af_id INTEGER, home_name TEXT, away_af_id INTEGER, away_name TEXT,
        home_goals INTEGER, away_goals INTEGER, status TEXT, referee TEXT,
        venue TEXT, city TEXT);
    CREATE TABLE IF NOT EXISTS af_team_map (
        team_id INTEGER PRIMARY KEY, af_team_id INTEGER, af_name TEXT);
    CREATE TABLE IF NOT EXISTS af_players (
        af_player_id INTEGER PRIMARY KEY, name TEXT, age INTEGER, nationality TEXT,
        height TEXT, weight TEXT, position TEXT, photo TEXT, team_id INTEGER,
        af_team_id INTEGER, season TEXT);
    CREATE TABLE IF NOT EXISTS af_coaches (
        af_coach_id INTEGER, name TEXT, nationality TEXT, team_id INTEGER,
        af_team_id INTEGER, start_date TEXT, end_date TEXT, is_current INTEGER);
    CREATE TABLE IF NOT EXISTS af_injuries (
        af_player_id INTEGER, player_name TEXT, af_team_id INTEGER, team_name TEXT,
        fixture_id INTEGER, injury_type TEXT, reason TEXT, date TEXT);
    CREATE TABLE IF NOT EXISTS af_lineups (
        fixture_id INTEGER, af_team_id INTEGER, team_name TEXT, formation TEXT,
        coach_id INTEGER, coach_name TEXT, player_id INTEGER, player_name TEXT,
        number INTEGER, pos TEXT, grid TEXT);
    CREATE TABLE IF NOT EXISTS af_events (
        fixture_id INTEGER, minute INTEGER, extra INTEGER, af_team_id INTEGER,
        team_name TEXT, player_id INTEGER, player_name TEXT, assist_id INTEGER,
        assist_name TEXT, type TEXT, detail TEXT, comments TEXT);
    CREATE INDEX IF NOT EXISTS idx_af_fx_date ON af_fixtures(date);
    CREATE INDEX IF NOT EXISTS idx_af_ev_fx ON af_events(fixture_id);
    CREATE INDEX IF NOT EXISTS idx_af_lu_fx ON af_lineups(fixture_id);
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(matches)")}
    for col, typ in (("referee", "TEXT"), ("venue", "TEXT"), ("af_fixture_id", "INTEGER")):
        if col not in cols:
            c.execute(f"ALTER TABLE matches ADD COLUMN {col} {typ}")
    pcols = {r[1] for r in c.execute("PRAGMA table_info(players)")}
    if "af_player_id" not in pcols:
        c.execute("ALTER TABLE players ADD COLUMN af_player_id INTEGER")
    c.commit()


def our_teams(c):
    """我们的球队 + 联赛"""
    return {r["name"]: (r["team_id"], r["league_id"])
            for r in c.execute("SELECT team_id, name, league_id FROM teams")}


def team_id_for(name, teams_norm, league_id=None):
    """我们的队名匹配(精确 -> 别名 -> 包含)"""
    n = norm(name)
    if n in teams_norm:
        return teams_norm[n]
    if name in ALIAS:
        a = norm(ALIAS[name])
        if a in teams_norm:
            return teams_norm[a]
    for k, tid in teams_norm.items():
        if n and (n in k or k in n) and abs(len(k) - len(n)) <= 8:
            return tid
    return None


# ---------------------------------------------------------------- 阶段实现
def phase_fixtures(cli, c, seasons, leagues, prog, limit=None, dry=False):
    """赛程 + 裁判 + 场地; 同时建立球队 ID 映射"""
    teams = our_teams(c)
    teams_norm = {norm(n): tid for n, (tid, _) in teams.items()}
    done = set(prog.setdefault("fixtures", []))
    tasks = [(lg, s) for lg in leagues for s in seasons]
    todo = [t for t in tasks if f"{t[0]}_{t[1]}" not in done]
    print(f"  fixtures: {len(todo)}/{len(tasks)} 个(联赛,赛季)待处理")
    if dry:
        print(f"  → 预计请求 {len(todo)} 次")
        return
    for lg, season in todo[:limit] if limit else todo:
        lid = AF_LEAGUES[lg]
        code = AF_SEASON_CODE.get(season, str(season))
        try:
            fixtures = cli.fixtures(lid, season)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        n_match = n_ref = 0
        for f in fixtures:
            fx, teams_d, goals, lg_d = (f.get("fixture", {}), f.get("teams", {}),
                                        f.get("goals", {}), f.get("league", {}))
            hid, aid = teams_d.get("home", {}), teams_d.get("away", {})
            c.execute("""INSERT OR REPLACE INTO af_fixtures VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (fx.get("id"), lid, code, str(fx.get("date", ""))[:10],
                       hid.get("id"), hid.get("name"), aid.get("id"), aid.get("name"),
                       goals.get("home"), goals.get("away"), fx.get("status", {}).get("short"),
                       fx.get("referee"), fx.get("venue", {}).get("name"),
                       fx.get("venue", {}).get("city")))
            for side in (hid, aid):
                tid = team_id_for(side.get("name", ""), teams_norm)
                if tid:
                    c.execute("INSERT OR REPLACE INTO af_team_map VALUES (?,?,?)",
                              (tid, side.get("id"), side.get("name")))
            # 回填我们比赛: 日期±1 + 队名匹配
            tidh = team_id_for(hid.get("name", ""), teams_norm)
            tida = team_id_for(aid.get("name", ""), teams_norm)
            if tidh and tida:
                d0 = str(fx.get("date", ""))[:10]
                mid = None
                for delta in (0, 1, -1):
                    dd = (datetime.fromisoformat(d0) + timedelta(days=delta)).date().isoformat()
                    mid = c.execute("""SELECT match_id FROM matches
                        WHERE home_team_id=? AND away_team_id=? AND date(?) = date(date)""",
                        (tidh, tida, dd)).fetchone()
                    if mid:
                        mid = mid["match_id"]
                        break
                if mid:
                    c.execute("""UPDATE matches SET af_fixture_id=?,
                            referee=COALESCE(NULLIF(referee,''), ?),
                            venue=COALESCE(NULLIF(venue,''), ?) WHERE match_id=?""",
                              (fx.get("id"), fx.get("referee"),
                               fx.get("venue", {}).get("name"), mid))
                    n_match += 1
                    if fx.get("referee"):
                        n_ref += 1
        c.commit()
        prog["fixtures"].append(f"{lg}_{season}")
        save_progress(prog)
        print(f"  ✓ {lg} {code}: 赛程 {len(fixtures)} 场 | 回填比赛 {n_match} | 有裁判 {n_ref}")


def phase_players(cli, c, seasons, leagues, prog, limit=None, dry=False):
    """球员档案: 体重/国籍/身高/照片 (按球队+赛季)"""
    amap = {r["team_id"]: (r["af_team_id"], r["af_name"])
            for r in c.execute("SELECT * FROM af_team_map")}
    done = set(prog.setdefault("players", []))
    tasks = [(tid, af, name, s) for tid, (af, name) in amap.items() for s in seasons]
    todo = [t for t in tasks if f"{t[0]}_{t[3]}" not in done]
    print(f"  players: {len(todo)}/{len(tasks)} 个(球队,赛季)待处理")
    if dry:
        print(f"  → 预计请求 {len(todo)} 次")
        return
    for tid, af, name, season in todo[:limit] if limit else todo:
        try:
            data = cli.players(af, season)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        code = AF_SEASON_CODE.get(season, str(season))
        n = 0
        for item in data:
            p = item.get("player", {})
            pid = p.get("id")
            if not pid:
                continue
            c.execute("""INSERT OR REPLACE INTO af_players VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                      (pid, p.get("name"), p.get("age"), p.get("nationality"),
                       str(p.get("height") or ""), str(p.get("weight") or ""),
                       p.get("position"), p.get("photo"), tid, af, code))
            # 按 ID 精确增强我们的球员(qxz_id 即 API-Football id)
            c.execute("""UPDATE players SET
                    weight       = COALESCE(weight, NULLIF(?, 'None')),
                    height       = COALESCE(height, NULLIF(?, 'None')),
                    nationality  = COALESCE(NULLIF(nationality,''), ?),
                    photo_url    = COALESCE(NULLIF(photo_url,''), ?),
                    af_player_id = COALESCE(af_player_id, ?)
                WHERE json_extract(stats_json, '$.qxz_id') = ?""",
                      (str(p.get("weight") or ""), str(p.get("height") or ""),
                       p.get("nationality"), p.get("photo"), pid, str(pid)))
            n += 1
        c.commit()
        prog["players"].append(f"{tid}_{season}")
        save_progress(prog)
        print(f"  ✓ {name:<18} {code}: {n} 名球员档案")


def phase_coaches(cli, c, seasons, leagues, prog, limit=None, dry=False):
    """主教练: 每队 1 次请求"""
    amap = {r["team_id"]: (r["af_team_id"], r["af_name"])
            for r in c.execute("SELECT * FROM af_team_map")}
    done = set(prog.setdefault("coaches", []))
    todo = [(tid, af, nm) for tid, (af, nm) in amap.items() if str(tid) not in done]
    print(f"  coaches: {len(todo)}/{len(amap)} 支球队待处理")
    if dry:
        print(f"  → 预计请求 {len(todo)} 次")
        return
    for tid, af, name in todo[:limit] if limit else todo:
        try:
            data = cli.coachs(af)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        cur, cur_start = None, ""
        for co in data:
            cid = co.get("id")
            for car in (co.get("career") or []):
                if car.get("team", {}).get("id") == af:
                    c.execute("""INSERT OR REPLACE INTO af_coaches VALUES (?,?,?,?,?,?,?,?)""",
                              (cid, co.get("name"), co.get("nationality"), tid, af,
                               car.get("start"), car.get("end"),
                               1 if not car.get("end") else 0))
                    if not car.get("end") and (car.get("start") or "") >= cur_start:
                        cur, cur_start = co.get("name"), car.get("start") or ""
        if cur:
            c.execute("UPDATE teams SET manager=COALESCE(NULLIF(manager,''), ?) "
                      "WHERE team_id=?", (cur, tid))
        c.commit()
        prog["coaches"].append(str(tid))
        save_progress(prog)
        print(f"  ✓ {name:<18} 主教练: {cur or '未获取'}")


def phase_injuries(cli, c, seasons, leagues, prog, limit=None, dry=False):
    """伤停: 按联赛+赛季, 1 次请求拿全季"""
    done = set(prog.setdefault("injuries", []))
    tasks = [(lg, s) for lg in leagues for s in seasons]
    todo = [t for t in tasks if f"{t[0]}_{t[1]}" not in done]
    print(f"  injuries: {len(todo)}/{len(tasks)} 个(联赛,赛季)待处理")
    if dry:
        print(f"  → 预计请求 {len(todo)} 次")
        return
    for lg, season in todo[:limit] if limit else todo:
        try:
            data = cli.injuries(AF_LEAGUES[lg], season)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        for it in data:
            p, t, fx = it.get("player", {}), it.get("team", {}), it.get("fixture", {})
            c.execute("""INSERT INTO af_injuries VALUES (?,?,?,?,?,?,?,?)""",
                      (p.get("id"), p.get("name"), t.get("id"), t.get("name"),
                       fx.get("id"), it.get("type"), it.get("reason"), it.get("date")))
        c.commit()
        prog["injuries"].append(f"{lg}_{season}")
        save_progress(prog)
        print(f"  ✓ {lg} {season}: {len(data)} 条伤停")


def _fixture_targets(c, phase, limit):
    """需要拉阵容/事件的比赛(优先已完赛、最近的)"""
    done = set()
    if phase == "lineups":
        done = {r[0] for r in c.execute("SELECT DISTINCT fixture_id FROM af_lineups")}
    else:
        done = {r[0] for r in c.execute("SELECT DISTINCT fixture_id FROM af_events")}
    rows = c.execute("""SELECT af_fixture_id, date, home_team_id, away_team_id
                        FROM matches WHERE af_fixture_id IS NOT NULL
                          AND status='FT' ORDER BY date DESC""").fetchall()
    out = [r["af_fixture_id"] for r in rows if r["af_fixture_id"] not in done]
    return out[:limit] if limit else out


def phase_lineups(cli, c, seasons, leagues, prog, limit=None, dry=False):
    targets = _fixture_targets(c, "lineups", limit)
    total = c.execute("SELECT COUNT(*) FROM matches WHERE af_fixture_id IS NOT NULL "
                      "AND status='FT'").fetchone()[0]
    print(f"  lineups: 待拉 {len(targets)} 场(共 {total} 场已映射)")
    if dry:
        print(f"  → 预计请求 {len(targets)} 次")
        return
    for fid in targets:
        try:
            data = cli.fixture_lineups(fid)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        for side in data:
            t = side.get("team", {})
            co = side.get("coach", {})
            for p in side.get("startXI", []) + side.get("substitutes", []):
                pl = p.get("player", {})
                c.execute("""INSERT INTO af_lineups VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
                          (fid, t.get("id"), t.get("name"), side.get("formation"),
                           co.get("id"), co.get("name"), pl.get("id"), pl.get("name"),
                           pl.get("number"), pl.get("pos"), pl.get("grid")))
        c.commit()
        prog.setdefault("lineups", []).append(fid)
        if len(prog["lineups"]) % 25 == 0:
            save_progress(prog)
            print(f"    阵容进度 {len(prog['lineups'])} 场 (今日已用 {cli.used})")
    save_progress(prog)
    print(f"  ✓ 阵容完成, 累计 {len(prog.get('lineups', []))} 场")


def phase_events(cli, c, seasons, leagues, prog, limit=None, dry=False):
    targets = _fixture_targets(c, "events", limit)
    print(f"  events: 待拉 {len(targets)} 场")
    if dry:
        print(f"  → 预计请求 {len(targets)} 次")
        return
    for fid in targets:
        try:
            data = cli.fixture_events(fid)
        except QuotaExceeded as e:
            print(f"  ⛔ {e}")
            return
        for e in data:
            t, p, a = e.get("team", {}), e.get("player", {}), e.get("assist", {})
            tm = e.get("time", {})
            c.execute("""INSERT INTO af_events VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
                      (fid, tm.get("elapsed"), tm.get("extra"), t.get("id"), t.get("name"),
                       p.get("id"), p.get("name"), a.get("id"), a.get("name"),
                       e.get("type"), e.get("detail"), e.get("comments")))
        c.commit()
        prog.setdefault("events", []).append(fid)
        if len(prog["events"]) % 25 == 0:
            save_progress(prog)
            print(f"    事件进度 {len(prog['events'])} 场 (今日已用 {cli.used})")
    save_progress(prog)
    print(f"  ✓ 事件完成, 累计 {len(prog.get('events', []))} 场")


PHASES = {"fixtures": phase_fixtures, "players": phase_players,
          "coaches": phase_coaches, "injuries": phase_injuries,
          "lineups": phase_lineups, "events": phase_events}
ORDER = ["fixtures", "players", "coaches", "injuries", "lineups", "events"]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", default="all", choices=["all"] + ORDER)
    ap.add_argument("--seasons", default="2021,2022,2023,2024,2025")
    ap.add_argument("--leagues", default=",".join(AF_LEAGUES))
    ap.add_argument("--limit", type=int, default=None, help="本次最多处理多少任务")
    ap.add_argument("--budget", type=int, default=None, help="今日请求预算")
    ap.add_argument("--min-interval", type=float, default=None)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    seasons = [int(s) for s in args.seasons.split(",") if s.strip()]
    leagues = [l for l in args.leagues.split(",") if l]
    c = db()
    ensure_schema(c)
    prog = load_progress()

    if args.dry_run:
        print("=" * 70)
        print("预估模式(不消耗请求) —— 需要先跑 --phase fixtures 建立球队映射")
        print("=" * 70)
    try:
        cli = ApiFootballClient(min_interval=args.min_interval, daily_budget=args.budget,
                                verbose=False)
    except ValueError as e:
        print(f"❌ {e}\n   → https://dashboard.api-football.com 免费注册后用 .env 配置 "
              f"API_SPORTS_KEY")
        return 1

    print(f"模式={cli.mode} | 今日已用 {cli.used}/{cli.daily_budget} | "
          f"间隔 {cli.min_interval}s\n")
    phases = ORDER if args.phase == "all" else [args.phase]
    try:
        for ph in phases:
            print(f"【{ph}】")
            PHASES[ph](cli, c, seasons, leagues, prog, args.limit, args.dry_run)
            if args.limit:
                break
    except QuotaExceeded as e:
        print(f"\n⛔ {e}\n   进度已保存, 明天继续运行同一命令即可。")
    except RuntimeError as e:
        msg = str(e)
        if any(k in msg for k in ("403", "not subscribed", "token", "key")):
            print(f"\n❌ 认证失败: {msg}")
            print("   → 请在 .env 配置有效的 key:")
            print("     官方直连(推荐): API_SPORTS_KEY=...   (dashboard.api-football.com)")
            print("     或 RapidAPI:    API_FOOTBALL_KEY=...")
        else:
            print(f"\n⚠️  {msg}")
    finally:
        c.close()

    print("\n" + "=" * 70)
    print("累计完成:")
    for k in ORDER:
        print(f"   {k:<10} {len(prog.get(k, [])):,}")
    print(f"\n今日请求累计: {cli.used}/{cli.daily_budget} (剩余 {cli.remaining()})")
    if cli.mode == "rapidapi":
        print("提示: 当前走 RapidAPI 模式; 若使用官方直连, 请在 .env 配置 API_SPORTS_KEY")
    return 0


if __name__ == "__main__":
    sys.exit(main())
