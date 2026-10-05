# -*- coding: utf-8 -*-
"""球队去重合并

背景: 不同数据源的队名不同(如 EPL 的 Coventry vs 英冠的 Coventry City),
      可能被建成两支球队, 导致球员/比赛分散。

做法: 按"去俱乐部词 + 归一化"分组, 同组保留"比赛数+球员数最多"的为主体,
      把比赛/球员/积分榜引用迁移到主体, 再删除重复行。

用法:
    python scripts/dedupe_teams.py            # 预演(不改库)
    python scripts/dedupe_teams.py --apply    # 实际执行
"""
import argparse
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

DB = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                  "data", "database", "football.db")
REPORT = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "data", "dedupe_report.json")

CLUB_TOKENS = {"fc", "cf", "sc", "afc", "ac", "cd", "ud", "ss", "us", "as",
               "rc", "cn", "tsg", "club", "calcio", "deportivo", "sport", "kv",
               "sk", "bk", "ik", "ifk"}
# 这些是"区分性后缀": 不能当通用后缀剥掉(否则 Manchester City / United 会混淆)
SUFFIX_TOKENS = {"city", "town", "united", "utd", "rovers", "albion",
                 "wanderers", "athletic", "county"}


def tokenize(name: str):
    s = unicodedata.normalize("NFKD", name or "").encode("ascii", "ignore").decode()
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s.lower())
    words = [w for w in s.split() if w not in CLUB_TOKENS]
    core = "".join(w for w in words if w not in SUFFIX_TOKENS)
    suffix = frozenset(w for w in words if w in SUFFIX_TOKENS)
    return core, suffix


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="实际执行(默认仅预演)")
    args = ap.parse_args()

    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    teams = {r["team_id"]: dict(r) for r in
             conn.execute("SELECT team_id, name, league_id FROM teams")}
    stats = {}
    for tid in teams:
        m = conn.execute("SELECT COUNT(*) FROM matches WHERE home_team_id=? OR away_team_id=?",
                         (tid, tid)).fetchone()[0]
        p = conn.execute("SELECT COUNT(*) FROM players WHERE team_id=?", (tid,)).fetchone()[0]
        s = conn.execute("SELECT COUNT(*) FROM standings WHERE team_id=?", (tid,)).fetchone()[0]
        stats[tid] = (m, p, s)

    groups = defaultdict(list)
    suffixes = {}
    for tid, t in teams.items():
        core, sfx = tokenize(t["name"])
        groups[core].append(tid)
        suffixes[tid] = sfx

    # 别名合并: 重复名 -> 规范名 (仅当两者都存在时执行)
    MANUAL_MERGE = {
        "Wolverhampton": "Wolves", "Nottingham": "Nott'm Forest",
        "Brighton Hove": "Brighton", "Bayern": "Bayern Munich",
        "Hsv": "Hamburg", "Bremen": "Werder Bremen", "Frankfurt": "Ein Frankfurt",
        "Barca": "Barcelona", "Atleti": "Ath Madrid",
        "Ipswich Town": "Ipswich", "Coventry City": "Coventry",
    }
    by_name = {t["name"]: tid for tid, t in teams.items()}
    alias_merges = []
    for dup_name, canon_name in MANUAL_MERGE.items():
        if dup_name in by_name and canon_name in by_name and dup_name != canon_name:
            alias_merges.append({"key": "alias", "main": canon_name,
                                 "main_id": by_name[canon_name],
                                 "dups": [{"id": by_name[dup_name], "name": dup_name,
                                           "matches": stats[by_name[dup_name]][0],
                                           "players": stats[by_name[dup_name]][1]}]})

    merges = []
    for key, tids in groups.items():
        if len(tids) < 2 or not key:
            continue
        # 后缀相容性: 只在"一方无区分性后缀, 或后缀集合相同"时才允许合并
        buckets = []
        for tid in tids:
            placed = False
            for b in buckets:
                ref = suffixes[b[0]]
                if suffixes[tid] == ref or not suffixes[tid] or not ref:
                    b.append(tid)
                    placed = True
                    break
            if not placed:
                buckets.append([tid])
        for tids_b in buckets:
            if len(tids_b) < 2:
                continue
            tids_b.sort(key=lambda x: (-stats[x][1], -stats[x][0],
                                       teams[x]["league_id"] > 5, x))
            main_id, dups = tids_b[0], tids_b[1:]
            merges.append({"key": key, "main": teams[main_id]["name"], "main_id": main_id,
                           "dups": [{"id": d, "name": teams[d]["name"],
                                     "matches": stats[d][0],
                                     "players": stats[d][1]} for d in dups]})

    merges = merges + alias_merges
    print(f"发现可合并组: {len(merges)} 组 (含别名合并 {len(alias_merges)} 组), 涉及重复球队 "
          f"{sum(len(m['dups']) for m in merges)} 支")
    for m in merges[:25]:
        print(f"  {m['main']:<22} ← " + ", ".join(d["name"] for d in m["dups"]))
    if len(merges) > 25:
        print(f"  ... 其余 {len(merges)-25} 组")

    with open(REPORT, "w", encoding="utf-8") as f:
        json.dump(merges, f, ensure_ascii=False, indent=1)
    print(f"\n报告已写入: {REPORT}")

    if not args.apply:
        print("\n(预演模式, 未修改数据库; 加 --apply 执行合并)")
        conn.close()
        return

    moved_m = moved_p = moved_s = deleted = 0
    for m in merges:
        main_id = m["main_id"]
        for d in m["dups"]:
            did = d["id"]
            moved_m += conn.execute("UPDATE matches SET home_team_id=? WHERE home_team_id=?",
                                    (main_id, did)).rowcount
            moved_m += conn.execute("UPDATE matches SET away_team_id=? WHERE away_team_id=?",
                                    (main_id, did)).rowcount
            moved_p += conn.execute("UPDATE players SET team_id=? WHERE team_id=?",
                                    (main_id, did)).rowcount
            moved_s += conn.execute("UPDATE standings SET team_id=? WHERE team_id=?",
                                    (main_id, did)).rowcount
            conn.execute("DELETE FROM teams WHERE team_id=?", (did,))
            deleted += 1
    # 积分榜去重: 同联赛+赛季+球队 只保留一行
    conn.execute("""DELETE FROM standings WHERE id NOT IN (
        SELECT MAX(id) FROM standings GROUP BY league_id, season, team_id)""")
    conn.commit()
    print(f"\n合并完成: 迁移比赛 {moved_m} 条引用 | 球员 {moved_p} 名 | 积分榜 {moved_s} 行 | "
          f"删除重复球队 {deleted} 支")
    print("剩余球队:", conn.execute("SELECT COUNT(*) FROM teams").fetchone()[0])
    conn.close()


if __name__ == "__main__":
    main()
