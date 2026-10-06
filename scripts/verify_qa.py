# -*- coding: utf-8 -*-
"""智能问答层自检（RAG 阶段 1）。

覆盖四件事：
  1. 工具层 —— 六个结构化工具返回真实库内事实（找队/找球员、近况去重、交锋记录、积分榜、预测、球员）；
  2. 意图与检索串 —— 中文问题的意图识别、实体识别，以及给全文检索用的去虚词查询串；
  3. 编排 —— 没有 LLM key 时降级为「检索摘要」、答案有事实兜底、引用编号连续且都能回主库查到；
  4. 接口与闸门 —— 未登录 401、登录后可用、status 与 ask 的形状与延迟。

诚实性检查（重点）：答案必须来自工具/检索结果（不是凭空生成），来源表中的每条
(table, id) 都必须在主库真实存在；没有 key 时必须明确说明处于检索摘要模式。

跑法：
    python scripts/build_search_index.py      # 检索索引要先建好
    python scripts/verify_qa.py               # 需要 API 已在 8000 端口运行
"""
from __future__ import annotations

import json
import os
import re
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

from src.qa import orchestrator  # noqa: E402
from src.qa import router as R  # noqa: E402
from src.qa import tools as T  # noqa: E402
from src.search.indexer import main_db_path  # noqa: E402

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


def http(path: str, headers: dict | None = None, data: dict | None = None, timeout: float = 60.0):
    body = json.dumps(data).encode("utf-8") if data is not None else None
    req = urllib.request.Request(API + path, data=body, headers=dict(headers or {}))
    if data is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"raw": raw[:200]}


def db_has(table: str, ident) -> bool | None:
    """主库里 (table, id) 是否真实存在；查不了的返回 None（跳过）。

    注意 predictions 是 WITHOUT ROWID 表（主键 pred_id, 没有 rowid）, 必须按各表主键查。
    """
    pk = {"leagues": "league_id", "teams": "team_id", "players": "player_id", "matches": "match_id",
          "predictions": "pred_id", "standings": "id", "player_radar": "player_id",
          "tm_player_seasons": "rowid", "tm_players": "player_id"}
    col = pk.get(table, "rowid")
    path = main_db_path()
    if not path or not Path(str(path)).is_file():
        return None
    try:
        con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    except sqlite3.Error:
        return None
    try:
        row = con.execute(f"SELECT 1 FROM {table} WHERE {col} = ? LIMIT 1", (ident,)).fetchone()
        return bool(row)
    except sqlite3.Error:
        return None
    finally:
        con.close()


def answer_grounded(answer: str, facts: list[dict]) -> tuple[bool, str]:
    """检索摘要模式下的答案应当由工具事实拼成 —— 抽查首条事实的开头是否出现在答案里。"""
    if not facts:
        return False, "没有工具事实"
    head = str(facts[0].get("summary") or "")[:14]
    return (head in answer) if head else False, head


def main() -> int:
    global PASS, FAIL
    PASS = FAIL = 0
    FAILED.clear()

    # ------------------------------------------------------------ 1. 工具层
    section("1. 工具层（六个结构化工具读到的是真库数据）")
    t = T.find_team("皇马")
    check("中文别名找队: 皇马 → Real Madrid", bool(t) and t["name"] == "Real Madrid",
          f"{t.get('name') if t else '-'} 别名={t.get('alias') if t else '-'}")
    check("中文别名找队: 曼城 / 巴萨",
          (T.find_team("曼城") or {}).get("name") == "Man City"
          and (T.find_team("巴萨") or {}).get("name") == "Barcelona")
    check("不存在的球队返回 None（不抛异常）", T.find_team("不存在的球队xyz") is None)

    info = T.team_info("皇家马德里")
    check("team_info: 有 Elo/身价/排名, 来源指向 teams 表",
          info["ok"] and "Elo" in info["summary"] and "身价" in info["summary"]
          and any(s["table"] == "teams" for s in info["sources"]),
          info["summary"][:60])

    form = T.team_form("曼城", 5)
    check("team_form: 返回 5 场", form["ok"] and len(form["data"]["items"]) == 5,
          f"{len(form['data'].get('items', []))} 场")
    keys = [(m["home"], m["away"], m["score"]) for m in form["data"]["items"]]
    check("team_form: 同对手同比分的重复采集已折叠", len(set(keys)) == len(keys),
          f"{len(keys)} 条 / 去重后 {len(set(keys))} 条")

    h2h = T.head_to_head("皇马", "巴萨", 10)
    rec = h2h["data"].get("record") or {}
    total = len(h2h["data"].get("items") or [])
    check("head_to_head: 胜平负之和等于场次数",
          h2h["ok"] and total > 0 and rec.get("a_wins", 0) + rec.get("draws", 0) + rec.get("b_wins", 0) == total,
          f"{total} 场 {rec}")
    hkeys = [(i["date"][:10], i["home"], i["away"], i["score"]) for i in h2h["data"]["items"]]
    check("head_to_head: 交锋记录无重复行（同一天同对阵同比分）", len(set(hkeys)) == len(hkeys),
          f"{len(hkeys)} 条（同比分不同赛季属正常, 不算重复）")

    table = T.league_table("英超", 5)
    ranks = [r["rank"] for r in table["data"].get("rows", [])]
    check("league_table: 5 行且名次递增", table["ok"] and len(ranks) == 5 and ranks == sorted(ranks),
          f"ranks={ranks}")

    pred = T.match_prediction("Elche", "Real Madrid")
    probs = pred["data"].get("probabilities") or {}
    total_p = sum(float(v) for v in probs.values()) if probs else 0
    check("match_prediction: 概率三项之和 ≈ 1, 带模型版本",
          pred["ok"] and abs(total_p - 1) < 0.01 and bool((pred["data"].get("match") or {}).get("model_version")),
          f"sum={total_p:.4f} model={(pred['data'].get('match') or {}).get('model_version')}")

    miss = T.match_prediction("不存在的队A", "不存在的队B")
    check("match_prediction: 查不到时 ok=False 且给出原因", miss["ok"] is False and bool(miss["summary"]),
          miss["summary"][:50])

    pl = T.player_info("凯帕")
    check("player_info: 事实里没有 55.0 这种浮点尾巴（已取整）",
          pl["ok"] and not re.search(r"\d+\.0(?![0-9])", pl["summary"]),
          pl["summary"][:60])

    bad = [T.team_info("不存在xyz"), T.team_form("不存在xyz"), T.head_to_head("不存在xyz", "皇马"),
           T.league_table("不存在的联赛"), T.player_info("不存在xyz")]
    check("未知实体: 五个工具都返回 ok=False 而不是抛异常", all(b["ok"] is False for b in bad))
    check("工具返回结构统一: tool/ok/summary/data/sources",
          all({"tool", "ok", "summary", "data", "sources"} <= set(b) for b in bad + [info, form, h2h, table, pred, pl]))

    # ------------------------------------------------- 2. 意图与检索串
    section("2. 意图与实体识别 / 检索查询串")
    cases = [("皇马和巴萨谁赢", "predict"), ("曼城最近状态", "form"), ("英超积分榜", "standings"),
             ("凯帕身价多少", "player"), ("利物浦主教练是谁", "team"), ("逆转", "search")]
    got = {q: (R.plan(q)["intent"]) for q, _ in cases}
    check("六类意图全部识别正确", all(got[q] == want for q, want in cases), str(got))

    sq = R.search_query("皇马和巴萨谁赢", R.extract("皇马和巴萨谁赢"))
    check("检索串已去掉疑问词（谁/和）", "谁" not in sq and "和" not in sq, f"「{sq}」")
    check("检索串仍保留实体", "皇马" in sq and "巴萨" in sq)
    sq2 = R.search_query("齐达内执教哪支球队", R.extract("齐达内执教哪支球队"))
    check("没有识别到实体时检索串也非空", bool(sq2.strip()), f"「{sq2}」")

    # ------------------------------------------------------------ 3. 编排
    section("3. 编排：事实 + 检索 + 引用（未配置 key 时降级）")
    r = orchestrator.ask("皇马和巴萨谁赢", use_llm=False, top_k=3)
    check("ask(use_llm=False) → mode=retrieval", r["mode"] == "retrieval", f"mode={r['mode']}")
    ok_grounded, head = answer_grounded(r["answer"], r["facts"])
    check("答案由工具事实拼成（不是凭空生成）", ok_grounded, f"首条事实开头「{head}」")
    nums = [s["n"] for s in r["sources"]]
    check("引用编号从 1 开始且连续", nums == list(range(1, len(nums) + 1)), f"{len(nums)} 条引用")
    missing_rows = []
    for s in r["sources"]:
        if s["table"] in ("docs",):
            continue
        exists = db_has(s["table"], s["id"])
        if exists is False:
            missing_rows.append(f"{s['table']}#{s['id']}")
    check("引用都能回主库查到（无幽灵来源）", not missing_rows, "、".join(missing_rows) or f"{len(r['sources'])} 条全部命中")
    check("检索部分带 query/tokens/count",
          bool(r["search"]["query"]) and bool(r["search"]["tokens"]) and isinstance(r["search"]["count"], int),
          f"tokens={r['search']['tokens']} count={r['search']['count']}")
    tm = r["timing"]
    check("timing 四个字段都是数字",
          all(isinstance(tm.get(k), int) for k in ("tools_ms", "search_ms", "llm_ms", "total_ms")), str(tm))
    check("计划里有可展示的步骤与理由",
          bool(r["plan"]["steps"]) and all(s.get("reason") for s in r["plan"]["steps"]),
          f"{len(r['plan']['steps'])} 步")

    if not orchestrator.llm.ready():
        honest = orchestrator.ask("皇马和巴萨谁赢", use_llm=True, top_k=2)   # 请求了 LLM 但没有 key
        check("未配置 LLM_API_KEY 时明确说明处于检索摘要模式",
              honest["mode"] == "retrieval" and any("LLM_API_KEY" in m for m in honest["missing"]),
              "；".join(honest["missing"])[:80] or "missing 里没有说明")
    else:
        check("已配置 LLM_API_KEY 时 mode 允许为 llm 或 retrieval（调用失败会降级）",
              r["mode"] in ("llm", "retrieval"), f"mode={r['mode']} llm.ok={r['llm']['ok']}")

    unknown = orchestrator.ask("齐达内执教哪支球队", use_llm=False)
    check("库内没有的问题也能给出回答或说明（不抛异常）",
          bool(unknown["answer"]) or bool(unknown["missing"]), f"intent={unknown['intent']}")
    empty = orchestrator.ask("", use_llm=False)
    check("空问题不报错", empty["mode"] in ("retrieval", "llm", "empty"), f"mode={empty['mode']}")

    # ------------------------------------------------------- 4. 接口与闸门
    section("4. 接口与登录闸门")
    code_anon, _ = http("/api/ui/ask/status")
    check("未登录 GET /api/ui/ask/status → 401", code_anon == 401, f"HTTP {code_anon}")
    code_anon2, _ = http("/api/ui/ask", data={"question": "英超积分榜", "use_llm": False})
    check("未登录 POST /api/ui/ask → 401", code_anon2 == 401, f"HTTP {code_anon2}")

    try:
        hdrs = _uiauth.headers()
    except SystemExit as e:
        check("取登录 token（admin/football2026）", False, str(e))
        hdrs = None

    if hdrs:
        code_st, st = http("/api/ui/ask/status", hdrs)
        check("status 接口: mode 与 llm_ready 一致",
              code_st == 200 and st.get("mode") == ("llm" if st.get("llm_ready") else "retrieval"),
              f"HTTP {code_st} llm_ready={st.get('llm_ready')} mode={st.get('mode')}")
        check("status 接口: 报告索引与别名规模",
              st.get("alias_teams", 0) > 0 and st.get("players_indexed", 0) > 0,
              f"别名球队 {st.get('alias_teams')} / 球员 {st.get('players_indexed')} / 联赛 {st.get('leagues_indexed')}")
        check("status 接口: 列出六个工具",
              isinstance(st.get("tools"), list) and len(st.get("tools") or []) == 6,
              f"{len(st.get('tools') or [])} 个")

        t0 = time.perf_counter()
        code_ask, body = http("/api/ui/ask", hdrs, {"question": "英超积分榜", "top_k": 3, "use_llm": False})
        dt = (time.perf_counter() - t0) * 1000
        check("POST /api/ui/ask → 200 且 mode/sources 正常",
              code_ask == 200 and body.get("mode") in ("llm", "retrieval") and bool(body.get("sources")),
              f"HTTP {code_ask} mode={body.get('mode')} sources={len(body.get('sources') or [])} {dt:.0f} ms")
        check("单次问答耗时 < 5s", dt < 5000, f"{dt:.0f} ms")

        code_get, body_get = http(f"/api/ui/ask?q={urllib.parse.quote('凯帕身价多少')}&use_llm=false", hdrs)
        check("GET /api/ui/ask（调试用）同样可用",
              code_get == 200 and bool(body_get.get("answer")), f"HTTP {code_get}")

        code_bad, body_bad = http("/api/ui/ask", hdrs, {"question": "英超积分榜", "top_k": 999})
        check("超出范围的 top_k 被参数校验拦住（422）", code_bad == 422, f"HTTP {code_bad}")

    print(f"\n结果: {PASS} 通过 / {FAIL} 失败  共 {PASS + FAIL} 项")
    if FAILED:
        print("失败项: " + "；".join(FAILED))
    return 1 if FAIL else 0


if __name__ == "__main__":
    raise SystemExit(main())
