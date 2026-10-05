"""AI Agent主体 - LangChain + 国内LLM
使用工具增强生成(Tool Use)架构，LLM不直接编造数据，而是调用工具获取真实数据
"""
from typing import Optional
from langchain.agents import AgentType, initialize_agent
from langchain.chat_models import ChatOpenAI
from langchain.memory import ConversationBufferMemory
from src.agent.tools import FootballAgentTools
from src.agent.prompts import FOOTBALL_AGENT_PROMPT, MATCH_ANALYSIS_PROMPT
from config.settings import settings


class FootballAnalysisAgent:
    """足球分析AI Agent"""

    def __init__(self, tools: FootballAgentTools,
                 llm_api_key: Optional[str] = None,
                 llm_base_url: Optional[str] = None,
                 llm_model: Optional[str] = None,
                 temperature: float = 0.3):
        """
        Args:
            tools: Agent工具集
            llm_api_key: LLM API密钥（默认从配置读取）
            llm_base_url: LLM API地址（支持DeepSeek/豆包/通义千问等OpenAI兼容接口）
            llm_model: 模型名称
            temperature: 温度（分析任务用低温度0.2-0.4）
        """
        api_key = llm_api_key or settings.LLM_API_KEY
        base_url = llm_base_url or settings.LLM_BASE_URL
        model = llm_model or settings.LLM_MODEL

        if not api_key or api_key == "your_llm_api_key_here":
            raise ValueError("请在 .env 中配置 LLM_API_KEY（支持DeepSeek/豆包/通义千问）")

        # 使用OpenAI兼容接口（国内LLM大多兼容）
        self.llm = ChatOpenAI(
            model=model,
            api_key=api_key,
            base_url=base_url,
            temperature=temperature,
            max_tokens=2000,
        )

        # 对话记忆
        self.memory = ConversationBufferMemory(
            memory_key="chat_history",
            return_messages=True
        )

        # 初始化Agent
        self.agent = initialize_agent(
            tools=tools.get_tools(),
            llm=self.llm,
            agent=AgentType.OPENAI_FUNCTIONS,
            memory=self.memory,
            verbose=True,
            agent_kwargs={"prefix": FOOTBALL_AGENT_PROMPT},
            max_iterations=5,  # 限制最大迭代次数，防止无限循环
        )

    def chat(self, user_message: str) -> str:
        """与Agent对话

        Args:
            user_message: 用户输入

        Returns:
            Agent回复
        """
        try:
            response = self.agent.run(user_message)
            return response
        except Exception as e:
            return f"分析过程中出现错误: {str(e)}\n请尝试换一种问法，或检查API配置。"

    def analyze_match(self, home_team: str, away_team: str) -> str:
        """深度分析一场比赛

        Args:
            home_team: 主队
            away_team: 客队

        Returns:
            深度分析报告
        """
        prompt = MATCH_ANALYSIS_PROMPT.format(home_team=home_team, away_team=away_team)
        return self.chat(prompt)

    def clear_memory(self):
        """清除对话记忆"""
        self.memory.clear()
