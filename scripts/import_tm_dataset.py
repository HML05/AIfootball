# -*- coding: utf-8 -*-
"""导入 Transfermarkt 开源数据集(按已匹配俱乐部过滤, 补齐球员档案/市值/转会/伤病/赛季数据)

前置: 先运行 scripts/crosswalk_clubs.py 生成 tm_club_map

用法:
    python scripts/import_tm_dataset.py            # 全部分步执行
    python scripts/import_tm_dataset.py --step 2   # 只跑某步
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.parent
EXT = BASE / "data" / "external"
DB = BASE / "data" / "database" / "football.db"
sys.path.insert(0, str(BASE))


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def clean_player_name(n) -> str:
    """去掉 TM 球员名尾部的 '(123456)' id"""
    return re.sub(r"\s*\(\d+\)\s*$", "", str(n or "")).strip()


def conn():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    return c


def ensure_tables(c):
    c.executescript("""
    CREATE TABLE IF NOT EXISTS tm_team_seasons (
        club_id TEXT, team_name TEXT, season_id TEXT, competition_name TEXT,
        competition_id TEXT, division TEXT);
    CREATE TABLE IF NOT EXISTS tm_players (
        player_id TEXT PRIMARY KEY, player_name TEXT, image_url TEXT,
        date_of_birth TEXT, citizenship TEXT, height REAL, position TEXT,
        main_position TEXT, foot TEXT, club_id TEXT, club_name TEXT);
    CREATE TABLE IF NOT EXISTS tm_player_seasons (
        player_id TEXT, season_name TEXT, competition_name TEXT, team_id TEXT,
        team_name TEXT, appearances INTEGER, goals INTEGER, assists INTEGER,
        yellow_cards INTEGER, red_cards INTEGER);
    CREATE TABLE IF NOT EXISTS tm_player_market_value (
        player_id TEXT, date_unix INTEGER, value REAL);
    CREATE TABLE IF NOT EXISTS tm_transfers (
        player_id TEXT, player_name TEXT, season_name TEXT, transfer_date TEXT,
        from_team_id TEXT, from_team_name TEXT, to_team_id TEXT, to_team_name TEXT,
        transfer_type TEXT, transfer_fee TEXT, value_at_transfer TEXT);
    CREATE TABLE IF NOT EXISTS tm_player_injuries (
        player_id TEXT, season_name TEXT, injury_reason TEXT, from_date TEXT,
        end_date TEXT, days_missed TEXT, games_missed TEXT);
    CREATE INDEX IF NOT EXISTS idx_tmps_pid ON tm_player_seasons(player_id);
    CREATE INDEX IF NOT EXISTS idx_tmmv_pid ON tm_player_market_value(player_id);
    CREATE INDEX IF NOT EXISTS idx_tmtr_from ON tm_transfers(from_team_id);
    CREATE INDEX IF NOT EXISTS idx_tmtr_to ON tm_transfers(to_team_id);
    CREATE INDEX IF NOT EXISTS idx_tminj_pid ON tm_player_injuries(player_id);
    """)
    cols = {r[1] for r in c.execute("PRAGMA table_info(players)")}
    for col, typ in (("tm_player_id", "TEXT"), ("foot", "TEXT"), ("tm_club_id", "TEXT")):
        if col not in cols:
            c.execute(f"ALTER TABLE players ADD COLUMN {col} {typ}")
    c.commit()


def club_maps(c):
    id2club = {r["team_id"]: str(r["club_id"]) for r in
               c.execute("SELECT team_id, club_id FROM tm_club_map")}
    club2ids = {}
    for tid, cid in id2club.items():
        club2ids.setdefault(cid, []).append(tid)
    return id2club, club2ids


def step1(c, club2ids):
    print("=" * 62)
    print("【步骤1】球队历史赛季(team_competitions_seasons)")
    print("=" * 62)
    df = pd.read_csv(EXT / "team_competitions_seasons" / "team_competitions_seasons.csv",
                     dtype=str, encoding="utf-8", on_bad_lines="skip")
    df = df[df["club_id"].isin(club2ids)]
    df = df.rename(columns={"season_id": "season_id", "club_division": "division"})
    df[["club_id", "team_name", "season_id", "competition_name", "competition_id",
        "division"]].to_sql("tm_team_seasons", c, if_exists="replace", index=False)
    print(f"  写入 tm_team_seasons: {len(df):,} 行 (涉及 {df['club_id'].nunique()} 家俱乐部)")

    # 顺带: 用 TM 队徽补我们缺的 29 个
    c.execute("""UPDATE teams SET logo_url = (
                    SELECT t.logo FROM team_details_tmp t WHERE t.cid = (
                        SELECT club_id FROM tm_club_map m WHERE m.team_id = teams.team_id))
                 WHERE (logo_url IS NULL OR logo_url = '')""") if False else None
    print("  (队徽补充见步骤4)")


def step2(c, club2ids):
    print("=" * 62)
    print("【步骤2】球员档案 + 赛季数据")
    print("=" * 62)
    perf = pd.read_csv(EXT / "player_performances" / "player_performances.csv",
                       dtype=str, encoding="utf-8", on_bad_lines="skip",
                       usecols=["player_id", "season_name", "competition_name", "team_id",
                                "team_name", "nb_on_pitch", "goals", "assists",
                                "yellow_cards", "direct_red_cards", "minutes_played"])
    print(f"  读取表现记录 {len(perf):,} 行")
    perf = perf[perf["team_id"].isin(club2ids)]
    print(f"  过滤到我们俱乐部: {len(perf):,} 行 ({perf['player_id'].nunique():,} 名球员)")
    for col in ("nb_on_pitch", "goals", "assists", "yellow_cards",
                "direct_red_cards", "minutes_played"):
        perf[col] = pd.to_numeric(perf[col], errors="coerce").fillna(0).astype(int)
    perf = perf.rename(columns={"nb_on_pitch": "appearances",
                                "direct_red_cards": "red_cards",
                                "minutes_played": "minutes"})
    perf.to_sql("tm_player_seasons", c, if_exists="replace", index=False)

    pids = set(perf["player_id"])
    prof = pd.read_csv(EXT / "player_profiles" / "player_profiles.csv",
                       dtype=str, encoding="utf-8", on_bad_lines="skip")
    print(f"  档案总数 {len(prof):,} | 字段: {list(prof.columns)[:12]}")
    prof = prof[prof["player_id"].isin(pids)]
    for col in ("height", "player_name", "player_image_url", "date_of_birth",
                "citizenship", "position", "main_position", "foot"):
        if col not in prof.columns:
            prof[col] = None
    prof = prof.rename(columns={"player_image_url": "image_url",
                                "player_name": "player_name"})
    prof["player_name"] = prof["player_name"].map(clean_player_name)
    prof["height"] = pd.to_numeric(prof["height"], errors="coerce")
    out = prof[["player_id", "player_name", "image_url", "date_of_birth", "citizenship",
                "height", "position", "main_position", "foot"]].copy()
    out.to_sql("tm_players", c, if_exists="replace", index=False)
    print(f"  写入 tm_players: {len(out):,} 名球员档案")
    return perf, out


def step2b_enrich(c, club2ids, prof):
    """把 TM 档案匹配到我们现有球员(俱乐部 + 姓名归一化; 取该俱乐部最近赛季阵容)"""
    print("\n  --- 增强现有球员(国籍/身高/惯用脚/市值) ---")
    our = c.execute("""SELECT p.player_id, p.team_id, p.name, t.name AS team
                       FROM players p JOIN teams t ON t.team_id=p.team_id""").fetchall()

    # 一次读入, 用 pandas 取"每个俱乐部最近赛季"的阵容(避免相关子查询卡死)
    ps = pd.read_sql_query(
        "SELECT team_id, season_name, player_id FROM tm_player_seasons", c)
    latest = ps.groupby("team_id")["season_name"].max().to_dict()
    ps["_is_latest"] = ps.apply(
        lambda r: r["season_name"] == latest.get(r["team_id"]), axis=1)
    squad_rows = ps[ps["_is_latest"]]
    squad = {}
    for tid, pid in zip(squad_rows["team_id"], squad_rows["player_id"]):
        squad.setdefault(str(tid), set()).add(pid)

    prof_by_id = {row["player_id"]: row for _, row in prof.iterrows()}
    tm_by_club = {}
    for cid, pids in squad.items():
        d = {}
        for pid in pids:
            p = prof_by_id.get(pid)
            if p is not None:
                d[norm(p["player_name"])] = p
        tm_by_club[cid] = d
    print(f"  覆盖俱乐部: {len(tm_by_club)} | 各队最近赛季阵容人数示例: "
          f"{[len(v) for v in list(tm_by_club.values())[:6]]}")

    mkt = {}
    for r in pd.read_csv(EXT / "player_latest_market_value" / "player_latest_market_value.csv",
                         dtype=str, encoding="utf-8", on_bad_lines="skip").itertuples():
        mkt[r.player_id] = r.value

    updated = 0
    matched_names = []
    for r in our:
        row = c.execute("SELECT club_id FROM tm_club_map WHERE team_id=?",
                        (r["team_id"],)).fetchone()
        if not row:
            continue
        p = tm_by_club.get(str(row["club_id"]), {}).get(norm(r["name"]))
        if p is None:
            continue
        c.execute("""UPDATE players SET
                nationality = COALESCE(NULLIF(nationality,''), ?),
                height = COALESCE(height, ?),
                foot = COALESCE(NULLIF(foot,''), ?),
                market_value = COALESCE(market_value, ?),
                tm_player_id = ? WHERE player_id = ?""",
                  (p.get("citizenship"), p.get("height"), p.get("foot"),
                   mkt.get(p["player_id"]), p["player_id"], r["player_id"]))
        updated += 1
        if len(matched_names) < 8:
            matched_names.append((r["name"], p["player_name"], r["team"]))
    c.commit()
    print(f"  按姓名匹配并增强: {updated} / {len(our)} 名球员 ({updated/len(our):.0%})")
    for m in matched_names:
        print(f"     {m[0]} → {m[1]} ({m[2]})")


def step3(c, club2ids):
    print("=" * 62)
    print("【步骤3】市值历史 / 转会史 / 伤病史")
    print("=" * 62)
    pids = {r[0] for r in c.execute("SELECT player_id FROM tm_players")}
    print(f"  目标球员: {len(pids):,}")

    mv = pd.read_csv(EXT / "player_market_value" / "player_market_value.csv",
                     dtype=str, encoding="utf-8", on_bad_lines="skip")
    mv = mv[mv["player_id"].isin(pids)]
    mv["date_unix"] = pd.to_numeric(mv["date_unix"], errors="coerce")
    mv["value"] = pd.to_numeric(mv["value"], errors="coerce")
    mv.to_sql("tm_player_market_value", c, if_exists="replace", index=False)
    print(f"  tm_player_market_value: {len(mv):,} 行")

    tr = pd.read_csv(EXT / "transfer_history" / "transfer_history.csv",
                     dtype=str, encoding="utf-8", on_bad_lines="skip")
    tr = tr[tr["from_team_id"].isin(club2ids) | tr["to_team_id"].isin(club2ids)]
    tr.to_sql("tm_transfers", c, if_exists="replace", index=False)
    print(f"  tm_transfers: {len(tr):,} 行")

    inj = pd.read_csv(EXT / "player_injuries" / "player_injuries.csv",
                      dtype=str, encoding="utf-8", on_bad_lines="skip")
    inj = inj[inj["player_id"].isin(pids)]
    inj.to_sql("tm_player_injuries", c, if_exists="replace", index=False)
    print(f"  tm_player_injuries: {len(inj):,} 行")


def step4_logos(c):
    print("=" * 62)
    print("【步骤4】用 TM 队徽补我们缺失的球队队徽")
    print("=" * 62)
    det = pd.read_csv(EXT / "team_details" / "team_details.csv",
                      dtype=str, encoding="utf-8", on_bad_lines="skip")
    det["club_id"] = det["club_id"].astype(str)
    logo = dict(zip(det["club_id"], det["logo_url"]))
    n = 0
    for r in c.execute("SELECT team_id, club_id FROM tm_club_map"):
        url = logo.get(str(r["club_id"]))
        if not url:
            continue
        cur = c.execute("UPDATE teams SET logo_url=? WHERE team_id=? "
                        "AND (logo_url IS NULL OR logo_url='')", (url, r["team_id"]))
        n += cur.rowcount
    c.commit()
    print(f"  补充队徽: {n} 支")


def step5_enrich_only(c):
    """仅执行"增强现有球员"(从已导入的 tm_players 表读取, 不重读大 CSV)"""
    print("=" * 62)
    print("【步骤5】增强现有球员(国籍/身高/惯用脚/市值)")
    print("=" * 62)
    prof = pd.read_sql_query(
        "SELECT player_id, player_name, citizenship, height, foot FROM tm_players", c)
    print(f"  TM 档案: {len(prof):,} 名")
    step2b_enrich(c, None, prof)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--step", type=int, default=None)
    args = ap.parse_args()

    c = conn()
    ensure_tables(c)
    id2club, club2ids = club_maps(c)
    print(f"已匹配俱乐部: {len(club2ids)} 个 (对应我们 {len(id2club)} 支球队)\n")

    if args.step == 5:
        step5_enrich_only(c)
    else:
        if args.step in (None, 1):
            step1(c, club2ids)
        if args.step in (None, 2):
            _, prof = step2(c, club2ids)
            step2b_enrich(c, club2ids, prof)
        if args.step in (None, 3):
            step3(c, club2ids)
        if args.step in (None, 4):
            step4_logos(c)

    print("\n" + "=" * 62)
    print("导入完成, 库内新增表统计:")
    for t in ("tm_team_seasons", "tm_players", "tm_player_seasons",
              "tm_player_market_value", "tm_transfers", "tm_player_injuries"):
        n = c.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  {t:<26} {n:>9,} 行")
    pl = c.execute("SELECT COUNT(*) FROM players WHERE nationality IS NOT NULL "
                   "AND nationality != ''").fetchone()[0]
    print(f"  我们球员中有国籍: {pl}")
    c.close()


if __name__ == "__main__":
    main()
