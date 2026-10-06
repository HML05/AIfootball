# -*- coding: utf-8 -*-
"""检索层自检（RAG 阶段 0）。

覆盖四件事：
  1. 语料与索引（规模、分词模式、6 类语料齐全）；
  2. 中文检索质量 —— **现场复现** unicode61 / trigram 分词器的问题，再验证本方案能命中；
  3. 引用溯源 —— 每条结果都能回溯到主库记录 / 文档行号；
  4. 接口与闸门 —— 未登录 401、登录后可用、kind 过滤、空查询与延迟。

跑法：
    python scripts/build_search_index.py      # 先建索引
    python scripts/verify_search.py           # 需要 API 已在 8000 端口运行
"""
from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

from src.search.indexer import SEARCH_DB, main_db_path  # noqa: E402
from src.search.query import KINDS, index_stats, search  # noqa: E402

import _uiauth  # noqa: E402

API = os.environ.get("FA_API", "http://127.0.0.1:8000").rstrip("/")
PASS = 0
FAIL = 0
FAILED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    global PASS, FAIL
    if cond:
        PASS += 1
        print(f"  [PASS] {name}" + (f"  {detail}" if detail else ""))
    else:
        FAIL += 1
        FAILED.append(name)
        print(f"  [FAIL] {name}  {detail}")


def section(title: str) -> None:
    print(f"\n=== {title} ===")


def http(path: str, headers: dict | None = None, timeout: float = 20.0):
    url = API + path
    req = urllib.request.Request(url, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(body)
        except Exception:
            return e.code, {"raw": body[:200]}


def fts_baseline(tokenize: str, text: str, query: str) -> tuple[int, str]:
    """现场建一个临时 FTS5 表，复现官方分词器在中文上的表现。"""
    con = sqlite3.connect(":memory:")
    try:
        con.execute(f"CREATE VIRTUAL TABLE t USING fts5(body, tokenize='{tokenize}')")
        con.execute("INSERT INTO t(body) VALUES(?)", (text,))
        n = con.execute("SELECT COUNT(*) FROM t WHERE t MATCH ?", (query,)).fetchone()[0]
        return n, tokenize
    except sqlite3.Error as e:  # 该分词器不可用
        return -1, f"{tokenize}: {e}"
    finally:
        con.close()


def main() -> int:
    print("FootballAI 检索层自检（RAG 阶段 0）")
    print(f"索引: {SEARCH_DB}")

    # ---------------------------------------------------------- 1. 语料与索引
    section("1. 语料与索引")
    check("索引文件已生成", SEARCH_DB.exists(), f"{SEARCH_DB}")
    if not SEARCH_DB.exists():
        print("\n请先运行: python scripts/build_search_index.py")
        return 1
    size_mb = SEARCH_DB.stat().st_size / 1048576
    check("索引体积 > 2 MB", size_mb > 2, f"{size_mb:.1f} MB")

    st = index_stats()
    check("分词模式已记录", bool(st.get("mode")), f"mode={st.get('mode')} ({st.get('mode_desc')})")
    check("文档总量 >= 19000", st["total"] >= 19000, f"total={st['total']}")
    missing = [k for k in KINDS if k not in st["by_kind"]]
    check("6 类语料齐全", not missing,
          "  ".join(f"{k}={st['by_kind'].get(k, 0)}" for k in KINDS) if not missing else f"缺: {missing}")

    # ------------------------------------------------- 2. 中文检索质量(含基线对比)
    section("2. 中文检索质量（先复现官方分词器的问题，再验证本方案）")
    sample = "皇家马德里主场逆转巴塞罗那"
    n_u61, _ = fts_baseline("unicode61", sample, "马德里")
    check("复现: unicode61 查「马德里」命中数 == 0", n_u61 == 0, f"unicode61 命中 {n_u61}")
    n_tri, _ = fts_baseline("trigram", sample, "逆转")
    check("复现: trigram 查两字词「逆转」命中数 == 0", n_tri == 0, f"trigram 命中 {n_tri}")

    r = search("马德里", limit=5)
    check("本方案: 查「马德里」有命中", r["count"] > 0,
          f"count={r['count']} tokens={r['tokens']}")

    # 从主库取一个真实的两字球队名，验证两字词召回
    con = sqlite3.connect(f"file:{main_db_path()}?mode=ro", uri=True)
    try:
        two = con.execute("SELECT name FROM teams WHERE LENGTH(name) = 2 LIMIT 1").fetchone()
        two_name = two[0] if two else "曼城"
        row = con.execute("SELECT name FROM players WHERE name IS NOT NULL AND LENGTH(name) >= 3 LIMIT 1").fetchone()
        player_name = row[0] if row else "姆巴佩"
        real_team = con.execute("SELECT name FROM teams ORDER BY elo_rating DESC LIMIT 1").fetchone()
        real_team = real_team[0] if real_team else "皇家马德里"
    finally:
        con.close()

    r2 = search(two_name, kind="team", limit=5)
    check(f"两字词召回: 「{two_name}」在球队语料里命中", r2["count"] > 0 and any(
        two_name in h["title"] for h in r2["hits"]),
        f"count={r2['count']} 首条={r2['hits'][0]['title'] if r2['hits'] else '-'}")

    r3 = search(real_team, kind="team", limit=5)
    check(f"球队检索: 「{real_team}」命中 team 且带联赛信息",
          r3["count"] > 0 and any("（" in h["title"] for h in r3["hits"]),
          f"count={r3['count']} 首条={r3['hits'][0]['title'] if r3['hits'] else '-'}")

    r4 = search(player_name, kind="player", limit=5)
    check(f"球员检索: 「{player_name}」命中 player", r4["count"] > 0,
          f"count={r4['count']} 首条={r4['hits'][0]['title'] if r4['hits'] else '-'}")

    r5 = search("部署", kind="doc", limit=5)
    doc_ok = r5["count"] > 0 and any("docs/" in (h["ref"] or "") and "#L" in (h["ref"] or "")
                                     for h in r5["hits"])
    check("文档检索: 查「部署」命中 docs/*.md 且带行号", doc_ok,
          f"count={r5['count']} 首条={r5['hits'][0]['ref'] if r5['hits'] else '-'}")

    # ------------------------------------------------------------- 3. 引用溯源
    section("3. 引用溯源（每条结果都要能回溯）")
    all_hits = [h for res in (r, r2, r3, r4, r5) for h in res["hits"]]
    complete = [h for h in all_hits
                if h["source"].get("table") and h["source"].get("id") and h["source"].get("ref")]
    check("所有命中都带 source(table/id/ref)", len(complete) == len(all_hits),
          f"{len(complete)}/{len(all_hits)}")

    con = sqlite3.connect(f"file:{main_db_path()}?mode=ro", uri=True)
    try:
        m_hits = [h for h in search("皇马", kind="match", limit=3)["hits"]]
        m_ok = 0
        for h in m_hits:
            n = con.execute("SELECT COUNT(*) FROM matches WHERE match_id = ?",
                            (int(h["source"]["id"]),)).fetchone()[0]
            m_ok += 1 if n else 0
        check("比赛命中的 source.id 在主库 matches 里真实存在",
              bool(m_hits) and m_ok == len(m_hits), f"{m_ok}/{len(m_hits)}")

        p_hits = search(player_name, kind="player", limit=3)["hits"]
        p_ok = sum(1 for h in p_hits if con.execute(
            "SELECT COUNT(*) FROM players WHERE player_id = ?", (int(h["source"]["id"]),)).fetchone()[0])
        check("球员命中的 source.id 在主库 players 里真实存在",
              bool(p_hits) and p_ok == len(p_hits), f"{p_ok}/{len(p_hits)}")

        d_hits = search("模型", kind="prediction", limit=3)["hits"]
        d_ok = sum(1 for h in d_hits if con.execute(
            "SELECT COUNT(*) FROM predictions WHERE pred_id = ?", (int(h["source"]["id"]),)).fetchone()[0])
        check("预测命中的 source.id 在主库 predictions 里真实存在",
              bool(d_hits) and d_ok == len(d_hits), f"{d_ok}/{len(d_hits)}")
    finally:
        con.close()

    url_hit = next((h for h in r3["hits"] if h["source"].get("url")), None)
    check("球队/球员/比赛命中带前端跳转 URL", url_hit is not None,
          f"{url_hit['source']['url'] if url_hit else '-'}")

    # --------------------------------------------------- 4. 接口、闸门与性能
    section("4. 接口与登录闸门")
    q = urllib.parse.quote("皇家马德里")
    st_code, _ = http(f"/api/ui/search?q={q}")
    check("未登录访问 /api/ui/search -> 401", st_code == 401, f"HTTP {st_code}")

    try:
        hdrs = _uiauth.headers()
    except SystemExit as e:
        check("取登录 token（admin/football2026）", False, str(e))
        hdrs = None

    if hdrs:
        code, body = http(f"/api/ui/search?q={q}&limit=5", hdrs)
        check("登录后 /api/ui/search -> 200 且有命中",
              code == 200 and body.get("count", 0) > 0,
              f"HTTP {code} count={body.get('count')} 首条={body['hits'][0]['title'] if body.get('hits') else '-'}")

        code2, body2 = http(f"/api/ui/search?q={urllib.parse.quote('曼城')}&kind=team", hdrs)
        kinds = {h["kind"] for h in body2.get("hits", [])}
        check("kind 过滤生效", code2 == 200 and kinds == {"team"}, f"HTTP {code2} kinds={kinds or '-'}")

        code3, body3 = http("/api/ui/search/stats", hdrs)
        check("索引统计接口可用", code3 == 200 and body3.get("ready") is True,
              f"HTTP {code3} total={body3.get('total')} mode={body3.get('mode')}")

        code4, body4 = http("/api/ui/search?q=", hdrs)
        check("空查询不报错且返回 0 条", code4 == 200 and body4.get("count") == 0,
              f"HTTP {code4} count={body4.get('count')}")

    # 性能
    t0 = time.perf_counter()
    for _ in range(20):
        search("皇家马德里 逆转", limit=10)
    dt = (time.perf_counter() - t0) / 20 * 1000
    check("单次查询平均耗时 < 300ms", dt < 300, f"{dt:.1f} ms（含连接建立）")

    print(f"\n结果: {PASS} 通过 / {FAIL} 失败  共 {PASS + FAIL} 项")
    if FAILED:
        print("失败项: " + "；".join(FAILED))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
