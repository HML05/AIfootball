"""中文分词适配层 —— 写入与查询必须使用同一套分词口径。

实测结论(打包在 scripts/verify_search.py 里可复现):
  * SQLite FTS5 的 unicode61 分词器把整段中文当成一个 token ->
    查「皇家马德里」里的「马德里」命中 0;
  * trigram 分词器能命中「马德里」, 但要求查询 >= 3 个字符 ->
    查「逆转」这种两字词命中 0。

因此这里自己分词:
  * 装了 jieba -> 用 jieba 精确模式(质量最好, 索引也最小);
  * 没装 jieba -> 退化成字符 bigram(零依赖, 且保证两字词可召回)。
分词模式会写进索引的 meta 表, 查询时按同一模式切分。
"""
from __future__ import annotations

import re

try:  # pragma: no cover - 取决于运行环境
    import jieba

    jieba.setLogLevel(20)  # 静音 "Building prefix dict ..."
    HAS_JIEBA = True
except Exception:  # pragma: no cover
    jieba = None
    HAS_JIEBA = False

MODE_JIEBA = "jieba"
MODE_BIGRAM = "bigram"

_ASCII_WORD = re.compile(r"[A-Za-z0-9_]+")
_CJK_RUN = re.compile(r"[\u4e00-\u9fff]+")
_CHUNK = re.compile(r"[A-Za-z0-9_]+|[\u4e00-\u9fff]+")


def default_mode() -> str:
    """当前环境可用的最佳分词模式。"""
    return MODE_JIEBA if HAS_JIEBA else MODE_BIGRAM


def tokenize(text: str, mode: str | None = None) -> list[str]:
    """把一段文本切成 token 列表(标点与空白丢弃)。"""
    if not text:
        return []
    mode = mode or default_mode()
    out: list[str] = []
    for chunk in _CHUNK.findall(text):
        if _ASCII_WORD.fullmatch(chunk):
            out.append(chunk.lower())
        elif mode == MODE_JIEBA and HAS_JIEBA:
            out.extend(w.strip().lower() for w in jieba.lcut(chunk) if w.strip())
        else:  # bigram: 「皇家马德里」-> 皇家 家马 马德 德里
            n = len(chunk)
            if n == 1:
                out.append(chunk)
            else:
                out.extend(chunk[i:i + 2] for i in range(n - 1))
    return out


def tokenize_for_index(text: str, mode: str | None = None) -> tuple[str, list[str]]:
    """返回 (给 FTS5 的 tokens 列, token 列表)。"""
    toks = tokenize(text, mode)
    return " ".join(toks), toks


def tokenize_for_query(text: str, mode: str | None = None) -> list[str]:
    """查询侧分词: 去掉重复 token, 保留顺序。"""
    seen: set[str] = set()
    out: list[str] = []
    for t in tokenize(text, mode):
        if t not in seen:
            seen.add(t)
            out.append(t)
    return out


def describe_mode(mode: str | None = None) -> str:
    m = mode or default_mode()
    if m == MODE_JIEBA:
        return "jieba 精确模式(jieba.lcut)"
    return "字符 bigram 回退(未安装 jieba)"


__all__ = [
    "HAS_JIEBA",
    "MODE_BIGRAM",
    "MODE_JIEBA",
    "default_mode",
    "describe_mode",
    "tokenize",
    "tokenize_for_index",
    "tokenize_for_query",
]
