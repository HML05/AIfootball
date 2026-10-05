# -*- coding: utf-8 -*-
"""把用户给的参考图落盘: 纯三维球场图 -> frontend/static/hero_stadium.jpg;
两张驾驶舱参考图 -> docs/skin/ref_light.png / ref_dark.png;
并把浅色参考图切成 6 块 2x 放大图放到 %TEMP%\\aifootball_view\\ref2_*.png 方便细读。"""
import os
from PIL import Image

ATT = r"C:\Users\陶东辰\.dsh\attachments\v1\objects"
LIGHT = os.path.join(ATT, "1b", "1b73e4e8e9cddb5a491f064ed243363db650278456073688643093f1c8f0029d")
DARK = os.path.join(ATT, "3d", "3d948c284fa9381a209dc1b6a983e9a5a7137b8bdbdd7fa880c58dce49e35bd8")
STADIUM = os.path.join(ATT, "6a", "6a5275dd783786440e8210ae3e3cbb18748e60a89746076abb4a857065c978fe")

ROOT = r"D:\AIfootball"
STATIC = os.path.join(ROOT, "frontend", "static")
SKIN = os.path.join(ROOT, "docs", "skin")
TMP = os.path.join(os.environ.get("TEMP", r"C:\Windows\Temp"), "aifootball_view")
os.makedirs(TMP, exist_ok=True)
os.makedirs(STATIC, exist_ok=True)

# 1) 纯三维球场图 -> 主图底图
im = Image.open(STADIUM).convert("RGB")
print("stadium src", im.size)
im.resize((1600, int(1600 * im.size[1] / im.size[0])), Image.LANCZOS).save(
    os.path.join(STATIC, "hero_stadium.jpg"), "JPEG", quality=88, optimize=True)
print("hero_stadium.jpg", os.path.getsize(os.path.join(STATIC, "hero_stadium.jpg")) // 1024, "KB")

# 2) 两张驾驶舱参考图归档
for src, name in ((LIGHT, "ref_light.png"), (DARK, "ref_dark.png")):
    Image.open(src).convert("RGB").save(os.path.join(SKIN, name), optimize=True)
    print(name, "ok")

# 3) 浅色参考图切块 (2x) 便于细读
light = Image.open(LIGHT).convert("RGB")
W, H = light.size
print("light", light.size)
tiles = {
    "nav": (0, 0, int(W * 0.22), H),
    "top": (int(W * 0.05), 0, W, int(H * 0.30)),
    "kpi": (int(W * 0.16), int(H * 0.10), W, int(H * 0.36)),
    "focus": (int(W * 0.16), int(H * 0.60), int(W * 0.68), H),
    "bars": (int(W * 0.50), int(H * 0.60), W, H),
    "right": (int(W * 0.72), 0, W, H),
}
for k, box in tiles.items():
    t = light.crop(box)
    scale = min(2.0, 1600.0 / t.size[0])
    t = t.resize((int(t.size[0] * scale), int(t.size[1] * scale)), Image.LANCZOS)
    p = os.path.join(TMP, f"ref2_{k}.png")
    t.save(p)
    print(k, t.size, "->", p)
