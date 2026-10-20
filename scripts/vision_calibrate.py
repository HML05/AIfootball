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
import itertools
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
# 投影出来的场地线有多少比例落在画面里的白线上。这是唯一不依赖「用户多点一个校验点」
# 的自动精度指标：点错了整条线会跑到草皮上，命中率立刻掉。同时算一个「整体平移 50 像素」
# 的对照组——判据看的是两者之差，不是绝对值（绝对值会被广告牌、观众席的白像素抬高）。
MIN_LINE_HIT = 0.65
MIN_HIT_LIFT = 1.6
# 单条线的最低命中率。总命中率会被「点对的那条线」拉高（实测：中线 100% + 小禁区 28%
# 合计还是 61%），所以每条线单独判——28% 说明小禁区那个框根本没扣在真实小禁区上。
MIN_LINE_EACH = 0.50


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


def _dpi_aware() -> None:
    """让 Windows 别给窗口做 DPI 缩放。

    150% 缩放的屏幕上，不做这件事的话「看到的像素」和「回调收到的坐标」会差一个比例，
    表现为「我明明点在禁区角上，它却记到别处去了」。
    """
    try:
        import ctypes

        ctypes.windll.shcore.SetProcessDpiAwareness(2)  # PER_MONITOR_AWARE
    except Exception:
        try:
            import ctypes

            ctypes.windll.user32.SetProcessDPIAware()
        except Exception:
            pass


class _View:
    """点选窗口的视图状态：可缩放、可平移。

    转播画面里要点的角落常常贴着画面边缘（甚至被裁掉一点），固定尺寸的窗口里
    鼠标根本够不着，所以必须能放大再点。
    """

    def __init__(self, frame) -> None:
        self.h, self.w = frame.shape[:2]
        self.zoom = 1.0
        self.cx = self.w / 2.0
        self.cy = self.h / 2.0

    def window_size(self) -> tuple[int, int]:
        max_w, max_h = 1600, 900
        vw = min(self.w, max_w) / self.zoom
        vh = min(self.h, max_h) / self.zoom
        return max(200, int(vw)), max(150, int(vh))

    def crop(self, frame):
        import cv2

        vw, vh = self.window_size()
        vw = min(vw, self.w)
        vh = min(vh, self.h)
        x0 = int(round(min(max(self.cx - vw / 2, 0), self.w - vw)))
        y0 = int(round(min(max(self.cy - vh / 2, 0), self.h - vh)))
        self.cx, self.cy = x0 + vw / 2, y0 + vh / 2
        patch = frame[y0:y0 + vh, x0:x0 + vw]
        return patch, x0, y0

    def to_image(self, x: float, y: float, x0: int, y0: int, shape) -> tuple[float, float]:
        vh, vw = shape[:2]
        vwid, vhei = self.window_size()
        return x * (vw / max(vwid, 1)) + x0, y * (vh / max(vhei, 1)) + y0

    def zoom_at(self, factor: float, img_pt: tuple[float, float]) -> None:
        self.zoom = min(8.0, max(1.0, self.zoom * factor))
        self.cx, self.cy = img_pt


def _click_points(frame, names: list[str]) -> list[tuple[float, float]]:
    """弹窗点选，Esc 取消。滚轮放大、右键拖动平移、u 撤销、r 重来。"""
    cv2 = _load_cv2()
    _dpi_aware()
    clicked: list[tuple[float, float]] = []
    win = "calibrate: click the anchors in order (Esc=cancel)"
    total = len(names)
    view = _View(frame)
    mapping: dict[str, int] = {"x0": 0, "y0": 0, "vw": view.window_size()[0], "vh": view.window_size()[1]}
    drag: list[float] = []

    def on_mouse(event, x, y, flags, param):  # noqa: ANN001
        if event == cv2.EVENT_MOUSEWHEEL:
            step = 1.25 if flags > 0 else 1 / 1.25
            img_pt = view.to_image(x, y, mapping["x0"], mapping["y0"], (mapping["vh"], mapping["vw"]))
            view.zoom_at(step, img_pt)
            return
        if event == cv2.EVENT_RBUTTONDOWN:
            drag[:] = [x, y]
            return
        if event == cv2.EVENT_MOUSEMOVE and drag:
            dx = (x - drag[0]) / view.zoom
            dy = (y - drag[1]) / view.zoom
            drag[:] = [x, y]
            view.cx -= dx
            view.cy -= dy
            return
        if event == cv2.EVENT_RBUTTONUP:
            drag.clear()
            return
        if event == cv2.EVENT_LBUTTONDOWN and len(clicked) < total:
            iu, iv = view.to_image(x, y, mapping["x0"], mapping["y0"], (mapping["vh"], mapping["vw"]))
            clicked.append((float(iu), float(iv)))
            print(f"[i] 第 {len(clicked)} 点 / {total} ({names[len(clicked) - 1]}) → 像素 ({iu:.0f}, {iv:.0f})")

    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win, 40, 20)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:  # 老版本/无此属性时忽略
        pass
    cv2.setMouseCallback(win, on_mouse)
    print("[i] 点选窗口已打开（标题 calibrate…）。没看到就把其他窗口最小化，或看任务栏。")
    print(f"[i] 按 1→{total} 的顺序点：鼠标滚轮放大、按住右键拖动画面、u 撤销上一点、r 重来、Esc 取消。")
    while True:
        patch, x0, y0 = view.crop(frame)
        mapping["x0"], mapping["y0"] = x0, y0
        mapping["vw"], mapping["vh"] = patch.shape[1], patch.shape[0]
        canvas = patch.copy()
        for i, (x, y) in enumerate(clicked):
            px, py = int(x - x0), int(y - y0)
            if not (0 <= px < canvas.shape[1] and 0 <= py < canvas.shape[0]):
                continue
            cv2.drawMarker(canvas, (px, py), (0, 0, 255), cv2.MARKER_CROSS, 26, 2)
            cv2.putText(canvas, f"{i + 1} {names[i]}", (px + 12, py - 12),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 255), 2)
        todo = names[len(clicked)] if len(clicked) < total else "done"
        cv2.putText(canvas, f"next ({min(len(clicked) + 1, total)}/{total}): {todo}   zoom x{view.zoom:.2f}",
                    (16, 34), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key == 27:
            cv2.destroyAllWindows()
            raise SystemExit("[取消] 已退出标定")
        if key in (ord("u"), ord("U")) and clicked:
            print(f"[i] 撤销：{names[len(clicked) - 1]}")
            clicked.pop()
        if key in (ord("r"), ord("R")):
            print("[i] 重来：清空已点的位置")
            clicked.clear()
        if key in (ord("+"), ord("=")):
            view.zoom_at(1.25, (view.cx, view.cy))
        if key in (ord("-"), ord("_")):
            view.zoom_at(1 / 1.25, (view.cx, view.cy))
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


def _imwrite(path: Path, img) -> bool:
    """cv2.imwrite 失败不抛异常、只返回 False，这里把它变成显式结果。"""
    cv2 = _load_cv2()
    try:
        ok = bool(cv2.imwrite(str(path), img))
    except Exception as exc:  # noqa: BLE001 - 权限/路径问题都归到这里
        print(f"     [!] 写图失败 {path.name}: {exc}")
        return False
    if not ok:
        print(f"     [!] 写图失败 {path.name}（目录不可写？）")
    return ok


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


def _draw_features(frame, h: np.ndarray):
    """把禁区、中线、中圈这些「一眼能认出来」的线按标定结果画回去。

    只看 5 米网格很难判断对不对（网格密、缺参照），但「禁区方框扣没扣在真实的禁区上」
    是一眼就能看出来的。颜色：外框红、中线绿、两个禁区品红、两个小禁区橙、中圈青。
    """
    cv2 = _load_cv2()
    h_inv = np.linalg.inv(h)
    out = frame.copy()
    h_img, w_img = out.shape[:2]
    L, W = pitch.PITCH_LENGTH, pitch.PITCH_WIDTH
    cy = W / 2
    pa_half, ga_half = 40.32 / 2, 18.32 / 2

    def line(pts, color, thick=3):
        prev = None
        for x, y in pts:
            u, v = _pitch_to_pixel(h_inv, x, y)
            if any(math.isnan(t) for t in (u, v)):
                prev = None
                continue
            if abs(u) > 6 * w_img or abs(v) > 6 * h_img:
                prev = None
                continue
            if prev is not None:
                cv2.line(out, prev, (int(u), int(v)), color, thick, cv2.LINE_AA)
            prev = (int(u), int(v))

    def seg(x0, y0, x1, y1, n=24):
        return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]

    line(seg(0, 0, L, 0) + seg(L, 0, L, W) + seg(L, W, 0, W) + seg(0, W, 0, 0), (60, 60, 255))
    line(seg(L / 2, 0, L / 2, W), (0, 210, 0))
    for x0, x1 in ((0.0, 16.5), (L, L - 16.5)):
        line(seg(x0, cy - pa_half, x1, cy - pa_half) + seg(x1, cy - pa_half, x1, cy + pa_half)
             + seg(x1, cy + pa_half, x0, cy + pa_half), (255, 0, 255), 2)
    for x0, x1 in ((0.0, 5.5), (L, L - 5.5)):
        line(seg(x0, cy - ga_half, x1, cy - ga_half) + seg(x1, cy - ga_half, x1, cy + ga_half)
             + seg(x1, cy + ga_half, x0, cy + ga_half), (0, 165, 255), 2)
    circle = [(L / 2 + 9.15 * math.cos(2 * math.pi * i / 90), cy + 9.15 * math.sin(2 * math.pi * i / 90))
              for i in range(91)]
    line(circle, (255, 255, 0), 2)
    return out


def _line_hit_ratio(frame, h: np.ndarray, tol: int = 4) -> tuple[float, float, list[tuple[str, float]]]:
    """自动质量指标：投影出来的场地线有多少比例落在「白漆」上。

    「白漆」= HSV 里亮且几乎没颜色（草皮饱和度高，白线饱和度低），比灰色阈值靠谱得多。
    同时算一个对照组：把同样的线整体平移 50 像素后有多少落白漆。标定歪掉时两组会差不多
    （≈ 随机命中率），标定正确时投影组要明显高——所以判据看的是「两者之差」，不是绝对值。
    """
    cv2 = _load_cv2()
    h_inv = np.linalg.inv(h)
    hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
    paint = ((hsv[:, :, 1] < 70) & (hsv[:, :, 2] > 165)).astype(np.uint8)
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (2 * tol + 1, 2 * tol + 1))
    near_paint = cv2.dilate(paint, kernel)  # 线上某点 tol 像素内有白漆就算命中
    h_img, w_img = near_paint.shape[:2]
    L, W = pitch.PITCH_LENGTH, pitch.PITCH_WIDTH
    cy = W / 2

    bars: list[tuple[str, tuple[tuple[float, float], tuple[float, float]]]] = [
        # 两条边线与两条球门线：这几条才是「点必须落在交点上」的判据。
        # 少了它们，一个只横向偏 20 px 的点也能蒙混过关——它还在中线上，
        # 但已经不在「中线 × 边线」那个交点了，整张单应会跟着歪。
        ("touchline_far", ((0.0, 0.0), (L, 0.0))),
        ("touchline_near", ((0.0, W), (L, W))),
        ("goal_left", ((0.0, 0.0), (0.0, W))),
        ("goal_right", ((L, 0.0), (L, W))),
        ("halfway", ((L / 2, 0), (L / 2, W))),
        ("pa_right", ((L - 16.5, cy - 20.16), (L - 16.5, cy + 20.16))),
        ("pa_left", ((16.5, cy - 20.16), (16.5, cy + 20.16))),
        ("pa_right_far", ((L - 16.5, cy - 20.16), (L, cy - 20.16))),
        ("pa_right_near", ((L - 16.5, cy + 20.16), (L, cy + 20.16))),
        ("ga_right", ((L - 5.5, cy - 9.16), (L - 5.5, cy + 9.16))),
        ("ga_left", ((5.5, cy - 9.16), (5.5, cy + 9.16))),
    ]

    def ratio(bar, dy: float = 0.0, n: int = 60) -> tuple[int, int]:
        (x0, y0), (x1, y1) = bar
        hits = seen = 0
        for i in range(n + 1):
            t = i / n
            u, v = _pitch_to_pixel(h_inv, x0 + (x1 - x0) * t, y0 + (y1 - y0) * t)
            if any(math.isnan(z) for z in (u, v)):
                continue
            ui, vi = int(round(u)), int(round(v + dy))
            if not (0 <= ui < w_img and 0 <= vi < h_img):
                continue
            seen += 1
            if near_paint[vi, ui]:
                hits += 1
        return hits, seen

    detail: list[tuple[str, float]] = []
    total_hit = total_seen = ctrl_hit = 0
    for name, bar in bars:
        hits, seen = ratio(bar)
        chits, _ = ratio(bar, dy=50.0)
        if seen >= 10:  # 采样太少（线基本在画面外）就不报，避免噪音
            detail.append((name, hits / seen))
            total_hit += hits
            total_seen += seen
            ctrl_hit += chits
    if not total_seen:
        return 0.0, 1.0, detail
    hit = total_hit / total_seen
    ctrl = ctrl_hit / total_seen
    return hit, ctrl, detail


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


def _overlay(frame, cal, names: list[str], hit: float, ctrl: float):
    """验收叠图：5 米网格 + 能一眼认出的场地线 + 点击位置 + 白线命中率。"""
    cv2 = _load_cv2()
    img = _draw_grid(frame, cal.homography)
    img = _draw_features(img, cal.homography)
    for i, ((u, v), _) in enumerate(cal.pairs, 1):
        cv2.circle(img, (int(u), int(v)), 12, (0, 0, 0), -1, cv2.LINE_AA)
        cv2.circle(img, (int(u), int(v)), 10, (0, 255, 255), -1, cv2.LINE_AA)
        label = names[i - 1] if i - 1 < len(names) else str(i)
        cv2.putText(img, label, (int(u) + 14, int(v) - 10),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2, cv2.LINE_AA)
    text = f"paint hit {hit * 100:.0f}% (ctrl {ctrl * 100:.0f}%)   y=save  n=redo  esc=cancel"
    cv2.putText(img, text, (24, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 0, 0), 5, cv2.LINE_AA)
    cv2.putText(img, text, (24, 44), cv2.FONT_HERSHEY_SIMPLEX, 1.0, (0, 255, 0), 2, cv2.LINE_AA)
    return img


def _confirm(frame, cal, names: list[str], hit: float, ctrl: float):
    """把验收叠图摊给用户看：红线/品红框没压住场地线就按 n 重点，或按键改单点。

    返回值：("y"|"n"|"esc") 或 ("redo", 下标)。
    为什么要能改单点：这段素材里禁区远端线和球门线的交点只有几十个像素宽，
    一次点不准很正常；整轮重来代价太大，边看叠图边改一个点才收敛得动。
    为什么要能缩放：判「压没压住」得看几十像素，整图缩到 1600 宽根本分不清，
    所以这里和点选窗一样支持滚轮缩放 + 右键拖动。
    """
    cv2 = _load_cv2()
    _dpi_aware()
    win = "calibrate: check the overlay (y=save n=redo 1-4=fix one point esc=cancel)"
    base = _overlay(frame, cal, names, hit, ctrl)
    view = _View(base)
    mapping: dict[str, int] = {"x0": 0, "y0": 0, "vw": view.window_size()[0], "vh": view.window_size()[1]}
    drag: list[float] = []
    result: list = []

    def on_mouse(event, x, y, flags, param):  # noqa: ANN001
        if event == cv2.EVENT_MOUSEWHEEL:
            img_pt = view.to_image(x, y, mapping["x0"], mapping["y0"], (mapping["vh"], mapping["vw"]))
            view.zoom_at(1.25 if flags > 0 else 1 / 1.25, img_pt)
            return
        if event == cv2.EVENT_RBUTTONDOWN:
            drag[:] = [x, y]
            return
        if event == cv2.EVENT_MOUSEMOVE and drag:
            view.cx -= (x - drag[0]) / view.zoom
            view.cy -= (y - drag[1]) / view.zoom
            drag[:] = [x, y]
            return
        if event == cv2.EVENT_RBUTTONUP:
            drag.clear()

    cv2.namedWindow(win, cv2.WINDOW_AUTOSIZE)
    cv2.moveWindow(win, 40, 20)
    try:
        cv2.setWindowProperty(win, cv2.WND_PROP_TOPMOST, 1)
    except Exception:
        pass
    cv2.setMouseCallback(win, on_mouse)
    print("[i] 验收窗已打开：红色外框 / 品红禁区 / 绿色中线 要压在真实白线上")
    print("[i] 滚轮放大、右键拖动看清楚；y=保存  n=整轮重来  1~4=只改第几个点  Esc=取消")
    while True:
        patch, x0, y0 = view.crop(base)
        mapping["x0"], mapping["y0"] = x0, y0
        mapping["vw"], mapping["vh"] = patch.shape[1], patch.shape[0]
        canvas = patch.copy()
        cv2.putText(canvas, f"zoom x{view.zoom:.2f}", (16, canvas.shape[0] - 18),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 255), 2)
        cv2.imshow(win, canvas)
        key = cv2.waitKey(20) & 0xFF
        if key in (ord("y"), ord("Y"), 13):
            result = ["y", None]
            break
        if key in (ord("n"), ord("N")):
            result = ["n", None]
            break
        if key in (ord("+"), ord("=")):
            view.zoom_at(1.25, (view.cx, view.cy))
        if key in (ord("-"), ord("_")):
            view.zoom_at(1 / 1.25, (view.cx, view.cy))
        if key == 27:
            result = ["esc", None]
            break
        if ord("1") <= key <= ord("9"):
            idx = key - ord("1")
            if idx < len(names):
                result = ["redo", idx]
                break
    cv2.destroyAllWindows()
    return (result[0], result[1]) if result else ("esc", None)


def _evaluate(frame, px_points, anchors, names):
    """拟合 + 全套自检，返回一个 dict（main 保存时要用）。"""
    n_fit = min(4, len(px_points), len(anchors))
    fit_px = px_points[:n_fit]
    fit_anchor = anchors[:n_fit]
    holdout = list(zip(px_points[n_fit:], anchors[n_fit:]))
    cal = pitch.build_calibration(list(zip(fit_px, fit_anchor)))

    spread = _spread(fit_px, frame.shape)
    scales = [_local_scale(cal.homography, p) for p in fit_px]
    scale_ratio = max(scales) / max(min(scales), 1e-9)
    hit, ctrl, hit_detail = _line_hit_ratio(frame, cal.homography)

    worst, _ = _reproject_error(cal.homography, cal.pairs)
    print(f"     内点误差 {worst:.3f} 米（4 点拟合恒为 0，不能当质量证明）")
    print(f"     4 点铺开程度 {spread * 100:.0f}% 画面对角线（建议 >{MIN_SPREAD * 100:.0f}%）")
    print(f"     每像素米数 {min(scales):.4f} ~ {max(scales):.4f}（比值 {scale_ratio:.1f}×，建议 <{MAX_SCALE_RATIO:.0f}×）")
    print(f"     投影线压在白漆上的比例 {hit * 100:.0f}%（对照组 {ctrl * 100:.0f}%，"
          f"要求 >{MIN_LINE_HIT * 100:.0f}% 且高出对照组 {MIN_HIT_LIFT:.1f} 倍）")
    for name, r in hit_detail:
        print(f"        {name:10s} {r * 100:4.0f}%")

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
    if hit < MIN_LINE_HIT or hit < ctrl * MIN_HIT_LIFT:
        problems.append(
            f"投出来的场地线只有 {hit * 100:.0f}% 落在白漆上（对照组 {ctrl * 100:.0f}%）——"
            "说明点位对错了场地特征，看验收图里哪个框没压住再点"
        )
    weak = [(n, r) for n, r in hit_detail if r < MIN_LINE_EACH]
    if weak:
        problems.append(
            "这几条线明显没压在真实场地线上：" + "、".join(f"{n} {r * 100:.0f}%" for n, r in weak)
            + f"（要求每条 >{MIN_LINE_EACH * 100:.0f}%）——对应的点重新找一下"
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
        print("     [!] 没给留出点：精度证据只有上面那条白漆命中率。多给 1 个锚点会更硬")
    return dict(cal=cal, fit_px=fit_px, fit_anchor=fit_anchor, problems=problems,
                hit=hit, ctrl=ctrl)


def _usable(h: np.ndarray, points) -> bool:
    """这组点配上这个单应，投影是不是有定义（不发散 / 不撞奇点）。"""
    for p in points:
        try:
            x, y = pitch.pixel_to_pitch(h, p)
        except (ZeroDivisionError, ValueError):
            return False
        if not (math.isfinite(x) and math.isfinite(y)):
            return False
    return True


def _best_subset(frame, px_points, anchors, names):
    """点多于 4 个时，挑「投出来的场地线最贴白漆」的那 4 个。

    为什么需要这个：4 点拟合的残差恒为 0，人眼在一张 1080p 全景里找「禁区 16.5 米线
    与边线的交点」本来就容易点到边线上（我给的坐标也错过）。多点两个当保险，让算法
    用白漆命中率自己淘汰点歪的那几个——顺便剩下的点变成真正的「留出点」，能给精度证据。
    """
    n = min(len(px_points), len(anchors))
    px_points, anchors = px_points[:n], anchors[:n]
    if n <= 4:
        return list(range(n)), []

    best = None
    for combo in itertools.combinations(range(n), 4):
        try:
            cal = pitch.build_calibration([(px_points[i], anchors[i]) for i in combo])
        except (ValueError, ZeroDivisionError):
            continue  # 3 点共线之类，解不出单应
        if not _usable(cal.homography, [px_points[i] for i in combo]):
            continue  # 单应在这几个点上就发散（近似退化），直接扔
        hit, ctrl, detail = _line_hit_ratio(frame, cal.homography)
        worst_line = min((r for _, r in detail), default=0.0)
        score = hit + 0.25 * worst_line  # 主看总命中率，辅以「最差那条线」
        if best is None or score > best["score"]:
            best = dict(score=score, combo=combo, hit=hit, ctrl=ctrl, worst=worst_line)

    if best is None:
        raise SystemExit("[错误] 这些点里没有一组能解出单应（3 点共线？）")

    combo = best["combo"]
    rest = [i for i in range(n) if i not in combo]
    print(f"     [i] 自动挑出这 4 个点（白漆命中 {best['hit'] * 100:.0f}%，最差一条线 {best['worst'] * 100:.0f}%）：")
    for i in combo:
        u, v = px_points[i]
        print(f"        {names[i]:18s} 像素 ({u:.0f},{v:.0f})")
    if rest:
        print(f"     [i] 剩下 {len(rest)} 个点当留出点（只做校验，不参与拟合）")
        for i in rest:
            u, v = px_points[i]
            print(f"        {names[i]:18s} 像素 ({u:.0f},{v:.0f})")
    return combo, rest


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

    px_points = _parse_points(args.points) if args.points else None
    out = Path(args.out) if args.out else ROOT / "data" / "vision" / "calib" / f"{stem}.json"

    # 交互模式下不直接存盘：先算一遍、把验收叠图摊出来，用户按 y 才认。
    # 这一环补的是「4 点残差恒为 0」那个洞——点错了照样解出完美残差，只有看图才抓得住。
    res = None
    while True:
        if px_points is None:
            px_points = _click_points(frame, names)
            if len(px_points) < 4:
                raise SystemExit(f"[错误] 只给了 {len(px_points)} 个像素点，至少要 4 个")
        n_use = min(len(px_points), len(anchors))
        combo, rest = _best_subset(frame, px_points, anchors, names)
        order = list(combo) + list(rest)
        res = _evaluate(
            frame,
            [px_points[i] for i in order],
            [anchors[i] for i in order],
            [names[i] for i in order],
        )
        if args.points:
            break
        key, redo = _confirm(frame, res["cal"], [names[i] for i in list(combo) + list(rest)], res["hit"], res["ctrl"])
        if key == "y":
            break
        if key == "redo" and redo is not None:
            # 只重设这一个点：在叠图上看出哪条线没压住，就只改它对应的那个点
            target = names[redo]
            print(f"[i] 只改第 {redo + 1} 个点（{target}），其余点保留")
            again = _click_points(frame, [target])
            if not again:
                raise SystemExit("[取消] 已退出标定")
            px_points = list(px_points)
            px_points[redo] = again[0]
            print(f"[i] {target} 改成 ({again[0][0]:.0f}, {again[0][1]:.0f})，重新计算")
            continue
        if key == "n":
            px_points = None
            print(f"[i] 重新点：按 1→{len(names)} 的顺序再来一次")
            continue
        raise SystemExit("[取消] 已退出标定")

    assert res is not None
    cal = res["cal"]
    fit_px = res["fit_px"]
    fit_anchor = res["fit_anchor"]
    problems = res["problems"]
    cal.note = f"{stem} @ frame {args.frame}"

    # 只有在自检没挑出毛病时才落到正式文件名；不合格的存成 .rejected.json 留证据，
    # 免得下游脚本误把一份歪的标定当成可用的（之前就出过这个坑）。
    written = out if not problems else out.with_suffix(".rejected.json")
    try:
        pitch.save_calibration(cal, written)
    except PermissionError:
        print("")
        print(f"[x] 写不进去：{written}")
        print("    Windows 拒绝了这个目录的写入（常见于目录权限被收紧）。修复命令：")
        print(f'    icacls "{written.parent}" /grant "%USERNAME%":(OI)(CI)F /T')
        print("    或者换个能写的输出位置，例如 --out v2.json（就写到仓库根目录）")
        return 3
    print(f"[ok] 标定写入 {written}")

    preview = frame.copy()
    for i, ((u, v), (x, y)) in enumerate(zip(fit_px, fit_anchor), 1):
        cv2.circle(preview, (int(u), int(v)), 9, (0, 255, 0), 2)
        cv2.putText(preview, f"{i}:{names[i - 1]}", (int(u) + 14, int(v) - 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
    prev_path = written.with_suffix(".preview.jpg")
    _imwrite(prev_path, preview)

    grid_path = None
    if not args.no_grid:
        grid = _draw_features(_draw_grid(frame, cal.homography), cal.homography)
        grid_path = written.with_suffix(".grid.jpg")
        _imwrite(grid_path, grid)

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
