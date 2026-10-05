/**
 * 真实数据接入层：把 /api/ui 的返回包装成带语言选择的 hook + 格式化工具。
 *
 * 组件里这样用：
 *   const { data, loading } = useHome()
 *   if (!data) return <CardSkeleton />
 *   data.stats.matches.value
 */
import { api } from '../lib/api'
import type { AdminPayload, HomePayload } from '../lib/api'
import { useApi } from '../lib/useApi'
import type { ApiState } from '../lib/useApi'
import type { Lang } from '../i18n'

export const useHome = (): ApiState<HomePayload> => useApi(api.home, 'home', 60_000)
export const useAdmin = (): ApiState<AdminPayload> => useApi(api.admin, 'admin', 60_000)

/** 中英双语取值 */
export const pick = (lang: Lang, zh?: string | null, en?: string | null): string =>
  lang === 'zh' ? (zh ?? en ?? '') : (en || zh || '')

/** 千分位；万级自动缩写（1,811,825 → 181.2 万） */
export function fmtNum(n: number | null | undefined, digits = 0): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  return n.toLocaleString('en-US', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

/** 大数中文习惯：>=10000 → x.x 万 */
export function fmtWan(n: number | null | undefined, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  if (Math.abs(n) >= 10_000) {
    const v = n / 10_000
    return `${v.toFixed(Math.abs(v) >= 100 ? 0 : digits)} 万`
  }
  return fmtNum(n)
}

/** 中文界面用「万」，英文界面用 k/M */
export function fmtCompact(lang: Lang, n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—'
  if (lang === 'zh') return fmtWan(n)
  if (Math.abs(n) >= 1_000_000) return `${(n / 1_000_000).toFixed(1)}M`
  if (Math.abs(n) >= 1_000) return `${(n / 1_000).toFixed(1)}k`
  return fmtNum(n)
}

/** 百分比 */
export const pct = (n: number | null | undefined, digits = 1): string =>
  n === null || n === undefined || Number.isNaN(n) ? '—' : `${n.toFixed(digits)}%`

/** '2026-09-13 04:00' → { date: '09-13', time: '04:00', weekday } */
export function splitDateTime(ts: string): { date: string; time: string; ymd: string } {
  const [d = '', t = ''] = (ts || '').split(' ')
  const [, m = '', day = ''] = d.split('-')
  return { date: m && day ? `${m}-${day}` : d, time: t.slice(0, 5), ymd: d }
}

export function weekdayShort(lang: Lang, ymd: string): string {
  if (!ymd) return ''
  const dt = new Date(`${ymd}T00:00:00`)
  if (Number.isNaN(dt.getTime())) return ''
  return lang === 'zh'
    ? ['周日', '周一', '周二', '周三', '周四', '周五', '周六'][dt.getDay()]
    : ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'][dt.getDay()]
}

/** 球队短名：优先 nameEn 的末词，中文取前 4 字 */
export function shortTeam(lang: Lang, zh: string, en?: string | null): string {
  if (lang === 'zh') return (zh || en || '').slice(0, 6)
  const s = en || zh || ''
  return s.length > 14 ? s.slice(0, 13) + '…' : s
}

/** 中文姓氏/英文姓氏缩写，用于无头像时的降级 */
export const initials = (name: string): string =>
  (name || '?')
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0]?.toUpperCase() ?? '')
    .join('')
