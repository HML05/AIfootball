# -*- coding: utf-8 -*-
"""打印页面正文前 1200 字(看 Streamlit 是否抛异常)。用法: python scripts/peek_page.py home"""
import json, sys, urllib.request
from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8000/api"


def token(user="admin", pwd="football2026"):
    req = urllib.request.Request(API + "/auth/login",
                                 data=json.dumps({"username": user, "password": pwd}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    return (j.get("data") or {}).get("token") or j.get("token")


def main():
    slug = sys.argv[1] if len(sys.argv) > 1 else "home"
    port = sys.argv[2] if len(sys.argv) > 2 else "8501"
    tk = token()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.goto(f"http://127.0.0.1:{port}/?page={slug}&auth_token={tk}",
                wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(12000)
        txt = pg.inner_text("body")
        sys.stdout.reconfigure(encoding="utf-8")
        print("=== 正文前 1500 字 ===")
        print(txt[:1500])
        print("=== JS 错误:", errs[:2])
        dump = pg.evaluate("""() => {
            const m = document.querySelector('[data-testid="stMainBlockContainer"]');
            const ex = document.querySelector('[data-testid="stException"]');
            return {
              mainHtml: m ? m.outerHTML.slice(0, 1800) : null,
              exception: ex ? ex.innerText.slice(0, 800) : null,
              alerts: [...document.querySelectorAll('[data-testid="stAlert"]')].map(e => e.innerText.slice(0,200)),
              blocks: document.querySelectorAll('[data-testid="stVerticalBlock"]').length,
              hidden: [...document.querySelectorAll('[data-testid="stMainBlockContainer"] *')]
                        .filter(e => getComputedStyle(e).display === 'none').length
            };
        }""")
        print("=== DOM ===")
        print(json.dumps(dump, ensure_ascii=False, indent=1)[:3000])
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
