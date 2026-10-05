"""按 git 规则核算「仓库里到底会有什么」——本机没装 git，用 pathspec 做等价推演。

用法: python scripts/audit_repo_payload.py [--top 15]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pathspec

ROOT = Path(__file__).resolve().parents[1]
SKIP_DIRS = {"node_modules", ".venv", "venv", "__pycache__", ".git", ".vite"}


def load_specs() -> list[tuple[str, pathspec.PathSpec]]:
    specs = []
    for name, rel in (("root", ".gitignore"), ("webui", "webui/.gitignore")):
        p = ROOT / rel
        if p.exists():
            lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
            specs.append((name, pathspec.PathSpec.from_lines("gitwildmatch", lines)))
    return specs


def main() -> int:
    specs = load_specs()
    tracked: list[Path] = []
    ignored: list[Path] = []

    for p in ROOT.rglob("*"):
        if not p.is_file():
            continue
        rel = p.relative_to(ROOT)
        if any(part in SKIP_DIRS for part in rel.parts):
            continue
        posix = rel.as_posix()
        verdict = "track"
        for name, spec in specs:
            # webui/.gitignore 只管 webui/ 子树
            if name == "webui" and not posix.startswith("webui/"):
                continue
            sub = posix[len("webui/"):] if name == "webui" else posix
            if spec.match_file(sub):
                verdict = "ignore"
        (ignored if verdict == "ignore" else tracked).append(rel)

    total = sum((ROOT / r).stat().st_size for r in tracked)
    print(f"[payload] 会进仓库: {len(tracked)} 个文件 / {total / 1024 / 1024:.1f} MB")
    print(f"[payload] 被忽略:   {len(ignored)} 个文件")

    top = sorted(tracked, key=lambda r: (ROOT / r).stat().st_size, reverse=True)[: int(_arg("--top", "12"))]
    print("\n最大的 12 个会入库文件:")
    for r in top:
        print(f"  {(ROOT / r).stat().st_size / 1024 / 1024:8.2f} MB  {r.as_posix()}")

    must_track = [
        ".env.example", "requirements.txt", "requirements-dev.txt", "start.sh", "README.md",
        ".gitignore", "docs/deploy.md", "deploy/footballai.service", "deploy/nginx.conf.example",
        "webui/dist/index.html", "webui/src/lib/base.ts", "webui/src/lib/auth.ts",
        "webui/src/lib/api.ts", "webui/src/App.tsx", "webui/src/pages/Login.tsx",
        "docs/console/login.html", "docs/console/forgot.html", "docs/console/register.html",
        "src/main.py", "src/api/auth.py", "config/settings.py",
        "tools/console_template.html", "scripts/build_webui.py",
    ]
    must_ignore = [
        ".env", "data/database/football.db", "data/database/football.db-wal",
        "data/database/football.db-shm",
        "data/external/player_performances/player_performances.csv",
        "models/ensemble_v2_v7.joblib", "models/xgb_v2.joblib", "webui/node_modules/.package-lock.json",
        "logs/uvicorn.log",
    ]
    problems = []
    tracked_set = set(tracked)
    for rel in must_track:
        p = ROOT / rel
        if p.exists() and Path(rel) not in tracked_set:
            problems.append(f"应该入库却被忽略: {rel}")
    for rel in must_ignore:
        if Path(rel) in tracked_set:
            problems.append(f"应该忽略却会入库: {rel}")

    big = [r for r in tracked if (ROOT / r).stat().st_size > 90 * 1024 * 1024]
    for r in big:
        problems.append(f"超过 GitHub 100 MB 限制: {r.as_posix()}")

    if problems:
        print("\n[!] 问题:")
        for x in problems:
            print("   -", x)
        return 1
    print("\n[ok] 关键文件该进的都进了、该忽略的都忽略了、没有 >90 MB 的单文件")
    return 0


def _arg(flag: str, default: str) -> str:
    if flag in sys.argv:
        return sys.argv[sys.argv.index(flag) + 1]
    return default


if __name__ == "__main__":
    raise SystemExit(main())
