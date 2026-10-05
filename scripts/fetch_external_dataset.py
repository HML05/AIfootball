# -*- coding: utf-8 -*-
"""下载 Transfermarkt 开源数据集(salimt/football-datasets, Kaggle 镜像, 免登录)

下载 zip → 解压到 data/external/ → 列出文件、行数、字段

用法: python scripts/fetch_external_dataset.py
"""
import csv
import os
import sys
import zipfile
from pathlib import Path

import requests

BASE = Path(__file__).parent.parent
OUT = BASE / "data" / "external"
ZIP = OUT / "football-datasets.zip"
URL = "https://www.kaggle.com/api/v1/datasets/download/xfkzujqjvx97n/football-datasets"


def download():
    OUT.mkdir(parents=True, exist_ok=True)
    if ZIP.exists() and ZIP.stat().st_size > 1_000_000:
        print(f"已存在 {ZIP} ({ZIP.stat().st_size/1024/1024:.1f} MB), 跳过下载")
        return
    print("正在下载数据集(~81MB)...", flush=True)
    with requests.get(URL, stream=True, timeout=300) as r:
        r.raise_for_status()
        total = int(r.headers.get("Content-Length") or 0)
        done = 0
        with open(ZIP, "wb") as f:
            for chunk in r.iter_content(chunk_size=1024 * 512):
                f.write(chunk)
                done += len(chunk)
                if total and done % (10 * 1024 * 1024) < 1024 * 512:
                    print(f"  {done/1024/1024:.0f}/{total/1024/1024:.0f} MB", flush=True)
    print(f"下载完成: {ZIP} ({ZIP.stat().st_size/1024/1024:.1f} MB)")


def extract():
    print("\n解压中...", flush=True)
    with zipfile.ZipFile(ZIP) as z:
        names = z.namelist()
        z.extractall(OUT)
    print(f"解压出 {len(names)} 个文件到 {OUT}")
    for n in names:
        p = OUT / n
        if p.is_file():
            print(f"  {n:<55} {p.stat().st_size/1024/1024:8.1f} MB")


def summarize():
    print("\n" + "=" * 70)
    print("各 CSV 概览")
    print("=" * 70)
    for p in sorted(OUT.rglob("*.csv")):
        try:
            with open(p, encoding="utf-8", errors="replace") as f:
                reader = csv.reader(f)
                header = next(reader)
                n = sum(1 for _ in reader)
            print(f"\n{p.relative_to(OUT)}")
            print(f"   行数 {n:,} | 字段 {len(header)}: {', '.join(header[:14])}")
        except Exception as e:
            print(f"\n{p.name}: 读取失败 {type(e).__name__}")


if __name__ == "__main__":
    download()
    if not any(OUT.rglob("*.csv")):
        extract()
    summarize()
