#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""分析白天实拍图：天际线、云的可分离性、草坪云影方向。

为"把照片里的云变成真正会飘的云层"做可行性判定：
如果蓝天/白云能在像素级干净分开（蓝天饱和度低亮、白云高亮低饱和），
就可以把云做成一层可平移的精灵，再补一张无云蓝天底图。
"""
import json
import os
import sys

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "assets", "stadium-day.jpg")

im = Image.open(SRC).convert("RGB")
a = np.asarray(im).astype(np.float32)
H, W, _ = a.shape
r, g, b = a[:, :, 0], a[:, :, 1], a[:, :, 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
mx = a.max(axis=2)
mn = a.min(axis=2)
sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1), 0)

# 蓝天：偏蓝（b 明显大于 r）且有一定饱和
blue = (b - r > 18) & (sat > 0.16) & (lum > 70)
# 白云：很亮且低饱和
white = (lum > 196) & (sat < 0.13)
# 天空候选（含云）
skyish = blue | white

row_blue = blue.mean(axis=1)
row_white = white.mean(axis=1)
# 天际线：从上往下，蓝天比例第一次掉到 12% 以下
city_top = H
for y in range(H):
    if row_blue[y] < 0.12:
        city_top = y
        break

print("== 尺寸 ==", W, "x", H)
print("== 天际线（蓝天比例<12%% 的第一行）==", city_top, "= %.3f of H" % (city_top / H))

bands = [(0.00, 0.10), (0.10, 0.20), (0.20, 0.30), (0.30, 0.40), (0.40, 0.50)]
print("\n== 各行带：蓝天% / 白云% ==")
for y0, y1 in bands:
    s = slice(int(y0 * H), int(y1 * H))
    print("  %.2f~%.2f   蓝天 %5.1f%%   白云 %5.1f%%" % (y0, y1, row_blue[s].mean() * 100, row_white[s].mean() * 100))

# 云掩码（只在上部天空里找）
ys, xs = np.where(white)
if len(ys):
    print("\n== 白云像素 ==", len(ys), "占比 %.2f%%" % (100 * len(ys) / (W * H)))
    print("   y 范围 %.3f~%.3f（中位 %.3f）  x 范围 %.3f~%.3f"
          % (ys.min() / H, ys.max() / H, np.median(ys) / H, xs.min() / W, xs.max() / W))
    # 云的连通块大小（粗粒度：按 16px 网格统计）
    grid = np.zeros((H // 16 + 1, W // 16 + 1), np.float32)
    np.add.at(grid, (ys // 16, xs // 16), 1)
    nz = grid[grid > 0]
    print("   16px 网格内有云的格子 %d 个，平均每格 %.0f 像素（说明云是成团的）" % (len(nz), nz.mean()))

# 蓝天颜色采样（避开云）
print("\n== 蓝天颜色（取蓝天像素的分位数） ==")
if blue.sum() > 0:
    bp = a[blue]
    for q in (0.1, 0.5, 0.9):
        print("   亮度分位 %.1f -> RGB %s" % (q, np.percentile(bp, q * 100, axis=0).round(0).astype(int)))
    yy = np.where(blue)
    for y0, y1 in [(0.0, 0.06), (0.06, 0.14), (0.14, 0.22), (0.22, 0.30)]:
        m = blue[int(y0 * H):int(y1 * H)]
        if m.sum() > 20:
            print("   y %.2f~%.2f 蓝天均值 %s" % (y0, y1, m[m].mean(axis=0).round(0).astype(int) if False else a[int(y0 * H):int(y1 * H)][m].mean(axis=0).round(0).astype(int)))

# 草坪云影：找绿色像素，再看其亮度分布
green = (g > r + 12) & (g > b + 12) & (lum > 30)
gy, gx = np.where(green)
if len(gy):
    gtop, gbot = gy.min(), gy.max()
    print("\n== 草坪 ==", "y %.3f~%.3f" % (gtop / H, gbot / H), "像素 %d" % len(gy))
    gl = lum[green]
    print("   亮度分位 10/50/90 = %.0f / %.0f / %.0f（差异大 = 草上有明显明暗）"
          % tuple(np.percentile(gl, [10, 50, 90])))
    # 暗区占草坪的比例
    dark = green & (lum < np.percentile(gl, 30))
    dy, dx = np.where(dark)
    if len(dy):
        print("   最暗 30%% 区域：x 中位 %.3f（0=左 1=右）、y 中位 %.3f" % (np.median(dx) / W, np.median(dy) / H))
        # 草坪内暗区重心相对于草坪重心
        print("   暗区重心 x %.3f vs 草坪重心 x %.3f" % (dx.mean() / W, gx.mean() / W))

out = {
    "w": W, "h": H, "cityTop": city_top / H,
    "blue_frac": float(blue.mean()), "white_frac": float(white.mean()),
}
with open(os.path.join(ROOT, "shots", "_photo_probe.json"), "w", encoding="utf-8") as f:
    json.dump(out, f, ensure_ascii=False, indent=2)
print("\n写入 shots/_photo_probe.json")
