# -*- coding: utf-8 -*-
"""构建 webui（React 前端）生产包 -> webui/dist

用法:
    python scripts/build_webui.py

为什么要这个脚本:
    1. vite build 期间的 esbuild 会在 %TEMP% 里建临时文件再删除，本机对 %TEMP%
       的删除会被拒绝（`[vite:esbuild-transpile] remove ...: Access is denied.` 导致
       整个构建失败）。把 TEMP/TMP 指到工作区内的 .buildtmp 就绕过了。
    2. 顺带打印产物大小，便于确认 dist 真的更新了。

构建完成后，FastAPI（src/main.py 末尾的 SPAStaticFiles 挂载）会自动在
http://127.0.0.1:8000/ 提供这个 dist。
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEBUI = ROOT / "webui"
TMP = ROOT / ".buildtmp"
NODE = Path(r"D:\nodejs\node.exe")


def main() -> int:
    if not WEBUI.is_dir():
        print(f"[x] 找不到前端工程: {WEBUI}")
        return 1
    TMP.mkdir(exist_ok=True)

    env = dict(os.environ)
    env["TEMP"] = str(TMP)
    env["TMP"] = str(TMP)

    vite = WEBUI / "node_modules" / "vite" / "bin" / "vite.js"
    if not vite.is_file():
        print(f"[x] 找不到 vite: {vite}（先在 webui 里 npm install）")
        return 1

    cmd = [str(NODE), str(vite), "build"]
    print("[build]", " ".join(cmd), f"(TEMP={TMP})")
    proc = subprocess.run(cmd, cwd=str(WEBUI), env=env)
    if proc.returncode != 0:
        print(f"[x] 构建失败，退出码 {proc.returncode}")
        return proc.returncode

    dist = WEBUI / "dist"
    files = sorted(dist.rglob("*"))
    files = [f for f in files if f.is_file()]
    total = sum(f.stat().st_size for f in files)
    print(f"[ok] dist: {len(files)} 个文件 / {total / 1024 / 1024:.2f} MB")
    for f in files:
        if f.suffix in {".js", ".css", ".html"}:
            print(f"     {f.relative_to(dist)}  {f.stat().st_size / 1024:.1f} KB")

    shutil.rmtree(TMP, ignore_errors=True)
    print("[ok] 已可访问 http://127.0.0.1:8000/  (FastAPI 提供 dist + /api/ui/*)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
