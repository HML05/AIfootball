#!/bin/sh
# ═══════════════════════════════════════════════════════════════════════════════
# deploy/entrypoint.sh 的自检（POSIX sh；本机没装 docker 也能验）
#
# 为什么需要它：容器入口脚本决定「镜像里没有数据时能不能自己把数据包拉下来」，
# 这条路径只在云端容器里跑，本机最容易漏测。这里把脚本里写死的 /app 换成一个
# 临时目录、用桩命令顶替 uvicorn/python，然后把五种情况都真跑一遍：
#   1. 库不存在 + 数据包地址可用  → 下载、解开、四个关键文件都到位、最后 exec uvicorn
#   2. 库已存在                   → 不再下载
#   3. 数据包地址不可用           → 给出警告但仍继续启动
#   4. 库与模型都缺且没配地址      → 两条警告，不崩
#   5. 有主库但缺检索索引          → 走「现场重建索引」分支
#
# 用法：
#   sh scripts/verify_entrypoint.sh /path/to/aifootball-data-pack-v1.tar.gz
#   DATA_PACK=/path/to/pack.tar.gz sh scripts/verify_entrypoint.sh
# 找不到数据包会 exit 2（先跑 python scripts/make_data_pack.py 生成）。
# ═══════════════════════════════════════════════════════════════════════════════
set -u

REPO=$(cd "$(dirname "$0")/.." && pwd)
WORK="${TMPDIR:-/tmp}/fa_entrypoint_check_$$"
PACK="${1:-${DATA_PACK:-}}"

pass=0
fail=0
ok()  { echo "  [PASS] $1"; pass=$((pass + 1)); }
bad() { echo "  [FAIL] $1"; fail=$((fail + 1)); }

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT INT TERM

if [ -z "$PACK" ] || [ ! -f "$PACK" ]; then
  echo "[x] 没找到数据包（用法：sh scripts/verify_entrypoint.sh <数据包路径>）"
  echo "    先生成：python scripts/make_data_pack.py"
  exit 2
fi

# curl 认的是 URL；Windows 上的 file:// 必须写成 file:///D:/... 这种盘符形式
case "$PACK" in
  /[a-zA-Z]/*)                     # MSYS/Git Bash 的 /d/dir/file
    DRIVE=$(echo "$PACK" | cut -c2 | tr 'a-z' 'A-Z')
    REST=$(echo "$PACK" | cut -c3-)
    PACK_URL="file:///$DRIVE:$REST"
    ;;
  [a-zA-Z]:[\\/]*)                 # 已经像 D:\dir\file
    PACK_URL="file:///$(echo "$PACK" | tr '\\' '/')"
    ;;
  *) PACK_URL="file://$PACK" ;;
esac

echo "数据包: $PACK"
echo "        $(wc -c < "$PACK" | tr -d ' ') 字节"
echo "脚本:   $REPO/deploy/entrypoint.sh"
echo

rm -rf "$WORK"
mkdir -p "$WORK/app" "$WORK/bin"

sed "s#/app#$WORK/app#g" "$REPO/deploy/entrypoint.sh" > "$WORK/entry.sh"
if grep -q "$WORK/app" "$WORK/entry.sh"; then
  ok "把脚本里的 /app 换成了临时目录"
else
  bad "替换 /app 失败"
fi

# 桩：uvicorn 只回显参数（别真起服务），python 直接成功
printf '#!/bin/sh\necho "[stub-uvicorn] $@"\n' > "$WORK/bin/uvicorn"
printf '#!/bin/sh\necho "[stub-python] $@"\n' > "$WORK/bin/python"
chmod +x "$WORK/bin/uvicorn" "$WORK/bin/python" "$WORK/entry.sh"

run_entry() {  # run_entry [额外环境变量…]
  ( cd "$WORK" && env PATH="$WORK/bin:$PATH" "$@" sh "$WORK/entry.sh" 2>&1 ) || true
}

echo
echo "== 场景 1：库不存在 + 数据包可用 → 应下载并解开 =="
out1=$(run_entry DATA_PACK_URL="$PACK_URL" PORT=9999)
echo "$out1" | grep -q "数据包解包完成" && ok "报告了解包完成" || bad "没有解包成功的提示"
[ -f "$WORK/app/data/database/football.db" ] && ok "football.db 已就位" || bad "football.db 缺失"
[ -f "$WORK/app/data/database/search.db" ] && ok "search.db 已就位" || bad "search.db 缺失"
[ -f "$WORK/app/models/xgb_match_predictor.joblib" ] && ok "预测模型已就位" || bad "预测模型缺失"
[ -f "$WORK/app/data/processed/all_matches.csv" ] && ok "特征 CSV 已就位" || bad "特征 CSV 缺失"
echo "$out1" | grep -q "\[stub-uvicorn\] src.main:app --host 0.0.0.0 --port 9999 --workers 1" \
  && ok "最后 exec 起 uvicorn（单 worker、端口取自 PORT）" || bad "没有 exec uvicorn 或参数不对"
echo "$out1" | grep -q "LLM_API_KEY = 未配置" && ok "配置回显能反映密钥状态" || bad "配置回显异常"
echo "$out1" | grep -q "已配置" && bad "回显里泄露了密钥状态以外的内容" || ok "回显里没有出现密钥本身"

echo
echo "== 场景 2：库已存在 → 不该再下载 =="
out2=$(run_entry DATA_PACK_URL="$PACK_URL" PORT=9999)
echo "$out2" | grep -q "尝试下载数据包" && bad "库已存在却仍然下载" || ok "库已存在时跳过下载"
echo "$out2" | grep -q "有效配置" && ok "仍然打印了有效配置" || bad "没有打印有效配置"

echo
echo "== 场景 3：数据包地址不可用 → 警告后继续启动 =="
rm -rf "$WORK/app/data"
out3=$(run_entry DATA_PACK_URL="file:///nonexistent/nope.tar.gz" PORT=9999)
echo "$out3" | grep -q "警告：数据包下载失败" && ok "下载失败给了警告" || bad "下载失败没有警告"
echo "$out3" | grep -q "\[stub-uvicorn\]" && ok "下载失败仍继续启动服务" || bad "下载失败后没有继续启动"

echo
echo "== 场景 4：库与模型都缺、又没配地址 → 警告但不崩 =="
rm -rf "$WORK/app/data" "$WORK/app/models"
out4=$(run_entry PORT=9999)
echo "$out4" | grep -q "警告：数据库不存在" && ok "提示数据库不存在" || bad "没有提示数据库不存在"
echo "$out4" | grep -q "警告：预测模型不存在" && ok "提示模型不存在" || bad "没有提示模型不存在"
echo "$out4" | grep -q "\[stub-uvicorn\]" && ok "仍然启动服务" || bad "没有启动服务"

echo
echo "== 场景 5：有主库但缺检索索引 → 现场重建 =="
mkdir -p "$WORK/app/data/database"
tar -xzf "$PACK" -C "$WORK/app" data/database/football.db models 2>/dev/null
rm -f "$WORK/app/data/database/search.db"
out5=$(run_entry PORT=9999)
echo "$out5" | grep -q "现场重建" && ok "缺索引时走重建分支" || bad "缺索引时没有重建"
echo "$out5" | grep -q "scripts/build_search_index.py" && ok "调用的是 scripts/build_search_index.py" || bad "重建命令不对"

echo
echo "----------------------------------------------------------------------"
echo "结果: $pass 通过 / $fail 失败"
[ "$fail" -eq 0 ] || exit 1
exit 0
