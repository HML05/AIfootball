# React 界面（webui）接入真数据说明

> 界面来源：Kimi 任务的 `talvex-dashboard`（React 19 + Vite 7 + TS + Tailwind 3 + shadcn/ui + recharts），
> 已作为正式界面落到 `D:\AIfootball\webui`，数据全部来自本机 SQLite `data/database/football.db`（经 FastAPI 暴露）。

## 1. 怎么跑

| 方式 | 命令 | 地址 |
| --- | --- | --- |
| 单端口交付（推荐） | 双击 `start_webui.bat`（缺 `webui/dist` 会先构建，再起 uvicorn） | http://127.0.0.1:8000/ |
| Linux/macOS 启动 | `./start.sh`（先体检依赖/数据/模型，缺产物且有 npm 时自动构建） | http://0.0.0.0:8000/ |
| 公网部署 | 见 [`docs/deploy.md`](deploy.md)：VPS + nginx 同源反代 + systemd 常驻 | https://你的域名/ |
| 前端开发模式 | `cd webui; npm run dev`（已配 `/api` → 8000 代理） | http://127.0.0.1:3000/ |
| 只重启后端 | `python -m uvicorn src.main:app --host 127.0.0.1 --port 8000` | http://127.0.0.1:8000/api/ui/home |
| 重新构建产物 | `python scripts/build_webui.py` | 输出 `webui/dist`（`TEMP` 会被指到 `.buildtmp`，避开 esbuild 权限坑） |

改 `src/api/ui.py` / `src/main.py` / `config/settings.py` 后必须重启 8000（uvicorn 未开 `--reload`）；
改 `vite.config.ts` 后必须重新构建，否则 8000 仍用旧产物。

### 1.1 登录（2026-10 新增）

登录页用的是**设计稿那一版**（`docs/console/login.html`，球场底图 + 昼/暮/夜/雨四套天气 + 账号密码 / 扫码两个页签）。它是静态页，只被读、不被改；React 这边**没有自己的登录页**，未登录时整页跳过去：

```
浏览器打开任意页面
  → 无登录态 → window.location.replace('/console/login.html?next=<原地址>')
  → 在该页登录 → 写 localStorage['fauth'] → 跳回 next
```

| 项 | 值 |
| --- | --- |
| 页面位置 | 后端把 `docs/console/` 挂在 **`/console`**（`src/main.py` 的 `CONSOLE_DIR`，只挂载不改文件），所以 `http://127.0.0.1:8000/console/login.html` 就是登录页；它自己的老服务 `scripts/serve_console.py`（8591）依然可用 |
| 演示账号 | `admin / football2026`（管理员，可进管理端）；库里另有 `viewer` / `user` / `uipreview` 三个非管理员账号（密码未在本文档记录） |
| 登录态存储 | `localStorage['fauth'] = {token, user}`（该页写的格式；本 SPA 额外容忍/补齐 `expires_at`、`remember`）。与后端扫码确认页 `src/auth/qr_page.py` 同一个键，三处登录方式共享一份登录态 |
| 同源 / 跨源 | 生产（8000 直接提供 dist）与登录页同源 → 直接共享 `localStorage`，`next` 用相对地址；开发（Vite 3000，登录页仍在 8000）跨源 → `next` 用**绝对地址**，该页回跳时附加 `?auth_token=`，由 `webui/src/lib/auth.ts` 的 `adoptTokenFromUrl()` 收进 `fauth`，再用 `/api/auth/me` 换成真实用户 |
| 会话时长 | 该页「记住我 30 天」勾选框；`GET /api/auth/me` 在冷启动校验一次，失效即清本地并回登录页 |
| 退出 | 顶栏头像 → 菜单 → 退出登录（先调 `POST /api/auth/logout` 删服务端会话，再清本地与接口缓存，最后回到登录页） |
| 权限 | 顶栏「设置」（管理端入口）仅 `role=admin` 显示；`/admin*` 由 `RequireAdmin` 守卫，非管理员显示「需要管理员权限」卡（含「换管理员账号登录」链接，带 `why=role`，登录页会解释原因） |
| 扫码登录 | 登录页自己的页签：`POST /api/auth/qr/start` → 轮询 `/api/auth/qr/poll`；扫码页走局域网 IP（如 `http://10.5.86.80:8000/api/auth/qr/scan?...`），需手机与电脑同一局域网 |
| 关闭登录闸门 | 环境变量 `UI_REQUIRE_AUTH=false` 启动 8000（`config/settings.py`），此时 `/api/ui/*` 恢复匿名可读（前端仍会跳登录页，除非已登录） |
| 注册入口（2026-10 新增） | 登录页表单下方「注册新账号 · Sign up」→ `/console/register.html`。走后端 `POST /api/auth/register`，**角色固定 `user`**（请求里塞 `role=admin` 会被忽略），注册成功直接写入 `localStorage['fauth']` 并跳 `?next=`；账号规则 3~20 位、字母开头、只允许字母数字下划线点横线，密码 ≥6 位。`AUTH_ALLOW_REGISTER=false` 可关闭自助注册（403） |
| 忘记密码入口（2026-10 新增） | 登录页表单下方「忘记密码 · Reset」→ `/console/forgot.html`。两步：`POST /api/auth/reset/request`（账号不存在 404）生成一次性 6 位数字码；`POST /api/auth/reset/confirm` 校验码（错 5 次作废、10 分钟过期、用过即废、同一账号重新申请会作废上一枚）后设新密码，并**删除该账号全部旧会话** |
| 重置码怎么拿到（默认「不回显」） | 本机/内网没有邮件通道，所以码走**服务端日志**：`config/settings.py` 的 `AUTH_RESET_SHOW_CODE` 默认 `false` → 页面上不出现任何数字码，只提示「请联系管理员索取」，码由 `src/api/auth.py` 的 `_log_reset_code()` 写到 **`logs/auth_reset.log`**（UTF-8，一行一条，格式 `[auth] 重置码 username=<账号> code=<6位> ttl=10min from=<ip> at=<时间>`）同时打到 uvicorn stdout。自己一个人用时可以把 `AUTH_RESET_SHOW_CODE=true` 打开（页面直接回显，照着输即可）。自检脚本用 `scripts/_uiauth.py` 的 `reset_code_from_log(账号)` 读这个文件 |
| 日志编码的坑 | stdout 被 shell 重定向时的编码由**那个 shell** 决定：Windows PowerShell 5.1 的 `*>` 写 UTF-16LE，pwsh 7 写 UTF-8 —— 同一路径的日志文件编码会在换 shell 重启后变化，按 UTF-8 硬解析旧文件会**静默取不到码**。所以取码主路径是专用的 `logs/auth_reset.log`（后端显式 `encoding="utf-8"` 写），stdout 日志只作兜底（`_uiauth._decode_variants` 会依次尝试 utf-8 / utf-16 / gbk） |
| `?next=` 透传 | 登录页的注册/忘记密码链接会把登录页的 `?next=` 一起带过去（登录页里 12 行内联脚本），两个页面办完事再带回来 |

后端闸门在 `src/api/ui.py` 的 `require_ui_login`：**除 `/api/ui/public/*` 与 `/api/ui/logo/*` 外，所有 `/api/ui/*` 都需要 `Authorization: Bearer <token>`**，否则 401 `{"detail":"未登录或登录已过期"}`。前端 `webui/src/lib/api.ts` 收到 401 会清登录态并跳到登录页。
公开端点 `/api/ui/public/summary` 只给品牌、数据截至时间与 6 个总量（比赛/完赛场次/待赛/球员/球队/联赛/准确率），**不含任何明细数据**。

## 2. 页面 → 接口对照

用户端导航 7 个入口（总览 / 赛程 / 联赛 / 球队 / 球员 / 预测 / 实时），管理端入口 = 顶栏右侧「设置」（仅管理员可见）。下面所有页面都需要登录（登录页本身在 SPA 之外，见 §1.1）。

| 路由 | 页面 | 数据来源 |
| --- | --- | --- |
| （SPA 外）`/console/login.html` | 登录页（设计稿控制台版；未登录时唯一可达页面） | `/api/auth/login`、`/api/auth/me`、`/api/auth/status`、`/api/auth/qr/*` |
| （SPA 外）`/console/register.html` | 注册页（2026-10 新增）：账号 3~20 位字母开头、密码 ≥6 位、显示名与手机号可选；注册成功直接发令牌并跳回 `?next=` | `/api/auth/register`（角色固定 `user`） |
| （SPA 外）`/console/forgot.html` | 忘记密码（2026-10 新增）：第一步申请重置码（默认不在页面显示，提示向管理员索取；管理员看 `logs/auth_reset.log`），第二步填码 + 新密码 | `/api/auth/reset/request`、`/api/auth/reset/confirm` |
| `/` | 首页概览（欢迎使用 FootballAI） | `/api/ui/home` + `/api/ui/predictions?size=1`（预测可信度卡） |
| `/matches` | 赛程与赛果（筛选状态写回 URL：`?status=&q=&season=&page=`） | `/api/ui/matches` |
| `/matches/:id` | 比赛详情（记分板 / 模型预测 / 数据对比 / 积分榜位置 / 双方近期比赛 / 历史交锋） | `/api/ui/matches/{id}` |
| `/leagues` | 联赛数据（10 张联赛卡） | `/api/ui/leagues`（含 `totals` 库内去重口径） |
| `/leagues/:id` | 联赛详情（积分榜 / 赛季趋势 / 球队实力 / 射手榜） | `/api/ui/leagues/{id}?season=` |
| `/teams` | 球队分析（231 支 · 9 种排序） | `/api/ui/teams`（含 `aggregates` / `top5`） |
| `/teams/:id` | 球队详情（资料卡 / 核心指标 / 七维画像 / 赛季战绩 / 近期战绩 / 未来赛程 / 阵容） | `/api/ui/teams/{id}` |
| `/players` | 球员分析（4,745 名 · 位置/联赛筛选；顶部可切「转会记录」） | `/api/ui/players` + `/api/ui/transfers` |
| `/players/:id` | 球员详情（画像 + 赛季记录） | `/api/ui/players/{id}` |
| `/predictions` | 比赛预测（预测列表 + 页首一处口径定义） | `/api/ui/predictions` |
| `/live` | 实时比分（最近完赛 + 即将开始） | `/api/ui/live` |
| `/ask` | 检索与问答（两页签：全文检索 `?tab=search` 默认，命中【】高亮 + 类型筛选 + 分页；智能问答 `?tab=ask`，含模式/意图徽标、可折叠执行步骤、`[n]` 引用来源列表；URL 状态 `tab/q/kind/page`） | `/api/ui/search` + `/api/ui/search/stats` + `/api/ui/ask` + `/api/ui/ask/status` |
| `/admin?tab=overview` | 管理端 · 数据总览（入库趋势 / 分布 / 管道 / 总进球分布 / 联赛对比） | `/api/ui/admin` |
| `/admin?tab=asset` | 管理端 · 数据资产（原 `/reports` 全文） | `/api/ui/reports` |
| `/admin?tab=models` | 管理端 · 模型注册表（生产模型卡 / 概率校准 / 混淆矩阵 / 特征 Top12 / 版本对比 / 最近预测） | `/api/ui/models` + `/api/ui/predictions` |
| `/admin?tab=system` | 管理端 · 系统与接口（数据源 / 实时通道 / 库表 / 数据质量） | `/api/ui/reports` + `/api/ui/live` |
| `/reports`、`/agent` | 已合并：分别 302 式前端重定向到 `/admin?tab=asset`、`/admin?tab=models` | — |

队徽统一走 `/api/ui/logo/{team_id}`（后端把外网 URL 换成本地代理，缺图返回字母占位徽，不再有破图）。

## 3. 数据口径（容易误读的地方）

- **赛季口径**：`/leagues/{id}?season=2627` 的 KPI/积分榜随赛季变；`teams`（球队实力）来自全量预计算表 `team_radar`，**不随赛季过滤**，前端已标注「全量聚合（跨赛季）」。
- **射手榜赛季**：来自 Transfermarkt 的 `tm_player_seasons`，用 `scorersSeason.label` 单独标注（如英超 25/26、欧冠 24/25、巴甲 2025）。最新赛季轮次少，进球数偏小是真实值。
- **场均口径**：`goals_pg/xg_pg` 只以**已完赛**场次为分母（未开赛的 0:0 不计入）。首页「预测准确率 50.14%」是 v9 集成 v2+v7 的样本外准确率，`/predictions` 里的「命中率」是全部已评估预测的命中比例，两者口径不同。
- **脏数据照实展示**：`players.age` 存在 2025 这类异常值、`team_radar.avg_age` 有 224.4（Granada）等；前端不掩盖。

## 4. 自检脚本

| 脚本 | 作用 |
| --- | --- |
| `scripts/_uiauth.py` | **其它脚本的登录助手**：`login()` / `auth_state()` / `init_script()`（给 Playwright 的 `add_init_script` 注入 `localStorage.fauth`）/ `headers()`（直连接口用）；账号取 `FA_USER`/`FA_PWD`（默认 `admin/football2026`）、后端地址取 `FA_API` |
| `scripts/smoke_ui_api.py` | 30 个 `/api/ui/*` 端点冒烟（含参数组合与关键字断言、检索两个 + 问答两个；自动带 Bearer） |
| `scripts/build_search_index.py` | 重建全文检索索引 `data/database/search.db`（19,800 条 / 17.8 MB / 约 5 秒；`--bigram` 强制退化分词） |
| `scripts/verify_search.py` | 检索层自检 23 项：中文分词口径（复现 unicode61 零命中、trigram 两字词失效）、中文与两字词召回、引用完整性（`source.id` 回主库核对）、跳转 URL、未鉴权 401、kind 过滤、空查询、查询耗时 |
| `scripts/verify_qa.py` | 智能问答自检 37 项：六个结构化工具（别名找队、去重、金额/浮点口径）、意图与检索串（去虚词）、编排（引用编号连续、**逐条回主库核对 (table,id) 无幽灵来源**、timing、无 key 提示）、接口与闸门（GET/POST 未登录 401、top_k 越界 422、耗时） |
| `scripts/verify_ask_ui.py` | `/ask` 页面浏览器自检 17 项：检索页（命中条数与分词、20 条结果链接、首条为站内路径、Predictions 筛选生效且条数变少）、问答页（提交「皇马和巴萨谁赢」出答案、含真实比分/百分比、`Retrieval summary` 徽标、未配 key 提示、`[n]` 引用、步骤折叠区）、页面质量（无溢出 / 无坏图 / 控制台 0 报错），截图存 `%TEMP%\aifootball_view\ask\` |
| `scripts/verify_webui.py` | 逐路由体检：控制台错误 / 坏图 / 横向溢出 / 残留骨架 / 真实数据标记，截图存 `%TEMP%\aifootball_view\verify\`；`/console/login.html` 走**未登录**上下文，其余路由自动注入登录态，共 19 条路由 |
| `scripts/_login_flow.py` | 登录端到端流程（生产 17 项 / 开发 16 项断言）：未登录被守卫送到控制台登录页且带 `next`、错密码提示、正确登录回原地址且用户信息被 `/api/auth/me` 换成真实账号、已登录时该页给「继续进入」、头像菜单退出后清态、非管理员（拦截 `/me` 返回 user 角色）看到权限卡与「换管理员账号登录」且看不到「设置」。`WEBUI_BASE=…:3000` 可验开发路径（跨源 `?auth_token=` 交接） |
| `scripts/_login_shots.py` | 登录页（控制台版）昼/暮/夜/雨四种天气截图 + 扫码页签检查（二维码真解码、倒计时在走） |
| `scripts/verify_auth_register.py` | 注册 / 忘记密码**后端**自检 30 项（纯接口、无需浏览器）：注册成功与 `role` 固定 user、塞 `role=admin` 不提权、重名 409、账号与密码规则 400、重置码 6 位与有效期、**默认响应不含 code 且能 `logs/auth_reset.log` 里取到码**、错码计数、重新申请作废旧码、码一次性、重置后旧密码 401 与旧会话 401、`/api/auth/users` 仍只认管理员；默认跑完删掉测试账号（`--keep` 保留） |
| `scripts/verify_account.py` | 账号设置**后端**自检 41 项（纯接口）：`PATCH /api/auth/profile` 改昵称/账号名/手机号与校验（账号名 3~20 位且字母开头、重名 409、非法手机号 400）、改名后旧账号名登录 401 但**已有令牌仍可用**、头像上传（PNG 与真照片都验、后端居中裁方并压到 512、伪装成图片的文本 400、>2 MB 413）、`GET /api/auth/avatar/{id}` 不鉴权可取图且带 `?v=` 版本号、`DELETE` 后 404、改密码后**其它设备的会话失效而当前会话保留**；默认跑完删掉测试账号与头像文件（`--keep` 保留） |
| `scripts/verify_account_ui.py` | 账号设置**弹层**自检 50 项（Playwright 真点）：顶栏头像 → 菜单「账号设置」→ `[role=dialog]`、点页面空白处能收起账号菜单、三页签齐备；头像页选图即时 `blob:` 预览、真发 multipart 上传并让**顶栏立刻换图**（带 `?v=` 防旧缓存）、「恢复默认头像」回到 `/images/profile.png`、>2 MB 本地拦截（错误文案带实际体积且不发请求）；资料页三个输入框是**后端真实值**回填、未改动时保存禁用、改昵称保存后顶栏与 `/me` 同步、非法账号名把后端 400 原文显示且不落库、测完把昵称改回原值；密码页本地拦「新密码至少 6 位」、错原密码显示后端「原密码不正确」且旧密码仍可登录；末尾断言弹层关掉后 0 坏图 / 0 横向溢出 / 0 控制台报错（负向用例故意打的 400 不计） |
| `scripts/_register_flow.py` | 注册 / 忘记密码**界面**端到端（Playwright 真点击，见下） |
| `scripts/docs_shots.py` | 重新生成 `docs/webui/` 的 22 张交付截图（生产构建 + 已登录，中文亮色；`/console/login.html`、`18-注册账号`、`19-忘记密码` 走未登录；`21-智能问答` 会先提一个真问题、`22-账号设置` 会先点头像开弹层） |
| `scripts/responsive_webui.py` | 1280 / 1440 / 1920 三宽度响应式体检（自动带登录态） |
| `scripts/audit_webui.py` | 信息架构盘点（逐页卡片顺序 / KPI 标签 / 表头 / 内滚块；自动带登录态） |
| `scripts/build_webui.py` | 生产构建（自动处理 TEMP 权限坑） |
| `scripts/shot_webui.py` | 单页截图 + 指标（支持带 query 的路由，自动带登录态，`/console/login.html` 除外）；`WEBUI_BASE` 可指向 3000 或 8000 |
| `scripts/api_shapes.py` | 打印端点真实返回结构（对字段用；自动带登录态） |
| `scripts/serve_console.py` | 单独起一个静态服务（默认 8591）提供 `docs/console/`，不依赖 8000 |
| `scripts/verify_console_gate.py` / `verify_auth_console.py` / `verify_auth_qr.py` / `verify_auth_streamlit.py` | 早已存在的控制台/Streamlit 侧登录与扫码闸门验证（针对 8591/8501/8502） |
| `scripts/db_cols.py` | 打印数据库表结构 |
| `scripts/check_deps.py` | 依赖体检：`ast` 解析 `src|config|scripts|tools|frontend|tests` 的 import，与 `requirements.txt` 对照（`--missing` 时缺必需依赖 exit 1） |
| `scripts/audit_repo_payload.py` | 按 `.gitignore` 推演「哪些文件会进仓库」（用 pathspec 等价 git 规则），断言关键文件该进的进了、该忽略的忽略了、没有 >90 MB 单文件 |
| `scripts/check_sameorigin.py` | 把控制台 5 页用 Playwright 的 route 挂在 `http://example.test` / `https://example.test` 上，断言 `/api/` 请求与页面同源且 URL 里不含 `:8000`（本机 8000 访问区分不出新旧取址写法，所以必须换假域名验） |

## 5. 已知边界

- 身价历史（`tm_player_market_value`，90.1 万行）目前只在统计口径里出现，没有独立时间序列页。
- 实时页是「30s 轮询 + 手动刷新」，只展示 `/ws/live-scores` 通道地址，未真正建立 WebSocket（管理端「系统与接口」页签同样只做只读展示，不建立连接）。
- `/api/ui/live` 的 `recent[].home_xg/away_xg` 与 `upcoming[].pred_*` 目前多为 null，页面分别走「隐藏」与「暂无预测」分支。
- 英文界面下少数专有名词仍为中文（模型版本名、联赛名、数据源名来自数据库，接口未提供英文名）。
- `/reports` 的 `leagues[].xgPg` 对英冠/荷甲/葡超/巴甲/欧冠为 null（上游未覆盖），前端显示「—」。
- 转会记录里个别赛季名异常（如 `07/08` 混在最新赛季中），源自上游 `transfer_date` 与 `season_name` 不一致，按原值展示。
- **比赛重复入库**：`matches` 表按 (赛季, 主队, 客队) 存在 99 组重复对阵（12,698 行 → 12,599 个唯一对阵），其中 83 组为「同比分且相隔 ≤3 天」的真重复（如 `match_id 3841` 与 `12651`：同 52v38、3:2，日期 2026-08-28 18:00 vs 2026-08-29 09:00）。展示层未删数据、按原样列出；`/api/ui/matches/{id}` 的「双方近期比赛」按 `_form_rows()` 内部去重（同对阵 + 同比分 + 相隔 ≤3 天视为一场，保留带 xG 的那条）。是否清理库内重复行待定。
- **球队字段缺口**：`teams.manager` 实测多为 null（Elche / Santander / Arsenal 三队全为 null），详情页显示「—」；`htHome/htAway`（半场比分）实测为 null，详情页不渲染半场贴片。
- **小样本指标**：`/teams/:id` 的核心指标来自 `team_radar` 预计算表（跨赛季全量），样本极少时（如 Santander 仅 6 场）七维画像会严重失真（attack 93 / defense 5），页面已在 hint 中写明「样本 N 场」；Arsenal 的赛季行是**跨赛事聚合**（25/26 为 53 场 / 104 球，含杯赛与欧战），不是联赛口径。
- **积分榜自身不齐**：同一场比赛的两队 `played` 可能不同（如 Elche 6 场 vs Sociedad 9 场），详情页只展示不校验，并标注「两队场次可能不同步」。
- **检索层（RAG 阶段 0）**：新增 `/api/ui/search`（`q`/`kind`/`limit`/`offset`）与 `/api/ui/search/stats` 两个端点，走同一登录闸门（未登录 401）；索引是**派生数据** `data/database/search.db`（不入库），数据更新后需重跑 `python scripts/build_search_index.py` 才会反映到检索结果（当前没有挂进定时任务）；细节与边界见 [`docs/检索层说明.md`](检索层说明.md)。
- **问答层（RAG 阶段 1）**：`/api/ui/ask`（POST，body `{question, top_k, use_llm, kind}`）与 `/api/ui/ask/status`、`GET /api/ui/ask`（调试）三个端点，同样走登录闸门；**必须重启 8000 才生效**（uvicorn 未开 `--reload`，改 `src/` 后不重启会继续跑旧代码 —— 排查时用 `GET /api/ui/ask/status` 或看 `search.query` 字段是否存在来判断新旧）。无 `LLM_API_KEY` 时 `mode=retrieval`（用库内事实 + 检索片段拼答案，不假装生成）；填 key 后 `mode=llm`（已用 `deepseek-flash` 真机联调，注意该模型推理 token 也占 `max_tokens`，`src/qa/llm.py` 会自动加倍预算重试，配置体检用 `python scripts/check_llm.py`）。前端页面 `/ask` 两页签共用这一组接口，细节见 [`docs/智能问答说明.md`](智能问答说明.md)。
- **账号设置（顶栏头像 → 弹层）**：新增 4 个端点 —— `PATCH /api/auth/profile`（改账号名 / 昵称 / 手机号）、`POST /api/auth/avatar`（multipart，字段 `file`）、`DELETE /api/auth/avatar`、`GET /api/auth/avatar/{user_id}`；前三者走登录闸门（未登录 401），**取图那一个故意不鉴权**（前端 `<img src>` 带不了 Authorization），因此头像 URL 是不可猜的用户 id + 版本号，而不是密钥。头像落 `data/uploads/avatars/<user_id>.<ext>`（**不在仓库里**，已加 `.gitignore`；丢了只会退回默认图 `/images/profile.png`），上传上限与边长由 `AVATAR_MAX_BYTES` / `AVATAR_MAX_SIDE` 控制（默认 2 MB / 512 px，后端居中裁方且只缩不放）。**必须重启 8000 才生效**。改密码会踢掉**其它**会话、当前会话保留。前端组件 `webui/src/sections/AccountSettings.tsx`（用户端与管理端共用同一个顶栏）→ 三页签「头像 / 资料 / 密码」，Esc 或点遮罩关闭；改完把新 user 写回本地登录态，顶栏昵称与头像即时更新。后端自检 `scripts/verify_account.py`（41 项），页面自检 `scripts/verify_account_ui.py`。
- **登录相关**：① `viewer`/`user`/`uipreview` 三个非管理员账号的密码本文档未记录，需要时用 `python scripts/add_user.py`（管理员接口）重置；② 扫码登录依赖手机与电脑在同一局域网，且扫码页写的是**后端**的局域网地址（`http://<LAN-IP>:8000/api/auth/qr/scan?...`），若只起了 3000 开发服、没起 8000，手机端会连不上后端；③ 前端 `localStorage` 里的登录态是「本机浏览器级」的，换浏览器需重新登录；④ 语言默认值仍是英文（`webui/src/i18n.tsx` 无本地记录时回落 `en`），首次访问 SPA 会显示英文，切到「中」后按浏览器记住 —— 是否把默认值改成中文待定；⑤ **控制台 5 页的取址已改为同源优先**（2026-10 部署前修复，原「写死 `http://127.0.0.1:8000`」已删除）：`file:` 协议回落到 127.0.0.1:8000，http 且端口非 8000 时用 `同主机:8000`，其余（含 nginx 反代的 HTTPS 域名）用空串走同源；用 `python scripts/check_sameorigin.py` 在假域名上验（10/10）。备份原件在 `D:\AIfootball_部署前备份_20261005\console\`；⑥ 我做的 React 版登录页 `webui/src/pages/Login.tsx` 已不在路由里（留作控制台页缺失时的兜底），页面清单/文档里不再提及。
