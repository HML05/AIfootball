"""视觉模块接口 - 上传视频 / 排队处理 / 取轨迹与指标

三条边界(改这个文件之前先看):
1. **这里绝不 import cv2 / ultralytics**: 云主机 2 GiB 装不下 torch, CI 也不装。
   视频元数据靠延迟 import cv2 探测, 拿不到就把字段留空并在 note 里说明。
2. 推理由 `scripts/run_vision_jobs.py` 在 `.venv-vision` 里跑(领数据库里的 queued 任务)。
   本文件只写任务行、读结果行 —— 所以 web 进程不会被一段视频卡住。
3. 视频流给 <video src> 用, 浏览器带不了 Authorization 头, 所以单独一个 media_router,
   用 ?token= 校验(与 /api/auth/avatar 同样的取舍: token 会出现在访问日志里)。
"""
import importlib.util
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import (APIRouter, Depends, File, Header, HTTPException, Query,
                     UploadFile)
from fastapi.responses import FileResponse
from pydantic import BaseModel
from sqlalchemy import func
from sqlalchemy.orm import Session

from config.settings import settings
from src.api.auth import _login_or_401, current_user
from src.database.crud import get_db
from src.database.models import VisionJob, VisionSummary, VisionTrack, VisionVideo

router = APIRouter()
media_router = APIRouter()

# 处理进程超过这么久没更新进度, 就认为它已经不在了(界面据此显示「离线」)
WORKER_STALE_SECONDS = 120

# 处理进程的心跳文件(由 scripts/run_vision_jobs.py 写)。为什么用文件而不用表:
# 心跳是「本机某个进程还活着」这件事, 一条 SQLite 写入落盘代价比一次文件覆盖大得多;
# 而且这个文件缺失时(云主机上从没跑过处理)正好就是「没有处理进程」这个事实。
WORKER_STATE_FILE = settings.VISION_DIR / "worker.json"


# ---------------- 小工具 ----------------

def _now() -> datetime:
    return datetime.now()


def _rel(path: Path) -> str:
    """落库的路径一律相对仓库根, 换机器/换目录时不至于全废。"""
    try:
        return str(path.relative_to(settings.BASE_DIR)).replace("\\", "/")
    except ValueError:
        return str(path).replace("\\", "/")


def _abs(rel: str) -> Path:
    p = Path(rel)
    return p if p.is_absolute() else settings.BASE_DIR / p


def _has_module(name: str) -> bool:
    try:
        return importlib.util.find_spec(name) is not None
    except (ImportError, ValueError):
        return False


def _worker_state() -> dict:
    """读处理进程的心跳(data/vision/worker.json)。读不到 = 没有进程在轮询。"""
    empty = {"online": False, "name": None, "host": None, "pid": None,
             "gpu": None, "deps": None, "last_job": None, "heartbeat_age": None}
    try:
        raw = json.loads(WORKER_STATE_FILE.read_text(encoding="utf-8"))
        age = time.time() - float(raw.get("heartbeat_ts") or 0)
    except (OSError, ValueError, TypeError):
        return empty
    out = dict(empty)
    for k in ("name", "host", "pid", "gpu", "deps", "last_job"):
        if k in raw:
            out[k] = raw[k]
    out["heartbeat_age"] = round(age, 1)
    out["online"] = age <= WORKER_STALE_SECONDS
    return out


def _capabilities() -> dict:
    cv2_ok = _has_module("cv2")
    ult_ok = _has_module("ultralytics")
    can = cv2_ok and ult_ok
    if can:
        note = None
    elif not cv2_ok and not ult_ok:
        note = ("这台机器没装视觉依赖(torch/ultralytics/opencv)，只能上传和查看已处理的结果。"
                "要在这里出结果: 先跑 scripts\\vision_setup.ps1，再在 .venv-vision 里跑 "
                "scripts\\run_vision_jobs.py。")
    else:
        note = "视觉依赖只装了一半(opencv 或 ultralytics 缺一个)，跑不起来。"
    return {"cv2": cv2_ok, "ultralytics": ult_ok, "can_process": can, "note": note}


def _probe(path: Path) -> dict:
    """探测时长/帧率/分辨率。没装 opencv 或读不出来就返回 ok=False。"""
    if not _has_module("cv2"):
        return {"ok": False, "note": "服务端没装 opencv，视频时长/帧率留空（不影响上传与处理）"}
    try:
        import cv2  # noqa: WPS433 - 延迟 import, 见文件头第 1 条

        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            return {"ok": False, "note": "视频能存下来，但 opencv 打不开它(编码可能不认识)"}
        fps = float(cap.get(cv2.CAP_PROP_FPS) or 0)
        frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
        cap.release()
        return {"ok": True, "fps": round(fps, 3), "frames": frames,
                "width": width, "height": height,
                "duration": round(frames / fps, 2) if fps > 0 else None}
    except Exception as e:  # pragma: no cover - 视机器而定
        return {"ok": False, "note": f"探测失败: {type(e).__name__}: {e}"}


def _job_dict(j: VisionJob) -> dict:
    return {
        "job_id": j.job_id, "video_id": j.video_id, "status": j.status,
        "progress": round(float(j.progress or 0), 1),
        "frames_done": j.frames_done or 0, "frames_total": j.frames_total,
        "step": j.step, "model": j.model, "conf": j.conf, "imgsz": j.imgsz,
        "message": j.message, "error": j.error, "worker": j.worker,
        "overlay": bool(j.overlay_path),
        "started_at": j.started_at.strftime("%Y-%m-%d %H:%M:%S") if j.started_at else None,
        "finished_at": j.finished_at.strftime("%Y-%m-%d %H:%M:%S") if j.finished_at else None,
        "created_at": j.created_at.strftime("%Y-%m-%d %H:%M:%S") if j.created_at else None,
    }


def _latest_job(db: Session, video_id: int, status: Optional[str] = None) -> Optional[VisionJob]:
    q = db.query(VisionJob).filter(VisionJob.video_id == video_id)
    if status:
        q = q.filter(VisionJob.status == status)
    return q.order_by(VisionJob.job_id.desc()).first()


def _summary_payload(db: Session, job_id: int) -> Optional[dict]:
    row = db.query(VisionSummary).filter(VisionSummary.job_id == job_id).first()
    if not row:
        return None
    try:
        return json.loads(row.payload)
    except ValueError:
        return None


def _video_dict(db: Session, v: VisionVideo) -> dict:
    job = _latest_job(db, v.video_id)
    done = _latest_job(db, v.video_id, "done")
    brief = None
    if done:
        p = _summary_payload(db, done.job_id) or {}
        sm = p.get("summary") or {}
        brief = {
            "persons_per_frame": (sm.get("person") or {}).get("per_frame_mean"),
            "ball_pct": (sm.get("ball") or {}).get("frames_with_ball_pct"),
            "fragmentation": (sm.get("tracking") or {}).get("fragmentation"),
        }
    return {
        "video_id": v.video_id, "name": v.name, "status": v.status,
        "size_bytes": v.size_bytes, "duration": v.duration, "fps": v.fps,
        "width": v.width, "height": v.height, "frames": v.frames,
        "message": v.message,
        "created_at": v.created_at.strftime("%Y-%m-%d %H:%M:%S") if v.created_at else None,
        "job": _job_dict(job) if job else None,
        "done_job_id": done.job_id if done else None,
        "brief": brief,
    }


# ---------------- 概览 ----------------

@router.get("/overview", summary="视觉模块概览(依赖探测 / 计数 / 最近任务)")
def overview(db: Session = Depends(get_db),
             authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    caps = _capabilities()
    total = db.query(func.count(VisionVideo.video_id)).scalar() or 0
    by_status = dict(db.query(VisionVideo.status, func.count(VisionVideo.video_id))
                     .group_by(VisionVideo.status).all())
    job_total = db.query(func.count(VisionJob.job_id)).scalar() or 0
    running = (db.query(VisionJob)
               .filter(VisionJob.status == "running")
               .order_by(VisionJob.job_id.desc()).first())
    beat = _worker_state()
    # 两个来源合一: 心跳文件说明「本机有进程在等任务」, running 任务的 updated_at
    # 说明「它正在跑」—— 后者兜住心跳写失败的情况。
    job_alive = bool(running and running.updated_at and
                     (datetime.now() - running.updated_at).total_seconds() < WORKER_STALE_SECONDS)
    worker = {
        "online": bool(beat["online"] or job_alive),
        "name": beat["name"] or (running.worker if running else None),
        "host": beat["host"], "pid": beat["pid"],
        "gpu": beat["gpu"], "deps": beat["deps"],
        "heartbeat_age": beat["heartbeat_age"],
        "job_id": running.job_id if running else None,
    }
    recent = (db.query(VisionJob).order_by(VisionJob.job_id.desc()).limit(5).all())
    return {
        "server": caps,
        "defaults": {
            "step": settings.VISION_DEFAULT_STEP,
            "model": settings.VISION_DEFAULT_MODEL,
            "max_bytes": settings.VISION_MAX_BYTES,
            "exts": list(settings.VISION_VIDEO_EXTS),
        },
        "videos": {"total": total, "by_status": by_status},
        "jobs": {"total": job_total, "done": (by_status.get("done") or 0)},
        "worker": worker,
        "recent_jobs": [_job_dict(j) for j in recent],
    }


# ---------------- 视频 ----------------

@router.get("/videos", summary="视频列表(带最新任务与指标摘要)")
def list_videos(limit: int = Query(default=30, ge=1, le=200),
                db: Session = Depends(get_db),
                authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    rows = (db.query(VisionVideo).order_by(VisionVideo.video_id.desc()).limit(limit).all())
    return {"items": [_video_dict(db, v) for v in rows], "total": len(rows)}


@router.post("/videos", status_code=201, summary="上传视频(默认上限 300 MB)")
async def upload_video(file: UploadFile = File(...),
                       db: Session = Depends(get_db),
                       authorization: Optional[str] = Header(default=None)):
    u = _login_or_401(db, authorization)
    name = Path(file.filename or "video.mp4").name
    ext = Path(name).suffix.lower()
    if ext not in settings.VISION_VIDEO_EXTS:
        raise HTTPException(status_code=400,
                            detail=f"只收 {' / '.join(settings.VISION_VIDEO_EXTS)} 这些格式")

    row = VisionVideo(name=name, path="", status="uploaded", owner_id=u.user_id,
                      created_at=_now(), updated_at=_now())
    db.add(row)
    db.flush()  # 先拿到 video_id, 文件名用 v<id>.<ext>(纯 ASCII, opencv 才打得开)

    dest = settings.VISION_VIDEO_DIR / f"v{row.video_id}{ext}"
    size = 0
    try:
        with dest.open("wb") as fh:
            while True:
                chunk = await file.read(1024 * 1024)
                if not chunk:
                    break
                size += len(chunk)
                if size > settings.VISION_MAX_BYTES:
                    raise HTTPException(
                        status_code=413,
                        detail=f"视频超过上限 {settings.VISION_MAX_BYTES // (1024 * 1024)} MB")
                fh.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        db.rollback()
        raise
    except Exception as e:
        dest.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=500, detail=f"存文件失败: {type(e).__name__}: {e}")

    if size == 0:
        dest.unlink(missing_ok=True)
        db.rollback()
        raise HTTPException(status_code=400, detail="空文件")

    meta = _probe(dest)
    row.path = _rel(dest)
    row.size_bytes = size
    if meta.get("ok"):
        row.fps = meta.get("fps")
        row.frames = meta.get("frames")
        row.width = meta.get("width")
        row.height = meta.get("height")
        row.duration = meta.get("duration")
        row.message = "上传完成，可以开始处理"
    else:
        row.message = meta.get("note") or "上传完成"
    row.updated_at = _now()
    db.commit()
    db.refresh(row)
    return _video_dict(db, row)


@router.delete("/videos/{video_id}", summary="删除视频(连同任务、轨迹、指标、文件)")
def delete_video(video_id: int, db: Session = Depends(get_db),
                 authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    v = db.query(VisionVideo).filter(VisionVideo.video_id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    jobs = db.query(VisionJob).filter(VisionJob.video_id == video_id).all()
    busy = [j for j in jobs if j.status in ("queued", "running")]
    if busy:
        raise HTTPException(status_code=409, detail="这个视频还有任务在排队/处理，先取消再删")
    for j in jobs:
        db.query(VisionTrack).filter(VisionTrack.job_id == j.job_id).delete()
        db.query(VisionSummary).filter(VisionSummary.job_id == j.job_id).delete()
        if j.overlay_path:
            _abs(j.overlay_path).unlink(missing_ok=True)
    db.query(VisionJob).filter(VisionJob.video_id == video_id).delete()
    for p in (_abs(v.path), settings.VISION_OUT_DIR / f"overlay_{video_id}.mp4"):
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(v)
    db.commit()
    return {"ok": True, "video_id": video_id}


class ProcessIn(BaseModel):
    step: int = 5
    model: Optional[str] = None
    conf: Optional[float] = None
    imgsz: Optional[int] = None
    max_frames: Optional[int] = None


@router.post("/videos/{video_id}/process", status_code=201, summary="排队一次检测跟踪任务")
def process_video(video_id: int, body: Optional[ProcessIn] = None,
                  db: Session = Depends(get_db),
                  authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    v = db.query(VisionVideo).filter(VisionVideo.video_id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    if not _abs(v.path).exists():
        raise HTTPException(status_code=410, detail="视频文件不在了，重新上传一份")

    body = body or ProcessIn()
    # 先验参数再查「有没有任务在跑」：请求本身不合法时该报 400，而不是被 409 遮住
    step = int(body.step if body.step is not None else settings.VISION_DEFAULT_STEP)
    if not 1 <= step <= 60:
        raise HTTPException(status_code=400, detail="step 要在 1~60 之间")
    conf = float(body.conf if body.conf is not None else 0.25)
    if not 0.05 <= conf <= 0.95:
        raise HTTPException(status_code=400, detail="conf 要在 0.05~0.95 之间")
    imgsz = int(body.imgsz if body.imgsz is not None else 960)
    if not 320 <= imgsz <= 1280:
        raise HTTPException(status_code=400, detail="imgsz 要在 320~1280 之间")
    model = (body.model or settings.VISION_DEFAULT_MODEL).strip()
    if not model or len(model) > 80:
        raise HTTPException(status_code=400, detail="model 名字不合法")
    max_frames = int(body.max_frames) if body.max_frames else None
    if max_frames is not None and max_frames < 1:
        raise HTTPException(status_code=400, detail="max_frames 至少 1")

    busy = (db.query(VisionJob)
            .filter(VisionJob.video_id == video_id,
                    VisionJob.status.in_(("queued", "running"))).first())
    if busy:
        raise HTTPException(status_code=409, detail=f"已经有任务 #{busy.job_id} 在排队/处理")

    job = VisionJob(video_id=video_id, status="queued", progress=0.0, frames_done=0,
                    frames_total=max_frames or v.frames, step=step, model=model,
                    conf=conf, imgsz=imgsz, message="排队中，等处理进程来领",
                    created_at=_now(), updated_at=_now())
    db.add(job)
    v.status = "queued"
    v.message = "已排队，等处理进程来领任务"
    v.updated_at = _now()
    db.commit()
    db.refresh(job)
    return _job_dict(job)


# ---------------- 任务 ----------------

@router.get("/jobs/{job_id}", summary="任务进度")
def get_job(job_id: int, db: Session = Depends(get_db),
            authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    j = db.query(VisionJob).filter(VisionJob.job_id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _job_dict(j)


@router.post("/jobs/{job_id}/cancel", summary="取消任务(排队中立刻生效; 处理中会在下一批中断)")
def cancel_job(job_id: int, db: Session = Depends(get_db),
               authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    j = db.query(VisionJob).filter(VisionJob.job_id == job_id).first()
    if not j:
        raise HTTPException(status_code=404, detail="任务不存在")
    if j.status not in ("queued", "running"):
        raise HTTPException(status_code=409, detail=f"任务已经是 {j.status}，不用取消")
    j.status = "canceled"
    j.message = "用户取消"
    j.finished_at = _now()
    j.updated_at = _now()
    v = db.query(VisionVideo).filter(VisionVideo.video_id == j.video_id).first()
    if v:
        v.status = "uploaded"
        v.message = "任务已取消"
        v.updated_at = _now()
    db.commit()
    return _job_dict(j)


# ---------------- 结果 ----------------

@router.get("/videos/{video_id}/tracks", summary="抽样轨迹(前端 canvas 叠加用)")
def get_tracks(video_id: int,
               job_id: Optional[int] = None,
               frame_from: int = Query(default=0, ge=0),
               frame_to: int = Query(default=0, ge=0),
               db: Session = Depends(get_db),
               authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    if job_id is None:
        done = _latest_job(db, video_id, "done")
        if not done:
            raise HTTPException(status_code=404, detail="这个视频还没有处理完成的任务")
        job_id = done.job_id
    job = db.query(VisionJob).filter(VisionJob.job_id == job_id).first()
    if not job or job.video_id != video_id:
        raise HTTPException(status_code=404, detail="任务不存在或不属于这个视频")

    q = db.query(VisionTrack).filter(VisionTrack.job_id == job_id)
    if frame_from:
        q = q.filter(VisionTrack.frame >= frame_from)
    if frame_to:
        q = q.filter(VisionTrack.frame <= frame_to)
    rows = q.order_by(VisionTrack.frame, VisionTrack.track_id).limit(200_000).all()

    frames: dict = {}
    for r in rows:
        frames.setdefault(r.frame, []).append([
            r.track_id, r.cls, round(float(r.conf or 0), 3),
            round(float(r.x1), 1), round(float(r.y1), 1),
            round(float(r.x2), 1), round(float(r.y2), 1),
        ])
    return {
        "job_id": job_id, "step": job.step,
        "frames": [{"f": f, "b": boxes} for f, boxes in sorted(frames.items())],
        "boxes": sum(len(b) for b in frames.values()),
        "note": "每个框 = [track_id, cls, conf, x1, y1, x2, y2](像素坐标, 原始分辨率)",
    }


@router.get("/videos/{video_id}/summary", summary="指标摘要(metrics.summarize + 逐条判定)")
def get_summary(video_id: int, job_id: Optional[int] = None,
                db: Session = Depends(get_db),
                authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    if job_id is None:
        done = _latest_job(db, video_id, "done")
        if not done:
            raise HTTPException(status_code=404, detail="这个视频还没有处理完成的任务")
        job_id = done.job_id
    payload = _summary_payload(db, job_id)
    if payload is None:
        raise HTTPException(status_code=404, detail="这个任务没有指标(可能还没跑完)")
    return {"video_id": video_id, "job_id": job_id,
            "summary": payload.get("summary"),
            "verdict": [{"mark": m, "text": t} for m, t in (payload.get("verdict") or [])],
            "elapsed": payload.get("elapsed")}


# ---------------- 视频流(给 <video src>, 用 ?token= 鉴权) ----------------

def _media_guard(db: Session, token: str):
    if not token or not current_user(db, f"Bearer {token}"):
        raise HTTPException(status_code=401, detail="未登录或登录已过期")


_MEDIA_TYPES = {".mp4": "video/mp4", ".m4v": "video/mp4", ".mov": "video/quicktime",
                ".webm": "video/webm", ".mkv": "video/x-matroska",
                ".avi": "video/x-msvideo", ".flv": "video/x-flv"}


@media_router.get("/videos/{video_id}/stream", summary="原视频流(支持 Range, 供 <video> 播放)")
def stream_video(video_id: int, token: str = Query(default=""),
                 db: Session = Depends(get_db)):
    _media_guard(db, token)
    v = db.query(VisionVideo).filter(VisionVideo.video_id == video_id).first()
    if not v:
        raise HTTPException(status_code=404, detail="视频不存在")
    p = _abs(v.path)
    if not p.exists():
        raise HTTPException(status_code=410, detail="视频文件不在了")
    return FileResponse(p, media_type=_MEDIA_TYPES.get(p.suffix.lower(), "application/octet-stream"),
                        headers={"Cache-Control": "private, max-age=3600"})


@media_router.get("/videos/{video_id}/overlay", summary="带框视频(处理进程生成过才有)")
def overlay_video(video_id: int, token: str = Query(default=""),
                  db: Session = Depends(get_db)):
    _media_guard(db, token)
    done = _latest_job(db, video_id, "done")
    if not done or not done.overlay_path:
        raise HTTPException(status_code=404, detail="还没有带框视频(处理时加 --overlay 才会生成)")
    p = _abs(done.overlay_path)
    if not p.exists():
        raise HTTPException(status_code=404, detail="带框视频文件不在了")
    return FileResponse(p, media_type="video/mp4",
                        headers={"Cache-Control": "private, max-age=3600"})


@router.get("/videos/{video_id}/overlay/meta", summary="带框视频是否可用")
def overlay_meta(video_id: int, db: Session = Depends(get_db),
                 authorization: Optional[str] = Header(default=None)):
    _login_or_401(db, authorization)
    done = _latest_job(db, video_id, "done")
    ok = bool(done and done.overlay_path and _abs(done.overlay_path).exists())
    return {"available": ok, "job_id": done.job_id if done else None,
            "size_bytes": (_abs(done.overlay_path).stat().st_size if ok else None)}
