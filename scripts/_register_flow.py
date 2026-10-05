"""注册 / 忘记密码「界面」端到端自检(Playwright 真点击)。

跑法:
  C:\\Python313\\python.exe scripts\\_register_flow.py                 # 默认打 http://127.0.0.1:8000
  set WEBUI_BASE=http://127.0.0.1:3000 && C:\\Python313\\python.exe scripts\\_register_flow.py

覆盖:
  1  登录页出现「注册 / 忘记密码」两个入口, 且 href 带上登录页的 ?next=
  2  点注册 → 注册页表单提交 → 写 localStorage.fauth → 跳回 next 指定地址(SPA 正常渲染)
  3  重复注册 → 页面显示后端原文「已被注册」
  4  弱密码 → 页面显示「至少 6 位」
  5  忘记密码第一步: 拿到 6 位重置码并显示在页面上
  6  第二步: 错码 → 「不正确」; 正确码 + 新密码 → 成功提示 → 自动回登录页
  7  用新密码在登录页真实登录 → 进首页; 旧密码 → 报错
  8  收尾: 删掉本次建的测试账号
"""
from __future__ import annotations

import os
import re
import sqlite3
import sys
import time
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")

from playwright.sync_api import sync_playwright          # noqa: E402
import _uiauth                                          # noqa: E402  （默认模式下从后端日志取重置码）

BASE = os.getenv("WEBUI_BASE", "http://127.0.0.1:8000").rstrip("/")
OUT = Path(os.getenv("TEMP", ".")) / "aifootball_view" / "webui"
OUT.mkdir(parents=True, exist_ok=True)
DB = Path(__file__).resolve().parent.parent / "data" / "database" / "football.db"

results: list[tuple[bool, str, str]] = []


def check(name: str, ok: bool, got="") -> None:
    results.append((ok, name, str(got)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<48} {got}")


def new_ctx(b, logged_out=True):
    ctx = b.new_context(viewport={"width": 1600, "height": 1000})
    if logged_out:
        # 只在第一次导航前清一次登录态: add_init_script 每次导航都跑,
        # 不设闸就会把注册成功后写入的 fauth 又擦掉(踩过)
        ctx.add_init_script(
            "try{if(!sessionStorage.getItem('fa_cleared')){"
            "localStorage.removeItem('fauth');sessionStorage.setItem('fa_cleared','1');}}catch(e){}")
    return ctx


def fill(pg, sel, val, timeout=15000):
    pg.wait_for_selector(sel, state="visible", timeout=timeout)
    pg.fill(sel, val)


def msg_of(pg, sel="#rMsg"):
    try:
        return (pg.text_content(sel) or "").strip()
    except Exception:
        return ""


def main() -> int:
    stamp = time.strftime("%m%d%H%M%S")
    user = f"ui_reg_{stamp}"
    pwd0, pwd1 = "ui-pass-2026", "ui-new-2026"
    next_path = "/matches/9012"
    console = f"{BASE}/console"
    errors: list[str] = []
    created = [user]

    print(f"[_register_flow] base={BASE}  测试账号={user}")
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")

        # ---------- 1 登录页两个入口 + next 透传 ----------
        print("\n— 1 登录页入口 —")
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(f"{console}/login.html?next=%2Fmatches%2F9012", wait_until="load")
        pg.wait_for_timeout(1500)
        reg_href = pg.get_attribute("#goRegister", "href") or ""
        forgot_href = pg.get_attribute("#goForgot", "href") or ""
        check("登录页有注册入口", pg.is_visible("#goRegister"), reg_href)
        check("登录页有忘记密码入口", pg.is_visible("#goForgot"), forgot_href)
        check("注册入口带上 next", "next=%2Fmatches%2F9012" in reg_href, reg_href)
        check("忘记密码入口带上 next", "next=%2Fmatches%2F9012" in forgot_href, forgot_href)

        # ---------- 2 点注册 → 提交 → 跳 next ----------
        print("\n— 2 注册成功链路 —")
        pg.click("#goRegister")
        pg.wait_for_url(re.compile(r"register\.html"), timeout=15000)
        check("跳到注册页且带 next", "next=%2Fmatches%2F9012" in pg.url, pg.url.split("/console/")[-1])
        # 注册卡有 ~1s 入场淡入(.step), 太早截图/误判会拍到空卡
        try:
            pg.wait_for_selector("#rUser", timeout=15000)
        except Exception:
            pass
        pg.wait_for_timeout(1400)
        op = pg.evaluate("""() => {
          const c = document.querySelector('.step') || document.querySelector('#rUser');
          return c ? getComputedStyle(c).opacity : null; }""")
        check("注册卡入场后不透明", op == "1", f"opacity={op}")
        fill(pg, "#rUser", user)
        if pg.query_selector("#rName"):
            pg.fill("#rName", "界面自检账号")
        if pg.query_selector("#rPhone"):
            pg.fill("#rPhone", "13900000000")
        fill(pg, "#rPwd", pwd0)
        fill(pg, "#rPwd2", pwd0)
        pg.screenshot(path=str(OUT / "reg_filled.png"))
        pg.click("#rSubmit")
        try:
            pg.wait_for_url(re.compile(r"/matches/9012"), timeout=25000)
            landed = True
        except Exception:
            landed = False
        check(f"注册后跳回 next（{next_path}）", landed, pg.url.replace(BASE, ""))
        # 等 SPA 真的把顶栏渲染出来(冷上下文里 936 KB JS 解析 + /me 校验可能超过 2.5s)
        # 注意: 顶栏导航项是 <button> 不是 <a>, 用 'nav a' 会永远等不到
        try:
            pg.wait_for_selector("nav button, nav a", timeout=25000)
        except Exception:
            pass
        pg.wait_for_timeout(400)
        state = pg.evaluate("""() => {
          let a = null; try { a = JSON.parse(localStorage.getItem('fauth') || 'null'); } catch (e) {}
          return {tok: !!(a && a.token), uname: a && a.user ? a.user.username : null,
                  role: a && a.user ? a.user.role : null,
                  nav: document.querySelectorAll('nav button, nav a').length};
        }""")
        check("注册页写了 localStorage.fauth", state["tok"] is True, f"username={state['uname']}")
        check("新账号角色是 user", state["role"] == "user", state["role"])
        check("跳转后 SPA 正常渲染", state["nav"] > 0, f"顶栏项 = {state['nav']}")
        pg.screenshot(path=str(OUT / "reg_after.png"))
        ctx.close()

        # ---------- 3 重复注册 ----------
        print("\n— 3 重复注册 / 弱密码 —")
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(f"{console}/register.html", wait_until="load")
        pg.wait_for_timeout(1200)
        fill(pg, "#rUser", user)
        fill(pg, "#rPwd", pwd0)
        fill(pg, "#rPwd2", pwd0)
        pg.click("#rSubmit")
        pg.wait_for_timeout(2000)
        m = msg_of(pg)
        check("重复注册提示后端原文", "已被注册" in m, m[:60])
        pg.screenshot(path=str(OUT / "reg_duplicate.png"))
        fill(pg, "#rUser", f"{user}_x")
        fill(pg, "#rPwd", "123")
        fill(pg, "#rPwd2", "123")
        pg.click("#rSubmit")
        pg.wait_for_timeout(1500)
        m = msg_of(pg)
        check("弱密码被拦下", "6" in m and ("位" in m or "least" in m.lower()), m[:60])
        ctx.close()

        # ---------- 4/5 忘记密码两步 ----------
        print("\n— 4 忘记密码 —")
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(f"{console}/forgot.html", wait_until="load")
        pg.wait_for_timeout(1200)
        fill(pg, "#fUser", user)
        pg.click("#fGet")
        pg.wait_for_timeout(2500)
        shown = ""
        for sel in ("#fCodeShow", "#fMsg", "body"):
            txt = (pg.text_content(sel) or "") if pg.query_selector(sel) else ""
            hit = re.search(r"\d{6}", txt)
            if hit:
                shown = hit.group(0)
                break
        if shown:
            # 本机开了 AUTH_RESET_SHOW_CODE=true: 页面上直接有码
            check("页面上出现 6 位重置码", True, f"code={shown}")
        else:
            # 默认(公网安全)模式: 页面不显示码, 只提示向管理员索取
            hint = (pg.text_content("#fCodeShow") or "") if pg.query_selector("#fCodeShow") else ""
            hint = hint or (pg.text_content("body") or "")
            check("默认模式下页面不显示重置码", re.search(r"\d{6}", hint) is None,
                  "页面上没有 6 位数字")
            check("默认模式下提示向管理员索取", "管理员" in hint,
                  hint.strip().splitlines()[0][:40] if hint.strip() else "(空)")
            shown = _uiauth.reset_code_from_log(user)
            check("从服务端日志取到 6 位重置码", len(shown) == 6, f"code={shown}")
        pg.screenshot(path=str(OUT / "forgot_step1.png"))
        # 第二步可见
        step2_vis = pg.is_visible("#fCode") if pg.query_selector("#fCode") else False
        check("自动进入第二步（重置码输入框可见）", step2_vis)
        wrong = "000000" if shown != "000000" else "111111"
        fill(pg, "#fCode", wrong)
        fill(pg, "#fPwd", pwd1)
        fill(pg, "#fPwd2", pwd1)
        pg.click("#fReset")
        pg.wait_for_timeout(2000)
        m = msg_of(pg, "#fMsg2") or msg_of(pg, "#fMsg")
        check("错码提示「不正确」", "不正确" in m, m[:60])
        fill(pg, "#fCode", shown)
        pg.click("#fReset")
        pg.wait_for_timeout(700)
        m = msg_of(pg, "#fMsg2") or msg_of(pg, "#fMsg")
        check("正确码重置成功", ("已重置" in m) or ("重置" in m and "成功" in m), m[:60])
        pg.screenshot(path=str(OUT / "forgot_step2.png"))
        try:
            pg.wait_for_url(re.compile(r"login\.html"), timeout=12000)
            back = True
        except Exception:
            back = False
        check("重置后自动回登录页", back, pg.url.replace(BASE, ""))
        # 直接用接口复核: 旧密码必须失效、新密码必须能用
        r_old = pg.request.post(f"{BASE}/api/auth/login",
                                data={"username": user, "password": pwd0})
        r_new = pg.request.post(f"{BASE}/api/auth/login",
                                data={"username": user, "password": pwd1})
        check("接口复核: 旧密码 401", r_old.status == 401, f"HTTP {r_old.status}")
        check("接口复核: 新密码 200", r_new.status == 200, f"HTTP {r_new.status}")
        ctx.close()

        # ---------- 6 新密码登录 ----------
        print("\n— 5 新密码登录 —")
        ctx = new_ctx(b)
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(f"pageerror: {e}"))
        pg.goto(f"{console}/login.html?next=%2F", wait_until="load")
        pg.wait_for_timeout(1200)
        fill(pg, "#gUser", user)
        fill(pg, "#gPwd", "wrong-pass-000")
        pg.click("#gLogin")
        pg.wait_for_timeout(2500)
        m = (pg.text_content("#gMsg") or "").strip()
        check("错误密码登录被拒", "不正确" in m, m[:60])
        fill(pg, "#gPwd", pwd1)
        pg.click("#gLogin")
        try:
            pg.wait_for_url(re.compile(re.escape(BASE) + r"/(\?|$)"), timeout=25000)
            ok_login = True
        except Exception:
            ok_login = False
        check("新密码登录进首页", ok_login, pg.url.replace(BASE, ""))
        pg.wait_for_timeout(2500)
        body = pg.text_content("body") or ""
        check("登录后首页有真实数据", "12,698" in body,
              "找到 12,698" if "12,698" in body else "未找到")
        pg.screenshot(path=str(OUT / "login_after_reset.png"))
        ctx.close()
        b.close()

    check("全程无页面 JS 报错", not errors, f"{len(errors)} 条 {errors[:2]}")
    cleanup(created)
    ok = sum(1 for r in results if r[0])
    print(f"\n[结果] {ok}/{len(results)} 项通过" + ("" if ok == len(results) else "  ← 有失败项"))
    print(f"[清理] 已删除测试账号 {', '.join(created)}")
    print(f"[截图] {OUT}\\reg_filled.png / reg_after.png / reg_duplicate.png / forgot_step1.png / forgot_step2.png / login_after_reset.png")
    return 0 if ok == len(results) else 1


def cleanup(users: list[str]) -> None:
    c = sqlite3.connect(str(DB))
    try:
        for u in users:
            row = c.execute("select user_id from auth_users where username=?", (u,)).fetchone()
            if row:
                c.execute("delete from auth_sessions where user_id=?", (row[0],))
            c.execute("delete from auth_reset_codes where username=?", (u,))
            c.execute("delete from auth_users where username=?", (u,))
        c.commit()
    finally:
        c.close()


if __name__ == "__main__":
    raise SystemExit(main())
