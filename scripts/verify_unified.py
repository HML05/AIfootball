# -*- coding: utf-8 -*-
"""统一入口自检: 一个应用, 按账号角色显示页面。

验收点:
  1) user  角色登录 -> 侧栏只有 8 个前端页面, 且看不到任何后台页面
  2) admin 角色登录 -> 侧栏 14 个页面(8 前端 + 6 后台)
  3) 普通用户用深链 ?page=models 也进不去后台页面
  4) 管理员用深链 ?page=models 能进模型管理
  5) 全程 0 个 JS 错误

用法: python scripts/verify_unified.py [--port 8501]
"""
import json
import re
import sys
import urllib.request
from pathlib import Path

from playwright.sync_api import sync_playwright

PORT = 8501
if "--port" in sys.argv:
    PORT = int(sys.argv[sys.argv.index("--port") + 1])
BASE = f"http://127.0.0.1:{PORT}"
API = "http://127.0.0.1:8000"
OUT = Path.home() / "AppData" / "Local" / "Temp" / "aifootball_view"
OUT.mkdir(parents=True, exist_ok=True)

USER_PAGES = ["首页概览", "联赛数据", "球队分析", "球员分析",
              "比赛详情", "比赛预测", "AI智能分析", "实时比分"]
ADMIN_PAGES = ["数据概览", "数据浏览", "API接口测试", "数据库管理", "数据更新控制", "模型管理"]

fails = []


def check(ok, label, extra=""):
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {extra}" if extra else ""))
    if not ok:
        fails.append(label)


def login(username, password):
    body = json.dumps({"username": username, "password": password}).encode()
    req = urllib.request.Request(f"{API}/api/auth/login", data=body,
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=15) as r:
        data = json.loads(r.read().decode())
    return (data.get("token") or (data.get("data") or {}).get("token"))


def sidebar_text(page):
    """侧栏(抽屉)文本: 无壳模式下侧栏是 display:none, 只能用 textContent 读。"""
    return page.eval_on_selector('[data-testid="stSidebar"]', "el => el.textContent || ''")


def ref_text(page):
    """参照稿 iframe 内的可见文本(首页/数据概览现在是参照稿整页)。"""
    return page.evaluate("""() => {
        const out = [];
        document.querySelectorAll('iframe').forEach(f => {
            try {
                const d = f.contentDocument;
                if (d && d.querySelector('.frame')) { out.push(d.body.innerText || ''); }
            } catch (e) {}
        });
        return out.join('\\n');
    }""")


def checked_nav(page):
    """当前选中的导航项。"""
    return page.evaluate("""() => {
        const el = document.querySelector('[data-testid="stSidebar"] input[type=radio]:checked');
        if (!el) { return ''; }
        const lab = el.closest('label');
        return lab ? (lab.textContent || '').trim() : '';
    }""")


def nav_items(page):
    page.wait_for_timeout(1500)
    # 无壳模式: 老侧栏默认 display:none, 需先点左下浮动按钮打开抽屉(body.nav-open)
    page.evaluate("""() => {
        const f = document.getElementById('nav-fab');
        if (f) { f.click(); }
        else { document.body.classList.add('nav-open'); }
    }""")
    page.wait_for_timeout(900)
    items = page.eval_on_selector_all(
        '[data-testid="stSidebar"] div[role="radiogroup"] label',
        "els => els.map(e => (e.innerText || '').trim())")
    page.evaluate("() => document.body.classList.remove('nav-open')")
    # 侧栏每项现在是「图标 页名」(设计说明第③条): Streamlit 把 :material/x: 渲染成
    # 连字图标, innerText 里剩下的是图标名(dashboard / emoji_events …), 比对时剥掉。
    out = []
    for s in items:
        s = re.sub(r"^[a-z_]+(?:\s+|$)", "", s.strip())
        out.append(s)
    return out


def main():
    tok_user = login("user", "user2026")
    tok_admin = login("admin", "football2026")
    print("令牌:", "user OK" if tok_user else "user 失败", "/", "admin OK" if tok_admin else "admin 失败")
    if not tok_user or not tok_admin:
        sys.exit("登录失败, 无法继续")

    errs = []
    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome", headless=True)
        ctx = br.new_context(viewport={"width": 1600, "height": 1100})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errs.append(str(e)))

        print("1) 普通用户登录")
        pg.goto(f"{BASE}/?auth_token={tok_user}", wait_until="domcontentloaded")
        pg.wait_for_timeout(14000)
        items = nav_items(pg)
        check(len(items) == 8, f"侧栏 8 个页面(实际 {len(items)})", str(items))
        check(not any(a in items for a in ADMIN_PAGES), "看不到后台页面")
        check("普通用户" in sidebar_text(pg), "侧栏角色显示普通用户")
        check("首页概览" in checked_nav(pg) or "首页概览" in ref_text(pg), "落在首页概览")
        pg.screenshot(path=str(OUT / "unified_user.png"))

        print("2) 普通用户深链后台页面")
        pg.goto(f"{BASE}/?page=models&auth_token={tok_user}", wait_until="domcontentloaded")
        pg.wait_for_timeout(14000)
        items = nav_items(pg)
        body = pg.inner_text("body")
        check("模型管理" not in items, "深链页不在导航里")
        check("部署模型评估" not in body, "后台内容未渲染")
        check("首页概览" in checked_nav(pg) or "首页概览" in ref_text(pg), "被送回首页概览")
        pg.screenshot(path=str(OUT / "unified_user_deeplink.png"))

        print("3) 管理员登录")
        pg2 = ctx.new_page()
        pg2.on("pageerror", lambda e: errs.append(str(e)))
        pg2.goto(f"{BASE}/?auth_token={tok_admin}", wait_until="domcontentloaded")
        pg2.wait_for_timeout(14000)
        items2 = nav_items(pg2)
        check(len(items2) == 14, f"侧栏 14 个页面(实际 {len(items2)})")
        check(all(a in items2 for a in ADMIN_PAGES), "6 个后台页面都在", str(items2))
        check("管理员" in sidebar_text(pg2), "侧栏角色显示管理员")
        pg2.screenshot(path=str(OUT / "unified_admin.png"))

        print("4) 管理员深链后台页面")
        pg2.goto(f"{BASE}/?page=models&auth_token={tok_admin}", wait_until="domcontentloaded")
        pg2.wait_for_timeout(14000)
        body2 = pg2.inner_text("body")
        check("部署模型评估" in body2, "模型管理页渲染出来了")
        pg2.screenshot(path=str(OUT / "unified_admin_models.png"))

        print("5) 控制台链接的用户端/后台入口")
        pg3 = ctx.new_page()
        pg3.goto(f"{BASE}/", wait_until="domcontentloaded")
        pg3.wait_for_timeout(9000)
        check("登录" in pg3.inner_text("body") or "SIGN" in pg3.inner_text("body").upper(),
              "未登录时是登录页")

        check(not errs, f"0 个 JS 错误(实际 {len(errs)})", str(errs[:3]))
        br.close()

    print("结果:", "全部通过" if not fails else f"{len(fails)} 项失败 -> {fails}")
    sys.exit(0 if not fails else 1)


if __name__ == "__main__":
    main()
