# -*- coding: utf-8 -*-
"""控制台(8591)登录闸门全流程验证。

跑法(确保 8000/8591 在跑):
    python scripts/verify_console_gate.py

覆盖: 未登录整页跳登录页 / 账号密码登录回用户端控制台 / 退出 / 后台作用域的管理员校验 /
      普通账号被拦 / 改登管理员进后台 / 扫码页可用 / 0 JS 错误。

截图落在 %TEMP%\\aifootball_view\\ (flow1..flow6)。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path.home() / "AppData/Local/Temp/aifootball_view"
OUT.mkdir(parents=True, exist_ok=True)
BASE = "http://127.0.0.1:8591"
ADMIN = ("admin", "football2026")
VIEWER = ("viewer", "viewer2026")

fails = []


def check(label: str, ok: bool, extra: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  ' + extra) if extra else ''}")
    if not ok:
        fails.append(label)
    return ok


def login(pg, user, pwd, expect_next_contains):
    if pg.locator("#paneResume").count() and pg.is_visible("#paneResume"):
        pg.click("#rsSwitch")              # 浏览器里已有登录态时先换账号
        pg.wait_for_timeout(600)
    pg.fill("#gUser", user)
    pg.fill("#gPwd", pwd)
    pg.click("#gLogin")
    pg.wait_for_url(lambda u: "login.html" not in u, timeout=30000)
    pg.wait_for_timeout(1800)
    return expect_next_contains in pg.url


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)

        print("1) 未登录访问 8591")
        pg = b.new_page(viewport={"width": 1440, "height": 950})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:140]))
        pg.goto(BASE + "/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(2500)
        check("整页落到登录页", "login.html" in pg.url, pg.url)
        check("带 next 回跳", "next=" in pg.url and "8591" in pg.url)
        check("登录表单可见", pg.is_visible("#panePw"))
        check("接口状态显示已连接", "已连接" in pg.inner_text("#apiText"),
              pg.inner_text("#apiText"))
        check("3D 足球面板已铺开", pg.eval_on_selector("#ballPanels", "el => el.children.length") > 0,
              f"{pg.eval_on_selector('#ballPanels', 'el => el.children.length')} 块, 场景 {pg.get_attribute('body', 'data-wx')}")
        pg.screenshot(path=str(OUT / "flow1_login.png"))

        print("2) admin 登录 -> 用户端控制台")
        ok = login(pg, *ADMIN, "index.html")
        pg.wait_for_timeout(2500)
        check("回到用户端控制台", ok, pg.url)
        who_role = pg.inner_text("#whoRole").strip()
        check("顶栏显示管理员", who_role.upper() in ("ADMIN", "管理员"), who_role)
        nav = pg.eval_on_selector_all("#nav .nav-item", "els => els.length")
        check("导航 8 项(只含用户端)", nav == 8, f"{nav} 项")
        check("首页是首页概览", pg.inner_text("#viewTitle") == "首页概览", pg.inner_text("#viewTitle"))
        pg.screenshot(path=str(OUT / "flow2_user_console.png"))

        print("2b) 用户端控制台「真实系统」-> 8501 免登录直达")
        before = set(pg.context.pages)
        pg.click("#realBtn")
        pg.wait_for_timeout(14000)
        opened = [x for x in pg.context.pages if x not in before]
        p3 = opened[0] if opened else pg          # 可能新标签, 也可能同页跳转
        check("到了用户端 8501", "8501" in p3.url, p3.url)
        check("没有再去登录页", "login.html" not in p3.url, p3.url)
        check("业务内容在", "首页概览" in p3.inner_text("body"))
        p3.screenshot(path=str(OUT / "flow2b_realsystem_8501.png"))
        for extra in opened:
            extra.close()
        pg.goto(BASE + "/index.html", wait_until="load", timeout=60000)   # 同页跳走过就回控制台
        pg.wait_for_timeout(3000)

        print("3) 退出")
        pg.click("#whoOut")
        pg.wait_for_url("**/login.html*", timeout=30000)
        pg.wait_for_timeout(1200)
        check("退出后回到登录页", "login.html" in pg.url, pg.url)
        check("浏览器里的登录态已清", not pg.evaluate("() => localStorage.getItem('fauth')"))

        print("4) 后台作用域 · 普通账号")
        pg.goto(BASE + "/admin.html", wait_until="load", timeout=60000)
        pg.wait_for_timeout(2000)
        login(pg, *VIEWER, "admin.html")
        pg.wait_for_timeout(2000)
        check("普通账号被拦在闸门", pg.is_visible("#gate"))
        check("提示写明需要管理员", "管理员" in pg.inner_text("#gMsg"), pg.inner_text("#gMsg"))
        pg.screenshot(path=str(OUT / "flow4_admin_denied.png"))

        print("5) 改登管理员 -> 管理后台控制台")
        pg.click("#gToLogin")
        pg.wait_for_timeout(2500)
        check("被送回登录页", "login.html" in pg.url, pg.url)
        ok = login(pg, *ADMIN, "admin.html")
        pg.wait_for_timeout(2500)
        check("进入后台控制台", ok, pg.url)
        nav2 = pg.eval_on_selector_all("#nav .nav-item", "els => els.length")
        check("导航 6 项(只含后台)", nav2 == 6, f"{nav2} 项")
        check("首页是数据概览", pg.inner_text("#viewTitle") == "数据概览", pg.inner_text("#viewTitle"))
        pg.screenshot(path=str(OUT / "flow5_admin_console.png"))

        print("6) 登录页扫码页签")
        p2 = b.new_context().new_page()
        p2.goto(BASE + "/login.html", wait_until="load", timeout=60000)
        p2.click("#tabQr")
        p2.wait_for_timeout(3500)
        check("二维码出来了", p2.is_visible("#gQrImg"), p2.inner_text("#gQrState"))
        check("状态是等待扫码", "等待" in p2.inner_text("#gQrState"), p2.inner_text("#gQrState"))
        p2.screenshot(path=str(OUT / "flow6_qr.png"))

        print("7) 管理后台控制台「真实系统」-> 8502 免登录直达")
        try:
            with pg.expect_popup(timeout=20000) as pop:
                pg.click("#realBtn")
            p4 = pop.value
        except Exception:
            p4 = pg
        p4.wait_for_timeout(14000)
        check("到了管理后台 8502", "8502" in p4.url, p4.url)
        check("没有再去登录页", "login.html" not in p4.url, p4.url)
        check("后台内容在", "数据概览" in p4.inner_text("body"))
        p4.screenshot(path=str(OUT / "flow7_realsystem.png"))

        check("全程 0 个 JS 错误", not errs, str(errs[:3]))
        b.close()

    print("\n结果:", "全部通过" if not fails else f"{len(fails)} 项失败 -> {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
