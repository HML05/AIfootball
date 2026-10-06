"""FootballAI 检索层（RAG 的第一半）: FTS5 全文索引 + 中文分词 + 引用溯源。

阶段 0 只做"把自然语言问题落到真实数据上并给出出处", 不依赖任何外部 LLM。

    from src.search import search, index_stats
"""
from src.search.query import (
    KINDS,
    KIND_LABEL,
    IndexMissing,
    index_stats,
    search,
    try_stats,
)

__all__ = ["KINDS", "KIND_LABEL", "IndexMissing", "index_stats", "search", "try_stats"]
