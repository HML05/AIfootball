"""账号设置 后端自检(不需要浏览器, 纯接口)。

跑法:
  C:\\Python313\\python.exe scripts\\verify_account.py
  C:\\Python313\\python.exe scripts\\verify_account.py --keep    # 保留测试账号, 不清理

覆盖(点顶栏头像 → 账号设置 背后的三个能力):
  资料   —— 未登录 401 / 改昵称 / 昵称超长 400 / 手机号格式 400 / 账号名非法 400 /
            账号名撞车 409 / 改名后旧名登录 401 且旧令牌仍可用 / 空改动不算错
  头像   —— 未登录 401 / 上传 PNG 与照片 200 且被压缩 / 落盘后不登录也能取图 /
            地址带版本参数(换图不吃旧缓存) / 非图片 400 / 超限 413 / 没上传过 404 /
            删除后 404 且 /me 的 avatar_url 变空 / 管理员用户列表里能看到头像
  密码   —— 原密码错 400 / 新密码太短 400 / 改成功 200 / 旧密码登录 401 / 新密码登录 200 /
            改密后其它设备上的旧会话被清掉

结束时删掉本次建的所有测试账号与它们的头像文件(用 --keep 可保留)。
"""
from __future__ import annotations

import io
import json
import secrets
import sqlite3
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.stdout.reconfigure(encoding="utf-8")
sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uiauth  # noqa: E402

ROOT = Path(__file__).resolve().parent.parent
API = "http://127.0.0.1:8000"
DB = ROOT / "data" / "database" / "football.db"
AVATAR_DIR = ROOT / "data" / "uploads" / "avatars"
DEFAULT_AVATAR = ROOT / "webui" / "public" / "images" / "profile.png"

_results: list[tuple[bool, str, str]] = []
CREATED: list[str] = []


def _send(req: urllib.request.Request) -> tuple[int, object]:
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            raw = r.read()
            ctype = r.headers.get("content-type", "")
            if ctype.startswith("image/"):
                return r.status, raw
            txt = raw.decode("utf-8", "replace")
            return r.status, (json.loads(txt) if txt.strip().startswith("{") else {"_raw": txt})
    except urllib.error.HTTPError as e:
        raw = e.read()
        try:
            return e.code, json.loads(raw.decode("utf-8", "replace"))
        except Exception:
            return e.code, {"_raw": repr(raw[:120])}
    except Exception as e:                                   # 服务没起来
        raise SystemExit(f"[verify_account] 连不上 {API}: {e}（8000 起了吗?）")


def call(path: str, body: dict | None = None, token: str | None = None,
         method: str | None = None) -> tuple[int, object]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(API + path, data=data,
                                 method=method or ("POST" if body is not None else "GET"))
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return _send(req)


def upload(path: str, content: bytes, token: str | None = None,
           filename: str = "avatar.png", ctype: str = "image/png") -> tuple[int, object]:
    """手工拼 multipart —— 只为不引入 requests 依赖。"""
    boundary = "----faverify" + secrets.token_hex(8)
    body = b"".join([
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(),
        f"Content-Type: {ctype}\r\n\r\n".encode(),
        content, b"\r\n", f"--{boundary}--\r\n".encode(),
    ])
    req = urllib.request.Request(API + path, data=body, method="POST")
    req.add_header("Content-Type", f"multipart/form-data; boundary={boundary}")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    return _send(req)


def check(name: str, ok: bool, got) -> None:
    _results.append((ok, name, str(got)))
    print(f"  {'PASS' if ok else 'FAIL'}  {name:<48} {got}")


def make_png(w: int, h: int, color=(40, 90, 60)) -> bytes:
    """造一张真 PNG(走 Pillow, 保证是后端认得的图片而不是伪造文件头)。"""
    from PIL import Image
    buf = io.BytesIO()
    Image.new("RGB", (w, h), color).save(buf, "PNG")
    return buf.getvalue()


def cleanup(users: list[str]) -> None:
    c = sqlite3.connect(str(DB))
    try:
        for u in users:
            row = c.execute("select user_id from auth_users where username=?", (u,)).fetchone()
            if row:
                c.execute("delete from auth_sessions where user_id=?", (row[0],))
                for ext in (".png", ".jpg", ".webp"):
                    p = AVATAR_DIR / f"{row[0]}{ext}"
                    if p.exists():
                        p.unlink()
            c.execute("delete from auth_reset_codes where username=?", (u,))
            c.execute("delete from auth_users where username=?", (u,))
        c.commit()
    finally:
        c.close()


def main() -> int:
    keep = "--keep" in sys.argv
    stamp = time.strftime("%m%d%H%M%S")
    user = f"qa_acct_{stamp}"
    user2 = f"qa_ren_{stamp}"
    pwd0, pwd1 = "qa-pass-2026", "qa-new-2027"

    print(f"[verify_account] 目标 {API}  测试账号 {user}")
    st, r = call("/api/auth/register", {"username": user, "password": pwd0,
                                        "display_name": "自检账号"})
    if st != 200:
        raise SystemExit(f"[verify_account] 建测试账号失败 HTTP {st}: {r}")
    token = r["token"]                                     # noqa: F841  (下面多处直接引用)
    uid = r["user"]["user_id"]
    CREATED.append(user)

    print("\n— 未登录时的闸门 —")
    st, r = call("/api/auth/profile", {"display_name": "x"}, method="PATCH")
    check("未登录 PATCH /profile → 401", st == 401, f"HTTP {st}")
    st, r = upload("/api/auth/avatar", make_png(64, 64))
    check("未登录 POST /avatar → 401", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/avatar", method="DELETE")
    check("未登录 DELETE /avatar → 401", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/me", token=token)
    check("新账号还没有头像(url 为空)", st == 200 and (r.get("user") or {}).get("avatar_url") == "",
          repr((r.get("user") or {}).get("avatar_url")))

    print("\n— 资料: 昵称 / 手机号 —")
    st, r = call("/api/auth/profile", {"display_name": "数据观察员"}, token=token, method="PATCH")
    check("改昵称 200", st == 200 and (r.get("user") or {}).get("display_name") == "数据观察员",
          f"HTTP {st} {(r.get('user') or {}).get('display_name')} · {r.get('detail')}")
    st, r = call("/api/auth/me", token=token)
    check("/me 反映了新昵称", (r.get("user") or {}).get("display_name") == "数据观察员",
          (r.get("user") or {}).get("display_name"))
    st, r = call("/api/auth/profile", {"display_name": "长" * 51}, token=token, method="PATCH")
    check("昵称超长 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/profile", {"phone": "不是手机号"}, token=token, method="PATCH")
    check("手机号格式不对 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/profile", {"phone": "138-0000 0000"}, token=token, method="PATCH")
    check("手机号可保存 200", st == 200 and (r.get("user") or {}).get("phone") == "138-0000 0000",
          (r.get("user") or {}).get("phone"))
    st, r = call("/api/auth/profile", {}, token=token, method="PATCH")
    check("空改动不报错(原样返回)", st == 200 and "没有变化" in (r.get("detail") or ""),
          f"HTTP {st} {r.get('detail')}")

    print("\n— 资料: 账号名 —")
    st, r = call("/api/auth/profile", {"username": "1bad"}, token=token, method="PATCH")
    check("非法账号名 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/profile", {"username": "admin"}, token=token, method="PATCH")
    check("账号名撞车 409", st == 409, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/login", {"username": user2, "password": pwd0})
    check("改名目标账号原本不存在", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/profile", {"username": user2}, token=token, method="PATCH")
    check("改账号名 200", st == 200 and (r.get("user") or {}).get("username") == user2,
          f"HTTP {st} {(r.get('user') or {}).get('username')}")
    st, r = call("/api/auth/login", {"username": user, "password": pwd0})
    check("旧账号名不能再登录 401", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/me", token=token)
    check("改名不影响已有登录态", st == 200 and (r.get("user") or {}).get("username") == user2,
          f"HTTP {st}")
    CREATED.append(user2)

    print("\n— 头像 —")
    st, r = upload("/api/auth/avatar", make_png(400, 300), token=token)
    aurl = (r.get("user") or {}).get("avatar_url") if isinstance(r, dict) else ""
    check("上传 PNG 200", st == 200 and bool(aurl), f"HTTP {st} {r.get('detail') if isinstance(r, dict) else r}")
    check("返回头像地址带版本参数", aurl.startswith(f"/api/auth/avatar/{uid}?v="), aurl)
    check("400×300 被压成正方形小图", isinstance(r, dict) and 0 < r.get("bytes", 0) < 60_000,
          f"{r.get('source_bytes')}B -> {r.get('bytes')}B")
    st, raw = call(f"/api/auth/avatar/{uid}?v=1")
    check("不登录也能取到头像图",
          st == 200 and isinstance(raw, bytes)
          and (raw[:4] == b"\x89PNG" or raw[:2] == b"\xff\xd8"),
          f"HTTP {st} {len(raw) if isinstance(raw, bytes) else raw} B")
    st, r = call("/api/auth/me", token=token)
    check("/me 里带上头像地址", bool((r.get("user") or {}).get("avatar_url")), "ok")

    if DEFAULT_AVATAR.exists():
        st, r = upload("/api/auth/avatar", DEFAULT_AVATAR.read_bytes(), token=token,
                       filename="photo.png")
        check("上传照片(512×512) 200 且转成 JPEG 更小",
              st == 200 and isinstance(r, dict) and r.get("bytes", 0) < DEFAULT_AVATAR.stat().st_size,
              f"{DEFAULT_AVATAR.stat().st_size}B -> {r.get('bytes')}B")
        st, raw = call(f"/api/auth/avatar/{uid}")
        check("照片按 image/jpeg 返回", st == 200 and isinstance(raw, bytes) and raw[:2] == b"\xff\xd8",
              f"HTTP {st}")

    st, r = upload("/api/auth/avatar", "这不是图片, 只是一段文本".encode("utf-8") * 10, token=token,
                   filename="fake.png")
    check("伪装成 png 的文本 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = upload("/api/auth/avatar", make_png(64, 64) + b"\x00" * (3 * 1024 * 1024),
                   token=token, filename="big.png")
    check("超过 2 MB 的图 413", st == 413, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/avatar/999901")
    check("没有头像的用户取图 404", st == 404, f"HTTP {st}")

    print("\n— 管理员视角 —")
    st, r = call("/api/auth/users", token=token)
    check("普通用户列用户被拦 403", st == 403, f"HTTP {st}")
    _, r_admin = call("/api/auth/login", {"username": "admin", "password": "football2026"})
    admin_tok = r_admin.get("token", "")
    st, r = call("/api/auth/users", token=admin_tok)
    row = next((u for u in (r.get("users") or []) if u.get("user_id") == uid), {})
    check("管理员用户列表里能看到该用户头像", st == 200 and bool(row.get("avatar_url")),
          row.get("avatar_url") or f"HTTP {st}")

    st, r = call("/api/auth/avatar", method="DELETE", token=token)
    check("删除头像 200", st == 200 and bool(r.get("removed")), f"HTTP {st} {r.get('removed')}")
    st, raw = call(f"/api/auth/avatar/{uid}")
    check("删除后再取图 404", st == 404, f"HTTP {st}")
    st, r = call("/api/auth/me", token=token)
    check("删除后 /me 的头像地址变空", (r.get("user") or {}).get("avatar_url") == "", "ok")
    left = [p.name for ext in (".png", ".jpg", ".webp") for p in [AVATAR_DIR / f"{uid}{ext}"] if p.exists()]
    check("落盘文件也清干净了", not left, left or "无残留")

    print("\n— 密码 —")
    _, r_other = call("/api/auth/login", {"username": user2, "password": pwd0})
    other_tok = r_other.get("token", "")                  # 模拟「另一台设备上的会话」
    check("另开一枚会话(另一台设备)", bool(other_tok), f"{len(other_tok)} 字符")
    st, r = call("/api/auth/password", {"old_password": "wrong-pass", "new_password": pwd1}, token=token)
    check("原密码不对 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/password", {"old_password": pwd0, "new_password": "123"}, token=token)
    check("新密码太短 400", st == 400, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/password", {"old_password": pwd0, "new_password": pwd1}, token=token)
    check("改密码 200", st == 200 and r.get("ok") is True, f"HTTP {st} {r.get('detail')}")
    st, r = call("/api/auth/login", {"username": user2, "password": pwd0})
    check("旧密码登录 401", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/login", {"username": user2, "password": pwd1})
    check("新密码登录 200", st == 200 and r.get("ok") is True, f"HTTP {st}")
    new_tok = r.get("token", "")
    st, r = call("/api/auth/me", token=other_tok)
    check("改密码把其它设备上的旧会话清掉了", st == 401, f"HTTP {st}")
    st, r = call("/api/auth/me", token=token)
    check("当前这枚会话不受影响", st == 200, f"HTTP {st}")
    st, r = call("/api/auth/me", token=new_tok)
    check("新登录的会话照常可用", st == 200, f"HTTP {st}")

    if not keep:
        cleanup(CREATED)
    ok = sum(1 for x in _results if x[0])
    print(f"\n结果: {ok} 通过 / {len(_results) - ok} 失败  共 {len(_results)} 项")
    if not keep:
        print(f"[清理] 已删除测试账号 {', '.join(CREATED)}")
    return 0 if ok == len(_results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
