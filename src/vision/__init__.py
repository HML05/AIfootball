"""YOLOv8 视频检测跟踪模块（视觉侧）。

隔离原则
--------
本包里的模块只依赖 numpy / opencv / ultralytics，**不** import 主应用的
FastAPI、sqlalchemy 和 config.settings，所以可以在只装了 vision 依赖的
.venv-vision 里单独跑；主应用所在的系统 Python 即使没装 torch，也照样能
import 本包（子模块用到了才真正加载重依赖）。

`__init__` 故意不 import 子模块：避免 "import src.vision" 就顺带拉起 cv2。
"""
from __future__ import annotations

__all__ = ["config", "detector", "metrics", "io"]
__version__ = "0.1.0"
