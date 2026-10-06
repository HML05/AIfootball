"""检索层查询: FTS5 MATCH + bm25 排序 + 中文命中片段。

用法:
    from src.search.query import search, index_stats
    search("皇马 逆转", kind="match", limit=5)
"""
from __future__ import annotations

import sqlite3
from typing import Any

from src.search.indexer import SEARCH_DB
from src.search.tokenizer import (
    MODE_JIEBA,
    default_mode,
    describe_mode,
    tokenize_for_query,
)

KINDS = ("league", "team", "player", "match", "prediction", "doc")
KIND_LABEL = {
    "league": "联赛",
    "team": "球队",
    "player": "球员",
    "match": "比赛",
    "prediction": "预测",
    "doc": "文档",
}


class IndexMissing(RuntimeError):
    """索引还没建 —— 提示用户先跑 scripts/build_search_index.py。"""


def _connect() -> sqlite3.Connection:
    if not SEARCH_DB.exists():
        raise IndexMissing(
            f"检索索引不存在: {SEARCH_DB}（先运行 python scripts/build_search_index.py）")
    con = sqlite3.connect(f"file:{SEARCH_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    return con


def _meta(con: sqlite3.Connection) -> dict[str, str]:
    try:
        return {r["key"]: r["value"] for r in con.execute("SELECT key, value FROM meta")}
    except sqlite3.Error:
        return {}


def index_stats() -> dict[str, Any]:
    """索引概况(给 /api/ui/search/stats 与自检脚本用)。"""
    con = _connect()
    try:
        meta = _meta(con)
        by_kind = {r["kind"]: r["n"] for r in
                   con.execute("SELECT kind, COUNT(*) AS n FROM docs GROUP BY kind")}
        total = sum(by_kind.values())
        return {
            "ready": True,
            "path": str(SEARCH_DB),
            "size_bytes": SEARCH_DB.stat().st_size,
            "total": total,
            "by_kind": by_kind,
            "by_kind_label": {KIND_LABEL.get(k, k): v for k, v in by_kind.items()},
            "mode": meta.get("mode", ""),
            "mode_desc": describe_mode(meta.get("mode")),
            "built_at": meta.get("built_at", ""),
            "main_db": meta.get("main_db", ""),
        }
    finally:
        con.close()


def _quote(token: str) -> str:
    """FTS5 语法安全: token 用双引号包住, 内部引号翻倍。"""
    return '"' + token.replace('"', '""') + '"'


def _match_expr(tokens: list[str], operator: str) -> str:
    return f" {operator} ".join(_quote(t) for t in tokens)


def _snippet(body: str, tokens: list[str], width: int = 46) -> str:
    """在原文里定位第一个命中的 token, 取上下文窗口并用【】标出。"""
    low = (body or "").lower()
    best = -1
    hit = ""
    for t in tokens:
        i = low.find(t.lower())
        if i >= 0 and (best < 0 or i < best):
            best, hit = i, t
    if best < 0:
        return (body or "")[: width * 2] + ("…" if len(body or "") > width * 2 else "")
    start = max(0, best - width // 2)
    end = min(len(body), best + len(hit) + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(body) else ""
    return f"{prefix}{body[start:best]}【{body[best:best + len(hit)]}】{body[best + len(hit):end]}{suffix}"


def _hit(row: sqlite3.Row, tokens: list[str]) -> dict[str, Any]:
    extra = None
    if row["extra"]:
        import json
        try:
            extra = json.loads(row["extra"])
        except Exception:
            extra = None
    return {
        "id": row["id"],
        "kind": row["kind"],
        "kind_label": KIND_LABEL.get(row["kind"], row["kind"]),
        "ref": row["ref"],
        "title": row["title"],
        "snippet": _snippet(row["body"], tokens),
        "score": round(-float(row["score"]), 4),  # bm25 越小越相关 -> 取负号变成"越大越相关"
        "source": {
            "table": row["src_table"],
            "id": row["src_id"],
            "ref": row["ref"],
            "url": _source_url(row["kind"], extra),
        },
        "extra": extra,
    }


def _source_url(kind: str, extra: dict | None) -> str | None:
    """让前端能一键跳到对应页面(前端路由见 webui/src/App.tsx)。"""
    extra = extra or {}
    if kind == "team" and extra.get("team_id"):
        return f"/teams/{extra['team_id']}"
    if kind == "player" and extra.get("player_id"):
        return f"/players/{extra['player_id']}"
    if kind == "match" and extra.get("match_id"):
        return f"/matches/{extra['match_id']}"
    return None


def search(query: str, kind: str | None = None, limit: int = 10, offset: int = 0) -> dict[str, Any]:
    """检索。

    先按 AND(所有 token 都要出现) 检索, 无结果再退化成 OR(任一词出现即可),
    这样"皇家马德里 逆转"这类长查询不会因为一个词缺失就 0 结果。
    """
    query = (query or "").strip()
    limit = max(1, min(int(limit or 10), 50))
    offset = max(0, int(offset or 0))
    kind = (kind or "").strip() or None
    if kind and kind not in KINDS:
        kind = None

    if not query:
        return {"query": query, "tokens": [], "count": 0, "operator": None,
                "mode": default_mode(), "hits": [], "kinds": list(KINDS)}

    con = _connect()
    try:
        meta = _meta(con)
        mode = meta.get("mode") or default_mode()
        tokens = tokenize_for_query(query, mode)
        if not tokens:
            return {"query": query, "tokens": [], "count": 0, "operator": None,
                    "mode": mode, "hits": [], "kinds": list(KINDS)}

        where = ["docs_fts MATCH ?"]
        params: list[Any] = []
        if kind:
            where.append("d.kind = ?")
        tail = "".join(f" AND {w}" for w in where[1:])

        rows: list[sqlite3.Row] = []
        operator = None
        for op in ("AND", "OR"):
            expr = _match_expr(tokens, op)
            rows = con.execute(
                f"""SELECT d.id, d.kind, d.ref, d.title, d.body, d.src_table, d.src_id, d.extra,
                           bm25(docs_fts) AS score
                    FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid
                    WHERE {where[0]}{tail}
                    ORDER BY (CASE WHEN d.title LIKE ? THEN 0 ELSE 1 END), score
                    LIMIT ? OFFSET ?""",
                [expr] + ([kind] if kind else []) + [f"%{query}%", limit, offset]).fetchall()
            operator = op
            if rows:
                break

        expr = _match_expr(tokens, operator or "AND")
        count = con.execute(
            f"SELECT COUNT(*) AS n FROM docs_fts JOIN docs d ON d.id = docs_fts.rowid"
            f" WHERE docs_fts MATCH ?{tail}",
            [expr] + ([kind] if kind else [])).fetchone()["n"]

        return {
            "query": query,
            "tokens": tokens,
            "operator": operator,
            "mode": mode,
            "mode_desc": describe_mode(mode),
            "kind": kind,
            "count": count,
            "returned": len(rows),
            "kinds": list(KINDS),
            "hits": [_hit(r, tokens) for r in rows],
        }
    finally:
        con.close()


def try_stats() -> dict[str, Any]:
    """不抛异常的统计(接口用): 索引缺失时返回 ready=False。"""
    try:
        return index_stats()
    except IndexMissing as e:
        return {"ready": False, "path": str(SEARCH_DB), "detail": str(e)}
    except sqlite3.Error as e:
        return {"ready": False, "path": str(SEARCH_DB), "detail": f"索引读取失败: {e}"}


__all__ = ["KINDS", "KIND_LABEL", "IndexMissing", "index_stats", "search", "try_stats"]
