# -*- coding: utf-8 -*-
"""打印 /api/ui 各端点的返回结构（键 + 样例值，深度受限），供写前端页面时对照。

用法:
    python scripts/api_shapes.py                 # 全部端点
    python scripts/api_shapes.py leagues teams   # 指定端点
"""
from __future__ import annotations

import json
import sys
import urllib.request

BASE = "http://127.0.0.1:8000/api/ui"

ENDPOINTS: dict[str, str] = {
    "home": "/home",
    "admin": "/admin",
    "leagues": "/leagues",
    "league": "/leagues/1",
    "league_pl": "/leagues/2",
    "teams": "/teams?size=3",
    "team": "/teams/57",
    "players": "/players?size=3",
    "player": "/players/1",
    "matches": "/matches?size=3",
    "predictions": "/predictions?size=3",
    "models": "/models",
    "transfers": "/transfers?size=3",
    "reports": "/reports",
    "live": "/live",
}


def shape(v, depth: int = 0, max_depth: int = 3):
    if depth >= max_depth:
        if isinstance(v, list):
            return f"[{len(v)} items]"
        if isinstance(v, dict):
            return "{…}"
        return v
    if isinstance(v, dict):
        return {k: shape(x, depth + 1, max_depth) for k, x in v.items()}
    if isinstance(v, list):
        if not v:
            return []
        return [shape(v[0], depth + 1, max_depth), f"…共 {len(v)} 项"] if len(v) > 1 else [shape(v[0], depth + 1, max_depth)]
    return v


def main() -> int:
    names = sys.argv[1:] or list(ENDPOINTS)
    for n in names:
        path = ENDPOINTS.get(n)
        if not path:
            print(f"!! 未知端点 {n}")
            continue
        try:
            with urllib.request.urlopen(BASE + path, timeout=60) as r:
                data = json.load(r)
        except Exception as exc:  # noqa: BLE001
            print(f"== {n} ({path}) 失败: {exc}\n")
            continue
        print(f"===== {n}  GET {BASE}{path}")
        print(json.dumps(shape(data), ensure_ascii=False, indent=1)[:6000])
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
