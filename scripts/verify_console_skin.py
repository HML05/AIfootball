# -*- coding: utf-8 -*-
"""控制台（8591）换肤自检：与登录页设计语言是否一致。

检查项（逐页）：
  底色/字色是否回到纸面白与墨黑；面板是否白玻璃 + 大圆角 + 柔投影；
  旧荧光绿 rgb(53,201,141) 是否清零；横向是否溢出；JS 是否报错。
截图输出: %TEMP%\\aifootball_view\\console_skin\\*.png
用法: python scripts/verify_console_skin.py [--no-shot]
"""
import json
import sys
from pathlib import Path
from urllib.request import Request, urlopen

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8591"
OUT = Path.home() / "AppData/Local/Temp/aifootball_view/console_skin"
PAGES = [
    ("index.html#home", "01_用户端_首页概览"),
    ("index.html#leagues", "02_用户端_联赛数据"),
    ("index.html#players", "03_用户端_球员分析"),
    ("index.html#predict", "04_用户端_比赛预测"),
    ("admin.html#overview", "05_后台_数据概览"),
    ("admin.html#browse", "06_后台_数据浏览"),
    ("admin.html#models", "07_后台_模型管理"),
]

PROBE = """() => {
  const rgb = (s) => (s || '').replace(/\\s/g, '');
  const oldGreen = 'rgb(53,201,141)';
  let green = 0, overflow = 0;
  const all = document.querySelectorAll('body *');
  for (const el of all) {
    const cs = getComputedStyle(el);
    for (const prop of ['color', 'backgroundColor', 'borderTopColor', 'borderLeftColor',
                        'boxShadow', 'backgroundImage', 'fill', 'stroke']) {
      const v = rgb(cs[prop]);
      if (v.includes(oldGreen) || v.includes('53,201,141')) green++;
    }
    const r = el.getBoundingClientRect();
    if (r.width > 0 && r.right > window.innerWidth + 2 && el.offsetParent !== null
        && getComputedStyle(el).position !== 'fixed') overflow++;
  }
  const panel = document.querySelector('.panel');
  const pcs = panel ? getComputedStyle(panel) : null;
  const nav = document.querySelector('.nav-item.active');
  return {
    bodyBg: getComputedStyle(document.body).backgroundColor,
    bodyFg: getComputedStyle(document.body).color,
    panelBg: pcs ? pcs.backgroundColor : '',
    panelRadius: pcs ? pcs.borderRadius : '',
    panelShadow: pcs ? pcs.boxShadow.slice(0, 46) : '',
    navActiveColor: nav ? getComputedStyle(nav).color : '',
    title: (document.querySelector('h1') || {}).innerText || '',
    titleFont: (document.querySelector('h1') ? getComputedStyle(document.querySelector('h1')).fontFamily : '').slice(0, 40),
    svgCount: document.querySelectorAll('svg').length,
    green, overflow,
    scrollW: document.documentElement.scrollWidth, winW: window.innerWidth,
  };
}"""


def main() -> int:
    shots = "--no-shot" not in sys.argv
    OUT.mkdir(parents=True, exist_ok=True)
    fails, errors = [], []

    with sync_playwright() as p:
        br = p.chromium.launch(channel="chrome")
        ctx = br.new_context(viewport={"width": 1440, "height": 950})
        pg = ctx.new_page()
        pg.on("pageerror", lambda e: errors.append(str(e)[:120]))

        # 登录一次（闸门 → 登录页 → 回控制台）
        pg.goto(BASE + "/index.html", wait_until="domcontentloaded", timeout=60000)
        pg.wait_for_timeout(4000)
        if "login.html" in pg.url:
            pg.fill("#username, input[type=text]", "admin")
            pg.fill("#password, input[type=password]", "football2026")
            pg.keyboard.press("Enter")
            pg.wait_for_timeout(9000)
        print("登录后:", pg.url)

        for path, name in PAGES:
            pg.goto(f"{BASE}/{path}", wait_until="domcontentloaded", timeout=60000)
            pg.wait_for_timeout(4200)
            r = pg.evaluate(PROBE)
            light = r["bodyBg"] in ("rgb(232, 241, 251)", "rgb(241, 247, 253)")
            dark_ink = r["bodyFg"] in ("rgb(20, 32, 46)",)
            ok = (light and dark_ink and r["green"] == 0
                  and r["scrollW"] <= r["winW"] + 2)
            print(("OK  " if ok else "!!  ") + f"{name}  {path}")
            print(f"      底{r['bodyBg']} 字{r['bodyFg']} 面板{r['panelBg']} 圆角{r['panelRadius']} "
                  f"标题体{r['titleFont'][:22]}")
            print(f"      旧绿残留 {r['green']} · 溢出 {r['overflow']} · svg {r['svgCount']} · "
                  f"sw{ r['scrollW']}/win{r['winW']} · 标题「{r['title'][:12]}」")
            if not ok:
                fails.append(name)
            if shots:
                pg.screenshot(path=str(OUT / f"{name}.png"))

        print(f"\nJS 错误 {len(errors)} 个", errors[:3])

        # 窄屏（DSH 侧边浏览器常见宽度）复核：只关心是否出现横向滚动
        if shots and "--no-narrow" not in sys.argv:
            pg.set_viewport_size({"width": 520, "height": 900})
            for path, name in [PAGES[0], PAGES[-1]]:
                pg.goto(f"{BASE}/{path}", wait_until="domcontentloaded", timeout=60000)
                pg.wait_for_timeout(4000)
                r = pg.evaluate(PROBE)
                ok = r["scrollW"] <= r["winW"] + 2 and r["green"] == 0
                print(("OK  " if ok else "!!  ") + f"520px {name}  sw{r['scrollW']}/win{r['winW']} "
                      f"旧绿{r['green']}")
                if not ok:
                    fails.append("520px " + name)
                pg.screenshot(path=str(OUT / f"520_{name}.png"))
        br.close()

    print("结果:", "全部通过" if not fails and not errors else f"需看一下 -> {fails} JS{len(errors)}")
    return 0 if not fails and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
