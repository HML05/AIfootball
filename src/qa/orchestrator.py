"""问答编排 —— 意图 → 工具/检索 → 生成 → 带引用的答案。

流程（见 docs/智能问答说明.md）:
  1. router.plan(question)            规则式意图识别 + 实体识别 → 工具调用计划
  2. router.run_plan(plan)            执行工具（只读主库, 数字全部来自库里）
  3. search(question)                 全文检索（FTS5 + jieba, RAG 阶段 0）补充证据
  4. llm.chat(...)                    有 LLM_API_KEY 时生成答案; 没有则退化为「检索摘要」
  5. 组装 sources                     每条事实/片段都有 表名 + 主键 + 前端可跳转路由

诚实原则: 没配 key 就明确说「检索摘要模式」; 工具没查到就写「库里没有」, 不用模型编。
"""
from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.qa import llm
from src.qa import router as R
from src.qa import tools as T
from src.search.query import IndexMissing
from src.search.query import search as search_index

SYSTEM_PROMPT = """你是 FootballAI 的数据问答助手。你只能依据下面给出的【工具事实】和【检索片段】回答。

硬性要求:
1. 数字（比分、概率、积分、身价、排名、日期）必须逐字来自上面给的材料, 不许自己算、不许估、不许编。
2. 每用到一条材料, 就在那句话末尾标出它的编号, 例如 [1][3]。
3. 材料里没有的信息, 直接说「库内没有相关记录」, 并说明还缺什么（例如"需要 XX 球员的赛季数据"）。
4. 回答用简体中文, 先给结论, 再列 1~3 条依据, 总长控制在 200 字以内; 不要复述这份说明。
5. 不要提"工具""材料""prompt"等字眼, 直接给结论。"""


def collect_sources(tool_results: list[dict], hits: list[dict]) -> list[dict]:
    """把工具来源与检索命中合并成带编号的引用表（同一「表+主键」只出现一次）。"""
    out: list[dict] = []
    seen: set[tuple] = set()

    def push(table: str, ident: Any, label: str, url: str | None, ref: str | None, via: str) -> None:
        key = (table, str(ident))
        if key in seen:
            return
        seen.add(key)
        out.append({"n": len(out) + 1, "table": table, "id": ident, "label": label,
                    "url": url, "ref": ref, "via": via})

    for res in tool_results:
        if not res.get("ok"):
            continue
        for s in res.get("sources") or []:
            push(s.get("table") or "?", s.get("id"), s.get("label") or "", s.get("url"), s.get("ref"),
                 f"工具:{res.get('tool')}")
    for h in hits:
        src = h.get("source") or {}
        push(src.get("table") or "?", src.get("id"), h.get("title") or "", src.get("url"), src.get("ref") or h.get("ref"),
             "检索")
    return out


def build_context(tool_results: list[dict], hits: list[dict], sources: list[dict]) -> str:
    """把事实拼成给模型看的材料（编号与 sources 一致）。"""
    idx = {(s["table"], str(s["id"])): s["n"] for s in sources}
    lines: list[str] = ["【工具事实】"]
    any_fact = False
    for res in tool_results:
        head = f"[{'/'.join(str(idx.get((s.get('table') or '?', str(s.get('id'))), '?')) for s in (res.get('sources') or [])[:1])}]"
        if not res.get("ok"):
            lines.append(f"{head} ({res.get('tool')}) 未查到: {res.get('summary')}")
            continue
        any_fact = True
        lines.append(f"{head} ({res.get('tool')}) {res.get('summary')}")
    if not any_fact:
        lines.append("（没有可用的结构化事实）")

    lines.append("\n【检索片段】")
    if hits:
        for h in hits:
            n = idx.get(((h.get("source") or {}).get("table"), str((h.get("source") or {}).get("id"))), "?")
            lines.append(f"[{n}] ({h.get('kind_label')}) {h.get('title')} — {h.get('snippet')}")
    else:
        lines.append("（检索没有命中）")
    return "\n".join(lines)


def digest_answer(question: str, tool_results: list[dict], hits: list[dict], sources: list[dict]) -> str:
    """没有 LLM 时的降级答案: 直接汇总库内事实 + 相关记录, 不生成任何新数字。"""
    blocks: list[str] = []
    for res in tool_results:
        if res.get("ok"):
            blocks.append(f"· {res.get('summary')}")
        else:
            blocks.append(f"· （{res.get('tool')}）{res.get('summary')}")
    if not blocks:
        blocks.append("· 结构化工具没有命中, 下面是全文检索的相关记录。")
    if hits:
        blocks.append("\n相关记录:")
        idx = {(s["table"], str(s["id"])): s["n"] for s in sources}
        for h in hits[:5]:
            n = idx.get(((h.get("source") or {}).get("table"), str((h.get("source") or {}).get("id"))), "?")
            blocks.append(f"[{n}] ({h.get('kind_label')}) {h.get('title')} — {h.get('snippet')}")
    return "\n".join(blocks)


def ask(question: str, top_k: int = 5, use_llm: bool = True, kind: str | None = None) -> dict[str, Any]:
    """一次问答。返回结构供 /api/ui/ask 直接序列化（见 docs/智能问答说明.md）。"""
    q = (question or "").strip()
    t0 = time.time()
    if not q:
        return {"question": q, "mode": "empty", "answer": "请输入一个问题，例如「皇马和巴萨谁赢」「英超积分榜」。",
                "plan": None, "facts": [], "sources": [], "search": None, "missing": ["问题为空"],
                "elapsed_ms": 0, "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S")}

    missing: list[str] = []

    # 1~2. 计划 + 工具
    plan = R.plan(q)
    t_tools = time.time()
    tool_results = R.run_plan(plan)
    tools_ms = int((time.time() - t_tools) * 1000)

    # 3. 全文检索（用去掉疑问词、拼上实体的查询串, 避免「多少」「谁」稀释结果）
    sq = R.search_query(q, plan.get("entities"))
    t_search = time.time()
    try:
        sr = search_index(sq, kind=kind, limit=max(1, min(int(top_k or 5), 20)))
    except IndexMissing as e:
        sr = {"query": sq, "hits": [], "count": 0, "tokens": [], "mode": "", "kinds": []}
        missing.append(f"检索索引不可用（{e}）：先运行 python scripts/build_search_index.py")
    search_ms = int((time.time() - t_search) * 1000)
    hits = sr.get("hits") or []

    sources = collect_sources(tool_results, hits)
    context = build_context(tool_results, hits, sources)

    # 4. 生成
    mode = "retrieval"
    answer = ""
    llm_info: dict[str, Any] = {"ok": False, "model": None, "error": None, "usage": None, "elapsed_ms": 0}
    if use_llm and llm.ready():
        t_llm = time.time()
        out = llm.chat([
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": f"问题: {q}\n\n{context}"},
        ])
        llm_info = {"ok": out.get("ok"), "model": out.get("model"), "error": out.get("error"),
                    "usage": out.get("usage"), "elapsed_ms": out.get("elapsed_ms")}
        if out.get("ok"):
            mode, answer = "llm", out["text"]
        else:
            missing.append(f"大模型调用失败（{out.get('error')}），已降级为检索摘要")
            answer = digest_answer(q, tool_results, hits, sources)
        _ = t_llm
    else:
        if use_llm and not llm.ready():
            missing.append("未配置 LLM_API_KEY：当前是「检索摘要」模式（库内事实 + 检索片段）, 在 .env 里填 key 后自动切到大模型作答")
        answer = digest_answer(q, tool_results, hits, sources)

    elapsed = int((time.time() - t0) * 1000)
    return {
        "question": q,
        "mode": mode,                      # llm | retrieval
        "answer": answer,
        "intent": plan.get("intent"),
        "plan": {"intent": plan.get("intent"), "keywords": plan.get("keywords"),
                 "steps": plan.get("steps"), "entities": {
                     "teams": [t.get("name") for t in (plan.get("entities") or {}).get("teams") or []],
                     "player": ((plan.get("entities") or {}).get("player") or {}).get("name"),
                     "league": ((plan.get("entities") or {}).get("league") or {}).get("name"),
                 }},
        "facts": [{k: v for k, v in r.items() if k != "sources"} for r in tool_results],
        "sources": sources,
        "search": {"query": sq, "count": sr.get("count"), "tokens": sr.get("tokens"), "mode": sr.get("mode"),
                   "operator": sr.get("operator"), "hits": hits},
        "missing": missing,
        "timing": {"tools_ms": tools_ms, "search_ms": search_ms,
                   "llm_ms": llm_info.get("elapsed_ms") or 0, "total_ms": elapsed},
        "llm": llm_info,
        "elapsed_ms": elapsed,
        "generatedAt": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    }


def status() -> dict[str, Any]:
    """给前端与自检脚本看的能力状态（不触发任何外部调用）。"""
    return {
        "llm_ready": llm.ready(),
        "llm_model": llm.model_name(),
        "llm_endpoint": llm.endpoint(),
        "mode": "llm" if llm.ready() else "retrieval",
        "mode_desc": "已配置 LLM_API_KEY，走大模型作答" if llm.ready()
                     else "未配置 LLM_API_KEY，返回「库内事实 + 检索片段」的检索摘要",
        "intents": sorted(R.KEYWORDS.keys()),
        "tools": T.describe(),
        "alias_teams": len(T.teams_index()),
        "players_indexed": len(T.players_index()),
        "leagues_indexed": len(T.leagues_index()),
    }
