# UI 协作交接说明（数据/模型 ↔ UI 设计）

> 本文档用于**两方并行开发**时对齐边界。数据与模型由我（数据/模型侧）维护；
> UI 由 UI 侧（Trae）维护。请先读第 1、2、6 节，再看数据契约与组件库。

---

## 1. 分工边界（重要）

| 层 | 目录 / 文件 | 归属 | 说明 |
|---|---|---|---|
| **UI 层** | `frontend/admin.py`、`frontend/app.py`、`frontend/theme.py`、`frontend/i18n.py` | **UI 侧** | 可自由重构样式、布局、组件、交互 |
| 数据/模型层 | `src/`、`scripts/`、`models/`、`config/`、`data/` | **数据侧（我）** | UI 不改这些目录 |
| 文档 | `docs/` | 各自新增，不改对方文件 | — |

**协作规则**

1. UI **只读取**数据（SQLite 只读 / 调 API），**不要改数据库表结构**；需要新字段、新表、新视图 → 提给我，我来加并保证数据填充；
2. UI 需要新的**派生字段**（如"胜率""场均 xG"）时，优先在 SQL 里算，不必新增列；
3. 我改动数据层时会**保持字段名向后兼容**；若必须改字段，我会在本文档追加"变更记录"并通知；
4. 两边都要避免"删除对方新增的页面/组件"，重构样式没问题。

---

## 2. 运行环境

```powershell
# 用户端(8 页)          http://127.0.0.1:8501
python -m streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501

# 管理后台(10 Tab)      http://127.0.0.1:8502
python -m streamlit run frontend/admin.py --server.address 127.0.0.1 --server.port 8502

# 后端 API(Swagger)     http://127.0.0.1:8000/docs
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
```

- 数据库：`data/database/football.db`（SQLite，单文件）
- 主要依赖：`streamlit`、`pandas`、`numpy`、`requests`、`xgboost`、`joblib`
- 请用 **127.0.0.1**（不要用 localhost）

**编译自检**

```powershell
python -m py_compile frontend/admin.py frontend/app.py frontend/theme.py frontend/i18n.py
```

---

## 3. 数据契约（UI 可直接查询的表）

### 3.1 核心表

| 表 | 规模 | 关键字段 |
|---|---|---|
| `matches` | 12,564 | `match_id, date, season, league_id, home_team_id, away_team_id, home_goals, away_goals, ht_home, ht_away, home_shots/away_shots, home_sot/away_sot, home_corners/away_corners, home_xg/away_xg（官方xG）, home_xg_proxy/away_xg_proxy（代理xG）, status（FT/NS）, referee, venue, af_fixture_id` |
| `teams` | 250 | `team_id, name, name_en, league_id, logo_url, stadium, capacity, founded, manager（待填充）` |
| `players` | 4,851 | `player_id, team_id, name, position, number, age, nationality, height, weight, foot, market_value, photo_url, tm_player_id, af_player_id` |
| `leagues` | 10 | `league_id, name` |
| `standings` | 497 | `league_id, season, team_id, rank, points, played, win, draw, loss, goals_for, goals_against` |
| `transfers` | 170,663 | `player_name, from_team_name, to_team_name, transfer_date, transfer_fee, transfer_type, season, source（qxz/transfermarkt）, from_team_id, to_team_id` |
| `predictions` | 1,803 | `match_id, predicted_result, prob_home/prob_draw/prob_away, confidence, model_version, hit` |

### 3.2 Transfermarkt 层（已填充，可直接做球员/球队详情页）

| 表 | 规模 | 用途 |
|---|---|---|
| `tm_players` | 32,417 | 球员档案：`player_name, citizenship, height, foot, position, image_url, date_of_birth` |
| `tm_player_seasons` | 370,362 | 球员赛季数据：`player_id, season_start, competition_name, team_id, appearances, goals, assists, minutes, yellow_cards, red_cards` |
| `tm_player_market_value` | 901,429 | 市值历史：`player_id, value_date（ISO 日期）, date_unix（YYYYMMDD 整数，可排序）, value` |
| `tm_transfers` | 176,100 | 转会原始数据（含 `player_name`、`value_at_transfer`、`transfer_fee`） |
| `tm_player_injuries` | 94,160 | 伤病：`player_id, injury_reason, from_date, end_date, days_missed, games_missed` |
| `tm_team_seasons` | 30,150 | 球队历史赛季：`club_id, season_start, competition_name, division` |
| `tm_club_map` | 252 | **我们的 team_id ↔ TM club_id 映射**（做 TM 阵容页必用） |

### 3.2b 球员雷达图数据表 `player_radar`（**UI 直接查，勿自行计算**）

已预计算 4,745 名球员的 **7 维能力值（0–100，按同位置组百分位）**，近 3 个赛季汇总，1,817 人有真实出场数据。

| 列 | 说明 |
|---|---|
| `player_id, team_id, name, name_en, position, pos_group` | 基本信息（`pos_group` ∈ GK/DF/MF/FW/OT） |
| `age, height, weight, nationality, foot, number, photo_url` | 档案 |
| `market_value` | 身价（欧元） |
| `apps, minutes, goals, assists, cards` | 近 3 赛季原始数据 |
| `goals_p90, assists_p90, involve_p90, minutes_share, cards_p90` | 每 90 分钟效率（原始值） |
| **`s_goals, s_assists, s_involve, s_minutes, s_discipline, s_value, s_experience`** | **7 维雷达分值 0–100** |

雷达图维度建议标签：进球能力 / 助攻能力 / 进攻参与 / 出场稳定性 / 纪律性 / 身价价值 / 比赛经验
（门将的进球/助攻维度已置 0，可用 出场/纪律/身价/经验 四维 + 身高体现）

```python
# 示例：画某球员雷达图（Plotly）
import pandas as pd, sqlite3
con = sqlite3.connect("data/database/football.db")
r = pd.read_sql_query("SELECT * FROM player_radar WHERE player_id=?", con, params=(pid,)).iloc[0]
labels = ["进球能力","助攻能力","进攻参与","出场稳定性","纪律性","身价价值","比赛经验"]
vals = [r.s_goals, r.s_assists, r.s_involve, r.s_minutes, r.s_discipline, r.s_value, r.s_experience]
```

### 3.2c 球员姓名：中英文已合并为同一行

`players` 表**同队同人不再有两条记录**（已合并 106 组）。现在：

- `name` = 中文名（球小策，若存在）→ **UI 主显示**
- `name_en` = 英文名 → 语言切换或副标题显示

> 请勿再把中文行与英文行当两条球员展示；建议显示为 `name`（副标题 `name_en`）。

### 3.2d 可视化专用分析表（**已预计算，直接查表出图，勿在页面里重算**）

| 表 | 行数 | 用途 / 建议图表 |
|---|---|---|
| `team_radar` | 231 | **球队 7 维雷达**：`s_attack` 进攻 / `s_defense` 防守 / `s_dominance` 射门压制 / `s_discipline` 纪律 / `s_value` 身价 / `s_experience` 经验 / `s_stability` 稳定性（0–100，同联赛内百分位）；原始值 `goals_pg, conceded_pg, shots_pg, shot_diff_pg, cards_pg, xg_pg, xga_pg, ppg, avg_age, squad_value` |
| `league_stats` | 40 | 各联赛各赛季：`goals_pg` 场均进球、`xg_pg` 场均 xG、`home_win_pct / draw_pct / away_win_pct` → **堆叠柱状图 / 折线趋势** |
| `model_metrics` | 12 | 各模型样本外指标：`acc, f1_macro, logloss, draw_recall, test_n` → **横向排行条**（按 acc 或 f1 排序） |
| `model_confusion` | 9 | 部署模型混淆矩阵（`actual, predicted, count`）→ **热力图**（共 9 格） |
| `model_calibration` | 26 | 概率校准曲线（`outcome, predicted, actual, n`）→ **折线 + 45° 参考线**，答辩加分项 |
| `feature_importance` | 40 | v7 特征重要性 Top40（`feature, importance`）→ **横向排行条** |

```python
# 球队雷达
r = pd.read_sql_query("SELECT * FROM team_radar WHERE team_id=?", con, params=(tid,)).iloc[0]
labels = ["进攻","防守","射门压制","纪律","身价","经验","稳定性"]
vals = [r.s_attack, r.s_defense, r.s_dominance, r.s_discipline, r.s_value, r.s_experience, r.s_stability]

# 模型对比排行
pd.read_sql_query("SELECT model, acc, f1_macro, logloss, draw_recall FROM model_metrics ORDER BY acc DESC", con)

# 混淆矩阵热力图
pd.read_sql_query("SELECT actual, predicted, count FROM model_confusion", con)

# 概率校准曲线
pd.read_sql_query("SELECT outcome, predicted, actual, n FROM model_calibration ORDER BY predicted", con)
```

> 这些表与 `player_radar` 一样，是我这边**预计算**的产物；数据更新后重跑
> `python scripts/build_analytics_tables.py` 即可刷新（约 1.5 分钟）。

### 3.3 待填充表（**框架已建好，UI 请做占位**）

| 表 | 字段 | 填充来源 |
|---|---|---|
| `af_lineups` | `fixture_id, af_team_id, team_name, formation, coach_name, player_id, player_name, number, pos, grid` | API-Football（`--phase lineups`） |
| `af_events` | `fixture_id, minute, extra, af_team_id, team_name, player_id, player_name, assist_name, type, detail` | API-Football（`--phase events`） |
| `af_injuries` | `af_player_id, player_name, af_team_id, team_name, fixture_id, injury_type, reason, date` | API-Football |
| `af_coaches` | `af_coach_id, name, nationality, team_id, af_team_id, start_date, end_date, is_current` | API-Football |
| `af_fixtures` | `fixture_id, league_id, season, date, home_name, away_name, referee, venue, city` | API-Football |
| `qxz_lineups` / `qxz_match_pack` | 赛前阵容 / 赛前全景包 | 球小策（付费） |

> 占位规范：无数据时用 `theme.empty_state(...)`，并附上填充命令；**不要**隐藏整个区块或报错。

### 3.4 常用查询示例

```python
import sqlite3, pandas as pd
con = sqlite3.connect("data/database/football.db")

# 最近 20 场(含裁判/场地/官方 xG)
pd.read_sql_query("""
  SELECT date(m.date) d, l.name lg, th.name home, ta.name away,
         m.home_goals, m.away_goals, m.home_xg, m.away_xg, m.referee, m.venue
  FROM matches m JOIN leagues l ON l.league_id=m.league_id
  JOIN teams th ON th.team_id=m.home_team_id
  JOIN teams ta ON ta.team_id=m.away_team_id
  WHERE m.status='FT' ORDER BY m.date DESC LIMIT 20""", con)

# 某队 TM 阵容(含身价) —— UI 的"球员详情/阵容"页
pd.read_sql_query("""
  SELECT p.player_name, p.citizenship, p.height, p.foot, p.position,
         (SELECT value FROM tm_player_market_value v WHERE v.player_id=p.player_id
          ORDER BY date_unix DESC LIMIT 1) mv
  FROM tm_players p JOIN tm_player_seasons s ON s.player_id=p.player_id
  WHERE s.team_id = ? AND s.season_start = (
      SELECT MAX(season_start) FROM tm_player_seasons WHERE team_id = ?)
  GROUP BY p.player_id ORDER BY mv DESC""", con, params=(club_id, club_id))

# 球队球员(含体重/身高/身价/惯用脚)
pd.read_sql_query("""
  SELECT name, position, number, age, nationality, height, weight, foot,
         market_value, photo_url FROM players WHERE team_id=? ORDER BY number""",
  con, params=(team_id,))
```

---

## 4. 组件库（`frontend/theme.py`）

```python
from theme import (apply_theme, page_header, section, metric_row, empty_state,
                   badge, code_chip, divider, card_metric, feature_card,
                   status_box, nav_link, sidebar_footer, T, COLORS)
```

| 组件 | 签名 | 用途 |
|---|---|---|
| `apply_theme()` | — | 注入全局样式（每个页面只调一次） |
| `page_header(title, subtitle=None, icon="", meta=None)` | 页面头部：标题+副标题+右侧元信息 | 每个页面/重要 Tab 顶部 |
| `section(title, subtitle=None, icon="")` | 区块标题（左侧强调竖条） | 内容分组 |
| `metric_row(items)` | `items=[{"value","label","hint","icon","color"}...]` 或元组 | 一行指标卡 |
| `empty_state(icon, title, desc, command=None)` | 空状态/待填充占位（带命令 chip） | 无数据区块 |
| `badge(text, kind="ok"/"wait"/"info"/"err")` | 徽标 | 状态标记 |
| `code_chip(text)` | 行内代码块 | 命令展示 |
| `divider()` | 细分割线 | 分隔 |
| `card_metric(label, value, delta=None, icon="", color=None)` | 单卡片（兼容旧调用） | — |
| `feature_card(icon, title, items, color=None)` | 功能卡 | 首页 |
| `status_box(kind, msg)` | info/success/warn/error 提示条 | — |

**设计令牌**（改主题只需改这里）

```python
T["bg0"]=#070f18  T["bg1"]=#0b1622  T["bg2"]=#101f2e  T["bg3"]=#17293c   # 背景层级
T["t1"]=#eaf2f7   T["t2"]=#9fb3c0   T["t3"]=#68808f                     # 文本三级
T["accent"]=#00d4aa  T["gold"]=#f5b301  T["purple"]=#a78bfa             # 主色/次色
T["blue"]=#4a9eff  T["red"]=#ff6b6b  T["ok"]=#22c55e                    # 语义色
T["r1"]=10px  T["r2"]=14px  T["r3"]=18px                                # 圆角
```

> ⚠️ **不要重命名** `T[...]` 的键（两个前端都在用）；需要新颜色请**追加**键。

---

## 5. 中英文切换（`frontend/i18n.py`）

```python
from i18n import t, lang_selector
lang_selector()                    # 侧边栏语言选择控件（已接好）
t("比赛数据", "Matches")            # 词条; 也可以用 t("比赛数据")（走内置词条表）
```

新页面里的所有文案请用 `t("中文", "English")` 包裹，保证双语可用。

---

## 6. 请勿改动（会破坏数据/模型链路）

1. **数据库表结构**（需要字段找我加，我会同时补数据）；
2. `src/`、`scripts/`、`models/`、`config/`；
3. `theme.py` 中 `T`/`COLORS` 的**已有键名**（可追加）；
4. 既有 Tab/页面的**入口**（可改样式、可调整顺序，但别删）。

---

## 7. 交付前自检清单

- [ ] `python -m py_compile frontend/*.py` 通过
- [ ] 刷新 8501 / 8502，**没有红色报错框**
- [ ] 无数据的区块显示 `empty_state`（不是报错、不是空白）
- [ ] 中英切换后**没有残留中文**（或反之）
- [ ] 表格列名、指标单位与本文档一致（如 xG 保留 2 位、身价用 M€）

相关文档：设计令牌与组件规范见 [UI设计规范](UI设计规范.md)；UI 侧收口评审、审计证据与打磨明细见 [UI高级审美评审报告](UI高级审美评审报告.md)、[UI合规审计报告](UI合规审计报告.md)、[UI打磨收口记录](UI打磨收口记录.md)。

---

## 8. 建议的 UI 增强方向（不限于此）

- **球员详情页**：档案 + 市值曲线（`tm_player_market_value`）+ 伤病 + 转会
- **球队页**：主教练、球场容量、TM 阵容身价、伤停名单
- **比赛详情页**：阵容/事件占位 → 数据到位即展示
- **图表化**：xG 趋势、身价曲线、积分走势（可用 `st.line_chart` / Plotly）
- **数据完整度面板**：已有（管理端「📈 数据完整度」），可做成可视化进度条
- **明暗主题切换**：全局令牌已集中，扩展成本低

---

## 10. 设计品味约束（taste-skill v2 + redesign 协议）

已安装 6 个 Agent Skill（`~/.dsh/skills/` 与项目 `.skills/`），改造 UI 时必须遵守：

| 约束 | 具体要求 | 依据 |
|---|---|---|
| **单一强调色锁** | 同一页面只用一种强调色（`T["accent"]` = 翡翠绿 #2ebd85，饱和度 62%）。金/紫/蓝/红**只能表达语义**（待处理/异常/信息/胜平负），不得用于装饰性区分 | taste §4.2 |
| **饱和度上限** | 强调色饱和度 < 80%（原 #00e676 为霓虹绿，已下调） | taste §4.2 |
| **圆角体系** | 按钮 8px / 卡片 12px / 面板 16px，全局统一，不得随手改 | taste §4.4 |
| **阴影着色** | 阴影带背景色相（`rgba(2,12,7,…)`），不用纯黑投影 | taste §4.4 |
| **交互状态** | 每个可点元素都要有 hover **与** `:active` 按压反馈（`scale(0.98)`/`translateY(1px)`）+ 可见焦点环 | taste §4.5 |
| **完整状态** | 空态（`empty_state`）必须有；错误态用内联提示，禁止裸异常；加载态仅在真的有延迟时使用 | taste §4.5 |
| **禁 emoji** | 用 `:material/xxx:` 图标，不用 emoji | taste §3.D |
| **无装饰性多色卡片** | 卡片层级用"强调 vs 中性"表达，不用彩虹色轮播 | redesign 审计 |
| **隐藏 Streamlit 外壳** | 菜单/页脚/工具栏/Deploy 按钮已由 `theme.py` 统一隐藏，不要重新引入 | redesign 审计 |

> ⚠️ **必须重启前端**：Streamlit **不会热重载 `theme.py`**（改了 CSS 刷新页面无效）。
> 改完 `theme.py` 后执行：`Stop-Process` 杀掉 8501 进程 → 重新 `streamlit run` → 再刷新浏览器。
> 改 `app.py` 只需刷新页面。

### 自查工具（无需人眼，可脚本验证）

```bash
# 1) 页面级异常检查(逐页跑真实 AppTest)
python scripts/check_ui.py --pages          # 待实现前可参考 docs 内示例

# 2) 图表渲染成 PNG 自检(Altair/Vega-Lite 图表)
ch.save("data/charts/xxx.png", scale_factor=2)

# 3) 真实界面截图(Playwright 驱动系统 Chrome, 无需下载浏览器)
python scripts/shot_ui.py                   # 待实现前可参考 docs 内示例
```

> 两个坑：① Vega-Lite 的 `mark_line` 会**按 x 值自动排序**，画多边形/雷达必须显式给
> `order` 通道；② Streamlit 内部滚动容器导致 `full_page` 截图截不到下方内容，需要滚动后再截。

---

## 11. 变更记录

| 日期 | 变更 | 影响 |
|---|---|---|
| 2026-09-12 | **修复"内容显示不全"(两处真 bug)** | ① **动效版块被裁**：iframe 高度原先按 `(n+1)//2` 估算行数，遇到横跨两列的卡片会算少一行（实际需 682px 只给了 364px）→ 改为**按实际排版分行估算** + 注入 `streamlit:setFrameHeight` 消息**自适应测高**（含 ResizeObserver 与动效结束后复测），实测所有版块"内容高度 = 可视高度"；② **页标题被切**：Streamlit 固定顶栏 `stHeader` 高 60px、不透明、`z-index 999990`，页标题顶部在 42px 处 → **实测被遮 18px** → 将顶栏压成 0 高且透明，并把侧栏折叠按钮单独固定在左上角保证可点 |
| 2026-09-12 | **明暗双主题** | `theme.py` 新增 `_DARK`/`_LIGHT` 两套**键名一致**的令牌 + `THEMES` + `current_theme()` + `theme_selector()`；`apply_theme()` 每次运行重建 CSS 并调用 `_sync_downstream()` 把配色回填给 `viz` / `blocks`（这两个模块在模块级缓存了颜色常量）。侧边栏「主题」下拉即可切换。**坑**：任何在模块级固化的 CSS（如原先 `blocks._BASE_CSS`）都必须改成函数，否则浅色下仍是深色 |
| 2026-09-12 | **浅色主题下的表格回退** | `st.dataframe` 是 canvas 渲染、跟随 Streamlit 自身主题，CSS 无法覆盖 → 浅色主题下 `show_df()` 改用 `st.table`（跟随本设计系统 CSS），超过 25 行截断并提示 |
| 2026-09-12 | **坐标轴防重叠** | `viz._ax()` 默认加 `labelOverlap="greedy"` + `labelFlush=False`；`line()`/`multi_line()` 新增 `tickCount` 参数；`rank_bar()` 数值轴限制 5 个刻度 |
| 2026-09-12 | **窄屏适配** | 主题层新增 1280/1024/760 三档媒体查询（内边距/字号/卡片间距/表格横向滚动）；`blocks.py` 改用 `clamp()` 流式字号，Bento 在 ≤700px 退化为单列，指标带 `flex-wrap` |
| 2026-09-12 | **后台 Tab 图表核查** | 「今日预测」「比赛数据」「预测复盘」三个 Tab 经核查**已有图表**（环形图/散点/排行条），本轮补齐其 `page_header` 统一版式 |
| 2026-09-12 | **全站巡检通过**：用户端 8 页 + 后台 6 页 + 后台数据浏览 8 个 Tab，**0 处运行时异常** | 可复现命令见 §10 自查工具 |
| 2026-09-12 | **后台模型管理页接入真实评估数据** | 新增「部署模型评估」区：模型对比条 / LogLoss 条 / 混淆矩阵 / 概率校准曲线 / 特征重要性 Top12（数据来自 `model_metrics` 等表）；并修正过时文案（移除未使用的 SHAP 声明，改为"集成 v2+v7 · 119 维 · 官方 xG"） |
| 2026-09-12 | **后台 Tab 页头统一** | 「今日预测」「比赛数据」补上 `page_header`，与其余 8 个 Tab 一致 |
| 2026-09-12 | **比赛详情默认选有统计的比赛** | 查询排序改为 `有技术统计 → 有 xG → 日期倒序`；修复表格"半场比分 None"（数值列仅在整列可解析为数字时才转换） |
| 2026-09-12 | **强调色降饱和** `#00e676` → `#2ebd85`（全站令牌 + 内联色一起替换） | 视觉更沉稳；若需回退只改 `theme.py` 的 `T["accent"]/["accent2"]/["accent_soft"]/["line_accent"]` 与内联 rgba |
| 2026-09-12 | **单一强调色锁**：11 处装饰性着色收敛为 accent | 卡片色轨不再五颜六色；语义色（胜平负/位置/图表系列）保留 |
| 2026-09-12 | **隐藏 Streamlit 外壳**（工具栏 / Deploy 按钮 / 状态部件） | 右上角不再出现 Deploy |
| 2026-09-12 | **新增格式化** `fmt_height()` / `fmt_nation()` | 身高显示 `180 cm`；多国籍显示 `Spain / Equatorial Guinea` |
| 2026-09-12 | **新增 6 张可视化分析表** | 见 §3.2d |
| 2026-09-12 | **新增表 `player_radar`** | 球员 7 维雷达分值（0–100）预计算完成，UI 直接查（见 §3.2b） |
| 2026-09-12 | **球员中英文合并** | `players` 同队同人只剩一行（`name` 中文 + `name_en` 英文）→ 阵容表不要再显示两行 |
| 2026-09-12 | **新增接口** `GET /api/teams/{team_name}/form?matches=10` | 返回真实近 N 场：`form`("WWDLW")、`won/drawn/lost`、`goals_for/against`、`games[]`(date/home/away/score/venue/result)。**"近10场走势"请用此接口** |
| 2026-09-12 | **积分榜全部重建**（用本库赛果计算） | `standings` 40 个(联赛,赛季)组合 / 812 行；`rank` 连续无重复；新增 `form` 近 5 场走势 |
| 2026-09-12 | **Elo 全库重算** | `teams.elo_rating` 240 支全为真实值（含欧冠/英冠球队），不再有默认 1500 |
| 2026-09-12 | **球队改名/合并** | 葡超 `Vitoria`→`Vitoria Guimaraes`；巴甲新增 `Vitoria`；合并 17 支重复队（`1. Koln`→`FC Koln`、`Psg`→`Paris SG` 等），UI 若有旧名缓存请刷新 |
| 2026-09-12 | **占位说明** | `matches.referee`/`venue` 目前全空（待 API-Football）→ UI 显示 `—`，**不要**用"联赛·日期"兜底文案冒充场地 |
| 2026-09-11 | 新增 `matches.referee` / `venue` / `af_fixture_id` | UI 可展示裁判与场地（现为空，待填充） |
| 2026-09-11 | 新增 `players.weight` / `foot` / `market_value` / `tm_player_id` / `af_player_id` | 球员页可展示完整字段 |
| 2026-09-11 | 新增 `transfers.source` / `season` | 区分球小策与 Transfermarkt 来源 |
| 2026-09-11 | 新增 TM 层 7 张表 + 待填充 6 张表 | 见第 3 节 |
