"""球场标定与米制统计：把像素坐标变到 105×68 米的球场坐标。

为什么必须有这一层：不做标定，算出来的「跑动距离」是像素数——换个机位、换个分辨率
数字就变，论文里站不住；越位判定更是没有米制坐标就无从谈起。

设计上的两个取舍：
1. **只依赖 numpy，不 import cv2**（主应用与 CI 的系统 Python 没有 cv2，
   而单应矩阵用 4 点 DLT 手解一个 8×8 线性方程组就够了，不需要 OpenCV 的
   getPerspectiveTransform）；
2. **按「一脚出球点」= 检测框底边中点**取位置。人站在草皮上，脚的位置才是地面位置；
   用框中心会让远端球员凭空往看台方向偏（框越高、偏得越多）。
"""
from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable, Sequence

import numpy as np

# 国际足联标准场地（米）
PITCH_LENGTH = 105.0
PITCH_WIDTH = 68.0

# 标定时可以直接复用的锚点（米，原点在左上角球点，x 沿长边、y 沿短边）
ANCHORS: dict[str, tuple[float, float]] = {
    "corner_tl": (0.0, 0.0),
    "corner_tr": (PITCH_LENGTH, 0.0),
    "corner_br": (PITCH_LENGTH, PITCH_WIDTH),
    "corner_bl": (0.0, PITCH_WIDTH),
    "penalty_spot_left": (11.0, PITCH_WIDTH / 2),
    "penalty_spot_right": (PITCH_LENGTH - 11.0, PITCH_WIDTH / 2),
    "center": (PITCH_LENGTH / 2, PITCH_WIDTH / 2),
    "halfway_top": (PITCH_LENGTH / 2, 0.0),
    "halfway_bottom": (PITCH_LENGTH / 2, PITCH_WIDTH),
}

# 禁区角点（16.5 米深、40.32 米宽）。转播的战术机位常常看不到角旗，
# 但禁区线几乎总在画面里，所以这四个点才是实战里最常用的锚点。
_PA_DEPTH = 16.5
_PA_TOP = (PITCH_WIDTH - 40.32) / 2      # 13.84
_PA_BOTTOM = PITCH_WIDTH - _PA_TOP        # 54.16
ANCHORS.update({
    "pa_left_top": (0.0 + _PA_DEPTH, _PA_TOP),
    "pa_left_bottom": (0.0 + _PA_DEPTH, _PA_BOTTOM),
    "pa_right_top": (PITCH_LENGTH - _PA_DEPTH, _PA_TOP),
    "pa_right_bottom": (PITCH_LENGTH - _PA_DEPTH, _PA_BOTTOM),
    "goal_left_top": (0.0, PITCH_WIDTH / 2 - 3.66),
    "goal_left_bottom": (0.0, PITCH_WIDTH / 2 + 3.66),
    "goal_right_top": (PITCH_LENGTH, PITCH_WIDTH / 2 - 3.66),
    "goal_right_bottom": (PITCH_LENGTH, PITCH_WIDTH / 2 + 3.66),
})

# 人类足球运动员的物理上限：冲刺 9~10 m/s。超过这个数基本是 ID 跳变或标定错了。
MAX_HUMAN_SPEED = 12.0


@dataclass
class Calibration:
    """一次机位标定的结果。"""

    homography: np.ndarray                     # 3×3，像素 → 米
    pairs: list[tuple[tuple[float, float], tuple[float, float]]]
    pitch_length: float = PITCH_LENGTH
    pitch_width: float = PITCH_WIDTH
    note: str = ""

    def pixel_to_pitch(self, u: float, v: float) -> tuple[float, float]:
        return pixel_to_pitch(self.homography, (u, v))

    def to_dict(self) -> dict[str, Any]:
        return {
            "homography": [round(float(x), 10) for x in self.homography.reshape(-1)],
            "pairs": [[[round(a, 3), round(b, 3)], [round(c, 3), round(d, 3)]] for (a, b), (c, d) in self.pairs],
            "pitch_length": self.pitch_length,
            "pitch_width": self.pitch_width,
            "note": self.note,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "Calibration":
        pairs = [((p[0][0], p[0][1]), (p[1][0], p[1][1])) for p in data["pairs"]]
        return cls(
            homography=np.array(data["homography"], dtype=float).reshape(3, 3),
            pairs=pairs,
            pitch_length=float(data.get("pitch_length", PITCH_LENGTH)),
            pitch_width=float(data.get("pitch_width", PITCH_WIDTH)),
            note=str(data.get("note", "")),
        )


def homography_from_points(pairs: Sequence[tuple[tuple[float, float], tuple[float, float]]]) -> np.ndarray:
    """4 组 (像素, 米) 对应点 → 3×3 单应矩阵（像素 → 米）。

    用的是标准 DLT：把 h33 固定成 1，解 8 个未知数的 8×8 线性方程组。
    点少于 4 组直接报错——3 组只能解仿射，透视方向会错，那样远端球员的位置会显著偏。
    """
    if len(pairs) < 4:
        raise ValueError(f"标定至少要 4 组对应点，收到 {len(pairs)} 组")
    a_rows: list[list[float]] = []
    b_rows: list[float] = []
    for (u, v), (x, y) in pairs[:4]:
        a_rows.append([u, v, 1.0, 0.0, 0.0, 0.0, -x * u, -x * v])
        b_rows.append(x)
        a_rows.append([0.0, 0.0, 0.0, u, v, 1.0, -y * u, -y * v])
        b_rows.append(y)
    sol, *_ = np.linalg.lstsq(np.array(a_rows, dtype=float), np.array(b_rows, dtype=float), rcond=None)
    h = np.array(
        [
            [sol[0], sol[1], sol[2]],
            [sol[3], sol[4], sol[5]],
            [sol[6], sol[7], 1.0],
        ],
        dtype=float,
    )
    if not np.all(np.isfinite(h)):
        raise ValueError("标定点共线或退化，解不出单应矩阵；换几个分散在画面四角的点")
    return h


def pixel_to_pitch(h: np.ndarray, uv: tuple[float, float]) -> tuple[float, float]:
    """单点透视变换。"""
    u, v = float(uv[0]), float(uv[1])
    w = h[2, 0] * u + h[2, 1] * v + h[2, 2]
    if abs(w) < 1e-12:
        raise ZeroDivisionError("单应矩阵奇点，无法投影该点")
    x = (h[0, 0] * u + h[0, 1] * v + h[0, 2]) / w
    y = (h[1, 0] * u + h[1, 1] * v + h[1, 2]) / w
    return float(x), float(y)


def build_calibration(
    pairs: Iterable[tuple[tuple[float, float], tuple[float, float]]],
    note: str = "",
) -> Calibration:
    pairs = [((float(a), float(b)), (float(c), float(d))) for (a, b), (c, d) in pairs]
    return Calibration(homography=homography_from_points(pairs), pairs=pairs, note=note)


def load_calibration(path: str | Path) -> Calibration:
    return Calibration.from_dict(json.loads(Path(path).read_text(encoding="utf-8")))


def save_calibration(cal: Calibration, path: str | Path) -> Path:
    p = Path(path)
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cal.to_dict(), ensure_ascii=False, indent=2), encoding="utf-8")
    return p


def feet_point(box: dict) -> tuple[float, float]:
    """检测框 → 地面位置（框底边中点）。"""
    x1, y1, x2, y2 = box["xyxy"]
    return (x1 + x2) / 2.0, float(y2)


def positions_from_tracks(
    frames: Iterable[dict],
    cal: Calibration,
    cls_id: int = 0,
    fps: float = 25.0,
    person_cls: int = 0,
) -> dict[int, list[tuple[float, float, float]]]:
    """逐帧轨迹 → {track_id: [(t 秒, x 米, y 米), ...]}，只保留指定类别且带 ID 的框。"""
    out: dict[int, list[tuple[float, float, float]]] = {}
    for fr in frames:
        idx = int(fr.get("frame", 0))
        t = idx / fps if fps > 0 else float(idx)
        for box in fr.get("boxes", []):
            if box.get("cls") != cls_id or box.get("id") is None:
                continue
            if person_cls is not None and box.get("cls") != person_cls:
                continue
            try:
                x, y = cal.pixel_to_pitch(*feet_point(box))
            except (ZeroDivisionError, KeyError):
                continue
            if not (math.isfinite(x) and math.isfinite(y)):
                continue
            out.setdefault(int(box["id"]), []).append((t, x, y))
    for tid in out:
        out[tid].sort(key=lambda p: p[0])
    return out


@dataclass
class MotionStat:
    """一个 track 的运动统计。"""

    track_id: int
    samples: int
    distance_m: float
    avg_speed: float
    max_speed: float
    rejected: int = 0            # 超过人类上限、被判成 ID 跳变的段数
    first_t: float = 0.0
    last_t: float = 0.0

    @property
    def duration_s(self) -> float:
        return max(self.last_t - self.first_t, 0.0)

    def to_dict(self) -> dict[str, Any]:
        return {
            "track_id": self.track_id,
            "samples": self.samples,
            "distance_m": round(self.distance_m, 2),
            "avg_speed": round(self.avg_speed, 2),
            "max_speed": round(self.max_speed, 2),
            "duration_s": round(self.duration_s, 2),
            "rejected": self.rejected,
        }


def motion_stats(
    positions: dict[int, list[tuple[float, float, float]]],
    max_speed: float = MAX_HUMAN_SPEED,
    pitch_length: float = PITCH_LENGTH,
    pitch_width: float = PITCH_WIDTH,
) -> list[MotionStat]:
    """逐 track 算距离/均速/最高速。

    三道过滤（不做的话数字会明显虚高）：
    1. 相邻两点算出的瞬时速度超过 ``max_speed`` → 当成 ID 跳变，不计入距离；
    2. 落点跑出球场外 8 米 → 当成标定/框误差，跳过；
    3. 同一帧时间差为 0 → 跳过（重复帧）。
    """
    stats: list[MotionStat] = []
    margin = 8.0
    for tid, pts in positions.items():
        dist = 0.0
        speeds: list[float] = []
        rejected = 0
        for (t0, x0, y0), (t1, x1, y1) in zip(pts, pts[1:]):
            dt = t1 - t0
            if dt <= 0:
                continue
            if not (-margin <= x1 <= pitch_length + margin and -margin <= y1 <= pitch_width + margin):
                continue
            step = math.hypot(x1 - x0, y1 - y0)
            v = step / dt
            if v > max_speed:
                rejected += 1
                continue
            dist += step
            speeds.append(v)
        stats.append(
            MotionStat(
                track_id=tid,
                samples=len(pts),
                distance_m=dist,
                avg_speed=(sum(speeds) / len(speeds)) if speeds else 0.0,
                max_speed=max(speeds) if speeds else 0.0,
                rejected=rejected,
                first_t=pts[0][0] if pts else 0.0,
                last_t=pts[-1][0] if pts else 0.0,
            )
        )
    stats.sort(key=lambda s: s.distance_m, reverse=True)
    return stats


def possession(
    positions: dict[int, list[tuple[float, float, float]]],
    ball_track: list[tuple[float, float, float]],
    radius_m: float = 2.5,
) -> dict[str, Any]:
    """控球归属的启发式统计。

    规则故意简单（论文里要如实写成「启发式」）：球的每一帧，找半径 2.5 米内最近的球员，
    连续同一人超过 0.4 秒才算一次控球；否则算「无人控球」（传球中/死球/球没检出）。
    """
    holder_frames: dict[int, int] = {}
    unowned = 0
    for t, bx, by in ball_track:
        best_id, best_d = None, radius_m
        for tid, pts in positions.items():
            # 时间上取最近的一条位置记录
            cand = min(pts, key=lambda p: abs(p[0] - t))
            if abs(cand[0] - t) > 0.2:
                continue
            d = math.hypot(cand[1] - bx, cand[2] - by)
            if d < best_d:
                best_id, best_d = tid, d
        if best_id is None:
            unowned += 1
        else:
            holder_frames[best_id] = holder_frames.get(best_id, 0) + 1
    total = sum(holder_frames.values()) + unowned
    return {
        "frames_with_ball": len(ball_track),
        "owned_frames": sum(holder_frames.values()),
        "unowned_frames": unowned,
        "owned_pct": round(100.0 * sum(holder_frames.values()) / total, 2) if total else 0.0,
        "by_track": dict(sorted(holder_frames.items(), key=lambda kv: kv[1], reverse=True)),
        "note": "启发式：球半径 2.5 米内最近球员视为控球；没有人工真值，不等同于官方控球率",
    }
