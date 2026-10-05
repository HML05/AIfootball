# -*- coding: utf-8 -*-
"""像素级对比「系统内的参照稿」与「单独跑的参照稿」, 输出差异区块。

用法: python scripts/diff_ref.py
"""
import os
import sys
from pathlib import Path

from PIL import Image, ImageChops

OUT = Path(os.environ.get("TEMP", ".")) / "aifootball_view"


def blocks(diff, thresh=28, min_area=400, top=12):
    """把差异图切成人眼可读的区块。"""
    w, h = diff.size
    px = diff.load()
    cell = 20
    grid = []
    for gy in range(0, h, cell):
        for gx in range(0, w, cell):
            hits = 0
            for y in range(gy, min(gy + cell, h), 2):
                for x in range(gx, min(gx + cell, w), 2):
                    if px[x, y] > thresh:
                        hits += 1
            if hits > 6:
                grid.append((gx, gy, hits))
    # 合并相邻格子为粗块
    merged = []
    for gx, gy, hits in grid:
        for m in merged:
            if abs(m[0] - gx) <= cell * 2 and abs(m[1] - gy) <= cell * 2:
                m[0] = min(m[0], gx); m[1] = min(m[1], gy)
                m[2] = max(m[2], gx); m[3] = max(m[3], gy)
                m[4] += hits
                break
        else:
            merged.append([gx, gy, gx, gy, hits])
    merged.sort(key=lambda m: -m[4])
    return merged[:top]


def main():
    a = OUT / "ref_solo_day.png"
    b = OUT / "cmp_app_1000.png"
    if not a.exists() or not b.exists():
        sys.exit(f"缺图: {a.exists()=} {b.exists()=}")
    ia, ib = Image.open(a).convert("RGB"), Image.open(b).convert("RGB")
    if ia.size != ib.size:
        print("尺寸不同:", ia.size, ib.size)
        w = min(ia.size[0], ib.size[0]); h = min(ia.size[1], ib.size[1])
        ia = ia.crop((0, 0, w, h)); ib = ib.crop((0, 0, w, h))
    d = ImageChops.difference(ia, ib)
    bbox = d.getbbox()
    stat = d.convert("L").histogram()
    total = sum(stat)
    over = sum(stat[28:])
    print(f"差异像素占比: {over / total * 100:.2f}%  bbox={bbox}")
    print("差异区块(x0,y0,x1,y1,强度):")
    for m in blocks(d.convert("L")):
        print("  ", m)
    d.convert("L").point(lambda v: 255 if v > 28 else 0).save(str(OUT / "diff_mask.png"))
    print("差异掩码:", OUT / "diff_mask.png")
    return 0


if __name__ == "__main__":
    sys.exit(main())
