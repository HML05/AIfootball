# -*- coding: utf-8 -*-
"""足球分析系统 - 统一数据可视化层 (viz.py)  v1.0

定位
----
本模块是前端(app.py)与后台(admin.py)**唯一**的图表渲染方。
所有图表基于 Altair / Vega-Lite 声明式语法(Streamlit 自带依赖, 零新增安装、
零 CDN、可离线运行), 配色与排版全部取自 theme.py 的设计令牌 ``T``,
与既有深色足球主题完全一致。

为什么图表要自带样式
--------------------
Altair 图表由 Streamlit 渲染在独立的 iframe 中, theme.py 的 ``UNIFIED_CSS``
无法穿透进去。因此每个图表都通过 ``configure_*`` 链把背景色 / 轴色 / 图例色
写进 spec 自身, 并让渲染时 ``theme=None`` 以免被 Streamlit 默认主题覆盖。

对外 API
--------
可用性:  available()
基础:    render()
柱状:    bar() / rank_bar() / grouped_bar() / stacked_bar()
趋势:    line() / multi_line()
分布:    histogram() / scatter()
矩阵:    heatmap()
占比:    donut() / prob_bar()

约定
----
* 所有函数在数据为空或 Altair 不可用时自动回退(表格 / 原生图表), 不会抛异常。
* 文案参数(标题 / 轴名)由调用方经 i18n 的 ``t()`` 传入, 本模块不做翻译。
"""
from __future__ import annotations

import math

import numpy as np
import pandas as pd
import streamlit as st

try:
    from theme import T, FONT_SANS, FONT_MONO
except Exception:                                     # pragma: no cover
    T = {}
    FONT_SANS = "sans-serif"
    FONT_MONO = "monospace"

try:
    import altair as alt
except Exception:                                     # pragma: no cover
    alt = None


# ============ 基础常量 ============
# 与 theme.FONT_SANS 同源, 保证图表文字与页面文字一致
# (Altair 图表在独立 iframe 内渲染, 无法继承 UNIFIED_CSS, 只能写进 spec)
CHART_FONT = FONT_SANS
# 数值标签用等宽体(参照 tools/console_template.html 的 .stat / .tbl):
# 等宽 + tabular 让不同图之间的数字列宽一致, 纵向扫读时小数点能对齐。
CHART_MONO = FONT_MONO

# 与设计令牌同源的分类色板(顺序 = 参照控制台 PALETTE: 强调色 → 蓝 → 琥珀 → 紫 → 红 → 强调色深)
PALETTE = [
    T.get("p1", "#2f86e0"), T.get("p2", "#2aa3c9"), T.get("p3", "#c8871a"),
    T.get("p4", "#5b6f8c"), T.get("p5", "#d0453c"), T.get("p6", "#63a8e8"),
    T.get("p7", "#86c9d8"), T.get("p8", "#3a6f9e"),
    T.get("p9", "#8a7f6a"), T.get("p10", "#93a6bb"),
]

BG = T.get("bg1", "#0b110e")
BG3 = T.get("bg3", "#17211c")
ACCENT = T.get("accent", "#2f86e0")
ACCENT2 = T.get("accent2", "#26a877")
GRID = T.get("line", "#1e2a24")
TXT1 = T.get("t1", "#e9f1ec")
TXT2 = T.get("t2", "#a0b2a8")
TXT3 = T.get("t3", "#7c8e84")

# 三分类语义色(主胜 / 平局 / 客胜), 与 KPI 卡保持一致
OUTCOME_COLORS = {
    "主胜": ACCENT, "home": ACCENT, "H": ACCENT, "win": ACCENT, "W": ACCENT,
    "平局": T.get("gold", "#e6b256"), "draw": T.get("gold", "#e6b256"), "D": T.get("gold", "#e6b256"),
    "客胜": T.get("red", "#f0685c"), "away": T.get("red", "#f0685c"),
    "A": T.get("red", "#f0685c"), "loss": T.get("red", "#f0685c"), "L": T.get("red", "#f0685c"),
}


def available() -> bool:
    """Altair 是否可用(不可用时所有图表函数自动回退)。"""
    return alt is not None


def outcome_color(label, default=None):
    """按 主胜/平局/客胜(或 W/D/L) 取语义色。"""
    return OUTCOME_COLORS.get(str(label), default or ACCENT)


# ============ 内部工具 ============
# Altair 6 对显式 ``type=`` 参数只接受完整类型名, 不接受 :N/:O/:Q/:T 短码
_TYPE = {"N": "nominal", "O": "ordinal", "Q": "quantitative",
         "T": "temporal", "G": "geojson",
         "nominal": "nominal", "ordinal": "ordinal",
         "quantitative": "quantitative", "temporal": "temporal"}


def _ttype(code, default="nominal"):
    """类型短码 -> 完整类型名。"""
    return _TYPE.get(str(code), default)


def tip(*cols):
    """公开的 tooltip 构造器(供页面侧自定义悬浮信息)。

    用法::

        VIZ.tip((t("球队"), "N"), (t("进球"), "Q"), (t("失球"), "Q"))
    """
    return _tip(*cols)


def _clean(**kw):
    """Altair 6 会校验 schema, 显式 None 会被判为非法值 —— 统一剔除。"""
    return {k: v for k, v in kw.items() if v is not None}


def _ax(**kw):
    """构造坐标轴配置: 剔除 None(仅 title 允许为 None 表示不显示轴标题)。

    默认加上标签防重叠策略(redesign 图表审计: 窄图里刻度会挤成一团):
      · labelOverlap="greedy" —— 自动丢弃挤不下的标签(优先后面的刻度)
      · labelFlush=False      —— 首尾标签不贴边, 避免被裁切
    调用方可覆盖 labelAngle / tickCount / format 等。
    """
    title = kw.pop("title", None)
    kw.setdefault("labelOverlap", "greedy")
    kw.setdefault("labelFlush", False)
    return alt.Axis(title=title, **_clean(**kw))


def _tip(*cols):
    """构造 tooltip: _tip("球队:N", ("Elo:Q", ",.1f"))

    Altair 6 会严格校验 ``type``, 只接受完整类型名, 因此这里统一做短码转换。
    """
    out = []
    for c in cols:
        if isinstance(c, (tuple, list)):
            field = c[0]
            ttype = c[1] if len(c) > 1 else "N"
            fmt = c[2] if len(c) > 2 else None
            kw = {"field": field, "type": _ttype(ttype)}
            if fmt:
                kw["format"] = fmt
            out.append(alt.Tooltip(**kw))
        else:
            field, _, ttype = str(c).partition(":")
            out.append(alt.Tooltip(field, type=_ttype(ttype or "N")))
    return out


def _theme(ch, height=None, title=None, unit=None):
    """给图表注入统一的深色主题配置, 并设置 height / title。"""
    if alt is None:
        return ch
    props = {}
    if height:
        props["height"] = height
    if title:
        props["title"] = title
    if props:
        ch = ch.properties(**props)
    return (ch
            .configure(background=BG, font=CHART_FONT)
            .configure_view(stroke=None, fill=BG)
            .configure_axis(
                labelColor=TXT2, titleColor=TXT3, labelFontSize=11, titleFontSize=11,
                labelPadding=6, titlePadding=8, domain=False, ticks=False,
                gridColor=GRID, gridOpacity=1, labelLimit=180,
                labelFont=CHART_FONT, titleFont=CHART_FONT, titleFontWeight="normal")
            .configure_axisX(grid=False)
            .configure_axisY(grid=True)
            .configure_legend(
                labelColor=TXT2, titleColor=TXT3, labelFontSize=11, titleFontSize=11,
                symbolSize=110, symbolStrokeWidth=0, padding=8, orient="top",
                direction="horizontal", labelFont=CHART_FONT, titleFont=CHART_FONT)
            .configure_title(color=TXT1, fontSize=13, fontWeight=600, anchor="start",
                             offset=10, font=CHART_FONT)
            .configure_range(category=PALETTE))


def render(ch, key=None, fallback=None, fallback_kind="table"):
    """渲染图表; Altair 不可用时按 fallback_kind 回退。"""
    if alt is None or ch is None:
        return _fallback(fallback, fallback_kind)
    kw = {"key": key} if key else {}
    try:
        st.altair_chart(ch, width="stretch", theme=None, **kw)
        return True
    except TypeError:
        pass
    try:
        st.altair_chart(ch, use_container_width=True, theme=None, **kw)
        return True
    except TypeError:
        pass
    try:
        st.altair_chart(ch, use_container_width=True, **kw)
        return True
    except Exception:                                 # pragma: no cover
        return _fallback(fallback, fallback_kind)


def _fallback(df, kind="table"):
    """Altair 缺失时的兜底渲染。"""
    if df is None or len(df) == 0:
        return False
    try:
        if kind == "line" and df.shape[1] >= 2:
            st.line_chart(df.set_index(df.columns[0])[df.columns[1]], height=280)
            return True
    except Exception:                                 # pragma: no cover
        pass
    try:
        st.dataframe(df, hide_index=True)
        return True
    except Exception:                                 # pragma: no cover
        return False


def _ok(df):
    return alt is not None and df is not None and len(df) > 0


def show(ch, key=None, fallback=None, fallback_kind="table"):
    """一步完成"构建 -> 渲染": 构建器返回 None 时按 fallback 兜底。

    页面侧的推荐用法::

        VIZ.show(VIZ.bar(df, "球队", "Elo"), key="elo", fallback=df)
    """
    if ch is None:
        return _fallback(fallback, fallback_kind)
    return render(ch, key=key, fallback=fallback, fallback_kind=fallback_kind)


# ============ 柱状 / 排行 ============
def bar(df, x, y, color=None, height=300, rotate=0, fmt=None, title=None,
        key=None, tooltip=None, sort=None, label=False, label_fmt=None,
        y_domain=None, bar_size=None, y_base=None):
    """纵向柱状图(分类 X × 数值 Y)。

    y_domain: 固定 Y 轴范围, 例如 (1400, 1900) —— 用于 "数值集中在高位" 的场景
              (如 Elo 对比: 不设范围时柱子会从 0 起, 差异被压平)。
              ⚠️ 设了 y_domain 必须同时给 y_base, 否则柱子仍从 0 起算、会被裁掉不可见。
    y_base  : 柱子基线(通常 = y_domain 的下界)。
    bar_size: 固定柱宽(像素), 用于类目很少时避免柱子过宽。
    """
    if not _ok(df):
        return None
    color = color or ACCENT
    order = None if sort is False else sort
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:N", **_clean(sort=order),
                axis=_ax(labelAngle=rotate, title=None, labelLimit=150)),
        y=alt.Y(f"{y}:Q", **_clean(scale=(alt.Scale(domain=list(y_domain))
                                          if y_domain else None)),
                axis=_ax(title=None, format=fmt)),
    )
    mk = {"cornerRadiusTopLeft": 5, "cornerRadiusTopRight": 5}
    if bar_size:
        mk["size"] = int(bar_size)
    bars = base.mark_bar(color=color, **mk)
    if y_base is not None:
        bars = bars.encode(y2=alt.Y2(datum=float(y_base)))
    ch = bars.encode(tooltip=tooltip or _tip((x, "N"), (y, "Q", fmt)))
    if label:
        ch = alt.layer(ch, base.mark_text(dy=-7, fontSize=11, color=TXT2,
                                          font=CHART_MONO)
                       .encode(text=alt.Text(f"{y}:Q", format=label_fmt or fmt or ",.0f")))
    return _theme(ch, height, title)


def rank_bar(df, label, value, color=None, height=None, fmt=",.0f", title=None,
             key=None, top=None, sort="-x", gradient=False, label_text=True,
             tooltip=None, bar_size=None):
    """横向排行条: 默认按数值降序, 条尾带数值标签。

    bar_size: 固定条粗(像素)。类目很少时(如只有 1~2 个模型)不设会撑满整块画布。
    """
    if not _ok(df):
        return None
    d = df.copy()
    if top:
        try:
            d = d.nlargest(int(top), value)
        except Exception:                             # pragma: no cover
            d = d.head(int(top))
    # 类目很少时: 限制条粗 + 收紧高度, 避免"一根柱子占满整屏"
    if bar_size is None and len(d) <= 3:
        bar_size = 34
    height = height or (max(150, 30 * len(d) + 56) if len(d) > 3 else 150)
    base = alt.Chart(d).encode(
        y=alt.Y(f"{label}:N", sort=sort,
                axis=_ax(title=None, labelLimit=170, labelOverlap=False)),
        x=alt.X(f"{value}:Q", axis=_ax(title=None, format=fmt, tickCount=5)),
    )
    if color:
        bar_enc = {"color": alt.value(color)}
    elif gradient:
        # 明→暗的暖色渐变: 两端都取暖色, 并强制 RGB 插值 ——
        # 默认 LAB 插值会让「浅冷白 → 深红」的路径穿过品红/淡紫, 在浅色主题下
        # 中段数值会渲染成刺眼的粉色条, 与登录页的暖橙语言不符。
        bar_enc = {"color": alt.Color(f"{value}:Q", legend=None,
                                      scale=alt.Scale(
                                          range=[T.get("accent_tint", "#f7dbce"), ACCENT],
                                          interpolate="rgb"))}
    else:
        bar_enc = {"color": alt.value(ACCENT)}
    mk = {"cornerRadiusEnd": 5}
    if bar_size:
        mk["size"] = int(bar_size)
    bars = base.mark_bar(**mk).encode(
        tooltip=tooltip or _tip((label, "N"), (value, "Q", fmt)), **bar_enc)
    ch = bars
    if label_text:
        ch = alt.layer(bars, base.mark_text(align="left", dx=6, fontSize=11,
                                            color=TXT2, baseline="middle",
                                            font=CHART_MONO)
                       .encode(text=alt.Text(f"{value}:Q", format=fmt)))
    return _theme(ch, height, title)


def grouped_bar(df, x, series, value, height=320, colors=None, fmt=None, title=None,
                key=None, tooltip=None, rotate=0):
    """分组柱状图(长表: x / series / value)。"""
    if not _ok(df):
        return None
    ch = (alt.Chart(df)
          .mark_bar(cornerRadiusTopLeft=4, cornerRadiusTopRight=4)
          .encode(
              x=alt.X(f"{x}:N", axis=_ax(labelAngle=rotate, title=None)),
              xOffset=alt.XOffset(f"{series}:N"),
              y=alt.Y(f"{value}:Q", axis=_ax(title=None, format=fmt)),
              color=alt.Color(f"{series}:N",
                              scale=alt.Scale(range=colors or PALETTE),
                              legend=alt.Legend(title=None)),
              tooltip=tooltip or _tip((x, "N"), (series, "N"), (value, "Q", fmt))))
    return _theme(ch, height, title)


def stacked_bar(df, x, series, value, height=320, colors=None, fmt=None, title=None,
                key=None, percent=False, tooltip=None, rotate=0):
    """堆叠柱状图(长表: x / series / value)。"""
    if not _ok(df):
        return None
    y_enc = (alt.Y(f"{value}:Q", stack="normalize", axis=_ax(title=None, format=".0%"))
             if percent else
             alt.Y(f"{value}:Q", stack="zero", axis=_ax(title=None, format=fmt)))
    tp = list(tooltip or _tip((x, "N"), (series, "N"), (value, "Q", fmt)))
    if percent:
        tp.append(alt.Tooltip(f"{value}:Q", title="占比", format=".1%"))
    ch = (alt.Chart(df)
          .mark_bar(stroke=BG, strokeWidth=1.2)
          .encode(
              x=alt.X(f"{x}:N", axis=_ax(labelAngle=rotate, title=None)),
              y=y_enc,
              color=alt.Color(f"{series}:N", scale=alt.Scale(range=colors or PALETTE),
                              legend=alt.Legend(title=None)),
              tooltip=tp))
    return _theme(ch, height, title)


# ============ 趋势 ============
def line(df, x, y, color=None, height=300, area=False, fmt=None, point=False,
         title=None, key=None, x_type="T", time_unit=None, tooltip=None, x_title=None,
         tick_count=None):
    """单序列折线 / 面积图。

    tick_count: 定量轴的刻度数量上限。窄图(如并排两张)里时间轴刻度会挤在一起,
                传 5~6 可显著改善; 不传则交给 Vega 的 labelOverlap 自动丢弃。
    """
    if not _ok(df):
        return None
    color = color or ACCENT
    x_enc = alt.X(f"{x}:{x_type}", **_clean(timeUnit=time_unit),
                  axis=_ax(title=x_title, labelAngle=0,
                           tickCount=tick_count,
                           format="%Y-%m" if x_type == "T" else None))
    y_enc = alt.Y(f"{y}:Q", axis=_ax(title=None, format=fmt))
    common = dict(x=x_enc, y=y_enc, tooltip=tooltip or _tip((x, x_type), (y, "Q", fmt)))

    if area:
        ln = (alt.Chart(df)
              .mark_area(line={"color": color, "strokeWidth": 2.4}, interpolate="monotone",
                         color=alt.Gradient(gradient="linear",
                                            stops=[alt.GradientStop(
                                                color="transparent", offset=0),
                                                alt.GradientStop(
                                                    color=T.get("accent_soft",
                                                                "rgba(47,134,224,0.12)"),
                                                    offset=1)],
                                            x1=1, x2=1, y1=1, y2=0))
              .encode(**common))
    else:
        ln = (alt.Chart(df)
              .mark_line(color=color, strokeWidth=2.4, interpolate="monotone")
              .encode(**common))

    ch = ln
    if point:
        pts = (alt.Chart(df)
               .mark_point(color=color, size=24, filled=True, stroke=BG, strokeWidth=1)
               .encode(**common))
        ch = alt.layer(ln, pts)
    return _theme(ch, height, title)


def multi_line(df, x, series, value, height=320, colors=None, fmt=None, title=None,
               key=None, x_type="T", time_unit=None, stroked=True, tooltip=None,
               diagonal=None, x_range=None, tick_count=None):
    """多序列折线(长表: x / series / value)。

    diagonal   : 传入参考线名称(如 "理想校准")时, 追加一条 y=x 的虚线,
                 用于概率校准曲线等"越贴近参考线越好"的场景。
    tick_count : 定量轴刻度上限(窄图里防止刻度文字重叠)。
    """
    if not _ok(df):
        return None
    d = df
    if diagonal:
        xs = pd.to_numeric(d[x], errors="coerce")
        lo, hi = (x_range if x_range else (float(xs.min()), float(xs.max())))
        ref = pd.DataFrame({x: [lo, hi], series: [diagonal, diagonal],
                            value: [lo, hi]})
        d = pd.concat([d, ref], ignore_index=True)
    ch = (alt.Chart(d)
          .mark_line(strokeWidth=2.2, interpolate="monotone")
          .encode(
              x=alt.X(f"{x}:{x_type}", **_clean(timeUnit=time_unit),
                      axis=_ax(title=None, labelAngle=0,
                               labelOverlap="greedy", tickCount=tick_count)),
              y=alt.Y(f"{value}:Q", axis=_ax(title=None, format=fmt)),
              color=alt.Color(f"{series}:N",
                              scale=alt.Scale(range=(colors or PALETTE) +
                                              [T.get("t3", "#5c6773")]),
                              legend=alt.Legend(title=None)),
              strokeDash=alt.StrokeDash(f"{series}:N", legend=None) if stroked else None,
              tooltip=tooltip or _tip((x, x_type), (series, "N"), (value, "Q", fmt))))
    return _theme(ch, height, title)


def scatter(df, x, y, color=None, height=320, size=None, fmt_x=None, fmt_y=None,
            title=None, key=None, tooltip=None):
    """散点图(用于相关性 / 分布观察)。"""
    if not _ok(df):
        return None
    enc = dict(
        x=alt.X(f"{x}:Q", axis=_ax(title=None, format=fmt_x)),
        y=alt.Y(f"{y}:Q", axis=_ax(title=None, format=fmt_y)),
        tooltip=tooltip or _tip((x, "Q", fmt_x), (y, "Q", fmt_y)),
    )
    if size:
        enc["size"] = alt.Size(f"{size}:Q", legend=None, scale=alt.Scale(range=[30, 420]))
    ch = alt.Chart(df).mark_circle(
        color=color or ACCENT, opacity=0.62, stroke=BG, strokeWidth=0.6).encode(**enc)
    return _theme(ch, height, title)


def histogram(df, x, bins=30, color=None, height=280, fmt=None, title=None, key=None):
    """数值分布直方图。"""
    if not _ok(df):
        return None
    ch = (alt.Chart(df)
          .mark_bar(color=color or T.get("blue", "#2aa3c9"), cornerRadiusTopLeft=3,
                    cornerRadiusTopRight=3)
          .encode(
              x=alt.X(f"{x}:Q", bin=alt.Bin(maxbins=int(bins)),
                      axis=_ax(title=None, format=fmt)),
              y=alt.Y("count():Q", axis=_ax(title=None)),
              tooltip=[alt.Tooltip("count():Q", title="数量")]))
    return _theme(ch, height, title)


# ============ 矩阵热力图 ============
def heatmap(df, x, y, value, height=320, fmt=None, title=None, key=None,
            low=None, mid=None, high=None, show_text=True, x_title=None, y_title=None,
            width=None, cell=78, order=True):
    """矩阵热力图(混淆矩阵 / 交叉统计)。

    width/cell : 画布宽度与单格宽度。默认按列数自适应, 避免画布过窄导致数字挤在一起。
    order      : True 时按数据出现顺序排列坐标轴(Vega 默认会按计数重排, 会让类别乱序)。
    """
    if not _ok(df):
        return None
    rng = [low or T.get("accent_tint", "#f7dbce"), mid or ACCENT2, high or ACCENT]
    sort_x = sort_y = None
    if order:
        try:
            sort_x = list(dict.fromkeys(df[x].astype(str).tolist()))
            sort_y = list(dict.fromkeys(df[y].astype(str).tolist()))
        except Exception:                             # pragma: no cover
            sort_x = sort_y = None
    base = alt.Chart(df).encode(
        x=alt.X(f"{x}:N", **_clean(sort=sort_x),
                axis=_ax(title=x_title, labelAngle=0, domain=False, ticks=False)),
        y=alt.Y(f"{y}:N", **_clean(sort=sort_y),
                axis=_ax(title=y_title, domain=False, ticks=False)),
    )
    rect = base.mark_rect(cornerRadius=4, stroke=BG, strokeWidth=2).encode(
        color=alt.Color(f"{value}:Q", legend=None,
                        scale=alt.Scale(range=rng, interpolate="rgb")),
        tooltip=_tip((y, "N"), (x, "N"), (value, "Q", fmt)))
    ch = rect
    if show_text:
        ch = alt.layer(rect, base.mark_text(fontSize=12, fontWeight=600, color=TXT1,
                                            font=CHART_MONO)
                       .encode(text=alt.Text(f"{value}:Q", format=fmt or ",.0f")))
    ch = _theme(ch, height, title)
    if width is None:
        try:
            nx = df[x].nunique()
        except Exception:                             # pragma: no cover
            nx = 3
        width = max(200, int(cell) * int(nx) + 80)
    return ch.properties(width=width)


# ============ 占比 ============
def donut(df, label, value, colors=None, height=300, title=None, key=None,
          fmt=",.0f", center=None):
    """环形占比图。"""
    if not _ok(df):
        return None
    radius = max(60, min(115, int(height / 2) - 34))
    ch = (alt.Chart(df)
          .mark_arc(innerRadius=int(radius * 0.62), outerRadius=radius,
                    stroke=BG, strokeWidth=2, cornerRadius=2)
          .encode(
              theta=alt.Theta(f"{value}:Q", stack=True),
              color=alt.Color(f"{label}:N", scale=alt.Scale(range=colors or PALETTE),
                              legend=alt.Legend(title=None)),
              tooltip=_tip((label, "N"), (value, "Q", fmt))))
    return _theme(ch, height, title)


def prob_bar(df, label, value, colors=None, height=180, pct=True, title=None,
             key=None, fmt=".1%", domain=(0, 1), tooltip=None):
    """水平概率条(主胜 / 平局 / 客胜), 固定顺序不排序。"""
    if not _ok(df):
        return None
    height = height or max(150, 34 * len(df) + 46)
    if colors is None:
        colors = [outcome_color(v) for v in df[label].tolist()]
    base = alt.Chart(df).encode(
        y=alt.Y(f"{label}:N", sort=list(df[label].tolist()),
                axis=_ax(title=None, labelLimit=200)),
        x=alt.X(f"{value}:Q", scale=alt.Scale(domain=list(domain)),
                axis=_ax(title=None, format=fmt if pct else None)),
        color=alt.Color(f"{label}:N", scale=alt.Scale(domain=list(df[label].tolist()),
                                                      range=colors), legend=None),
    )
    bars = base.mark_bar(cornerRadiusEnd=5, height=20).encode(
        tooltip=tooltip or _tip((label, "N"), (value, "Q", fmt)))
    ch = alt.layer(bars, base.mark_text(align="left", dx=6, baseline="middle",
                                        fontSize=11, color=TXT2, font=CHART_MONO)
                   .encode(text=alt.Text(f"{value}:Q", format=fmt)))
    return _theme(ch, height, title)


# ============ 雷达图(能力图) ============
def radar(df, dim, value, series=None, height=380, domain_max=None, colors=None,
          title=None, key=None, fill_opacity=0.22, label_factor=1.14,
          rings=(0.25, 0.5, 0.75, 1.0), tooltip=None, width=None):
    """雷达图 —— 球员/球队多维能力对比。

    参数
    ----
    df         : 长表, 含 [维度列, 数值列]; 多序列时再加 [系列列]
    dim / value: 维度列名 / 数值列名(0~domain_max)
    series     : 系列列名(如 "球队"/"球员"); 为空则画单条
    domain_max : 量纲上限, 默认按数据向上取整到 10 的倍数

    示例::

        long = pd.DataFrame({t("能力"): dims, t("数值"): vals, t("球队"): [name]*len(dims)})
        VIZ.show(VIZ.radar(long, t("能力"), t("数值"), series=t("球队")), fallback=long)
    """
    if not _ok(df):
        return None
    d = df.copy()
    d[dim] = d[dim].astype(str)
    order = list(dict.fromkeys(d[dim].tolist()))
    n = len(order)
    if n < 3:
        return None
    vals = pd.to_numeric(d[value], errors="coerce").fillna(0)
    if domain_max is None:
        domain_max = max(10.0, math.ceil(float(vals.max() or 1) / 10.0) * 10)

    idx = {k: i for i, k in enumerate(order)}
    # 从正上方开始顺时针排列, 视觉上更符合习惯
    ang = {k: math.pi / 2 - 2.0 * math.pi * i / n for k, i in idx.items()}
    d["_i"] = d[dim].map(idx)
    v = vals.clip(upper=domain_max).to_numpy(dtype=float)
    # 注意: ang 是以"维度名"为键, 这里必须用"索引"换算角度(用错会得到 NaN 坐标)
    a = np.array([math.pi / 2 - 2.0 * math.pi * int(i) / n for i in d["_i"]],
                 dtype=float)
    d["_x"], d["_y"] = v * np.cos(a), v * np.sin(a)
    d["_series"] = d[series].astype(str) if series else "value"

    R = float(domain_max)
    lim = R * (label_factor + 0.06)
    scale = alt.Scale(domain=[-lim, lim], zero=False)

    def _x(f="x"):
        return alt.X(f, scale=scale, axis=None)

    def _y(f="y"):
        return alt.Y(f, scale=scale, axis=None)

    layers = []

    # 注意: Vega-Lite 的 mark_line 对"定量 x"会默认按 x 排序, 会打乱多边形顶点顺序,
    #       因此所有折线图层都必须显式给出 order 通道(用递增的 _o 列)。
    # ① 同心网格环: 每环一个独立图层
    for r in rings:
        pts = [{"x": R * r * math.cos(ang[k]), "y": R * r * math.sin(ang[k]), "_o": i}
               for i, k in enumerate(order + [order[0]])]
        layers.append(alt.Chart(pd.DataFrame(pts))
                      .mark_line(color=GRID, strokeWidth=1)
                      .encode(x=_x(), y=_y(), order=alt.Order("_o:Q")))

    # ② 辐射线: 每个维度"圆心 -> 外圈"两点一组
    sp = []
    for k in order:
        sp.append({"x": 0.0, "y": 0.0, "g": k, "_o": 0})
        sp.append({"x": R * math.cos(ang[k]), "y": R * math.sin(ang[k]), "g": k, "_o": 1})
    layers.append(alt.Chart(pd.DataFrame(sp))
                  .mark_line(color=GRID, strokeWidth=1)
                  .encode(x=_x(), y=_y(), detail=alt.Detail("g:N"),
                          order=alt.Order("_o:Q")))

    # ③ 每个系列一条闭合折线 + 顶点圆点(带 tooltip)
    palette = colors or PALETTE
    for i, (s, g) in enumerate(d.groupby("_series", sort=False)):
        g = g.sort_values("_i")
        col = palette[i % len(palette)]
        pts = [{"x": float(x), "y": float(y), "_o": j}
               for j, (x, y) in enumerate(zip(g["_x"], g["_y"]))]
        pts.append({"x": pts[0]["x"], "y": pts[0]["y"], "_o": len(pts)})   # 闭合
        layers.append(alt.Chart(pd.DataFrame(pts))
                      .mark_line(strokeWidth=2.2, color=col, fill=col,
                                 fillOpacity=fill_opacity)
                      .encode(x=_x(), y=_y(), order=alt.Order("_o:Q")))
        tip_cols = [(dim, "N"), (value, "Q")]
        if series:
            tip_cols.insert(0, (series, "N"))
        layers.append(alt.Chart(g)
                      .mark_point(size=46, color=col, filled=True, stroke=BG,
                                  strokeWidth=1)
                      .encode(x=_x("_x"), y=_y("_y"),
                              tooltip=tooltip or _tip(*tip_cols)))

    # ④ 维度标签(外圈再外推一点)
    lab = pd.DataFrame([{"x": R * label_factor * math.cos(ang[k]),
                         "y": R * label_factor * math.sin(ang[k]), "k": k}
                        for k in order])
    layers.append(alt.Chart(lab)
                  .mark_text(fontSize=11, color=TXT2, fontWeight=600)
                  .encode(x=_x(), y=_y(), text=alt.Text("k:N")))

    ch = alt.layer(*layers)
    ch = _theme(ch, height, title)
    # 关键: 横纵同域 + 画布正方形 -> 等比例(否则被拉成椭圆)
    return ch.properties(width=height if width is None else width)
