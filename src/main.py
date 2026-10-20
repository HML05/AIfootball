"""FastAPI 应用入口
启动: uvicorn src.main:app --reload --host 0.0.0.0 --port 8000
API文档: http://localhost:8000/docs
"""
# 直接运行这个文件(`python src\main.py`, 或在 IDE 里 F5 起当前文件)时,
# Python 只把 src\ 放进 sys.path, 于是下面的 `from config.settings import ...`
# 会报 ModuleNotFoundError: No module named 'config'。
# 这里把仓库根补进 sys.path —— 这样 `python -m src.main`、`python src\main.py`、
# IDE 直接运行三种方式都能起来。必须放在 import config 之前。
if __package__ in (None, ""):
    import sys
    from pathlib import Path as _Path
    _ROOT_DIR = _Path(__file__).resolve().parents[1]
    if str(_ROOT_DIR) not in sys.path:
        sys.path.insert(0, str(_ROOT_DIR))

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from pathlib import Path
from typing import List
import json
import pandas as pd

from config.settings import settings
from src.database.crud import init_db
from src.api.leagues import router as leagues_router
from src.api.teams import router as teams_router
from src.api.players import router as players_router
from src.api.matches import router as matches_router
from src.api.predictions import router as predictions_router
from src.api.agent import router as agent_router
from src.api.auth import router as auth_router
from src.api.ui import router as ui_router
from src.api.search import router as search_router
from src.api.qa import router as qa_router
from src.api.vision import media_router as vision_media_router
from src.api.vision import router as vision_router


# ============ WebSocket 连接管理 ============

class ConnectionManager:
    """WebSocket连接管理器 - 用于实时比分推送"""

    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict):
        """向所有连接广播消息"""
        for connection in self.active_connections:
            try:
                await connection.send_json(message)
            except Exception:
                self.disconnect(connection)

    async def send_to(self, websocket: WebSocket, message: dict):
        """向单个连接发送消息"""
        try:
            await websocket.send_json(message)
        except Exception:
            self.disconnect(websocket)


manager = ConnectionManager()


# ============ 应用生命周期 ============

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用启动和关闭时的生命周期管理"""
    # 启动时: 初始化数据库
    print("正在初始化数据库...")
    init_db()
    print("数据库初始化完成")

    # 加载比赛数据并初始化预测器
    print("正在加载比赛数据...")
    try:
        import pandas as pd
        from src.api.predictions import _matches_df, _predictor, _feature_engineer
        from src.prediction.predictor import MatchPredictor
        from src.prediction.feature_engineer import FeatureEngineer
        from src.analysis.elo_rating import EloRating
        from pathlib import Path

        matches_path = settings.DATA_DIR / "processed" / "all_matches.csv"
        if matches_path.exists():
            df = pd.read_csv(matches_path, encoding="utf-8-sig")
            df["Date"] = pd.to_datetime(df["Date"], errors="coerce")
            df = df.dropna(subset=["HomeTeam", "AwayTeam", "FTR"])
            import src.api.predictions as pred_mod
            pred_mod._matches_df = df
            print(f"比赛数据加载完成: {len(df)} 场")

            # 初始化Elo和特征工程
            elo = EloRating()
            elo.batch_update(df)
            pred_mod._feature_engineer = FeatureEngineer(df, elo)
            print("特征工程器初始化完成")

            # 加载预测模型
            model_path = settings.MODEL_DIR / "xgb_match_predictor.joblib"
            if model_path.exists():
                pred_mod._predictor = MatchPredictor(str(model_path))
                print("预测模型加载完成")
            else:
                print("警告: 预测模型未找到，请先运行训练脚本")
        else:
            print("警告: 比赛数据文件未找到，请先运行数据初始化")
    except Exception as e:
        print(f"数据加载失败: {e}")

    # 启动定时任务（如果启用）
    scheduler = None
    if settings.ENABLE_DAILY_UPDATE:
        try:
            from src.scheduler.tasks import start_scheduler
            scheduler = start_scheduler()
            print("定时任务已启动")
        except Exception as e:
            print(f"定时任务启动失败: {e}")

    yield

    # 关闭时
    if scheduler:
        try:
            scheduler.shutdown()
        except Exception:
            pass
    print("应用已关闭")


# ============ 创建应用 ============

app = FastAPI(
    title="足球数据分析与AI预测系统",
    description="基于五大联赛数据的足球分析系统，包含数据可视化、比赛预测、AI智能分析",
    version="1.0.0",
    lifespan=lifespan,
)

# CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # 开发环境允许所有来源，生产环境应限制
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 注册路由
app.include_router(leagues_router, prefix="/api/leagues", tags=["联赛"])
app.include_router(teams_router, prefix="/api/teams", tags=["球队"])
app.include_router(players_router, prefix="/api/players", tags=["球员"])
app.include_router(matches_router, prefix="/api/matches", tags=["比赛"])
app.include_router(predictions_router, prefix="/api/predictions", tags=["预测"])
app.include_router(agent_router, prefix="/api/agent", tags=["AI分析"])
app.include_router(auth_router, prefix="/api/auth", tags=["登录认证"])
app.include_router(ui_router, prefix="/api/ui", tags=["界面数据"])
app.include_router(search_router, prefix="/api/ui", tags=["全文检索"])
app.include_router(qa_router, prefix="/api/ui", tags=["智能问答"])
# 视觉模块: JSON 接口要登录; media 路由(path 里带 /stream 与 /overlay)自带 ?token= 校验
app.include_router(vision_router, prefix="/api/vision", tags=["视觉分析"])
app.include_router(vision_media_router, prefix="/api/vision", tags=["视觉分析"])


# ============ 基础路由 ============

@app.get("/")
async def root():
    """根路径 - 有前端构建产物时直接给出界面，否则返回系统信息"""
    index = Path(__file__).resolve().parent.parent / "webui" / "dist" / "index.html"
    if index.is_file():
        from fastapi.responses import FileResponse

        return FileResponse(str(index))
    return {
        "name": "足球数据分析与AI预测系统",
        "version": "1.0.0",
        "status": "running",
        "docs": "/docs",
        "hint": "前端界面未构建：cd webui && npm run build",
        "api_endpoints": {
            "leagues": "/api/leagues/",
            "teams": "/api/teams/search?name=曼城",
            "players": "/api/players/search?name=哈兰德",
            "matches": "/api/matches/upcoming?days=7",
            "predictions": "/api/predictions/predict (POST)",
            "agent": "/api/agent/chat (POST)",
        },
    }


@app.get("/health")
async def health_check():
    """健康检查"""
    return {"status": "healthy", "timestamp": pd.Timestamp.now().isoformat()}


# ============ WebSocket 实时比分 ============

@app.websocket("/ws/live-scores")
async def websocket_live_scores(websocket: WebSocket):
    """实时比分WebSocket端点
    客户端连接后，服务端定时推送实时比分更新
    """
    await manager.connect(websocket)
    try:
        # 发送连接确认
        await manager.send_to(websocket, {
            "type": "connected",
            "message": "已连接到实时比分服务",
            "active_connections": len(manager.active_connections),
        })

        # 监听客户端消息（如订阅特定联赛）
        while True:
            data = await websocket.receive_json()
            # 处理客户端订阅请求
            if data.get("type") == "subscribe":
                league = data.get("league")
                await manager.send_to(websocket, {
                    "type": "subscribed",
                    "league": league,
                    "message": f"已订阅 {league} 实时比分",
                })
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception as e:
        manager.disconnect(websocket)


# ============ 前端静态资源（webui 构建产物）/ ============
# 构建: cd webui && npm run build  ->  webui/dist
# 挂载在最后: /api/* 与 /docs 优先命中，其余路径交给单页应用（找不到文件时回落到 index.html）
WEBUI_DIST = Path(__file__).resolve().parent.parent / "webui" / "dist"

from starlette.staticfiles import StaticFiles  # noqa: E402

# 设计稿控制台（Football Labs）: 登录页 + 总览页 + 管理后台，纯静态、不改动。
# 挂在 /console，与 SPA 同源，登录态（localStorage.fauth）互通：
#   未登录访问 SPA 任一页面 -> /console/login.html?next=<原地址> -> 登录后跳回。
CONSOLE_DIR = Path(__file__).resolve().parent.parent / "docs" / "console"

if (CONSOLE_DIR / "login.html").is_file():
    app.mount("/console", StaticFiles(directory=str(CONSOLE_DIR), html=True), name="console")

if WEBUI_DIST.is_dir():
    from starlette.exceptions import HTTPException as StarletteHTTPException

    class SPAStaticFiles(StaticFiles):
        """SPA 回落：未知路径返回 index.html，让前端路由接管。

        接口路径（/api/*、/health）**不回落** —— 写错接口名时应该看到 404 JSON，
        而不是一份 index.html；否则 curl / 监控会把拼错的接口当成 200 正常
        （2026-10 部署前用 7860 端口探接口时踩到：/api/ui/overview 这个不存在的
        路径返回了 200 + 首页 HTML）。
        """

        @staticmethod
        def _is_api_path(scope) -> bool:
            path = scope.get("path", "")
            return path.startswith("/api/") or path == "/health"

        async def get_response(self, path, scope):
            try:
                return await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and not self._is_api_path(scope):
                    return await super().get_response("index.html", scope)
                raise

    app.mount("/", SPAStaticFiles(directory=str(WEBUI_DIST), html=True), name="webui")


# ============ 启动入口 ============

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "src.main:app",
        host=settings.SERVER_HOST,
        port=settings.SERVER_PORT,
        reload=settings.DEBUG,
    )
