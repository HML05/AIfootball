"""把「视频链接」抓成本地片段，喂给 src/vision。

为什么单独一个脚本：
  - 用户手上通常是**网页链接**（B 站 / 腾讯视频 / 抖音），不是 mp4 直链；
  - cv2 在 Windows 上打不开中文路径，所以落地文件名强制 ASCII；
  - 只需要 30~120 秒，整段下载纯属浪费，所以支持 --start/--duration 只取一段。

用法：
  python scripts/vision_fetch.py "<链接>" --list          # 先看有哪些清晰度
  python scripts/vision_fetch.py "<链接>" --start 01:20 --duration 60 --max-height 1080
  python scripts/vision_fetch.py "<mp4 直链>" --name match1

依赖：yt-dlp（+ ffmpeg 合并音视频；没装 PATH 里的话用 imageio-ffmpeg 自带的那个）。
版权：抓下来的片段只落 data/vision/（已 gitignore），不进仓库、不进 Release、不进论文附录。
"""

from __future__ import annotations

import argparse
import hashlib
import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

DEFAULT_OUT = ROOT / "data" / "vision" / "videos"


def _ffmpeg_location() -> str | None:
    """把 ffmpeg 弄到「yt-dlp 能找到」的地方，返回它所在目录（找不到返回 None）。

    两个坑叠在一起：
      1. yt-dlp 会在目录里找**名字就叫 ffmpeg.exe** 的文件，而 imageio-ffmpeg 给的文件名是
         `ffmpeg-win-x86_64-v7.1.exe`，直接喂路径 → 一直报「ffmpeg is not installed」；
      2. 只传 `ffmpeg_location` 参数时，`--start/--duration` 这种「部分下载」在解析阶段就要
         判断 ffmpeg 在不在，那一刻还没用上这个参数。
    所以既复制改名，又把它塞进 PATH（双保险），再返回目录。
    """
    from shutil import copy2, which

    if which("ffmpeg"):
        return None
    try:
        import imageio_ffmpeg

        src = Path(imageio_ffmpeg.get_ffmpeg_exe())
    except Exception:  # noqa: BLE001 — 没装就是没有，交给 yt-dlp 报错
        return None
    bin_dir = ROOT / "data" / "vision" / ".bin"
    bin_dir.mkdir(parents=True, exist_ok=True)
    dst = bin_dir / "ffmpeg.exe"
    if not dst.exists() or dst.stat().st_size != src.stat().st_size:
        copy2(src, dst)
    os.environ["PATH"] = str(bin_dir) + os.pathsep + os.environ.get("PATH", "")
    return str(bin_dir)


def ascii_name(title: str, fallback: str = "clip") -> str:
    """把标题变成安全的 ASCII 文件名（opencv 读不了中文路径）。"""
    stem = re.sub(r"[^0-9A-Za-z_-]+", "_", title or "").strip("_")[:40]
    if len(stem) < 3:  # "英超 第3轮" 会被抠成一个 "3"，这种名字不如用哈希
        stem = hashlib.md5((title or fallback).encode("utf-8")).hexdigest()[:8]
    return stem.lower()


def _parse_ts(text: str) -> float:
    """"83" / "1:23" / "01:02:03" 都接受，返回秒。"""
    parts = [p for p in str(text).split(":") if p != ""]
    total = 0.0
    for p in parts:
        total = total * 60 + float(p)
    return total


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="抓取视频链接的一段到 data/vision/videos")
    ap.add_argument("url", help="网页链接或 mp4 直链")
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="落地目录（默认 data/vision/videos）")
    ap.add_argument("--name", default=None, help="文件名（不含扩展名；默认按标题生成 ASCII 名）")
    ap.add_argument("--start", default=None, help="从第几秒/几分几秒开始，如 90 或 01:30")
    ap.add_argument("--duration", default=None, help="只要多少秒，如 60")
    ap.add_argument("--max-height", type=int, default=1080, help="清晰度上限（默认 1080）")
    ap.add_argument("--list", action="store_true", help="只列出可用清晰度，不下载")
    args = ap.parse_args(argv)

    try:
        import yt_dlp
    except ImportError:
        print("[!] 没装 yt-dlp：python -m pip install -i https://pypi.tuna.tsinghua.edu.cn/simple yt-dlp",
              file=sys.stderr)
        return 2

    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)
    ffmpeg = _ffmpeg_location()

    common: dict = {"quiet": True, "no_warnings": True, "noprogress": True, "noplaylist": True}
    if ffmpeg:
        common["ffmpeg_location"] = ffmpeg

    if args.list:
        with yt_dlp.YoutubeDL({**common, "skip_download": True}) as ydl:
            info = ydl.extract_info(args.url, download=False)
        heights = sorted({f.get("height") for f in info.get("formats") or [] if f.get("height")})
        print(f"标题: {info.get('title')}")
        print(f"作者: {info.get('uploader')}   时长: {info.get('duration')} 秒")
        print(f"可用清晰度: {heights or '未知（可能是直链）'}")
        return 0

    name = args.name or ascii_name(args.url.split("/")[-1] if args.name is None else args.name)
    opts: dict = {
        **common,
        "format": f"bv*[height<={args.max_height}]+ba/b[height<={args.max_height}]/b",
        "merge_output_format": "mp4",
        "outtmpl": str(out_dir / f"{name}.%(ext)s"),
    }
    if args.start or args.duration:
        start = _parse_ts(args.start) if args.start else 0.0
        end = start + float(args.duration) if args.duration else None
        opts["download_ranges"] = yt_dlp.utils.download_range_func(None, [(start, end)])
        opts["force_keyframes_at_cuts"] = True

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(args.url, download=True)
        path = Path(ydl.prepare_filename(info))
    if not path.exists():
        cands = sorted(out_dir.glob(f"{name}.*"))
        path = cands[0] if cands else path
    size = path.stat().st_size / 1024 / 1024
    print(f"[ok] {path}  {size:.1f} MB")
    print(f"     下一步: .venv-vision\\Scripts\\python.exe scripts\\vision_smoke.py \"{path}\" --overlay")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
