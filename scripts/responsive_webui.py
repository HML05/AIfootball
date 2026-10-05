# -*- coding: utf-8 -*-
"""Webui(React) 响应式体检：同一路由在多个视口宽度下的横向溢出/截断/网格塌陷情况。

用法:
    python scripts/responsive_webui.py                 # / 与 /admin，默认 3 个宽度
    python scripts/responsive_webui.py /teams /players # 指定路由
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:3000")
OUT = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view" / "responsive"
OUT.mkdir(parents=True, exist_ok=True)

WIDTHS = [(1280, 800), (1440, 900), (1920, 1080)]
ROUTES = [a for a in sys.argv[1:] if a.startswith("/")] or ["/", "/admin"]

PROBE = """() => {
    const txt = document.body.innerText || '';
    const overflowEls = [...document.querySelectorAll('*')]
      .filter(el => el.scrollWidth > el.clientWidth + 2 && el.clientWidth > 0)
      .slice(0, 12)
      .map(el => (el.tagName + '.' + String(el.className).split(' ').slice(0, 3).join('.')).slice(0, 80));
    const grid1 = [...document.querySelectorAll('.grid')]
      .filter(el => getComputedStyle(el).gridTemplateColumns.split(' ').length <= 1).length;
    return {
      docW: document.documentElement.scrollWidth,
      docH: document.documentElement.scrollHeight,
      hOverflow: document.documentElement.scrollWidth - document.documentElement.clientWidth,
      overflowEls, singleColGrids: grid1,
      navLinks: document.querySelectorAll('nav a').length,
      text: txt.replace(/\\s+/g, ' ').slice(0, 220),
    };
}"""


def slug(route: str) -> str:
    return route.strip("/").replace("/", "_") or "home"


def main() -> int:
    report: dict = {}
    import _uiauth

    state = _uiauth.auth_state()
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        for route in ROUTES:
            for w, h in WIDTHS:
                key = f"{route}@{w}"
                ctx = browser.new_context(viewport={"width": w, "height": h}, device_scale_factor=1)
                ctx.add_init_script(_uiauth.init_script(state))
                pg = ctx.new_page()
                errors: list[str] = []
                pg.on("console", lambda m: errors.append(f"{m.type}: {m.text}") if m.type == "error" else None)
                pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
                url = f"{BASE}{route}{'&' if '?' in route else '?'}lang=zh"
                try:
                    pg.goto(url, wait_until="load", timeout=45000)
                except Exception as exc:  # noqa: BLE001
                    report[key] = {"goto": f"failed: {exc}"}
                    ctx.close()
                    continue
                pg.wait_for_timeout(3800)
                pg.wait_for_selector("nav", timeout=15000)
                pg.wait_for_timeout(900)
                m = pg.evaluate(PROBE)
                m["errors"] = errors[:6]
                shot = OUT / f"{slug(route)}_{w}.png"
                pg.screenshot(path=str(shot))
                m["shot"] = str(shot)
                report[key] = m
                print(f"{key:>18}  overflow={m['hOverflow']:>4}  docH={m['docH']:>5}  singleColGrids={m['singleColGrids']}  errs={len(m['errors'])}")
                if m["overflowEls"]:
                    print(f"{'':>18}  overflowing: {m['overflowEls'][:5]}")
                ctx.close()
        browser.close()
    (OUT / "report.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
    print("report ->", OUT / "report.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
