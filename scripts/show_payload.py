"""把 /api/ui 的返回结构压成可读的骨架（供前端定义类型）。

用法: C:\\Python313\\python.exe scripts/show_payload.py home admin leagues
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

OUT = Path.home() / "AppData/Local/Temp/aifootball_view"


def shape(v, depth: int = 0, key: str = "") -> str:
    pad = "  " * depth
    if isinstance(v, dict):
        lines = [f"{pad}{key}{{"]
        for k, vv in list(v.items())[:40]:
            lines.append(shape(vv, depth + 1, f"{k}: "))
        lines.append(f"{pad}}}")
        return "\n".join(lines)
    if isinstance(v, list):
        if not v:
            return f"{pad}{key}[] (空)"
        head = shape(v[0], depth + 1, "")
        return f"{pad}{key}[{len(v)}] 项, 每项:\n{head}"
    s = repr(v)
    if len(s) > 70:
        s = s[:70] + "…"
    return f"{pad}{key}{s}"


def main() -> int:
    for name in sys.argv[1:] or ["home", "admin"]:
        p = OUT / f"ui_{name}.json"
        if not p.exists():
            print(f"[缺失] {p}")
            continue
        data = json.loads(p.read_text(encoding="utf-8"))
        print(f"\n########## {name} ##########")
        print(shape(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
