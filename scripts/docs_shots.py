# -*- coding: utf-8 -*-
"""生成 docs/webui/ 的交付截图（生产构建 + 已登录态，中文、亮色）。

用法:
    python scripts/docs_shots.py                 # 全部 22 张
    python scripts/docs_shots.py /ask /         # 只重拍指定路由

约定:
    * 除 /login 外都带登录态（/api/ui/* 现在需要 Bearer）。
    * 只拍视口 1600x1000（不拍 full_page），与历史交付截图规格一致。
    * 文件名即文档里的编号：01-登录.png … 22-账号设置.png
"""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uiauth  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "docs" / "webui"
BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:8000")  # 默认用生产构建（FastAPI 提供的 dist）
# 登录页 = 设计稿控制台那一版（docs/console/login.html，挂在 /console），看它要未登录态
PUBLIC = {"/console/login.html", "/console/register.html?next=%2F", "/console/forgot.html?next=%2F"}

SHOTS: list[tuple[str, str]] = [
    ("/console/login.html", "01-登录"),
    ("/", "02-首页概览"),
    ("/matches", "03-赛程与赛果"),
    ("/matches/9012", "04-比赛详情"),
    ("/matches/9107", "05-比赛详情-技术统计"),
    ("/leagues", "06-联赛数据"),
    ("/leagues/1", "07-联赛详情"),
    ("/teams", "08-球队分析"),
    ("/teams/38", "09-球队详情"),
    ("/players", "10-球员分析"),
    ("/players/1658", "11-球员详情"),
    ("/predictions", "12-比赛预测"),
    ("/live", "13-实时比分"),
    ("/admin?tab=overview", "14-管理端-数据总览"),
    ("/admin?tab=asset", "15-管理端-数据资产"),
    ("/admin?tab=models", "16-管理端-模型注册表"),
    ("/admin?tab=system", "17-管理端-系统与接口"),
    # 2026-10 新增：注册 / 忘记密码两页（同属控制台登录流程，排在最后避免打乱既有编号）
    ("/console/register.html?next=%2F", "18-注册账号"),
    ("/console/forgot.html?next=%2F", "19-忘记密码"),
    # 2026-10 新增：RAG 检索与问答
    ("/ask?q=%E7%9A%87%E5%AE%B6%E9%A9%AC%E5%BE%B7%E9%87%8C", "20-检索与问答"),
    ("/ask?tab=ask", "21-智能问答"),
    # 2026-10 新增：账号设置（顶栏头像 → 弹层；panel 参数只是本脚本的标记，页面会忽略）
    ("/?panel=account", "22-账号设置"),
]


ASK_TAB = "/ask?tab=ask"
ASK_QUESTION = "皇马和巴萨谁赢"
ACCOUNT_PANEL = "/?panel=account"


def _prepare(pg, route: str) -> None:
    """个别页面需要在截图前先操作一下才好看。

    * 问答页：空态截图没有信息量，先提交一个真实问题、等答案渲染完再拍
      （配了 LLM key 时就是模型作答的样子）。
    * 账号设置：它是顶栏头像里的弹层，得先点开头像 → 「账号设置」。
    """
    if route == ASK_TAB:
        box = pg.locator("textarea").first
        box.fill(ASK_QUESTION)
        box.press("Control+Enter")  # Ask.tsx 支持 Ctrl/⌘+Enter 提交
        for _ in range(75):  # 最多等 60 s：模型作答 2~4 s，截断重试时会翻倍
            pg.wait_for_timeout(800)
            body = pg.inner_text("body")
            if "Type a question and press Ask" not in body and "[1]" in body:
                break
        return
    if route == ACCOUNT_PANEL:
        pg.locator("header button:has(img[alt='avatar'])").first.click()
        pg.wait_for_timeout(500)
        pg.get_by_role("button", name=re.compile("账号设置|Account settings")).first.click()
        pg.wait_for_timeout(1200)  # 等弹层动画结束
        return


def main() -> int:
    want = [a for a in sys.argv[1:] if a.startswith("/")]
    jobs = [s for s in SHOTS if not want or s[0] in want]
    if not jobs:
        print("没有匹配的路由", want)
        return 1
    OUT.mkdir(parents=True, exist_ok=True)

    state = _uiauth.auth_state()
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        vp = {"width": 1600, "height": 1000}
        ctx_auth = b.new_context(viewport=vp, device_scale_factor=1)
        ctx_auth.add_init_script(_uiauth.init_script(state))
        ctx_pub = b.new_context(viewport=vp, device_scale_factor=1)
        ctx_pub.add_init_script("try{localStorage.removeItem('fauth')}catch(e){}")
        for route, name in jobs:
            ctx = ctx_pub if route in PUBLIC else ctx_auth
            pg = ctx.new_page()
            errs: list[str] = []
            pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
            pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)
            url = f"{BASE}{route}{'&' if '?' in route else '?'}lang=zh&theme=light"
            pg.goto(url, wait_until="load", timeout=60000)
            pg.wait_for_timeout(4500)
            _prepare(pg, route)
            info = pg.evaluate(
                """() => ({
                  broken: [...document.images].filter(i => i.complete && i.naturalWidth === 0 && (i.getAttribute('src') || '').trim() !== '').length,
                  overflow: document.documentElement.scrollWidth - window.innerWidth,
                  h1: (document.querySelector('h1')?.innerText || '').slice(0, 24),
                })"""
            )
            path = OUT / f"{name}.png"
            pg.screenshot(path=str(path), full_page=False)
            ok = not errs and not info["broken"] and info["overflow"] <= 1
            bad += 0 if ok else 1
            print(f"[{'OK' if ok else '! '}] {route:<22} -> {path.name:<26} h1={info['h1']!r} "
                  f"坏图={info['broken']} 溢出={info['overflow']} 错误={len(errs)}")
            if errs:
                print("     ", errs[:3])
            pg.close()
        b.close()
    print("-" * 90)
    print(f"{len(jobs) - bad}/{len(jobs)} 张已写入 {OUT}")
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main())
