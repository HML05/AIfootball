"""配置管理 - 从环境变量加载配置"""
import os
from dotenv import load_dotenv
from pathlib import Path

# 加载 .env 文件
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings:
    """全局配置"""

    # 数据库
    DATABASE_URL: str = os.getenv("DATABASE_URL", "sqlite:///./data/database/football.db")

    # API-Football
    API_FOOTBALL_KEY: str = os.getenv("API_FOOTBALL_KEY", "")
    API_FOOTBALL_HOST: str = os.getenv("API_FOOTBALL_HOST", "api-football-v1.p.rapidapi.com")

    # API-Football / API-Sports 直连(付费档: 7500 次/天; 免费档: 100 次/天)
    #   在 https://dashboard.api-football.com 注册后把 key 填到 .env 的 API_SPORTS_KEY
    API_SPORTS_KEY: str = os.getenv("API_SPORTS_KEY", "")
    API_SPORTS_BASE: str = os.getenv("API_SPORTS_BASE", "https://v3.football.api-sports.io")
    # 每日请求预算(留出余量, 避免把配额跑满)
    AF_DAILY_BUDGET: int = int(os.getenv("AF_DAILY_BUDGET", "7000"))
    # 请求最小间隔(秒): 免费档限速 10 次/分钟 -> 6.0; Pro 档 300 次/分钟 -> 0.25
    AF_MIN_INTERVAL: float = float(os.getenv("AF_MIN_INTERVAL", "6.0"))

    # Football-Data.org (免费, 覆盖五大联赛赛程/结果/积分榜)
    FOOTBALL_DATA_TOKEN: str = os.getenv("FOOTBALL_DATA_TOKEN", "")

    # 球小策 (按点计费, 精细化数据: xG/阵容/球员统计/伤停/转会)
    QIXIAOCE_API_KEY: str = os.getenv("QIXIAOCE_API_KEY", "")
    QIXIAOCE_BASE: str = os.getenv(
        "QIXIAOCE_BASE",
        "https://www.qiuxiaoce.com/wp-json/abv2-creator/v1")

    # LLM
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # 服务
    SERVER_HOST: str = os.getenv("SERVER_HOST", "0.0.0.0")
    SERVER_PORT: int = int(os.getenv("SERVER_PORT", "8000"))
    DEBUG: bool = os.getenv("DEBUG", "true").lower() == "true"

    # 界面数据接口是否要求登录(默认开启)
    #   /api/ui/* 需要 Authorization: Bearer <token>(由 /api/auth/login 或扫码登录取得);
    #   设成 false 可临时放行, 便于本地调试或离线截图。
    UI_REQUIRE_AUTH: bool = os.getenv("UI_REQUIRE_AUTH", "true").lower() == "true"

    # 注册 / 忘记密码(见 src/api/auth.py 的 /register 与 /reset/*)
    #   注册默认开放, 新账号固定是 user(用户端), 不会注册出管理员;
    #   部署到公网想关掉自助注册就设 AUTH_ALLOW_REGISTER=false。
    AUTH_ALLOW_REGISTER: bool = os.getenv("AUTH_ALLOW_REGISTER", "true").lower() == "true"
    #   这套系统是本机/内网部署, 没有邮件短信通道:
    #   重置码**只写服务端日志**(默认), 由管理员转告用户 —— 公网部署安全;
    #   本机自用图方便可设 AUTH_RESET_SHOW_CODE=true 让码直接回显到页面上
    #   (那样任何能访问端口的人都能取到任意账号的重置码, 千万别在公网开着)。
    AUTH_RESET_SHOW_CODE: bool = os.getenv("AUTH_RESET_SHOW_CODE", "false").lower() == "true"
    AUTH_RESET_TTL_MINUTES: int = int(os.getenv("AUTH_RESET_TTL_MINUTES", "10"))
    AUTH_RESET_MAX_TRIES: int = int(os.getenv("AUTH_RESET_MAX_TRIES", "5"))

    # 定时任务
    ENABLE_LIVE_SCORE_UPDATE: bool = os.getenv("ENABLE_LIVE_SCORE_UPDATE", "true").lower() == "true"
    ENABLE_DAILY_UPDATE: bool = os.getenv("ENABLE_DAILY_UPDATE", "true").lower() == "true"

    # 项目路径
    BASE_DIR: Path = Path(__file__).parent.parent
    DATA_DIR: Path = BASE_DIR / "data"
    RAW_DATA_DIR: Path = DATA_DIR / "raw"
    MODEL_DIR: Path = BASE_DIR / "models"

    def __init__(self):
        # 确保目录存在
        for d in [self.DATA_DIR, self.RAW_DATA_DIR, self.MODEL_DIR,
                  self.DATA_DIR / "processed", self.DATA_DIR / "database"]:
            d.mkdir(parents=True, exist_ok=True)


settings = Settings()
