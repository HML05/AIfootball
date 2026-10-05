"""列出若干表的列（写文件跑，避免 PowerShell 引号地狱）。

用法: C:\\Python313\\python.exe scripts/db_cols.py tm_player_seasons tm_players ...
不带参数则列出全部表名 + 列数。
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

DB = Path(__file__).resolve().parents[1] / "data" / "database" / "football.db"


def main() -> int:
    con = sqlite3.connect(f"file:{DB.as_posix()}?mode=ro", uri=True)
    names = sys.argv[1:]
    if not names:
        names = [r[0] for r in con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    for n in names:
        cols = [r[1] for r in con.execute(f"PRAGMA table_info({n})")]
        cnt = con.execute(f"SELECT COUNT(*) FROM {n}").fetchone()[0]
        print(f"\n== {n}  ({cnt:,} 行)")
        print("   " + ", ".join(cols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
