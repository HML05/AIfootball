# 足球数据分析与 AI 预测系统（FootballAI）

> 毕业设计项目 | React + FastAPI + XGBoost + SQLite ｜ 数据截至 2026-09-12

## 这是什么

基于五大联赛（英超、西甲、德甲、意甲、法甲）真实数据的足球数据分析与预测系统：
**12,698 场比赛 · 11,315 场已完赛 · 1,379 场待赛 · 4,745 名球员 · 240 支球队 · 10 个联赛**。
界面、图表与每一个数字都来自本地 SQLite 数据库（`data/database/football.db`，158.8 MB / 36 张表），
没有写死的假数据。

## 入口

| 入口 | 地址 | 说明 |
|---|---|---|
| 用户端 + 管理端（React SPA） | <http://127.0.0.1:8000/> | 16 条路由：总览 / 赛程 / 比赛详情 / 联赛 / 联赛详情 / 球队 / 球队详情 / 球员 / 球员详情 / 预测 / 实时；管理端 4 页签在 `/admin`（数据总览 / 数据资产 / 模型注册表 / 系统与接口） |
| 登录页（控制台设计稿版） | <http://127.0.0.1:8000/console/login.html> | 未登录访问任何页面都会整页跳到这里；演示账号 `admin / football2026`；页面下方有 **注册新账号** 与 **忘记密码** 两个入口 |
| 注册 | <http://127.0.0.1:8000/console/register.html> | 自助注册，新账号固定是 `user`（用户端）角色，注册成功即登录；`AUTH_ALLOW_REGISTER=false` 可关闭 |
| 忘记密码 | <http://127.0.0.1:8000/console/forgot.html> | 两步式：申请一次性 6 位重置码 → 用它设新密码并踢掉旧会话。**默认页面上不显示码**（公网安全），码写在 **`logs/auth_reset.log`**（UTF-8，一行一条）与 uvicorn 日志里，由管理员转告用户；自己一个人用可设 `AUTH_RESET_SHOW_CODE=true` 让它直接回显 |
| 接口文档 | <http://127.0.0.1:8000/docs> | FastAPI 自动生成 |
| 控制台静态页（可选） | <http://127.0.0.1:8591/> | `python scripts/serve_console.py` |
| 参照版界面（Streamlit，可选） | <http://127.0.0.1:8501/> · <http://127.0.0.1:8502/> | `start.bat` / `start_admin.bat` |

## 技术栈

| 层级 | 技术 |
|---|---|
| 前端 | React 19 + TypeScript + Vite + Tailwind（自研玻璃质感组件 kit） |
| 后端框架 | FastAPI + Uvicorn |
| 数据处理 | Pandas + NumPy + SQLAlchemy |
| 数据库 | SQLite（开发） |
| 检索 | SQLite FTS5 + jieba 中文分词（自建索引 `data/database/search.db`，不依赖外部检索服务） |
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
│   ├── api/ui.py            # 前端所需的全部聚合接口（26 个端点）
│   ├── api/search.py        # 全文检索接口（RAG 阶段 0，见 docs/检索层说明.md）
│   └── api/auth.py          # 登录 / 会话 / 扫码 / 账号管理
├── webui/                   # 前端：React 源码 + 构建产物 dist（node_modules 不入库）
│   ├── src/pages/           # 16 条路由对应的页面
│   └── src/sections/        # 首页等页面的区块组件
├── docs/
│   ├── console/             # 控制台静态页（登录页 login.html 就在这里）
│   ├── webui/               # 交付截图 17 张
│   └── *.md                 # 设计与实现文档（见下方索引）
├── scripts/                 # 构建、导入、自检脚本
├── deploy/                  # 部署用：systemd 单元 + nginx 反代示例
├── data/                    # 数据库 + 采集到的原始/外部数据（不入库）
├── models/                  # 训练好的模型文件（.joblib/.pt 不入库）
├── tools/                   # console_template.html（控制台生成器的输入）与一次性补丁脚本
├── frontend/                # 参照版界面（Streamlit，8501/8502）
├── requirements.txt         # 运行时依赖（服务器上只需要这一份）
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

登录：`admin / football2026`（另有 `viewer` / `user` 两个非管理员账号，用于验证权限控制）。
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

**要放到公网服务器上**：见 [`docs/deploy.md`](docs/deploy.md)（VPS + nginx 同源 + systemd 的完整步骤，含「数据库/模型/特征 CSV 怎么传」与排错表）。

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
| `scripts/verify_webui.py` | 17 条路由逐页截图 + 断言（控制台报错 / 坏图 / 横向溢出） |
| `scripts/smoke_ui_api.py` | 28 个后端端点连通性与关键字段（含检索两个） |
| `scripts/_login_flow.py` | 登录链路端到端 17 项（未登录跳转、错密码、回跳、退出、权限卡） |
| `scripts/verify_auth_register.py` | 注册 / 忘记密码后端自检 30 项（重名、账号密码规则、默认不回码但日志可取码、重置码时效与一次性、旧会话失效、不提权） |
| `scripts/docs_shots.py` | 重新生成 `docs/webui/` 的 19 张交付截图 |
| `scripts/build_webui.py` | 构建前端产物到 `webui/dist` |
| `scripts/check_deps.py` | 依赖体检：源码 import 与 `requirements.txt` 对照 |
| `scripts/audit_repo_payload.py` | 按 `.gitignore` 推演「哪些文件会进仓库」、有没有 >100 MB 的大文件 |
| `scripts/check_sameorigin.py` | 把控制台 5 页挂在假域名（http/https）上，验证接口是否同源 |
| `scripts/build_search_index.py` | 重建全文检索索引（`data/database/search.db`，19,800 条 / 4.9 秒） |
| `scripts/verify_search.py` | 检索层自检 23 项（中文分词口径、问题复现、引用溯源、接口闸门） |
| `scripts/audit_webui.py` · `scripts/responsive_webui.py` | 信息架构体检 · 多分辨率适配检查 |

## 文档索引

| 文档 | 内容 |
|---|---|
| `docs/详细技术方案.md` | 完整技术设计（模块划分、代码示例、开发路线） |
| `docs/系统架构设计.md` / `docs/系统实现说明.md` | 架构与实现说明 |
| `docs/数据来源与采集说明.md` / `docs/API-Football使用说明.md` | 数据来源、采集流程与第三方接口 |
| `docs/模型评估报告.md` | 模型指标、版本对比、概率校准 |
| `docs/React界面接入说明.md` | 前端路由、登录闸门、脚本与已知边界 |
| `docs/检索层说明.md` | **全文检索层（RAG 阶段 0）**：中文分词实测对比、19,800 条语料、两个检索接口、溯源结构与边界 |
| `docs/信息架构评审.md` | 逐页点评、逻辑硬伤整改、目标结构 |
| `docs/deploy.md` | **部署说明**：VPS + nginx 同源 + systemd、数据/模型怎么传、更新与备份、排错表 |
| `docs/UI设计规范.md` / `docs/UI高级审美评审报告.md` / `docs/UI合规审计报告.md` / `docs/UI协作交接说明.md` / `docs/UI打磨收口记录.md` | UI 规范、评审与打磨记录 |

## 维护说明

- **已清理**：设计迭代产物、旧数据库备份、已解压的数据集压缩包、渲染帧序列、第三方工具目录等共 596.8 MB，
  已移到项目外的 `D:\AIfootball_已清理_20261005\`（保留可恢复，确认无用后手动删除即可）
- **仓库里只有代码 + 项目**：约 **603 个文件 / 35.6 MB**（含 `webui/dist` 构建产物）。
  `data/`（含 `data/external` 的 562 MB 与 3 个 >100 MB 的 CSV）、`models/*.joblib|pt`、`.env`、`node_modules`、派生索引 `data/database/search.db` 都已排除 ——
  部署时前三样要单独传（清单见 `docs/deploy.md` 第 5 节），检索索引在服务器上重建
- 核对命令：`python scripts/audit_repo_payload.py`（按 `.gitignore` 推演会入库的文件，并检查有没有超过 GitHub 100 MB 限制的单文件）
- **Git 状态**：已 `git init -b main` 并完成首次提交（`78932fb`，593 文件 / 94,891 行），远端尚未配置 ——
  建好 GitHub 空仓库后 `git remote add origin <地址>` + `git push -u origin main`（步骤见 `docs/deploy.md` 第 2 节）

## License

MIT
