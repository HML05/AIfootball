# 部署说明（把系统放到一台能公网访问的服务器上）

> 目标形态：**一台 VPS（最小 2 核 2G）+ nginx 同源反代 + systemd 常驻**；
> **代码走 GitHub**，**数据与模型单独传**（不进仓库）。
> 本地开发不用这套，直接看最后一节。

---

## 0. 为什么是这套（结论先给）

| 方案 | 能不能用 | 关键理由 |
|---|---|---|
| **VPS + nginx + systemd**（推荐） | ✅ | 数据库是 **SQLite 单文件（~159 MB）**，必须有持久盘；5 个定时任务要有常驻进程；启动即载 shap + 模型，常驻内存 **0.7~1.2 GB** |
| Cloudflare Tunnel（过渡） | ✅ | 免费、自带 HTTPS、免备案、当天就有网址；但**依赖你本机常开**，同一套同源修复照样要做 |
| PaaS（Render / Railway / Vercel…） | ⚠️ | 界面能跑，但免费层是**临时盘**（重启即丢库）、会休眠、国内访问不稳 |
| 只开 8000 端口直连 | ⚠️ | 能用，但没 HTTPS：浏览器会提示不安全，登录态与密码走明文 |

**域名与备案**：国内服务器 + 域名必须 ICP 备案（1~3 周）；急着上线就选香港/新加坡 VPS（国内访问 30~80 ms，免备案）。

---

## 1. 仓库里有什么、没有什么

`.gitignore` 已把大文件与密钥排除，仓库只有 **618 个文件 / 37.2 MB**（含 `webui/dist` 构建产物，最大单文件 2.28 MB）。

**仓库里有**：`src/`（后端）、`webui/`（React 前端源码 + `dist`）、`docs/`（含 `docs/console/*.html` 登录/注册/忘记密码页）、`scripts/`、`tools/`、`frontend/`（旧 Streamlit 参照版）、`stadium-scenes/`、`requirements*.txt`、`deploy/`、`start*.bat`、`start.sh`。

**仓库里没有（部署时必须单独补，见第 5 节）**：

1. `data/database/football.db` —— 数据库本体（~159 MB）
2. `models/*.joblib`、`models/*.pt` —— 预测模型（~11 MB，缺了预测接口会 `FileNotFoundError`）
3. `data/processed/*.csv` —— 预测特征输入（`all_matches.csv`、`tm_team_season.csv`、`match_xg.csv`）
4. `.env` —— 由 `.env.example` 复制后填真实 key

---

## 2. 一次性准备：本地

```bash
# 1) 装 Git（Windows 目前没有装：https://git-scm.com/download/win，装完重开终端）
git --version

# 2) 初始化并首次提交（在项目根目录）
cd D:/AIfootball
git init -b main
git add .
git status            # 确认：没有 .env、没有 data/、没有 models/*.joblib；有 webui/dist 与 webui/src/lib
git commit -m "feat: 足球数据分析与 AI 预测系统（React 界面 + 登录/注册/忘记密码）"

# 3) 推到 GitHub（先在网页上建一个空仓库，别勾 README）
git remote add origin https://github.com/你的账号/AIfootball.git
git push -u origin main
```

> 提交前务必核对两件事：**`.env` 没被提交**（含 3 把真 key）；**`webui/src/lib/` 和 `webui/dist/` 在提交列表里**（早期 `.gitignore` 的 `lib/`、`dist/` 写成裸规则会误伤它们，已修成 `/lib/`、`/dist/`）。
> 改了前端源码后，提交前先 `python scripts/build_webui.py`，否则服务器上跑的还是旧界面。

## 3. 一次性准备：服务器

```bash
# 以 Ubuntu 22.04/24.04 为例，root 执行
apt update && apt install -y python3 python3-venv python3-pip git nginx sqlite3

# 建一个专用账号（不要用 root 跑服务）
useradd -m -s /bin/bash football
mkdir -p /opt/footballai && chown football:football /opt/footballai

# 换源可加速（国内机器）
# pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

## 4. 拉代码 + 装依赖

```bash
sudo -iu football
git clone https://github.com/你的账号/AIfootball.git /opt/footballai
cd /opt/footballai

python3 -m venv .venv
.venv/bin/python -m pip install -U pip
.venv/bin/python -m pip install -r requirements.txt      # ~19 个包，约 3~5 分钟

# 体检：源码用到的第三方模块是否都装上了（缺必需依赖会 exit 1）
.venv/bin/python scripts/check_deps.py
```

`requirements.txt` 里已经补上了 **`qrcode` + `pillow`**（扫码登录要用，原来漏了）；`langchain` 不在里面 —— 它只被 `src/agent/*` 用，而没有任何模块 import 那段代码，**主应用启动不会加载它**。

## 5. 把数据与模型传上服务器（关键一步）

在**本地**打包这 4 样（它们不在 Git 里）：

```bash
cd D:/AIfootball
tar -czf football_data.tgz data/database/football.db data/processed/*.csv
tar -czf football_models.tgz models/*.joblib models/*.pt
scp football_data.tgz football_models.tgz football@服务器IP:/tmp/
```

在**服务器**上展开：

```bash
cd /opt/footballai
mkdir -p data/database data/processed models
tar -xzf /tmp/football_data.tgz -C .
tar -xzf /tmp/football_models.tgz -C .
ls -lh data/database/football.db models/ensemble_v2_v7.joblib models/xgb_v2.joblib \
       data/processed/all_matches.csv data/processed/tm_team_season.csv data/processed/match_xg.csv
```

缺这几样的后果：

| 缺什么 | 会怎样 |
|---|---|
| `data/database/football.db` | 界面数字全是 0（表会自动建，但没数据） |
| `models/ensemble_v2_v7.joblib` / `models/xgb_v2.joblib` | 预测接口报 `FileNotFoundError: 未找到 models/…, 请先运行 scripts/train_v2.py` |
| `data/processed/*.csv` | 预测特征算不出来（`src/prediction/vector_features*.py` 读它们） |

> `data/external/`（562 MB，含 3 个 >100 MB 的文件）**不用传**：那是离线数据集，运行时只用到 `data/external/af_cache` 缓存目录（会自动创建）。

**还要建一次全文检索索引**（`data/database/search.db` 不在 Git 里，属于可重建的派生数据）：

```bash
cd /opt/footballai
python scripts/build_search_index.py     # 19,800 条 / 17.8 MB / 约 5 秒；缺 jieba 会自动退化为字符 bigram
python scripts/verify_search.py          # 23 项自检（需要服务已在 8000 运行）
```

不建也不影响主界面：`/api/ui/search` 会返回 503 并提示先建索引，`/api/ui/search/stats` 返回 `ready: false`。
`data/reference/team_alias_zh.json`（240 支球队中文别名）**在 Git 里**，不用单独传；它决定「皇马」「曼城」这类中文队名能否被搜到。

## 6. 配置 .env

```bash
cd /opt/footballai
cp .env.example .env
nano .env
# 如果 .env 是在 Windows 上编辑过再传上来的，先去掉 CRLF —— systemd 的 EnvironmentFile
# 会把 \r 一起吃进变量值，导致 host/端口带非法字符
sed -i 's/\r$//' .env
```

生产**至少**改这几项：

```ini
DEBUG=false                        # 生产必须关，否则 uvicorn 开 --reload
SERVER_HOST=127.0.0.1              # 由 nginx 反代对外；想直接对外就 0.0.0.0
SERVER_PORT=8000
UI_REQUIRE_AUTH=true               # 登录闸门
AUTH_ALLOW_REGISTER=true           # 允许自助注册；不想开放就 false
AUTH_RESET_SHOW_CODE=false         # 公网安全：重置码只写日志，由管理员转告
ENABLE_LIVE_SCORE_UPDATE=true      # 每 5 分钟拉实时比分（可关）
ENABLE_DAILY_UPDATE=true           # 每日赛程/赛果/身价同步（可关）
# 数据源 key 按需填：API_FOOTBALL_KEY / API_SPORTS_KEY / FOOTBALL_DATA_TOKEN / QIXIAOCE_API_KEY
```

**管理员账号**：数据库里已有 4 个账号（`admin` / `viewer` / `user` / `uipreview`，密码是哈希，取不回来）。要改密码：

```bash
.venv/bin/python scripts/add_user.py --list
.venv/bin/python scripts/add_user.py -u admin -p 你的新密码 --role admin
```

## 7. 先在前台跑一遍，逐条自检

```bash
cd /opt/footballai
.venv/bin/python -m uvicorn src.main:app --host 127.0.0.1 --port 8000 --workers 1
```

另开一个终端：

```bash
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/                     # 200 界面
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/console/login.html   # 200 登录页
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/docs                 # 200 接口文档
curl -s http://127.0.0.1:8000/api/ui/public/summary                                 # {"matches":12698,...}
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8000/api/ui/home          # 401（闸门生效）
curl -s -X POST http://127.0.0.1:8000/api/auth/login \
     -H 'Content-Type: application/json' \
     -d '{"username":"admin","password":"你的密码"}'                                 # {"ok":true,"token":...}
python scripts/smoke_ui_api.py      # 28 个端点（含检索两个）
python scripts/verify_search.py     # 23 项检索层断言
```

浏览器打开 `http://服务器IP:8000/`（或先做完第 9 节的 nginx 再访问域名）：应自动跳到登录页，用管理员登录后能看到真实数据。
忘记密码的验证码写在 **`logs/auth_reset.log`**（同时进 journald/stdout）：
`[auth] 重置码 username=xxx code=123456 ttl=10min from=…`

## 8. 用 systemd 常驻

```bash
sudo cp deploy/footballai.service /etc/systemd/system/footballai.service
sudo nano /etc/systemd/system/footballai.service     # 改 User=football、WorkingDirectory=/opt/footballai
sudo systemctl daemon-reload
sudo systemctl enable --now footballai
systemctl status footballai --no-pager
journalctl -u footballai -f                          # 看日志（Ctrl+C 退出）
```

> **必须单 worker**（`--workers 1`）：应用启动时会拉起 APScheduler 的 5 个定时任务，多 worker 会各跑一份，造成重复抓取、重复写库。单元文件里已经写死。

## 9. nginx 同源反代 + HTTPS

```bash
sudo cp deploy/nginx.conf.example /etc/nginx/sites-available/footballai
sudo nano /etc/nginx/sites-available/footballai     # 改 server_name 为你的域名
sudo ln -s /etc/nginx/sites-available/footballai /etc/nginx/sites-enabled/
sudo rm -f /etc/nginx/sites-enabled/default
sudo nginx -t && sudo systemctl reload nginx

sudo apt install -y certbot python3-certbot-nginx
sudo certbot --nginx -d 你的域名 -d www.你的域名     # 自动签证书、自动续期
```

**为什么一定要同源**：控制台页（`docs/console/*.html`）和前端 SPA 都按「同源优先」取接口 —— 这段逻辑已经改好了：

```js
var API = '';
try {
  if (location.protocol === 'file:') API = 'http://127.0.0.1:8000';
  else if (location.protocol !== 'https:' && location.port && location.port !== '8000')
    API = 'http://' + (location.hostname || '127.0.0.1') + ':8000';
} catch (e) { API = ''; }
```

含义：从 nginx/HTTPS 进来时 `API` 为空 → 走同源 `/api/...`（无跨域、无混合内容）；本机用 Python 直接起 8000 时也自然同源；老写法 `http://<host>:8000` 已删除。React 前端不用管（`webui/src/lib/base.ts` 本来就是同源优先，开发态才用 `127.0.0.1:8000`）。

## 10. 日常更新流程

```bash
# 本地：改代码 → 验证 → 提交
cd D:/AIfootball
#   改了前端源码才需要：  python scripts/build_webui.py
git add -A && git commit -m "xxx" && git push

# 服务器：拉取 + 重启（改了前端要顺手拉上新的 webui/dist，它已在仓库里）
cd /opt/footballai
git pull
.venv/bin/python -m pip install -r requirements.txt      # 仅当依赖变了
sudo systemctl restart footballai
journalctl -u footballai -n 50 --no-pager
```

回滚就是 `git revert` 或 `git checkout <上一个提交>` 后重启。**数据不会被覆盖**（`data/`、`models/`、`.env` 都不在仓库里）。

## 11. 备份

```bash
# SQLite 一致性备份（不要直接 cp 正在写的库）
sqlite3 /opt/footballai/data/database/football.db ".backup '/opt/backup/football-$(date +%F).db'"
# 定时备份（crontab -e，每天 4:10）
10 4 * * * sqlite3 /opt/footballai/data/database/football.db ".backup '/opt/backup/football-$(date +\%F).db'"
# 模型、配置与用户上传（data/uploads 只有头像，丢了会退回默认图，可按需省略）
tar -czf /opt/backup/models-$(date +%F).tgz -C /opt/footballai models .env data/uploads
```

> `data/uploads/avatars/` 是用户上传的头像（`POST /api/auth/avatar` 落盘处）。
> 它不在仓库里，**丢了只会退回默认头像 `/images/profile.png`**，不备也无所谓；
> 想连头像一起保住，就照上面那行把 `data/uploads` 一并打包。

## 12. 排错

| 现象 | 原因 / 处理 |
|---|---|
| 打开是白屏、控制台报 404 `/assets/index-xxx.js` | `webui/dist` 没传或没提交 → 本地 `python scripts/build_webui.py` 后一起上传 |
| 一排 `401 {"detail":"未登录或登录已过期"}` | 正常，闸门生效；要么登录，要么临时 `UI_REQUIRE_AUTH=false` 起服务 |
| 登录一直提示「账号或密码不正确」 | 密码框不做 trim（末尾空格会失败）、区分大小写；用 `scripts/add_user.py` 重置 |
| 界面数字全是 0 | `data/database/football.db` 没传（第 5 节） |
| 预测页报 `FileNotFoundError: 未找到 models/…` | `models/*.joblib` 没传 |
| 页面能开但数据接口 CORS/混合内容报错 | 没走同源：确认用域名（nginx）访问，而不是 `IP:8000` + HTTPS |
| 扫码登录页签空白 | 缺 `qrcode`/`pillow` → `pip install -r requirements.txt` |
| 内存被杀（OOM） | 启动即载 shap + 模型，常驻 0.7~1.2 GB → 至少 2 GB 内存，或加 swap |
| 定时任务重复抓取 | 起了多个 worker → 只能用 `--workers 1` |
| 服务器时间不对导致任务不跑 | 时区：`timedatectl set-timezone Asia/Shanghai`（任务按 Asia/Shanghai 排程） |

## 13. 本地开发（和部署无关）

```bash
# 后端（Windows：双击 start_webui.bat 等价）
python -m uvicorn src.main:app --host 127.0.0.1 --port 8000
# 前端热更新（改 webui/src 立刻生效，接口指向 8000）
cd webui && npm run dev            # http://127.0.0.1:3000
# 自检
python scripts/verify_webui.py     # 17 条路由：无报错/无坏图/无横向溢出
python scripts/smoke_ui_api.py     # 26 个接口
python scripts/_login_flow.py      # 登录/退出/权限 17 项
python scripts/verify_auth_register.py   # 注册/忘记密码 30 项接口断言
python scripts/_register_flow.py   # 注册 + 忘记密码浏览器端 25 项
python scripts/check_deps.py       # 依赖体检
```

自检脚本依赖 `requirements-dev.txt`（playwright / torch / scipy / vl-convert / pathspec），生产不用装。

---

## 14. 这份文档对应的改动（2026-10 部署前「填坑」记录）

| 改了什么 | 为什么 |
|---|---|
| 根 `.gitignore` 重写：`dist/`、`lib/` 等裸规则改为根目录锚定 `/dist/`、`/lib/` | 裸规则匹配任意层级，会把 **`webui/dist`（构建产物）与 `webui/src/lib`（前端工具库）一起忽略**，推上去是白屏的坏仓库 |
| 新增忽略 `data/external/`、`data/cache/`、`*.gz`、`*.parquet`、`data/database/*.db-wal/-shm/-journal` | `data/external` 有 3 个 >100 MB 的文件（GitHub 硬限），WAL 侧文件也不该进仓库 |
| `webui/.gitignore` 去掉忽略 `dist` | 改为**故意提交**构建产物：服务器不装 Node，`git pull` 就能跑 |
| `requirements.txt` 补 `qrcode` + `pillow`，版本改为本机实装版本 | 扫码登录缺这两个包会静默失效；原文件版本号是过时的（numpy 1.26 vs 实装 2.4.1） |
| 新增 `requirements-dev.txt` | 自检/训练用的 playwright / torch / scipy / vl-convert / pathspec 与生产隔离 |
| 新增 `scripts/check_deps.py` | 用 `ast` 扫全项目 import 与依赖文件对照，避免再漏包 |
| 新增 `scripts/audit_repo_payload.py` | 用 pathspec 等价推演「哪些文件会进仓库」+ 检查 >100 MB 单文件（写它的时候本机还没装 git；现在已装 Git 2.55 并已 `git init` + 首次提交） |
| 新增 `scripts/check_sameorigin.py` | 本机 8000 访问区分不出新旧取址写法，用假域名（http/https）验证同源 |
| `.env.example` 重写 | 补齐 `config/settings.py` 里全部 env 名（注册/重置码/数据源预算等），并写明必填与生产默认值 |
| 控制台 5 页（login / register / forgot / index / admin）取址改为**同源优先** | 原写法 `http://<host>:8000` 在「域名 + HTTPS」下会被浏览器按混合内容拦截；备份原件在 `D:\AIfootball_部署前备份_20261005\console\` |
| 新增 `start.sh`、`deploy/footballai.service`、`deploy/nginx.conf.example`、`docs/deploy.md` | 一套可直接照抄的部署路径 |

**验证记录**：`scripts/check_sameorigin.py` 10/10（假域名下 5 页全部同源、无 `:8000`、无控制台报错）；`scripts/verify_webui.py` 17/17（生产构建）；`scripts/smoke_ui_api.py` 28/28；`scripts/_login_flow.py` 17/17；`scripts/verify_search.py` 23/23；`scripts/check_deps.py` 通过；`scripts/audit_repo_payload.py` 通过（603 文件 / 35.6 MB，最大单文件 2.28 MB）。

### 14.1 后续增补：全文检索层（RAG 阶段 0，2026-10）

| 改了什么 | 说明 |
|---|---|
| 新增 `src/search/`（tokenizer / indexer / query）与 `src/api/search.py` | 中文全文检索：FTS5 + jieba 分词，语料 19,800 条、索引 17.8 MB、查询 2~11 ms；详见 `docs/检索层说明.md` |
| 新增 `data/reference/team_alias_zh.json` | 业务库 `teams` 只有英文名，中文队名（皇马/曼城/拜仁…）靠这张 240 队别名表才能召回；**该文件入库** |
| `data/database/search.db` 属派生数据 | 已被 `data/database/*.db` 忽略，服务器上按第 5 节用 `scripts/build_search_index.py` 重建 |
| `scripts/smoke_ui_api.py` 26 → **28** 个端点 | 新增 `/api/ui/search`、`/api/ui/search/stats` 两个用例 |
| `requirements.txt` 增 `jieba==0.42.1` | 装了走上等分词；没装自动退化为字符 bigram（不影响启动） |

**未验证项**：`start.sh` 在本机无法执行（没装 bash，WSL 也没装发行版），只做了人工核对；Windows 路径由 `start_webui.bat` + 直接起 uvicorn 验证过。首次上服务器时请留意第 7 节的逐条自检。
