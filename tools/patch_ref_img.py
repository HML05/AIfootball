# -*- coding: utf-8 -*-
"""把参照稿模板里的远端底图换成项目本地底图(离线可用, 设计与结构一字不改)。"""
import io
import re
import sys

P = r"D:\AIfootball\frontend\templates\dashboard_ref.html"
s = io.open(P, encoding="utf-8").read()
m = re.search(r'<img src="([^"]+)"', s)
print("原图:", (m.group(1)[:70] if m else None))
s2, n = re.subn(r'(<img src=")[^"]+(")', r'\1/app/static/hero_stadium.jpg\2', s, count=1)
if n:
    io.open(P, "w", encoding="utf-8", newline="\n").write(s2)
    print("替换 %d 处 -> /app/static/hero_stadium.jpg" % n)
else:
    print("未找到 img, 跳过")
sys.exit(0)
