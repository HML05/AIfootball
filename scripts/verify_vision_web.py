#!/usr/bin/env python
"""视觉分析模块的 Web 接口自检（纯 HTTP，不需要 torch/ultralytics）。

覆盖：鉴权、概览、上传（含格式/空文件拒绝）、排队、进度、媒体流 token、
取消、删除保护。上传用的是一段 2.7 KB 的真实 mp4（scripts/fixtures/tiny.mp4），
所以本自检在没装 opencv 的机器上也能跑（元数据断言自动跳过）。

用法:
    python scripts/verify_vision_web.py                 # 默认打 FA_API 或 127.0.0.1:8000
    python scripts/verify_vision_web.py http://8.133.235.32:8000

前置：服务已起、FA_USER/FA_PWD 有管理员权限（默认 admin/football2026）。
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import _uiauth  # noqa: E402

BASE = (sys.argv[1] if len(sys.argv) > 1 else os.environ.get("FA_API", "http://127.0.0.1:8000")).rstrip("/")
FIXTURE = Path(__file__).resolve().parent / "fixtures" / "tiny.mp4"

PASSED: list[str] = []
FAILED: list[str] = []
SKIPPED: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> bool:
    (PASSED if ok else FAILED).append(name)
    mark = "PASS" if ok else "FAIL"
    print(f"[{mark}] {name}" + (f"  <- {detail}" if detail and not ok else (f"  ({detail})" if detail else "")))
    return ok


def skip(name: str, why: str) -> None:
    SKIPPED.append(name)
    print(f"[SKIP] {name}  ({why})")


def request(method: str, path: str, *, token: str | None = None, body=None, raw: bytes | None = None,
            content_type: str | None = None, timeout: float = 30.0):
    """返回 (status, headers, bytes)；HTTP 错误码也照常返回，不抛异常。"""
    data = raw
    headers = {}
    if token:
        headers["Authorization"] = "Bearer " + token
    if body is not None:
        data = json.dumps(body).encode("utf-8")
        headers["Content-Type"] = "application/json"
    if raw is not None and content_type:
        headers["Content-Type"] = content_type
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, dict(r.headers), r.read()
    except urllib.error.HTTPError as e:
        return e.code, dict(e.headers), e.read()


def jget(status: int, payload: bytes):
    try:
        return json.loads(payload.decode("utf-8"))
    except Exception:  # noqa: BLE001
        return {}


def upload(name: str, data: bytes, mime: str = "video/mp4"):
    """手搓 multipart：不引第三方库，和 verify_account.py 的做法一致。"""
    boundary = "----faVision" + uuid.uuid4().hex
    parts = [
        f"--{boundary}\r\n".encode(),
        f'Content-Disposition: form-data; name="file"; filename="{name}"\r\n'.encode(),
        f"Content-Type: {mime}\r\n\r\n".encode(),
        data,
        f"\r\n--{boundary}--\r\n".encode(),
    ]
    return request("POST", "/api/vision/videos", token=TOKEN, raw=b"".join(parts),
                   content_type=f"multipart/form-data; boundary={boundary}")


def main() -> int:
    global TOKEN
    if not FIXTURE.exists():
        print(f"[FAIL] 找不到测试样本 {FIXTURE}")
        return 1

    print(f"[info] 目标 {BASE}")
    status, _, payload = request("GET", "/api/vision/overview")
    check("未登录访问概览返回 401", status == 401, f"HTTP {status}")

    TOKEN = _uiauth.login(base=BASE)["token"]

    status, _, payload = request("GET", "/api/vision/overview", token=TOKEN)
    ov = jget(status, payload)
    check("登录后概览 200", status == 200, f"HTTP {status}")
    check("概览带 server/defaults/videos/jobs/worker",
          all(k in ov for k in ("server", "defaults", "videos", "jobs", "worker")), str(list(ov))[:120])
    defaults = ov.get("defaults", {})
    check("默认抽样间隔 5 帧", defaults.get("step") == 5, str(defaults.get("step")))
    check("默认扩展名含 .mp4", ".mp4" in (defaults.get("exts") or []), str(defaults.get("exts"))[:80])
    check("server.can_process 是布尔", isinstance(ov.get("server", {}).get("can_process"), bool),
          str(ov.get("server")))
    worker = ov.get("worker", {})
    check("worker 有心跳字段(online/heartbeat_age)", "online" in worker and "heartbeat_age" in worker,
          str(list(worker))[:80])

    baseline = (ov.get("videos") or {}).get("total", 0)

    status, _, payload = request("GET", "/api/vision/videos", token=TOKEN)
    lst = jget(status, payload)
    check("视频列表 200", status == 200, f"HTTP {status}")
    check("列表 total 与 items 一致", lst.get("total") == len(lst.get("items") or []),
          f'{lst.get("total")} vs {len(lst.get("items") or [])}')

    # ---------- 上传 ----------
    data = FIXTURE.read_bytes()
    status, _, payload = upload("tiny.mp4", data)
    vid = jget(status, payload)
    check("上传 mp4 返回 201", status == 201, f"HTTP {status} {payload[:120]}")
    video_id = vid.get("video_id")
    check("上传后状态 uploaded", vid.get("status") == "uploaded", str(vid.get("status")))
    check("落库字节数与文件一致", vid.get("size_bytes") == len(data), f'{vid.get("size_bytes")} vs {len(data)}')
    if vid.get("width") and vid.get("frames"):
        check("元数据探测正确(160x120/10fps/10 帧)",
              vid.get("width") == 160 and vid.get("height") == 120 and vid.get("fps") == 10.0 and vid.get("frames") == 10,
              f'{vid.get("width")}x{vid.get("height")} {vid.get("fps")}fps {vid.get("frames")}f')
    else:
        skip("元数据探测正确(160x120/10fps/10 帧)", "服务端没装 opencv，探测被跳过")

    try:
        status, _, _ = upload("note.txt", b"not a video")
        check("拒绝非视频扩展名(400)", status == 400, f"HTTP {status}")
        status, _, _ = upload("empty.mp4", b"")
        check("拒绝空文件(400)", status == 400, f"HTTP {status}")

        # ---------- 排队 ----------
        status, _, _ = request("POST", "/api/vision/videos/999999/process", token=TOKEN, body={"step": 5})
        check("给不存在的视频排队返回 404", status == 404, f"HTTP {status}")

        status, _, payload = request("POST", f"/api/vision/videos/{video_id}/process", token=TOKEN, body={"step": 5})
        job = jget(status, payload)
        check("排队成功返回 201", status == 201, f"HTTP {status} {payload[:120]}")
        job_id = job.get("job_id")
        check("任务初始状态 queued", job.get("status") == "queued", str(job.get("status")))
        check("任务 step 按请求记录", job.get("step") == 5, str(job.get("step")))
        check("任务 frames_total 与视频帧数一致", job.get("frames_total") in (None, 10),
              f'{job.get("frames_total")}')

        status, _, _ = request("POST", f"/api/vision/videos/{video_id}/process", token=TOKEN, body={"step": 5})
        check("同一视频重复排队返回 409", status == 409, f"HTTP {status}")

        status, _, _ = request("POST", f"/api/vision/videos/{video_id}/process", token=TOKEN, body={"step": 0})
        check("step 越界返回 400", status == 400, f"HTTP {status}")

        status, _, payload = request("GET", f"/api/vision/jobs/{job_id}", token=TOKEN)
        job2 = jget(status, payload)
        check("任务进度接口 200", status == 200, f"HTTP {status}")
        check("排队中进度为 0", job2.get("progress") == 0.0, str(job2.get("progress")))

        status, _, _ = request("GET", f"/api/vision/videos/{video_id}/tracks", token=TOKEN)
        check("没跑完时取轨迹返回 404", status == 404, f"HTTP {status}")
        status, _, _ = request("GET", f"/api/vision/videos/{video_id}/summary", token=TOKEN)
        check("没跑完时取指标返回 404", status == 404, f"HTTP {status}")

        # ---------- 媒体流 ----------
        status, _, _ = request("GET", f"/api/vision/videos/{video_id}/stream")
        check("视频流不带 token 返回 401", status == 401, f"HTTP {status}")
        status, headers, body = request("GET", f"/api/vision/videos/{video_id}/stream?token={TOKEN}")
        check("视频流带 token 返回 200", status == 200, f"HTTP {status}")
        ctype = next((v for k, v in headers.items() if k.lower() == "content-type"), "")
        check("视频流 Content-Type 是视频", str(ctype).startswith("video/"), str(ctype))
        check("视频流字节数与原文件一致", len(body) == len(data), f"{len(body)} vs {len(data)}")
        status, _, _ = request("GET", f"/api/vision/videos/{video_id}/overlay?token={TOKEN}")
        check("还没生成带框视频时返回 404", status == 404, f"HTTP {status}")

        # ---------- 取消 / 删除 ----------
        status, _, payload = request("POST", f"/api/vision/jobs/{job_id}/cancel", token=TOKEN)
        check("取消任务 200", status == 200, f"HTTP {status}")
        check("取消后状态 canceled", jget(status, payload).get("status") == "canceled",
              str(jget(status, payload).get("status")))
        status, _, _ = request("POST", f"/api/vision/jobs/{job_id}/cancel", token=TOKEN)
        check("重复取消返回 409", status == 409, f"HTTP {status}")

        status, _, payload = request("POST", f"/api/vision/videos/{video_id}/process", token=TOKEN, body={"step": 5})
        check("取消后可以再排队(201)", status == 201, f"HTTP {status}")
        job3 = jget(status, payload).get("job_id")

        status, _, _ = request("DELETE", f"/api/vision/videos/{video_id}", token=TOKEN)
        check("有任务排队时删除返回 409", status == 409, f"HTTP {status}")
        request("POST", f"/api/vision/jobs/{job3}/cancel", token=TOKEN)

        status, _, _ = request("DELETE", f"/api/vision/videos/{video_id}", token=TOKEN)
        check("取消后删除 200", status == 200, f"HTTP {status}")
        status, _, _ = request("GET", f"/api/vision/videos/{video_id}/summary", token=TOKEN)
        check("删除后再取摘要返回 404", status == 404, f"HTTP {status}")

        status, _, payload = request("GET", "/api/vision/overview", token=TOKEN)
        ov2 = jget(status, payload)
        check("删除后视频总数回到基线", (ov2.get("videos") or {}).get("total") == baseline,
              f'{(ov2.get("videos") or {}).get("total")} vs {baseline}')
    finally:
        # 半路失败也别留垃圾
        request("DELETE", f"/api/vision/videos/{video_id}", token=TOKEN)

    total = len(PASSED) + len(FAILED)
    print(f"\n[汇总] 通过 {len(PASSED)} / 失败 {len(FAILED)} / 跳过 {len(SKIPPED)}（共 {total} 项断言）")
    if FAILED:
        print("[失败项] " + "; ".join(FAILED))
    return 0 if not FAILED else 1


if __name__ == "__main__":
    sys.exit(main())
