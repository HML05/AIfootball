# -*- coding: utf-8 -*-
"""登录页（设计稿控制台版）四种天气模式 + 扫码页签的目视截图与冒烟检查。

登录页 = docs/console/login.html（由 FastAPI 挂到 /console，见 src/main.py），
它自带昼/暮/夜/雨四套天气（按钮 `button.dn-btn[data-wx=...]`，落在 body[data-wx]），
这里逐一点过去各拍一张，并切到「扫码登录」页签检查二维码图片真的解码成功。

用法: python scripts/_login_shots.py                 # 默认 http://127.0.0.1:8000
      WEBUI_BASE=http://127.0.0.1:8591 python scripts/_login_shots.py
输出: %TEMP%\\aifootball_view\\webui\\console_login_<mode>.png、console_login_qr.png
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = os.environ.get("WEBUI_BASE", "http://127.0.0.1:8000")
LOGIN = "/console/login.html"
OUT = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view" / "webui"
OUT.mkdir(parents=True, exist_ok=True)
MODES = ["day", "dusk", "night", "rain"]


def main() -> int:
    bad = 0
    with sync_playwright() as p:
        b = p.chromium.launch(channel="chrome")
        ctx = b.new_context(viewport={"width": 1600, "height": 1000})
        ctx.add_init_script(
            "try{localStorage.removeItem('fauth');localStorage.setItem('talvex-lang','zh')}catch(e){}"
        )
        pg = ctx.new_page()
        errs: list[str] = []
        pg.on("pageerror", lambda e: errs.append(f"pageerror: {e}"))
        pg.on("console", lambda m: errs.append(f"{m.type}: {m.text}") if m.type == "error" else None)

        pg.goto(f"{BASE}{LOGIN}", wait_until="load", timeout=45000)
        pg.wait_for_timeout(3000)
        print(f"[page] {pg.url}  title={pg.title()!r}")

        for mode in MODES:
            sel = f'button.dn-btn[data-wx="{mode}"]'
            if pg.locator(sel).count() == 0:
                print(f"[{mode}] 找不到天气按钮 {sel}")
                bad += 1
                continue
            pg.click(sel)
            pg.wait_for_timeout(1200)
            cur = pg.evaluate("() => document.body.dataset.wx")
            path = OUT / f"console_login_{mode}.png"
            pg.screenshot(path=str(path))
            ok = cur == mode
            bad += 0 if ok else 1
            print(f"[{mode}] body[data-wx]={cur!r} -> {path.name}")

        # 扫码页签
        if pg.locator("#tabQr").count():
            pg.click("#tabQr")
            pg.wait_for_timeout(4000)
            vis = pg.locator("#paneQr").is_visible()
            nw = pg.evaluate(
                "() => { const i = document.querySelector('#gQrImg'); return i && i.complete ? i.naturalWidth : -1; }"
            )
            state = (pg.inner_text("#gQrState") or "").strip() if pg.locator("#gQrState").count() else ""
            pg.screenshot(path=str(OUT / "console_login_qr.png"))
            ok = vis and isinstance(nw, int) and nw > 0
            bad += 0 if ok else 1
            print(f"[qr] paneQr={vis} 二维码像素宽={nw} 状态={state[:40]!r}")

        real = [e for e in errs if "Failed to load resource" not in e]
        print(f"[console] 错误 {len(real)} 条 {real[:3]}")
        bad += 1 if real else 0
        ctx.close()
        b.close()
    print("-" * 80)
    print(f"截图目录 {OUT}；异常项 {bad}")
    return 0 if bad == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
