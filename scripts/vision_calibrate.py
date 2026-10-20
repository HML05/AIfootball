"""点 4 个点，把画面标定到 105×68 米的球场坐标。

用法（两种）：

    # 1) 交互点选：弹出画面，按提示顺序点 4 个角球点/罚球点
    .venv-vision\\Scripts\\python.exe scripts\\vision_calibrate.py ^
        --video data\\vision\\videos\\v2.mp4 --frame 300 ^
        --anchors corner_tl,corner_tr,corner_br,corner_bl ^
        --out data\\vision\\calib\\v2.json

    # 2) 直接给坐标（知道像素点时最省事）：--points "u,v;u,v;u,v;u,v"
    ... --points "12,540;1908,520;1912,1032;8,1044" --anchors corner_tl,corner_tr,corner_br,corner_bl

标定产物是一个 JSON（单应矩阵 + 4 组对应点 + 重投影误差），后面
`src/vision/pitch.py` 用它把每帧的球员位置换算成米，再算跑动距离/速度/雷达图坐标。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.vision import pitch  # noqa: E402


def _load_cv2():
    try:
        import cv2  # noqa: F401
    except ImportError as exc:  # pragma: no cover - 环境问题
        raise SystemExit(
            "[错误] 没有 cv2。标定要用它读数与画图：\n"
            "  .venv-vision\\Scripts\\python.exe -m pip install opencv-python"
        ) from exc
    import cv2 as _cv2

    return _cv2


def _grab_frame(video: Path, index: int):
    cv2 = _load_cv2()
    cap = cv2.VideoCapture(str(video))
    if not cap.isOpened():
        raise SystemExit(f"[错误] 打不开视频：{video}")
    if index > 0:
        cap.set(cv2.CAP_PROP_POS_FRAMES, index)
    ok, frame = cap.read()
    cap.release()
    if not ok or frame is None:
        raise SystemExit(f"[错误] 读不到第 {index} 帧")
    return frame


def _parse_points(text: str) -> list[tuple[float, float]]:
    pts: list[tuple[float, float]] = []
    for chunk in text.replace("|", ";").split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        parts = [p for p in chunk.replace(" ", ",").split(",") if p]
        if len(parts) != 2:
            raise SystemExit(f"[错误] --points 的每一组要两个数（u,v），收到：{chunk}")
        pts.append((float(parts[0]), float(parts[1])))
    return pts


def _parse_anchors(text: str) -> list[tuple[float, float]]:
    names = [n.strip() for n in text.split(",") if n.strip()]
    out: list[tuple[float, float]] = []
    for n in names:
        if n not in pitch.ANCHORS:
            raise SystemExit(f"[错误] 不认识的锚点 {n}，可选：{', '.join(pitch.ANCHORS)}")
        out.append(pitch.ANCHORS[n])
    return out


def _click_points(frame, names: list[str]) -> list[tuple[float, float]]:
    """弹窗点选，Esc 取消。"""
    cv2 = _load_cv2()
    clicked: list[tuple[float, float]] = []
    win = "calibrate: click 4 points (Esc to cancel)"

    def on_mouse(event, x, y, flags, param):  # noqa: ANN001
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < len(names):
            clicked.append((float(x), float(y)))

    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    cv2.setMouseCallback(win, on_mouse)
    while True:
        canvas = frame.copy()
        for i, (x, y) in enumerate(clicked):
            cv2.circle(canvas, (int(x), int(y)), 8, (0, 0, 255), -1)
            cv2.putText(canvas, f"{i + 1} {names[i]}", (int(x) + 12, int(y) - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        todo = names[len(clicked)] if len(clicked) < len(names) else "done"
        cv2.putText(canvas, f"next: {todo}", (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            cv2.destroyAllWindows()
            raise SystemExit("[取消] 已退出标定")
        if len(clicked) >= len(names):
            cv2.destroyAllWindows()
            return clicked


def _reproject_error(h: np.ndarray, pairs) -> tuple[float, list[float]]:
    """每个标定点投回去，看差多少米——标定质量的自检。"""
    errs = []
    for (u, v), (x, y) in pairs:
        px, py = pitch.pixel_to_pitch(h, (u, v))
        errs.append(((px - x) ** 2 + (py - y) ** 2) ** 0.5)
    return max(errs), errs


def main() -> int:
    ap = argparse.ArgumentParser(description="把转播画面标定到 105×68 米球场坐标")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", default="", help="视频文件（配合 --frame 选一帧来点）")
    src.add_argument("--image", default="", help="直接给一张截图")
    ap.add_argument("--frame", type=int, default=0, help="--video 时用第几帧（默认 0）")
    ap.add_argument("--anchors", default="corner_tl,corner_tr,corner_br,corner_bl",
                    help=f"按点击顺序给出锚点名，可选：{','.join(pitch.ANCHORS)}")
    ap.add_argument("--points", default="", help="不给就弹窗点选；给了就直接用：'u,v;u,v;u,v;u,v'")
    ap.add_argument("--out", default="", help="标定 JSON 输出路径（默认 data/vision/calib/<名字>.json）")
    args = ap.parse_args()

    cv2 = _load_cv2()
    anchors = _parse_anchors(args.anchors)
    if len(anchors) < 4:
        raise SystemExit("[错误] 至少要 4 个锚点（3 个只能解仿射，远端会偏）")

    if args.image:
        img_path = Path(args.image)
        frame = cv2.imread(str(img_path))
        if frame is None:
            raise SystemExit(f"[错误] 读不到图片：{img_path}")
        stem = img_path.stem
    else:
        frame = _grab_frame(Path(args.video), max(args.frame, 0))
        stem = Path(args.video).stem

    px_points = _parse_points(args.points) if args.points else _click_points(frame, args.anchors.split(","))
    if len(px_points) < len(anchors):
        raise SystemExit(f"[错误] 给了 {len(px_points)} 个像素点，但有 {len(anchors)} 个锚点")

    pairs = list(zip(px_points[: len(anchors)], anchors))
    cal = pitch.build_calibration(pairs, note=f"{stem} @ frame {args.frame}")
    worst, errs = _reproject_error(cal.homography, pairs)

    out = Path(args.out) if args.out else ROOT / "data" / "vision" / "calib" / f"{stem}.json"
    pitch.save_calibration(cal, out)

    # 顺手存一张标注了锚点的预览图，方便回头核对
    preview = frame.copy()
    for i, ((u, v), (x, y)) in enumerate(pairs, 1):
        cv2.circle(preview, (int(u), int(v)), 9, (0, 255, 0), 2)
        cv2.putText(preview, f"{i}:{x:.0f},{y:.0f}m", (int(u) + 14, int(v) - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    prev_path = out.with_suffix(".preview.jpg")
    cv2.imwrite(str(prev_path), preview)

    print(f"[ok] 标定写入 {out}")
    print(f"     重投影误差：最大 {worst:.3f} 米 / 各点 {', '.join(f'{e:.3f}' for e in errs)}")
    if worst > 0.5:
        print("     [!] 误差偏大：检查这 4 个点是否真的对得上标准场地的锚点（角球点/罚球点）")
    print(f"     预览图 {prev_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
