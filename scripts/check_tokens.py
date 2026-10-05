# -*- coding: utf-8 -*-
"""体检: 主题字典是否有重复键 / 关键令牌取值。"""
import collections
import re
import sys

sys.path.insert(0, r"D:\AIfootball\frontend")
src = open(r"D:\AIfootball\frontend\theme.py", encoding="utf-8").read()
for name in ("_DARK", "_LIGHT"):
    m = re.search(name + r" = \{(.*?)\n\}", src, re.S)
    body = m.group(1)
    keys = re.findall(r'^\s{4}"([a-z0-9_]+)"\s*:', body, re.M)
    dup = [k for k, c in collections.Counter(keys).items() if c > 1]
    print(name, "keys=", len(keys), "dup=", dup)

import theme  # noqa: E402
print("DARK glass_mid:", theme._DARK.get("glass_mid"), "| lite:", theme._DARK.get("glass_lite"))
print("DARK bg0:", theme._DARK.get("bg0"), "| t1:", theme._DARK.get("t1"))
print("LIGHT glass_mid:", theme._LIGHT.get("glass_mid"))
print("missing in DARK vs LIGHT:", sorted(set(theme._LIGHT) - set(theme._DARK)))
print("missing in LIGHT vs DARK:", sorted(set(theme._DARK) - set(theme._LIGHT)))
