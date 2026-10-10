"""对运行中的 FastAPI（默认 127.0.0.1:8000）做 /api/ui/* 全端点冒烟测试。

用法: python scripts/smoke_ui_api.py [base_url]
退出码非 0 表示有端点失败。
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"

# (路径, 断言关键字 -> 期望出现在响应里的片段)
CASES: list[tuple[str, list[str]]] = [
    ("/health", ['"status"']),
    ("/api/ui/public/summary", ["brand", "matches", "accuracy"]),
    ("/api/ui/home", ["matches", "topScorers", "focusMatch"]),
    ("/api/ui/admin", ["modules", "models", "dbTables"]),
    ("/api/ui/leagues", ["items"]),
    ("/api/ui/leagues/1", ["standings", "scorers", "scorersSeason"]),
    ("/api/ui/leagues/10?season=2526", ["scorersSeason"]),
    ("/api/ui/teams?sort=elo&size=5", ["items", "elo_rating"]),
    ("/api/ui/teams?q=Bayern", ["Bayern"]),
    ("/api/ui/players?sort=value&size=5", ["market_value"]),
    ("/api/ui/players?sort=name&size=5", ["items"]),
    ("/api/ui/players?sort=age&dir=asc&size=5", ["age"]),
    ("/api/ui/players?group=GK&size=5", ["group"]),
    ("/api/ui/players/1658", ["player", "seasons"]),
    ("/api/ui/matches?size=5", ["items", "stats"]),
    ("/api/ui/matches?status=FT&size=5", ["home_goals"]),
    ("/api/ui/matches/9012", ["prediction", "segments", "standing", "form", "h2h"]),
    ("/api/ui/matches/9107", ["stats", "home", "away"]),
    ("/api/ui/teams/38", ["metrics", "seasons", "recent", "upcoming", "squad", "squadGroups"]),
    ("/api/ui/teams/1", ["radar", "standing"]),
    ("/api/ui/predictions?size=5", ["calibration", "confusion", "hitRate"]),
    ("/api/ui/models", ["items", "featureImportance"]),
    ("/api/ui/transfers?size=5", ["transfer_fee"]),
    ("/api/ui/reports", ["tables", "months", "sources", "quality"]),
    ("/api/ui/live", ["recent", "upcoming"]),
    ("/api/ui/logo/52", ["svg", "png", "image"]),
    # 检索层（RAG 阶段 0）—— q 用 URL 编码的「皇家马德里」
    ("/api/ui/search?q=%E7%9A%87%E5%AE%B6%E9%A9%AC%E5%BE%B7%E9%87%8C&limit=3",
     ["hits", "source", "snippet", "tokens"]),
    ("/api/ui/search/stats", ["total", "by_kind", "mode"]),
    # 智能问答（RAG 阶段 1）—— q 用 URL 编码的「英超积分榜」, use_llm=false 不依赖 LLM key
    ("/api/ui/ask?q=%E8%8B%B1%E8%B6%85%E7%A7%AF%E5%88%86%E6%A6%9C&use_llm=false",
     ["answer", "mode", "sources", "timing", "intent"]),
    ("/api/ui/ask/status", ["llm_ready", "mode", "tools", "intents"]),
]


def main() -> int:
    import _uiauth

    # 服务器返回的数据里可能有 GBK 装不下的字符（球员名里的 ü/ö 之类），
    # Windows 控制台默认 GBK，print 会直接 UnicodeEncodeError 崩掉整个冒烟。
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):  # pragma: no cover - 老环境兜底
        pass

    hdrs = _uiauth.headers(_uiauth.login(base=BASE))
    fails: list[str] = []
    for path, needles in CASES:
        url = BASE + path
        try:
            req = urllib.request.Request(url, headers=hdrs)
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
                code = r.status
                ctype = r.headers.get("content-type", "")
        except urllib.error.HTTPError as e:  # 4xx/5xx
            fails.append(f"{path} -> HTTP {e.code}")
            print(f"[FAIL] {path:<44} HTTP {e.code}")
            continue
        except Exception as e:  # noqa: BLE001
            fails.append(f"{path} -> {e}")
            print(f"[FAIL] {path:<44} {e}")
            continue
        text = body.decode("utf-8", "replace")
        if path.endswith("/logo/52"):
            ok = code == 200 and ctype.startswith("image/")
        else:
            ok = code == 200 and all(n in text for n in needles)
        note = ""
        if ok and path.startswith("/api/ui/home"):
            d = json.loads(text)
            st = d.get("stats", {})
            note = f" · {st.get('matches')} 场 / 预测 {st.get('predictions')} / 准确率 {st.get('accuracy')}"
        if ok and path.startswith("/api/ui/leagues/1"):
            d = json.loads(text)
            note = f" · 榜首 {(d.get('scorers') or [{}])[0].get('player_name')} · 赛季 {(d.get('scorersSeason') or {}).get('label')}"
        print(f"[{'OK' if ok else 'FAIL'}] {path:<44} {code} {len(body):>7} B{note}")
        if not ok:
            fails.append(f"{path} -> 缺少关键字 {needles}")
    print("-" * 78)
    if fails:
        print(f"{len(fails)} 个端点失败:")
        for f in fails:
            print("  -", f)
        return 1
    print(f"全部 {len(CASES)} 个端点通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
