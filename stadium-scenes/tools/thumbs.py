#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""把 shots/<id>.png 压成 shots/thumbs/<id>.jpg（640 宽，JPEG q82）。

index.html 的四个预览卡用它，避免整页内联 4 张 1280x720 PNG 把文件撑到几 MB。
用法：python tools/thumbs.py
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SHOTS = os.path.join(ROOT, "shots")
OUT = os.path.join(SHOTS, "thumbs")
IDS = ["day", "dusk", "night", "rain"]

from PIL import Image  # noqa: E402

os.makedirs(OUT, exist_ok=True)
ok = 0
for sid in IDS:
    src = os.path.join(SHOTS, sid + ".png")
    if not os.path.exists(src):
        print("skip  %-6s (没有 %s.png)" % (sid, sid))
        continue
    im = Image.open(src).convert("RGB")
    w, h = im.size
    nw = 640
    nh = max(1, round(h * nw / w))
    im = im.resize((nw, nh), Image.LANCZOS)
    dst = os.path.join(OUT, sid + ".jpg")
    im.save(dst, "JPEG", quality=82, optimize=True, progressive=True)
    print("%-6s %4dx%-4d -> %3dx%-4d  %5.0f KB" % (sid, w, h, nw, nh, os.path.getsize(dst) / 1024))
    ok += 1
print("完成 %d/%d，输出目录 shots/thumbs/" % (ok, len(IDS)))
sys.exit(0)
