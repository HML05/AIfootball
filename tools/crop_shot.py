# -*- coding: utf-8 -*-
"""把实况截图切成几块放大, 便于肉眼核对细节(和参照图对照)。"""
import sys
from pathlib import Path

from PIL import Image

src = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(
    r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view\d2_home.png")
out_dir = Path(r"C:\Users\陶东辰\AppData\Local\Temp\aifootball_view")
img = Image.open(src)
W, H = img.size
print("src", src.name, img.size)

boxes = {
    "cur_kpi": (280, 160, 1600, 320),
    "cur_lower": (280, 740, 1600, 960),
    "cur_right": (1200, 160, 1600, 960),
}
for name, box in boxes.items():
    box = (max(0, box[0]), max(0, box[1]), min(W, box[2]), min(H, box[3]))
    crop = img.crop(box)
    scale = 2 if crop.width < 900 else 1.6
    crop = crop.resize((int(crop.width * scale), int(crop.height * scale)), Image.LANCZOS)
    p = out_dir / f"{name}.png"
    crop.save(p)
    print(name, crop.size, "->", p)
