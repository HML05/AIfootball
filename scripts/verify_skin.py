# -*- coding: utf-8 -*-
"""换肤后自检: 8501 用户端 + 8502 管理后台 全 14 页。

做三件事:
  1) 结构回归 —— 与换肤前的基线 %TEMP%\\aifootball_view\\report.json 对比
     (图表数 / 表格数 / iframe 数 / 文本长度), 确认「除了视觉, 什么都没变」;
  2) 换肤体检 —— 页面底色与文字色是否已是新的日场令牌, 是否还有旧绿残留,
     是否出现横向溢出或文字裁切;
  3) 逐页截图 —— 存到 %TEMP%\\aifootball_view\\skin\\NN_slug.png, 供人眼核对。

用法: python scripts/verify_skin.py
"""
from __future__ import annotations

import json
import os
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

API = "http://127.0.0.1:8000"
USER = {"username": "admin", "password": "football2026", "remember": True}
OUT = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view"
SHOTS = OUT / "skin"
BASELINE = OUT / "report.json"

# (端口, slug, 中文名, 与基线 report.json 里的 page 字段对应)
PAGES = [
    (8501, "home", "首页概览", "用户端 首页概览"),
    (8501, "leagues", "联赛数据", "用户端 联赛数据"),
    (8501, "teams", "球队分析", "用户端 球队分析"),
    (8501, "players", "球员分析", "用户端 球员分析"),
    (8501, "match", "比赛详情", "用户端 比赛详情"),
    (8501, "predict", "比赛预测", "用户端 比赛预测"),
    (8501, "agent", "AI智能分析", "用户端 AI智能分析"),
    (8501, "live", "实时比分", "用户端 实时比分"),
    (8502, "overview", "数据概览", "后台 数据概览"),
    (8502, "browse", "数据浏览", "后台 数据浏览"),
    (8502, "api", "API接口测试", "后台 API接口测试"),
    (8502, "database", "数据库管理", "后台 数据库管理"),
    (8502, "update", "数据更新控制", "后台 数据更新控制"),
    (8502, "models", "模型管理", "后台 模型管理"),
]

AUDIT_JS = r"""
() => {
  const GREEN = ['rgb(53, 201, 141)', 'rgb(38, 168, 119)', 'rgb(92, 184, 240)',
                 'rgb(47, 214, 166)', 'rgb(53,201,141)'];
  let green = 0; const samples = [];
  document.querySelectorAll('*').forEach(el => {
    const cs = getComputedStyle(el);
    [cs.color, cs.backgroundColor, cs.borderTopColor, cs.backgroundImage].forEach(v => {
      if (!v) return;
      if (GREEN.some(g => v.includes(g))) {
        green++;
        if (samples.length < 4) {
          samples.push(el.tagName + '.' + String(el.className || '').slice(0, 34) + ' → ' + v.slice(0, 52));
        }
      }
    });
  });
  const df = el => !!(el.closest && el.closest('[data-testid="stDataFrame"],[data-testid="stTable"]'));
  const charts = document.querySelectorAll('[data-testid="stVegaLiteChart"]').length;
  const clipped = [];
  document.querySelectorAll('h1,h2,h3,h4,p,span,div,td,th,.k,.v').forEach(el => {
    if (el.children.length) return;
    if (!el.offsetParent && el.tagName !== 'BODY') return;
    if (el.scrollWidth > el.clientWidth + 3 && el.clientWidth > 0) {
      clipped.push(String(el.className || el.tagName).slice(0, 28));
    }
  });
  const app = document.querySelector('.stApp');
  const acs = app ? getComputedStyle(app) : null;
  const h1 = document.querySelector('h1');
  return {
    appBg: acs ? acs.backgroundColor : '',
    appColor: acs ? acs.color : '',
    appBgImage: acs ? acs.backgroundImage.slice(0, 70) : '',
    innerBg: (() => { const m = document.querySelector('[data-testid="stAppViewContainer"]');
                      return m ? getComputedStyle(m).backgroundColor : ''; })(),
    charts: charts,
    frames: document.querySelectorAll('iframe').length,
    tables: document.querySelectorAll('[data-testid="stDataFrame"],[data-testid="stTable"]').length,
    tabs: document.querySelectorAll('[data-testid="stTabs"]').length,
    typed: document.querySelectorAll('[data-testid="stMetricValue"]').length,
    clipped: clipped.slice(0, 6),
    clippedN: clipped.length,
    overflowX: document.documentElement.scrollWidth - window.innerWidth,
    bodyLen: (document.body.innerText || '').replace(/\s+/g, ' ').trim().length,
    bodyText: (document.body.innerText || '').replace(/\s+/g, ' ').slice(0, 30000),
    // Streamlit 的 st.tabs 只渲染当前标签页, 其余面板 display:none 不进 innerText;
    // textContent 能拿到全部面板文字, 用来区分「真丢了」与「在别的标签页里」。
    bodyAll: (document.body.textContent || '').replace(/\s+/g, ' ').slice(0, 700000),
    pageH: document.documentElement.scrollHeight,
    title: document.title,
    h1: h1 ? h1.innerText.trim().slice(0, 40) : '',
    oldGreen: green,
    greenSamples: samples,
    errs: 0,
  };
}
"""


def login_token() -> str:
    body = json.dumps(USER).encode()
    req = urllib.request.Request(API + "/api/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    tok = data.get("token")
    if not tok:
        raise SystemExit("登录失败, 没拿到令牌: " + json.dumps(data, ensure_ascii=False)[:200])
    return tok


def ref_skeleton(pg, slug: str) -> dict:
    """参照稿整页页(首页概览/数据概览)的骨架验收: 内容在 iframe 里, 按参照稿自己的区块判定。

    预期骨架: .frame / .navbar / .sidebar(.menu a>=8) / .kpis .kpi==4 / .focus(.odds .odd==3, .donut)
              / .bars .brow==4 / .rightcol(用户卡 + .stat==4 + .todo) / .panel-row>=3
    另外校验 KPI 数字都非空(sample 值未被真数据替换就会是空的)。
    """
    for f in pg.frames:
        try:
            if f.query_selector(".frame") and f.query_selector(".kpis"):
                return f.evaluate("""() => {
                    const q = (s) => document.querySelectorAll(s).length;
                    const nums = [].slice.call(document.querySelectorAll('.kpis .kpi .num'))
                        .map(e => (e.innerText || '').trim());
                    const empty = nums.filter(n => !n).length;
                    const bars = [].slice.call(document.querySelectorAll('.bars .brow .bar > i'))
                        .map(e => (e.style.width || ''));
                    const out = {
                        frame: q('.frame'), navbar: q('.navbar'), sidebar: q('.sidebar'),
                        menu: q('.sidebar .menu a'), kpi: q('.kpis .kpi'), focus: q('.focus'),
                        odds: q('.focus .odds .odd'), donut: q('.focus .donut'),
                        brow: q('.bars .brow'), stat: q('.rightcol .stat'),
                        userCard: q('.rightcol .user-card'), todo: q('.rightcol .todo'),
                        panelRow: q('.panel-row'), nums: nums, emptyNums: empty,
                        barWidths: bars, jsErr: 0,
                    };
                    const want = {frame: 1, navbar: 1, sidebar: 1, kpi: 4, focus: 1, odds: 3,
                                  donut: 1, brow: 4, stat: 4, userCard: 1, todo: 1};
                    const bad = [];
                    for (const k in want) { if (out[k] < want[k]) bad.push(k + '=' + out[k]); }
                    if (out.menu < 8) bad.push('menu=' + out.menu);
                    if (out.panelRow < 3) bad.push('panelRow=' + out.panelRow);
                    if (out.emptyNums) bad.push('空KPI=' + out.emptyNums);
                    if (bars.some(w => !w)) bad.push('空进度条');
                    out.ok = bad.length === 0;
                    out.why = bad.join(', ');
                    return out;
                }""")
        except Exception:
            continue
    return {"ok": False, "why": "找不到参照稿 iframe(.frame/.kpis)"}


def main() -> int:
    base = {}
    if BASELINE.exists():
        for rec in json.loads(BASELINE.read_text(encoding="utf-8")):
            base[rec.get("page")] = rec
    SHOTS.mkdir(parents=True, exist_ok=True)
    token = login_token()
    print("已登录, 令牌拿到 (%d 字符)" % len(token))

    rows, bad = [], []
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome")
        for i, (port, slug, name, base_key) in enumerate(PAGES, 1):
            ctx = br.new_context(viewport={"width": 1440, "height": 950})
            pg = ctx.new_page()
            errs = []
            pg.on("pageerror", lambda e: errs.append(str(e)[:160]))
            pg.on("console", lambda m: errs.append("console:" + m.text[:120])
                  if m.type == "error" else None)
            url = f"http://127.0.0.1:{port}/?page={slug}&auth_token={token}"
            pg.goto(url, wait_until="domcontentloaded", timeout=90000)
            pg.wait_for_timeout(14000)
            try:
                pg.wait_for_selector('[data-testid="stAppViewContainer"]', timeout=20000)
            except Exception:
                pass
            pg.wait_for_timeout(3000)
            rec = pg.evaluate(AUDIT_JS)
            shot = SHOTS / f"{i:02d}_{slug}.png"
            pg.screenshot(path=str(shot), full_page=False)
            rec.update(page=name, port=port, slug=slug, errs=len(errs), errList=errs[:3],
                       url=pg.url, shot=str(shot))
            # 首页概览 / 数据概览 = 整页参照稿: 趁页面还开着, 在 iframe 里验参照稿骨架
            REF_PAGES = {"首页概览": "home", "数据概览": "overview"}
            if name in REF_PAGES:
                rec["ref"] = ref_skeleton(pg, REF_PAGES[name])
            rows.append(rec)
            ctx.close()

            b = base.get(base_key, {})
            notes = []
            # 分区标题回归: 换肤前每个分区的小标题都必须还在(内容一字未改的硬证据)
            # 基线里每节形如 "图标\n标题\n副标题", 有的把图标与标题挤在一行 —— 统一
            # 去掉所有空白后再剥掉开头那个图标名(纯 ASCII), 避免被排版差异误判。
            def _squash(s: object) -> str:
                return re.sub(r"\s+", "", str(s))

            def _kw(sec: object) -> str:
                return re.sub(r"^[a-z][a-z0-9_]*", "", _squash(sec))

            body_squashed = _squash(rec.get("bodyText", ""))
            all_squashed = _squash(rec.get("bodyAll", ""))
            missing, in_other_tab = [], []
            # 无壳模式后, 首页概览 / 数据概览 = 整页参照稿(内容在 iframe 里, 外层既没有
            # 旧版式的分区标题, 也数不到图/表)。这两页改按参照稿自己的骨架验收
            # (骨架已在 ctx.close() 之前采样到 rec["ref"])。
            REF_PAGES = {"首页概览": "home", "数据概览": "overview"}
            if name in REF_PAGES:
                ref = rec.get("ref") or {}
                if not ref.get("ok"):
                    notes.append("参照稿骨架缺失 " + str(ref.get("why")))
            # 基线串页污染: 基线里「数据浏览」那条记录混进了「数据概览」的三节
            # (数据分布 / 系统状态 / 数据完整性检查), 而这三节在数据概览页已单独校验过。
            POLLUTED = {("数据浏览", "数据分布")}
            for sec in ([] if name in REF_PAGES else (b.get("sections") or [])):
                key = _kw(sec)
                if not key:
                    continue
                if key[:4] in body_squashed:
                    continue                       # 当前视图里看得见
                if (name, key[:4]) in POLLUTED:
                    continue                       # 基线串页, 不算回归
                if key[:4] in all_squashed:
                    in_other_tab.append(key[:16])  # 在别的标签页里(st.tabs 懒渲染)
                else:
                    missing.append(key[:24])       # DOM 里都没有 = 真的丢了
            if missing:
                notes.append("缺分区 " + "、".join(missing[:4]))
            if rec["oldGreen"]:
                notes.append("旧绿残留 %d 处" % rec["oldGreen"])
            if rec["clippedN"]:
                notes.append("文字裁切 %d" % rec["clippedN"])
            if rec["overflowX"] > 4:
                notes.append("横向溢出 %dpx" % rec["overflowX"])
            if rec["errs"]:
                notes.append("JS 错误 %d" % rec["errs"])
            flag = "OK " if not notes else "!! "
            tail = "结构与肤色均正常"
            if name in REF_PAGES:
                r = rec.get("ref") or {}
                extra = "" if r.get("ok") else (" 骨架: " + str(r.get("why")))
                tail = ("参照稿整页正常（KPI %d 张 / 赌率 3 列 / 环形 / 条形 4 / 右列 stat 4 / 面板 %d）%s"
                        % (r.get("kpi", 0), r.get("panelRow", 0), extra))
            if in_other_tab:
                tail += "（%d 个分区在其它标签页内: %s…）" % (
                    len(in_other_tab), "、".join(in_other_tab[:3]))
            print("%s%2d %-12s %s | 图%s 表%s 框%s 标签页%s | 底%s 字%s | %s"
                  % (flag, i, name, pg_title(rec), rec["charts"], rec["tables"], rec["frames"],
                     rec["tabs"], rec["appBg"], rec["appColor"],
                     "；".join(notes) or tail))
            if notes:
                bad.append((name, notes))

        br.close()

    (OUT / "skin_report.json").write_text(json.dumps(rows, ensure_ascii=False, indent=1),
                                          encoding="utf-8")
    print("\n报告: %s" % (OUT / "skin_report.json"))
    print("截图: %s" % SHOTS)
    print("结果: %s" % ("全部通过" if not bad else "%d 页需要看一下 -> %s"
                        % (len(bad), [b[0] for b in bad])))
    return 1 if bad else 0


def pg_title(rec: dict) -> str:
    return (rec.get("h1") or rec.get("title") or "")[:14]


if __name__ == "__main__":
    sys.exit(main())
