"""从视频里按固定间隔抽帧 —— 标注、微调、冒烟都用它产出素材。

为什么要保留原帧号：抽帧是按间隔跳的，标注和回放时必须能把「第 7 张图」
映射回「第 105 帧」，否则轨迹、时间戳会整体错位。frames_index.json 就是这张表。

用法（在仓库根目录，用视觉模块的独立环境）：
    .venv-vision\\Scripts\\python.exe scripts\\vision_extract_frames.py --src data\\vision\\videos\\clip.mp4
    ... --src data\\vision\\videos --step 15 --max-frames 300
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:  # Windows 控制台默认 GBK，视频名里带中文会直接崩
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from src.vision import config, io  # noqa: E402

VIDEO_SUFFIXES = {".mp4", ".avi", ".mov", ".mkv", ".flv", ".m4v", ".webm"}


def collect_sources(src: Path) -> list[Path]:
    if src.is_dir():
        return sorted(p for p in src.iterdir() if p.suffix.lower() in VIDEO_SUFFIXES)
    return [src]


def extract_one(
    video: Path,
    out_dir: Path,
    step: int,
    start_sec: float,
    end_sec: float | None,
    max_frames: int,
    width: int,
    quality: int,
) -> dict:
    cv2 = io._cv2()
    meta = io.probe_video(video)
    fps = meta["fps"] or 25.0
    start = int(round(start_sec * fps))
    end = None if end_sec is None else int(round(end_sec * fps))

    out_dir.mkdir(parents=True, exist_ok=True)
    saved: list[dict] = []
    for frame_idx, frame in io.iter_frames(video, step=step, start=start, end=end):
        if max_frames and len(saved) >= max_frames:
            break
        if width and frame.shape[1] > width:
            scale = width / frame.shape[1]
            frame = cv2.resize(
                frame, (width, int(round(frame.shape[0] * scale))), interpolation=cv2.INTER_AREA
            )
        name = f"{video.stem}_{frame_idx:06d}.jpg"
        target = out_dir / name
        cv2.imwrite(str(target), frame, [int(cv2.IMWRITE_JPEG_QUALITY), quality])
        saved.append({"file": name, "frame": frame_idx, "t": round(frame_idx / fps, 3)})

    index = {
        "video": str(video),
        "fps": fps,
        "step": step,
        "start_frame": start,
        "end_frame": end,
        "extracted": len(saved),
        "frames": saved,
    }
    io.dump_json(out_dir / "frames_index.json", index)
    return index


def main() -> int:
    ap = argparse.ArgumentParser(description="按固定间隔从视频抽帧")
    ap.add_argument("--src", required=True, help="视频文件，或装着视频的目录")
    ap.add_argument("--out", default="", help="输出目录（默认 data/vision/frames/<视频名>）")
    ap.add_argument("--step", type=int, default=15, help="每 N 帧取一张（25fps 下 15 ≈ 0.6 秒）")
    ap.add_argument("--start-sec", type=float, default=0.0)
    ap.add_argument("--end-sec", type=float, default=None)
    ap.add_argument("--max-frames", type=int, default=0, help="每个视频最多抽几张（0=不限）")
    ap.add_argument("--width", type=int, default=0, help="可选：缩放到该宽度，0=原尺寸")
    ap.add_argument("--quality", type=int, default=92, help="JPEG 质量")
    args = ap.parse_args()

    config.ensure_dirs()
    src = Path(args.src)
    if not src.exists():
        print(f"[错误] 找不到 {src}")
        return 2

    total = 0
    for video in collect_sources(src):
        out_dir = Path(args.out) if args.out else config.FRAME_DIR / video.stem
        if len(collect_sources(src)) > 1 and args.out:
            out_dir = Path(args.out) / video.stem
        info = extract_one(
            video, out_dir, args.step, args.start_sec, args.end_sec,
            args.max_frames, args.width, args.quality,
        )
        total += info["extracted"]
        print(f"[抽帧] {video.name}: {info['extracted']} 张 → {out_dir}")
        if info["extracted"] == 0:
            print("       提示：step 太大或 --start-sec 超出视频长度；先看上面的 fps/总帧数")

    print(f"\n完成：共 {total} 张，索引写在各自目录的 frames_index.json")
    print("下一步：python scripts/vision_prelabel.py --src <抽帧目录>")
    return 0 if total else 1


if __name__ == "__main__":
    raise SystemExit(main())
