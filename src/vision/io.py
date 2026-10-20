"""视频读写的公共小工具：探测元信息、轨迹 JSON 落盘、带框图渲染。

opencv 在这里也是「用到才 import」，保证没有视觉依赖的环境能 import 本模块。
"""
from __future__ import annotations

import gzip
import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any, Iterator

from . import config

# 每个类别的画框颜色（BGR），不够就循环取
_COLORS = [
    (0, 200, 0),      # 绿
    (0, 140, 255),    # 橙
    (255, 120, 0),    # 蓝
    (180, 0, 255),    # 紫
    (0, 220, 220),    # 黄
]


def _cv2():
    import cv2

    return cv2


def probe_video(path: str | Path) -> dict:
    """读视频的帧率/尺寸/总帧数（不依赖 ffmpeg，走 opencv 自带解码）。"""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"打不开视频：{path}")
    try:
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0.0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
    finally:
        cap.release()
    return {
        "path": str(path),
        "fps": round(fps, 3),
        "frames": frames,
        "width": width,
        "height": height,
        "duration": round(frames / fps, 2) if fps else None,
    }


def safe_stem(name: str | Path) -> str:
    """把任意文件名换成纯 ASCII 的 stem，给「写出去的文件」用。

    为什么需要：Windows 上 opencv 的 VideoWriter/imwrite 走的是窄字符 API，
    路径里有中文（`比赛_上半场.mp4`）会直接打不开写入器，报一个看不出原因的错误。
    ASCII 名字原样保留；含非 ASCII 字符时退化成 `md5 前 8 位`，保证可重复、不撞车。
    """
    stem = Path(name).stem or "video"
    if stem.isascii():
        return stem
    digest = hashlib.md5(stem.encode("utf-8")).hexdigest()[:8]
    return f"clip_{digest}"


def ascii_video_path(path: str | Path, cache_dir: str | Path | None = None) -> Path:
    """返回一个 cv2 能打开的等价路径（原路径含非 ASCII 时做硬链接/复制）。

    读取侧同样有中文路径问题，所以进来的视频先换成一个 ASCII 路径再喂给
    cv2.VideoCapture；硬链接不占额外空间，跨盘才退化成复制。
    """
    path = Path(path)
    if str(path).isascii():
        return path
    cache = Path(cache_dir) if cache_dir else Path(config.OUT_DIR) / "_ascii"
    cache.mkdir(parents=True, exist_ok=True)
    target = cache / f"{safe_stem(path.name)}{path.suffix.lower()}"
    if not target.exists():
        try:
            os.link(path, target)
        except OSError:
            shutil.copy2(path, target)
    return target


def dump_json(path: str | Path, obj: Any) -> Path:
    """落 JSON；后缀给 .gz 就顺便压缩（轨迹文件动辄几十 MB）。"""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    text = json.dumps(obj, ensure_ascii=False, separators=(",", ":"))
    if path.suffix == ".gz":
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            fh.write(text)
    else:
        path.write_text(text, encoding="utf-8")
    return path


def load_json(path: str | Path) -> Any:
    path = Path(path)
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            return json.load(fh)
    return json.loads(path.read_text(encoding="utf-8"))


def draw_boxes(image: Any, boxes: list[dict], thickness: int = 2) -> Any:
    """在 BGR 图上画框 + 「id 类别 置信度」标签，返回同一个 image（原地改）。"""
    cv2 = _cv2()
    for item in boxes:
        x1, y1, x2, y2 = (int(round(v)) for v in item["xyxy"])
        color = _COLORS[int(item.get("cls", 0)) % len(_COLORS)]
        cv2.rectangle(image, (x1, y1), (x2, y2), color, thickness)

        tag = str(item.get("name", item.get("cls", "")))
        if item.get("id") is not None:
            tag = f"#{item['id']} {tag}"
        tag = f"{tag} {item.get('conf', 0):.2f}"
        (tw, th), base = cv2.getTextSize(tag, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)
        top = max(y1 - th - base - 4, 0)
        cv2.rectangle(image, (x1, top), (x1 + tw + 6, top + th + base + 4), color, -1)
        cv2.putText(
            image, tag, (x1 + 3, top + th + 2),
            cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1, cv2.LINE_AA,
        )
    return image


def write_overlay(
    source: str | Path,
    tracks: list[dict],
    out_path: str | Path,
    fps: float | None = None,
    limit: int | None = None,
) -> Path:
    """把 tracks 叠回原视频，写成新的 mp4（演示用；不做逐帧对齐校正）。"""
    cv2 = _cv2()
    source, out_path = Path(source), Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    cap = cv2.VideoCapture(str(source))
    if not cap.isOpened():
        raise FileNotFoundError(f"打不开视频：{source}")
    try:
        real_fps = float(fps or cap.get(cv2.CAP_PROP_FPS) or 25.0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        writer = cv2.VideoWriter(
            str(out_path), cv2.VideoWriter_fourcc(*"mp4v"), real_fps, (width, height)
        )
        by_frame = {int(t["frame"]): t.get("boxes", []) for t in tracks}
        # 只写「有轨迹覆盖的那一段」；调用方再给 limit 就取更小值
        last = (max(by_frame) + 1) if by_frame else None
        stop = last if limit is None else (min(limit, last) if last else limit)
        idx = 0
        while True:
            if stop is not None and idx >= stop:
                break
            ok, frame = cap.read()
            if not ok:
                break
            draw_boxes(frame, by_frame.get(idx, []))
            writer.write(frame)
            idx += 1
        writer.release()
    finally:
        cap.release()
    return out_path


def iter_frames(path: str | Path, step: int = 1, start: int = 0, end: int | None = None) -> Iterator[tuple[int, Any]]:
    """按帧序读取 (原始帧号, frame)，供抽帧脚本使用。"""
    cv2 = _cv2()
    cap = cv2.VideoCapture(str(path))
    if not cap.isOpened():
        raise FileNotFoundError(f"打不开视频：{path}")
    try:
        idx = 0
        while True:
            ok, frame = cap.read()
            if not ok:
                break
            if idx >= start and (end is None or idx <= end) and (idx - start) % step == 0:
                yield idx, frame
            idx += 1
    finally:
        cap.release()
