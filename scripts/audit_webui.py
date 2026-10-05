"""逐页盘点信息架构：标题 / 卡片顺序 / KPI / 表头 / 行数 / 内部滚动块。

用法: python scripts/audit_webui.py [--base http://127.0.0.1:8000] [路由...]
不传路由则跑全部 11 条。输出为便于比对的文本清单，用于排版与信息架构评审。
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROUTES = [
    "/", "/matches", "/matches/9012", "/leagues", "/leagues/1", "/teams", "/teams/38",
    "/players", "/players/1658", "/predictions", "/live",
    "/admin?tab=overview", "/admin?tab=asset", "/admin?tab=models", "/admin?tab=system",
]

JS = r"""
() => {
  const txt = (el) => (el?.innerText || '').replace(/\s+/g, ' ').trim();
  const h1 = txt(document.querySelector('h1'));
  const sub = txt(document.querySelector('h1')?.parentElement?.querySelector('p'));
  const cards = [...document.querySelectorAll('.glass, .glass-dark, .glass-pop, section')]
      .map(el => ({ t: txt(el.querySelector('h1,h2,h3,h4')), cls: el.className.toString().slice(0, 24) }))
      .filter(c => c.t && c.t.length < 40);
  const seen = new Set(); const titles = [];
  for (const c of cards) { if (!seen.has(c.t)) { seen.add(c.t); titles.push(c.t); } }
  const kpiLabels = [...document.querySelectorAll('*')]
      .filter(el => el.children.length === 0 && /text-xs|text-\[11px\]|tracking-wide/.test(el.className.toString()))
      .map(el => txt(el)).filter(t => t && t.length < 30);
  const tables = [...document.querySelectorAll('table')].map(tb => ({
      cols: [...tb.querySelectorAll('thead th')].map(th => txt(th)),
      rows: tb.querySelectorAll('tbody tr').length,
      scroll: tb.parentElement ? tb.parentElement.scrollHeight - tb.parentElement.clientHeight : 0,
  }));
  const tabs = [...document.querySelectorAll('[role="tab"], .tab, button')].map(b => txt(b)).filter(t => t && t.length < 14);
  const scrollers = [...document.querySelectorAll('*')]
      .filter(el => el.scrollHeight - el.clientHeight > 40 && el.clientHeight > 60)
      .map(el => ({ cls: el.className.toString().slice(0, 30), over: el.scrollHeight - el.clientHeight }));
  return { h1, sub, titles, kpiLabels, tables, tabs: [...new Set(tabs)].slice(0, 14), scrollers, docH: document.documentElement.scrollHeight };
}
"""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8000")
    ap.add_argument("routes", nargs="*")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()
    routes = args.routes or ROUTES
    out_dir = Path(os.environ.get("TEMP", ".")) / "aifootball_view" / "audit"
    out_dir.mkdir(parents=True, exist_ok=True)
    report = {}
    import _uiauth

    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = _uiauth.new_context(b, viewport={"width": 1600, "height": 1000})
        pg = ctx.new_page()
        for r in routes:
            pg.goto(args.base + r + ("&lang=zh" if "?" in r else "?lang=zh"), wait_until="load", timeout=60000)
            pg.wait_for_timeout(4200)
            info = pg.evaluate(JS)
            report[r] = info
            if not args.json:
                print("=" * 96)
                print(f"### {r}   h1={info['h1']}   副题={info['sub'][:60]}")
                print(f"  卡片顺序({len(info['titles'])}): " + " | ".join(info['titles']))
                print(f"  KPI 小标签: " + " / ".join(info['kpiLabels'][:16]))
                for tb in info["tables"]:
                    print(f"  表[{tb['rows']} 行 内滚{tb['scroll']}]: " + " | ".join(tb["cols"][:12]))
                if info["scrollers"]:
                    print("  内部滚动块: " + ", ".join(f"{s['cls']}(+{s['over']})" for s in info["scrollers"][:5]))
                print(f"  文档高: {info['docH']}")
        b.close()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=1))
    else:
        (out_dir / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        print(f"\n[ok] 盘点 JSON → {out_dir / 'inventory.json'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
