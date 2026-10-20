"""点 4 个点，把画面标定到 105×68 米的球场坐标。

用法（两种）：

    # 1) 交互点选：弹出画面，按提示顺序点 4 个锚点（第 5 个及以后只做校验）
    .venv-vision\\Scripts\\python.exe scripts\\vision_calibrate.py ^
        --video data\\vision\\videos\\v2.mp4 --frame 0 ^
        --anchors center,halfway_top,halfway_bottom,pa_right_top ^
        --out data\\vision\\calib\\v2.json

    # 2) 直接给坐标（知道像素点时最省事）：--points "u,v;u,v;u,v;u,v"
    ... --points "470,357;425,113;500,853;1445,205"

标定产物是一个 JSON（单应矩阵 + 4 组对应点），后面 `src/vision/pitch.py`
用它把每帧的球员位置换算成米，再算跑动距离/速度/雷达图坐标。

**为什么 4 个点的「重投影误差」一定是 0**：4 组对应点 = 8 个方程，
单应矩阵的自由度也是 8，方程组恰好可解，所以内点误差恒为 0——它只能说明
「算出来了」，不能说明「算对了」。真正的质量判据有两条，本脚本都会检查：

1. **留出点误差**：多给 1~2 个锚点（第 5、6 个），它们不参与拟合，只用来验收。
   留出点误差才是可信的数字。
2. **栅格叠图**：把 5 米一格的球场网格按标定结果画回画面（`<out>.grid.jpg`），
   网格线该和真实白线重合。肉眼一看就知道对不对。
"""
from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

from src.vision import pitch  # noqa: E402

# 4 个点至少要把画面铺开这么多，否则单应矩阵条件数极差（实测踩过：4 次点击挤在
# 画面中央 200 像素内，解出来的「球场」只有几米宽，距离全是错的）
MIN_SPREAD = 0.25
# 同一画面里「每像素多少米」的最大/最小比值上限。战术机位约 2~4 倍，
# 超过 8 倍基本说明点配错了（把禁区角当成了角旗之类）
MAX_SCALE_RATIO = 8.0


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
    win = "calibrate: click the anchors in order (Esc to cancel)"
    total = len(names)

    def on_mouse(event, x, y, flags, param):  # noqa: ANN001
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < total:
            clicked.append((float(x), float(y)))

    h, w = frame.shape[:2]
    # 有些机器上 OpenCV 的窗口会开在别的窗口后面、或跑到屏幕外，
    # 看起来就像「双击了没反应」。所以显式给个位置与大小，并置顶。
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    scale = min(1.0, 1600.0 / max(w, 1))
    cv2.resizeWindow(win, int(w * scale), int(h * scale))
    cv2.moveWindow(win, 60, 40)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:  # 老版本/无此属性时忽略
        pass
    cv2.setMouseCallback(win, on_mouse)
    print("[i] 点选窗口已打开（标题 calibrate…）。没看到就把其他窗口最小化，或看任务栏。")
    print(f"[i] 按 1→{total} 的顺序点，Esc 取消。")
    cv2.setMouseCallback(win, on_mouse)
    while True:
        canvas = frame.copy()
        for i, (x, y) in enumerate(clicked):
            cv2.circle(canvas, (int(x), int(y)), 8, (0, 0, 255), -1)
            cv2.putText(canvas, f"{i + 1} {names[i]}", (int(x) + 12, int(y) - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        todo = names[len(clicked)] if len(clicked) < total else "done"
        cv2.putText(canvas, f"next ({len(clicked) + 1}/{total}): {todo}",
                    (20, 40), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 255), 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(30) & 0xFF
        if key == 27:
            cv2.destroyAllWindows()
            raise SystemExit("[取消] 已退出标定")
        if len(clicked) >= total:
            cv2.destroyAllWindows()
            return clicked


def _reproject_error(h: np.ndarray, pairs) -> tuple[float, list[float]]:
    """每个标定点投回去，看差多少米。4 点拟合时恒为 0，只能当「算出来了」的证据。"""
    errs = []
    for (u, v), (x, y) in pairs:
        px, py = pitch.pixel_to_pitch(h, (u, v))
        errs.append(math.hypot(px - x, py - y))
    return max(errs), errs


def _spread(points: list[tuple[float, float]], shape) -> float:
    xs = [p[0] for p in points]
    ys = [p[1] for p in points]
    diag = math.hypot(max(xs) - min(xs), max(ys) - min(ys))
    return diag / math.hypot(shape[1], shape[0])


def _local_scale(h: np.ndarray, point: tuple[float, float], d: float = 1.0) -> float:
    """某点附近「每像素多少米」，用来判断整幅画面是否被拉得离谱。"""
    x0, y0 = pitch.pixel_to_pitch(h, point)
    x1, y1 = pitch.pixel_to_pitch(h, (point[0] + d, point[1]))
    return math.hypot(x1 - x0, y1 - y0) / d


def _pitch_to_pixel(h_inv: np.ndarray, x: float, y: float) -> tuple[float, float]:
    p = h_inv @ np.array([x, y, 1.0])
    if abs(p[2]) < 1e-12:
        return (float("nan"), float("nan"))
    return (p[0] / p[2], p[1] / p[2])


def _draw_grid(frame, h: np.ndarray, step: float = 5.0):
    """把球场网格按标定结果画回画面：线该压在真实白线上。"""
    cv2 = _load_cv2()
    h_inv = np.linalg.inv(h)
    out = frame.copy()
    h_img, w_img = out.shape[:2]

    def seg(p, q):
        u1, v1 = _pitch_to_pixel(h_inv, *p)
        u2, v2 = _pitch_to_pixel(h_inv, *q)
        if any(math.isnan(t) for t in (u1, v1, u2, v2)):
            return
        if not (-2000 < u1 < w_img + 2000 and -2000 < u2 < w_img + 2000):
            return
        cv2.line(out, (int(u1), int(v1)), (int(u2), int(v2)), (0, 200, 255), 1, cv2.LINE_AA)

    x = 0.0
    while x <= pitch.PITCH_LENGTH + 1e-6:
        seg((x, 0), (x, pitch.PITCH_WIDTH))
        x += step
    y = 0.0
    while y <= pitch.PITCH_WIDTH + 1e-6:
        seg((0, y), (pitch.PITCH_LENGTH, y))
        y += step

    # 外框加粗，方便一眼看出边界对不对
    box = [(0, 0), (pitch.PITCH_LENGTH, 0), (pitch.PITCH_LENGTH, pitch.PITCH_WIDTH), (0, pitch.PITCH_WIDTH), (0, 0)]
    for a, b in zip(box, box[1:]):
        u1, v1 = _pitch_to_pixel(h_inv, *a)
        u2, v2 = _pitch_to_pixel(h_inv, *b)
        if not any(math.isnan(t) for t in (u1, v1, u2, v2)):
            cv2.line(out, (int(u1), int(v1)), (int(u2), int(v2)), (60, 60, 255), 2, cv2.LINE_AA)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="把转播画面标定到 105×68 米球场坐标")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--video", default="", help="视频文件（配合 --frame 选一帧来点）")
    src.add_argument("--image", default="", help="直接给一张截图")
    ap.add_argument("--frame", type=int, default=0, help="--video 时用第几帧（默认 0）")
    ap.add_argument("--anchors", default="corner_tl,corner_tr,corner_br,corner_bl",
                    help=f"按点击顺序给出锚点名（第 5 个起只做校验），可选：{','.join(pitch.ANCHORS)}")
    ap.add_argument("--points", default="", help="不给就弹窗点选；给了就直接用：'u,v;u,v;u,v;u,v'")
    ap.add_argument("--out", default="", help="标定 JSON 输出路径（默认 data/vision/calib/<名字>.json）")
    ap.add_argument("--no-grid", action="store_true", help="不生成栅格叠图（默认生成）")
    args = ap.parse_args()

    cv2 = _load_cv2()
    names = [n.strip() for n in args.anchors.split(",") if n.strip()]
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

    px_points = _parse_points(args.points) if args.points else _click_points(frame, names)
    if len(px_points) < 4:
        raise SystemExit(f"[错误] 只给了 {len(px_points)} 个像素点，至少要 4 个")
    n_fit = min(4, len(px_points), len(anchors))
    fit_px = px_points[:n_fit]
    fit_anchor = anchors[:n_fit]
    holdout = list(zip(px_points[n_fit:], anchors[n_fit:]))

    cal = pitch.build_calibration(list(zip(fit_px, fit_anchor)), note=f"{stem} @ frame {args.frame}")
    worst, errs = _reproject_error(cal.homography, list(zip(fit_px, fit_anchor)))

    out = Path(args.out) if args.out else ROOT / "data" / "vision" / "calib" / f"{stem}.json"
    pitch.save_calibration(cal, out)

    spread = _spread(fit_px, frame.shape)
    scales = [_local_scale(cal.homography, p) for p in fit_px]
    scale_ratio = max(scales) / max(min(scales), 1e-9)

    print(f"[ok] 标定写入 {out}")
    print(f"     内点误差 {worst:.3f} 米（4 点拟合恒为 0，不能当质量证明）")
    print(f"     4 点铺开程度 {spread * 100:.0f}% 画面对角线（建议 >{MIN_SPREAD * 100:.0f}%）")
    print(f"     每像素米数 {min(scales):.4f} ~ {max(scales):.4f}（比值 {scale_ratio:.1f}×，建议 <{MAX_SCALE_RATIO:.0f}×）")

    problems: list[str] = []
    if spread < MIN_SPREAD:
        problems.append(
            f"4 个点只铺开了画面的 {spread * 100:.0f}%，太集中——解出来的球场尺度基本是猜的。"
            "请点在画面四角附近（中圈两端、左右禁区角）"
        )
    if scale_ratio > MAX_SCALE_RATIO:
        problems.append(
            f"画面不同位置的比例差 {scale_ratio:.1f} 倍，正常机位不该这么大——多半是把禁区角/门柱当成了角旗"
        )
    if holdout:
        worst_hold = 0.0
        for (u, v), (x, y) in holdout:
            px, py = pitch.pixel_to_pitch(cal.homography, (u, v))
            err = math.hypot(px - x, py - y)
            worst_hold = max(worst_hold, err)
            print(f"     留出点 ({x:.1f},{y:.1f})m 误差 {err:.2f} 米")
        if worst_hold > 3.0:
            problems.append(f"留出点误差 {worst_hold:.1f} 米偏大，标定不可信（>3 米）")
    else:
        print("     [!] 没给留出点：这里没有可信的精度证据。想验收就多给 1 个锚点当第 5 点")

    preview = frame.copy()
    for i, ((u, v), (x, y)) in enumerate(zip(fit_px, fit_anchor), 1):
        cv2.circle(preview, (int(u), int(v)), 9, (0, 255, 0), 2)
        cv2.putText(preview, f"{i}:{names[i - 1]}", (int(u) + 14, int(v) - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    prev_path = out.with_suffix(".preview.jpg")
    cv2.imwrite(str(prev_path), preview)

    grid_path = None
    if not args.no_grid:
        grid = _draw_grid(frame, cal.homography)
        grid_path = out.with_suffix(".grid.jpg")
        cv2.imwrite(str(grid_path), grid)

    print(f"     预览图 {prev_path.name}")
    if grid_path:
        print(f"     栅格图 {grid_path.name}  ← 打开看：橙线该压在真实白线上")

    if problems:
        print("")
        for p in problems:
            print(f"[!] {p}")
        print("[!] 这份标定不建议用来算距离，先改点重跑")
        return 2
    print("[ok] 自检通过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
