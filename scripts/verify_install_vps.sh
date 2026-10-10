#!/usr/bin/env bash
# ═══════════════════════════════════════════════════════════════════════════════
# deploy/install_vps.sh 的自检（不需要真云主机）
#
# 做法：把 apt-get / git / python3 / pip / curl / tar / systemctl / swapon 全部换成
# 桩命令（写调用日志 + 造出脚本期待的文件），然后按场景跑安装脚本，断言它
#   · 装对了系统依赖、建了 venv、用镜像装依赖
#   · 只在缺主库时下载数据包、缺索引时重建
#   · 生成 .env 时把公网安全开关都写对（UI_REQUIRE_AUTH / AUTH_ALLOW_REGISTER / DEBUG …）
#   · systemd 单元里的 ExecStart 是单 worker、绑 0.0.0.0、端口取自 PORT
#   · 可重复执行：第二次是 fetch/reset 而不是 clone，.env 不被覆盖、数据包不再下载
#   · DRY_RUN 时什么都不落盘；非 root、健康检查超时都明确失败
#
# 用法：bash scripts/verify_install_vps.sh
# ═══════════════════════════════════════════════════════════════════════════════
set -uo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT="$ROOT/deploy/install_vps.sh"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

PASS=0
FAIL=0
ok()   { echo "[ok] $1";   PASS=$((PASS + 1)); }
bad()  { echo "[FAIL] $1"; FAIL=$((FAIL + 1)); }
check() { if [ "$2" = "1" ]; then ok "$1"; else bad "$1"; fi }
has()  { if [ -f "$1" ] && grep -qF -- "$2" "$1" 2>/dev/null; then echo 1; else echo 0; fi }
hasnt() { if [ -f "$1" ] && grep -qF -- "$2" "$1" 2>/dev/null; then echo 0; else echo 1; fi }
contains() { case "$1" in *"$2"*) echo 1 ;; *) echo 0 ;; esac; }

[ -f "$SCRIPT" ] || { echo "找不到 $SCRIPT"; exit 1; }

# ── 桩命令 ────────────────────────────────────────────────────────────────────
mkdir -p "$TMP/bin"
mkstub() { # mkstub <name> <<'EOF' … EOF
  cat > "$TMP/bin/$1"
  chmod +x "$TMP/bin/$1"
}

mkstub id <<'EOF'
#!/bin/sh
echo "${FA_ID:-0}"
EOF

mkstub apt-get <<'EOF'
#!/bin/sh
echo "apt-get $*" >> "$FA_CALLS"
exit 0
EOF

mkstub swapon <<'EOF'
#!/bin/sh
echo "swapon $*" >> "$FA_CALLS"
if [ "${1:-}" = "--show" ]; then
  [ "${FA_HAS_SWAP:-0}" = "1" ] && echo "/swapfile file 2G 0B used"
  exit 0
fi
exit 0
EOF

mkstub fallocate <<'EOF'
#!/bin/sh
echo "fallocate $*" >> "$FA_CALLS"
target=""
for a in "$@"; do target="$a"; done
[ -n "$target" ] && : > "$target"
exit 0
EOF

mkstub mkswap <<'EOF'
#!/bin/sh
echo "mkswap $*" >> "$FA_CALLS"
exit 0
EOF

# chmod 也桩掉：只为记下「脚本确实对 .env 收紧过权限」，
# 因为 Windows 的 Git Bash 上 chmod 600 是空操作（stat 恒为 644），
# 真正的权限位校验留给 Linux（本机 WSL/CI）。
mkstub chmod <<'EOF'
#!/bin/sh
echo "chmod $*" >> "$FA_CALLS"
exit 0
EOF

mkstub git <<'EOF'
#!/bin/sh
echo "git $*" >> "$FA_CALLS"
if [ "${1:-}" = "clone" ]; then
  dest=""
  for a in "$@"; do dest="$a"; done
  mkdir -p "$dest/.git"
  cp -r "$FA_SKELETON"/. "$dest"/ 2>/dev/null || true
fi
exit 0
EOF

mkstub python3 <<'EOF'
#!/bin/sh
echo "python3 $*" >> "$FA_CALLS"
if [ "${1:-}" = "-c" ]; then echo "3.12.3"; exit 0; fi
if [ "${1:-}" = "-m" ] && [ "${2:-}" = "venv" ]; then
  d="$3"
  mkdir -p "$d/bin"
  cat > "$d/bin/python" <<'PY'
#!/bin/sh
echo "venv-python $*" >> "$FA_CALLS"
exit 0
PY
  cat > "$d/bin/pip" <<'PIP'
#!/bin/sh
echo "venv-pip $*" >> "$FA_CALLS"
exit 0
PIP
  chmod +x "$d/bin/python" "$d/bin/pip"
  exit 0
fi
exit 0
EOF

mkstub curl <<'EOF'
#!/bin/sh
echo "curl $*" >> "$FA_CALLS"
out=""
prev=""
url=""
for a in "$@"; do
  [ "$prev" = "-o" ] && out="$a"
  prev="$a"
  url="$a"
done
case "$url" in
  */health) exit "${FA_HEALTH:-0}" ;;
  *releases/download*)
    [ "${FA_PACK_FAIL:-0}" = "1" ] && exit 22
    [ -n "$out" ] && printf 'fake-tarball-bytes' > "$out"
    exit 0 ;;
esac
exit 0
EOF

mkstub tar <<'EOF'
#!/bin/sh
echo "tar $*" >> "$FA_CALLS"
dir=""
prev=""
for a in "$@"; do
  [ "$prev" = "-C" ] && dir="$a"
  prev="$a"
done
[ -z "$dir" ] && exit 0
mkdir -p "$dir/data/database" "$dir/models"
: > "$dir/data/database/football.db"
[ "${FA_TAR_NO_SEARCH:-0}" = "1" ] || : > "$dir/data/database/search.db"
: > "$dir/models/xgb_match_predictor.pkl.joblib"
exit 0
EOF

for name in systemctl journalctl sleep; do
  mkstub "$name" <<'EOF'
#!/bin/sh
echo "$(basename "$0") $*" >> "$FA_CALLS"
exit 0
EOF
done

# ── 假仓库骨架（git clone 桩会把它复制到 APP_DIR）──────────────────────────────
FA_SKELETON="$TMP/skeleton"
mkdir -p "$FA_SKELETON/scripts"
echo "fastapi==0.141.1" > "$FA_SKELETON/requirements-deploy.txt"
echo "# stub" > "$FA_SKELETON/scripts/build_search_index.py"

# ── 场景默认值 ────────────────────────────────────────────────────────────────
reset_scenario() { # reset_scenario <名字>
  SCEN="$1"
  FA_APP="$TMP/$SCEN/app"
  FA_SYSD="$TMP/$SCEN/systemd"
  FA_SWAP="$TMP/$SCEN/swapfile"
  FA_FSTAB="$TMP/$SCEN/fstab"
  FA_PORT="8000"
  FA_SWAPMB="2048"
  FA_DRYRUN="0"
  FA_HEALTH="0"
  FA_PACK_FAIL="0"
  FA_TAR_NO_SEARCH="0"
  FA_ID="0"
  FA_HAS_SWAP="0"
  FA_CALLS="$TMP/$SCEN/calls.log"
  mkdir -p "$TMP/$SCEN"
  : > "$FA_FSTAB"
}

OUT=""
RCPT=1
run_install() {
  OUT=$( PATH="$TMP/bin:$PATH" \
         FA_CALLS="$FA_CALLS" FA_SKELETON="$FA_SKELETON" \
         APP_DIR="$FA_APP" SYSTEMD_DIR="$FA_SYSD" SWAPFILE="$FA_SWAP" FSTAB="$FA_FSTAB" \
         PORT="$FA_PORT" SWAP_MB="$FA_SWAPMB" DRY_RUN="$FA_DRYRUN" \
         FA_HEALTH="$FA_HEALTH" FA_PACK_FAIL="$FA_PACK_FAIL" FA_TAR_NO_SEARCH="$FA_TAR_NO_SEARCH" \
         FA_ID="$FA_ID" FA_HAS_SWAP="$FA_HAS_SWAP" \
         bash "$SCRIPT" 2>&1 )
  RCPT=$?
}

echo "── 场景 1：全新安装 ──────────────────────────────────────────────────────"
reset_scenario fresh
run_install
UNIT="$FA_SYSD/aifootball.service"
ENVF="$FA_APP/.env"
check "全新安装退出码 0" "$([ "$RCPT" = 0 ] && echo 1 || echo 0)"
check "装了 python3-venv / git / curl" "$(has "$FA_CALLS" "apt-get install" )"
check "apt 清单里有 python3-venv" "$([ "$(has "$FA_CALLS" "python3-venv")" = 1 ] && echo 1 || echo 0)"
check "创建了 2048M 交换文件" "$(has "$FA_CALLS" "fallocate -l 2048M")"
check "swap 写进 fstab" "$(has "$FA_FSTAB" "$FA_SWAP none swap sw 0 0")"
check "用了数据包下载（git clone 之前先拉仓库）" "$(has "$FA_CALLS" "git clone --depth 1")"
check "建了 venv" "$(has "$FA_CALLS" "python3 -m venv")"
check "pip 走镜像源装运行依赖" "$(has "$FA_CALLS" "-i https://pypi.tuna.tsinghua.edu.cn/simple -r")"
check "requirements-deploy.txt 被使用" "$(has "$FA_CALLS" "requirements-deploy.txt")"
check "下载了数据包" "$(has "$FA_CALLS" "releases/download/data-pack-v1")"
check "解包到 APP_DIR" "$(has "$FA_CALLS" "tar -xzf /tmp/aifootball-pack.tar.gz -C $FA_APP")"
check "生成了 .env" "$([ -f "$ENVF" ] && echo 1 || echo 0)"
check ".env：强制登录" "$(has "$ENVF" "UI_REQUIRE_AUTH=true")"
check ".env：关闭自助注册" "$(has "$ENVF" "AUTH_ALLOW_REGISTER=false")"
check ".env：重置码不回显" "$(has "$ENVF" "AUTH_RESET_SHOW_CODE=false")"
check ".env：DEBUG 关掉" "$(has "$ENVF" "DEBUG=false")"
check ".env：每日抓取关掉" "$(has "$ENVF" "ENABLE_DAILY_UPDATE=false")"
check ".env：实时比分关掉" "$(has "$ENVF" "ENABLE_LIVE_SCORE_UPDATE=false")"
check ".env：key 占位为空" "$(has "$ENVF" "LLM_API_KEY=")"
# 权限位这条要分平台，但只算一条断言（好让 Windows 与 Linux/CI 的计数一致）：
#   Linux：直接看 .env 的权限位是不是 600
#   其它平台：Git Bash 的 chmod 是空操作（stat 恒 644），改查「脚本确实调用了 chmod 600」
if [ "$(uname -s 2>/dev/null)" = "Linux" ]; then
  check ".env 权限位真的是 600（Linux 校验）" "$([ "$(stat -c %a "$ENVF" 2>/dev/null)" = "600" ] && echo 1 || echo 0)"
else
  check ".env 收紧了权限（$(uname -s 2>/dev/null) 上查 chmod 600 调用）" "$(has "$FA_CALLS" "chmod 600 $ENVF")"
fi
check "写了 systemd 单元" "$([ -f "$UNIT" ] && echo 1 || echo 0)"
check "单元里 WorkingDirectory 正确" "$(has "$UNIT" "WorkingDirectory=$FA_APP")"
check "单元里 ExecStart 绑 0.0.0.0:8000 单 worker" "$(has "$UNIT" "--host 0.0.0.0 --port 8000 --workers 1")"
check "单元里 Restart=always" "$(has "$UNIT" "Restart=always")"
check "单元里读 .env（EnvironmentFile 可缺省）" "$(has "$UNIT" "EnvironmentFile=-$ENVF")"
check "systemctl daemon-reload 被调用" "$(has "$FA_CALLS" "systemctl daemon-reload")"
check "systemctl enable --now aifootball 被调用" "$(has "$FA_CALLS" "systemctl enable --now aifootball")"
check "轮询了 /health" "$(has "$FA_CALLS" "curl -fsS http://127.0.0.1:8000/health")"
check "输出里给了部署完成与后续两步" "$([ "$(contains "$OUT" "✅ 部署完成")$(contains "$OUT" "放行 8000")" = "11" ] && echo 1 || echo 0)"

echo
echo "── 场景 2：重复执行（幂等）───────────────────────────────────────────────"
echo "# 手工标记，用来确认 .env 不被覆盖" >> "$ENVF"
CALLS2="$TMP/fresh/calls2.log"
: > "$CALLS2"
FA_CALLS="$CALLS2"
run_install
check "第二次执行退出码 0" "$([ "$RCPT" = 0 ] && echo 1 || echo 0)"
check "第二次是 fetch/reset 而不是 clone" "$([ "$(has "$CALLS2" "git -C $FA_APP fetch")" = 1 ] && [ "$(hasnt "$CALLS2" "git clone")" = 1 ] && echo 1 || echo 0)"
check "第二次不再下载数据包" "$(hasnt "$CALLS2" "releases/download/data-pack-v1")"
check "第二次不覆盖 .env" "$(has "$ENVF" "手工标记，用来确认 .env 不被覆盖")"
check "第二次不再建 venv" "$(hasnt "$CALLS2" "python3 -m venv")"

echo
echo "── 场景 3：换端口 ────────────────────────────────────────────────────────"
reset_scenario port
FA_PORT="9000"
run_install
check "端口覆盖生效（--port 9000）" "$(has "$FA_SYSD/aifootball.service" "--port 9000")"
check "端口覆盖进了 .env（SERVER_PORT=9000）" "$(has "$FA_APP/.env" "SERVER_PORT=9000")"
check "健康检查打的是 9000" "$(has "$FA_CALLS" "http://127.0.0.1:9000/health")"

echo
echo "── 场景 4：数据包下载失败 ────────────────────────────────────────────────"
reset_scenario packfail
FA_PACK_FAIL="1"
run_install
check "下载失败仍继续（退出码 0）" "$([ "$RCPT" = 0 ] && echo 1 || echo 0)"
check "明确警告数据包失败" "$(contains "$OUT" "数据包下载失败")"
check "没有数据库时也警告了" "$(contains "$OUT" "界面会看不到数据")"
check "缺库时不尝试重建索引" "$(hasnt "$FA_CALLS" "build_search_index.py")"

echo
echo "── 场景 5：数据包缺检索索引 ──────────────────────────────────────────────"
reset_scenario noindex
FA_TAR_NO_SEARCH="1"
run_install
check "缺 search.db 时现场重建" "$([ "$(has "$FA_CALLS" "venv-python $FA_APP/scripts/build_search_index.py")" = "1" ] && echo 1 || echo 0)"

echo
echo "── 场景 6：健康检查一直不过 ──────────────────────────────────────────────"
reset_scenario sick
FA_HEALTH="7"
run_install
check "健康检查失败 → 退出码 1" "$([ "$RCPT" = 1 ] && echo 1 || echo 0)"
check "报错说清了是 /health 没过" "$(contains "$OUT" "没有通过 /health 检查")"
check "顺带打了 journalctl 日志" "$(has "$FA_CALLS" "journalctl -u aifootball")"

echo
echo "── 场景 7：非 root ───────────────────────────────────────────────────────"
reset_scenario nonroot
FA_ID="1000"
run_install
check "非 root 直接失败" "$([ "$RCPT" = 1 ] && echo 1 || echo 0)"
check "提示要 sudo" "$(contains "$OUT" "请用 root 运行")"
check "非 root 时什么都没装" "$([ "$(hasnt "$FA_CALLS" "apt-get install")" = 1 ] && [ ! -d "$FA_APP" ] && echo 1 || echo 0)"

echo
echo "── 场景 8：DRY_RUN ───────────────────────────────────────────────────────"
reset_scenario dry
FA_DRYRUN="1"
run_install
check "DRY_RUN 退出码 0" "$([ "$RCPT" = 0 ] && echo 1 || echo 0)"
check "DRY_RUN 不建 APP_DIR" "$([ ! -d "$FA_APP" ] && echo 1 || echo 0)"
check "DRY_RUN 不写 systemd 单元" "$([ ! -d "$FA_SYSD" ] && echo 1 || echo 0)"
check "DRY_RUN 不改 fstab" "$([ ! -s "$FA_FSTAB" ] && echo 1 || echo 0)"
check "DRY_RUN 会说明将要轮询健康检查" "$(contains "$OUT" "轮询 /health")"

echo
echo "── 场景 9：机器已有 swap ─────────────────────────────────────────────────"
reset_scenario hasswap
FA_HAS_SWAP="1"
run_install
check "已有 swap 时不再创建" "$(hasnt "$FA_CALLS" "fallocate")"
check "已有 swap 时也不 mkswap" "$(hasnt "$FA_CALLS" "mkswap")"
check "仍然完成部署" "$([ "$RCPT" = 0 ] && echo 1 || echo 0)"

echo
echo "──────────────────────────────────────────────────────────────────────────"
echo "通过 $PASS，失败 $FAIL"
[ "$FAIL" = 0 ] || exit 1
echo "[ok] deploy/install_vps.sh 自检全部通过"
