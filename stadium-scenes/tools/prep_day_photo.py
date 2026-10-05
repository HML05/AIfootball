#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把白天实拍图拆成"可以真的飘起来"的素材。

思路：照片里的云是画死的，要让它飘，就得把它从蓝天里分离出来：
  1) 逐行估计"这一行的纯净蓝天颜色" S(y)（只统计该行的蓝像素中位数，再平滑）
  2) 每个天空像素看作 P = a*C + (1-a)*S  →  解出云的不透明度 a 与云自身颜色 C
  3) 蓝天部分重绘成 S(y) 的竖直渐变 → 得到"无云底板" plate.jpg
  4) 云层 C/a 做成左右可无缝平铺的贴图 clouds.png（半分辨率，云是软的，看不出差别）
  5) 天空轮廓 skyline.json：每列第一个"非天空"像素的 y（城市/看台轮廓），
     运行时用它裁剪云层 → 云始终在城市与看台后面

输出：
  assets/plate.jpg          无云底板（天空已重绘）
  assets/clouds.png         可平铺云层（RGBA，半分辨率）
  assets/skyline.json       天空轮廓（归一化坐标，供 canvas 裁剪）
  shots/_cloudcheck.png     原图 vs 重建 对照图（人工校验用）

用法：python tools/prep_day_photo.py
"""
import json
import os

import numpy as np
from PIL import Image, ImageFilter

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SRC = os.path.join(ROOT, "assets", "stadium-day.jpg")
ASSETS = os.path.join(ROOT, "assets")
SHOTS = os.path.join(ROOT, "shots")

SKY_BOT = 0.235          # 云只可能在这个比例以上（再往下是城市雾气/楼群）
PLATE_W = 1536           # 底板输出宽度（显示尺寸，够用且省体积）
TILE_SCALE = 0.72        # 云层贴图相对底板的分辨率比例
SEAM = 0.26              # 左右边缘交叉融合的宽度比例（消除平铺接缝）

os.makedirs(SHOTS, exist_ok=True)
im = Image.open(SRC).convert("RGB")
A = np.asarray(im).astype(np.float32)
H, W, _ = A.shape
r, g, b = A[:, :, 0], A[:, :, 1], A[:, :, 2]
lum = 0.2126 * r + 0.7152 * g + 0.0722 * b
mx = A.max(axis=2)
mn = A.min(axis=2)
sat = np.where(mx > 1, (mx - mn) / np.maximum(mx, 1), 0)

# ---------------------------------------------------------------- 1) 逐行蓝天
# 逐行取"蓝像素中位数"作为该行纯净天空色，再补空缺 + 竖直平滑：
# 天空是从顶部深蓝到地平线发白的连续渐变，二次多项式拟合会跑偏，逐行平滑更准。
blue_px = (b - r > 24) & (sat > 0.18)
valid = np.zeros(H, bool)
rows = np.zeros((H, 3), np.float32)
SKY_FIT_TOP = 0.27                                     # 只在前 27% 高度里取样
for y in range(int(SKY_FIT_TOP * H)):
    m = blue_px[y]
    if m.sum() > W * 0.03:
        rows[y] = np.median(A[y][m], axis=0)
        valid[y] = True
idx = np.arange(H, dtype=np.float32)
sky_row = np.zeros((H, 3), np.float32)
good = np.where(valid)[0].astype(np.int64)
for c in range(3):
    sky_row[:, c] = np.interp(idx, good.astype(np.float32), rows[good, c])
sig = 9.0
off = np.arange(-int(3 * sig), int(3 * sig) + 1, dtype=np.float32)
ker = np.exp(-(off ** 2) / (2 * sig * sig))
ker /= ker.sum()
for c in range(3):
    sky_row[:, c] = np.convolve(np.pad(sky_row[:, c], len(off) // 2, mode="edge"), ker, mode="same")[len(off) // 2:-(len(off) // 2)]
sky_row = np.clip(sky_row, 0, 255)
print("蓝天渐变（顶 / y=0.15 / y=0.22）：", sky_row[4].round(0), sky_row[int(0.15 * H)].round(0),
      sky_row[int(0.22 * H)].round(0))

# ------------------------------------------------- 1b) 每列的"天空下边界"轮廓
# 城市楼群/看台顶棚是从上往下第一个"非天空"像素；云要在它后面，
# 所以这里先算出来，既用于抑制"楼顶雾气被误判成云"，也用于运行时裁剪。
lumS_row = 0.2126 * sky_row[:, 0] + 0.7152 * sky_row[:, 1] + 0.0722 * sky_row[:, 2]
skyish_px = ((b - r > 16) | (lum > lumS_row[:, None] + 8))
skylim = np.zeros(W, np.float32)
for x in range(W):
    col = np.where(~skyish_px[: int(0.50 * H), x])[0]
    col = col[col > int(0.12 * H)]
    skylim[x] = (col[0] / H) if len(col) else 1.0
NB = 96
step = W // NB
pts = []
for i in range(NB + 1):
    x0, x1 = i * step, min(W, (i + 1) * step)
    if x0 >= W:
        break
    pts.append([round(x0 / W, 5), round(float(np.percentile(skylim[x0:x1], 5)), 5)])
# 平滑轮廓 + 每列查表
pxs = np.array([p[0] for p in pts], np.float32)
pys = np.array([p[1] for p in pts], np.float32)
k = np.ones(5, np.float32) / 5
pys_s = np.convolve(np.pad(pys, 2, mode="edge"), k, mode="same")[2:-2]
lim_per_col = np.interp(np.arange(W) / W, pxs, pys_s)
print("天空下边界（列轮廓）：y %.3f ~ %.3f" % (lim_per_col.min(), lim_per_col.max()))

# ---------------------------------------------------------------- 2) 解出云
S = np.repeat(sky_row[:, None, :], W, axis=1)          # 每行的蓝天基色
lumS = 0.2126 * S[:, :, 0] + 0.7152 * S[:, :, 1] + 0.0722 * S[:, :, 2]
mxS = S.max(axis=2)
mnS = S.min(axis=2)
satS = np.where(mxS > 1, (mxS - mnS) / np.maximum(mxS, 1), 0)

band = np.zeros((H, W), bool)
band[: int(SKY_BOT * H)] = True

dLum = lum - lumS
dSat = satS - sat
a_lum = np.clip(dLum / np.maximum(235.0 - lumS, 40.0), 0, 1)
a_sat = np.clip(dSat / np.maximum(satS, 0.08) * 0.9, 0, 1)
alpha = np.clip(np.maximum(a_lum, a_sat * 0.85), 0, 1)
alpha = np.where(band, alpha, 0.0)

# 楼群轮廓附近（城市雾气）一律不算云：留 0.045 的余量
yy = np.arange(H, dtype=np.float32)[:, None]
alpha = np.where(yy < (lim_per_col[None, :] - 0.045) * H, alpha, 0.0)

# 去掉零散噪点：小于阈值的都归零再重新拉伸
alpha = np.clip((alpha - 0.10) / 0.90, 0, 1)
alpha = alpha ** 1.1
# 再压掉"淡雾"成分：云层要平铺两层用，残留的低 alpha 薄雾叠两层就会把天空洗成灰白。
# 用 smoothstep 只削低值、不动浓云主体，云的形状与边缘保留。
_hz = np.clip((alpha - 0.06) / (0.34 - 0.06), 0, 1)
alpha = alpha * (_hz * _hz * (3 - 2 * _hz))

# 云自身颜色 C = (P - (1-a)S)/a
# 直接除会放大噪声（淡云的 a 很小），所以用"先各自模糊再相除"的做法稳住：
#   C = blur(P - (1-a)S) / blur(a)
def _gauss(arr, r):
    if arr.ndim == 2:
        img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "L")
        return np.asarray(img.filter(ImageFilter.GaussianBlur(r))).astype(np.float32)
    img = Image.fromarray(np.clip(arr, 0, 255).astype(np.uint8), "RGB")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(r))).astype(np.float32)


num = A - (1 - alpha)[:, :, None] * S
den = _gauss(alpha * 255.0, 2.2) / 255.0
numB = _gauss(num, 2.2)
C = numB / np.maximum(den, 0.02)[:, :, None]
C = np.clip(C, 0, 255)
C = np.where(alpha[:, :, None] > 0.02, C, 255.0)       # 全透明处给白色

print("云覆盖率（天空带内）：%.1f%%" % (100 * (alpha[band] > 0.15).mean()))

# ---------------------------------------------------------------- 3) 底板
plate = np.where(alpha[:, :, None] > 0.004, S, A)      # 云像素换成蓝天
plate = np.where(alpha[:, :, None] > 0.004, alpha[:, :, None] * 0 + plate, plate)
plate_img = Image.fromarray(plate.round().astype(np.uint8))
plate_img = plate_img.resize((PLATE_W, round(H * PLATE_W / W)), Image.LANCZOS)
plate_img.save(os.path.join(ASSETS, "plate.jpg"), "JPEG", quality=86, optimize=True, progressive=True)
print("底板 plate.jpg  %dx%d  %.0f KB" % (plate_img.size[0], plate_img.size[1],
                                          os.path.getsize(os.path.join(ASSETS, "plate.jpg")) / 1024))

# ---------------------------------------------------------------- 4) 云层贴图
band_h = int(SKY_BOT * H)
full_a = Image.fromarray((alpha * 255).round().astype(np.uint8), "L").crop((0, 0, W, band_h))
full_c = Image.fromarray(C.round().astype(np.uint8), "RGB").crop((0, 0, W, band_h))
tw, th = int(PLATE_W * TILE_SCALE), max(2, int(round(band_h * PLATE_W / W * TILE_SCALE)))
ta = np.asarray(full_a.resize((tw, th), Image.LANCZOS)).astype(np.float32) / 255.0
tc = np.asarray(full_c.resize((tw, th), Image.LANCZOS)).astype(np.float32)

# 左右交叉融合 → 平铺无缝
sw = max(2, int(tw * SEAM))
w = np.linspace(0, 1, sw, dtype=np.float32)[None, :, None]
left_a, right_a = ta[:, :sw, None].copy(), ta[:, tw - sw:, None].copy()
left_c, right_c = tc[:, :sw].copy(), tc[:, tw - sw:].copy()
mix_a = left_a * w + right_a * (1 - w)
mix_c = left_c * w + right_c * (1 - w)
ta[:, :sw] = mix_a[:, :, 0]
ta[:, tw - sw:] = mix_a[:, :, 0]
tc[:, :sw] = mix_c
tc[:, tw - sw:] = mix_c

# 云层下沿收边：接近 SKY_BOT 处 alpha 归零，飘移时不会硬切
fade = np.ones(th, np.float32)
f0, f1 = int(th * 0.80), th
fade[f0:] = 1 - (np.arange(f1 - f0) / max(1, f1 - f0)) ** 0.8
ta = ta * fade[:, None]

rgba = np.dstack([np.clip(tc, 0, 255), np.clip(ta * 255, 0, 255)]).round().astype(np.uint8)
cloud_img = Image.fromarray(rgba, "RGBA")
cloud_img.save(os.path.join(ASSETS, "clouds.png"), "PNG", optimize=True)
print("云层 clouds.png  %dx%d  %.0f KB" % (tw, th, os.path.getsize(os.path.join(ASSETS, "clouds.png")) / 1024))

# ---------------------------------------------------------------- 5) 天空轮廓
with open(os.path.join(ASSETS, "skyline.json"), "w", encoding="utf-8") as f:
    json.dump({"bottom": SKY_BOT, "pts": pts}, f)
print("天空轮廓 skyline.json  %d 个采样点，顶部包络 y %.3f~%.3f"
      % (len(pts), min(p[1] for p in pts), max(p[1] for p in pts)))

# ---------------------------------------------------------------- 6) 对照图
sky_band = np.asarray(
    Image.fromarray(sky_row.round().astype(np.uint8)[:, None, :].repeat(W, 1), "RGB")
    .resize((tw, th), Image.BILINEAR)).astype(np.float32)
recon = np.clip(ta[:, :, None] * tc + (1 - ta[:, :, None]) * sky_band, 0, 255).astype(np.uint8)
orig_band = np.asarray(im.crop((0, 0, W, int(SKY_BOT * H))).resize((tw, th), Image.LANCZOS)).astype(np.uint8)
stack = np.vstack([orig_band, np.full((6, tw, 3), 255, np.uint8), recon])
chk = Image.fromarray(stack).resize((tw * 2, stack.shape[0] * 2), Image.NEAREST)
chk.save(os.path.join(SHOTS, "_cloudcheck.png"))
print("对照图 shots/_cloudcheck.png（上：原图天空带 %dx%d  下：云层+蓝天重建）" % (tw, th))
