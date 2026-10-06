# -*- coding: utf-8 -*-
"""LLM 配置体检 —— 确认 .env 里的 key / 地址 / 模型名真的能用。

用法:
    python scripts/check_llm.py              # 列模型 + 发一次最小请求
    python scripts/check_llm.py --models     # 只列模型，不产生对话计费

它做三件事（全部只读，不改任何文件）:
    1. 打印脱敏后的 key 前缀、base_url、model（key 永远不完整回显）；
    2. GET {base}/models —— 列出账号真的能用的模型 id；
    3. POST {base}/chat/completions 发一句 "ping"（max_tokens=8）验证鉴权与模型名。

退出码: 0 = 对话可用；1 = 配置缺失或鉴权/模型名有问题（会打印服务端原文，便于定位 401/402/400）。
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests  # noqa: E402

from config.settings import settings  # noqa: E402
from src.qa import llm  # noqa: E402


def mask(key: str) -> str:
    key = (key or "").strip()
    if not key:
        return "<空>"
    return f"{key[:6]}…{key[-4:]}（{len(key)} 字符）"


def main() -> int:
    key = (settings.LLM_API_KEY or "").strip()
    base = llm.endpoint().rsplit("/chat/completions", 1)[0]
    model = llm.model_name()
    print(f"[配置] key      = {mask(key)}")
    print(f"[配置] base_url = {base}")
    print(f"[配置] model    = {model}")
    if not key:
        print("[!] LLM_API_KEY 为空 —— 问答会走检索摘要（mode=retrieval）。")
        print("    填法: 打开 .env 第 20 行 → LLM_API_KEY=sk-… ，保存后重启服务。")
        return 1

    hdr = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
    ids: list[str] = []
    try:
        r = requests.get(f"{base}/models", headers=hdr, timeout=20)
    except Exception as e:
        print(f"[!] 连不上 {base}/models: {type(e).__name__}: {e}")
        print("    检查网络 / 代理；GitHub 那种 hosts 加速器不影响 DeepSeek，但 VPN 可能拦截。")
        return 1
    if r.status_code == 200:
        try:
            ids = [d.get("id", "") for d in (r.json().get("data") or [])]
        except Exception as e:
            print(f"[!] /models 返回的不是预期 JSON: {e} / {r.text[:200]}")
        print(f"[模型] 账号可用 {len(ids)} 个: {', '.join(ids) if ids else '(列表为空)'}")
        if ids and model not in ids:
            print(f"[!] 当前 LLM_MODEL={model} 不在可用列表里 —— 建议改成: {ids[0]}")
        elif ids:
            print(f"[ok] LLM_MODEL={model} 在可用列表里")
    else:
        print(f"[!] GET /models -> HTTP {r.status_code}: {r.text[:300]}")
        print("    401/403 = key 不对或已删除；402 = 余额不足。")

    if "--models" in sys.argv:
        return 0 if r.status_code == 200 else 1

    print("[请求] POST /chat/completions  question='ping'  max_tokens=8 …")
    out = llm.chat([{"role": "user", "content": "ping"}], temperature=0, max_tokens=8, timeout=30)
    if out["ok"]:
        print(f"[ok] 对话可用: model={out['model']} elapsed={out['elapsed_ms']} ms "
              f"usage={out.get('usage')} text={out['text'][:40]!r}")
        print("     重启 API（改 .env 后必须重启）→ GET /api/ui/ask/status 应显示 llm_ready=true")
        return 0
    print(f"[!] 对话失败: {out['error']}")
    print("    400 = 模型名不对（对照上面的可用列表改 .env）；401 = key；402 = 余额；超时 = 网络。")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
