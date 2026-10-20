"""视觉模块的路径与默认参数（全部可用环境变量覆盖）。

约定：所有大文件（视频、抽帧、权重、训练产物）都落在 data/vision 与
models/vision 下，并且这两个目录都在 .gitignore 里——仓库是 Public 的，
视频素材有版权风险，权重是几百 MB 的二进制。
"""
from __future__ import annotations

import os
from pathlib import Path

# D:\AIfootball  —— src/vision/config.py 的上两级
BASE_DIR = Path(__file__).resolve().parents[2]

VISION_DIR = Path(os.getenv("VISION_DIR", BASE_DIR / "data" / "vision"))
VIDEO_DIR = VISION_DIR / "videos"      # 原始/待处理视频
FRAME_DIR = VISION_DIR / "frames"      # 抽出来的帧
RUN_DIR = VISION_DIR / "runs"          # ultralytics 的 runs（训练/验证输出）
OUT_DIR = VISION_DIR / "out"           # 冒烟结果：tracks.json / summary.json / 带框视频
DATASET_DIR = VISION_DIR / "dataset"   # YOLO 格式数据集（images/ labels/ data.yaml）

# 权重单独放，不跟主应用那几个 joblib 混在一起
WEIGHT_DIR = Path(os.getenv("VISION_WEIGHT_DIR", BASE_DIR / "models" / "vision"))

DEFAULT_MODEL = os.getenv("VISION_MODEL", "yolov8s.pt")
DEFAULT_IMGSZ = int(os.getenv("VISION_IMGSZ", "960"))
DEFAULT_CONF = float(os.getenv("VISION_CONF", "0.25"))
DEFAULT_TRACKER = os.getenv("VISION_TRACKER", "bytetrack.yaml")

# ultralytics 会把 settings.json 写到 %APPDATA%\Ultralytics；本机因为中文用户名那条路
# 被判成不可写，它会回落到「当前工作目录/Ultralytics」，也就是仓库根目录。
# 实测 `YOLO_CONFIG_DIR` 环境变量在 8.4.x 里管不到这个位置（USER_CONFIG_DIR 仍落在 cwd），
# 所以不折腾重定向，直接在 .gitignore 里挡掉 `Ultralytics/`——它只是 ultralytics 的设置文件。

# COCO 预训练的类别编号；自己微调后按训练时 names 的顺序来
COCO_PERSON = 0
COCO_SPORTS_BALL = 32

DIRS = (VIDEO_DIR, FRAME_DIR, RUN_DIR, OUT_DIR, DATASET_DIR, WEIGHT_DIR)


def ensure_dirs() -> None:
    """建好所有输出目录（幂等）。"""
    for d in DIRS:
        d.mkdir(parents=True, exist_ok=True)


def describe() -> dict:
    """给脚本开头打印用：当前生效的配置与目录是否存在。"""
    from importlib import util as _util

    def _has(mod: str) -> bool:
        return _util.find_spec(mod) is not None

    return {
        "BASE_DIR": str(BASE_DIR),
        "VISION_DIR": str(VISION_DIR),
        "WEIGHT_DIR": str(WEIGHT_DIR),
        "model": DEFAULT_MODEL,
        "imgsz": DEFAULT_IMGSZ,
        "conf": DEFAULT_CONF,
        "tracker": DEFAULT_TRACKER,
        "has_cv2": _has("cv2"),
        "has_torch": _has("torch"),
        "has_ultralytics": _has("ultralytics"),
    }
