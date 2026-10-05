# -*- coding: utf-8 -*-
"""修正 Transfermarkt 俱乐部映射错误(国家不符的重新匹配)

用法: python scripts/fix_tm_mapping.py [--apply]
"""
import argparse
import csv
import re
import sqlite3
import unicodedata
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"
EXT = BASE / "data" / "external"

LEAGUE_COUNTRY = {1: "England", 2: "Spain", 3: "Germany", 4: "Italy", 5: "France",
                  7: "England", 8: "Netherlands", 9: "Portugal", 10: "Brazil"}


def clean(n):
    return re.sub(r"\s*\(\d+\)\s*$", "", str(n or "")).strip()


def norm(n):
    s = unicodedata.normalize("NFKD", clean(n)).encode("ascii", "ignore").decode()
    return "".join(ch for ch in s.lower() if ch.isalnum())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()

    clubs = []
    with open(EXT / "team_details" / "team_details.csv", encoding="utf-8",
              errors="replace") as f:
        for r in csv.DictReader(f):
            clubs.append({"club_id": str(r["club_id"]), "name": clean(r["club_name"]),
                          "country": r.get("country_name") or "",
                          "logo": r.get("logo_url")})
    by_norm = defaultdict(list)
    for cl in clubs:
        by_norm[norm(cl["name"])].append(cl)
    print(f"TM 俱乐部 {len(clubs)} 个")

    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row
    rows = c.execute("""
        SELECT t.team_id, t.name, t.league_id, t.logo_url,
               mc.club_id, mc.tm_name, mc.tm_country
        FROM teams t LEFT JOIN tm_club_map mc ON mc.team_id = t.team_id""").fetchall()

    fixed = 0
    for r in rows:
        want = LEAGUE_COUNTRY.get(r["league_id"])
        cur_ctry = r["tm_country"] or ""
        need = (not r["club_id"]) or (want and cur_ctry and want.lower() not in cur_ctry.lower())
        if not need or not want:
            continue
        cands = [cl for cl in by_norm.get(norm(r["name"]), [])
                 if want.lower() in (cl["country"] or "").lower()]
        if not cands:
            # 退一步: 在国家范围内按"含关键词"匹配(关键词需 >=5 字符, 避免误配)
            key = norm(r["name"])
            cands = [cl for cl in clubs
                     if want.lower() in (cl["country"] or "").lower()
                     and len(key) >= 5
                     and (key in norm(cl["name"]) or norm(cl["name"]) in key)]
        if not cands:
            print(f"   ✗ {r['name']:<18} 现映射={r['tm_name']}({cur_ctry}) 找不到 {want} 同名俱乐部")
            continue
        cl = cands[0]
        print(f"   ✓ {r['name']:<18} {r['tm_name']}({cur_ctry}) -> {cl['name']}({cl['country']})")
        if args.apply:
            c.execute("INSERT OR REPLACE INTO tm_club_map VALUES (?,?,?,?,?,?,?)",
                      (r["team_id"], cl["club_id"], cl["name"], cl["country"],
                       None, cl["logo"], "rematch"))
        fixed += 1
    if args.apply:
        c.commit()
    print(f"\n{'已修正' if args.apply else '待修正'} {fixed} 条映射")
    c.close()


if __name__ == "__main__":
    main()
