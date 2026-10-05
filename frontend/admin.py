"""
足球数据分析系统 - 管理员后台
功能：数据概览、数据浏览、API测试、数据库管理、数据更新、模型管理
运行：streamlit run frontend/admin.py --server.port 8502
"""
import streamlit as st
import sqlite3
import pandas as pd
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# 导入共享主题模块
sys.path.insert(0, str(Path(__file__).parent))
from theme import (
    apply_theme, card_metric, feature_card, status_box,
    nav_link, sidebar_footer, section_title, COLORS,
    page_header, section, section_cap, metric_row, empty_state, badge, code_chip, divider,
    status_list, status_row, brand_header, app_footer, info_card, chip_row, hero,
    theme_selector,
    T,
    API_BASE as THEME_API_BASE, FRONTEND_URL, ADMIN_URL
)
from i18n import t, lang, lang_selector, pos_zh, pos_group, pos_group_label

try:
    import blocks as BLK                             # 灵动版块(指标带/走马灯等)
except Exception:                                     # pragma: no cover
    class BLK:                                    # type: ignore
        @staticmethod
        def stat_band(*a, **k):
            pass

        @staticmethod
        def ticker(*a, **k):
            pass

        @staticmethod
        def hero_band(*a, **k):
            pass

        @staticmethod
        def bento_grid(*a, **k):
            pass

# ---------- 图表渲染层(统一由 viz.py 提供, 与前端共用) ----------
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

# 配置页面

# 路径配置
BASE_DIR = Path(__file__).parent.parent
DB_PATH = BASE_DIR / 'data' / 'database' / 'football.db'
ENV_PATH = BASE_DIR / '.env'
MODELS_DIR = BASE_DIR / 'models'
PROGRESS_PATH = BASE_DIR / 'data' / 'player_import_progress.json'
API_BASE = THEME_API_BASE

# 应用统一主题（与前端app.py完全一致）

# ---------- 登录闸门 ----------
# 管理后台只放管理员进来(role=admin); 普通用户会被提示换账号。
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


# 数据库连接
def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn

def get_table_count(table_name):
    try:
        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute(f"SELECT COUNT(*) FROM {table_name}")
        count = cur.fetchone()[0]
        conn.close()
        return count
    except:
        return 0

def get_table_columns(table_name):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute(f"PRAGMA table_info({table_name})")
    cols = [row[1] for row in cur.fetchall()]
    conn.close()
    return cols

# ---------- 展示工具(与前端 app.py 保持一致) ----------
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


def show_df(df, height=None, hide_index=True, **extra):
    """表格渲染(兼容 Streamlit 新旧 API); 列名与单元格值均经 i18n 词条翻译

    浅色主题下 st.dataframe 仍是深色网格(canvas 渲染, 跟随 Streamlit 自身主题,
    无法用 CSS 覆盖), 在浅色页面上会非常突兀 —— 此时改用跟随本设计系统 CSS 的
    st.table; 行数过多则截断并提示。
    """
    df = i18n_df(df)
    kw = {"hide_index": hide_index}
    if height:
        kw["height"] = height
    kw.update(extra)
    try:
        _light = st.session_state.get("ui_theme", "dark") == "light"
    except Exception:                                  # pragma: no cover
        _light = False
    if _light and len(df) <= 60:
        st.table(df if len(df) <= 25 else df.head(25))
        if len(df) > 25:
            st.caption(t("仅显示前 25 行（浅色主题下表格为静态渲染，可切换到深色主题查看完整数据）"))
        return
    try:
        st.dataframe(df, width="stretch", **kw)
    except TypeError:                                  # pragma: no cover
        st.dataframe(df, use_container_width=True, **kw)


def wide_button(label, key=None, type_=None):
    """整宽按钮(兼容 Streamlit 新旧 API)"""
    kw = {}
    if key:
        kw["key"] = key
    if type_:
        kw["type"] = type_
    try:
        return st.button(label, width="stretch", **kw)
    except TypeError:                                  # pragma: no cover
        return st.button(label, use_container_width=True, **kw)


def q_df(sql, params=()):
    """只读查询 -> DataFrame(失败返回空表, 不抛异常)。"""
    try:
        conn = get_db_connection()
        try:
            return pd.read_sql_query(sql, conn, params=params)
        finally:
            conn.close()
    except Exception:
        return pd.DataFrame()


def num(sql, params=(), default=0):
    """标量查询(取首行首列)。"""
    try:
        conn = get_db_connection()
        try:
            cur = conn.cursor()
            cur.execute(sql, params)
            row = cur.fetchone()
            return row[0] if row and row[0] is not None else default
        finally:
            conn.close()
    except Exception:
        return default


def load_json(name):
    """读取 models/ 下的 JSON 报告(不存在或损坏返回 None)。"""
    p = MODELS_DIR / name
    if not p.exists():
        return None
    try:
        with open(p, 'r', encoding='utf-8') as fh:
            return json.load(fh)
    except Exception:
        return None


# ---------- 比赛可视化浏览辅助 ----------

def get_leagues():
    """获取联赛中文名列表"""
    conn = get_db_connection()
    rows = [r[0] for r in conn.execute("SELECT name FROM leagues ORDER BY league_id")]
    conn.close()
    return rows

def league_id_map():
    """联赛名 -> league_id(按 league_id 排序, 覆盖数据库全部联赛)。

    旧实现硬编码五大联赛, 与数据库实际联赛数不一致; 这里改为数据驱动。
    """
    try:
        conn = get_db_connection()
        try:
            rows = conn.execute("SELECT league_id, name FROM leagues ORDER BY league_id").fetchall()
        finally:
            conn.close()
        return {r[1]: r[0] for r in rows}
    except Exception:
        return {}

def get_seasons():
    """获取数据库中的赛季列表(新→旧)"""
    conn = get_db_connection()
    rows = [r[0] for r in conn.execute("SELECT DISTINCT season FROM matches ORDER BY season DESC")]
    conn.close()
    return rows

MATCH_JOIN = """
    FROM matches m
    LEFT JOIN leagues l ON m.league_id = l.league_id
    LEFT JOIN teams th ON m.home_team_id = th.team_id
    LEFT JOIN teams ta ON m.away_team_id = ta.team_id
"""

def match_where(league, season, result, team, date_from="", date_to=""):
    """构造比赛筛选条件, 返回 (where_sql, params)"""
    conds, params = [], []
    if league and league != "全部":
        conds.append("l.name = ?"); params.append(league)
    if season and season != "全部":
        conds.append("m.season = ?"); params.append(season)
    if result == "主胜":
        conds.append("m.home_goals > m.away_goals")
    elif result == "平局":
        conds.append("m.home_goals = m.away_goals AND m.home_goals IS NOT NULL")
    elif result == "客胜":
        conds.append("m.home_goals < m.away_goals")
    elif result == "未开赛":
        conds.append("(m.status IS NULL OR m.status != 'FT')")
    if team:
        conds.append("(th.name LIKE ? OR ta.name LIKE ?)")
        params += [f"%{team}%", f"%{team}%"]
    if date_from:
        conds.append("date(m.date) >= date(?)"); params.append(date_from)
    if date_to:
        conds.append("date(m.date) <= date(?)"); params.append(date_to)
    where = " AND ".join(conds) if conds else "1=1"
    return where, params

# 侧边栏导航

# 登录后由 main() 写入(统一入口会直接把已登录用户赋给它)
AUTH_USER = {}


# ============ 页面渲染函数(统一入口 frontend/main.py 调用) ============


def render_overview():
    """数据概览"""
    # ---- 参照稿骨架(用户 m05889): 顶栏 → KPI 行 → 快捷操作 + 进度卡 → 大视区 + 通知列 ----
    if DASH:
        _n_leagues = get_table_count('leagues')
        _n_teams = get_table_count('teams')
        _n_matches = get_table_count('matches')
        _n_ft = int(num("SELECT COUNT(*) FROM matches WHERE status='FT'", default=0))
        _n_ns = int(num("SELECT COUNT(*) FROM matches WHERE status='NS'", default=0))
        _n_preds = get_table_count('predictions')
        _n_xgft = int(num("SELECT COUNT(*) FROM matches WHERE status='FT' AND home_xg IS NOT NULL", default=0))
        _n_noxg = int(num("SELECT COUNT(*) FROM matches WHERE status='FT' AND home_xg IS NULL", default=0))
        _n_players = get_table_count('players')
        _n_mv = int(num("SELECT COUNT(*) FROM players WHERE market_value IS NOT NULL", default=0))
        _n_transfers = get_table_count('transfers')
        _n_tm = int(num("SELECT COUNT(*) FROM tm_players", default=0))
        _n_tables = int(num("SELECT COUNT(*) FROM sqlite_master WHERE type='table'", default=0))
        _n_rows = 0
        _last_day = str(num("SELECT MAX(date(date)) FROM matches", default="—") or "—")
        _pct_xg = (_n_xgft / _n_ft * 100) if _n_ft else 0
        _pct_mv = (_n_mv / _n_players * 100) if _n_players else 0
        _pct_pred = (_n_preds / _n_matches * 100) if _n_matches else 0
        _db_mb = DB_PATH.stat().st_size / 1024 / 1024 if DB_PATH.exists() else 0
        _model_files2 = list(MODELS_DIR.glob('*.joblib')) if MODELS_DIR.exists() else []
        _notices = [
            {"title": t("完赛缺 xG"), "value": f"{_n_noxg:,} {t('场')} · Understat 待回填",
             "time": t("数据质量"), "tone": "warn"},
            {"title": t("球员缺身价"), "value": f"{_n_players - _n_mv:,} {t('名')} · Transfermarkt 未关联",
             "time": t("数据质量"), "tone": "warn"},
            {"title": t("数据库"), "value": f"{_db_mb:.1f} MB · {_n_tables} {t('张表')}",
             "time": "SQLite · football.db", "tone": "ok"},
            {"title": t("模型文件"), "value": f"{len(_model_files2)} {t('个')} · v1 / v2 / v7 / 集成",
             "time": t("models/"), "tone": "info"},
            {"title": t("最新比赛日"), "value": f"{_last_day} · {t('未来赛程')} {_n_ns:,} {t('场')}",
             "time": "matches.date", "tone": "info"},
        ]
        # 无壳模式(用户 m07431): 参照稿即整页, 系统自己的顶栏不再渲染(老导航走左下浮动抽屉)
        # ---- 中央三维场景两侧的真实统计(与用户端首页同一套版式) ----
        _lg_df = q_df("""SELECT l.name AS lg, COUNT(m.match_id) AS n
                         FROM leagues l LEFT JOIN matches m ON m.league_id = l.league_id
                         GROUP BY l.league_id ORDER BY 2 DESC""")
        _lg_rows = [(i18n_s(r.lg), f"{int(r.n):,}") for r in _lg_df.itertuples()][:4] \
            if not _lg_df.empty else []
        _rank_a = ([{"label": i18n_s(r.lg), "value": int(r.n)} for r in _lg_df.itertuples()][:8]
                   if not _lg_df.empty else [])
        _md = q_df("""SELECT substr(date,1,7) AS m, COUNT(*) AS n FROM matches
                      WHERE date IS NOT NULL GROUP BY m ORDER BY m DESC LIMIT 12""")
        _months_a = list(reversed(_md["m"].tolist())) if not _md.empty else []
        _counts_a = [int(v) for v in (reversed(_md["n"].tolist()) if not _md.empty else [])]
        _top4 = _rank_a[:4]
        _other = max(0, _n_matches - sum(s["value"] for s in _top4))
        _mx_a = max([s["value"] for s in _top4] or [1])
        # 参照图版式: 整版驾驶舱(与用户端首页同一套组件)
        _pct_pos_a = (int(num("SELECT COUNT(*) FROM players WHERE position IS NOT NULL", default=0))
                      / _n_players * 100) if _n_players else 0
        _pct_ns_a = (_n_ns / _n_matches * 100) if _n_matches else 0

        # ---------------- 把真数据灌进参照稿(与管理端/用户端同一套补丁层) ----------------
        _stg_a = q_df("""SELECT s.rank AS rk, tm.name AS nm, s.points AS pt
                         FROM standings s JOIN teams tm ON tm.team_id = s.team_id
                         WHERE s.season = (SELECT season FROM standings GROUP BY season
                                           ORDER BY COUNT(*) DESC LIMIT 1)
                           AND s.league_id = (SELECT league_id FROM standings GROUP BY league_id
                                              ORDER BY COUNT(*) DESC LIMIT 1)
                         ORDER BY s.rank LIMIT 5""")
        _srows_a = ([{"rank": int(r["rk"]), "name": i18n_s(str(r["nm"])),
                      "pct": int(round(100 * float(r["pt"]) / max(1.0, float(_stg_a["pt"].max())))),
                      "val": str(int(r["pt"]))} for _, r in _stg_a.iterrows()]
                    if not _stg_a.empty else [])
        _tb_a = q_df("SELECT name AS nm, n_rows AS n FROM (SELECT 'matches' AS name, COUNT(*) AS n_rows FROM matches)")
        _tabdf = q_df("""SELECT name AS nm, (SELECT COUNT(*) FROM sqlite_master m2
                                       WHERE m2.name = m.name) AS n FROM sqlite_master m
                         WHERE m.type='table' ORDER BY m.name LIMIT 5""")
        _modeldf = []
        try:
            _modeldf = [{"rank": i + 1, "name": p.name,
                         "pct": int(round(100 * p.stat().st_size / max(1, max(q.stat().st_size for q in _model_files2)))),
                         "val": f"{p.stat().st_size/1024/1024:.1f}MB"}
                        for i, p in enumerate(sorted(_model_files2, key=lambda x: -x.stat().st_size)[:5])]
        except Exception:
            _modeldf = []
        _recdf_a = q_df("""SELECT ht.name AS h, at.name AS a, m.home_goals AS hg,
                                  m.away_goals AS ag, m.status AS st
                           FROM matches m JOIN teams ht ON ht.team_id = m.home_team_id
                           JOIN teams at ON at.team_id = m.away_team_id
                           WHERE m.status IN ('FT','NS') AND m.home_goals IS NOT NULL
                           ORDER BY m.date DESC LIMIT 4""")
        _recrows_a = ([{"home": i18n_s(str(r["h"])), "away": i18n_s(str(r["a"])),
                        "score": f"{int(r['hg'])} : {int(r['ag'])}" if r["st"] == "FT" else "vs",
                        "status": t("已结束") if r["st"] == "FT" else t("未开始"),
                        "cls": "end" if r["st"] == "FT" else "soon"} for _, r in _recdf_a.iterrows()]
                      if not _recdf_a.empty else [])
        _hotdf_a = q_df("""SELECT tm.name AS nm, COUNT(*) AS n FROM matches m
                           JOIN teams tm ON tm.team_id = m.home_team_id
                           GROUP BY tm.name ORDER BY n DESC LIMIT 4""")
        _hotmax_a = float(_hotdf_a["n"].max()) if not _hotdf_a.empty else 1.0
        _hotrows_a = ([{"name": i18n_s(str(r["nm"])), "pct": int(round(100 * float(r["n"]) / _hotmax_a))}
                       for _, r in _hotdf_a.iterrows()] if not _hotdf_a.empty else [])

        _refdata_a = {
            "kpis": [
                {"tag": t("比赛数量"), "num": f"{_n_matches:,}",
                 "trend": f"{t('已完赛')} {_n_ft:,}"},
                {"tag": t("预测记录"), "num": f"{_n_preds:,}",
                 "trend": f"{t('覆盖')} {_pct_pred:.1f}% {t('赛事')}"},
                {"tag": t("球员 / 球队"), "num": f"{_n_players:,} / {_n_teams}" if False else f"{_n_players:,}",
                 "trend": f"{t('含身价')} {_n_mv:,}"},
                {"tag": t("数据库大小"), "num": f"{_db_mb:.1f} MB",
                 "trend": f"{_n_tables} {t('张表')} · SQLite", "plus": True},
            ],
            "focus": {
                "title": f"{t('库内赛事分布')} · football-data.org + Understat",
                "odds": [
                    {"k": t("联赛"), "v": f"{len(_lg_df)}", "s": t("已接入")},
                    {"k": t("比赛"), "v": f"{_n_matches:,}", "s": t("全部赛季")},
                    {"k": t("转会记录"), "v": f"{_n_transfers:,}", "s": "Transfermarkt"},
                ],
                "ring": round(_pct_pred, 1),
                "mini": [
                    {"k": t("已完赛"), "v": f"{_n_ft:,}"},
                    {"k": t("未来赛程"), "v": f"{_n_ns:,}"},
                    {"k": t("历史预测"), "v": f"{_n_preds:,}"},
                    {"k": t("模型文件"), "v": f"{len(_model_files2)} {t('个')}"},
                    {"k": t("数据库"), "v": f"{_db_mb:.1f} MB"},
                ],
            },
            "bars": [
                {"label": t("官方 xG 覆盖"), "pct": round(_pct_xg, 1)},
                {"label": t("球员身价覆盖"), "pct": round(_pct_mv, 1)},
                {"label": t("赛事预测覆盖"), "pct": round(_pct_pred, 1)},
                {"label": t("位置数据覆盖"), "pct": round(_pct_pos_a, 1)},
            ],
            "right": {
                "slim": {"label": f"{t('数据库')} · {_db_mb:.1f} MB", "pct": round(_pct_pred, 1)},
                "stats": [
                    {"icon": "📄", "pct": f"{_pct_xg:.1f}%"},
                    {"icon": "💰", "pct": f"{_pct_mv:.1f}%"},
                    {"icon": "🤖", "pct": f"{_pct_pred:.1f}%"},
                    {"icon": "🕐", "pct": f"{_pct_pos_a:.1f}%"},
                ],
                "todo": {"title": t("数据完整度"), "link": t("质量与资产") + " ›",
                         "items": [{"tone": "y" if n["tone"] == "warn" else "g",
                                    "text": f"{n['title']} · {n['value']}"} for n in _notices]},
            },
            "foot": [f"{t('数据更新时间')}: {_last_day} · SQLite · football.db",
                     f"{_n_matches:,} {t('场比赛')} · {_n_tables} {t('张表')} · {len(_model_files2)} {t('个模型文件')}"],
            "panels": {
                "standings": {"title": t("联赛积分榜"), "rows": _srows_a},
                "scorers": {"title": t("模型文件 Top 5"), "rows": _modeldf},
                "recent": {"title": t("近期比赛"), "rows": _recrows_a},
                "ai": {"title": t("数据更新控制"),
                       "big": f"{t('最近刷新')} · {_last_day}", "bigPct": f"{_pct_pred:.1f}%",
                       "tags": [f"{t('比赛')} {_n_matches:,}", f"{t('球队')} {_n_teams}",
                                f"{t('球员')} {_n_players:,}"],
                       "tip": f"{t('数据源')} football-data.org / Understat / Transfermarkt · "
                              f"{_n_tables} {t('张表')} · {_n_rows if _n_rows else _db_mb:.1f} MB"},
                "hot": {"title": t("球队比赛量 Top 4"), "rows": _hotrows_a},
            },
        }
        _refuser_a = {"name": (AUTH_USER or {}).get("display_name") or (AUTH_USER or {}).get("username") or "",
                      "role": (AUTH_USER or {}).get("role_label") or "管理员",
                      "lang": st.session_state.get("lang", "中文"),
                      "theme": _theme_key(), "notices": _notices, "guest": False}
        REF.render(theme=_theme_key(), height=1000, slug="overview", data=_refdata_a,
                   admin=True, user=_refuser_a)
        return                                  # 参照稿即整页, 不再往下渲染旧版式
    page_header(t("数据概览"), t("系统各模块数据量与运行状态总览"),
                icon=":material/bar_chart:", meta=t("数据源：SQLite · football.db"))

    # 数据量: 改用"指标带"(分隔线版式)而非 8 张彩色卡片 —— 更紧凑、更少卡片堆叠,
    # 且与用户端首页保持同一套版式语言(taste-skill §4.4: 高密度页面禁用卡片堆叠)
    _players_count = get_table_count('players')
    _model_files = list(MODELS_DIR.glob('*.joblib')) if MODELS_DIR.exists() else []
    _db_size = DB_PATH.stat().st_size / 1024 / 1024 if DB_PATH.exists() else 0
    BLK.stat_band([
        (f"{get_table_count('leagues'):,}", t("联赛数量"), t("含 5 大联赛 + 5 项杯赛/次级联赛")),
        (f"{get_table_count('teams'):,}", t("球队数量"), t("已完成重复合并")),
        (f"{get_table_count('matches'):,}", t("比赛数量"), t("已完赛 + 未来赛程")),
        (f"{_players_count:,}", t("球员数量"), t("含身价 / 国籍 / 伤病")),
    ])
    BLK.stat_band([
        (f"{get_table_count('transfers'):,}", t("转会记录"), t("Transfermarkt 层")),
        (f"{get_table_count('predictions'):,}", t("预测记录"), t("含样本外回测")),
        (f"{len(_model_files)}", t("模型文件"), t("v1 / v2 / v7 / 集成")),
        (f"{_db_size:.1f} MB", t("数据库大小"), "SQLite · football.db"),
    ])

    divider()

    # 数据分布可视化
    section(t("数据分布"), t("核心数据表规模 · 比赛数据时间分布"), icon=":material/trending_up:")
    dc1, dc2 = st.columns([3, 2])
    with dc1:
        tb = pd.DataFrame({
            t("数据表"): [t("比赛记录"), t("球员档案"), t("球队"), t("预测记录"),
                          t("身价记录"), t("伤病记录"), t("转会记录")],
            t("行数"): [get_table_count(x) for x in
                        ("matches", "players", "teams", "predictions",
                         "tm_player_market_value", "tm_player_injuries", "transfers")],
        })
        tb = tb[tb[t("行数")] > 0]
        if tb.empty:
            empty_state(":material/bar_chart:", t("暂无数据"), t("请先导入数据"),
                        command="python scripts/import_data.py")
        else:
            VIZ.show(VIZ.rank_bar(tb, t("数据表"), t("行数"), fmt=",.0f", gradient=True,
                                  title=t("核心数据表规模"), height=300),
                     key="admin_tables", fallback=tb)
    with dc2:
        mm = q_df("""SELECT strftime('%Y-%m', date) AS "月份", COUNT(*) AS "场次"
                     FROM matches WHERE date IS NOT NULL
                     GROUP BY 1 ORDER BY 1""")
        mm = mm.tail(24)
        if mm.empty:
            empty_state(":material/calendar_month:", t("暂无比赛时间数据"), t("请先导入比赛数据"),
                        command="python scripts/import_data.py")
        else:
            mm_chart = i18n_df(mm)
            VIZ.show(VIZ.line(mm_chart, t("月份"), t("场次"), area=True, fmt=",.0f", x_type="T",
                              title=t("比赛数据月度分布"), height=300),
                     key="admin_matches_month", fallback=mm_chart)

    divider()

    # 系统状态
    section(t("系统状态"), icon=":material/sensors:")
    col_a, col_b, col_c = st.columns(3)

    with col_a:
        st.markdown(f"**{t('后端API状态')}**")
        _api_state, _api_text = "warn", t("未启动")
        try:
            import requests
            # 注意: API_BASE 是 ".../api", 而 /docs 挂在根路径下,
            # 旧代码写成 f"{API_BASE}/docs" 会得到 .../api/docs -> 404 -> 误报"异常"。
            _root = API_BASE.replace("/api", "")
            resp = requests.get(f"{_root}/docs", timeout=3)
            if resp.status_code == 200:
                _api_state, _api_text = "ok", t("运行中")
            else:
                _api_state, _api_text = "err", t("异常")
        except Exception:
            pass
        status_row(t("服务"), _api_text, _api_state)
        if _api_state == "ok":
            st.markdown(f"{t('地址')}: `{API_BASE}`")
        else:
            code_chip("python -m uvicorn src.main:app --port 8000")

    with col_b:
        st.markdown(f"**{t('球员数据导入状态')}**")
        if PROGRESS_PATH.exists():
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            completed = len(prog.get('completed_teams', []))
            total_players = prog.get('total_players', 0)
            status_row(t("已完成球队"), f"{completed} / 138", "ok")
            status_row(t("已导入球员"), f"{total_players:,}", "ok")
            if prog.get('last_update'):
                st.markdown(f"{t('最后更新')}: {prog['last_update'][:19]}")
        else:
            status_row(t("导入进度"), t("未开始"), "warn")
            st.markdown(t("需配置 API-Football key 后运行导入"))

    with col_c:
        st.markdown(f"**{t('API Key 配置状态')}**")
        api_key = ''
        if ENV_PATH.exists():
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('API_FOOTBALL_KEY='):
                        api_key = line.split('=', 1)[1].strip()
        if api_key:
            status_row(t("API-Football Key"), t("已配置"), "ok")
            st.markdown(f"`{api_key[:8]}...{api_key[-4:]}`")
        else:
            status_row(t("API-Football Key"), t("未配置"), "err")
            st.markdown(t("球员数据和实时比分需要 API-Football key"))

    divider()

    # 数据完整性检查
    section(t("数据完整性检查"), icon=":material/science:")
    issues = []
    if get_table_count('players') == 0:
        issues.append(t("球员表为空，需导入球员数据"))
    if get_table_count('matches') == 0:
        issues.append(t("比赛表为空，需导入比赛数据"))
    if get_table_count('teams') < 100:
        issues.append(t("球队数量较少({n})，五大联赛应有约100+支").replace(
            "{n}", str(get_table_count('teams'))))

    if issues:
        for issue in issues:
            st.markdown(f'<div class="warn-box">{issue}</div>', unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="success-box">{t("所有核心数据表均有数据，系统数据完整")}</div>',
                    unsafe_allow_html=True)

# ==================== 页面2: 数据浏览 ====================

def render_browse():
    """数据浏览"""
    page_header(t("数据浏览"), t("按主题浏览系统全部数据：预测 / 比赛 / 球队 / 复盘 / 身价 …"),
                icon=":material/checklist:", meta=t("10 个数据主题"))
    tab_today, tab_matches, tab_players, tab_review, tab_standings, tab_tm, tab_squad, tab_cover, tab_pre, tab_tables = st.tabs(
        [t("今日预测"), t("比赛数据"), t("球员与球队"), t("预测复盘"),
         t("积分榜"), t("TM 身价与转会"), t("阵容·事件·伤停"),
         t("数据完整度"), t("赛前分析"), t("通用表浏览")])

    # ---------- Tab 0: 今日预测 ----------
    with tab_today:
        page_header(t("今日预测", "Today's Predictions"),
                    t("未来 3 天比赛的 XGBoost 预测（v2+v7 集成模型 · 90+ 维特征）"),
                    icon=":material/online_prediction:",
                    meta=t("数据源：本地预测表 predictions"))
        conn = get_db_connection()
        rows = conn.execute("""
            SELECT m.date, l.name lg, th.name h, ta.name a,
                   p.pred_result, p.pred_home_win, p.pred_draw, p.pred_away_win,
                   p.model_version
            FROM matches m
            JOIN leagues l ON l.league_id = m.league_id
            JOIN teams th ON th.team_id = m.home_team_id
            JOIN teams ta ON ta.team_id = m.away_team_id
            LEFT JOIN predictions p ON p.match_id = m.match_id
            WHERE m.status='NS' AND date(m.date) <= date('now', '+3 day')
              AND m.league_id IN (1,2,3,4,5)
            ORDER BY m.date""").fetchall()
        conn.close()
        HEAD = {"H": "主胜", "D": "平局", "A": "客胜"}
        if not rows:
            empty_state(":material/inbox:", t("未来 3 天暂无五大联赛比赛"),
                        t("赛程同步后，这里会自动列出未来比赛及其预测结果"))
        else:
            n_pred = sum(1 for r in rows if r["pred_result"])
            metric_row([
                {"value": f"{len(rows)}", "label": t("未来3天比赛"), "icon": ":material/calendar_month:",
                 "color": T["accent"]},
                {"value": f"{n_pred}", "label": t("已生成预测"), "icon": ":material/online_prediction:",
                 "color": T["accent"]},
            ])
            data = []
            for r in rows:
                conf = ""
                if r["pred_result"]:
                    p = {"H": r["pred_home_win"], "D": r["pred_draw"],
                         "A": r["pred_away_win"]}[r["pred_result"]]
                    conf = f"{p:.0%}"
                data.append({
                    "时间": r["date"][:16], "联赛": r["lg"],
                    "对阵": f"{r['h']} vs {r['a']}",
                    # 内部编码(H/D/A)先映射中文再经 t() 译成当前语言
                    "预测": t(HEAD.get(r["pred_result"], "未预测")),
                    "置信度": conf,
                    "主胜": f"{r['pred_home_win']:.0%}" if r["pred_home_win"] is not None else "—",
                    "平局": f"{r['pred_draw']:.0%}" if r["pred_draw"] is not None else "—",
                    "客胜": f"{r['pred_away_win']:.0%}" if r["pred_away_win"] is not None else "—",
                    "模型": r["model_version"] or "—",
                })
            show_df(pd.DataFrame(data), height=480)

            divider()
            tc1, tc2 = st.columns([2, 3])
            with tc1:
                oc = {}
                for r in rows:
                    # 映射后再经 t(): 英文态环形图的分类标签不能残留中文
                    key = t(HEAD.get(r["pred_result"], "未预测"))
                    oc[key] = oc.get(key, 0) + 1
                oc_df = pd.DataFrame({t("预测结果"): list(oc.keys()),
                                      t("场次"): list(oc.values())})
                VIZ.show(VIZ.donut(oc_df, t("预测结果"), t("场次"),
                                   colors=[T["accent"], T["gold"], T["blue"], T["t3"]],
                                   title=t("未来 3 天预测结果构成"), fmt=",.0f",
                                   height=300),
                         key="adm_today_donut", fallback=oc_df)
            with tc2:
                cf = [(f"{r['h']} vs {r['a']}",
                       {"H": r["pred_home_win"], "D": r["pred_draw"],
                        "A": r["pred_away_win"]}.get(r["pred_result"]))
                      for r in rows if r["pred_result"]]
                cf = [(nm, v) for nm, v in cf if v is not None]
                if not cf:
                    empty_state(":material/online_prediction:", t("暂无预测置信度"),
                                t("运行预测脚本后可查看置信度分布"),
                                command="python scripts/train_v7.py")
                else:
                    cf_df = pd.DataFrame({t("对阵"): [nm for nm, _ in cf],
                                          t("置信度"): [float(v) * 100
                                                     for _, v in cf]})
                    cf_df = cf_df.nlargest(12, t("置信度"))
                    VIZ.show(VIZ.rank_bar(cf_df, t("对阵"), t("置信度"), top=12,
                                          fmt=",.1f", gradient=True,
                                          title=t("预测置信度 Top 12 (%)"), height=300),
                             key="adm_today_conf", fallback=cf_df)

    # ---------- Tab A: 比赛数据（可视化浏览） ----------
    with tab_matches:
        page_header(t("比赛数据", "Matches"),
                    t("按 联赛 / 赛季 / 赛果 / 球队 / 日期 筛选，顶部为整组筛选的实时统计"),
                    icon=":material/calendar_month:",
                    meta=t("数据源：Football-Data · Understat"))
        leagues = get_leagues()
        seasons = get_seasons()

        c1, c2, c3, c4 = st.columns([2, 2, 2, 3])
        with c1:
            # 选项值保持中文(match_where 依赖), 仅翻译显示
            sel_league = st.selectbox(t("联赛"), ["全部"] + leagues,
                                     format_func=lambda x: t(x), key="m_league")
        with c2:
            sel_season = st.selectbox(t("赛季"), ["全部"] + seasons,
                                     format_func=lambda x: t(x), key="m_season")
        with c3:
            sel_result = st.selectbox(t("赛果"), ["全部", "主胜", "平局", "客胜", "未开赛"],
                                     format_func=lambda x: t(x), key="m_result")
        with c4:
            sel_team = st.text_input(
                t("球队"), placeholder=t("输入队名, 如 Man City（留空=全部）"), key="m_team")

        c5, c6, c7 = st.columns([2, 2, 1.4])
        with c5:
            date_from = st.text_input(
                t("开始日期"), placeholder=t("YYYY-MM-DD, 留空不限"), key="m_from")
        with c6:
            date_to = st.text_input(
                t("结束日期"), placeholder=t("YYYY-MM-DD, 留空不限"), key="m_to")
        with c7:
            page_size = st.selectbox(t("每页显示"), [20, 50, 100], index=1, key="m_size")

        where, params = match_where(
            sel_league, sel_season, sel_result, sel_team.strip(),
            date_from.strip(), date_to.strip())

        conn = get_db_connection()

        # 汇总统计（按整组筛选，不受分页影响）
        stats_sql = f"""SELECT
                COUNT(*) AS total,
                SUM(CASE WHEN m.home_goals > m.away_goals THEN 1 ELSE 0 END) AS h,
                SUM(CASE WHEN m.home_goals = m.away_goals AND m.home_goals IS NOT NULL THEN 1 ELSE 0 END) AS d,
                SUM(CASE WHEN m.home_goals < m.away_goals THEN 1 ELSE 0 END) AS a,
                SUM(CASE WHEN m.home_xg IS NOT NULL AND m.away_xg IS NOT NULL THEN 1 ELSE 0 END) AS xg_cnt
                {MATCH_JOIN} WHERE {where}"""
        s = conn.execute(stats_sql, params).fetchone()
        total, h, d, a, xg_cnt = int(s[0] or 0), int(s[1] or 0), int(s[2] or 0), int(s[3] or 0), int(s[4] or 0)
        finished = h + d + a
        pct = lambda x: f"{x / finished:.1%}" if finished else "-"

        metric_row([
            {"value": f"{total:,}", "label": t("筛选场次"), "icon": ":material/folder:", "color": T["accent"]},
            {"value": f"{h} · {pct(h)}", "label": t("主胜"), "icon": ":material/home:", "color": T["accent"]},
            {"value": f"{d} · {pct(d)}", "label": t("平局"), "icon": ":material/handshake:", "color": T["accent"]},
            {"value": f"{a} · {pct(a)}", "label": t("客胜"), "icon": ":material/flight:", "color": T["accent"]},
            {"value": f"{xg_cnt} / {total}", "label": t("含xG场次"), "icon": ":material/trending_up:", "color": T["accent"]},
        ])

        mc1, mc2 = st.columns([2, 3])
        with mc1:
            oc_df = pd.DataFrame({
                t("赛果"): [t("主胜"), t("平局"), t("客胜")],
                t("场次"): [h, d, a],
            })
            if int(oc_df[t("场次")].sum()) > 0:
                VIZ.show(VIZ.donut(oc_df, t("赛果"), t("场次"),
                                   colors=[T["accent"], T["gold"], T["blue"]],
                                   title=t("筛选范围赛果构成"), fmt=",.0f",
                                   center=f"{finished:,}"),
                         key="adm_match_donut", fallback=oc_df)
        with mc2:
            sc_sql = f"""SELECT CAST(m.home_goals AS TEXT) || '-' ||
                                CAST(m.away_goals AS TEXT) AS "比分",
                                COUNT(*) AS "场次"
                         {MATCH_JOIN}
                         WHERE {where} AND m.home_goals IS NOT NULL
                         GROUP BY 1 ORDER BY 2 DESC LIMIT 12"""
            try:
                conn_sc = get_db_connection()
                try:
                    sc_df = pd.read_sql_query(sc_sql, conn_sc, params=params)
                finally:
                    conn_sc.close()
            except Exception:
                sc_df = pd.DataFrame()
            if sc_df.empty:
                empty_state(":material/sports_soccer:", t("暂无比分数据"), t("当前筛选条件下没有已完赛比赛"))
            else:
                sc_chart = i18n_df(sc_df)
                VIZ.show(VIZ.bar(sc_chart, t("比分"), t("场次"), fmt=",.0f", label=True,
                                 color=T["accent"],
                                 title=t("常见比分 Top 12"), height=300),
                         key="adm_match_score", fallback=sc_chart)
        divider()

        # 分页控件
        total_pages = max(1, (total + page_size - 1) // page_size)
        pc1, pc2 = st.columns([1, 4])
        with pc1:
            page_num = st.number_input(t("页码"), min_value=1, max_value=total_pages, value=1, key="m_page")
        with pc2:
            section_cap(f'{t("共")} <b>{total}</b> {t("场")} · {total_pages} {t("页")} · '
                        f'{t("每页")} {page_size} {t("场")}', ":material/description:")
        offset = (page_num - 1) * page_size

        # 数据查询（按页）
        sel_sql = f"""SELECT date(m.date) AS 日期, l.name AS 联赛, m.season AS 赛季,
                th.name AS 主队, ta.name AS 客队,
                m.home_goals AS 主进球, m.away_goals AS 客进球,
                m.ht_home AS 主半场, m.ht_away AS 客半场,
                m.home_shots AS 主射门, m.away_shots AS 客射门,
                m.home_sot AS 主射正, m.away_sot AS 客射正,
                m.home_corners AS 主角球, m.away_corners AS 客角球,
                m.home_xg AS 主xG, m.away_xg AS 客xG,
                m.referee AS 裁判, m.venue AS 场地, m.status AS 状态
                {MATCH_JOIN} WHERE {where} ORDER BY m.date DESC LIMIT ? OFFSET ?"""
        df = pd.read_sql_query(sel_sql, conn, params=params + [page_size, offset])
        conn.close()

        if df.empty:
            empty_state(":material/search:", t("没有符合筛选条件的比赛"), t("试试放宽联赛或时间范围等筛选条件"))
        else:
            def fmt_score(r):
                if pd.notna(r["主进球"]) and pd.notna(r["客进球"]):
                    return f"{int(r['主进球'])} - {int(r['客进球'])}"
                return "—"

            def fmt_result(r):
                if r["状态"] != "FT" or pd.isna(r["主进球"]):
                    return t("未开赛")
                hg, ag = int(r["主进球"]), int(r["客进球"])
                # 文案经 t(): 该列同时用于页面表格与 CSV 导出
                return t("主胜") if hg > ag else (t("平局") if hg == ag else t("客胜"))

            def fmt_xg(r):
                if pd.notna(r["主xG"]) and pd.notna(r["客xG"]):
                    return f"{r['主xG']:.2f} - {r['客xG']:.2f}"
                return "—"

            def fmt_pair(h, a):
                if pd.notna(h) and pd.notna(a):
                    return f"{int(h)} - {int(a)}"
                return "—"

            df["比分"] = df.apply(fmt_score, axis=1)
            df["赛果"] = df.apply(fmt_result, axis=1)
            df["射门"] = df.apply(lambda r: fmt_pair(r["主射门"], r["客射门"]), axis=1)
            df["射正"] = df.apply(lambda r: fmt_pair(r["主射正"], r["客射正"]), axis=1)
            df["角球"] = df.apply(lambda r: fmt_pair(r["主角球"], r["客角球"]), axis=1)
            df["半场"] = df.apply(lambda r: fmt_pair(r["主半场"], r["客半场"]), axis=1)
            df["xG"] = df.apply(fmt_xg, axis=1)
            show = df[["日期", "联赛", "赛季", "主队", "客队", "比分", "半场",
                       "赛果", "射门", "射正", "角球", "xG", "裁判", "场地", "状态"]]
            show_df(show, height=440)
            st.caption(t("第 {p} / {n} 页（当前页 {c} 场）").format(
                p=page_num, n=total_pages, c=len(df)))

            # 导出当前筛选（全部，不分页）
            if st.button(t("导出当前筛选全部比赛 (CSV)"), key="m_export"):
                conn = get_db_connection()
                full_sql = f"""SELECT date(m.date) AS 日期, l.name AS 联赛, m.season AS 赛季,
                        th.name AS 主队, ta.name AS 客队,
                        m.home_goals AS 主进球, m.away_goals AS 客进球,
                        m.home_xg AS 主xG, m.away_xg AS 客xG, m.status AS 状态
                        {MATCH_JOIN} WHERE {where} ORDER BY m.date DESC"""
                full = pd.read_sql_query(full_sql, conn, params=params)
                conn.close()
                full["比分"] = full.apply(fmt_score, axis=1)
                full["赛果"] = full.apply(fmt_result, axis=1)
                st.download_button(t("下载 CSV"), full.to_csv(index=False).encode("utf-8-sig"),
                                   f"matches_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                                   "text/csv", key="m_download")

    # ---------- Tab C: 积分榜 ----------
    with tab_standings:
        section(t("五大联赛积分榜"), t("数据源 Football-Data.org · 当前赛季"), icon=":material/emoji_events:")
        conn = get_db_connection()
        season_rows = [r[0] for r in conn.execute(
            "SELECT DISTINCT season FROM standings ORDER BY season DESC")]
        conn.close()
        if not season_rows:
            empty_state(":material/emoji_events:", t("暂无积分榜数据"),
                        t("请先运行同步，或在「数据更新控制」点击同步"),
                        command="python scripts/sync_standings.py")
        else:
            lg_map = league_id_map() or {"英超": 1, "西甲": 2, "德甲": 3, "意甲": 4, "法甲": 5}
            sel_league = st.selectbox(t("联赛"), list(lg_map.keys()),
                                     format_func=lambda x: t(x), key="st_league")
            sel_season = st.selectbox(t("赛季"), season_rows, index=0, key="st_season")
            lid = lg_map.get(sel_league, 1)
            conn = get_db_connection()
            rows = conn.execute("""
                SELECT s.rank, t.name, s.played, s.won, s.draw, s.lost,
                       s.goals_for, s.goals_against, s.goal_diff, s.points, s.form
                FROM standings s JOIN teams t ON t.team_id = s.team_id
                WHERE s.league_id = ? AND s.season = ? ORDER BY s.rank""",
                (lid, sel_season)).fetchall()
            conn.close()
            if not rows:
                empty_state(":material/bar_chart:", t("该联赛暂无积分榜数据"))
            else:
                df = pd.DataFrame([dict(r) for r in rows])
                df = df.rename(columns={
                    "rank": "排名", "name": "球队", "played": "场次", "won": "胜",
                    "draw": "平", "lost": "负", "goals_for": "进球",
                    "goals_against": "失球", "goal_diff": "净胜球",
                    "points": "积分", "form": "近5场"})
                df["近5场"] = df["近5场"].fillna("—")
                show_df(df, height=600)
                st.caption(f"{t('共')} {len(rows)} {t('行')} · {t('数据截至最近一次同步')}")

                st1, st2 = st.columns([3, 2])
                with st1:
                    df_chart = i18n_df(df)
                    VIZ.show(VIZ.scatter(df_chart, t("进球"), t("失球"), size=t("积分"),
                                         fmt_x=",.0f", fmt_y=",.0f",
                                         tooltip=VIZ.tip((t("球队"), "N"), (t("进球"), "Q"),
                                                         (t("失球"), "Q"), (t("积分"), "Q")),
                                         title=t("进攻 / 防守分布 (气泡大小 = 积分)"),
                                         height=340),
                             key="adm_st_scatter", fallback=df_chart)
                with st2:
                    gd = df[["球队", "净胜球"]].copy()
                    gd["净胜球"] = pd.to_numeric(gd["净胜球"], errors="coerce")
                    gd = gd.dropna(subset=["净胜球"])
                    if gd.empty:
                        empty_state(":material/bar_chart:", t("暂无净胜球数据"), t("该赛季积分榜缺少净胜球字段"))
                    else:
                        gd_chart = i18n_df(gd)
                        VIZ.show(VIZ.rank_bar(gd_chart, t("球队"), t("净胜球"), fmt=",.0f",
                                              gradient=True,
                                              title=t("球队净胜球排名"), height=340),
                                 key="adm_st_gd", fallback=gd_chart)

    # ---------- Tab E: 球员与球队 ----------
    with tab_players:
        section(t("球队档案与阵容"), t("数据源：球小策 / TheSportsDB / Transfermarkt"), icon=":material/group:")
        lg_map_p = league_id_map() or {"英超": 1, "西甲": 2, "德甲": 3, "意甲": 4, "法甲": 5}
        pc1, pc2 = st.columns([2, 3])
        with pc1:
            sel_lg = st.selectbox(t("联赛"), list(lg_map_p.keys()),
                                 format_func=lambda x: t(x), key="pl_league")
        with pc2:
            conn = get_db_connection()
            teams = [r["name"] for r in conn.execute("""
                SELECT DISTINCT t.name FROM standings s
                JOIN teams t ON t.team_id = s.team_id
                WHERE s.season='2627' AND s.league_id=?
                ORDER BY t.name""", (lg_map_p[sel_lg],))]
            conn.close()
            sel_team = st.selectbox(t("球队"), teams, key="pl_team")

        conn = get_db_connection()
        info = conn.execute("""
            SELECT t.name, t.name_en, t.logo_url, t.stadium, t.capacity, t.founded,
                   t.manager, t.team_id, l.name AS league
            FROM teams t JOIN leagues l ON l.league_id = t.league_id
            WHERE t.name = ? LIMIT 1""", (sel_team,)).fetchone()
        squad = conn.execute("""
            SELECT p.name, p.position, p.number, p.age, p.nationality, p.photo_url,
                   p.height, p.weight, p.foot, p.market_value
            FROM players p JOIN teams t ON t.team_id = p.team_id
            WHERE t.name = ? ORDER BY
                CASE p.position WHEN 'Goalkeeper' THEN 0 WHEN 'Defender' THEN 1
                     WHEN 'Midfielder' THEN 2 WHEN 'Attacker' THEN 3 ELSE 4 END,
                p.number""", (sel_team,)).fetchall()
        # 该队 TM 层阵容身价 + 伤病(有数据即展示, 无则占位)
        tm_val = None
        try:
            tm_val = conn.execute("""
                SELECT SUM(v.value) AS total FROM tm_club_map m
                JOIN tm_player_seasons s ON s.team_id = m.club_id
                JOIN tm_players p ON p.player_id = s.player_id
                JOIN tm_player_market_value v ON v.player_id = p.player_id
                WHERE m.team_id = ? AND v.value_date = (
                    SELECT MAX(value_date) FROM tm_player_market_value x
                    WHERE x.player_id = v.player_id)
                  AND s.season_start = (SELECT MAX(season_start) FROM tm_player_seasons y
                                        WHERE y.team_id = m.club_id)""",
                (info["team_id"] if info else -1,)).fetchone()
        except Exception:
            tm_val = None
        conn.close()

        if info:
            ic1, ic2 = st.columns([1, 3])
            with ic1:
                if info["logo_url"]:
                    st.image(info["logo_url"], width=110)
            with ic2:
                _lines = [
                    f"{t('英文名')}: {info['name_en'] or '-'}",
                    f"{t('主教练')}: {info['manager'] or t('待补（API-Football）')}",
                    f"{t('主场')}: {info['stadium'] or '-'}（{t('容量')} {info['capacity'] or '-'}）",
                    f"{t('成立')}: {info['founded'] or '-'} · {t('阵容')}: {len(squad)} {t('名球员')}",
                ]
                if tm_val and tm_val["total"]:
                    _lines.append(f"{t('TM 阵容总身价')}: {float(tm_val['total'])/1e6:.0f}M€")
                info_card(f"{info['name']} · {info['league']}", _lines, icon=":material/shield:",
                          color=T["accent"])

        if squad:
            sq = pd.DataFrame([dict(r) for r in squad]).rename(columns={
                "name": "球员", "position": "位置", "number": "号码",
                "age": "年龄", "nationality": "国籍", "photo_url": "照片",
                "height": "身高", "weight": "体重", "foot": "惯用脚",
                "market_value": "身价(€)"})
            # 位置大组(语言无关)先算好, 再换成显示名: 明细表保留粒度, 环形图按 4 组收敛
            sq["_grp"] = sq["位置"].map(pos_group)
            sq["位置"] = sq["位置"].map(pos_zh)
            show_df(
                sq[["号码", "球员", "位置", "年龄", "国籍", "身高", "体重",
                    "惯用脚", "身价(€)", "照片"]],
                height=520,
                column_config={
                    "照片": st.column_config.ImageColumn("照片", width="small")
                },
            )

            divider()
            ps1, ps2 = st.columns([2, 3])
            with ps1:
                pos_cnt = sq["_grp"].value_counts()
                pos_df = pd.DataFrame({t("位置"): [pos_group_label(k) for k in pos_cnt.index],
                                       t("人数"): [int(v) for v in pos_cnt.values]})
                VIZ.show(VIZ.donut(pos_df, t("位置"), t("人数"),
                                   colors=[T["gold"], T["blue"], T["purple"],
                                           T["accent"], T["t3"]],
                                   title=t("阵容位置构成"), fmt=",.0f", height=300),
                         key="adm_pl_pos", fallback=pos_df)
            with ps2:
                vv = sq[["球员", "身价(€)"]].copy()
                vv["身价(€)"] = pd.to_numeric(vv["身价(€)"], errors="coerce")
                vv = vv.dropna(subset=["身价(€)"])
                vv = vv[vv["身价(€)"] > 0].nlargest(10, "身价(€)")
                if vv.empty:
                    empty_state(":material/payments:", t("暂无身价数据"), t("该球队球员身价尚未导入"))
                else:
                    vv_chart = i18n_df(vv)
                    VIZ.show(VIZ.rank_bar(vv_chart, t("球员"), t("身价(€)"), top=10, fmt=",.0f",
                                          gradient=True,
                                          title=t("阵容身价 Top 10"), height=300),
                             key="adm_pl_val", fallback=vv_chart)
        else:
            empty_state(":material/group:", t("该队暂无球员数据"), t("可在「数据更新控制」导入阵容数据"))

        # 全库概览
        conn = get_db_connection()
        n_pl = conn.execute("SELECT COUNT(*) FROM players").fetchone()[0]
        n_tm = conn.execute("SELECT COUNT(DISTINCT team_id) FROM players").fetchone()[0]
        # 联动积分榜: 该队当前排名
        st_tbl = conn.execute("""
            SELECT s.rank, s.played, s.won, s.draw, s.lost, s.goals_for,
                   s.goals_against, s.goal_diff, s.points, s.form
            FROM standings s JOIN teams t ON t.team_id = s.team_id
            WHERE t.name = ? AND s.season = '2627' LIMIT 1""", (sel_team,)).fetchone()
        conn.close()
        if st_tbl:
            section(t("本赛季排名（2627）"), icon=":material/bar_chart:")
            metric_row([
                {"value": f"{st_tbl['rank']}", "label": t("排名"), "icon": ":material/military_tech:", "color": T["accent"]},
                {"value": f"{st_tbl['points']}", "label": t("积分"), "icon": ":material/star:", "color": T["accent"]},
                {"value": f"{st_tbl['won']}-{st_tbl['draw']}-{st_tbl['lost']}", "label": t("胜-平-负"), "icon": ":material/checklist:", "color": T["accent"]},
                {"value": f"{st_tbl['goals_for']}:{st_tbl['goals_against']}",
                 "label": f"{t('进:失')} ({t('净')}{st_tbl['goal_diff']:+d})", "icon": ":material/sports_soccer:", "color": T["accent"]},
            ])
            if st_tbl["form"]:
                st.caption(f"{t('近 5 场')}: {st_tbl['form']}")
        divider()
        st.caption(f"{t('数据库共')} {n_pl} {t('名球员，覆盖')} {n_tm} {t('支球队')}")

    # ---------- Tab D: 预测复盘 ----------
    with tab_review:
        section(t("预测复盘"), t("XGBoost 预测 vs 实际赛果 —— 命中率复盘（赛后自动回填）"), icon=":material/target:")
        sys.path.insert(0, str(BASE_DIR))
        try:
            from src.prediction.prediction_service import (backfill_results,
                                                           review_stats)
            if st.button(t("回填赛果并刷新复盘"), key="rv_refresh"):
                info = backfill_results()
                st.success(t("已回填 {n} 条预测的实际赛果").format(n=info["backfilled"]))
            s = review_stats()
            if s["total"] == 0:
                empty_state(":material/target:", t("暂无已结算预测"),
                            t("可先运行预测脚本生成预测，或做历史回测"),
                            command="python scripts/predict_upcoming.py")
            else:
                metric_row([
                    {"value": f"{s['total']:,}", "label": t("已结算预测"), "icon": ":material/folder:", "color": T["accent"]},
                    {"value": f"{s['hit']:,}", "label": t("命中"), "icon": ":material/check_circle:", "color": T["accent"]},
                    {"value": f"{s['hit_rate']:.1%}" if s["hit_rate"] is not None else "-",
                     "label": t("命中率"), "icon": ":material/target:", "color": T["accent"]},
                    {"value": f"{s['pending']:,}", "label": t("待结算(未开赛)"), "icon": ":material/hourglass_top:", "color": T["accent"]},
                ])
                HEAD = {"H": "主胜", "D": "平局", "A": "客胜"}
                colA, colB = st.columns(2)
                with colA:
                    section_cap(t("分联赛命中率"), ":material/emoji_events:")
                    lg_df = pd.DataFrame(s["by_league"])
                    if not lg_df.empty:
                        lg_df["命中率"] = (lg_df["hit"] / lg_df["n"]).map(lambda x: f"{x:.1%}")
                        lg_df = lg_df.rename(columns={"league": "联赛", "n": "场次", "hit": "命中"})
                        show_df(lg_df[["联赛", "场次", "命中", "命中率"]])
                        lg_ch = lg_df.dropna(subset=["联赛"]).copy()
                        lg_ch["命中率%"] = (pd.to_numeric(lg_ch["命中"], errors="coerce")
                                          / pd.to_numeric(lg_ch["场次"], errors="coerce") * 100)
                        lg_ch = lg_ch.dropna(subset=["命中率%"])
                        if not lg_ch.empty:
                            lg_ch_chart = i18n_df(lg_ch)
                            VIZ.show(VIZ.rank_bar(lg_ch_chart, t("联赛"), t("命中率%"), fmt=",.1f",
                                                  gradient=True,
                                                  title=t("分联赛命中率 (%)"), height=300),
                                     key="adm_rv_lg", fallback=lg_ch_chart)
                with colB:
                    section_cap(t("分预测类型"), ":material/numbers:")
                    pr_df = pd.DataFrame(s["by_pred"])
                    if not pr_df.empty:
                        # 内部编码(H/D/A)先映射中文再经 t() 译成当前语言
                        pr_df["类型"] = pr_df["pred"].map(lambda x: t(HEAD.get(x, x)))
                        pr_df["命中率"] = (pr_df["hit"] / pr_df["n"]).map(lambda x: f"{x:.1%}")
                        pr_df = pr_df.rename(columns={"n": "场次", "hit": "命中"})
                        show_df(pr_df[["类型", "场次", "命中", "命中率"]])
                        pr_ch = pr_df.copy()
                        pr_ch["场次"] = pd.to_numeric(pr_ch["场次"], errors="coerce")
                        pr_ch = pr_ch.dropna(subset=["场次"])
                        if not pr_ch.empty:
                            pr_ch_chart = i18n_df(pr_ch)
                            VIZ.show(VIZ.bar(pr_ch_chart, t("类型"), t("场次"), fmt=",.0f", label=True,
                                             color=T["accent"],
                                             title=t("分预测类型分布"), height=300),
                                     key="adm_rv_pred", fallback=pr_ch_chart)

                hit_df = pd.DataFrame({
                    t("结果"): [t("命中"), t("未命中"), t("待结算")],
                    t("场次"): [int(s["hit"] or 0),
                               int(max((s["total"] or 0) - (s["hit"] or 0), 0)),
                               int(s["pending"] or 0)],
                })
                if int(hit_df[t("场次")].sum()) > 0:
                    VIZ.show(VIZ.donut(hit_df, t("结果"), t("场次"),
                                       colors=[T["accent"], T["red"], T["t3"]],
                                       title=t("预测命中构成"), fmt=",.0f",
                                       height=300),
                             key="adm_rv_donut", fallback=hit_df)

                section_cap(t("最近结算明细"), ":material/receipt_long:")
                rc = pd.DataFrame(s["recent"])
                if not rc.empty:
                    # 内部编码(H/D/A)先映射中文再经 t() 译成当前语言
                    rc["预测"] = rc["pred_result"].map(lambda x: t(HEAD.get(x, x)))
                    rc["实际"] = rc["actual_result"].map(lambda x: t(HEAD.get(x, x)))
                    rc["比分"] = rc["home_goals"].astype(str) + "-" + rc["away_goals"].astype(str)
                    rc["命中"] = rc["hit"].map(lambda x: "✓" if x else "✗")
                    rc["日期"] = rc["date"].str[:10]
                    rc["对阵"] = rc["home"] + " vs " + rc["away"]
                    show_df(rc[["日期", "league", "对阵", "比分", "预测", "实际", "命中"]]
                            .rename(columns={"league": "联赛"}),
                            height=420)
        except Exception as e:
            st.markdown(f'<div class="warn-box">{t("复盘模块不可用")}: {e}</div>',
                        unsafe_allow_html=True)

    # ---------- Tab G: TM 身价与转会 ----------
    with tab_tm:
        section(t("Transfermarkt 数据"),
                t("球队阵容身价 · 球员市值曲线 · 转会记录 · 伤病记录"), icon=":material/euro:")
        conn = get_db_connection()
        try:
            clubs = conn.execute("""
                SELECT m.club_id, COALESCE(t.name, m.tm_name) AS team_name, m.tm_name,
                       (SELECT MAX(season_start) FROM tm_player_seasons s WHERE s.team_id = m.club_id) AS latest
                FROM tm_club_map m LEFT JOIN teams t ON t.team_id = m.team_id
                ORDER BY team_name""").fetchall()
        except Exception:
            clubs = []
        if not clubs:
            empty_state(":material/euro:", t("暂无 Transfermarkt 数据"),
                        t("请先运行数据导入脚本"),
                        command="python scripts/import_tm_dataset.py")
        else:
            # 值用行号(语言无关), 显示名交给 format_func -> 切语言不会丢已选球队
            labels = {i: f"{c['team_name']}  ({c['tm_name']})" for i, c in enumerate(clubs)}
            sel_i = st.selectbox(t("选择球队", "Select team"), list(labels),
                                 format_func=lambda i: labels[i], key="tm_club")
            club = clubs[sel_i]
            cid, latest = club["club_id"], club["latest"]
            sq = conn.execute("""
                SELECT p.player_id, p.player_name, p.citizenship, p.height, p.position,
                       p.foot, p.date_of_birth,
                       (SELECT value FROM tm_player_market_value v WHERE v.player_id=p.player_id
                        ORDER BY date_unix DESC LIMIT 1) AS mv,
                       (SELECT value_date FROM tm_player_market_value v WHERE v.player_id=p.player_id
                        ORDER BY date_unix DESC LIMIT 1) AS mv_date,
                       (SELECT SUM(goals) FROM tm_player_seasons g WHERE g.player_id=p.player_id
                        AND g.team_id=?) AS goals,
                       (SELECT SUM(assists) FROM tm_player_seasons g WHERE g.player_id=p.player_id
                        AND g.team_id=?) AS assists
                FROM tm_players p
                JOIN tm_player_seasons s ON s.player_id = p.player_id
                WHERE s.team_id = ? AND s.season_start = ?
                GROUP BY p.player_id ORDER BY mv DESC""", (cid, cid, cid, latest)).fetchall()
            conn.close()

            if not sq:
                empty_state(":material/checklist:", t("该球队暂无阵容数据"))
            else:
                total_mv = sum(float(r["mv"]) for r in sq if r["mv"])
                metric_row([
                    {"value": f"{len(sq)}", "label": t("阵容人数"), "icon": ":material/group:", "color": T["accent"]},
                    {"value": f"{total_mv/1e6:.0f}M€", "label": t("阵容总身价"), "icon": ":material/payments:", "color": T["accent"]},
                    {"value": f"{latest}/{str(latest+1)[2:]}", "label": t("数据赛季"), "icon": ":material/calendar_month:", "color": T["accent"]},
                ])

                df = pd.DataFrame([{
                    t("球员"): r["player_name"],
                    t("位置"): r["position"],
                    t("国籍"): r["citizenship"],
                    t("年龄"): (2026 - int(str(r["date_of_birth"])[:4]))
                              if r["date_of_birth"] and str(r["date_of_birth"])[:4].isdigit() else None,
                    t("身高"): r["height"],
                    t("惯用脚"): r["foot"],
                    t("身价"): round(float(r["mv"]) / 1e6, 1) if r["mv"] else None,
                    t("进球"): r["goals"], "Assists": r["assists"],
                } for r in sq])
                show_df(df, height=380)

                # 球员详情: 市值曲线 / 伤病 / 转会
                pnames = [r["player_name"] for r in sq]
                psel = st.selectbox(t("查看球员详情", "Player detail"), pnames, key="tm_player")
                pid = next(r["player_id"] for r in sq if r["player_name"] == psel)
                c2 = get_db_connection()
                mv = pd.read_sql_query("""
                    SELECT value_date AS date, ROUND(value/1e6, 2) AS value_million_eur
                    FROM tm_player_market_value WHERE player_id=? ORDER BY date_unix""",
                    c2, params=(pid,))
                inj = pd.read_sql_query("""
                    SELECT injury_reason, from_date, end_date, days_missed, games_missed
                    FROM tm_player_injuries WHERE player_id=? ORDER BY from_date DESC LIMIT 15""",
                    c2, params=(pid,))
                tr = pd.read_sql_query("""
                    SELECT transfer_date, from_team_name, to_team_name, transfer_type,
                           transfer_fee FROM tm_transfers WHERE player_id=?
                    ORDER BY transfer_date DESC LIMIT 15""", c2, params=(pid,))
                c2.close()

                cc1, cc2 = st.columns([3, 2])
                with cc1:
                    section_cap(f"{t('市值曲线')} ({t('单位：百万欧')})", ":material/trending_up:")
                    if mv.empty:
                        st.caption(t("暂无市值记录"))
                    else:
                        VIZ.show(VIZ.line(mv, "date", "value_million_eur", area=True,
                                          point=True, fmt=",.2f", x_type="T",
                                          height=280),
                                 key="adm_mv", fallback=mv, fallback_kind="line")
                with cc2:
                    section_cap(t("伤病记录"), ":material/medical_services:")
                    if inj.empty:
                        st.caption(t("暂无伤病记录"))
                    else:
                        show_df(inj.rename(columns={
                            "injury_reason": t("伤病"),
                            "from_date": t("开始"),
                            "end_date": t("结束"),
                            "days_missed": t("缺席天数"),
                            "games_missed": t("缺席场次")}),
                            height=260)
                section_cap(t("转会记录"), ":material/repeat:")
                if tr.empty:
                    st.caption(t("暂无转会记录"))
                else:
                    show_df(tr.rename(columns={
                        "transfer_date": t("日期"),
                        "from_team_name": t("原球队"),
                        "to_team_name": t("新球队"),
                        "transfer_type": t("类型"),
                        "transfer_fee": t("费用")}),
                        height=260)

    # ---------- Tab H: 阵容·事件·伤停 ----------
    with tab_squad:
        page_header(t("阵容 · 事件 · 伤停", "Lineups · Events · Injuries"),
                    t("比赛级明细：首发阵容 · 事件时间轴 · 伤停名单 · 裁判",
                      "Match-level detail: lineups · event timeline · injuries · referee"),
                    icon=":material/extension:",
                    meta=t("数据来源：API-Football", "Source: API-Football"))
        conn = get_db_connection()

        def _count(sql, default=0):
            try:
                return conn.execute(sql).fetchone()[0] or 0
            except Exception:
                return default

        n_ref = _count("SELECT COUNT(*) FROM matches WHERE referee IS NOT NULL AND referee!=''")
        n_venue = _count("SELECT COUNT(*) FROM matches WHERE venue IS NOT NULL AND venue!=''")
        n_lu = _count("SELECT COUNT(DISTINCT fixture_id) FROM af_lineups")
        n_ev = _count("SELECT COUNT(DISTINCT fixture_id) FROM af_events")
        n_inj = _count("SELECT COUNT(*) FROM af_injuries")
        n_tm_inj = _count("SELECT COUNT(*) FROM tm_player_injuries")

        metric_row([
            {"value": f"{n_ref:,}", "label": t("有裁判的比赛", "With referee"), "icon": ":material/gavel:",
             "hint": t("待填充", "pending") if not n_ref else "", "color": T["accent"]},
            {"value": f"{n_venue:,}", "label": t("有场地的比赛", "With venue"), "icon": ":material/stadium:",
             "hint": t("待填充", "pending") if not n_venue else "", "color": T["accent"]},
            {"value": f"{n_lu:,}", "label": t("有阵容的比赛", "With lineups"), "icon": ":material/group:",
             "hint": t("待填充", "pending") if not n_lu else "", "color": T["accent"]},
            {"value": f"{n_ev:,}", "label": t("有事件的比赛", "With events"), "icon": ":material/bolt:",
             "hint": t("待填充", "pending") if not n_ev else "", "color": T["accent"]},
            {"value": f"{n_inj:,}", "label": t("伤停记录", "Injury records"), "icon": ":material/medical_services:",
             "hint": t(f"TM 层另有 {n_tm_inj:,} 条", f"TM layer: {n_tm_inj:,}"),
             "color": T["red"]},
        ])

        if not (n_lu or n_ev or n_ref):
            empty_state(
                ":material/extension:",
                t("框架已就绪，等待数据填充", "Framework ready, waiting for data"),
                t("数据来源：<b>API-Football Pro</b>（裁判随赛程返回，阵容/事件按场抓取）。"
                  "填充后本页自动展示阵容与事件时间轴。",
                  "Source: <b>API-Football Pro</b> (referee comes with fixtures; "
                  "lineups/events are per-match). This page will populate automatically."),
                command="python scripts/import_af_backfill.py --phase fixtures|lineups|events")
        else:
            # 有数据：按比赛查看阵容/事件
            fx = conn.execute("""
                SELECT DISTINCT m.match_id, date(m.date) d, th.name h, ta.name a,
                       m.af_fixture_id
                FROM matches m JOIN teams th ON th.team_id=m.home_team_id
                JOIN teams ta ON ta.team_id=m.away_team_id
                WHERE m.af_fixture_id IN (SELECT DISTINCT fixture_id FROM af_lineups
                                          UNION SELECT DISTINCT fixture_id FROM af_events)
                ORDER BY m.date DESC LIMIT 300""").fetchall()
            if fx:
                opts = [f"{r['d']} {r['h']} vs {r['a']}" for r in fx]
                pick = st.selectbox(t("选择比赛", "Select match"), opts, key="sq_match")
                fid = fx[opts.index(pick)]["af_fixture_id"]
                lu = pd.read_sql_query("""SELECT team_name, formation, player_name, number, pos,
                                                 grid FROM af_lineups WHERE fixture_id=?
                                          ORDER BY team_name, number""", conn, params=(fid,))
                ev = pd.read_sql_query("""SELECT minute, team_name, player_name, type, detail,
                                                 assist_name FROM af_events WHERE fixture_id=?
                                          ORDER BY minute""", conn, params=(fid,))
                lu["pos"] = lu["pos"].map(pos_zh)   # 位置列: 中文态中文, 英文态原文
                lc, rc = st.columns(2)
                if not lu.empty:
                    for col, team in zip((lc, rc), lu["team_name"].unique()[:2]):
                        with col:
                            section_cap(f"{team} — {t('阵容')}", ":material/apparel:")
                            show_df(lu[lu["team_name"] == team][
                                ["number", "player_name", "pos", "formation"]],
                                height=380)
                if not ev.empty:
                    section_cap(t("事件时间轴"), ":material/bolt:")
                    show_df(ev, height=300)
                if not lu.empty or not ev.empty:
                    divider()
                    sq1, sq2 = st.columns([2, 3])
                    with sq1:
                        if not lu.empty:
                            pcnt = lu["pos"].fillna("—").value_counts()
                            p_df = pd.DataFrame(
                                {t("位置"): [str(k) for k in pcnt.index],
                                 t("人数"): [int(v) for v in pcnt.values]})
                            VIZ.show(VIZ.donut(p_df, t("位置"), t("人数"),
                                               colors=[T["gold"], T["blue"],
                                                       T["purple"], T["accent"],
                                                       T["t3"]],
                                               title=t("首发位置构成"), fmt=",.0f",
                                               height=300),
                                     key="adm_sq_pos", fallback=p_df)
                    with sq2:
                        if not ev.empty:
                            ecnt = ev["type"].fillna("—").value_counts().head(12)
                            e_df = pd.DataFrame(
                                {t("事件类型"): [str(k) for k in ecnt.index],
                                 t("次数"): [int(v) for v in ecnt.values]})
                            VIZ.show(VIZ.bar(e_df, t("事件类型"), t("次数"), fmt=",.0f",
                                             label=True, rotate=-15,
                                             color=T["accent"],
                                             title=t("比赛事件类型分布"), height=300),
                                     key="adm_sq_ev", fallback=e_df)
        conn.close()

    # ---------- Tab I: 数据完整度 ----------
    with tab_cover:
        page_header(t("数据完整度", "Data Completeness"),
                    t("一眼看清哪些数据已齐、哪些待补（填数据后本面板自动更新）",
                      "What is complete, what is pending (updates automatically)"),
                    icon=":material/trending_up:")
        conn = get_db_connection()

        def _one(sql):
            try:
                return conn.execute(sql).fetchone()[0] or 0
            except Exception:
                return 0

        rows_spec = [
            (t("比赛", "Matches"), "matches", None),
            (t("· 射门类统计", "· shots/corners/cards"), "matches", "home_shots IS NOT NULL"),
            (t("· 半场比分", "· half-time score"), "matches", "ht_home IS NOT NULL"),
            (t("· 官方 xG", "· official xG"), "matches", "home_xg IS NOT NULL"),
            (t("· 代理 xG", "· proxy xG"), "matches", "home_xg_proxy IS NOT NULL"),
            (t("· 裁判", "· referee"), "matches", "referee IS NOT NULL AND referee!=''"),
            (t("· 场地", "· venue"), "matches", "venue IS NOT NULL AND venue!=''"),
            (t("球队", "Teams"), "teams", None),
            (t("· 队徽", "· logo"), "teams", "logo_url IS NOT NULL AND logo_url!=''"),
            (t("· 球场/容量", "· stadium/capacity"), "teams", "stadium IS NOT NULL AND stadium!=''"),
            (t("· 主教练", "· manager"), "teams", "manager IS NOT NULL AND manager!=''"),
            (t("球员", "Players"), "players", None),
            (t("· 位置/年龄", "· position/age"), "players", "position IS NOT NULL AND position!=''"),
            (t("· 国籍", "· nationality"), "players", "nationality IS NOT NULL AND nationality!=''"),
            (t("· 身高/体重", "· height/weight"), "players", "height IS NOT NULL"),
            (t("· 身价", "· market value"), "players", "market_value IS NOT NULL"),
            (t("转会", "Transfers"), "transfers", None),
            (t("积分榜", "Standings"), "standings", None),
            (t("TM 球员档案", "TM player profiles"), "tm_players", None),
            (t("TM 市值历史", "TM market values"), "tm_player_market_value", None),
            (t("TM 伤病", "TM injuries"), "tm_player_injuries", None),
            (t("比赛阵容(待补)", "Lineups (pending)"), "af_lineups", None),
            (t("比赛事件(待补)", "Events (pending)"), "af_events", None),
            (t("伤停(待补)", "Injuries (pending)"), "af_injuries", None),
        ]
        base_m = _one("SELECT COUNT(*) FROM matches")
        rows = []
        for label, tbl, cond in rows_spec:
            n = _one(f"SELECT COUNT(*) FROM {tbl}" + (f" WHERE {cond}" if cond else ""))
            if cond:
                pct = f"{n/max(base_m,1):.0%}" if tbl == "matches" else "—"
            else:
                pct = "100%" if n else "0%"
            rows.append({t("数据集", "Dataset"): label, t("行数", "Rows"): f"{n:,}",
                         t("覆盖率", "Coverage"): pct,
                         t("状态", "Status"): t("完整", "Ready") if n else t("待填充", "Pending")})
        conn.close()
        show_df(pd.DataFrame(rows), height=620)

        cover_df = pd.DataFrame([
            {t("数据集", "Dataset"): r[t("数据集", "Dataset")],
             t("覆盖率", "Coverage"): float(str(r[t("覆盖率", "Coverage")]).rstrip('%'))}
            for r in rows if str(r[t("覆盖率", "Coverage")]).endswith('%')
        ])
        cover_df = cover_df[cover_df[t("覆盖率", "Coverage")] > 0]
        if not cover_df.empty:
            VIZ.show(VIZ.rank_bar(cover_df, t("数据集", "Dataset"),
                                  t("覆盖率", "Coverage"), top=12, fmt=",.0f",
                                  gradient=True,
                                  title=t("关键数据集覆盖率 (%)", "Key dataset coverage (%)"),
                                  height=380),
                     key="adm_cover", fallback=cover_df)
            st.caption(t("覆盖率 = 该数据集相对比赛总数的填充比例",
                         "Coverage = filled ratio relative to total matches"))

        st.markdown('<div class="info-box">'
                    + t("待填充 = 框架已就绪，填写数据后本面板自动更新。",
                        "Pending = framework ready. This panel updates automatically "
                        "once data is loaded.")
                    + '</div>', unsafe_allow_html=True)

    # ---------- Tab F: 赛前分析（球小策赛前全景包） ----------
    with tab_pre:
        section(t("赛前分析"), t("球小策赛前全景包：预测首发 / 伤停影响 / 战术指纹 / 交锋 / 赛程负荷"), icon=":material/online_prediction:")
        conn = get_db_connection()
        try:
            packs = conn.execute("""
                SELECT p.match_id, p.kickoff, p.payload, th.name h, ta.name a, l.name lg
                FROM qxz_match_pack p JOIN matches m ON m.match_id = p.match_id
                JOIN teams th ON th.team_id = m.home_team_id
                JOIN teams ta ON ta.team_id = m.away_team_id
                JOIN leagues l ON l.league_id = m.league_id
                ORDER BY p.kickoff""").fetchall()
        except Exception:
            packs = []
        preds = {r["match_id"]: dict(r) for r in conn.execute(
            "SELECT match_id, pred_result, pred_home_win, pred_draw, pred_away_win "
            "FROM predictions")}
        conn.close()

        if not packs:
            empty_state(":material/online_prediction:", t("暂无赛前包数据"),
                        t("可在比赛前 24–36 小时内运行数据导入脚本"),
                        command="python scripts/import_paid_qxz.py matchpacks --max-hours-ahead 36")
        else:
            HEAD2 = {"H": "主胜", "D": "平局", "A": "客胜"}
            n_full = 0
            for pk in packs:
                try:
                    d = json.loads(pk["payload"])
                except Exception:
                    continue
                meta = d.get("meta") or {}
                is_full = bool(meta.get("is_full_pack"))
                n_full += is_full
                pack = d.get("pack") or {}
                pr = preds.get(pk["match_id"]) or {}
                tag = t("完整包") if is_full else t("基础快照(未到生成窗口)")
                with st.expander(f"{pk['kickoff'][:16]}  {pk['lg']} | {pk['h']} vs {pk['a']}  —  {tag}"):
                    if pr:
                        st.markdown(
                            t("**模型预测**：{r}（主 {h} / 平 {d} / 客 {a}）").format(
                                r=t(HEAD2.get(pr["pred_result"], "-")),
                                h=f"{pr['pred_home_win']:.0%}",
                                d=f"{pr['pred_draw']:.0%}",
                                a=f"{pr['pred_away_win']:.0%}"))
                    # 通用提取: 兼容不同快照/完整包结构
                    def _show(dct, title):
                        if isinstance(dct, dict) and dct:
                            st.markdown(f"**{title}**")
                            flat = {k: v for k, v in dct.items()
                                    if isinstance(v, (str, int, float, bool)) or v is None}
                            if flat:
                                st.markdown("　".join(f"`{k}`: {v}" for k, v in flat.items()))
                            for k, v in dct.items():
                                if isinstance(v, dict):
                                    _show(v, f"{title} · {k}")
                                elif isinstance(v, list) and v and isinstance(v[0], dict):
                                    st.markdown(f"**{title} · {k}** " + t("（共 {n} 项）").format(n=len(v)))
                                    show_df(pd.DataFrame(v[:10]))
                    for key in ("home_form", "away_form", "predicted_lineups", "lineups",
                                "injury_impact", "injuries", "tactical", "tactics",
                                "h2h", "strength", "strengths", "schedule", "fatigue",
                                "coach", "coaches", "market_value", "values", "summary"):
                        if key in pack:
                            _show(pack[key], key)
                    with st.expander(t("原始 JSON")):
                        st.json(d)
            st.markdown(t("共 **{a}** 场赛前包，其中完整包 **{b}** 场").format(
                a=len(packs), b=n_full))

            divider()
            pc1, pc2 = st.columns([2, 3])
            with pc1:
                pk_df = pd.DataFrame({
                    t("包类型"): [t("完整包"), t("基础快照")],
                    t("场次"): [int(n_full), int(max(len(packs) - n_full, 0))],
                })
                VIZ.show(VIZ.donut(pk_df, t("包类型"), t("场次"),
                                   colors=[T["accent"], T["t3"]],
                                   title=t("赛前包完整度构成"), fmt=",.0f",
                                   height=300),
                         key="adm_pre_donut", fallback=pk_df)
            with pc2:
                lg_cnt = {}
                for pk in packs:
                    lg_cnt[pk["lg"]] = lg_cnt.get(pk["lg"], 0) + 1
                lg_df = pd.DataFrame({t("联赛"): list(lg_cnt.keys()),
                                      t("场次"): list(lg_cnt.values())})
                VIZ.show(VIZ.rank_bar(lg_df, t("联赛"), t("场次"), top=12, fmt=",.0f",
                                      gradient=True,
                                      title=t("赛前包联赛分布"), height=300),
                         key="adm_pre_lg", fallback=lg_df)

    # ---------- Tab B: 通用表浏览 ----------
    with tab_tables:
        section(t("通用表浏览"), t("查看数据库各表数据，支持搜索和分页"), icon=":material/database:")

        tables = ['leagues', 'teams', 'players', 'matches', 'transfers', 'predictions']
        table_labels = {
            'leagues': '联赛表',
            'teams': '球队表',
            'players': '球员表',
            'matches': '比赛表',
            'transfers': '转会表',
            'predictions': '预测表'
        }

        selected_table = st.selectbox(t("选择数据表"), tables,
                                      format_func=lambda x: t(table_labels[x]), key="g_table")
        count = get_table_count(selected_table)
        st.caption(f"{t('共')} {count} {t('条记录')}")

        if count == 0:
            empty_state(":material/database:", t("该表暂无数据"), t("请先在「数据更新控制」页面导入数据"))
        else:
            # 搜索
            cols = get_table_columns(selected_table)
            search_col = st.selectbox(t("搜索字段"), ["无"] + cols,
                                      format_func=lambda x: t(x), key="g_searchcol")
            search_val = st.text_input(t("搜索值"), "", key="g_searchval") \
                if search_col != "无" else ""

            # 分页
            page_size_g = st.selectbox(t("每页显示"), [20, 50, 100], index=0, key="g_size")
            total_pages_g = (count + page_size_g - 1) // page_size_g
            page_num_g = st.number_input(t("页码"), min_value=1, max_value=total_pages_g,
                                         value=1, key="g_page")

            # 查询
            conn = get_db_connection()
            offset = (page_num_g - 1) * page_size_g

            if search_col != '无' and search_val:
                query = f"SELECT * FROM {selected_table} WHERE {search_col} LIKE ? LIMIT ? OFFSET ?"
                df_g = pd.read_sql_query(query, conn, params=(f'%{search_val}%', page_size_g, offset))
            else:
                query = f"SELECT * FROM {selected_table} LIMIT ? OFFSET ?"
                df_g = pd.read_sql_query(query, conn, params=(page_size_g, offset))

            conn.close()

            # 显示
            show_df(df_g, height=500)
            st.caption(f"{t('第')} {page_num_g}/{total_pages_g} {t('页')}")

            # 数值字段分布
            num_cols = [c for c in df_g.columns
                        if pd.api.types.is_numeric_dtype(df_g[c])
                        and df_g[c].notna().sum() >= 2]
            if num_cols:
                divider()
                hv1, hv2 = st.columns([1, 3])
                with hv1:
                    pick_col = st.selectbox(t("数值字段分布"), num_cols,
                                            key="g_histcol")
                with hv2:
                    h_df = df_g[[pick_col]].dropna()
                    h_df = h_df.rename(columns={pick_col: t("数值")})
                    VIZ.show(VIZ.histogram(h_df, t("数值"), bins=20,
                                           color=T["accent"],
                                           title=f"{pick_col} · {t('分布')}",
                                           height=280),
                             key="adm_tbl_hist", fallback=h_df)

            # 导出
            if st.button(t("导出当前页为CSV"), key="g_export"):
                csv_data = df_g.to_csv(index=False)
                st.download_button(t("下载CSV"), csv_data,
                                   f"{selected_table}_page{page_num_g}.csv",
                                   "text/csv", key="g_download")

# ==================== 页面3: API接口测试 ====================

def render_api():
    """API接口测试"""
    page_header(t("API 接口测试"), t("测试后端 FastAPI 接口，查看返回数据"),
                icon=":material/electrical_services:", meta=f"{API_BASE}")

    # 检查API状态(与"数据概览"一致: /docs 在根路径, 不在 /api 下)
    try:
        import requests
        resp = requests.get(f"{API_BASE.replace('/api', '')}/docs", timeout=3)
        api_online = resp.status_code == 200
    except Exception:
        api_online = False

    if not api_online:
        empty_state(":material/electrical_services:", t("后端 API 未启动"),
                    t("请先运行后端服务：python -m uvicorn src.main:app --port 8000"),
                    command="python -m uvicorn src.main:app --port 8000")
    else:
        st.markdown(f'<div class="success-box">{t("后端API运行中")}</div>',
                    unsafe_allow_html=True)

        endpoints = {
            "GET /api/leagues": ("获取联赛列表", "/api/leagues", {}),
            "GET /api/teams": ("搜索球队", "/api/teams", {"q": "搜索关键词"}),
            "GET /api/teams/{id}": ("球队详情", "/api/teams/1", {}),
            "GET /api/matches": ("比赛列表", "/api/matches", {"league": "英超", "limit": 10}),
            "POST /api/predict": ("比赛预测", "/api/predict", {"home_team": "Man City", "away_team": "Arsenal"}),
            "GET /api/players": ("球员列表", "/api/players", {"team_id": 1, "limit": 10}),
            "GET /api/stats/overview": ("数据概览统计", "/api/stats/overview", {}),
        }

        # key 必须显式给出: label 与 format_func 输出均随语言变化, 无 key 时
        # 控件元素 id 会随语言改变 -> 切换语言后已选接口被丢弃。
        selected = st.selectbox(t("选择接口"), list(endpoints.keys()),
                                format_func=lambda x: f"{x} - {t(endpoints[x][0])}",
                                key="api_endpoint")
        _, endpoint, default_params = endpoints[selected]

        # 参数输入
        section_cap(t("请求参数"), ":material/receipt_long:")
        params = {}
        for key, default_val in default_params.items():
            params[key] = st.text_input(key, value=str(default_val))

        # 发送请求
        if st.button(t("发送请求"), type="primary"):
            try:
                url = f"{API_BASE}{endpoint}"
                if selected.startswith("POST"):
                    resp = requests.post(url, json=params, timeout=10)
                else:
                    resp = requests.get(url, params={k: v for k, v in params.items() if v}, timeout=10)

                status_list([
                    (t("状态码"), f"{resp.status_code}",
                     "ok" if resp.status_code < 400 else "err"),
                    (t("响应时间"), f"{resp.elapsed.total_seconds():.3f}s", "off"),
                ])

                try:
                    data = resp.json()
                    section_cap(t("响应数据"), ":material/inventory_2:")
                    st.json(data)
                    recs = None
                    if isinstance(data, list) and data and isinstance(data[0], dict):
                        recs = pd.DataFrame(data)
                    elif isinstance(data, dict):
                        for _v in data.values():
                            if isinstance(_v, list) and _v and isinstance(_v[0], dict):
                                recs = pd.DataFrame(_v)
                                break
                    if recs is not None and not recs.empty:
                        num_cols = [c for c in recs.columns
                                    if pd.api.types.is_numeric_dtype(recs[c])
                                    and recs[c].notna().sum() >= 2]
                        divider()
                        if num_cols:
                            av1, av2 = st.columns([1, 3])
                            with av1:
                                acol = st.selectbox(t("数值字段分布"), num_cols,
                                                    key="api_histcol")
                            with av2:
                                a_df = recs[[acol]].dropna().rename(
                                    columns={acol: t("数值")})
                                VIZ.show(VIZ.histogram(a_df, t("数值"), bins=20,
                                                       color=T["accent"],
                                                       title=f"{acol} · {t('分布')}",
                                                       height=280),
                                         key="adm_api_hist", fallback=a_df)
                        else:
                            show_df(recs, height=360)
                except:
                    st.text(resp.text[:2000])
            except Exception as e:
                st.error(f"{t('请求失败')}: {e}")

# ==================== 页面4: 数据库管理 ====================

def render_database():
    """数据库管理"""
    page_header(t("数据库管理"), t("执行SQL查询、查看表结构、备份数据库"),
                icon=":material/database:", meta=f"football.db · {DB_PATH.stat().st_size/1024/1024:.1f} MB" if DB_PATH.exists() else "football.db")

    tab1, tab2, tab3 = st.tabs([t("SQL查询"), t("表结构"), t("备份恢复")])

    with tab1:
        section_cap(t("执行自定义SQL查询"), ":material/edit_note:")
        # key 必须显式给出: label 随语言变化, 无 key 时切语言会清空已输入的 SQL。
        sql = st.text_area(t("SQL语句"),
                           value="SELECT * FROM matches ORDER BY date DESC LIMIT 10",
                           height=100, key="db_sql")
        if st.button(t("执行查询"), type="primary"):
            try:
                conn = get_db_connection()
                df = pd.read_sql_query(sql, conn)
                conn.close()
                st.success(t("查询成功，返回 {n} 行").format(n=len(df)))
                show_df(df)
                num_cols = [c for c in df.columns
                            if pd.api.types.is_numeric_dtype(df[c])
                            and df[c].notna().sum() >= 2]
                if num_cols:
                    divider()
                    dc1, dc2 = st.columns([1, 3])
                    with dc1:
                        qcol = st.selectbox(t("数值字段分布"), num_cols,
                                            key="db_histcol")
                    with dc2:
                        q_df2 = df[[qcol]].dropna().rename(
                            columns={qcol: t("数值")})
                        VIZ.show(VIZ.histogram(q_df2, t("数值"), bins=20,
                                               color=T["accent"],
                                               title=f"{qcol} · {t('分布')}",
                                               height=280),
                                 key="adm_db_hist", fallback=q_df2)
            except Exception as e:
                st.error(f"{t('查询失败')}: {e}")

    with tab2:
        section_cap(t("数据库表结构"), ":material/checklist:")
        tables = ['leagues', 'teams', 'players', 'matches', 'transfers', 'predictions']
        col_cnt = []
        for tbl in tables:
            with st.expander(f"{tbl} ({get_table_count(tbl)} {t('条')})"):
                conn = get_db_connection()
                cur = conn.cursor()
                cur.execute(f"PRAGMA table_info({tbl})")
                cols_info = cur.fetchall()
                conn.close()
                col_df = pd.DataFrame(cols_info, columns=['cid', 'name', 'type', 'notnull', 'dflt_value', 'pk'])
                show_df(col_df[['name', 'type', 'notnull', 'pk']])
            col_cnt.append({t("数据表"): tbl, t("字段数"): len(cols_info),
                            t("记录数"): get_table_count(tbl)})
        cnt_df = pd.DataFrame(col_cnt)
        if not cnt_df.empty:
            divider()
            tc1, tc2 = st.columns(2)
            with tc1:
                VIZ.show(VIZ.rank_bar(cnt_df, t("数据表"), t("字段数"), top=12,
                                      fmt=",.0f", gradient=True,
                                      title=t("各表字段数"), height=300),
                         key="adm_db_cols", fallback=cnt_df)
            with tc2:
                cnt_df2 = cnt_df[cnt_df[t("记录数")] > 0]
                if cnt_df2.empty:
                    empty_state(":material/database:", t("暂无记录"), t("请先导入数据"),
                                command="python scripts/import_data.py")
                else:
                    VIZ.show(VIZ.rank_bar(cnt_df2, t("数据表"), t("记录数"), top=12,
                                          fmt=",.0f", gradient=True,
                                          title=t("各表记录数"), height=300),
                             key="adm_db_rows", fallback=cnt_df2)

    with tab3:
        section_cap(t("数据库备份与恢复"), ":material/save:")
        db_size = DB_PATH.stat().st_size / 1024 / 1024
        st.caption(f"{t('当前数据库')}: {DB_PATH.name} ({db_size:.2f} MB)")

        col1, col2 = st.columns(2)
        with col1:
            if wide_button(t("创建备份"), key="db_backup", type_="primary"):
                backup_dir = BASE_DIR / 'data' / 'backups'
                backup_dir.mkdir(parents=True, exist_ok=True)
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                backup_path = backup_dir / f'football_backup_{timestamp}.db'
                import shutil
                shutil.copy2(str(DB_PATH), str(backup_path))
                st.success(f"{t('备份成功')}: {backup_path.name}")

        with col2:
            backups = list((BASE_DIR / 'data' / 'backups').glob('*.db')) if (BASE_DIR / 'data' / 'backups').exists() else []
            if backups:
                st.caption(f"{t('现有备份')}: {len(backups)} {t('个')}")
                for b in sorted(backups, reverse=True)[:5]:
                    size = b.stat().st_size / 1024 / 1024
                    st.markdown(f"- `{b.name}` ({size:.1f} MB)")
            else:
                st.caption(t("暂无备份"))

# ==================== 页面5: 数据更新控制 ====================

def render_update():
    """数据更新控制"""
    page_header(t("数据更新控制"), t("配置数据源、触发数据更新、查看更新日志"),
                icon=":material/sync:", meta=t("数据源：football-data.co.uk · API-Football"))

    tab1, tab2, tab3 = st.tabs([t("API Key配置"), t("数据导入"), t("更新日志")])

    with tab1:
        section(t("API-Football Key 配置"), t("免费注册: https://www.api-football.com/ (100请求/天)"), icon=":material/key:")

        # 读取当前key
        current_key = ''
        if ENV_PATH.exists():
            with open(ENV_PATH, 'r', encoding='utf-8') as f:
                for line in f:
                    if line.startswith('API_FOOTBALL_KEY='):
                        current_key = line.split('=', 1)[1].strip().strip('"').strip("'")

        new_key = st.text_input("API Key", value=current_key, type="password")
        if st.button(t("保存配置"), type="primary"):
            # 读取现有.env
            env_lines = []
            if ENV_PATH.exists():
                with open(ENV_PATH, 'r', encoding='utf-8') as f:
                    env_lines = f.readlines()

            # 更新或添加
            key_found = False
            new_lines = []
            for line in env_lines:
                if line.startswith('API_FOOTBALL_KEY='):
                    new_lines.append(f'API_FOOTBALL_KEY={new_key}\n')
                    key_found = True
                else:
                    new_lines.append(line)
            if not key_found:
                new_lines.append(f'API_FOOTBALL_KEY={new_key}\n')

            with open(ENV_PATH, 'w', encoding='utf-8') as f:
                f.writelines(new_lines)
            st.success(t("API Key 已保存到 .env 文件"))

        divider()
        section_cap(t("其他配置"), ":material/extension:")
        status_list([
            ("API_FOOTBALL_KEY", t("球员/转会/实时比分数据"), "ok" if current_key else "err"),
            ("LLM_API_KEY", t("AI Agent 智能问答"), "warn"),
            ("football-data.co.uk", t("比赛历史数据(免key)"), "ok"),
        ])

    with tab2:
        section_cap(t("数据导入工具"), ":material/download:")

        col1, col2 = st.columns(2)
        with col1:
            section_cap(t("比赛数据"), ":material/sports_soccer:")
            info_card(t("足球比赛数据"), [
                f"{t('当前')}: {get_table_count('matches')} {t('场')}",
                f"{t('来源')}: football-data.co.uk ({t('免key')})",
                f"{t('覆盖')}: {t('五大联赛')} 2021-2026",
            ], icon=":material/sports_soccer:", color=T["accent"])
            if wide_button(t("重新导入比赛数据"), key="import_matches"):
                with st.spinner(t("正在导入比赛数据...")):
                    result = subprocess.run(
                        [sys.executable, str(BASE_DIR / 'scripts' / 'import_matches.py')],
                        capture_output=True, text=True, cwd=str(BASE_DIR)
                    )
                    st.text(result.stdout[-2000:] if result.stdout else t("无输出"))
                    if result.returncode == 0:
                        st.success(t("比赛数据导入完成"))
                    else:
                        st.error(f"{t('导入失败')}: {result.stderr[-500:]}")

        with col2:
            section_cap(t("球员数据"), ":material/person:")
            info_card(t("球员数据"), [
                f"{t('当前')}: {get_table_count('players')} {t('名')}",
                f"{t('来源')}: API-Football ({t('需key')})",
                f"{t('免费tier')}: 100 {t('请求/天')}",
            ], icon=":material/person:", color=T["accent"])
            if not current_key:
                st.markdown(f'<div class="warn-box">{t("请先配置 API Key")}</div>',
                            unsafe_allow_html=True)
            else:
                if wide_button(t("开始导入球员数据"), key="import_players"):
                    with st.spinner(t("正在导入球员数据（可能需要几分钟）...")):
                        result = subprocess.run(
                            [sys.executable, str(BASE_DIR / 'scripts' / 'import_players.py')],
                            capture_output=True, text=True, cwd=str(BASE_DIR),
                            timeout=300
                        )
                        st.text(result.stdout[-3000:] if result.stdout else t("无输出"))
                        if result.returncode == 0:
                            st.success(t("球员数据导入完成"))
                        else:
                            st.error(f"{t('导入失败')}: {result.stderr[-500:]}")

        divider()
        section(t("赛程同步"), t("Football-Data.org 免费 · 拉取未来 7 天真实赛程与实时比分"), icon=":material/calendar_month:")
        st.caption(t("未配置 Token 时自动退回演示模式；数据幂等、可一键清除。"))
        sync_script = BASE_DIR / 'scripts' / 'sync_fixtures.py'
        if sync_script.exists():
            c1, c2 = st.columns(2)
            with c1:
                if st.button(t("同步未来 7 天真实赛程"), type="primary", key="sync_real"):
                    with st.spinner(t("正在同步...")):
                        result = subprocess.run(
                            [sys.executable, str(sync_script), "--days", "7"],
                            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120
                        )
                        st.text(result.stdout[-2500:] if result.stdout else t("无输出"))
                        if result.returncode == 0:
                            st.success(t("同步完成，刷新页面即可看到真实赛程"))
                        else:
                            st.error(f"{t('同步失败')}: {result.stderr[-500:]}")
            with c2:
                if st.button(t("清除演示赛程"), key="sync_clear"):
                    with st.spinner(t("正在清除...")):
                        result = subprocess.run(
                            [sys.executable, str(sync_script), "--clear"],
                            capture_output=True, text=True, cwd=str(BASE_DIR), timeout=120
                        )
                        st.text(result.stdout[-1500:] if result.stdout else t("无输出"))
                        if result.returncode == 0:
                            st.success(t("演示赛程已清除，恢复为仅含真实数据"))
        else:
            st.error(t("未找到 scripts/sync_fixtures.py"))

        divider()
        section_cap(t("导入进度"), ":material/bar_chart:")
        if PROGRESS_PATH.exists():
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            st.json(prog)
            if isinstance(prog, dict):
                prog_num = {k: v for k, v in prog.items()
                            if isinstance(v, (int, float))
                            and not isinstance(v, bool)}
                if prog_num:
                    pr_df = pd.DataFrame(
                        {t("指标"): list(prog_num.keys()),
                         t("数值"): [float(v) for v in prog_num.values()]})
                    divider()
                    VIZ.show(VIZ.rank_bar(pr_df, t("指标"), t("数值"), top=12,
                                          fmt=",.0f", gradient=True,
                                          title=t("导入进度指标"), height=300),
                             key="adm_prog", fallback=pr_df)
        else:
            st.caption(t("暂无导入进度记录"))

    with tab3:
        section(t("数据更新日志"), t("数据导入与同步的历史日志"), icon=":material/history_edu:")
        log_dir = BASE_DIR / 'data' / 'logs'
        if log_dir.exists():
            logs = sorted(log_dir.glob('*.log'), reverse=True)
            if logs:
                # key 必须显式给出: label 随语言变化, 无 key 时切语言会丢失已选日志文件。
                selected_log = st.selectbox(t("选择日志文件"), [l.name for l in logs], key="log_file")
                log_path = log_dir / selected_log
                with open(log_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                st.text_area(t("日志内容"), content, height=400, key="log_content")
            else:
                st.caption(t("暂无日志文件"))
        else:
            st.caption(t("暂无日志目录"))

        divider()
        section_cap(t("最近数据更新记录"), ":material/schedule:")
        status_list([
            (t("数据库最后修改"),
             datetime.fromtimestamp(DB_PATH.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S'), "off"),
        ])
        if PROGRESS_PATH.exists():
            with open(PROGRESS_PATH, 'r', encoding='utf-8') as f:
                prog = json.load(f)
            if prog.get('last_update'):
                status_list([(t("球员导入最后更新"), prog['last_update'], "off")])

# ==================== 页面6: 模型管理 ====================

def render_models():
    """模型管理"""
    page_header(t("模型管理"), t("查看模型信息、评估指标、触发模型重训"),
                icon=":material/smart_toy:",
                meta=t("XGBoost · 集成 v2+v7 · 官方 xG 特征"))

    # ---------- 当前部署模型的样本外评估(读预计算分析表, 不再依赖旧的 evaluation_result.json) ----------
    section(t("部署模型评估"), t("严格样本外 · 训练集 < 2025-08-01 · 测试集 1,817 场"),
            icon=":material/science:")
    _conn = get_db_connection()
    try:
        _mm = pd.read_sql_query("SELECT * FROM model_metrics ORDER BY acc DESC", _conn)
        _conf = pd.read_sql_query("SELECT actual, predicted, count FROM model_confusion", _conn)
        _cal = pd.read_sql_query("SELECT outcome, predicted, actual, n FROM model_calibration "
                                 "ORDER BY predicted", _conn)
        _fi = pd.read_sql_query("SELECT feature, importance FROM feature_importance "
                                "ORDER BY importance DESC LIMIT 12", _conn)
    except Exception as e:
        _mm = _conf = _cal = _fi = pd.DataFrame()
        st.markdown(f'<div class="warn-box">{t("分析数据表不存在")}（{e}）<br>'
                    f'<code>python scripts/build_analytics_tables.py</code></div>',
                    unsafe_allow_html=True)
    _conn.close()

    if not _mm.empty:
        _top = _mm.iloc[0]
        metric_row([
            {"value": str(_top["model"]), "label": t("最优模型"), "hint": t("按准确率"),
             "icon": ":material/emoji_events:", "color": T["accent"]},
            {"value": f"{float(_top['acc']):.2f}%", "label": t("准确率"),
             "hint": t("全押主胜基线 44.36%"), "icon": ":material/target:", "color": T["accent"]},
            {"value": f"{float(_top['logloss']):.4f}", "label": "LogLoss",
             "hint": t("概率校准质量"), "icon": ":material/trending_down:", "color": T["accent"]},
            {"value": f"{float(_top['f1_macro']):.4f}", "label": t("宏平均 F1"),
             "hint": f"{t('平局召回')} {float(_top['draw_recall']):.1f}%",
             "icon": ":material/balance:", "color": T["accent"]},
        ])
        mc1, mc2 = st.columns([3, 2])
        with mc1:
            _cmp = _mm.rename(columns={"model": t("模型"), "acc": t("准确率")})
            VIZ.show(VIZ.rank_bar(_cmp, t("模型"), t("准确率"), fmt=",.2f", top=8,
                                  gradient=True, bar_size=24,
                                  title=t("各方案样本外准确率 (%)"), height=300),
                     key="adm_model_acc", fallback=_cmp)
        with mc2:
            _ll = _mm.rename(columns={"model": t("模型"), "logloss": "LogLoss"})
            VIZ.show(VIZ.rank_bar(_ll, t("模型"), "LogLoss", fmt=",.4f", top=8,
                                  color=T["accent"], bar_size=24,
                                  title=t("LogLoss（越低越好）"), height=300),
                     key="adm_model_ll", fallback=_ll)

        ec1, ec2 = st.columns([2, 3])
        with ec1:
            if not _conf.empty:
                _cm = _conf.rename(columns={"actual": t("实际"), "predicted": t("预测"),
                                            "count": t("场次")})
                VIZ.show(VIZ.heatmap(_cm, t("预测"), t("实际"), t("场次"), fmt=",.0f",
                                     show_text=True, title=t("混淆矩阵（集成模型）"),
                                     height=300),
                         key="adm_model_cm", fallback=_cm)
        with ec2:
            if not _cal.empty:
                _c = _cal.rename(columns={"outcome": t("结果"), "predicted": t("预测概率"),
                                          "actual": t("实际频率")})
                VIZ.show(VIZ.multi_line(_c, t("预测概率"), t("结果"), t("实际频率"),
                                        fmt=",.2f", x_type="Q", diagonal=t("理想校准"),
                                        x_range=(0.0, 1.0),
                                        title=t("概率校准曲线（越贴近虚线越好）"), height=300),
                         key="adm_model_cal", fallback=_c)
        if not _fi.empty:
            _f = _fi.rename(columns={"feature": t("特征"), "importance": t("重要性")})
            VIZ.show(VIZ.rank_bar(_f, t("特征"), t("重要性"), top=12, fmt=",.4f",
                                  gradient=True, bar_size=20,
                                  title=t("特征重要性 Top 12"), height=340),
                     key="adm_model_fi", fallback=_f)
        divider()

    # 模型文件列表
    model_files = list(MODELS_DIR.glob('*.joblib')) if MODELS_DIR.exists() else []
    section(t("模型文件"), f"{len(model_files)} {t('个')}", icon=":material/inventory_2:")

    if not model_files:
        empty_state(":material/inventory_2:", t("暂无模型文件"), t("请先训练模型"),
                    command="python scripts/train_model_fast.py")
    else:
        for mf in model_files:
            size = mf.stat().st_size / 1024
            mtime = datetime.fromtimestamp(mf.stat().st_mtime).strftime('%Y-%m-%d %H:%M')
            with st.expander(f"{mf.name} ({size:.1f} KB, {mtime})"):
                info_card(mf.name, [f"{t('路径')}: {mf}", f"{t('大小')}: {size:.1f} KB",
                                    f"{t('修改时间')}: {mtime}"], icon=":material/inventory_2:", color=T["accent"])

                # 评估结果
                eval_path = MODELS_DIR / 'evaluation_result.json'
                if eval_path.exists():
                    with open(eval_path, 'r', encoding='utf-8') as f:
                        eval_data = json.load(f)
                    section_cap(t("评估结果"), ":material/target:")

                    acc = eval_data.get("accuracy")
                    ll = eval_data.get("log_loss")
                    tr_n = eval_data.get("train_samples")
                    te_n = eval_data.get("test_samples")
                    metric_row([
                        {"value": f"{acc:.1%}" if isinstance(acc, (int, float)) else "—",
                         "label": t("整体准确率"), "hint": t("三分类"), "icon": ":material/target:",
                         "color": T["accent"]},
                        {"value": f"{ll:.3f}" if isinstance(ll, (int, float)) else "—",
                         "label": t("对数损失"), "hint": "Log Loss", "icon": ":material/trending_down:",
                         "color": T["accent"]},
                        {"value": f"{tr_n:,}" if isinstance(tr_n, (int, float)) else "—",
                         "label": t("训练样本"), "icon": ":material/science:", "color": T["accent"]},
                        {"value": f"{te_n:,}" if isinstance(te_n, (int, float)) else "—",
                         "label": t("测试样本"), "icon": ":material/straighten:", "color": T["accent"]},
                    ])

                    names = [t("主胜"), t("平局"), t("客胜")]
                    cm = eval_data.get("confusion_matrix")
                    cl = eval_data.get("class_accuracy") or {}
                    ev1, ev2 = st.columns([3, 2])
                    with ev1:
                        if cm and len(cm) == len(names) and all(
                                len(r) == len(names) for r in cm):
                            cm_long = (pd.DataFrame(cm, index=names, columns=names)
                                       .stack().reset_index())
                            cm_long.columns = [t("实际结果"), t("预测结果"), t("样本数")]
                            VIZ.show(VIZ.heatmap(cm_long, t("预测结果"), t("实际结果"),
                                                 t("样本数"), fmt=",.0f", show_text=True,
                                                 title=t("混淆矩阵"), height=300),
                                     key="mdl_cm", fallback=cm_long)
                        else:
                            st.json(eval_data)
                    with ev2:
                        if cl:
                            ca_df = pd.DataFrame({
                                t("类别"): [t(k) for k in cl.keys()],
                                t("准确率"): [float(v) * 100 for v in cl.values()],
                            })
                            VIZ.show(VIZ.bar(ca_df, t("类别"), t("准确率"), fmt=",.1f",
                                             label=True, rotate=0,
                                             title=t("各类别准确率 (%)"), height=300),
                                     key="mdl_ca", fallback=ca_df)
                        else:
                            st.json(cl or {})

                # 特征重要性
                fi_path = MODELS_DIR / 'feature_importance.json'
                if fi_path.exists():
                    with open(fi_path, 'r', encoding='utf-8') as f:
                        fi_data = json.load(f)
                    section_cap(t("Top 10 重要特征"), ":material/bar_chart:")
                    if isinstance(fi_data, list) and fi_data:
                        fi_df = pd.DataFrame(fi_data[:10])
                        feat_col = t("特征")
                        val_col = t("重要性")
                        fi_df = fi_df.rename(columns={"feature": feat_col,
                                                      "importance": val_col})
                        fi_df[val_col] = pd.to_numeric(fi_df[val_col], errors="coerce")
                        fi_df = fi_df.dropna(subset=[val_col])
                        if fi_df.empty:
                            show_df(pd.DataFrame(fi_data[:10]))
                        else:
                            VIZ.show(VIZ.rank_bar(fi_df, feat_col, val_col, top=10,
                                                  fmt=",.4f", gradient=True,
                                                  title=t("特征重要性 Top 10"), height=340),
                                     key="mdl_fi", fallback=fi_df)
                    elif isinstance(fi_data, dict):
                        st.json(fi_data)

    divider()

    # 模型重训
    section(t("模型重训"), t("使用最新数据重新训练 XGBoost 预测模型"), icon=":material/rocket_launch:")

    train_script = BASE_DIR / 'scripts' / 'train_model_fast.py'
    if train_script.exists():
        if st.button(t("开始训练模型"), type="primary"):
            with st.spinner(t("正在训练模型（约10-30秒）...")):
                result = subprocess.run(
                    [sys.executable, str(train_script)],
                    capture_output=True, text=True, cwd=str(BASE_DIR),
                    timeout=120
                )
                st.text(result.stdout[-3000:] if result.stdout else t("无输出"))
                if result.returncode == 0:
                    st.success(t("模型训练完成！"))
                else:
                    st.error(f"{t('训练失败')}: {result.stderr[-500:]}")
    else:
        st.error(t("训练脚本不存在"))

    divider()

    # 模型信息(与实际实现保持一致: 集成模型 + 官方 xG 特征; 不再宣称未使用的 SHAP)
    section(t("模型信息"), icon=":material/info:")
    col1, col2, col3 = st.columns(3)
    with col1:
        info_card(t("算法"), [t("XGBoost（三分类）"), t("主胜 / 平局 / 客胜"),
                              (t("v2 与 v7 概率加权集成"), True)],
                  icon=":material/psychology:", color=T["accent"])
    with col2:
        info_card(t("特征"), [t("119 维：Elo / 状态 / 攻防 / 赛程 / 交锋"),
                              (t("官方 xG（Understat）"), True),
                              (t("阵容身价与伤病（Transfermarkt）"), True)],
                  icon=":material/straighten:", color=T["accent"])
    with col3:
        info_card(t("评估"), [t("严格时间序列切分（防数据泄露）"),
                              (t("概率校准曲线 + 混淆矩阵"), True),
                              (t("特征重要性可追溯"), True)],
                  icon=":material/query_stats:", color=T["accent"])

    divider()

    # 模型版本对比
    section(t("模型版本对比"), t("离线评估报告可视化"), icon=":material/science:")

    v7 = load_json('v7_report.json') or {}
    wf = load_json('walkforward_compare.json') or {}
    px = load_json('proxy_xg_report.json') or {}
    cutoff = v7.get('cutoff') or wf.get('cutoff')
    if cutoff:
        st.caption(f"{t('评估切分点')}: {cutoff}")

    mc1, mc2 = st.columns(2)
    with mc1:
        v7_res = v7.get('results') or []
        if not v7_res:
            empty_state(":material/science:", t("暂无模型对比数据"),
                        t("运行训练脚本可生成模型对比报告"),
                        command="python scripts/train_v7.py")
        else:
            long_m = pd.DataFrame(
                [{t("模型"): str(r.get('model', '—')), t("指标"): mname,
                  t("数值"): float(r.get(mkey, 0) or 0) * 100}
                 for r in v7_res
                 for mname, mkey in ((t("准确率"), 'acc'), (t("宏 F1"), 'f1_macro'),
                                     (t("平局召回率"), 'draw_recall'))])
            VIZ.show(VIZ.grouped_bar(long_m, t("模型"), t("指标"), t("数值"),
                                     colors=[T["accent"], T["blue"], T["gold"]],
                                     fmt=",.1f", rotate=-12,
                                     title=t("模型指标对比 (%)"), height=320),
                     key="mdl_v7_cmp", fallback=long_m)
    with mc2:
        corr = px.get('corr_official_xg') or {}
        if not corr:
            empty_state(":material/trending_up:", t("暂无代理 xG 报告"),
                        t("运行代理 xG 训练脚本后可查看相关性"),
                        command="python scripts/train_proxy_xg.py")
        else:
            corr_df = pd.DataFrame({
                t("维度"): [t("主队"), t("客队")],
                t("相关系数"): [float(corr.get('home', 0) or 0),
                               float(corr.get('away', 0) or 0)],
            })
            VIZ.show(VIZ.bar(corr_df, t("维度"), t("相关系数"), fmt=",.3f", label=True,
                             color=T["accent"],
                             title=t("代理 xG 与官方 xG 相关性"), height=320),
                     key="mdl_pxg", fallback=corr_df)

    wf_res = wf.get('results') or []
    if wf_res:
        wf_df = pd.DataFrame({
            t("特征方案"): [f"{r.get('model', '—')} · {int(r.get('features') or 0)}{t('维')}"
                            for r in wf_res],
            t("准确率"): [float(r.get('acc', 0) or 0) * 100 for r in wf_res],
        }).sort_values(t("准确率"), ascending=False)
        VIZ.show(VIZ.rank_bar(wf_df, t("特征方案"), t("准确率"), top=10, fmt=",.2f",
                              gradient=True,
                              title=t("Walk-forward 各特征方案准确率 (%)"), height=340),
                 key="mdl_wf", fallback=wf_df)

    divider()

    # ---------- 深度学习分支: 多切点稳健性 + 显著性 + 泄漏检验 ----------
    section(t("深度学习分支 · 稳健性证据"),
            t("3 个时间切点 × 3 随机种子 · 同一 126 维特征 · 与 XGBoost 同协议"),
            icon=":material/science:")
    dlr = load_json('dl_robustness.json')
    if not dlr or not dlr.get("summary"):
        empty_state(":material/science:", t("暂无稳健性结果"),
                    t("运行脚本可生成多切点对比、McNemar 配对检验与标签置换泄漏检验"),
                    command="python scripts/dl_robustness.py --seeds 3 --epochs 150")
    else:
        cuts = dlr.get("cutoffs") or []
        summary = dlr["summary"]
        # 跨切点准确率对比(分组柱: 每个方案在各切点的表现)
        rows_dl = []
        for name, v in summary.items():
            for cut, acc in zip(cuts, v.get("accs", [])):
                rows_dl.append({t("方案"): name, t("切点"): cut,
                                t("准确率"): float(acc) * 100})
        dl_df = pd.DataFrame(rows_dl)
        if not dl_df.empty:
            VIZ.show(VIZ.grouped_bar(dl_df, t("切点"), t("方案"), t("准确率"),
                                     colors=[T["accent"], T["blue"], T["gold"],
                                             T["purple"], T["red"], T["t3"]],
                                     fmt=",.1f", rotate=0,
                                     title=t("各方案在 3 个时间切点上的准确率 (%)"),
                                     height=330),
                     key="mdl_dl_cuts", fallback=dl_df)

        dl1, dl2 = st.columns([3, 2])
        with dl1:
            mean_df = pd.DataFrame({
                t("方案"): list(summary.keys()),
                t("均值准确率"): [v["mean_acc"] * 100 for v in summary.values()],
                t("跨切点极差"): [round((max(v["accs"]) - min(v["accs"])) * 100, 2)
                                  for v in summary.values()],
            }).sort_values(t("均值准确率"), ascending=False)
            VIZ.show(VIZ.rank_bar(mean_df, t("方案"), t("均值准确率"), top=8,
                                  fmt=",.2f", gradient=True, bar_size=24,
                                  title=t("跨切点均值准确率 (%)"), height=300),
                     key="mdl_dl_mean", fallback=mean_df)
        with dl2:
            st.markdown(f"**{t('McNemar 配对检验')}**")
            mc_rows = []
            for r in dlr.get("results", []):
                for other, v in (r.get("mcnemar") or {}).items():
                    mc_rows.append({
                        t("切点"): r["cutoff"], t("对比"): f"{r['model']} vs {other}",
                        "p": v["p_value"],
                        t("结论"): t("显著") if v["p_value"] < 0.05 else t("不显著"),
                    })
            if mc_rows:
                mc_df = pd.DataFrame(mc_rows)
                st.dataframe(mc_df, width="stretch", hide_index=True, height=232)
                n_sig = sum(1 for r in mc_rows if r["p"] < 0.05)
                st.caption(f"{t('共')} {len(mc_rows)} {t('组比较')}，"
                           f"{n_sig} {t('组 p<0.05')}")
            leak = dlr.get("leakage_test") or {}
            if leak:
                ok = abs(leak.get("acc", 0) - leak.get("baseline", 0)) < 0.01
                st.markdown(
                    f'<div class="{"success-box" if ok else "warn-box"}">'
                    f'{t("标签置换泄漏检验")}: {t("打乱训练标签后测试集准确率")} '
                    f'{leak.get("acc", 0):.2%}（{t("基线")} {leak.get("baseline", 0):.2%}）'
                    f'{" ✅ " + t("无泄漏迹象") if ok else " ⚠️ " + t("需排查")}'
                    f'<br>LogLoss {leak.get("logloss", 0):.4f}（{t("随机")} 1.0986）</div>',
                    unsafe_allow_html=True)
        st.caption(t("判读：深度学习分支在 3 个切点上全部领先且波动更小，但平局召回极低"
                     "（放弃平局换准确率），宏平均 F1 并不高于 XGBoost —— 属取舍关系，"
                     "详见 docs/模型评估报告.md 第六节。"))


def main():
    # 单独运行本文件(streamlit run frontend/xxx.py)时的完整流程
    st.set_page_config(
        page_title="足球分析系统 - 管理员后台",
        page_icon=":material/sports_soccer:",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    apply_theme()
    global AUTH_USER
    AUTH_USER = login_gate()
    with st.sidebar:
        # 当前登录用户 + 退出(管理后台只放管理员进来)
        if _sidebar_user and AUTH_USER:
            _sidebar_user(AUTH_USER)

        # 语言切换置于侧栏最顶部: session_state["lang"] 必须在本次运行内、任何 t()
        # 调用之前写入。若放在品牌区之后, 品牌标题会滞后一次交互才更新。
        lang_selector()
        theme_selector(t("主题"))

        brand_header(t("足球分析系统"), t("管理员后台 · Admin Console"), ":material/settings:")
        divider()

        # ---- 深链支持: ?page=models 之类可直接打开某一页(见 docs/system_viewer/index.html) ----
        _SLUGS = {
            "overview": "数据概览", "browse": "数据浏览", "api": "API接口测试",
            "database": "数据库管理", "update": "数据更新控制", "models": "模型管理",
        }
        _OPS = list(_SLUGS.values())
        _qp = st.query_params.get("page")
        if isinstance(_qp, list):
            _qp = _qp[0] if _qp else None
        if _qp and _qp != st.session_state.get("_applied_qp"):
            _target = _SLUGS.get(_qp, _qp)
            if _target in _OPS:
                st.session_state["adm_page"] = _target
            st.session_state["_applied_qp"] = _qp

        # key 必须显式给出: 无 key 时 radio 的元素 id 由参数(含 translate 后的选项)推导,
        # 切换语言会让 id 变化 -> 已提交的选中项被丢弃 -> 页面被重置回"数据概览"。
        # 分组标记(参照稿的分组导航): 只给主题 CSS 用 ::before 加「概览 / 数据 / 运维」组标题
        st.markdown('<div class="nav-groups-admin"></div>', unsafe_allow_html=True)
        page = st.radio(t("管理功能"), [
            "数据概览",
            "数据浏览",
            "API接口测试",
            "数据库管理",
            "数据更新控制",
            "模型管理",
        ], format_func=lambda x: t(x), label_visibility="collapsed", key="adm_page")

        divider()

        # ---- 系统状态 ----
        section_cap(t("系统状态"), ":material/sensors:")
        _db_ok = DB_PATH.exists()
        _db_size = f"{DB_PATH.stat().st_size / 1024 / 1024:.0f} MB" if _db_ok else "—"
        status_list([
            (t("数据库"), _db_size, "ok" if _db_ok else "err"),
            (t("最后刷新"), datetime.now().strftime("%H:%M:%S"), "off"),
        ])
        status_list([
            (t("联赛"), f"{get_table_count('leagues'):,}", "off"),
            (t("球队"), f"{get_table_count('teams'):,}", "off"),
            (t("球员"), f"{get_table_count('players'):,}", "off"),
            (t("比赛"), f"{get_table_count('matches'):,}", "off"),
        ])

        divider()

        # ---- 返回前端 ----
        section_cap(t("系统管理"), ":material/build:")
        nav_link(FRONTEND_URL, t("返回前端首页"), ":material/home:")
        if wide_button(t("刷新页面"), key="side_refresh"):
            st.rerun()

        app_footer(t("足球数据分析系统 · 管理员后台 · 毕业设计"))

    # ==================== 页面1: 数据概览 ====================
    if page == "数据概览":
        render_overview()
    elif page == "数据浏览":
        render_browse()
    elif page == "API接口测试":
        render_api()
    elif page == "数据库管理":
        render_database()
    elif page == "数据更新控制":
        render_update()
    elif page == "模型管理":
        render_models()
    else:
        st.warning("未知页面: " + str(page))
    # 页脚
    divider()
    app_footer(f"{t('足球数据分析系统 · 管理员后台 v1.0')} · {t('数据库')}: {DB_PATH.name} · {t('最后刷新')}: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")


if __name__ == "__main__":
    main()

