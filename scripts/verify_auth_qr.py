# -*- coding: utf-8 -*-
"""扫码登录端到端: PC 控制台显示二维码 -> 手机(移动视口)扫码确认 -> PC 自动进入。"""
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view")
USER, PWD = "admin", "CaCH9WYGmWMH"


def txt(pg):
    return pg.evaluate("document.body.innerText.replace(/\\s+/g,' ')")


with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)

    # PC: 控制台(干净的 storage, 必然停在登录页)
    pc = b.new_page(viewport={"width": 1440, "height": 950})
    pc.goto("http://127.0.0.1:8591/", wait_until="load", timeout=60000)
    pc.wait_for_timeout(1500)
    print("PC 停在登录页:", pc.is_visible("#gate"), "|", pc.inner_text("#gQrState"))

    src = pc.get_attribute("#gQrImg", "src")
    qr_id = src.split("qr_id=")[1].split("&")[0]
    secret = src.split("secret=")[1].split("&")[0]
    scan = f"http://127.0.0.1:8000/api/auth/qr/scan?qr_id={qr_id}&secret={secret}"
    print("票据:", qr_id[:12], "…")

    # 手机: 移动视口打开确认页并同意
    phone = b.new_page(viewport={"width": 390, "height": 844},
                       user_agent=("Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                                   "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"))
    phone.goto(scan, wait_until="load", timeout=30000)
    phone.wait_for_timeout(1200)
    phone.screenshot(path=str(OUT / "qr_phone_form.png"))
    print("手机页面:", phone.inner_text("h1"), "| 设备行:", phone.inner_text(".dev-name"))

    # 等一下, 让 PC 轮询到 scanned
    pc.wait_for_timeout(4000)
    print("PC 状态(扫码后):", pc.inner_text("#gQrState"))

    phone.fill("#u", USER)
    phone.fill("#p", PWD)
    phone.click("button[type=submit]")
    phone.wait_for_timeout(2000)
    print("手机提示:", phone.inner_text("#msg"))
    print("手机已存登录态:", phone.evaluate("!!localStorage.getItem('fauth')"))
    phone.screenshot(path=str(OUT / "qr_phone_done.png"))

    # PC 应自动进入
    pc.wait_for_timeout(4000)
    entered = not pc.is_visible("#gate")
    print("PC 自动登录:", entered,
          "| 顶栏:", pc.inner_text("#whoName") if entered else "(仍在登录页)")
    pc.screenshot(path=str(OUT / "qr_pc_logged_in.png"))

    # 已登录的手机再扫一次: 应一键同意(不用再输密码)
    pc.click("#whoOut")
    pc.wait_for_timeout(3000)
    src2 = pc.get_attribute("#gQrImg", "src")
    scan2 = ("http://127.0.0.1:8000/api/auth/qr/scan?qr_id=" + src2.split("qr_id=")[1].split("&")[0]
             + "&secret=" + src2.split("secret=")[1].split("&")[0])
    phone.goto(scan2, wait_until="load", timeout=30000)
    phone.wait_for_timeout(2000)
    one_tap = phone.locator("#oneTap")
    print("手机已登录 -> 一键同意按钮:", one_tap.count() > 0, "|", txt(phone)[:56])
    phone.screenshot(path=str(OUT / "qr_phone_onetap.png"))
    if one_tap.count():
        one_tap.click()
        phone.wait_for_timeout(2000)
        print("手机提示:", phone.inner_text("#msg"))
        pc.wait_for_timeout(5000)
        print("一键同意后 PC 自动登录:", not pc.is_visible("#gate"),
              "| 顶栏:", pc.inner_text("#whoName") if not pc.is_visible("#gate") else "-")
    b.close()
