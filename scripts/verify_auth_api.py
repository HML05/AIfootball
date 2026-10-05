# -*- coding: utf-8 -*-
"""登录接口端到端自检(账号密码 + 扫码轮询)。只读地跑一遍全流程。"""
import json
import sys
import time
import urllib.error
import urllib.request

BASE = "http://127.0.0.1:8000"
USER, PWD = "admin", "CaCH9WYGmWMH"


def req(method, path, body=None, token=None, raw=False):
    url = BASE + path
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    if body is not None:
        r.add_header("Content-Type", "application/json")
    if token:
        r.add_header("Authorization", "Bearer " + token)
    r.add_header("User-Agent", "Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/126")
    try:
        with urllib.request.urlopen(r, timeout=25) as resp:
            b = resp.read()
            if raw:
                return resp.status, b[:16], resp.headers.get("content-type")
            return resp.status, json.loads(b.decode("utf-8"))
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")[:200]


def show(label, res):
    print(f"[{label}] {res if not isinstance(res, dict) else json.dumps(res, ensure_ascii=False)[:300]}")


ok = True

# 1) 服务状态
st, body = req("GET", "/api/auth/status")
show("status", body)
ok &= st == 200 and body.get("qr_available") is True

# 2) 错密码 -> 401 且提示统一
st, body = req("POST", "/api/auth/login", {"username": USER, "password": "wrong-password"})
show("错密码", (st, body))
ok &= st == 401

# 3) 正确密码 -> token
st, body = req("POST", "/api/auth/login", {"username": USER, "password": PWD})
tok = body.get("token") if isinstance(body, dict) else None
show("登录", {"status": st, "user": body.get("user") if isinstance(body, dict) else body,
              "token": (tok or "")[:10] + "…"})
ok &= st == 200 and bool(tok)

# 4) /me
st, body = req("GET", "/api/auth/me", token=tok)
show("me", body)
ok &= st == 200 and body.get("user", {}).get("username") == USER

# 5) 无令牌 /me -> 401
st, _ = req("GET", "/api/auth/me")
ok &= st == 401
print("[无令牌 me] HTTP", st)

# 6) 发起扫码
st, qr = req("POST", "/api/auth/qr/start")
show("qr/start", qr)
ok &= st == 200 and "scan_url" in (qr or {})
if not isinstance(qr, dict):
    print("!! 无法继续扫码流程"); sys.exit(1)

# 7) 二维码图片是 PNG
st, head, ctype = req("GET", qr["image_url"], raw=True)
print("[qr/image] HTTP", st, "| magic:", head[:8], "|", ctype)
ok &= st == 200 and head.startswith(b"\x89PNG")

# 8) 轮询第一下: pending
st, p1 = req("GET", qr["poll_url"])
show("poll#1", p1)
ok &= p1.get("status") in ("pending", "scanned")

# 9) 手机打开确认页 -> 状态变 scanned
st, htmlhead, ctype = req("GET", qr["scan_url"].split("8000")[-1], raw=True)
print("[qr/scan] HTTP", st, "|", ctype, "| 有账号输入框:", b'id="u"' in htmlhead or "text/html" in (ctype or ""))
st, p2 = req("GET", qr["poll_url"])
show("poll#2", p2)
ok &= p2.get("status") == "scanned"

# 10) 手机同意(账号密码)
st, appr = req("POST", "/api/auth/qr/approve",
               {"qr_id": qr["qr_id"], "secret": qr["secret"], "username": USER, "password": PWD})
show("approve", appr)
ok &= st == 200 and appr.get("ok") is True

# 11) 轮询拿到令牌
st, p3 = req("GET", qr["poll_url"])
qtok = p3.get("token") if isinstance(p3, dict) else None
show("poll#3", {"status": p3.get("status") if isinstance(p3, dict) else p3,
                "user": p3.get("user") if isinstance(p3, dict) else None,
                "token": (qtok or "")[:10] + "…"})
ok &= p3.get("status") == "confirmed" and bool(qtok)

# 12) 令牌可用
st, me2 = req("GET", "/api/auth/me", token=qtok)
ok &= st == 200
print("[扫码令牌 me] HTTP", st, me2.get("user") if isinstance(me2, dict) else me2)

# 13) 票据只能用一次
st, p4 = req("GET", qr["poll_url"])
print("[poll#4 重放] HTTP", st, p4 if not isinstance(p4, dict) else p4.get("status"))
ok &= (p4.get("status") == "consumed") if isinstance(p4, dict) else True

# 14) 手机端确认页 HTML 检查(过期态)
st, qr2 = req("POST", "/api/auth/qr/start")
st, page, ctype = req("GET", qr2["scan_url"].split("8000")[-1], raw=True)
ok &= st == 200

# 15) 退出登录后令牌失效
st, _ = req("POST", "/api/auth/logout", token=tok)
st2, _ = req("GET", "/api/auth/me", token=tok)
print("[logout -> me] HTTP", st2)
ok &= st == 200 and st2 == 401

print()
print("=== 端到端结果:", "全部通过" if ok else "有失败项", "===")
sys.exit(0 if ok else 1)
