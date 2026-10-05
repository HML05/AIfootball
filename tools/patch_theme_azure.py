# -*- coding: utf-8 -*-
"""把前端主题(frontend/theme.py)的令牌切换成「参照稿」的天蓝玻璃语言。

参照稿 = 用户提供的后台 UI 设计稿(晴空蓝玻璃仪表盘): 浅蓝天光底 + 白色玻璃卡
+ 天蓝强调(#2f86e0 一族) + 石板灰/琥珀作为次色; 面板仍是玻璃态(与登录页一致)。

只改令牌取值与注释, 不改结构、不改键名 —— 因此 theme/viz/blocks/页面代码
无需分叉, 第 26 节「对齐层」也因为全部走令牌而自动跟随。

用法: python tools/patch_theme_azure.py [--check]
"""
from __future__ import annotations

import io
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
THEME = ROOT / "frontend" / "theme.py"

NEW_DARK = '''_DARK = {
    # ---- 夜场(参照稿的夜空版: 深蓝墨底 + 天蓝强调 + 玻璃卡片) ----
    # 令牌名与浅色主题完全一致, 因此 theme / viz / blocks / 页面代码无需分叉。
    # 背景层级(由深到浅: 画布 -> 侧栏 -> 面板 -> 悬浮)
    "bg0": "#0a1524", "bg1": "rgba(18,30,46,0.72)", "bg2": "rgba(22,36,54,0.92)",
    "bg3": "#152a40",
    # 边框: 白色透明叠加的发丝线(玻璃面的接缝)
    "line": "rgba(255,255,255,0.14)",
    "line_strong": "rgba(255,255,255,0.24)",
    "line_accent": "rgba(74,157,248,0.34)",
    # 文本: t3 在 bg0 上 5.6:1 / bg2 上 4.9:1, 四层背景全部 >= 4.5:1 (WCAG AA)
    "t1": "#e8eff8", "t2": "#aec0d4", "t3": "#7d90a6",
    # 主色: 参照稿的天蓝(#4090e0 一族)在深底上的提亮版
    "accent": "#4a9df8", "accent2": "#2f86e0", "accent_ink": "#06131f",
    "accent_soft": "rgba(74,157,248,0.16)",
    "accent_tint": "#123047",
    "gold": "#e8b44a", "purple": "#93a4c4", "blue": "#45c2dd",
    "red": "#ff7a6b", "ok": "#3fbf8f",
    "gold_soft": "rgba(232,180,74,0.12)", "purple_soft": "rgba(147,164,196,0.12)",
    "blue_soft": "rgba(69,194,221,0.14)", "red_soft": "rgba(255,122,107,0.14)",
    # 状态点: 实心圆 + 一圈淡光晕
    "ok_soft": "rgba(63,191,143,0.14)", "ok_halo": "rgba(63,191,143,0.18)",
    # 次要色(青蓝)与暖/冷两处光晕
    "cool": "#45c2dd", "cool_glow": "rgba(143,198,232,1)",
    "warm_deep": "#a8641f", "warm_glow": "rgba(255,190,130,1)",
    # 尺寸: 10 / 14 / 22 + 999(胶囊), 与登录页 --r-xs / --r-sm / --r 对应
    "r1": "10px", "r2": "14px", "r3": "22px", "pill": "999px",
    # 布局尺度(保持不变)
    "sidebar_w": "252px", "pad": "26px", "topbar_h": "66px",
    # 深色下的柔影(冷蓝黑, 不是纯黑)
    "shadow": ("0 34px 80px -30px rgba(0,0,0,0.86), "
               "0 12px 28px -16px rgba(0,0,0,0.55)"),
    "shadow_sm": "0 10px 26px -14px rgba(0,0,0,0.60)",
    # 主按钮: 天蓝渐变 + 顶部内高光 + 悬停蓝投影
    "accent_grad": "linear-gradient(180deg,#5aa9f8 0%,#2f86e0 100%)",
    "accent_shadow": "0 18px 34px -14px rgba(31,111,196,0.55)",
    "inset_hl": "inset 0 1px 0 rgba(255,255,255,0.22)",
    # 玻璃面(与登录页 --glass / --glass-strong / --glass-line 同写法)
    "glass": "rgba(18,30,46,0.72)", "glass_strong": "rgba(22,36,54,0.92)",
    "glass_line": "rgba(255,255,255,0.10)",
    # 画布光晕: 右上冷蓝天光 + 左下青蓝反光
    "scene": ("radial-gradient(1200px 620px at 78% -8%, rgba(74,157,248,0.22) 0%, "
              "rgba(74,157,248,0) 62%), "
              "radial-gradient(1000px 560px at 4% 104%, rgba(69,194,221,0.16) 0%, "
              "rgba(69,194,221,0) 60%)"),
    # 图表专用实底(Altair 背景不吃半透明, 单独给一个不透明值)
    "bg_chart": "#121e2e",
    # 浏览器表面色(滚动条滑块 / 插入符)
    "thumb": "#22344a", "thumb_hover": "#2f4761", "caret": "#4a9df8",
    # 页面底层质感: 点阵网格 + 光晕强度
    "grain_opacity": "0.05", "glow_opacity": "0.07",
    # 点阵网格的像素色(深色下用白点, 浅色下用墨点)
    "dot": "rgba(255,255,255,0.055)",
    # 图表类别色板: 天蓝打头, 青蓝/琥珀/石板灰拉开色相
    "p1": "#4a9df8", "p2": "#45c2dd", "p3": "#e8b44a", "p4": "#93a4c4",
    "p5": "#ff7a6b", "p6": "#7fc0e0", "p7": "#a8d8e8", "p8": "#4f8bab",
    "p9": "#c9a06a", "p10": "#b3c1cf",
    # 统一缓动(登录页入场: cubic-bezier(.2,.75,.2,1))
    "ease": "cubic-bezier(.2,.75,.2,1)",
    # 展示层字体(衬线标题, 登录页 "Sign in." 同栈)
    "font_title": FONT_TITLE,
}'''

NEW_LIGHT = '''_LIGHT = {
    # ---- 日场(参照稿本体: 晴空蓝天光底 + 白玻璃卡 + 天蓝强调) ----
    # 层次靠 1px 发丝线 + 冷蓝柔影, 不用重阴影。
    "bg0": "#e8f1fb", "bg1": "rgba(255,255,255,0.62)", "bg2": "rgba(255,255,255,0.86)",
    "bg3": "#f1f7fd",
    "line": "rgba(30,64,110,0.14)",
    "line_strong": "rgba(30,64,110,0.24)",
    "line_accent": "rgba(47,134,224,0.34)",
    # t3 #5d6d80 在 #ffffff 上 5.5:1 / bg0 上 5.0:1, 满足 WCAG AA
    "t1": "#14202e", "t2": "#3c4c60", "t3": "#5d6d80",
    # 主色 = 参照稿的天蓝 #4090e0(取 #2f86e0 做按钮/描边, #1f6fc4 做深态)
    "accent": "#2f86e0", "accent2": "#1f6fc4", "accent_ink": "#ffffff",
    "accent_soft": "rgba(47,134,224,0.12)",
    "accent_tint": "#cfe4f8",
    "gold": "#c8871a", "purple": "#5b6f8c", "blue": "#2aa3c9",
    "red": "#d0453c", "ok": "#2e9e6b",
    "gold_soft": "rgba(200,135,26,0.12)", "purple_soft": "rgba(91,111,140,0.12)",
    "blue_soft": "rgba(42,163,201,0.12)", "red_soft": "rgba(208,69,60,0.12)",
    # 状态绿点 + 淡光晕(参照稿的在线/正常标记)
    "ok_soft": "rgba(46,158,107,0.12)", "ok_halo": "rgba(46,158,107,0.18)",
    "cool": "#2aa3c9", "cool_glow": "rgba(122,196,232,1)",
    "warm_deep": "#a8641f", "warm_glow": "rgba(255,190,130,1)",
    "r1": "10px", "r2": "14px", "r3": "22px", "pill": "999px",
    "sidebar_w": "252px", "pad": "26px", "topbar_h": "66px",
    # 冷蓝柔影(参照稿的面板投影是蓝灰, 不是纯黑)
    "shadow": ("0 30px 70px -28px rgba(21,54,99,0.28), "
               "0 12px 26px -16px rgba(21,54,99,0.16)"),
    "shadow_sm": "0 10px 24px -14px rgba(21,54,99,0.22)",
    "accent_grad": "linear-gradient(180deg,#4a9df0 0%,#1f6fc4 100%)",
    "accent_shadow": "0 16px 30px -14px rgba(31,111,196,0.55)",
    "inset_hl": "inset 0 1px 0 rgba(255,255,255,0.42)",
    # 玻璃面: 与登录页 --glass / --glass-strong 同写法(半透明白 + 背景模糊)
    "glass": "rgba(255,255,255,0.60)", "glass_strong": "rgba(255,255,255,0.84)",
    "glass_line": "rgba(255,255,255,0.80)",
    # 画布光晕: 右上晴空蓝 + 左下浅青(参照稿的天光渐层)
    "scene": ("radial-gradient(1200px 620px at 80% -10%, rgba(122,182,245,0.52) 0%, "
              "rgba(122,182,245,0) 62%), "
              "radial-gradient(1000px 560px at 2% 106%, rgba(140,206,240,0.40) 0%, "
              "rgba(140,206,240,0) 60%)"),
    "bg_chart": "#ffffff",
    "thumb": "#c3d6ea", "thumb_hover": "#a6bed6", "caret": "#2f86e0",
    "grain_opacity": "0.04", "glow_opacity": "0.05",
    "dot": "rgba(30,64,110,0.06)",
    "p1": "#2f86e0", "p2": "#2aa3c9", "p3": "#c8871a", "p4": "#5b6f8c",
    "p5": "#d0453c", "p6": "#63a8e8", "p7": "#86c9d8", "p8": "#3a6f9e",
    "p9": "#8a7f6a", "p10": "#93a6bb",
    "ease": "cubic-bezier(.2,.75,.2,1)",
    "font_title": FONT_TITLE,
}'''


def replace_dict(src: str, name: str, new_block: str) -> str:
    """把 `name = {` 起始的字典整块替换掉(到第一个顶格 `}` 为止)。"""
    m = re.search(r"^%s = \{" % re.escape(name), src, re.M)
    if not m:
        raise SystemExit("[patch] 找不到 %s 字典" % name)
    end = src.find("\n}", m.end())
    if end < 0:
        raise SystemExit("[patch] %s 字典没有收尾" % name)
    return src[:m.start()] + new_block + src[end + 2:]


def main() -> int:
    src = io.open(THEME, encoding="utf-8").read()
    before = len(src)

    src = replace_dict(src, "_DARK", NEW_DARK)
    src = replace_dict(src, "_LIGHT", NEW_LIGHT)

    # 顶部说明里的主色描述(旧: 暖橙)
    src = src.replace(
        "  · 主色  —— 单一暖橙强调 #e2552b(日场) / #ff6a3d(夜场), 仅用于数据与状态",
        "  · 主色  —— 单一强调色 天蓝 #2f86e0(日场) / #4a9df8(夜场), 仅用于数据与状态")
    src = src.replace(
        "# 深色 = 主主题(深墨绿数据终端); 浅色 = 演示/打印友好版本。",
        "# 深色 = 夜场(深蓝玻璃终端); 浅色 = 日场(晴空蓝玻璃, 默认)。")

    # 点阵网格色改为走令牌(原来是写死的灰蓝 rgba)
    src = src.replace(
        "radial-gradient(rgba(120,140,160,{T['grain_opacity']}) 1px, transparent 1.4px) !important;",
        "radial-gradient({T['dot']} 1px, transparent 1.4px) !important;")

    if "--check" in sys.argv:
        print("[check] 未写入, 仅演练: %d -> %d 字符" % (before, len(src)))
        return 0

    io.open(THEME, "w", encoding="utf-8", newline="").write(src)
    print("[patch] frontend/theme.py: %d -> %d 字符" % (before, len(src)))
    for probe in ('"accent": "#2f86e0"', '"accent": "#4a9df8"', "T['dot'] 1px"):
        print("  %-26s %s" % (probe, "OK" if probe in src else "缺失!"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
