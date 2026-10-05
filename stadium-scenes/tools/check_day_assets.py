#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""校验白天场景的素材：把 plate + clouds 按引擎的方式合成回去，和原图逐像素比对。

引擎画法：先画 plate（无云底板），再把 clouds.png（半分辨率）拉伸到天空带贴上。
这里完全照这个流程复现一遍，再看：
  1) 云区之外的像素差（MAE）—— 底板/天空渐变是否忠实
  2) 云区的像素差 —— 云层贴图是否还原
  3) 输出左右两段的 1:1 对照条，人工看接缝与云边缘

用法：python tools/check_day_assets.py
"""
import os

import numpy as np
from PIL import Image

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
A_DIR = os.path.join(ROOT, "assets")
SHOTS = os.path.join(ROOT, "shots")

SKY_BOT = 0.235

orig = Image.open(os.path.join(A_DIR, "stadium-day.jpg")).convert("RGB")
plate = Image.open(os.path.join(A_DIR, "plate.jpg")).convert("RGB")
clouds = Image.open(os.path.join(A_DIR, "clouds.png")).convert("RGBA")
W, H = plate.size
bw, bh = W, int(round(SKY_BOT * H))

# 引擎画法：底板 + 云层（拉伸到天空带）
comp = plate.copy()
cl = clouds.resize((bw, bh), Image.BILINEAR)
comp.paste(cl, (0, 0), cl)

# 原图缩到同一个尺寸做基准
base = orig.resize((W, H), Image.LANCZOS)

o = np.asarray(base.crop((0, 0, W, bh))).astype(np.float32)
c = np.asarray(comp.crop((0, 0, W, bh))).astype(np.float32)
ca = np.asarray(clouds.split()[3].resize((bw, bh), Image.BILINEAR)).astype(np.float32) / 255.0

sky = ca < 0.06
print("== 天空带 %dx%d ==" % (bw, bh))
print("   云区之外像素占比 %.1f%%，平均绝对误差 %.1f / 255" % (100 * sky.mean(), np.abs(o - c)[sky].mean()))
cl_mask = ca > 0.55
if cl_mask.sum():
    print("   浓云区（alpha>0.55）占比 %.1f%%，平均绝对误差 %.1f / 255"
          % (100 * cl_mask.mean(), np.abs(o - c)[cl_mask].mean()))

# 逐行带对比：底板天空 vs 原图天空（云区之外）
print("\n== 云区之外的平均色（原图 vs 合成） ==")
for y0, y1 in [(0.0, 0.06), (0.06, 0.12), (0.12, 0.18), (0.18, 0.235)]:
    s = slice(int(y0 * H), int(y1 * H))
    m = sky[s]
    if m.sum() > 50:
        print("   y %.3f~%.3f  原图 %s  合成 %s" % (
            y0, y1,
            o[s][m].mean(axis=0).round(0).astype(int),
            c[s][m].mean(axis=0).round(0).astype(int)))

# 对照条（1:1，两段各 768 宽，2 倍放大便于看边缘）
for i, x0 in enumerate((0, W // 2)):
    a = base.crop((x0, 0, x0 + W // 2, bh))
    b = comp.crop((x0, 0, x0 + W // 2, bh))
    sep = Image.new("RGB", (a.size[0], 4), (255, 255, 255))
    stack = Image.new("RGB", (a.size[0], a.size[1] * 2 + 4))
    stack.paste(a, (0, 0))
    stack.paste(sep, (0, a.size[1]))
    stack.paste(b, (0, a.size[1] + 4))
    stack = stack.resize((stack.size[0] * 2, stack.size[1] * 2), Image.NEAREST)
    p = os.path.join(SHOTS, "_dayband_%d.png" % i)
    stack.save(p)
    print("对照条 " + p + "（上：原图  下：底板+云层）")
