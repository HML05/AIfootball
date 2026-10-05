/**
 * 足球数据分析与 AI 预测系统 —— 真实项目数据
 * 提取自 indexFT.html（LEAGUES / TEAMS / STANDINGS / PLAYERS / UPCOMING / MATCH / MODULES / TABLES / MODELS / UPDATE_LOG / 入库趋势 / 数据分布 / 进球时段）
 */

/* ---- 联赛 ---- */
export const leagues = [
  { id: 'premier-league', name: '英超', en: 'Premier League', country: '英格兰', teams: 10 },
  { id: 'la-liga', name: '西甲', en: 'LaLiga', country: '西班牙', teams: 8 },
  { id: 'bundesliga', name: '德甲', en: 'Bundesliga', country: '德国', teams: 7 },
  { id: 'serie-a', name: '意甲', en: 'Serie A', country: '意大利', teams: 8 },
  { id: 'ligue-1', name: '法甲', en: 'Ligue 1', country: '法国', teams: 6 },
]

/* ---- 球队（Elo 降序） ---- */
export const teams = [
  { id: 'real-madrid', name: '皇家马德里', short: 'RMA', elo: 1910, color: '#febe10', form: ['W', 'W', 'W', 'W', 'D'] },
  { id: 'man-city', name: '曼城', short: 'MCI', elo: 1905, color: '#6cabdd', form: ['W', 'W', 'D', 'W', 'W'] },
  { id: 'bayern', name: '拜仁慕尼黑', short: 'FCB', elo: 1895, color: '#dc052d', form: ['W', 'W', 'W', 'D', 'W'] },
  { id: 'barcelona', name: '巴塞罗那', short: 'BAR', elo: 1890, color: '#a50044', form: ['W', 'W', 'D', 'W', 'W'] },
  { id: 'psg', name: '巴黎圣日耳曼', short: 'PSG', elo: 1880, color: '#004170', form: ['W', 'W', 'W', 'W', 'L'] },
  { id: 'arsenal', name: '阿森纳', short: 'ARS', elo: 1878, color: '#ef0107', form: ['W', 'D', 'W', 'W', 'L'] },
  { id: 'liverpool', name: '利物浦', short: 'LIV', elo: 1867, color: '#c8102e', form: ['W', 'W', 'L', 'W', 'D'] },
  { id: 'atletico', name: '马德里竞技', short: 'ATM', elo: 1845, color: '#cb3524', form: ['W', 'D', 'W', 'W', 'W'] },
  { id: 'inter', name: '国际米兰', short: 'INT', elo: 1840, color: '#0068a8', form: ['W', 'W', 'D', 'W', 'W'] },
  { id: 'leverkusen', name: '勒沃库森', short: 'B04', elo: 1830, color: '#e32221', form: ['W', 'D', 'W', 'W', 'L'] },
  { id: 'napoli', name: '那不勒斯', short: 'NAP', elo: 1820, color: '#12a0d7', form: ['W', 'W', 'W', 'L', 'D'] },
  { id: 'atalanta', name: '亚特兰大', short: 'ATA', elo: 1815, color: '#1e71b8', form: ['W', 'D', 'W', 'W', 'L'] },
]

/* ---- 焦点赛事预测 ---- */
export const upcoming = [
  { league: '英超', home: '曼城', away: '阿森纳', date: '2026-03-14', time: '20:00', prob: [46, 27, 27], score: '2-1', conf: 0.71, model: '集成模型 v4' },
  { league: '英超', home: '利物浦', away: '切尔西', date: '2026-03-14', time: '22:30', prob: [52, 26, 22], score: '2-0', conf: 0.68, model: '集成模型 v4' },
  { league: '西甲', home: '皇家马德里', away: '巴塞罗那', date: '2026-03-15', time: '23:00', prob: [40, 28, 32], score: '2-2', conf: 0.58, model: '集成模型 v4' },
  { league: '意甲', home: '国际米兰', away: '那不勒斯', date: '2026-03-15', time: '21:45', prob: [48, 30, 22], score: '1-0', conf: 0.66, model: '集成模型 v4' },
  { league: '德甲', home: '拜仁慕尼黑', away: '勒沃库森', date: '2026-03-15', time: '22:30', prob: [44, 26, 30], score: '2-1', conf: 0.62, model: '集成模型 v4' },
  { league: '法甲', home: '巴黎圣日耳曼', away: '马赛', date: '2026-03-16', time: '03:00', prob: [61, 22, 17], score: '3-1', conf: 0.74, model: '集成模型 v4' },
]

/* ---- 首页 KPI ---- */
export const homeKpis = {
  matches: 12840,
  players: 5200,
  teams: 220,
  eventsWan: 96.4,
  accuracy: 55.1,
  modelsOnline: 4,
}

/* ---- 系统同步日志 ---- */
export const updateLog = [
  { id: 'sync', ts: '2026-03-09 06:12', level: 'ok', title: '赛程同步完成', desc: '英超 / 西甲 / 意甲 第 28 轮，共 480 场赛程与结果写入' },
  { id: 'live', ts: '2026-03-08 23:40', level: 'ok', title: '实时比分入库', desc: '接收 32 场比赛事件，合并 214 条进/失球与换人事件' },
  { id: 'api', ts: '2026-03-08 18:05', level: 'warn', title: '外部 API 限流', desc: 'football-data 接口触发 429，已退避重试并补齐缺失数据' },
  { id: 'retrain', ts: '2026-03-08 06:12', level: 'ok', title: '模型重训练', desc: '集成模型 v4 完成样本外评估，准确率 55.1%（+0.6pp）' },
  { id: 'odds', ts: '2026-03-07 06:12', level: 'ok', title: '赔率数据同步', desc: '写入 12 家博彩公司盘口，共 960 条记录' },
]

/* ---- 管理后台：数据模块 ---- */
export const modules = [
  { id: 'matches', name: '比赛', value: 12840, unit: '场', delta: '+5.8%' },
  { id: 'players', name: '球员', value: 5200, unit: '名', delta: '+3.4%' },
  { id: 'events', name: '比赛事件', value: 96.4, unit: '万条', delta: '+7.2%', decimals: 1 },
  { id: 'predictions', name: '预测样本', value: 1280, unit: '条', delta: '+12.5%' },
]

/* ---- 入库趋势（近 12 周 · 万条） ---- */
export const ingestTrend = [38, 41, 45, 44, 52, 49, 58, 61, 57, 68, 74, 82]

/* ---- 数据分布（按记录类型） ---- */
export const dataDistribution = [
  { key: 'events', count: 964000 },
  { key: 'passes', count: 620000 },
  { key: 'playerStats', count: 145600 },
  { key: 'others', count: 210400 },
]

/* ---- 数据库表（按行数 Top 8） ---- */
export const dbTables = [
  { name: 'passes', rows: 9820000 },
  { name: 'match_events', rows: 964000 },
  { name: 'shots', rows: 238000 },
  { name: 'audit_log', rows: 52400 },
  { name: 'elo_ratings', rows: 26400 },
  { name: 'transfers', rows: 18400 },
  { name: 'favorites', rows: 18800 },
  { name: 'player_stats', rows: 145600 },
]

/* ---- 数据管道（漏斗） ---- */
export const pipeline = [
  { key: 'passes', value: 9820000 },
  { key: 'events', value: 964000 },
  { key: 'shots', value: 238000 },
  { key: 'predictions', value: 1280 },
]

/* ---- 进球时段分布 ---- */
export const goalBands = [
  { band: "0-15'", count: 42 },
  { band: "16-30'", count: 55 },
  { band: "31-45'", count: 61 },
  { band: "46-60'", count: 58 },
  { band: "61-75'", count: 66 },
  { band: "76-90'", count: 79 },
]

/* ---- 预测模型注册表 ---- */
export const models = [
  { id: 'ensemble', name: '集成模型 v4', algo: 'Stacking (GBDT + NN + LR)', acc: 55.1, logloss: 0.974, brier: 0.188, status: 'production', trained: '2026-02-28' },
  { id: 'gbdt', name: '梯度提升 GBDT', algo: 'XGBoost', acc: 54.6, logloss: 0.982, brier: 0.191, status: 'challenger', trained: '2026-02-27' },
  { id: 'nn', name: '神经网络 NN', algo: 'MLP 3×256', acc: 53.8, logloss: 0.990, brier: 0.196, status: 'challenger', trained: '2026-02-26' },
  { id: 'lr', name: '逻辑回归 LR', algo: 'Multinomial Logistic', acc: 52.1, logloss: 1.010, brier: 0.203, status: 'baseline', trained: '2026-02-20' },
]

/* ---- 射手榜 Top 7 ---- */
export const topScorers = [
  { name: '哈里·凯恩', en: 'Kane', team: 'bayern', goals: 28 },
  { name: '基利安·姆巴佩', en: 'Mbappé', team: 'real-madrid', goals: 26 },
  { name: '埃尔林·哈兰德', en: 'Haaland', team: 'man-city', goals: 24 },
  { name: '劳塔罗·马丁内斯', en: 'Lautaro', team: 'inter', goals: 22 },
  { name: '罗伯特·莱万', en: 'Lewa', team: 'barcelona', goals: 21 },
  { name: '穆罕默德·萨拉赫', en: 'Salah', team: 'liverpool', goals: 20 },
  { name: '奥斯曼·登贝莱', en: 'Dembélé', team: 'psg', goals: 19 },
]

/* ---- 系统状态检查 ---- */
export const systemChecks = [
  { name: '数据源连接', status: 'ok', note: '3/3 在线' },
  { name: '数据库连接池', status: 'ok', note: '12 / 20 使用中' },
  { name: '外部 API 配额', status: 'warn', note: '剩余 38%' },
  { name: '模型服务', status: 'ok', note: 'v4 · 延迟 42ms' },
  { name: '定时同步任务', status: 'ok', note: '下次 06:00' },
  { name: '磁盘占用', status: 'ok', note: '128 GB / 512 GB' },
]
