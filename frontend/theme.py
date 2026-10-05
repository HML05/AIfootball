"""
足球分析系统 - 统一设计系统 (theme.py)  v5.0  "Matchday Gazette / 赛事公报"

设计语言: 足球数据公报 (editorial print almanac)
  整站 = 一份印刷出来的足球数据年鉴/比赛日公报:
  · 纸面  —— 暖米纸 #f2ecdc 做底, 深林墨 #0e2a22 当油墨; 层次靠纸色阶梯
             (paper-2 #eae3d1 / paper-3 #d9d2c2) 与 1px 墨色发丝线, 扁平无玻璃。
  · 双主题 —— 晨报 Gazette(暖米纸 + 林墨, 默认, 旗舰)
             / 晚报 Evening(墨版: 林墨纸 #0e2a22 + 米色字, 同构反色)
  · 主色  —— 绯红 #db3356 单一强调, 极克制: 只给激活态、主按钮、头名与关键数字;
             语义色各司其职守恒全站: 胜/墨绿 · 平/砖黄 · 负/砖红 · 信息/蓝。
  · 标题  —— 衬线展示体: 拉丁 Georgia/Times, 中文落宋体系(公报标题的骨架);
             正文系统无衬线; 数据一律等宽 tabular(年鉴表格语言)。
  · 版式  —— 编号眉题(mono 大写宽字距)、双细线版头、栏线画布(196px 栏距),
             发丝线分隔取代卡片套卡片; 圆角收紧到 4/6/10, 扁平 + 1px 底影。
  · 按钮  —— 描边胶囊(透明底 + 墨色边, hover 墨 5%), 主按钮绯红实底。

结构约定(与 v3/v4 相同, 向后兼容):
  1. TOKENS  —— 设计令牌(两套主题键名完全一致)
  2. CSS     —— 全局样式(前端 app.py 与后台 admin.py 共用同一份)
  3. 组件     —— page_header / section / metric_row / hero / empty_state / badge ...

约束(继承 v3, 见 docs/UI协作交接说明.md):
  · 前端(app.py)与后台(admin.py)必须引用同一份 CSS, 不允许各自内联 <style>
  · 既有令牌键名与组件函数签名保持向后兼容: 只做新增/增强, 不重命名
  · 登录页(docs/console/login.html)不在本文件管辖范围, 保持原样
"""
import re
import sys

import streamlit as st

# ============ 配置常量 ============
API_BASE = "http://127.0.0.1:8000/api"
FRONTEND_URL = "http://127.0.0.1:8501"
ADMIN_URL = "http://127.0.0.1:8502"

# ============ 字体栈 ============
# 全部为本地字体(离线可用, 不依赖 CDN / 联网):
#   · FONT_SERIF   —— 展示标题: 拉丁 Georgia/Times(年鉴衬线), 中文落宋体系
#   · FONT_SANS    —— 界面正文与控件 (系统无衬线)
#   · FONT_MONO    —— 眉题 / 数值 / 代码 (等宽 tabular)
FONT_SERIF = ('Georgia, "Times New Roman", "Nirmala UI", '
              '"Songti SC", "STSong", "STZhongsong", "SimSun", serif')
FONT_SANS = ('-apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", '
             '"Hiragino Sans GB", "Microsoft YaHei", system-ui, sans-serif')
# 标题走衬线路径 —— 公报版头/章节题的字形骨架
FONT_TITLE = FONT_SERIF
# 展示层保留一个无衬线别名, 供"不适合衬线的场合"显式引用
FONT_DISPLAY = FONT_SANS
FONT_MONO = ('ui-monospace, "JetBrains Mono", "SFMono-Regular", "Cascadia Mono", '
             'Consolas, "Courier New", monospace')

# ============ 设计令牌(双主题) ============
# 浅色 = 晨报(暖米纸公报, 旗舰默认); 深色 = 晚报(林墨纸反色版)。
# 两套令牌**键名完全一致**, 因此 theme / viz / blocks / 页面代码无需分叉。
_LIGHT = {
    # ---- 晨报: 暖米纸 + 深林墨 + 绯红 ----
    # 纸色阶梯(由浅到深: 画布 -> 侧栏/板面 -> 面板 -> 内嵌/hover)
    "bg0": "#f2ecdc", "bg1": "#f6f1e3", "bg2": "#fbf7ec", "bg3": "#eae3d1",
    # 发丝缝: 墨色三层透明度, 只承担"分界", 不承担装饰
    "line": "rgba(14,42,34,0.13)",
    "line_strong": "rgba(14,42,34,0.26)",
    "line_accent": "rgba(219,51,86,0.42)",
    # 文本: 墨色四层, t3 在 bg2 上约 4.7:1 满足 WCAG AA
    "t1": "#0e2a22", "t2": "#3d4f47", "t3": "#65736b",
    # 主色: 绯红(公报表头/头名标记色), 米白字压在上面
    "accent": "#db3356", "accent2": "#b8254a", "accent_ink": "#fdf7ee",
    "accent_soft": "rgba(219,51,86,0.08)",
    "accent_tint": "#f3d8de",
    # 语义: 胜/墨绿 · 平/砖黄 · 负/砖红(与绯红拉开) · 信息/蓝
    "gold": "#a8740a", "purple": "#6b5d8a", "blue": "#2a6fc4",
    "red": "#c23b2e", "ok": "#1e7a4c",
    # 强调橙: 只用于峰值/首选/第一名这类单点强调
    "orange": "#c96a12", "orange_soft": "rgba(201,106,18,0.10)",
    "orange_line": "rgba(201,106,18,0.32)",
    "gold_soft": "rgba(168,116,10,0.10)", "purple_soft": "rgba(107,93,138,0.10)",
    "blue_soft": "rgba(42,111,196,0.10)", "red_soft": "rgba(194,59,46,0.10)",
    # 状态点: 实心核 + 一圈同色晕
    "ok_soft": "rgba(30,122,76,0.10)", "ok_halo": "rgba(30,122,76,0.16)",
    "cool": "#2a6fc4", "cool_glow": "rgba(42,111,196,1)",
    "warm_deep": "#a8740a", "warm_glow": "rgba(168,116,10,1)",
    # 圆角: 印刷件是"挺括的" —— 4 控件 / 6 内件 / 10 面板 / 999 胶囊
    "r1": "4px", "r2": "6px", "r3": "10px", "pill": "999px", "r4": "12px",
    # 布局尺度(与 v3 保持一致, 页面结构不动)
    "sidebar_w": "252px", "pad": "26px", "topbar_h": "66px",
    # 投影: 纸面只需要 1px 底影 + 极轻的远影, 不带色相
    "shadow": ("0 1px 0 rgba(14,42,34,0.05), "
               "0 18px 38px -24px rgba(14,42,34,0.28)"),
    "shadow_sm": "0 1px 0 rgba(14,42,34,0.06), 0 8px 18px -12px rgba(14,42,34,0.16)",
    # 主按钮: 绯红实色(报纸头版的绯红块), 不做渐变
    "accent_grad": "#db3356",
    "accent_shadow": "0 10px 22px -12px rgba(219,51,86,0.45)",
    "inset_hl": "none",
    # 表面(继承 v3 键名, 语义为"纸面"): 侧栏纸 / 面板纸 / 墨线
    "glass": "#f6f1e3", "glass_strong": "#fbf7ec",
    "glass_line": "rgba(14,42,34,0.13)",
    # 悬浮层(下拉/弹层/抽屉): 面板纸 + 墨线
    "glass_lite": "rgba(14,42,34,0.045)", "glass_mid": "#fbf7ec",
    "glass_edge": "rgba(14,42,34,0.18)",
    "glass_blur": "none",
    "glass_hl": "none",
    "glass_shadow": "0 14px 30px -18px rgba(14,42,34,0.24)",
    # 画布: 栏线(196px 栏距的竖向墨线) + 顶部版头粗细分栏线
    "scene": ("repeating-linear-gradient(90deg, rgba(14,42,34,0.045) 0px, "
              "rgba(14,42,34,0.045) 1px, transparent 1px, transparent 196px), "
              "linear-gradient(180deg, rgba(14,42,34,0.05) 0px, "
              "rgba(14,42,34,0.05) 1px, transparent 1px, transparent 100%)"),
    "hero_filter": "none",
    "bg_chart": "#fbf7ec",
    # 浏览器表面色(滚动条滑块 / 插入符)
    "thumb": "#c9bfa5", "thumb_hover": "#a99f83", "caret": "#db3356",
    "grain_opacity": "0.05", "glow_opacity": "0.0",
    # 点阵纸纹的像素色(墨点极淡)
    "dot": "rgba(14,42,34,0.05)",
    # 图表类别色板: 绯红打头, 林墨/蓝/砖黄/砖红/鼠尾草依次拉开
    "p1": "#db3356", "p2": "#14503c", "p3": "#2a6fc4", "p4": "#c98a1b",
    "p5": "#1e7a4c", "p6": "#c2452d", "p7": "#6b5d8a", "p8": "#2a8a7a",
    "p9": "#7a8c3f", "p10": "#8a938c",
    # 统一缓动
    "ease": "cubic-bezier(.2,.75,.2,1)",
    "font_title": FONT_TITLE,
}

_DARK = {
    # ---- 晚报: 林墨纸 + 米色字 + 绯红(同构反色) ----
    # 墨色阶梯(由深到浅: 画布 -> 侧栏 -> 面板 -> 内嵌/hover)
    "bg0": "#0e2a22", "bg1": "#123026", "bg2": "#16352a", "bg3": "#1d4033",
    # 发丝缝: 米色三层透明度
    "line": "rgba(242,236,220,0.13)",
    "line_strong": "rgba(242,236,220,0.26)",
    "line_accent": "rgba(224,68,100,0.45)",
    # 文本: 米色四层, t3 在 bg2 上约 4.6:1 满足 WCAG AA
    "t1": "#f2ecdc", "t2": "#c6c2b1", "t3": "#92a197",
    # 主色: 绯红在墨纸上提亮半档, 米白字压在上面
    "accent": "#e04464", "accent2": "#f0607f", "accent_ink": "#fdf7ee",
    "accent_soft": "rgba(224,68,100,0.14)",
    "accent_tint": "#43222b",
    # 语义: 胜/薄荷绿 · 平/琥珀 · 负/鲑红 · 信息/浅蓝
    "gold": "#e0a83c", "purple": "#a79cc9", "blue": "#6fa8e8",
    "red": "#e06a5a", "ok": "#4cc38a",
    "orange": "#e8933c", "orange_soft": "rgba(232,147,60,0.13)",
    "orange_line": "rgba(232,147,60,0.38)",
    "gold_soft": "rgba(224,168,60,0.13)", "purple_soft": "rgba(167,156,201,0.13)",
    "blue_soft": "rgba(111,168,232,0.13)", "red_soft": "rgba(224,106,90,0.14)",
    "ok_soft": "rgba(76,195,138,0.13)", "ok_halo": "rgba(76,195,138,0.20)",
    "cool": "#6fa8e8", "cool_glow": "rgba(111,168,232,1)",
    "warm_deep": "#e0a83c", "warm_glow": "rgba(224,168,60,1)",
    "r1": "4px", "r2": "6px", "r3": "10px", "pill": "999px", "r4": "12px",
    "sidebar_w": "252px", "pad": "26px", "topbar_h": "66px",
    "shadow": ("0 1px 0 rgba(0,0,0,0.25), "
               "0 18px 38px -22px rgba(0,0,0,0.55)"),
    "shadow_sm": "0 1px 0 rgba(0,0,0,0.25), 0 8px 18px -12px rgba(0,0,0,0.40)",
    "accent_grad": "#e04464",
    "accent_shadow": "0 10px 22px -12px rgba(224,68,100,0.40)",
    "inset_hl": "none",
    "glass": "#123026", "glass_strong": "#16352a",
    "glass_line": "rgba(242,236,220,0.13)",
    "glass_lite": "rgba(242,236,220,0.05)", "glass_mid": "#1a3a2e",
    "glass_edge": "rgba(242,236,220,0.18)",
    "glass_blur": "none",
    "glass_hl": "none",
    "glass_shadow": "0 14px 30px -18px rgba(0,0,0,0.5)",
    # 画布: 栏线(米色极淡) + 顶部版头线
    "scene": ("repeating-linear-gradient(90deg, rgba(242,236,220,0.035) 0px, "
              "rgba(242,236,220,0.035) 1px, transparent 1px, transparent 196px), "
              "linear-gradient(180deg, rgba(242,236,220,0.045) 0px, "
              "rgba(242,236,220,0.045) 1px, transparent 1px, transparent 100%)"),
    "hero_filter": "none",
    "bg_chart": "#16352a",
    "thumb": "#2c4a3e", "thumb_hover": "#3d6151", "caret": "#e04464",
    "grain_opacity": "0.05", "glow_opacity": "0.0",
    "dot": "rgba(242,236,220,0.045)",
    "p1": "#e04464", "p2": "#4cc38a", "p3": "#6fa8e8", "p4": "#e0a83c",
    "p5": "#8fd0b2", "p6": "#e8933c", "p7": "#a79cc9", "p8": "#4ec9b0",
    "p9": "#a3c14a", "p10": "#93a197",
    "ease": "cubic-bezier(.2,.75,.2,1)",
    "font_title": FONT_TITLE,
}


THEMES = {"dark": _DARK, "light": _LIGHT}
# T 是**可变**映射: apply_theme() 每次运行会把它刷成当前主题的值,
# 这样页面/图表/版块里所有 T["..."] 取值自动跟随主题, 无需分叉代码。
T = dict(_LIGHT)

# 兼容旧代码的配色字典
COLORS = {
    "bg_primary": T["bg1"], "bg_secondary": T["bg2"],
    "bg_card": T["bg2"],
    "accent": T["accent"], "accent_light": T["accent_soft"],
    "gold": T["gold"], "gold_light": T["gold_soft"],
    "purple": T["purple"], "purple_light": T["purple_soft"],
    "red": T["red"], "red_light": T["red_soft"],
    "text_primary": T["t1"], "text_secondary": T["t2"], "text_muted": T["t3"],
    "border": T["line_accent"], "border_light": T["line"],
}



# ============ 全局样式 ============
def _build_css(t: dict) -> str:
    """按给定令牌生成整站 CSS(每次运行按当前主题重建)"""
    T = t
    return f"""
<style>
/* ================= 1. 基础与公报纸面 ================= */
html, body, [class*="css"] {{
    font-family: {FONT_SANS};
    -webkit-font-smoothing: antialiased;
    -moz-osx-font-smoothing: grayscale;
    text-rendering: optimizeLegibility;
    font-feature-settings: "kern" 1;
}}
/* 浏览器表面(选区/插入符/滚动条)必须由调色板统一上色 */
::selection {{ background: {T['accent']}; color: {T['accent_ink']}; }}
html, body {{ caret-color: {T['caret']}; accent-color: {T['accent']}; }}
.stApp {{
    background: {T['bg0']};
    /* 公报画布: 196px 栏距的竖向栏线 + 顶部版头线, 再叠一层极淡墨点纸纹;
       全部 fixed 铺满视口, 栏线把"纯色大平面"变成"排好栏的纸面"。 */
    background-image:
        {T['scene']},
        radial-gradient({T['dot']} 1px, transparent 1.4px);
    background-size: auto, 22px 22px;
    background-attachment: fixed, fixed;
    background-repeat: no-repeat, repeat;
    color: {T['t1']};
    counter-reset: gzsec;
}}
.block-container {{ padding: 26px 26px 40px; max-width: 100%; }}
[data-testid="stAppViewContainer"] > .main {{ background: transparent; }}

/* ================= 2. 标题层级(衬线展示体) ================= */
h1 {{ font-size: 1.7rem !important; font-weight: 700 !important;
      letter-spacing: 0; color: {T['t1']} !important;
      margin-bottom: 0.25rem !important; line-height: 1.3 !important;
      text-wrap: balance; }}
h2 {{ font-size: 1.24rem !important; font-weight: 700 !important; letter-spacing: 0;
      color: {T['t1']} !important; margin-top: 1.4rem !important;
      text-wrap: balance; }}
h3 {{ font-size: 1.0rem !important; font-weight: 700 !important; color: {T['t1']} !important; }}
h4 {{ font-size: 0.92rem !important; font-weight: 600 !important; color: {T['t2']} !important; }}
p, li, span, label {{ color: {T['t2']}; }}
strong {{ color: {T['t1']}; }}
a {{ color: {T['accent']}; text-underline-offset: 3px;
     text-decoration-thickness: 1px; }}
code {{ color: {T['accent']}; background: {T['accent_soft']};
        border-radius: 4px; padding: 0.08rem 0.34rem; font-size: 0.85em;
        font-family: {FONT_MONO}; }}

/* 展示标题: 拉丁 Georgia/Times 衬线(年鉴版头骨架), 中文落宋体系 */
h1, h2, .page-head .ph-title, .hero h2, .sec, .brand .b-title, .empty-state .es-title,
.tb-title {{
    font-family: {T['font_title']} !important;
    letter-spacing: 0 !important;
}}

/* ================= 3. 页面头部(版头双细线) ================= */
.page-head {{
    display: flex; align-items: flex-start; justify-content: space-between; gap: 1rem;
    padding: 0.1rem 0 0.9rem 0; border-bottom: 3px double {T['line_strong']};
    margin-bottom: 1.15rem; position: relative;
}}
.page-head .ph-title {{ font-size: 1.72rem; font-weight: 700;
    color: {T['t1']}; display: flex; align-items: center; gap: 0.6rem; line-height: 1.24; }}
.page-head .ph-sub {{ color: {T['t2']}; font-size: 0.89rem; margin-top: 0.38rem;
    max-width: 78ch; line-height: 1.6; }}
.page-head .ph-crumb {{ color: {T['accent']}; font-size: 0.74rem; letter-spacing: 0.14em;
    text-transform: uppercase; margin-bottom: 0.35rem; font-family: {FONT_MONO}; }}
.page-head .ph-meta {{ color: {T['t3']}; font-size: 0.78rem; text-align: right;
    white-space: nowrap; line-height: 1.7; }}

/* ================= 4. 区块标题(编号眉题) ================= */
.sec {{ display: flex; align-items: baseline; gap: 0.55rem;
        font-size: 1.06rem; font-weight: 700; color: {T['t1']};
        margin: 1.5rem 0 0.7rem 0; counter-increment: gzsec; }}
/* 公报栏目编号: "01 ·" 等宽绯红, 取代旧色条 */
.sec::before {{ content: counter(gzsec, decimal-leading-zero) " ·";
                font-family: {FONT_MONO}; font-size: 0.72em; font-weight: 550;
                letter-spacing: 0.08em; color: {T['accent']}; flex: none; }}
.sec-sub {{ color: {T['t3']}; font-size: 0.8rem; font-weight: 400; margin-left: 0.35rem; }}

/* ================= 5. Hero 欢迎横幅(版头纸卡) ================= */
.hero {{
    position: relative; overflow: hidden; margin-bottom: 1.15rem;
    border: 1px solid {T['line']}; border-top: 3px double {T['line_strong']};
    border-radius: {T['r3']}; padding: 1.5rem 1.7rem;
    background: {T['bg2']};
    box-shadow: {T['shadow_sm']};
    display: flex; align-items: center; justify-content: space-between; gap: 1.6rem;
    flex-wrap: wrap;
}}
.hero .hero-body {{ position: relative; z-index: 1; min-width: 0; }}
.hero h2 {{ margin: 0 0 0.45rem 0 !important; font-size: 1.34rem !important;
    font-weight: 700 !important; }}
.hero p {{ color: {T['t2']} !important; font-size: 0.86rem; max-width: 70ch;
    line-height: 1.72; margin: 0; }}
.hero .hero-stats {{ display: flex; gap: 2.3rem; position: relative; z-index: 1;
    flex-wrap: wrap; }}
.hero .hero-stat .v {{ font-family: {T['font_title']}; font-size: 1.72rem; font-weight: 700;
    color: {T['accent']}; font-variant-numeric: tabular-nums; line-height: 1.15; }}
.hero .hero-stat .l {{ font-family: {FONT_MONO}; font-size: 0.68rem; color: {T['t3']};
    margin-top: 0.22rem; letter-spacing: 0.12em; text-transform: uppercase; }}

/* ================= 6. 指标卡 / KPI(纸卡 + 衬线大数字) ================= */
.metric-row {{
    display: grid; gap: 0.7rem; margin: 0.15rem 0 0.25rem 0;
    grid-template-columns: repeat(var(--mc-n, 4), minmax(0, 1fr));
    align-items: stretch;
}}
.metric-card {{
    position: relative; background: {T['bg2']};
    border: 1px solid var(--mc-line, {T['line']});
    border-radius: {T['r2']}; padding: 1rem 1.15rem 1.05rem 1.15rem;
    min-height: 106px; height: 100%; min-width: 0;
    display: flex; flex-direction: column; justify-content: center;
    box-shadow: 0 1px 0 {T['line']};
    transition: border-color .18s ease, background .18s ease;
}}
.metric-card:hover {{ border-color: {T['line_accent']}; background: {T['bg3']}; }}
.metric-card .mc-top {{ display: flex; align-items: center; gap: 0.45rem;
    color: {T['t3']}; font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em;
    line-height: 1.35; overflow-wrap: normal; }}
.metric-card .mc-value {{ color: {T['t1']}; font-size: 1.78rem; font-weight: 700;
    line-height: 1.15; margin-top: 0.35rem; font-variant-numeric: tabular-nums;
    letter-spacing: 0; overflow-wrap: normal; font-family: {T['font_title']}; }}
.metric-card .mc-hint {{ color: {T['t2']}; font-size: 0.76rem; margin-top: 0.3rem;
    line-height: 1.4; overflow-wrap: normal; }}
.metric-card .metric-value {{ color: {T['t1']}; font-size: 1.78rem; font-weight: 700;
    line-height: 1.15; margin-top: 0.35rem; font-variant-numeric: tabular-nums;
    letter-spacing: 0; overflow-wrap: normal; font-family: {T['font_title']}; }}
.metric-card .metric-label {{ color: {T['t3']}; font-size: 0.75rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.06em; overflow-wrap: normal; }}

/* ================= 7. 功能卡 / 能力带 / 信息卡 ================= */
.feature-card {{ background: {T['bg2']}; border: 1px solid var(--fc-line, {T['line']});
    border-radius: {T['r2']}; padding: 1.15rem 1.25rem; height: 100%;
    box-shadow: 0 1px 0 {T['line']};
    transition: border-color .18s ease, background .18s ease; }}
.feature-card:hover {{ border-color: {T['line_accent']}; background: {T['bg3']}; }}
.feature-card .fc-icon {{ font-size: 1.5rem; line-height: 1; color: {T['accent']}; }}
.feature-card .fc-title {{ margin: 0.5rem 0 0.7rem 0; font-size: 1rem;
    font-weight: 700; color: {T['t1']}; }}
.feature-card .fc-list {{ padding-left: 1.1rem; margin: 0; }}
.feature-card .fc-list li {{ color: {T['t2']}; font-size: 0.85rem; margin: 0.3rem 0;
    line-height: 1.6; }}

/* 能力带: 1 张"主打"卡横跨整行 + 2 张"支撑"卡并排 */
.bento {{ display: grid; grid-template-columns: 1fr 1fr; gap: 0.9rem;
    align-items: stretch; }}
.bento-main {{ grid-column: 1 / -1; }}
.bento-main, .bento-item {{ background: {T['bg2']}; border: 1px solid {T['line']};
    border-radius: {T['r2']}; padding: 1.2rem 1.3rem;
    box-shadow: 0 1px 0 {T['line']};
    transition: border-color .18s ease, background .18s ease; }}
.bento-main:hover, .bento-item:hover {{ border-color: {T['line_accent']};
    background: {T['bg3']}; }}
.bento .bt-icon {{ font-size: 1.45rem; line-height: 1; color: {T['accent']}; }}
.bento-item .bt-icon {{ font-size: 1.25rem; }}
.bento .bt-title {{ margin: 0.5rem 0 0.7rem 0; font-size: 1.02rem;
    font-weight: 700; color: {T['t1']}; }}
.bento-item .bt-title {{ font-size: 0.95rem; margin: 0.4rem 0 0.6rem 0; }}
.bento .bt-list {{ padding-left: 1.1rem; margin: 0; }}
.bento-main .bt-list {{ columns: 2; column-gap: 1.9rem; }}
.bento .bt-list li {{ color: {T['t2']}; font-size: 0.86rem; margin: 0.32rem 0;
    line-height: 1.6; break-inside: avoid; }}
.bento-item .bt-list li {{ font-size: 0.83rem; margin: 0.26rem 0; }}

.info-card {{ background: {T['bg2']}; border: 1px solid var(--ic-line, {T['line']});
    border-radius: {T['r2']}; padding: 1rem 1.1rem; height: 100%;
    box-shadow: 0 1px 0 {T['line']};
    transition: border-color .18s ease, background .18s ease; }}
.info-card:hover {{ border-color: {T['line_accent']}; background: {T['bg3']}; }}
.info-card .ic-title {{ color: {T['t1']}; font-size: 0.92rem; font-weight: 700;
    display: flex; align-items: center; gap: 0.45rem; margin-bottom: 0.45rem; }}
.info-card .ic-line {{ color: {T['t2']}; font-size: 0.83rem; line-height: 1.78; }}
.info-card .ic-line.dim {{ color: {T['t3']}; font-size: 0.78rem; }}

/* ================= 8. 状态盒(柔底 + 语义细边 —— 公报的"告示栏") ================= */
.info-box, .success-box, .warn-box, .error-box {{
    border-radius: {T['r1']}; padding: 0.68rem 0.95rem; margin: 0.5rem 0;
    font-size: 0.86rem; border: 1px solid {T['line']}; line-height: 1.6;
    background: {T['bg2']};
}}
.info-box    {{ border-color: color-mix(in srgb, {T['blue']} 38%, transparent);  background: {T['blue_soft']}; }}
.success-box {{ border-color: color-mix(in srgb, {T['ok']} 38%, transparent);    background: {T['ok_soft']}; }}
.warn-box    {{ border-color: color-mix(in srgb, {T['gold']} 42%, transparent);  background: {T['gold_soft']}; }}
.error-box   {{ border-color: color-mix(in srgb, {T['red']} 38%, transparent);   background: {T['red_soft']}; }}

/* ================= 9. 状态行(方形刊点) ================= */
.status-list {{ display: flex; flex-direction: column; gap: 2px; }}
.status-row {{ display: flex; align-items: center; gap: 0.6rem; padding: 0.6rem 0.2rem;
    border-bottom: 1px solid {T['line']}; font-size: 0.86rem; }}
.status-row:last-child {{ border-bottom: none; }}
.status-row .sr-label {{ color: {T['t2']}; min-width: 150px; }}
.status-row .sr-value {{ color: {T['t1']}; font-weight: 600; margin-left: auto;
    text-align: right; font-variant-numeric: tabular-nums; }}
/* 刊点: 小方点(印刷校对符号), live 加呼吸 */
.status-dot {{ width: 7px; height: 7px; border-radius: 1.5px; flex: none;
    background: {T['ok']}; box-shadow: 0 0 0 3px {T['ok_halo']}; }}
.status-dot.off {{ background: {T['t3']}; box-shadow: 0 0 0 3px {T['line']}; }}
.status-dot.warn {{ background: {T['gold']}; box-shadow: 0 0 0 3px {T['gold_soft']}; }}
.status-dot.err {{ background: {T['red']}; box-shadow: 0 0 0 3px {T['red_soft']}; }}
.status-dot.live {{ animation: pulse 1.8s ease-in-out infinite; }}
@keyframes pulse {{ 0%,100% {{ opacity: 1; }} 50% {{ opacity: .35; }} }}

/* 有序步骤序号(绯红方块) */
.step-no {{ width: 26px; height: 26px; border-radius: 4px; flex: none;
    display: flex; align-items: center; justify-content: center;
    font-size: 0.8rem; font-weight: 700; background: {T['accent']};
    color: {T['accent_ink']}; font-family: {FONT_MONO}; }}
.step-list .status-row {{ align-items: flex-start; }}
.step-list .sr-label {{ font-weight: 600; color: {T['t1']}; }}
.step-list .sr-value {{ font-weight: 400; color: {T['t2']}; }}

/* 兼容 admin.py 既有的状态类 */
.status-good {{ color: {T['ok']} !important; font-weight: 600; }}
.status-bad  {{ color: {T['red']} !important; font-weight: 600; }}
.status-warn {{ color: {T['gold']} !important; font-weight: 600; }}

/* ================= 10. 空状态(虚线占位 —— 报纸的"剪角框") ================= */
.empty-state {{
    border: 1px dashed {T['line_accent']}; border-radius: {T['r3']};
    background: {T['bg2']};
    padding: 1.55rem 1.4rem; text-align: center; margin: 0.6rem 0;
}}
.empty-state .es-icon {{ font-size: 1.85rem; line-height: 1; color: {T['accent']}; }}
.empty-state .es-title {{ color: {T['t1']}; font-size: 0.98rem; font-weight: 700;
    margin-top: 0.5rem; }}
.empty-state .es-desc {{ color: {T['t2']}; font-size: 0.85rem; margin-top: 0.38rem;
    line-height: 1.68; }}
.empty-state .es-desc code, .code-chip {{
    background: {T['accent_soft']}; color: {T['accent']};
    border: 1px solid {T['line_accent']}; border-radius: 4px;
    padding: 0.1rem 0.42rem; font-size: 0.79rem;
    font-family: {FONT_MONO};
}}

/* ================= 11. 徽标 / 标签 ================= */
.badge {{ display: inline-block; padding: 0.13rem 0.52rem; border-radius: 3px;
    font-size: 0.73rem; font-weight: 600; border: 1px solid transparent;
    line-height: 1.5; font-family: {FONT_MONO}; letter-spacing: 0.05em; }}
.badge-ok   {{ background: {T['ok_soft']}; color: {T['ok']}; border-color: color-mix(in srgb, {T['ok']} 34%, transparent); }}
.badge-wait {{ background: {T['gold_soft']}; color: {T['gold']}; border-color: color-mix(in srgb, {T['gold']} 32%, transparent); }}
.badge-info {{ background: {T['blue_soft']}; color: {T['blue']}; border-color: color-mix(in srgb, {T['blue']} 32%, transparent); }}
.badge-err  {{ background: {T['red_soft']}; color: {T['red']}; border-color: color-mix(in srgb, {T['red']} 32%, transparent); }}
.badge-mute {{ background: {T['bg3']}; color: {T['t3']}; border-color: {T['line']}; }}

.chip-row {{ display: flex; flex-wrap: wrap; gap: 7px; align-items: center;
    margin: 0.2rem 0 0.4rem 0; }}
.chip {{ display: inline-block; border: 1px solid {T['line']}; border-radius: {T['pill']};
    padding: 0.22rem 0.72rem; color: {T['t3']}; font-size: 0.78rem; }}
.chip.on {{ border-color: {T['accent']}; color: {T['accent']};
    background: {T['accent_soft']}; font-weight: 600; }}

/* ================= 12. 表格容器(年鉴表格: 表头双细线) ================= */
[data-testid="stDataFrame"], [data-testid="stTable"] {{
    border: 1px solid {T['line']}; border-radius: {T['r2']}; overflow: hidden;
    background: {T['bg2']};
}}
[data-testid="stDataFrame"] [role="columnheader"] {{ background: {T['bg3']} !important; }}
[data-testid="stTable"] table {{ background: {T['bg2']}; }}
[data-testid="stTable"] th {{ background: {T['bg3']} !important; color: {T['t3']} !important;
    font-family: {FONT_MONO} !important; font-size: 0.656rem !important;
    font-weight: 550 !important; letter-spacing: 0.1em !important;
    text-transform: uppercase !important;
    border-bottom: 3px double {T['line_strong']} !important;
    padding: 9px 12px !important; }}
[data-testid="stTable"] td {{ color: {T['t2']}; border-bottom: 1px solid {T['line']} !important;
    padding: 10px 12px !important; }}
[data-testid="stTable"] tr:hover td,
[data-testid="stDataFrame"] [role="row"]:hover [role="gridcell"] {{
    background: {T['accent_soft']} !important; }}

/* ================= 13. 标签页(分段控件) ================= */
.stTabs [data-baseweb="tab-list"] {{
    background: transparent; border-bottom: 1px solid {T['line']};
    border-radius: 0; padding: 0 0 0 0; gap: 2px; flex-wrap: wrap;
}}
.stTabs [data-baseweb="tab"] {{ color: {T['t2']}; border-radius: 0;
    padding: 8px 14px; font-size: 0.85rem; font-weight: 550; background: transparent;
    border-bottom: 2px solid transparent; }}
.stTabs [data-baseweb="tab"]:hover {{ color: {T['t1']}; }}
.stTabs [aria-selected="true"] {{
    background: transparent !important; color: {T['accent']} !important;
    border-bottom: 2px solid {T['accent']} !important;
    box-shadow: none !important; font-weight: 700;
}}
.stTabs [data-baseweb="tab-highlight"], .stTabs [data-baseweb="tab-border"] {{ display: none; }}

/* ================= 14. 侧边栏 ================= */
[data-testid="stSidebar"], section[data-testid="stSidebar"] {{
    background: {T['bg1']};
    border-right: 1px solid {T['line']};
}}
@media (min-width: 900px) {{
    section[data-testid="stSidebar"], [data-testid="stSidebar"] {{
        width: {T['sidebar_w']} !important; min-width: {T['sidebar_w']} !important;
        max-width: {T['sidebar_w']} !important;
    }}
    section[data-testid="stSidebar"] > div, [data-testid="stSidebar"] > div {{
        width: {T['sidebar_w']} !important;
    }}
}}
[data-testid="stSidebar"] .block-container {{ padding-top: 1.1rem; }}
[data-testid="stSidebar"] [role="radiogroup"] {{ gap: 2px; }}
[data-testid="stSidebar"] [role="radiogroup"] label {{
    padding: 0.44rem 0.62rem; border-radius: {T['r1']};
    border: 1px solid transparent;
    transition: background .15s ease, color .15s ease, border-color .15s ease; width: 100%;
}}
[data-testid="stSidebar"] [role="radiogroup"] label:hover {{ background: {T['bg3']}; }}
[data-testid="stSidebar"] [role="radiogroup"] label p {{ font-size: 0.89rem; color: {T['t1']}; }}
/* 选中态: 绯红字 + 淡绯底(公报目录的"本期"标记) */
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) {{
    background: {T['accent_soft']};
    border-color: {T['line_accent']};
}}
[data-testid="stSidebar"] [role="radiogroup"] label:has(input:checked) p {{
    color: {T['accent']} !important; font-weight: 700;
}}
[data-testid="stSidebar"] h3 {{ font-size: 0.74rem !important; text-transform: uppercase;
    letter-spacing: 0.1em; color: {T['t3']} !important; margin: 1rem 0 0.45rem 0 !important; }}
[data-testid="stSidebar"] hr {{ margin: 0.9rem 0; }}
[data-testid="stSidebar"] .status-row .sr-label {{ min-width: 0; }}
[data-testid="stSidebar"] .status-row {{ padding: 0.42rem 0.1rem; font-size: 0.82rem; }}
[data-testid="stSidebar"] .status-row .sr-value {{ font-size: 0.82rem; }}
.side-cap {{ color: {T['t3']}; font-size: 0.72rem; font-weight: 600;
    text-transform: uppercase; letter-spacing: 0.1em; margin: 0.1rem 0 0.35rem 0; }}

/* 侧栏品牌块(报头铭牌) */
.brand {{ padding: 0.15rem 0 0.85rem 0; display: flex; align-items: center; gap: 0.6rem;
    border-bottom: 3px double {T['line_strong']}; margin-bottom: 0.5rem; }}
.brand .b-mark {{ width: 34px; height: 34px; border-radius: 5px; flex: none;
    display: flex; align-items: center; justify-content: center; font-size: 1.05rem;
    background: {T['accent']};
    color: {T['accent_ink']}; box-shadow: {T['accent_shadow']}; }}
.brand .b-title {{ font-size: 1.0rem; font-weight: 700; color: {T['t1']};
    letter-spacing: 0.02em; line-height: 1.3; }}
.brand .b-sub {{ font-size: 0.66rem; font-weight: 600; text-transform: uppercase;
    color: {T['t3']}; letter-spacing: 0.16em; margin-top: 0.16rem;
    font-family: {FONT_MONO}; }}

/* ================= 15. 输入控件 ================= */
.stTextInput input, .stNumberInput input, .stDateInput input, .stTextArea textarea,
[data-baseweb="select"] > div, [data-baseweb="input"] > div {{
    background: {T['bg2']} !important; border-color: {T['line']} !important;
    border-radius: {T['r1']} !important; color: {T['t1']} !important;
}}
.stTextInput input:focus, .stNumberInput input:focus, .stDateInput input:focus,
.stTextArea textarea:focus,
[data-baseweb="select"] > div:focus-within {{
    border-color: {T['accent']} !important;
    box-shadow: 0 0 0 3px {T['accent_soft']} !important;
}}
[data-baseweb="popover"] li, [data-baseweb="menu"] li {{
    background: {T['bg2']}; color: {T['t1']};
}}
.stSlider [data-baseweb="slider"] div[role="slider"] {{ background: {T['accent']} !important; }}
/* 主区横向 radio 呈现为筛选胶囊 */
section.main [data-testid="stRadio"] [role="radiogroup"],
[data-testid="stAppViewContainer"] [data-testid="stRadio"] [role="radiogroup"] {{
    display: flex; flex-wrap: wrap; gap: 6px;
}}
section.main [data-testid="stRadio"] [role="radiogroup"] label {{
    border: 1px solid {T['line']}; border-radius: {T['pill']}; padding: 0.16rem 0.68rem;
    background: transparent;
}}
section.main [data-testid="stRadio"] [role="radiogroup"] label:hover {{
    border-color: {T['accent']}; color: {T['t1']};
}}
section.main [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) {{
    background: {T['accent_soft']}; border-color: {T['accent']};
}}
section.main [data-testid="stRadio"] [role="radiogroup"] label:has(input:checked) p {{
    color: {T['accent']} !important; font-weight: 600;
}}
section.main [data-testid="stRadio"] [role="radiogroup"] label p {{ font-size: 0.8rem; }}

/* ================= 16. 按钮(描边胶囊 + 绯红主按钮) ================= */
.stButton > button, .stDownloadButton > button {{
    background: transparent; color: {T['t1']}; border: 1px solid {T['line_strong']};
    border-radius: {T['pill']}; font-weight: 600; font-size: 0.85rem;
    padding: 0.4rem 1.1rem;
    transition: background .16s {T['ease']}, color .16s {T['ease']},
                border-color .16s {T['ease']}, transform .16s {T['ease']};
}}
.stButton > button:hover, .stDownloadButton > button:hover {{
    background: {T['glass_lite']}; color: {T['accent']};
    border-color: {T['accent']};
}}
/* 主按钮: 绯红实底 + 米白字(头版绯红块) */
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"] {{
    background: {T['accent']} !important;
    color: {T['accent_ink']} !important; border: 1px solid {T['accent']} !important;
    font-weight: 700;
}}
.stButton > button[kind="primary"]:hover, .stDownloadButton > button[kind="primary"]:hover {{
    background: {T['accent2']} !important; color: {T['accent_ink']} !important;
    border-color: {T['accent2']} !important;
    box-shadow: {T['accent_shadow']};
}}
/* 按压反馈 */
.stButton > button:active, .stDownloadButton > button:active,
.stLinkButton a:active {{
    transform: translateY(1px) scale(0.985);
    transition-duration: 60ms;
}}
/* 键盘可达性: 可见焦点环 */
.stButton > button:focus-visible, .stLinkButton a:focus-visible,
.stTextInput input:focus-visible, [data-baseweb="select"] > div:focus-within {{
    outline: 2px solid {T['accent']};
    outline-offset: 2px;
}}
.stLinkButton a {{ background: transparent; border: 1px solid {T['line_strong']};
    color: {T['accent']} !important; border-radius: {T['pill']}; font-weight: 600; }}
.stLinkButton a:hover {{ background: {T['accent_soft']}; border-color: {T['accent']}; }}

/* ================= 17. 原生 st.metric ================= */
[data-testid="stMetric"] {{ background: {T['bg2']}; border: 1px solid {T['line']};
    border-radius: {T['r2']}; padding: 0.8rem 1rem;
    box-shadow: 0 1px 0 {T['line']}; }}
[data-testid="stMetricLabel"] p {{ color: {T['t3']} !important; font-size: 0.76rem;
    text-transform: uppercase; letter-spacing: 0.05em; }}
[data-testid="stMetricValue"] {{ color: {T['t1']} !important; font-size: 1.32rem;
    font-variant-numeric: tabular-nums; }}
[data-testid="stMetricDelta"] {{ font-size: 0.76rem !important; }}

/* ================= 18. 提示 / 展开器 / 代码 ================= */
.stAlert, [data-testid="stAlert"] {{ border-radius: {T['r1']} !important; }}
.stAlert p {{ color: {T['t1']} !important; }}
[data-testid="stExpander"], .streamlit-expanderHeader {{
    background: {T['bg2']} !important; border: 1px solid {T['line']} !important;
    border-radius: {T['r1']} !important;
}}
[data-testid="stExpander"] summary {{ color: {T['t1']} !important; font-weight: 550; }}
[data-testid="stExpander"] summary:hover {{ background: {T['accent_soft']} !important; }}
.stCodeBlock, [data-testid="stCodeBlock"] {{ border-radius: {T['r1']} !important;
    border: 1px solid {T['line']} !important; }}
[data-testid="stVerticalBlockBorderWrapper"] {{
    background: {T['bg2']}; border: 1px solid {T['line']} !important;
    border-radius: {T['r2']} !important;
    box-shadow: 0 1px 0 {T['line']};
}}
[data-testid="stProgress"] > div > div {{ background: {T['bg3']} !important;
    border-radius: {T['pill']} !important; }}
[data-testid="stProgress"] > div > div > div,
[data-testid="stProgress"] > div > div > div > div {{
    background: {T['accent']} !important; border-radius: {T['pill']} !important; }}
.stSpinner > div > div {{ border-top-color: {T['accent']} !important; }}

/* ================= 19. 聊天消息 ================= */
[data-testid="stChatMessage"], .stChatMessage {{
    border-radius: {T['r2']} !important; padding: 0.95rem !important;
    margin-bottom: 0.7rem !important; border: 1px solid {T['line']} !important;
    background: {T['bg2']} !important;
}}
[data-testid="stChatMessage"]:has([data-testid="chatAvatarIcon-user"]) {{
    background: {T['accent_soft']} !important;
    border-color: {T['line_accent']} !important;
}}
[data-testid="stChatMessage"] p, [data-testid="stChatMessage"] li {{
    color: {T['t1']} !important;
}}

/* ================= 20. 其他 ================= */
hr {{ border: none; border-top: 1px solid {T['line']}; margin: 1rem 0; }}
.app-footer {{ text-align: center; color: {T['t3']}; font-size: 0.74rem;
    padding: 1rem; border-top: 3px double {T['line_strong']}; margin-top: 2.2rem;
    letter-spacing: 0.02em; }}
.nav-link-btn {{ display: block; background: transparent; border: 1px solid {T['line_strong']};
    color: {T['accent']} !important; padding: 9px 14px; border-radius: {T['pill']};
    text-decoration: none !important; font-size: 0.85rem; font-weight: 600;
    text-align: center;
    transition: background .16s ease, border-color .16s ease, color .16s ease; }}
.nav-link-btn:hover {{ background: {T['accent_soft']}; border-color: {T['accent']}; }}
/* 细滚动条 */
::-webkit-scrollbar {{ width: 8px; height: 8px; }}
::-webkit-scrollbar-track {{ background: transparent; }}
::-webkit-scrollbar-thumb {{ background: {T['thumb']}; border-radius: {T['pill']};
    border: 2px solid transparent; background-clip: padding-box; }}
::-webkit-scrollbar-thumb:hover {{ background: {T['thumb_hover']}; background-clip: padding-box; }}
/* Streamlit 自带外壳全部隐藏 */
#MainMenu, footer, header [data-testid="stToolbar"],
[data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], .stAppDeployButton,
[data-testid="stAppDeployButton"] {{ display: none !important; visibility: hidden !important; }}
/* 固定顶栏压成 0 高且透明, 只把侧栏折叠按钮单独固定在左上角 */
[data-testid="stHeader"] {{
    background: transparent !important;
    height: 0 !important;
    min-height: 0 !important;
    box-shadow: none !important;
    border: none !important;
    z-index: 1 !important;
    pointer-events: none;
}}
[data-testid="stHeader"] * {{ pointer-events: auto; }}
[data-testid="stSidebarCollapsedControl"],
[data-testid="stSidebarCollapseButton"],
[data-testid="stExpandSidebarButton"] {{
    position: fixed !important;
    top: 0.55rem; left: 0.55rem;
    z-index: 999999 !important;
    background: {T['bg2']} !important;
    border: 1px solid {T['line_strong']} !important;
    border-radius: {T['r1']} !important;
}}

/* ================= 21. 响应式 (断点 1440 / 1024 / 768 / 480) ================= */
@media (max-width: 1440px) {{
    .block-container {{ max-width: 1360px; }}
}}
@media (max-width: 1024px) {{
    .block-container {{ padding-left: 1rem; padding-right: 1rem; padding-top: 1.1rem; }}
    .page-head {{ flex-direction: column; }}
    .page-head .ph-meta {{ text-align: left; }}
    .hero {{ padding: 1.2rem 1.25rem; flex-direction: column; align-items: flex-start;
             gap: 1rem; }}
    .hero .hero-stats {{ gap: 1.5rem; flex-wrap: wrap; }}
    .metric-row[data-compact="1"] {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
    .metric-card, .info-card, .feature-card {{ padding: 0.85rem 0.95rem !important; }}
    [data-testid="stDataFrame"] {{ overflow-x: auto; }}
}}
@media (max-width: 768px) {{
    h1 {{ font-size: 1.45rem !important; }}
    .page-head .ph-title {{ font-size: 1.35rem; }}
    .hero .hero-stats {{ gap: 1.1rem; }}
    .hero .hero-stat .v {{ font-size: 1.25rem; }}
    .metric-card {{ min-height: 92px; padding: 0.85rem 0.95rem; }}
    .metric-card .mc-value {{ font-size: 1.42rem; }}
    .bento {{ grid-template-columns: 1fr; }}
    .bento-main {{ grid-column: auto; }}
    .bento-main .bt-list {{ columns: 1; }}
}}
@media (max-width: 480px) {{
    .block-container {{ padding-left: 0.7rem; padding-right: 0.7rem; padding-top: 1rem; }}
    h1 {{ font-size: 1.28rem !important; }}
    .page-head .ph-title {{ font-size: 1.18rem; }}
    .brand .b-title {{ font-size: 0.9rem; }}
    .sec {{ font-size: 0.95rem; }}
    .metric-card .mc-value {{ font-size: 1.3rem; }}
    .metric-row {{ grid-template-columns: 1fr; }}
    .hero .hero-stats {{ gap: 0.85rem; }}
    [data-testid="stSidebar"] .block-container {{ padding-top: 0.6rem; }}
    .app-footer {{ font-size: 0.68rem; }}
}}

/* ---- 21.1 内容宽度驱动的回退(容器查询) ----
   侧栏可展开/收起, 主内容宽度在同一视口下能跳变 —— 按真实内容宽度回退,
   不按视口。 */
[data-testid="stMainBlockContainer"] {{ container-type: inline-size; container-name: main; }}

@container main (max-width: 880px) {{
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .info-card):not(:has(> [data-testid="stColumn"] .metric-row)) > [data-testid="stColumn"],
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .feature-card) > [data-testid="stColumn"] {{
        flex: 0 1 calc(50% - 0.5rem);
        min-width: calc(50% - 0.5rem);
        max-width: calc(50% - 0.5rem);
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .metric-row) > [data-testid="stColumn"] {{
        flex: 1 1 100%;
        min-width: 100%;
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .metric-row) .metric-card {{
        min-height: 0; padding: 0.6rem 1.05rem;
        flex-direction: row; align-items: center; justify-content: space-between; gap: 1rem;
    }}
    [data-testid="stHorizontalBlock"]:has(> [data-testid="stColumn"] .metric-row) .metric-card .mc-value {{
        margin-top: 0; font-size: 1.28rem;
    }}
}}

/* ================= 22. 图标字形(离线 Material Symbols) ================= */
.msr, .material-symbols-rounded, [data-testid="stIconMaterial"] {{
    font-family: "Material Symbols Rounded" !important;
    font-weight: 400; font-style: normal;
    font-size: 1.05em; line-height: 1;
    letter-spacing: normal; text-transform: none; white-space: nowrap;
    direction: ltr; display: inline-block;
    -webkit-font-feature-settings: "liga"; -webkit-font-smoothing: antialiased;
    font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
    vertical-align: -0.135em;
}}
.sec .msr, .mc-top .msr, .ic-title .msr, .b-mark .msr,
.es-icon .msr, .ph-title .msr, .bt-icon .msr, .fc-icon .msr {{
    vertical-align: -0.16em; }}

/* ================= 23. 交互反馈(指针 / 过渡) ================= */
.stButton > button, .stDownloadButton > button, .stLinkButton a,
.stTabs [data-baseweb="tab"],
[role="radiogroup"] label, [data-testid="stCheckbox"] label,
[data-testid="stExpander"] summary,
[data-baseweb="select"] > div, [data-baseweb="input"] > div,
[data-testid="stFileUploader"] button,
[data-testid="stFileUploaderDropzone"],
.stSlider [role="slider"], [data-testid="stPagination"] button,
[data-testid="stChatInput"] button, .nav-link-btn {{
    cursor: pointer;
}}
.stTextInput input, .stNumberInput input, .stTextArea textarea,
[data-baseweb="base-input"] input {{ cursor: text; }}
.stTabs [data-baseweb="tab"] {{
    transition: background .2s ease, color .2s ease;
}}
[data-testid="stExpander"] summary {{
    transition: background .2s ease, color .2s ease;
}}

/* ================= 24. 无障碍 ================= */
:focus-visible {{ outline: 2px solid {T['accent']}; outline-offset: 2px;
    border-radius: 4px; }}
[data-testid="stSidebar"] [role="radiogroup"] label:focus-within,
.stButton > button:focus-visible, [data-testid="stExpander"] summary:focus-visible {{
    outline: 2px solid {T['accent']}; outline-offset: 2px;
}}

/* ================= 25. 年鉴排版层(等宽微标签 + 衬线数字) =================
   密集数据一律等宽 tabular(纵向可比), 微标签 10px 等宽大写 letter-spacing;
   KPI 大数字走衬线展示体(公报头版数字), 本层放在视觉规则之后统一覆盖。 */
.mc-top, .metric-label, .micro-label, .fc-eyebrow, .hero .eyebrow,
[data-testid="stMetricLabel"] p, [data-testid="stWidgetLabel"] p {{
    font-family: {FONT_MONO} !important;
    font-size: 0.625rem !important; font-weight: 550 !important;
    letter-spacing: 0.14em !important;
    text-transform: uppercase !important; color: {T['t3']} !important;
}}
[data-testid="stMetricValue"],
[data-testid="stMetricValue"] > div, .kpi-value, .stat-value, .table-value {{
    font-family: {FONT_MONO} !important;
    font-variant-numeric: tabular-nums !important;
    font-feature-settings: "tnum" 1;
    letter-spacing: 0;
}}
/* KPI 卡左上角的图标砖(绯红淡底) */
.metric-card .mc-top .msr {{
    display: inline-flex; align-items: center; justify-content: center;
    width: 24px; height: 24px; margin-right: 7px; border-radius: 4px;
    background: {T['accent_soft']} !important; color: {T['accent']} !important;
    font-size: 15px !important; line-height: 1;
}}
/* -- 原生控件皮肤: react-aria 版下拉/单选按新 DOM 上令牌 -- */
[data-testid="stSelectbox"] div:has(> input[role="combobox"]) {{
    background: {T['bg2']} !important; border: 1px solid {T['line']} !important;
    border-radius: {T['r1']} !important;
}}
[data-testid="stSelectbox"] div:has(> input[role="combobox"]):focus-within {{
    border-color: {T['accent']} !important;
    box-shadow: 0 0 0 3px {T['accent_soft']} !important;
}}
[data-testid="stSelectbox"] input {{
    color: {T['t1']} !important; background: transparent !important;
}}
[data-testid="stSelectbox"] button {{ background: transparent !important; }}
[data-testid="stSelectbox"] button svg {{ fill: {T['t2']} !important; color: {T['t2']} !important; }}
[role="listbox"] {{
    background: {T['glass_mid']} !important; border: 1px solid {T['line']} !important;
    border-radius: {T['r1']} !important; box-shadow: {T['shadow']} !important;
}}
[role="listbox"] [role="option"] {{ color: {T['t1']} !important; }}
[role="listbox"] [role="option"]:hover,
[role="listbox"] [role="option"][data-selected="true"] {{
    background: {T['accent_soft']} !important;
}}
/* -- 单选圆点: 未选中只留描边, 选中用绯红 + 米色内点 -- */
[data-testid="stRadioOption"] > div > div > div:first-child {{
    background: transparent !important;
    border: 1.5px solid {T['line_strong']} !important;
}}
[data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child {{
    background: {T['accent']} !important; border-color: {T['accent']} !important;
}}
[data-testid="stRadioOption"][data-selected="true"] > div > div > div:first-child > div {{
    background: {T['accent_ink']} !important;
}}

/* ================= 26. 入场动效(0.4s 上移淡入, 尊重减少动态) ================= */
@keyframes tmRise {{
    from {{ opacity: 0; transform: translateY(8px); }}
    to   {{ opacity: 1; transform: translateY(0); }}
}}
.metric-card, .feature-card, .info-card, [data-testid="stMetric"],
[data-testid="stDataFrame"], .stTabs, [data-testid="stExpander"], .hero {{
    animation: tmRise .4s cubic-bezier(.22,.61,.36,1) both;
}}
.metric-card:nth-child(2), .feature-card:nth-child(2), [data-testid="stMetric"]:nth-child(2) {{
    animation-delay: .05s; }}
.metric-card:nth-child(3), .feature-card:nth-child(3), [data-testid="stMetric"]:nth-child(3) {{
    animation-delay: .1s; }}
.metric-card:nth-child(4), .feature-card:nth-child(4), [data-testid="stMetric"]:nth-child(4) {{
    animation-delay: .15s; }}
@media (prefers-reduced-motion: reduce) {{
    *, *::before, *::after {{ animation-duration: 0.001ms !important;
        animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }}
    .metric-card:hover, .feature-card:hover {{ transform: none; }}
}}

/* ================= 27. 顶栏 / 快捷操作卡 / 弹层(版式层) =================
   驾驶舱顶栏用 Streamlit 原生列 + popover 实现(要能触发注销与切页)。 */
.st-key-topbar {{
    border-bottom: 3px double {T['line_strong']} !important;
    padding-bottom: .5rem !important; margin-bottom: 1.1rem !important;
}}
.tb-title {{
    font-family: {T['font_title']} !important;
    font-size: 1.46rem !important; font-weight: 700 !important;
    color: {T['t1']} !important; line-height: 1.2; letter-spacing: 0;
}}
.tb-crumb {{
    font-family: {FONT_MONO} !important; font-size: .64rem !important;
    letter-spacing: .18em; text-transform: uppercase;
    color: {T['t3']} !important; margin-top: .28rem;
}}
.tb-left {{ display: flex !important; align-items: center !important; gap: .85rem !important; }}
.tb-brand {{ display: flex !important; align-items: center !important; gap: .58rem !important; }}
.tb-logo {{
    width: 38px; height: 38px; flex: 0 0 38px; border-radius: 6px;
    display: flex; align-items: center; justify-content: center;
    background: {T['accent']} !important; color: {T['accent_ink']} !important;
    box-shadow: {T['accent_shadow']};
    font-size: 1.15rem !important; line-height: 1;
}}
.tb-logo .msr {{ font-size: 1.22rem !important; color: {T['accent_ink']} !important; }}
.tb-brand-name {{
    font-size: .92rem !important; font-weight: 700 !important;
    color: {T['t1']} !important; line-height: 1.12;
}}
.tb-brand-sub {{
    font-family: {FONT_MONO} !important; font-size: .56rem !important;
    letter-spacing: .16em; text-transform: uppercase;
    color: {T['t3']} !important; margin-top: .18rem;
}}
.tb-sep {{ width: 1px; height: 30px; background: {T['line']}; flex: 0 0 auto; }}
.st-key-topbar [data-testid="stPopover"] > button,
.st-key-topbar [data-testid="stBaseButton-secondary"] {{
    background: transparent !important;
    border: 1px solid {T['line_strong']} !important; border-radius: {T['pill']} !important;
    color: {T['t2']} !important; font-size: .78rem !important; font-weight: 600 !important;
    min-height: 34px !important; padding: 0 .7rem !important;
}}
.st-key-topbar [data-testid="stPopover"] > button:hover,
.st-key-topbar [data-testid="stBaseButton-secondary"]:hover {{
    border-color: {T['accent']} !important; color: {T['accent']} !important;
    background: {T['accent_soft']} !important;
}}
.tb-pop-cap {{
    font-family: {FONT_MONO} !important; font-size: .62rem !important;
    letter-spacing: .18em; text-transform: uppercase; color: {T['t3']};
    margin-bottom: .5rem;
}}
.tb-pop-row {{
    display: flex; gap: .55rem; align-items: flex-start;
    padding: .5rem .1rem; border-bottom: 1px solid {T['line']}; font-size: .8rem;
}}
.tb-pop-row:last-child {{ border-bottom: none; }}
.tb-pop-row b {{ color: {T['t1']}; font-size: .8rem; }}
.tb-pop-val {{ display: block; color: {T['t2']}; font-size: .74rem; margin-top: .15rem; }}
.tb-pop-time {{
    display: block; font-family: {FONT_MONO}; font-size: .62rem;
    letter-spacing: .1em; color: {T['t3']}; margin-top: .2rem;
}}
.dot {{ width: 7px; height: 7px; border-radius: 1.5px; margin-top: .35rem; flex: 0 0 auto; }}
.dot.info {{ background: {T['blue']}; }}
.dot.warn {{ background: {T['gold']}; }}
.dot.ok {{ background: {T['ok']}; }}
.dot.danger {{ background: {T['red']}; }}
.tb-me {{ display: flex; align-items: center; gap: .6rem; }}
.tb-me-av {{
    width: 34px; height: 34px; border-radius: 6px; display: flex;
    align-items: center; justify-content: center; font-weight: 800; font-size: .95rem;
    background: {T['accent']} !important; color: {T['accent_ink']} !important;
}}
.tb-me-role {{
    display: block; font-family: {FONT_MONO}; font-size: .62rem;
    letter-spacing: .14em; color: {T['t3']}; margin-top: .15rem;
}}
/* 快捷操作卡(右列图标按钮组) */
.st-key-qa_card, .st-key-qa_card_admin_card {{
    background: {T['bg2']} !important;
    border: 1px solid {T['line']} !important; border-radius: {T['r3']} !important;
    padding: .9rem 1rem 1rem !important; box-shadow: 0 1px 0 {T['line']} !important;
}}
.qa-head {{
    display: flex !important; align-items: baseline !important; gap: .5rem !important;
    margin-bottom: .7rem;
}}
.qa-title {{
    font-size: .82rem !important; font-weight: 700 !important; color: {T['t1']} !important;
}}
.qa-sub {{
    font-family: {FONT_MONO} !important; font-size: .6rem !important;
    letter-spacing: .1em; color: {T['t3']} !important;
}}
.qa-cap {{
    font-family: {FONT_MONO} !important; font-size: .62rem !important;
    letter-spacing: .2em; text-transform: uppercase; color: {T['t3']};
    margin-bottom: .7rem;
}}
.st-key-qa_card button, .st-key-qa_card_admin_card button {{
    min-height: 62px !important; border-radius: {T['r2']} !important;
    background: {T['accent_soft']} !important;
    border: 1px solid {T['line']} !important;
    transition: border-color .2s {T['ease']}, background .2s {T['ease']};
}}
.st-key-qa_card button p, .st-key-qa_card_admin_card button p {{
    display: flex !important; flex-direction: column !important;
    align-items: center !important; gap: .3rem !important;
    font-size: .72rem !important; font-weight: 600 !important; color: {T['t1']} !important;
}}
.st-key-qa_card button span[data-testid="stIconMaterial"],
.st-key-qa_card_admin_card button span[data-testid="stIconMaterial"] {{
    font-size: 1.28rem !important; color: {T['accent']} !important;
    width: 1.7rem !important; min-width: 1.7rem !important;
    display: inline-flex !important; align-items: center; justify-content: center;
}}
.st-key-qa_card button:hover, .st-key-qa_card_admin_card button:hover {{
    border-color: {T['accent']} !important;
    background: {T['accent_tint']} !important;
}}
/* 参照稿的「分组导航」: 侧栏 radio 列表里插入组标题(纯视觉, 不改交互) */
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label,
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label,
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label {{
    position: relative;
}}
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label::before,
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label::before,
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label::before {{
    content: ""; position: absolute; top: -19px; left: 3px;
    font: 600 9.5px/1 ui-monospace, monospace; letter-spacing: .2em;
    text-transform: uppercase; color: {T['t3']};
}}
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(1)::before {{ content: "概览"; }}
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2)::before {{ content: "数据"; }}
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(5)::before {{ content: "分析"; }}
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(1)::before {{ content: "概览"; }}
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2)::before {{ content: "数据"; }}
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(3)::before {{ content: "运维"; }}
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(1)::before {{ content: "概览"; }}
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2)::before {{ content: "数据"; }}
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(5)::before {{ content: "分析"; }}
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(9)::before {{ content: "管理"; }}
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2),
.stApp:has(.nav-groups-user) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(5),
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2),
.stApp:has(.nav-groups-admin) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(3),
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(2),
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(5),
.stApp:has(.nav-groups-both) section[data-testid="stSidebar"] div[role="radiogroup"] > label:nth-child(9) {{
    margin-top: 2.15rem !important;
}}

/* ================= 28. 侧栏收起救援按钮 ================= */
#sb-rescue {{
    position: fixed !important;
    top: 0.7rem; left: 0.7rem;
    z-index: 1000000;
    display: none;
    align-items: center; justify-content: center;
    width: 2.35rem; height: 2.35rem;
    padding: 0;
    border-radius: 6px;
    border: 1px solid {T['line_strong']};
    background: {T['bg2']};
    color: {T['t2']};
    cursor: pointer;
    box-shadow: {T['shadow_sm']};
    transition: color .15s, border-color .15s, transform .15s;
}}
#sb-rescue:hover {{ color: {T['accent']}; border-color: {T['line_accent']}; transform: translateY(-1px); }}
#sb-rescue:active {{ transform: translateY(0); }}
[data-testid="stSidebarCollapseButton"] {{ pointer-events: none !important; }}

/* ================= 29. 悬浮板面(主区纸版 + 侧栏浮板) =================
   整个驾驶舱 = 一块压在公报纸面上的版面: 顶栏留在板外的天头,
   板面由伪元素画出(描边/投影不把天头圈进去)。 */
[data-testid="stMainBlockContainer"], [data-testid="stMain"] > .block-container {{
    position: relative !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    margin: 14px 18px 20px !important;
}}
[data-testid="stMainBlockContainer"]::before,
[data-testid="stMain"] > .block-container::before {{
    content: ''; position: absolute; z-index: -1; pointer-events: none;
    left: 0; right: 0; top: 130px; bottom: 0;
    background: {T['bg1']};
    border: 1px solid {T['line']};
    border-radius: 12px;
    box-shadow: {T['shadow_sm']};
}}
[data-testid="stSidebar"], section[data-testid="stSidebar"] {{
    margin: 16px 0 20px 16px !important;
    border-radius: 10px !important;
    border: 1px solid {T['line']} !important;
    box-shadow: {T['shadow_sm']} !important;
}}

/* ============================================================
   30. 无壳模式(参照稿自带顶栏与侧栏, 它就是整个界面)
   Streamlit 自带的侧栏 / 顶栏 / 工具条一律隐藏, 页面撑满整屏;
   需要老导航时点左下浮动按钮打开抽屉(body.nav-open)。
   ============================================================ */
[data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
[data-testid="stStatusWidget"], [data-testid="stSidebarCollapsedControl"] {{
    display: none !important;
}}
[data-testid="stSidebar"] {{
    display: none !important;
}}
#sb-rescue {{ display: none !important; }}
[data-testid="stAppViewContainer"] > .main,
.stApp [data-testid="stMainBlockContainer"],
.stApp [data-testid="stMain"] > .block-container {{
    padding: 0 !important;
    margin: 0 !important;
    max-width: 100% !important;
}}
[data-testid="stMainBlockContainer"]::before {{ display: none !important; }}
.block-container {{ padding: 0 !important; }}
[data-testid="stMainBlockContainer"] [data-testid="stVerticalBlock"] {{ gap: 0 !important; }}
.st-key-navfab {{ display: none !important; }}
.st-key-refpage, .st-key-refpage [data-testid="stElementContainer"] {{
    height: 100vh !important;
    margin: 0 !important;
}}
.st-key-refpage [data-testid="stIFrame"] {{
    display: block !important;
    width: 100vw !important;
    height: 100vh !important;
}}
/* 只有「整页参照稿」的页面才铺满且锁滚动; 其余旧版式页面保留内边距与正常滚动 */
.stApp:has(.st-key-refpage) .stAppViewContainer,
.stApp:has(.st-key-refpage) [data-testid="stMain"] {{
    height: 100vh !important;
    overflow: hidden !important;
}}
.stApp:has(.st-key-refpage) [data-testid="stMainBlockContainer"] {{
    padding: 0 !important;
    margin: 0 !important;
}}
.stApp:not(:has(.st-key-refpage)) [data-testid="stMainBlockContainer"] {{
    padding: 22px 26px 40px !important;
}}

/* 抽屉模式: 点浮动按钮后, 老侧栏以浮层形式盖上来 */
body.nav-open [data-testid="stSidebar"] {{
    display: block !important;
    position: fixed !important;
    left: 0; top: 0; bottom: 0;
    width: min(320px, 86vw) !important;
    min-width: 0 !important; max-width: none !important;
    z-index: 99990 !important;
    box-shadow: {T['shadow']} !important;
    border-right: 1px solid {T['line']} !important;
    border-radius: 0 !important;
    margin: 0 !important;
    background: {T['bg1']} !important;
    transform: none !important; visibility: visible !important;
    overflow-y: auto !important;
}}
body.nav-open::after {{
    content: ""; position: fixed; inset: 0; z-index: 99980;
    background: rgba(14, 42, 34, .45);
}}
#nav-fab {{
    position: fixed; left: 14px; bottom: 14px; z-index: 99999;
    width: 40px; height: 40px; border-radius: 6px; border: 1px solid {T['line_strong']};
    display: inline-flex; align-items: center; justify-content: center; cursor: pointer;
    background: {T['bg2']};
    box-shadow: {T['shadow_sm']};
    color: {T['t2']}; font-size: 18px; line-height: 1;
}}
#nav-fab:hover {{ color: {T['accent']}; border-color: {T['line_accent']}; }}
</style>
"""


def current_theme() -> str:
    """当前主题(light=晨报 / dark=晚报), 由侧边栏开关写入 session_state

    默认 light(晨报·暖米纸): 公报设计以纸面为旗舰,
    深色的晚报是同构反色备选。
    """
    try:
        v = st.session_state.get("ui_theme", "light")
    except Exception:
        v = "light"
    return v if v in THEMES else "light"


def _sync_downstream():
    """把配色同步给 viz / blocks 等模块。

    这两个模块在模块级缓存了颜色常量(Altair/iframe 需要具体色值),
    而 Streamlit 会复用已导入模块, 因此每次切换主题后必须显式回写,
    否则图表与动效版块会停留在上一套配色。
    """
    mapping = {
        "viz": {"BG": "bg_chart", "BG3": "bg3", "ACCENT": "accent", "ACCENT2": "accent2",
                "GRID": "line", "TXT1": "t1", "TXT2": "t2", "TXT3": "t3"},
        "blocks": {"BG0": "bg0", "BG1": "bg1", "BG2": "bg2", "BG3": "bg3",
                   "ACCENT": "accent", "ACCENT2": "accent2", "T1": "t1",
                   "T2": "t2", "T3": "t3", "LINE": "line"},
    }
    for mod_name, attrs in mapping.items():
        mod = sys.modules.get(mod_name)
        if mod is None:
            continue
        for attr, key in attrs.items():
            if key in T:
                setattr(mod, attr, T[key])
        if mod_name == "viz":
            # 图表色板 = 登录页的设计语言（暖橙为主 · 冷蓝次之 · 石板灰压场），
            # 用 p1..p10 显式定义，避免与 UI 令牌(accent2 等)撞色后互相靠近。
            pal = [T.get("p%d" % n) for n in range(1, 11)]
            if hasattr(mod, "PALETTE"):
                mod.PALETTE = pal
            oc = getattr(mod, "OUTCOME_COLORS", None)
            if isinstance(oc, dict):
                for k in ("主胜", "home", "H", "win", "W"):
                    oc[k] = T.get("accent")
                for k in ("平局", "draw", "D"):
                    oc[k] = T.get("gold")
                for k in ("客胜", "away", "A", "loss", "L"):
                    oc[k] = T.get("red")


def apply_theme():
    """应用统一主题样式(前端与后台共用); 按当前主题重载 CSS 并同步下游模块"""
    name = current_theme()
    T.clear()
    T.update(THEMES[name])
    _sync_downstream()
    st.markdown(_build_css(T), unsafe_allow_html=True)


def _on_theme_change():
    """主题下拉的 on_change 回调: 在脚本重跑**之前**写入 ui_theme。

    为什么不用 `st.rerun()`: 主题下拉在侧栏, 而 `st.rerun()` 会当场中断本次
    脚本运行 —— 侧栏之后的控件(管理功能 radio / 页面选择等)这一轮根本没被
    渲染, 它们的状态随即被 Streamlit 清理, 表现为「一切主题就跳回数据概览」。
    改成回调后: 回调先改状态, Streamlit 自然重跑, 整份脚本完整跑一遍,
    页面停留在原地。
    """
    v = str(st.session_state.get("ui_theme_choice", ""))
    st.session_state["ui_theme"] = "light" if v.startswith("晨报") else "dark"


def theme_selector(label: str = "🎨 主题 / Theme"):
    """侧边栏主题切换(晨报暖米纸 / 晚报林墨版)"""
    cur = current_theme()
    opts = ["晨报 Gazette（暖米纸）", "晚报 Evening（林墨版）"]
    idx = 0 if cur == "light" else 1
    try:
        st.selectbox(label, opts, index=idx, key="ui_theme_choice",
                     on_change=_on_theme_change)
    except Exception:                                     # pragma: no cover
        return


# ============ 组件 ============
_MATERIAL_RE = re.compile(r":material/([A-Za-z0-9_]+):")


def _icon(html):
    """把 Material 短代码 :material/icon_name: 归一化为 <span class="msr">icon_name</span>。

    为什么需要这一层? Streamlit 的短代码替换只作用于 markdown 的 **text 节点**;
    而 unsafe_allow_html=True 的 HTML 块(如 <div> 开头)内部, 短代码不会走 remark
    文本替换, 会原样显示为 ":material/icon_name:" 字面文字。而本设计系统的所有图标
    都经由下方的 HTML 助手函数注入, 因此必须在此统一转成 <span class="msr"> 形式
    (字形样式见 _build_css() 第 22 节)。

    例外: st.set_page_config(page_icon=":material/x:") 是 Streamlit 官方直接支持,
    不经过这里, 保持短代码即可。
    """
    return _MATERIAL_RE.sub(
        lambda m: f'<span class="msr" aria-hidden="true">{m.group(1)}</span>',
        str(html))


def _flat(html):
    """把多行 HTML 压平为单行, 并把短代码归一化为 HTML 图标。

    Streamlit 会对 markdown 文本做去缩进处理; 若 HTML 字符串中含缩进空格,
    其后的深缩进行会被解析为『缩进代码块』, 于是标签以源码形式显示在页面上。
    统一压平(合并空白)可彻底规避该问题。
    """
    return _icon(" ".join(str(html).split()))


def _tint(color, alpha=0.42):
    """把 #rrggbb 令牌转为同色相低透明度的 rgba()。

    用于把强调色"微染"到 1px 描边里 —— 保持单一色相语言, 同时避免
    >1px 的彩色边框(craft-floor Refuse)与高饱和色块。非 #rrggbb 输入原样返回。
    """
    c = str(color or "").strip()
    if len(c) == 7 and c.startswith("#"):
        try:
            r, g, b = int(c[1:3], 16), int(c[3:5], 16), int(c[5:7], 16)
            return f"rgba({r},{g},{b},{alpha})"
        except ValueError:
            pass
    return c or T["accent"]


def page_header(title, subtitle=None, icon="", meta=None, breadcrumb=None):
    """页面头部: 面包屑 + 标题 + 副标题 + 右侧元信息"""
    crumb = f'<div class="ph-crumb">{breadcrumb}</div>' if breadcrumb else ""
    sub = f'<div class="ph-sub">{subtitle}</div>' if subtitle else ""
    met = f'<div class="ph-meta">{meta}</div>' if meta else ""
    st.markdown(_flat(f"""
    <div class="page-head">
      <div>
        {crumb}
        <div class="ph-title">{f'{icon} ' if icon else ''}{title}</div>
        {sub}
      </div>
      {met}
    </div>"""), unsafe_allow_html=True)


def section(title, subtitle=None, icon=""):
    """区块标题(左侧强调条)"""
    sub = f'<span class="sec-sub">{subtitle}</span>' if subtitle else ""
    st.markdown(_icon(f'<div class="sec">{f"{icon} " if icon else ""}{title}{sub}</div>'),
                unsafe_allow_html=True)


def section_cap(text, icon=":material/sensors:"):
    """次级小标签(胶囊样式), 用于卡片内部或子分组"""
    st.markdown(_icon(f'<div class="side-cap">{icon} {text}</div>'), unsafe_allow_html=True)


def hero(title, desc="", stats=None, icon=""):
    """首屏欢迎横幅: stats = [(value, label), ...]"""
    stats_html = ""
    if stats:
        cells = "".join(
            f'<div class="hero-stat"><div class="v">{v}</div>'
            f'<div class="l">{l}</div></div>' for v, l in stats)
        stats_html = f'<div class="hero-stats">{cells}</div>'
    st.markdown(_flat(f"""
    <div class="hero">
      <div class="hero-body">
        <h2>{f'{icon} ' if icon else ''}{title}</h2>
        <p>{desc}</p>
      </div>
      {stats_html}
    </div>"""), unsafe_allow_html=True)


def metric_row(items):
    """一行指标卡: items = [(value, label, hint, icon, color), ...] 或 dict 列表

    dict 支持的键: value / label / hint / icon / color / delta

    渲染成单个 .metric-row 网格(不再用 st.columns 的定宽列):
      · 卡片由 grid 自动等高, 不再出现 4 张卡高度参差;
      · 列数由 --mc-n 显式给出, 窄视口按 data-compact 降为 2 列,
        单卡宽度始终 ≥200px, "12,564" / "XGBoost" 这类短值不会被折断。
    """
    if not items:
        return
    cards = []
    for it in items:
        if isinstance(it, dict):
            value, label = it.get("value"), it.get("label")
            hint, icon = it.get("hint"), it.get("icon", "")
            color = it.get("color", T["accent"])
            delta = it.get("delta")
        else:
            value, label = it[0], it[1]
            hint = it[2] if len(it) > 2 else None
            icon = it[3] if len(it) > 3 else ""
            color = it[4] if len(it) > 4 else T["accent"]
            delta = None
        hint_html = f'<div class="mc-hint">{hint}</div>' if hint else ""
        delta_html = (f'<div class="mc-hint" style="color:{color};font-weight:600;">'
                      f'{delta}</div>') if delta else ""
        cards.append(_flat(f"""
        <div class="metric-card" style="--mc-line:{_tint(color, 0.42)};">
          <div class="mc-top">{f'{icon} ' if icon else ''}{label}</div>
          <div class="mc-value">{value}</div>
          {delta_html}{hint_html}
        </div>"""))
    st.markdown(_flat(f"""
    <div class="metric-row" style="--mc-n:{len(items)};"
         data-compact="{'1' if len(items) >= 4 else '0'}">
      {"".join(cards)}
    </div>"""), unsafe_allow_html=True)


def empty_state(icon, title, desc, command=None):
    """空状态(待填充占位)"""
    cmd = (f'<div class="es-desc" style="margin-top:0.7rem;">'
           f'<span class="code-chip">{command}</span></div>') if command else ""
    st.markdown(_flat(f"""
    <div class="empty-state">
      <div class="es-icon">{icon}</div>
      <div class="es-title">{title}</div>
      <div class="es-desc">{desc}</div>
      {cmd}
    </div>"""), unsafe_allow_html=True)


def badge(text, kind="ok"):
    """徽标: ok / wait / info / err / mute (兼容 good/bad/warn 别名)"""
    kind = {"good": "ok", "bad": "err", "warn": "wait", "success": "ok",
            "error": "err"}.get(kind, kind)
    st.markdown(_icon(f'<span class="badge badge-{kind}">{text}</span>'), unsafe_allow_html=True)


def chip_row(items, active=None):
    """静态筛选标签行(展示当前筛选条件)"""
    if not items:
        return
    if active is None:
        active = []
    if isinstance(active, str):
        active = [active]
    html = "".join(
        f'<span class="chip{" on" if it in active else ""}">{it}</span>' for it in items)
    st.markdown(f'<div class="chip-row">{html}</div>', unsafe_allow_html=True)


def status_row(label, value=None, state="ok"):
    """系统状态行: state = ok / off / warn / err / live"""
    dot = f'<span class="status-dot {"" if state == "ok" else state}"></span>'
    val = f'<span class="sr-value">{value}</span>' if value is not None else ""
    st.markdown(f'<div class="status-row">{dot}<span class="sr-label">{label}</span>{val}</div>',
                unsafe_allow_html=True)


def status_list(rows):
    """状态清单: rows = [(label, value, state), ...]"""
    if not rows:
        return
    html = []
    for r in rows:
        label = r[0]
        value = r[1] if len(r) > 1 else None
        state = r[2] if len(r) > 2 else "ok"
        dot = f'<span class="status-dot {"" if state == "ok" else state}"></span>'
        val = f'<span class="sr-value">{value}</span>' if value is not None else ""
        html.append(f'<div class="status-row">{dot}<span class="sr-label">{label}</span>{val}</div>')
    st.markdown(f'<div class="status-list">{"".join(html)}</div>', unsafe_allow_html=True)


def code_chip(text):
    st.markdown(f'<span class="code-chip">{text}</span>', unsafe_allow_html=True)


def step_list(steps):
    """有序步骤清单: steps = [(序号, 标题, 说明), ...] (允许内联 HTML)"""
    if not steps:
        return
    html = []
    for no, title, desc in steps:
        html.append(
            f'<div class="status-row"><span class="step-no">{no}</span>'
            f'<span class="sr-label">{title}</span>'
            f'<span class="sr-value">{desc}</span></div>')
    st.markdown(f'<div class="status-list step-list">{"".join(html)}</div>',
                unsafe_allow_html=True)


def info_card(title, lines, icon="", color=None):
    """信息卡: title 标题, lines 为字符串列表(可用 ('文本', True) 表示弱化)"""
    color = color or T["accent"]
    html = []
    for ln in (lines or []):
        if isinstance(ln, (tuple, list)):
            text, dim = ln[0], bool(ln[1] if len(ln) > 1 else False)
        else:
            text, dim = ln, False
        html.append(f'<div class="ic-line{" dim" if dim else ""}">{text}</div>')
    st.markdown(_flat(f"""
    <div class="info-card" style="--ic-line:{_tint(color, 0.38)};">
      <div class="ic-title">{f'{icon} ' if icon else ''}{title}</div>
      {"".join(html)}
    </div>"""), unsafe_allow_html=True)


def divider():
    st.markdown(f'<hr style="border:none;border-top:1px solid {T["line"]};margin:1rem 0;">',
                unsafe_allow_html=True)


def brand_header(title="足球分析系统", subtitle="Football Analytics", mark=":material/sports_soccer:"):
    """侧栏顶部品牌块"""
    st.markdown(_flat(f"""
    <div class="brand">
      <div class="b-mark">{mark}</div>
      <div>
        <div class="b-title">{title}</div>
        <div class="b-sub">{subtitle}</div>
      </div>
    </div>"""), unsafe_allow_html=True)


def app_footer(text="足球数据分析与AI预测系统 · 毕业设计项目"):
    st.markdown(f'<div class="app-footer">{text}</div>', unsafe_allow_html=True)


# ---- 兼容旧接口 ----
def card_metric(label, value, delta=None, icon="", color=None):
    color = color or T["accent"]
    st.markdown(_flat(f"""
    <div class="metric-card" style="--mc-line:{_tint(color, 0.42)};">
      <div class="mc-top">{f'{icon} ' if icon else ''}{label}</div>
      <div class="mc-value">{value}</div>
      {f'<div class="mc-hint">{delta}</div>' if delta else ''}
    </div>"""), unsafe_allow_html=True)


def feature_card(icon, title, items, color=None):
    """功能卡(兼容接口)。视觉: 1px 同色描边 + 染色的图标, 不再用 >1px 彩色顶边。"""
    color = color or T["accent"]
    items_html = "".join(f"<li>{i}</li>" for i in items)
    st.markdown(_flat(f"""
    <div class="feature-card" style="--fc-line:{_tint(color, 0.38)};">
      <div class="fc-icon">{icon}</div>
      <div class="fc-title">{title}</div>
      <ul class="fc-list">{items_html}</ul>
    </div>"""), unsafe_allow_html=True)


def capability_band(primary, secondary):
    """能力带: 主打项横跨整行 + 支撑项并排(替代三等宽功能卡)。

    primary   = (icon, title, [要点, ...])
    secondary = [(icon, title, [要点, ...]), ...]
    层级由跨度与条目密度区分, 而不是把三张卡摊成等宽三等分。
    """
    if not primary:
        return
    p_icon, p_title, p_items = primary
    main_html = "".join(f"<li>{i}</li>" for i in (p_items or []))
    side_html = ""
    for s in (secondary or []):
        s_icon, s_title = s[0], s[1]
        s_items = s[2] if len(s) > 2 else []
        items_html = "".join(f"<li>{i}</li>" for i in s_items)
        side_html += (f'<div class="bento-item"><div class="bt-icon">{s_icon}</div>'
                      f'<div class="bt-title">{s_title}</div>'
                      f'<ul class="bt-list">{items_html}</ul></div>')
    st.markdown(_flat(f"""
    <div class="bento">
      <div class="bento-main">
        <div class="bt-icon">{p_icon}</div>
        <div class="bt-title">{p_title}</div>
        <ul class="bt-list">{main_html}</ul>
      </div>
      {side_html}
    </div>"""), unsafe_allow_html=True)


def status_box(status_type, message):
    icon_map = {"info": ":material/info:", "success": ":material/check_circle:", "warn": ":material/warning:", "error": ":material/cancel:"}
    st.markdown(_icon(f'<div class="{status_type}-box">{icon_map.get(status_type, "")} {message}</div>'),
                unsafe_allow_html=True)


def nav_link(url, label, icon=""):
    st.markdown(_icon(f'<a href="{url}" target="_blank" class="nav-link-btn">{icon} {label}</a>'),
                unsafe_allow_html=True)


def sidebar_footer(app_name="足球分析系统"):
    from i18n import t   # 延迟导入, 避免模块级循环依赖
    divider()
    st.markdown(f'<div style="text-align:center;color:{T["t3"]};font-size:0.72rem;">'
                f'{t(app_name)} v1.0.0<br>{t("毕业设计")}</div>', unsafe_allow_html=True)


def section_title(title, subtitle=None):
    """兼容旧接口"""
    section(title, subtitle)
