"""视觉处理进程: 从数据库领 queued 任务, 用 YOLOv8 跑检测+跟踪, 写回轨迹与指标

必须在视觉环境里跑(要 torch / ultralytics / opencv):
    .venv-vision\\Scripts\\python.exe scripts\\run_vision_jobs.py            # 一直等任务
    .venv-vision\\Scripts\\python.exe scripts\\run_vision_jobs.py --once     # 处理完当前队列就退
    .venv-vision\\Scripts\\python.exe scripts\\run_vision_jobs.py --job-id 3 # 只跑某一个

为什么不在 FastAPI 里跑: uvicorn 是单 worker, 被一段视频占住整站就不响应了;
而且云主机(2 GiB)根本没有 torch。所以处理是**独立进程 + 数据库排队**,
这边直接用 stdlib 的 sqlite3(这个 venv 里没有 sqlalchemy, 也不需要)。
"""
import argparse
import os
import socket
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.vision import config as vcfg  # noqa: E402
from src.vision.io import ascii_video_path, probe_video, write_overlay  # noqa: E402
from src.vision.metrics import summarize, verdict  # noqa: E402

DEFAULT_DB = ROOT / "data" / "database" / "football.db"

# 心跳文件: 页面靠它显示「处理进程在线/离线」以及这台机器有没有 GPU。
# 用文件而不是写数据库, 是因为它只是「本机这个进程还活着」, 不想每 3 秒往 SQLite 落一次盘。
HEARTBEAT = vcfg.VISION_DIR / "worker.json"

_WORKER = f"{socket.gethostname()}:{os.getpid()}"
_ENV: dict = {}


def env_info() -> dict:
    """把 GPU 与依赖版本记进心跳, 页面上直接能看出「这台机器能不能跑」。"""
    gpu = None
    try:
        import torch
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
    except Exception:  # noqa: BLE001 - 没有 torch 就是没有 GPU, 不是错误
        pass
    deps = None
    try:
        import ultralytics
        deps = f"ultralytics {ultralytics.__version__}"
    except Exception:  # noqa: BLE001
        pass
    return {"gpu": gpu, "deps": deps}


def beat(last_job: int | None = None) -> None:
    """写一次心跳(原子替换: 页面永远读不到写了一半的 JSON)。"""
    import json

    info = {"name": _WORKER, "host": socket.gethostname(), "pid": os.getpid(),
            "heartbeat_ts": round(time.time(), 3), "last_job": last_job}
    info.update(_ENV)
    try:
        HEARTBEAT.parent.mkdir(parents=True, exist_ok=True)
        tmp = HEARTBEAT.with_name(HEARTBEAT.name + ".tmp")
        tmp.write_text(json.dumps(info, ensure_ascii=False), encoding="utf-8")
        tmp.replace(HEARTBEAT)
    except OSError:
        pass


def now_str() -> str:
    return datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def db_path(arg: str | None) -> Path:
    return Path(arg or os.getenv("FA_DB") or DEFAULT_DB)


def connect(path: Path) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def _abs(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else ROOT / p


def _rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


# ---------------- 任务领取 ----------------

def claim(conn: sqlite3.Connection, worker: str, job_id: int | None = None) -> sqlite3.Row | None:
    """原子领取一个 queued 任务(BEGIN IMMEDIATE 防两个进程抢同一个)。"""
    conn.execute("BEGIN IMMEDIATE")
    try:
        if job_id:
            cur = conn.execute(
                "UPDATE vision_jobs SET status='running', started_at=?, updated_at=?, worker=?"
                " WHERE job_id=? AND status='queued'",
                (now_str(), now_str(), worker, job_id))
        else:
            row = conn.execute(
                "SELECT job_id FROM vision_jobs WHERE status='queued' ORDER BY job_id LIMIT 1"
            ).fetchone()
            if not row:
                conn.execute("COMMIT")
                return None
            cur = conn.execute(
                "UPDATE vision_jobs SET status='running', started_at=?, updated_at=?, worker=?"
                " WHERE job_id=? AND status='queued'",
                (now_str(), now_str(), worker, row["job_id"]))
        if cur.rowcount != 1:
            conn.execute("ROLLBACK")
            return None
        target = job_id or row["job_id"]  # type: ignore[name-defined]
        got = conn.execute("SELECT * FROM vision_jobs WHERE job_id=?", (target,)).fetchone()
        v = conn.execute("SELECT * FROM vision_videos WHERE video_id=?", (got["video_id"],)).fetchone()
        conn.execute(
            "UPDATE vision_videos SET status='running', message=?, updated_at=? WHERE video_id=?",
            (f"任务 #{target} 处理中", now_str(), got["video_id"]))
        conn.execute("COMMIT")
        return {"job": got, "video": v}
    except Exception:
        conn.execute("ROLLBACK")
        raise


def is_canceled(conn: sqlite3.Connection, job_id: int) -> bool:
    row = conn.execute("SELECT status FROM vision_jobs WHERE job_id=?", (job_id,)).fetchone()
    return bool(row and row["status"] == "canceled")


def fail(conn: sqlite3.Connection, job: sqlite3.Row, video_id: int, msg: str) -> None:
    conn.execute("UPDATE vision_jobs SET status='failed', error=?, message=?, finished_at=?,"
                 " updated_at=? WHERE job_id=?",
                 (msg, "处理失败", now_str(), now_str(), job["job_id"]))
    conn.execute("UPDATE vision_videos SET status='failed', message=?, updated_at=? WHERE video_id=?",
                 (f"处理失败: {msg[:180]}", now_str(), video_id))


# ---------------- 跑一个任务 ----------------

def run_job(conn: sqlite3.Connection, job: sqlite3.Row, video: sqlite3.Row,
            with_overlay: bool = False, overlay_frames: int = 600) -> dict:
    from src.vision.detector import Detector  # 延迟 import: 只有真跑任务时才需要 torch

    job_id, video_id = job["job_id"], video["video_id"]
    src = _abs(video["path"])
    if not src.exists():
        fail(conn, job, video_id, f"视频文件不在了: {video['path']}")
        return {"ok": False, "job_id": job_id, "error": "视频文件不在了"}

    step = max(1, int(job["step"] or 5))
    max_frames = int(job["frames_total"] or 0) or None
    probe = probe_video(ascii_video_path(src, vcfg.OUT_DIR / "_ascii"))
    total = probe.get("frames") or 0

    det = Detector(model=job["model"], imgsz=int(job["imgsz"] or 960),
                   conf=float(job["conf"] or 0.25), verbose=False)
    conn.execute("UPDATE vision_jobs SET frames_total=?, message=?, updated_at=? WHERE job_id=?",
                 (total or None, f"开始处理: {job['model']}", now_str(), job_id))

    frames: list[dict] = []       # 全部帧(算指标用)
    rows: list[tuple] = []        # 抽样轨迹(入库)
    t0 = time.time()
    n = 0
    last_report = 0.0

    for frame in det.track(str(ascii_video_path(src, vcfg.OUT_DIR / "_ascii"))):
        n += 1
        frames.append(frame)
        if (frame["frame"] % step) == 0:
            for b in frame["boxes"]:
                x1, y1, x2, y2 = b["xyxy"]
                rows.append((job_id, int(frame["frame"]), b.get("id"), int(b["cls"]),
                             float(b.get("conf") or 0), float(x1), float(y1), float(x2), float(y2)))

        if n % 25 == 0:
            beat(job_id)
            pct = min(99.0, round(n / total * 100, 1)) if total else 0.0
            conn.execute("UPDATE vision_jobs SET frames_done=?, progress=?, updated_at=? WHERE job_id=?",
                         (n, pct, now_str(), job_id))
            if total and time.time() - last_report > 5:
                last_report = time.time()
                rate = n / max(time.time() - t0, 0.001)
                print(f"[job {job_id}] {n}/{total} 帧 ({pct}%) {rate:.1f} 帧/秒", flush=True)
            if is_canceled(conn, job_id):
                print(f"[job {job_id}] 用户取消，停在第 {n} 帧", flush=True)
                conn.execute("UPDATE vision_videos SET status='uploaded', message=?, updated_at=?"
                             " WHERE video_id=?", ("任务已取消", now_str(), video_id))
                return {"ok": False, "job_id": job_id, "canceled": True, "frames": n}
        if max_frames and n >= max_frames:
            break

    elapsed = round(time.time() - t0, 2)

    # 抽样轨迹入库(先清掉这个 job 的旧行, 支持重跑)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM vision_tracks WHERE job_id=?", (job_id,))
        conn.executemany(
            "INSERT INTO vision_tracks (job_id, frame, track_id, cls, conf, x1, y1, x2, y2)"
            " VALUES (?,?,?,?,?,?,?,?,?)", rows)
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    meta = {"path": _rel(src), "fps": probe.get("fps"), "frames": total or n,
            "width": probe.get("width"), "height": probe.get("height"),
            "step": step, "model": job["model"], "imgsz": job["imgsz"], "conf": job["conf"]}
    summary = summarize(frames, meta=meta, elapsed=elapsed)
    lines = verdict(summary)

    overlay_path = None
    if with_overlay:
        out = vcfg.OUT_DIR / f"overlay_{job_id}.mp4"
        try:
            write_overlay(ascii_video_path(src, vcfg.OUT_DIR / "_ascii"), frames, out,
                          fps=probe.get("fps"), limit=overlay_frames)
            overlay_path = _rel(out)
        except Exception as e:  # 带框视频只是附加产物, 失败不影响指标
            print(f"[job {job_id}] 带框视频没生成: {type(e).__name__}: {e}", flush=True)

    import json
    payload = json.dumps({"summary": summary, "verdict": [list(x) for x in lines],
                          "elapsed": elapsed}, ensure_ascii=False)
    conn.execute("BEGIN IMMEDIATE")
    try:
        conn.execute("DELETE FROM vision_summaries WHERE job_id=?", (job_id,))
        conn.execute("INSERT INTO vision_summaries (job_id, video_id, payload, created_at)"
                     " VALUES (?,?,?,?)", (job_id, video_id, payload, now_str()))
        conn.execute("UPDATE vision_jobs SET status='done', progress=100.0, frames_done=?,"
                     " frames_total=?, message=?, overlay_path=?, finished_at=?, updated_at=?"
                     " WHERE job_id=?",
                     (n, total or n, f"完成: {n} 帧 / {elapsed} 秒", overlay_path,
                      now_str(), now_str(), job_id))
        conn.execute("UPDATE vision_videos SET status='done', fps=?, frames=?, width=?, height=?,"
                     " duration=?, message=?, updated_at=? WHERE video_id=?",
                     (probe.get("fps"), total or n, probe.get("width"), probe.get("height"),
                      probe.get("duration"), "处理完成，可以看轨迹与指标", now_str(), video_id))
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise

    print(f"[job {job_id}] 完成 {n} 帧 / {elapsed} 秒, 抽样 {len(rows)} 条轨迹, "
          f"指标 {len(lines)} 条判定", flush=True)
    beat(None)
    return {"ok": True, "job_id": job_id, "frames": n, "tracks": len(rows),
            "elapsed": elapsed, "summary": summary}


# ---------------- 主循环 ----------------

def main() -> int:
    ap = argparse.ArgumentParser(description="视觉处理进程(领数据库里的 queued 任务)")
    ap.add_argument("--once", action="store_true", help="处理完当前队列就退出")
    ap.add_argument("--job-id", type=int, default=None, help="只跑指定任务")
    ap.add_argument("--interval", type=float, default=3.0, help="空队列时每隔几秒看一眼")
    ap.add_argument("--overlay", action="store_true", help="额外生成带框视频(慢, 只做下载)")
    ap.add_argument("--overlay-frames", type=int, default=600, help="带框视频最多渲染多少帧")
    ap.add_argument("--db", default=None, help="数据库路径(默认 data/database/football.db)")
    args = ap.parse_args()

    path = db_path(args.db)
    if not path.exists():
        print(f"[x] 找不到数据库: {path}", flush=True)
        return 1
    conn = connect(path)
    worker = _WORKER
    global _ENV
    _ENV = env_info()
    beat()
    print(f"[ok] 处理进程启动 worker={worker} db={path}", flush=True)
    print(f"[ok] VISION_DIR={vcfg.VISION_DIR}", flush=True)
    print(f"[ok] 环境: {_ENV}", flush=True)

    if args.job_id:
        beat(args.job_id)
        got = claim(conn, worker, args.job_id)
        if not got:
            print(f"[x] 任务 #{args.job_id} 不在 queued 状态(可能已被别人领走)", flush=True)
            return 1
        run_job(conn, got["job"], got["video"], args.overlay, args.overlay_frames)
        return 0

    idle_rounds = 0
    while True:
        beat()
        got = claim(conn, worker)
        if not got:
            if args.once:
                print("[ok] 队列空了, 退出", flush=True)
                return 0
            idle_rounds += 1
            time.sleep(max(0.5, args.interval))
            continue
        idle_rounds = 0
        try:
            run_job(conn, got["job"], got["video"], args.overlay, args.overlay_frames)
        except KeyboardInterrupt:
            raise
        except Exception as e:
            fail(conn, got["job"], got["video"]["video_id"], f"{type(e).__name__}: {e}")
            print(f"[x] job {got['job']['job_id']} 失败: {type(e).__name__}: {e}", flush=True)
        if args.once:
            print("[ok] 处理完一轮(--once), 退出", flush=True)
            return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        print("\n[ok] 收到中断, 退出", flush=True)
        sys.exit(0)
