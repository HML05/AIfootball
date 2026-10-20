"""按球衣颜色给轨迹分队，产出 teams.json（给雷达图上色用）。

用法（在仓库根目录、用 .venv-vision 的解释器）:
    .venv-vision\\Scripts\\python.exe scripts\\vision_teams.py --job-id 2 --video data\\vision\\videos\\v2.mp4

它做三件事：
1. 从库里读出某次任务的轨迹（vision_tracks），按帧分组；
2. 每隔几帧回到原视频取一帧，按人物框取躯干颜色；
3. 把每条轨迹的中位颜色聚类成两队，写出 JSON + 一张「每队抽样拼图」供人眼复核。

为什么要拼图：聚类可能把「主队白」和「场地白线/裁判」混在一起，
数字看不出来，眼睛一看就知道。
"""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.vision import teams as vteams  # noqa: E402
from src.vision import io as vio  # noqa: E402

TEAM_BGR = [(40, 40, 235), (235, 160, 40)]  # 队 0 红、队 1 蓝（BGR）


def load_tracks(db: str, job_id: int, cls: int = 0) -> dict[int, list[tuple]]:
    con = sqlite3.connect(db)
    cur = con.execute(
        "select frame, track_id, x1, y1, x2, y2 from vision_tracks "
        "where job_id = ? and cls = ? order by frame, track_id",
        (job_id, cls),
    )
    by_frame: dict[int, list[tuple]] = {}
    for frame, tid, x1, y1, x2, y2 in cur.fetchall():
        by_frame.setdefault(int(frame), []).append((int(tid), (x1, y1, x2, y2)))
    con.close()
    return by_frame


def collect(video: str, by_frame: dict[int, list[tuple]], stride: int, limit: int
            ) -> tuple[dict[int, list], int]:
    wanted = sorted(by_frame)[::stride][:limit]
    samples: dict[int, list] = {}
    used = 0
    for idx, frame in vio.iter_frames(video, step=max(1, stride)):
        if used >= limit:
            break
        boxes = by_frame.get(int(idx))
        if not boxes:
            continue
        for tid, box in boxes:
            color = vteams.sample_color(frame, box)
            if color is not None:
                samples.setdefault(tid, []).append(color)
        used += 1
    return samples, used


def contact_sheet(video: str, by_frame: dict[int, list[tuple]], teams: dict[int, int],
                  out: Path, per_team: int = 8) -> int:
    """每队抽若干个人物框拼成一张图，人眼复核分队对不对。"""
    import cv2
    import numpy as np

    picks: dict[int, list[tuple[int, tuple]]] = {}
    for frame in sorted(by_frame)[::10]:
        for tid, box in by_frame[frame]:
            team = teams.get(tid)
            if team is None:
                continue
            bucket = picks.setdefault(team, [])
            if len(bucket) < per_team:
                bucket.append((frame, box))
        if all(len(picks.get(t, [])) >= per_team for t in (0, 1)):
            break

    tiles = []
    cap = cv2.VideoCapture(str(video))
    frames_cache: dict[int, object] = {}

    def grab(frame: int):
        if frame in frames_cache:
            return frames_cache[frame]
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame)
        ok, img = cap.read()
        frames_cache.clear()
        frames_cache[frame] = img if ok else None
        return frames_cache[frame]

    for team in (0, 1):
        for frame, box in picks.get(team, []):
            x1, y1, x2, y2 = [int(v) for v in box]
            img = grab(frame)
            if img is None:
                continue
            h, w = img.shape[:2]
            x1c, x2c = max(0, x1), min(w, x2)
            y1c, y2c = max(0, y1), min(h, y2)
            if x2c - x1c < 4 or y2c - y1c < 4:
                continue
            crop = img[y1c:y2c, x1c:x2c]
            tile = cv2.resize(crop, (96, 192), interpolation=cv2.INTER_AREA)
            cv2.rectangle(tile, (0, 0), (95, 191), TEAM_BGR[team], 2)
            cv2.putText(tile, str(team), (4, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.5,
                        TEAM_BGR[team], 1, cv2.LINE_AA)
            tiles.append(tile)
    cap.release()

    if not tiles:
        return 0
    cols = 8
    rows = (len(tiles) + cols - 1) // cols
    sheet = np.zeros((rows * 192, cols * 96, 3), dtype=np.uint8)
    for i, tile in enumerate(tiles):
        r, c = divmod(i, cols)
        sheet[r * 192:(r + 1) * 192, c * 96:(c + 1) * 96] = tile
    return int(cv2.imwrite(str(out), sheet))


def main() -> int:
    ap = argparse.ArgumentParser(description="按球衣颜色给轨迹分队")
    ap.add_argument("--db", default=str(ROOT / "data" / "database" / "football.db"))
    ap.add_argument("--job-id", type=int, required=True)
    ap.add_argument("--video", required=True)
    ap.add_argument("--stride", type=int, default=10, help="每多少帧采一次颜色")
    ap.add_argument("--limit", type=int, default=60, help="最多看多少帧")
    ap.add_argument("--out", default=str(ROOT / "data" / "vision" / "out" / "teams.json"))
    ap.add_argument("--sheet", default="", help="抽样拼图输出路径（不填则不生成）")
    args = ap.parse_args()

    by_frame = load_tracks(args.db, args.job_id)
    if not by_frame:
        print(f"[-] 任务 {args.job_id} 还没有轨迹数据", file=sys.stderr)
        return 1
    samples, used = collect(args.video, by_frame, args.stride, args.limit)
    print(f"[i] 采了 {used} 帧、{len(samples)} 条轨迹的颜色")

    try:
        result = vteams.assign_teams(samples)
    except vteams.TeamError as exc:
        print(f"[-] 分队失败：{exc}", file=sys.stderr)
        return 2

    teams = {int(k): int(v) for k, v in result["teams"].items()}
    counts = [sum(1 for v in teams.values() if v == 0), sum(1 for v in teams.values() if v == 1)]
    confs = [c for c in result["confidence"].values()]
    print(f"[ok] 分成两队：队0 {counts[0]} 人（轨迹）、队1 {counts[1]} 人（轨迹）")
    print(f"     质心 {result['centers']}（r', g' 色度）")
    if confs:
        print(f"     置信度 中位 {sorted(confs)[len(confs) // 2]:.2f}，"
              f"低于 0.2 的 {sum(1 for c in confs if c < 0.2)} 条（这些基本是分不清的）")
    if result["skipped"]:
        print(f"     采样不足被跳过 {len(result['skipped'])} 条")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "job_id": args.job_id,
        "teams": {str(k): v for k, v in teams.items()},
        "centers": result["centers"],
        "confidence": {str(k): v for k, v in result["confidence"].items()},
        "skipped": result["skipped"],
    }
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[ok] 写入 {out}")

    if args.sheet:
        wrote = contact_sheet(args.video, by_frame, teams, Path(args.sheet))
        if wrote:
            print(f"[ok] 抽样拼图 {args.sheet}")
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    raise SystemExit(main())
