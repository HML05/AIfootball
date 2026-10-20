"""React 前端（webui）+ /api/ui 的全量验收：11 条路由逐页体检 + 真实数据断言。

用法:
  python scripts/verify_webui.py                 # 全部路由
  python scripts/verify_webui.py / /teams        # 指定路由
  python scripts/verify_webui.py --base http://127.0.0.1:3000

每页检查: console/pageerror 为空、无坏图、无横向溢出、骨架已消失、
文本里出现该页应有的真实数据标记（正则）。截图存 %TEMP%\\aifootball_view\\verify\\。
退出码: 0 全部通过，1 有失败项。
"""
from __future__ import annotations

import argparse
import os
import re
import sys
from pathlib import Path

BASE_DEFAULT = "http://127.0.0.1:3000"

# 路由 -> (页面中文名, 必须出现的真实数据标记正则)
# 不需要登录的路由（未登录态验收，不注入 token）
# 登录页是设计稿控制台那一版（docs/console/login.html，后端挂在 /console），不在 SPA 路由里
PUBLIC_ROUTES = {"/console/login.html"}

ROUTES: list[tuple[str, str, str]] = [
    ("/console/login.html", "登录页（未登录 · 控制台版）", r"MATCHDAY|Sign in|登录"),
    ("/", "首页概览", r"12,698"),
    ("/matches", "赛程与赛果", r"12,698|11,315"),
    ("/matches/9012", "比赛详情（未开赛有预测）", r"46\.8|Santander"),
    ("/matches/9107", "比赛详情（已完赛有技术统计）", r"2\.87|0\.88|2"),
    ("/leagues", "联赛数据", r"12,698|2,003"),
    ("/leagues/1", "联赛详情", r"Arsenal|1,973"),
    ("/teams", "球队分析", r"1890\.9|Bayern"),
    ("/teams/38", "球队详情", r"Elche|Elche CF"),
    ("/players", "球员分析", r"4,745|200M€"),
    ("/players/1658", "球员详情", r"拉明|Lamine|1658"),
    ("/predictions", "比赛预测", r"1,803|53\.5|50\.14"),
    ("/live", "实时比分", r"2026-09-12|Sevilla"),
    ("/ask?q=皇家马德里", "检索与问答 · 全文检索", r"518|皇家马德里|jieba"),
    ("/ask?tab=ask", "检索与问答 · 智能问答", r"智能问答|Ask the assistant"),
    ("/admin?tab=overview", "管理端 · 数据总览", r"12,698|90\.1"),
    ("/admin?tab=asset", "管理端 · 数据资产", r"1\.8M|36"),
    ("/admin?tab=models", "管理端 · 模型注册表", r"v9|50\.14"),
    ("/admin?tab=system", "管理端 · 系统与接口", r"12\.7k|901\.4k"),
    ("/vision", "视频分析（视觉模块）", r"视频分析|Video analysis"),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("routes", nargs="*", help="要检查的路由（默认全部）")
    ap.add_argument("--base", default=BASE_DEFAULT)
    ap.add_argument("--lang", default="zh")
    ap.add_argument("--width", type=int, default=1600)
    ap.add_argument("--height", type=int, default=1000)
    args = ap.parse_args()

    from playwright.sync_api import sync_playwright

    import _uiauth

    out_dir = Path(os.environ.get("TEMP", ".")) / "aifootball_view" / "verify"
    out_dir.mkdir(parents=True, exist_ok=True)

    targets = [r for r in ROUTES if not args.routes or r[0] in args.routes]
    if not targets:
        print("没有匹配的路由:", args.routes)
        return 1

    rows: list[tuple[str, str, str, str]] = []
    failed = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = _uiauth.new_context(browser, viewport={"width": args.width, "height": args.height})
        ctx_public = browser.new_context(viewport={"width": args.width, "height": args.height})
        for path, label, pattern in targets:
            pg = (ctx_public if path in PUBLIC_ROUTES else ctx).new_page()
            errors: list[str] = []
            pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            pg.on("console", lambda m: errors.append(f"console.{m.type}: {m.text}") if m.type == "error" else None)
            url = f"{args.base}{path}" + ("?lang=en" if args.lang == "en" else "")
            try:
                pg.goto(url, wait_until="load", timeout=60000)
                pg.wait_for_timeout(4200)
                info = pg.evaluate(
                    """() => {
                        const txt = document.body.innerText || '';
                        const imgs = [...document.images];
                        // 空 src 的占位图（如控制台登录页未展开的二维码）不算坏图
                        const broken = imgs.filter(i => i.complete && i.naturalWidth === 0
                            && (i.getAttribute('src') || '').trim() !== '').length;
                        const overflow = document.documentElement.scrollWidth - window.innerWidth;
                        const skeletons = document.querySelectorAll('.skeleton').length;
                        return { text: txt, imgs: imgs.length, broken, overflow, skeletons,
                                 docH: document.documentElement.scrollHeight };
                    }"""
                )
            except Exception as e:  # noqa: BLE001
                rows.append((path, label, "失败", f"加载异常: {e}"))
                failed += 1
                pg.close()
                continue
            shot = out_dir / (re.sub(r"[^a-z0-9]+", "_", path.lower()).strip("_") or "home")
            pg.screenshot(path=str(shot) + ".png", full_page=False)
            hit = re.search(pattern, info["text"]) is not None
            problems: list[str] = []
            if errors:
                problems.append(f"{len(errors)} 个控制台错误: {errors[0][:110]}")
            if info["broken"]:
                problems.append(f"{info['broken']} 张坏图")
            if info["overflow"] > 1:
                problems.append(f"横向溢出 {info['overflow']}px")
            if info["skeletons"]:
                problems.append(f"残留骨架 {info['skeletons']}")
            if not hit:
                problems.append(f"未见真实数据标记 /{pattern}/")
            if problems:
                failed += 1
                rows.append((path, label, "失败", "; ".join(problems)))
            else:
                rows.append(
                    (path, label, "通过",
                     f"{info['text'].strip().splitlines()[0][:26] if info['text'].strip() else ''} · 图 {info['imgs']} · 高 {info['docH']}")
                )
            pg.close()
        browser.close()

    width = max(len(r[0]) for r in rows)
    print(f"{'路由'.ljust(width)}  结果  说明")
    print("-" * 100)
    for path, label, status, note in rows:
        print(f"{path.ljust(width)}  {status}  {label} · {note}")
    print("-" * 100)
    print(f"截图目录: {out_dir}")
    if failed:
        print(f"{failed}/{len(rows)} 个页面未通过")
        return 1
    print(f"全部 {len(rows)} 个页面通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
