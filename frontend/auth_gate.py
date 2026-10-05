# -*- coding: utf-8 -*-
"""登录闸门 —— 用户端(app.py)与管理后台(admin.py)共用。

用法(放在 apply_theme() 之后、业务渲染之前):

    from auth_gate import login_gate, sidebar_user
    USER = login_gate()                    # 用户端
    USER = login_gate(admin_only=True)     # 管理后台(必须是 admin 角色)

未登录时本模块会把整页交给控制台的登录页(用户新做的 login.html, 自带 3D 足球与
日照/黄昏/夜晚/雨四个场景), 登录成功后按 ?next= 带令牌回到本页; 若控制台的登录页
连不上(8591 没起), 自动退回本模块自带的 Streamlit 表单, 不会把人卡在门外。

令牌来自三处, 优先级: 会话状态 > URL 参数 auth_token(控制台「真实系统」按钮与
登录页回跳都带过来) > 无。

为什么还要在 Streamlit 里再拦一道: 控制台的闸门是前端 JS, 绕过它直接访问
8501/8502 就没保护了。真正的关口在这里(以及后端 /api/auth)。
"""
import json
import os
import urllib.error
import urllib.parse
import urllib.request

import streamlit as st

try:                                                  # 与全站同一套设计令牌
    from theme import T as _T
except Exception:                                     # pragma: no cover
    _T = {}

API_ROOT = os.getenv("FA_API_ROOT", "http://127.0.0.1:8000").rstrip("/")
CONSOLE_LOGIN = os.getenv("FA_CONSOLE_LOGIN", "http://127.0.0.1:8591/login.html").rstrip("/")
_SS_TOKEN = "auth_token"
_SS_QR = "qr_ticket"
_AUTH_REJECTED = "_auth_rejected"


# ---------------- 后端调用 ----------------

def _api(method: str, path: str, payload: dict = None, token: str = "",
         raw: bool = False, timeout: int = 10):
    """调后端 /api/*; 失败返回 None(调用方按失败处理, 不抛异常打断页面)。"""
    url = API_ROOT + path
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read()
            return body if raw else json.loads(body.decode("utf-8"))
    except urllib.error.HTTPError as e:
        if raw:
            return None
        try:
            return {"_error": e.code, **json.loads(e.read().decode("utf-8"))}
        except Exception:
            return {"_error": e.code}
    except Exception:
        return None


def _take_query_token() -> str:
    """控制台「真实系统」会把 auth_token 放进 URL —— 收下后立刻从地址栏抹掉。"""
    try:
        raw = st.query_params.get("auth_token")
    except Exception:
        return ""
    if isinstance(raw, (list, tuple)):
        raw = raw[0] if raw else ""
    if raw:
        st.session_state[_SS_TOKEN] = raw
        try:
            del st.query_params["auth_token"]
        except Exception:
            pass
    return raw or ""


def current_user() -> dict:
    """当前登录用户; 未登录返回 {}(令牌存在但失效会顺手清掉)。"""
    token = st.session_state.get(_SS_TOKEN) or _take_query_token()
    if not token:
        return {}
    res = _api("GET", "/api/auth/me", token=token)
    if res and res.get("user"):
        st.session_state.pop(_AUTH_REJECTED, None)
        return res["user"]
    st.session_state.pop(_SS_TOKEN, None)
    st.session_state[_AUTH_REJECTED] = True      # 从登录页回跳的令牌无效: 别再弹回去
    return {}


def logout() -> None:
    """注销令牌并回到登录界面。"""
    token = st.session_state.get(_SS_TOKEN, "")
    if token:
        _api("POST", "/api/auth/logout", token=token)
    for k in (_SS_TOKEN, _SS_QR):
        st.session_state.pop(k, None)
    st.rerun()


# ---------------- 侧栏用户区 ----------------

def sidebar_user(user: dict, *, admin_url: str = "") -> None:
    """在侧栏顶部显示当前用户与退出按钮(在 sidebar 上下文里调用)。"""
    name = user.get("display_name") or user.get("username") or "—"
    role = "管理员" if user.get("role") == "admin" else "普通用户"
    st.markdown(
        f"""<div style="display:flex;align-items:center;gap:10px;padding:10px 12px;
        border:1px solid {_T.get('line', 'rgba(19,26,33,.12)')};
        border-radius:{_T.get('r1', '10px')};background:{_T.get('glass_strong', 'rgba(255,255,255,.93)')};
        margin-bottom:10px">
          <span style="width:30px;height:30px;border-radius:9px;background:{_T.get('accent', '#2f86e0')};
          color:{_T.get('accent_ink', '#ffffff')};
          display:flex;align-items:center;justify-content:center;font-weight:800;font-size:14px">
          {name[:1].upper()}</span>
          <span style="line-height:1.35">
            <b style="font-size:13px">{name}</b>
            <span style="display:block;font:500 10px/1.5 ui-monospace,monospace;
            letter-spacing:.12em;color:{_T.get('t3', '#5c6773')}">{role}</span>
          </span>
        </div>""",
        unsafe_allow_html=True,
    )
    if st.button("退出登录", key="auth_logout", use_container_width=True):
        logout()
    if admin_url:
        st.link_button("管理后台", admin_url, use_container_width=True)


# ---------------- 登录页 ----------------

_STATUS_TEXT = {
    "pending": "等待手机扫码…",
    "scanned": "已扫码，请在手机上点「同意登录」",
    "confirmed": "已确认，正在进入…",
    "consumed": "这次登录已经完成",
    "expired": "二维码已过期，请点「刷新二维码」",
}


def _start_qr() -> dict:
    res = _api("POST", "/api/auth/qr/start") or {}
    st.session_state[_SS_QR] = res
    return res


def _poll_once(ticket: dict) -> None:
    """轮询一次票据状态; 已确认则写入令牌并整页重跑。"""
    res = _api("GET", ticket.get("poll_url", "")) or {}
    status = res.get("status", "")
    if status == "confirmed" and res.get("token"):
        st.session_state[_SS_TOKEN] = res["token"]
        st.session_state.pop(_SS_QR, None)
        st.rerun()
    if status in ("expired", "consumed"):
        st.session_state.pop(_SS_QR, None)
    st.caption(f"状态：{_STATUS_TEXT.get(status, '等待扫码…')}")


if hasattr(st, "fragment"):          # Streamlit ≥1.33: 自动每 2 秒刷新状态
    _poll_live = st.fragment(run_every="2s")(_poll_once)
else:                                # pragma: no cover
    _poll_live = _poll_once


def _console_login_alive(timeout: float = 1.5) -> bool:
    """控制台的登录页(8591)是否可用 —— 不可用就退回本地表单, 免得整站进不去。"""
    try:
        with urllib.request.urlopen(CONSOLE_LOGIN, timeout=timeout) as resp:
            return getattr(resp, "status", 200) == 200
    except Exception:
        return False


def _self_url() -> str:
    """本页地址 —— 交给登录页当回跳目标(保留 ?page=xx 这类参数, 去掉令牌)。

    host 取自请求头, 所以用 127.0.0.1 还是局域网 IP 打开都能原样回来。
    """
    host = ""
    try:
        host = (st.context.headers.get("Host") or "").strip()
    except Exception:
        host = ""
    if not host:
        port = 8501
        try:
            port = int(st.get_option("server.port") or 8501)
        except Exception:
            pass
        host = f"127.0.0.1:{port}"
    try:
        qs = urllib.parse.urlencode([(k, v) for k, v in st.query_params.items() if k != _SS_TOKEN])
    except Exception:
        qs = ""
    return f"http://{host}/" + (f"?{qs}" if qs else "")


_HIDE_CHROME_CSS = """<style>
  /* 未登录时把 Streamlit 自己的外壳收掉, 视觉上就是「打开系统 -> 登录页」 */
  [data-testid="stHeader"], [data-testid="stToolbar"], [data-testid="stDecoration"],
  [data-testid="stStatusWidget"], [data-testid="stSidebar"], #MainMenu, footer
    {display:none !important}
  [data-testid="stAppViewContainer"] > .main {background:transparent}
  .block-container, [data-testid="stAppViewBlockContainer"]{padding:0 !important;max-width:100% !important}
</style>"""


def render_login(*, admin_only: bool = False) -> dict:
    """未登录 -> 整页交给控制台的登录页(用户新做的界面)。

    登录成功后 login.html 按 ?next= 回到本页并带上 ?auth_token=..., 由 _take_query_token()
    收下令牌并抹掉地址栏里的令牌; 8591 没起时退回自带表单。

    跳转用 <meta http-equiv="refresh"> —— 实测 Streamlit 组件 iframe 的 sandbox 没有
    allow-top-navigation, window.top.location 会被浏览器拦掉, 而 st.markdown 里的
    meta refresh 能真正把整页交出去。
    """
    bounced = bool(st.session_state.get(_AUTH_REJECTED))
    if bounced:
        return _render_login_native(
            admin_only=admin_only,
            notice="从登录页带回来的登录状态已失效（可能已注销或过期），请重新登录。",
        )
    if not _console_login_alive():
        return _render_login_native(
            admin_only=admin_only,
            notice=f"登录页（{CONSOLE_LOGIN}）现在打不开，先用这里的表单登录。",
        )

    url = CONSOLE_LOGIN + "?next=" + urllib.parse.quote(_self_url(), safe="")
    if admin_only:
        url += "&why=role"
    st.markdown(_HIDE_CHROME_CSS, unsafe_allow_html=True)
    st.markdown(
        f'<meta http-equiv="refresh" content="0;url={url}">'
        '<div style="font:500 12px/1.8 ui-monospace,monospace;'
        f'color:{_T.get("t3", "#5c6773")};padding:18px 22px">'
        '正在前往登录页… 没有自动跳转？'
        f'<a href="{url}" style="color:{_T.get("accent2", "#1f6fc4")}">点这里</a></div>',
        unsafe_allow_html=True,
    )
    st.stop()
    return {}          # 永远到不了, 仅为类型清晰


def _render_login_native(*, admin_only: bool = False, notice: str = "") -> dict:
    """自带登录表单(账号密码 + 扫码) —— 控制台登录页不可用时的兜底。"""
    st.markdown(
        f"""<div style="max-width:900px">
        <div style="font:600 10px/1.6 ui-monospace,monospace;letter-spacing:.2em;
        color:{_T.get('t3', '#5c6773')};text-transform:uppercase">Sign in to continue</div>
        <h1 style="font-size:26px;margin:6px 0 4px">足球数据分析与 AI 预测系统</h1>
        <p style="color:{_T.get('t2', '#3e4a57')};font-size:13.5px;margin:0">
        请先登录：用账号密码，或用手机扫码（手机点「同意登录」，这台电脑自动进入）。</p>
        </div>""",
        unsafe_allow_html=True,
    )
    if notice:
        st.warning(notice, icon="⚠️")
    if admin_only:
        st.caption("管理后台需要管理员账号（role=admin）。")

    left, right = st.columns([1, 1], gap="large")

    with left:
        with st.form("auth_login_form", clear_on_submit=False):
            st.markdown("#### 账号密码登录")
            username = st.text_input("账号", key="auth_user", placeholder="请输入账号")
            password = st.text_input("密码", key="auth_pwd", type="password",
                                     placeholder="请输入密码")
            remember = st.checkbox("记住我（30 天）", value=True, key="auth_remember")
            submitted = st.form_submit_button("登录", use_container_width=True, type="primary")
        if submitted:
            if not username or not password:
                st.error("请输入账号和密码")
            else:
                res = _api("POST", "/api/auth/login",
                           {"username": username.strip(), "password": password,
                            "remember": remember})
                if res and res.get("token"):
                    st.session_state[_SS_TOKEN] = res["token"]
                    st.session_state.pop(_SS_QR, None)
                    st.rerun()
                elif res is None:
                    st.error(f"连不上后端 {API_ROOT}（请确认 8000 端口已启动）")
                else:
                    st.error(res.get("detail") or "登录失败")

    with right:
        st.markdown("#### 扫码登录")
        ticket = st.session_state.get(_SS_QR) or _start_qr()
        if not ticket.get("qr_id"):
            st.error(f"无法申请二维码（后端 {API_ROOT} 未响应）")
            if st.button("重试", use_container_width=True):
                st.session_state.pop(_SS_QR, None)
                st.rerun()
        else:
            png = _api("GET", ticket.get("image_url", ""), raw=True)
            if png:
                st.image(png, width=196, caption="用手机扫码 → 在手机上点「同意登录」")
            else:
                st.warning("二维码图片加载失败")
            _poll_live(ticket)
            if st.button("刷新二维码", use_container_width=True):
                st.session_state.pop(_SS_QR, None)
                st.rerun()
            st.caption(f"二维码地址（手机需同局域网）：{ticket.get('scan_url', '')}")

    st.caption("账号由管理员创建：python scripts/add_user.py --username <账号>")
    st.stop()
    return {}          # 永远到不了, 仅为类型清晰


def login_gate(*, admin_only: bool = False) -> dict:
    """已登录返回用户字典; 未登录渲染登录页并停住。"""
    user = current_user()
    if user and admin_only and user.get("role") != "admin":
        st.warning(f"当前账号 {user.get('display_name') or user.get('username')} "
                   f"是普通用户，管理后台需要管理员账号。")
        if st.button("退出并换个账号登录"):
            logout()
        st.stop()
    if not user:
        render_login(admin_only=admin_only)
    return user
