# -*- coding: utf-8 -*-
"""参照稿实况截图: 应用内首页 + ?ref=1 全屏预览(1600 宽, 三主题各一张, 走主题按钮切换)。"""
import sys

import requests
from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8000"
OUT = r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view"


def main():
    r = requests.post(f"{API}/api/auth/login",
                      json={"username": "admin", "password": "football2026"}, timeout=20)
    j = r.json()
    tok = (j.get("data") or {}).get("token") or j.get("token")
    if not tok:
        print("登录失败", r.status_code, r.text[:200])
        return 1
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        errs = []

        # 1) 应用内首页(参照稿渲染在 Streamlit 主区里)
        pg = b.new_page(viewport={"width": 1600, "height": 1200})
        pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg.goto(f"http://127.0.0.1:8501/?auth_token={tok}", wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(9000)          # 大图 387KB: 等它画完再截, 否则主图会空白
        pg.screenshot(path=f"{OUT}\\ref_app_home.png")
        print("app home ok")

        # 2) 全屏预览 ?ref=1, 依次点参照稿自带的主题按钮拍三张
        pg2 = b.new_page(viewport={"width": 1600, "height": 1000})
        pg2.on("pageerror", lambda e: errs.append(str(e)[:160]))
        pg2.goto(f"http://127.0.0.1:8501/?ref=1&auth_token={tok}",
                 wait_until="networkidle", timeout=90000)
        pg2.wait_for_timeout(4000)
        for name in ("day", "sunset", "night"):
            fr = None
            for f in pg2.frames:
                try:
                    if f.query_selector(".frame"):
                        fr = f
                        break
                except Exception:
                    pass
            if fr is None:
                print("未找到参照稿 iframe")
                break
            pg2.screenshot(path=f"{OUT}\\ref_full_{name}.png")
            print("full", name, "ok")
            try:
                fr.click("#themeBtn", timeout=5000)
            except Exception as e:
                print("主题按钮点击失败:", str(e)[:80])
                break
            pg2.wait_for_timeout(1600)
        print("JS 错误:", len(errs), errs[:2])
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
