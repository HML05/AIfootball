# YOLOv8 足球视频检测跟踪 —— 方案与当前进度

> 题目（导师 2026-10 改定）：**基于 YOLOv8 的足球视频球员检测跟踪系统设计与实现**
> 改题原因（导师原话）：「应该是存在博彩风险 尽量不要往预测比分上面靠」；「运动数据统计可以在论文里面写」。
> 落地方式：**保留现有 FootballAI 全部功能**，在同一仓库里长出一个视觉模块（不是推倒重做）。

---

## 1. 定位与边界

| 项 | 决定 | 原因 |
| --- | --- | --- |
| 推理在哪跑 | **本地 RTX 3060 Laptop 6 GB** | 线上是阿里云 2 vCPU / 2 GiB / 无 GPU，装不下也跑不动 2 GB 的 torch CUDA |
| 线上干什么 | 只展示：任务状态、轨迹回放、统计报表 | 与现有 FastAPI + React 一致，不引入新部署形态 |
| 代码放哪 | 同一个仓库 `D:\AIfootball`，新增 `src/vision/` | 用户要求「保留现在的项目，然后与之结合」 |
| 依赖 | 独立 `requirements-vision.txt` + `.venv-vision` | 不能让 torch 拖累主应用与 CI（CI 不装 torch） |
| 视频/权重 | `data/vision/`、`models/vision/`，**均 gitignore** | 仓库是 Public，比赛录像有版权风险 |

**一句话**：本地做重活、把结果写成结构化数据；线上只读这些数据。

---

## 2. 目录结构（本次已落地）

```
D:\AIfootball
├─ src/vision/
│   ├─ __init__.py      包说明；故意不 import 子模块（避免 import 就拉起 cv2）
│   ├─ config.py        路径与默认参数，全部可用环境变量覆盖
│   ├─ detector.py      YOLO 的薄封装：predict() / track()，重依赖懒加载
│   ├─ metrics.py       轨迹 → 统计量（人数/ID 碎裂/球检出/框尺寸/速度）
│   └─ io.py            视频探测、轨迹 JSON 读写、画框与带框视频
├─ scripts/
│   ├─ vision_setup.ps1          一键建 .venv-vision 并装 CUDA 版 torch
│   ├─ vision_fetch.py           把网页链接/mp4 直链抓成本地片段（可只取 30~120 秒）
│   ├─ vision_extract_frames.py  按间隔抽帧（保留原帧号，写 frames_index.json）
│   ├─ vision_prelabel.py        预标注 → YOLO txt（可拼 images/ labels/ data.yaml）
│   └─ vision_smoke.py           阶段 1 可行性冒烟（统计 JSON + 轨迹 + 带框视频）
├─ requirements-vision.txt
├─ data/vision/{videos,frames,runs,out,dataset}/   （gitignore）
└─ models/vision/                                  （gitignore）
```

`src/vision/*` 不 import FastAPI / sqlalchemy / `config.settings`，所以：
主应用的系统 Python 即使没装 torch 也能 `import src.vision`；CI 不受影响。

---

## 3. 环境

```powershell
# 一条命令（建 .venv-vision + CUDA 12.1 版 torch + ultralytics）
powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1

# 没有 NVIDIA 显卡时
powershell -ExecutionPolicy Bypass -File scripts\vision_setup.ps1 -Cpu
```

手动等价命令：

```powershell
py -3.12 -m venv .venv-vision
.venv-vision\Scripts\python.exe -m pip install --index-url https://download.pytorch.org/whl/cu121 torch torchvision
.venv-vision\Scripts\python.exe -m pip install -r requirements-vision.txt
```

**坑**：本机 `py -3.12` 会报 `No suitable Python runtime found`（3.12 是 uv 装的，py 启动器认不到），
必须用完整路径 `C:\Users\陶东辰\AppData\Roaming\uv\python\cpython-3.12.14-windows-x86_64-none\python.exe`；
`scripts/vision_setup.ps1` 里已经写了这条兜底。

依赖装完的判据：

```powershell
.venv-vision\Scripts\python.exe -c "import torch,ultralytics;print(torch.__version__, torch.cuda.is_available(), ultralytics.__version__)"
# 期望：2.x.x True 8.x.x
```

### 3.1 在 VS Code 里跑
`.vscode/` 在 `.gitignore` 里（各人本地配置不入库），本机已放好两份配置：

- `.vscode/settings.json`：**故意不设** `python.defaultInterpreterPath` —— 主应用要跑在系统 Python 3.13，
  视觉模块要跑在 `.venv-vision`（3.12 + torch），设了全局默认就会让其中一个选错环境；
  只配了 `python.analysis.extraPaths` 和排除 2 GB 的 venv 索引。
- `.vscode/launch.json`：三个配置各自钉死解释器路径 ——
  「视觉: 运行当前脚本 (.venv-vision)」「视觉: 冒烟 --demo (.venv-vision)」「主应用: uvicorn (系统 Python 3.13)」。

换机器时照抄这两个配置即可；也可以在 VS Code 右下角手动选解释器，两种方式都不影响另一个环境。

---

## 4. 五条命令

```powershell
$PY = ".venv-vision\Scripts\python.exe"

# 0) 素材是网页链接也能用：先看清晰度，再只抓一段（B 站/腾讯视频/抖音都行，mp4 直链也行）
python scripts\vision_fetch.py "https://www.bilibili.com/video/BVxxxx" --list
python scripts\vision_fetch.py "https://www.bilibili.com/video/BVxxxx" --start 01:20 --duration 60 --max-height 1080

# 1) 抽帧：每 15 帧取一张（25 fps 下约 0.6 秒一张），保留原帧号
& $PY scripts\vision_extract_frames.py --src data\vision\videos\clip.mp4 --step 15
& $PY scripts\vision_extract_frames.py --src data\vision\videos --step 15 --max-frames 300

# 2) 预标注：人基本能检到，球基本会漏 —— 产出 YOLO txt 供人工修
& $PY scripts\vision_prelabel.py --src data\vision\frames\clip --dataset-root data\vision\dataset

# 3) 阶段 1 冒烟：先验证管线通不通（没有真实片段就用 --demo）
& $PY scripts\vision_smoke.py --demo --overlay
& $PY scripts\vision_smoke.py data\vision\videos\clip.mp4 --max-frames 300 --overlay

# 4) 训练（等数据集标好再跑；参数是 6 GB 显存下的保守值）
& $PY -c "from ultralytics import YOLO; YOLO('yolov8s.pt').train(data=r'data\vision\dataset\data.yaml', imgsz=960, batch=4, epochs=60, device=0)"
```

**抓链接的两个坑**（`vision_fetch.py` 里已处理，写下来免得重踩）：
yt-dlp 只认名字叫 `ffmpeg.exe` 的可执行文件，而 `imageio-ffmpeg` 给的是
`ffmpeg-win-x86_64-v7.1.exe`，直接把路径传给 `ffmpeg_location` 会一直报
`You have requested downloading the video partially, but ffmpeg is not installed`；
而且「只下一段」（`--start/--duration`）在解析阶段就要求 ffmpeg 可达。现在的做法是复制改名成
`data/vision/.bin/ffmpeg.exe` 并塞进 PATH。**B 站 1080p 需要登录 cookies**，不登录一般拿到 720p 及以下。

产物：`data/vision/out/<名字>_tracks.json.gz`、`_summary.json`、`_overlay.mp4`；
训练产物在 `data/vision/runs/`。

**权重**：`yolov8s.pt`（21.5 MB）已放在 `models/vision/`（该目录 gitignore）。
本机 GitHub 直连不通（`schannel: CRYPT_E_NO_REVOCATION_CHECK`），这份是从镜像取的：

```powershell
curl.exe -L -o models\vision\yolov8s.pt https://ghfast.top/https://github.com/ultralytics/assets/releases/download/v8.3.0/yolov8s.pt
```

`Detector.load()` 的查找顺序是「字面路径 → `models/vision/<同名文件>` → 交给 ultralytics 自动下载」，
所以命令行写 `--model yolov8s.pt` 会命中本地这份，不会往仓库根目录再落一个 .pt。
训练产出的 `best.pt` 直接给 `--model data\vision\runs\detect\train\weights\best.pt` 即可。

---

## 5. 阶段计划

| 阶段 | 内容 | 判据 | 状态 |
| --- | --- | --- | --- |
| 0 环境 | venv、CUDA torch、ultralytics、目录骨架 | `cuda.is_available()` 为 True | **已完成**（2026-10-20 实测，见下） |
| 1 可行性 | 拿 1~2 段真实片段跑通「检测+跟踪+统计+画框」 | 人数与肉眼一致；球检出率有数 | 脚本已就绪，等真实片段 |
| 2 数据与微调 | 300~800 帧标好 → 微调 yolov8s → 对比 mAP/球召回 | 球召回明显上升 | 未开始 |
| 3 跟踪与视角归一化 | BoT-SORT 调参 + 单应性映射到球场坐标 | 遮挡后 ID 不跳；距离是米而不是像素 | 未开始 |
| 4 统计与论文 | 跑动距离/热区/阵型，接进现有系统 | 线上能看到轨迹回放 | 未开始 |

**阶段 1 的两个硬发现（写论文时可当「问题分析」）**：
1. COCO 预训练模型**几乎看不见足球**（球只有几十个像素 + 白色 + 运动模糊），必须微调；
2. 不做视角归一化就算出「跑动距离」，那是像素距离，答辩一问就露馅。

### 5.1 阶段 0 的实测记录（2026-10-20，本机）

| 项 | 实测值 |
| --- | --- |
| 解释器 | `.venv-vision`（Python 3.12.14，uv 装的 3.12 建的 venv） |
| torch | `2.5.1+cu121`（wheel 2335.9 MB，SJTU 镜像下载；`--no-deps` 装 + 手补 filelock/sympy/networkx/jinja2/fsspec） |
| CUDA / cuDNN | 12.1 / 90100，`torch.cuda.is_available()` = **True** |
| GPU | RTX 3060 Laptop GPU 6 GB（驱动 546.30） |
| ultralytics / cv2 / lap | 8.4.183 / 5.0.0 / 0.5.13 |
| 推理速度 | 合成片段 1280×720、`imgsz=960`、150 帧 → **9.4 s ≈ 15.97 帧/秒**（含跟踪，不含解码预热） |
| 正控（模型是否真的能认人） | ultralytics 官方 `bus.jpg` → **4 个 person + 1 个 bus**，person 框高中位 482.7 px |
| 合成片段（负控） | 3 个红方块 + 白球 → 检出 **0 个目标**（符合预期：那不是人也不是球） |

两个环境层面的坑（都已处理进代码）：

- **GitHub 直连不通**（`schannel: CRYPT_E_NO_REVOCATION_CHECK`）：torch 走 SJTU 镜像、
  `yolov8s.pt` 走 `ghfast.top` 镜像，见下面《权重》一节。
- **opencv 在 Windows 上打不开含中文的路径**（`VideoWriter` 直接 `isOpened()=False`，
  `imwrite` 静默失败）：所以 `io.safe_stem()` 把输出名换成纯 ASCII、`io.ascii_video_path()`
  把中文名的源视频硬链接成一个 ASCII 路径再喂给 cv2。**素材文件名用中文也能跑**，但产物名会被换掉。
- ultralytics 会在 `%APPDATA%\Ultralytics` 不可写时把设置文件落到**仓库根目录**（`Ultralytics/`），
  已在 `.gitignore` 挡掉；`YOLO_CONFIG_DIR` 只在进程启动前设置才生效。

---

## 6. 数据要求（给用户的操作口径）

| 用途 | 数量 | 规格 |
| --- | --- | --- |
| 冒烟 | 1~2 段 30~60 秒 | 1080p、单机位固定转播机位 |
| 训练 | 20~40 段，抽 300~800 帧 | 白天+夜间、≥3 种球衣配色、台标尽量小 |
| 验证 | 5~10 段独立比赛，各 50~100 帧 | **按「比赛/视频」划分，不能按帧随机划分**（否则 mAP 虚高 10~20 点） |
| 演示 | 2~3 段 60~120 秒 | 用来出带框视频/GIF |

其它原则：集锦与慢放帧不当训练数据；先标 200 帧看趋势再批量；难样本（小目标、遮挡）必须进训练集。

### 6.1 素材从哪来（按可行度排序）

1. **自己录屏**：找一场公开转播（电视/网络直播），全屏播放用 OBS 录 1~2 段 60 秒 1080p。
   最省事、马上能做；画质取决于源，压过一次也够跑通。
2. **公开数据集**：SoccerNet（`soccer-net.org`，需申请学术授权）有标注好的比赛片段与跟踪真值，
   拿来做「有真值」的验证最省力；但下载几十 GB，且申请要等。
3. **授权公开素材**：赛事官方或俱乐部发布的免费集锦（注意看许可），只用于本地实验。

版权边界：**录进来的一切只放 `data/vision/`（已 gitignore）**，不进仓库、不进 Release、
不进论文附录；论文里用「第 X 场转播画面」这种匿名描述，不贴原视频帧。

### 6.2 自检

```powershell
# 不需要 torch/cv2 也能跑的核心逻辑（CI 的 static job 就是这种环境）
python scripts\verify_vision.py
# 完整跑（有 cv2 时多 9 项：probe_video / iter_frames / 带框视频）
.venv-vision\Scripts\python.exe scripts\verify_vision.py
```

当前实测：**55 项断言全过**（本机系统 Python 3.13 与 `.venv-vision` 都是 55/55）。
没有 cv2 的环境（CI 的 static job 只装 `requirements.txt`，实测用一个裸 Python 3.12 跑过）会把
「中文路径改道 2 项 + probe_video 尺寸/帧数 + iter_frames 跳帧 + 带框视频 + meta 透传」这 7 项
合并成 1 条跳过 → **48 通过 + 1 跳过**，退出码仍 0。模块这 55 项留本机跑；**接口面的 39 项
（`verify_vision_web.py`）已进 CI 的 runtime job**，见 §8.6。

---

## 7. 难点与对策

| 难点 | 表现 | 对策 |
| --- | --- | --- |
| 球是小目标 | 几十像素、白球贴白线 | 微调 + 提高 imgsz（960/1280）+ 滑窗；投标注一个 `ball` 类 |
| 交叉遮挡 | ID 跳变、同一个人两个 ID | BoT-SORT + 相机运动补偿；碎裂比 >3 就调 `track_buffer` |
| 镜头平移/变焦 | 直接算距离是像素级假数 | 用球场线做单应性（H 矩阵）映射到 105×68 m |
| 6 GB 显存 | batch 一大就 OOM | imgsz 960 + batch 4 + AMP；overnight 跑 |
| 线上跑不动 | 2 GiB 内存 + 无 GPU | 分工：本地处理、结果入库、线上只读 |

---

## 8. 与现有系统的接入（2026-10-20 已落地）

分工一句话：**推理只在本地 `.venv-vision` 里跑，Web 进程只排队与展示**（线上 2 GiB / 无 GPU，装不下
torch，也不该让单 worker 被一次推理卡住）。

### 8.1 表（只增不改）

| 表 | 作用 |
| --- | --- |
| `vision_videos` | 上传的视频：名称、路径、字节数、时长/帧率/宽高/帧数、状态（`uploaded/queued/running/done/failed`） |
| `vision_jobs` | 一次处理任务：`step`/`model`/`conf`/`imgsz`、进度（`frames_done/frames_total/progress`）、`worker`、`overlay_path`、起止时间、错误 |
| `vision_tracks` | 抽样轨迹：`(job_id, frame)` 建索引，每行一个框（`track_id/cls/conf/x1..y2`） |
| `vision_summaries` | 每个任务一份 JSON（`metrics.summarize` 的产物 + `verdict`） |

建表靠 `src/database/crud.py:23 init_db()`（`Base.metadata.create_all`），启动即自动建。

### 8.2 接口（`src/api/vision.py`，12 条）

| 方法 | 路径 | 说明 |
| --- | --- | --- |
| GET | `/api/vision/overview` | 视频数/状态分布、任务数、能力探测（`importlib.util.find_spec` 查 cv2/ultralytics，**不 import**）、处理进程在线状态 |
| GET | `/api/vision/videos` | 视频列表（带最新任务、已处理任务的指标摘要） |
| POST | `/api/vision/videos` | multipart 上传，默认上限 300 MB，落 `data/vision/videos/v<id>.<ext>`；空文件/非视频 400，超限 413 |
| DELETE | `/api/vision/videos/{id}` | 有排队/处理中任务时 409；级联删 tracks / summary / 文件 |
| POST | `/api/vision/videos/{id}/process` | 建排队任务（`step` 1~60、`conf` 0.05~0.95、`imgsz` 320~1280）；同视频已有排队/处理中 409 |
| GET | `/api/vision/jobs/{id}` | 进度 |
| POST | `/api/vision/jobs/{id}/cancel` | 取消（重复取消 409） |
| GET | `/api/vision/videos/{id}/tracks` | 抽样轨迹，紧凑数组 `{"f": 帧, "b": [[id, cls, conf, x1, y1, x2, y2], …]}` |
| GET | `/api/vision/videos/{id}/summary` | 指标 + 五条判定（未完成 404） |
| GET | `/api/vision/videos/{id}/overlay/meta` | 带框视频是否已生成 |
| GET | `/api/vision/videos/{id}/stream?token=` | 原视频（`<video src>` 带不了请求头 → 令牌放查询串） |
| GET | `/api/vision/videos/{id}/overlay?token=` | 带框视频（`--overlay` 生成，mp4v，浏览器多半只给下载） |

### 8.3 处理进程 `scripts/run_vision_jobs.py`

纯 stdlib `sqlite3`（不依赖 SQLAlchemy），所以只要 `.venv-vision` 里装了 torch/ultralytics 就能跑：

```powershell
.venv-vision\Scripts\python.exe scripts\run_vision_jobs.py            # 常驻，每 3 秒领一次队列
.venv-vision\Scripts\python.exe scripts\run_vision_jobs.py --once     # 只跑一轮（验收/CI 用）
.venv-vision\Scripts\python.exe scripts\run_vision_jobs.py --job-id 3 --overlay
```

- `BEGIN IMMEDIATE` + `UPDATE … WHERE status='queued'` 领取任务（`rowcount` 必须为 1），并发起两个进程不会重复吃；
- 每 25 帧更新一次 `frames_done/progress`，并检查 `status='canceled'` 立即停；
- 按 `frame % step == 0` 抽样写库，`metrics.summarize` + `verdict` 写 `vision_summaries`；
- 每轮写心跳 `data/vision/worker.json`（原子替换），网页据此显示「处理进程在线 / 显卡 / 依赖版本」。

### 8.4 页面 `/vision`

顶栏第 8 个入口「视频分析」，与其它页同一套 `PageShell` / `SectionCard` / `KpiStrip` / `Bar` / `Pill`：
左侧原视频 + 绝对定位 canvas（`requestAnimationFrame` 里按 `currentTime*fps` 二分找最近的抽样帧，
画黄框人 / 粉框球 + `#id 置信度%` + 回看 12 帧的轨迹折线；只给高度 ≥46 px（near 档）的框标 ID、每帧最多 10 个），
右侧视频库 / 上传 / 抽样间隔 / 开始处理 / 进度 / 取消 / 删除，下方指标卡与五条判定（`OK / 待看 / 不行`）。
**用 canvas 叠框而不是预渲染带框视频**：浏览器能直接播原视频（H.264），叠框是数据驱动的，随时可关。

### 8.5 首次端到端实测（2026-10-20，本机 RTX 3060 Laptop）

素材：B 站公开业余比赛集锦裁 30 秒（`BV1ehn36VEak`，`scripts/vision_fetch.py --start 00:20 --duration 30 --max-height 720`），
1280×720 / 30 fps / 900 帧 / 6.3 MB。

| 指标 | 实测 | 说明 |
| --- | --- | --- |
| 处理速度 | **34.26 帧/秒**（900 帧 26.27 秒） | `yolov8s` + imgsz 960 + ByteTrack，6 GB 显存够用 |
| 场上人数 | 平均 **11.27 人/帧**（最多 16） | 业余单机位远景，符合画面观感 |
| 唯一 ID | **123** | 30 秒内 123 个 ID 明显偏多 |
| ID 碎裂 | **7.69**（唯一 ID / 单帧最多人数） | >3 即严重，交叉与出画都在换 ID —— **这正是论文要改进的点** |
| 球覆盖率 | **11.89%**（最长连续 33 帧） | COCO 预训练对「远处白球」本来就弱，微调后应显著上升 |
| 框高中位 | **69.3 px**（far 5.1% / mid 66.8% / near 28.1%） | 远景占比高，符合转播机位 |

这些数字只证明「管线通、指标算得对」，**不是模型精度**（没有人工标注真值，算不出召回/mAP）。

### 8.5.1 第二段素材：1080p 转播战术机位（同日补测）

素材：西甲第 11 轮 皇马 2:1 巴萨「战术视角」整场录像（B 站 `BV1NqqABLEDc`）里 10:00 起的 60 秒，
1920×1080 / 25 fps / 1503 帧 / 16.7 MB。这段是高位全景，22 名球员全在画面里，远端只有十几像素 ——
比上面那段业余集锦更接近论文要处理的场景。

| 指标 | 第一段（720p 业余） | 第二段（1080p 转播） | 读法 |
| --- | --- | --- | --- |
| 处理速度 | 34.26 帧/秒 | **35.64 帧/秒**（1503 帧 42.17 秒） | 分辨率涨了 2.25 倍，速度没掉 —— 瓶颈在 `imgsz=960` 的固定缩放，不在原图 |
| 场上人数 | 11.27 人/帧（最多 16） | **25.17 人/帧**（最多 29） | 22 名球员 + 3 名裁判 ≈ 25；场边替补/工作人员也会被算进去 |
| 唯一 ID | 123 | **166** | 60 秒 / 25 人，ID 数明显偏多 |
| ID 碎裂 | 7.69 | **5.72** | 绝对值是「唯一 ID ÷ 单帧最多人数」，两段人口基数不同，不能直接横比 |
| 球覆盖率 | 11.89%（连续 33 帧） | **0.20%（3 帧，连续 3 帧）** | 全景机位下球只有 ~10 px，COCO 几乎检不到 |
| 框高中位 | 69.3 px（far 5.1 / mid 66.8 / near 28.1） | **53.6 px**（far 4.7 / mid 95.2 / near 0.1） | 几乎全部落在 40~90 px 的 mid 档，near 只剩 0.1% |

两条从这组对比里读出来的结论（写论文时可以直接用）：

1. **「球」是这个题目最真实的难点，不是「人」。** 人一帧能检出 25 个、碎裂 5.7；球在战术全景里几乎全丢。
   要往上走只有三条路：把 `conf` 降到 0.1 看召回曲线、**切片推理（SAHI，把 1080p 切块再检）**、
   或者拿标好的球样本单独微调（COCO 的 `sports ball` 本来就少而小）。
2. **人数统计需要一个「场上区域」约束。** 25.17 比场上实际 22~23 人偏高，多出来的是裁判、场边替补与工作人员。
   后处理里用边线/场地多边形做掩膜（或者直接人工框一次场地范围），论文里的「跑动统计」才有意义。

### 8.6 自检

```powershell
python scripts\verify_vision_web.py                     # 39 项接口断言（只需一个跑着的服务）
.venv-vision\Scripts\python.exe scripts\verify_vision.py # 55 项模块断言
python scripts\verify_vision.py                          # 没有 cv2 的环境：48 通过 + 1 跳过，退出码仍 0
```

`verify_vision_web.py` 已进 CI 的 runtime job（不需要 torch：它用 `scripts/fixtures/tiny.mp4`，
一个 2,774 B 的真 mp4）。**处理进程本身不进 CI** —— 2.4 GB 的 torch 装不进分钟预算，
所以「推理真的跑通了」这条只能靠本机实测记录（就是上面 8.5 那张表）。

### 8.7 部署上的边界（别误解）

- 线上实例能**上传、排队、看已入库的结果**；点「开始处理」只是建一条 `queued` 任务，
  **不会真的推理**（网页进程没有 torch），要靠本机跑 `run_vision_jobs.py`；
- 因此线上页面里「处理进程」那一栏常显示 `offline`、显卡/依赖为空 —— 这是设计如此，不是坏了；
- 视频文件落在 `data/vision/`（已 gitignore），不进仓库、不进 Release，公网实例上也只是临时数据；
- 若以后要「服务器自己处理」，得换带 GPU 的机器或把推理做成独立服务，属于另一件工程。

---

## 9. 参数实验：球到底能不能检到（2026-10-20 实测）

素材固定为上面那段 1080p 转播战术机位（`data/vision/videos/v2.mp4`，1920×1080 / 25 fps / 1503 帧），
机器固定为本机 RTX 3060 Laptop 6 GB（驱动 546.30，torch 2.5.1+cu121）。三个实验各跑满全片。

### 9.1 实验 A：只降阈值 —— 无效

| `conf` | 球覆盖率 | 球框总数 | 最长连续段 | 人数/帧 | 碎裂 | 唯一 ID |
| --- | --- | --- | --- | --- | --- | --- |
| 0.25（默认） | 0.20% | 3 | 3 帧 | 25.17 | 5.72 | 166 |
| 0.15 | 0.20% | 3 | 3 帧 | 25.62 | 5.27 | 158 |
| 0.10 | 0.20% | 3 | 3 帧 | 25.93 | 4.87 | 151 |
| 0.05 | 0.20% | 3 | 3 帧 | 25.93 | 4.87 | 151 |

阈值从 0.25 一路压到 0.05，球框总数一动不动（都是 3 个、都是同 3 帧）。
**结论：不是置信度卡住了，是球在 `imgsz=960` 的输入下只剩 3~5 像素，特征根本没进网络。**

### 9.2 实验 B：只换输入分辨率 —— 决定性

`conf` 固定 0.10，其余参数不动：

| `imgsz` | 处理速度 | 球覆盖率 | 球框总数 | 最长连续段 | 人数/帧 | 碎裂 | 唯一 ID | 框高中位 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- |
| 960 | 26.98 帧/秒 | 0.20% | 3 | 3 帧 | 25.93 | 4.87 | 151 | 53.3 px |
| 1280 | 27.14 帧/秒 | 2.00% | 30 | 24 帧 | 27.05 | 3.50 | 112 | 53.1 px |
| **1536** | 23.86 帧/秒 | **20.23%** | **373** | **91 帧** | 28.04 | 3.31 | 112 | 52.6 px |

**结论：球的问题几乎全是分辨率问题。** 960 → 1536，球覆盖率涨 100 倍（0.20% → 20.23%）、
最长连续段从 3 帧涨到 91 帧，代价只有速度掉 12%（27 → 24 帧/秒）。这条比「上 SAHI」便宜得多。

顺带一个必须写下来的测量陷阱：**同一配置首次运行会明显偏快**。
第一轮（冷机）读数是 32.81 / 38.58 / 26.04 帧/秒，连跑三轮后同样配置只有 26.98 / 27.14 / 23.86 ——
笔记本 GPU 有热降频，速度必须在热机后测，否则第一轮会被高估约 20%。上面表里用的是热机读数。

### 9.3 实验 C：人眼验框（这个数字可信到什么程度）

在 `imgsz=1536`、`conf≥0.20` 下取前 6 个球检出，各裁「球框周围 320×320、放大 2 倍」存图
（`_vision_tmp/ballcheck/`）人工看：框贴住的是一个亮黄绿色的小目标，位置在边线与守门员之间，
**不是白线、广告牌或球鞋造成的误检**。但 6 帧都停在同一位置、`conf` 0.25~0.46 —— 这一段是定位球摆放，
球本来就不动，所以它只证明「检得到」，不证明「检得准」。

诚实的边界：**没有人工标注真值，20.23% 只是覆盖率，不是召回率，更不是精度**。
要写进论文的召回率/精度，只能靠 9.5 那份人工标注。

### 9.4 由实验得到的三个参数决定

1. **默认 `imgsz` 从 960 提到 1280**：速度不变，球覆盖率翻 10 倍；
2. **1536 作为「球分析」档位**：速度 -12% 换球覆盖 20%，处理 60 秒片段仍只要 63 秒；
3. **SAHI 切片推理暂时不上**：1536 已经拿到 20% 覆盖，SAHI 等效再放大 3~4 倍但会把速度压到 4~8 帧/秒，
   等微调之后再评估要不要为「球事件检测」单独上。

### 9.5 预标注数据集（微调的准备，已备好）

| 项目 | 现状 |
| --- | --- |
| 抽帧 | `vision_extract_frames.py --src data/vision/videos/v2.mp4 --step 15 --max-frames 100` → **100 张 1080p**，`frames_index.json` 记录原帧号（便于回查视频） |
| 预标注 | `vision_prelabel.py --conf 0.10 --roi 0.01,0.15,0.99,0.94 --min-height 18` → **2500 框 / 100 张 = 25 框每张**（ROI 外丢掉 317 个看台/替补席假人，过小 4 个） |
| 为什么是 25 框 | 场上 22 名球员 + 3 名裁判 ≈ 25，正好对得上 —— 说明 ROI 过滤后留下的基本是真正的比赛参与者 |
| 目录 | `data/vision/dataset/{images,labels,classes.txt,data.yaml,启动标注.bat}`（已 gitignore，不进仓库） |
| 标注工具 | labelImg（已装进系统 Python 3.13，Qt 5.15.2）；双击 `启动标注.bat` 即打开并预填目录 |

标注口径（省时间的关键是**预标注已经把「画框」变成「改框」**）：

- 预标注给的框大多是对的，只需要改错框、删假框（看台上的人、被画面切一半的人）；
- 球漏了就手动画一个 `ball` 框；真没球就留空 —— 空标签是有信息量的负样本；
- 标完把 `data.yaml` 的 `val` 指向**另一场比赛**抽的帧：**数据集必须按比赛/视频划分，不能按帧随机划分**，
  同一场比赛的相邻帧几乎一样，随机划分会让 mAP 虚高 10~20 个点；
- 训练命令（6 GB 显存下 `batch=8` + `imgsz=1280` 已接近上限）：

```powershell
.venv-vision\Scripts\python.exe -m ultralytics detect train `
  data=data\vision\dataset\data.yaml model=models\vision\yolov8s.pt `
  epochs=100 imgsz=1280 batch=8 project=models\vision\runs name=finetune-v1
```

---

## 10. 验收口径（诚实说明）

- 阶段 1 的 `_summary.json` **不含 mAP / 召回率**：没有人工标注真值就算不出来，里面只有
  「检出密度、球覆盖率、ID 碎裂比、框尺寸分布、处理速度」——它们是「管线跑通」的证据，不是模型精度。
- 真指标要等阶段 2 数据集标好后跑 `yolo val`，届时把 mAP50 / mAP50-95 / 球召回写进文档与论文。
- `--demo` 生成的合成片段里没有人（三个方块不是人），跑出来人数为 0 属预期，只证明链路通。
