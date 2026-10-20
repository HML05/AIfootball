"""阶段 1「可行性冒烟」：跑一段视频，把能不能用变成一张可复核的表。

输出三样东西（都在 data/vision/out/ 下）：
  <名字>_tracks.json.gz   逐帧框 + 跟踪 ID（后续画框、入库、算指标都靠它）
  <名字>_summary.json     统计汇总（人数/球检出率/ID 碎裂/框尺寸/速度）
  <名字>_overlay.mp4      带框图（加 --overlay）

用法：
    .venv-vision\\Scripts\\python.exe scripts\\vision_smoke.py --src data\\vision\\videos\\clip.mp4 --overlay
    # 手上还没有真实比赛片段时，先验证管线是否通：
    .venv-vision\\Scripts\\python.exe scripts\\vision_smoke.py --demo
"""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from src.vision import config, io, metrics  # noqa: E402

DEMO_NAME = "_demo.mp4"


def make_demo_clip(path: Path, seconds: int = 6, fps: int = 25) -> Path:
    """造一段合成片段（三个方块 + 一个小球在动）。

    它不是足球画面，YOLO 也检不出任何目标——用途只有一个：
    证明「解码 → 推理 → 跟踪 → 统计 → 写 JSON/视频」这条链路是通的。
    """
    cv2 = io._cv2()
    path.parent.mkdir(parents=True, exist_ok=True)
    width, height = 1280, 720
    writer = cv2.VideoWriter(str(path), cv2.VideoWriter_fourcc(*"mp4v"), fps, (width, height))
    if not writer.isOpened():
        raise RuntimeError(f"写不了视频：{path}（编码器不可用？）")
    for i in range(seconds * fps):
        frame = 30 + (i // 3) % 40
        img = cv2.UMat(height, width, cv2.CV_8UC3).get()
        img[:] = (frame, frame, frame)
        cv2.rectangle(img, (0, height // 2), (width, height), (40, 90, 40), -1)
        for k in range(3):
            x = int(150 + k * 300 + 120 * ((i / fps) % 2))
            y = int(height // 2 + (k - 1) * 40)
            cv2.rectangle(img, (x, y), (x + 46, y + 110), (30, 30, 230 - k * 40), -1)
        bx = int(200 + 60 * ((i / fps) % 10))
        cv2.circle(img, (bx, height // 2 + 60), 5, (255, 255, 255), -1)
        writer.write(img)
    writer.release()
    return path


def run(args: argparse.Namespace) -> int:
    from src.vision.detector import Detector

    config.ensure_dirs()
    info = config.describe()
    print("配置：", {k: info[k] for k in ("model", "imgsz", "conf", "tracker")})
    print(f"目录：{info['VISION_DIR']}")

    given = args.src or args.src_opt
    src = Path(given) if given else config.VIDEO_DIR / DEMO_NAME
    if args.demo and not src.exists():
        print("没有真实片段，先造一段合成片段验证管线 …")
        make_demo_clip(src)
    if not src.exists():
        print(f"[错误] 找不到视频 {src}")
        print("  真实片段放到 data/vision/videos/ 下，然后 --src 指过去；或用 --demo。")
        return 2

    # opencv 在 Windows 上打不开含中文的路径：先换成 ASCII 等价路径再往下走
    real_src = src
    src = io.ascii_video_path(src, config.OUT_DIR / "_ascii")
    if src != real_src:
        print(f"源文件名含非 ASCII，已改用等价路径：{src}")

    try:
        import torch
        cuda = torch.cuda.is_available()
        print(f"torch {torch.__version__} / cuda {cuda}" + (f" / {torch.cuda.get_device_name(0)}" if cuda else ""))
    except ImportError:
        pass

    meta = io.probe_video(src)
    print(f"视频：{src.name}  {meta['width']}x{meta['height']}  {meta['fps']}fps  共 {meta['frames']} 帧")

    det = Detector(
        model=args.model,
        imgsz=args.imgsz,
        conf=args.conf,
        classes=[int(c) for c in args.classes.split(",") if c.strip()],
        tracker=args.tracker,
        device=args.device,
    )

    tracks: list[dict] = []
    started = time.perf_counter()
    for item in det.track(src):
        tracks.append(item)
        if args.max_frames and len(tracks) >= args.max_frames:
            break
        if len(tracks) % 100 == 0:
            print(f"  处理中 {len(tracks)} 帧 …", end="\r")
    elapsed = time.perf_counter() - started
    print(f"  处理完成 {len(tracks)} 帧，用时 {elapsed:.1f}s" + " " * 20)

    summary = metrics.summarize(tracks, meta, elapsed=elapsed)
    stem = Path(args.prefix) if args.prefix else Path(io.safe_stem(src.name))
    tracks_path = io.dump_json(config.OUT_DIR / f"{stem.name}_tracks.json.gz", tracks)
    summary_path = io.dump_json(config.OUT_DIR / f"{stem.name}_summary.json", summary)

    p = summary["person"]
    t = summary["tracking"]
    b = summary["ball"]
    print("\n—— 结果 ——")
    print(f"人数      平均 {p['per_frame_mean']} 人/帧，单帧最多 {p['per_frame_max']}，有人的帧 {p['frames_with_person_pct']}%")
    print(f"跟踪      唯一 ID {t['unique_ids']}，碎裂比 {t['fragmentation']}，ID 中位存活 {t['id_lifetime_median']} 帧")
    print(f"球        检出覆盖率 {b['frames_with_ball_pct']}%（{b['frames_with_ball']}/{summary['frames_processed']} 帧）")
    print(f"框尺寸    中位高 {summary['box_height_px']['median']} px，分档 {summary['box_height_px']['buckets_pct']}")
    if "speed" in summary:
        print(f"速度      {summary['speed']['fps_processed']} 帧/秒（纯推理，不含解码预热）")

    print("\n—— 阶段 1 判定（经验阈值，仅供参考）——")
    rows = metrics.verdict(summary)
    for mark, text in rows:
        print(f"  [{mark}] {text}")
    if summary["frames_processed"] and p["boxes_total"] == 0:
        print("\n  注意：一帧都没检出目标。要么素材里没有人（合成片段就是这样），")
        print("        要么模型/类别参数不对——COCO 预训练只认 person(0) 与 sports ball(32)。")

    print(f"\n轨迹：{tracks_path}\n汇总：{summary_path}")
    if args.overlay:
        overlay = io.write_overlay(
            src, tracks, config.OUT_DIR / f"{stem.name}_overlay.mp4", fps=meta["fps"], limit=len(tracks)
        )
        print(f"带框视频：{overlay}")

    if args.strict and any(mark == "不行" for mark, _ in rows):
        return 1
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="YOLOv8 检测跟踪可行性冒烟")
    ap.add_argument("src", nargs="?", default="", help="视频路径（也可以写成 --src）")
    ap.add_argument("--src", dest="src_opt", default="", help="视频路径（默认 data/vision/videos）")
    ap.add_argument("--demo", action="store_true", help="没有真实片段时造一段合成片段验证管线")
    ap.add_argument("--model", default=config.DEFAULT_MODEL, help="权重（.pt 不存在会自动下载）")
    ap.add_argument("--imgsz", type=int, default=config.DEFAULT_IMGSZ)
    ap.add_argument("--conf", type=float, default=config.DEFAULT_CONF)
    ap.add_argument("--classes", default="0,32", help="COCO 类别：0=person 32=sports ball")
    ap.add_argument("--tracker", default=config.DEFAULT_TRACKER, help="bytetrack.yaml / botsort.yaml")
    ap.add_argument("--device", default=None, help='"cpu" 可强制 CPU')
    ap.add_argument("--max-frames", type=int, default=0, help="只跑前 N 帧（调试用）")
    ap.add_argument("--overlay", action="store_true", help="另外输出带框视频")
    ap.add_argument("--prefix", default="", help="输出文件名前缀（默认用视频名）")
    ap.add_argument("--strict", action="store_true", help="判定里出现「不行」就返回退出码 1")
    return run(ap.parse_args())


if __name__ == "__main__":
    raise SystemExit(main())
