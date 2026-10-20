/**
 * 真实数据 API 客户端 —— 对接 FastAPI（src/api/ui.py，挂载在 /api/ui）
 *
 * 开发时后端跑在 http://127.0.0.1:8000；生产（打包进 FastAPI 静态目录）时同源。
 * 可用 VITE_API_BASE 覆盖，例如 VITE_API_BASE=/api/ui
 *
 * 登录：/api/ui/* 需要 Authorization: Bearer <token>（见 lib/auth.ts）。
 * 401 时清掉本地登录态并广播 UNAUTHORIZED_EVENT，由路由守卫跳回 /login。
 */
import { API_BASE, SERVER_ROOT, AUTH_BASE } from './base'
import { authHeader, clearAuth, getToken, UNAUTHORIZED_EVENT } from './auth'

export { API_BASE, SERVER_ROOT, AUTH_BASE }

/* ---------------- 通用 ---------------- */

export interface Paged<T> {
  items: T[]
  total: number
  page: number
  size: number
  pages: number
}

export class ApiError extends Error {
  status: number

  constructor(status: number, message: string) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

export async function getJSON<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    signal,
    headers: { Accept: 'application/json', ...authHeader() },
  })
  if (res.status === 401) {
    clearAuth()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(401, '登录已过期，请重新登录')
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} · ${path}`)
  return (await res.json()) as T
}

/**
 * POST JSON —— 与 getJSON 同款行为：带 Bearer、401 清登录态并广播、错误抛 ApiError。
 * /api/ui/ask 是 POST，getJSON 只支持 GET，故单独实现。
 */
export async function postJSON<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: 'POST',
    signal,
    headers: { Accept: 'application/json', 'Content-Type': 'application/json', ...authHeader() },
    body: JSON.stringify(body),
  })
  if (res.status === 401) {
    clearAuth()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(401, '登录已过期，请重新登录')
  }
  if (!res.ok) throw new ApiError(res.status, `${res.status} ${res.statusText} · ${path}`)
  return (await res.json()) as T
}

export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

/* ---------------- 视觉（YOLOv8 视频分析，挂在 /api/vision） ---------------- */

/** 视觉接口前缀：不在 /api/ui 下面，所以单独一个 base */
export const VISION_BASE: string = `${SERVER_ROOT}/api/vision`

/**
 * 视觉接口统一走这里：GET / POST(JSON) / POST(FormData) / DELETE 都能用。
 * 与 getJSON 的差别只有 base，401 的处理完全一致（清登录态 + 广播跳回登录页）。
 */
async function visionJSON<T>(path: string, init: RequestInit = {}): Promise<T> {
  const isForm = typeof FormData !== 'undefined' && init.body instanceof FormData
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(init.body && !isForm ? { 'Content-Type': 'application/json' } : {}),
    ...authHeader(),
  }
  const res = await fetch(`${VISION_BASE}${path}`, { ...init, headers })
  if (res.status === 401) {
    clearAuth()
    window.dispatchEvent(new Event(UNAUTHORIZED_EVENT))
    throw new ApiError(401, '登录已过期，请重新登录')
  }
  if (!res.ok) {
    // 后端把「格式不对 / 超上限 / 已有任务」写在 detail 里，直接透给用户看
    let detail = ''
    try {
      const b = (await res.json()) as { detail?: unknown }
      detail = typeof b?.detail === 'string' ? b.detail : ''
    } catch {
      /* 响应不是 JSON 就用状态码文案 */
    }
    throw new ApiError(res.status, detail || `${res.status} ${res.statusText} · ${path}`)
  }
  if (res.status === 204) return undefined as T
  return (await res.json()) as T
}

/** <video src> 带不了 Authorization 头，所以流地址把 token 放查询串（与头像同样的取舍） */
export const visionStreamUrl = (videoId: number): string =>
  `${VISION_BASE}/videos/${videoId}/stream?token=${encodeURIComponent(getToken() ?? '')}`

export const visionOverlayUrl = (videoId: number): string =>
  `${VISION_BASE}/videos/${videoId}/overlay?token=${encodeURIComponent(getToken() ?? '')}`

export const logoUrl = (teamId?: number | null): string | undefined =>
  teamId === undefined || teamId === null ? undefined : `${API_BASE}/logo/${teamId}`

/* ---------------- 类型 ---------------- */

export interface StatBlock {
  label: string
  labelEn: string
  value: number
  decimals?: number
  suffix?: string
  delta?: number
  sub?: string
  subEn?: string
}

export interface TeamRef {
  name: string
  nameEn: string
  logo: string | null
  id: number
}

export interface FocusMatch {
  matchId: number
  date: string
  status: string
  league: string
  leagueEn: string
  season: string
  home: TeamRef
  away: TeamRef
  segments: { key: 'home' | 'draw' | 'away'; label: string; labelEn: string; pct: number }[]
  pick: string
  pickEn: string
  conf: number
  model: string
}

export interface ScorerRow {
  rank: number
  name: string
  team: string
  league: string
  goals: number
  assists: number
  apps: number
  minutes: number
  photo: string | null
  position: string
}

export interface Top3Row {
  rank: number
  team: string
  teamEn: string
  points: number
  played: number
  form: string
  logo: string | null
}

export interface LeagueCard {
  id: number
  name: string
  nameEn: string
  country?: string
  countryEn?: string
  season: string
  matches: number
  teams: number
  goalsPg: number | null
  xgPg: number | null
  homeWinPct: number | null
  drawPct: number | null
  awayWinPct: number | null
  top3: Top3Row[]
}

export interface LeagueTotals {
  leagues: number
  matches: number
  teams: number
  players: number
  goalsPg: number
}

export interface LeagueListPayload {
  items: LeagueCard[]
  totals?: LeagueTotals
}

export interface MatchRow {
  match_id: number
  date: string
  /** 赛季代码，如 '2627'（后端返回，用于查询/展示） */
  season?: string | null
  /** 轮次，未定轮次时为 0 */
  matchday?: number | null
  home_goals: number | null
  away_goals: number | null
  home_xg: number | null
  away_xg: number | null
  lg: string
  lg_en: string
  h: string
  h_en: string
  h_logo: string | null
  a: string
  a_en: string
  a_logo: string | null
  status?: string
  pred_home_win?: number | null
  pred_draw?: number | null
  pred_away_win?: number | null
  pred_result?: string | null
  /** 后端判定的命中：1 命中 / 0 未中 / null 未评估（以它为准，勿前端自算） */
  hit?: number | null
  model_version?: string | null
}

export interface UpcomingRow extends MatchRow {
  home_team_id: number
  away_team_id: number
}

export interface CalendarPayload {
  month: string
  baseDate: string
  days: { d: string; date: string; label: string; n: number }[]
  hours: number[]
  events: {
    id: string
    title: string
    subtitle: string
    startDay: number
    span: number
    startHour: number
    theme: 'dark' | 'light'
    logos: string[]
    time: string
    matchId: number
  }[]
}

export interface UpdateLogRow {
  id: string
  ts: string
  level: string
  title: string
  titleEn: string
  desc: string
  descEn: string
  done: boolean
}

export interface TrendPayload {
  labels: string[]
  values: number[]
  finished?: number[]
  caption?: string
  unit: string
  unitEn: string
}

export interface CoveragePayload {
  matches: number
  finished: number
  upcoming: number
  xofficial: number
  predictions: number
  rangeFrom: string
  rangeTo: string
}

export interface HomePayload {
  generatedAt: string
  dataNow: string
  brand: { name: string; sub: string; subEn: string }
  stats: Record<'matches' | 'players' | 'accuracy' | 'models' | 'teams' | 'leagues' | 'records' | 'ingest', StatBlock>
  hero: FocusMatch
  focusMatch: FocusMatch
  topScorers: { season: string; seasonCode: string; items: ScorerRow[] }
  leagueCards: LeagueCard[]
  recent: MatchRow[]
  upcoming: UpcomingRow[]
  calendar: CalendarPayload
  updateLog: UpdateLogRow[]
  trend: TrendPayload
  coverage: CoveragePayload
}

export interface AdminPayload {
  generatedAt: string
  dataNow: string
  modules: { id: 'matches' | 'players' | 'events' | 'predictions'; value: number; unit: string; unitEn: string; delta: string; sub: string; subEn: string }[]
  trend: TrendPayload
  distribution: { key: string; label: string; labelEn: string; count: number }[]
  pipeline: { key: string; label: string; labelEn: string; value: number }[]
  goalBands: { band: string; count: number }[]
  models: ModelRow[]
  tableGroups: { group: string; groupEn: string; name: string; rows: number }[]
  dbTables: { total: number; records: number; items: { name: string; rows: number; group: string; groupEn: string }[] }
  checks: { name: string; nameEn: string; status: string; note: string; noteEn: string }[]
  counts: Record<string, number>
  leagueStats: LeagueCard[]
}

export interface ModelRow {
  model: string
  acc: number
  f1_macro: number
  logloss: number
  draw_recall: number
  test_n: number
  status: 'production' | 'challenger' | 'baseline' | string
  /** 后端可选补充字段（/models 不返回） */
  name?: string
  nameEn?: string
  trainedAt?: string
}

/** 球队行（/teams、联赛页 teams）—— 字段为后端原始 snake_case */
export interface TeamRow {
  team_id: number
  team: string
  name_en: string | null
  league_id: number
  league_name: string
  league_name_en: string
  matches: number
  goals_pg: number
  conceded_pg: number
  shots_pg: number
  shot_diff_pg: number
  cards_pg: number
  xg_pg: number | null
  xga_pg: number | null
  ppg: number
  avg_age: number | null
  squad_value: number | null
  valueText: string | null
  elo_rating: number | null
  stadium: string | null
  manager: string | null
  logo_url: string | null
  s_attack: number
  s_defense: number
  s_dominance: number
  s_discipline: number
  s_value: number
  s_experience: number
  s_stability: number
  radar: Record<string, number>
}

export interface PlayerRow {
  player_id: number
  name: string
  name_en: string | null
  position: string | null
  nationality: string | null
  age: number | null
  height: number | null
  number: number | null
  market_value: number | null
  valueText?: string | null
  photo_url: string | null
  foot: string | null
  team: string | null
  team_en?: string | null
  team_logo: string | null
  team_id: number | null
  league: string | null
  league_en?: string | null
  group: string
}

export interface PredictionRow {
  pred_id: number
  match_id: number
  model_version: string
  pred_home_win: number
  pred_draw: number
  pred_away_win: number
  /** 'H' | 'D' | 'A' */
  pred_result: string | null
  actual_result: string | null
  hit: number | null
  is_backtest: number
  created_at: string
  date: string
  lg: string
  lg_en: string
  h: string
  h_logo: string | null
  a: string
  a_logo: string | null
  home_goals: number | null
  away_goals: number | null
  status: string
}

export interface TransferRow {
  player_id: string
  player_name: string
  season_name: string
  transfer_date: string | null
  from_team_name: string | null
  to_team_name: string | null
  transfer_type: string | null
  value_at_transfer: string | null
  transfer_fee: string | null
}

export interface TransferPayload extends Paged<TransferRow> {
  seasons: string[]
  top: {
    player_name: string
    from_team_name: string | null
    to_team_name: string | null
    transfer_fee: string | null
    season_name: string
    transfer_date: string | null
  }[]
}

export interface ReportPayload {
  generatedAt: string
  core: {
    matches: number
    finished: number
    upcoming: number
    first_date: string
    last_date: string
    now: string
    players: number
    teams: number
    leagues: number
    records: number
    tables: number
  }
  tables: { name: string; rows: number }[]
  months: { m: string; n: number; ft: number }[]
  leagues: LeagueCard[]
  sources: { name: string; nameEn: string; records: number; detail: string; detailEn: string }[]
  quality: {
    matchWithXg: number
    matchTotal: number
    playerWithValue: number
    playerTotal: number
    injuries: number
    marketValueRows: number
  }
}

export interface LivePayload {
  generatedAt: string
  source: string
  wsEndpoint: string
  recent: MatchRow[]
  upcoming: UpcomingRow[]
  lastDay: string
  lastDayCount: number
}

export interface MatchesPayload extends Paged<MatchRow> {
  stats: { ft: number; hw: number; dr: number; aw: number; goals_pg: number; n: number }
}

/** KPI 用的「筛选范围全量口径」——与分页无关 */
export interface TeamsPayload extends Paged<TeamRow> {
  aggregates: {
    scope: string
    n: number
    avgGoalsPg: number | null
    avgConcededPg: number | null
    maxElo: number | null
    maxEloTeam: string | null
    squadValue: number
    valueText: string
  }
  top5: (TeamRow & { valueText: string })[]
}

export interface PlayersPayload extends Paged<PlayerRow> {
  aggregates: {
    scope: string
    n: number
    withValue: number
    avgAge: number | null
    ageSampleDirty: number
    topValue: number | null
    topValueText: string
    topValueName: string | null
    topValueNameEn: string | null
  }
}

/* ---------------- 比赛详情 / 球队详情 ---------------- */

export interface StandingRow {
  rank: number
  played: number
  won: number
  draw: number
  lost: number
  goals_for: number
  goals_against: number
  goal_diff: number
  points: number
  form: string | null
}

/** 球队近期战绩行（带该队视角的 W/D/L） */
export interface FormRow {
  match_id: number
  date: string
  season: string
  home_goals: number | null
  away_goals: number | null
  home_xg: number | null
  away_xg: number | null
  home_team_id: number
  away_team_id: number
  lg: string
  lg_en: string
  h: string
  h_en: string
  h_logo: string | null
  a: string
  a_en: string
  a_logo: string | null
  isHome: boolean
  gf: number | null
  ga: number | null
  result: 'W' | 'D' | 'L'
}

export interface FixtureRow {
  match_id: number
  date: string
  status: string
  lg: string
  lg_en: string
  h: string
  h_en: string
  h_logo: string | null
  h_id: number
  a: string
  a_en: string
  a_logo: string | null
  a_id: number
  pred_home_win: number | null
  pred_draw: number | null
  pred_away_win: number | null
  pred_result: string | null
  model_version: string | null
}

export interface MatchDetailSide {
  id: number
  name: string
  nameEn: string | null
  logo: string | null
  stadium: string | null
  manager: string | null
  elo: number | null
  standing: StandingRow | null
  form: FormRow[]
}

export interface MatchDetailPayload {
  matchId: number
  date: string
  status: string
  season: string
  seasonCode: string
  matchday: number | null
  league: { id: number; name: string; nameEn: string; country: string; countryEn: string }
  home: MatchDetailSide
  away: MatchDetailSide
  score: { home: number | null; away: number | null; htHome: number | null; htAway: number | null }
  xg: { home: number | null; away: number | null; proxyHome: number | null; proxyAway: number | null }
  stats: { label: string; labelEn: string; home: number | null; away: number | null }[]
  prediction: {
    predId: number
    model: string
    segments: { key: string; label: string; labelEn: string; pct: number }[]
    pick: string | null
    pickLabel: string
    pickLabelEn: string
    conf: number
    actual: string | null
    hit: number | null
    isBacktest: number | null
    createdAt: string | null
  } | null
  h2h: {
    items: {
      match_id: number
      date: string
      home_goals: number | null
      away_goals: number | null
      home_team_id: number
      away_team_id: number
      lg: string
      lg_en: string
      h: string
      a: string
      resultForHome: 'W' | 'D' | 'L'
    }[]
    meetings: number
    homeWins: number
    draws: number
    awayWins: number
  }
}

export interface TeamSeasonRow {
  season: string
  seasonCode: string
  played: number
  ft: number
  won: number
  drawn: number
  lost: number
  goalsFor: number | null
  goalsAgainst: number | null
  xgPg: number | null
}

export interface SquadRow {
  player_id: number
  name: string
  name_en: string | null
  position: string | null
  age: number | null
  number: number | null
  market_value: number | null
  photo_url: string | null
  foot: string | null
  group: string
  valueText: string
}

export interface TeamDetailPayload {
  team: {
    id: number
    name: string
    nameEn: string | null
    shortName: string | null
    logo: string | null
    elo: number | null
    stadium: string | null
    capacity: number | null
    manager: string | null
    founded: number | null
    league: { id: number | null; name: string | null; nameEn: string | null }
  }
  radar: {
    attack: number | null
    defense: number | null
    dominance: number | null
    discipline: number | null
    value: number | null
    experience: number | null
    stability: number | null
  } | null
  metrics: {
    matches: number | null
    goalsPg: number | null
    concededPg: number | null
    shotsPg: number | null
    shotDiffPg: number | null
    cardsPg: number | null
    xgPg: number | null
    xgaPg: number | null
    ppg: number | null
    avgAge: number | null
    squadValue: number | null
    valueText: string
  } | null
  standing: (StandingRow & { id: number; league_id: number; season: string; team_id: number }) | null
  seasons: TeamSeasonRow[]
  recent: FormRow[]
  upcoming: FixtureRow[]
  squad: SquadRow[]
  squadGroups: { GK: number; DF: number; MF: number; FW: number; total: number }
}

/* ---------------- 检索 / 问答 ---------------- */

/** 全文检索单条命中（snippet 已由后端用【】标出命中词） */
export interface SearchHit {
  id: number
  kind: string
  kind_label: string
  ref: string
  title: string
  snippet: string
  score: number
  source: { table: string; id: string | number; ref: string; url: string | null }
  extra: Record<string, unknown>
}

export interface SearchPayload {
  query: string
  tokens: string[]
  operator: string | null
  mode: string
  mode_desc?: string
  kind: string | null
  count: number
  returned: number
  kinds: string[]
  hits: SearchHit[]
}

/** 检索索引状态（/api/ui/search/stats）—— by_kind 为各类型条数 */
export interface SearchStats {
  ready: boolean
  total: number
  mode: string
  mode_desc: string
  by_kind: Record<string, number>
  by_kind_label: Record<string, string>
  main_db: string
  path: string
  size_bytes: number
  built_at: string
}

export interface AskStatus {
  llm_ready: boolean
  llm_model: string
  llm_endpoint: string
  mode: string
  mode_desc: string
  intents: string[]
  tools: { name: string; desc: string }[]
  alias_teams: number
  players_indexed: number
  leagues_indexed: number
}

export interface AskFact {
  tool: string
  ok: boolean
  summary: string
  data: Record<string, unknown>
}

export interface AskSource {
  n: number
  table: string
  id: string | number
  label: string
  url: string | null
  ref: string | null
  via: string
}

export interface AskStep {
  tool: string
  args: unknown[]
  reason: string
}

export interface AskPayload {
  question: string
  mode: 'llm' | 'retrieval' | 'empty'
  answer: string
  intent: string | null
  plan: {
    intent: string | null
    keywords: string[]
    steps: AskStep[]
    entities: { teams: (string | null)[]; player: string | null; league: string | null }
  }
  facts: AskFact[]
  sources: AskSource[]
  /** 实测：/ask 返回的 search 对象没有 query 字段（只有 /search 有），故为可选 */
  search: {
    query?: string
    count: number
    tokens: string[]
    mode: string
    operator: string | null
    hits: SearchHit[]
  }
  missing: string[]
  timing: { tools_ms: number; search_ms: number; llm_ms: number; total_ms: number }
  llm: { ok: boolean; model: string | null; error: string | null; elapsed_ms: number }
  elapsed_ms: number
  generatedAt: string
}

/* ---------------- 端点 ---------------- */

/** 登录页公开信息（/api/ui/public/summary，无需 token） */
export interface PublicSummary {
  brand: { name: string; sub: string; subEn: string }
  dataNow: string
  generatedAt: string
  matches: number
  finished: number
  upcoming: number
  players: number
  teams: number
  leagues: number
  accuracy: number
  model: string
  accuracySamples: number
}

export const api = {
  base: API_BASE,
  logoUrl,
  /** 登录页公开信息（无需 token） */
  publicSummary: (signal?: AbortSignal) => getJSON<PublicSummary>('/public/summary', signal),
  home: (signal?: AbortSignal) => getJSON<HomePayload>('/home', signal),
  admin: (signal?: AbortSignal) => getJSON<AdminPayload>('/admin', signal),
  leagues: (signal?: AbortSignal) => getJSON<LeagueListPayload>('/leagues', signal),
  league: (id: number, season?: string, signal?: AbortSignal) =>
    getJSON<LeagueDetail>(`/leagues/${id}${qs({ season })}`, signal),
  teams: (p: Record<string, string | number | undefined | null> = {}, signal?: AbortSignal) =>
    getJSON<TeamsPayload>(`/teams${qs(p)}`, signal),
  players: (p: Record<string, string | number | undefined | null> = {}, signal?: AbortSignal) =>
    getJSON<PlayersPayload>(`/players${qs(p)}`, signal),
  player: (id: number, signal?: AbortSignal) => getJSON<PlayerDetail>(`/players/${id}`, signal),
  matches: (p: Record<string, string | number | undefined | null> = {}, signal?: AbortSignal) =>
    getJSON<MatchesPayload>(`/matches${qs(p)}`, signal),
  matchDetail: (id: number, signal?: AbortSignal) =>
    getJSON<MatchDetailPayload>(`/matches/${id}`, signal),
  teamDetail: (id: number, signal?: AbortSignal) =>
    getJSON<TeamDetailPayload>(`/teams/${id}`, signal),
  predictions: (p: Record<string, string | number | undefined | null> = {}, signal?: AbortSignal) =>
    getJSON<PredictionPayload>(`/predictions${qs(p)}`, signal),
  models: (signal?: AbortSignal) => getJSON<ModelsPayload>('/models', signal),
  transfers: (p: Record<string, string | number | undefined | null> = {}, signal?: AbortSignal) =>
    getJSON<TransferPayload>(`/transfers${qs(p)}`, signal),
  reports: (signal?: AbortSignal) => getJSON<ReportPayload>('/reports', signal),
  live: (signal?: AbortSignal) => getJSON<LivePayload>('/live', signal),
  /** 全文检索（kind 为空时不带该参数） */
  search: (q: string, opts: { kind?: string; limit?: number; offset?: number } = {}, signal?: AbortSignal) =>
    getJSON<SearchPayload>(`/search${qs({ q, kind: opts.kind, limit: opts.limit ?? 20, offset: opts.offset ?? 0 })}`, signal),
  searchStats: (signal?: AbortSignal) => getJSON<SearchStats>('/search/stats', signal),
  askStatus: (signal?: AbortSignal) => getJSON<AskStatus>('/ask/status', signal),
  /** 智能问答（POST，非 GET） */
  ask: (question: string, opts: { topK?: number; useLlm?: boolean; kind?: string } = {}) =>
    postJSON<AskPayload>('/ask', {
      question,
      top_k: opts.topK ?? 5,
      use_llm: opts.useLlm ?? true,
      kind: opts.kind || null,
    }),
  /* ---- 视觉（YOLOv8 检测跟踪；处理在本地 .venv-vision 里跑，网页只排队与展示） ---- */
  visionOverview: (signal?: AbortSignal) => visionJSON<VisionOverview>('/overview', { signal }),
  visionVideos: (signal?: AbortSignal) => visionJSON<{ items: VisionVideo[]; total: number }>('/videos', { signal }),
  visionUpload: (file: File) => {
    const fd = new FormData()
    fd.append('file', file)
    return visionJSON<VisionVideo>('/videos', { method: 'POST', body: fd })
  },
  visionDelete: (videoId: number) =>
    visionJSON<{ ok: boolean }>(`/videos/${videoId}`, { method: 'DELETE' }),
  visionProcess: (
    videoId: number,
    opts: { step?: number; conf?: number; imgsz?: number; model?: string; maxFrames?: number } = {},
  ) =>
    visionJSON<VisionJob>(`/videos/${videoId}/process`, {
      method: 'POST',
      body: JSON.stringify({
        step: opts.step,
        conf: opts.conf,
        imgsz: opts.imgsz,
        model: opts.model,
        max_frames: opts.maxFrames,
      }),
    }),
  visionJob: (jobId: number, signal?: AbortSignal) => visionJSON<VisionJob>(`/jobs/${jobId}`, { signal }),
  visionCancel: (jobId: number) => visionJSON<VisionJob>(`/jobs/${jobId}/cancel`, { method: 'POST' }),
  visionTracks: (videoId: number, jobId?: number, signal?: AbortSignal) =>
    visionJSON<VisionTracks>(`/videos/${videoId}/tracks${qs({ job_id: jobId })}`, { signal }),
  visionSummary: (videoId: number, jobId?: number, signal?: AbortSignal) =>
    visionJSON<VisionSummaryPayload>(`/videos/${videoId}/summary${qs({ job_id: jobId })}`, { signal }),
  visionStreamUrl,
  visionOverlayUrl,
}

export interface LeagueDetail {
  league: {
    id: number
    name: string
    nameEn: string
    country: string
    countryEn?: string
    season: string
  }
  season: string
  seasons: string[]
  standings: {
    id?: number
    season?: string
    rank: number
    team_id: number
    name: string
    name_en: string
    logo_url: string | null
    played: number
    won: number
    draw: number
    lost: number
    goals_for: number
    goals_against: number
    goal_diff: number
    points: number
    form: string
    updated_at?: string
  }[]
  history: {
    season: string
    seasonLabel: string
    matches: number
    goals_pg: number
    xg_pg: number | null
    home_win_pct?: number | null
    draw_pct?: number | null
    away_win_pct?: number | null
  }[]
  scorers: {
    player_id: string
    player_name: string
    team_name: string | null
    competition_name?: string | null
    goals: number
    assists: number
    appearances: number
    minutes?: number | null
    image_url: string | null
  }[]
  teams: {
    team: string
    team_id: number
    matches?: number
    ppg: number
    xg_pg: number | null
    xga_pg: number | null
    goals_pg?: number | null
    conceded_pg?: number | null
    shots_pg?: number | null
    cards_pg?: number | null
    squad_value: number | null
    avg_age: number | null
    elo_rating?: number | null
    logo_url: string | null
  }[]
  summary: Record<string, number | string | null>
  /** 射手榜真实所属赛季（来自 Transfermarkt 赛季名，可能与积分榜赛季不同） */
  scorersSeason?: { code: string; label: string }
  /** teams 表的口径：team_radar 是全量预计算表，不随赛季过滤 */
  teamsScope?: string
  /** 所选赛季的 league_stats 行（场均进球/xG/胜平负占比） */
  seasonStats?: {
    season: string
    matches: number
    goals_pg: number | null
    xg_pg: number | null
    home_win_pct: number | null
    draw_pct: number | null
    away_win_pct: number | null
  } | null
  /** 全量（跨赛季）汇总，用于与赛季口径对照 */
  allTime?: Record<string, number | string | null>
}

/** 球员画像（player_radar 一行） */
export interface PlayerRadar {
  player_id: number
  team_id: number | null
  name: string
  name_en: string | null
  position: string | null
  pos_group: string
  age: number | null
  height: number | null
  nationality: string | null
  foot: string | null
  number: number | null
  photo_url: string | null
  market_value: number | null
  apps: number | null
  minutes: number | null
  goals: number | null
  assists: number | null
  cards: number | null
  goals_p90: number | null
  assists_p90: number | null
  involve_p90: number | null
  minutes_share: number | null
  cards_p90: number | null
  s_goals: number
  s_assists: number
  s_involve: number
  s_minutes: number
  s_discipline: number
  s_value: number
  s_experience: number
}

export interface PlayerDetail {
  player: PlayerRow
  radar: PlayerRadar | null
  seasons: {
    player_id: string
    season_name: string
    competition_name: string | null
    team_id: string | null
    team_name: string | null
    appearances: number
    goals: number
    assists: number
    yellow_cards: number
    red_cards: number
    minutes: number
    season_start: number | null
  }[]
}

export interface PredictionPayload extends Paged<PredictionRow> {
  models: ModelRow[]
  calibration: { outcome: string; predicted: number; actual: number; n: number }[]
  confusion: { actual: string; predicted: string; count: number }[]
  featureImportance: { feature: string; importance: number }[]
  versions: { model_version: string; n: number }[]
  hitRate: number
  evaluated: number
}

export interface ModelsPayload {
  items: ModelRow[]
  calibration: { outcome: string; predicted: number; actual: number; n: number }[]
  confusion: { actual: string; predicted: string; count: number }[]
  featureImportance: { feature: string; importance: number }[]
}

/* ---------------- 视觉（YOLOv8 检测跟踪）类型 ---------------- */

export interface VisionCaps {
  cv2: boolean
  ultralytics: boolean
  can_process: boolean
  note: string | null
}

export interface VisionJob {
  job_id: number
  video_id: number
  status: 'queued' | 'running' | 'done' | 'failed' | 'canceled' | string
  progress: number
  frames_done: number
  frames_total: number | null
  step: number
  model: string
  conf: number
  imgsz: number
  message: string | null
  error: string | null
  worker: string | null
  overlay: boolean
  started_at: string | null
  finished_at: string | null
  created_at: string | null
}

export interface VisionVideoBrief {
  persons_per_frame: number | null
  ball_pct: number | null
  fragmentation: number | null
}

export interface VisionVideo {
  video_id: number
  name: string
  status: string
  size_bytes: number
  duration: number | null
  fps: number | null
  width: number | null
  height: number | null
  frames: number | null
  message: string | null
  created_at: string | null
  job: VisionJob | null
  done_job_id: number | null
  brief: VisionVideoBrief | null
}

export interface VisionOverview {
  server: VisionCaps
  defaults: { step: number; model: string; max_bytes: number; exts: string[] }
  videos: { total: number; by_status: Record<string, number> }
  jobs: { total: number; done: number }
  worker: {
    online: boolean
    name: string | null
    job_id: number | null
    host: string | null
    pid: number | null
    gpu: string | null
    deps: string | null
    heartbeat_age: number | null
  }
  recent_jobs: VisionJob[]
}

/** 一个框 = [track_id, cls, conf, x1, y1, x2, y2]（像素坐标，原始分辨率） */
export type VisionBox = [number | null, number, number, number, number, number, number]

export interface VisionTracks {
  job_id: number
  step: number
  frames: { f: number; b: VisionBox[] }[]
  boxes: number
  note: string
}

export interface VisionMetrics {
  frames_processed: number
  video: Record<string, unknown>
  person: {
    frames_with_person: number
    frames_with_person_pct: number
    per_frame_mean: number | null
    per_frame_max: number
    per_frame_min: number | null
    boxes_total: number
    mean_conf: number | null
  }
  tracking: {
    unique_ids: number
    max_ids_in_one_frame: number
    fragmentation: number | null
    id_lifetime_median: number | null
    id_lifetime_mean: number | null
  }
  ball: {
    frames_with_ball: number
    frames_with_ball_pct: number
    boxes_total: number
    mean_conf: number | null
    longest_consecutive_run: number
  }
  box_height_px: {
    median: number | null
    buckets: { far: number; mid: number; near: number }
    buckets_pct: { far: number; mid: number; near: number }
    cutoffs_px: { far_below: number; mid_below: number }
  }
  speed?: { elapsed_sec: number; fps_processed: number | null }
  notes: string[]
}

export interface VisionSummaryPayload {
  video_id: number
  job_id: number
  summary: VisionMetrics
  verdict: { mark: string; text: string }[]
  elapsed: number | null
}
