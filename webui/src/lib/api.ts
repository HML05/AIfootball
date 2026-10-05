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
import { authHeader, clearAuth, UNAUTHORIZED_EVENT } from './auth'

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

export function qs(params: Record<string, string | number | undefined | null>): string {
  const sp = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v !== undefined && v !== null && v !== '') sp.set(k, String(v))
  }
  const s = sp.toString()
  return s ? `?${s}` : ''
}

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
