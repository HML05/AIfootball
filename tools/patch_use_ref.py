# -*- coding: utf-8 -*-
"""把首页/数据概览里的 HERO.render(...) 整段换成参照稿渲染 REF.render(theme=...)。

复刻阶段(用户 m07333: 先复刻、看、确认后再套数据):
    页面直接用 `templates/dashboard_ref.html` 原样渲染 —— 参照稿自带示例数据一字不改。
    数据阶段只需把 REF.render(theme=...) 换成 REF.render(theme=..., data={...})。
"""
import io
import re
import sys

REPL = {
    r"D:\AIfootball\frontend\app.py":
        '            REF.render(theme=_theme_key(), height=1000)\n',
    r"D:\AIfootball\frontend\admin.py":
        '        REF.render(theme=_theme_key(), height=1000)\n',
}


def patch(path, new_line):
    src = io.open(path, encoding="utf-8").read()
    lines = src.split("\n")
    start = end = None
    depth = None
    for i, ln in enumerate(lines):
        if start is None and re.match(r"^\s*HERO\.render\(", ln):
            start = i
            depth = len(ln) - len(ln.lstrip())
            continue
        if start is not None and ln.strip() and (len(ln) - len(ln.lstrip())) <= depth:
            end = i - 1
            break
    if start is None:
        print("[skip] %s: 没找到 HERO.render(" % path)
        return False
    if end is None:
        end = len(lines) - 1
    # 回退: 末尾可能留下批注/空行, 去掉紧跟的空行
    print("[patch] %s: 第 %d-%d 行 -> REF.render(...)" % (path, start + 1, end + 1))
    out = lines[:start] + [new_line.rstrip("\n")] + lines[end + 1:]
    io.open(path, "w", encoding="utf-8", newline="\n").write("\n".join(out))
    return True


ok = True
for p, line in REPL.items():
    ok = patch(p, line) and ok
sys.exit(0 if ok else 1)
