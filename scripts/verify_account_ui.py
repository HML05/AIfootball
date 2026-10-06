# -*- coding: utf-8 -*-
"""「账号设置」弹层的浏览器端自检（顶栏头像 → 账号设置）。

验证的是**真点击真上传真保存**，而且跑完不留副作用：
    1) 入口：点头像 → 菜单 → 「账号设置」→ 弹层（role=dialog）+ 三个页签
    2) 头像：本地预览、上传（真发 multipart）、顶栏即时换图、恢复默认、>2 MB 前端拦截
    3) 资料：真实账号名回填、未改动时按钮禁用、改昵称能保存并同步顶栏、
            非法账号名把后端 400 原文显示出来（且不落库）
    4) 密码：本地校验（新密码太短）+ 错的原密码由后端拒绝（原文「原密码不正确」）
    5) 质量：弹层与页面都无横向溢出 / 坏图 / 控制台报错

头像与昵称的写操作最后都会**改回原样**（临时昵称 → 原昵称；上传的头像 → 恢复默认），
所以可以反复跑、不会污染交付截图用的 admin 账号。

用法（需要 API 8000 与前端产物都在）:
    python scripts/verify_account_ui.py                     # 默认 http://127.0.0.1:8000
    python scripts/verify_account_ui.py --base http://127.0.0.1:3000   # 走 vite dev
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _uiauth  # noqa: E402

BASE_DEFAULT = "http://127.0.0.1:8000"
SHOT_DIR = Path(os.environ.get("TEMP", "/tmp")) / "aifootball_view" / "account"

results: list[tuple[str, str, bool]] = []


def check(label: str, ok: bool, detail: str = "") -> bool:
    results.append((label, detail, bool(ok)))
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + (f"  {detail}" if detail else ""))
    return bool(ok)


def _me(base: str) -> dict:
    """当前登录账号的真实资料（用来做「回填是否真实」与跑完复原的基准）。

    `/api/auth/me` 的外层是 `{"ok": true, "user": {...}}`，这里直接返回里面的 user。
    """
    req = urllib.request.Request(f"{base}/api/auth/me", headers=_uiauth.headers())
    with urllib.request.urlopen(req, timeout=20) as r:
        data = json.loads(r.read().decode())
    return data.get("user") or data


def _make_images() -> tuple[Path, Path]:
    """造两张测试图：一张 300×300 真 PNG、一张 >2 MB 的假图（前端按体积拦，不校验内容）。"""
    from PIL import Image

    SHOT_DIR.mkdir(parents=True, exist_ok=True)
    small = SHOT_DIR / "qa_avatar.png"
    img = Image.new("RGB", (300, 300), (46, 74, 120))
    for x in range(300):  # 画个斜条纹，免得是一片纯色看不清是否真的换了图
        for y in range(300):
            if (x + y) % 40 < 20:
                img.putpixel((x, y), (208, 176, 96))
    img.save(small)

    big = SHOT_DIR / "qa_avatar_big.png"
    with open(big, "wb") as f:
        f.write(b"\x89PNG\r\n\x1a\n" + os.urandom(3 * 1024 * 1024))
    return small, big


def _open_account(page) -> bool:
    """点顶栏头像 → 菜单里的「账号设置」。返回弹层是否出现。"""
    page.locator("header button:has(img[alt='avatar'])").first.click()
    page.wait_for_timeout(450)
    page.get_by_role("button", name="账号设置").first.click()
    page.wait_for_timeout(800)
    return page.locator("[role=dialog]").count() == 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default=BASE_DEFAULT)
    ap.add_argument("--headed", action="store_true")
    args = ap.parse_args()
    base = args.base.rstrip("/")

    from playwright.sync_api import sync_playwright

    print("FootballAI 账号设置弹层自检（浏览器）")
    me = _me(base)
    user_id = me.get("user_id")
    origin_name = me.get("display_name") or ""
    origin_avatar = me.get("avatar_url") or ""
    print(f"  当前账号: id={user_id} username={me.get('username')} 昵称={origin_name!r} "
          f"头像={'已上传' if origin_avatar else '默认图'}")
    small_png, big_png = _make_images()

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=not args.headed)
        ctx = _uiauth.new_context(browser, viewport={"width": 1600, "height": 1000})
        errors: list[str] = []
        expect_4xx = [False]   # 负向用例故意打 400，浏览器会记一条 Failed to load resource，不算缺陷
        ctx.on("weberror", lambda e: errors.append(str(e.error)))
        page = ctx.new_page()

        def _on_console(m) -> None:
            if m.type != "error":
                return
            if expect_4xx[0] and "Failed to load resource" in m.text:
                return
            errors.append(m.text)

        page.on("console", _on_console)

        page.goto(f"{base}/?lang=zh&theme=light", wait_until="domcontentloaded")
        page.wait_for_timeout(2500)

        # ---------------------------------------------------------- 1. 入口
        print("\n=== 1. 顶栏头像 → 账号设置 ===")
        avatar_btn = page.locator("header button:has(img[alt='avatar'])").first
        check("顶栏有头像按钮", avatar_btn.count() == 1, "header button > img[alt=avatar]")
        src0 = avatar_btn.locator("img").first.get_attribute("src") or ""
        check("头像有真实地址（默认图或已上传的图）",
              src0.startswith("/images/profile.png") or src0.startswith("/api/auth/avatar/"),
              f"src={src0}")
        check("当前显示与后端状态一致（默认图 / 上传图）",
              (src0.startswith("/api/auth/avatar/")) == bool(origin_avatar), f"avatar_url={origin_avatar or '—'}")

        avatar_btn.click()
        page.wait_for_timeout(450)
        menu = page.inner_text("header")
        check("点头像弹出账号菜单", "账号设置" in menu and "退出登录" in menu, "含「账号设置」「退出登录」")

        # 顶栏的玻璃效果会让它成为 fixed 后代的 containing block：遮罩若留在顶栏里，
        # 点页面空白处关不掉菜单（这是本次顺手修掉的同类 bug，专门断言一下）。
        page.mouse.click(60, 950)
        page.wait_for_timeout(450)
        check("点页面空白处能关掉账号菜单",
              ("退出登录" in page.inner_text("header")) is False, "菜单已收起")
        avatar_btn.click()
        page.wait_for_timeout(450)

        check("再次点头像仍能打开菜单", "账号设置" in page.inner_text("header"))
        page.get_by_role("button", name="账号设置").first.click()
        page.wait_for_timeout(800)
        dlg = page.locator("[role=dialog]")
        check("选择「账号设置」后弹层打开（role=dialog）", dlg.count() == 1)
        head = dlg.inner_text().splitlines()
        check("弹层标题是「账号设置」且带当前账号",
              head and head[0].strip() == "账号设置" and f"@{me.get('username')}" in dlg.inner_text(),
              " · ".join(x.strip() for x in head[:2]))
        for label in ("头像", "资料", "密码"):
            check(f"页签「{label}」在弹层里", dlg.get_by_role("button", name=label).count() >= 1)

        # ---------------------------------------------------------- 2. 头像页
        print("\n=== 2. 头像页：预览 / 上传 / 恢复默认 / 超限拦截 ===")
        preview = dlg.locator("img[alt=avatar]").first
        check("头像页有圆形预览图", preview.count() == 1,
              f"src={(preview.get_attribute('src') or '')[:40]}")
        file_input = dlg.locator("input[type=file]").first
        accept = file_input.get_attribute("accept") or ""
        check("文件选择限定图片类型", "image/png" in accept and "image/jpeg" in accept, accept)
        upload_btn = dlg.get_by_role("button", name="上传头像")
        check("未选文件时「上传头像」是禁用的", upload_btn.is_disabled())
        restore_btn = dlg.get_by_role("button", name="恢复默认头像")
        check("没上传过头像时「恢复默认头像」是禁用的", restore_btn.is_disabled() == (not origin_avatar),
              f"disabled={restore_btn.is_disabled()}")

        file_input.set_input_files(str(small_png))
        page.wait_for_timeout(700)
        check("选图后立刻出现本地预览（blob:）",
              (preview.get_attribute("src") or "").startswith("blob:"),
              f"src={(preview.get_attribute('src') or '')[:24]}…")
        check("显示文件名与体积", "qa_avatar.png" in dlg.inner_text() and "KB" in dlg.inner_text(),
              "qa_avatar.png · xx KB")
        check("选好图后「上传头像」可点", not upload_btn.is_disabled())

        upload_btn.click()
        for _ in range(25):  # 上传后要等接口回包 + 顶栏 re-render
            page.wait_for_timeout(400)
            if "头像已更新" in dlg.inner_text():
                break
        check("上传成功并提示「头像已更新」", "头像已更新" in dlg.inner_text(), "multipart 上传走通")
        page.wait_for_timeout(600)
        src1 = avatar_btn.locator("img").first.get_attribute("src") or ""
        check("顶栏头像换成上传后的地址（带版本号防旧缓存）",
              src1.startswith(f"/api/auth/avatar/{user_id}") and "?v=" in src1, f"src={src1}")
        check("「恢复默认头像」随即可点", not restore_btn.is_disabled())
        page.screenshot(path=str(SHOT_DIR / "account_avatar_uploaded.png"), full_page=False)

        if restore_btn.is_disabled():   # 上传那步已经 FAIL，别让点击超时把后面的检查全带走
            check("点「恢复默认头像」后提示并回到默认图", False, "上传失败 → 恢复按钮仍禁用")
        else:
            restore_btn.click()
            for _ in range(25):
                page.wait_for_timeout(400)
                if "已恢复默认头像" in dlg.inner_text():
                    break
            check("点「恢复默认头像」后提示并回到默认图",
                  "已恢复默认头像" in dlg.inner_text()
                  and (avatar_btn.locator("img").first.get_attribute("src") or "").startswith("/images/profile.png"),
                  "顶栏回到 /images/profile.png")

        file_input.set_input_files(str(big_png))
        page.wait_for_timeout(700)
        big_txt = dlg.inner_text()
        # 超限文案是 limitText() = 「上限 2 MB 3.00 MB → 2 MB」；同时确认没被当成已选文件（无预览、按钮仍禁用、没发请求）
        check("超过 2 MB 的图被前端拦下并给出原因",
              ("3.00 MB" in big_txt and "上限 2 MB" in big_txt) or "over the 2 MB limit" in big_txt,
              "错误文案含实际体积，未发出请求")
        check("超限时「上传头像」仍是禁用的", upload_btn.is_disabled())

        page.keyboard.press("Escape")
        page.wait_for_timeout(600)
        check("Esc 关闭弹层", page.locator("[role=dialog]").count() == 0)

        # ---------------------------------------------------------- 3. 资料页
        print("\n=== 3. 资料页：真实回填 / 校验 / 保存 ===")
        check("重新打开弹层", _open_account(page))
        dlg = page.locator("[role=dialog]")
        dlg.get_by_role("button", name="资料").first.click()
        page.wait_for_timeout(500)
        fields = dlg.locator("form input")
        check("资料页三个字段都在（账号名 / 昵称 / 手机号）", fields.count() == 3, f"{fields.count()} 个输入框")
        check("账号名是后端真实值（不是占位空串）",
              fields.nth(0).input_value() == me.get("username"), f"username={fields.nth(0).input_value()}")
        check("昵称是后端真实值", fields.nth(1).input_value() == origin_name, f"昵称={fields.nth(1).input_value()!r}")
        save_btn = dlg.get_by_role("button", name="保存修改")
        check("没改动时「保存修改」是禁用的（只 PATCH 改动的字段）", save_btn.is_disabled())

        tmp_name = f"QA 临时昵称 {int(time.time()) % 100000}"
        fields.nth(1).fill(tmp_name)
        page.wait_for_timeout(300)
        check("改了昵称后「保存修改」可点", not save_btn.is_disabled())
        save_btn.click()
        for _ in range(20):
            page.wait_for_timeout(400)
            if "资料已保存" in dlg.inner_text():
                break
        check("保存成功并提示「资料已保存」", "资料已保存" in dlg.inner_text())
        page.wait_for_timeout(500)
        check("顶栏昵称随即更新成新值", tmp_name in page.inner_text("header"), tmp_name)
        check("后端也真的落库了（/me 返回新昵称）", (_me(base).get("display_name") or "") == tmp_name,
              "已写库")
        page.screenshot(path=str(SHOT_DIR / "account_profile.png"), full_page=False)

        fields.nth(0).fill("1bad")
        page.wait_for_timeout(300)
        expect_4xx[0] = True     # 下面这条 400 是故意打的
        save_btn.click()
        for _ in range(20):
            page.wait_for_timeout(400)
            if "账号需 3~20 位" in dlg.inner_text():
                break
        check("非法账号名：把后端 400 原文显示在弹层里", "账号需 3~20 位" in dlg.inner_text(),
              "账号需 3~20 位, 以字母开头…")
        check("非法值没有落库（后端仍是原名）", _me(base).get("username") == me.get("username"))

        fields.nth(0).fill(me.get("username"))
        fields.nth(1).fill(origin_name)
        page.wait_for_timeout(300)
        save_btn.click()
        for _ in range(20):
            page.wait_for_timeout(400)
            if "资料已保存" in dlg.inner_text():
                break
        check("昵称改回原值并保存（不留副作用）",
              (_me(base).get("display_name") or "") == origin_name, f"昵称已复原为 {origin_name!r}")

        # ---------------------------------------------------------- 4. 密码页
        print("\n=== 4. 密码页：本地校验 + 后端拒绝 ===")
        expect_4xx[0] = True     # 下面「错的原密码」是故意打的 400
        dlg.get_by_role("button", name="密码").first.click()
        page.wait_for_timeout(500)
        pwds = dlg.locator("form input[type=password]")
        check("密码页有三个密码框（原密码 / 新密码 / 确认）", pwds.count() == 3, f"{pwds.count()} 个")
        check("页面提示了「其它设备会登出」", "其它设备" in dlg.inner_text(), "改完密码只保留本设备")
        pwds.nth(0).fill("whatever")
        page.wait_for_timeout(200)
        dlg.get_by_role("button", name="修改密码").click()
        page.wait_for_timeout(500)
        check("新密码太短：本地就拦下（不发请求）", "新密码至少 6 位" in dlg.inner_text(),
              "本地校验")
        pwds.nth(1).fill("qa-pass-12345")
        pwds.nth(2).fill("qa-pass-12345")
        page.wait_for_timeout(200)
        dlg.get_by_role("button", name="修改密码").click()
        for _ in range(20):
            page.wait_for_timeout(400)
            if "原密码不正确" in dlg.inner_text():
                break
        check("错的原密码：后端拒绝并把原文显示出来", "原密码不正确" in dlg.inner_text(), "400 原密码不正确")
        check("失败时不会出现成功提示", "密码已更新" not in dlg.inner_text())
        check("密码没被改动（原密码仍可用）", _login_ok(base, me.get("username")), "旧密码仍能登录")
        expect_4xx[0] = False

        page.keyboard.press("Escape")
        page.wait_for_timeout(500)

        # ---------------------------------------------------------- 5. 质量
        print("\n=== 5. 页面质量 ===")
        overflow = page.evaluate("document.documentElement.scrollWidth > window.innerWidth + 2")
        check("弹层关闭后页面无横向溢出", not overflow, "scrollWidth <= innerWidth")
        broken = page.evaluate(
            "Array.from(document.images).filter(i => i.complete && i.naturalWidth === 0).length")
        check("没有坏图", broken == 0, f"{broken} 张")
        check("控制台无报错", len(errors) == 0, "; ".join(errors[:2]))

        # ---------------------------------------------------------- 6. 管理端同一个顶栏也能进
        print("\n=== 6. 管理端：顶栏头像同样能开账号设置 ===")
        page.goto(f"{base}/admin?tab=overview&lang=zh&theme=light", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        admin_avatar = page.locator("header button:has(img[alt='avatar'])").first
        check("管理端顶栏也有头像按钮", admin_avatar.count() == 1)
        admin_avatar.click()
        page.wait_for_timeout(450)
        page.get_by_role("button", name="账号设置").first.click()
        page.wait_for_timeout(900)
        admin_dlg = page.locator("[role=dialog]")
        check("管理端也能打开账号设置弹层", admin_dlg.count() == 1)
        check("管理端弹层里三页签齐备",
              all(admin_dlg.get_by_role("button", name=x).count() >= 1 for x in ("头像", "资料", "密码")))
        page.screenshot(path=str(SHOT_DIR / "account_admin.png"), full_page=False)
        page.keyboard.press("Escape")
        page.wait_for_timeout(500)
        check("管理端 Esc 也能关掉弹层", page.locator("[role=dialog]").count() == 0)

        ctx.close()
        browser.close()

    passed = sum(1 for _, _, ok in results if ok)
    print(f"\n结果: {passed} 通过 / {len(results) - passed} 失败  共 {len(results)} 项")
    print(f"截图目录: {SHOT_DIR}")
    return 0 if passed == len(results) else 1


def _login_ok(base: str, username: str) -> bool:
    """用原密码试一次登录：失败才说明密码真的被改了（本脚本不该改密码）。

    密码取 `_uiauth.PWD`（可由 `FA_PWD` 覆盖），不写死在脚本里。
    """
    try:
        return bool(_uiauth.login(base, username=username, password=_uiauth.PWD).get("token"))
    except SystemExit:  # 401 = 原密码不对
        return False


if __name__ == "__main__":
    raise SystemExit(main())
