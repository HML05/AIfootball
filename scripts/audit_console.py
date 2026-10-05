# -*- coding: utf-8 -*-
"""渲染 docs/console/index.html 的 14 个页面并做结构化审计。"""
import json
import re
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

PAGE = Path("docs/console/index.html").resolve()
OUT = Path(r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view")
SLUGS = ["home", "leagues", "teams", "players", "match", "predict", "agent", "live",
         "overview", "browse", "api", "database", "update", "models"]

DEMO = ["曼城", "阿森纳", "哈兰德", "凯恩", "姆巴佩", "伊蒂哈德", "奥利弗", "皇马", "塞维利亚",
        "12,840", "5,200", "55.1", "0.188", "0.974", "1280", "96.4", "220", "1.2s", "v4",
        "演示", "示例", "Man City", "Manchester City", "demo", "RMA", "FCB", "BAR", "PSG",
        "premier-league", "la-liga", "serie-a", "bundesliga", "ligue-1", "man-city", "arsenal"]

report = {}
errors = []

with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    pg = b.new_page(viewport={"width": 1440, "height": 950})
    pg.on("pageerror", lambda e: errors.append(str(e)))
    pg.on("console", lambda m: errors.append("console:" + m.text) if m.type == "error" else None)
    pg.goto(PAGE.as_uri(), wait_until="load", timeout=60000)
    pg.wait_for_timeout(900)
    for slug in SLUGS:
        pg.evaluate("s => { location.hash = s; }", slug)
        pg.wait_for_timeout(700)
        info = pg.evaluate("""(dem) => {
            const c = document.getElementById('content');
            const txt = c.innerText || '';
            const imgs = [...c.querySelectorAll('img')];
            return {
                title: document.getElementById('viewTitle').textContent,
                sub: document.getElementById('viewSub').textContent,
                chars: txt.length,
                svg: c.querySelectorAll('svg').length,
                tables: c.querySelectorAll('table').length,
                charts: c.querySelectorAll('svg.chart, .heat').length,
                imgs: imgs.length,
                broken: imgs.filter(i => !i.complete || i.naturalWidth === 0).map(i => i.getAttribute('src')),
                empty: c.querySelectorAll('.empty').length,
                hits: dem.filter(d => txt.includes(d)),
                text: txt.replace(/\\n{2,}/g, '\\n').slice(0, 2600)
            };
        }""", DEMO)
        info["hash"] = pg.evaluate("location.hash")
        report[slug] = info
        pg.screenshot(path=str(OUT / f"ct_{slug}.png"), full_page=False)
    b.close()

if errors:
    print("JS 错误:", json.dumps(errors[:10], ensure_ascii=False, indent=1))
else:
    print("JS 错误: 0")

print(f"{'页':10s} {'标题':16s} {'字符':>6s} {'svg':>4s} {'表':>3s} {'图':>3s} {'图img':>5s} {'坏图':>4s} {'空':>3s} 演示命中")
for s in SLUGS:
    r = report[s]
    print(f"{s:10s} {r['title'][:15]:16s} {r['chars']:6d} {r['svg']:4d} {r['tables']:3d} {r['charts']:3d} "
          f"{r['imgs']:5d} {len(r['broken']):4d} {r['empty']:3d} {','.join(r['hits'][:8])}")

(OUT / "console_audit.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("报告:", OUT / "console_audit.json")
