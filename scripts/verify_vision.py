"""视觉模块自检：不依赖 torch / ultralytics 也能跑（有 cv2 就跑视频相关的那几项）。

用法：
    python scripts/verify_vision.py          # 用系统 Python（无 cv2 时相关项标 SKIP）
    .venv-vision\\Scripts\\python.exe scripts\\verify_vision.py   # 全项都跑

为什么这么设计：CI 的 static job 只装 requirements.txt，没有 cv2/ultralytics；
把「纯逻辑」和「要重依赖的」分开，才能在两边都给出可复跑的结论。
"""
from __future__ import annotations

import os
import shutil
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from src.vision import config, metrics  # noqa: E402
from src.vision import io as vio  # noqa: E402

PASSED = FAILED = SKIPPED = 0


def check(label: str, cond: bool, detail: str = "") -> None:
    global PASSED, FAILED
    if cond:
        PASSED += 1
        print(f"  [ok]   {label}" + (f" — {detail}" if detail else ""))
    else:
        FAILED += 1
        print(f"  [FAIL] {label}" + (f" — {detail}" if detail else ""))


def skip(label: str, why: str) -> None:
    global SKIPPED
    SKIPPED += 1
    print(f"  [skip] {label} — {why}")


def has_module(name: str) -> bool:
    from importlib import util

    return util.find_spec(name) is not None


# ---------------------------------------------------------------- 假数据
def fake_tracks(frames: int = 150, people: int = 3, ball_every: int = 3) -> list[dict]:
    out = []
    for f in range(frames):
        boxes = [
            {
                "id": k + 1, "cls": 0, "name": "person", "conf": 0.9,
                "xyxy": [100 + k * 300, 360, 140 + k * 300, 460],
            }
            for k in range(people)
        ]
        if ball_every and f % ball_every == 0:
            boxes.append(
                {"id": None, "cls": 32, "name": "sports ball", "conf": 0.4, "xyxy": [600, 420, 610, 430]}
            )
        out.append({"frame": f, "boxes": boxes})
    return out


class _Tensor:
    """够用的假 tensor：只要 .tolist()。"""

    def __init__(self, data):
        self._d = data

    def tolist(self):
        return self._d


class _Boxes:
    def __init__(self, xyxy, conf, cls, ids=None):
        self.xyxy = _Tensor(xyxy)
        self.conf = _Tensor(conf)
        self.cls = _Tensor(cls)
        self.id = None if ids is None else _Tensor(ids)

    def __len__(self):
        return len(self.xyxy._d)


class _Result:
    def __init__(self, boxes, names=None):
        self.boxes = boxes
        self.names = names or {0: "person", 32: "sports ball"}


# ---------------------------------------------------------------- 各项自检
def check_config() -> None:
    print("\n[1] config")
    check("BASE_DIR 指向仓库根", (config.BASE_DIR / "README.md").exists(), str(config.BASE_DIR))
    vision_dir = str(config.VISION_DIR).replace("\\", "/")
    # 默认落在 data/vision；用 VISION_DIR 覆盖时（换盘、或环境只允许写某个目录）也算通过
    override = os.environ.get("VISION_DIR")
    if override:
        check("VISION_DIR 被环境变量覆盖",
              os.path.normcase(str(config.VISION_DIR)) == os.path.normcase(override), vision_dir)
    else:
        check("数据目录在 data/vision 下", vision_dir.endswith("data/vision"), vision_dir)
    weight_dir = str(config.WEIGHT_DIR).replace("\\", "/")
    check("权重目录在 models/vision 下", weight_dir.endswith("models/vision"), weight_dir)
    config.ensure_dirs()
    check("ensure_dirs 建出 6 个目录", all(d.is_dir() for d in config.DIRS), f"{len(config.DIRS)} 个")
    info = config.describe()
    check("describe 带 model/imgsz/conf", {"model", "imgsz", "conf"} <= set(info), info["model"])
    check("所有输出目录都在仓库内", all(str(d).startswith(str(config.BASE_DIR)) for d in config.DIRS))


def check_metrics() -> None:
    print("\n[2] metrics（纯逻辑，无重依赖）")
    tracks = fake_tracks()
    s = metrics.summarize(tracks, {"fps": 25.0}, elapsed=2.0)
    check("帧数", s["frames_processed"] == 150, str(s["frames_processed"]))
    check("平均人数 3", s["person"]["per_frame_mean"] == 3.0, str(s["person"]["per_frame_mean"]))
    check("唯一 ID 3", s["tracking"]["unique_ids"] == 3, str(s["tracking"]["unique_ids"]))
    check("碎裂比 1.0", s["tracking"]["fragmentation"] == 1.0, str(s["tracking"]["fragmentation"]))
    check("ID 中位存活 150 帧", s["tracking"]["id_lifetime_median"] == 150, str(s["tracking"]["id_lifetime_median"]))
    check("球覆盖率 33.33%", s["ball"]["frames_with_ball_pct"] == 33.33, str(s["ball"]["frames_with_ball_pct"]))
    check("球最长连续段 = 1", s["ball"]["longest_consecutive_run"] == 1, str(s["ball"]["longest_consecutive_run"]))
    check("框高全落 near 档", s["box_height_px"]["buckets_pct"]["near"] == 100.0, str(s["box_height_px"]["buckets"]))
    check("速度 75 帧/秒", s["speed"]["fps_processed"] == 75.0, str(s["speed"]))
    check("含「无 GT」的提示", any("mAP" in n for n in s["notes"]), s["notes"][0][:24])
    rows = metrics.verdict(s)
    check("verdict 5 行", len(rows) == 5, str(len(rows)))
    check("verdict 用标记而不是布尔", all(r[0] in ("OK  ", "不行", "待看 ") for r in rows), rows[0][0])
    empty = metrics.summarize([], {}, elapsed=0.0)
    check("空轨迹不崩", empty["frames_processed"] == 0 and empty["tracking"]["fragmentation"] is None)
    # 每帧 2 个人、但 ID 一直在换（1..6）→ 唯一 6 / 单帧 2 = 3.0，正好卡在"可接受"上限
    churn = [
        {"frame": f, "boxes": [
            {"id": 1 + (f * 2) % 6, "cls": 0, "name": "person", "conf": 0.8, "xyxy": [0, 0, 40, 100]},
            {"id": 1 + (f * 2 + 1) % 6, "cls": 0, "name": "person", "conf": 0.8, "xyxy": [50, 0, 90, 100]},
        ]}
        for f in range(12)
    ]
    check("碎裂比能反映 ID 跳变", metrics.summarize(churn, {})["tracking"]["fragmentation"] == 3.0,
          str(metrics.summarize(churn, {})["tracking"]["fragmentation"]))


def _tmpdir() -> tempfile.TemporaryDirectory:
    """临时目录优先放在 data/vision/out/_verify 下。

    为什么不直接用系统临时目录：部分受限环境（沙箱/公司策略）只允许写工作目录，
    %TEMP% 会被拒；放在项目自己的输出目录里两种情况都能跑，退出时一样自动清理。
    """
    base = Path(config.OUT_DIR) / "_verify"
    try:
        base.mkdir(parents=True, exist_ok=True)
        return tempfile.TemporaryDirectory(dir=base)
    except OSError:
        return tempfile.TemporaryDirectory()


def check_io() -> None:
    print("\n[3] io：轨迹 JSON")
    from scripts.vision_smoke import make_demo_clip as _demo_clip

    tracks = fake_tracks(10)
    with _tmpdir() as tmp:
        p1 = vio.dump_json(Path(tmp) / "t.json", tracks)
        check("普通 JSON 往返", vio.load_json(p1) == tracks, f"{p1.stat().st_size} B")
        p2 = vio.dump_json(Path(tmp) / "t.json.gz", tracks)
        check("gzip JSON 往返", vio.load_json(p2) == tracks, f"{p2.stat().st_size} B")
        check("gzip 比明文小", p2.stat().st_size < p1.stat().st_size, f"{p2.stat().st_size} < {p1.stat().st_size}")
        check("自动建父目录", (Path(tmp) / "t.json.gz").exists())
        # 中文文件名：opencv 在 Windows 上打不开，所以输出名要过 safe_stem
        check("safe_stem 保留 ASCII 名", vio.safe_stem("match_1.mp4") == "match_1", vio.safe_stem("match_1.mp4"))
        cn = vio.safe_stem("英超 第3轮.mp4")
        check("safe_stem 把中文换成 clip_哈希", cn.startswith("clip_") and cn.isascii() and len(cn) == 13, cn)
        check("safe_stem 同源同名结果稳定", vio.safe_stem("英超 第3轮.mp4") == cn)

    if not has_module("cv2"):
        skip("probe_video / write_overlay", "当前解释器没有 cv2（系统 Python 就没装）")
        return

    with _tmpdir() as tmp:
        clip_cn = Path(tmp) / "中文片段.mp4"
        shutil.copy2(_demo_clip(Path(tmp) / "asrc.mp4", seconds=1, fps=10), clip_cn)
        ascii_clip = vio.ascii_video_path(clip_cn, Path(tmp) / "_ascii")
        check("ascii_video_path 换成 ASCII 文件名",
              ascii_clip.name.isascii() and ascii_clip.exists(), ascii_clip.name)
        check("改道后的视频能正常读帧", vio.probe_video(ascii_clip)["frames"] == 10,
              str(vio.probe_video(ascii_clip)["frames"]))

    with _tmpdir() as tmp:
        clip = _demo_clip(Path(tmp) / "demo.mp4", seconds=2, fps=10)
        meta = vio.probe_video(clip)
        check("probe_video 读出尺寸", meta["width"] == 1280 and meta["height"] == 720, f"{meta['width']}x{meta['height']}")
        check("probe_video 读出帧数", meta["frames"] == 20, str(meta["frames"]))
        frames = list(vio.iter_frames(clip, step=5))
        check("iter_frames 按 step 取帧", [i for i, _ in frames] == [0, 5, 10, 15], str([i for i, _ in frames]))
        overlay = vio.write_overlay(clip, fake_tracks(20), Path(tmp) / "ov.mp4", fps=meta["fps"], limit=20)
        check("带框视频写出来了", overlay.stat().st_size > 0, f"{overlay.stat().st_size} B")
        s = metrics.summarize(fake_tracks(20), meta)
        check("metrics 吃 probe_video 的 meta", s["video"]["width"] == 1280)


def check_detector() -> None:
    print("\n[4] detector：结构与依赖报错")
    from src.vision import detector as vd

    try:
        vd._import_yolo()
        have = True
    except vd.VisionDependencyError as exc:
        have = False
        ok_msg = "vision_setup.ps1" in str(exc) and "requirements-vision.txt" in str(exc)
        check("缺 ultralytics 时给出可照抄的修复命令", ok_msg, str(exc).splitlines()[0])
    if have:
        check("装了 ultralytics 能拿到 YOLO 类", True, "本环境已安装")

    d = vd.Detector()
    check("默认参数与 config 一致", d.model == config.DEFAULT_MODEL and d.imgsz == config.DEFAULT_IMGSZ)
    res = _Result(
        _Boxes(
            xyxy=[[10.0, 20.0, 50.0, 120.0], [600.0, 400.0, 610.0, 410.0]],
            conf=[0.91, 0.42],
            cls=[0, 32],
            ids=[7, None],
        )
    )
    frame = vd._frame_dict(0, res)
    check("_frame_dict 带出跟踪 ID", frame["boxes"][0]["id"] == 7, str(frame["boxes"][0]["id"]))
    check("_frame_dict 无 ID 时为 None", frame["boxes"][1]["id"] is None)
    check("_frame_dict 带类别名", frame["boxes"][1]["name"] == "sports ball", frame["boxes"][1]["name"])
    check("_frame_dict 置信度保留 4 位", frame["boxes"][0]["conf"] == 0.91, str(frame["boxes"][0]["conf"]))
    empty = vd._frame_dict(3, _Result(_Boxes([], [], [])))
    check("空帧不崩", empty == {"frame": 3, "boxes": []}, str(empty))


def check_prelabel() -> None:
    print("\n[5] prelabel：YOLO 标签换算")
    from scripts.vision_prelabel import in_roi, parse_map, parse_roi, to_yolo_line

    check("parse_map 解析映射", parse_map("0:0,32:1") == {0: 0, 32: 1})
    line = to_yolo_line({"xyxy": [100, 100, 300, 400]}, 1000, 1000, 0)
    parts = line.split()
    check("归一化中心点", parts[1:] == ["0.200000", "0.250000", "0.200000", "0.300000"], line)
    out = to_yolo_line({"xyxy": [-10, -10, 1010, 1010]}, 1000, 1000, 1)
    check("越界坐标被夹到 [0,1]", all(0.0 <= float(v) <= 1.0 for v in out.split()[1:]), out)
    check("类别号生效", out.startswith("1 "), out)

    # --roi 把看台/替补席上的人从预标注里剔掉；框中心点判断，空串表示不过滤
    roial = parse_roi("0.1,0.2,0.9,0.8")
    check("parse_roi 解析四段", roial == (0.1, 0.2, 0.9, 0.8), roial)
    check("parse_roi 空串不过滤", parse_roi("") is None)
    check("in_roi 场内框保留", in_roi({"xyxy": [400, 400, 600, 700]}, 1000, 1000, roial))
    check("in_roi 看台框剔除", not in_roi({"xyxy": [400, 20, 460, 90]}, 1000, 1000, roial))
    try:
        parse_roi("0.1,0.2,0.9")
        check("parse_roi 段数不对要报错", False, "没有抛错")
    except SystemExit:
        check("parse_roi 段数不对要报错", True)


def check_fetch() -> None:
    print("\n[6] vision_fetch：文件名与时间解析")
    from scripts.vision_fetch import _parse_ts, ascii_name

    check("_parse_ts 纯秒", _parse_ts("83") == 83, _parse_ts("83"))
    check("_parse_ts 分:秒", _parse_ts("1:23") == 83, _parse_ts("1:23"))
    check("_parse_ts 时:分:秒", _parse_ts("1:02:03") == 3723, _parse_ts("1:02:03"))
    check("ascii_name 保留 ASCII 名", ascii_name("match_1") == "match_1", ascii_name("match_1"))
    cn = ascii_name("英超 第3轮")
    check("ascii_name 中文回退成哈希", cn.isascii() and len(cn) == 8, cn)


def check_pitch() -> None:
    print("\n[7] pitch：标定与米制统计")
    import numpy as np

    from src.vision import pitch as vpitch

    # 已知变换：米 → 像素做一次仿射+缩放，再标定回来，误差应该是 0（数值噪声级）
    h_known = np.array([[2.0, 0.0, 300.0], [0.0, 2.0, 120.0], [0.0, 0.0, 1.0]])
    pairs = []
    for x, y in [(0, 0), (105, 0), (105, 68), (0, 68)]:
        u = 2.0 * x + 300.0
        v = 2.0 * y + 120.0
        pairs.append(((u, v), (float(x), float(y))))
    cal = vpitch.build_calibration(pairs)
    errs = []
    for (u, v), (x, y) in pairs:
        px, py = cal.pixel_to_pitch(u, v)
        errs.append(((px - x) ** 2 + (py - y) ** 2) ** 0.5)
    check("4 点 DLT 还原已知变换", max(errs) < 1e-6, f"最大误差 {max(errs):.2e} 米")
    check("标定矩阵是 3×3", cal.homography.shape == (3, 3), str(cal.homography.shape))

    try:
        vpitch.homography_from_points(pairs[:3])
        check("少于 4 点要报错", False, "没有抛错")
    except ValueError:
        check("少于 4 点要报错", True)

    with tempfile.TemporaryDirectory() as tmp:
        p = vpitch.save_calibration(cal, Path(tmp) / "cal.json")
        back = vpitch.load_calibration(p)
        a = back.pixel_to_pitch(500.0, 300.0)
        b = cal.pixel_to_pitch(500.0, 300.0)
        check("标定 JSON 存读一致", abs(a[0] - b[0]) < 1e-6 and abs(a[1] - b[1]) < 1e-6, f"{a[0]:.3f},{a[1]:.3f}")

    check(
        "取脚点（框底边中点）",
        vpitch.feet_point({"xyxy": [100, 200, 160, 300]}) == (130.0, 300.0),
        str(vpitch.feet_point({"xyxy": [100, 200, 160, 300]})),
    )

    # 每秒 10 米直线跑 3 秒 = 30 米；25 fps → 每帧 0.04 秒、每帧走 0.4 米
    pts = [(i * 0.04, 10.0 + 0.4 * i, 20.0) for i in range(76)]
    stats = vpitch.motion_stats({7: pts})
    st = stats[0]
    check("距离累加正确", abs(st.distance_m - 30.0) < 0.1, f"{st.distance_m:.2f} 米")
    check("均速正确", abs(st.avg_speed - 10.0) < 0.1, f"{st.avg_speed:.2f} m/s")
    check("最高速正确", abs(st.max_speed - 10.0) < 0.1, f"{st.max_speed:.2f} m/s")

    jump = [(0.0, 10.0, 10.0), (0.04, 90.0, 60.0), (0.08, 90.4, 60.0)]
    st2 = vpitch.motion_stats({9: jump})[0]
    check(
        "超人类速度的跳变被丢弃、后续正常帧仍计入",
        st2.rejected == 1 and abs(st2.distance_m - 0.4) < 0.01,
        f"rejected {st2.rejected} / {st2.distance_m:.2f} 米",
    )
    far = [(0.0, 5.0, 5.0), (0.04, 300.0, 5.0)]
    check("跑出球场外 8 米的点被跳过", vpitch.motion_stats({3: far})[0].distance_m == 0.0)

    holders = {1: [(0.0, 10.0, 10.0), (0.04, 10.1, 10.0), (0.08, 10.2, 10.0)]}
    near = vpitch.possession(holders, [(0.0, 10.5, 10.5), (0.04, 10.6, 10.5), (0.08, 50.0, 50.0)])
    check("控球归属（半径内算控球）", near["owned_frames"] == 2 and near["unowned_frames"] == 1, str(near["owned_frames"]))
    check("控球百分比分母含无人控球帧", near["owned_pct"] == round(100.0 * 2 / 3, 2), str(near["owned_pct"]))


def check_teams() -> None:
    print("[8] teams 球衣分队")
    import numpy as np

    from src.vision import teams as vteams

    # 两支球衣颜色各 8 条轨迹、每条 6 次采样；第 17~18 条是裁判（深色），应当被踢出两队
    red = np.array([0.60, 0.28, 0.35], dtype=np.float32)
    blue = np.array([0.20, 0.45, 0.35], dtype=np.float32)
    dark = np.array([0.34, 0.32, 0.10], dtype=np.float32)
    samples: dict[int, list] = {}
    for tid in range(8):
        samples[tid] = [red + np.float32(i) * 0.001 for i in range(6)]
    for tid in range(8, 16):
        samples[tid] = [blue + np.float32(i) * 0.001 for i in range(6)]
    for tid in (16, 17, 18):
        samples[tid] = [dark + np.float32(i) * 0.001 for i in range(6)]

    res = vteams.assign_teams(samples)
    teams = res["teams"]
    check("两支主队各自成一组", len({teams[t] for t in range(8)}) == 1 and len({teams[t] for t in range(8, 16)}) == 1)
    check("红队与蓝队不在同组", teams[0] != teams[8])
    check("深色（裁判）不塞进两队", all(t in res["other"] for t in (16, 17, 18)), str(res["other"]))
    check("质心是 3 维（色度 + 亮度）", all(len(c) == 3 for c in res["centers"]))
    check("同一份输入结果稳定", vteams.assign_teams(samples)["teams"] == teams)
    check("采样不足的轨迹被跳过", vteams.assign_teams({**samples, 99: [red] * 2})["skipped"] == [99])
    try:
        vteams.assign_teams({i: [red + np.float32(i) * 0.001 for _ in range(6)] for i in range(8)})
        same = False
    except vteams.TeamError:
        same = True
    check("全是一种颜色时会明确报错，而不是硬分两队", same)

    # 躯干裁剪：只取框的上半部分，且不会越界
    x1, y1, x2, y2 = vteams.torso_box((10, 100, 50, 200))
    check("躯干框在人物框上半部", y1 >= 100 and y2 <= 200 and y2 - y1 < 100, f"{x1},{y1},{x2},{y2}")
    check("退化框不会算出负高度", vteams.torso_box((0, 0, 10, 2))[3] > vteams.torso_box((0, 0, 10, 2))[1])


def check_calibration_metric() -> None:
    print("[9] 标定判据（合成图，验证「白漆命中率」本身可信）")
    if not has_module("cv2"):
        skip("标定判据整体", "没装 cv2")
        return
    import cv2
    import numpy as np

    from scripts import vision_calibrate as vcal
    from src.vision import pitch as vpitch

    # 造一张「已知单应」的假球场：绿底 + 白线，再让判据给它打分。
    # 判据可信的标志是：正确单应接近满分，整体平移 50 px 立刻掉到接近 0。
    width, height = 1920, 1080
    pair_px = [(200.0, 150.0), (1750.0, 220.0), (1800.0, 1000.0), (120.0, 900.0)]
    pair_m = [vpitch.ANCHORS[n] for n in ("corner_tl", "corner_tr", "corner_br", "corner_bl")]
    h_true = vpitch.homography_from_points(list(zip(pair_px, pair_m)))
    h_inv = np.linalg.inv(h_true)

    img = np.zeros((height, width, 3), dtype=np.uint8)
    img[:] = (60, 140, 60)

    def to_px(x, y):
        q = h_inv @ np.array([x, y, 1.0])
        return int(q[0] / q[2]), int(q[1] / q[2])

    def seg(x0, y0, x1, y1, n=40):
        return [(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1)]

    cy = 34.0
    polylines = [
        seg(0, 0, 105, 0) + seg(105, 0, 105, 68) + seg(105, 68, 0, 68) + seg(0, 68, 0, 0),
        seg(52.5, 0, 52.5, 68),
        seg(0, cy - 20.16, 16.5, cy - 20.16) + seg(16.5, cy - 20.16, 16.5, cy + 20.16) + seg(16.5, cy + 20.16, 0, cy + 20.16),
        seg(105, cy - 20.16, 88.5, cy - 20.16) + seg(88.5, cy - 20.16, 88.5, cy + 20.16) + seg(88.5, cy + 20.16, 105, cy + 20.16),
        seg(0, cy - 9.16, 5.5, cy - 9.16) + seg(5.5, cy - 9.16, 5.5, cy + 9.16) + seg(5.5, cy + 9.16, 0, cy + 9.16),
        seg(105, cy - 9.16, 99.5, cy - 9.16) + seg(99.5, cy - 9.16, 99.5, cy + 9.16) + seg(99.5, cy + 9.16, 105, cy + 9.16),
        [(52.5 + 9.15 * np.cos(2 * np.pi * i / 120), cy + 9.15 * np.sin(2 * np.pi * i / 120)) for i in range(121)],
    ]
    for line in polylines:
        for i in range(len(line) - 1):
            cv2.line(img, to_px(*line[i]), to_px(*line[i + 1]), (255, 255, 255), 3, cv2.LINE_AA)

    hit, ctrl, detail = vcal._line_hit_ratio(img, h_true)
    check("正确单应白漆命中率 ≥ 阈值", hit >= vcal.MIN_LINE_HIT, f"{hit * 100:.0f}%")
    check("每条场地线都压在白漆上", all(r >= vcal.MIN_LINE_EACH for _, r in detail),
          "、".join(f"{n} {r * 100:.0f}%" for n, r in detail))
    shifted = np.roll(img, 50, axis=1)
    hit2, _, _ = vcal._line_hit_ratio(shifted, h_true)
    check("整体平移 50 px 后命中率崩塌（判据有分辨力）", hit - hit2 > 0.5, f"{hit2 * 100:.0f}%")
    check("对照组不会高过正确解", hit >= ctrl, f"hit {hit * 100:.0f}% vs ctrl {ctrl * 100:.0f}%")


def main() -> int:
    print(f"视觉模块自检（解释器：{sys.version.split()[0]}）")
    check_config()
    check_metrics()
    check_io()
    check_detector()
    check_prelabel()
    check_fetch()
    check_pitch()
    check_teams()
    check_calibration_metric()
    print(f"\n合计：{PASSED} 通过 / {FAILED} 失败 / {SKIPPED} 跳过")
    return 1 if FAILED else 0


if __name__ == "__main__":
    raise SystemExit(main())
