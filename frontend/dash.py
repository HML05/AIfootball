# -*- coding: utf-8 -*-
"""参照稿仪表盘组件 (dash.py)

用户给了一张后台 UI 参照稿(宝鸡市公路局巡检服务平台), 要求「高度模仿, 复刻图片 UI」。
参照稿的骨架是:

    顶栏(品牌 + 面包屑 | 消息 / 个人中心 / 退出系统)
    左侧栏(分组导航: 基础 / 操作 / 数据 / 管理)
    主区第 1 行: 4 张 KPI 卡(标签 + 大号数字 + 增量行 + 右上角图标砖)
    主区第 2 行: 快捷操作(图标按钮条) + 任务进度卡(3 行: 名称 + 编号 + 进度条 + 耗时)
    主区第 3 行: 大视区(地图) + 浮层状态胶囊×3   ｜  右列: 消息通知(染色卡片列表)

本模块把这套骨架的**版式与组件**实现出来, 数据一律取自本地库真实统计(不造数):

    topbar(...)          顶栏(原生 Streamlit: 面包屑 + 消息/个人中心/退出)
    kpi_row(items)       4 张 KPI 卡(图标砖 + 大号等宽数字 + 增量行)
    main_panel(...)      大视区(球场示意 + 标题 + 胶囊 + 底部浮层状态胶囊)
    progress_card(...)   进度卡(名称 + 编号 + 进度条 + 说明)
    notice_column(...)   右列消息通知(染色卡片 + 圆点 + 时间)
    quick_actions(...)   快捷操作(原生 Streamlit 按钮, 点一下切页, 不丢登录态)

为什么快捷操作和顶栏用原生组件而不是 iframe: 版块 iframe 里的链接会把整页重新加载,
而登录令牌只存在 Streamlit 会话里(session_state), 重新加载等于掉登录。所以凡是
**要触发动作**的组件都走原生控件, 只有纯展示的才放进 iframe。
"""
from __future__ import annotations

import streamlit as st

import blocks as B

try:                       # 令牌在渲染时读取(主题切换后 blocks 的模块级令牌会被回写)
    from theme import T
except Exception:                                       # pragma: no cover
    T = {}


def _t(key: str, fallback: str) -> str:
    return str(T.get(key, fallback) or fallback)


# ============ 1. 顶栏(原生) ============

def _msr(name: str) -> str:
    """Material Symbols 字形(离线): <span class="msr"> 见 theme.py 第 22 节。"""
    return f'<span class="msr" aria-hidden="true">{name}</span>'


def topbar(*, title: str, crumb: str, user: dict, notices=None,
           on_logout=None, admin_url: str = "",
           brand: str = "足球分析系统", brand_sub: str = "FOOTBALL ANALYTICS") -> None:
    """参照稿顶栏: 左=品牌标(足球图标+系统名)+标题+面包屑, 右=消息/个人中心/退出。

    品牌块按设计说明放主区顶栏(不再重复挂在侧栏顶部); 消息与个人中心用
    st.popover(点开就是面板), 退出是真的注销按钮。
    """
    name = (user or {}).get("display_name") or (user or {}).get("username") or "—"
    role = "管理员" if (user or {}).get("role") == "admin" else "普通用户"
    n_notice = len(notices or [])
    # 包一层带 key 的容器: Streamlit 会挂上 .st-key-topbar, 供主题的第 28 节样式命中
    with st.container(key="topbar"):
        _topbar_body(title=title, crumb=crumb, name=name, role=role,
                     notices=notices, n_notice=n_notice, on_logout=on_logout,
                     brand=brand, brand_sub=brand_sub)


def _topbar_body(*, title: str, crumb: str, name: str, role: str,
                 notices, n_notice: int, on_logout=None,
                 brand: str = "足球分析系统", brand_sub: str = "FOOTBALL ANALYTICS") -> None:
    st.markdown('<div class="tb-anchor"></div>', unsafe_allow_html=True)
    c_left, c_right = st.columns([2.4, 1.9], gap="small", vertical_alignment="center")
    with c_left:
        st.markdown(
            f"""<div class="tb-left">
              <div class="tb-brand">
                <div class="tb-logo" aria-hidden="true">{_msr('sports_soccer')}</div>
                <div>
                  <div class="tb-brand-name">{B._esc(brand)}</div>
                  <div class="tb-brand-sub">{B._esc(brand_sub)}</div>
                </div>
              </div>
              <div class="tb-sep"></div>
              <div class="tb-page">
                <div class="tb-title">{B._esc(title)}</div>
                <div class="tb-crumb">{B._esc(crumb)}</div>
              </div>
            </div>""",
            unsafe_allow_html=True,
        )
    with c_right:
        b1, b2, b3 = st.columns([1, 1, 1], gap="small")
        with b1:
            with st.popover(f"消息 {n_notice}" if n_notice else "消息",
                            icon=":material/notifications:", use_container_width=True):
                st.markdown('<div class="tb-pop-cap">系统提醒</div>', unsafe_allow_html=True)
                if not notices:
                    st.caption("暂无提醒")
                for it in (notices or []):
                    st.markdown(
                        f"""<div class="tb-pop-row">
                          <span class="dot {it.get('tone', 'info')}"></span>
                          <span><b>{B._esc(it.get('title', ''))}</b>
                          <span class="tb-pop-val">{B._esc(it.get('value', ''))}</span>
                          <span class="tb-pop-time">{B._esc(it.get('time', ''))}</span></span>
                        </div>""",
                        unsafe_allow_html=True,
                    )
        with b2:
            with st.popover("个人中心", icon=":material/account_circle:",
                            use_container_width=True):
                st.markdown(
                    f"""<div class="tb-me">
                      <div class="tb-me-av">{B._esc(name[:1].upper())}</div>
                      <div><b>{B._esc(name)}</b>
                      <span class="tb-me-role">{B._esc(role)}</span></div>
                    </div>""",
                    unsafe_allow_html=True,
                )
                st.caption("账号由管理员创建 · 会话 12 小时 / 记住我 30 天")
        with b3:
            if st.button("退出系统", icon=":material/logout:", key="tb_logout",
                         use_container_width=True):
                if on_logout:
                    on_logout()
                else:                                      # pragma: no cover
                    st.session_state.clear()
                    st.rerun()


# ============ 2. KPI 卡(参照稿: 图标砖 + 大号数字 + 增量行) ============
def kpi_row(items, height=None) -> None:
    """items: [{'label','value','note','delta','dir','icon'}, ...] —— 4 张一行。

    delta 行对应参照稿的“↑ 较昨日 +2”; 我们没有“昨日”快照时一律写真实口径
    (如“本月新增 222”), 不编造日环比。
    """
    items = list(items)[:4]
    h = height or 132
    cards = ""
    for i, it in enumerate(items):
        d = str(it.get("delta", "") or "")
        dir_ = str(it.get("dir", "up") or "up")
        delta_html = (f'<div class="delta {dir_}">{B._esc(d)}</div>') if d else ""
        note = it.get("note")
        cards += f"""
        <div class="kpi rise" style="animation-delay:{i * 0.07:.2f}s">
          <div class="kpi-tile">{B._esc(it.get('icon', '✦'))}</div>
          <div class="kpi-label">{B._esc(it.get('label', ''))}</div>
          <div class="kpi-value" data-count="{B._esc(it.get('value', ''))}">{B._esc(it.get('value', ''))}</div>
          {delta_html}
          {f'<div class="kpi-note">{B._esc(note)}</div>' if note else ''}
        </div>"""
    B._render(f"""
    <div class="kpi-row">{cards}</div>
    <style>
      .kpi-row {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
                  gap: 14px; }}
      /* 卡片渲染在独立 iframe 里, 媒体查询按 iframe 宽度生效 —— 中央列约 900px,
         所以 4 列要一直保持到 760px, 只在更窄时才折成 2 列; 中间区间改用紧凑字号。 */
      @media (max-width: 1040px) {{
        .kpi-row {{ gap: 10px; }}
        .kpi {{ padding: 13px 14px 12px; }}
        .kpi-value {{ font-size: 27px; margin-top: 7px; }}
        .kpi-label {{ font-size: 10.5px; padding-right: 32px; }}
        .kpi-tile {{ top: 11px; right: 11px; width: 26px; height: 26px; font-size: 13px; }}
        .kpi-delta, .kpi-note {{ font-size: 10px; }}
      }}
      @media (max-width: 760px) {{ .kpi-row {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }} }}
      .kpi {{
        position: relative; padding: 16px 18px 14px; min-height: {h - 14}px;
        /* 液态玻璃(Apple Liquid Glass): 透明底 + 镜面高光描边 + 大圆角 + 内高光 + 带色投影 */
        background: linear-gradient(155deg, {_t('glass_mid', 'rgba(255,255,255,.28)')} 0%,
                                   {_t('glass_lite', 'rgba(255,255,255,.15)')} 100%);
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        border-radius: {_t('r4', '24px')};
        box-shadow: {_t('glass_shadow', 'inset 0 1px 1px rgba(255,255,255,.8), 0 8px 32px rgba(59,130,246,.12)')},
                    0 0 0 1px {B.LINE};
        transition: transform .25s ease, border-color .25s ease, box-shadow .25s ease;
      }}
      .kpi:hover {{ transform: translateY(-3px); border-color: {B.ACCENT};
                    box-shadow: 0 16px 34px -22px {B._rgba('accent', 0.55, 'rgba(47,134,224,.55)')}; }}
      .kpi-tile {{
        position: absolute; top: 14px; right: 14px;
        width: 30px; height: 30px; border-radius: 10px;
        display: flex; align-items: center; justify-content: center;
        font-size: 15px; line-height: 1;
        color: {B.ACCENT};
        background: {B._rgba('accent', 0.12, 'rgba(47,134,224,.12)')};
        border: 1px solid {B._rgba('accent', 0.28, 'rgba(47,134,224,.28)')};
      }}
      .kpi-label {{ font-size: 11.5px; letter-spacing: .06em; color: {B.T3};
                    text-transform: uppercase; padding-right: 38px; }}
      .kpi-value {{ font-size: 34px; font-weight: 700; color: {B.T1}; margin-top: 10px;
                    font-variant-numeric: tabular-nums; letter-spacing: -0.022em; }}
      .delta {{ margin-top: 8px; font-size: 11.5px; font-weight: 600; }}
      .delta.up {{ color: {_t('ok', '#2e8b57')}; }}
      .delta.down {{ color: {_t('danger', '#c0392b')}; }}
      .delta.flat {{ color: {B.T3}; }}
      .kpi-note {{ margin-top: 6px; font-size: 11.5px; color: {B.T2}; line-height: 1.5; }}
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
        const dec = (m[0].split('.')[1] || '').length;
        let t0 = null;
        function step(ts) {{
          if (!t0) t0 = ts;
          const p = Math.min((ts - t0) / 850, 1);
          const v = target * (1 - Math.pow(1 - p, 3));
          el.textContent = prefix + v.toLocaleString('en-US',
            {{minimumFractionDigits: dec, maximumFractionDigits: dec}}) + suffix;
          if (p < 1) requestAnimationFrame(step);
        }}
        requestAnimationFrame(step);
      }});
    </script>
    """, h)


# ============ 3. 大视区(3D 球场场景 + 底部浮层状态胶囊) ============
def main_panel(*, title: str, sub: str = "", pill: str = "", rows=None,
               chips=None, height=None, bg: str = "", show_head: bool = True,
               pitch: bool = True, ring=None) -> None:
    """参照稿的中间大块(那边是三维地图 + 右下三枚状态胶囊)。

    bg 给图片地址时用**三维球场场景**当底图(用户提供的渲染图, 走 Streamlit 静态目录
    /app/static/…); 没给就退回内联 SVG 球场示意。底部浮层胶囊展示真实状态
    (球队近况 / 模型置信度 / 数据覆盖)。
    show_head=False 时只留画面(供「主图」单独成卡, 赛事信息另卡放主图下方)。
    row 写成 {'k','v','hot':True} 时该值走橙色强调; chip 里 'hot':True 时圆环走橙色。
    ring={'pct':66.6,'label':'首选'} 时在卡右侧画一枚大号液态玻璃圆环(参照图「焦点
    赛事」右侧那枚大蓝环)。
    """
    rows = rows or []
    chips = chips or []
    h = height or (470 if bg else 430 + (26 if chips else 0))
    row_html = ""
    for r in rows:
        # 允许两种写法: ("标签", "值") 元组, 或 {"k":…, "v":…, "hot":…} 字典
        hot = False
        if isinstance(r, dict):
            _k, _v = r.get("k", r.get("label", "")), r.get("v", r.get("value", ""))
            hot = bool(r.get("hot"))
        else:
            _k, _v = (list(r) + ["", ""])[:2]
        row_html += f"""
        <div class="mp-row">
          <div class="mp-k">{B._esc(_k)}</div>
          <div class="mp-v{' hot' if hot else ''}">{B._esc(_v)}</div>
        </div>"""
    chip_html = ""
    for c in chips:
        pct = max(0.0, min(100.0, float(c.get("pct", 0) or 0)))
        chip_html += f"""
        <div class="chip rise">
          <div class="chip-txt">
            <div class="chip-name">{B._esc(c.get('name', ''))}
              <span class="chip-tag">{B._esc(c.get('tag', ''))}</span></div>
            <div class="chip-meta">{B._esc(c.get('meta', ''))}</div>
          </div>
          <div class="ring{' hot' if c.get('hot') else ''}" style="--p:{pct:.1f}">
            <span>{pct:.0f}<i>%</i></span>
          </div>
        </div>"""
    ring_html = ""
    if ring:
        _rp = max(0.0, min(100.0, float(ring.get("pct", 0) or 0)))
        ring_html = f"""
        <div class="bring" style="--p:{_rp:.1f}">
          <div class="bring-core">
            <b>{_rp:.1f}<i>%</i></b>
            <span>{B._esc(ring.get('label', ''))}</span>
          </div>
        </div>"""
    head_html = f"""
      <div class="mp-head">
        <div>
          <div class="mp-title">{B._esc(title)}</div>
          {f'<div class="mp-sub">{B._esc(sub)}</div>' if sub else ''}
        </div>
        {f'<div class="mp-pill">{B._esc(pill)}</div>' if pill else ''}
      </div>""" if show_head else (
        f'<div class="mp-head mp-head-solo"><div></div>'
        f'<div class="mp-pill">{B._esc(pill)}</div></div>' if pill else "")
    B._render(f"""
    <div class="mp card{' mp-photo' if bg else ''}">
      <div class="mp-glow"></div>
      {f'<img class="mp-bg" src="{B._esc(bg)}" alt="">' if bg else ''}
      {'' if (bg or not pitch) else '''<svg class="pitch" viewBox="0 0 640 380" preserveAspectRatio="none" aria-hidden="true">
        <rect x="10" y="10" width="620" height="360" rx="6"/>
        <line x1="320" y1="10" x2="320" y2="370"/>
        <circle cx="320" cy="190" r="52"/>
        <rect x="10" y="105" width="70" height="170"/>
        <rect x="560" y="105" width="70" height="170"/>
        <rect x="10" y="150" width="26" height="80"/>
        <rect x="604" y="150" width="26" height="80"/>
      </svg>'''}
      {f'<div class="mp-wash"></div>' if bg else ''}
      {head_html}
      <div class="mp-main">
        <div class="mp-body">{row_html}</div>
        {ring_html}
      </div>
      <div class="chips">{chip_html}</div>
    </div>
    <style>
      .mp {{ position: relative; overflow: hidden; border-radius: {_t('r4', '24px')}; padding: 18px 20px 16px;
             min-height: {h - 14}px; display: flex; flex-direction: column; }}
      .mp-glow {{ position: absolute; inset: -30%;
        background:
          radial-gradient(closest-side, {B._rgba('accent', 0.18, 'rgba(47,134,224,.18)')}, transparent 70%) 20% 20%/54% 62% no-repeat,
          radial-gradient(closest-side, {B._rgba('cool', 0.12, 'rgba(63,124,168,.12)')}, transparent 70%) 82% 82%/48% 56% no-repeat;
        filter: blur(20px); }}
      .pitch {{ position: absolute; inset: 0; width: 100%; height: 100%;
                opacity: .5; }}
      .pitch rect, .pitch circle, .pitch line {{
        fill: none; stroke: {B._rgba('accent', 0.22, 'rgba(47,134,224,.22)')}; stroke-width: 1.4; }}
      /* 三维球场底图 + 洗白层(保证标题/胶囊在任何图上都读得清) */
      .mp-bg {{ position: absolute; inset: 0; width: 100%; height: 100%;
                object-fit: cover; object-position: center 62%; }}
      .mp-wash {{ position: absolute; inset: 0; pointer-events: none;
        background:
          linear-gradient(180deg, rgba(255,255,255,.86) 0%, rgba(255,255,255,.34) 24%,
                          rgba(255,255,255,.05) 50%, rgba(232,241,251,.62) 100%),
          linear-gradient(90deg, rgba(255,255,255,.72) 0%, rgba(255,255,255,0) 20%,
                          rgba(255,255,255,0) 80%, rgba(255,255,255,.72) 100%),
          radial-gradient(120% 92% at 50% 46%, rgba(255,255,255,0) 50%,
                          rgba(232,241,251,.55) 100%); }}
      .mp-photo .mp-glow {{ display: none; }}
      .mp-head {{ position: relative; display: flex; align-items: flex-start;
                  justify-content: space-between; gap: 12px; }}
      .mp-title {{ font-size: 14.5px; font-weight: 700; color: {B.T1}; }}
      .mp-sub {{ font-size: 11.5px; color: {B.T3}; margin-top: 4px; }}
      .mp-pill {{ font: 600 10.5px/1 ui-monospace, monospace; letter-spacing: .16em;
        text-transform: uppercase; color: {B.ACCENT};
        border: 1px solid {B._rgba('accent', 0.32, 'rgba(47,134,224,.32)')};
        background: {B._rgba('accent', 0.10, 'rgba(47,134,224,.10)')};
        padding: 6px 12px; border-radius: 999px; white-space: nowrap; }}
      .mp-main {{ position: relative; display: flex; align-items: flex-start; gap: 18px; }}
      .mp-body {{ position: relative; flex: 1 1 auto; min-width: 0; display: flex; flex-wrap: wrap;
                  gap: 10px 26px; margin-top: 16px; }}
      /* 大号液态玻璃圆环(参照图「焦点赛事」右侧) */
      .bring {{ --p: 50; width: 128px; height: 128px; flex: 0 0 128px; margin: 14px 2px 0 auto;
        border-radius: 50%; position: relative;
        background: conic-gradient({B.ACCENT} calc(var(--p) * 1%),
                                   {B._rgba('accent', 0.14, 'rgba(47,134,224,.14)')} 0);
        display: flex; align-items: center; justify-content: center;
        box-shadow: 0 14px 34px -16px {B._rgba('accent', 0.55, 'rgba(47,134,224,.55)')}; }}
      .bring::after {{ content: ''; position: absolute; inset: -5px; border-radius: 50%;
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')}; }}
      .bring-core {{ width: 100px; height: 100px; border-radius: 50%; position: relative;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
        background: linear-gradient(180deg, {_t('glass_mid', 'rgba(255,255,255,.28)')} 0%,
                                           {_t('glass_lite', 'rgba(255,255,255,.15)')} 100%);
        box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')}; }}
      .bring-core b {{ font: 700 21px/1 ui-monospace, monospace; color: {B.T1};
        font-variant-numeric: tabular-nums; letter-spacing: -0.02em; }}
      .bring-core i {{ font-style: normal; font-size: 10px; color: {B.T3}; }}
      .bring-core span {{ font-size: 10.5px; color: {B.T2}; margin-top: 5px; }}
      .mp-row {{ min-width: 120px; }}
      .mp-k {{ font-size: 10.5px; color: {B.T3}; text-transform: uppercase;
               letter-spacing: .08em; }}
      .mp-v {{ font-size: 15px; font-weight: 700; color: {B.T1}; margin-top: 3px;
               font-variant-numeric: tabular-nums; }}
      .mp-v.hot {{ color: {_t('orange', '#f28c3b')}; }}
      .chips {{ position: relative; margin-top: auto; padding-top: 18px;
                display: flex; gap: 12px; flex-wrap: wrap; }}
      .chip {{ flex: 1 1 170px; min-width: 0; display: flex; align-items: center; gap: 10px;
        background: linear-gradient(180deg, {_t('glass_mid', 'rgba(255,255,255,.28)')} 0%,
                                   {_t('glass_lite', 'rgba(255,255,255,.15)')} 100%);
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        border-radius: 18px; padding: 10px 12px;
        box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')};
        backdrop-filter: {_t('glass_blur', 'blur(8px) saturate(180%)')}; }}
      .chip-name {{ font-size: 12px; font-weight: 700; color: {B.T1}; }}
      .chip-tag {{ margin-left: 6px; font: 600 9.5px/1 ui-monospace, monospace;
        letter-spacing: .10em; color: {B.ACCENT}; }}
      .chip-meta {{ font-size: 10.5px; color: {B.T3}; margin-top: 3px;
        overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
      .chip-txt {{ min-width: 0; }}
      .ring {{ --p: 50; width: 38px; height: 38px; flex: 0 0 38px; border-radius: 50%; margin-left: auto;
        background: conic-gradient({B.ACCENT} calc(var(--p) * 1%), {B._rgba('accent', 0.14, 'rgba(47,134,224,.14)')} 0);
        display: flex; align-items: center; justify-content: center; position: relative; }}
      .ring::before {{ content: ''; position: absolute; inset: 4px; border-radius: 50%;
        background: {_t('glass_mid', 'rgba(255,255,255,.28)')}; }}
      .ring span {{ position: relative; font: 700 9.5px/1 ui-monospace, monospace;
        color: {B.T1}; letter-spacing: -0.02em; }}
      .ring i {{ font-style: normal; font-size: 6.5px; color: {B.T3}; }}
      .ring.hot {{
        background: conic-gradient({_t('orange', '#f28c3b')} calc(var(--p) * 1%),
                                   {_t('orange_soft', 'rgba(242,140,59,.12)')} 0); }}
    </style>
    """, h)


# ============ 4. 进度卡(名称 + 编号 + 进度条 + 说明) ============
def progress_card(*, title: str, sub: str = "", items=None, height=None) -> None:
    """items: [{'name','code','pct','meta','icon'}, ...] —— 参照稿「数据完整度」。

    icon 给 Material 图标名(如 'verified')时, 该行左侧出现一枚浅蓝圆角图标砖 ——
    参照图右列每行都是「图标砖 + 大号百分比 + 进度条」。
    """
    items = items or []
    h = height or (122 + 58 * max(1, len(items)))
    rows = ""
    for i, it in enumerate(items):
        pct = max(0.0, min(100.0, float(it.get("pct", 0) or 0)))
        ico = it.get("icon") or ""
        rows += f"""
        <div class="pg-row rise" style="animation-delay:{i * 0.08:.2f}s">
          <div class="pg-ico">{_msr(ico) if ico else ''}</div>
          <div class="pg-main">
            <div class="pg-line">
              <span class="pg-name">{B._esc(it.get('name', ''))}</span>
              <span class="pg-code">{B._esc(it.get('code', ''))}</span>
              <span class="pg-pct">{pct:.1f}%</span>
            </div>
            <div class="pg-bar"><i style="width:{pct:.1f}%"></i></div>
            <div class="pg-meta">{B._esc(it.get('meta', ''))}</div>
          </div>
        </div>"""
    B._render(f"""
    <div class="pg card">
      <div class="pg-head">
        <div class="pg-title">{B._esc(title)}</div>
        {f'<div class="pg-sub">{B._esc(sub)}</div>' if sub else ''}
      </div>
      {rows}
    </div>
    <style>
      .pg {{ padding: 16px 18px 14px; border-radius: {_t('r4', '24px')}; min-height: {h - 14}px; }}
      .pg-head {{ display: flex; align-items: baseline; gap: 10px; margin-bottom: 12px; }}
      .pg-title {{ font-size: 13.5px; font-weight: 700; color: {B.T1}; }}
      .pg-sub {{ font-size: 11px; color: {B.T3}; }}
      .pg-row {{ display: flex; align-items: flex-start; gap: 10px; padding: 7px 0 9px; }}
      .pg-ico {{ width: 28px; height: 28px; flex: 0 0 28px; border-radius: 9px; margin-top: 1px;
        display: flex; align-items: center; justify-content: center;
        background: linear-gradient(180deg, {B._rgba('accent', 0.18, 'rgba(47,134,224,.18)')} 0%,
                                           {B._rgba('accent', 0.07, 'rgba(47,134,224,.07)')} 100%);
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')};
        color: {B.ACCENT}; font-size: 15px; }}
      .pg-main {{ flex: 1 1 auto; min-width: 0; }}
      .pg-line {{ display: flex; align-items: baseline; gap: 8px; }}
      .pg-name {{ font-size: 12.5px; font-weight: 600; color: {B.T1}; }}
      .pg-code {{ font: 500 10px/1.6 ui-monospace, monospace; letter-spacing: .06em;
                  color: {B.T3}; }}
      .pg-pct {{ margin-left: auto; font: 700 16.5px/1 ui-monospace, monospace;
                 color: {B.ACCENT}; letter-spacing: -0.02em;
                 font-variant-numeric: tabular-nums; }}
      .pg-bar {{ height: 7px; border-radius: 999px; margin: 8px 0 6px;
                 background: {B._rgba('accent', 0.12, 'rgba(47,134,224,.12)')}; overflow: hidden; }}
      .pg-bar i {{ display: block; height: 100%; border-radius: 999px;
                   background: linear-gradient(90deg, {B.ACCENT2}, {B.ACCENT});
                   box-shadow: 0 0 12px -2px {B._rgba('accent', 0.7, 'rgba(47,134,224,.7)')}; }}
      .pg-meta {{ font-size: 11px; color: {B.T2}; }}
    </style>
    """, h)


# ============ 5. 右列消息通知(染色卡片) ============
def notice_column(*, title: str, sub: str = "", items=None, height=None) -> None:
    """items: [{'title','value','time','tone'}], tone: info|warn|ok|danger"""
    items = items or []
    h = height or (96 + 58 * max(1, len(items)))
    rows = ""
    for i, it in enumerate(items):
        tone = it.get("tone", "info")
        rows += f"""
        <div class="nt {tone} rise" style="animation-delay:{i * 0.06:.2f}s">
          <div class="nt-body">
            <div class="nt-title">{B._esc(it.get('title', ''))}</div>
            <div class="nt-val">{B._esc(it.get('value', ''))}</div>
            <div class="nt-time">{B._esc(it.get('time', ''))}</div>
          </div>
          <span class="nt-dot"></span>
        </div>"""
    B._render(f"""
    <div class="ntc card">
      <div class="ntc-head">
        <div class="ntc-title">{B._esc(title)}</div>
        {f'<div class="ntc-sub">{B._esc(sub)}</div>' if sub else ''}
      </div>
      {rows}
    </div>
    <style>
      .ntc {{ padding: 16px 16px 12px; border-radius: {_t('r4', '24px')}; min-height: {h - 14}px; }}
      .ntc-head {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 10px; }}
      .ntc-title {{ font-size: 13.5px; font-weight: 700; color: {B.T1}; }}
      .ntc-sub {{ font-size: 10.5px; color: {B.T3}; }}
      .nt {{
        display: flex; align-items: flex-start; gap: 10px; margin-bottom: 9px;
        padding: 10px 12px; border-radius: 12px; position: relative;
        border: 1px solid {B.LINE};
      }}
      .nt-body {{ min-width: 0; }}
      .nt-title {{ font-size: 12px; font-weight: 700; color: {B.T1}; }}
      .nt-val {{ font-size: 11.5px; color: {B.T2}; margin-top: 4px; line-height: 1.5; }}
      .nt-time {{ font: 500 10px/1.6 ui-monospace, monospace; color: {B.T3};
                  margin-top: 5px; letter-spacing: .06em; }}
      .nt-dot {{ width: 7px; height: 7px; border-radius: 50%; margin-left: auto;
                 margin-top: 4px; flex: 0 0 auto; }}
      .nt.info {{ background: {B._rgba('accent', 0.08, 'rgba(47,134,224,.08)')}; }}
      .nt.info .nt-dot {{ background: {B.ACCENT}; }}
      .nt.warn {{ background: rgba(200, 135, 26, .10); }}
      .nt.warn .nt-dot {{ background: #c8871a; }}
      .nt.ok {{ background: {B._rgba('ok', 0.10, 'rgba(46,139,87,.10)')}; }}
      .nt.ok .nt-dot {{ background: {_t('ok', '#2e8b57')}; }}
      .nt.danger {{ background: rgba(208, 69, 60, .10); }}
      .nt.danger .nt-dot {{ background: #d0453c; }}
    </style>
    """, h)


# ============ 6. 快捷操作(原生按钮, 点一下切页) ============
def quick_actions(items, *, key: str = "qa", label: str = "快捷操作",
                  cols: int | None = None) -> None:
    """items: [(标签, 图标, 目标页中文名), ...] —— 点按钮直接切到那一页。

    走 st.session_state["nav_page"](侧栏导航用的同一个键) + st.rerun(), 因此
    不会重新加载页面, 登录态不会丢。
    cols 给定整数时改成「卡片 + 每行 cols 个」的网格(设计说明里的右列快捷操作卡)。
    """
    items = list(items)
    if cols:
        grid = [items[i:i + cols] for i in range(0, len(items), cols)]
        with st.container(key=f"{key}_card"):
            st.markdown(
                f"""<div class="qa-head"><span class="qa-title">{B._esc(label)}</span>
                <span class="qa-sub">常用入口</span></div>""",
                unsafe_allow_html=True,
            )
            for row in grid:
                cs = st.columns(cols, gap="small")
                for col, (text, icon, target) in zip(cs, row):
                    with col:
                        if st.button(text, icon=icon, key=f"{key}_{target}",
                                     use_container_width=True):
                            st.session_state["nav_page"] = target
                            st.rerun()
        return
    st.markdown(f'<div class="qa-cap">{B._esc(label)}</div>', unsafe_allow_html=True)
    cs = st.columns(len(items), gap="small")
    for col, (text, icon, target) in zip(cs, items):
        with col:
            if st.button(text, icon=icon, key=f"{key}_{target}", use_container_width=True):
                st.session_state["nav_page"] = target
                st.rerun()


# ============ 7. 侧列小卡(趋势 / 结构 / 排行) ============
def chart_card(*, title: str, sub: str = "", kind: str = "area",
               points=None, labels=None, segments=None, height=None,
               unit: str = "", show_pct: bool = True) -> None:
    """左列小卡: kind="area" 画折线/面积(SVG), kind="donut" 画环形结构图。

    points   : [数字, ...] 面积图的序列(真实统计值)
    labels   : [标签, ...] 与 points 等长, 只显示首尾(避免拥挤)
    segments : [{"label","value","tone"}] 环形图分段(tone: accent/cool/ok/warn)
    show_pct : 环形图图例是否带百分比列(窄卡 + 长标签时关掉, 免得名字被挤成单字)
    """
    points = [float(p or 0) for p in (points or [])]
    labels = list(labels or [])
    segments = segments or []
    if kind == "donut":
        h = height or 214
        total = sum(float(s.get("value", 0) or 0) for s in segments) or 1.0
        tones = {"accent": B.ACCENT, "cool": _t("cool", "#3f7ca8"), "ok": _t("ok", "#2e8b57"),
                 "warn": "#c8871a", "muted": B._rgba("accent", 0.22, "rgba(47,134,224,.22)")}
        R, SW = 46.0, 15.0
        circ = 2 * 3.14159265 * R
        off, arcs = 0.0, ""
        for s in segments:
            frac = float(s.get("value", 0) or 0) / total
            ln = max(0.0, frac * circ - 2.2)                 # 2.2 是分段缝
            col = tones.get(str(s.get("tone", "accent")), B.ACCENT)
            arcs += (f'<circle cx="60" cy="60" r="{R}" fill="none" stroke="{col}" '
                     f'stroke-width="{SW}" stroke-linecap="round" '
                     f'stroke-dasharray="{ln:.1f} {circ - ln:.1f}" '
                     f'stroke-dashoffset="{-off:.1f}" transform="rotate(-90 60 60)"/>')
            off += frac * circ
        legend = ""
        for s in segments:
            col = tones.get(str(s.get("tone", "accent")), B.ACCENT)
            val = float(s.get("value", 0) or 0)
            legend += f"""
            <div class="lg-row">
              <span class="lg-dot" style="background:{col}"></span>
              <span class="lg-name">{B._esc(s.get('label', ''))}</span>
              <span class="lg-val">{val:,.0f}<i>{B._esc(unit)}</i></span>
              {f'<span class="lg-pct">{val / total * 100:.1f}%</span>' if show_pct else ''}
            </div>"""
        mid = f"{total:,.0f}" if total > 999 else f"{total:,.1f}"
        body = f"""
        <div class="lg-wrap">
          <div class="dg">
            <svg viewBox="0 0 120 120" aria-hidden="true">
              <circle cx="60" cy="60" r="{R}" fill="none"
                      stroke="{B._rgba('accent', 0.10, 'rgba(47,134,224,.10)')}" stroke-width="{SW}"/>
              {arcs}
            </svg>
            <div class="dg-mid"><b>{mid}</b><span>{B._esc(title)}</span></div>
          </div>
          <div class="lg">{legend}</div>
        </div>"""
    else:
        h = height or 214
        n = len(points)
        w, hh, pad = 244.0, 96.0, 6.0
        mx = max(points) if points else 1.0
        mn = min(points) if points else 0.0
        span = (mx - mn) or 1.0
        step = (w - pad * 2) / max(1, n - 1)
        xy = [(pad + i * step, hh - pad - (v - mn) / span * (hh - pad * 2 - 12))
              for i, v in enumerate(points)]
        line = " ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
        area = (f"{pad:.1f},{hh - pad:.1f} " + line +
                f" {xy[-1][0]:.1f},{hh - pad:.1f}") if xy else ""
        dots = "".join(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="2.6" fill="{B.ACCENT}"/>'
                       for x, y in xy[-3:])
        first = labels[0] if labels else ""
        last = labels[-1] if labels else ""
        body = f"""
        <div class="ac-wrap">
          <div class="ac-max"><b>{mx:,.0f}</b><span>{B._esc(unit or '峰值')}</span></div>
          <svg class="ac-svg" viewBox="0 0 {w:.0f} {hh:.0f}" preserveAspectRatio="none" aria-hidden="true">
            <defs>
              <linearGradient id="acg" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stop-color="{B._rgba('accent', 0.34, 'rgba(47,134,224,.34)')}"/>
                <stop offset="100%" stop-color="{B._rgba('accent', 0.02, 'rgba(47,134,224,.02)')}"/>
              </linearGradient>
            </defs>
            <polygon points="{area}" fill="url(#acg)"/>
            <polyline points="{line}" fill="none" stroke="{B.ACCENT}"
                      stroke-width="2" stroke-linejoin="round" stroke-linecap="round"/>
            {dots}
          </svg>
          <div class="ac-x"><span>{B._esc(first)}</span><span>{B._esc(last)}</span></div>
        </div>"""
    B._render(f"""
    <div class="sc card">
      <div class="sc-head">
        <div class="sc-title">{B._esc(title)}</div>
        {f'<div class="sc-sub">{B._esc(sub)}</div>' if sub else ''}
      </div>
      {body}
    </div>
    <style>
      .sc {{ padding: 12px 14px 10px; border-radius: {_t('r4', '24px')}; }}
      .sc-head {{ display: flex; align-items: baseline; gap: 8px; margin-bottom: 8px; }}
      .sc-title {{ font-size: 12.5px; font-weight: 700; color: {B.T1}; }}
      .sc-sub {{ font-size: 10px; color: {B.T3}; }}
      .ac-wrap {{ position: relative; }}
      .ac-max {{ position: absolute; right: 0; top: -4px; text-align: right; }}
      .ac-max b {{ font: 700 15px/1 ui-monospace, monospace; color: {B.T1};
                   font-variant-numeric: tabular-nums; }}
      .ac-max span {{ display: block; font-size: 9.5px; color: {B.T3}; margin-top: 2px; }}
      .ac-svg {{ width: 100%; height: 86px; display: block; }}
      .ac-x {{ display: flex; justify-content: space-between; font: 500 9.5px/1.6 ui-monospace, monospace;
               color: {B.T3}; letter-spacing: .04em; }}
      .lg-wrap {{ display: flex; gap: 12px; align-items: center; }}
      .dg {{ position: relative; width: 76px; height: 76px; flex: 0 0 76px; }}
      .dg svg {{ width: 76px; height: 76px; display: block; }}
      .dg-mid {{ position: absolute; inset: 0; display: flex; flex-direction: column;
                 align-items: center; justify-content: center; text-align: center; }}
      .dg-mid b {{ font: 700 14px/1.1 ui-monospace, monospace; color: {B.T1};
                   font-variant-numeric: tabular-nums; }}
      .dg-mid span {{ font-size: 9px; color: {B.T3}; margin-top: 2px; }}
      .lg {{ flex: 1 1 auto; min-width: 0; }}
      .lg-row {{ display: flex; align-items: center; gap: 6px; font-size: 11px; padding: 3px 0; }}
      .lg-dot {{ width: 7px; height: 7px; border-radius: 50%; flex: 0 0 7px; }}
      .lg-name {{ color: {B.T2}; flex: 1 1 auto; min-width: 26px; white-space: nowrap;
                  overflow: hidden; text-overflow: ellipsis; }}
      .lg-val {{ flex: 0 0 auto; font: 600 11px/1 ui-monospace, monospace; color: {B.T1};
                 font-variant-numeric: tabular-nums; }}
      .lg-val i {{ font-style: normal; font-size: 9px; color: {B.T3}; }}
      .lg-pct {{ flex: 0 0 34px; text-align: right; font: 500 10px/1 ui-monospace, monospace;
                 color: {B.T3}; }}
    </style>
    """, h)


def rank_card(*, title: str, sub: str = "", items=None, unit: str = "",
              height=None) -> None:
    """右列排行卡: 名称 + 条形 + 数值(真值缩放, 最长条占满)。"""
    items = items or []
    h = height or (30 + 26 * max(1, len(items)))
    mx = max([float(i.get("value", 0) or 0) for i in items] or [1.0]) or 1.0
    rows = ""
    for idx, i in enumerate(items):
        val = float(i.get("value", 0) or 0)
        pct = max(3.0, val / mx * 100.0)
        rows += f"""
        <div class="rk-row">
          <div class="rk-name">{B._esc(i.get('label', ''))}</div>
          <div class="rk-bar"><span class="{'hot' if idx == 0 else ''}" style="width:{pct:.1f}%"></span></div>
          <div class="rk-val">{val:,.0f}<i>{B._esc(unit)}</i></div>
        </div>"""
    B._render(f"""
    <div class="sc card">
      <div class="sc-head">
        <div class="sc-title">{B._esc(title)}</div>
        {f'<div class="sc-sub">{B._esc(sub)}</div>' if sub else ''}
      </div>
      <div class="rk">{rows}</div>
    </div>
    <style>
      .rk-row {{ display: flex; align-items: center; gap: 8px; padding: 4px 0; }}
      .rk-name {{ width: 46px; flex: 0 0 46px; font-size: 11px; color: {B.T2};
                  overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
      .rk-bar {{ flex: 1 1 auto; height: 7px; border-radius: 999px;
                 background: {B._rgba('accent', 0.12, 'rgba(47,134,224,.12)')}; overflow: hidden; }}
      .rk-bar span {{ display: block; height: 100%; border-radius: 999px;
                      background: linear-gradient(90deg, {B.ACCENT}, {_t('accent2', '#1f6fc4')}); }}
      .rk-bar span.hot {{ background: linear-gradient(90deg, {_t('orange', '#f28c3b')},
                          {_t('orange', '#f28c3b')}); }}
      .rk-val {{ width: 52px; text-align: right; font: 600 10.5px/1 ui-monospace, monospace;
                 color: {B.T1}; font-variant-numeric: tabular-nums; }}
      .rk-val i {{ font-style: normal; font-size: 9px; color: {B.T3}; }}
    </style>
    """, h)


# ============ 7. 侧栏收起救援 ============
# 实测(Streamlit 1.62, 系统 Chrome): 侧栏收起后 Streamlit 自带的展开控件
# [data-testid="stExpandSidebarButton"] 被它的祖先容器 display:none 掉 ——
# getComputedStyle 报 width/height 41.6px, 但 getBoundingClientRect() 是 0×0,
# 于是页面上根本没有可点的「展开」按钮(用户报: 侧边栏收起后无法返回)。
# 这里用 0 高度 iframe 往父页面 body 挂一颗自己的固定按钮, 收起态才显示;
# 点击时去 .click() Streamlit 自己的展开控件(元素在 DOM 里, 程序化点击能触发
# React 的展开逻辑 —— 已实测 sideX 从 -300 回到 0)。
_SIDEBAR_RESCUE_JS = """<!doctype html><html><head><meta charset="utf-8">
<style>html,body{margin:0;padding:0;height:0;overflow:hidden;background:transparent}</style>
</head><body>
<script>
(function () {
  var P = null;
  try { P = window.parent; } catch (e) { return; }
  if (!P || !P.document) { return; }

  function find(sel) { try { return P.document.querySelector(sel); } catch (e) { return null; } }

  function clickExpand() {
    var t = find('[data-testid="stExpandSidebarButton"]')
         || find('[data-testid="stSidebarCollapsedControl"]');
    if (!t) { return; }
    var b = (t.tagName === 'BUTTON') ? t : (t.querySelector('button') || t);
    try { b.click(); } catch (e) {}
  }

  function sync() {
    var side = find('[data-testid="stSidebar"]');
    var collapsed = !!side && side.getAttribute('aria-expanded') === 'false';
    var fab = P.document.getElementById('sb-rescue');
    if (!collapsed) { if (fab) { fab.style.display = 'none'; } return; }
    if (!fab) {
      fab = P.document.createElement('button');
      fab.id = 'sb-rescue';
      fab.type = 'button';
      fab.title = '展开侧边栏';
      fab.setAttribute('aria-label', '展开侧边栏');
      fab.innerHTML = '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" '
        + 'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
        + '<rect x="3" y="4" width="18" height="16" rx="2.5"></rect>'
        + '<path d="M9 4v16M15 9l3 3-3 3"></path></svg>';
      fab.addEventListener('click', function () { clickExpand(); setTimeout(sync, 500); });
      P.document.body.appendChild(fab);
    }
    fab.style.display = 'inline-flex';
  }

  sync();
  setInterval(sync, 600);
})();
</script>
</body></html>"""


def sidebar_rescue() -> None:
    """往页面挂一颗「展开侧边栏」按钮(仅侧栏收起时可见)。"""
    try:
        import streamlit.components.v1 as _c
        _c.html(_SIDEBAR_RESCUE_JS, height=0, scrolling=False)
    except Exception:                                     # pragma: no cover
        pass


# ============ 8. 驾驶舱整版(复刻用户给的驾驶舱图, 一个 iframe 内用 CSS grid 画) ============
#
# 参照图版式: 左 KPI 四卡 → 中央三维球场大图 → 大图下方「焦点赛事(带大圆环)」
# 与「进度条列表」并排; 右列自上而下 = 1 行细卡 + 两张各 2 行的百分比卡 + 一张
# 彩色圆点清单卡。这套版式靠严格的列宽比例与卡高, 用 st.columns 只能近似,
# 所以整版放进一个 iframe 用 CSS grid 画(纯展示, 无需交互控件)。

def _bar(pct, *, tone: str = "") -> str:
    p = max(0.0, min(100.0, float(pct or 0)))
    cls = "bar" + (f" {tone}" if tone else "")
    return f'<div class="{cls}"><i style="width:{p:.1f}%"></i></div>'


def _tile(icon: str, *, size: int = 44) -> str:
    return (f'<div class="tile" style="width:{size}px;height:{size}px">'
            f'{_msr(icon)}</div>')


def dashboard(*, kpis, hero, focus, bars, side, height: int = 900) -> None:
    """整版驾驶舱(iframe + CSS grid, 比例与参照图对齐)。"""
    kpi_html = ""
    for i, k in enumerate(list(kpis)[:4]):
        plus = '<div class="kpi-plus">+</div>' if k.get("plus") else ""
        chip = k.get("chip", "")
        chip_html = ('<div class="kpi-chip"><span class="mini"></span>'
                     f'<span>{B._esc(chip)}</span></div>') if chip else ""
        kpi_html += f"""
        <div class="kpi rise" style="animation-delay:{i * 0.06:.2f}s">
          {plus}
          <div class="kpi-lab">{B._esc(k.get('lab', ''))}</div>
          <div class="kpi-val">{B._esc(k.get('val', ''))}</div>
          {chip_html}
        </div>"""

    fcols = ""
    for c in (focus.get("cols") or [])[:3]:
        cls = "fc-col hot" if c.get("hot") else "fc-col"
        fcols += (f'<div class="{cls}"><div class="fc-lab">{B._esc(c.get("lab", ""))}</div>'
                  f'<div class="fc-val">{B._esc(c.get("val", ""))}</div>'
                  f'<div class="fc-cap">{B._esc(c.get("cap", ""))}</div></div>')
    ring = focus.get("ring") or {}
    rpct = max(0.0, min(100.0, float(ring.get("pct", 0) or 0)))
    ring_html = (
        f'<div class="fc-ring" title="{B._esc(ring.get("label", ""))}">'
        f'<div class="ring-outer" style="background:conic-gradient({B.ACCENT} {rpct:.1f}%, '
        f'{B._rgba("accent", 0.16, "rgba(47,134,224,.16)")} 0)">'
        '<div class="ring-core"><span class="msr">play_arrow</span></div></div>'
        f'<div class="ring-cap">{B._esc(ring.get("label", ""))}</div></div>')
    stats = "".join(
        f'<div class="fc-stat"><div class="k">{B._esc(s.get("k", ""))}</div>'
        f'<div class="v">{B._esc(s.get("v", ""))}</div></div>'
        for s in (focus.get("stats") or [])[:5])

    brows = ""
    for r in (bars.get("rows") or [])[:4]:
        brows += ('<div class="brow"><div class="btop">'
                  f'<span class="msr">{B._esc(r.get("icon", "sports_soccer"))}</span>'
                  f'<span class="bname">{B._esc(r.get("name", ""))}</span>'
                  f'<span class="bval">{B._esc(r.get("val", ""))}</span></div>'
                  f'{_bar(r.get("pct", 0), tone=r.get("tone", ""))}</div>')

    slim = side.get("slim") or {}
    slim_html = f"""
      <div class="card slim">
        {_tile(slim.get('icon', 'groups'), size=42)}
        <div class="slim-mid">
          <div class="slim-lab"><span>{B._esc(slim.get('lab', ''))}</span>
            <span class="slim-val">{B._esc(slim.get('val', ''))}</span></div>
          {_bar(slim.get('pct', 0))}
        </div>
        <span class="msr chev">expand_more</span>
      </div>"""
    pct_cards = ""
    for card in (side.get("pct") or [])[:2]:
        rows = ""
        for r in (card.get("rows") or [])[:2]:
            rows += f"""
            <div class="prow">
              <div class="ptop">
                {_tile(r.get('icon', 'analytics'), size=40)}
                <div class="pval">{B._esc(r.get('val', ''))}</div>
                <span class="msr chev">expand_more</span>
              </div>
              {_bar(r.get('pct', 0))}
            </div>"""
        pct_cards += f'<div class="card pct">{rows}</div>'
    dots = side.get("dots") or {}
    dot_rows = "".join(
        f'<div class="drow"><span class="dot {B._esc(d.get("tone", "info"))}"></span>'
        f'<span class="dtxt">{B._esc(d.get("text", ""))}'
        f'<span class="dsub">{B._esc(d.get("sub", ""))}</span></span></div>'
        for d in (dots.get("rows") or [])[:6])

    B._render(f"""
    <div class="db">
      <div class="db-main">
        <div class="db-kpis">{kpi_html}</div>

        <div class="db-hero">
          <img src="{B._esc(hero.get('src', ''))}" alt="">
          <span class="hero-pill">{B._esc(hero.get('pill', ''))}</span>
        </div>

        <div class="db-lower">
          <div class="card focus">
            <div class="fc-head"><span>{B._esc(focus.get('title', ''))}</span>
              <span class="msr chev">expand_more</span></div>
            <div class="fc-top">
              <div class="fc-cols">{fcols}</div>
              {ring_html}
            </div>
            <div class="fc-stats">{stats}</div>
          </div>

          <div class="card bars">
            <div class="fc-head"><span>{B._esc(bars.get('title', ''))}</span>
              <span class="msr chev">expand_more</span></div>
            <div class="bar-sub">{B._esc(bars.get('sub', ''))}</div>
            <div class="brows">{brows}</div>
            <div class="bar-foot">{B._esc(bars.get('foot', ''))}</div>
          </div>
        </div>
      </div>

      <aside class="db-side">
        {slim_html}
        {pct_cards}
        <div class="card dots">
          <div class="fc-head"><span>{B._esc(dots.get('title', ''))}</span>
            <span class="dlink">{B._esc(dots.get('link', ''))} ›</span></div>
          <div class="drows">{dot_rows}</div>
        </div>
      </aside>
    </div>
    <style>
      * {{ box-sizing: border-box; }}
      html, body {{ margin: 0; padding: 0; background: transparent; }}
      body {{ font-family: {_t('font_sans', '-apple-system, "Segoe UI", "Microsoft YaHei", sans-serif')};
              -webkit-font-smoothing: antialiased; }}
      .db {{ display: grid; grid-template-columns: minmax(0, 1fr) 336px; gap: 16px;
             height: {height - 10}px; }}
      .db-main {{ display: grid; grid-template-rows: auto minmax(0, 1fr) auto;
                  gap: 14px; min-height: 0; }}
      .db-kpis {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 12px; }}
      .db-hero {{ position: relative; border-radius: 24px; overflow: hidden;
                  border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
                  box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')},
                              0 0 0 1px {B.LINE}; }}
      .db-hero img {{ width: 100%; height: 100%; object-fit: cover; display: block;
                      filter: {_t('hero_filter', 'none')}; }}
      .hero-pill {{ position: absolute; top: 13px; right: 13px; padding: 6px 13px;
        border-radius: 999px; font-size: 12px; color: {B.T2};
        background: {_t('glass_mid', 'rgba(255,255,255,.28)')};
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        backdrop-filter: {_t('glass_blur', 'blur(8px) saturate(180%)')}; }}
      .db-lower {{ display: grid; grid-template-columns: minmax(0, 1.42fr) minmax(0, 1fr);
                   gap: 14px; }}

      .card {{
        background: linear-gradient(155deg, {_t('glass_mid', 'rgba(255,255,255,.28)')} 0%,
                                   {_t('glass_lite', 'rgba(255,255,255,.15)')} 100%);
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        border-radius: 24px;
        box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')},
                    0 0 0 1px {B.LINE}, {_t('glass_shadow', '0 8px 32px rgba(59,130,246,.12)')};
        padding: 15px 17px;
      }}
      .chev {{ font-size: 19px; color: {B.T3}; }}
      .msr {{ font-family: "Material Symbols Rounded", "Material Icons"; font-size: 18px;
              line-height: 1; font-weight: normal;
              -webkit-font-feature-settings: 'liga'; font-feature-settings: 'liga'; }}

      .kpi {{ position: relative; padding: 13px 15px 12px; border-radius: 20px;
        background: linear-gradient(155deg, {_t('glass_mid', 'rgba(255,255,255,.28)')} 0%,
                                   {_t('glass_lite', 'rgba(255,255,255,.15)')} 100%);
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')};
        box-shadow: {_t('glass_hl', 'inset 0 1px 1px rgba(255,255,255,.8)')},
                    0 0 0 1px {B.LINE}; }}
      .kpi-lab {{ font-size: 10.5px; color: {B.T3}; letter-spacing: .04em; }}
      .kpi-val {{ font-size: 31px; font-weight: 700; color: {B.T1}; line-height: 1.15;
                  margin-top: 3px; letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }}
      .kpi-chip {{ display: flex; align-items: center; gap: 7px; margin-top: 9px;
                   font-size: 10.5px; color: {B.T3}; }}
      .mini {{ width: 26px; height: 8px; border-radius: 4px; flex: none;
        background: linear-gradient(90deg, {_t('ok', '#2f9e6b')},
                                    {_t('ok_soft', 'rgba(47,158,107,.35)')}); }}
      .kpi-plus {{ position: absolute; top: 11px; right: 11px; width: 27px; height: 27px;
        border-radius: 50%; display: grid; place-items: center; color: #fff; font-size: 17px;
        background: linear-gradient(135deg, {B.ACCENT}, {B.ACCENT2}); }}

      .fc-head {{ display: flex; align-items: center; justify-content: space-between;
                  font-size: 15px; font-weight: 700; color: {B.T1}; }}
      .fc-top {{ display: flex; align-items: center; gap: 14px; margin-top: 12px; }}
      .fc-cols {{ display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); flex: 1; }}
      .fc-col {{ padding: 0 13px; border-left: 1px solid {B.LINE}; }}
      .fc-col:first-child {{ border-left: none; padding-left: 0; }}
      .fc-lab {{ font-size: 11.5px; color: {B.T3}; }}
      .fc-val {{ font-size: 27px; font-weight: 700; color: {B.T1}; margin-top: 4px;
                 letter-spacing: -0.02em; font-variant-numeric: tabular-nums; }}
      .fc-col.hot .fc-val {{ color: {_t('orange', '#f28c3b')}; }}
      .fc-cap {{ font-size: 10.5px; color: {B.T3}; margin-top: 6px; }}
      .fc-ring {{ flex: none; display: grid; justify-items: center; gap: 5px; }}
      .ring-outer {{ width: 118px; height: 118px; border-radius: 50%;
        display: grid; place-items: center;
        box-shadow: 0 0 26px {B._rgba('accent', 0.35, 'rgba(47,134,224,.35)')}; }}
      .ring-core {{ width: 84px; height: 84px; border-radius: 50%; display: grid;
        place-items: center; color: {B.ACCENT};
        background: {_t('glass_mid', 'rgba(255,255,255,.28)')};
        border: 1px solid {_t('glass_edge', 'rgba(255,255,255,.62)')}; }}
      .ring-core .msr {{ font-size: 22px; }}
      .ring-cap {{ font-size: 11px; color: {B.T3}; }}
      .fc-stats {{ display: grid; grid-template-columns: repeat(5, minmax(0, 1fr)); gap: 10px;
                   margin-top: 13px; padding-top: 11px; border-top: 1px solid {B.LINE}; }}
      .fc-stat .k {{ font-size: 10.5px; color: {B.T3}; }}
      .fc-stat .v {{ font-size: 13px; font-weight: 600; color: {B.T1}; margin-top: 2px;
                     font-variant-numeric: tabular-nums; }}

      .bar-sub {{ font-size: 10.5px; color: {B.T3}; margin-top: 3px; }}
      .brows {{ margin-top: 8px; display: grid; gap: 9px; }}
      .brow .btop {{ display: grid; grid-template-columns: 18px 1fr auto; align-items: center;
                     gap: 8px; margin-bottom: 5px; }}
      .brow .btop .msr {{ font-size: 15px; color: {B.T3}; }}
      .bname {{ font-size: 11.5px; color: {B.T2}; }}
      .bval {{ font-size: 11.5px; color: {B.T1}; font-variant-numeric: tabular-nums; }}
      .bar {{ height: 7px; border-radius: 4px; overflow: hidden;
              background: {_t('bar_track', 'rgba(120,150,190,.20)')}; }}
      .bar > i {{ display: block; height: 100%; border-radius: 4px;
        background: linear-gradient(90deg, {B._rgba('accent', 0.55, 'rgba(47,134,224,.55)')}, {B.ACCENT}); }}
      .bar.warm > i {{ background: linear-gradient(90deg, {_t('orange_line', 'rgba(242,140,59,.4)')},
                                                   {_t('orange', '#f28c3b')}); }}
      .bar-foot {{ margin-top: 10px; padding-top: 9px; border-top: 1px solid {B.LINE};
                   font-size: 10.5px; color: {B.T3}; }}

      .db-side {{ display: grid; grid-template-rows: auto auto auto minmax(0, 1fr); gap: 14px; }}
      .tile {{ border-radius: 14px; display: grid; place-items: center; flex: none; color: #fff;
        background: linear-gradient(135deg, {B._rgba('accent', 0.85, 'rgba(47,134,224,.85)')}, {B.ACCENT2});
        box-shadow: 0 6px 16px -8px {B._rgba('accent', 0.75, 'rgba(47,134,224,.75)')}; }}
      .tile .msr {{ font-size: 19px; }}
      .card.slim {{ display: grid; grid-template-columns: 42px 1fr 18px; align-items: center;
                    gap: 12px; }}
      .slim-lab {{ font-size: 11px; color: {B.T3}; display: flex; justify-content: space-between;
                   margin-bottom: 7px; }}
      .slim-val {{ color: {B.T1}; font-weight: 600; }}
      .card.pct {{ display: grid; gap: 12px; }}
      .prow .ptop {{ display: grid; grid-template-columns: 40px 1fr 18px; align-items: center;
                     gap: 12px; margin-bottom: 7px; }}
      .pval {{ font-size: 23px; font-weight: 700; color: {B.ACCENT}; letter-spacing: -0.02em;
               font-variant-numeric: tabular-nums; }}
      .dlink {{ font-size: 10.5px; color: {B.T3}; }}
      .drows {{ margin-top: 10px; display: grid; gap: 11px; }}
      .drow {{ display: grid; grid-template-columns: 12px 1fr; gap: 10px; align-items: start; }}
      .drow .dot {{ width: 11px; height: 11px; border-radius: 50%; margin-top: 3px; }}
      .dot.warn {{ background: #f0a03c; }} .dot.ok {{ background: #35b877; }}
      .dot.info {{ background: {B.ACCENT}; }} .dot.bad {{ background: #e2685c; }}
      .dtxt {{ font-size: 11.5px; color: {B.T2}; line-height: 1.5; }}
      .dsub {{ display: block; font-size: 10.5px; color: {B.T3}; }}
      .rise {{ animation: rise .5s ease both; }}
      @keyframes rise {{ from {{ opacity: 0; transform: translateY(7px); }}
                         to {{ opacity: 1; transform: none; }} }}
    </style>""", height)
