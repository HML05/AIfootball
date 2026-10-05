# -*- coding: utf-8 -*-
"""灵动版块组件 (blocks.py)

Streamlit 原生组件无法实现入场动效 / 数字滚动 / 走马灯, 因此这里用
``streamlit.components.v1.html`` 渲染"自包含"的 HTML+CSS+JS 版块:
每个版块在独立 iframe 内, 自带主题色与字体, 不污染页面其余部分。

设计依据: taste-skill v2 (§4.4 材质 / §4.5 交互状态 / §10 版块词汇)
  · 单一强调色(来自 theme.T), 不用装饰性多色
  · 入场: 交错淡入上移(stagger), 不用"一次性全部弹出"
  · 数字: count-up 滚动(有意义的动效: 传达"数据在增长")
  · hover: 轻微抬升 + 强调色描边(反馈), 不用夸张位移
  · 尊重 prefers-reduced-motion: 关闭所有动效

对外 API:
    hero_band(title, subtitle, stats, badge=None, height=None)
    stat_band(items, height=None)
    bento_grid(cells, height=None)
    ticker(items, height=None)
"""
from __future__ import annotations

import html as _html

import streamlit as st

try:
    from theme import T, FONT_SANS
except Exception:                                     # pragma: no cover
    T, FONT_SANS = {}, "sans-serif"

try:
    import streamlit.components.v1 as components
except Exception:                                     # pragma: no cover
    components = None

BG0 = T.get("bg0", "#090d0b")
BG1 = T.get("bg1", "#0b110e")
BG2 = T.get("bg2", "#0f1512")
BG3 = T.get("bg3", "#17211c")
ACCENT = T.get("accent", "#2f86e0")
ACCENT2 = T.get("accent2", "#26a877")
T1 = T.get("t1", "#e9f1ec")
T2 = T.get("t2", "#a0b2a8")
T3 = T.get("t3", "#7c8e84")
LINE = T.get("line", "#1e2a24")
SAMPLES = {1: 2, 2: 3, 3: 4, 4: 5, 5: 6, 6: 5, 7: 4}   # 供 CSS 交错延迟使用


def _rgba(key: str, alpha: float, fallback: str) -> str:
    """取令牌色并转成同色相的低透明度 rgba(用于柔光 / 微染 / 光晕)。

    为什么要这层? 本文件里的极光层、徽标描边、悬停光晕都需要"预乘 alpha 的强调色",
    而令牌里存的是实色(#2f86e0)。写死 rgba 会在换肤后留下旧色相的辉光(实测踩过),
    因此统一从令牌派生 —— 主题一切换, 这些辉光跟着换。
    """
    c = str(T.get(key, fallback) or fallback).strip()
    if len(c) == 7 and c.startswith("#"):
        try:
            r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            return f"rgba({r},{g},{b},{alpha})"
        except ValueError:
            pass
    return fallback

def _glass() -> dict:
    """液态玻璃令牌(Apple Liquid Glass), **每次调用时**从 theme.T 现取。

    为什么必须是函数: 换肤(apply_theme)是原地更新 T 字典, 模块级缓存的字符串
    会停在上一次的主题上(深色主题的玻璃底会留在日场里, 实测踩过)。
    兜底值 = 设计说明里的原始写法。
    """
    return {
        "lite": str(T.get("glass_lite", "rgba(255,255,255,0.15)")),
        "mid": str(T.get("glass_mid", "rgba(255,255,255,0.28)")),
        "edge": str(T.get("glass_edge", "rgba(255,255,255,0.62)")),
        "blur": str(T.get("glass_blur", "blur(8px) saturate(180%)")),
        "shadow": str(T.get("glass_shadow",
                            "inset 0 1px 1px rgba(255,255,255,0.80), "
                            "0 8px 32px rgba(59,130,246,0.12)"))
                  + ", 0 0 0 1px " + str(T.get("line", "rgba(30,64,110,0.14)")),
        "r": str(T.get("r4", "24px")),
    }


def _base_css() -> str:
    """基础样式(每次渲染时按当前主题令牌生成)。

    注意: 这里必须是**函数**而不是模块级常量 —— 主题切换后 theme.apply_theme()
    会把新令牌同步到本模块的 BG1/BG2/ACCENT..., 若 CSS 在导入时就固化,
    浅色主题下卡片仍会是深色(实测踩过这个坑)。
    """
    g = _glass()
    return f"""
:root {{ color-scheme: light; }}
* {{ box-sizing: border-box; }}
html, body {{
    margin: 0; padding: 0; background: transparent !important;
    font-family: {FONT_SANS};
    -webkit-font-smoothing: antialiased;
    color: {T1};
}}
.wrap {{ position: relative; overflow: hidden; }}
.card {{
    background: linear-gradient(155deg, {g['mid']} 0%, {g['lite']} 100%);
    border: 1px solid {g['edge']}; border-radius: {g['r']};
    backdrop-filter: {g['blur']}; -webkit-backdrop-filter: {g['blur']};
    box-shadow: {g['shadow']};
    transition: border-color .25s ease, transform .25s ease, background .25s ease;
}}
.card:hover {{ border-color: {ACCENT}; transform: translateY(-3px); }}
/* Material Symbols 连字图标: dash/blocks 的卡片渲染在**独立 iframe** 里,
   theme.py 的页面级 §22 规则进不来, 短代码会退化成裸文字(实测 "verified" 直接显字) —— 
   所以图标字体必须在 iframe 自己的基础样式里声明一次。 */
@font-face {{
    font-family: 'Material Symbols Rounded';
    font-style: normal; font-weight: 100 700; font-display: block;
    src: url('https://fonts.gstatic.com/s/materialsymbolsrounded/v211/syl0-zNym6YjUruM-QrEh7-nyTnjDwKNJ_190FjpZIvDmUSVOK7BDB_Qb9vUSzq3wzLK-P0J-V_Zs-QtQth3-jOcbTCVpeRL2w5rwZu2rIelXxeJKJBiCa8.woff2') format('woff2');
}}
.msr, .material-symbols-rounded, [data-testid="stIconMaterial"] {{
    font-family: 'Material Symbols Rounded' !important;
    font-weight: normal; font-style: normal; line-height: 1;
    letter-spacing: normal; text-transform: none; display: inline-block;
    white-space: nowrap; word-wrap: normal; direction: ltr;
    font-variation-settings: 'FILL' 0, 'wght' 400, 'GRAD' 0, 'opsz' 24;
    -webkit-font-feature-settings: 'liga'; -webkit-font-smoothing: antialiased;
}}
@keyframes riseIn {{
    from {{ opacity: 0; transform: translateY(14px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
.rise {{ opacity: 0; animation: riseIn .6s cubic-bezier(.22,.61,.36,1) forwards; }}
@keyframes auroraShift {{
    0%   {{ transform: translate3d(-4%, -3%, 0) scale(1.05); }}
    50%  {{ transform: translate3d(4%, 3%, 0) scale(1.12); }}
    100% {{ transform: translate3d(-4%, -3%, 0) scale(1.05); }}
}}
@keyframes tickerMove {{
    from {{ transform: translateX(0); }}
    to   {{ transform: translateX(-50%); }}
}}
@media (prefers-reduced-motion: reduce) {{
    .rise {{ animation: none; opacity: 1; }}
    .aurora {{ animation: none !important; }}
    .ticker-track {{ animation: none !important; }}
}}
"""


def _is_dark() -> bool:
    """当前是否深色主题(浅色主题下噪点/光晕要更弱, 否则页面发脏)"""
    try:
        from theme import current_theme
        return current_theme() == "dark"
    except Exception:                                 # pragma: no cover
        return True


def _render(html_body: str, height: int):
    """渲染一个自包含版块。

    height 只是**初始高度**(避免加载瞬间抖动); 真正的做法是让 iframe 内容
    自己测量高度并通知 Streamlit 调整 —— 否则内容一多就会被裁掉(卡片底部被切)。
    这里用 Streamlit 官方约定的 ``streamlit:setFrameHeight`` 消息实现自适应:
    iframe 是同源 srcdoc, 直接读 body.scrollHeight 即可, 并在字体/动效稳定后
    再测一次(字体加载会改变换行)。
    """
    if components is None:                            # pragma: no cover
        st.markdown(html_body, unsafe_allow_html=True)
        return
    autofit = """
    <script>
      (function () {
        function fit() {
          var h = Math.max(
            document.body.scrollHeight,
            document.documentElement.scrollHeight,
            document.body.getBoundingClientRect().height
          );
          if (!h) return;
          h = Math.ceil(h) + 2;
          try { window.parent.postMessage({type: 'streamlit:setFrameHeight', height: h}, '*'); }
          catch (e) {}
          try { if (window.frameElement) window.frameElement.style.height = h + 'px'; }
          catch (e) {}
        }
        window.addEventListener('load', fit);
        document.addEventListener('DOMContentLoaded', fit);
        // 动效(0.6s 上移淡入)结束后再测一次, 避免测量到动画中间态
        setTimeout(fit, 120);
        setTimeout(fit, 700);
        setTimeout(fit, 1500);
        if (window.ResizeObserver) {
          try { new ResizeObserver(fit).observe(document.body); } catch (e) {}
        }
      })();
    </script>
    """
    doc = (f"<!DOCTYPE html><html><head><meta charset='utf-8'>"
           f"<style>{_base_css()}</style></head><body>{html_body}{autofit}</body></html>")
    components.html(doc, height=height, scrolling=False)


def _esc(v):
    return _html.escape(str(v))


# ============ 1. 英雄版块(极光背景 + 交错入场 + 数字滚动) ============
def hero_band(title, subtitle, stats, badge=None, height=None):
    """stats: [(数值字符串, 标签), ...] —— 数值中的数字会自动 count-up"""
    h = height or (300 if not badge else 330)
    stat_html = ""
    for i, (val, label) in enumerate(stats):
        stat_html += f"""
        <div class="stat rise" style="animation-delay:{0.35 + i * 0.09:.2f}s">
          <div class="stat-v" data-count="{_esc(val)}">{_esc(val)}</div>
          <div class="stat-l">{_esc(label)}</div>
        </div>"""
    badge_html = (f'<div class="badge rise" style="animation-delay:.12s">'
                  f'{_esc(badge)}</div>') if badge else ""
    _render(f"""
    <div class="wrap" style="height:{h - 16}px;border-radius:18px;">
      <div class="aurora"></div>
      <div class="grid-lines"></div>
      <div class="hero-inner">
        {badge_html}
        <h1 class="rise" style="animation-delay:.2s">{_esc(title)}</h1>
        <p class="rise" style="animation-delay:.28s">{_esc(subtitle)}</p>
        <div class="stats">{stat_html}</div>
      </div>
    </div>
    <style>
      .wrap {{ border: 1px solid {LINE}; }}
      .aurora {{
        position: absolute; inset: -30%;
        background:
          radial-gradient(closest-side, {_rgba('accent', 0.20, 'rgba(47,134,224,0.20)')}, transparent 70%) 22% 18%/48% 60% no-repeat,
          radial-gradient(closest-side, {_rgba('accent2', 0.16, 'rgba(206,62,30,0.16)')}, transparent 70%) 78% 78%/52% 62% no-repeat,
          radial-gradient(closest-side, {_rgba('cool', 0.09, 'rgba(63,124,168,0.09)')}, transparent 70%) 60% 8%/40% 50% no-repeat;
        filter: blur(18px);
        animation: auroraShift 22s ease-in-out infinite;
      }}
      .grid-lines {{
        position: absolute; inset: 0; opacity: .5;
        background-image:
          linear-gradient({LINE} 1px, transparent 1px),
          linear-gradient(90deg, {LINE} 1px, transparent 1px);
        background-size: 48px 48px, 48px 48px;
        mask-image: radial-gradient(ellipse 80% 70% at 30% 40%, #000 20%, transparent 75%);
      }}
      .hero-inner {{ position: relative; padding: clamp(18px, 2.4vw, 30px) clamp(18px, 2.6vw, 34px) clamp(16px, 2vw, 26px); }}
      .badge {{
        display: inline-block; font-size: 11px; letter-spacing: .12em; text-transform: uppercase;
        color: {ACCENT}; border: 1px solid {_rgba('accent', 0.32, 'rgba(47,134,224,0.32)')}; background: {_rgba('accent', 0.10, 'rgba(47,134,224,0.10)')};
        padding: 3px 10px; border-radius: 6px; font-weight: 600;
      }}
      h1 {{ margin: 14px 0 0; font-size: clamp(19px, 2.3vw, 30px); line-height: 1.15;
            letter-spacing: -0.02em; font-weight: 700; color: {T1}; max-width: 22ch; }}
      p {{ margin: 10px 0 0; color: {T2}; font-size: clamp(12px, 1.1vw, 13.5px);
           line-height: 1.6; max-width: 62ch; }}
      .stats {{ display: flex; gap: clamp(16px, 3vw, 40px); margin-top: clamp(14px, 2vw, 24px);
                flex-wrap: wrap; }}
      .stat-v {{ font-size: clamp(19px, 2vw, 26px); font-weight: 700; color: {ACCENT};
                 font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}
      .stat-l {{ font-size: 11.5px; color: {T3}; margin-top: 3px;
                 text-transform: uppercase; letter-spacing: .06em; }}
    </style>
    <script>
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      document.querySelectorAll('[data-count]').forEach(el => {{
        const raw = el.getAttribute('data-count');
        const m = raw.match(/[\\d.,]+/);
        if (!m || reduce) return;
        const target = parseFloat(m[0].replace(/,/g, ''));
        if (!isFinite(target)) return;
        const prefix = raw.slice(0, m.index), suffix = raw.slice(m.index + m[0].length);
        const decimals = (m[0].split('.')[1] || '').length;
        let start = null;
        const dur = 900;
        function step(ts) {{
          if (!start) start = ts;
          const p = Math.min((ts - start) / dur, 1);
          const eased = 1 - Math.pow(1 - p, 3);
          const v = target * eased;
          el.textContent = prefix + v.toLocaleString('en-US',
              {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}}) + suffix;
          if (p < 1) requestAnimationFrame(step);
        }}
        el.textContent = prefix + (0).toFixed(decimals) + suffix;
        requestAnimationFrame(step);
      }});
    </script>
    """, h)


# ============ 2. 指标带(等宽, 数字滚动) ============
def stat_band(items, height=None):
    """items: [(数值, 标签, 说明), ...] 紧凑一行, 用分隔线而非卡片(高密度页面)"""
    h = height or 118
    cells = ""
    for i, it in enumerate(items):
        val, label = it[0], it[1]
        hint = it[2] if len(it) > 2 else None
        cells += f"""
        <div class="cell rise" style="animation-delay:{i * 0.06:.2f}s">
          <div class="v" data-count="{_esc(val)}">{_esc(val)}</div>
          <div class="l">{_esc(label)}</div>
          {f'<div class="h">{_esc(hint)}</div>' if hint else ''}
        </div>"""
    _render(f"""
    <div class="band card">{cells}</div>
    <style>
      .band {{ display: flex; padding: 16px 8px; flex-wrap: wrap; }}
      .cell {{ flex: 1 1 0; min-width: 130px; padding: 2px 20px; border-left: 1px solid {LINE}; }}
      .cell:first-child {{ border-left: none; }}
      .v {{ font-size: 23px; font-weight: 700; color: {T1};
            font-variant-numeric: tabular-nums; letter-spacing: -0.01em; }}
      .l {{ font-size: 11.5px; color: {T3}; margin-top: 4px;
            text-transform: uppercase; letter-spacing: .06em; }}
      .h {{ font-size: 11.5px; color: {T2}; margin-top: 6px; line-height: 1.5; }}
    </style>
    <script>
      const reduce = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
      document.querySelectorAll('[data-count]').forEach(el => {{
        const raw = el.getAttribute('data-count');
        const m = raw.match(/[\\d.,]+/);
        if (!m || reduce) return;
        const target = parseFloat(m[0].replace(/,/g, ''));
        if (!isFinite(target)) return;
        const prefix = raw.slice(0, m.index), suffix = raw.slice(m.index + m[0].length);
        const decimals = (m[0].split('.')[1] || '').length;
        let start = null;
        function step(ts) {{
          if (!start) start = ts;
          const p = Math.min((ts - start) / 850, 1);
          const v = target * (1 - Math.pow(1 - p, 3));
          el.textContent = prefix + v.toLocaleString('en-US',
              {{minimumFractionDigits: decimals, maximumFractionDigits: decimals}}) + suffix;
          if (p < 1) requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);
      }});
    </script>
    """, h)


# ============ 3. Bento 网格(非对称细胞 + 交错入场 + hover 描边) ============
def bento_grid(cells, height=None):
    """cells: [{'title','items','span'(1|2),'mark','kicker'}, ...]

    span=2 的卡片占两列宽(制造节奏, 避免"三张等宽卡"的模板感)。
    mark: 几何标记字符(✦ ◆ ▦ ⬡ 等)。不用 emoji, 也不用 Streamlit 的
          ``:material/x:`` 语法 —— 后者在 iframe 里会原样显示成文本。
    """
    # 先按"实际排版"分行: span=2 独占一行, 其余两两成行。
    # (早期版本用 (n+1)//2 估算行数, 遇到横跨两列的卡片会算少一行 -> 内容被裁掉)
    rows_cells, cur = [], []
    for c in cells:
        if int(c.get("span", 1)) == 2:
            if cur:
                rows_cells.append(cur)
                cur = []
            rows_cells.append([c])
        else:
            cur.append(c)
            if len(cur) == 2:
                rows_cells.append(cur)
                cur = []
    if cur:
        rows_cells.append(cur)

    if height is None:
        # 粗估: 卡片头(标记+眉标+标题) 约 108px, 每条列表项约 26px
        h = sum(108 + max(len(c.get("items", [])) for c in r) * 26 for r in rows_cells)
        h += 12 * max(0, len(rows_cells) - 1) + 10
        height = int(h)

    body = ""
    for i, c in enumerate(cells):
        span = int(c.get("span", 1))
        items = "".join(f"<li>{_esc(x)}</li>" for x in c.get("items", []))
        kicker = (f'<div class="k">{_esc(c["kicker"])}</div>' if c.get("kicker") else "")
        mark = c.get("mark", "✦")
        body += f"""
        <div class="card b rise{' span2' if span == 2 else ''}"
             style="animation-delay:{i * 0.08:.2f}s">
          <div class="ico">{_esc(mark)}</div>
          {kicker}
          <h3>{_esc(c.get('title', ''))}</h3>
          <ul>{items}</ul>
        </div>"""
    _render(f"""
    <div class="bento">{body}</div>
    <style>
      .bento {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
      .b {{ padding: 20px 22px 18px; position: relative; overflow: hidden; }}
      .b.span2 {{ grid-column: span 2; }}
      .b::after {{                       /* 悬停时的强调色光晕(taste §4.4 spotlight 简化版) */
        content: ""; position: absolute; inset: 0; opacity: 0;
        background: radial-gradient(220px 120px at 15% 0%, {_rgba('accent', 0.10, 'rgba(47,134,224,0.10)')}, transparent 70%);
        transition: opacity .25s ease; pointer-events: none;
      }}
      .b:hover::after {{ opacity: 1; }}
      .ico {{ font-size: 15px; line-height: 1; margin-bottom: 13px; color: {ACCENT};
              opacity: .9; }}
      .k {{ font-size: 10.5px; letter-spacing: .12em; text-transform: uppercase;
            color: {T3}; margin-bottom: 6px; }}
      h3 {{ margin: 0 0 10px; font-size: 15.5px; font-weight: 650; color: {T1};
            letter-spacing: -0.01em; }}
      ul {{ margin: 0; padding-left: 16px; }}
      li {{ color: {T2}; font-size: 12.8px; line-height: 1.85; }}
      li::marker {{ color: {T3}; }}
      /* 窄屏: Bento 退化为单列, 否则两列会把中文压成一行两三个字 */
      @media (max-width: 700px) {{
        .bento {{ grid-template-columns: 1fr; }}
        .b.span2 {{ grid-column: span 1; }}
        .b {{ padding: 16px 16px 14px; }}
      }}
    </style>
    """, h)


# ============ 4. 走马灯(单条, 用于数据源/赛事名) ============
def ticker(items, height=None):
    h = height or 56
    seq = "".join(f'<span class="tk">{_esc(x)}</span><span class="dot"></span>' for x in items)
    _render(f"""
    <div class="card tk-wrap"><div class="ticker-track">{seq}{seq}</div></div>
    <style>
      .tk-wrap {{ padding: 12px 0; overflow: hidden;
                  mask-image: linear-gradient(90deg, transparent, #000 8%, #000 92%, transparent); }}
      .ticker-track {{ display: inline-flex; align-items: center; white-space: nowrap;
                       animation: tickerMove 34s linear infinite; }}
      .tk {{ color: {T2}; font-size: 12.5px; letter-spacing: .04em; padding: 0 4px; }}
      .dot {{ width: 4px; height: 4px; border-radius: 50%; background: {ACCENT};
              opacity: .65; margin: 0 16px; display: inline-block; }}
      .tk-wrap:hover .ticker-track {{ animation-play-state: paused; }}
    </style>
    """, h)
