# -*- coding: utf-8 -*-
"""Webui(React) 页面实况截图 + 关键内容检查。

用法:
    python scripts/shot_webui.py                 # 截首页与 admin
    python scripts/shot_webui.py /leagues /teams # 指定路由
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:3000")
OUT = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view" / "webui"
OUT.mkdir(parents=True, exist_ok=True)

ROUTES = sys.argv[1:] or ["/", "/admin"]

# 未登录态截图的路线（不注入 token）
PUBLIC_ROUTES = {"/console/login.html"}


def slug(route: str) -> str:
    s = route.strip("/").replace("/", "_") or "home"
    # 清理 Windows 文件名非法字符（含查询串里的 ? & = 等），否则带 ?tab= 的路由必崩
    for ch in '?&=%*:<>|"\\\'#':
        s = s.replace(ch, "_")
    return s


def main() -> int:
    report = {}
    import _uiauth

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        vp = {"width": 1600, "height": 1000}
        ctx = _uiauth.new_context(browser, viewport=vp, device_scale_factor=1)
        ctx_public = browser.new_context(viewport=vp, device_scale_factor=1)
        for route in ROUTES:
            pg = (ctx_public if route in PUBLIC_ROUTES else ctx).new_page()
            errors: list[str] = []
            pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
            url = f"{BASE}/{('?' + 'lang=zh') if '?' not in route else ''}" if route == "/" else f"{BASE}{route}{'?' if '?' not in route else '&'}lang=zh"
            try:
                pg.goto(url, wait_until="load", timeout=45000)
            except Exception as exc:  # noqa: BLE001
                report[route] = {"error": f"goto failed: {exc}"}
                pg.close()
                continue
            pg.wait_for_timeout(4200)
            try:
                pg.wait_for_selector("nav", timeout=15000)
            except Exception:  # noqa: BLE001
                pass
            pg.wait_for_timeout(1200)
            metrics = pg.evaluate(
                """() => {
                    const q = (s) => document.querySelectorAll(s).length;
                    const txt = document.body.innerText || '';
                    const bad = [...document.querySelectorAll('*')].filter(el => el.children.length === 0 && el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0).length;
                    return {
                      title: document.title,
                      nodes: document.querySelectorAll('*').length,
                      imgs: q('img'),
                      brokenImgs: [...document.querySelectorAll('img')].filter(i => i.complete && i.naturalWidth === 0 && (i.getAttribute('src') || '').trim() !== '').length,
                      skeletons: q('.skeleton'),
                      cards: q('.glass, .glass-dark, .glass-soft'),
                      hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
                      docH: document.documentElement.scrollHeight,
                      clipped: bad,
                      text: txt.replace(/\\s+/g, ' ').slice(0, 700),
                    };
                }"""
            )
            shot = OUT / f"{slug(route)}.png"
            pg.screenshot(path=str(shot), full_page=False)
            full = OUT / f"{slug(route)}_full.png"
            pg.screenshot(path=str(full), full_page=True)
            metrics["shot"] = str(shot)
            metrics["errors"] = errors[:8]
            report[route] = metrics
            print(f"== {route} -> {shot}")
            print(json.dumps(metrics, ensure_ascii=False, indent=1)[:1600])
            pg.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("report ->", OUT / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
