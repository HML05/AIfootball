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
         max_tokens: int = 1600, timeout: float = 45.0,
         retry_on_truncate: bool = True) -> dict[str, Any]:
    """调用兼容 OpenAI 的对话接口。

    返回 {ok, text, model, error, elapsed_ms, usage, finish_reason, truncated,
          reasoning_tokens, retried}；任何异常都落成 ok=False + error,
    调用方据此降级（绝不把异常抛给前端）。

    为什么要看 finish_reason:
      推理型模型（如 deepseek-flash / deepseek-reasoner）会先输出 reasoning_content,
      **推理 token 也算在 max_tokens 预算里** —— 预算不够时 content 会被硬切成半句话,
      而 HTTP 依然是 200。所以这里显式识别 finish_reason == "length"（truncated=True）,
      并自动用两倍预算重试一次；重试仍被截断才如实上报。
    """
    if not ready():
        return {"ok": False, "text": "", "model": model_name(), "error": "未配置 LLM_API_KEY",
                "elapsed_ms": 0, "usage": None, "finish_reason": None, "truncated": False,
                "reasoning_tokens": None, "retried": False}

    def _post(mt: int) -> dict[str, Any]:
        t0 = time.time()
        payload = {
            "model": model_name(),
            "messages": messages,
            "temperature": temperature,
            "max_tokens": int(mt),
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
                    "error": f"{type(e).__name__}: {e}", "elapsed_ms": int((time.time() - t0) * 1000),
                    "usage": None, "finish_reason": None, "truncated": False,
                    "reasoning_tokens": None, "retried": False}
        ms = int((time.time() - t0) * 1000)
        if r.status_code != 200:
            return {"ok": False, "text": "", "model": model_name(),
                    "error": f"HTTP {r.status_code}: {r.text[:300]}", "elapsed_ms": ms,
                    "usage": None, "finish_reason": None, "truncated": False,
                    "reasoning_tokens": None, "retried": False}
        try:
            data = r.json()
            choice = (data.get("choices") or [{}])[0]
            text = (choice.get("message") or {}).get("content", "")
            finish = choice.get("finish_reason")
            usage = data.get("usage") or {}
            rtok = (usage.get("completion_tokens_details") or {}).get("reasoning_tokens")
            return {"ok": bool((text or "").strip()), "text": (text or "").strip(),
                    "model": data.get("model") or model_name(),
                    "error": None if (text or "").strip() else "模型返回空内容",
                    "elapsed_ms": ms, "usage": usage or None,
                    "finish_reason": finish,
                    "truncated": finish == "length",
                    "reasoning_tokens": rtok, "retried": False}
        except Exception as e:
            return {"ok": False, "text": "", "model": model_name(),
                    "error": f"响应解析失败: {e}", "elapsed_ms": ms, "usage": None,
                    "finish_reason": None, "truncated": False,
                    "reasoning_tokens": None, "retried": False}

    out = _post(max_tokens)
    # 注意判据是 truncated 而不是 ok：推理模型可能把预算全花在 reasoning 上、
    # content 直接是空的（HTTP 200 且 finish_reason=length），这种也值得加倍预算重试一次。
    if retry_on_truncate and out.get("truncated"):
        bigger = _post(max(1600, int(max_tokens) * 2))
        if bigger.get("ok") and len(bigger.get("text") or "") > len(out.get("text") or ""):
            bigger["retried"] = True
            out = bigger
        else:
            out["retried"] = True
    return out

