# 足球分析系统 · UI 设计规范

> 版本 **v2.0** · 适用前端 `frontend/app.py`、后台 `frontend/admin.py`、设计系统 `frontend/theme.py`、文案层 `frontend/i18n.py`
>
> 本规范描述**已实现**的视觉与交互约定。所有数值均与 `frontend/theme.py` 中的实现一一对应，修改样式前请先同步本文档。

---

## 0. 适用范围与硬约束

本规范覆盖 UI 层四个文件，可自由重构样式与布局；以下约束在任何改动中都不得突破（与 `docs/UI协作交接说明.md` 一致）：

| 约束 | 说明 |
|---|---|
| 数据层只读 | 不得修改 `src/`、`scripts/`、`models/`、`config/`、`data/` 与数据库模式；UI 仅通过 SQLite 只读或 API 取数 |
| 令牌键不可改名 | `theme.T` 中已有键名（`bg0`/`t1`/`accent` …）保持向后兼容，新增颜色只能**追加** |
| 页面条目不可删除 | 现有 Tab 与页面条目只能重样式、重排序，不能删除 |
| 空数据不隐藏 | 空数据一律走 `theme.empty_state(...)` 并给出填充命令，绝不隐藏、绝不抛错 |
| 文案全量 i18n | 所有面向用户的文案经 `i18n.t()` 输出，中英双语必须完整 |
| 单一样式源 | 前端与后台引用**同一份** `UNIFIED_CSS`，禁止各自内联 `<style>` |
| 访问地址 | 统一使用 `127.0.0.1`，不用 `localhost` |

---

## 1. 设计定位

设计语言：**Dark Pitch Console（深色球场控制台）**。

三条视觉主张：

1. **球场墨绿做底，不做纯黑** —— 背景是四层递进的草场墨绿，而非 #000，避免"控制台=黑底"的廉价感。
2. **主色克制，一处一亮** —— 只用一种高饱和强调色（球场绿 `#00e676`），其余语义色（金/紫/蓝/红）仅承担信息分类，不参与装饰。
3. **发光来自内容，不来自容器** —— 光晕只出现在状态点、品牌标记、Hero 角落；卡片本身只用 1px 描边与极浅内阴影，不做玻璃拟态与大面积辉光。

禁止出现的"AI 味"元素：白底紫渐变、Inter/Roboto 默认字体、大面积高斯模糊玻璃卡、无意义的等距 3D 插画、emoji 充当图标。

---

## 2. 色彩系统

### 2.1 令牌表（`theme.T`）

**背景层级** —— 由深到浅，对应画布 → 侧栏 → 面板 → 悬浮：

| 令牌 | 色值 | 用途 |
|---|---|---|
| `bg0` | `#07130d` | 应用画布（`.stApp`） |
| `bg1` | `#0b1c13` | 侧边栏底色、Tab 轨道 |
| `bg2` | `#0f2418` | 卡片 / 面板 / 输入框 / 表格底 |
| `bg3` | `#142e1f` | 悬浮态（卡片 hover、Tab hover、表头） |

**文本层级**：

| 令牌 | 色值 | 用途 |
|---|---|---|
| `t1` | `#e8f5ec` | 主文本、标题、数值 |
| `t2` | `#9db8a8` | 正文、说明、表格单元格 |
| `t3` | `#729e80` | 弱化文本：面包屑、页脚、维度标签、表头小字 |

**强调与语义色**：

| 令牌 | 色值 | 语义 | 典型场景 |
|---|---|---|---|
| `accent` | `#00e676` | 主色 / 正常 | 主按钮、选中态、正常状态点 |
| `accent2` | `#00b85e` | 主色暗阶 | 渐变终点、品牌标记 |
| `accent_ink` | `#04170c` | 主色上的墨色 | **仅**用于渐变按钮内部文字 |
| `gold` | `#ffb300` | 待处理 / 警告 | 待填充徽标、warn 状态盒 |
| `blue` | `#4a9eff` | 信息 | info 状态盒、信息徽标 |
| `purple` | `#a78bfa` | 模型 / AI | AI 相关功能卡、模型分区 |
| `red` | `#ff5252` | 异常 | 错误状态盒、失败徽标 |

**浅底（12% 透明度）**：`accent_soft` / `gold_soft` / `purple_soft` / `blue_soft` / `red_soft`，用于状态盒背景、徽标底色、选中态填充。

**描边**：

| 令牌 | 值 | 用途 |
|---|---|---|
| `line` | `rgba(255,255,255,0.07)` | 常规分隔线、卡片描边 |
| `line_strong` | `rgba(255,255,255,0.12)` | 表头下边框等强分隔 |
| `line_accent` | `rgba(0,230,118,0.22)` | 强调描边：卡片 hover、空状态虚线框 |

### 2.2 语义色使用规则

- **一屏一强调**：同一视区内 `accent` 的高饱和使用点不超过 3 处（如选中项、主按钮、状态点）。
- **语义色不装饰**：`gold`/`purple`/`blue`/`red` 必须对应真实语义（待处理/模型/信息/异常），不得为"好看"而随机上色。
- **渐变只用于两处**：品牌标记 `.b-mark` 与主按钮，方向固定 `135deg`。
- **新增颜色只能追加**：需要新色时在 `T` 中新开键名，并回填本表。

### 2.3 对比度核算（WCAG 2.1）

实测各文本色在四层背景上的对比度（脚本核算，非估算）：

| 前景 | 色值 | on bg0 | on bg1 | on bg2 | on bg3 | 结论 |
|---|---|---|---|---|---|---|
| `t1` | `#e8f5ec` | 16.88 | 15.72 | 14.55 | 12.99 | AA |
| `t2` | `#9db8a8` | 8.89 | 8.28 | 7.66 | 6.84 | AA |
| `t3` | `#729e80` | 6.24 | 5.81 | 5.38 | 4.80 | AA |
| `accent` | `#00e676` | 11.35 | 10.57 | 9.78 | 8.73 | AA |
| `gold` | `#ffb300` | 10.56 | 9.83 | 9.10 | 8.12 | AA |
| `purple` | `#a78bfa` | 6.96 | 6.49 | 6.00 | 5.36 | AA |
| `blue` | `#4a9eff` | 6.88 | 6.41 | 5.93 | 5.29 | AA |
| `red` | `#ff5252` | 5.94 | 5.53 | 5.12 | 4.57 | AA |

**全部文本色在所有背景上 ≥ 4.5:1**。

- `t3` 原值 `#6b9478` 在 `bg3` 上仅 4.26:1，未达 AA 正文标准，已提亮至 `#729e80`（色相不变）。这是唯一一次为合规而调整的令牌值，**若需回退必须同步复核卡片 hover 态**。
- `accent_ink`（`#04170c`）不参与本表：它只作为渐变按钮**内部**文字色，不存在"文字铺在背景上"的场景。

---

## 3. 字体系统

### 3.1 字体栈

三套字体均为 Streamlit **本地内置**（离线可用，不依赖 CDN），同时用它们替换系统默认的 Inter / Segoe UI —— 这是消除"模板感"的第一步。

| 令牌 | 字体栈 | 用途 |
|---|---|---|
| `FONT_SANS` | `"Source Sans", -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", "Hiragino Sans GB", "Microsoft YaHei", sans-serif` | 界面正文与全部控件 |
| `FONT_DISPLAY` | `"Source Serif", Georgia, "Songti SC", "Times New Roman", serif` | 拉丁展示数字与斜体副题（**克制使用**） |
| `FONT_MONO` | `"Source Code Pro", ui-monospace, SFMono-Regular, Menlo, Consolas, monospace` | 代码、路径、命令 |

规则：

- 中文形体由栈尾 `PingFang SC` / `Microsoft YaHei` 接管回退，**不引入中文 Web 字体**（体积与离线约束）。
- `FONT_DISPLAY` 只用于：Hero 大数字 `.hero-stat .v`、品牌副题 `.b-sub`（斜体）。除此之外一律 `FONT_SANS`。
- 全局开启 `-webkit-font-smoothing: antialiased` 与 `font-feature-settings: "kern" 1`；数值一律 `font-variant-numeric: tabular-nums` 保证等宽对齐。

### 3.2 字号层级

| 层级 | 字号 | 字重 | 颜色 | 实现位置 |
|---|---|---|---|---|
| 页面主标题 `h1` | 1.7rem | 700 | `t1` | `h1` |
| 页面头标题 `.ph-title` | 1.62rem | 700 | `t1` | `.page-head` |
| Hero 标题 | 1.28rem | 700 | `t1` | `.hero h2` |
| 区块标题 `h2` | 1.24rem | 650 | `t1` | `h2` |
| 区块条 `.sec` | 1.0rem | 650 | `t1` | `.sec` |
| `h3` | 1.0rem | 600 | `t1` | `h3` |
| KPI 数值 `.mc-value` | 1.68rem | 700 | `t1` | `.metric-card` |
| Hero 数值 `.hero-stat .v` | 1.6rem | 700 | `accent` | `FONT_DISPLAY` |
| 品牌标题 `.b-title` | 0.98rem | 700 | `t1` | `.brand` |
| 卡片标题 `.ic-title` | 0.92rem | 650 | `t1` | `.info-card` |
| `h4` | 0.92rem | 600 | `t2` | `h4` |
| 页面头副题 `.ph-sub` | 0.89rem | 400 | `t2` | `.page-head` |
| 正文 / 状态行 | 0.86rem | 400 | `t2` | `.status-row` `.hero p` |
| 按钮 / Tab | 0.85rem | 550–600 | `t1`/`t2` | `.stButton` `.stTabs` |
| 信息行 `.ic-line` | 0.83rem | 400 | `t2` | `.info-card` |
| 区块副题 `.sec-sub` | 0.8rem | 400 | `t3` | `.sec` |
| 弱化信息行 `.ic-line.dim` | 0.78rem | 400 | `t3` | `.info-card` |
| 筛选胶囊 `.chip` | 0.78rem | 400–600 | `t3`/`accent` | `.chip-row` |
| 页面头元信息 `.ph-meta` | 0.78rem | 400 | `t3` | `.page-head` |
| 卡片提示 `.mc-hint` | 0.76rem | 400–600 | `t2` | `.metric-card` |
| KPI 维度标签 `.mc-top` | 0.75rem | 600 | `t3` | 大写 + `0.06em` 字距 |
| 品牌副题 `.b-sub` | 0.75rem | 400 | `t3` | `FONT_DISPLAY` 斜体 |
| 页脚 `.app-footer` | 0.74rem | 400 | `t3` | `0.02em` 字距 |
| 面包屑 `.ph-crumb` | 0.74rem | 400 | `t3` | 大写 + `0.08em` 字距 |
| 侧栏分组标 | 0.74rem | 600 | `t3` | 大写 + `0.1em` 字距 |
| 侧栏胶囊标 `.side-cap` | 0.72rem | 600 | `t3` | 大写 + `0.1em` 字距 |
| 徽标 `.badge` | 0.73rem | 600 | 语义色 | `.badge-*` |

规则：

- **字重只用 400 / 600 / 650 / 700 四档**，不用 300 细体（深色背景上细体发虚）。
- 大写文本必须同时给 `letter-spacing`（0.02–0.1em），否则中英混排会挤在一起。
- 标题统一 `text-wrap: balance`，避免孤字换行。

---

## 4. 空间系统

### 4.1 间距刻度

以 **4px 为基准**，实现中使用的档位：

| 档位 | 值 | 用途 |
|---|---|---|
| 1 | 0.35rem / 5.6px | 标签与图标的内联间隙 |
| 2 | 0.45rem / 7.2px | 图标与文字间隙 |
| 3 | 0.55–0.62rem / 8.8–10px | 紧凑行内边距、状态行上下距 |
| 4 | 0.7rem / 11.2px | 移动端容器左右内边距 |
| 5 | 0.85–0.95rem / 13.6–15.2px | 卡片内边距（紧凑）、状态盒内边距 |
| 6 | 1rem / 16px | 卡片内边距（标准）、平板容器内边距 |
| 7 | 1.15–1.25rem / 18.4–20px | 卡片内边距（宽松）、区块上边距 |
| 8 | 1.4–1.55rem / 22.4–24.8px | 空状态内边距、页面顶部留白 |
| 9 | 1.5–1.7rem / 24–27.2px | Hero 内边距 |
| 10 | 2.2–3rem / 35.2–48px | 页脚上边距、页面底部留白 |

规则：同一容器内间距用**同一档或相邻一档**；卡片内边距"上下略小于左右"（如 `1rem 1.15rem`）以视觉上更稳。

### 4.2 容器与栅格

- 主容器 `.block-container`：`max-width: 1560px`，`padding-top: 1.55rem`，`padding-bottom: 3rem`。
- 卡片栅格由 Streamlit `st.columns` 控制；卡片一律 `height: 100%` 保证同行等高。
- 侧栏 `.block-container` 单独收紧到 `padding-top: 1.1rem`。
- 文本最大宽度：页面副题 `78ch`、Hero 正文 `70ch` —— 控制行长在可读区间。

### 4.3 响应式断点

四档，**移动优先的收窄策略：逐级降低容器宽度与字号，不清除任何功能**。

| 断点 | 目标设备 | 主要变化 |
|---|---|---|
| `max-width: 1440px` | 桌面超宽 | 容器收窄至 1360px |
| `max-width: 1024px` | 平板横屏 / 小笔记本 | 容器左右内边距 1rem；`.page-head` 转列；`.hero` 转列、统计项换行 |
| `max-width: 768px` | 平板竖屏 | `h1` 1.45rem、`.ph-title` 1.35rem；Hero 数值 1.25rem；KPI 卡 min-height 92px、数值 1.42rem |
| `max-width: 480px` | 手机竖屏 | 容器 `padding: 0.7rem`、顶部 1rem；`h1` 1.28rem、`.ph-title` 1.18rem；品牌标题 0.9rem；`.sec` 0.95rem；KPI 数值 1.3rem；Hero 统计间距 0.85rem |

> 移动基准宽度 **375px** 由 480px 档覆盖 —— 用 480 作阈值可同时兜住 376–480px 的大屏手机区间；若阈值设为 375，该区间将失去降级规则。

---

## 5. 形状与层级

### 5.1 圆角

| 令牌 | 值 | 用途 |
|---|---|---|
| `r1` | 8px | 按钮、输入框、Tab、状态盒、侧栏项、导航按钮 |
| `r2` | 12px | 卡片（KPI / 功能 / 信息）、表格容器、Tab 轨道 |
| `r3` | 16px | Hero 横幅、空状态容器 |

补充：胶囊 999px（徽标 / 筛选项）、代码块 5–6px、品牌标记 9px、状态点与步骤序号 50%、焦点描边 4px。

规则：**圆角不超过容器短边的 1/4**；嵌套容器内层圆角比外层小一档。

### 5.2 阴影

| 场景 | 值 |
|---|---|
| 卡片（默认） | `inset 0 1px 0 rgba(255,255,255,0.025), 0 1px 2px rgba(0,0,0,0.22)` |
| 抬升令牌 `shadow` | `0 10px 28px rgba(0,0,0,0.35)` |
| 发光（品牌标记） | `0 0 18px rgba(0,230,118,0.28)` |
| 发光（状态点） | `0 0 8px <当前状态色>` |

规则：深色主题下阴影几乎不可见，**层次主要靠 1px 描边 + 背景层级差**表达；发光只给"品牌"与"状态"两类元素，点缀式使用。

### 5.3 层级

- 背景层级由 `bg0→bg3` 四档承担（见 2.1），不依赖 z-index 堆叠。
- `z-index` 仅在局部使用：Hero 文案与统计块 `z-index: 1`，压在其装饰圆斑之上。
- 固定/隐藏：`#MainMenu, footer { visibility: hidden; }` 隐藏 Streamlit 自带菜单与页脚。

---

## 6. 图标系统

**禁用 emoji 作为图标。** 全站图标统一使用 Streamlit 内置的 **Material Symbols Rounded** 矢量字体（离线可用）。

### 6.1 两种写法

| 写法 | 适用场景 | 示例 |
|---|---|---|
| 短代码 `:material/icon_name:` | Streamlit 原生组件参数（如 `st.set_page_config(page_icon=...)`）、markdown 文本节点 | `page_icon=":material/sports_soccer:"` |
| HTML `<span class="msr">icon_name</span>` | 一切经 `theme.py` 助手注入的 HTML 块 | `<div class="sec"><span class="msr">home</span> 标题</div>` |

### 6.2 关键机制（务必理解，否则图标会显示成字面文字）

Streamlit 的短代码替换**只作用于 markdown 的 text 节点**：其 remark 插件基于 `unist-util-find-and-replace` 遍历 `text` 节点，而 `unsafe_allow_html=True` 的 HTML 块走 rehype-raw 直出。因此：

> 在 `<div>...</div>` 这类 HTML 块内部写 `:material/home:`，页面上会**原样显示为字面字符串**，不会渲染成图标。

设计系统已在 `theme.py` 中统一解决：

```python
_MATERIAL_RE = re.compile(r":material/([A-Za-z0-9_]+):")

def _icon(html):
    return _MATERIAL_RE.sub(
        lambda m: f'<span class="msr" aria-hidden="true">{m.group(1)}</span>',
        str(html))
```

- `_flat()`（压平多行 HTML 的助手）内部已调用 `_icon()`；
- 5 个不经过 `_flat()` 的助手（`section` / `section_cap` / `status_box` / `nav_link` / `badge`）各自显式调用 `_icon()`；
- **新增任何直接 `st.markdown(..., unsafe_allow_html=True)` 的 HTML 助手，必须自己套一层 `_icon(...)`。**

### 6.3 字形样式

`.msr` 及 `[data-testid="stIconMaterial"]`：

```css
font-family: "Material Symbols Rounded" !important;
font-size: 1.05em; line-height: 1;
font-variation-settings: "FILL" 0, "wght" 400, "GRAD" 0, "opsz" 24;
vertical-align: -0.135em;   /* 文字行内为 -0.16em */
```

### 6.4 图标选用

- 只能使用 `streamlit/material_icon_names.py` 中 `ALL_MATERIAL_ICONS` 收录的名称（4271 个）。
- 语义固定化：`sports_soccer` 品牌 / `home` 首页 / `bar_chart` 数据 / `target` 预测 / `smart_toy` AI / `database` 数据源 / `settings` 后台 / `sensors` 系统状态 / `build` 运维工具。
- 图标不单独承载信息，必须与文字标签同时出现（`aria-hidden="true"`，装饰性）。

---

## 7. 组件库（`theme.py`）

共 26 个助手。**函数签名保持向后兼容，不得重命名或删除参数。**

### 页面骨架

| 函数 | 签名 | 说明 |
|---|---|---|
| `apply_theme()` | `()` | 注入 `UNIFIED_CSS`，前端与后台各调一次 |
| `page_header` | `(title, subtitle=None, icon="", meta=None, breadcrumb=None)` | 页面头：标题 + 副题 + 面包屑 + 右侧元信息 + 主色短下划线 |
| `section` | `(title, subtitle=None, icon="")` | 区块条：左侧 3px 主色竖线 + 标题 + 副题 |
| `section_title` | `(title, subtitle=None)` | `section` 的别名，兼容旧调用 |
| `section_cap` | `(text, icon=":material/sensors:")` | 侧栏/分区小标签（大写 + 字距） |
| `divider()` | `()` | 1px 分隔线 |
| `app_footer` | `(text="足球数据分析与AI预测系统 · 毕业设计项目")` | 页脚 |
| `brand_header` | `(title="足球分析系统", subtitle="Football Analytics", mark=":material/sports_soccer:")` | 侧栏品牌区（渐变徽标 + 标题 + 斜体副题） |
| `sidebar_footer` | `(app_name="足球分析系统")` | 侧栏底部版本信息 |

### 内容块

| 函数 | 签名 | 说明 |
|---|---|---|
| `hero` | `(title, desc="", stats=None, icon="")` | 欢迎横幅：渐变底 + 角落光斑 + 右侧统计组 |
| `metric_row` | `(items)` | KPI 卡行。`item` 支持元组 `(v, label, hint, icon, color)` 或 `dict` |
| `card_metric` | `(label, value, delta=None, icon="", color=None)` | 单张 KPI 卡 |
| `metric_row` 配套类 | `.metric-card` / `.mc-top` / `.mc-value` / `.mc-hint` | 兼容旧标记 `.metric-value` / `.metric-label` |
| `feature_card` | `(icon, title, items, color=None)` | 功能卡：图标 + 标题 + 要点列表 |
| `info_card` | `(title, lines, icon="", color=None)` | 信息卡：`lines` 中 `(文本, True)` 表示弱化行 |
| `status_box` | `(status_type, message)` | 状态盒，取值 `info` / `success` / `warn` / `error` |
| `empty_state` | `(icon, title, desc, command=None)` | 空状态（虚线框 + 图标 + 标题 + 描述 + 填充命令），**空数据必须走这里** |
| `status_row` | `(label, value=None, state="ok")` | 单行状态，`state` 取值 `ok` / `off` / `warn` / `err` / `live` |
| `status_list` | `(rows)` | 状态行清单 |
| `step_list` | `(steps)` | 带圆形序号的步骤清单 |
| `badge` | `(text, kind="ok")` | 徽标，`kind` 取值 `ok` / `wait` / `info` / `err` / `mute` |
| `chip_row` | `(items, active=None)` | 静态筛选胶囊行（展示用，非交互控件） |
| `code_chip` | `(text)` | 行内代码片 |
| `nav_link` | `(url, label, icon="")` | 跳转按钮（新窗口） |

### 状态盒与徽标配色对照

| 类型 | 背景 | 左边框/文字 |
|---|---|---|
| `info` / `badge-info` | `blue_soft` | `blue` |
| `success` / `badge-ok` | `accent_soft` | `accent` |
| `warn` / `badge-wait` | `gold_soft` | `gold` |
| `error` / `badge-err` | `red_soft` | `red` |
| `badge-mute` | `rgba(255,255,255,0.05)` | `t3` |

---

## 8. 交互反馈

### 8.1 指针光标

| 元素 | 光标 |
|---|---|
| 按钮、下载按钮、链接按钮、Tab、单选/复选标签、展开器标题、下拉框、文件上传、滑块、分页、聊天发送、导航按钮 | `pointer` |
| 文本输入、数字输入、多行文本 | `text` |

### 8.2 过渡

- 时长统一落在 **150–300ms**（实现取 0.15s / 0.18s / 0.2s）。
- **禁止 `transition: all`** —— 只声明实际变化的属性，避免布局属性被意外动画化。
- 典型声明：
  - 卡片：`border-color .18s ease, transform .18s ease, background .18s ease`
  - 按钮：`background .2s ease, color .2s ease, border-color .2s ease, transform .2s ease`
  - Tab / 展开器：`background .2s ease, color .2s ease`
  - 侧栏项：`background .15s ease, color .15s ease`

### 8.3 三态齐备

每个可交互元素必须具备 **默认 / 悬停 / 选中或聚焦** 三态，且状态切换不做纯色突变：

- 卡片 hover：描边转 `line_accent` + `translateY(-2px)` + 底色升到 `bg3`。
- 按钮 hover：底色转 `accent_soft`、文字转 `accent`、描边转 `accent`、`translateY(-1px)`。
- 侧栏选中：左侧 2px 主色竖条 + 左向右的 `accent_soft` 渐变填充 + 文字转 `accent` 且加粗到 650。
- Tab 选中：`accent_soft` 底 + `accent` 文字；隐藏 BaseWeb 默认高亮条，改用色块表达。
- 主区横向 radio：呈现为筛选胶囊，选中态加主色描边与浅底。

---

## 9. 无障碍

- **对比度**：全部文本色在全部背景上 ≥ 4.5:1（核算见 2.3）。
- **焦点态**：`:focus-visible` 统一 2px `accent` 描边 + 2px 偏移 + 4px 圆角；侧栏项、按钮、展开器标题额外显式声明，避免被组件库默认样式覆盖。
- **动效偏好**：`@media (prefers-reduced-motion: reduce)` 下把动画与过渡时长压到 0.001ms，并移除卡片的 `translateY` 位移。
- **图标**：装饰性图标一律 `aria-hidden="true"`，不重复朗读文字已表达的信息。
- **不依赖颜色单独传意**：状态除了颜色外还有文字标签（徽标文字、状态行数值），色盲用户可读。
- **控制行长**：正文最大 78ch / 70ch，避免超宽屏下阅读疲劳。

---

## 10. 文案与国际化

- 所有面向用户的字符串经 `i18n.t()` 输出；**中文为键**，`EN` 字典保存英文。
- 新增文案必须**同时补中英两侧**，不允许只写中文或只写英文。
- 文案中不内嵌 emoji，也不内嵌图标短代码（图标由组件参数传入，不写进文案字符串）。
- 术语统一：

| 中文 | 英文 | 说明 |
|---|---|---|
| 命中 | Hit | 预测命中 |
| 待填充 | Pending | 数据未导入 |
| 完整 | Ready | 数据已就绪 |
| 预期进球 | xG | 保留 2 位小数 |
| 身价 | Market Value | 单位 M€ |

---

## 11. 交付检查清单

改动 UI 后逐项确认：

1. `py -3.13 -m py_compile frontend/{theme,app,admin,i18n,viz}.py` 通过。
2. 刷新 `http://127.0.0.1:8501` 与 `http://127.0.0.1:8502`，页面**无红色错误框**。
3. 页面文本中不存在字面 `:material/` 字符串（说明 HTML 块内短代码已被 `_icon()` 归一化）。
4. 空数据场景渲染为 `empty_state` 且带填充命令，页面不隐藏、不报错。
5. i18n 无残留硬编码中文（文案均已进字典）。
6. 表列名与单位一致：xG 保留 2 位小数、身价单位 M€。
7. 新增/修改的助手函数是否遗漏 `_icon()` 包裹。
8. 浏览器缩放到 480 / 768 / 1024 / 1440 四档宽度，无横向滚动条、无内容截断。

---

## 12. 禁止事项

| 禁止 | 原因 |
|---|---|
| 用 emoji 当图标 | 跨平台字形不一致，且无法统一尺寸与颜色 |
| 在 HTML 块内直写 `:material/x:` 短代码 | 会显示为字面文字（见 6.2） |
| `transition: all` | 会连带动画布局属性，造成卡顿与抖动 |
| 重命名 / 删除 `theme.T` 已有键 | 破坏前端与后台的共享契约 |
| 删除 Tab 或页面条目 | 违反交接说明硬约束 |
| 前端 / 后台各自内联 `<style>` | 样式分叉，规范失效 |
| 引入 CDN 字体或联网资源 | 破坏离线可用性 |
| 白底紫渐变、玻璃拟态、大面积辉光 | 模板味与 AI 味的典型特征 |
| 用 `localhost` 替代 `127.0.0.1` | 与运行环境约定不符 |
