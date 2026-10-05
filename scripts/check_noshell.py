# -*- coding: utf-8 -*-
"""无壳模式下的逐页体检: 每页截一张图 + 量外层是否被截断/贴边。

用法: python scripts/check_noshell.py [--only home,leagues]
产物: %TEMP%\\aifootball_view\\ns\\NN_slug.png
"""
import argparse
import json
import os
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(os.environ.get("TEMP", ".")) / "aifootball_view" / "ns"
OUT.mkdir(parents=True, exist_ok=True)
API = "http://127.0.0.1:8000/api"

PAGES = [("home", 8501), ("leagues", 8501), ("teams", 8501), ("players", 8501),
         ("match", 8501), ("predict", 8501), ("agent", 8501), ("live", 8501),
         ("overview", 8502), ("browse", 8502), ("api", 8502), ("database", 8502),
         ("update", 8502), ("models", 8502)]

PROBE = """() => {
  const m = document.querySelector('[data-testid="stMainBlockContainer"]');
  const cs = m ? getComputedStyle(m) : null;
  const r = m ? m.getBoundingClientRect() : null;
  const app = document.querySelector('.stApp');
  const hasRef = !!document.querySelector('.st-key-refpage');
  const fab = document.getElementById('nav-fab');
  const sb = document.querySelector('[data-testid="stSidebar"]');
  return {
    hasRef: hasRef,
    pad: cs ? [cs.paddingTop, cs.paddingRight, cs.paddingBottom, cs.paddingLeft] : null,
    box: r ? [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)] : null,
    docScroll: document.documentElement.scrollHeight,
    vh: window.innerHeight,
    scrollable: document.documentElement.scrollHeight > window.innerHeight + 2,
    fab: fab ? Math.round(fab.getBoundingClientRect().width) : null,
    sidebarShown: sb ? getComputedStyle(sb).display : null,
    appOverflow: app ? getComputedStyle(app).overflow : null
  };
}"""


def token(user="admin", pwd="football2026"):
    req = urllib.request.Request(API + "/auth/login",
                                 data=json.dumps({"username": user, "password": pwd}).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        j = json.loads(r.read().decode())
    return (j.get("data") or {}).get("token") or j.get("token")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default="")
    args = ap.parse_args()
    only = {s.strip() for s in args.only.split(",") if s.strip()}
    tk = token()
    errs, rows = [], []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        for i, (slug, port) in enumerate(PAGES, 1):
            if only and slug not in only:
                continue
            pg = ctx.new_page()
            pg.on("pageerror", lambda e: errs.append(str(e)[:120]))
            url = f"http://127.0.0.1:{port}/?page={slug}&auth_token={tk}"
            pg.goto(url, wait_until="networkidle", timeout=90000)
            pg.wait_for_timeout(11000)
            info = pg.evaluate(PROBE)
            info["slug"] = slug
            rows.append(info)
            pg.screenshot(path=str(OUT / f"{i:02d}_{slug}.png"))
            print(f"{i:02d} {slug:9s} ref={int(info['hasRef'])} pad={info['pad']} "
                  f"box={info['box']} scroll={info['scrollable']} fab={info['fab']} "
                  f"side={info['sidebarShown']}")
            pg.close()
        b.close()
    print("JS 错误:", len(errs), errs[:3])
    return 0


if __name__ == "__main__":
    sys.exit(main())
