# 足球数据分析与 AI 预测系统（FootballAI）

> 毕业设计项目 | React + FastAPI + XGBoost + SQLite ｜ 数据截至 2026-09-12

## 这是什么

基于五大联赛（英超、西甲、德甲、意甲、法甲）真实数据的足球数据分析与预测系统：
**12,698 场比赛 · 11,315 场已完赛 · 1,379 场待赛 · 4,745 名球员 · 240 支球队 · 10 个联赛**。
界面、图表与每一个数字都来自本地 SQLite 数据库（`data/database/football.db`，158.8 MB / 36 张表），
没有写死的假数据。

> **进行中的第二个模块（毕设新题目）**：基于 YOLOv8 的足球视频球员检测跟踪。
> 目前只落地了骨架：`src/vision/` 四个模块（config / detector / metrics / io）、三条命令行
> （抓链接 / 抽帧 / 预标注 / 可行性冒烟）、50 项自检；**尚未接入 Web 界面，也还没在真实比赛片段上跑过**（等素材）。
> 环境已在 RTX 3060 上跑通（torch 2.5.1+cu121，合成片段 15.97 帧/秒）。
> 方案、命令、样本要求与难点见 [`docs/YOLOv8-检测跟踪-方案.md`](docs/YOLOv8-检测跟踪-方案.md)。

## 在线演示

**<http://8.133.235.32:8000>** —— 2026-10-10 上线，跑在阿里云轻量应用服务器（2 vCPU / 2 GiB / Ubuntu 24.04，上海）上，
用 [`deploy/install_vps.sh`](deploy/install_vps.sh) 一条命令装好（systemd 常驻、开机自启）。
**线上实例的管理员账号名与口令都已经改过**（拿 `admin` 登不进去，这是有意的），所以我给不了「点开就能自己登录逛一圈」的账号 ——
想看界面请按下面的《快速开始》在自己机器上跑一份：Release 数据包里的初始账号仍叫 `admin`，口令 `football2026`，
第一次登录后请立刻改掉。

三条如实说明的现状（细节见 [`docs/部署-公网托管.md`](docs/部署-公网托管.md) 第 8 节）：

- **个人云主机，不是 7×24 商业服务**：机器关机或到期（2027-10-10）站点就下线，冷启动首次访问会慢一点。
- **HTTP 而非 HTTPS**：`http://IP:端口` 下登录密码是明文过网的，别拿它传真实敏感信息。
- **数据是 2026-09-12 的快照**：部署时把两个定时抓取任务关掉了，页面数据不会自己更新。

安全口径：强制登录（未登录访问任何业务接口 401）、自助注册关闭（`POST /api/auth/register` 403）、
忘记密码的验证码不回显、`DEBUG` 关闭；上线后从外网复核 **41 项全绿**（11 项安全与资源 + 30 个接口冒烟）。

## 入口

> 下表地址都是 **`127.0.0.1`** —— 它们只对「正在跑这个服务的这台机器」有效，
> 在 GitHub 上直接点会打不开（那是你自己的电脑的意思）。线上的公开入口是 <http://8.133.235.32:8000>，路径完全相同。

| 入口 | 地址 | 说明 |
|---|---|---|
| 用户端 + 管理端（React SPA） | <http://127.0.0.1:8000/> | 19 条路由：总览 / 赛程 / 比赛详情 / 联赛 / 联赛详情 / 球队 / 球队详情 / 球员 / 球员详情 / 预测 / 实时 / **检索与问答 `/ask`**；管理端 4 页签在 `/admin`（数据总览 / 数据资产 / 模型注册表 / 系统与接口） |
| 登录页（控制台设计稿版） | <http://127.0.0.1:8000/console/login.html> | 未登录访问任何页面都会整页跳到这里；数据包里的初始账号是 `admin`（管理员），另有 `viewer` / `user` 两个非管理员账号用于验证权限；**首次跑的口令是 `football2026`，登录后必须立刻改掉**（本机与线上这两台都已改名 + 改密，仓库里没有可用口令）；页面下方有 **注册新账号** 与 **忘记密码** 两个入口 |
| 注册 | <http://127.0.0.1:8000/console/register.html> | 自助注册，新账号固定是 `user`（用户端）角色，注册成功即登录。`.env.example` 默认是开着的（`AUTH_ALLOW_REGISTER=true`）；公开部署时建议关掉 —— 本机与线上这两台都已关，**页面打得开、提交会返回 403**（`当前未开放自助注册`） |
| 忘记密码 | <http://127.0.0.1:8000/console/forgot.html> | 两步式：申请一次性 6 位重置码 → 用它设新密码并踢掉旧会话。**默认页面上不显示码**（`AUTH_RESET_SHOW_CODE=false`，公网安全），码写在 **`logs/auth_reset.log`**（UTF-8，一行一条）与 uvicorn 日志里，由管理员转告用户；自己一个人用可设 `true` 让它直接回显 |
| 接口文档 | <http://127.0.0.1:8000/docs> | FastAPI 自动生成（公网实例上同样打得开） |
| 控制台静态页（可选） | <http://127.0.0.1:8591/> | `python scripts/serve_console.py` —— 要单独起一个进程，不随 8000 一起跑；线上实例没开 |
| 参照版界面（Streamlit，可选） | <http://127.0.0.1:8501/> · <http://127.0.0.1:8502/> | `start.bat` / `start_admin.bat` —— 同样是独立进程（旧版参照界面，非交付主线）；线上实例没开 |

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 19 + TypeScript + Vite + Tailwind（自研玻璃质感组件 kit） |
| 后端框架 | FastAPI + Uvicorn |
| 数据处理 | Pandas + NumPy + SQLAlchemy |
| 数据库 | SQLite（开发） |
| 检索 | SQLite FTS5 + jieba 中文分词（自建索引 `data/database/search.db`，不依赖外部检索服务） |
| 智能问答 | 自研三步编排（意图 → 工具/检索 → 作答）+ 引用溯源；有 LLM key 走大模型，无 key 降级检索摘要 |
| 机器学习 | XGBoost + scikit-learn（v9 = v2+v7 集成） |
| 图表 | React 端：recharts + 自研 SVG（雷达 / 环形 / 条形）；Python 端：Altair / Vega-Lite 出图（`src/visualization/`） |
| 认证 | 自研 PBKDF2 + 会话令牌；密码登录 + 扫码登录 |
| 自检 | Playwright（截图 + DOM 断言：溢出 / 坏图 / 控制台报错） |
| 定时任务 | APScheduler |

## 目录结构

```
AIfootball/
├── src/                     # 后端：FastAPI 入口、数据源、数据库、分析、预测、可视化、认证、API 路由
│   ├── main.py              # 应用入口（挂载 /api/*、React 产物 /、控制台 /console）
│   ├── api/ui.py            # 前端所需的全部聚合接口（21 条路径 / 22 个方法）
│   ├── api/search.py        # 全文检索接口（RAG 阶段 0，见 docs/检索层说明.md）
│   ├── api/qa.py            # 智能问答接口（RAG 阶段 1，见 docs/智能问答说明.md）
│   ├── qa/                  # 问答编排：tools / router / llm / orchestrator
│   ├── search/              # 检索层：tokenizer / indexer / query
│   └── api/auth.py          # 登录 / 会话 / 扫码 / 账号管理 / 头像与个人资料
├── webui/                   # 前端：React 源码 + 构建产物 dist（node_modules 不入库）
│   ├── src/pages/           # 19 条路由对应的页面（含 pages/Ask.tsx 检索与问答）
│   └── src/sections/        # 首页等页面的区块组件
├── docs/
│   ├── console/             # 控制台静态页（登录页 login.html 就在这里）
│   ├── webui/               # 交付截图 22 张
│   └── *.md                 # 设计与实现文档（见下方索引）
├── scripts/                 # 构建、导入、自检脚本
├── deploy/                  # 部署用：systemd 单元 + nginx 示例 + docker-compose / Caddyfile / 容器入口脚本
├── .github/workflows/       # CI（static 语法/依赖体检/直装脚本自检 56 项 + runtime 数据包到位后 149 项）
├── data/                    # 数据库 + 采集到的原始/外部数据（不入库）
├── models/                  # 训练好的模型文件（.joblib/.pt 不入库）
├── tools/                   # console_template.html（控制台生成器的输入）与一次性补丁脚本
├── frontend/                # 参照版界面（Streamlit，8501/8502）
├── Dockerfile               # 容器化部署（构建期从 Release 拉数据包）
├── render.yaml              # Render 免费档 Blueprint（一键建服务）
├── requirements.txt         # 运行时依赖（服务器上只需要这一份）
├── requirements-deploy.txt  # 部署子集（去掉只给 frontend/ 用的 streamlit/altair）
├── requirements-dev.txt     # 开发/自检依赖（playwright / torch / scipy / vl-convert）
├── .env.example             # 环境变量模板（.env 不入库）
├── start_webui.bat          # Windows 一键启动（按需构建前端 + 起 8000）
├── start.sh                 # Linux/macOS 一键启动（含依赖与数据体检）
└── README.md
```

## 快速开始

```bat
:: 1) 依赖
pip install -r requirements.txt
cd webui && npm install && cd ..

:: 2) 环境变量
copy .env.example .env      :: 填入 API key（可留空，界面不依赖外部 API）

:: 3) 启动（需要时自动构建前端）
start_webui.bat             :: 界面 http://127.0.0.1:8000/
```

登录：`admin` / `viewer` / `user` 三个账号（`admin` 是管理员，另两个用于验证权限控制）。
**密码不在仓库里**：新克隆下来的库首次跑用的是内置初始密码 `football2026`，登录后请立刻在
「头像 → 账号设置 → 密码」里改掉（部署到公网时这一步是硬要求，不是可选项）。
改过前端代码后重新构建：`python scripts\build_webui.py`。

**Linux/macOS**：

```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
./start.sh                  # 会先体检依赖/数据/模型，再起 8000
```

**全文检索（RAG 阶段 0）**：用 SQLite FTS5 + jieba 自建中文索引，`GET /api/ui/search?q=皇家马德里` 返回带 `sources` 的可溯源结果
（19,800 条语料、17.8 MB、单次查询 2~11 ms；内置 unicode61 分词对「马德里」是 0 命中，本方案 518 条）。
建索引：`python scripts/build_search_index.py`；原理与边界见 [`docs/检索层说明.md`](docs/检索层说明.md)。

**智能问答（RAG 阶段 1）**：问「皇马和巴萨谁赢」「英超积分榜」「凯帕身价多少」，后端先识别意图与实体，
再查库（6 个结构化工具）+ 检索，最后作答并给每条结论标引用 `[n]`（引用可点回站内页面）。
`POST /api/ui/ask` 实测 **84~139 ms**（无大模型，热运行；冷启动首次约 0.66 s，其中工具 68~95 ms、检索 12~22 ms）。`.env` 里 `LLM_API_KEY` **留空也能用** ——
自动降级为「库内事实 + 检索片段」的检索摘要（`mode=retrieval`）；填上 key 即切到大模型作答（`mode=llm`），
`SYSTEM_PROMPT` 五条硬规矩保证「材料里没有就说没有」。**已用 `deepseek-flash` 真机联调**：
「英超积分榜前 5」返回 261 字带 `[1]` 引用的答案（约 2.2 s），「皇马和巴萨谁赢」如实回答「库内没有尚未开赛比赛的确定胜负记录」。
注意该模型是**推理型**（会先输出 `reasoning_content`，推理 token 同样占用 `max_tokens` 预算），
预算不足时 `content` 会被静默切成半句话而 HTTP 仍是 200 —— `src/qa/llm.py` 已识别 `finish_reason=length` 并自动双倍预算重试，
`scripts/check_llm.py` 可体检配置与可用模型。原理见 [`docs/智能问答说明.md`](docs/智能问答说明.md)，
自检 `python scripts/verify_qa.py`（37 项）。

**要放到公网给别人访问**：见 [`docs/部署-公网托管.md`](docs/部署-公网托管.md)。
最省事的是 **路线 B-直装**（第 8 节，本项目线上就是这么部署的）：在没有 Docker 的云主机上跑一条命令
`curl -fsSL https://raw.githubusercontent.com/HML05/AIfootball/main/deploy/install_vps.sh | bash`，
它会装依赖 → 建 swap → 拉代码 → 下数据包 → 生成 `.env` → 写 systemd 单元 → 等 `/health` 通过；
第 8.1 节记录了阿里云轻量上的**首次真跑实测**（含 GitHub 直连断流、改走国内镜像、外网 41 项复核）。
另外还有三条路线：Render 免费容器（`render.yaml`）/ 云服务器 Docker Compose + Caddy / GitHub Pages 纯静态展示。
要在自己的服务器上用 systemd + nginx 跑，见 [`docs/deploy.md`](docs/deploy.md)。

## 数据与模型

| 数据源 | 用途 | 成本 |
|---|---|---|
| football-data.co.uk | 历史比赛数据（训练用） | 免费 |
| API-Football (RapidAPI) | 实时比分、球队/球员详情、转会 | 免费 100 次/天 |
| Transfermarkt | 球员身价、转会详情 | 免费（限速爬虫） |

- **模型**：v9 集成 v2 + v7，样本外 1,817 场，三分类准确率 **50.14%**、FI-Macro 39.9%、LogLoss 1.0338（明细见 `docs/模型评估报告.md`）
- **两类口径要分开看**：命中率 = 全部已评估预测（含回测，1,752 条）的命中比例；准确率 = 生产模型的样本外准确率。两者样本不同，不能直接比较（页面上有一处定义说明）

## 自检脚本

| 脚本 | 作用 |
|---|---|
| `scripts/verify_webui.py` | 19 条路由逐页截图 + 断言（控制台报错 / 坏图 / 横向溢出） |
| `scripts/smoke_ui_api.py` | 30 个后端端点连通性与关键字段（含检索两个 + 问答两个） |
| `scripts/_login_flow.py` | 登录链路端到端 17 项（未登录跳转、错密码、回跳、退出、权限卡） |
| `scripts/verify_auth_register.py` | 注册 / 忘记密码后端自检 30 项（重名、账号密码规则、默认不回码但日志可取码、重置码时效与一次性、旧会话失效、不提权） |
| `scripts/verify_account.py` | 账号设置后端自检 41 项（改昵称/账号名/手机号与撞车、头像上传的压缩与类型校验、改密码后旧会话失效） |
| `scripts/verify_account_ui.py` | 账号设置**页面**自检 50 项（浏览器真点：顶栏头像入口与点空白处收起菜单、三页签、选图预览与 multipart 上传落地、恢复默认、>2 MB 拦截、资料真实回填与 400 原文、改密码被后端拒绝且旧密码仍可用、跑完复原不留副作用） |
| `scripts/docs_shots.py` | 重新生成 `docs/webui/` 的 22 张交付截图 |
| `scripts/build_webui.py` | 构建前端产物到 `webui/dist` |
| `scripts/check_deps.py` | 依赖体检：源码 import 与 `requirements.txt` 对照 |
| `scripts/audit_repo_payload.py` | 按 `.gitignore` 推演「哪些文件会进仓库」、有没有 >100 MB 的大文件 |
| `scripts/check_sameorigin.py` | 把控制台 5 页挂在假域名（http/https）上，验证接口是否同源 |
| `scripts/build_search_index.py` | 重建全文检索索引（`data/database/search.db`，19,800 条 / 4.9 秒） |
| `scripts/verify_search.py` | 检索层自检 23 项（中文分词口径、问题复现、引用溯源、接口闸门） |
| `scripts/verify_qa.py` | 智能问答自检 37 项（六个工具、意图与检索串、编排与引用回主库核对、接口闸门） |
| `scripts/verify_ask_ui.py` | `/ask` 页面自检 17 项（浏览器：检索页命中/高亮/筛选、问答页提交与引用、页面质量；按是否配了 LLM key 自动切换断言） |
| `scripts/check_llm.py` | 大模型配置体检：脱敏回显 key/base/model、列账号可用模型、发一次真实 ping（`--models` 只列模型不计费） |
| `scripts/verify_entrypoint.sh` | 容器入口脚本自检 18 项（POSIX sh；本机没装 docker 也能验：把 `/app` 换成临时目录、用桩命令顶替 uvicorn，拿**真数据包**跑五种情况 —— 缺库时下载解包、库已存在不重复下载、地址不可用仍能启动、缺库缺模型给警告不崩、缺检索索引现场重建） |
| `scripts/verify_install_vps.sh` | 云主机直装脚本自检 56 项（把 apt/git/python3/pip/curl/tar/systemctl 全换成桩命令，跑九个场景：依赖与 venv、pip 走镜像、只在缺主库时下数据包、`.env` 六项安全开关与 `chmod 600`、systemd 单元内容、重复执行幂等、下载失败仍能起、健康检查超时明确失败、非 root 拒绝、`DRY_RUN` 不落盘） |
| `scripts/make_data_pack.py` | 生成 / 校验部署数据包（51.8 MB：主库 + 检索索引 + 模型 + 特征 CSV） |
| `deploy/install_vps.sh` | 云主机一条命令直装（Ubuntu/Debian，不用 Docker）：装依赖 → venv → 拉代码 → 下数据包 → 生成 `.env` → systemd 常驻 → 等 `/health`；幂等、可 `DRY_RUN` |
| `scripts/export_md_docx.py` | 把任意 Markdown 文档导出成 Word（如 `python scripts/export_md_docx.py docs/项目报告总览.md`） |
| `scripts/audit_webui.py` · `scripts/responsive_webui.py` | 信息架构体检 · 多分辨率适配检查 |

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/项目报告总览.md` | **项目报告总览**：一页速览 / 分层架构 / 数据·模型·服务·界面四层说明 / RAG 检索与问答 / 工程质量与 398 项断言 / 部署交付 / 已知限制与规划 / 最小复现路径（另附导出的 Word 版 `项目报告总览.docx`） |
| `docs/详细技术方案.md` | 完整技术设计（模块划分、代码示例、开发路线） |
| `docs/系统架构设计.md` / `docs/系统实现说明.md` | 架构与实现说明 |
| `docs/数据来源与采集说明.md` / `docs/API-Football使用说明.md` | 数据来源、采集流程与第三方接口 |
| `docs/模型评估报告.md` | 模型指标、版本对比、概率校准 |
| `docs/React界面接入说明.md` | 前端路由、登录闸门、脚本与已知边界 |
| `docs/检索层说明.md` | **全文检索层（RAG 阶段 0）**：中文分词实测对比、19,800 条语料、两个检索接口、溯源结构与边界 |
| `docs/智能问答说明.md` | **智能问答层（RAG 阶段 1）**：旧 langchain Agent 为什么不可用、六个工具、意图与实体识别、引用溯源与防幻觉、问答接口、37 项后端自检 + 17 项页面自检与边界 |
| `docs/信息架构评审.md` | 逐页点评、逻辑硬伤整改、目标结构 |
| `docs/deploy.md` | **部署说明**：VPS + nginx 同源 + systemd、数据/模型怎么传、更新与备份、排错表 |
| `docs/部署-公网托管.md` | **公网托管**：**路线 B-直装**（云主机一条命令，`deploy/install_vps.sh`，含第 8.1 节阿里云轻量首次真跑实测）/ Render 免费容器（`render.yaml` 一键建服务）/ 云服务器 Docker Compose + Caddy / GitHub Pages 静态展示；数据包制作与校验、部署后检查清单、排错表、本机按生产配置实测与 CI 里的 205 项断言 |
| `docs/UI设计规范.md` / `docs/UI高级审美评审报告.md` / `docs/UI合规审计报告.md` / `docs/UI协作交接说明.md` / `docs/UI打磨收口记录.md` | UI 规范、评审与打磨记录 |
| `docs/YOLOv8-检测跟踪-方案.md` | **毕设新模块（进行中）**：YOLOv8 视频球员检测跟踪 —— 目录骨架、独立环境、抽帧/预标注/冒烟三条命令、五阶段计划、样本要求与难点对策；本机处理、线上只读 |

## 维护说明

- **已清理**：设计迭代产物、旧数据库备份、已解压的数据集压缩包、渲染帧序列、第三方工具目录等共 596.8 MB，
  已移到项目外的 `D:\AIfootball_已清理_20261005\`（保留可恢复，确认无用后手动删除即可）
- **仓库里只有代码 + 项目**：**636 个受跟踪文件 / 36.4 MB**（含 `webui/dist` 构建产物与 22 张界面截图；
  最大的单文件是截图 `docs/webui/01-登录.png`，约 2.3 MB，离 GitHub 的 100 MB 限制很远）。
  `data/`（含 `data/external` 的 562 MB 与 3 个 >100 MB 的 CSV）、`models/*.joblib|pt`、`.env`、`node_modules`、派生索引 `data/database/search.db` 都已排除 ——
  部署时它们合并成一个 51.8 MB 的**数据包**上传（见 `docs/部署-公网托管.md` 第 1 节；不再需要逐个手传、也不需要在服务器上重建索引）
- 核对命令：`python scripts/audit_repo_payload.py`（按 `.gitignore` 推演会入库的文件，并检查有没有超过 GitHub 100 MB 限制的单文件）
- **代码规模**（`git ls-files` 口径，可复跑复核）：**190 个 Python 文件 / 32,264 行** ·
  **100 个 TS/TSX 文件 / 16,502 行** · **22 份 Markdown / 3,882 行**，另有 `docs/webui/` 22 张交付截图
  （前端构建产物里的压缩 JS 与 `docs/console/*.html` 这类单行文件没并入统计）。
  行数一律以脚本量出来的为准、不估算：
  `git ls-files "*.py" | %{ (Get-Content $_ | Measure-Object -Line).Lines } | Measure-Object -Sum`
- **Git 状态**：已 `git init -b main` 并推送到 GitHub（<https://github.com/HML05/AIfootball>，Public），
  本地与 `origin/main` 同步、`main` 已建立跟踪；完整提交链见 `git log --oneline`（数量随开发增长，此处不写死）；
  CI 状态见 [Actions](https://github.com/HML05/AIfootball/actions)
- **持续集成**：`.github/workflows/ci.yml` —— 每次 push / PR 跑 `compileall` + 依赖体检 + **云主机直装脚本自检 56 项**
  （`bash scripts/verify_install_vps.sh`，纯桩命令、不需要真服务器；`.env` 的 600 权限位只有 Linux 上验得准，
  所以这一项必须进 CI），再拉数据包起真实服务跑 **149 项**（检索 23 + 问答 37 + 接口 30 + 账号 41 + 容器入口 18）
  —— 合计 **205 项**。后一段要等数据包 Release 传上去才跑；传之前会自动跳过并留一条 warning，
  免得「还没传数据包」被误读成「代码坏了」。5 个 Playwright 脚本留本机跑（见 `docs/部署-公网托管.md` 第 7 节）

## License

MIT
