# -*- coding: utf-8 -*-
"""Streamlit 前端 - 足球数据分析与AI预测系统

统一设计系统: frontend/theme.py  (深色足球主题 / 侧栏导航 + 页面头 + KPI + 分区面板)
启动: streamlit run frontend/app.py

说明: 本文件不再内联任何 <style>, 所有样式与组件均由 theme.py 提供,
      与管理员后台 admin.py 共用同一套视觉语言。
"""
import json
import re
import sys
from pathlib import Path
from datetime import datetime

import pandas as pd
import requests
import sqlite3
import streamlit as st

# ---------- 共享模块 ----------
sys.path.insert(0, str(Path(__file__).parent))

try:
    import blocks as BLK                             # 灵动版块(英雄/Bento/走马灯/数字滚动)
except Exception:                                     # pragma: no cover
    class BLK:                                    # type: ignore
        @staticmethod
        def hero_band(*a, **k):
            pass

        @staticmethod
        def stat_band(*a, **k):
            pass

        @staticmethod
        def bento_grid(*a, **k):
            pass

        @staticmethod
        def ticker(*a, **k):
            pass


try:
    from i18n import (t as _t, lang as _lang, lang_selector as _lang_selector,
                      pos_zh as _pos_zh, pos_group as _pos_group,
                      pos_group_label as _pos_group_label)
except Exception:                                     # pragma: no cover
    def _t(zh, en=None):
        return zh

    def _lang():
        return "zh"

    def _lang_selector():
        pass

    def _pos_zh(p):
        return "—" if not p else str(p)

    def _pos_group(p):
        return "OT"

    def _pos_group_label(code):
        return str(code)

t = _t
lang = _lang
pos_zh = _pos_zh
pos_group = _pos_group
pos_group_label = _pos_group_label

try:
    from theme import (
        apply_theme, page_header, section, section_cap, metric_row, hero, empty_state,
        badge, chip_row, status_list, status_row, code_chip, divider,
        brand_header, app_footer, info_card, step_list, card_metric, feature_card,
        capability_band, theme_selector,
        nav_link, T as TH,
    )
    from theme import API_BASE as _API_BASE, ADMIN_URL as _ADMIN_URL
except Exception:                                     # pragma: no cover
    TH = {}
    _API_BASE, _ADMIN_URL = "http://127.0.0.1:8000/api", "http://127.0.0.1:8502"

    def theme_selector(*a, **k):
        return None

    def _noop(*a, **k):
        return None

    apply_theme = page_header = section = section_cap = metric_row = hero = divider = _noop
    chip_row = status_list = status_row = code_chip = step_list = _noop
    brand_header = app_footer = info_card = nav_link = _noop
    card_metric = feature_card = capability_band = _noop

    def empty_state(icon, title, desc, command=None):
        st.info(f"{icon} {title} — {desc}")

    def badge(text, kind="ok"):
        st.markdown(f"`{text}`")


API_BASE = _API_BASE
ADMIN_URL = _ADMIN_URL

# ---------- 图表渲染层(统一由 viz.py 提供, 与后台共用) ----------
try:
    import viz as VIZ
except Exception:                                     # pragma: no cover
    class _VizStub:
        """viz 不可用时的空实现: 所有图表构建器退化为 None。"""

        def __getattr__(self, _name):
            def _noop_viz(*a, **k):
                return None
            return _noop_viz
    VIZ = _VizStub()

# ---------- 页面配置 ----------


# ---------- 登录闸门 ----------
# 未登录直接在这里拦住(渲染登录界面 + st.stop); 令牌可由控制台「真实系统」带过来。
try:
    from auth_gate import login_gate, sidebar_user as _sidebar_user, logout as _auth_logout
except Exception:                                     # pragma: no cover
    def login_gate(**kw):
        return {}

    _sidebar_user = None
    _auth_logout = None

try:
    import dash as DASH                                 # 参照稿仪表盘组件(顶栏/KPI/大视区/通知列)
except Exception:                                       # pragma: no cover
    DASH = None

try:
    import hero_dash as HERO                            # 参照稿主视区 1:1 复刻层(舞台+KPI+焦点+右列)
except Exception:                                       # pragma: no cover
    HERO = None

try:
    import ref_page as REF                              # 整页参照稿渲染层(严格按 templates/dashboard_ref.html)
except Exception:                                       # pragma: no cover
    REF = None

try:
    from theme import current_theme as _theme_key       # 当前主题键(light/dark/night)
except Exception:                                       # pragma: no cover
    def _theme_key():
        return "light"


DB_PATH = Path(__file__).parent.parent / "data" / "database" / "football.db"


# ============ 取数工具 ============
def q_df(sql, params=()):
    """直连 SQLite 查询(只读), 不依赖后端服务"""
    con = sqlite3.connect(str(DB_PATH))
    try:
        return pd.read_sql_query(sql, con, params=params)
    finally:
        con.close()


def q_one(sql, params=(), default=0):
    con = sqlite3.connect(str(DB_PATH))
    try:
        row = con.execute(sql, params).fetchone()
        return row[0] if row and row[0] is not None else default
    except Exception:
        return default
    finally:
        con.close()


def num(sql, default=0):
    v = q_one(sql, default=default)
    try:
        return int(v)
    except Exception:
        return default


# ============ 展示工具 ============
def isnull(v):
    try:
        return v is None or pd.isna(v)
    except Exception:
        return v is None


def txt(v, default="—"):
    return default if isnull(v) else str(v)


def txt_i(v, default="—"):
    """展示用文本, 但会按 i18n 词条翻译(随语言切换)。

    用于「库里存的是中文、展示时要跟随语言」的取值, 如联赛名 / 国家名;
    队名 / 球员名等专有名词没有词条, t() 原样回退, 不会被译坏。
    """
    return default if isnull(v) else t(str(v))


def numf(v, nd=2, default="—"):
    return default if isnull(v) else f"{float(v):.{nd}f}"


def intf(v, default="—"):
    return default if isnull(v) else f"{int(v)}"


def fmt_height(v, default="—"):
    """身高格式化: 去掉 '.0' 并带单位, 例如 180.0 -> 180 cm"""
    if isnull(v):
        return default
    try:
        return f"{int(round(float(v)))} cm"
    except Exception:
        return txt(v, default)


_NATION_WORDS = [
    "Equatorial Guinea", "Trinidad and Tobago", "Bosnia-Herzegovina",
    "Northern Ireland", "North Macedonia", "Saudi Arabia", "South Korea",
    "New Zealand", "South Africa", "Costa Rica", "Czech Republic", "Ivory Coast",
    "DR Congo", "Burkina Faso", "Sierra Leone", "Guinea-Bissau", "Cape Verde",
    "Netherlands", "Switzerland", "Argentina", "Australia", "England", "Scotland",
    "Wales", "Ireland", "France", "Germany", "Italy", "Spain", "Portugal", "Brazil",
    "Belgium", "Croatia", "Denmark", "Sweden", "Norway", "Poland", "Turkey",
    "Ukraine", "Serbia", "Slovenia", "Slovakia", "Romania", "Hungary", "Austria",
    "Greece", "Russia", "Morocco", "Algeria", "Tunisia", "Egypt", "Senegal",
    "Nigeria", "Ghana", "Cameroon", "Mali", "Guinea", "Angola", "Zambia", "Kenya",
    "Uruguay", "Colombia", "Chile", "Peru", "Ecuador", "Paraguay", "Bolivia",
    "Venezuela", "Mexico", "United States", "Canada", "Japan", "China", "Israel",
    "Iran", "Iraq", "Jamaica", "Honduras", "Panama", "Georgia", "Albania",
    "Montenegro", "Kosovo", "Belarus", "Finland", "Iceland", "Bulgaria", "Cyprus",
    "Armenia", "Azerbaijan", "Kazakhstan", "Uzbekistan", "Curaçao", "Suriname",
    "Haiti", "Cuba", "Zimbabwe", "Uganda", "Togo", "Benin", "Gabon", "Congo",
    "Gambia", "Liberia", "Sudan", "Libya", "Syria", "Qatar", "Kuwait", "Oman",
]


def fmt_nation(v, default="—"):
    """国籍格式化: Transfermarkt 的多国籍是拼接串(如 'Spain Equatorial Guinea')。
    用国家名词表贪婪切分, 输出 'Spain / Equatorial Guinea'; 切不开则原样返回。"""
    if isnull(v):
        return default
    s = str(v).strip()
    if not s:
        return default
    words = sorted(_NATION_WORDS, key=len, reverse=True)
    out, rest = [], s
    while rest:
        for n in words:
            if rest.startswith(n):
                out.append(n)
                rest = rest[len(n):].strip()
                break
        else:
            out.append(rest)
            break
    uniq = list(dict.fromkeys(out))
    return " / ".join(uniq) if len(uniq) > 1 else s


def i18n_s(s):
    """标签 / 列名 i18n: 字符串按词条翻译(幂等), 非字符串原样返回。

    词条缺失时 t() 回退中文原文, 因此不会把队名 / 球员名等专有名词翻译坏。
    """
    return t(s) if isinstance(s, str) else s


def i18n_df(df):
    """返回「列名 + 单元格值」均已按 i18n 词条翻译的 DataFrame 副本。

    图表库以「列名」作轴标题 / 图例, 以「单元格值」作分类标签(如联赛名),
    表格同理 —— 二者都要先翻译成当前语言再交给渲染层; 原 DataFrame 保持不变。
    仅 object 列参与值翻译, 数值 / 日期 / 布尔列不受影响。
    """
    if isinstance(df, pd.DataFrame):
        return i18n_vals(df.rename(columns=i18n_s))
    return df


def money(v, default="—"):
    """身价格式化: 中文态用「亿€ / 万€」, 英文态用「€M / €K」(单位随语言切换)。"""
    if isnull(v):
        return default
    v = float(v)
    if lang() == "en":
        if v >= 1e6:
            return f"€{v / 1e6:,.1f}M"
        if v >= 1e3:
            return f"€{v / 1e3:,.0f}K"
        return f"€{v:,.0f}"
    if v >= 1e8:
        return f"{v / 1e8:.2f} 亿€"
    if v >= 1e4:
        return f"{v / 1e4:.0f} 万€"
    return f"{v:,.0f} €"


def i18n_vals(df):
    """返回「单元格值」已按 i18n 词条翻译的 DataFrame 副本(仅 object 列)。

    图表的分类标签(如联赛名)与表格正文都来自单元格值, 而 st.dataframe 更由
    canvas 渲染、单元格文本不进 DOM, 残留中文无法靠 DOM 扫描发现。故在此统一
    兜底: 数值 / 日期 / 布尔列不触碰, 词条缺失回退原文, 专有名词不受影响。
    """
    if not isinstance(df, pd.DataFrame):
        return df
    return df.apply(
        lambda col: col.map(i18n_s) if col.dtype == object else col, axis=0)


def show_df(df, height=None, hide_index=True):
    """表格渲染(兼容 Streamlit 新旧 API); 列名与单元格值均经 i18n 词条翻译

    可读性增强(taste §4.6 数据模式 / redesign 表格审计):
      · 数值列自动右对齐 + 千分位(把"看起来是数字的文本列"转成真正的数值列,
        否则 Streamlit 会把它们当字符串左对齐, 数字位对不齐)
      · 列宽与行高交给 Streamlit 默认策略, 不再强行撑满
    """
    df = i18n_df(df).copy()
    cfg = {}
    for c in list(df.columns):
        if df[c].dtype == object:
            s = df[c].astype(str).str.replace(",", "", regex=False).str.strip()
            num = pd.to_numeric(s, errors="coerce")
            total, valid = df[c].notna().sum(), num.notna().sum()
            # 只有"整列都是数字"才转数值列: 否则 '—' 这类占位会被 NumberColumn
            # 渲染成 "None"(混排列保持文本, 数字靠右对齐的收益不值得这个代价)
            if total and valid == total:
                df[c] = num
        if pd.api.types.is_numeric_dtype(df[c]):
            try:
                cfg[c] = st.column_config.NumberColumn(c, format="localized")
            except Exception:                          # pragma: no cover
                pass
    kw = {"hide_index": hide_index}
    if height:
        kw["height"] = height
    if cfg:
        kw["column_config"] = cfg
    # 浅色主题下 st.dataframe 仍是深色网格(canvas 渲染, 用的是 Streamlit 自身的主题,
    # 我们无法用 CSS 覆盖) —— 在浅色页面上会非常突兀。此时改用跟随本设计系统 CSS 的
    # st.table; 行数过多则截断, 避免页面被拉得过长。
    _light = False
    try:
        _light = st.session_state.get("ui_theme", "dark") == "light"
    except Exception:                                  # pragma: no cover
        pass
    if _light and len(df) <= 60:
        st.table(df if len(df) <= 25 else df.head(25))
        if len(df) > 25:
            st.caption(t("仅显示前 25 行（浅色主题下表格为静态渲染，可切换到深色主题查看完整数据）"))
        return
    try:
        st.dataframe(df, width="stretch", **kw)
    except TypeError:                                  # pragma: no cover
        kw.pop("column_config", None)
        st.dataframe(df, use_container_width=True, **kw)


def wide_button(label, key=None, type_=None):
    kw = {}
    if key:
        kw["key"] = key
    if type_:
        kw["type"] = type_
    try:
        return st.button(label, width="stretch", **kw)
    except TypeError:                                  # pragma: no cover
        return st.button(label, use_container_width=True, **kw)


def bar_chart(df, x, y, color=None, height=280, rotate=0, key=None):
    """统一风格柱状图(委托 viz 渲染层, 自动回退)"""
    return VIZ.show(
        VIZ.bar(df, x, y, color=color or TH.get("accent", "#2f86e0"),
                height=height, rotate=rotate, sort=None),
        key=key, fallback=df)


# 状态中文映射(位置映射已收敛到 i18n 的 pos_zh / pos_group, 前后台共用)
HEAD_ZH = {"H": "主胜", "D": "平局", "A": "客胜"}


def head_zh(h):
    return t(HEAD_ZH.get(str(h), str(h)), str(h))


def backend_ok():
    try:
        r = requests.get(f"{API_BASE.replace('/api', '')}/", timeout=3)
        return r.status_code == 200
    except Exception:
        return False


# ============ 侧边栏 ============

# 登录后由 main() 写入(统一入口会直接把已登录用户赋给它)
AUTH_USER = {}


# ============ 页面渲染函数(统一入口 frontend/main.py 调用) ============


def render_home():
    """首页概览"""
    n_league = num("SELECT COUNT(DISTINCT league_id) FROM matches", 10)
    n_match = num("SELECT COUNT(*) FROM matches")
    n_ft = num("SELECT COUNT(*) FROM matches WHERE status='FT'")
    n_xg = num("SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL")
    n_team = num("SELECT COUNT(*) FROM teams")
    n_player = num("SELECT COUNT(*) FROM players")
    n_mv = num("SELECT COUNT(*) FROM players WHERE market_value IS NOT NULL")
    n_tm = num("SELECT COUNT(*) FROM tm_players")
    n_pred = num("SELECT COUNT(*) FROM predictions")
    n_transfer = num("SELECT COUNT(*) FROM transfers")
    last_day = txt(q_one("SELECT MAX(date(date)) FROM matches", default=None))

    # ---------------- 参照稿骨架(用户 m05889: 高度模仿复刻图片 UI) ----------------
    # 版式对齐参照稿: 顶栏(面包屑 + 消息/个人中心/退出) → 4 张 KPI 卡 → 快捷操作 +
    # 进度卡 → 大视区(底部浮层状态胶囊) + 右列消息通知。全部数字取自本地库真实统计。
    if DASH:
        _n_xgft = int(num("SELECT COUNT(*) FROM matches WHERE status='FT' AND home_xg IS NOT NULL"))
        _n_noxg = int(num("SELECT COUNT(*) FROM matches WHERE status='FT' AND home_xg IS NULL"))
        _n_nomv = int(num("SELECT COUNT(*) FROM players WHERE market_value IS NULL"))
        _n_new_month = int(num("SELECT COUNT(*) FROM matches WHERE strftime('%Y-%m', date) = strftime('%Y-%m','now')"))
        _n_ft30 = int(num("SELECT COUNT(*) FROM matches WHERE status='FT' AND date(date) >= date('now','-30 day')"))
        _n_ns = int(num("SELECT COUNT(*) FROM matches WHERE status='NS'"))
        _n_tables = int(num("SELECT COUNT(*) FROM sqlite_master WHERE type='table'"))
        _pct_xg = (_n_xgft / n_ft * 100) if n_ft else 0
        _pct_mv = (n_mv / n_player * 100) if n_player else 0
        _pct_pred = (n_pred / n_match * 100) if n_match else 0
        _db_mb = DB_PATH.stat().st_size / 1024 / 1024 if DB_PATH.exists() else 0
        _notices = [
            {"title": t("完赛缺 xG"), "value": f"{_n_noxg:,} {t('场')} · {t('待 Understat 回填')}",
             "time": t("数据质量"), "tone": "warn"},
            {"title": t("球员缺身价"), "value": f"{_n_nomv:,} {t('名')} · {t('Transfermarkt 未关联')}",
             "time": t("数据质量"), "tone": "warn"},
            {"title": t("数据库"), "value": f"{_db_mb:.1f} MB · {_n_tables} {t('张表')} · SQLite",
             "time": t("本地库"), "tone": "ok"},
            {"title": t("转会记录"), "value": f"{n_transfer:,} {t('条')} · Transfermarkt 层",
             "time": t("数据资产"), "tone": "info"},
            {"title": t("最新比赛日"), "value": f"{last_day} · {n_match:,} {t('场比赛中')} {n_ft:,} {t('场已完赛')}",
             "time": t("matches.date"), "tone": "info"},
        ]
        # 无壳模式(用户 m07431「我只要一个新做的」):
        # 参照稿自带顶栏与侧栏, 它就是整个界面 —— 不再渲染系统自己的顶栏, 渲染完直接结束本页。
        # (老导航改由左下浮动按钮打开的抽屉提供, 见 main.py 的 nav_fab)

        # ---- 中央三维场景两侧的真实统计(供左/右卡列) ----
        _mrows = q_df("""SELECT substr(date,1,7) AS m, COUNT(*) AS n FROM matches
                         WHERE date IS NOT NULL GROUP BY m ORDER BY m DESC LIMIT 12""")
        _months = list(reversed(_mrows["m"].tolist())) if not _mrows.empty else []
        _counts = [int(v) for v in (reversed(_mrows["n"].tolist()) if not _mrows.empty else [])]
        _resdf = q_df("""SELECT CASE WHEN home_goals > away_goals THEN 'H'
                                     WHEN home_goals = away_goals THEN 'D' ELSE 'A' END AS r,
                                COUNT(*) AS n FROM matches WHERE status = 'FT' GROUP BY r""")
        _rmap = {str(r["r"]): int(r["n"]) for _, r in _resdf.iterrows()} if not _resdf.empty else {}
        _lrows = q_df("""SELECT l.name AS lg, COUNT(*) AS n FROM matches m
                         JOIN leagues l ON l.league_id = m.league_id
                         GROUP BY l.name ORDER BY n DESC LIMIT 8""")
        _rank = ([{"label": i18n_s(r["lg"]), "value": int(r["n"])} for _, r in _lrows.iterrows()]
                 if not _lrows.empty else [])

        _fx = q_one("""SELECT p.match_id FROM predictions p JOIN matches m ON m.match_id = p.match_id
                       WHERE m.status='NS' ORDER BY m.date DESC LIMIT 1""", default=None)
        _frow = None
        if _fx:
            _fdf = q_df("""SELECT m.match_id, date(m.date) AS d, l.name AS lg,
                                  ht.name AS home, at.name AS away,
                                  p.model_version, p.pred_home_win, p.pred_draw, p.pred_away_win,
                                  p.pred_result, p.features_json
                           FROM predictions p JOIN matches m ON m.match_id = p.match_id
                           JOIN teams ht ON ht.team_id = m.home_team_id
                           JOIN teams at ON at.team_id = m.away_team_id
                           LEFT JOIN leagues l ON l.league_id = m.league_id
                           WHERE m.match_id = ? LIMIT 1""", (int(_fx),))
            if not _fdf.empty:
                _frow = _fdf.iloc[0].to_dict()
        if _frow:
            _feat = {}
            try:
                _feat = json.loads(_frow.get("features_json") or "{}")
            except Exception:
                _feat = {}
            _ph = float(_frow["pred_home_win"] or 0) * 100
            _pd = float(_frow["pred_draw"] or 0) * 100
            _pa = float(_frow["pred_away_win"] or 0) * 100
            # 参照图版式: 整版驾驶舱 = KPI 四卡 → 三维球场大图 → 焦点赛事(大蓝环)+进度列表 → 右列卡片组
            _maxp = max(_ph, _pd, _pa)
            _pick = {"H": t("主胜"), "D": t("平局"), "A": t("客胜")}.get(_frow.get("pred_result"), t("首选"))
            _top4 = _rank[:4]
            _mx = max([r["value"] for r in _top4] or [1])
            _pct_pos = (num("SELECT COUNT(*) FROM players WHERE position IS NOT NULL") / n_player * 100) if n_player else 0
            _pct_ns = (_n_ns / n_match * 100) if n_match else 0

            # ---------------- 把真数据灌进参照稿(模板一字未改, 走 DOM 补丁层) ----------------
            _stg = q_df("""SELECT s.rank AS rk, tm.name AS nm, s.points AS pt
                           FROM standings s JOIN teams tm ON tm.team_id = s.team_id
                           WHERE s.season = (SELECT season FROM standings GROUP BY season
                                             ORDER BY COUNT(*) DESC LIMIT 1)
                             AND s.league_id = (SELECT league_id FROM standings GROUP BY league_id
                                                ORDER BY COUNT(*) DESC LIMIT 1)
                           ORDER BY s.rank LIMIT 5""")
            _srows = ([{"rank": int(r["rk"]), "name": i18n_s(r["nm"]),
                        "pct": int(round(100 * float(r["pt"]) / max(1, float(_stg["pt"].max())))),
                        "val": str(int(r["pt"]))} for _, r in _stg.iterrows()]
                      if not _stg.empty else [])
            _mvdf = q_df("""SELECT name, market_value FROM players WHERE market_value IS NOT NULL
                            ORDER BY market_value DESC LIMIT 5""")
            _mvrows = ([{"rank": i + 1, "name": str(r["name"]),
                         "pct": int(round(100 * float(r["market_value"]) / max(1.0, float(_mvdf["market_value"].max())))),
                         "val": f"{float(r['market_value'])/1e6:.0f}M€"} for i, (_, r) in enumerate(_mvdf.iterrows())]
                       if not _mvdf.empty else [])
            _recdf = q_df("""SELECT date(m.date) AS d, ht.name AS h, at.name AS a,
                                    m.home_goals AS hg, m.away_goals AS ag, m.status AS st
                             FROM matches m JOIN teams ht ON ht.team_id = m.home_team_id
                             JOIN teams at ON at.team_id = m.away_team_id
                             WHERE m.status IN ('FT','NS') AND m.home_goals IS NOT NULL
                             ORDER BY m.date DESC LIMIT 4""")
            _recrows = ([{"home": i18n_s(r["h"]), "away": i18n_s(r["a"]),
                          "score": f"{int(r['hg'])} : {int(r['ag'])}" if r["st"] == "FT" else "vs",
                          "status": t("已结束") if r["st"] == "FT" else t("未开始"),
                          "cls": "end" if r["st"] == "FT" else "soon"} for _, r in _recdf.iterrows()]
                        if not _recdf.empty else [])
            _trows = q_df("""SELECT tm.name AS nm, COUNT(*) AS n FROM matches m
                             JOIN teams tm ON tm.team_id = m.home_team_id
                             GROUP BY tm.name ORDER BY n DESC LIMIT 4""")
            _hotmax = float(_trows["n"].max()) if not _trows.empty else 1.0
            _hotrows = ([{"name": i18n_s(r["nm"]), "pct": int(round(100 * float(r["n"]) / _hotmax))}
                         for _, r in _trows.iterrows()] if not _trows.empty else [])

            _refdata = {
                "kpis": [
                    {"tag": t("比赛场次"), "num": f"{n_match:,}",
                     "trend": f"{t('本月新增')} {_n_new_month:,}"},
                    {"tag": t("已完赛"), "num": f"{n_ft:,}",
                     "trend": f"{t('官方 xG 覆盖')} {_pct_xg:.0f}%"},
                    {"tag": t("联赛 / 球队"), "num": f"{n_league} / {n_team}",
                     "trend": f"{t('转会记录')} {n_transfer:,}"},
                    {"tag": t("球员"), "num": f"{n_player:,}",
                     "trend": f"{t('含身价')} {n_mv:,}", "plus": True},
                ],
                "focus": {
                    "title": f"{t('焦点赛事')} · {i18n_s(_frow['home'])} vs {i18n_s(_frow['away'])}",
                    "odds": [
                        {"k": t("主胜"), "v": f"{_ph:.1f}%", "s": i18n_s(_frow["home"])},
                        {"k": t("平局"), "v": f"{_pd:.1f}%",
                         "s": f"{i18n_s(_frow['lg'])} · {_frow['model_version']}"},
                        {"k": t("客胜"), "v": f"{_pa:.1f}%", "s": i18n_s(_frow["away"])},
                    ],
                    "ring": round(_maxp, 1),
                    "mini": [
                        {"k": t("比赛日"), "v": str(_frow["d"])[:10]},
                        {"k": t("首选"), "v": _pick},
                        {"k": t("置信度"), "v": f"{_maxp:.1f}%"},
                        {"k": t("模型"), "v": str(_frow["model_version"])},
                        {"k": t("样本外"), "v": f"{_pct_pred:.1f}%"},
                    ],
                },
                "bars": [
                    {"label": t("官方 xG 覆盖"), "pct": round(_pct_xg, 1)},
                    {"label": t("球员身价覆盖"), "pct": round(_pct_mv, 1)},
                    {"label": t("赛事预测覆盖"), "pct": round(_pct_pred, 1)},
                    {"label": t("位置数据覆盖"), "pct": round(_pct_pos, 1)},
                ],
                "right": {
                    "slim": {"label": f"{t('未来赛程')} · {_n_ns:,} {t('场')}", "pct": round(_pct_ns, 1)},
                    "stats": [
                        {"icon": "📄", "pct": f"{_pct_xg:.1f}%"},
                        {"icon": "💰", "pct": f"{_pct_mv:.1f}%"},
                        {"icon": "🤖", "pct": f"{_pct_pred:.1f}%"},
                        {"icon": "🕐", "pct": f"{_pct_pos:.1f}%"},
                    ],
                    "todo": {"title": t("数据完整度"), "link": t("质量与资产") + " ›",
                             "items": [{"tone": "y" if n["tone"] == "warn" else "g",
                                        "text": f"{n['title']} · {n['value']}"} for n in _notices]},
                },
                "foot": [f"{t('数据更新时间')}: {last_day} · SQLite",
                         f"{n_match:,} {t('场比赛')} · {n_ft:,} {t('场已完赛')} · {n_league} {t('联赛')}"],
                "panels": {
                    "standings": {"title": t("联赛积分榜"), "rows": _srows},
                    "scorers": {"title": t("球员身价 Top 5"), "rows": _mvrows},
                    "recent": {"title": t("近期比赛"), "rows": _recrows},
                    "ai": {"title": t("AI 智能预测"),
                           "big": f"{t('推荐')} · {_pick}", "bigPct": f"{_maxp:.1f}%",
                           "tags": [f"{t('主胜')} {_ph:.1f}%", f"{t('平局')} {_pd:.1f}%",
                                    f"{t('客胜')} {_pa:.1f}%"],
                           "tip": f"{i18n_s(_frow['home'])} vs {i18n_s(_frow['away'])} · "
                                  f"{i18n_s(_frow['lg'])} {str(_frow['d'])[:10]} · "
                                  f"{t('模型')} {_frow['model_version']} · {t('首选')} {_pick} {_maxp:.1f}%"},
                    "hot": {"title": t("球队比赛量 Top 4"), "rows": _hotrows},
                },
            }
            _refuser = {"name": (AUTH_USER or {}).get("display_name") or (AUTH_USER or {}).get("username") or "",
                        "role": (AUTH_USER or {}).get("role_label") or (AUTH_USER or {}).get("role") or "",
                        "lang": st.session_state.get("lang", "中文"),
                        "theme": _theme_key(), "notices": _notices, "guest": False}
            REF.render(theme=_theme_key(), height=1000, slug="home", data=_refdata,
                       admin=str((AUTH_USER or {}).get("role") or "").lower() == "admin",
                       user=_refuser)
            return                              # 参照稿即整页, 不再往下渲染旧版式
        section(t("关键指标"), t("取自本地数据库实时统计"), icon=":material/trending_up:")
    BLK.stat_band([
        (f"{n_match:,}", t("比赛场次"), f"{t('已完赛')} {n_ft:,}"),
        (f"{n_xg:,}", t("官方 xG"), t("Understat · 五大联赛 99%")),
        (f"{n_team}", t("球队"), t("已完成重复合并")),
        (f"{n_player:,}", t("球员"), f"{t('含身价')} {n_mv:,}"),
        (f"{n_pred:,}", t("历史预测"), t("含样本外回测")),
        (f"{n_transfer:,}", t("转会记录"), t("Transfermarkt 层")),
    ])

    section(t("核心功能"), t("数据 · 预测 · 对话"), icon=":material/rocket_launch:")
    # 非对称 Bento: 主功能横跨两列, 其余并列 —— 制造节奏, 避免"三张等宽卡"的模板脸
    BLK.bento_grid([
        {"mark": "✦", "kicker": t("核心能力"),
         "title": t("AI 比赛预测"), "span": 2,
         "items": [t("集成模型 v2+v7：样本外准确率 50.14%，优于全押主胜基线 5.8pp"),
                   t("官方 xG 特征 + 阵容身价/伤病，90+ 维特征工程"),
                   t("时间序列切分防数据泄露，概率校准曲线可验证"),
                   t("混淆矩阵、特征重要性、逐场概率全部可追溯")]},
        {"mark": "▦", "kicker": t("数据"),
         "title": t("数据可视化"),
         "items": [t("联赛积分榜与排名变化"), t("球队 / 球员多维雷达"),
                   t("身价走势与技术统计"), t("10 项赛事全览")]},
        {"mark": "◆", "kicker": t("交互"),
         "title": t("智能 Agent"),
         "items": [t("自然语言查询球队与球员"), t("比赛深度分析报告"),
                   t("6 个工具增强检索"), t("支持国内大模型接入")]},
        {"mark": "⬡", "kicker": t("数据底座"),
         "title": t("四层数据源 · 可持续更新"),
         "span": 2,
         "items": [f"{t('Football-Data')}：{n_match:,} {t('场比赛')} · {n_league} {t('项赛事')} · {t('含半场比分与射门统计')}",
                   f"{t('Understat')}：{n_xg:,} {t('场官方 xG')}（{t('五大联赛覆盖 99%')}）",
                   f"{t('Transfermarkt')}：{n_tm:,} {t('球员档案')} · {num('SELECT COUNT(*) FROM tm_player_market_value'):,} {t('条身价记录')} · {num('SELECT COUNT(*) FROM tm_player_injuries'):,} {t('条伤病记录')}",
                   f"{t('API-Football')}：{t('阵容 / 事件 / 伤停字段已建表，待回填')}"]},
    ])

    section(t("覆盖赛事"), t("football-data.org 免费档 + Understat"), icon=":material/emoji_events:")
    BLK.ticker([t("英超"), t("西甲"), t("德甲"), t("意甲"), t("法甲"), t("欧冠"),
                t("英冠"), t("荷甲"), t("葡超"), t("巴甲"),
                "Football-Data.org", "Understat", "Transfermarkt", "Reep", "API-Football"])

    section(t("数据分布"), t("各赛事比赛场次 · 数据资产构成"), icon=":material/bar_chart:")
    lg_stat = q_df("""SELECT l.name AS lg, COUNT(m.match_id) AS n
                      FROM leagues l LEFT JOIN matches m ON m.league_id = l.league_id
                      GROUP BY l.league_id ORDER BY 2 DESC""")
    hc1, hc2 = st.columns([3, 2])
    with hc1:
        if lg_stat.empty:
            empty_state(":material/bar_chart:", t("暂无比赛数据"), t("请先导入比赛数据"),
                        command="python scripts/import_data.py")
        else:
            # 列名与联赛取值都随语言切换(Altair 以列名作图例 / 轴标题)
            lg_stat = lg_stat.rename(columns={"lg": t("赛事"), "n": t("比赛场次")})
            lg_stat[t("赛事")] = lg_stat[t("赛事")].map(i18n_s)
            VIZ.show(VIZ.rank_bar(lg_stat, t("赛事"), t("比赛场次"), gradient=True,
                                  fmt=",.0f", title=t("各赛事比赛场次")),
                     key="home_lg_matches", fallback=lg_stat)
    with hc2:
        # 环形图不适合"量级差异极大"的数据(901k 身价 vs 4.7k 球员), 改为横向排行条:
        # 数值可比较、排序一目了然(taste §4.6 数据模式 / redesign 图表选择)
        asset = pd.DataFrame({
            t("数据类别"): [t("身价记录"), t("伤病记录"), t("比赛记录"),
                            t("球员档案"), t("球队档案")],
            t("记录数"): [int(num("SELECT COUNT(*) FROM tm_player_market_value")),
                          int(num("SELECT COUNT(*) FROM tm_player_injuries")),
                          int(n_match), int(n_player), int(n_team)],
        })
        VIZ.show(VIZ.rank_bar(asset, t("数据类别"), t("记录数"), gradient=True,
                              fmt=",.0f", bar_size=22, title=t("数据资产构成")),
                 key="home_asset_bar", fallback=asset)

    section(t("技术架构"), t("从数据采集到智能问答"), icon=":material/settings:")
    a1, a2, a3, a4 = st.columns(4)
    with a1:
        info_card(t("后端服务"), ["FastAPI + Uvicorn", "RESTful API + WebSocket",
                                  (t("定时任务 APScheduler"), True)], icon=":material/electrical_services:")
    with a2:
        info_card(t("数据层"), ["SQLite + SQLAlchemy", "Pandas + NumPy",
                                (t("27 张数据表"), True)], icon=":material/database:")
    with a3:
        info_card(t("机器学习"), ["XGBoost + scikit-learn", t("SHAP 可解释性"),
                                  (t("三分类胜平负"), True)], icon=":material/psychology:")
    with a4:
        info_card(t("AI Agent"), [t("LangChain + 工具增强"), t("DeepSeek / 豆包"),
                                  (t("自然语言查询"), True)], icon=":material/smart_toy:")

# ============================================================
# 联赛数据
# ============================================================

def render_leagues():
    """联赛数据"""
    page_header(t("联赛数据"), t("积分榜 · 球队实力 · 赛季概览"),
                icon=":material/bar_chart:", breadcrumb=t("数据浏览"))

    lgs = q_df("SELECT league_id, name, country, season FROM leagues ORDER BY league_id")
    if lgs.empty:
        empty_state(":material/bar_chart:", t("暂无联赛数据"), t("请先运行数据导入脚本初始化数据库"),
                    command="python scripts/init_db.py")
    else:
        # 联赛名 / 国家名随语言切换(词条缺失时回退原文, 不会译坏专有名词)
        # 选项「值」必须与语言无关(这里用行号), 显示名交给 format_func —— 否则切语言
        # 后标签串改变, 已选联赛会因不在新选项里而被丢弃、回落到第一项。
        labels = {i: f"{i18n_s(r.name)} · {i18n_s(r.country)}" for i, r in enumerate(lgs.itertuples())}
        c1, c2, c3 = st.columns([2, 1, 2])
        with c1:
            pick_i = st.selectbox(t("选择联赛"), list(labels),
                                  format_func=lambda i: labels[i], key="lg_pick")
        lid = int(lgs.iloc[pick_i]["league_id"])

        seasons = q_df("""SELECT DISTINCT season FROM standings WHERE league_id=?
                          ORDER BY season DESC""", (lid,))
        season_opts = seasons["season"].tolist() if not seasons.empty else []
        with c2:
            season = st.selectbox(t("赛季"), season_opts, key="lg_season") if season_opts else None

        stn = pd.DataFrame()
        if season:
            with c3:
                chip_row([t("联赛"), t("赛季"), t("排名")], active=[t("赛季")])
            stn = q_df("""SELECT s.rank AS "排名", tm.name AS "球队", s.played AS "场次",
                                 s.won AS "胜", s.draw AS "平", s.lost AS "负",
                                 s.goals_for AS "进球", s.goals_against AS "失球",
                                 s.goal_diff AS "净胜球", s.points AS "积分"
                          FROM standings s JOIN teams tm ON tm.team_id = s.team_id
                          WHERE s.league_id=? AND s.season=? ORDER BY s.rank""", (lid, season))

        n_team_lg = num("SELECT COUNT(*) FROM teams WHERE league_id=?", default=0) \
            if False else num(f"SELECT COUNT(*) FROM teams WHERE league_id={lid}")
        n_match_lg = num(f"SELECT COUNT(*) FROM matches WHERE league_id={lid}")

        section(t("联赛概览"), icon=":material/push_pin:")
        metric_row([
            (f"{n_team_lg}", t("参赛球队"), t("当前联赛"), ":material/circle:", TH.get("accent")),
            (f"{n_match_lg:,}", t("累计比赛"), t("含历史赛季"), ":material/sports_soccer:", TH.get("accent")),
            (f"{len(stn)}", t("积分榜行数"), season and f"{str(season)[:2]}/{str(season)[2:]} {t('赛季')}" or "—",
             ":material/emoji_events:", TH.get("accent")),
        ])

        if not stn.empty:
            section(t("积分榜"), t("数据源 Football-Data.org"), icon=":material/emoji_events:")
            show_df(stn, height=min(760, 42 + 36 * len(stn)))

            sc1, sc2 = st.columns([3, 2])
            with sc1:
                stn_chart = i18n_df(stn)
                VIZ.show(VIZ.scatter(stn_chart, t("进球"), t("失球"), size=t("积分"),
                                     fmt_x=",.0f", fmt_y=",.0f",
                                     tooltip=VIZ.tip((t("球队"), "N"), (t("进球"), "Q"),
                                                     (t("失球"), "Q"), (t("积分"), "Q")),
                                     title=t("进攻 / 防守分布 (气泡大小 = 积分)"),
                                     height=330),
                         key="lg_scatter", fallback=stn_chart)
            with sc2:
                wdl = pd.DataFrame({
                    t("结果"): [t("胜"), t("平"), t("负")],
                    t("场次"): [int(pd.to_numeric(stn["胜"], errors="coerce").sum()),
                                int(pd.to_numeric(stn["平"], errors="coerce").sum()),
                                int(pd.to_numeric(stn["负"], errors="coerce").sum())],
                })
                VIZ.show(VIZ.donut(wdl, t("结果"), t("场次"),
                                   colors=[TH.get("accent"), TH.get("gold"), TH.get("red")],
                                   title=t("联赛胜平负构成"), fmt=",.0f"),
                         key="lg_wdl", fallback=wdl)

        section(t("球队实力 (Elo)"), t("按 Elo 评级排序"), icon=":material/trending_up:")
        elo = q_df("""SELECT name AS "球队", ROUND(elo_rating,1) AS "Elo"
                      FROM teams WHERE league_id=? AND elo_rating IS NOT NULL
                      ORDER BY elo_rating DESC LIMIT 14""", (lid,))
        if elo.empty:
            empty_state(":material/trending_up:", t("暂无 Elo 数据"), t("该联赛球队尚未计算 Elo 评级"))
        else:
            elo_chart = i18n_df(elo)
            VIZ.show(VIZ.rank_bar(elo_chart, t("球队"), "Elo", top=14, fmt=",.1f", gradient=True,
                                  title=t("球队 Elo 评级 (Top 14)")),
                     key="lg_elo", fallback=elo_chart)

# ============================================================
# 球队分析
# ============================================================

def render_teams():
    """球队分析"""
    page_header(t("球队分析"), t("球队档案 · 双队对比 · 近期状态 · 历史交锋"),
                icon=":material/circle:", breadcrumb=t("数据浏览"))

    tdf = q_df("""SELECT t.team_id, t.name, t.short_name, t.league_id,
                         l.name AS lg, t.founded, t.stadium, t.capacity, t.elo_rating
                  FROM teams t LEFT JOIN leagues l ON l.league_id = t.league_id
                  ORDER BY t.name""")
    if tdf.empty:
        empty_state(":material/circle:", t("暂无球队数据"), t("请先导入球队与联赛数据"))
    else:
        # 同 联赛数据: 值用行号, 联赛名只作 format_func 显示名 -> 切语言不缺省回第一队
        labels = {i: f"{r.name}  ·  {txt_i(r.lg)}" for i, r in enumerate(tdf.itertuples())}
        c1, c2 = st.columns(2)
        with c1:
            ai = st.selectbox(t("球队 A"), list(labels),
                              format_func=lambda i: labels[i], key="cmp_a")
        with c2:
            bi = st.selectbox(t("球队 B"), list(labels), index=min(1, len(labels) - 1),
                              format_func=lambda i: labels[i], key="cmp_b")

        A = tdf.iloc[ai]
        B = tdf.iloc[bi]

        def team_form(team_id, n=10):
            df = q_df("""SELECT home_team_id, away_team_id, home_goals hg, away_goals ag
                         FROM matches WHERE status='FT'
                           AND (home_team_id=? OR away_team_id=?)
                         ORDER BY date DESC LIMIT ?""", (team_id, team_id, n))
            w = d = l = 0
            seq = []
            for r in df.itertuples():
                if isnull(r.hg) or isnull(r.ag):
                    continue
                gf = r.hg if r.home_team_id == team_id else r.ag
                ga = r.ag if r.home_team_id == team_id else r.hg
                if gf > ga:
                    w += 1
                    seq.append("W")
                elif gf == ga:
                    d += 1
                    seq.append("D")
                else:
                    l += 1
                    seq.append("L")
            return w, d, l, seq

        wA, dA, lA, seqA = team_form(int(A.team_id))
        wB, dB, lB, seqB = team_form(int(B.team_id))

        section(t("对比概览"), icon=":material/swords:")
        cc1, cc2, cc3 = st.columns([2, 1, 2])
        with cc1:
            info_card(f"{A['name']}", [
                f"{t('Elo 评级')}: <b>{numf(A.elo_rating, 1)}</b>",
                f"{t('联赛')}: {txt_i(A.lg)} · {txt(A.short_name)}",
                f"{t('成立年份')}: {intf(A.founded)}",
                f"{t('主场')}: {txt(A.stadium)}",
                f"{t('容纳人数')}: {intf(A.capacity)}",
                f"{t('近 10 场')}: <b>{wA}</b>{t('胜')} <b>{dA}</b>{t('平')} <b>{lA}</b>{t('负')}",
                (f"{t('走势')}: {' '.join(seqA) or '—'}", True),
            ], icon=":material/circle:", color=TH.get("accent"))
        with cc2:
            metric_row([("VS", t("对比分析"), "", ":material/balance:", TH.get("accent"))])
        with cc3:
            info_card(f"{B['name']}", [
                f"{t('Elo 评级')}: <b>{numf(B.elo_rating, 1)}</b>",
                f"{t('联赛')}: {txt_i(B.lg)} · {txt(B.short_name)}",
                f"{t('成立年份')}: {intf(B.founded)}",
                f"{t('主场')}: {txt(B.stadium)}",
                f"{t('容纳人数')}: {intf(B.capacity)}",
                f"{t('近 10 场')}: <b>{wB}</b>{t('胜')} <b>{dB}</b>{t('平')} <b>{lB}</b>{t('负')}",
                (f"{t('走势')}: {' '.join(seqB) or '—'}", True),
            ], icon=":material/circle:", color=TH.get("accent"))

        diff = (A.elo_rating or 0) - (B.elo_rating or 0)
        if diff > 0:
            badge(f"{A['name']} Elo 领先 {abs(diff):.1f}", "ok")
        elif diff < 0:
            badge(f"{B['name']} Elo 领先 {abs(diff):.1f}", "wait")
        else:
            badge(t("两队 Elo 评级相同"), "info")

        section(t("关键指标对比"), f"{A['name']} vs {B['name']}", icon=":material/bar_chart:")
        cmp_df = pd.DataFrame({
            t("指标"): [t("Elo 评级"), t("成立年份"), t("主场容纳"), t("联赛")],
            str(A["name"]): [numf(A.elo_rating, 1), intf(A.founded), intf(A.capacity), txt_i(A.lg)],
            str(B["name"]): [numf(B.elo_rating, 1), intf(B.founded), intf(B.capacity), txt_i(B.lg)],
        })
        show_df(cmp_df)

        kc1, kc2 = st.columns([3, 2])
        with kc1:
            form_df = pd.DataFrame({
                t("球队"): [str(A["name"])] * 3 + [str(B["name"])] * 3,
                t("结果"): [t("胜"), t("平"), t("负")] * 2,
                t("场次"): [wA, dA, lA, wB, dB, lB],
            })
            VIZ.show(VIZ.grouped_bar(form_df, t("球队"), t("结果"), t("场次"),
                                     colors=[TH.get("accent"), TH.get("gold"), TH.get("red")],
                                     fmt=",.0f", rotate=-15,
                                     title=t("近 10 场战绩对比"), height=280),
                     key="team_form_cmp", fallback=form_df)
        with kc2:
            elo_df = pd.DataFrame({
                t("球队"): [str(A["name"]), str(B["name"])],
                "Elo": [float(A.elo_rating or 0), float(B.elo_rating or 0)],
            })
            if elo_df["Elo"].abs().sum() == 0:
                empty_state(":material/trending_up:", t("暂无 Elo 数据"), t("这两支球队尚未计算 Elo 评级"))
            else:
                # Elo 数值集中在 1400~1900: 固定轴范围 + 指定柱子基线,
                # 否则柱子从 0 起算会被轴范围裁掉(只剩数字标签, 柱子看不见)
                lo = max(0, int(elo_df["Elo"].min() - 60))
                hi = int(elo_df["Elo"].max() + 40)
                VIZ.show(VIZ.bar(elo_df, t("球队"), "Elo", fmt=",.1f", label=True,
                                 rotate=-10, title=t("Elo 评级对比"), height=280,
                                 y_domain=(lo, hi), y_base=lo, bar_size=64),
                         key="team_elo_cmp", fallback=elo_df)

        # ---------- 球队能力雷达(数据来自预计算表 team_radar) ----------
        tr = q_df("""SELECT * FROM team_radar WHERE team_id IN (?,?)""",
                  (int(A.team_id), int(B.team_id)))
        if len(tr) >= 2:
            dims_zh = [t("进攻"), t("防守"), t("射门压制"), t("纪律"),
                       t("身价"), t("经验"), t("稳定性")]
            dims_en = ["Attack", "Defense", "Shot control", "Discipline",
                       "Squad value", "Experience", "Stability"]
            dim_names = dims_zh if lang() == "zh" else dims_en
            rows = []
            for _, rr in tr.iterrows():
                for dn, col in zip(dim_names,
                                   ["s_attack", "s_defense", "s_dominance", "s_discipline",
                                    "s_value", "s_experience", "s_stability"]):
                    rows.append({t("能力"): dn, t("数值"): float(rr[col] or 0),
                                 t("球队"): str(rr["team"])})
            rdf = pd.DataFrame(rows)
            section(t("球队能力雷达"), t("同联赛内百分位（0–100）"), icon=":material/radar:")
            VIZ.show(VIZ.radar(rdf, t("能力"), t("数值"), series=t("球队"),
                               domain_max=100, height=420,
                               title=f"{A['name']} vs {B['name']}"),
                     key="team_radar_cmp", fallback=rdf)
        else:
            empty_state(":material/radar:", t("球队雷达数据不足"),
                        t("该两队需至少有 5 场已完赛比赛才会生成能力雷达"))

        h2h = q_df("""SELECT date(m.date) AS "日期", m.home_goals AS "主队进球",
                             m.away_goals AS "客队进球"
                      FROM matches m
                      WHERE m.status='FT' AND ((m.home_team_id=? AND m.away_team_id=?)
                            OR (m.home_team_id=? AND m.away_team_id=?))
                      ORDER BY m.date DESC LIMIT 8""",
                    (int(A.team_id), int(B.team_id), int(B.team_id), int(A.team_id)))
        section(t("历史交锋"), f"{A['name']} vs {B['name']}", icon=":material/handshake:")
        if h2h.empty:
            empty_state(":material/handshake:", t("暂无交锋记录"), t("两队在该数据库范围内没有已完赛的交锋"))
        else:
            show_df(h2h)
        st.info(t("提示") + "：" + t("前往「比赛预测」页面可获取 AI 概率预测与 SHAP 归因。")
                + f" {A['name']} vs {B['name']}")

# ============================================================
# 球员分析
# ============================================================

def render_players():
    """球员分析"""
    page_header(t("球员分析"), t("球员档案 · 身价与能力 · 球队阵容"),
                icon=":material/person:", breadcrumb=t("数据浏览"))

    tab_search, tab_squad = st.tabs([f"{t('球员检索')}", f"{t('球队阵容')}"])

    with tab_search:
        cq1, cq2 = st.columns([3, 2])
        with cq1:
            # key 必须显式给出: label/placeholder 随语言变化, 无 key 时切语言会清空已输入的检索词。
            kw = st.text_input(t("球员名称"), value="",
                               placeholder=t("中文名或英文名，如 哈兰德 / Haaland（留空看身价 Top 20）"),
                               key="pl_search")
        k = kw.strip()
        _HIT_SQL = """SELECT p.player_id, p.name AS "球员", p.name_en AS "英文名",
                             p.position AS "位置", t.name AS "球队", l.name AS "联赛",
                             p.age AS "年龄", p.nationality AS "国籍",
                             p.market_value AS "身价(€)", p.height AS "身高",
                             p.foot AS "惯用脚"
                      FROM players p
                      LEFT JOIN teams t ON t.team_id = p.team_id
                      LEFT JOIN leagues l ON l.league_id = t.league_id
                      WHERE {cond} ORDER BY p.market_value DESC NULLS LAST LIMIT 40"""
        if k:
            hits = q_df(_HIT_SQL.format(cond="(p.name LIKE ? OR p.name_en LIKE ?)"),
                        (f"%{k}%", f"%{k}%"))
        else:
            # 留空时给出默认内容, 保证页面不是空白(雷达图等一键可见)
            hits = q_df(_HIT_SQL.format(cond="p.market_value IS NOT NULL"))
            st.caption(t("未输入关键词：默认展示身价 Top 40，可直接从下方选择球员查看档案与能力雷达。"))

        if hits.empty:
            empty_state(":material/search:", t("未找到匹配球员"), f"{t('关键词')}: {kw}",
                        command="SELECT * FROM players WHERE name LIKE '%...%'")
        else:
            section(t("匹配结果"), f"{len(hits)} {t('名球员')}", icon=":material/checklist:")
            disp = hits.copy()
            disp["位置"] = disp["位置"].map(pos_zh)
            disp["国籍"] = disp["国籍"].map(fmt_nation)
            disp["身高"] = disp["身高"].map(fmt_height)
            disp["身价(€)"] = disp["身价(€)"].map(money)
            show_df(disp[[c for c in disp.columns if c != "player_id"]], height=260)

            # 球员选择器: 在结果中切换查看对象(默认第一位)
            plabels = {}
            for _, r in hits.iterrows():
                tag = str(r["球员"])
                en = r["英文名"]
                if isinstance(en, str) and en.strip() and en != r["球员"]:
                    tag += f"  ·  {en}"
                team = r["球队"]
                if isinstance(team, str) and team.strip():
                    tag += f"  ·  {team}"
                plabels[int(r["player_id"])] = tag
            with cq2:
                sel_pid = st.selectbox(t("选择球员查看详情"), list(plabels),
                                       format_func=lambda i: plabels[i], key="pl_pick")
            top = hits[hits["player_id"] == sel_pid].iloc[0]

            section(t("球员档案"), plabels[int(sel_pid)], icon=":material/badge:")
            mv_hist = pd.DataFrame()
            tm_id = q_one("SELECT tm_player_id FROM players WHERE player_id=?",
                          (int(sel_pid),), default=None)
            if tm_id:
                mv_hist = q_df("""SELECT value_date AS "日期", value AS "身价(€)"
                                  FROM tm_player_market_value WHERE player_id=?
                                  ORDER BY value_date""", (int(tm_id),))
                pc1, pc2, pc3 = st.columns(3)
                with pc1:
                    info_card(t("基本信息"), [
                        f"{t('位置')}: {pos_zh(top['位置'])}",
                        f"{t('年龄')}: {intf(top['年龄'])}",
                        f"{t('国籍')}: {fmt_nation(top['国籍'])}",
                        f"{t('身高')}: {fmt_height(top['身高'])}",
                        f"{t('惯用脚')}: {txt(top['惯用脚'])}",
                    ], icon=":material/badge:", color=TH.get("accent"))
                with pc2:
                    info_card(t("所属球队"), [
                        f"{t('球队')}: {txt(top['球队'])}",
                        f"{t('联赛')}: {txt(top['联赛'])}",
                        f"{t('市场身价')}: <b>{money(top['身价(€)'])}</b>",
                    ], icon=":material/circle:", color=TH.get("accent"))
                with pc3:
                    info_card(t("数据覆盖"), [
                        f"TM {t('档案')}: {t('已关联') if tm_id else t('未关联')}",
                        f"{t('身价记录')}: {len(mv_hist)} {t('条')}",
                        (t("转会 / 伤病数据来自 Transfermarkt"), True),
                    ], icon=":material/folder:", color=TH.get("accent"))

                # ---------- 能力雷达图(数据来自预计算表 player_radar) ----------
                pr = q_df("""SELECT * FROM player_radar WHERE player_id=?""",
                          (int(top["player_id"]),))
                if not pr.empty:
                    r0 = pr.iloc[0]
                    dims_zh = [t("进球能力"), t("助攻能力"), t("进攻参与"), t("出场稳定性"),
                               t("纪律性"), t("身价价值"), t("比赛经验")]
                    dims_en = ["Finishing", "Creativity", "Involvement", "Availability",
                               "Discipline", "Market value", "Experience"]
                    dim_names = dims_zh if lang() == "zh" else dims_en
                    rl = pd.DataFrame({
                        t("能力"): dim_names,
                        t("数值"): [float(r0.s_goals or 0), float(r0.s_assists or 0),
                                    float(r0.s_involve or 0), float(r0.s_minutes or 0),
                                    float(r0.s_discipline or 0), float(r0.s_value or 0),
                                    float(r0.s_experience or 0)],
                        t("球员"): [str(top["球员"])] * 7,
                    })
                    section(t("能力雷达"), t("同位置百分位（0–100）"), icon=":material/radar:")
                    rc1, rc2 = st.columns([3, 2])
                    with rc1:
                        VIZ.show(VIZ.radar(rl, t("能力"), t("数值"), series=t("球员"),
                                           domain_max=100, height=380,
                                           title=t("能力雷达（近 3 赛季同位置百分位）")),
                                 key="player_radar", fallback=rl)
                    with rc2:
                        if lang() == "zh":
                            info_card(t("近 3 赛季原始数据"), [
                                f"{t('出场')}: {int(r0.apps or 0)} 场 / {int(r0.minutes or 0)} 分钟",
                                f"{t('进球')}: {int(r0.goals or 0)}",
                                f"{t('助攻')}: {int(r0.assists or 0)}",
                                f"{t('场均参与')}: {float(r0.involve_p90 or 0):.2f} / 90min",
                                f"{t('纪律')}: {float(r0.cards_p90 or 0):.2f} 张/90min",
                                f"{t('位置组')}: {r0.pos_group}",
                            ], icon=":material/query_stats:", color=TH.get("accent"))
                        else:
                            info_card("Last 3 seasons", [
                                f"Apps: {int(r0.apps or 0)} / {int(r0.minutes or 0)} min",
                                f"Goals: {int(r0.goals or 0)}",
                                f"Assists: {int(r0.assists or 0)}",
                                f"Involvement: {float(r0.involve_p90 or 0):.2f} / 90",
                                f"Cards: {float(r0.cards_p90 or 0):.2f} / 90",
                                f"Position group: {r0.pos_group}",
                            ], icon=":material/query_stats:", color=TH.get("accent"))
                else:
                    empty_state(":material/radar:", t("暂无能力雷达数据"),
                                t("该球员缺少近 3 赛季出场数据（需与 Transfermarkt 关联并有比赛记录）"))

                # ---------- 伤病 / 转会(来自 Transfermarkt 层) ----------
                if tm_id:
                    inj = q_df("""SELECT injury_reason AS "伤病", from_date AS "开始",
                                         end_date AS "结束", days_missed AS "缺席天数",
                                         games_missed AS "缺席场次"
                                  FROM tm_player_injuries WHERE player_id=?
                                  ORDER BY from_date DESC LIMIT 12""", (int(tm_id),))
                    trf = q_df("""SELECT transfer_date AS "日期", from_team_name AS "原球队",
                                         to_team_name AS "新球队", transfer_type AS "类型",
                                         transfer_fee AS "费用"
                                  FROM tm_transfers WHERE player_id=?
                                  ORDER BY transfer_date DESC LIMIT 12""", (int(tm_id),))
                    if not inj.empty or not trf.empty:
                        section(t("伤病与转会"), "Transfermarkt", icon=":material/history:")
                        ic1, ic2 = st.columns(2)
                        with ic1:
                            st.markdown(f"**{t('伤病记录')}**")
                            if inj.empty:
                                st.caption(t("暂无伤病记录"))
                            else:
                                show_df(inj)
                        with ic2:
                            st.markdown(f"**{t('转会记录')}**")
                            if trf.empty:
                                st.caption(t("暂无转会记录"))
                            else:
                                show_df(trf)

                if not mv_hist.empty:
                    section(t("身价走势"), "Transfermarkt", icon=":material/payments:")
                    mv_line = mv_hist.copy()
                    mv_line["身价(€)"] = pd.to_numeric(mv_line["身价(€)"], errors="coerce")
                    mv_line = mv_line.dropna(subset=["身价(€)"])
                    # 列名随语言切换(Altair 以列名作轴标题), fallback 也须用译后表
                    mv_chart = i18n_df(mv_line)
                    ff_mv = i18n_df(mv_hist)
                    VIZ.show(VIZ.line(mv_chart, t("日期"), t("身价(€)"), area=True, point=True,
                                      fmt=",.0f", x_type="T",
                                      title=t("身价走势 (Transfermarkt)"), height=300),
                             key="player_mv", fallback=ff_mv, fallback_kind="line")

    with tab_squad:
        sq = q_df("""SELECT t.team_id, t.name, l.name AS lg FROM teams t
                     LEFT JOIN leagues l ON l.league_id = t.league_id ORDER BY t.name""")
        if sq.empty:
            empty_state(":material/group:", t("暂无球队数据"), t("请先导入球队数据"))
        else:
            # 值用行号(语言无关), 队名+联赛名交给 format_func -> 切语言不会丢已选球队
            slabels = {i: f"{r.name}  ·  {txt_i(r.lg)}" for i, r in enumerate(sq.itertuples())}
            sel_i = st.selectbox(t("选择球队"), list(slabels),
                                 format_func=lambda i: slabels[i], key="squad_team")
            trow = sq.iloc[sel_i]
            squad = q_df("""SELECT name AS "球员", position AS "位置", age AS "年龄",
                                   nationality AS "国籍", number AS "号码",
                                   height AS "身高", market_value AS "身价(€)"
                            FROM players WHERE team_id=? ORDER BY market_value DESC""",
                          (int(trow.team_id),))
            if squad.empty:
                empty_state(":material/group:", f"{trow['name']} {t('暂无球员数据')}",
                            t("该球队阵容尚未导入"),
                            command="python scripts/import_players.py")
            else:
                section(t("阵容规模"), trow["name"], icon=":material/group:")
                # 按语言无关的位置大组代码计数, 避免英文态用中文键查不到而显示 0
                positions = squad["位置"].map(pos_group).value_counts()
                metric_row([
                    (f"{len(squad)}", t("球员总数"), txt_i(trow.lg), ":material/group:", TH.get("accent")),
                    (f"{int(positions.get('FW', 0))}", t("前锋"), t("Attacker"), ":material/bolt:", TH.get("gold")),
                    (f"{int(positions.get('MF', 0))}", t("中场"), t("Midfielder"), ":material/target:", TH.get("blue")),
                    (f"{int(positions.get('DF', 0))}", t("后卫"), t("Defender"), ":material/shield:", TH.get("purple")),
                ])
                sqd = squad.copy()
                sqd["位置"] = sqd["位置"].map(pos_zh)
                sqd["身价(€)"] = sqd["身价(€)"].map(money)

                sc1, sc2 = st.columns([2, 3])
                with sc1:
                    pos_df = pd.DataFrame({
                        t("位置"): [pos_group_label(k) for k in positions.index],
                        t("人数"): [int(v) for v in positions.values],
                    })
                    VIZ.show(VIZ.donut(pos_df, t("位置"), t("人数"),
                                       colors=[TH.get("gold"), TH.get("blue"),
                                               TH.get("purple"), TH.get("accent")],
                                       title=t("阵容位置构成"), fmt=",.0f"),
                             key="squad_pos", fallback=pos_df)
                with sc2:
                    val = squad.copy()
                    val["身价(€)"] = pd.to_numeric(val["身价(€)"], errors="coerce")
                    val = val.dropna(subset=["身价(€)"])
                    val = val[val["身价(€)"] > 0].nlargest(10, "身价(€)")
                    if val.empty:
                        empty_state(":material/payments:", t("暂无身价数据"), t("该球队球员身价尚未导入"))
                    else:
                        val_chart = i18n_df(val)
                        VIZ.show(VIZ.rank_bar(val_chart, t("球员"), t("身价(€)"), top=10,
                                              fmt=",.0f", gradient=True,
                                              title=t("阵容身价 Top 10"), height=320),
                                 key="squad_value", fallback=val_chart)

                section(t("球员名单"), t("按身价降序"), icon=":material/checklist:")
                show_df(sqd, height=min(700, 42 + 36 * len(sqd)))

# ============================================================
# 比赛详情
# ============================================================

def render_match():
    """比赛详情"""
    page_header(t("比赛详情"), t("技术统计 · 首发阵容 · 事件时间轴 · 伤停名单 · 裁判"),
                icon=":material/search:", breadcrumb=t("数据浏览"),
                meta="Football-Data / Understat<br>Transfermarkt / API-Football")

    fc1, fc2 = st.columns([1, 3])
    with fc1:
        # 选项来自数据库全部联赛(不再是硬编码 5 个); 内部值保持中文
        # (下方 lg_where / params 以 l.name 绑定 SQL), 仅翻译显示
        lg_names = q_df("SELECT name FROM leagues ORDER BY league_id")
        lg_opts = ["全部"] + (lg_names["name"].tolist() if not lg_names.empty else [])
        lg_sel = st.selectbox(t("联赛"), lg_opts, format_func=lambda x: t(x), key="md_lg")
    lg_where = "" if lg_sel == "全部" else "AND l.name = ?"
    params = () if lg_sel == "全部" else (lg_sel,)
    mdf = q_df(f"""SELECT m.match_id, date(m.date) d, l.name lg, th.name h, ta.name a,
                          m.home_goals hg, m.away_goals ag, m.ht_home hh, m.ht_away ha,
                          m.home_shots hs, m.away_shots ash, m.home_sot hst, m.away_sot ast,
                          m.home_corners hc, m.away_corners ac,
                          m.home_xg hx, m.away_xg ax, m.referee, m.venue,
                          m.af_fixture_id, m.home_team_id, m.away_team_id
                   FROM matches m JOIN leagues l ON l.league_id = m.league_id
                   JOIN teams th ON th.team_id = m.home_team_id
                   JOIN teams ta ON ta.team_id = m.away_team_id
                   WHERE m.status = 'FT' {lg_where}
                   -- 优先列出"有技术统计"的比赛: 否则默认选中最新一场(可能缺统计),
                   -- 页面一进来全是空状态, 误以为功能不可用。
                   ORDER BY (m.home_shots IS NOT NULL) DESC,
                            (m.home_xg IS NOT NULL) DESC,
                            m.date DESC LIMIT 200""", params)

    if mdf.empty:
        empty_state(":material/search:", t("暂无已完赛比赛"), t("请先导入比赛数据"),
                    command="python scripts/import_data.py")
    else:
        opts = [f"{r.d}  {r.h} vs {r.a}  ({intf(r.hg)}-{intf(r.ag)})" for r in mdf.itertuples()]
        with fc2:
            pick = st.selectbox(t("选择比赛"), opts, key="md_match")
        row = mdf.iloc[opts.index(pick)]

        metric_row([
            (f"{intf(row.hg)} : {intf(row.ag)}", t("全场比分"),
             f"{t('半场')} {intf(row.hh)} : {intf(row.ha)}", ":material/sports_soccer:", TH.get("accent")),
            (f"{numf(row.hx)} : {numf(row.ax)}", t("xG 预期进球"),
             f"{t('射门')} {intf(row.hs)}-{intf(row.ash)} · {t('射正')} {intf(row.hst)}-{intf(row.ast)}",
             ":material/trending_up:", TH.get("blue")),
            (txt(row.referee), t("主裁判"), None, ":material/gavel:", TH.get("purple")),
            (txt(row.venue)[:18], t("比赛场地"),
             t("待填充（API-Football）") if isnull(row.venue) else txt_i(row.lg),
             ":material/stadium:", TH.get("gold")),
        ])

        md_tabs = st.tabs([t("技术统计"), t("首发阵容"), t("事件时间轴"), t("伤停名单")])

        with md_tabs[0]:
            section(t("比赛技术统计"), f"{row.h} vs {row.a}", icon=":material/bar_chart:")
            stat_rows = [
                (t("射门"), row.hs, row.ash), (t("射正"), row.hst, row.ast),
                (t("角球"), row.hc, row.ac),
                (t("xG"), round(row.hx, 2) if not isnull(row.hx) else None,
                 round(row.ax, 2) if not isnull(row.ax) else None),
                (t("半场比分"), intf(row.hh), intf(row.ha)),
            ]
            show_df(pd.DataFrame([{t("指标"): k, f"{row.h}": txt(v1), f"{row.a}": txt(v2)}
                                  for k, v1, v2 in stat_rows]))

            ms1, ms2 = st.columns([3, 2])
            with ms1:
                base = [(t("射门"), row.hs, row.ash), (t("射正"), row.hst, row.ast),
                        (t("角球"), row.hc, row.ac)]
                base = [(k, v1, v2) for k, v1, v2 in base
                        if not isnull(v1) or not isnull(v2)]
                if not base:
                    empty_state(":material/bar_chart:", t("暂无技术统计数据"),
                                t("该场比赛的射门 / 角球数据尚未导入"))
                else:
                    long_t = pd.DataFrame(
                        [{t("指标"): k, t("球队"): txt(nm), t("数值"): float(v or 0)}
                         for k, v1, v2 in base
                         for nm, v in ((row.h, v1), (row.a, v2))])
                    VIZ.show(VIZ.grouped_bar(long_t, t("指标"), t("球队"), t("数值"),
                                             colors=[TH.get("accent"), TH.get("blue")],
                                             fmt=",.0f",
                                             title=t("射门 / 射正 / 角球对比"), height=280),
                             key="md_technique", fallback=long_t)
            with ms2:
                if isnull(row.hx) and isnull(row.ax):
                    empty_state(":material/trending_up:", t("暂无 xG 数据"),
                                t("该场比赛未收录预期进球 (xG)")
                                if lg_sel != "全部" else t("所选联赛范围内暂无 xG"),
                                command="python scripts/import_understat.py")
                else:
                    xg_df = pd.DataFrame({
                        t("球队"): [txt(row.h), txt(row.a)],
                        "xG": [float(row.hx or 0), float(row.ax or 0)],
                    })
                    VIZ.show(VIZ.bar(xg_df, t("球队"), "xG", fmt=",.2f", label=True,
                                     rotate=-10, color=TH.get("accent"),
                                     title=t("预期进球 (xG) 对比"), height=280),
                             key="md_xg", fallback=xg_df)

        with md_tabs[1]:
            n_lu = q_one("SELECT COUNT(*) FROM af_lineups")
            if row.af_fixture_id and n_lu:
                lu = q_df("""SELECT team_name, formation, number, player_name, pos
                             FROM af_lineups WHERE fixture_id = ?
                             ORDER BY team_name, number""", (int(row.af_fixture_id),))
                for team in (lu["team_name"].unique() if not lu.empty else []):
                    st.markdown(f"**{team}** · {t('阵型')}: "
                                f"{lu[lu.team_name == team]['formation'].iloc[0] or '—'}")
                    show_df(lu[lu.team_name == team][["number", "player_name", "pos"]],
                            height=360)
            else:
                empty_state(":material/group:", t("阵容数据待填充"),
                            t("来源：API-Football fixtures/lineups"),
                            command="python scripts/import_af_backfill.py --phase lineups")
                st.caption(f"{t('现有可参考')}：{t('球小策赛前阵容')} "
                           f"{q_one('SELECT COUNT(*) FROM qxz_lineups')} {t('场')}")

        with md_tabs[2]:
            n_ev = q_one("SELECT COUNT(*) FROM af_events")
            if row.af_fixture_id and n_ev:
                ev = q_df("""SELECT minute, team_name, player_name, type, detail, assist_name
                             FROM af_events WHERE fixture_id = ? ORDER BY minute""",
                          (int(row.af_fixture_id),))
                show_df(ev, height=360)
            else:
                empty_state(":material/bolt:", t("事件时间轴待填充"),
                            t("来源：API-Football fixtures/events"),
                            command="python scripts/import_af_backfill.py --phase events")

        with md_tabs[3]:
            club_ids = q_df("SELECT club_id FROM tm_club_map WHERE team_id IN (?,?)",
                            (int(row.home_team_id), int(row.away_team_id)))
            if club_ids.empty:
                st.info(t("该两队尚未建立 Transfermarkt 映射"))
            else:
                ids = tuple(club_ids["club_id"].tolist())
                ph = ",".join("?" * len(ids))
                inj = q_df(f"""SELECT p.player_name AS "球员", i.injury_reason AS "伤病",
                                      i.from_date AS "开始", i.end_date AS "结束",
                                      i.days_missed AS "缺席天数", i.games_missed AS "缺席场次"
                               FROM tm_player_injuries i
                               JOIN tm_players p ON p.player_id = i.player_id
                               WHERE i.player_id IN (SELECT player_id FROM tm_player_seasons
                                                     WHERE team_id IN ({ph}))
                               ORDER BY i.from_date DESC LIMIT 25""", ids)
                section(t("伤停名单"), f"{row.h} / {row.a} · Transfermarkt", icon=":material/medical_services:")
                if inj.empty:
                    empty_state(":material/medical_services:", t("暂无伤病记录"), t("这两支球队近期没有伤病数据"))
                else:
                    show_df(inj, height=320)

# ============================================================
# 比赛预测
# ============================================================

def render_predict():
    """比赛预测"""
    page_header(t("比赛结果预测"),
                t("单场预测含 SHAP 归因 · 批量预测为集成 v2+v7 · 严格样本外评估 + 历史复盘"),
                icon=":material/target:", breadcrumb=t("AI 能力"))

    n_pred_bt = num("SELECT COUNT(*) FROM predictions WHERE is_backtest=1")
    hit_avg = q_one("SELECT AVG(hit) FROM predictions WHERE is_backtest=1", default=None)
    n_xg = num("SELECT COUNT(*) FROM matches WHERE home_xg IS NOT NULL AND away_xg IS NOT NULL")
    # 严格样本外指标(与后台「模型管理」同源: model_metrics 表)——这是**当前模型**的可信数字
    _oos = q_df("SELECT model, acc, test_n FROM model_metrics ORDER BY acc DESC LIMIT 1")
    if not _oos.empty:
        oos_model = str(_oos.iloc[0]["model"])
        oos_acc = float(_oos.iloc[0]["acc"])
        oos_n = int(_oos.iloc[0]["test_n"]) if not isnull(_oos.iloc[0]["test_n"]) else 1817
    else:
        oos_model, oos_acc, oos_n = "v9 集成 v2+v7", 50.14, 1817

    section(t("模型信息"), icon=":material/smart_toy:")
    metric_row([
        (t("集成 v2+v7"), t("预测模型"),
         t("单场走 v2 + SHAP 归因 · 批量用集成"), ":material/smart_toy:", TH.get("accent")),
        # 首页/后台/评估报告统一使用「严格样本外」数字; 旧的 v1 回测(含训练期重叠)只作参考,
        # 且必须明确标注 —— 否则页面上摆的是被自家文档标注为"虚高"的那个数。
        (f"{oos_acc:.2f}%", t("严格样本外准确率"),
         f"{oos_model} · {oos_n:,} {t('场')} · {t('基线')} 44.36%",
         ":material/target:", TH.get("accent")),
        (f"{n_xg:,}", t("官方 xG 覆盖"), t("Understat 官方预期进球"), ":material/trending_up:", TH.get("accent")),
        (f"{hit_avg:.1%}" if not isnull(hit_avg) else "—", t("历史回测命中率"),
         f"{n_pred_bt:,} {t('场')} · v1 {t('模型 · 含训练期重叠，仅作参考')}",
         ":material/history:", TH.get("gold")),
    ])

    section(t("发起预测"), t("选择主客队，调用后端模型"), icon=":material/bolt:")
    all_teams = q_df("SELECT name FROM teams WHERE league_id BETWEEN 1 AND 5 "
                     "ORDER BY elo_rating DESC LIMIT 120")
    team_opts = all_teams["name"].tolist() if not all_teams.empty else []
    if not team_opts:
        empty_state(":material/target:", t("暂无球队数据"), t("请先导入球队数据"))
    else:
        c1, c2 = st.columns(2)
        with c1:
            home_team = st.selectbox(f"{t('主队')}", team_opts, key="pred_home")
        with c2:
            away_team = st.selectbox(f"{t('客队')}", team_opts,
                                     index=min(1, len(team_opts) - 1), key="pred_away")

        if wide_button(f"{t('开始AI预测')}", type_="primary"):
            with st.spinner(t("AI 正在构建特征并推理...")):
                try:
                    resp = requests.post(f"{API_BASE}/predictions/predict",
                                         json={"home_team": home_team, "away_team": away_team},
                                         timeout=30)
                    if resp.status_code == 200:
                        result = resp.json()
                        probs = result.get("probabilities", {})
                        pred_label = str(result.get("prediction", ""))

                        pred_color = (TH.get("accent") if "主胜" in pred_label
                                      else TH.get("gold") if "平" in pred_label else TH.get("red"))
                        section(t("AI 预测结果"), f"{home_team} vs {away_team}", icon=":material/target:")
                        metric_row([{
                            "value": pred_label, "label": t("预测结论"),
                            "hint": f"{home_team} vs {away_team} · "
                                    f"{t('置信度')}: {result.get('confidence', 0):.1%}",
                            "icon": ":material/target:", "color": pred_color,
                        }])

                        section(t("概率分布"), icon=":material/bar_chart:")
                        metric_row([
                            (f"{probs.get('home_win', 0):.1%}", t("主胜"), home_team, ":material/home:", TH.get("accent")),
                            (f"{probs.get('draw', 0):.1%}", t("平局"), "Draw", ":material/balance:", TH.get("gold")),
                            (f"{probs.get('away_win', 0):.1%}", t("客胜"), away_team, ":material/flight:", TH.get("red")),
                        ])
                        pdf = pd.DataFrame({
                            t("结果"): [f"{home_team} ({t('主胜')})", t("平局"),
                                       f"{away_team} ({t('客胜')})"],
                            t("概率"): [float(probs.get("home_win", 0)),
                                       float(probs.get("draw", 0)),
                                       float(probs.get("away_win", 0))],
                        })
                        VIZ.show(VIZ.prob_bar(pdf, t("结果"), t("概率"),
                                              colors=[TH.get("accent"), TH.get("gold"),
                                                      TH.get("red")],
                                              height=190, fmt=".1%",
                                              title=t("胜平负概率分布")),
                                 key="pred_prob", fallback=pdf)

                        exp = result.get("explanation", {}) or {}
                        section(t("SHAP 可解释性分析"), t("特征贡献度"), icon=":material/search:")
                        ec1, ec2 = st.columns(2)
                        with ec1:
                            section_cap(t("支持预测的关键因素"), icon=":material/check_circle:")
                            pos = exp.get("top_positive_factors", [])[:5]
                            if pos:
                                for f in pos:
                                    info_card(
                                        str(f.get('feature')),
                                        [(f"SHAP: +{float(f.get('shap_value', 0)):.4f} · "
                                          f"{t('取值')} {f.get('feature_value', 'N/A')}", True)],
                                        icon=":material/trending_up:", color=TH.get("accent"))
                            else:
                                st.info(t("暂无正向因素数据"))
                        with ec2:
                            section_cap(t("不利因素"), icon=":material/warning:")
                            neg = exp.get("top_negative_factors", [])[:5]
                            if neg:
                                for f in neg:
                                    info_card(
                                        str(f.get('feature')),
                                        [(f"SHAP: {float(f.get('shap_value', 0)):.4f} · "
                                          f"{t('取值')} {f.get('feature_value', 'N/A')}", True)],
                                        icon=":material/trending_down:", color=TH.get("red"))
                            else:
                                st.info(t("暂无负向因素数据"))
                    else:
                        st.error(f"{t('预测失败')}: {resp.json().get('detail', t('未知错误'))}")
                except Exception as e:
                    st.error(f"{t('连接后端失败')}: {e}")
                    empty_state(":material/electrical_services:", t("后端服务未启动"),
                                t("请运行 uvicorn src.main:app 后重试"),
                                command="uvicorn src.main:app")

    # ---- 历史预测复盘 ----
    section(t("历史预测复盘"), t("赛后自动回填命中情况"), icon=":material/history_edu:")
    hist = q_df("""SELECT date(m.date) AS "日期", th.name AS "主队", ta.name AS "客队",
                          p.model_version AS "模型", p.pred_result AS "预测",
                          p.actual_result AS "实际", p.hit AS "命中"
                   FROM predictions p
                   JOIN matches m ON m.match_id = p.match_id
                   JOIN teams th ON th.team_id = m.home_team_id
                   JOIN teams ta ON ta.team_id = m.away_team_id
                   ORDER BY m.date DESC LIMIT 40""")
    if hist.empty:
        empty_state(":material/history_edu:", t("暂无预测记录"), t("运行预测脚本后此处会展示复盘结果"),
                    command="python scripts/train_v7.py")
    else:
        hist["预测"] = hist["预测"].map(head_zh)
        hist["实际"] = hist["实际"].map(lambda x: head_zh(x) if not isnull(x) else "—")
        hist["命中"] = hist["命中"].map(lambda x: "✓" if x == 1 else ("✗" if x == 0 else "—"))
        show_df(hist, height=min(700, 42 + 36 * len(hist)))

        hb1, hb2 = st.columns(2)
        with hb1:
            # 分组键用数值(1/0/NULL), 文案在 Python 侧经 t() 映射,
            # 避免 SQL 字面量里的中文在英文态泄漏
            hit_df = q_df("""SELECT hit AS h, COUNT(*) AS n
                             FROM predictions GROUP BY 1 ORDER BY 2 DESC""")
            if hit_df.empty:
                empty_state(":material/target:", t("暂无回测数据"), t("运行回测脚本后可查看命中分布"),
                            command="python scripts/backtest.py")
            else:
                hit_df[t("回测结果")] = hit_df["h"].map(
                    lambda x: t("命中") if x == 1 else (t("未命中") if x == 0 else t("待回填")))
                hit_df[t("场次")] = hit_df["n"]
                hit_df = hit_df[[t("回测结果"), t("场次")]]
                VIZ.show(VIZ.donut(hit_df, t("回测结果"), t("场次"),
                                   colors=[TH.get("accent"), TH.get("red"),
                                           TH.get("t3")],
                                   title=t("样本外回测命中构成"), fmt=",.0f"),
                         key="pred_hit_donut", fallback=hit_df)
        with hb2:
            dist_df = q_df("""SELECT pred_result AS "预测结果", COUNT(*) AS "场次"
                              FROM predictions WHERE pred_result IS NOT NULL
                              GROUP BY 1 ORDER BY 2 DESC""")
            if dist_df.empty:
                empty_state(":material/bar_chart:", t("暂无预测记录"), t("运行预测脚本后可查看分布"),
                            command="python scripts/train_v7.py")
            else:
                dist_df["预测结果"] = dist_df["预测结果"].map(head_zh)
                dist_chart = i18n_df(dist_df)
                VIZ.show(VIZ.bar(dist_chart, t("预测结果"), t("场次"), fmt=",.0f",
                                 color=TH.get("blue"), label=True,
                                 title=t("历史预测结果分布"), height=300),
                         key="pred_dist", fallback=dist_chart)

        model_hit = q_df("""SELECT model_version AS "模型", COUNT(*) AS "样本",
                                   ROUND(AVG(hit) * 100, 1) AS "命中率"
                            FROM predictions
                            WHERE is_backtest = 1 AND hit IS NOT NULL
                            GROUP BY 1 HAVING COUNT(*) >= 10 ORDER BY 3 DESC""")
        if not model_hit.empty:
            mh_chart = i18n_df(model_hit)
            # 诚实标注: predictions 表里的历史回测都是 v1 模型(1,752 场),
            # 其训练期与该赛季有重叠, 官方文档已标注"虚高" —— 因此不能与上方的
            # 严格样本外数字(50.14%)混为一谈, 标题与脚注都要写清楚。
            _mh_title = (t("回测命中率 (%)") if len(mh_chart) <= 1
                         else t("各模型版本回测命中率 (%)"))
            # 样本很少时用指标卡呈现(单根柱子会被拉伸满屏, 视觉上失真)
            if len(mh_chart) <= 2:
                metric_row([(f"{r['命中率']:.1f}%", f"{r['模型']}",
                             f"{t('样本')} {int(r['样本']):,} · {t('含训练期重叠')}",
                             ":material/percent:", TH.get("gold"))
                            for _, r in mh_chart.iterrows()])
            else:
                VIZ.show(VIZ.rank_bar(mh_chart, t("模型"), t("命中率"), top=10, fmt=",.1f",
                                      gradient=True,
                                      title=_mh_title, height=300),
                         key="pred_model_hit", fallback=mh_chart)
            st.caption(t("说明：上表为历史回测（v1 模型，训练期与该赛季部分重叠），"
                         "仅作趋势参考；当前模型的严谨指标见下方「模型样本外对比」。"))

        # ---------- 模型评估可视化(数据来自 model_metrics / confusion / calibration) ----------
        mm = q_df("""SELECT * FROM model_metrics ORDER BY acc DESC LIMIT 8""")
        if not mm.empty:
            section(t("模型样本外对比"), t("同一测试集（训练 < 2025-08-01）"),
                    icon=":material/model_training:")
            ev1, ev2 = st.columns([3, 2])
            with ev1:
                mc = mm.rename(columns={"model": t("模型"), "acc": t("准确率")})
                VIZ.show(VIZ.rank_bar(mc, t("模型"), t("准确率"), fmt=",.2f", top=8,
                                      gradient=True, bar_size=26,
                                      title=t("准确率对比 (%)"), height=320),
                         key="model_acc", fallback=mc)
            with ev2:
                met = mm.rename(columns={"model": t("模型"), "logloss": "LogLoss"})
                VIZ.show(VIZ.rank_bar(met, t("模型"), "LogLoss", fmt=",.4f", top=8,
                                      color=TH.get("purple"), bar_size=26,
                                      title=t("LogLoss（越低越好）"), height=320),
                         key="model_ll", fallback=met)

            conf = q_df("""SELECT actual, predicted, count FROM model_confusion""")
            cal = q_df("""SELECT outcome, predicted, actual, n FROM model_calibration
                          ORDER BY predicted""")
            ec1, ec2 = st.columns([2, 3])
            with ec1:
                if not conf.empty:
                    cm = conf.rename(columns={"actual": t("实际"), "predicted": t("预测"),
                                              "count": t("场次")})
                    VIZ.show(VIZ.heatmap(cm, t("预测"), t("实际"), t("场次"),
                                         fmt=",.0f", show_text=True,
                                         title=t("混淆矩阵（集成模型 · 样本外）"), height=300),
                             key="model_conf", fallback=cm)
            with ec2:
                if not cal.empty:
                    cal2 = cal.copy()
                    cal2["outcome_zh"] = cal2["outcome"].map(
                        lambda x: t(x) if isinstance(x, str) else x)
                    cal3 = cal2.rename(columns={"outcome_zh": t("结果"),
                                                "predicted": t("预测概率"),
                                                "actual": t("实际频率")})
                    VIZ.show(VIZ.multi_line(cal3, t("预测概率"), t("结果"), t("实际频率"),
                                            fmt=",.2f", x_type="Q",
                                            diagonal=t("理想校准"), x_range=(0.0, 1.0),
                                            title=t("概率校准曲线（越贴近虚线越好）"),
                                            height=300),
                             key="model_cal", fallback=cal3)

        fi = q_df("""SELECT feature, importance FROM feature_importance ORDER BY importance DESC LIMIT 15""")
        if not fi.empty:
            section(t("特征重要性 Top 15"), t("XGBoost v7（官方 xG + 阵容身价）"),
                    icon=":material/insights:")
            fic = fi.rename(columns={"feature": t("特征"), "importance": t("重要性")})
            VIZ.show(VIZ.rank_bar(fic, t("特征"), t("重要性"), top=15, fmt=",.4f",
                                  gradient=True, bar_size=20,
                                  title=t("特征重要性"), height=380),
                     key="feat_imp", fallback=fic)

# ============================================================
# AI 智能分析
# ============================================================

def render_agent():
    """AI智能分析"""
    page_header(t("AI 智能分析助手"), t("LangChain 工具增强 Agent · 自然语言查询球队 / 球员 / 比赛数据"),
                icon=":material/smart_toy:", breadcrumb=t("AI 能力"))

    section(t("可用工具"), t("Agent 可调用的数据工具"), icon=":material/home_repair_service:")
    tools_c = st.columns(3)
    tool_items = [
        (":material/circle:", t("球队查询"), [t("球队档案与 Elo"), t("近期战绩与排名")]),
        (":material/person:", t("球员查询"), [t("球员档案与身价"), t("球队阵容检索")]),
        (":material/sports_soccer:", t("比赛查询"), [t("历史交锋记录"), t("技术统计详情")]),
        (":material/emoji_events:", t("积分榜"), [t("五大联赛排名"), t("积分与净胜球")]),
        (":material/target:", t("比赛预测"), [t("调用 XGBoost 模型"), t("胜平负概率输出")]),
        (":material/trending_up:", t("统计分析"), [t("进球 / xG 统计"), t("球队对比分析")]),
    ]
    for i, (icon, name, lines) in enumerate(tool_items):
        with tools_c[i % 3]:
            info_card(name, lines, icon=icon,
                      color=[TH.get("accent"), TH.get("blue"), TH.get("gold")][i % 3])

    section(t("快捷提问"), icon=":material/lightbulb:")
    q1, q2, q3 = st.columns(3)
    with q1:
        if wide_button(f"{t('曼城近期状态')}", key="q1"):
            st.session_state.quick_question = "曼城近期状态如何？"
    with q2:
        if wide_button(f"{t('预测曼城 vs 阿森纳')}", key="q2"):
            st.session_state.quick_question = "预测曼城vs阿森纳的比赛结果"
    with q3:
        if wide_button(f"{t('英超积分榜')}", key="q3"):
            st.session_state.quick_question = "英超当前积分榜是什么样的？"

    divider()

    if "messages" not in st.session_state:
        st.session_state.messages = []

    if not st.session_state.messages:
        empty_state(":material/smart_toy:", t("开始对话"),
                    t("例如：分析利物浦本赛季的表现 / 对比曼城与阿森纳的攻防数据"))

    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    prefill = st.session_state.pop("quick_question", "")
    if prefill:
        st.info(f"{t('已选择快捷问题')}：{prefill}")

    if prompt := st.chat_input(t("输入你的问题，例如：分析利物浦本赛季的表现...")):
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):
            with st.spinner(t("AI 正在调用工具分析数据...")):
                try:
                    resp = requests.post(f"{API_BASE}/agent/chat",
                                         json={"message": prompt}, timeout=60)
                    if resp.status_code == 200:
                        answer = resp.json().get("response", "")
                        st.markdown(answer)
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    else:
                        st.error(f"{t('AI 分析失败')}: "
                                 f"{resp.json().get('detail', t('未知错误'))}")
                except Exception as e:
                    st.error(f"{t('连接后端失败')}: {e}")
                    st.info(t("请确认后端已启动，且在 .env 中配置了 LLM_API_KEY"))

    if st.session_state.messages and st.button(f"{t('清空对话')}"):
        st.session_state.messages = []
        st.rerun()

# ============================================================
# 实时比分
# ============================================================

def render_live():
    """实时比分"""
    page_header(t("实时比分"), t("WebSocket 推送 · 比赛日定时刷新"),
                icon=":material/sensors:", breadcrumb=t("数据浏览"))

    _ok = backend_ok()
    section(t("服务状态"), icon=":material/link:")
    status_list([
        (t("后端服务"), t("运行中") if _ok else t("未启动"), "ok" if _ok else "err"),
        (t("WebSocket 端点"), "/ws/live-scores", "ok" if _ok else "off"),
        (t("刷新频率"), f"2 {t('分钟')}", "off"),
        (t("数据来源"), "API-Football", "ok" if _ok else "off"),
    ])

    section(t("正在进行的比赛"), icon=":material/sports_soccer:")
    if not _ok:
        empty_state(":material/electrical_services:", t("后端服务未启动"), t("实时比分依赖后端 WebSocket 推送"),
                    command="uvicorn src.main:app")
    else:
        try:
            resp = requests.get(f"{API_BASE}/matches/live", timeout=5)
            data = resp.json()
            if isinstance(data, dict) and "note" in data:
                empty_state(":material/pause:", t("当前无正在进行的比赛"),
                            t("非比赛日或实时比分服务未配置"))
            elif isinstance(data, list) and data:
                st.success(f"{t('正在进行')} {len(data)} {t('场比赛')}")
                show_df(pd.DataFrame(data))
            else:
                empty_state(":material/inbox:", t("暂无实时数据"), t("比赛开始后此处会自动刷新"))
        except Exception as e:
            st.error(f"{t('无法连接后端服务')}: {e}")

    section(t("使用说明"), icon=":material/menu_book:")
    steps = [
        ("1", t("配置 API 密钥"),
         t("在 <code>.env</code> 中设置 <code>API_FOOTBALL_KEY</code>")),
        ("2", t("启动后端服务"),
         t("运行 <code>uvicorn src.main:app</code>，定时任务每 2 分钟拉取一次")),
        ("3", t("WebSocket 推送"),
         t("前端通过 <code>/ws/live-scores</code> 接收推送")),
        ("4", t("历史数据"),
         t("非比赛日可查看历史比赛与赛程")),
    ]
    step_list(steps)


def main():
    # 单独运行本文件(streamlit run frontend/xxx.py)时的完整流程
    st.set_page_config(
        page_title="足球数据分析与AI预测系统",
        page_icon=":material/sports_soccer:",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    apply_theme()
    global AUTH_USER
    AUTH_USER = login_gate()
    with st.sidebar:
        # 当前登录用户 + 退出(登录闸门已确保有 AUTH_USER)
        if _sidebar_user and AUTH_USER:
            _sidebar_user(AUTH_USER, admin_url=_ADMIN_URL)

        # 语言切换置于侧栏最顶部: session_state["lang"] 必须在本次运行内、任何 t()
        # 调用之前写入。若放在品牌区之后, 品牌标题会滞后一次交互才更新。
        _lang_selector()

        # 主题切换(深色/浅色): 与语言同放顶部, 因为它会重建整站 CSS
        theme_selector(t("主题"))

        brand_header(t("足球分析系统"), "Football Analytics", ":material/sports_soccer:")
        divider()

        # ---- 深链支持: ?page=players 之类可直接打开某一页 ----
        # 供侧边浏览器/外部入口使用(见 docs/system_viewer/index.html)。
        # 只在传入值与上次已应用的不同时写入 session_state,
        # 否则每轮都会把 radio 拉回深链页 -> 用户无法在页面内手动切换。
        _SLUGS = {
            "home": "首页概览", "leagues": "联赛数据", "teams": "球队分析",
            "players": "球员分析", "match": "比赛详情", "predict": "比赛预测",
            "agent": "AI智能分析", "live": "实时比分",
        }
        _OPS = list(_SLUGS.values())
        _qp = st.query_params.get("page")
        if isinstance(_qp, list):
            _qp = _qp[0] if _qp else None
        if _qp and _qp != st.session_state.get("_applied_qp"):
            _target = _SLUGS.get(_qp, _qp)
            if _target in _OPS:
                st.session_state["nav_page"] = _target
            st.session_state["_applied_qp"] = _qp

        # 内部值保持中文(下方 if page == "首页概览" 等分支依赖), 仅翻译显示。
        # key 必须显式给出: 无 key 时 radio 的元素 id 由参数(含 translate 后的选项)推导,
        # 切换语言会让 id 变化 -> 已提交的选中项被丢弃 -> 页面被重置回"首页概览"。
        # 分组标记(参照稿的分组导航): 只给主题 CSS 用 ::before 加「概览 / 数据 / 分析」组标题
        st.markdown('<div class="nav-groups-user"></div>', unsafe_allow_html=True)
        page = st.radio(t("导航"), [
            "首页概览",
            "联赛数据",
            "球队分析",
            "球员分析",
            "比赛详情",
            "比赛预测",
            "AI智能分析",
            "实时比分",
        ], format_func=lambda x: t(x), label_visibility="collapsed", key="nav_page")

        divider()

        # ---- 系统状态 ----
        section_cap(t("系统状态"), ":material/sensors:")
        _ok = backend_ok()
        status_list([
            (t("后端服务"), t("运行中") if _ok else t("未启动"), "ok" if _ok else "err"),
            (t("数据源"), "SQLite", "ok"),
            (t("数据库"), f"{DB_PATH.stat().st_size / 1024 / 1024:.0f} MB" if DB_PATH.exists() else "—",
             "ok" if DB_PATH.exists() else "err"),
        ])
        status_list([
            (t("比赛"), f"{num('SELECT COUNT(*) FROM matches'):,}", "off"),
            (t("球队"), f"{num('SELECT COUNT(*) FROM teams'):,}", "off"),
            (t("球员"), f"{num('SELECT COUNT(*) FROM players'):,}", "off"),
        ])

        divider()

        # ---- 系统管理入口 ----
        section_cap(t("系统管理"), ":material/build:")
        nav_link(ADMIN_URL, t("进入管理员后台"), ":material/settings:")

        app_footer(t("足球数据分析与AI预测系统 · 毕业设计"))


    # ============================================================
    # 首页概览
    # ============================================================
    if page == "首页概览":
        render_home()
    elif page == "联赛数据":
        render_leagues()
    elif page == "球队分析":
        render_teams()
    elif page == "球员分析":
        render_players()
    elif page == "比赛详情":
        render_match()
    elif page == "比赛预测":
        render_predict()
    elif page == "AI智能分析":
        render_agent()
    elif page == "实时比分":
        render_live()
    else:
        st.warning("未知页面: " + str(page))


if __name__ == "__main__":
    main()

