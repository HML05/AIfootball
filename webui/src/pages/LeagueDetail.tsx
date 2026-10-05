/**
 * 联赛详情 —— 真实数据来自 GET /api/ui/leagues/{id}?season=xxxx
 *
 * 结构：赛季切换（standings 里出现过的赛季）+ KPI（比赛/完赛/场均进球/场均 xG/时间跨度）
 * 左列：积分榜表 · 赛季趋势（recharts 双线） · 球队实力表
 * 右列：射手榜（dark） · 联赛概览
 *
 * 注意：接口里 summary / teams 是该联赛的**全量聚合**（跨赛季），
 *       赛季相关的数字（积分榜、趋势、概览的胜平负）以 standings / history 为准。
 */
import { useEffect, useMemo, useRef, useState } from 'react'
import { useParams } from 'react-router'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import {
  PageShell,
  SectionCard,
  Pill,
  Bar,
  Tabs,
  EmptyState,
  ErrorState,
  KpiStrip,
} from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api } from '../lib/api'
import type { LeagueDetail as LeagueDetailPayload } from '../lib/api'
import { useApi } from '../lib/useApi'
import { pick, fmtNum, fmtCompact, pct, initials } from '../data/live'
import { useLang } from '../i18n'

const AMBER = '#F6C945'
const BLUE = '#A8C5E2'
const MUTED = '#b3ad97'

/* ---------------- 小工具 ---------------- */

type StandRow = LeagueDetailPayload['standings'][number]
type TeamRow = LeagueDetailPayload['teams'][number]
type HistRow = LeagueDetailPayload['history'][number]
type ScorerRow = LeagueDetailPayload['scorers'][number]

const num = (v: unknown): number | null => (typeof v === 'number' && Number.isFinite(v) ? v : null)

/** '2026-09-12 09:08:46' → '2026-09-12' */
const day = (v: unknown): string => (typeof v === 'string' && v.length >= 10 ? v.slice(0, 10) : '—')

const dec = (v: number | null | undefined, digits = 2): string =>
  v === null || v === undefined || !Number.isFinite(v) ? '—' : v.toFixed(digits)

/** season code '2627' → '2026/27'；已是 '2026-27' 之类的可读格式则原样返回 */
const seasonLabel = (code: string): string => {
  if (!/^\d{4}$/.test(code)) return code
  const year = 2000 + Number(code.slice(0, 2))
  return `${year}/${String(year + 1).slice(2)}`
}

/** 相对最大值的条形（用于实力列的横向对比） */
function MiniBar({ value, max, tone = 'yellow' }: { value: number | null; max: number; tone?: 'yellow' | 'blue' }) {
  return <Bar value={value} max={max} tone={tone} height={5} className="max-w-[58px]" />
}

/** 近况 'WWWWW' → 小圆点（W 琥珀 / D 灰 / L 蓝灰） */
function FormDots({ form }: { form: string }) {
  const chars = (form || '').toUpperCase().replace(/[^WDL]/g, '').slice(0, 5)
  if (!chars.length) return <span className="t-3 text-[10px]">—</span>
  return (
    <span className="flex items-center gap-1">
      {chars.split('').map((c, i) => (
        <span
          key={i}
          title={c}
          className="flex h-[15px] w-[15px] items-center justify-center rounded-full text-[8.5px] font-bold"
          style={{
            backgroundColor: c === 'W' ? AMBER : c === 'D' ? MUTED : BLUE,
            color: '#26251F',
          }}
        >
          {c}
        </span>
      ))}
    </span>
  )
}

/* ---------------- 表头 / 单元格样式 ---------------- */

const TH = 'px-3 py-2 text-left text-[10px] font-semibold uppercase tracking-wide t-3 whitespace-nowrap'
const THR = 'px-3 py-2 text-right text-[10px] font-semibold uppercase tracking-wide t-3 whitespace-nowrap'
const TD = 'px-3 py-2.5 text-[12px] font-medium t-2 whitespace-nowrap'
const TDR = 'px-3 py-2.5 text-right text-[12px] font-medium t-2 tabular-nums whitespace-nowrap'

/* ---------------- 赛季趋势（recharts） ---------------- */

function SeasonTrend({ history }: { history: HistRow[] }) {
  const { lang } = useLang()
  const rows = useMemo(
    () =>
      [...history]
        .sort((a, b) => (a.season || '').localeCompare(b.season || ''))
        .map((h) => ({ label: h.seasonLabel || h.season, goals: num(h.goals_pg), xg: num(h.xg_pg) })),
    [history],
  )
  if (rows.length === 0) return <EmptyState text={pick(lang, '暂无赛季趋势数据', 'No seasonal trend data')} />
  const hasXg = rows.some((r) => r.xg !== null)
  return (
    <div className="h-[240px] w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={rows} margin={{ top: 6, right: 8, bottom: 0, left: -18 }}>
          <defs>
            <linearGradient id="ld-goals" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={AMBER} stopOpacity={0.45} />
              <stop offset="100%" stopColor={AMBER} stopOpacity={0.02} />
            </linearGradient>
            <linearGradient id="ld-xg" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={BLUE} stopOpacity={0.35} />
              <stop offset="100%" stopColor={BLUE} stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid stroke="var(--c-line)" vertical={false} />
          <XAxis dataKey="label" tick={{ fontSize: 10, fill: 'var(--c-faint)' }} tickLine={false} axisLine={false} />
          <YAxis
            domain={['dataMin - 0.4', 'dataMax + 0.3']}
            tick={{ fontSize: 10, fill: 'var(--c-faint)' }}
            tickLine={false}
            axisLine={false}
            width={42}
            tickFormatter={(v: number) => v.toFixed(1)}
          />
          <Tooltip
            cursor={{ stroke: 'var(--c-muted)', strokeDasharray: '3 3' }}
            contentStyle={{
              background: 'rgba(43,43,39,0.94)',
              border: '1px solid rgba(255,255,255,0.12)',
              borderRadius: 14,
              fontSize: 12,
              padding: '8px 12px',
            }}
            labelStyle={{ color: '#fbf6e9', fontWeight: 600, marginBottom: 4 }}
            itemStyle={{ color: '#fbf6e9' }}
            formatter={(value: number, name: string) => [
              Number(value).toFixed(2),
              name === 'goals' ? pick(lang, '场均进球', 'Goals / match') : pick(lang, '场均 xG', 'xG / match'),
            ]}
          />
          <Area
            type="monotone"
            dataKey="goals"
            stroke={AMBER}
            strokeWidth={2.5}
            fill="url(#ld-goals)"
            connectNulls={false}
            dot={{ r: 3, fill: AMBER, strokeWidth: 0 }}
            activeDot={{ r: 5, stroke: '#fff', strokeWidth: 2 }}
          />
          {hasXg && (
            <Area
              type="monotone"
              dataKey="xg"
              stroke={BLUE}
              strokeWidth={2}
              fill="url(#ld-xg)"
              connectNulls={false}
              dot={{ r: 3, fill: BLUE, strokeWidth: 0 }}
              activeDot={{ r: 5, stroke: '#fff', strokeWidth: 2 }}
            />
          )}
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------------- 页面 ---------------- */

export default function LeagueDetail() {
  const { lang } = useLang()
  const { id } = useParams()
  const lid = Number(id)
  const [season, setSeason] = useState('')

  // 赛季 code 从详情接口的 seasons 里取（详情响应的 season 字段即"当前赛季"）。
  // 不要用 /leagues 列表里的 season：那里是展示用的 '2026/27'，而 season 参数要的是 code '2627'。
  // 首发不带 season → 后端按默认赛季返回 seasons + 默认 season code，随后自动定位到该 code。
  const { data, loading, error } = useApi<LeagueDetailPayload>(
    () => api.league(lid, season || undefined),
    `league:${lid}:${season}`,
  )

  // 把响应的默认赛季同步到本地 state。
  // 关键：key 变化后 useApi 会先保留**上一次**的数据对象，此时 data.season 仍是旧赛季，
  // 若直接同步会把用户刚选的新赛季覆盖回去（表现为点赛季页签没反应）→ 用 ref 记录已同步过的
  // 赛季，只对"没见过"的赛季做一次同步。
  const syncedSeason = useRef('')
  useEffect(() => {
    if (data?.season && data.season !== syncedSeason.current) {
      syncedSeason.current = data.season
      setSeason(data.season)
    }
  }, [data?.season])

  const seasons = data?.seasons ?? []
  const standings = data?.standings ?? []
  const history = data?.history ?? []
  const teamsList = data?.teams ?? []
  const scorers = data?.scorers ?? []
  const league = data?.league

  const latest = useMemo<HistRow | null>(() => {
    const ordered = [...history].sort((a, b) => (a.season || '').localeCompare(b.season || ''))
    return ordered.length ? ordered[ordered.length - 1] : null
  }, [history])

  const sum = data?.summary ?? {}
  const allTime = data?.allTime ?? {}
  const all = num(allTime.n)
  const allFt = num(allTime.ft)
  const kpis = useMemo(
    () => [
      {
        label: pick(lang, '比赛', 'Matches'),
        value: fmtNum(num(sum.n)),
        sub: all !== null ? pick(lang, `全量 ${fmtNum(all)} 场`, `${fmtNum(all)} all-time`) : undefined,
      },
      {
        label: pick(lang, '已完赛', 'Finished'),
        value: fmtNum(num(sum.ft)),
        sub: num(sum.upcoming) ? pick(lang, `待赛 ${fmtNum(num(sum.upcoming))} 场`, `${fmtNum(num(sum.upcoming))} upcoming`) : undefined,
      },
      { label: pick(lang, '场均进球', 'Goals / match'), value: dec(num(sum.goals_pg)) },
      { label: pick(lang, '场均 xG', 'xG / match'), value: dec(num(sum.xg_pg)) },
      {
        label: pick(lang, '时间跨度', 'Date range'),
        value: `${day(sum.mn)} → ${day(sum.mx)}`,
        sub: allFt !== null ? pick(lang, `本季 ${fmtNum(num(sum.ft))} / 全量 ${fmtNum(allFt)}`, `${fmtNum(num(sum.ft))} this season`) : undefined,
      },
    ],
    [lang, sum.n, sum.ft, sum.upcoming, sum.goals_pg, sum.xg_pg, sum.mn, sum.mx, all, allFt],
  )

  const maxPpg = Math.max(0.1, ...teamsList.map((t) => t.ppg || 0))
  const maxShots = Math.max(1, ...teamsList.map((t) => t.shots_pg || 0))

  /* -------- 概览行（没有数据的项直接省略） -------- */
  const overview: { key: string; value: string }[] = []
  if (league?.country)
    overview.push({ key: pick(lang, '国家 / 地区', 'Country'), value: pick(lang, league.country, league.countryEn || league.nameEn) })
  overview.push({ key: pick(lang, '赛季', 'Season'), value: league?.season || season || '—' })
  overview.push({ key: pick(lang, '比赛数', 'Matches'), value: fmtNum(num(sum.n)) })
  overview.push({ key: pick(lang, '球队数', 'Teams'), value: standings.length ? fmtNum(standings.length) : '—' })
  overview.push({ key: pick(lang, '场均进球', 'Goals / match'), value: dec(num(sum.goals_pg)) })
  if (num(sum.xg_pg) !== null) overview.push({ key: pick(lang, '场均 xG', 'xG / match'), value: dec(num(sum.xg_pg)) })
  const ss = data?.seasonStats
  if (ss) {
    if (ss.home_win_pct !== null && ss.home_win_pct !== undefined)
      overview.push({ key: pick(lang, '主胜', 'Home win'), value: pct(ss.home_win_pct) })
    if (ss.draw_pct !== null && ss.draw_pct !== undefined)
      overview.push({ key: pick(lang, '平局', 'Draw'), value: pct(ss.draw_pct) })
    if (ss.away_win_pct !== null && ss.away_win_pct !== undefined)
      overview.push({ key: pick(lang, '客胜', 'Away win'), value: pct(ss.away_win_pct) })
  } else if (latest) {
    if (latest.home_win_pct !== null && latest.home_win_pct !== undefined)
      overview.push({ key: pick(lang, '主胜', 'Home win'), value: pct(latest.home_win_pct) })
    if (latest.draw_pct !== null && latest.draw_pct !== undefined)
      overview.push({ key: pick(lang, '平局', 'Draw'), value: pct(latest.draw_pct) })
    if (latest.away_win_pct !== null && latest.away_win_pct !== undefined)
      overview.push({ key: pick(lang, '客胜', 'Away win'), value: pct(latest.away_win_pct) })
  }
  if (overview.length === 0)
    overview.push({ key: pick(lang, '状态', 'Status'), value: pick(lang, '暂无数据', 'No data') })

  const tabs = seasons.map((s) => ({ key: s, label: s }))
  const headerRight = (
    <div className="flex flex-wrap items-center gap-2">
      {league?.season ? <Pill tone="yellow">{league.season}</Pill> : null}
      {tabs.length > 0 ? <Tabs items={tabs} value={season} onChange={setSeason} /> : null}
    </div>
  )

  return (
    <PageShell
      title={pick(lang, league?.name, league?.nameEn) || pick(lang, '联赛详情', 'League detail')}
      subtitle={
        league
          ? `${league.season || season} · ${fmtNum(standings.length)} ${pick(lang, '支球队', 'teams')} · ${pick(lang, league.country, league.countryEn || league.nameEn) || '—'}`
          : undefined
      }
      activePath="/leagues"
      right={headerRight}
    >
      {error && !data ? (
        <div className="mt-6">
          <ErrorState text={error} />
        </div>
      ) : null}

      <div className="mt-6">
        {loading && !data ? (
          <div className="grid gap-4" style={{ gridTemplateColumns: 'repeat(5, minmax(0, 1fr))' }}>
            {Array.from({ length: 5 }).map((_, i) => (
              <div key={i} className="glass rounded-[24px] px-5 py-4">
                <CardSkeleton rows={2} />
              </div>
            ))}
          </div>
        ) : (
          <KpiStrip items={kpis} />
        )}
      </div>

      {error && data ? (
        <p className="t-3 mt-4 text-[11.5px] font-medium">
          {pick(lang, '数据刷新失败，当前展示的是上一次成功加载的结果。', 'Refresh failed — showing the last successful load.')}
        </p>
      ) : null}

      <div className="mt-6 grid grid-cols-1 gap-5 xl:grid-cols-[minmax(0,1fr)_360px]">
        {/* ================= 左列 ================= */}
        <div className="flex min-w-0 flex-col gap-5">
          {/* ① 积分榜 */}
          <SectionCard
            title={pick(lang, '积分榜', 'Standings')}
            hint={`${seasonLabel(season || league?.season || '')} · ${fmtNum(standings.length)} ${pick(lang, '支球队', 'teams')}`}
            bodyClass="-mx-1 overflow-x-auto"
          >
            {loading && !data ? (
              <CardSkeleton rows={8} />
            ) : standings.length === 0 ? (
              <EmptyState text={pick(lang, '该赛季暂无积分榜数据', 'No standings for this season')} />
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="line-c border-b">
                    <th className={TH}>#</th>
                    <th className={TH}>{pick(lang, '球队', 'Team')}</th>
                    <th className={THR}>{pick(lang, '场次', 'P')}</th>
                    <th className={THR}>{pick(lang, '胜平负', 'W-D-L')}</th>
                    <th className={THR}>{pick(lang, '进-失', 'GF-GA')}</th>
                    <th className={THR}>{pick(lang, '净胜', 'GD')}</th>
                    <th className={THR}>{pick(lang, '积分', 'Pts')}</th>
                    <th className={TH}>{pick(lang, '近况', 'Form')}</th>
                  </tr>
                </thead>
                <tbody>
                  {standings.map((s: StandRow) => (
                    <tr key={s.team_id ?? s.rank} className="line-c border-b last:border-0 hover:bg-white/35">
                      <td className={TD}>
                        <span className="t-1 flex h-6 w-6 items-center justify-center rounded-full bg-[var(--track)] text-[11px] font-semibold tabular-nums">
                          {s.rank}
                        </span>
                      </td>
                      <td className={TD}>
                        <span className="flex items-center gap-2.5">
                          {s.logo_url ? (
                            <img src={s.logo_url} alt="" className="crest h-5 w-5 shrink-0 rounded-full" loading="lazy" />
                          ) : (
                            <span className="h-5 w-5 shrink-0 rounded-full bg-[var(--track)]" />
                          )}
                          <span className="t-1 max-w-[210px] truncate font-semibold">{pick(lang, s.name, s.name_en)}</span>
                        </span>
                      </td>
                      <td className={TDR}>{fmtNum(s.played)}</td>
                      <td className={TDR}>
                        {fmtNum(s.won)}-{fmtNum(s.draw)}-{fmtNum(s.lost)}
                      </td>
                      <td className={TDR}>
                        {fmtNum(s.goals_for)}-{fmtNum(s.goals_against)}
                      </td>
                      <td className={`${TDR} ${s.goal_diff > 0 ? 'text-[#255a30]' : s.goal_diff < 0 ? 'text-[#7a3540]' : ''}`}>
                        {s.goal_diff > 0 ? `+${fmtNum(s.goal_diff)}` : fmtNum(s.goal_diff)}
                      </td>
                      <td className={`${TDR} t-1 font-semibold`}>{fmtNum(s.points)}</td>
                      <td className={TD}>
                        <FormDots form={s.form} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </SectionCard>

          {/* ② 赛季趋势 */}
          <SectionCard
            title={pick(lang, '赛季趋势', 'Seasonal trend')}
            hint={pick(lang, '场均进球 / 场均 xG', 'Goals per match · xG per match')}
            right={
              <div className="flex items-center gap-3">
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: AMBER }} />
                  <span className="t-3 text-[10px] font-medium">{pick(lang, '场均进球', 'Goals / match')}</span>
                </span>
                <span className="flex items-center gap-1.5">
                  <span className="h-2 w-2 rounded-full" style={{ backgroundColor: BLUE }} />
                  <span className="t-3 text-[10px] font-medium">{pick(lang, '场均 xG', 'xG / match')}</span>
                </span>
              </div>
            }
          >
            <SeasonTrend history={history} />
          </SectionCard>

          {/* ③ 球队实力 */}
          <SectionCard
            title={pick(lang, '球队实力', 'Team strength')}
            hint={pick(lang, '全量聚合（跨赛季，不随赛季切换）', 'all-time aggregate · not season-scoped')}
            bodyClass="-mx-1 overflow-x-auto"
          >
            {loading && !data ? (
              <CardSkeleton rows={8} />
            ) : teamsList.length === 0 ? (
              <EmptyState text={pick(lang, '暂无球队数据', 'No team data')} />
            ) : (
              <table className="w-full border-collapse">
                <thead>
                  <tr className="line-c border-b">
                    <th className={TH}>{pick(lang, '球队', 'Team')}</th>
                    <th className={THR}>ppg</th>
                    <th className={THR}>{pick(lang, '场均进球', 'GF / match')}</th>
                    <th className={THR}>{pick(lang, '场均 xG', 'xG / match')}</th>
                    <th className={THR}>{pick(lang, '场均失球', 'GA / match')}</th>
                    <th className={THR}>{pick(lang, '场均射门', 'Shots / match')}</th>
                    <th className={THR}>{pick(lang, '阵容身价', 'Squad value')}</th>
                    <th className={THR}>{pick(lang, '平均年龄', 'Avg age')}</th>
                  </tr>
                </thead>
                <tbody>
                  {teamsList.map((t: TeamRow) => (
                    <tr key={t.team_id} className="line-c border-b last:border-0 hover:bg-white/35">
                      <td className={TD}>
                        <span className="flex items-center gap-2.5">
                          {t.logo_url ? (
                            <img src={t.logo_url} alt="" className="crest h-5 w-5 shrink-0 rounded-full" loading="lazy" />
                          ) : (
                            <span className="h-5 w-5 shrink-0 rounded-full bg-[var(--track)]" />
                          )}
                          <span className="t-1 max-w-[180px] truncate font-semibold">{t.team}</span>
                        </span>
                      </td>
                      <td className={TDR}>
                        <span className="inline-flex w-full items-center justify-end gap-2">
                          <MiniBar value={t.ppg} max={maxPpg} />
                          <span className="t-1 w-8 text-right font-semibold">{dec(t.ppg, 2)}</span>
                        </span>
                      </td>
                      <td className={TDR}>{dec(num(t.goals_pg), 2)}</td>
                      <td className={TDR}>{dec(num(t.xg_pg), 2)}</td>
                      <td className={TDR}>{dec(num(t.conceded_pg), 2)}</td>
                      <td className={TDR}>
                        <span className="inline-flex w-full items-center justify-end gap-2">
                          <MiniBar value={num(t.shots_pg)} max={maxShots} tone="blue" />
                          <span className="w-11 text-right">{dec(num(t.shots_pg), 1)}</span>
                        </span>
                      </td>
                      <td className={TDR}>{t.squad_value === null ? '—' : fmtCompact(lang, t.squad_value)}</td>
                      <td className={TDR}>{dec(num(t.avg_age), 1)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </SectionCard>
        </div>

        {/* ================= 右列 ================= */}
        <div className="flex min-w-0 flex-col gap-5">
          {/* ① 射手榜（dark） */}
          <SectionCard
            dark
            title={pick(lang, '射手榜', 'Top scorers')}
            hint={
              data?.scorersSeason?.label
                ? pick(
                    lang,
                    `前 10 · 赛季 ${data.scorersSeason.label}（Transfermarkt）`,
                    `Top 10 · season ${data.scorersSeason.label} (Transfermarkt)`,
                  )
                : pick(lang, '前 10 · 进球 / 助攻 / 出场', 'Top 10 · goals / assists / apps')
            }
          >
            {loading && !data ? (
              <CardSkeleton rows={6} />
            ) : scorers.length === 0 ? (
              <EmptyState text={pick(lang, '暂无射手数据', 'No scorer data')} />
            ) : (
              <ul className="flex flex-col">
                {scorers.slice(0, 10).map((s: ScorerRow, i) => (
                  <li
                    key={s.player_id}
                    className={`flex items-center gap-2.5 py-2 ${i > 0 ? 'border-t border-white/10' : ''}`}
                  >
                    <span className="on-ink w-4 shrink-0 text-[11px] font-semibold tabular-nums opacity-60">{i + 1}</span>
                    {s.image_url ? (
                      <img
                        src={s.image_url}
                        alt=""
                        className="h-7 w-7 shrink-0 rounded-full object-cover"
                        loading="lazy"
                      />
                    ) : (
                      <span className="bg-ink on-ink flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
                        {initials(s.player_name)}
                      </span>
                    )}
                    <span className="min-w-0 flex-1">
                      <span className="on-ink block truncate text-[12px] font-semibold">{s.player_name}</span>
                      <span className="block truncate text-[10px] font-medium text-[#B3AD97]">{s.team_name || '—'}</span>
                    </span>
                    <span className="shrink-0 text-right">
                      <span className="block text-[13px] font-bold tabular-nums" style={{ color: AMBER }}>
                        {fmtNum(s.goals)}
                      </span>
                      <span className="block text-[9.5px] font-medium tabular-nums text-[#B3AD97]">
                        {fmtNum(s.assists)} {pick(lang, '助', 'A')} · {fmtNum(s.appearances)} {pick(lang, '场', 'P')}
                      </span>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </SectionCard>

          {/* ② 联赛概览 */}
          <SectionCard title={pick(lang, '联赛概览', 'League overview')} hint={pick(lang, '排序不分先后', 'key facts')}>
            <dl className="flex flex-col">
              {overview.map((row, i) => (
                <div
                  key={row.key}
                  className={`flex items-baseline justify-between gap-3 py-2 ${i > 0 ? 'line-c border-t' : ''}`}
                >
                  <dt className="t-3 text-[11.5px] font-medium">{row.key}</dt>
                  <dd className="t-1 text-right text-[12.5px] font-semibold tabular-nums">{row.value}</dd>
                </div>
              ))}
            </dl>
          </SectionCard>
        </div>
      </div>
    </PageShell>
  )
}
