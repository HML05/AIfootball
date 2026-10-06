"""登录认证接口: 账号密码 + 二维码轮询。

对外路由(前缀 /api/auth):
  POST /login          账号密码登录 -> 会话令牌
  GET  /me             用令牌取当前用户(前端/后台/控制台启动时校验)
  POST /logout         注销当前令牌
  POST /password       修改自己的密码
  POST /register       注册新账号(固定 user 角色, 注册即登录)
  POST /reset/request  忘记密码第一步: 申请一次性重置码
  POST /reset/confirm  忘记密码第二步: 用重置码设新密码
  POST /qr/start       发起一次扫码登录(PC 侧调用) -> 票据 + 二维码地址
  GET  /qr/image       二维码图片(PNG)
  GET  /qr/poll        PC 轮询: 等待手机确认, 确认后一次性取回令牌
  GET  /qr/scan        手机扫码打开的确认页(HTML)
  POST /qr/approve     手机点「同意登录」(需要账号密码或手机上已有的令牌)
  PATCH /profile       改自己的账号名 / 昵称 / 手机号
  POST /avatar         上传或更换自己的头像(图片文件)
  DELETE /avatar       恢复默认头像
  GET  /avatar/{id}    取某个用户的头像图片(没上传过返回 404, 不要求登录)
  GET  /users          用户列表(仅管理员)
  POST /users          新建/重置用户(仅管理员)

设计取舍:
  · 令牌是随机会话串, 服务端存库, 可随时失效 —— 不引入 JWT/第三方依赖。
  · 二维码票据带独立 secret, 轮询与确认都必须带上, 光猜 id 拿不到任何东西。
  · 票据默认 120 秒有效、只能兑换一次(兑换后置 consumed), 防重放。
  · 注册固定成 user 角色(管理端只认 role=admin), 想关掉自助注册用
    AUTH_ALLOW_REGISTER=false; 重置码一次性、有次数与时效上限。
"""
import hashlib
import io
import re
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, Depends, File, Header, HTTPException, Query,
                     Request, UploadFile)
from fastapi.responses import FileResponse, HTMLResponse, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from config.settings import settings
from src.auth import qr_page
from src.auth.security import (QR_TTL_SECONDS, SESSION_TTL_HOURS,
                               SESSION_TTL_REMEMBER_DAYS, hash_password,
                               lan_ip, mask_token, new_qr_id, new_secret,
                               new_token, public_base, verify_password)
from src.database.crud import get_db
from src.database.models import AuthResetCode, AuthSession, AuthUser, QrTicket

router = APIRouter()

# 账号规则: 字母开头, 允许字母/数字/下划线/点/横线, 3~20 位(登录页与注册页同一套提示)
USERNAME_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{2,19}$")
PASSWORD_MIN = 6

try:  # 二维码图片: qrcode 是纯 Python 包(出图用已装的 Pillow)
    import qrcode
    _QR_OK = True
except Exception:                                    # pragma: no cover
    _QR_OK = False


# ---------------- 通用工具 ----------------

def _now() -> datetime:
    return datetime.now()


def _user_dict(u: AuthUser) -> dict:
    return {
        "user_id": u.user_id, "username": u.username,
        "display_name": u.display_name or u.username,
        "role": u.role or "user", "phone": u.phone or "",
        "last_login": u.last_login.strftime("%Y-%m-%d %H:%M:%S") if u.last_login else None,
        # 上传过头像才有值(带修改时间); 空串表示用前端的默认图 /images/profile.png
        "avatar_url": _avatar_url(u),
    }


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else ""


def _ua(request: Request) -> str:
    """把 User-Agent 压成一句人话, 手机确认页上要显示「是不是这台机器」。"""
    raw = request.headers.get("user-agent", "")
    if not raw:
        return "未知设备"
    low = raw.lower()
    os_name = ("Windows" if "windows" in low else
               "macOS" if "mac os" in low or "macintosh" in low else
               "Android" if "android" in low else
               "iPhone/iPad" if "iphone" in low or "ipad" in low else
               "Linux" if "linux" in low else "")
    browser = ("Edge" if "edg/" in low else
               "Chrome" if "chrome" in low else
               "Firefox" if "firefox" in low else
               "Safari" if "safari" in low else "浏览器")
    label = " ".join(x for x in (os_name, browser) if x)
    return (label or raw)[:160]


def _new_session(db: Session, user: AuthUser, request: Request,
                 remember: bool = False) -> AuthSession:
    ttl = (timedelta(days=SESSION_TTL_REMEMBER_DAYS) if remember
           else timedelta(hours=SESSION_TTL_HOURS))
    s = AuthSession(token=new_token(), user_id=user.user_id,
                    created_at=_now(), expires_at=_now() + ttl,
                    user_agent=request.headers.get("user-agent", "")[:200],
                    client_ip=_client_ip(request))
    db.add(s)
    user.last_login = _now()
    db.commit()
    return s


def _purge(db: Session) -> None:
    """顺手清理过期会话与票据(数量很小, 每次登录/轮询跑一次即可)。"""
    now = _now()
    db.query(AuthSession).filter(AuthSession.expires_at < now).delete()
    db.query(QrTicket).filter(QrTicket.expires_at < now - timedelta(minutes=10)).delete()
    db.query(AuthResetCode).filter(AuthResetCode.expires_at < now - timedelta(minutes=10)).delete()
    db.commit()


def current_user(db: Session,
                 authorization: Optional[str] = Header(default=None)) -> Optional[AuthUser]:
    """从 Authorization: Bearer <token> 解析当前用户; 无效返回 None。"""
    if not authorization:
        return None
    token = authorization.split(" ", 1)[1].strip() if " " in authorization else authorization.strip()
    if not token:
        return None
    s = db.query(AuthSession).filter(AuthSession.token == token).first()
    if not s or s.expires_at < _now():
        return None
    u = db.query(AuthUser).filter(AuthUser.user_id == s.user_id).first()
    if not u or not u.is_active:
        return None
    return u


def _login_or_401(db: Session, authorization: Optional[str]) -> AuthUser:
    u = current_user(db, authorization)
    if not u:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    return u


def _admin_or_403(db: Session, authorization: Optional[str]) -> AuthUser:
    u = _login_or_401(db, authorization)
    if (u.role or "user") != "admin":
        raise HTTPException(status_code=403, detail="需要管理员权限")
    return u


# ---------------- 账号密码 ----------------

class LoginIn(BaseModel):
    username: str
    password: str
    remember: bool = False


@router.post("/login", summary="账号密码登录")
def login(payload: LoginIn, request: Request, db: Session = Depends(get_db)):
    _purge(db)
    username = (payload.username or "").strip()
    u = db.query(AuthUser).filter(AuthUser.username == username).first()
    if not u or not u.is_active or not verify_password(payload.password, u.pwd_hash):
        # 账号不存在与密码错误返回同一句话, 不给爆破者额外信息
        raise HTTPException(status_code=401, detail="账号或密码不正确")
    s = _new_session(db, u, request, remember=payload.remember)
    return {"ok": True, "token": s.token, "user": _user_dict(u),
            "expires_at": s.expires_at.strftime("%Y-%m-%d %H:%M:%S")}


@router.get("/me", summary="当前登录用户")
def me(db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)):
    u = _login_or_401(db, authorization)
    return {"ok": True, "user": _user_dict(u)}


@router.post("/logout", summary="退出登录")
def logout(db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)):
    if authorization:
        token = authorization.split(" ", 1)[1].strip() if " " in authorization else authorization.strip()
        db.query(AuthSession).filter(AuthSession.token == token).delete()
        db.commit()
    return {"ok": True}


class PasswordIn(BaseModel):
    old_password: str
    new_password: str


@router.post("/password", summary="修改自己的密码")
def change_password(payload: PasswordIn, db: Session = Depends(get_db),
                    authorization: Optional[str] = Header(default=None)):
    u = _login_or_401(db, authorization)
    if not verify_password(payload.old_password, u.pwd_hash):
        raise HTTPException(status_code=400, detail="原密码不正确")
    if len(payload.new_password or "") < 6:
        raise HTTPException(status_code=400, detail="新密码至少 6 位")
    u.pwd_hash = hash_password(payload.new_password)
    # 改密后其它设备上的旧会话全部失效(当前这枚除外)
    cur = authorization.split(" ", 1)[1].strip() if authorization and " " in authorization else authorization
    db.query(AuthSession).filter(AuthSession.user_id == u.user_id,
                                 AuthSession.token != cur).delete()
    db.commit()
    return {"ok": True, "detail": "密码已更新"}


# ---------------- 注册 ----------------

class RegisterIn(BaseModel):
    username: str
    password: str
    display_name: str = ""
    phone: str = ""


def _check_new_account(username: str, password: str) -> None:
    """注册/重置共用的账号密码规则(不通过就抛 400, 文案直接给页面显示)。"""
    if not USERNAME_RE.match(username):
        raise HTTPException(status_code=400,
                            detail="账号需 3~20 位, 以字母开头, 只能用字母/数字/下划线/点/横线")
    if len(password or "") < PASSWORD_MIN:
        raise HTTPException(status_code=400, detail=f"密码至少 {PASSWORD_MIN} 位")
    if password.strip() != password:
        raise HTTPException(status_code=400, detail="密码首尾不要有空格")


@router.post("/register", summary="注册新账号")
def register(payload: RegisterIn, request: Request, db: Session = Depends(get_db)):
    """开放注册: 新账号一律是 user 角色(管理端要 role=admin, 注册不出来)。

    注册成功直接给一枚会话令牌 —— 和登录一样, 前端可以立刻进系统。
    """
    if not settings.AUTH_ALLOW_REGISTER:
        raise HTTPException(status_code=403, detail="当前未开放自助注册, 请联系管理员开通")
    _purge(db)
    username = (payload.username or "").strip()
    _check_new_account(username, payload.password or "")
    if db.query(AuthUser).filter(AuthUser.username == username).first():
        raise HTTPException(status_code=409, detail="该账号已被注册, 换一个试试")
    u = AuthUser(username=username,
                 display_name=(payload.display_name or "").strip() or username,
                 role="user",                       # 固定: 不接受客户端传角色
                 pwd_hash=hash_password(payload.password),
                 phone=(payload.phone or "").strip() or None,
                 is_active=True, created_at=_now())
    db.add(u)
    db.commit()
    db.refresh(u)
    s = _new_session(db, u, request, remember=False)
    print(f"[auth] 新用户注册: {u.username} (user_id={u.user_id}) from {_client_ip(request)}")
    return {"ok": True, "token": s.token, "user": _user_dict(u),
            "expires_at": s.expires_at.strftime("%Y-%m-%d %H:%M:%S")}


# ---------------- 忘记密码(本机/内网: 无邮件通道, 重置码直接给页面) ----------------

class ResetRequestIn(BaseModel):
    username: str


class ResetConfirmIn(BaseModel):
    username: str
    code: str
    new_password: str


def _new_reset_code() -> str:
    """6 位数字重置码(用 secrets, 不用 random)。"""
    import secrets
    return f"{secrets.randbelow(10 ** 6):06d}"


def _code_hash(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


RESET_LOG = Path(__file__).resolve().parents[2] / "logs" / "auth_reset.log"


def _log_reset_code(username: str, code: str, ttl: int, ip: str) -> None:
    """默认模式下重置码的唯一下发途径: 独立 UTF-8 日志 + 标准输出。

    单开一个文件是为了不受 shell 重定向编码影响 —— PowerShell 5.1 的 `>`/`*>` 会把
    stdout 写成 UTF-16LE, 读日志的人很容易解不出来(本项目就踩过)。
    这一行格式别随意改: scripts/_uiauth.py 与自检脚本按它解析。
    """
    line = (f"[auth] 重置码 username={username} code={code} ttl={ttl}min from={ip} "
            f"at={_now().strftime('%Y-%m-%d %H:%M:%S')}")
    try:
        RESET_LOG.parent.mkdir(parents=True, exist_ok=True)
        with open(RESET_LOG, "a", encoding="utf-8") as f:
            f.write(line + "\n")
    except OSError:
        pass
    # 必须 flush=True —— stdout 被重定向到文件时是块缓冲, 不 flush 管理员要等一整块才看得到
    print(line, flush=True)


@router.post("/reset/request", summary="忘记密码第一步: 申请重置码")
def reset_request(payload: ResetRequestIn, request: Request, db: Session = Depends(get_db)):
    _purge(db)
    username = (payload.username or "").strip()
    u = db.query(AuthUser).filter(AuthUser.username == username).first()
    if not u or not u.is_active:
        raise HTTPException(status_code=404, detail="账号不存在")
    # 同一账号旧的重置码作废(只保留最新一枚)
    db.query(AuthResetCode).filter(AuthResetCode.username == username,
                                   AuthResetCode.used.is_(False)) \
                           .update({"used": True}, synchronize_session=False)
    code = _new_reset_code()
    ttl = max(1, settings.AUTH_RESET_TTL_MINUTES)
    row = AuthResetCode(username=username, code_hash=_code_hash(code),
                        created_at=_now(), expires_at=_now() + timedelta(minutes=ttl),
                        used=False, tries=0, client_ip=_client_ip(request))
    db.add(row)
    db.commit()
    # 这一行是默认模式下唯一的取码途径(管理员看日志转告用户), 格式别随意改。
    _log_reset_code(username, code, ttl, _client_ip(request))
    out = {"ok": True, "username": username, "expires_in": ttl * 60,
           "expires_at": row.expires_at.strftime("%Y-%m-%d %H:%M:%S"),
           "detail": f"重置码已生成, {ttl} 分钟内有效, 请向管理员索取（已记入服务端日志）"}
    # 默认不回码(公网安全): 码只写上面的服务端日志, 由管理员转告用户;
    # 本机自用可设 AUTH_RESET_SHOW_CODE=true 让码直接回显到页面上。
    if settings.AUTH_RESET_SHOW_CODE:
        out["code"] = code
        out["detail"] = f"重置码: {code}（{ttl} 分钟内有效, 请立刻使用）"
    return out


@router.post("/reset/confirm", summary="忘记密码第二步: 用重置码设新密码")
def reset_confirm(payload: ResetConfirmIn, db: Session = Depends(get_db)):
    username = (payload.username or "").strip()
    code = (payload.code or "").strip()
    _check_new_account(username, payload.new_password or "")
    u = db.query(AuthUser).filter(AuthUser.username == username).first()
    if not u or not u.is_active:
        raise HTTPException(status_code=404, detail="账号不存在")
    row = (db.query(AuthResetCode)
             .filter(AuthResetCode.username == username, AuthResetCode.used.is_(False))
             .order_by(AuthResetCode.id.desc()).first())
    if not row or row.expires_at < _now():
        raise HTTPException(status_code=400, detail="重置码不存在或已过期, 请重新获取")
    if (row.tries or 0) >= settings.AUTH_RESET_MAX_TRIES:
        row.used = True
        db.commit()
        raise HTTPException(status_code=400, detail="重置码错误次数过多, 请重新获取")
    if not code or _code_hash(code) != row.code_hash:
        row.tries = (row.tries or 0) + 1
        db.commit()
        left = max(0, settings.AUTH_RESET_MAX_TRIES - row.tries)
        raise HTTPException(status_code=400, detail=f"重置码不正确（还可试 {left} 次）")
    row.used = True
    u.pwd_hash = hash_password(payload.new_password)
    # 密码重置后, 该账号所有旧会话全部失效(可能被他人登录着)
    db.query(AuthSession).filter(AuthSession.user_id == u.user_id).delete()
    db.commit()
    print(f"[auth] 密码已重置: {username} (user_id={u.user_id})")
    return {"ok": True, "detail": "密码已重置, 请用新密码登录"}


# ---------------- 二维码登录 ----------------

@router.post("/qr/start", summary="发起扫码登录(PC 侧)")
def qr_start(request: Request, db: Session = Depends(get_db)):
    _purge(db)
    t = QrTicket(qr_id=new_qr_id(), secret=new_secret(), status="pending",
                 created_at=_now(), expires_at=_now() + timedelta(seconds=QR_TTL_SECONDS),
                 pc_user_agent=_ua(request)[:200], pc_ip=_client_ip(request))
    db.add(t)
    db.commit()
    base = public_base(request.url.port or 8000)
    return {
        "ok": True, "qr_id": t.qr_id, "secret": t.secret,
        "expires_in": QR_TTL_SECONDS,
        "expires_at": t.expires_at.strftime("%H:%M:%S"),
        "scan_url": f"{base}/api/auth/qr/scan?qr_id={t.qr_id}&secret={t.secret}",
        "image_url": f"/api/auth/qr/image?qr_id={t.qr_id}&secret={t.secret}",
        "poll_url": f"/api/auth/qr/poll?qr_id={t.qr_id}&secret={t.secret}",
        "lan_url": base,
    }


def _ticket(db: Session, qr_id: str, secret: str) -> QrTicket:
    t = db.query(QrTicket).filter(QrTicket.qr_id == qr_id,
                                  QrTicket.secret == secret).first()
    if not t:
        raise HTTPException(status_code=404, detail="二维码不存在或已被刷新")
    if t.expires_at < _now() and t.status in ("pending", "scanned"):
        t.status = "expired"
        db.commit()
    return t


@router.get("/qr/image", summary="二维码图片")
def qr_image(request: Request, qr_id: str = Query(...), secret: str = Query(...),
             db: Session = Depends(get_db)):
    t = _ticket(db, qr_id, secret)
    if not _QR_OK:
        raise HTTPException(status_code=503, detail="服务端缺少 qrcode 包, 无法生成二维码")
    base = public_base(request.url.port or 8000)
    url = f"{base}/api/auth/qr/scan?qr_id={t.qr_id}&secret={t.secret}"
    qr = qrcode.QRCode(box_size=8, border=2,
                       error_correction=qrcode.constants.ERROR_CORRECT_M)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#07130d", back_color="#ffffff")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return Response(content=buf.getvalue(), media_type="image/png",
                    headers={"Cache-Control": "no-store"})


@router.get("/qr/poll", summary="PC 轮询扫码状态")
def qr_poll(qr_id: str = Query(...), secret: str = Query(...),
            request: Request = None, db: Session = Depends(get_db)):
    t = _ticket(db, qr_id, secret)
    if t.status == "confirmed" and t.user_id:
        u = db.query(AuthUser).filter(AuthUser.user_id == t.user_id).first()
        if not u or not u.is_active:
            t.status = "expired"
            db.commit()
            return {"ok": True, "status": "expired"}
        s = _new_session(db, u, request, remember=True)
        t.status = "consumed"
        db.commit()
        return {"ok": True, "status": "confirmed", "token": s.token,
                "user": _user_dict(u),
                "expires_at": s.expires_at.strftime("%Y-%m-%d %H:%M:%S")}
    if t.status == "pending":
        t.status = "scanned" if request and request.headers.get("x-qr-scanned") else t.status
    return {"ok": True, "status": t.status,
            "expires_in": max(0, int((t.expires_at - _now()).total_seconds()))}


@router.get("/qr/scan", response_class=HTMLResponse, summary="手机确认页")
def qr_scan(request: Request, qr_id: str = Query(...), secret: str = Query(...),
            db: Session = Depends(get_db)):
    t = _ticket(db, qr_id, secret)
    if t.status == "pending":
        t.status = "scanned"          # 手机已经把页面打开了
        db.commit()
    return HTMLResponse(qr_page.render(qr_id=t.qr_id, secret=t.secret, status=t.status,
                                       pc_ua=_ua_from_ticket(t), pc_ip=t.pc_ip or ""))


def _ua_from_ticket(t: QrTicket) -> str:
    return t.pc_user_agent or "未知设备"


class ApproveIn(BaseModel):
    qr_id: str
    secret: str
    username: Optional[str] = None
    password: Optional[str] = None
    token: Optional[str] = None


@router.post("/qr/approve", summary="手机端同意登录")
def qr_approve(payload: ApproveIn, request: Request, db: Session = Depends(get_db)):
    t = _ticket(db, payload.qr_id, payload.secret)
    if t.status == "expired":
        raise HTTPException(status_code=410, detail="二维码已过期, 请在电脑上刷新后重扫")
    if t.status == "consumed":
        raise HTTPException(status_code=409, detail="这次登录已经完成过了")
    if t.status == "confirmed":
        return {"ok": True, "detail": "已确认, 请回到电脑继续"}

    user = None
    if payload.token:                       # 手机上已登录 -> 直接同意
        row = db.query(AuthSession).filter(AuthSession.token == payload.token).first()
        if row and row.expires_at >= _now():
            user = db.query(AuthUser).filter(AuthUser.user_id == row.user_id).first()
    if user is None:                        # 否则现验一次账号密码
        username = (payload.username or "").strip()
        u = db.query(AuthUser).filter(AuthUser.username == username).first()
        if not u or not u.is_active or not verify_password(payload.password or "", u.pwd_hash):
            raise HTTPException(status_code=401, detail="账号或密码不正确")
        user = u

    t.status = "confirmed"
    t.user_id = user.user_id
    t.confirmed_at = _now()
    db.commit()
    # 兑换逻辑在 PC 侧: /qr/poll 拿到 confirmed 后为电脑新开一条会话。
    # 这里额外给「这台手机」发一枚长效会话(30 天), 下次扫码就能一键同意,
    # 不用每次重新输账号密码; 只在使用账号密码确认时发, 用已有令牌确认则不轮换。
    out = {"ok": True, "detail": "已确认, 请回到电脑继续", "user": _user_dict(user)}
    if not payload.token:
        phone = _new_session(db, user, request, remember=True)
        out["phone_token"] = phone.token
        out["phone_expires_at"] = phone.expires_at.strftime("%Y-%m-%d %H:%M:%S")
    return out


# ---------------- 个人资料与头像(点顶栏头像 → 账号设置) ----------------

# 头像只认这三种落盘扩展名; 带透明的存 png, 照片存 jpg(体积小一个数量级)
AVATAR_EXTS = (".png", ".jpg", ".webp")
AVATAR_MIME = {".png": "image/png", ".jpg": "image/jpeg", ".webp": "image/webp"}
PHONE_RE = re.compile(r"^[0-9+\-() ]{5,20}$")


def _avatar_file(user_id: int) -> Optional[Path]:
    """当前用户的头像文件; 没上传过返回 None(前端回退到 /images/profile.png)。"""
    for ext in AVATAR_EXTS:
        p = settings.AVATAR_DIR / f"{user_id}{ext}"
        if p.exists() and p.stat().st_size > 0:
            return p
    return None


def _avatar_url(u: AuthUser) -> str:
    """头像地址; 带上修改时间, 换完头像浏览器立刻拿到新图而不是旧缓存。"""
    p = _avatar_file(u.user_id)
    return f"/api/auth/avatar/{u.user_id}?v={int(p.stat().st_mtime)}" if p else ""


def _drop_avatars(user_id: int) -> list:
    """删掉该用户的旧头像(换扩展名时旧文件要一起清掉), 返回删掉的文件名。"""
    gone = []
    for ext in AVATAR_EXTS:
        p = settings.AVATAR_DIR / f"{user_id}{ext}"
        if p.exists():
            try:
                p.unlink()
                gone.append(p.name)
            except OSError:
                pass
    return gone


class ProfileIn(BaseModel):
    """只改传进来的字段; 全部不传等于没改动。"""
    username: Optional[str] = None
    display_name: Optional[str] = None
    phone: Optional[str] = None


@router.patch("/profile", summary="修改自己的资料(账号名/昵称/手机号)")
def update_profile(payload: ProfileIn, db: Session = Depends(get_db),
                   authorization: Optional[str] = Header(default=None)):
    u = _login_or_401(db, authorization)
    changed = []

    username = (payload.username or "").strip()
    if username and username != u.username:
        if not USERNAME_RE.match(username):
            raise HTTPException(status_code=400,
                                detail="账号需 3~20 位, 以字母开头, 只能用字母/数字/下划线/点/横线")
        clash = (db.query(AuthUser)
                   .filter(AuthUser.username == username, AuthUser.user_id != u.user_id).first())
        if clash:
            raise HTTPException(status_code=409, detail="该账号名已被占用, 换一个试试")
        u.username = username
        changed.append("账号名")

    if payload.display_name is not None:
        name = payload.display_name.strip()
        if len(name) > 50:
            raise HTTPException(status_code=400, detail="昵称最多 50 个字")
        u.display_name = name or (username or u.username)
        changed.append("昵称")

    if payload.phone is not None:
        phone = payload.phone.strip()
        if phone and not PHONE_RE.match(phone):
            raise HTTPException(status_code=400, detail="手机号格式不对(只能数字/+/-/空格/括号, 5~20 位)")
        u.phone = phone or None
        changed.append("手机号")

    if not changed:
        return {"ok": True, "detail": "资料没有变化", "user": _user_dict(u)}
    db.commit()
    db.refresh(u)
    print(f"[auth] 资料已更新: {u.username} (user_id={u.user_id}) {('/'.join(changed))}")
    return {"ok": True, "detail": "已更新: " + " / ".join(changed), "user": _user_dict(u)}


@router.post("/avatar", summary="上传/更换头像(图片文件, 默认上限 2 MB)")
async def upload_avatar(file: UploadFile = File(...), db: Session = Depends(get_db),
                        authorization: Optional[str] = Header(default=None)):
    """收下原图 → 居中裁成正方形 → 压到 AVATAR_MAX_SIDE → 落盘。

    只做「像不像一张图」的校验: 真正的类型判定交给 Pillow 解码, 不信任浏览器送的
    content-type 与文件名(前端那两样都是可以随便写的)。
    """
    u = _login_or_401(db, authorization)
    limit = max(64 * 1024, settings.AVATAR_MAX_BYTES)
    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="没有收到图片内容")
    if len(raw) > limit:
        raise HTTPException(status_code=413,
                            detail=f"图片太大, 上限 {limit // (1024 * 1024)} MB(可先压缩或换小图)")

    try:
        from PIL import Image, ImageOps
        img = Image.open(io.BytesIO(raw))
        img.load()
    except Exception:
        raise HTTPException(status_code=400, detail="这不像是能识别的图片(png / jpg / webp)")

    img = ImageOps.exif_transpose(img)                 # 手机竖拍照片别倒过来
    side = max(64, settings.AVATAR_MAX_SIDE)
    w, h = img.size
    if w != h:                                          # 头像在前端是正圆, 先居中裁成正方形
        s = min(w, h)
        img = img.crop(((w - s) // 2, (h - s) // 2, (w - s) // 2 + s, (h - s) // 2 + s))
    if img.size != (side, side) and img.width > side:
        img = img.resize((side, side), Image.LANCZOS)   # 只缩不放: 小图放大只会更模糊更占地方

    keep_alpha = img.mode in ("RGBA", "LA") or (img.mode == "P" and "transparency" in img.info)
    _drop_avatars(u.user_id)                            # 换了扩展名, 旧文件不能留
    if keep_alpha:
        dst = settings.AVATAR_DIR / f"{u.user_id}.png"
        img.convert("RGBA").save(dst, "PNG", optimize=True)
    else:
        dst = settings.AVATAR_DIR / f"{u.user_id}.jpg"
        img.convert("RGB").save(dst, "JPEG", quality=88, optimize=True, progressive=True)
    print(f"[auth] 头像已更新: {u.username} (user_id={u.user_id}) "
          f"{len(raw)}B -> {dst.name} {dst.stat().st_size}B")
    return {"ok": True, "detail": "头像已更新", "user": _user_dict(u),
            "bytes": dst.stat().st_size, "source_bytes": len(raw)}


@router.delete("/avatar", summary="恢复默认头像")
def delete_avatar(db: Session = Depends(get_db),
                  authorization: Optional[str] = Header(default=None)):
    u = _login_or_401(db, authorization)
    gone = _drop_avatars(u.user_id)
    return {"ok": True, "removed": gone, "user": _user_dict(u),
            "detail": "已恢复默认头像" if gone else "本来就没有上传过头像"}


@router.get("/avatar/{user_id}", summary="取用户头像图片(没上传过返回 404)")
def get_avatar(user_id: int):
    """故意不要求登录: 前端用 <img src> 直接显示, 带不了 Authorization 头。

    只暴露「这个人上传过的头像图片」本身, 地址里的 user_id 已经是公开信息(用户管理页可见)。
    """
    p = _avatar_file(user_id)
    if not p:
        raise HTTPException(status_code=404, detail="该用户没有自定义头像")
    st = p.stat()
    return FileResponse(p, media_type=AVATAR_MIME.get(p.suffix, "application/octet-stream"),
                        headers={"Cache-Control": "public, max-age=86400",
                                 "ETag": f'W/"{int(st.st_mtime)}-{st.st_size}"'})


# ---------------- 用户管理(管理员) ----------------

class UserIn(BaseModel):
    username: str
    password: str
    display_name: Optional[str] = None
    role: str = "user"
    phone: Optional[str] = None


@router.get("/users", summary="用户列表(管理员)")
def list_users(db: Session = Depends(get_db), authorization: Optional[str] = Header(default=None)):
    _admin_or_403(db, authorization)
    rows = db.query(AuthUser).order_by(AuthUser.user_id).all()
    return {"ok": True, "count": len(rows), "users": [_user_dict(u) for u in rows]}


@router.post("/users", summary="新建/重置用户(管理员)")
def upsert_user(payload: UserIn, db: Session = Depends(get_db),
                authorization: Optional[str] = Header(default=None)):
    _admin_or_403(db, authorization)
    username = (payload.username or "").strip()
    if not username or len(payload.password or "") < 6:
        raise HTTPException(status_code=400, detail="账号不能为空, 密码至少 6 位")
    if payload.role not in ("user", "admin"):
        raise HTTPException(status_code=400, detail="角色只能是 user 或 admin")
    u = db.query(AuthUser).filter(AuthUser.username == username).first()
    created = u is None
    if created:
        u = AuthUser(username=username, created_at=_now())
        db.add(u)
    u.display_name = payload.display_name or u.display_name or username
    u.role = payload.role
    u.phone = payload.phone or u.phone
    u.pwd_hash = hash_password(payload.password)
    u.is_active = True
    db.commit()
    db.refresh(u)
    return {"ok": True, "created": created, "user": _user_dict(u),
            "detail": ("已创建账号 " if created else "已重置账号 ") + username}


@router.get("/status", summary="认证服务状态(不含敏感信息)")
def auth_status(db: Session = Depends(get_db)):
    return {
        "ok": True,
        "qr_available": _QR_OK,
        "users": db.query(AuthUser).count(),
        "active_sessions": db.query(AuthSession).filter(AuthSession.expires_at >= _now()).count(),
        "lan_url": public_base(8000),
        "lan_ip": lan_ip(),
        "session_ttl_hours": SESSION_TTL_HOURS,
        "qr_ttl_seconds": QR_TTL_SECONDS,
    }
