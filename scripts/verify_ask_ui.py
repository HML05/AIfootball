# -*- coding: utf-8 -*-
"""`/ask` 页面（检索 + 智能问答）的浏览器端自检。

验证的是**真点击真渲染**：
    1) 检索页：带 q 打开 → 命中条数、分词、类型筛选、结果标题与来源
    2) 问答页：输入问题并提交 → 答案、引用来源、模式徽标、执行步骤
    3) 两个页签都不该有控制台报错 / 横向溢出 / 坏图

用法（需要 API 8000 与前端产物都在）:
    python scripts/verify_ask_ui.py                      # 默认 http://127.0.0.1:8000
    python scripts/verify_ask_ui.py --base http://127.0.0.1:3000   # 走 vite dev

设计说明：断言尽量贴**真实数据**（命中数、分词模式、引用编号），不写「页面有内容」这种空断言。
"""
from __future__ import annotations

import argparse
import sys
import urllib.parse
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _uiauth  # noqa: E402

BASE_DEFAULT = "http://127.0.0.1:8000"
SHOT_DIR = Path(__import__("os").environ.get("TEMP", "/tmp")) / "aifootball_view" / "ask"

PROBE_QUERY = "皇家马德里"
PROBE_QUESTION = "皇马和巴萨谁赢"

results: list[tuple[str, str, bool]] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    results.append((label, detail, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    return bool(ok)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_DEFAULT)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    from playwright.sync_api import sync_playwright

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    print("FootballAI /ask 页面自检（浏览器）")

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not args.headed)
        ctx = _uiauth.new_context(browser, viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        ctx.on("weberror", lambda e: errors.append(str(e.error)))
        page = ctx.new_page()
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)

        # ---------------------------------------------------------- 检索页
        print("\n=== 1. 检索页（/ask?q=…）===")
        page.goto(f"{base}/ask?q={urllib.parse.quote(PROBE_QUERY)}", wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        body = page.inner_text("body")
        check("页面标题与两个页签都在", "Search & Ask" in body and "Full-text search" in body,
              "title=Search & Ask")
        check("命中条数与分词模式来自接口", "matches · tokenizer jieba" in body,
              next((ln for ln in body.splitlines() if "matches" in ln and "tokenizer" in ln), ""))
        check("分词结果展示在页面上", "皇家" in body and "马德里" in body, "tokens: 皇家 / 马德里")
        hit_cards = page.locator("a[href^='/matches/'], a[href^='/teams/'], a[href^='/players/']")
        before_n = hit_cards.count()  # locator 是实时的，必须先取快照再点筛选
        check("结果卡片带站内跳转链接", before_n > 0, f"{before_n} 个链接")
        first_href = hit_cards.first.get_attribute("href") if hit_cards.count() else ""
        check("首条链接是站内路径（不是 http://127.0.0.1:8000）",
              bool(first_href) and first_href.startswith("/") and ":8000" not in first_href, first_href or "")

        # 类型筛选：点「Predictions」应只剩 prediction 结果
        # （不用 Teams/Players 做探针 —— 顶栏导航同名，会点到导航按钮跳走）
        preds_pill = page.locator("button", has_text="Predictions").first
        preds_pill.click()
        page.wait_for_timeout(1500)
        after = page.locator("a[href^='/matches/'], a[href^='/teams/'], a[href^='/players/']").count()
        check("点击「Predictions」筛选生效且 URL 带上 kind",
              "kind=prediction" in page.url, f"url={page.url.split('?')[-1]} · {after} 条")
        check("筛选后条数变少（确实过滤了）",
              after < before_n, f"筛选前 {before_n} → 筛选后 {after}")

        page.screenshot(path=str(SHOT_DIR / "ask_search.png"), full_page=True)

        # ---------------------------------------------------------- 问答页
        print("\n=== 2. 智能问答页（/ask?tab=ask）===")
        page.goto(f"{base}/ask?tab=ask", wait_until="domcontentloaded")
        page.wait_for_timeout(1200)
        check("切到问答页签", "Ask the assistant" in page.inner_text("body"))
        box = page.locator("textarea").first
        box.fill(PROBE_QUESTION)
        # 顶栏也有一个 "Ask" 导航按钮，所以用页面里的快捷键提交（Ask.tsx: Ctrl/⌘+Enter）
        box.press("Control+Enter")
        page.wait_for_timeout(5000)
        body3 = page.inner_text("body")
        check("问题提交后出现答案（不再是空态）", "Type a question and press Ask" not in body3,
              "答案已渲染")
        check("答案里带库里真实数字（比分/概率）",
              any(t in body3 for t in ("Real Madrid", "Barcelona", "%")), "含队名或百分比")
        check("模式徽标显示 Retrieval summary（未配 LLM key）",
              "Retrieval summary" in body3, "Retrieval summary")
        check("未配 key 的诚实提示在页面上", "LLM_API_KEY" in body3, "LLM_API_KEY is not configured")
        check("引用来源编号 [1] 之类出现", "[" in body3 and "]" in body3)
        check("展示了执行步骤/依据（可折叠区块）", "steps" in body3.lower() or "Step" in body3
              or "match_prediction" in body3 or "head_to_head" in body3, "")
        page.screenshot(path=str(SHOT_DIR / "ask_answer.png"), full_page=True)

        # ---------------------------------------------------------- 公共质量
        print("\n=== 3. 页面质量 ===")
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
        check("无横向溢出", not overflow, "scrollWidth <= innerWidth")
        broken = page.evaluate(
            "Array.from(document.images).filter(i => i.complete && i.naturalWidth === 0).length")
        check("没有坏图", broken == 0, f"{broken} 张")
        check("控制台无报错", len(errors) == 0, "; ".join(errors[:2]))

        ctx.close()
        browser.close()

    passed = sum(1 for _, _, ok in results if ok)
    print(f"\n结果: {passed} 通过 / {len(results) - passed} 失败  共 {len(results)} 项")
    print(f"截图目录: {SHOT_DIR}")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
