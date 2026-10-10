#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════════
# 容器入口脚本（POSIX sh，python:3.13-slim 里是 dash）
#
# 做三件事：
#   1. 数据库缺失时兜底下载一次数据包（镜像里通常已经打好了，这是给「平台构建期
#      拿不到数据包、但运行期能联网」的场景留的后路）
#   2. 打印一份**不含密钥**的有效配置，便于在平台日志里排查
#   3. exec uvicorn（单 worker —— SQLite + 进程内定时任务，多 worker 会互相打架）
# ═══════════════════════════════════════════════════════════════════════════════
set -eu

PORT="${PORT:-7860}"
PACK_URL="${DATA_PACK_URL:-}"
DB_FILE="/app/data/database/football.db"
SEARCH_DB="/app/data/database/search.db"
MODEL_FILE="/app/models/xgb_match_predictor.joblib"

echo "[entrypoint] FootballAI 启动中… port=${PORT}"

if [ ! -f "$DB_FILE" ] && [ -n "$PACK_URL" ]; then
  echo "[entrypoint] 未找到 $DB_FILE，尝试下载数据包：$PACK_URL"
  if curl -fL --retry 3 --retry-delay 2 -o /tmp/data-pack.tar.gz "$PACK_URL"; then
    tar -xzf /tmp/data-pack.tar.gz -C /app
    rm -f /tmp/data-pack.tar.gz
    echo "[entrypoint] 数据包解包完成"
  else
    echo "[entrypoint] 警告：数据包下载失败，服务会照常启动，但预测/检索没有真实数据" >&2
  fi
fi

if [ ! -f "$DB_FILE" ]; then
  echo "[entrypoint] 警告：数据库不存在（$DB_FILE）—— 界面会看不到数据" >&2
fi
if [ ! -f "$MODEL_FILE" ]; then
  echo "[entrypoint] 警告：预测模型不存在（$MODEL_FILE）—— 预测接口会报模型未加载" >&2
fi

# 检索索引是独立库（data/database/search.db）。数据包里有；万一没有就现场重建一次 ——
# 建索引只依赖主库与 docs/ 语料，都是离线可做的（约几十秒）。
if [ ! -f "$SEARCH_DB" ] && [ -f "$DB_FILE" ]; then
  echo "[entrypoint] 未找到检索索引（$SEARCH_DB），现场重建…"
  python scripts/build_search_index.py || \
    echo "[entrypoint] 警告：索引重建失败，检索与问答会不可用" >&2
fi

echo "[entrypoint] 有效配置（不含密钥）："
echo "  登录闸门 UI_REQUIRE_AUTH        = ${UI_REQUIRE_AUTH:-true(默认)}"
echo "  自助注册 AUTH_ALLOW_REGISTER    = ${AUTH_ALLOW_REGISTER:-true(默认)}"
echo "  重置码回显 AUTH_RESET_SHOW_CODE = ${AUTH_RESET_SHOW_CODE:-false(默认)}"
echo "  调试模式 DEBUG                  = ${DEBUG:-false(默认)}"
echo "  每日任务 ENABLE_DAILY_UPDATE    = ${ENABLE_DAILY_UPDATE:-true(默认)}"
echo "  实时比分 ENABLE_LIVE_SCORE_...  = ${ENABLE_LIVE_SCORE_UPDATE:-true(默认)}"
echo "  大模型 key 是否配置 LLM_API_KEY = $( [ -n "${LLM_API_KEY:-}" ] && echo 已配置 || echo 未配置 )"

exec uvicorn src.main:app --host 0.0.0.0 --port "$PORT" --workers 1
