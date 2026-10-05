# -*- coding: utf-8 -*-
"""参照稿 1:1 复刻层: 主视区(三维球场舞台 + KPI + 焦点赛事 + 覆盖率 + 右列卡片)。

为什么单独一个模块?
    这份版式的每一个值(玻璃边缘的 mask-composite 渐变、光晕半径、舞台遮罩、
    卡片圆角与阴影)都是从参照稿 index.html 里逐字抄下来的, 与 dash.py 里那套
    「按主题令牌生成」的组件不是一条路子。分开放, 复刻层改动不会外溢到其它页面。

主题: 参照稿自带三套(白天 theme-day / 黄昏 theme-sunset / 夜晚 theme-night),
    这里按当前 Streamlit 主题切 body 的 class, 变量整块搬过来。
"""
import html as _html

import streamlit.components.v1 as components

_THEME_CLASS = {"light": "theme-day", "dark": "theme-sunset", "night": "theme-night"}

# ---- 三套主题变量(逐字来自参照稿) ----
_VARS = {
    "theme-day": """
--bg:linear-gradient(165deg,#eef5fd 0%,#dcebfa 30%,#cfe3f7 55%,#dcebfa 78%,#e8f3fc 100%);
--side:rgba(255,255,255,.34);--line:rgba(255,255,255,.92);--hair:rgba(255,255,255,.72);
--text:#17395f;--sub:#5e82a8;
--accent-grad:linear-gradient(135deg,#57a0ff,#2e6fe6);--accent-solid:#2e7cf0;
--glow:0 5px 14px rgba(59,130,246,.38);--track:#d7e6f6;--green:#17b26a;
--ring1:#3f8dff;--ring2:#c2e0ff;--halo-ring:rgba(90,190,255,.55);--halo-glow:rgba(90,190,255,.30);
--img-filter:saturate(1.03);
--veil:linear-gradient(180deg,rgba(255,255,255,.30),rgba(255,255,255,0) 42%,rgba(255,255,255,.14));
--num-glow:none;--dot-y:#f5a83c;--dot-g:#3ecf6e;--glass-hi:rgba(255,255,255,.95);
--glass-rim:linear-gradient(155deg,rgba(255,255,255,.98) 0%,rgba(255,255,255,.28) 38%,rgba(150,195,250,.55) 78%,rgba(255,255,255,.85) 100%);
--glass-sheen:linear-gradient(118deg,rgba(255,255,255,.55) 0%,rgba(255,255,255,.10) 26%,rgba(255,255,255,0) 44%);
--glass-outer:0 16px 38px rgba(96,150,220,.20),0 2px 6px rgba(96,150,220,.10);
--glass-inner:inset 0 1.5px 2px rgba(255,255,255,.95),inset 0 -8px 18px rgba(255,255,255,.18);
--card-bg:linear-gradient(155deg,rgba(255,255,255,.72) 0%,rgba(255,255,255,.42) 48%,rgba(255,255,255,.55) 100%);
--donut-core:linear-gradient(160deg,rgba(255,255,255,.92),rgba(255,255,255,.72));
""",
    "theme-sunset": """
--bg:radial-gradient(58% 38% at 72% 0%,rgba(255,224,175,.95),transparent 62%),radial-gradient(46% 32% at 18% 6%,rgba(255,196,148,.85),transparent 65%),radial-gradient(64% 44% at 88% 34%,rgba(255,158,104,.55),transparent 70%),radial-gradient(50% 36% at 8% 42%,rgba(255,178,120,.5),transparent 70%),linear-gradient(160deg,#f2a06b 0%,#e97f5f 62%,#d97a6e 100%);
--side:rgba(255,228,190,.32);--line:rgba(255,236,205,.92);--hair:rgba(255,232,198,.75);
--text:#4e2a0a;--sub:#9a6234;
--accent-grad:linear-gradient(135deg,#ffc257,#ee7d2d);--accent-solid:#ee8430;
--glow:0 5px 16px rgba(238,132,48,.5);--track:rgba(125,70,20,.20);--green:#84c53e;
--ring1:#f6a93b;--ring2:#ffe2a6;--halo-ring:rgba(255,205,115,.65);--halo-glow:rgba(255,175,85,.38);
--img-filter:sepia(.35) saturate(1.5) hue-rotate(-12deg) brightness(1.0);
--veil:linear-gradient(200deg,rgba(255,170,90,.22),rgba(255,120,60,.06) 55%,rgba(150,60,20,.16));
--num-glow:none;--dot-y:#ffb84d;--dot-g:#8fd14f;--glass-hi:rgba(255,252,238,.95);
--glass-rim:linear-gradient(155deg,rgba(255,250,228,.98) 0%,rgba(255,214,150,.30) 40%,rgba(255,170,90,.60) 80%,rgba(255,238,200,.90) 100%);
--glass-sheen:linear-gradient(118deg,rgba(255,248,222,.70) 0%,rgba(255,224,170,.12) 28%,rgba(255,224,170,0) 46%);
--glass-outer:0 16px 38px rgba(190,100,40,.30),0 0 30px rgba(255,170,85,.38);
--glass-inner:inset 0 1.5px 2px rgba(255,252,238,.95),inset 0 -8px 20px rgba(255,196,128,.25);
--card-bg:linear-gradient(155deg,rgba(255,240,206,.66) 0%,rgba(255,214,158,.38) 48%,rgba(255,226,182,.52) 100%);
--donut-core:linear-gradient(160deg,rgba(255,255,255,.92),rgba(255,255,255,.72));
""",
    "theme-night": """
--bg:linear-gradient(165deg,#0a1730 0%,#0f2547 55%,#0b1e3c 100%);
--side:rgba(14,36,68,.45);--line:rgba(110,180,255,.30);--hair:rgba(110,180,255,.22);
--text:#eaf4ff;--sub:#8fb0d4;
--accent-grad:linear-gradient(135deg,#22d3ee,#2f6fe6);--accent-solid:#38bdf8;
--glow:0 5px 16px rgba(34,211,238,.45);--track:rgba(255,255,255,.14);--green:#34d399;
--ring1:#38bdf8;--ring2:#155e9e;--halo-ring:rgba(80,220,255,.5);--halo-glow:rgba(60,200,255,.28);
--img-filter:brightness(.5) saturate(1.15) contrast(1.08);
--veil:linear-gradient(180deg,rgba(6,16,38,.5),rgba(6,16,38,.15) 50%,rgba(6,16,38,.45));
--num-glow:0 0 14px rgba(120,210,255,.5);--dot-y:#fbbf24;--dot-g:#34d399;--glass-hi:rgba(160,220,255,.35);
--glass-rim:linear-gradient(155deg,rgba(170,225,255,.70) 0%,rgba(80,140,220,.15) 40%,rgba(34,211,238,.45) 100%);
--glass-sheen:linear-gradient(118deg,rgba(180,230,255,.18) 0%,rgba(255,255,255,0) 40%);
--glass-outer:0 16px 38px rgba(0,10,30,.5),0 0 24px rgba(34,211,238,.14);
--glass-inner:inset 0 1.5px 2px rgba(160,220,255,.35),inset 0 -8px 20px rgba(20,60,120,.25);
--card-bg:linear-gradient(155deg,rgba(30,62,110,.62) 0%,rgba(16,38,72,.50) 50%,rgba(24,52,94,.58) 100%);
--donut-core:linear-gradient(160deg,rgba(40,80,140,.9),rgba(24,52,96,.85));
""",
}

# ---- 结构样式(逐字来自参照稿的 .main / .g / .kpi / .focus / .bars / .rightcol 段) ----
_CSS = """
:root{__VARS__}
*{margin:0;padding:0;box-sizing:border-box}
html,body{background:transparent}
body{font-family:"PingFang SC","Microsoft YaHei",sans-serif;color:var(--text);overflow-x:hidden}
.ic{width:15px;height:15px;stroke:currentColor;fill:none;stroke-width:1.8;stroke-linecap:round;stroke-linejoin:round;flex:none}
.chev{opacity:.5;width:14px;height:14px}
.main{position:relative;min-height:__H__px;overflow:hidden;border-radius:24px}
.stage-bg{position:absolute;inset:-20px;width:calc(100% + 40px);height:calc(100% + 40px);object-fit:cover;object-position:center 45%;-webkit-mask-image:radial-gradient(118% 118% at 50% 45%,#000 52%,transparent 92%);mask-image:radial-gradient(118% 118% at 50% 45%,#000 52%,transparent 92%);filter:var(--img-filter);transition:filter .8s}
.veil{position:absolute;inset:0;background:var(--veil);pointer-events:none;transition:background .8s}
.halo{position:absolute;left:47%;top:57%;width:60%;height:44%;transform:translate(-50%,-50%);border-radius:50%;border:2px solid var(--halo-ring);box-shadow:0 0 36px var(--halo-glow),inset 0 0 50px var(--halo-glow);opacity:.85;pointer-events:none;transition:all .8s}
.halo::before{content:"";position:absolute;inset:-30px;border-radius:50%;border:1.5px solid var(--halo-ring);opacity:.45}
.halo::after{content:"";position:absolute;inset:-70px;border-radius:50%;background:radial-gradient(50% 50% at 50% 50%,var(--halo-glow),transparent 70%);filter:blur(6px)}
.main-grid{position:relative;z-index:2;display:grid;grid-template-columns:1fr 300px;gap:15px;padding:15px 17px 17px;min-height:__H__px}
.left-col{display:grid;grid-template-rows:auto 1fr auto;gap:15px}
.g{position:relative;border-radius:18px;background:var(--card-bg);backdrop-filter:blur(24px) saturate(190%) brightness(1.04);-webkit-backdrop-filter:blur(24px) saturate(190%) brightness(1.04);box-shadow:var(--glass-outer),var(--glass-inner);transition:background .6s,box-shadow .6s}
.g::before{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;background:var(--glass-sheen)}
.g::after{content:"";position:absolute;inset:0;border-radius:inherit;pointer-events:none;padding:1.4px;background:var(--glass-rim);-webkit-mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);-webkit-mask-composite:xor;mask:linear-gradient(#000 0 0) content-box,linear-gradient(#000 0 0);mask-composite:exclude}
.g>*{position:relative;z-index:1}
.kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:15px}
.kpi{padding:13px 17px 12px;position:relative}
.kpi .tag{display:flex;align-items:center;gap:6px;font-size:10.5px;color:var(--sub)}
.kpi .tag i{width:13px;height:13px;border-radius:4px;background:var(--accent-grad);flex:none;box-shadow:var(--glow)}
.kpi .num{font-size:31px;font-weight:800;letter-spacing:.4px;margin:3px 0 5px;font-variant-numeric:tabular-nums;text-shadow:var(--num-glow);white-space:nowrap}
.kpi .num.sm{font-size:24px}
.kpi .trend{font-size:10.5px;color:var(--green);font-weight:600}
.kpi .plus{position:absolute;top:12px;right:12px;width:27px;height:27px;border-radius:50%;border:none;cursor:pointer;color:#fff;background:var(--accent-grad);font-size:16px;line-height:1;box-shadow:var(--glow)}
.bottom{display:grid;grid-template-columns:1.42fr 1fr;gap:15px}
.focus{padding:14px 20px 12px}
.focus h3,.todo h3{font-size:15px;font-weight:800;display:flex;align-items:center;justify-content:space-between}
.focus h3 .chev,.todo h3 .chev{opacity:.5;width:14px;height:14px}
.odds{display:flex;align-items:center;margin:11px 0 9px}
.odd{flex:1;text-align:center;padding:2px 6px}
.odd+.odd{border-left:1px solid var(--hair)}
.odd .k{font-size:11px;color:var(--sub)}
.odd .v{font-size:26px;font-weight:800;margin:2px 0;text-shadow:var(--num-glow)}
.odd .s{font-size:9.5px;color:var(--sub);opacity:.8}
.donut{width:104px;height:104px;border-radius:50%;flex:none;position:relative;margin-left:10px;background:conic-gradient(var(--ring2) 0 __SEG__%,var(--ring1) __SEG__% 100%);box-shadow:var(--glow)}
.donut::before{content:"";position:absolute;inset:15px;border-radius:50%;background:var(--donut-core);box-shadow:inset 0 1.5px 2px rgba(255,255,255,.8),0 2px 8px rgba(0,0,0,.06)}
.donut::after{content:"\\276F";position:absolute;inset:0;display:grid;place-items:center;font-size:24px;font-weight:800;color:var(--accent-solid)}
.donut .dot{position:absolute;top:5px;right:15px;width:10px;height:10px;border-radius:50%;background:#fff;box-shadow:0 0 0 3px var(--ring1)}
.mini-stats{display:flex;border-top:1px solid var(--hair);padding-top:9px}
.mini-stats div{flex:1;text-align:center}
.mini-stats .k{font-size:9.5px;color:var(--sub)}
.mini-stats .v{font-size:12px;font-weight:700;margin-top:2px}
.mini-stats div+div{border-left:1px solid var(--hair)}
.bars{padding:15px 20px;display:flex;flex-direction:column;justify-content:space-around;gap:12px}
.brow{display:flex;align-items:center;gap:10px}
.brow .bl{width:96px;flex:none;font-size:11.5px;color:var(--sub);display:flex;align-items:center;gap:6px}
.brow .bl i{width:6px;height:6px;border-radius:2px;background:var(--accent-grad);flex:none}
.brow .bar{flex:1}
.brow .bp{width:44px;flex:none;text-align:right;font-size:12px;font-weight:700}
.bar{height:7px;border-radius:4px;background:var(--track);overflow:hidden}
.bar i{display:block;height:100%;border-radius:4px;background:var(--accent-grad);transition:width .6s,background .6s}
.rightcol{display:flex;flex-direction:column;gap:12px}
.card{padding:13px 15px}
.sq{width:37px;height:37px;border-radius:11px;display:grid;place-items:center;color:#fff;background:var(--accent-grad);flex:none;box-shadow:var(--glow),inset 0 1.5px 2px rgba(255,255,255,.5)}
.sq .ic{width:17px;height:17px}
.user-card{display:flex;align-items:center;gap:11px}
.user-card .info{flex:1;min-width:0}
.user-card .lbl{font-size:11px;color:var(--sub);margin-bottom:7px}
.stat{display:flex;align-items:center;gap:11px}
.stat .info{flex:1;min-width:0}
.stat .pct{font-size:20px;font-weight:800;text-shadow:var(--num-glow)}
.stat .bar{margin-top:6px}
.todo{flex:1;display:flex;flex-direction:column;min-height:0}
.todo h3 a{font-size:10.5px;color:var(--accent-solid);text-decoration:none;font-weight:600}
.todo ul{flex:1;list-style:none;margin-top:6px;display:flex;flex-direction:column;justify-content:space-evenly}
.todo li{display:flex;align-items:center;gap:9px;font-size:11.5px;color:var(--text);opacity:.88;padding:4px 0}
.todo li::before{content:"";width:8px;height:8px;border-radius:50%;flex:none}
.todo li.y::before{background:var(--dot-y)}
.todo li.g::before{background:var(--dot-g)}
.page-foot{position:relative;z-index:1;margin:10px 4px 2px;font-size:10px;color:var(--sub);opacity:.6;line-height:1.9}
"""

_SPRITE = (
    '<svg style="position:absolute;width:0;height:0" aria-hidden="true">'
    '<symbol id="i-chev" viewBox="0 0 24 24"><path d="M6 9l6 6 6-6"/></symbol>'
    '<symbol id="i-doc" viewBox="0 0 24 24"><path d="M6 3h9l4 4v14H6z"/>'
    '<path d="M9 12h6M9 16h6"/></symbol>'
    '<symbol id="i-chart" viewBox="0 0 24 24"><path d="M4 20V10M10 20V4M16 20v-7"/>'
    '<path d="M2 20h20"/></symbol>'
    '<symbol id="i-clock" viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5"/>'
    '<path d="M12 7v5l3.5 2"/></symbol>'
    '<symbol id="i-player" viewBox="0 0 24 24"><circle cx="12" cy="8" r="3.5"/>'
    '<path d="M5 20c1.5-4 4-5.5 7-5.5s5.5 1.5 7 5.5"/></symbol>'
    '<symbol id="i-db" viewBox="0 0 24 24"><ellipse cx="12" cy="6" rx="7" ry="3"/>'
    '<path d="M5 6v12c0 1.7 3.1 3 7 3s7-1.3 7-3V6"/><path d="M5 12c0 1.7 3.1 3 7 3s7-1.3 7-3"/></symbol>'
    '</svg>'
)


def _e(v):
    return _html.escape(str(v), quote=True)


def _ic(name, cls="ic"):
    return f'<svg class="{cls}"><use href="#{name}"/></svg>'


def render(*, kpis, stage, focus, bars, side, foot="", height=800, theme="light"):
    """渲染参照稿主视区。

    kpis  : [{tag, num, trend, plus(bool)}]            四张 KPI 玻璃卡
    stage : 舞台底图 URL(相对 /app/static/...)
    focus : {title, odds:[{k,v,s}], seg:环形占比, mini:[{k,v}]}
    bars  : {rows:[{label,pct,val}]}                    覆盖率卡
    side  : {slim:{icon,label,pct}, stats:[{icon,pct}], todo:{title,link,rows:[{tone,text}]}}
    """
    h = max(560, int(height))
    css = _CSS.replace("__VARS__", _VARS.get(_THEME_CLASS.get(theme, "theme-day"),
                                              _VARS["theme-day"]))
    css = css.replace("__H__", str(h)).replace("__SEG__",
                                               f"{100 - float(focus.get('seg', 66.6)):.1f}")

    kpi_html = "".join(
        '<div class="kpi g"><div class="tag"><i></i>{tag}</div>'
        '<div class="num{sm}">{num}</div><div class="trend">{trend}</div>{plus}</div>'.format(
            tag=_e(k.get("tag", "")), num=_e(k.get("num", "")), trend=_e(k.get("trend", "")),
            sm=" sm" if len(str(k.get("num", ""))) > 6 else "",
            plus='<button class="plus">+</button>' if k.get("plus") else "")
        for k in kpis)

    odds_html = "".join(
        f'<div class="odd"><div class="k">{_e(o.get("k",""))}</div>'
        f'<div class="v">{_e(o.get("v",""))}</div>'
        f'<div class="s">{_e(o.get("s",""))}</div></div>' for o in focus.get("odds", []))

    mini_html = "".join(
        f'<div><div class="k">{_e(m.get("k",""))}</div>'
        f'<div class="v">{_e(m.get("v",""))}</div></div>' for m in focus.get("mini", []))

    bars_html = "".join(
        f'<div class="brow"><span class="bl"><i></i>{_e(b.get("label",""))}</span>'
        f'<div class="bar"><i style="width:{float(b.get("pct",0)):.1f}%"></i></div>'
        f'<span class="bp">{_e(b.get("val",""))}</span></div>' for b in bars.get("rows", []))

    slim = side.get("slim", {})
    slim_html = (
        f'<div class="card g user-card"><div class="sq">{_ic(slim.get("icon","i-player"))}</div>'
        f'<div class="info"><div class="lbl">{_e(slim.get("label",""))} · {_e(slim.get("val",""))}</div>'
        f'<div class="bar"><i style="width:{float(slim.get("pct",0)):.1f}%"></i></div></div>'
        f'{_ic("i-chev", "ic chev")}</div>') if slim else ""

    stat_html = "".join(
        f'<div class="card g stat"><div class="sq">{_ic(s.get("icon","i-doc"))}</div>'
        f'<div class="info"><div class="pct">{_e(s.get("pct",""))}%</div>'
        f'<div class="bar"><i style="width:{float(s.get("pct",0)):.1f}%"></i></div></div>'
        f'{_ic("i-chev", "ic chev")}</div>' for s in side.get("stats", []))

    todo = side.get("todo", {})
    todo_html = (
        f'<div class="card g todo"><h3>{_e(todo.get("title",""))}'
        f'<a href="#">{_e(todo.get("link",""))}</a></h3><ul>' +
        "".join(f'<li class="{_e(r.get("tone","g"))}">{_e(r.get("text",""))}</li>'
                for r in todo.get("rows", [])) + "</ul></div>") if todo else ""

    html = f"""<!DOCTYPE html><html><head><meta charset="UTF-8"><style>{css}</style></head>
<body class="{_THEME_CLASS.get(theme, 'theme-day')}">{_SPRITE}
<main class="main">
  <img class="stage-bg" src="{_e(stage)}" alt="" onerror="this.style.display='none'">
  <div class="veil"></div><div class="halo"></div>
  <div class="main-grid">
    <div class="left-col">
      <section class="kpis">{kpi_html}</section>
      <div></div>
      <section class="bottom">
        <div class="focus g"><h3>{_e(focus.get('title',''))} {_ic('i-chev', 'ic chev')}</h3>
          <div class="odds">{odds_html}<div class="donut"><span class="dot"></span></div></div>
          <div class="mini-stats">{mini_html}</div></div>
        <div class="bars g">{bars_html}</div>
      </section>
    </div>
    <aside class="rightcol">{slim_html}{stat_html}{todo_html}</aside>
  </div>
</main>
{f'<div class="page-foot">{foot}</div>' if foot else ''}
</body></html>"""
    components.html(html, height=h + (34 if foot else 8), scrolling=False)
