#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# FootballAI 启动脚本（Linux / macOS；Windows 用 start_webui.bat）
#
#   ./start.sh                     前台启动，读 .env 里的 SERVER_HOST / SERVER_PORT
#   PORT=9000 ./start.sh           临时换端口
#   SKIP_BUILD=1 ./start.sh        即使缺前端产物也不构建（只起 API）
#   ./start.sh --install-service   打印 systemd 安装步骤（见 docs/deploy.md）
#
# 生产环境请用 systemd 常驻（deploy/footballai.service），本脚本也适合直接跑。
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail
cd "$(dirname "$0")"

PY="${PYTHON:-python3}"
# .env 可能是在 Windows 上编辑的（CRLF），取值时顺手去掉 \r，否则 host 会变成 "0.0.0.0\r"
env_val() { grep -E "^$1=" .env 2>/dev/null | head -n1 | cut -d= -f2- | tr -d '\r' || true; }
HOST="${HOST:-$(env_val SERVER_HOST)}"
PORT="${PORT:-$(env_val SERVER_PORT)}"
HOST="${HOST:-0.0.0.0}"
PORT="${PORT:-8000}"

echo "============================================================"
echo "  足球数据分析与 AI 预测系统"
echo "============================================================"
echo "  服务地址    http://${HOST}:${PORT}/"
echo "  接口文档    http://${HOST}:${PORT}/docs"
echo "  登录页      http://${HOST}:${PORT}/console/login.html"
echo "------------------------------------------------------------"

if [ ! -f .env ]; then
  echo "[!] 没有 .env —— 从模板复制一份再填 key：cp .env.example .env"
fi

# 依赖体检（缺包时给出明确提示，而不是等启动时 ImportError）
if ! "$PY" -c 'import fastapi, uvicorn, sqlalchemy, pandas, numpy, xgboost, shap' 2>/dev/null; then
  echo "[!] 依赖不全，先装：$PY -m pip install -r requirements.txt"
  exit 1
fi

# 数据库 / 模型 / 预测特征这三样不在 Git 里，缺了会起不来或预测报错
for f in data/database/football.db models/ensemble_v2_v7.joblib models/xgb_v2.joblib \
         data/processed/all_matches.csv data/processed/tm_team_season.csv data/processed/match_xg.csv; do
  [ -e "$f" ] || echo "[!] 缺少 $f —— 见 docs/deploy.md「把数据与模型传上服务器」"
done

# 前端产物：缺了就尝试现场构建（服务器没 Node 时会失败，那就本地构建后一并上传）
if [ ! -f webui/dist/index.html ]; then
  if [ "${SKIP_BUILD:-0}" = "1" ]; then
    echo "[!] 缺 webui/dist/index.html（SKIP_BUILD=1，跳过构建）"
  elif command -v npm >/dev/null 2>&1; then
    echo "[1/2] 未发现前端产物，正在构建…"
    "$PY" scripts/build_webui.py
  else
    echo "[!] 缺 webui/dist/index.html 且本机没有 npm —— 在本地跑 python scripts/build_webui.py 后把 webui/dist 传上来"
    exit 1
  fi
else
  echo "[1/2] 已有前端产物，跳过构建（重建：python scripts/build_webui.py）"
fi

echo "[2/2] 启动服务…"
# 注意：必须单 worker —— 应用内在启动时拉起 APScheduler（start_scheduler()），
# 多 worker 会各跑一份定时任务，造成重复抓取与重复写库。
exec "$PY" -m uvicorn src.main:app --host "$HOST" --port "$PORT" --workers 1
