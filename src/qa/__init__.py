"""智能问答层（RAG 阶段 1）。

模块分工:
    tools.py        六个结构化工具（纯函数, 只读主库, 带 sources）
    router.py       中文问题的意图与实体识别 → 工具调用计划
    llm.py          OpenAI 兼容的对话客户端（只依赖 requests, 可选）
    orchestrator.py 编排 + 带引用的答案 + 无 key 时的检索摘要降级

接口见 src/api/qa.py（POST /api/ui/ask、GET /api/ui/ask/status）。
"""
from src.qa.orchestrator import ask, status

__all__ = ["ask", "status"]
