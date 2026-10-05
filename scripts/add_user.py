# -*- coding: utf-8 -*-
"""创建 / 重置登录账号。

用法(在项目根目录执行):
    python scripts/add_user.py --list
    python scripts/add_user.py --username admin --role admin            # 自动生成随机密码
    python scripts/add_user.py --username admin --password 你的密码 --name 管理员

不传 --password 时会生成一个 12 位随机密码并打印出来, 请立即抄走 ——
数据库里只存 pbkdf2 哈希, 事后无法反推。
"""
import argparse
import secrets
import string
import sys
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.auth.security import hash_password                      # noqa: E402
from src.database.crud import SessionLocal, init_db              # noqa: E402
from src.database.models import AuthUser                         # noqa: E402


def gen_password(n: int = 12) -> str:
    """生成易抄写但足够强的密码(去掉了 0/O/1/l/I 这些看错的字符)。"""
    alphabet = "".join(c for c in string.ascii_letters + string.digits
                       if c not in "0O1lI")
    return "".join(secrets.choice(alphabet) for _ in range(n))


def main() -> int:
    ap = argparse.ArgumentParser(description="创建或重置登录账号")
    ap.add_argument("--username", "-u", default="admin", help="账号(默认 admin)")
    ap.add_argument("--password", "-p", default="", help="密码(不填则随机生成)")
    ap.add_argument("--name", default="", help="显示名")
    ap.add_argument("--role", default="admin", choices=["admin", "user"], help="角色")
    ap.add_argument("--phone", default="", help="手机号(可选, 预留)")
    ap.add_argument("--list", action="store_true", help="只列出已有账号")
    args = ap.parse_args()

    init_db()                       # 确保表存在(首次运行会建表)
    db = SessionLocal()
    try:
        if args.list:
            rows = db.query(AuthUser).order_by(AuthUser.user_id).all()
            if not rows:
                print("还没有任何账号。用 python scripts/add_user.py --username admin 创建一个。")
                return 0
            print(f"{'ID':<4}{'账号':<16}{'显示名':<14}{'角色':<8}{'状态':<6}最后登录")
            for u in rows:
                print(f"{u.user_id:<4}{u.username:<16}{(u.display_name or ''):<14}"
                      f"{(u.role or 'user'):<8}{'启用' if u.is_active else '停用':<6}"
                      f"{u.last_login.strftime('%Y-%m-%d %H:%M') if u.last_login else '—'}")
            return 0

        username = (args.username or "").strip()
        if not username:
            print("账号不能为空", file=sys.stderr)
            return 2
        password = args.password or gen_password()
        if len(password) < 6:
            print("密码至少 6 位", file=sys.stderr)
            return 2

        u = db.query(AuthUser).filter(AuthUser.username == username).first()
        created = u is None
        if created:
            u = AuthUser(username=username, created_at=datetime.now())
            db.add(u)
        u.display_name = args.name or u.display_name or username
        u.role = args.role
        u.phone = args.phone or u.phone
        u.pwd_hash = hash_password(password)
        u.is_active = True
        db.commit()
        db.refresh(u)

        print(("已创建账号" if created else "已重置账号") + f": {username} (ID {u.user_id}, 角色 {u.role})")
        if not args.password:
            print(f"随机密码: {password}")
        print("现在可以用它登录 http://127.0.0.1:8591 或 http://127.0.0.1:8501")
        return 0
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())
