"""把「仓库里没有、但跑起来必须有」的数据打成部署数据包。

打包内容（正好是 .gitignore 里那几条被排除的东西）：
    data/database/football.db     业务主库（~159 MB，36 张表 / 181 万行）
    data/database/search.db       中文检索索引（~18 MB，独立库；缺了检索与问答直接不可用）
    models/                       预测模型与评估报告（~11 MB）
    data/processed/*.csv          预测特征输入（~5 MB）

两个细节：
  * 数据库先经 `VACUUM INTO` 复制一份干净副本再打包 —— 运行中的库带 WAL
    （football.db-wal 约 2 MB），直接拷 .db 会丢最近的提交；VACUUM INTO 出来的
    副本自洽、无 WAL，体积也更小。
  * 数据包一次性上传到 GitHub Release 后，Render / 云服务器等云端构建可直接下载，
    **不需要从本机上传大文件**。

用法：
    python scripts/make_data_pack.py                    # 生成到 %TEMP%/aifootball-data-pack-v1.tar.gz
    python scripts/make_data_pack.py -o D:/pack.tar.gz  # 指定输出位置
    python scripts/make_data_pack.py --verify-only URL  # 只检查远端数据包能否解开

生成后会打印 SHA256 与两种上传方式（网页拖拽 / gh 命令行），照做即可。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import sys
import tarfile
import tempfile
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

# 与 Dockerfile 默认值、render.yaml 里的 DATA_PACK_URL 保持一致
DEFAULT_ASSET_NAME = "aifootball-data-pack-v1.tar.gz"
DEFAULT_RELEASE_TAG = "data-pack-v1"
DEFAULT_REPO = "HML05/AIfootball"

# 打包清单：(相对路径, 是否允许缺失)
PACK_ITEMS: list[tuple[str, bool]] = [
    ("data/database/football.db", False),
    ("data/database/search.db", False),
    ("models", False),
    ("data/processed", False),
]

# 这些是 SQLite 库：打包前用 VACUUM INTO 出一份干净副本（避开 WAL 丢数据）
SQLITE_ITEMS = {"data/database/football.db", "data/database/search.db"}


def _human(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024 or unit == "GB":
            return f"{n:.2f} {unit}"
        n /= 1024
    return f"{n:.2f} GB"


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _vacuum_into(src: Path, dst: Path) -> None:
    """用 SQLite 自己的 VACUUM INTO 生成自洽副本（含 WAL 里已提交的数据）。"""
    import sqlite3

    dst.parent.mkdir(parents=True, exist_ok=True)
    if dst.exists():
        dst.unlink()
    con = sqlite3.connect(f"file:{src}?mode=ro", uri=True)
    try:
        con.execute("VACUUM INTO ?", (str(dst),))
    finally:
        con.close()


def _collect(stage: Path) -> tuple[list[tuple[Path, str]], int]:
    """准备要进包的内容；返回 [(实际路径, 包内路径)] 与原始总字节数。"""
    entries: list[tuple[Path, str]] = []
    total = 0
    for rel, _optional in PACK_ITEMS:
        p = BASE_DIR / rel
        if not p.exists():
            print(f"[x] 缺少打包内容：{rel}")
            print("    数据库应先跑 scripts/init_database.py；检索索引跑 scripts/build_search_index.py；")
            print("    模型要先跑训练脚本（models/ 下的 train_*.py）。")
            raise SystemExit(1)
        if rel in SQLITE_ITEMS:
            dst = stage / Path(rel).name
            _vacuum_into(p, dst)
            entries.append((dst, rel))
            total += dst.stat().st_size
            print(f"      {rel} → VACUUM INTO 副本 {_human(dst.stat().st_size)}")
        else:
            entries.append((p, rel))
            if p.is_file():
                total += p.stat().st_size
            else:
                total += sum(f.stat().st_size for f in p.rglob("*") if f.is_file())
    return entries, total


def build(out: Path) -> Path:
    import shutil
    import tempfile

    stage = Path(tempfile.mkdtemp(prefix="fa_pack_"))
    try:
        print(f"[1/3] 准备打包内容（{len(PACK_ITEMS)} 项）")
        entries, raw = _collect(stage)
        out.parent.mkdir(parents=True, exist_ok=True)
        if out.exists():
            out.unlink()
        print(f"      原始合计 {_human(raw)} → {out}")
        with tarfile.open(out, "w:gz", compresslevel=6) as tar:
            for path, arcname in entries:
                tar.add(path, arcname=arcname)
        size = out.stat().st_size
        print(f"[2/3] 完成：{_human(size)}（压缩率 {size / raw:.1%}）")
        print(f"[3/3] SHA256 = {_sha256(out)}")
    finally:
        shutil.rmtree(stage, ignore_errors=True)
    print()
    print("下一步：把这个文件作为一个 Release 资产传上去（二选一）")
    print()
    print("  A. 网页上传（不需要装任何工具）")
    print(f"     1) 打开 https://github.com/{DEFAULT_REPO}/releases/new")
    print(f"     2) Tag 填 {DEFAULT_RELEASE_TAG}，标题填「部署数据包 v1（数据库 + 模型 + 检索索引 + 特征）」")
    print("     3) 把下面这个文件拖进「Attach binaries」区域，点 Publish release")
    print(f"        {out}")
    print()
    print("  B. 命令行（需先 gh auth login，浏览器授权一次）")
    print(f"     gh release create {DEFAULT_RELEASE_TAG} \"{out}\" \\")
    print("       --repo " + DEFAULT_REPO + " \\")
    print("       --title \"部署数据包 v1（数据库 + 模型 + 检索索引 + 特征）\" \\")
    print("       --notes \"云端构建用：data/database/{football,search}.db + models/ + data/processed/\"")
    print()
    print("上传完成后，地址应当是：")
    print(f"  https://github.com/{DEFAULT_REPO}/releases/download/{DEFAULT_RELEASE_TAG}/{DEFAULT_ASSET_NAME}")
    return out


def verify_only(target: str) -> int:
    """列出数据包内容（验证它真的能解开）。

    target 既可以是远端 URL（上传 Release 之后用来确认），也可以是本地文件路径
    （上传之前先自查一遍，别把一个坏包传上去）。
    """
    local = Path(target)
    if local.is_file():
        tmp = local
        print(f"[1/2] 本地文件 {tmp}")
    else:
        import urllib.request

        tmp = Path(tempfile.gettempdir()) / "aifootball-pack-check.tar.gz"
        print(f"[1/2] 下载 {target}")
        try:
            urllib.request.urlretrieve(target, tmp)  # noqa: S310 - 这里是用户显式给定的 URL
        except Exception as exc:  # noqa: BLE001
            print(f"[x] 下载失败：{exc}")
            return 1
    print(f"      {_human(tmp.stat().st_size)}  SHA256 = {_sha256(tmp)}")
    print("[2/2] 内容：")
    try:
        with tarfile.open(tmp, "r:gz") as tar:
            names = tar.getnames()
        files = set(names)
    except Exception as exc:  # noqa: BLE001
        print(f"[x] 解包失败：{exc}")
        return 1
    for n in names:
        print("      " + n)

    # 关键文件是否都在（缺一个就说明这个包不能用来部署）
    required = [
        "data/database/football.db",
        "data/database/search.db",
        "models/xgb_match_predictor.joblib",
        "data/processed/all_matches.csv",
    ]
    missing = [r for r in required if r not in files]
    print(f"      共 {len(names)} 条；关键文件 {len(required) - len(missing)}/{len(required)} 在包里")
    if missing:
        print("[x] 缺少：" + "、".join(missing))
        return 1
    print("[ok] 数据包可用")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="生成/校验部署数据包")
    ap.add_argument("-o", "--out", default=str(Path(tempfile.gettempdir()) / DEFAULT_ASSET_NAME))
    ap.add_argument("--verify-only", metavar="URL或本地文件", help="列出数据包内容并检查关键文件是否齐全")
    args = ap.parse_args()

    if args.verify_only:
        return verify_only(args.verify_only)

    os.environ.setdefault("PYTHONIOENCODING", "utf-8")
    build(Path(args.out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
