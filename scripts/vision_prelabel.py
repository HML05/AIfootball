"""用预训练的 YOLOv8 给抽好的帧做预标注，产出 YOLO 格式的 txt。

它的作用是把「从零画 300~800 个框」变成「检查并修正错框」——
足球画面里人几乎都能被 COCO 模型检到，所以人框基本可用；
球是重灾区，预标注漏掉的要自己补，这也是后面微调的主要收益点。

用法：
    .venv-vision\\Scripts\\python.exe scripts\\vision_prelabel.py --src data\\vision\\frames\\clip
    ... --dataset-root data\\vision\\dataset   # 同时拼出 images/ labels/ data.yaml
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except (AttributeError, OSError):  # pragma: no cover
    pass

from src.vision import config, io  # noqa: E402

IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".bmp"}
DEFAULT_NAMES = {0: "player", 1: "ball"}


def parse_map(text: str) -> dict[int, int]:
    """'0:0,32:1' → {0: 0, 32: 1}（COCO 类别 → 数据集类别）"""
    mapping: dict[int, int] = {}
    for part in text.split(","):
        part = part.strip()
        if not part:
            continue
        src, _, dst = part.partition(":")
        mapping[int(src)] = int(dst or src)
    return mapping


def parse_roi(text: str) -> tuple[float, float, float, float] | None:
    """'0.02,0.16,0.98,0.99' → 归一化矩形；传空则不过滤。

    为什么要这个：转播机位的看台、替补席、场边广告牌上全是「人」，
    COCO 会把它们一起检出来（实测一段 1080p 片段每帧 28 个框，其中一半在看台上）。
    预标注阶段先用一个固定矩形把场地圈出来，人工改框的工作量能砍掉一半。
    """
    text = (text or "").strip()
    if not text:
        return None
    parts = [float(x) for x in text.split(",")]
    if len(parts) != 4:
        raise SystemExit("[错误] --roi 需要 4 个数：x1,y1,x2,y2（归一化 0~1）")
    return parts[0], parts[1], parts[2], parts[3]


def in_roi(box: dict, width: int, height: int, roi: tuple[float, float, float, float]) -> bool:
    """框中心点是否落在 ROI 内。"""
    x1, y1, x2, y2 = box["xyxy"]
    cx = (x1 + x2) / 2.0 / max(width, 1)
    cy = (y1 + y2) / 2.0 / max(height, 1)
    rx1, ry1, rx2, ry2 = roi
    return rx1 <= cx <= rx2 and ry1 <= cy <= ry2


def to_yolo_line(box: dict, width: int, height: int, cls_id: int) -> str:
    x1, y1, x2, y2 = box["xyxy"]
    cx = (x1 + x2) / 2.0 / width
    cy = (y1 + y2) / 2.0 / height
    w = (x2 - x1) / width
    h = (y2 - y1) / height
    clamp = lambda v: min(max(v, 0.0), 1.0)  # noqa: E731
    return f"{cls_id} {clamp(cx):.6f} {clamp(cy):.6f} {clamp(w):.6f} {clamp(h):.6f}"


def main() -> int:
    ap = argparse.ArgumentParser(description="用预训练 YOLOv8 生成 YOLO 格式预标注")
    ap.add_argument("--src", required=True, help="抽帧目录（或单张图片）")
    ap.add_argument("--weights", default=config.DEFAULT_MODEL)
    ap.add_argument("--imgsz", type=int, default=config.DEFAULT_IMGSZ)
    ap.add_argument("--conf", type=float, default=0.25)
    ap.add_argument("--classes", default="0,32", help="推理时保留的 COCO 类别")
    ap.add_argument("--map", dest="mapping", default="0:0,32:1", help="COCO→数据集 类别映射")
    ap.add_argument("--out", default="", help="labels 输出目录（默认 <src>/labels）")
    ap.add_argument("--dataset-root", default="", help="可选：拼 YOLO 目录结构并写 data.yaml")
    ap.add_argument("--copy-images", action="store_true", help="把图片复制进 dataset/images")
    ap.add_argument("--roi", default="", help="只保留中心点落在该归一化矩形内的框，格式 x1,y1,x2,y2（如 0.02,0.16,0.98,0.99）")
    ap.add_argument("--min-height", type=float, default=0.0, help="丢弃像素高度小于该值的框（去噪，远处像素小人）")
    args = ap.parse_args()

    from src.vision.detector import Detector

    src = Path(args.src)
    images = [src] if src.is_file() else sorted(
        p for p in src.iterdir() if p.suffix.lower() in IMAGE_SUFFIXES
    )
    if not images:
        print(f"[错误] {src} 下没有图片")
        return 2

    out_dir = Path(args.out) if args.out else (src if src.is_dir() else src.parent) / "labels"
    out_dir.mkdir(parents=True, exist_ok=True)
    mapping = parse_map(args.mapping)
    classes = [int(c) for c in args.classes.split(",") if c.strip()]
    roi = parse_roi(args.roi)

    det = Detector(model=args.weights, imgsz=args.imgsz, conf=args.conf, classes=classes)
    manifest: list[dict] = []
    total_boxes = dropped = 0
    roi_dropped = small_dropped = 0

    for i, image in enumerate(images, 1):
        result = det.predict(image)[0]
        probe = io._cv2().imread(str(image))
        if probe is None:
            print(f"[警告] 读不出图片，跳过 {image.name}")
            continue
        height, width = probe.shape[:2]

        lines: list[str] = []
        kept = 0
        for box in result["boxes"]:
            coco = int(box["cls"])
            if coco not in mapping:
                dropped += 1
                continue
            if roi is not None and not in_roi(box, width, height, roi):
                roi_dropped += 1
                continue
            if args.min_height > 0 and (box["xyxy"][3] - box["xyxy"][1]) < args.min_height:
                small_dropped += 1
                continue
            lines.append(to_yolo_line(box, width, height, mapping[coco]))
            kept += 1

        (out_dir / f"{image.stem}.txt").write_text("\n".join(lines), encoding="utf-8")
        total_boxes += kept
        manifest.append({"image": image.name, "boxes": kept, "width": width, "height": height})
        if i % 20 == 0 or i == len(images):
            print(f"  预标注 {i}/{len(images)} … 已出 {total_boxes} 个框")

    io.dump_json(out_dir / "manifest.json", {"images": manifest, "mapping": mapping, "boxes": total_boxes})
    (out_dir / "classes.txt").write_text(
        "\n".join(f"{k} {v}" for k, v in sorted(DEFAULT_NAMES.items())), encoding="utf-8"
    )

    yaml_path = None
    if args.dataset_root:
        root = Path(args.dataset_root)
        (root / "images" / "train").mkdir(parents=True, exist_ok=True)
        (root / "labels" / "train").mkdir(parents=True, exist_ok=True)
        for image in images:
            if args.copy_images:
                shutil.copy2(image, root / "images" / "train" / image.name)
            label = out_dir / f"{image.stem}.txt"
            if label.exists():
                shutil.copy2(label, root / "labels" / "train" / label.name)
        yaml_path = root / "data.yaml"
        names = "\n".join(f"  {k}: {v}" for k, v in sorted(DEFAULT_NAMES.items()))
        yaml_path.write_text(
            f"path: {root}\ntrain: images/train\nval: images/train\nnames:\n{names}\n",
            encoding="utf-8",
        )

    extra = f"，ROI 外 {roi_dropped} 个，过小 {small_dropped} 个" if (roi_dropped or small_dropped) else ""
    print(f"\n完成：{len(manifest)} 张图 / {total_boxes} 个框（丢弃非目标类别 {dropped} 个{extra}）")
    print(f"标签目录：{out_dir}")
    if yaml_path:
        print(f"数据集配置：{yaml_path}（val 先指向 train，标够之后按视频划分再改）")
    print("提醒：这是预标注，球几乎一定会漏；进训练集前必须人工过一遍。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
