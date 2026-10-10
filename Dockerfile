# ═══════════════════════════════════════════════════════════════════════════════
# FootballAI 生产镜像
#
# 里面有什么：FastAPI 主应用（单 worker，SQLite）+ React 构建产物 webui/dist
#             + /console 设计稿静态页 + 数据库与模型（来自数据包）
# 里面没有什么：Node、torch、playwright、streamlit —— 运行期都不需要
#
# 构建：
#   docker build -t aifootball:local .                       # 默认从 Release 拉数据包
#   docker build -t aifootball:local --build-arg DATA_PACK_URL= .   # 数据已在上下文里时不下载
#
# 为什么需要数据包：data/database/football.db（158.8 MB）、models/*.joblib（11.3 MB）、
# data/processed/*.csv（5.1 MB）都在 .gitignore 里（仓库不该放二进制大文件），
# 云端构建（Render / HF Spaces / 云服务器）拿到的仓库里没有它们，所以构建期下载。
# 打包与上传见 scripts/make_data_pack.py，三条托管路线见 docs/部署-公网托管.md。
# ═══════════════════════════════════════════════════════════════════════════════
FROM python:3.13-slim

# 数据包地址（默认指向本项目 Release 的公共资产；传空字符串表示「数据已在构建上下文里」）
ARG DATA_PACK_URL="https://github.com/HML05/AIfootball/releases/download/data-pack-v1/aifootball-data-pack-v1.tar.gz"

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    TZ=Asia/Shanghai \
    PORT=7860

WORKDIR /app

# libgomp1: xgboost 与 numba(shap 依赖) 的 OpenMP 运行库，slim 镜像里没有
# curl: 构建期取数据包；运行期健康检查也用它
RUN apt-get update \
 && apt-get install -y --no-install-recommends ca-certificates curl libgomp1 \
 && rm -rf /var/lib/apt/lists/*

# 依赖层单独放前面：改业务代码不会让这层缓存失效
COPY requirements-deploy.txt ./
RUN pip install --no-cache-dir -r requirements-deploy.txt

# 应用代码与前端产物（webui/dist 是已经构建好的静态文件，镜像里不装 Node）
COPY config/ ./config/
COPY src/ ./src/
COPY webui/dist/ ./webui/dist/
COPY docs/console/ ./docs/console/
COPY scripts/ ./scripts/
COPY deploy/ ./deploy/

# 数据包：数据库 + 模型 + 特征 CSV（解包后落在 /app/data 与 /app/models）
RUN set -eux; \
    if [ -n "$DATA_PACK_URL" ]; then \
      curl -fL --retry 3 --retry-delay 2 -o /tmp/data-pack.tar.gz "$DATA_PACK_URL"; \
      tar -xzf /tmp/data-pack.tar.gz -C /app; \
      rm -f /tmp/data-pack.tar.gz; \
    fi; \
    mkdir -p /app/data/uploads/avatars /app/logs

# 非 root 运行（安全基线，也是 Hugging Face Spaces 的硬性要求）
RUN useradd -m -u 1000 app && chown -R app:app /app
USER app

EXPOSE 7860

HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
  CMD curl -fsS "http://127.0.0.1:${PORT}/health" || exit 1

# entrypoint 会在数据库缺失时兜底下载一次数据包，然后 exec uvicorn
CMD ["sh", "/app/deploy/entrypoint.sh"]
