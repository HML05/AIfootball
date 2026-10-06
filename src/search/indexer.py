"""构建全文检索索引(SQLite FTS5)。

设计要点:
  * 索引放在**独立库** `data/database/search.db`, 不动业务主库 football.db,
    可以随时删掉重建, 也不影响已有 37 张表与接口;
  * FTS5 用 external content 表(content='docs'), 原文存在 docs.body,
    真正参与检索的是 docs.tokens(分词后的空格串);
  * 分词模式写进 meta 表, 查询时按同一模式切分, 避免"写入用 jieba、
    查询用 bigram"这类口径不一致导致的漏召回。

覆盖语料: 联赛 / 球队 / 球员 / 比赛 / 预测记录 + docs/*.md 文档(按标题分块)。
"""
from __future__ import annotations

import os
import re
import sqlite3
import time
from pathlib import Path
from typing import Iterable, Iterator

from config.settings import settings
from src.search.tokenizer import tokenize_for_index, default_mode, describe_mode

SEARCH_DB: Path = settings.DATA_DIR / "database" / "search.db"
MAX_BODY = 1200          # 单条文档正文上限(避免把整篇长文塞进索引)
DOCS_DIR: Path = settings.BASE_DIR / "docs"
# 中文别名表: 库里 teams 只有英文名, 用户却只会说「皇马」「巴萨」
ALIAS_FILE: Path = settings.DATA_DIR / "reference" / "team_alias_zh.json"

_ALIAS_CACHE: dict[str, list[str]] | None = None


def load_aliases(path: Path | None = None) -> dict[str, list[str]]:
    """读取中文别名表, 返回 {英文队名: [中文别名...]}。缺失时返回空表(不影响其它语料)。"""
    global _ALIAS_CACHE
    if _ALIAS_CACHE is not None and path is None:
        return _ALIAS_CACHE
    target = Path(path or ALIAS_FILE)
    data: dict[str, list[str]] = {}
    if target.exists():
        import json
        try:
            payload = json.loads(target.read_text(encoding="utf-8"))
            raw = payload.get("teams", payload)
            data = {str(k): [str(x) for x in v] for k, v in raw.items()
                    if isinstance(v, list)}
        except Exception as e:  # 别名表坏了不该让索引建不起来
            print(f"[search] 别名表解析失败({target}): {e}")
    if path is None:
        _ALIAS_CACHE = data
    return data


def alias_text(*names: str) -> str:
    """把若干英文队名对应的中文别名拼成一段可检索文本。"""
    table = load_aliases()
    out: list[str] = []
    for n in names:
        if not n:
            continue
        for a in table.get(n, []):
            if a not in out:
                out.append(a)
    return " ".join(out)


SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS docs(
  id        INTEGER PRIMARY KEY,
  kind      TEXT NOT NULL,
  ref       TEXT,
  title     TEXT NOT NULL,
  body      TEXT NOT NULL,
  tokens    TEXT NOT NULL,
  src_table TEXT,
  src_id    TEXT,
  extra     TEXT
);
CREATE VIRTUAL TABLE IF NOT EXISTS docs_fts USING fts5(
  title, tokens, content='docs', content_rowid='id', tokenize='unicode61'
);
CREATE INDEX IF NOT EXISTS idx_docs_kind ON docs(kind);
CREATE INDEX IF NOT EXISTS idx_docs_ref  ON docs(ref);
"""


def main_db_path() -> Path:
    """业务主库路径(与 SQLAlchemy 的 DATABASE_URL 保持一致)。"""
    url = settings.DATABASE_URL or ""
    if url.startswith("sqlite:///"):
        raw = url[len("sqlite:///"):]
        p = Path(raw)
        return p if p.is_absolute() else (settings.BASE_DIR / p).resolve()
    return settings.DATA_DIR / "database" / "football.db"


# ---------------------------------------------------------------- 语料生成

def _clip(text: str, limit: int = MAX_BODY) -> str:
    text = re.sub(r"\s+", " ", text or "").strip()
    return text if len(text) <= limit else text[:limit] + "…"


def league_docs(con: sqlite3.Connection) -> Iterator[dict]:
    for r in con.execute("SELECT league_id, name, name_en, country, season FROM leagues"):
        name = r[1] or r[2] or f"联赛{r[0]}"
        body = f"{name} {r[2] or ''} {r[3] or ''} 足球联赛 赛季 {r[4] or ''}"
        yield dict(kind="league", ref=f"league:{r[0]}", title=f"{name}（{r[3] or ''}联赛）",
                   body=body, src_table="leagues", src_id=str(r[0]),
                   extra={"league_id": r[0], "name": name})


def team_docs(con: sqlite3.Connection) -> Iterator[dict]:
    sql = """SELECT t.team_id, t.name, t.name_en, t.short_name, t.stadium, t.manager,
                    t.founded, t.elo_rating, l.name
             FROM teams t LEFT JOIN leagues l ON l.league_id = t.league_id"""
    for r in con.execute(sql):
        tid, name = r[0], r[1] or r[2] or f"球队{tid}"
        alias = alias_text(name)
        body = (f"{name} {r[2] or ''} {r[3] or ''} {alias} 球队 主教练 {r[5] or '未知'} "
                f"主场 {r[4] or '未知'} 成立 {r[6] or '未知'} 联赛 {r[8] or ''} "
                f"ELO {round(r[7], 1) if r[7] is not None else '未知'}")
        yield dict(kind="team", ref=f"team:{tid}", title=f"{name} {alias}（{r[8] or ''}）",
                   body=body, src_table="teams", src_id=str(tid),
                   extra={"team_id": tid, "name": name, "league": r[8], "alias": alias})


def player_docs(con: sqlite3.Connection) -> Iterator[dict]:
    sql = """SELECT p.player_id, p.name, p.name_en, p.position, p.nationality, p.age,
                    p.market_value, p.number, t.name, t.team_id
             FROM players p LEFT JOIN teams t ON t.team_id = p.team_id"""
    for r in con.execute(sql):
        pid, name = r[0], r[1] or r[2] or f"球员{pid}"
        body = (f"{name} {r[2] or ''} 球员 位置 {r[3] or '未知'} 国籍 {r[4] or '未知'} "
                f"年龄 {r[5] if r[5] is not None else '未知'} 号码 {r[7] or '未知'} "
                f"身价 {r[6] if r[6] is not None else '未知'} 效力 {r[8] or '未知'}")
        yield dict(kind="player", ref=f"player:{pid}", title=f"{name}（{r[8] or ''}）",
                   body=body, src_table="players", src_id=str(pid),
                   extra={"player_id": pid, "name": name, "team": r[8], "team_id": r[9]})


def match_docs(con: sqlite3.Connection) -> Iterator[dict]:
    sql = """SELECT m.match_id, m.date, m.season, m.matchday, m.status,
                    m.home_goals, m.away_goals, m.home_xg, m.away_xg,
                    m.referee, m.venue, h.name, a.name, l.name
             FROM matches m
             LEFT JOIN teams h ON h.team_id = m.home_team_id
             LEFT JOIN teams a ON a.team_id = m.away_team_id
             LEFT JOIN leagues l ON l.league_id = m.league_id"""
    for r in con.execute(sql):
        mid, home, away = r[0], r[11] or "主队", r[12] or "客队"
        score = (f"{r[5]}-{r[6]}" if r[5] is not None and r[6] is not None else "未开赛/无比分")
        alias = alias_text(home, away)
        body = (f"{home} 对阵 {away} {alias} 比分 {score} 日期 {r[1] or ''} 赛季 {r[2] or ''} "
                f"第 {r[3] or '?'} 轮 联赛 {r[13] or ''} 状态 {r[4] or ''} "
                f"xG {r[7] if r[7] is not None else '-'} 比 {r[8] if r[8] is not None else '-'} "
                f"裁判 {r[9] or '未知'} 场地 {r[10] or '未知'}")
        yield dict(kind="match", ref=f"match:{mid}", title=f"{home} {score} {away} {alias}",
                   body=body, src_table="matches", src_id=str(mid),
                   extra={"match_id": mid, "date": r[1], "home": home, "away": away})


def prediction_docs(con: sqlite3.Connection) -> Iterator[dict]:
    sql = """SELECT p.pred_id, p.match_id, p.model_version, p.pred_home_win, p.pred_draw,
                    p.pred_away_win, p.pred_result, p.actual_result, p.hit, p.is_backtest,
                    h.name, a.name, m.date
             FROM predictions p
             LEFT JOIN matches m ON m.match_id = p.match_id
             LEFT JOIN teams h ON h.team_id = m.home_team_id
             LEFT JOIN teams a ON a.team_id = m.away_team_id"""
    for r in con.execute(sql):
        home, away = r[10] or "主队", r[11] or "客队"
        probs = [x for x in (r[3], r[4], r[5]) if x is not None]
        pct = "/".join(f"{round(x * 100, 1)}%" for x in probs) if probs else "无概率"
        hit = "命中" if r[8] else ("未命中" if r[8] is not None else "未评估")
        kindtxt = "回测样本" if r[9] else "实盘预测"
        alias = alias_text(home, away)
        body = (f"{home} 对 {away} {alias} 预测 模型 {r[2]} 概率(主胜/平/客胜) {pct} "
                f"预测结果 {r[6] or '-'} 实际 {r[7] or '-'} {hit} {kindtxt} 日期 {r[12] or ''}")
        yield dict(kind="prediction", ref=f"prediction:{r[0]}",
                   title=f"预测 {home} vs {away} {alias}：{r[6] or '待定'}",
                   body=body, src_table="predictions", src_id=str(r[0]),
                   extra={"pred_id": r[0], "match_id": r[1], "model": r[2], "hit": r[8]})


_HEADING = re.compile(r"^(#{1,4})\s+(.*)$")


def doc_chunks() -> Iterator[dict]:
    """把 docs/*.md 按标题切块 —— 检索到的是"哪篇文档的哪一节"。"""
    if not DOCS_DIR.exists():
        return
    for path in sorted(DOCS_DIR.glob("*.md")):
        lines = path.read_text(encoding="utf-8", errors="replace").splitlines()
        title_stack: list[str] = []
        buf: list[str] = []
        start_line = 1
        rel = f"docs/{path.name}"

        def flush(end_line: int) -> dict | None:
            body = _clip("\n".join(buf))
            if not body:
                return None
            head = " · ".join(t for t in title_stack if t) or path.stem
            return dict(kind="doc", ref=f"{rel}#L{start_line}", title=f"{path.name} · {head}",
                        body=body, src_table="file", src_id=f"{rel}#L{start_line}",
                        extra={"file": rel, "line": start_line, "heading": head})

        for i, line in enumerate(lines, start=1):
            m = _HEADING.match(line)
            if m:
                if buf:
                    d = flush(i - 1)
                    if d:
                        yield d
                    buf = []
                level = len(m.group(1))
                title_stack = title_stack[: level - 1] + [m.group(2).strip()]
                start_line = i
            else:
                if not buf:
                    start_line = i
                buf.append(line)
        d = flush(len(lines))
        if d:
            yield d


def iter_documents(main_con: sqlite3.Connection) -> Iterable[dict]:
    yield from league_docs(main_con)
    yield from team_docs(main_con)
    yield from player_docs(main_con)
    yield from match_docs(main_con)
    yield from prediction_docs(main_con)
    yield from doc_chunks()


# ---------------------------------------------------------------- 建库

def build(path: Path | None = None, mode: str | None = None, verbose: bool = True) -> dict:
    """重建索引, 返回统计信息。

    先建到 `<索引>.tmp`, 建完再整体替换过去 —— 服务端正在同时被查询时,
    读连接拿到的要么是旧的完整索引、要么是新的完整索引, 不会读到建了一半的文件。
    """
    target = Path(path or SEARCH_DB)
    target.parent.mkdir(parents=True, exist_ok=True)
    mode = mode or default_mode()
    main_db = main_db_path()
    if not main_db.exists():
        raise FileNotFoundError(f"主库不存在: {main_db}")

    t0 = time.time()
    tmp = target.with_suffix(target.suffix + ".tmp")
    for leftover in (tmp, Path(str(tmp) + "-wal"), Path(str(tmp) + "-shm")):
        if leftover.exists():
            leftover.unlink()
    con = sqlite3.connect(tmp)
    try:
        con.executescript(SCHEMA)
        src = sqlite3.connect(f"file:{main_db}?mode=ro", uri=True)
        try:
            counts: dict[str, int] = {}
            batch: list[tuple] = []
            for doc in iter_documents(src):
                tokens, _ = tokenize_for_index(f"{doc['title']} {doc['body']}", mode)
                batch.append((doc["kind"], doc["ref"], doc["title"], doc["body"], tokens,
                              doc["src_table"], doc["src_id"],
                              _json_extra(doc.get("extra"))))
                counts[doc["kind"]] = counts.get(doc["kind"], 0) + 1
                if len(batch) >= 2000:
                    _insert(con, batch)
                    batch = []
            if batch:
                _insert(con, batch)
        finally:
            src.close()
        # content='docs' 的外部内容表: 写完 content 后整体重建一次 FTS 索引
        con.execute("INSERT INTO docs_fts(docs_fts) VALUES('rebuild')")
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)", ("mode", mode))
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                    ("built_at", time.strftime("%Y-%m-%d %H:%M:%S")))
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                    ("main_db", str(main_db)))
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                    ("source", "FootballAI 检索层 v1"))
        aliases = load_aliases()
        con.execute("INSERT OR REPLACE INTO meta(key, value) VALUES(?, ?)",
                    ("alias_teams", str(len(aliases))))
        con.commit()
        total = sum(counts.values())
        size = tmp.stat().st_size
        info = {"path": str(target), "mode": mode, "mode_desc": describe_mode(mode),
                "total": total, "by_kind": counts, "size_bytes": size,
                "alias_teams": len(aliases),
                "seconds": round(time.time() - t0, 1)}
    finally:
        con.close()

    _swap_in(tmp, target)
    if verbose:
        print(f"[search] 索引已重建: {target}")
        print(f"[search] 分词模式: {describe_mode(mode)}")
        print(f"[search] 文档数: {total}  " +
              "  ".join(f"{k}={v}" for k, v in sorted(counts.items(), key=lambda x: -x[1])))
        print(f"[search] 中文别名: {len(aliases)} 支球队（{ALIAS_FILE.name}）")
        print(f"[search] 体积: {size / 1048576:.1f} MB  用时: {info['seconds']}s")
    return info


def _swap_in(tmp: Path, target: Path, tries: int = 20, delay: float = 0.15) -> None:
    """把建好的临时索引替换成正式索引。

    Windows 上若还有别的进程正打开 target(哪怕只读), os.replace 会 PermissionError;
    服务端是"每次查询开一次连接、查完就关", 所以重试几次就能等到空档。
    """
    last: Exception | None = None
    for _ in range(max(1, tries)):
        try:
            os.replace(tmp, target)
            return
        except PermissionError as e:  # 目标被占用
            last = e
            time.sleep(delay)
        except OSError as e:  # 跨盘等情况退回到"删旧再改名"
            last = e
            break
    try:
        if target.exists():
            target.unlink()
        tmp.rename(target)
        return
    except OSError as e:
        raise RuntimeError(f"索引替换失败({target}): {last or e} —— 请停掉 API 后重试") from e
    finally:
        con.close()


def _insert(con: sqlite3.Connection, batch: list[tuple]) -> None:
    """只写 content 表; FTS 索引在全部写完后再整体 rebuild 一次(比逐批 rebuild 快)。"""
    con.executemany(
        "INSERT INTO docs(kind, ref, title, body, tokens, src_table, src_id, extra)"
        " VALUES(?,?,?,?,?,?,?,?)", batch)


def _json_extra(extra) -> str | None:
    if not extra:
        return None
    import json
    return json.dumps(extra, ensure_ascii=False)


if __name__ == "__main__":  # pragma: no cover
    build()
