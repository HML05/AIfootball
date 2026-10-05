# -*- coding: utf-8 -*-
"""球队 ID 映射: 本库 teams <-> Transfermarkt club_id

输入: data/external/team_details/team_details.csv (2,175 俱乐部)
      data/external/team_competitions_seasons/team_competitions_seasons.csv (196,378 行)
输出: data/tm_club_map.json + DB 表 tm_club_map

用法: python scripts/crosswalk_clubs.py
"""
import csv
import json
import os
import re
import sqlite3
import sys
import unicodedata
from collections import defaultdict
from pathlib import Path

BASE = Path(__file__).parent.parent
EXT = BASE / "data" / "external"
DB = BASE / "data" / "database" / "football.db"

CLUB_TOKENS = {"fc", "cf", "sc", "afc", "ac", "cd", "ud", "ss", "us", "as", "rc",
               "cn", "tsg", "club", "calcio", "deportivo", "sport", "kv", "sk",
               "bk", "ik", "ifk", "sv", "vfb", "vfl", "sd", "cp"}
SUFFIX_TOKENS = {"city", "town", "united", "utd", "rovers", "albion", "wanderers",
                 "athletic", "county"}
LEAGUE_COUNTRY = {1: "England", 2: "Spain", 3: "Germany", 4: "Italy", 5: "France"}

# 人工别名: 本库简称 -> Transfermarkt 常用名(用于 exact/fuzzy 匹配)
TM_MANUAL_ALIAS = {
    "Man City": "Manchester City", "Man United": "Manchester United",
    "Nott'm Forest": "Nottingham Forest", "Wolves": "Wolverhampton Wanderers",
    "Brighton": "Brighton & Hove Albion", "Tottenham": "Tottenham Hotspur",
    "West Ham": "West Ham United", "Newcastle": "Newcastle United",
    "Leeds": "Leeds United", "Hull": "Hull City", "Qpr": "Queens Park Rangers",
    "West Brom": "West Bromwich Albion", "Sheffield Utd": "Sheffield United",
    "Sheffield Wed": "Sheffield Wednesday", "Ipswich": "Ipswich Town",
    "Coventry": "Coventry City", "Norwich": "Norwich City",
    "Ath Bilbao": "Athletic Club", "Ath Madrid": "Atletico de Madrid",
    "Betis": "Real Betis", "Espanol": "RCD Espanyol Barcelona",
    "Espanyol": "RCD Espanyol Barcelona", "Sociedad": "Real Sociedad",
    "Vallecano": "Rayo Vallecano", "Celta": "RC Celta de Vigo",
    "La Coruna": "Deportivo de La Coruna", "Santander": "Racing Santander",
    "Bielefeld": "Arminia Bielefeld", "Ein Frankfurt": "Eintracht Frankfurt",
    "Hamburg": "Hamburger SV", "Hertha": "Hertha BSC",
    "M'gladbach": "Borussia Monchengladbach", "Union Berlin": "1.FC Union Berlin",
    "FC Koln": "1. FC Koln", "1. Koln": "1. FC Koln", "Bayern Munich": "Bayern Munich",
    "Bordeaux": "FC Girondins Bordeaux", "Brest": "Stade Brestois 29",
    "Rennes": "Stade Rennais FC", "Psg": "Paris Saint-Germain",
    "Psv": "PSV Eindhoven", "Nec": "NEC Nijmegen", "Willem Ii": "Willem II Tilburg",
    "Avs": "AVS Futebol SAD", "Acad. Viseu": "Academico Viseu FC",
    "Bahia": "Esporte Clube Bahia", "Coritiba": "Coritiba Foot Ball Club",
    "Qarabag Agdam": "Qarabag Agdam", "Slavia Praha": "SK Slavia Prague",
    "Bod/Glimt": "FK Bodo/Glimt", "Olympiakos": "Olympiacos Piraeus",
    "Paphos": "Pafos FC", "Kbenhavn": "FC Copenhagen",
    "Fk Kairat": "FC Kairat Almaty", "Pae Aek": "AEK Athens",
    "Sl. Bratislava": "SK Slovan Bratislava", "Shaktar": "Shakhtar Donetsk",
    "Sabah Fk": "Sabah FK", "Elversberg": "SV Elversberg",
    "Paderborn": "SC Paderborn 07", "Schalke 04": "FC Schalke 04",
    "Greuther Furth": "SpVgg Greuther Furth", "Heidenheim": "1.FC Heidenheim 1846",
    "Darmstadt": "SV Darmstadt 98", "Hoffenheim": "TSG 1899 Hoffenheim",
    "Dortmund": "Borussia Dortmund", "RB Leipzig": "RB Leipzig",
    "Leverkusen": "Bayer 04 Leverkusen", "Stuttgart": "VfB Stuttgart",
    "Mainz": "1.FSV Mainz 05", "Augsburg": "FC Augsburg",
    "Werder Bremen": "SV Werder Bremen", "Freiburg": "SC Freiburg",
    "Wolfsburg": "VfL Wolfsburg", "Monchengladbach": "Borussia Monchengladbach",
    "Real Betis": "Real Betis Balompie", "Hsv": "Hamburger SV",
    "Bremen": "SV Werder Bremen", "Az": "AZ Alkmaar",
    "Bragantino": "Red Bull Bragantino", "Barca": "FC Barcelona",
    "Atleti": "Atletico de Madrid", "Qarabag Agdam": "Qarabag FK",
    "Bod/Glimt": "Bodo/Glimt", "Paphos": "Pafos FC",
    "Fk Kairat": "Kairat Almaty", "Sabah Fk": "Sabah FK",
    "Olympiacos": "Olympiacos Piraeus", "Copenhagen": "FC Copenhagen",
}


def clean_name(name: str) -> str:
    """去掉 Transfermarkt 俱乐部名尾部的 '(123456)' id"""
    return re.sub(r"\s*\(\d+\)\s*$", "", (name or "")).strip()


def norm(name: str):
    s = unicodedata.normalize("NFKD", clean_name(name)).encode("ascii", "ignore").decode()
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s.lower())
    words = [w for w in s.split() if w not in CLUB_TOKENS]
    return "".join(words)


def core_suffix(name: str):
    n = norm(name)
    suffix = {w for w in SUFFIX_TOKENS if n.endswith(w)}
    core = n
    for w in suffix:
        core = core[: -len(w)]
    return core, frozenset(suffix)


def is_youth(name: str) -> bool:
    low = clean_name(name).lower()
    return any(k in low for k in ("u19", "u20", "u21", "u23", "under", " ii", " b",
                                  "youth", "academy", "junioren"))


def tokens(name: str):
    s = unicodedata.normalize("NFKD", clean_name(name)).encode("ascii", "ignore").decode()
    s = "".join(ch if (ch.isalnum() or ch.isspace()) else " " for ch in s.lower())
    return {w for w in s.split() if w not in CLUB_TOKENS and len(w) > 2}


def main():
    # 1) Transfermarkt 俱乐部
    clubs = {}
    with open(EXT / "team_details" / "team_details.csv", encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            cid = r.get("club_id")
            if not cid:
                continue
            clubs.setdefault(cid, {
                "club_id": cid, "name": clean_name(r.get("club_name")),
                "logo": r.get("logo_url"), "country": r.get("country_name"),
                "competition": r.get("competition_name"),
                "division": r.get("club_division")})
    print(f"Transfermarkt 俱乐部: {len(clubs)}")

    # 2) 联赛名(取该俱乐部最近一次出现的联赛)
    comp_of = {}
    with open(EXT / "team_competitions_seasons" / "team_competitions_seasons.csv",
              encoding="utf-8", errors="replace") as f:
        for r in csv.DictReader(f):
            cid = r.get("club_id")
            season = r.get("season_id") or ""
            if cid and season >= comp_of.get(cid, ("", ""))[0]:
                comp_of[cid] = (season, r.get("competition_name"))
    for cid, (s, comp) in comp_of.items():
        if cid in clubs and comp:
            clubs[cid]["competition"] = comp

    # 3) 索引
    by_norm = defaultdict(list)
    club_tokens = {}
    for cid, c in clubs.items():
        by_norm[norm(c["name"])].append(cid)
        club_tokens[cid] = tokens(c["name"])

    # 别名(复用项目内已有别名表, 处理 Man City -> Manchester City 这类差异)
    try:
        from src.data_sources.thesportsdb import SEARCH_ALIAS
    except Exception:
        SEARCH_ALIAS = {}
    sys.path.insert(0, str(BASE))

    def candidate_names(name):
        out = [name]
        for extra in (TM_MANUAL_ALIAS.get(name), SEARCH_ALIAS.get(name)):
            if extra and extra not in out:
                out.append(extra)
        return out

    def fuzzy(cand_name, topn=3, country=None):
        """词元包含度匹配(处理 Man City vs Manchester City 这类包含关系)"""
        tk = tokens(cand_name)
        if not tk:
            return []
        scored = []
        for cid, ct in club_tokens.items():
            if not ct or is_youth(clubs[cid]["name"]):
                continue
            if country and (clubs[cid].get("country") or "") != country:
                continue
            inter = tk & ct
            if not inter or not any(len(w) >= 4 for w in inter):
                continue
            score = len(inter) / min(len(tk), len(ct))
            scored.append((score, cid))
        scored.sort(reverse=True)
        return scored[:topn]

    # 4) 本库球队
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    our = conn.execute("SELECT team_id, name, league_id FROM teams").fetchall()
    conn.execute("""CREATE TABLE IF NOT EXISTS tm_club_map (
        team_id INTEGER PRIMARY KEY, club_id TEXT, tm_name TEXT,
        tm_country TEXT, tm_competition TEXT, tm_logo TEXT, method TEXT)""")

    matched, unmatched = {}, []
    for t in our:
        name = t["name"]
        n = norm(name)
        cid = None
        method = None
        # 同名候选: 优先非青年队
        same = by_norm.get(n, [])
        if same:
            seniors = [c for c in same if not is_youth(clubs[c]["name"])]
            pool = seniors or same
            cid, method = pool[0], ("exact" if len(pool) == 1 else "exact-multi")
        else:
            core, sfx = core_suffix(name)
            cands = []
            for cid2, c in clubs.items():
                if is_youth(c["name"]):
                    continue
                c_core, c_sfx = core_suffix(c["name"])
                if c_core and c_core == core and (not sfx or not c_sfx or sfx == c_sfx):
                    cands.append(cid2)
            if len(cands) == 1:
                cid, method = cands[0], "core"
            elif len(cands) > 1:
                cands.sort(key=lambda x: abs(len(clubs[x]["name"]) - len(name)))
                cid, method = cands[0], "core-multi"

        # 仍未匹配: 别名 + 词元包含度(带国家过滤)
        if not cid:
            country = LEAGUE_COUNTRY.get(t["league_id"])
            best = (0.0, None, None)
            for cand_name in candidate_names(name):
                n2 = norm(cand_name)
                same2 = [c for c in by_norm.get(n2, [])
                         if not is_youth(clubs[c]["name"])] or by_norm.get(n2, [])
                if same2:
                    best = (1.0, same2[0], "alias-exact")
                    break
                for score, cid2 in fuzzy(cand_name, country=country) or fuzzy(cand_name):
                    if score > best[0]:
                        best = (score, cid2, "fuzzy")
            if best[1] and best[0] >= 0.6:
                cid, method = best[1], f"{best[2]}({best[0]:.2f})"
        if cid:
            c = clubs[cid]
            matched[name] = c
            conn.execute("INSERT OR REPLACE INTO tm_club_map VALUES (?,?,?,?,?,?,?)",
                         (t["team_id"], cid, c["name"], c["country"],
                          c["competition"], c["logo"], method))
        else:
            cands = fuzzy(name, topn=3)
            unmatched.append((name, [(round(s, 2), clubs[c]["name"], clubs[c].get("country"))
                                     for s, c in cands]))
    conn.commit()
    print(f"\n匹配成功: {len(matched)} / {len(our)}  ({len(matched)/len(our):.0%})")
    print(f"未匹配: {len(unmatched)} 支")
    for name, cands in unmatched[:40]:
        print(f"  {name:<20} 候选: " + "; ".join(f"{n}({c},{s})" for s, n, c in cands))

    with open(BASE / "data" / "tm_club_map.json", "w", encoding="utf-8") as f:
        json.dump({"matched": {k: v for k, v in sorted(matched.items())},
                   "unmatched": [{"name": n, "cands": c} for n, c in unmatched]},
                  f, ensure_ascii=False, indent=1)
    print(f"\n映射已保存: data/tm_club_map.json 与 DB 表 tm_club_map")
    conn.close()


if __name__ == "__main__":
    main()
