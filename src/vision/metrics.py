"""把轨迹算成「能看懂、能写进论文」的统计量。

诚实前提：这里没有人工标注的真值（GT），所以**算不出召回率/mAP**。
本模块给的是「管线可行性」证据：检出密度、球检出覆盖率、ID 碎裂程度、
框尺寸分布、速度。真值指标要等标好数据集后跑 ultralytics 的 val。
"""
from __future__ import annotations

from statistics import median
from typing import Any

PERSON_NAME = "person"
BALL_NAME = "sports ball"

# 框高的分档（像素）：远 / 中 / 近。只按 1080p 转播画面给的初始经验值，
# 换分辨率要同步调，所以同时输出原始分位数。
FAR_MAX = 40
MID_MAX = 90


def _mean(values: list[float]) -> float | None:
    return round(sum(values) / len(values), 3) if values else None


def _pct(part: int, whole: int) -> float:
    return round(100.0 * part / whole, 2) if whole else 0.0


def summarize(
    tracks: list[dict],
    meta: dict | None = None,
    person_cls: int = 0,
    ball_cls: int = 32,
    elapsed: float | None = None,
) -> dict:
    """tracks: [{"frame": i, "boxes": [...]}, ...]；meta 来自 io.probe_video。"""
    frames_total = len(tracks)
    per_frame_persons: list[int] = []
    per_frame_ball: list[int] = []
    person_conf: list[float] = []
    ball_conf: list[float] = []
    lifetimes: dict[int, int] = {}
    heights: list[float] = []
    frames_with_person = frames_with_ball = 0
    ball_frames: list[int] = []

    for item in tracks:
        boxes = item.get("boxes") or []
        people = [b for b in boxes if int(b.get("cls", -1)) == person_cls]
        balls = [b for b in boxes if int(b.get("cls", -1)) == ball_cls]

        per_frame_persons.append(len(people))
        per_frame_ball.append(len(balls))
        if people:
            frames_with_person += 1
        if balls:
            frames_with_ball += 1
            ball_frames.append(int(item["frame"]))

        for b in people:
            person_conf.append(float(b.get("conf", 0.0)))
            h = float(b["xyxy"][3]) - float(b["xyxy"][1])
            heights.append(h)
            tid = b.get("id")
            if tid is not None:
                lifetimes[int(tid)] = lifetimes.get(int(tid), 0) + 1
        for b in balls:
            ball_conf.append(float(b.get("conf", 0.0)))

    life_values = sorted(lifetimes.values())
    max_persons = max(per_frame_persons) if per_frame_persons else 0
    unique_ids = len(lifetimes)
    short_ids = sum(1 for v in life_values if v <= 2)

    # 球检出覆盖率与最长连续段：比总覆盖率更能说明「能不能追住球」
    longest_run = run = 0
    prev = None
    for f in ball_frames:
        run = run + 1 if prev is not None and f == prev + 1 else 1
        longest_run = max(longest_run, run)
        prev = f

    def bucket(h: float) -> str:
        if h < FAR_MAX:
            return "far"
        return "mid" if h < MID_MAX else "near"

    dist = {"far": 0, "mid": 0, "near": 0}
    for h in heights:
        dist[bucket(h)] += 1

    out: dict[str, Any] = {
        "frames_processed": frames_total,
        "video": meta or {},
        "person": {
            "frames_with_person": frames_with_person,
            "frames_with_person_pct": _pct(frames_with_person, frames_total),
            "per_frame_mean": _mean([float(v) for v in per_frame_persons]),
            "per_frame_max": max_persons,
            "per_frame_min": min(per_frame_persons) if per_frame_persons else None,
            "boxes_total": len(person_conf),
            "mean_conf": _mean(person_conf),
        },
        "tracking": {
            "unique_ids": unique_ids,
            "max_ids_in_one_frame": max_persons,
            # 1.0 = 每帧人数与 ID 总数一致，越大越碎（遮挡/换人越容易碎）
            "fragmentation": round(unique_ids / max_persons, 3) if max_persons else None,
            "id_lifetime_median": median(life_values) if life_values else None,
            "id_lifetime_mean": _mean([float(v) for v in life_values]),
            "short_ids_le_2_frames": short_ids,
        },
        "ball": {
            "frames_with_ball": frames_with_ball,
            "frames_with_ball_pct": _pct(frames_with_ball, frames_total),
            "boxes_total": len(ball_conf),
            "mean_conf": _mean(ball_conf),
            "longest_consecutive_run": longest_run,
        },
        "box_height_px": {
            "median": median(heights) if heights else None,
            "buckets": dist,
            "buckets_pct": {k: _pct(v, len(heights)) for k, v in dist.items()},
            "cutoffs_px": {"far_below": FAR_MAX, "mid_below": MID_MAX},
        },
    }
    if elapsed:
        out["speed"] = {
            "elapsed_sec": round(elapsed, 2),
            "fps_processed": round(frames_total / elapsed, 2) if elapsed else None,
        }
    out["notes"] = [
        "没有人工标注真值，本表不含召回率/mAP；它们是「管线跑通」证据，不是模型精度。",
        "fragmentation = 唯一 ID 数 / 单帧最多人数；越接近 1 越好，>3 说明 ID 碎裂严重。",
        "球检出率是 COCO 预训练模型在足球画面上的真实表现，专门微调后应显著提高。",
    ]
    return out


def verdict(summary: dict) -> list[tuple[str, str]]:
    """按经验阈值给「阶段 1 是否通过」的判定（参考值，非学术指标）。"""
    person = summary.get("person", {})
    tracking = summary.get("tracking", {})
    ball = summary.get("ball", {})

    def row(ok: bool | None, label: str, detail: str) -> tuple[str, str]:
        mark = "OK  " if ok else ("待看 " if ok is None else "不行")
        return mark, f"{label}：{detail}"

    frag = tracking.get("fragmentation")
    rows = [
        row((person.get("per_frame_mean") or 0) >= 10, "场上人数", f"平均 {person.get('per_frame_mean')} 人/帧"),
        row(frag is not None and frag <= 3, "ID 碎裂", f"{frag}（≤3 可接受）"),
        row((ball.get("frames_with_ball_pct") or 0) >= 20, "球检出覆盖率", f"{ball.get('frames_with_ball_pct')}%"),
        row((ball.get("longest_consecutive_run") or 0) >= 15, "球最长连续段", f"{ball.get('longest_consecutive_run')} 帧"),
        row(
            (summary.get("box_height_px", {}).get("median") or 0) >= FAR_MAX,
            "框尺寸",
            f"中位高 {summary.get('box_height_px', {}).get('median')} px",
        ),
    ]
    return rows
