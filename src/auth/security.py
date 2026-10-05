"""认证基础件: 口令哈希 / 会话令牌 / 局域网地址探测。

刻意只用标准库:
  · 口令用 pbkdf2_hmac(sha256) + 每用户随机盐, 存成
    ``pbkdf2_sha256$轮数$盐$哈希``; 校验走 hmac.compare_digest 防时序侧信道。
  · 会话令牌用 secrets.token_urlsafe(32) —— 256 位熵, 不可猜。
这样不引入 bcrypt/passlib/jwt 等依赖, 换机器也不会因为装不上包而挂掉。
"""
import hashlib
import hmac
import os
import secrets
import socket

# ---- 参数(集中在这里, 便于审计) ----
PBKDF2_ROUNDS = 120_000          # 约 60ms/次, 登录慢一点但抗爆破
SESSION_TTL_HOURS = 12           # 默认会话时长
SESSION_TTL_REMEMBER_DAYS = 30   # 勾选「记住我」
QR_TTL_SECONDS = 120             # 二维码有效期(手机上会倒计时)
TOKEN_BYTES = 32                 # 会话令牌熵
SECRET_BYTES = 16                # 二维码票据密钥熵


# ---------------- 口令 ----------------

def hash_password(password: str, rounds: int = PBKDF2_ROUNDS) -> str:
    """把明文口令变成可入库的哈希串。"""
    salt = secrets.token_hex(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                             salt.encode("ascii"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${dk.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """校验口令; 任何格式异常都返回 False(不抛异常)。"""
    try:
        algo, rounds, salt, hexhash = stored.split("$")
        if algo != "pbkdf2_sha256":
            return False
        dk = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"),
                                 salt.encode("ascii"), int(rounds))
        return hmac.compare_digest(dk.hex(), hexhash)
    except Exception:
        return False


# ---------------- 令牌 ----------------

def new_token() -> str:
    """会话令牌(给浏览器/客户端持有)。"""
    return secrets.token_urlsafe(TOKEN_BYTES)


def new_qr_id() -> str:
    """票据 id: 32 位十六进制。"""
    return secrets.token_hex(16)


def new_secret() -> str:
    """票据密钥: 轮询与确认都要带, 防止只靠 id 猜。"""
    return secrets.token_urlsafe(SECRET_BYTES)


def mask_token(token: str) -> str:
    """日志里只留头尾, 避免把完整令牌写进日志。"""
    if not token or len(token) < 12:
        return "***"
    return f"{token[:6]}…{token[-4:]}"


# ---------------- 网络 ----------------

def lan_ip() -> str:
    """探测本机在局域网里的地址(手机扫码要用它, 不能用 127.0.0.1)。

    做法是连一个外网地址的 UDP 端口(不会真的发包), 取本地出口网卡的 IP。
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except Exception:
        return "127.0.0.1"
    finally:
        s.close()


def public_base(port: int = 8000) -> str:
    """二维码里要写进手机的地址。

    优先用 AUTH_PUBLIC_BASE 环境变量(例如经过反向代理的域名),
    否则用本机局域网地址 —— 手机必须能访问到这个地址, 否则扫码打不开。
    """
    env = os.getenv("AUTH_PUBLIC_BASE", "").strip()
    if env:
        return env.rstrip("/")
    host = os.getenv("AUTH_PUBLIC_HOST", "").strip() or lan_ip()
    return f"http://{host}:{port}"
