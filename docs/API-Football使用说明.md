# API-Football 使用说明（补齐裁判 / 阵容 / 事件 / 体重 · 国籍 / 主教练 / 伤停）

> 配套代码已写好，**不需要先付费**：先用免费档验证覆盖，确认值得再花 $19 买一个月 Pro。

## 一、能补什么、不能补什么

| 数据 | 端点 | 能否补 | 说明 |
|---|---|---|---|
| **裁判** | `fixtures`（内含 `referee`） | ✅ | 按"联赛+赛季"一次拿全季，**几乎不花请求** |
| **主教练** | `coachs?team=` | ✅ | 取 career 中 end 为空的现任 |
| **比赛阵容** | `fixtures/lineups?fixture=` | ✅ | 每场 1 次 |
| **比赛事件** | `fixtures/events?fixture=` | ✅ | 进球/牌/换人时间轴，每场 1 次 |
| **球员体重** | `players?team=&season=` | ✅ | 我们缺的字段，API-Football 有 |
| **球员国籍/身高/照片** | `players` | ✅ | **按 ID 精确补**（我们的 `qxz_id` 就是它的球员 id） |
| **伤停** | `injuries?league=&season=` | ✅ | 按联赛+赛季 1 次 |
| **历史积分榜** | `standings?league=&season=` | ✅ | 可补 2122/2223 |
| 球员身价/市值 | — | ❌ | 不提供（已用 Transfermarkt 90 万条市值解决） |
| 非五大联赛官方 xG | — | ❌ | 覆盖不一致（已用 Understat + 代理 xG 解决） |

## 二、三步走

> **前置说明（2026-09 核实）**：API-Football 已**不再提供可用的免费档**；同时我们逐一验证了
> 其他免费替代源，**全部不可用或覆盖极小**（详见文末"免费替代源验证结果"）。
> 因此直接购买 Pro 是唯一现实路径；但验证覆盖只需 **50 次请求**（Pro 有 7,500 次/天），
> 买完第一分钟即可验完，风险极低。

### 第 1 步：购买 Pro（$19 / 月，7500 次/天）并立即验证覆盖

1. 打开 https://dashboard.api-football.com ，在 Subscription 页选
   **Football (Soccer) Pro, 1 Month, 1 Seat**（页面写明 **不自动续费**，到期自动停止）；
2. 复制 API key，写入 `.env`：

```env
API_SPORTS_KEY=你的key
AF_MIN_INTERVAL=0.25     # Pro 档 300 次/分钟
AF_DAILY_BUDGET=7000     # 留 500 次余量
```

3. **立刻**运行覆盖检查（10 赛事 × 5 赛季 = 50 次请求，占当日配额 0.7%）：

```powershell
python scripts/check_af_coverage.py
```

输出会逐条打印 `events=✅ lineups=✅ players=✅ injuries=✅ ...`，汇总"每类数据有多少联赛-赛季可用"，并写入 `data/af_coverage.json`。**若某赛事覆盖不足，后续阶段可只跑覆盖好的赛事，避免浪费请求。**

### 第 2 步：分阶段回填（支持断点续传）

```powershell
# 预估请求数（不消耗）
python scripts/import_af_backfill.py --dry-run

# ① 先拉赛程 + 裁判（同时建立球队 ID 映射，后续阶段依赖它）
python scripts/import_af_backfill.py --phase fixtures

# ② 球员档案（体重/国籍/身高/照片，按 ID 精确补）
python scripts/import_af_backfill.py --phase players

# ③ 主教练
python scripts/import_af_backfill.py --phase coaches

# ④ 伤停
python scripts/import_af_backfill.py --phase injuries

# ⑤ 阵容 / ⑥ 事件（每场 1 次，可分批；每天跑一次直到全部完成）
python scripts/import_af_backfill.py --phase lineups --limit 5000
python scripts/import_af_backfill.py --phase events  --limit 5000

# 或一条命令按顺序跑到配额用完
python scripts/import_af_backfill.py --phase all
```

**配额用完会自动停止并保存进度**，第二天运行同一条命令即从断点继续（进度文件 `data/af_backfill_progress.json`）。

## 三、请求预算（估算）

| 阶段 | 请求数 | 说明 |
|---|---|---|
| fixtures（赛程+裁判） | 50 | 10 赛事 × 5 赛季 |
| players（球员档案） | ~1,000 | 250 队 × 4 赛季（只跑有映射的队） |
| coaches（主教练） | ~250 | 每队 1 次 |
| injuries（伤停） | 50 | 按联赛+赛季 |
| lineups（阵容） | ~12,500 | 每场 1 次 |
| events（事件） | ~12,500 | 每场 1 次 |
| **合计** | **约 2.6 万** | Pro 档 7,500/天 → **约 4 天** |

## 四、落库位置

| 内容 | 表/字段 |
|---|---|
| 赛程+裁判+场地 | `af_fixtures`；同时回填 `matches.referee` / `matches.venue` / `matches.af_fixture_id` |
| 球队 ID 映射 | `af_team_map`（我们的 `team_id` ↔ API-Football 球队 id） |
| 球员档案 | `af_players`；同时补 `players.weight/nationality/height/photo_url/af_player_id` |
| 主教练 | `af_coaches` + `teams.manager` |
| 伤停 | `af_injuries` |
| 阵容 | `af_lineups` |
| 事件 | `af_events` |

## 五、免费替代源验证结果（已逐一实测，均不可行）

| 备选源 | 结果 | 说明 |
|---|---|---|
| FotMob 公开接口 | ❌ 404 / 需 token | 域名可达，但接口路径改版且需 `x-mas` 令牌 |
| Sofascore API | ❌ 403 | Cloudflare 拦截 |
| ESPN 公开接口 | ❌ 403 | 被拦截（含 `site.api.espn.com`） |
| FBref | ❌ 403 | Cloudflare 拦截 |
| Transfermarkt 直抓 | ❌ 405 | 反爬拦截 |
| StatsBomb open data | ⚠️ 覆盖极小 | 与我们赛季重叠仅 **127 场**（Bundesliga 2324 有 34 场、La Liga 2021 有 35 场、Ligue 1 26+32 场），而我们有 12,564 场 |
| Understat | ✅ 已用 | 仅 xG（已抓 9,049 场） |
| Kaggle / GitHub(镜像) / Reep | ✅ 已用 | 已全部榨取（TM 数据集、实体映射表） |

**结论**：要补「裁判 / 阵容 / 事件 / 球员体重 / 主教练 / 伤停」，**API-Football Pro（$19 一个月）是唯一现实路径**，且因其**不自动续费**，跑完即可停止。

## 六、注意事项

1. **不抓赔率**：本项目为纯预测系统，不使用任何博彩数据；只调用上述非赔率端点；
2. **限速**：客户端按 `AF_MIN_INTERVAL` 自动限速，并持久化每日配额计数（`data/af_quota.json`）；
3. **缓存**：所有原始响应缓存在 `data/external/af_cache/`，重复请求零消耗；如需强制刷新可删除对应文件；
4. **可停机**：一个月到期后自动回到免费档，数据已落库，不影响系统运行。
