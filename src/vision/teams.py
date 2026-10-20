"""按球衣颜色把球员分成两队。

为什么需要：检测器只给「人」这一个类，雷达图要像转播那样分红/蓝两点，
就得自己判断谁跟谁一队。这里用最朴素也最可解释的办法——取躯干颜色、
去掉草皮色、在色度空间上做 2 均值聚类（k-means）。没有 sklearn 依赖。

刻意不做的事：不训练颜色分类器、不假设「主队穿白」。两支队的划分是
无监督的，所以输出的队号（0/1）本身没有语义，只是「分成了两组」。
门将通常自成一组，用 `MIN_SAMPLES` 和置信度把它筛出来，而不是硬塞进两队。
"""

from __future__ import annotations

import math
from typing import Iterable, Sequence

import numpy as np

# 草皮的 HSV 色相范围（OpenCV: H 0-179），以及判成草皮所需的饱和度。
GRASS_HUE = (35, 95)
GRASS_MIN_SAT = 60

# 躯干取框的这一段：太靠上是头（发色干扰），太靠下是短裤（有些队和上衣不同色）。
TORSO_TOP = 0.10
TORSO_BOTTOM = 0.55

# 一个 track 至少要有这么多帧采到颜色，才参与分队。
MIN_SAMPLES = 5


class TeamError(ValueError):
    """输入不足或无法分队时抛出（调用方应当降级成「不分队」而不是崩）。"""


def torso_box(box: Sequence[float], top: float = TORSO_TOP, bottom: float = TORSO_BOTTOM
              ) -> tuple[int, int, int, int]:
    """把人物框裁成躯干区域，返回 (x1, y1, x2, y2) 整数像素。"""
    x1, y1, x2, y2 = (float(v) for v in box[:4])
    h = y2 - y1
    ty1 = int(round(y1 + h * top))
    ty2 = int(round(y1 + h * bottom))
    if ty2 <= ty1:
        ty2 = ty1 + 1
    return int(round(x1)), ty1, int(round(x2)), ty2


def shirt_pixels(frame: np.ndarray, box: Sequence[float]) -> np.ndarray:
    """取出躯干里「不是草皮、不是场地白线」的像素（BGR，float32 的 N×3）。"""
    import cv2

    x1, y1, x2, y2 = torso_box(box)
    h, w = frame.shape[:2]
    x1, x2 = max(0, min(x1, w - 1)), max(0, min(x2, w))
    y1, y2 = max(0, min(y1, h - 1)), max(0, min(y2, h))
    if x2 - x1 < 2 or y2 - y1 < 2:
        return np.empty((0, 3), dtype=np.float32)
    patch = frame[y1:y2, x1:x2]
    hsv = cv2.cvtColor(patch, cv2.COLOR_BGR2HSV)
    hue, sat, val = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    grass = (hue >= GRASS_HUE[0]) & (hue <= GRASS_HUE[1]) & (sat >= GRASS_MIN_SAT)
    # 场地白线：很亮且几乎无饱和，跟白衣球员撞色，只能靠「细」这一特征排除，
    # 这里先不排（躯干里白线像素占比很低），只在统计时用中位数抗干扰。
    keep = ~grass
    if keep.sum() < 8:
        return np.empty((0, 3), dtype=np.float32)
    return patch[keep].reshape(-1, 3).astype(np.float32)


def chromaticity(rgb: np.ndarray) -> np.ndarray:
    """把颜色投到「只看颜色、不看亮度」的二维色度平面。

    r' = R/(R+G+B), g' = G/(R+G+B)。这样同一种球衣在阴影和阳光下的差异
    会被压掉大半，白色 (1/3,1/3) 与深色 (1/3,1/3) 也重合——所以纯白和纯黑
    分不开，这是这套方法的已知盲点，靠队服出现比例兜底。
    """
    arr = np.asarray(rgb, dtype=np.float32).reshape(-1, 3)
    total = arr.sum(axis=1, keepdims=True)
    total[total < 1e-6] = 1e-6
    return arr[:, [2, 1]] / total  # BGR -> (r', g')


def sample_color(frame: np.ndarray, box: Sequence[float]) -> np.ndarray | None:
    """一帧一个采样：躯干像素的 (色度 r', 色度 g', 亮度)。

    亮度也带进来，是因为「纯白」与「纯黑/深灰」在色度平面上重合（都接近 1/3,1/3），
    只有亮度能把它们分开。前者是白衣球队，后者通常是裁判或门将的深色衣服。
    """
    px = shirt_pixels(frame, box)
    if px.shape[0] < 8:
        return None
    chroma = np.median(chromaticity(px), axis=0)
    brightness = float(np.median(px.mean(axis=1))) / 255.0
    return np.array([chroma[0], chroma[1], brightness], dtype=np.float32)


def kmeans(points: np.ndarray, k: int = 2, iters: int = 40, seed: int = 0
           ) -> tuple[np.ndarray, np.ndarray]:
    """确定性的 k 均值聚类，返回 (标签, 质心)。只用 numpy，随机种子固定。

    特征维度不限（分队用到 2 维色度或 3 维带亮度），所以按实际维度 reshape。
    """
    arr = np.asarray(points, dtype=np.float32)
    dim = arr.shape[1] if arr.ndim == 2 else 1
    pts = arr.reshape(-1, dim)
    if pts.shape[0] < k:
        raise TeamError(f"少于 {k} 个样本，分不了 {k} 类")
    rng = np.random.default_rng(seed)
    # k-means++ 初始化：先随机取一颗，之后每颗取「离已有质心最远」的点
    centers = [pts[int(rng.integers(0, pts.shape[0]))]]
    for _ in range(k - 1):
        d = np.min(((pts[:, None, :] - np.asarray(centers)[None, :, :]) ** 2).sum(axis=2), axis=1)
        centers.append(pts[int(np.argmax(d))])
    centers = np.asarray(centers, dtype=np.float32)
    labels = np.full(pts.shape[0], -1, dtype=np.int32)
    for _ in range(iters):
        dist = ((pts[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = np.argmin(dist, axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for c in range(k):
            sel = labels == c
            if sel.any():
                centers[c] = pts[sel].mean(axis=0)
    return labels, centers


def kmeans2(points: np.ndarray, iters: int = 30, seed: int = 0) -> tuple[np.ndarray, np.ndarray]:
    """两类的特例，保留旧签名。"""
    return kmeans(points, k=2, iters=iters, seed=seed)
    labels = np.zeros(pts.shape[0], dtype=np.int32)
    for _ in range(iters):
        dist = ((pts[:, None, :] - centers[None, :, :]) ** 2).sum(axis=2)
        new_labels = np.argmin(dist, axis=1).astype(np.int32)
        if np.array_equal(new_labels, labels):
            break
        labels = new_labels
        for k in (0, 1):
            sel = labels == k
            if sel.any():
                centers[k] = pts[sel].mean(axis=0)
    return labels, centers


def assign_teams(samples: dict[int, Iterable[np.ndarray]], k: int = 3, seed: int = 0
                 ) -> dict[str, object]:
    """把每个 track 的中位颜色聚成 k 类，再从里面挑出两支球队。

    篮球场上除了两队，还有裁判（通常黑/黄）和门将（常穿异色）。一刀切成 2 类
    会把裁判和白队混在一起，所以先聚 3 类，再按「人数」和「颜色差异」挑两支：
    最大的两类如果是两支主队，剩下的自然就是裁判/门将。

    samples: {track_id: [ [r', g', v], ... ]}（`sample_color` 的返回值列表）
    返回 {"teams": {tid: 0|1}, "other": [tid...], "centers": [...],
          "confidence": {tid: 0~1}, "skipped": [tid...], "clusters": [...]}
    """
    per_track: dict[int, np.ndarray] = {}
    skipped: list[int] = []
    for tid, values in samples.items():
        arr = np.asarray([v for v in values if v is not None], dtype=np.float32)
        if arr.shape[0] < MIN_SAMPLES:
            skipped.append(int(tid))
            continue
        per_track[int(tid)] = np.median(arr, axis=0)

    if len(per_track) < max(6, k * 2):
        raise TeamError(f"只有 {len(per_track)} 条轨迹可采样，太少，分队没意义")

    tids = sorted(per_track)
    pts = np.asarray([per_track[t] for t in tids], dtype=np.float32)
    # 亮度权重压到 0.5，避免「黑衣服」把白色的两个人拆成两族
    feats = pts.copy()
    feats[:, 2] = pts[:, 2] * 0.5
    labels, centers = kmeans(feats, k=k, seed=seed)

    sizes = [(int((labels == c).sum()), c) for c in range(k)]
    sizes.sort(key=lambda x: (-x[0], x[1]))
    if len(sizes) < 2 or sizes[1][0] == 0:
        raise TeamError("聚类结果只有一类，分不出两队")
    team_a, team_b = sizes[0][1], sizes[1][1]
    # 两队质心靠得太近说明这次分不出来（比如画面里几乎只有一队）
    gap = distance(centers[team_a][:2], centers[team_b][:2])
    if gap < 0.03:
        raise TeamError(f"两类颜色几乎一样（色度差 {gap:.3f}），这次分不出两队")

    team_of = {team_a: 0, team_b: 1}
    teams: dict[int, int] = {}
    others: list[int] = []
    conf: dict[int, float] = {}
    for i, t in enumerate(tids):
        lab = int(labels[i])
        if lab not in team_of:
            others.append(int(t))
            continue
        teams[int(t)] = team_of[lab]
        other = team_b if lab == team_a else team_a
        d_near = distance(feats[i], centers[lab])
        d_far = distance(feats[i], centers[other])
        conf[int(t)] = 0.0 if d_far < 1e-6 else round(1.0 - d_near / d_far, 3)

    clusters = []
    for size, c in sizes:
        members = [int(tids[i]) for i in range(len(tids)) if int(labels[i]) == c]
        clusters.append({
            "cluster": int(c),
            "size": int(size),
            "center": [round(float(v), 4) for v in centers[c]],
            "team": team_of.get(c),
            "tracks": members,
        })
    return {
        "teams": teams,
        "other": others,
        "centers": [[round(float(v), 4) for v in centers[team_a]],
                    [round(float(v), 4) for v in centers[team_b]]],
        "confidence": conf,
        "skipped": skipped,
        "clusters": clusters,
    }

def distance(a: Sequence[float], b: Sequence[float]) -> float:
    """两点欧氏距离（测试与排序用）。"""
    return math.dist([float(a[0]), float(a[1])], [float(b[0]), float(b[1])])
