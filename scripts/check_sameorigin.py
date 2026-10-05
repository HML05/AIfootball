"""同源体检：控制台 5 页在「真域名」下会不会把接口打到同源（部署前必跑）。

为什么需要它：在 127.0.0.1:8000 上访问时，新旧两种取址写法算出的 API 都是
http://127.0.0.1:8000，**区分不出来**。本脚本用 Playwright 的 route 把页面挂在
http://example.test 与 https://example.test 上（直接 fulfill，不需要 DNS 或证书），
再断言：页面发出的 /api/ 请求必须与页面同源、URL 里不能出现 ':8000'、
控制台不能有报错。注册/忘记密码页在提交前不发请求，脚本会主动填表并点一次。

用法: python scripts/check_sameorigin.py
退出码: 0=全部同源；1=有跨源或含 :8000 的请求
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

ROOT = Path(__file__).resolve().parents[1]
OUT = Path.home() / "AppData/Local/Temp/aifootball_view/webui"
OUT.mkdir(parents=True, exist_ok=True)

PAGES = [
    ("login.html", "#gUser", {}),
    ("register.html", "#rUser", {"#rUser": "sameorigin_probe", "#rPwd": "probe123456",
                                 "#rPwd2": "probe123456", "__click__": "#rSubmit"}),
    ("forgot.html", "#fUser", {"#fUser": "admin", "__click__": "#fGet"}),
    ("index.html", None, {}),
    ("admin.html", None, {}),
]

STATUS_STUB = '{"ok":true,"users":4,"active_sessions":1,"session_ttl_hours":12,"lan_url":""}'
TEXT = {".html": "text/html; charset=utf-8", ".css": "text/css; charset=utf-8",
        ".js": "application/javascript"}


def run_origin(browser, scheme: str) -> list[dict]:
    origin = f"{scheme}://example.test"
    ctx = browser.new_context(viewport={"width": 1600, "height": 1000}, ignore_https_errors=True)

    def route_console(route):
        name = route.request.url.split("/console/")[-1].split("?")[0]
        f = ROOT / "docs" / "console" / name
        if f.exists() and f.is_file() and f.suffix in TEXT:
            route.fulfill(status=200, content_type=TEXT[f.suffix],
                          body=f.read_text(encoding="utf-8"))
        else:  # 视频/图片/字体直接给空响应，避免真下载
            route.fulfill(status=200, body=b"")

    ctx.route(f"{origin}/console/**", route_console)
    ctx.route(f"{origin}/images/**", lambda r: r.fulfill(status=200, body=b""))
    ctx.route(f"{origin}/api/**", lambda r: r.fulfill(
        status=200, content_type="application/json", body=STATUS_STUB))

    rows = []
    for name, sel, action in PAGES:
        pg = ctx.new_page()
        urls: list[str] = []
        errs: list[str] = []
        pg.on("request", lambda r: urls.append(r.url) if "/api/" in r.url else None)
        pg.on("console", lambda m: errs.append(m.text) if m.type == "error" else None)
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.goto(f"{origin}/console/{name}", wait_until="load")
        pg.wait_for_timeout(1200)
        try:
            for k, v in action.items():
                if k == "__click__":
                    pg.click(v)
                else:
                    pg.fill(k, v)
            if action:
                pg.wait_for_timeout(1200)
        except Exception as exc:  # noqa: BLE001
            errs.append(f"交互失败: {type(exc).__name__}")
        same = [u for u in urls if u.startswith(origin)]
        cross = [u for u in urls if not u.startswith(origin)]
        port = [u for u in urls if ":8000" in u]
        sel_ok = True if not sel else pg.locator(sel).count() == 1
        ok = bool(urls) and not cross and not port and sel_ok and not errs
        rows.append({"scheme": scheme, "page": name, "sel": sel or "-", "sel_ok": sel_ok,
                     "api_reqs": len(urls), "same_origin": len(same), "cross": cross[:2],
                     "contains_8000": port[:2], "errors": errs[:2], "ok": ok})
        print(f"  [{scheme:5}] {name:15} api={len(urls):2} same={len(same):2} "
              f"跨源={cross[:1]} 含:8000={port[:1]} 选择器={sel_ok} 错误={errs[:1]} "
              f"-> {'OK' if ok else 'FAIL'}")
        pg.close()
    ctx.close()
    return rows


def main() -> int:
    rows: list[dict] = []
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        for scheme in ("http", "https"):
            rows += run_origin(b, scheme)
        b.close()
    (OUT / "console_sameorigin_report.json").write_text(
        json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    fails = [f"{r['scheme']}:{r['page']}" for r in rows if not r["ok"]]
    print(f"\n结果: {len(rows) - len(fails)}/{len(rows)} 通过" + (f"  失败: {fails}" if fails else
                                                              " —— 控制台页在真域名下都是同源请求"))
    return 1 if fails else 0


if __name__ == "__main__":
    raise SystemExit(main())
