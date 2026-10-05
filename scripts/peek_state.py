# -*- coding: utf-8 -*-
"""看登录态: 是否有密码框 / 页面上都有哪些 testid。用法: python scripts/peek_state.py"""
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
    tk = token()
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.goto(f"http://127.0.0.1:8501/?auth_token={tk}", wait_until="networkidle", timeout=90000)
        pg.wait_for_timeout(10000)
        sys.stdout.reconfigure(encoding="utf-8")
        info = pg.evaluate("""() => {
            const ids = {};
            document.querySelectorAll('[data-testid]').forEach(e => {
                const k = e.getAttribute('data-testid');
                ids[k] = (ids[k] || 0) + 1;
            });
            return {
              pwdInputs: document.querySelectorAll('input[type=password]').length,
              textInputs: document.querySelectorAll('input').length,
              buttons: [...document.querySelectorAll('button')].map(b => (b.innerText||'').trim().slice(0,20)).filter(Boolean).slice(0,12),
              ids: ids, url: location.href.slice(0, 140),
              bodyLen: (document.body.innerText || '').length
            };
        }""")
        print(json.dumps(info, ensure_ascii=False, indent=1)[:2500])
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
