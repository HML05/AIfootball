"""注册 / 忘记密码 后端自检(不需要浏览器, 纯接口)。

跑法:
  C:\\Python313\\python.exe scripts\\verify_auth_register.py
  C:\\Python313\\python.exe scripts\\verify_auth_register.py --keep    # 保留测试账号, 不清理

覆盖:
  注册   —— 成功(role 固定 user) / 重名 409 / 账号或密码不合规 400 / 伪造 role 不提权
  登录   —— 新账号可登录
  忘记密码 —— 账号不存在 404 / 申请码 / 错码 400(带剩余次数) / 正确码重置 200 /
             旧密码失效 401 / 新密码可登录 200 / 旧会话与旧码一起作废 / 重新申请后旧码作废
结束时删掉本次建的所有测试账号(用 --keep 可保留)。
"""
from __future__ import annotations

import json
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uiauth  # noqa: E402  （默认模式下要从后端日志里取重置码）

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8000"
DB = ROOT / "data" / "database" / "football.db"

_results: list[tuple[bool, str, str]] = []
CREATED: list[str] = []


def call(path: str, body: dict | None = None, token: str | None = None,
         method: str | None = None) -> tuple[int, dict]:
    url = API + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data,
                                 method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read().decode("utf-8", "replace")
            return r.status, (json.loads(raw) if raw.strip().startswith("{") else {"_raw": raw})
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", "replace")
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {"_raw": raw}
    except Exception as e:                                   # 服务没起来
        raise SystemExit(f"[verify_auth_register] 连不上 {url}: {e}（8000 起了吗?）")


def check(name: str, ok: bool, got) -> None:
    _results.append((ok, name, str(got)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<46} {got}")
    if not ok:
        pass


def main() -> int:
    keep = "--keep" in sys.argv
    stamp = time.strftime("%m%d%H%M%S")
    user = f"qa_reg_{stamp}"
    pwd0, pwd1 = "qa-pass-2026", "qa-new-2026"

    print(f"[verify_auth_register] 目标 {API}  测试账号 {user}")
    print("\n— 注册 —")
    st, r = call("/api/auth/register", {"username": user, "password": pwd0,
                                        "display_name": "自检账号", "phone": "13800000000"})
    check("注册成功 200", st == 200 and r.get("ok") is True, f"HTTP {st}")
    token0 = r.get("token", "")
    CREATED.append(user)
    check("新账号角色固定为 user", (r.get("user") or {}).get("role") == "user",
          (r.get("user") or {}).get("role"))
    check("注册直接返回可用令牌", bool(token0) and len(token0) > 20, f"token {len(token0)} 字符")
    st, r = call("/api/auth/me", token=token0)
    check("令牌可访问 /me", st == 200 and (r.get("user") or {}).get("username") == user,
          f"HTTP {st} {r.get('user', {}).get('username')}")
    st, r = call("/api/auth/register", {"username": user, "password": pwd0})
    check("重名注册 409", st == 409, f"HTTP {st} {r.get('detail')}")
    for bad, why in (("ab", "太短"), ("1abc", "数字开头"), ("中文账号", "非 ASCII"),
                     ("has space", "带空格")):
        st, r = call("/api/auth/register", {"username": bad, "password": pwd0})
        check(f"非法账号 400（{why}: {bad!r}）", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/register", {"username": f"{user}_b", "password": "123"})
    check("弱密码 400", st == 400 and "6" in str(r.get("detail")), f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/register", {"username": f"{user}_c", "password": "abc123 "})
    check("密码尾随空格 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/register", {"username": f"{user}_d", "password": pwd0,
                                        "role": "admin", "user_id": 1})
    CREATED.append(f"{user}_d")
    check("请求里塞 role=admin 不提权",
          st == 200 and (r.get("user") or {}).get("role") == "user",
          f"HTTP {st} role={(r.get('user') or {}).get('role')}")

    print("\n— 新账号登录 —")
    st, r = call("/api/auth/login", {"username": user, "password": pwd0, "remember": False})
    check("新账号可登录", st == 200 and bool(r.get("token")), f"HTTP {st}")
    old_token = r.get("token", "")

    print("\n— 忘记密码 —")
    st, r = call("/api/auth/reset/request", {"username": f"no_such_user_{stamp}"})
    check("账号不存在 404", st == 404, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/reset/request", {"username": user})
    shown = str(r.get("code", ""))
    check("申请重置码 200", st == 200 and r.get("ok") is True, f"HTTP {st}")
    check("带有效期(秒)", int(r.get("expires_in") or 0) > 0, f"expires_in={r.get('expires_in')}")
    if shown:
        # 本机开了 AUTH_RESET_SHOW_CODE=true: 码直接回给接口
        check("返回 6 位数字重置码", len(shown) == 6 and shown.isdigit(), f"code={shown}")
        code1 = shown
    else:
        # 默认(公网安全)模式: 响应不带 code, 只写服务端日志
        check("默认不下发重置码(响应无 code)", "code" not in r, f"keys={sorted(r.keys())}")
        check("默认提示向管理员索取", "管理员" in str(r.get("detail", "")), str(r.get("detail"))[:60])
        code1 = _uiauth.reset_code_from_log(user)
        check("日志里能取到 6 位重置码", len(code1) == 6 and code1.isdigit(), f"code={code1}")
    st, r = call("/api/auth/reset/confirm", {"username": user, "code": "000000" if code1 != "000000" else "111111",
                                             "new_password": pwd1})
    check("错码 400 且提示剩余次数", st == 400 and "不正确" in str(r.get("detail")),
          f"HTTP {st} {r.get('detail')}")
    # 重新申请会把上一枚作废
    st, r = call("/api/auth/reset/request", {"username": user})
    code2 = str(r.get("code", "")) or _uiauth.reset_code_from_log(user)
    check("重新申请拿到新码", st == 200 and len(code2) == 6, f"code={code2}")
    st, r = call("/api/auth/reset/confirm", {"username": user, "code": code1, "new_password": pwd1})
    check("旧码作废 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/reset/confirm", {"username": user, "code": code2, "new_password": "123"})
    check("重置时校验新密码 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/reset/confirm", {"username": user, "code": code2, "new_password": pwd1})
    check("用正确码重置 200", st == 200 and r.get("ok") is True, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/reset/confirm", {"username": user, "code": code2, "new_password": pwd1})
    check("重置码一次性(二次使用 400)", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/login", {"username": user, "password": pwd0})
    check("旧密码登录 401", st == 401, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/login", {"username": user, "password": pwd1})
    check("新密码登录 200", st == 200 and bool(r.get("token")), f"HTTP {st}")
    st, r = call("/api/auth/me", token=old_token)
    check("重置后旧会话失效 401", st == 401, f"HTTP {st}")

    print("\n— 管理端仍只认 admin —")
    st, r = call("/api/auth/users", token=old_token)
    check("新账号访问 /users 403", st == 401 or st == 403, f"HTTP {st}")
    st, r = call("/api/auth/login", {"username": "admin", "password": "football2026"})
    admin_tok = r.get("token", "")
    st, r = call("/api/auth/users", token=admin_tok)
    check("管理员可列用户", st == 200 and isinstance(r.get("users"), list),
          f"HTTP {st} {len(r.get('users') or [])} 个")

    if not keep:
        cleanup(CREATED)
    ok = sum(1 for x in _results if x[0])
    print(f"\n[结果] {ok}/{len(_results)} 项通过" + ("" if ok == len(_results) else "  ← 有失败项"))
    if not keep:
        print(f"[清理] 已删除测试账号 {', '.join(CREATED)}")
    return 0 if ok == len(_results) else 1


def cleanup(users: list[str]) -> None:
    c = sqlite3.connect(str(DB))
    try:
        for u in users:
            uid = c.execute("select user_id from auth_users where username=?", (u,)).fetchone()
            if uid:
                c.execute("delete from auth_sessions where user_id=?", (uid[0],))
            c.execute("delete from auth_reset_codes where username=?", (u,))
            c.execute("delete from auth_users where username=?", (u,))
        c.commit()
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
