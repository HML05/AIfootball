"""YOLOv8 检测 + 跟踪的薄封装。

为什么包一层
------------
1. ultralytics 的调用参数在不同小版本之间会漂（conf/iou/imgsz/persist/stream），
   集中在这里改一处，脚本和后续的接口层都不用动；
2. ultralytics 在真正用到时才 import——没装视觉依赖的环境（CI、线上部署、
   主应用的系统 Python）照样能 import 本模块，不会因为缺 torch 就崩；
3. 输出统一成「每帧一个纯 Python dict」，方便落 JSON、入库、画框，
   不让 torch.Tensor 泄漏到脚本层。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterator, Sequence

from . import config


class VisionDependencyError(RuntimeError):
    """缺 ultralytics/torch 时给出可直接照抄的修复命令，而不是干巴巴的 ImportError。"""


def _import_yolo():
    try:
        from ultralytics import YOLO
    except ImportError as exc:  # pragma: no cover - 取决于运行环境
        raise VisionDependencyError(
            "当前解释器里没有 ultralytics / torch。请用视觉模块的独立环境运行：\n"
            "  powershell -ExecutionPolicy Bypass -File scripts\\vision_setup.ps1\n"
            "或手动：\n"
            "  .venv-vision\\Scripts\\python.exe -m pip install -r requirements-vision.txt\n"
            f"（原始错误：{exc}）"
        ) from exc
    return YOLO


def _frame_dict(idx: int, result: Any) -> dict:
    """把 ultralytics 的单帧 Result 转成纯 dict。"""
    boxes = getattr(result, "boxes", None)
    frame = {"frame": idx, "boxes": []}
    if boxes is None or len(boxes) == 0:
        return frame

    names = getattr(result, "names", None) or {}
    xyxy = boxes.xyxy.tolist()
    confs = boxes.conf.tolist()
    clss = boxes.cls.tolist()
    raw_ids = getattr(boxes, "id", None)
    ids = raw_ids.tolist() if raw_ids is not None else [None] * len(xyxy)

    for box, conf, cls_id, track_id in zip(xyxy, confs, clss, ids):
        ci = int(cls_id)
        frame["boxes"].append(
            {
                "id": None if track_id is None else int(track_id),
                "cls": ci,
                "name": str(names.get(ci, ci)) if isinstance(names, dict) else str(ci),
                "conf": round(float(conf), 4),
                "xyxy": [round(float(v), 2) for v in box],
            }
        )
    return frame


@dataclass
class Detector:
    """一个模型实例 + 一套默认推理参数。"""

    model: str = config.DEFAULT_MODEL
    imgsz: int = config.DEFAULT_IMGSZ
    conf: float = config.DEFAULT_CONF
    iou: float = 0.5
    classes: Sequence[int] | None = None  # None=全部；[0]=只人；[0,32]=人+球
    tracker: str = config.DEFAULT_TRACKER
    device: str | None = None  # None=自动；"cpu" 强制 CPU
    verbose: bool = False
    _model: Any = field(default=None, init=False, repr=False)

    # ---- 模型加载 -------------------------------------------------------
    def load(self) -> Any:
        """首次调用时加载权重。

        权重查找顺序：字面路径 → models/vision/<同名文件> → 交给 ultralytics 自动下载（需联网）。
        中间那一档是为了让 'yolov8s.pt' 这种短名能命中我们放好的本地权重，
        又不至于把 .pt 下载到仓库根目录。
        """
        if self._model is None:
            YOLO = _import_yolo()
            path = Path(self.model)
            local = Path(config.WEIGHT_DIR) / path.name
            self._model = YOLO(str(path if path.exists() or not local.exists() else local))
        return self._model

    def _opts(self) -> dict:
        opts: dict[str, Any] = {
            "imgsz": self.imgsz,
            "conf": self.conf,
            "iou": self.iou,
            "verbose": self.verbose,
        }
        if self.classes is not None:
            opts["classes"] = list(self.classes)
        if self.device:
            opts["device"] = self.device
        return opts

    # ---- 两条主要用法 ---------------------------------------------------
    def predict(self, source: str | Path) -> list[dict]:
        """单帧/多帧静态图片检测（无跟踪 ID，预标注用这个）。"""
        model = self.load()
        results = model.predict(source=str(source), **self._opts())
        return [_frame_dict(i, r) for i, r in enumerate(results)]

    def track(self, source: str | Path) -> Iterator[dict]:
        """视频/图片序列 —— 检测 + 跟踪，逐帧 yield（内存不会炸）。"""
        model = self.load()
        opts = self._opts()
        opts.update({"tracker": self.tracker, "persist": True, "stream": True})
        results = model.track(source=str(source), **opts)
        for idx, result in enumerate(results):
            yield _frame_dict(idx, result)
