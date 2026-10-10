#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# 在 Ubuntu 云服务器上直接部署 FootballAI（venv + systemd 常驻）
#
# 与 deploy/entrypoint.sh（容器入口）的分工：
#   entrypoint.sh  → 平台托管（Render 等），镜像里已打好数据，入口只做兜底与启动
#   本脚本         → 自己的一台机器（阿里云轻量 / 腾讯云 / 内网虚拟机），
#                    负责装系统依赖、拉代码、建 venv、下数据包、配 systemd
#
# 用法（root）：
#   sudo bash deploy/install_vps.sh
#   或 repo 还没拉下来时：
#   curl -fsSL https://raw.githubusercontent.com/HML05/AIfootball/main/deploy/install_vps.sh | sudo bash
#
# 可用环境变量覆盖（默认值见下）：
#   PORT=8000                     对外端口
#   APP_DIR=/opt/aifootball       安装目录
#   REPO=https://github.com/HML05/AIfootball.git
#   PACK_URL=<Release 数据包地址>  数据库缺失时才下载
#   PIP_MIRROR=https://pypi.tuna.tsinghua.edu.cn/simple
#   SERVICE_NAME=aifootball       systemd 服务名
#   SWAP_MB=2048                  没有 swap 时创建多大的交换文件（0 = 不创建）
#   DRY_RUN=1                     只打印将要执行的动作，不落盘
#
# 本脚本可重复执行（幂等）：已拉过代码就 fetch/reset，已有 .env 就不覆盖，
# 数据库已在就不再下载数据包。
#
# 自检：bash scripts/verify_install_vps.sh（用桩命令跑，不需要真云主机）
# ═══════════════════════════════════════════════════════════════════════════════
set -euo pipefail

PORT="${PORT:-8000}"
APP_DIR="${APP_DIR:-/opt/aifootball}"
REPO="${REPO:-https://github.com/HML05/AIfootball.git}"
PACK_URL="${PACK_URL:-https://github.com/HML05/AIfootball/releases/download/data-pack-v1/aifootball-data-pack-v1.tar.gz}"
PIP_MIRROR="${PIP_MIRROR:-https://pypi.tuna.tsinghua.edu.cn/simple}"
SERVICE_NAME="${SERVICE_NAME:-aifootball}"
SWAP_MB="${SWAP_MB:-2048}"
DRY_RUN="${DRY_RUN:-0}"
# 这几个只在自检里被覆盖，好让脚本写到临时目录而不是真的系统目录
SWAPFILE="${SWAPFILE:-/swapfile}"
FSTAB="${FSTAB:-/etc/fstab}"
SYSTEMD_DIR="${SYSTEMD_DIR:-/etc/systemd/system}"

log()  { echo "[install] $*"; }
warn() { echo "[install] 警告：$*" >&2; }
die()  { echo "[install] 失败：$*" >&2; exit 1; }

# run：统一走这里，DRY_RUN=1 时只打印不执行
run() {
  if [ "$DRY_RUN" = "1" ]; then
    log "[dry-run] $*"
    return 0
  fi
  log "$*"
  "$@"
}

[ "$(id -u)" = "0" ] || die "请用 root 运行：sudo bash $0"
command -v apt-get >/dev/null 2>&1 || die "这个脚本只支持 Ubuntu/Debian（需要 apt-get）"

log "FootballAI 安装开始：PORT=$PORT APP_DIR=$APP_DIR DRY_RUN=$DRY_RUN"

# ── 1. 系统依赖 ───────────────────────────────────────────────────────────────
log "1/8 安装系统依赖（python3-venv / git / curl / tar）"
run apt-get update -qq
DEBIAN_FRONTEND=noninteractive run apt-get install -y -qq \
  python3 python3-venv python3-pip git curl ca-certificates tar
command -v python3 >/dev/null 2>&1 || die "python3 装完仍找不到，请检查 apt 源"
PY_VER="$(python3 -c 'import sys; print("%d.%d" % sys.version_info[:2])')"
log "     python3 版本：$PY_VER"

# ── 2. swap（2 GiB 小机器上 pandas 峰值时的保险）────────────────────────────────
if [ "$SWAP_MB" != "0" ]; then
  if swapon --show 2>/dev/null | grep -q .; then
    log "2/8 已有 swap，跳过"
  elif [ -f "$SWAPFILE" ]; then
    log "2/8 交换文件 $SWAPFILE 已存在，直接启用"
    run chmod 600 "$SWAPFILE"
    run swapon "$SWAPFILE" || warn "启用 $SWAPFILE 失败"
  else
    log "2/8 创建 ${SWAP_MB} MB 交换文件（$SWAPFILE）"
    run fallocate -l "${SWAP_MB}M" "$SWAPFILE" || dd if=/dev/zero of="$SWAPFILE" bs=1M count="$SWAP_MB"
    run chmod 600 "$SWAPFILE"
    run mkswap "$SWAPFILE"
    run swapon "$SWAPFILE" || warn "启用 swap 失败"
    if ! grep -q "^$SWAPFILE " "$FSTAB" 2>/dev/null; then
      if [ "$DRY_RUN" = "1" ]; then
        log "[dry-run] 追加 '$SWAPFILE none swap sw 0 0' 到 $FSTAB"
      else
        echo "$SWAPFILE none swap sw 0 0" >> "$FSTAB"
        log "    已写入 $FSTAB（重启后自动挂载）"
      fi
    fi
  fi
else
  log "2/8 SWAP_MB=0，跳过 swap"
fi

# ── 3. 拉代码 ─────────────────────────────────────────────────────────────────
if [ -d "$APP_DIR/.git" ]; then
  log "3/8 更新已有仓库：$APP_DIR"
  run git -C "$APP_DIR" fetch --depth 1 origin main
  run git -C "$APP_DIR" reset --hard origin/main
  run git -C "$APP_DIR" clean -fd -e .env -e data -e models
else
  log "3/8 克隆仓库到 $APP_DIR"
  run mkdir -p "$(dirname "$APP_DIR")"
  run git clone --depth 1 "$REPO" "$APP_DIR"
fi
[ "$DRY_RUN" = "1" ] || [ -f "$APP_DIR/requirements-deploy.txt" ] || die "$APP_DIR 里没有 requirements-deploy.txt，仓库不完整？"

# ── 4. venv + 依赖 ────────────────────────────────────────────────────────────
log "4/8 准备 Python 环境（venv + 运行依赖）"
if [ "$DRY_RUN" = "1" ] || [ ! -x "$APP_DIR/.venv/bin/python" ]; then
  run python3 -m venv "$APP_DIR/.venv"
fi
if [ "$DRY_RUN" = "1" ]; then
  log "[dry-run] $APP_DIR/.venv/bin/pip install -i $PIP_MIRROR -r $APP_DIR/requirements-deploy.txt"
else
  "$APP_DIR/.venv/bin/pip" install --quiet --upgrade pip
  "$APP_DIR/.venv/bin/pip" install --quiet -i "$PIP_MIRROR" -r "$APP_DIR/requirements-deploy.txt"
fi

# ── 5. 数据包（只在缺主库时下载）──────────────────────────────────────────────
DB_FILE="$APP_DIR/data/database/football.db"
SEARCH_DB="$APP_DIR/data/database/search.db"
if [ ! -f "$DB_FILE" ]; then
  log "5/8 未找到数据库，下载数据包：$PACK_URL"
  if [ "$DRY_RUN" = "1" ]; then
    log "[dry-run] curl -fL --retry 3 -o /tmp/aifootball-pack.tar.gz $PACK_URL && tar -xzf - -C $APP_DIR"
  elif curl -fL --retry 3 --retry-delay 2 -o /tmp/aifootball-pack.tar.gz "$PACK_URL"; then
    tar -xzf /tmp/aifootball-pack.tar.gz -C "$APP_DIR"
    rm -f /tmp/aifootball-pack.tar.gz
    log "    数据包解包完成"
  else
    warn "数据包下载失败 —— 服务仍会启动，但预测/检索没有真实数据"
    warn "可以手动把 aifootball-data-pack-v1.tar.gz 放到服务器再执行：tar -xzf 那个包 -C $APP_DIR"
  fi
else
  log "5/8 数据库已存在，跳过数据包下载"
fi

if [ ! -f "$DB_FILE" ]; then
  warn "数据库仍然缺失（$DB_FILE），界面会看不到数据"
fi

# 检索索引是独立库，数据包里有；万一没有就现场重建（离线可做，几十秒）
if [ -f "$DB_FILE" ] && [ ! -f "$SEARCH_DB" ]; then
  log "    未找到检索索引，现场重建…"
  if [ "$DRY_RUN" = "1" ]; then
    log "[dry-run] $APP_DIR/.venv/bin/python $APP_DIR/scripts/build_search_index.py"
  else
    "$APP_DIR/.venv/bin/python" "$APP_DIR/scripts/build_search_index.py" \
      || warn "索引重建失败，检索与问答会不可用"
  fi
fi

# ── 6. .env（已存在就不动）────────────────────────────────────────────────────
ENV_FILE="$APP_DIR/.env"
if [ -f "$ENV_FILE" ]; then
  log "6/8 .env 已存在，保持原样（要改就编辑 $ENV_FILE）"
elif [ "$DRY_RUN" = "1" ]; then
  log "[dry-run] 写入 $ENV_FILE（公网安全开关 + 大模型地址）"
else
  log "6/8 生成 $ENV_FILE"
  cat > "$ENV_FILE" <<EOF
# ── 由 deploy/install_vps.sh 生成；改完执行 systemctl restart $SERVICE_NAME ──
# 公网部署安全开关：必须登录、关闭自助注册、重置码只进日志不回显
UI_REQUIRE_AUTH=true
AUTH_ALLOW_REGISTER=false
AUTH_RESET_SHOW_CODE=false
DEBUG=false
# 没有配数据源 key，定时抓取开着只会刷日志
ENABLE_DAILY_UPDATE=false
ENABLE_LIVE_SCORE_UPDATE=false
SERVER_PORT=$PORT
# 大模型：填上 key 后问答会从「检索摘要」升级为「真模型作答」
LLM_BASE_URL=https://api.deepseek.com
LLM_MODEL=deepseek-flash
LLM_API_KEY=
# 数据包地址（换新数据包时改这里）
DATA_PACK_URL=$PACK_URL
EOF
  chmod 600 "$ENV_FILE"
fi

# ── 7. systemd 常驻服务 ───────────────────────────────────────────────────────
UNIT_FILE="$SYSTEMD_DIR/$SERVICE_NAME.service"
log "7/8 写 systemd 服务：$UNIT_FILE"
if [ "$DRY_RUN" = "1" ]; then
  log "[dry-run] 生成 $UNIT_FILE 并 systemctl daemon-reload && systemctl enable --now $SERVICE_NAME"
else
  mkdir -p "$SYSTEMD_DIR"
  cat > "$UNIT_FILE" <<EOF
[Unit]
Description=FootballAI（FastAPI + 静态前端，单 worker）
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory=$APP_DIR
EnvironmentFile=-$ENV_FILE
Environment=PYTHONUNBUFFERED=1
ExecStart=$APP_DIR/.venv/bin/python -m uvicorn src.main:app --host 0.0.0.0 --port $PORT --workers 1
Restart=always
RestartSec=5
# 内存：启动即载 shap + 模型，常驻约 0.7~1.2 GB（见 deploy/footballai.service 注释），
# 所以这里不设 MemoryMax —— 2 GiB 的机器靠上面那个 swap 兜住峰值，设硬上限反而会被 OOM 杀掉。
StandardOutput=journal
StandardError=journal
SyslogIdentifier=$SERVICE_NAME

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable --now "$SERVICE_NAME"
fi

# ── 8. 等健康检查 ─────────────────────────────────────────────────────────────
log "8/8 等待服务就绪（http://127.0.0.1:$PORT/health）"
if [ "$DRY_RUN" = "1" ]; then
  log "[dry-run] 轮询 /health 最多 60 秒"
  exit 0
fi

HEALTHY=0
for _ in $(seq 1 30); do
  if curl -fsS "http://127.0.0.1:$PORT/health" >/dev/null 2>&1; then
    HEALTHY=1
    break
  fi
  sleep 2
done

if [ "$HEALTHY" != "1" ]; then
  echo "[install] 失败：服务 60 秒内没有通过 /health 检查，最近日志：" >&2
  journalctl -u "$SERVICE_NAME" -n 40 --no-pager >&2 || true
  exit 1
fi

log "✅ 部署完成"
log "   本机自检：curl http://127.0.0.1:$PORT/health"
log "   对外访问：http://<这台机器的公网 IP>:$PORT"
log "   服务管理：systemctl status|restart|stop $SERVICE_NAME ；看日志 journalctl -u $SERVICE_NAME -f"
log "   还没做的两件事："
log "     1) 云控制台的防火墙要放行 $PORT 端口（默认只开 22）"
log "     2) 首次登录 admin / football2026 后，点右上角头像 → 账号设置 → 密码，把默认密码改掉"
