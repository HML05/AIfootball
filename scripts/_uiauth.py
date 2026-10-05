# -*- coding: utf-8 -*-
"""webui 验收 / 截图脚本的登录态助手（自 2026-10 起 /api/ui/* 需要登录）。

后端闸门在 `src/api/ui.py` 的 `require_ui_login`：除 `/api/ui/public/*` 与
`/api/ui/logo/*` 外都要求 `Authorization: Bearer <token>`，否则 401。
本模块把「登录一次 → 拿到 token → 注入到浏览器 localStorage」这套动作收成一行。

账号来自环境变量（默认与演示账号一致）:
    FA_USER / FA_PWD / FA_API

用法:
    import _uiauth
    ctx = _uiauth.new_context(browser, viewport={"width": 1600, "height": 1000})   # 已登录的 Context
    ctx_public = browser.new_context(...)                                          # 需要看未登录态时用干净的
    urlopen(Request(url, headers=_uiauth.headers()))                               # 直接打接口的脚本
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request

API = os.environ.get("FA_API", "http://127.0.0.1:8000")
USER = os.environ.get("FA_USER", "admin")
PWD = os.environ.get("FA_PWD", "football2026")
# 后端日志（uvicorn 的 stdout 被后台 job 重定向到这里）—— 兜底用
LOG = os.environ.get("FA_API_LOG",
                     os.path.join(os.environ.get("TEMP", "/tmp"), "aifootball_view", "api8000.log"))
# 重置码专用日志（src/api/auth.py 的 _log_reset_code 以 UTF-8 追加写）—— 首选
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
RESET_LOG = os.environ.get("FA_RESET_LOG", os.path.join(ROOT, "logs", "auth_reset.log"))
RESET_CODE_RE = re.compile(r"\[auth\] 重置码 username=(\S+) code=(\d{6})")

_STATE: dict | None = None


def _decode_variants(raw: bytes) -> list[str]:
    """把日志尾巴解成多份文本 —— 日志编码取决于写它的那个 shell，不做假设。

    PowerShell 5.1 的 `>`/`*>` 写 UTF-16LE，pwsh 7 写 UTF-8，旧脚本可能写 GBK，
    还有「同一个文件前半段 UTF-16LE、后半段 UTF-8」的混合情况（重启时换了 shell）。
    """
    out = [raw.decode("utf-8", "replace")]
    for enc in ("utf-8-sig", "utf-16", "gbk"):
        try:
            out.append(raw.decode(enc))
        except (UnicodeDecodeError, UnicodeError):
            pass
    return out


def _codes_in(path: str, username: str, tail: int = 262144) -> list[str]:
    size = os.path.getsize(path)
    with open(path, "rb") as f:
        f.seek(max(0, size - tail))
        raw = f.read()
    hits: list[str] = []
    for text in _decode_variants(raw):
        hits += [m.group(2) for m in RESET_CODE_RE.finditer(text) if m.group(1) == username]
    return hits


def reset_code_from_log(username: str, timeout: float = 20.0,
                        log_path: str | None = None) -> str:
    """取某账号最新一枚重置码（AUTH_RESET_SHOW_CODE=false 时，这是唯一的途径）。

    先看 `logs/auth_reset.log`（后端按 UTF-8 写的专用文件），再兜底读服务端日志尾部
    （多编码尝试）。不按偏移量读 —— 别的进程重启时会把日志截断重写，偏移量会失效。
    取该账号**最后**一条，因为申请新码会让旧码作废。
    """
    paths = [log_path] if log_path else [RESET_LOG, LOG]
    deadline = time.time() + timeout
    while True:
        for path in paths:
            if not os.path.exists(path):
                continue
            try:
                hits = _codes_in(path, username)
            except OSError:
                continue
            if hits:
                return hits[-1]
        if time.time() >= deadline:
            raise SystemExit(
                f"[_uiauth] {timeout:.0f}s 内没找到 {username} 的重置码（看 {paths[0]} 与 {paths[-1]}；"
                f"确认后端已用默认模式重启，且 reset/request 真的打到了 {API}）")
        time.sleep(0.4)



def login(base: str | None = None, username: str | None = None, password: str | None = None, timeout: float = 30.0) -> dict:
    """POST /api/auth/login，返回后端原始响应 {ok, token, user, expires_at}。"""
    url = (base or API).rstrip("/") + "/api/auth/login"
    payload = json.dumps(
        {"username": username or USER, "password": password or PWD, "remember": True}
    ).encode("utf-8")
    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:  # noqa: PERF203
        detail = e.read().decode("utf-8", "replace")[:120]
        raise SystemExit(f"[_uiauth] 登录失败 HTTP {e.code}: {detail}（后端是否已启动？）") from None
    except Exception as e:  # noqa: BLE001
        raise SystemExit(f"[_uiauth] 无法连接 {url}: {e}") from None


def auth_state(payload: dict | None = None) -> dict:
    """构造与 webui/src/lib/auth.ts 的 AuthState 同构的对象（键名必须一致）。"""
    global _STATE
    if payload is None:
        if _STATE is None:
            _STATE = login()
        payload = _STATE
    return {
        "token": payload["token"],
        "user": payload["user"],
        "expires_at": payload.get("expires_at"),
        "remember": True,
    }


def init_script(state: dict | None = None) -> str:
    """给 Playwright 的 context.add_init_script()：每次导航前把登录态写进 localStorage。"""
    literal = json.dumps(json.dumps(auth_state(state), ensure_ascii=False))
    return f"try{{localStorage.setItem('fauth', {literal})}}catch(e){{}}"


def headers(state: dict | None = None) -> dict:
    """直接请求 /api/ui/* 时用的请求头。"""
    return {"Authorization": "Bearer " + auth_state(state)["token"]}


def new_context(browser, **kwargs):
    """建一个已登录的 BrowserContext（进程内只登录一次）。"""
    ctx = browser.new_context(**kwargs)
    ctx.add_init_script(init_script())
    return ctx
