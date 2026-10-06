"""重建检索索引。

    python scripts/build_search_index.py            # 全量重建(默认 jieba)
    python scripts/build_search_index.py --bigram   # 强制用 bigram 分词(没装 jieba 时)

索引落在 data/database/search.db, 与业务主库分开, 随时可删可重建;
定时任务里也可以挂它(数据更新后重建索引)。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.search.indexer import SEARCH_DB, build  # noqa: E402
from src.search.tokenizer import MODE_BIGRAM, MODE_JIEBA, HAS_JIEBA  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description="重建 FootballAI 检索索引(FTS5)")
    ap.add_argument("--bigram", action="store_true", help="强制使用字符 bigram 分词")
    ap.add_argument("--jieba", action="store_true", help="强制使用 jieba 分词(默认)")
    ap.add_argument("--out", default=str(SEARCH_DB), help="索引文件路径")
    args = ap.parse_args()

    mode = MODE_BIGRAM if args.bigram else MODE_JIEBA
    if mode == MODE_JIEBA and not HAS_JIEBA:
        print("[search] 未安装 jieba, 自动退化为 bigram（pip install jieba 可启用更优分词）")
        mode = MODE_BIGRAM

    info = build(path=Path(args.out), mode=mode)
    print(f"[search] 完成: {info['total']} 条  {info['size_bytes'] / 1048576:.1f} MB  "
          f"{info['seconds']}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
