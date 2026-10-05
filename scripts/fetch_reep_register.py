# -*- coding: utf-8 -*-
"""下载 Reep 注册表(支持断点续传, 可指定文件)

用法:
    python scripts/fetch_reep_register.py small     # 小文件(教练/裁判/球队/球员等)
    python scripts/fetch_reep_register.py bridges   # 只下 ID 映射(100MB, 慢)
    python scripts/fetch_reep_register.py all
"""
import sys
import time
from pathlib import Path

import requests

BASE = Path(__file__).parent.parent
OUT = BASE / "data" / "external" / "reep"
H = {"User-Agent": "Mozilla/5.0"}
SMALL = ["coaches.csv.gz", "referees.csv.gz", "teams.csv.gz", "players.csv.gz",
         "seasons.csv.gz", "competitions.csv.gz", "relationships.csv.gz", "matches.csv.gz"]
BIG = ["bridges.csv.gz"]


def download(stamp, fn, expect):
    dest = OUT / fn
    url = f"https://data.reep.football/releases/{stamp}/csv/{fn}"
    part = dest.with_suffix(dest.suffix + ".part")
    have = part.stat().st_size if part.exists() else 0
    if dest.exists() and dest.stat().st_size >= expect * 0.99:
        print(f"  已有 {fn}")
        return
    for attempt in range(6):
        try:
            headers = dict(H)
            if have:
                headers["Range"] = f"bytes={have}-"
            r = requests.get(url, headers=headers, stream=True, timeout=120)
            if r.status_code not in (200, 206):
                print(f"    {fn} HTTP {r.status_code}")
                time.sleep(5)
                continue
            mode = "ab" if (have and r.status_code == 206) else "wb"
            if mode == "wb":
                have = 0
            done = have
            t0 = time.time()
            with open(part, mode) as f:
                for chunk in r.iter_content(1024 * 256):
                    f.write(chunk)
                    done += len(chunk)
            if done >= expect * 0.99:
                part.replace(dest)
                print(f"  ✓ {fn} {done/1024/1024:.1f} MB | {time.time()-t0:.0f}s")
                return
            have = done
            print(f"    {fn} 中断于 {done/1024/1024:.1f}/{expect/1024/1024:.1f} MB, 重试{attempt+1}")
        except Exception as e:
            have = part.stat().st_size if part.exists() else 0
            print(f"    {fn} 异常 {type(e).__name__}, 已下 {have/1024/1024:.1f} MB, 重试{attempt+1}")
            time.sleep(4)
    print(f"  ✗ {fn} 未完成")


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "small"
    OUT.mkdir(parents=True, exist_ok=True)
    STAMP = "20260907T201034Z"          # 已在 release.json 中确认
    # 已知文件大小(MB) —— 避免再请求容易超时的 release.json
    SIZES = {"coaches.csv.gz": 433989, "referees.csv.gz": 630000, "teams.csv.gz": 555000,
             "players.csv.gz": 8240000, "seasons.csv.gz": 94000,
             "competitions.csv.gz": 25940, "relationships.csv.gz": 28100000,
             "matches.csv.gz": 31800000, "bridges.csv.gz": 105009441}
    files = SMALL if mode == "small" else BIG if mode == "bridges" else SMALL + BIG
    print(f"Reep {STAMP} | 下载 {len(files)} 个文件 (HTTPS + 断点续传)")
    for fn in files:
        download(STAMP, fn, SIZES.get(fn, 10_000_000))
    for p in sorted(OUT.glob("*.gz")):
        print(f"  {p.name:<24} {p.stat().st_size/1024/1024:8.2f} MB")


if __name__ == "__main__":
    main()
