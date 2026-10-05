# -*- coding: utf-8 -*-
"""登录闸门端到端验证: 8501/8502 未登录 -> 控制台登录页(8591/login.html) -> 带令牌回跳。

跑法(先确保 8000/8501/8502/8591 都在跑):
    python scripts/verify_auth_streamlit.py

检查项:
  1. 未登录访问 8501 -> 整页跳到登录页, 且带上 ?next=http://127.0.0.1:8501/
  2. 管理员登录 -> 回到 8501 且地址栏令牌已被抹掉, 出现业务导航
  3. 未登录访问 8502 -> 登录页带 &why=role
  4. 普通账号登录 -> 被应用自身拦下(管理后台需要管理员账号)
  5. 点「退出并换个账号登录」-> 回登录页 -> 管理员登录 -> 进后台
  6. 全程 0 个 JS 错误

截图落在 %TEMP%\\aifootball_view\\(st1..st4)。
"""
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path.home() / "AppData/Local/Temp/aifootball_view"
OUT.mkdir(parents=True, exist_ok=True)
LOGIN = "8591/login.html"
ADMIN = ("admin", "football2026")
VIEWER = ("viewer", "viewer2026")

fails = []


def check(label: str, ok: bool, extra: str = "") -> bool:
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}{('  ' + extra) if extra else ''}")
    if not ok:
        fails.append(label)
    return ok


def sign_in(pg, user, pwd, tag):
    pg.wait_for_selector("#gUser", timeout=30000)
    if pg.locator("#paneResume").count() and pg.is_visible("#paneResume"):
        pg.click("#rsSwitch")                      # 手机已登录时才有的「换个账号」
        pg.wait_for_timeout(400)
    pg.fill("#gUser", user)
    pg.fill("#gPwd", pwd)
    pg.click("#gLogin")
    pg.wait_for_timeout(6000)
    print(f"    ({tag}) 登录后 -> {pg.url}")
    return pg.url


def main() -> int:
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome", headless=True)

        print("1) 用户端 8501")
        ctx = b.new_context()
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:140]))
        pg.goto("http://127.0.0.1:8501/", wait_until="load", timeout=60000)
        pg.wait_for_timeout(12000)
        check("未登录被送到登录页", LOGIN in pg.url, pg.url)
        check("带上了 next 回跳参数", "next=" in pg.url and "8501" in pg.url)
        pg.screenshot(path=str(OUT / "st1_jump_login.png"))

        url = sign_in(pg, *ADMIN, "8501")
        check("管理员登录后回到 8501", "8501" in url and LOGIN not in url, url)
        check("地址栏令牌已抹掉", "auth_token" not in url)
        pg.wait_for_timeout(6000)
        body = pg.inner_text("body")
        check("看到业务导航", "首页概览" in body)
        check("侧栏显示管理员", "管理员" in body)
        pg.screenshot(path=str(OUT / "st2_back_8501.png"))

        print("2) 后台 8502 · 普通账号")
        pg2 = b.new_context().new_page()
        errs2 = []
        pg2.on("pageerror", lambda e: errs2.append(str(e)[:140]))
        pg2.goto("http://127.0.0.1:8502/", wait_until="load", timeout=60000)
        pg2.wait_for_timeout(12000)
        check("后台未登录也被送到登录页", LOGIN in pg2.url, pg2.url)
        check("带上了 why=role 说明", "why=role" in pg2.url)
        url2 = sign_in(pg2, *VIEWER, "8502-viewer")
        pg2.wait_for_timeout(6000)
        body2 = pg2.inner_text("body")
        check("普通账号被拦下", "管理后台需要管理员账号" in body2, body2[:60].replace("\n", " "))
        pg2.screenshot(path=str(OUT / "st3_admin_denied.png"))

        print("3) 后台 8502 · 换成管理员")
        btn = pg2.get_by_role("button", name="退出并换个账号登录")
        if check("有「退出并换个账号登录」按钮", btn.count() > 0):
            btn.first.click()
            pg2.wait_for_timeout(8000)
            check("按钮把人送回登录页", LOGIN in pg2.url, pg2.url)
            if LOGIN in pg2.url:
                url3 = sign_in(pg2, *ADMIN, "8502-admin")
                pg2.wait_for_timeout(6000)
                check("管理员进得去后台", "8502" in url3 and LOGIN not in url3, url3)
                check("后台内容在", "管理员后台" in pg2.inner_text("body"))
                pg2.screenshot(path=str(OUT / "st4_admin_ok.png"))

        check("全程 0 个 JS 错误", not errs and not errs2, f"{errs[:2]} {errs2[:2]}")
        b.close()

    print("\n结果:", "全部通过" if not fails else f"{len(fails)} 项失败 -> {fails}")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
