"""LLM 客户端 —— 只依赖 requests, 走 OpenAI 兼容的 /chat/completions。

为什么不用 langchain:
  * 项目里老代码 src/agent/agent.py 用的是 langchain 0.x 的 initialize_agent / langchain.chat_models,
    这套 API 在 langchain 0.2+ 已迁到 langchain-classic / langchain-openai, 装上也是坏的;
  * 编排逻辑本来就只有「意图 → 工具 → 生成」三步, 自己写反而更可控、更好测;
  * 没有 LLM key 时整条链路要能降级成检索摘要（见 orchestrator.py）, 所以这里必须可选。

配置来自 config/settings.py: LLM_API_KEY / LLM_BASE_URL / LLM_MODEL
（DeepSeek 用默认值即可: https://api.deepseek.com + deepseek-chat）。
"""
from __future__ import annotations

import time
from typing import Any

import requests

from config.settings import settings


def ready() -> bool:
    return bool((settings.LLM_API_KEY or "").strip())


def model_name() -> str:
    return settings.LLM_MODEL or "deepseek-chat"


def endpoint() -> str:
    base = (settings.LLM_BASE_URL or "https://api.deepseek.com").rstrip("/")
    return f"{base}/chat/completions"


def chat(messages: list[dict[str, str]], temperature: float = 0.2,
         max_tokens: int = 900, timeout: float = 45.0) -> dict[str, Any]:
    """调用兼容 OpenAI 的对话接口。

    返回 {ok, text, model, error, elapsed_ms, usage}；任何异常都落成 ok=False + error,
    调用方据此降级（绝不把异常抛给前端）。
    """
    if not ready():
        return {"ok": False, "text": "", "model": model_name(), "error": "未配置 LLM_API_KEY",
                "elapsed_ms": 0, "usage": None}
    t0 = time.time()
    payload = {
        "model": model_name(),
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
    }
    try:
        r = requests.post(
            endpoint(),
            json=payload,
            headers={
                "Authorization": f"Bearer {settings.LLM_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=timeout,
        )
    except Exception as e:  # 网络不通 / DNS / 超时
        return {"ok": False, "text": "", "model": model_name(),
                "error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000), "usage": None}
    ms = int((time.time() - t0) * 1000)
    if r.status_code != 200:
        return {"ok": False, "text": "", "model": model_name(),
                "error": f"HTTP {r.status_code}: {r.text[:300]}", "elapsed_ms": ms, "usage": None}
    try:
        data = r.json()
        text = (data.get("choices") or [{}])[0].get("message", {}).get("content", "")
        return {"ok": bool(text.strip()), "text": (text or "").strip(),
                "model": data.get("model") or model_name(),
                "error": None if text.strip() else "模型返回空内容",
                "elapsed_ms": ms, "usage": data.get("usage")}
    except Exception as e:
        return {"ok": False, "text": "", "model": model_name(),
                "error": f"响应解析失败: {e}", "elapsed_ms": ms, "usage": None}
