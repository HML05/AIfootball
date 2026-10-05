# -*- coding: utf-8 -*-
"""Data Command 改版验证: 采集计算样式 + 截图 + 错误, 覆盖 1440 / 520 两档宽度。"""
import json
from pathlib import Path

from playwright.sync_api import sync_playwright

OUT = Path(r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view")
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    (8501, "home", "用户端首页"),
    (8501, "leagues", "用户端联赛"),
    (8501, "players", "用户端球员"),
    (8501, "predict", "用户端预测"),
    (8502, "overview", "后台概览"),
    (8502, "models", "后台模型"),
    (8502, "database", "后台数据库"),
    (8502, "browse", "后台数据浏览"),
]

PROBE = """() => {
  const cs = (el) => el ? getComputedStyle(el) : null;
  const app = document.querySelector('.stApp') || document.body;
  const kpi = document.querySelector('.mc-value, .metric-value, [data-testid="stMetricValue"]');
  const lab = document.querySelector('.mc-top, .metric-label, [data-testid="stMetricLabel"] p');
  const sb = document.querySelector('[data-testid="stSidebar"]');
  const card = document.querySelector('.metric-card');
  const btn = document.querySelector('.stButton > button[kind="primary"]');
  const hairline = card ? getComputedStyle(card, '::before') : null;
  return {
    bodyBg: cs(document.body).backgroundColor,
    appBg: cs(app).backgroundColor,
    appBgImage: (cs(app).backgroundImage || '').slice(0, 120),
    sidebarBg: sb ? cs(sb).backgroundColor : null,
    cardBg: card ? cs(card).backgroundColor : null,
    cardRadius: card ? cs(card).borderRadius : null,
    kpiColor: kpi ? cs(kpi).color : null,
    kpiFont: kpi ? cs(kpi).fontFamily : null,
    kpiWeight: kpi ? cs(kpi).fontWeight : null,
    kpiVariant: kpi ? cs(kpi).fontVariantNumeric : null,
    labFont: lab ? cs(lab).fontFamily : null,
    labSize: lab ? cs(lab).fontSize : null,
    labSpacing: lab ? cs(lab).letterSpacing : null,
    labTransform: lab ? cs(lab).textTransform : null,
    btnPrimaryBg: btn ? cs(btn).backgroundColor : null,
    hairline: hairline ? hairline.backgroundImage.slice(0, 80) : null,
    metricCards: document.querySelectorAll('.metric-card').length,
    featureCards: document.querySelectorAll('.feature-card').length,
    badges: document.querySelectorAll('.badge').length,
    charts: document.querySelectorAll('iframe[title*="altair"], .stAltairChart, [data-testid="stVegaLiteChart"]').length,
    tables: document.querySelectorAll('[data-testid="stDataFrame"], [data-testid="stTable"]').length,
    tabs: document.querySelectorAll('.stTabs [data-baseweb="tab"]').length,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    text: (document.body.innerText || '').replace(/\\s+/g, ' ').slice(0, 160),
  };
}"""

report = []
with sync_playwright() as p:
    b = p.chromium.launch(channel="chrome", headless=True)
    for width, height, tag in ((1440, 950, "1440"), (520, 900, "520")):
        ctx = b.new_context(viewport={"width": width, "height": height})
        pg = ctx.new_page()
        errs = []
        pg.on("pageerror", lambda e: errs.append(str(e)[:200]))
        pg.on("console", lambda m: errs.append("console:" + m.text[:160])
              if m.type == "error" else None)
        for port, slug, name in PAGES:
            errs.clear()
            try:
                pg.goto(f"http://127.0.0.1:{port}/?page={slug}", wait_until="load", timeout=90000)
                pg.wait_for_timeout(9000)
                try:
                    pg.wait_for_selector('.metric-card, [data-testid="stMetric"]', timeout=25000)
                except Exception:
                    pass
                pg.wait_for_timeout(2500)
                data = pg.evaluate(PROBE)
                data.update({"port": port, "slug": slug, "name": name, "width": width,
                             "errors": len(errs), "err0": (errs[0] if errs else None)})
                report.append(data)
                pg.screenshot(path=str(OUT / f"dc_{tag}_{slug}.png"), full_page=False)
                print(f"[{tag}] {name:8s} bg={data['bodyBg']:18s} kpiFont={str(data['kpiFont'])[:28]:30s} "
                      f"卡片={data['metricCards']:2d} 图={data['charts']:2d} 表={data['tables']:2d} "
                      f"溢出={data['overflowX']:4d} 错={data['errors']}")
            except Exception as e:                       # pragma: no cover
                print(f"[{tag}] {name} 失败: {str(e)[:160]}")
        ctx.close()
    b.close()

(OUT / "dc_verify.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
print("报告:", OUT / "dc_verify.json")
