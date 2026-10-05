# -*- coding: utf-8 -*-
"""盘点 football.db: 每张表的行数与列(含类型/示例值前 3 个), 并扫描 models 目录。

输出: %TEMP%\\aifootball_view\\db_schema.txt (完整) + 控制台精简版(表名/行数/列名)。
"""
import os
import sqlite3
import sys
from pathlib import Path

DB = Path(r"D:\AIfootball\data\database\football.db")
MODELS = Path(r"D:\AIfootball\models")
OUT = Path(os.environ.get("TEMP", ".")) / "aifootball_view"
OUT.mkdir(parents=True, exist_ok=True)

sys.stdout.reconfigure(encoding="utf-8")
con = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)
cur = con.cursor()
tables = [r[0] for r in cur.execute(
    "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
lines = [f"# DB={DB}  size={DB.stat().st_size/1024/1024:.1f} MB  tables={len(tables)}", ""]
summary = []
for t in tables:
    try:
        n = cur.execute(f'SELECT COUNT(*) FROM "{t}"').fetchone()[0]
    except Exception as e:
        n = f"ERR {e}"
    cols = [(c[1], c[2]) for c in cur.execute(f'PRAGMA table_info("{t}")')]
    sample = []
    try:
        rows = cur.execute(f'SELECT * FROM "{t}" LIMIT 2').fetchall()
        names = [c[1] for c in cur.execute(f'PRAGMA table_info("{t}")')]
        for r in rows:
            sample.append({names[i]: (str(v)[:28] if v is not None else None)
                           for i, v in enumerate(r)})
    except Exception:
        pass
    lines.append(f"## {t}  rows={n}  cols={len(cols)}")
    lines.append("   " + ", ".join(f"{c}:{ty}" for c, ty in cols))
    for s in sample:
        lines.append("   · " + ", ".join(f"{k}={v}" for k, v in list(s.items())[:14]))
    lines.append("")
    summary.append(f"{t:24s} {n if isinstance(n,int) else n:>10}  {', '.join(c for c,_ in cols)[:120]}")

lines.append("# models 目录")
for p in sorted(MODELS.glob("**/*")) if MODELS.exists() else []:
    if p.is_file():
        lines.append(f"  {p.name:40s} {p.stat().st_size/1024:8.1f} KB  {p.parent.name}")

(OUT / "db_schema.txt").write_text("\n".join(lines), encoding="utf-8")
print("\n".join(summary))
print(f"\n[完整 schema] {OUT / 'db_schema.txt'}")
