"""问题路由 —— 把中文自然语言问题拆成「意图 + 实体 + 工具调用计划」。

为什么用规则而不是模型:
  * 零依赖、可单测、可解释（前端能把「为什么调这个工具」显示出来）;
  * 项目里没有 LLM key 时也要能跑（阶段 1 的编排在无 key 时退化为检索摘要）;
  * 实体识别靠全量名字 + 中文别名表做最长匹配, 不猜。

意图 → 工具计划:
  predict     「皇马和巴萨谁赢」      → match_prediction + head_to_head + 两队近期战绩
  h2h         「两队历史交锋」        → head_to_head + 两队近期战绩
  form        「曼城最近状态」        → team_form
  team        「利物浦主教练是谁」    → team_info + team_form
  player      「凯帕身价多少」        → player_info
  standings   「英超积分榜」          → league_table
  search      其它 / 纯关键词         → 只走全文检索
"""
from __future__ import annotations

import re
from typing import Any

from src.qa import tools as T

# ---------------------------------------------------------------- 关键词表

KEYWORDS: dict[str, tuple[str, ...]] = {
    "predict": ("预测", "胜率", "概率", "谁赢", "谁会赢", "谁会胜", "能赢", "胜算", "赢面", "看好谁",
                "谁会", "结果会", "分析一下", "predict", "win probability"),
    "h2h": ("交锋", "交手", "对阵", "历史战绩", "过往", "碰面", "相遇", "直接对话", "互相", "head to head", "h2h"),
    "form": ("近况", "状态", "最近", "近期", "战绩", "走势", "连胜", "连败", "不败", "连续", "几场", "最近几场",
             "form", "recent"),
    "standings": ("积分榜", "排名", "榜首", "第几", "领跑", "降级", "争四", "夺冠", "联赛榜", "standings", "table"),
    "player": ("球员", "身价", "进球", "助攻", "位置", "年龄", "身高", "出场", "数据", "谁是最", "射手"),
    "team": ("球队", "主教练", "主帅", "教练", "主场", "球场", "阵容", "成立", "老板", "队徽", "资料"),
}

# 停用词里的「球队名」干扰项: 这些短词会被误当成队名（库里确实有同名队）
_STOP_SURFACES = {"ac", "sc", "fc", "as", "us", "if", "bk", "cd", "cp", "ca", "sv", "sk"}


def _hit_keywords(text: str) -> list[str]:
    low = text.lower()
    return [intent for intent, words in KEYWORDS.items() if any(w in low for w in words)]


# ---------------------------------------------------------------- 实体识别

_TEAM_SURFACES: list[tuple[str, int]] | None = None
_PLAYER_SURFACES: list[tuple[str, int]] | None = None
_LEAGUE_SURFACES: list[tuple[str, int]] | None = None


def _usable(s: Any) -> bool:
    s = str(s or "").strip()
    if len(s) < 2:
        return False
    if s.lower() in _STOP_SURFACES:
        return False
    ascii_only = bool(re.fullmatch(r"[A-Za-z0-9 .'\-]+", s))
    return len(s) >= 4 if ascii_only else True


def team_surfaces() -> list[tuple[str, int]]:
    global _TEAM_SURFACES
    if _TEAM_SURFACES is None:
        out: list[tuple[str, int]] = []
        for t in T.teams_index():
            for n in [t.get("name"), t.get("name_en"), t.get("short_name"), *(t.get("alias") or [])]:
                if _usable(n):
                    out.append((str(n).strip(), t["team_id"]))
        _TEAM_SURFACES = sorted(set(out), key=lambda x: -len(x[0]))
    return _TEAM_SURFACES


def player_surfaces() -> list[tuple[str, int]]:
    global _PLAYER_SURFACES
    if _PLAYER_SURFACES is None:
        out: list[tuple[str, int]] = []
        for p in T.players_index():
            for n in (p.get("name"), p.get("name_en")):
                if _usable(n):
                    out.append((str(n).strip(), p["player_id"]))
        _PLAYER_SURFACES = sorted(set(out), key=lambda x: -len(x[0]))
    return _PLAYER_SURFACES


def league_surfaces() -> list[tuple[str, int]]:
    global _LEAGUE_SURFACES
    if _LEAGUE_SURFACES is None:
        out: list[tuple[str, int]] = []
        for lg in T.leagues_index():
            for n in (lg.get("name"), lg.get("name_en")):
                if _usable(n):
                    out.append((str(n).strip(), lg["league_id"]))
        _LEAGUE_SURFACES = sorted(set(out), key=lambda x: -len(x[0]))
    return _LEAGUE_SURFACES


def _find_in(question: str, surfaces: list[tuple[str, int]], limit: int) -> list[int]:
    """在问题里找出现的名字（长名字优先, 取前 limit 个不同 id）。"""
    low = question.lower()
    hits: list[tuple[int, int, int]] = []  # (位置, -长度, id) —— 位置靠前、名字更长者优先
    for surface, ident in surfaces:
        s = surface.lower()
        pos = low.find(s)
        if pos >= 0 and s not in _STOP_SURFACES:
            hits.append((pos, -len(s), ident))
    hits.sort()
    ids: list[int] = []
    for _, _, ident in hits:
        if ident not in ids:
            ids.append(ident)
        if len(ids) >= limit:
            break
    return ids


def extract(question: str) -> dict:
    """识别问题里的球队 / 球员 / 联赛（返回完整记录, 便于直接喂给工具）。"""
    q = question or ""
    team_ids = _find_in(q, team_surfaces(), 2)
    player_ids = _find_in(q, player_surfaces(), 1)
    league_ids = _find_in(q, league_surfaces(), 1)
    teams = [t for t in (T.find_team(i) for i in team_ids) if t]
    player = T.find_player(player_ids[0]) if player_ids else None
    league = T.find_league(league_ids[0]) if league_ids else None
    return {"teams": teams, "player": player, "league": league}


# 疑问词/虚词：全文检索时去掉, 否则「多少」「谁」这类词会命中几千条无关记录
FILLER: tuple[str, ...] = (
    "请问", "帮我", "帮忙", "告诉我", "查一下", "看一下", "看看", "一下",
    "怎么样", "如何", "是不是", "能不能", "可不可以", "有没有",
    "什么", "多少", "哪个", "哪些", "哪位", "哪支", "哪只", "哪里", "怎么", "为什么",
    "最近", "近期", "现在", "目前", "这场", "这", "那", "我", "你", "他", "她", "它",
    "和", "与", "及", "跟", "的", "了", "吗", "呢", "啊", "是", "在", "有", "会", "要", "能", "都", "还", "谁",
)


def search_query(question: str, entities: dict | None = None) -> str:
    """给全文检索用的查询串: 问题去掉疑问词/虚词, 再拼上识别到的实体名。

    例:「皇马和巴萨谁赢」→「皇马 巴萨 Real Madrid Barcelona」——检索不再被「谁」稀释。
    """
    s = str(question or "")
    for w in FILLER:
        s = s.replace(w, " ")
    names: list[str] = []
    ent = entities or {}
    for t in ent.get("teams") or []:
        alias = t.get("alias") or []
        names.append(alias[0] if alias else (t.get("name") or ""))
    p = ent.get("player") or {}
    if p:
        names.append(p.get("name") or p.get("name_en") or "")
    lg = ent.get("league") or {}
    if lg:
        names.append(lg.get("name") or "")
    out = " ".join([s.strip()] + [n for n in names if n]).strip()
    return out or str(question or "").strip()


# ---------------------------------------------------------------- 计划


def plan(question: str) -> dict:
    """返回 {intent, keywords, entities, steps}；steps 里每步都有理由, 前端会展示。"""
    q = (question or "").strip()
    kws = _hit_keywords(q)
    ent = extract(q)
    teams, player, league = ent["teams"], ent["player"], ent["league"]
    steps: list[dict] = []

    def add(tool: str, args: list[Any], reason: str) -> None:
        steps.append({"tool": tool, "args": args, "reason": reason})

    if len(teams) >= 2:
        a, b = teams[0], teams[1]
        if "predict" in kws:
            intent = "predict"
            add("match_prediction", [a["name"], b["name"]], "问题里有两支球队且问了胜负/概率 → 查库里已落库的模型预测")
            add("head_to_head", [a["name"], b["name"]], "预测需要交锋背景 → 查两队历史交锋")
            add("team_form", [a["name"]], f"补充 {a['name']} 近期状态")
            add("team_form", [b["name"]], f"补充 {b['name']} 近期状态")
        elif "h2h" in kws:
            intent = "h2h"
            add("head_to_head", [a["name"], b["name"]], "问的是两队交锋 → 查历史交锋记录")
            add("team_form", [a["name"]], f"补充 {a['name']} 近期状态")
            add("team_form", [b["name"]], f"补充 {b['name']} 近期状态")
        else:
            intent = "compare"
            add("head_to_head", [a["name"], b["name"]], "问题提到两支球队 → 直接对比交锋记录")
            add("team_info", [a["name"]], f"给出 {a['name']} 的基本面")
            add("team_info", [b["name"]], f"给出 {b['name']} 的基本面")
            add("team_form", [a["name"]], f"给出 {a['name']} 的近期战绩")
            add("team_form", [b["name"]], f"给出 {b['name']} 的近期战绩")
    elif player and ("player" in kws or not teams):
        intent = "player"
        add("player_info", [player["name"]], "问题里识别到球员 → 查球员资料与赛季数据")
    elif league and "standings" in kws:
        intent = "standings"
        add("league_table", [league["name"], 10], "问题问积分榜/排名 → 查该联赛最新赛季积分榜")
    elif teams and "standings" in kws:
        intent = "standings"
        add("team_info", [teams[0]["name"]], f"问题提到 {teams[0]['name']} 的排名 → 先取该队资料（含最近赛季名次）")
        if league:
            add("league_table", [league["name"], 10], "同时给出所属联赛积分榜")
    elif teams and "form" in kws:
        intent = "form"
        add("team_form", [teams[0]["name"], 6], "问的是近期状态 → 查最近比赛战绩")
        add("team_info", [teams[0]["name"]], "补充球队基本面")
    elif teams:
        intent = "team"
        add("team_info", [teams[0]["name"]], "问题提到球队 → 查球队资料")
        add("team_form", [teams[0]["name"]], "顺带给出近期战绩")
    elif league:
        intent = "standings"
        add("league_table", [league["name"], 10], "问题只提到联赛 → 给出积分榜")
    else:
        intent = "search"

    return {"intent": intent, "keywords": kws, "entities": ent, "steps": steps}


def run_plan(p: dict) -> list[dict]:
    """执行计划里的工具调用（单个工具失败不影响其它）。"""
    out: list[dict] = []
    for step in p.get("steps", []):
        fn = T.TOOLS.get(step["tool"])
        if not fn:
            continue
        try:
            res = fn(*step["args"])
        except Exception as e:  # 单个工具异常不该让整个问答挂掉
            res = {"tool": step["tool"], "ok": False, "summary": f"工具执行失败: {e}", "data": {}, "sources": []}
        res["reason"] = step.get("reason", "")
        res["args"] = step.get("args", [])
        out.append(res)
    return out
