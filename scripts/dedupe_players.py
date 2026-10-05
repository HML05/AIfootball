# -*- coding: utf-8 -*-
"""球员去重合并: 同一球员的中文行(球小策) 与 英文行(Transfermarkt) 合并为一行

保留策略:
  - name    = 中文名(球小策, 若有)  ← UI 主显示
  - name_en = 英文名(TM/球小策)     ← UI 可切英文
  - 其余字段取"更完整/更权威"的值: 号码取中文行(球小策有号码), 身价取 TM, 身高/体重/惯用脚取有值者

匹配: ① 同队 + 相同 tm_player_id  ② 同队 + 位置组相同 + 身高相同 + 年龄差≤1

用法:
    python scripts/dedupe_players.py            # 预演
    python scripts/dedupe_players.py --apply    # 执行
"""
import argparse
import re
import sqlite3
import unicodedata
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DB = BASE / "data" / "database" / "football.db"


def has_cn(s):
    return bool(re.search(r"[\u4e00-\u9fff]", str(s or "")))


def pos_group(p):
    p = str(p or "").lower()
    for k, v in (("goal", "GK"), ("keeper", "GK"), ("defend", "DF"),
                 ("midfield", "MF"), ("attack", "FW"), ("forward", "FW"),
                 ("striker", "FW"), ("winger", "FW")):
        if k in p:
            return v
    return p[:3].upper()


def score(row):
    """字段完整度打分(用于决定保留哪一行)"""
    fields = ["name", "name_en", "position", "nationality", "age", "height",
              "weight", "number", "market_value", "photo_url", "foot"]
    return sum(1 for f in fields if row[f] not in (None, "", "None"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    c = sqlite3.connect(str(DB))
    c.row_factory = sqlite3.Row

    rows = [dict(r) for r in c.execute("SELECT * FROM players")]
    by_team = {}
    for r in rows:
        by_team.setdefault(r["team_id"], []).append(r)
    print(f"球员总数 {len(rows):,} | 球队 {len(by_team)}")

    merges = []          # (keep_id, drop_id)
    used = set()

    # ① 同队 + tm_player_id 相同
    for tid, group in by_team.items():
        idx = {}
        for r in group:
            if r["tm_player_id"] and r["player_id"] not in used:
                idx.setdefault(str(r["tm_player_id"]), []).append(r)
        for tm_id, rs in idx.items():
            if len(rs) < 2:
                continue
            rs = sorted(rs, key=lambda x: (-(1 if has_cn(x["name"]) else 0), -score(x)))
            keep, drops = rs[0], rs[1:]
            for d in drops:
                if d["player_id"] not in used:
                    merges.append((keep, d))
                    used.add(d["player_id"])

    # ② 同队 + 位置组 + 身高 + 年龄差≤1 (无 tm 映射的中文/英文行)
    for tid, group in by_team.items():
        cn = [r for r in group if has_cn(r["name"]) and not r["tm_player_id"]
              and r["player_id"] not in used]
        en = [r for r in group if not has_cn(r["name"]) and not r["tm_player_id"]
              and r["player_id"] not in used]
        for a in cn:
            for b in en:
                if b["player_id"] in used:
                    continue
                if (pos_group(a["position"]) == pos_group(b["position"])
                        and a["height"] and b["height"]
                        and abs(float(a["height"]) - float(b["height"])) < 1
                        and a["age"] and b["age"] and abs(a["age"] - b["age"]) <= 1):
                    merges.append((a, b))
                    used.add(b["player_id"])
                    break

    print(f"可合并 {len(merges)} 组")
    for keep, drop in merges[:6]:
        print(f"   保留 {keep['name']}(id={keep['player_id']}) ← 删除 {drop['name']}(id={drop['player_id']})")

    if not args.apply:
        print("\n(预演, 未修改; 加 --apply 执行)")
        c.close()
        return

    for keep, drop in merges:
        # 合并字段: 名称双语并存, 其余取有值者
        name = keep["name"] if has_cn(keep["name"]) else (drop["name"] if has_cn(drop["name"]) else keep["name"])
        name_en = keep["name_en"] or (drop["name"] if not has_cn(drop["name"]) else None) \
            or (keep["name"] if not has_cn(keep["name"]) else None)
        c.execute("""UPDATE players SET
                name=?, name_en=COALESCE(NULLIF(name_en,''), ?),
                position=COALESCE(NULLIF(position,''), ?),
                nationality=COALESCE(NULLIF(nationality,''), ?),
                height=COALESCE(height, ?), weight=COALESCE(NULLIF(weight,''), ?),
                foot=COALESCE(NULLIF(foot,''), ?),
                number=COALESCE(number, ?),
                market_value=COALESCE(market_value, ?),
                photo_url=COALESCE(NULLIF(photo_url,''), ?),
                age=COALESCE(age, ?),
                tm_player_id=COALESCE(tm_player_id, ?),
                af_player_id=COALESCE(af_player_id, ?)
            WHERE player_id=?""",
            (name, name_en or None,
             keep["position"] or drop["position"], keep["nationality"] or drop["nationality"],
             keep["height"] or drop["height"], keep["weight"] or drop["weight"],
             keep["foot"] or drop["foot"], keep["number"] or drop["number"],
             keep["market_value"] or drop["market_value"],
             keep["photo_url"] or drop["photo_url"], keep["age"] or drop["age"],
             keep["tm_player_id"] or drop["tm_player_id"],
             keep["af_player_id"] or drop["af_player_id"], keep["player_id"]))
        c.execute("DELETE FROM players WHERE player_id=?", (drop["player_id"],))
    c.commit()
    left = c.execute("SELECT COUNT(*) FROM players").fetchone()[0]
    print(f"\n合并完成: 删除重复 {len(merges)} 行 | 球员数 {len(rows):,} -> {left:,}")
    dup = c.execute("""SELECT COUNT(*) FROM (SELECT team_id, tm_player_id FROM players
                       WHERE tm_player_id IS NOT NULL GROUP BY team_id, tm_player_id
                       HAVING COUNT(*)>1)""").fetchone()[0]
    print(f"同队同 tm 重复组: {dup} (应为 0)")
    c.close()


if __name__ == "__main__":
    main()
