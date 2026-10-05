/**
 * 用户端仪表盘结构 —— 数值来自 src/data/football.ts（足球数据分析与 AI 预测系统真实数据）
 */
import { homeKpis, leagues, topScorers, upcoming } from './football'

export interface StatPillData {
  label: string
  value: number
  suffix: string
  variant: 'dark' | 'yellow' | 'light'
  decimals?: number
}

export interface BigStatData {
  icon: 'members' | 'openings' | 'launches'
  value: number
  label: string
  decimals?: number
}

export interface ActivityBar {
  day: string
  hours: number
  label?: string
  active?: boolean
}

export interface PendingAction {
  id: string
  icon: 'sync' | 'live' | 'api' | 'retrain' | 'odds'
  done: boolean
}

export interface CalendarEvent {
  id: string
  startDay: number
  span: number
  startHour: number
  theme: 'dark' | 'light'
  avatars: number[]
}

export const greeting = { prefix: 'Welcome to ', name: 'FootballAI' }

export const navItems = ['Overview', 'Leagues', 'Teams', 'Players', 'Predict', 'Agent', 'Live', 'Reports']

export const statPills: StatPillData[] = [
  { label: 'Matches', value: homeKpis.matches, suffix: '', variant: 'dark' },
  { label: 'Players', value: homeKpis.players, suffix: '', variant: 'yellow' },
]

export const sprintCycle = { label: 'Accuracy', value: homeKpis.accuracy }

export const returnStat: StatPillData = { label: 'Models', value: homeKpis.modelsOnline, suffix: '', variant: 'light' }

export const bigStats: BigStatData[] = [
  { icon: 'members', value: homeKpis.teams, label: 'Teams' },
  { icon: 'openings', value: homeKpis.eventsWan, label: 'Events', decimals: 1 },
  { icon: 'launches', value: 27, label: 'Tables' },
]

/** 射手榜 Top 7（真实数据） */
export const activity = {
  total: topScorers[0].goals,
  bars: topScorers.map((p, i) => ({
    day: p.en.slice(0, 4),
    hours: p.goals,
    label: p.name,
    active: i === 0,
  })) as ActivityBar[],
}

export const accuracyRing = {
  value: homeKpis.accuracy,
}

/** 焦点战预测：曼城 vs 阿森纳 */
const focus = upcoming[0]
export const focusMatch = {
  home: focus.home,
  away: focus.away,
  score: focus.score,
  conf: focus.conf,
  segments: [
    { label: 'home', percent: focus.prob[0], theme: 'yellow' as const },
    { label: 'draw', percent: focus.prob[1], theme: 'dark' as const },
    { label: 'away', percent: focus.prob[2], theme: 'gray' as const },
  ],
}

export const pendingMeta = { title: 'Update Log', total: 8 }

export const pendingActions: PendingAction[] = [
  { id: 'sync', icon: 'sync', done: true },
  { id: 'live', icon: 'live', done: true },
  { id: 'api', icon: 'api', done: false },
  { id: 'retrain', icon: 'retrain', done: true },
  { id: 'odds', icon: 'odds', done: false },
]

export const calendar = {
  days: [
    { d: 'Fri', n: 13 },
    { d: 'Sat', n: 14 },
    { d: 'Sun', n: 15 },
    { d: 'Mon', n: 16 },
    { d: 'Tue', n: 17 },
    { d: 'Wed', n: 18 },
  ],
  hours: [20, 21, 22, 23],
  events: [
    { id: 'city', startDay: 1, span: 2, startHour: 20, theme: 'dark', avatars: [32, 47, 5] },
    { id: 'derby', startDay: 2, span: 2, startHour: 21, theme: 'light', avatars: [12, 68] },
  ] as CalendarEvent[],
}

export const profile = {
  name: '曼城 2-1 阿森纳',
  rate: 'FT',
  photo: '/images/stadium.jpg',
}

/** 联赛列表（真实数据） */
export const sideMenu = leagues.map((l, i) => ({
  id: l.id,
  meta: `${l.country} · ${l.teams} 队`,
  open: i === 0,
  device: i === 0 ? { name: '曼城', edition: 'Elo 1905 · 榜首' } : undefined,
}))
