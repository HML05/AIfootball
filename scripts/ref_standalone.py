# -*- coding: utf-8 -*-
"""把参照稿模板单独在浏览器里跑一遍(不经过 Streamlit), 作为 1:1 对照基准。

用法:  python scripts/ref_standalone.py
产物:  %TEMP%\\aifootball_view\\ref_solo_{day,sunset,night}.png  (1600x1000)
"""
import os
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
TPL = ROOT / "frontend" / "templates" / "dashboard_ref.html"
IMG = ROOT / "frontend" / "static" / "hero_stadium.jpg"
OUT = Path(os.environ.get("TEMP", ".")) / "aifootball_view"
OUT.mkdir(parents=True, exist_ok=True)


def main() -> int:
    html = TPL.read_text(encoding="utf-8")
    # file:// 下 /app/static/... 不存在, 换成本地文件 URL
    html = html.replace("/app/static/hero_stadium.jpg", IMG.as_uri())
    solo = OUT / "ref_solo.html"
    solo.write_text(html, encoding="utf-8")

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        pg = b.new_page(viewport={"width": 1600, "height": 1000})
        pg.goto(solo.as_uri(), wait_until="load")
        pg.wait_for_timeout(2500)
        for name in ("day", "sunset", "night"):
            pg.screenshot(path=str(OUT / f"ref_solo_{name}.png"))
            print("solo", name, "ok")
            pg.click("#themeBtn")
            pg.wait_for_timeout(900)
        # 关键尺寸, 用于和系统内渲染对齐
        info = pg.evaluate("""() => {
            const q = s => document.querySelector(s);
            const box = el => { if (!el) return null; const r = el.getBoundingClientRect();
                return [Math.round(r.x), Math.round(r.y), Math.round(r.width), Math.round(r.height)]; };
            return {
              frame: box(q('.frame')), nav: box(q('.navbar')), side: box(q('.sidebar')),
              main: box(q('.main')), kpis: box(q('.kpis')), kpi0: box(q('.kpi')),
              stage: box(q('.stage')), focus: box(q('.focus')), bars: box(q('.bars')),
              right: box(q('.side-col') || q('.col-right') || q('.right')),
              stat0: box(q('.stat')), todo: box(q('.todo')), foot: box(q('.page-foot')),
              mainScroll: q('.main') ? q('.main').scrollHeight : null,
              docScroll: document.documentElement.scrollHeight
            };
        }""")
        print("boxes:", info)
        b.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
