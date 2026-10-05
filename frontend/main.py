# -*- coding: utf-8 -*-
"""统一入口 - 足球数据分析与 AI 预测系统

一个应用、一套导航、按账号角色显示页面:

    user  角色 -> 只看到 8 个前端页面
    admin 角色 -> 8 个前端页面 + 6 个管理后台页面(共 14 页)

页面实现仍在 frontend/app.py(用户端) 与 frontend/admin.py(后台) 里, 本文件只负责:
登录闸门 -> 侧栏(用户卡 / 语言 / 主题 / 分组导航 / 系统状态) -> 按角色过滤 -> 分发渲染。

启动: streamlit run frontend/main.py --server.port 8501
"""
import sys
from pathlib import Path

import streamlit as st

# ---------- 共享模块 ----------
sys.path.insert(0, str(Path(__file__).parent))

try:
    from i18n import t as _t, lang_selector as _lang_selector
except Exception:                                     # pragma: no cover
    def _t(zh, en=None):
        return zh

    def _lang_selector():
        pass


try:
    from theme import (
        apply_theme, section_cap, divider, status_list, brand_header, app_footer,
        theme_selector, nav_link, T as TH,
    )
    from theme import API_BASE as _API_BASE
except Exception:                                     # pragma: no cover
    TH = {}
    _API_BASE = "http://127.0.0.1:8000/api"

    def _noop(*a, **k):
        return None

    apply_theme = section_cap = divider = status_list = _noop
    brand_header = app_footer = theme_selector = nav_link = _noop

t = _t

try:
    from auth_gate import login_gate, sidebar_user as _sidebar_user, logout as _auth_logout
except Exception:                                     # pragma: no cover
    def login_gate(**kw):
        return {}

    _sidebar_user = None
    _auth_logout = None

API_BASE = _API_BASE

# ---------- 页面配置(必须是第一个 Streamlit 命令) ----------
st.set_page_config(
    page_title="足球数据分析与AI预测系统",
    page_icon=":material/sports_soccer:",
    layout="wide",
    initial_sidebar_state="expanded",
)

apply_theme()

# ---------- 登录闸门(未登录直接渲染登录页并停住) ----------
AUTH_USER = login_gate()
IS_ADMIN = (AUTH_USER or {}).get("role") == "admin"

# ---------- 参照稿全屏预览(?ref=1): 隐藏 Streamlit 外壳, 只剩参照稿本身 ----------
# 用途: 用户 m07333「先复刻，复刻出来给我看」——这里给出与参照稿逐像素一致的一屏,
# 便于和 index(1).html 直接对照; 确认后再进入数据接入阶段。
if str(st.query_params.get("ref", "")) == "1":
    try:
        import ref_page as _REF
        from theme import current_theme as _theme_key
    except Exception:                                   # pragma: no cover
        _REF = None
    # 注意: 缩进的 HTML 会被 markdown 当成代码块原样显示 —— 必须压成单行(不换行、不带前导空格)
    _chrome_off = (
        '<style>'
        '[data-testid="stSidebar"],[data-testid="stHeader"],[data-testid="stToolbar"],'
        '[data-testid="stDecoration"],[data-testid="stStatusWidget"],#sb-rescue,.stApp>header'
        '{display:none !important}'
        '[data-testid="stAppViewContainer"]>.main,[data-testid="stMainBlockContainer"]'
        '{padding:0 !important;margin:0 !important;max-width:100% !important;inset:auto !important}'
        '[data-testid="stMainBlockContainer"]::before{display:none !important}'
        '.block-container{padding:0 !important}'
        'iframe[title="streamlit_components.v1.html"]{display:block;width:100% !important}'
        '.stApp{background:#eef5fd}'
        '</style>'
        '<a href="?ref=0" target="_self" style="position:fixed;right:14px;bottom:12px;z-index:99;'
        'font:600 12px/1 Microsoft YaHei,sans-serif;color:#2e7cf0;background:rgba(255,255,255,.72);'
        'border:1.5px solid rgba(255,255,255,.9);border-radius:999px;padding:9px 16px;'
        'text-decoration:none;box-shadow:0 8px 22px rgba(60,120,200,.22)">← 退出预览，回到系统</a>')
    st.markdown(_chrome_off, unsafe_allow_html=True)
    if _REF:
        _REF.render(theme=_theme_key(), height=1180)
    else:
        st.error("参照稿渲染层不可用(frontend/ref_page.py)")
    st.stop()

# ---------- 页面实现: 用户端 8 页 + 管理后台 6 页 ----------
import app as APP                                     # noqa: E402  用户端页面渲染函数
import admin as ADM                                   # noqa: E402  管理后台页面渲染函数

APP.AUTH_USER = AUTH_USER or {}                       # 页面函数从各自模块读 AUTH_USER
ADM.AUTH_USER = AUTH_USER or {}

USER_PAGES = [
    "首页概览", "联赛数据", "球队分析", "球员分析",
    "比赛详情", "比赛预测", "AI智能分析", "实时比分",
]
ADMIN_PAGES = ["数据概览", "数据浏览", "API接口测试", "数据库管理", "数据更新控制", "模型管理"]

SLUG2PAGE = {
    "home": "首页概览", "leagues": "联赛数据", "teams": "球队分析", "players": "球员分析",
    "match": "比赛详情", "predict": "比赛预测", "agent": "AI智能分析", "live": "实时比分",
    "overview": "数据概览", "browse": "数据浏览", "api": "API接口测试",
    "database": "数据库管理", "update": "数据更新控制", "models": "模型管理",
}

RENDER = {
    "首页概览": APP.render_home, "联赛数据": APP.render_leagues,
    "球队分析": APP.render_teams, "球员分析": APP.render_players,
    "比赛详情": APP.render_match, "比赛预测": APP.render_predict,
    "AI智能分析": APP.render_agent, "实时比分": APP.render_live,
    "数据概览": ADM.render_overview, "数据浏览": ADM.render_browse,
    "API接口测试": ADM.render_api, "数据库管理": ADM.render_database,
    "数据更新控制": ADM.render_update, "模型管理": ADM.render_models,
}

PAGES = USER_PAGES + (ADMIN_PAGES if IS_ADMIN else [])

# 侧栏导航图标(设计说明第③条: 菜单每项带小图标) —— 走 Material 短代码, 由 Streamlit 渲染
NAV_ICON = {
    "首页概览": "dashboard", "联赛数据": "emoji_events", "球队分析": "shield",
    "球员分析": "person_search", "比赛详情": "sports_soccer", "比赛预测": "insights",
    "AI智能分析": "smart_toy", "实时比分": "sensors",
    "数据概览": "monitoring", "数据浏览": "table_view", "API接口测试": "api",
    "数据库管理": "storage", "数据更新控制": "sync", "模型管理": "model_training",
}


def _nav_label(page_name: str) -> str:
    """侧栏选项显示文本: :material/icon: + 页名(图标进 CSS nth-child 分组规则不受影响)。"""
    ic = NAV_ICON.get(page_name)
    return f":material/{ic}: {t(page_name)}" if ic else t(page_name)


def backend_ok() -> bool:
    """后端 API 是否在跑(侧栏状态行用)。"""
    try:
        import requests
        return requests.get(f"{API_BASE.replace('/api', '')}/", timeout=3).status_code == 200
    except Exception:
        return False


# ---------- 无壳模式: 左下浮动按钮开/关老导航抽屉 ----------
# 参照稿自带顶栏与侧栏, 它就是界面本身; 老侧栏只在需要时以浮层形式出现(用户 m07431)。
_NAV_FAB_JS = """
<div style="height:0"></div>
<script>
(function(){
  var d;
  try { d = window.parent.document; } catch(e) { return; }
  if (!d || d.getElementById('nav-fab')) { return; }
  var b = d.createElement('button');
  b.id = 'nav-fab';
  b.type = 'button';
  b.title = '导航 / 主题 / 语言';
  b.innerHTML = '<svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor"'
    + ' stroke-width="2" stroke-linecap="round"><path d="M4 7h16M4 12h16M4 17h16"/></svg>';
  b.addEventListener('click', function(){
    d.body.classList.toggle('nav-open');
  });
  d.body.appendChild(b);
  // 抽屉里点任一项后自动收起
  d.addEventListener('click', function(ev){
    var t = ev.target;
    if (t && t.closest && t.closest('[data-testid="stSidebar"] label')) {
      setTimeout(function(){ d.body.classList.remove('nav-open'); }, 260);
    }
  }, true);
  // Esc 关闭
  d.addEventListener('keydown', function(ev){
    if (ev.key === 'Escape') { d.body.classList.remove('nav-open'); }
  });
})();
</script>
"""


def nav_fab() -> None:
    try:
        import streamlit.components.v1 as _c
        with st.container(key="navfab"):     # 0 高度容器, 主题 CSS 会把它 display:none
            _c.html(_NAV_FAB_JS, height=0)
    except Exception:                                   # pragma: no cover
        pass


# ============ 侧边栏 ============
with st.sidebar:
    if _sidebar_user and AUTH_USER:
        _sidebar_user(AUTH_USER)                      # 用户卡 + 退出(合并后不再需要跳后台链接)

    _lang_selector()
    theme_selector(t("主题"))

    divider()

    # ---- 深链支持: ?page=models 之类可直接打开某一页(按角色过滤) ----
    _qp = st.query_params.get("page")
    if isinstance(_qp, list):
        _qp = _qp[0] if _qp else None
    if _qp and _qp != st.session_state.get("_applied_qp"):
        _target = SLUG2PAGE.get(_qp, _qp)
        if _target in PAGES:
            st.session_state["nav_page"] = _target
        st.session_state["_applied_qp"] = _qp

    # 换了账号(页面列表变了)时, 清掉不属于当前角色的停留页
    if st.session_state.get("nav_page") not in PAGES:
        st.session_state["nav_page"] = PAGES[0]

    # 分组标记(参照稿的分组导航): 只给主题 CSS 用 ::before 加组标题
    st.markdown('<div class="nav-groups-both"></div>' if IS_ADMIN
                else '<div class="nav-groups-user"></div>', unsafe_allow_html=True)
    page = st.radio(t("导航"), PAGES, format_func=_nav_label,
                    label_visibility="collapsed", key="nav_page")

    divider()

    # ---- 系统状态 ----
    section_cap(t("系统状态"), ":material/sensors:")
    _ok = backend_ok()
    _db = Path(__file__).parent.parent / "data" / "database" / "football.db"
    status_list([
        (t("后端服务"), t("运行中") if _ok else t("未启动"), "ok" if _ok else "err"),
        (t("数据源"), "SQLite", "ok"),
        (t("数据库"), f"{_db.stat().st_size / 1024 / 1024:.0f} MB" if _db.exists() else "—",
         "ok" if _db.exists() else "err"),
    ])
    status_list([
        (t("页面数"), f"{len(PAGES)}", "off"),
        (t("当前角色"), t("管理员") if IS_ADMIN else t("普通用户"), "off"),
    ])

    divider()
    app_footer(t("足球数据分析与AI预测系统 · 毕业设计"))


# ============ 分发渲染 ============
nav_fab()                          # 左下浮动按钮: 需要时打开老导航抽屉(无壳模式)

_render = RENDER.get(page)
if _render is None:
    st.warning(f"{t('当前账号没有这个页面的权限')}: {page}")
else:
    _render()
