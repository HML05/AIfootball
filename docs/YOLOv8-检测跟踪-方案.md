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

当前实测：**50 项断言全过**（本机系统 Python 3.13 与 `.venv-vision` 都是 50/50）。
没有 cv2 的环境（CI 的 static job 只装 `requirements.txt`，实测用一个裸 Python 3.12 跑过）会把
「中文路径改道 2 项 + probe_video 尺寸/帧数 + iter_frames 跳帧 + 带框视频 + meta 透传」这 7 项
合并成 1 条跳过 → **43 通过 + 1 跳过**，退出码仍 0。这个脚本暂未接入 CI —— 等视觉接口落地时再一起接。

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

## 8. 与现有系统的接入点（后续工作，尚未开始）

1. 表（只增不改）：`vision_videos`、`vision_jobs`、`vision_tracks`（抽样入库）、`vision_summary`；
2. 接口：`src/api/vision.py`，在 `src/main.py` 里 `include_router`；
3. 处理进程：`scripts/run_vision_jobs.py`（独立进程，绝不塞进 uvicorn 请求里——单 worker 会卡整站）；
4. 前端：`webui/src/sections/Vision.tsx` + `App.tsx` 加一条 `/vision` 路由，用 canvas 叠框而不是预渲染视频。

---

## 9. 验收口径（诚实说明）

- 阶段 1 的 `_summary.json` **不含 mAP / 召回率**：没有人工标注真值就算不出来，里面只有
  「检出密度、球覆盖率、ID 碎裂比、框尺寸分布、处理速度」——它们是「管线跑通」的证据，不是模型精度。
- 真指标要等阶段 2 数据集标好后跑 `yolo val`，届时把 mAP50 / mAP50-95 / 球召回写进文档与论文。
- `--demo` 生成的合成片段里没有人（三个方块不是人），跑出来人数为 0 属预期，只证明链路通。
