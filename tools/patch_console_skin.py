# -*- coding: utf-8 -*-
"""把 8591 控制台（tools/console_template.html）改造成登录页的设计语言。

登录页 = docs/console/login.html：纸面白底 + 白玻璃卡 + 暖橙强调 + 衬线展示标题。

做法（全部只动视觉，不动结构/数据/交互）：
  1. 重写 :root 令牌块（变量名保持不变，避免牵动下游 3000 行 CSS/JS）；
  2. 把深色时代写死的颜色字面量按映射表换成浅色同义色；
  3. 在主样式块末尾追加一"登录页设计语言对齐层"。

用法: python tools/patch_console_skin.py [--dry-run]
"""
import re
import sys
from pathlib import Path

TPL = Path(__file__).resolve().parent / "console_template.html"

# ---------------------------------------------------------------- 1. 令牌块
NEW_TOKENS = """:root{
  /* 纸面（对齐参照稿「晴空蓝玻璃仪表盘」：蓝白纸面 + 白玻璃卡） */
  --bg:#e8f1fb;
  --bg-2:#f1f7fd;
  --panel:rgba(255,255,255,.86);
  --panel-2:#ffffff;
  --panel-3:#f1f7fd;
  --line:rgba(30,64,110,.14);
  --line-2:#d7e4f2;
  --text:#14202e;
  --text-2:#3c4c60;
  --text-3:#5d6d80;
  /* 主色 = 参照稿的天蓝 #4090e0 一族 */
  --accent:#2f86e0;
  --accent-2:#1f6fc4;
  --accent-deep:#17539a;
  --accent-soft:rgba(47,134,224,.10);
  --accent-tint:#cfe4f8;
  --accent-ink:#ffffff;
  --warm-glow:rgba(122,182,245,.45);
  --cool-glow:rgba(140,206,240,.34);
  --amber:#c8871a;
  --red:#d0453c;
  --blue:#2aa3c9;
  --violet:#5b6f8c;

  --radius:22px;
  --radius-sm:14px;
  --radius-xs:10px;
  --radius-pill:999px;
  --shadow:0 30px 70px -28px rgba(21,54,99,.28), 0 12px 26px -16px rgba(21,54,99,.16);
  --shadow-sm:0 10px 24px -14px rgba(21,54,99,.22);
  --hair:rgba(30,64,110,.12);
  --glass:rgba(255,255,255,.56);
  --sidebar-w:252px;
  --topbar-h:66px;
  --pad:26px;

  --font-sans:"PingFang SC","HarmonyOS Sans SC","Microsoft YaHei UI","Microsoft YaHei","Noto Sans SC",system-ui,-apple-system,"Segoe UI",sans-serif;
  --font-mono:"SF Mono","JetBrains Mono","Cascadia Mono",ui-monospace,"DejaVu Sans Mono",Consolas,monospace;
  /* 展示体：登录页的 Cormorant Garamond → Georgia → 中文回落 */
  --font-display:"Cormorant Garamond","PP Editorial New",Georgia,"Times New Roman","Songti SC","PingFang SC","Microsoft YaHei",serif;

  --ease-out:cubic-bezier(.16,.84,.44,1);
  --ease-in:cubic-bezier(.5,0,.75,0);
  --ease:cubic-bezier(.2,.75,.2,1);
}"""

NEW_BODY_BG = """body::before{
  content:"";position:fixed;inset:0;pointer-events:none;z-index:0;
  background:
    radial-gradient(1100px 620px at 82% -14%, var(--warm-glow), transparent 62%),
    radial-gradient(860px 560px at -8% 110%, var(--cool-glow), transparent 64%),
    radial-gradient(rgba(19,26,33,.055) 1px, transparent 1.4px);
  background-size:auto,auto,22px 22px;
}"""

# ------------------------------------------------- 2. 写死色 → 浅色同义色
RGBA_RULES = [
    (r"rgba\(\s*53\s*,\s*201\s*,\s*141\s*,", "rgba(226,85,43,"),      # 荧光绿 → 暖橙
    (r"rgba\(\s*38\s*,\s*168\s*,\s*119\s*,", "rgba(206,62,30,"),
    (r"rgba\(\s*230\s*,\s*178\s*,\s*86\s*,", "rgba(169,116,26,"),      # 琥珀
    (r"rgba\(\s*240\s*,\s*104\s*,\s*92\s*,", "rgba(192,57,43,"),       # 红
    (r"rgba\(\s*92\s*,\s*184\s*,\s*240\s*,", "rgba(63,124,168,"),      # 蓝
    (r"rgba\(\s*160\s*,\s*190\s*,\s*175\s*,", "rgba(19,26,33,"),       # 中性线
    (r"rgba\(\s*160\s*,\s*178\s*,\s*168\s*,", "rgba(19,26,33,"),
    (r"rgba\(\s*180\s*,\s*220\s*,\s*200\s*,", "rgba(19,26,33,"),
    (r"rgba\(\s*140\s*,\s*175\s*,\s*158\s*,", "rgba(19,26,33,"),
    (r"rgba\(\s*30\s*,\s*42\s*,\s*36\s*,", "rgba(19,26,33,"),
    (r"rgba\(\s*9\s*,\s*13\s*,\s*11\s*,", "rgba(255,255,255,"),        # 顶栏玻璃
    (r"rgba\(\s*4\s*,\s*7\s*,\s*6\s*,", "rgba(19,26,33,"),             # 遮罩
    (r"rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*\.92\s*\)", "rgba(14,28,45,.34)"),
    (r"rgba\(\s*0\s*,\s*0\s*,\s*0\s*,\s*\.8\s*\)", "rgba(14,28,45,.30)"),
    (r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*\.05\s*\)", "rgba(255,255,255,.75)"),
    (r"rgba\(\s*255\s*,\s*255\s*,\s*255\s*,\s*\.04\s*\)", "rgba(255,255,255,.60)"),
]

HEX_RULES = [    # 绿family → 暖family
    ("#7ff0bf", "#f2a173"), ("#43db9a", "#ce3e1e"), ("#8fd8b8", "#a82f14"),
    ("#c9f6e2", "#a82f14"), ("#cdf6e5", "#a82f14"), ("#7fe6bb", "#a82f14"),
    ("#9beec8", "#a82f14"), ("#bdf0d8", "#a82f14"), ("#eafff5", "#131a21"),
    ("#35c98d", "#e2552b"), ("#26a877", "#ce3e1e"), ("#05130d", "#ffffff"),
    # 琥珀 / 红 / 蓝 / 紫
    ("#f1cf92", "#8a5c10"), ("#e6b256", "#a9741a"),
    ("#f7a79e", "#8f2a1e"), ("#f6a59c", "#8f2a1e"), ("#f0685c", "#c0392b"),
    ("#a6d9f8", "#2c5c80"), ("#8ec7f0", "#2c5c80"), ("#5cb8f0", "#3f7ca8"),
    ("#9c8cf0", "#5d6b8a"),
    # 深色面板/线 → 浅色
    ("#090d0b", "#eef1f5"), ("#0b110e", "#f6f8fa"), ("#0f1512", "#ffffff"),
    ("#121a16", "#ffffff"), ("#17211c", "#f1f5f9"), ("#1e2a24", "#e4ebf2"),
    ("#27342d", "#d8e2ec"), ("#e9f1ec", "#131a21"), ("#a0b2a8", "#3e4a57"),
    ("#7c8e84", "#5c6773"),
    ("#202c26", "#e4ebf2"), ("#2b3a32", "#d6e0ea"), ("#33443a", "#c9d4e0"),
    ("#3a4b41", "#cbd5df"), ("#546b60", "#b8c2cc"), ("#c3d2ca", "#3e4a57"),
    ("#0c1a13", "#eaf0f6"), ("#0e1d15", "#e2eaf2"),
    ("#123a2a", "#f7dbce"), ("#163046", "#dbe7f3"),
    ("#2c7d5d", "#35657f"), ("#1f5c44", "#2c5c80"),
]

# JS 里以"裸三元组"形式写的颜色（没有 rgb()/rgba() 外壳），例如
#   const scale = opts.accent || '53,201,141';
# rgba 正则与 hex 表都抓不到，必须单独映射，否则图表主色仍是旧的荧光绿。
BARE_RULES = [
    ("53,201,141", "226,85,43"),      # 荧光绿 → 暖橙
    ("38,168,119", "206,62,30"),
    ("240,104,92", "192,57,43"),      # 红
    ("92,184,240", "63,124,168"),     # 蓝
    ("230,178,86", "169,116,26"),     # 琥珀
    ("156,140,240", "93,107,138"),    # 紫 → 石墨蓝
    ("60,120,90", "53,101,127"),
]

# --------------------------------------------- 3. 登录页设计语言对齐层
LAYER = """
/* ============================================================
   26. 参照稿(晴空蓝玻璃仪表盘)设计语言对齐层
   —— 与 docs/console/login.html 同一套玻璃面板 + 参照稿的天蓝强调：
      蓝白纸面 + 白玻璃卡 + 天蓝 #2f86e0 + 衬线展示标题 + 等宽大写微标签。
      只覆盖视觉，不动布局与任何交互逻辑。
   ============================================================ */
body{background:var(--bg);color:var(--text)}

/* 面板 = 白玻璃 + 发丝线 + 大圆角 + 柔投影 */
.panel,.card,.fn-card,.league-tile,.row-item,.tbl-wrap{
  backdrop-filter:blur(10px) saturate(120%);
}
.panel{
  border:1px solid var(--hair);border-radius:var(--radius);
  box-shadow:var(--shadow-sm);
}
.panel::before{
  background:linear-gradient(90deg,transparent,rgba(255,255,255,.9),transparent);
}
.panel-head{border-bottom:1px solid var(--hair)}

/* 展示体标题：衬线 */
h1,h2,.ph-title,.panel-head h2,.panel-head .title,.brand .b-title,#pageTitle,#pageTitle2{
  font-family:var(--font-display);font-weight:600;letter-spacing:.005em;
}
h1,.ph-title{font-weight:600}
h3,h4,.section-title,.panel-head .sub{font-family:var(--font-sans)}

/* 等宽大写微标签 */
.kicker,.panel-head .cap,.sec-cap,.micro,.eyebrow,.badge,.tag,
.tbl thead th,.kpi .label,.stat .label,.metric .label,.side-cap{
  font-family:var(--font-mono);text-transform:uppercase;letter-spacing:.16em;
}
.tbl thead th{letter-spacing:.14em;color:var(--text-3);background:transparent}
.panel-head .cap,.side-cap{letter-spacing:.22em;font-size:.62rem;color:var(--text-3)}

/* 导航：选中 = 暖色玻璃块 + 左侧暖条 */
.nav-item{border-radius:var(--radius-xs)}
.nav-item.active{
  color:var(--accent-deep);
  background:linear-gradient(90deg,var(--accent-soft),rgba(47,134,224,.03));
  box-shadow:inset 3px 0 0 var(--accent);
}
.nav-item:hover{background:rgba(19,26,33,.04)}

/* 按钮：主按钮暖色渐变 + 内高光 + 悬停暖投影 + 按压 1px */
.btn{border-radius:var(--radius-xs);border:1px solid var(--hair);background:var(--glass)}
.btn:hover{background:#fff;border-color:var(--accent-soft)}
.btn-primary{
  border:0;color:#fff;background:linear-gradient(180deg,#4a9df0 0%,#1f6fc4 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.34),0 10px 24px -14px rgba(31,111,196,.55);
}
.btn-primary:hover{
  background:linear-gradient(180deg,#5aa9f8 0%,#2f86e0 100%);
  box-shadow:inset 0 1px 0 rgba(255,255,255,.38),0 18px 34px -14px rgba(31,111,196,.7);
}
.btn:active{transform:translateY(1px)}

/* 输入控件：白底 + 发丝线 + 暖色聚焦环 */
.input,.select,select,input[type="text"],input[type="search"],textarea{
  background:#fff;border:1px solid var(--hair);border-radius:var(--radius-xs);color:var(--text);
}
.input:focus,.select:focus,select:focus,input:focus,textarea:focus{
  outline:none;border-color:var(--accent);
  box-shadow:0 0 0 4px var(--accent-soft);
}
.input:hover,.select:hover,select:hover{border-color:rgba(19,26,33,.22)}
.segmented{background:var(--panel-3);border:1px solid var(--hair);border-radius:var(--radius-pill)}
.segmented button{border-radius:var(--radius-pill)}
.segmented button.on{background:#fff;color:var(--accent-deep);box-shadow:var(--shadow-sm)}

/* 芯片 / 标签 / 徽标：令牌色 1px 同色描边 */
.chip{border-radius:var(--radius-pill);background:var(--glass)}
.chip:hover{border-color:rgba(19,26,33,.22)}
.chip.on{border-color:var(--accent);color:var(--accent-deep);background:var(--accent-soft)}
.tag{border-width:1px;border-radius:var(--radius-pill);text-transform:none;letter-spacing:.02em;
  font-family:var(--font-mono)}

/* 表格：发丝分割线 + 悬停暖底 */
.tbl tbody td{border-bottom:1px solid var(--hair)}
.tbl tbody tr:hover{background:rgba(47,134,224,.05)}
.row-item{border-bottom:1px solid var(--hair)}
.check{border-bottom:1px solid var(--hair)}

/* 状态点：3px 淡光晕（与登录页一致） */
.dot.ok{box-shadow:0 0 0 3px rgba(46,158,107,.18)}
.dot.warn{box-shadow:0 0 0 3px rgba(200,135,26,.18)}
.dot.err{box-shadow:0 0 0 3px rgba(208,69,60,.18)}

/* 数值：等宽 tabular */
.kpi .v,.stat .v,.metric .v,.dual .v,.meter .v,.big-num{
  font-family:var(--font-mono);font-variant-numeric:tabular-nums;
}

/* 进度条 / 仪表：暖色渐变 */
.bar-fill,.meter-fill,.progress-fill{
  background:linear-gradient(90deg,var(--accent),#86c9d8);
}
.meter-fill.dim{background:#cbd5df}

/* 侧栏与顶栏：玻璃 */
.sidebar,.side{background:var(--glass);backdrop-filter:blur(14px);border-right:1px solid var(--hair)}
.topbar,.top{background:rgba(255,255,255,.78);backdrop-filter:blur(14px);border-bottom:1px solid var(--hair)}
.brand{color:var(--text)}
.brand .mark,.logo,.brand-mark{
  background:linear-gradient(180deg,#4a9df0,#1f6fc4);color:#fff;
  box-shadow:0 8px 20px -10px rgba(31,111,196,.55);
}

/* 滚动条：浅色 */
::-webkit-scrollbar-thumb{background:#c3d6ea;border:3px solid var(--bg)}
::-webkit-scrollbar-thumb:hover{background:#a6bed6}

/* 代码块：浅底深字 */
.code{background:#f6f8fa;color:#2f3b46;border:1px solid var(--hair);border-radius:var(--radius-sm)}
.code .k{color:#17539a}.code .s{color:#8a5c10}.code .n{color:#2c5c80}

/* 图表：网格线/坐标轴跟随令牌 */
.chart .grid-line{stroke:rgba(19,26,33,.10)}
.chart .axis-line{stroke:rgba(19,26,33,.18)}
.chart text{fill:var(--text-3)}

/* 球场示意：改浅草色 */
.pitch{background:repeating-linear-gradient(0deg,#eef5ea,#eef5ea 8.5%,#e4eedd 8.5%,#e4eedd 17%)}
.pitch .line{border-color:rgba(19,26,33,.16)}
.pitch .dot{background:#cfe4f8;color:#17539a;border-color:var(--accent);box-shadow:0 4px 10px -4px rgba(14,28,45,.35)}

/* 遮罩 */
.scrim{background:rgba(19,26,33,.32);backdrop-filter:blur(2px)}

/* 入场：与登录页同一条缓动曲线 */
@keyframes tmRise{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:none}}
.main > *,.panel,.fn-card,.league-tile{animation:tmRise .7s var(--ease) both}
.panel:nth-child(2){animation-delay:.07s}
.panel:nth-child(3){animation-delay:.14s}
.panel:nth-child(4){animation-delay:.21s}
@media (prefers-reduced-motion:reduce){
  .main > *,.panel,.fn-card,.league-tile{animation:none}
}

/* 窄栏（DSH 侧边浏览器 ~520px）：内容区与顶栏允许横向滚动，
   避免固定最小宽度的表格/按钮被裁掉后无法查看（只放开滚动，不改宽度、不隐藏内容）。 */
@media (max-width:900px){
  .content{overflow-x:auto}
  .topbar{overflow-x:auto;padding:0 12px;gap:10px}
  .btn,.who,.tb-actions{white-space:nowrap}
}
"""


def main() -> int:
    dry = "--dry-run" in sys.argv
    src = TPL.read_text(encoding="utf-8")
    out = src
    report = []

    # 1) 令牌块
    m = re.search(r":root\{.*?\n\}", out, re.S)
    if not m:
        print("!! 找不到 :root 令牌块")
        return 1
    report.append((":root 令牌块", 1, 1))
    out = out[:m.start()] + NEW_TOKENS + out[m.end():]

    # 2) body::before 背景
    m = re.search(r"body::before\{.*?\n\}", out, re.S)
    if not m:
        print("!! 找不到 body::before")
        return 1
    report.append(("body::before 背景", 1, 1))
    out = out[:m.start()] + NEW_BODY_BG + out[m.end():]

    # 3) rgba 映射
    for pat, new in RGBA_RULES:
        out, n = re.subn(pat, new, out)
        report.append((pat[:34], n, n))

    # 4) hex 映射
    low = out.lower()
    for old, new in HEX_RULES:
        n = low.count(old)
        if n:
            out = re.sub(re.escape(old), new, out, flags=re.I)
            low = out.lower()
        report.append((old + " → " + new, n, n))

    # 4b) JS 裸 RGB 三元组
    for old, new in BARE_RULES:
        n = out.count(old)
        if n:
            out = out.replace(old, new)
        report.append(("裸三元组 " + old + " → " + new, n, n))

    # 5) 设计语言层（幂等：已插入过就"整段替换"，避免重复追加）
    #    标记用「设计语言对齐层」这个稳定子串 —— 层标题换过两次措辞
    #    (登录页 → 参照稿)，用带前缀的旧标题当标记会在改名后判定失败,
    #    从而把整层再追加一遍(实测踩过: 模板 +5.9KB 双份 CSS)。
    marker = "设计语言对齐层"
    idx = out.find(marker)
    if idx >= 0:
        start = out.rfind("/*", 0, idx)
        end = out.find("</style>", idx)
        if start >= 0 and end >= 0:
            out = out[:start] + LAYER.lstrip("\n") + "\n" + out[end:]
            report.append(("设计语言对齐层(已存在, 已更新)", 1, 1))
    else:
        end = out.rfind("</style>")
        if end < 0:
            print("!! 找不到 </style>")
            return 1
        out = out[:end] + LAYER + out[end:]
        report.append(("设计语言对齐层(新插入)", 1, 1))

    hits = sum(1 for _, n, _ in report if n)
    print("命中 %d 条规则：" % hits)
    for name, n, _ in report:
        if n:
            print("  %-40s %d 处" % (name, n))
    if not dry:
        TPL.write_text(out, encoding="utf-8")
        print("\n已写回 tools/console_template.html（%d → %d 字符，+%d）"
              % (len(src), len(out), len(out) - len(src)))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
