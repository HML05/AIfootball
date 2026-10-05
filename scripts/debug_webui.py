# -*- coding: utf-8 -*-
"""调试 webui 与后端 /api/ui 的联通性（打印所有请求/失败/控制台输出）。"""
from __future__ import annotations

import json
import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:3000")
ROUTE = sys.argv[1] if len(sys.argv) > 1 else "/"


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome")
        ctx = browser.new_context(viewport={"width": 1400, "height": 900})
        pg = ctx.new_page()
        log: list[str] = []
        pg.on("console", lambda m: log.append(f"[console.{m.type}] {m.text}"))
        pg.on("pageerror", lambda e: log.append(f"[pageerror] {e}"))
        pg.on("requestfailed", lambda r: log.append(f"[requestfailed] {r.url} · {r.failure}"))
        pg.on(
            "response",
            lambda r: log.append(f"[response {r.status}] {r.url[:120]}") if "/api/ui" in r.url else None,
        )
        pg.goto(f"{BASE}{ROUTE}?lang=zh", wait_until="load", timeout=45000)
        pg.wait_for_timeout(5000)
        inline = pg.evaluate(
            """async () => {
                const out = {};
                try {
                    const r = await fetch('http://127.0.0.1:8000/api/ui/home');
                    out.status = r.status;
                    const j = await r.json();
                    out.keys = Object.keys(j).slice(0, 12);
                } catch (e) { out.err = String(e); }
                return out;
            }"""
        )
        print("inline fetch:", json.dumps(inline, ensure_ascii=False))
        print("--- events ---")
        for line in log[-40:]:
            print(line)
        browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
