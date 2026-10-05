# -*- coding: utf-8 -*-
"""控制台登录闸门自检: 闸门可见 → 扫码二维码生成 → 账密登录 → 刷新免登录 → 退出。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view")
USER, PWD = "admin", "CaCH9WYGmWMH"
errs = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
    pg.goto("http://127.0.0.1:8591/", wait_until="load", timeout=60000)
    pg.wait_for_timeout(1200)

    gate_visible = pg.is_visible("#gate")
    print("1) 闸门可见:", gate_visible)
    print("   账号输入框:", pg.is_visible("#gUser"), "| 二维码图:", pg.is_visible("#gQrImg"))
    qr_src = pg.get_attribute("#gQrImg", "src") or ""
    print("   二维码 src:", (qr_src[:70] + "…") if qr_src else "(空)")
    print("   扫码状态:", pg.inner_text("#gQrState"))
    pg.screenshot(path=str(OUT / "gate_1440.png"))

    # 手机端确认页的样子(同一张票据)
    import json as _json
    import urllib.request
    req = urllib.request.Request("http://127.0.0.1:8000/api/auth/qr/start", method="POST")
    q = _json.loads(urllib.request.urlopen(req, timeout=20).read().decode())
    mp = b.new_page(viewport={"width": 390, "height": 844})
    mp.goto(q["scan_url"].replace("10.5.86.80", "127.0.0.1"), wait_until="load", timeout=30000)
    mp.wait_for_timeout(900)
    mp.screenshot(path=str(OUT / "gate_mobile.png"))
    print("2) 手机确认页标题:", mp.inner_text("h1"))
    mp.close()

    # 错误密码
    pg.fill("#gUser", USER)
    pg.fill("#gPwd", "wrong-password")
    pg.click("#gLogin")
    pg.wait_for_timeout(1500)
    print("3) 错误密码提示:", pg.inner_text("#gMsg"))

    # 正确密码
    pg.fill("#gPwd", PWD)
    pg.click("#gLogin")
    pg.wait_for_timeout(2500)
    print("4) 登录后闸门隐藏:", not pg.is_visible("#gate"),
          "| 顶栏用户:", pg.inner_text("#whoName") if pg.is_visible("#whoBox") else "(未显示)",
          pg.inner_text("#whoRole") if pg.is_visible("#whoBox") else "")
    pg.screenshot(path=str(OUT / "gate_after_login.png"))

    # 刷新免登录
    pg.reload(wait_until="load")
    pg.wait_for_timeout(1800)
    print("5) 刷新后仍需登录:", pg.is_visible("#gate"))

    # 退出
    pg.click("#whoOut")
    pg.wait_for_timeout(2000)
    print("6) 退出后回到登录页:", pg.is_visible("#gate"))

    print("JS 错误:", len(errs), errs[:3])
    b.close()
