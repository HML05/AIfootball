# -*- coding: utf-8 -*-
"""登录流程端到端验收（Playwright，真实点击）。

登录页用的是设计稿控制台那一版（docs/console/login.html，后端挂在 /console），
本 SPA 不再自带登录页：未登录时整页跳到 /console/login.html?next=<原地址>，
两边同源、共用 localStorage.fauth，登录后跳回原地址。

覆盖:
  1. 未登录访问 / → 被送到 /console/login.html 且带上 next=原地址
  2. 登录表单可见（账号 / 密码 / 登录按钮）
  3. 填错密码 → 页面内提示，仍停在登录页
  4. 正确账号 → 自动跳回 / → 首页出现真实数据，localStorage.fauth 有 token
  5. 已登录再访问登录页 → 显示「继续进入」而不是表单
  6. 顶栏头像菜单 → 退出登录 → 回到登录页且 fauth 已清
  7. 非管理员（拦截 /api/auth/me 返回 user 角色）→ /admin 显示权限卡 + 「换管理员账号登录」（带 why=role）
  8. 全程无控制台错误

用法: python scripts/_login_flow.py            # 默认 http://127.0.0.1:8000（生产构建）
      WEBUI_BASE=http://127.0.0.1:3000 python scripts/_login_flow.py
输出截图: %TEMP%\\aifootball_view\\webui\\flow_*.png
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uiauth  # noqa: E402

BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:8000")
OUT = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view" / "webui"
OUT.mkdir(parents=True, exist_ok=True)

LOGIN_PATH = "/console/login.html"
ADMIN = ("admin", "football2026")

# 生产（8000 直接提供 dist）时登录页与 SPA 同源；开发（3000 是 Vite）时登录页仍由 8000 提供，
# 于是「已登录时登录页给继续进入」这条同源才成立的行为在开发模式下跳过。
SAME_ORIGIN = ":3000" not in BASE
CONSOLE_BASE = BASE if SAME_ORIGIN else "http://127.0.0.1:8000"

results: list[tuple[str, bool, str]] = []


def check(name: str, ok: bool, note: str = "") -> None:
    results.append((name, ok, note))
    print(f"[{'PASS' if ok else 'FAIL'}] {name}{(' — ' + note) if note else ''}")


def text_of(pg) -> str:
    return (pg.inner_text("body") or "").replace("\n", " ")


def new_ctx(b, *, logged_in: bool = False):
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    # 注意: add_init_script 每次导航都会执行 —— 清 fauth 必须做成「每标签页只清一次」，
    # 否则登录成功后跳回首页时又被清掉，看起来像「登录跳转失败」（其实是被测试脚本清空的）。
    ctx.add_init_script(
        "try{localStorage.setItem('talvex-lang','zh');"
        "if(!sessionStorage.getItem('fa_cleared')){localStorage.removeItem('fauth');"
        "sessionStorage.setItem('fa_cleared','1')}}catch(e){}"
    )
    if logged_in:
        ctx.add_init_script(_uiauth.init_script())
    return ctx


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = new_ctx(b)
        pg = ctx.new_page()
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)

        # 1. 未登录 → 整页跳到控制台登录页，带 next
        pg.goto(f"{BASE}/?lang=zh", wait_until="load", timeout=45000)
        pg.wait_for_timeout(2500)
        check("未登录访问 / 被送到控制台登录页", LOGIN_PATH in pg.url, f"url={pg.url}")
        check("回跳地址 next 带上原页面", "next=" in pg.url and ("%2F" in pg.url or "/" in pg.url.split("next=")[-1]), pg.url)
        check("登录页表单可见（#panePw / #gUser / #gPwd）",
              pg.locator("#panePw").count() == 1 and pg.locator("#gUser").count() == 1
              and pg.locator("#gPwd").count() == 1,
              f"panePw={pg.locator('#panePw').count()}")
        pg.screenshot(path=str(OUT / "flow_1_guard.png"))

        # 2. 错密码
        pg.fill("#gUser", ADMIN[0])
        pg.fill("#gPwd", "definitely-wrong")
        pg.click("#gLogin")
        pg.wait_for_timeout(2500)
        msg = (pg.inner_text("#gMsg") or "").strip()
        check("错误密码提示留在登录页", LOGIN_PATH in pg.url and len(msg) > 0, f"msg={msg[:40]}")
        pg.screenshot(path=str(OUT / "flow_2_badpwd.png"))

        # 3. 正确账号 → 自动跳回 /
        pg.fill("#gPwd", ADMIN[1])
        pg.click("#gLogin")
        try:
            pg.wait_for_url(lambda u: LOGIN_PATH not in u, timeout=20000)
        except Exception as e:  # noqa: BLE001
            check("登录后自动跳回原地址", False, str(e)[:60])
        pg.wait_for_timeout(3500)
        check("登录后自动跳回原地址", LOGIN_PATH not in pg.url, f"url={pg.url}")
        t = text_of(pg)
        check("首页渲染真实数据", "12,698" in t and "欢迎使用" in t, t[:60])
        fauth = pg.evaluate("() => localStorage.getItem('fauth')")
        check("登录态写入 localStorage.fauth", bool(fauth) and "token" in (fauth or ""), (fauth or "")[:60])
        # 跨源（开发 3000）时 fauth 是登录页用 ?auth_token= 交接过来的，用户信息要靠 /api/auth/me 换成真实的
        check("登录态里的用户是真实账号（admin / 管理员）",
              '"username":"admin"' in (fauth or "") and ('"role":"admin"' in (fauth or "")),
              (fauth or "")[-90:])
        pg.screenshot(path=str(OUT / "flow_3_home.png"))

        # 4. 已登录再打开登录页 → 「继续进入」（同源才有登录态，开发模式下跳过）
        if SAME_ORIGIN:
            pg.goto(f"{CONSOLE_BASE}{LOGIN_PATH}", wait_until="load", timeout=45000)
            pg.wait_for_timeout(2500)
            check("已登录时登录页给「继续进入」而不是表单",
                  pg.locator("#paneResume").is_visible() and not pg.locator("#panePw").is_visible(),
                  f"resume={pg.locator('#paneResume').is_visible()}")
        else:
            print("[skip] 开发模式（3000）与登录页（8000）跨源，登录态不共享，跳过「继续进入」检查")

        # 5. 退出登录（顶栏头像菜单）
        pg.goto(f"{BASE}/", wait_until="load", timeout=45000)
        pg.wait_for_timeout(3000)
        pg.locator("header button").last.click()
        pg.wait_for_timeout(900)
        pg.screenshot(path=str(OUT / "flow_5_menu.png"))
        try:
            pg.click("text=退出登录", timeout=5000)
        except Exception as e:  # noqa: BLE001
            check("点击退出登录", False, str(e)[:60])
        pg.wait_for_timeout(3000)
        check("退出后回到登录页", LOGIN_PATH in pg.url, f"url={pg.url}")
        check("退出后 localStorage 已清", not pg.evaluate("() => localStorage.getItem('fauth')"))

        # 6. 非管理员 → /admin 权限卡（拦截 /me 冒充普通用户）
        ctx2 = new_ctx(b, logged_in=True)
        pg2 = ctx2.new_page()
        pg2.route("**/api/auth/me", lambda route: route.fulfill(
            status=200,
            content_type="application/json",
            body=json.dumps({"ok": True, "user": {"user_id": 2, "username": "viewer",
                                                  "display_name": "只读访客", "role": "user"}},
                            ensure_ascii=False),
        ))
        pg2.goto(f"{BASE}/admin?tab=models", wait_until="load", timeout=45000)
        pg2.wait_for_timeout(3500)
        t2 = text_of(pg2)
        check("非管理员看到权限提示而非白屏", "需要管理员权限" in t2, t2[:60])
        check("非管理员看不到管理端正文（无 v9 模型卡）", "v9" not in t2)
        href = pg2.locator("a", has_text="换管理员账号登录").first.get_attribute("href") if pg2.locator("a", has_text="换管理员账号登录").count() else ""
        check("权限卡给出「换管理员账号登录」且带 why=role",
              LOGIN_PATH in (href or "") and "why=role" in (href or ""), str(href))
        check("非管理员顶栏不显示「设置」入口", pg2.locator("header").count() == 0 or "设置" not in pg2.inner_text("header"))
        pg2.screenshot(path=str(OUT / "flow_6_noauth_admin.png"))
        pg2.goto(f"{BASE}/", wait_until="load", timeout=45000)
        pg2.wait_for_timeout(3500)
        check("非管理员仍可看用户端数据", "12,698" in text_of(pg2), text_of(pg2)[:50])
        ctx2.close()

        real = [e for e in errs if "401" not in e and "Failed to load resource" not in e]
        check("全程无控制台错误（忽略故意输错密码的 401）", not real, str(real[:3]))

        ctx.close()
        b.close()

    ok = sum(1 for _, o, _ in results if o)
    print("-" * 90)
    print(f"{ok}/{len(results)} 项通过；截图 → {OUT}")
    return 0 if ok == len(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
