"""依赖体检: 扫描源码里的第三方 import, 和 requirements.txt 对照。

用途: 部署前确认 requirements.txt 是完整的 —— 少一个包, 服务器上 pip install 后
启动/某个功能就会 500 或静默失效(例如缺 qrcode 时登录页的"扫码登录"页签直接失效)。

用法:
    python scripts/check_deps.py            # 打印对照结果
    python scripts/check_deps.py --missing  # 只打印缺失(供 CI/脚本判定)

退出码: 有缺失依赖时返回 1, 否则 0。
"""
from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent

# 扫描范围(源码目录)
SCAN_DIRS = ("src", "config", "scripts", "tools", "frontend", "tests")

# 本地模块(不是第三方包)
LOCAL_MODULES = {"src", "config", "scripts", "tools", "frontend", "tests", "_uiauth"}

# 由已声明的包带进来的传递依赖(fastapi/uvicorn 等), 不必单独写在 requirements.txt
TRANSITIVE = {"starlette", "anyio", "sniffio", "click", "h11", "typing_extensions", "idna", "certifi"}

# import 名 -> PyPI 发行名(仅列不一致的)
DIST_ALIAS = {
    "PIL": "pillow",
    "cv2": "opencv-python",
    "sklearn": "scikit-learn",
    "bs4": "beautifulsoup4",
    "dotenv": "python-dotenv",
    "yaml": "pyyaml",
    "dateutil": "python-dateutil",
    "serial": "pyserial",
    "google": "protobuf",
    "jwt": "pyjwt",
    "OpenSSL": "pyopenssl",
    "docx": "python-docx",
}

# 已知的可选/开发期依赖(缺失不算问题), 例如 torch 只被训练脚本用
OPTIONAL = {"torch", "vl_convert", "playwright", "streamlit", "plotly", "altair", "vega_datasets",
            "scipy", "PIL", "matplotlib", "seaborn", "openpyxl", "tqdm",
            # AI Agent(src/agent/*)当前未启用, 且没有任何模块 import 它;
            # 真要启用时再装 langchain / langchain-openai / openai
            "langchain", "langchain_openai", "openai", "langchain_community"}

# 同目录下的本地模块名(例如 frontend/ 里 import theme, blocks, viz —— 不是 PyPI 包)
LOCAL_STEMS = {p.stem for d in SCAN_DIRS for p in (BASE / d).glob("*.py")} if (BASE / "frontend").is_dir() else set()


def iter_imports(path: Path) -> set[str]:
    """返回该文件里出现过的顶层模块名。"""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except (SyntaxError, UnicodeDecodeError):  # 有语法错误的文件跳过, 不阻塞体检
        return set()
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                names.add(a.name.split(".")[0])
        elif isinstance(node, ast.ImportFrom):
            if node.level == 0 and node.module:
                names.add(node.module.split(".")[0])
    return names


def scan() -> dict[str, set[str]]:
    """import 名 -> 用到它的文件集合"""
    found: dict[str, set[str]] = {}
    for d in SCAN_DIRS:
        root = BASE / d
        if not root.is_dir():
            continue
        for p in sorted(root.rglob("*.py")):
            for name in iter_imports(p):
                found.setdefault(name, set()).add(str(p.relative_to(BASE)))
    return found


def requirement_names(files: tuple[str, ...] = ("requirements.txt",)) -> set[str]:
    out: set[str] = set()
    for rel in files:
        req = BASE / rel
        if not req.exists():
            continue
        for line in req.read_text(encoding="utf-8").splitlines():
            line = line.split("#", 1)[0].strip()
            if not line:
                continue
            name = re.split(r"[<>=!\[;]", line, maxsplit=1)[0].strip().lower()
            out.add(name.replace("_", "-"))
    return out


def main() -> int:
    found = scan()
    declared = requirement_names()
    declared_dev = requirement_names(("requirements-dev.txt",))
    # 视觉模块(YOLOv8)的依赖单独一个文件: torch CUDA 版 2 GB+, 只装在 .venv-vision,
    # 主应用与 CI 都不装 —— 所以这里既不能算"缺失", 也不能算 requirements.txt 的一部分。
    declared_vision = requirement_names(("requirements-vision.txt",))
    third_party = {
        name: files
        for name, files in found.items()
        if name not in sys.stdlib_module_names
        and name not in LOCAL_MODULES
        and name not in LOCAL_STEMS
        and name not in TRANSITIVE
        and not name.startswith("_")
    }

    missing: list[tuple[str, str, list[str]]] = []
    dev_only: list[tuple[str, str, list[str]]] = []
    vision_only: list[tuple[str, str, list[str]]] = []
    for name, files in sorted(third_party.items()):
        dist = DIST_ALIAS.get(name, name).lower().replace("_", "-")
        if dist in declared:
            continue
        if dist in declared_dev:
            dev_only.append((name, dist, sorted(files)))
            continue
        if dist in declared_vision:
            vision_only.append((name, dist, sorted(files)))
            continue
        missing.append((name, dist, sorted(files)))

    missing_required = [m for m in missing if m[0] not in OPTIONAL]
    missing_optional = [m for m in missing if m[0] in OPTIONAL]

    print(f"[deps] requirements.txt 声明 {len(declared)} 个包"
          f"(+ requirements-dev.txt {len(declared_dev)} 个, "
          f"+ requirements-vision.txt {len(declared_vision)} 个); "
          f"源码里用到 {len(third_party)} 个第三方模块")
    if missing_required:
        print("\n[!] 缺失(必须补进 requirements.txt 或 requirements-dev.txt):")
        for name, dist, files in missing_required:
            print(f"    - {name}  ->  pip 包名 {dist}")
            for f in files[:3]:
                print(f"        用在 {f}")
    if missing_optional:
        print("\n[i] 未声明但可接受(可选/开发期依赖):")
        for name, dist, files in missing_optional:
            print(f"    - {name} ({dist})  {len(files)} 处")
    if dev_only:
        print("\n[i] 只写在 requirements-dev.txt(生产不装, 自检/训练才用):")
        for name, dist, files in dev_only:
            print(f"    - {name} ({dist})  {len(files)} 处  用在 {files[0]}")
    if vision_only:
        print("\n[i] 只写在 requirements-vision.txt(视觉模块独立环境 .venv-vision, 主应用/CI 不装):")
        for name, dist, files in vision_only:
            print(f"    - {name} ({dist})  {len(files)} 处  用在 {files[0]}")
    if not missing:
        print("[ok] 源码 import 与 requirements 完全对得上")
    if "--missing" in sys.argv:
        return 1 if missing_required else 0
    print("\n[ok] 体检完成" if not missing_required else "\n[!] 体检未通过")
    return 1 if missing_required else 0


if __name__ == "__main__":
    raise SystemExit(main())
