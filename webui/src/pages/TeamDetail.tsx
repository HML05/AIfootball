/**
 * 球队详情页 —— 真实数据来自 /api/ui/teams/{id}（teams × team_radar × standings × matches × players）
 *
 * 版式：头部资料卡 → 跨赛季全量 KPI → 七维画像 + 联赛现状 → 赛季战绩表 → 近期战绩 + 未来赛程 → 阵容。
 *
 * 口径说明（重要，页面上有对应 hint）：
 * - metrics / radar 取自 team_radar 预计算表，是「跨赛季全量」口径，不等于本赛季；
 * - seasons 按 matches.season 聚合，`played` 含未开赛/未结束场次，`won/drawn/lost` 与进失球也
 *   按 match 行统计（胜场不含未结束场次），所以 played ≠ ft、胜平负之和可能 < ft；
 *   本页把「场次 已完赛」两列并排展示，让口径自明；
 * - radar / metrics / standing 都可能为 null（球队不在 team_radar / standings 里），
 *   recent / upcoming / squad 可能为空数组 → 降级为 EmptyState，不渲染空卡、不出现 NaN。
 */
import { useState, type CSSProperties, type ReactNode } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { PageShell, SectionCard, Pill, Bar, EmptyState, ErrorState, KpiStrip } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api, logoUrl } from '../lib/api'
import type { FixtureRow, FormRow, SquadRow, TeamSeasonRow } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, initials, pick } from '../data/live'
import { footLabel, posLabel } from '../lib/labels'
import { useLang } from '../i18n'

/* ---------- 展示层常量 ---------- */

const RADAR_DIMS: { key: 'attack' | 'defense' | 'dominance' | 'discipline' | 'value' | 'experience' | 'stability'; zh: string; en: string }[] = [
  { key: 'attack', zh: '进攻', en: 'Attack' },
  { key: 'defense', zh: '防守', en: 'Defense' },
  { key: 'dominance', zh: '掌控', en: 'Dominance' },
  { key: 'discipline', zh: '纪律', en: 'Discipline' },
  { key: 'value', zh: '身价', en: 'Value' },
  { key: 'experience', zh: '经验', en: 'Experience' },
  { key: 'stability', zh: '稳定', en: 'Stability' },
]

const GROUP_META: { key: 'GK' | 'DF' | 'MF' | 'FW'; zh: string; en: string; tone: 'yellow' | 'blue' | 'green' | 'pink' }[] = [
  { key: 'GK', zh: '门将', en: 'Goalkeeper', tone: 'yellow' },
  { key: 'DF', zh: '后卫', en: 'Defender', tone: 'blue' },
  { key: 'MF', zh: '中场', en: 'Midfielder', tone: 'green' },
  { key: 'FW', zh: '前锋', en: 'Forward', tone: 'pink' },
]

type ResultKey = 'W' | 'D' | 'L'

/* ---------- 格式化小工具 ---------- */

/** 大身价：1260M€ 读着别扭，按 十亿/百万 缩写（千分位由 fmtNum 兜底） */
function valueText(v: number | null | undefined, text: string | null | undefined): string {
  if (text) return text
  if (v === null || v === undefined || Number.isNaN(v) || v <= 0) return '—'
  if (v >= 1_000_000_000) return `${(v / 1_000_000_000).toFixed(2)}B€`
  if (v >= 1_000_000) return `${(v / 1_000_000).toFixed(1)}M€`
  return `${Math.round(v / 1_000)}K€`
}

/** 2026/27 → 26/27（表里太长的赛季名统一成短码） */
function seasonLabel(s: string | null | undefined): string {
  if (!s) return '—'
  const m = s.match(/^(\d{4})\/(\d{2,4})$/)
  if (!m) return s
  return `${m[1].slice(2)}/${m[2].length === 4 ? m[2].slice(2) : m[2]}`
}

/** 日期：2026-09-13 11:30 → 09-13 */
function dayOf(date: string | null | undefined): string {
  const d = (date ?? '').split(' ')[0]
  const [, m = '', day = ''] = d.split('-')
  return m && day ? `${m}-${day}` : d || '—'
}

const num1 = (v: number | null | undefined): string => (typeof v === 'number' ? v.toFixed(1) : '—')
const num2 = (v: number | null | undefined): string => (typeof v === 'number' ? v.toFixed(2) : '—')
const intOr = (v: number | null | undefined): string => (typeof v === 'number' ? fmtNum(v) : '—')

/* ---------- 本地小件组件 ---------- */

/** 队徽：优先走后端本地代理（离线可用），失败 / 缺失时降级成首字母圆片 */
function Crest({ id, name, size = 24 }: { id: number | null; name: string; size?: number }) {
  const [bad, setBad] = useState(false)
  const src = logoUrl(id)
  if (!src || bad) {
    return (
      <span
        className="glass-soft t-2 flex shrink-0 items-center justify-center rounded-full font-bold"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      >
        {initials(name)}
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setBad(true)}
      className="crest shrink-0 rounded-full"
      style={{ width: size, height: size }}
    />
  )
}

/** W/D/L 圆点 */
function ResultDot({ result, size = 22 }: { result: ResultKey; size?: number }) {
  const bg = result === 'W' ? 'bg-[#9FD6A8] text-[#255a30]' : result === 'D' ? 'bg-[var(--track)] t-2' : 'bg-[#E8B4B8] text-[#7a3540]'
  return (
    <span
      className={`flex shrink-0 items-center justify-center rounded-full font-bold ${bg}`}
      style={{ width: size, height: size, fontSize: Math.round(size * 0.45) }}
    >
      {result}
    </span>
  )
}

function InfoRow({ label, value, title }: { label: string; value: ReactNode; title?: string }) {
  return (
    <div className="min-w-0">
      <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{label}</p>
      <p className="t-1 mt-0.5 truncate text-[12.5px] font-semibold" title={title}>
        {value}
      </p>
    </div>
  )
}

/** 指标单元：有 label 时上方加一行小标题，否则只有一个数值（行内对齐） */
function StatCol({ label, value, strong = false }: { label?: string; value: string; strong?: boolean }) {
  return (
    <div className="min-w-0">
      {label ? <p className="t-3 text-[9.5px] font-semibold uppercase tracking-wider">{label}</p> : null}
      <p className={`text-[12.5px] tabular-nums ${label ? 'mt-0.5' : ''} ${strong ? 't-1 font-semibold' : 't-2 font-medium'}`}>
        {value}
      </p>
    </div>
  )
}

/** 主客标记 */
function SidePill({ home }: { home: boolean }) {
  const { lang } = useLang()
  return <Pill tone={home ? 'yellow' : 'blue'}>{home ? pick(lang, '主', 'H') : pick(lang, '客', 'A')}</Pill>
}

/** 三分类概率条（无预测时显示「暂无预测」） */
function PredictionBars({ row }: { row: FixtureRow }) {
  const { lang } = useLang()
  const has = typeof row.pred_home_win === 'number' && typeof row.pred_draw === 'number' && typeof row.pred_away_win === 'number'
  if (!has) {
    return <span className="t-3 text-[10.5px] font-medium">{pick(lang, '暂无预测', 'No prediction')}</span>
  }
  const segs: { key: string; label: string; v: number; tone: 'yellow' | 'muted' | 'blue' }[] = [
    { key: 'h', label: pick(lang, '主胜', 'Home'), v: row.pred_home_win ?? 0, tone: 'yellow' },
    { key: 'd', label: pick(lang, '平局', 'Draw'), v: row.pred_draw ?? 0, tone: 'muted' },
    { key: 'a', label: pick(lang, '客胜', 'Away'), v: row.pred_away_win ?? 0, tone: 'blue' },
  ]
  return (
    <span className="flex items-center gap-2">
      {segs.map((s) => (
        <span key={s.key} className="flex items-center gap-1.5">
          <span className="t-3 text-[9.5px] font-medium">{s.label}</span>
          <span className="block w-[46px]">
            <Bar value={s.v * 100} max={100} tone={s.tone} height={6} />
          </span>
          <span className="t-2 text-[10.5px] font-semibold tabular-nums">{(s.v * 100).toFixed(0)}%</span>
        </span>
      ))}
      {row.pred_result ? (
        <Pill tone={row.pred_result === 'H' ? 'yellow' : row.pred_result === 'D' ? 'muted' : 'blue'}>
          {row.pred_result === 'H' ? pick(lang, '主胜', 'Home') : row.pred_result === 'D' ? pick(lang, '平局', 'Draw') : pick(lang, '客胜', 'Away')}
        </Pill>
      ) : null}
    </span>
  )
}

/* ---------- 页面 ---------- */

export default function TeamDetail() {
  const { lang } = useLang()
  const { id } = useParams()
  const navigate = useNavigate()
  const teamId = Number(id)
  const { data, loading, error } = useApi(() => api.teamDetail(teamId), `team:${id}`)

  const title = pick(lang, '球队详情', 'Team Detail')

  if (loading && !data) {
    return (
      <PageShell title={title} subtitle={pick(lang, '正在读取球队数据…', 'loading team data…')} activePath="/teams">
        <div className="mt-6">
          <CardSkeleton rows={12} />
        </div>
      </PageShell>
    )
  }

  if (error || !data) {
    return (
      <PageShell title={title} subtitle={pick(lang, '球队数据', 'team data')} activePath="/teams">
        <div className="mt-6">
          <ErrorState text={error ?? pick(lang, '未找到该球队', 'Team not found')} />
        </div>
      </PageShell>
    )
  }

  const t = data.team
  const name = pick(lang, t.name, t.nameEn)
  const altName = lang === 'zh' ? t.nameEn : t.name
  const leagueName = pick(lang, t.league.name, t.league.nameEn)
  const radar = data.radar
  const metrics = data.metrics
  const standing = data.standing
  const seasons = data.seasons ?? []
  const recent = (data.recent ?? []).slice(0, 8)
  const upcoming = (data.upcoming ?? []).slice(0, 5)
  const squad = (data.squad ?? []).slice(0, 12)
  const groups = data.squadGroups

  const subParts = [
    leagueName || '',
    t.stadium ?? '',
    t.capacity ? `${pick(lang, '容量', 'Capacity')} ${fmtNum(t.capacity)}` : '',
    t.founded ? `${pick(lang, '成立', 'Founded')} ${t.founded}` : '',
  ].filter(Boolean)

  const kpis = metrics
    ? [
        { label: pick(lang, '场均进球', 'Goals / game'), value: num2(metrics.goalsPg) },
        { label: pick(lang, '场均失球', 'Conceded / game'), value: num2(metrics.concededPg) },
        // 说明：KpiStrip 给 label 加了 uppercase，xG 会被渲染成 XG，此处标签统一写 xG 由 CSS 决定
        { label: pick(lang, '场均 xG', 'xG / game'), value: num2(metrics.xgPg) },
        { label: pick(lang, '场均射门', 'Shots / game'), value: num2(metrics.shotsPg) },
        { label: pick(lang, '场均积分', 'PPG'), value: num2(metrics.ppg) },
        { label: pick(lang, '阵容身价', 'Squad value'), value: valueText(metrics.squadValue, metrics.valueText), sub: 'Transfermarkt' },
        { label: pick(lang, '平均年龄', 'Average age'), value: num1(metrics.avgAge) },
      ]
    : []

  const recentStat = recent.reduce(
    (acc, m) => {
      if (m.result === 'W') acc.w += 1
      else if (m.result === 'D') acc.d += 1
      else if (m.result === 'L') acc.l += 1
      acc.gf += m.gf ?? 0
      acc.ga += m.ga ?? 0
      return acc
    },
    { w: 0, d: 0, l: 0, gf: 0, ga: 0 },
  )

  return (
    <PageShell title={name || title} subtitle={subParts.join(' · ') || pick(lang, '球队数据', 'team data')} activePath="/teams">
      <div className="mt-6 flex flex-col gap-5">
        {/* ---------- 1. 头部资料卡 ---------- */}
        <div className="anim-in" style={{ '--d': '60ms' } as CSSProperties}>
          <SectionCard>
            <div className="flex flex-wrap items-center gap-5">
              <Crest id={t.id} name={name} size={76} />
              <div className="flex min-w-0 flex-1 flex-col">
                <div className="flex flex-wrap items-center gap-2.5">
                  <h2 className="t-1 break-words text-[27px] font-semibold leading-tight">{name || '—'}</h2>
                  {t.elo !== null && t.elo !== undefined ? <Pill tone="ink">ELO {fmtNum(t.elo, 1)}</Pill> : null}
                </div>
                {altName && altName !== name ? <p className="t-3 mt-1 text-[12px] font-medium">{altName}</p> : null}
                <div className="mt-2.5 flex flex-wrap items-center gap-2">
                  {t.league.id !== null ? (
                    <Link
                      to={`/leagues/${t.league.id}`}
                      className="glass-soft card-hover t-1 flex items-center gap-1.5 rounded-full px-3 py-1 text-[11.5px] font-semibold transition-colors duration-300 hover:bg-[#F6C945]/35"
                      title={pick(lang, '查看联赛页', 'Open league page')}
                    >
                      {leagueName || '—'}
                      <span className="t-3">›</span>
                    </Link>
                  ) : (
                    <Pill tone="muted">{leagueName || pick(lang, '未知联赛', 'Unknown league')}</Pill>
                  )}
                  {standing ? (
                    <Pill tone="yellow">
                      {pick(lang, '联赛第', 'Rank')} {standing.rank}
                      {pick(lang, ' 位 · ', ' · ')}
                      {fmtNum(standing.points)} {pick(lang, '分', 'pts')}
                    </Pill>
                  ) : null}
                  {standing?.form ? <Pill tone="muted">{pick(lang, '近况', 'Form')} {standing.form}</Pill> : null}
                </div>
              </div>
            </div>

            <div className="line-c mt-5 grid grid-cols-2 gap-x-5 gap-y-3.5 border-t pt-4 sm:grid-cols-4">
              <InfoRow
                label={pick(lang, '主场', 'Stadium')}
                value={t.stadium ?? '—'}
                title={t.stadium ?? undefined}
              />
              <InfoRow label={pick(lang, '主教练', 'Manager')} value={t.manager ?? '—'} title={t.manager ?? undefined} />
              <InfoRow
                label={pick(lang, '成立年份', 'Founded')}
                value={t.founded === null || t.founded === undefined ? '—' : String(t.founded)}
              />
              <InfoRow
                label={pick(lang, '容量', 'Capacity')}
                value={t.capacity === null || t.capacity === undefined ? '—' : fmtNum(t.capacity)}
              />
            </div>
          </SectionCard>
        </div>

        {/* ---------- 2. KPI（跨赛季全量口径） ---------- */}
        {kpis.length ? (
          <div className="flex flex-col gap-2.5">
            <div className="anim-in flex flex-wrap items-baseline gap-2.5" style={{ '--d': '80ms' } as CSSProperties}>
              <h2 className="t-1 text-[15px] font-semibold">{pick(lang, '核心指标', 'Key metrics')}</h2>
              <span className="t-3 text-[10.5px] font-medium">
                {pick(lang, '跨赛季全量口径（team_radar 预计算表），不是本赛季数据', 'all-time scope (team_radar pre-computed), not the current season')}
                {metrics?.matches !== null && metrics?.matches !== undefined
                  ? ` · ${pick(lang, '样本', 'sample')} ${fmtNum(metrics.matches)} ${pick(lang, '场', 'matches')}`
                  : ''}
              </span>
            </div>
            <KpiStrip items={kpis} className="grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-7" />
          </div>
        ) : null}

        {/* ---------- 3. 七维画像 + 联赛现状 ---------- */}
        <div className="grid grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)] gap-5">
          <SectionCard
            title={pick(lang, '七维画像', 'Seven-dimension profile')}
            hint={pick(lang, '跨赛季全量口径 · 0-100 分位', 'all-time scope · percentile 0-100')}
          >
            {!radar ? (
              <EmptyState text={pick(lang, '该球队暂无画像数据', 'No profile data for this team')} />
            ) : (
              <div className="flex flex-col gap-2.5">
                {RADAR_DIMS.map((d) => {
                  const v = radar[d.key]
                  const shown = typeof v === 'number' && !Number.isNaN(v)
                  return (
                    <div key={d.key} className="flex items-center gap-3">
                      {/* 标签列要容纳英文最长词 Discipline / Dominance，46px 会被裁掉 */}
                      <span className="t-2 w-[70px] shrink-0 text-[11.5px] font-medium">{pick(lang, d.zh, d.en)}</span>
                      <span className="min-w-0 flex-1">
                        <Bar value={shown ? v : 0} max={100} tone={shown && v >= 70 ? 'yellow' : 'blue'} height={7} />
                      </span>
                      <span className="t-2 w-9 shrink-0 text-right text-[12px] font-semibold tabular-nums">
                        {shown ? Math.round(v) : '—'}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title={pick(lang, '联赛现状', 'League standing')}
            hint={standing?.season ? `${pick(lang, '赛季', 'Season')} ${seasonLabel(standing.season)}` : pick(lang, '最新积分榜', 'latest table')}
          >
            {!standing ? (
              <EmptyState text={pick(lang, '暂无积分榜数据', 'No standing data')} />
            ) : (
              <>
                <div className="flex items-end gap-4">
                  <div>
                    <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '排名', 'Rank')}</p>
                    <p className="t-1 mt-1 text-[32px] font-medium leading-none tabular-nums">{standing.rank}</p>
                  </div>
                  <div>
                    <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '积分', 'Points')}</p>
                    <p className="t-1 mt-1 text-[32px] font-medium leading-none tabular-nums">{standing.points}</p>
                  </div>
                  <div className="ml-auto text-right">
                    <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '净胜球', 'Goal diff')}</p>
                    <p className="t-1 mt-1 text-[20px] font-semibold leading-none tabular-nums">
                      {standing.goal_diff > 0 ? `+${standing.goal_diff}` : standing.goal_diff}
                    </p>
                  </div>
                </div>
                <div className="line-c mt-4 flex flex-wrap items-center gap-x-5 gap-y-1.5 border-t pt-3.5">
                  {[
                    { label: pick(lang, '场次', 'Played'), value: fmtNum(standing.played) },
                    { label: pick(lang, '胜', 'Won'), value: fmtNum(standing.won) },
                    { label: pick(lang, '平', 'Drawn'), value: fmtNum(standing.draw) },
                    { label: pick(lang, '负', 'Lost'), value: fmtNum(standing.lost) },
                    { label: pick(lang, '进 / 失', 'GF / GA'), value: `${standing.goals_for} / ${standing.goals_against}` },
                  ].map((c) => (
                    <div key={c.label} className="min-w-0">
                      <p className="t-3 text-[9.5px] font-semibold uppercase tracking-wider">{c.label}</p>
                      <p className="t-1 mt-0.5 text-[13px] font-semibold tabular-nums">{c.value}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </SectionCard>
        </div>

        {/* ---------- 4. 赛季战绩表 ---------- */}
        <SectionCard
          title={pick(lang, '赛季战绩', 'Season record')}
          hint={pick(lang, '按 matches.season 聚合 · 最多 6 个赛季', 'aggregated from matches.season · up to 6 seasons')}
          right={<Pill tone="muted">{seasons.length}</Pill>}
        >
          {!seasons.length ? (
            <EmptyState text={pick(lang, '暂无赛季数据', 'No season data')} />
          ) : (
            <>
              <div className="-mx-1 overflow-x-auto">
                <div className="min-w-[680px] px-1">
                  <div className="grid grid-cols-[96px_repeat(8,minmax(0,1fr))] items-center gap-3">
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '赛季', 'Season')}</span>
                    {[
                      pick(lang, '场次', 'Played'),
                      pick(lang, '已完赛', 'Finished'),
                      pick(lang, '胜', 'W'),
                      pick(lang, '平', 'D'),
                      pick(lang, '负', 'L'),
                      pick(lang, '进球', 'GF'),
                      pick(lang, '失球', 'GA'),
                      pick(lang, '场均 xG', 'xG / game'),
                    ].map((label) => (
                      <span key={label} className="t-3 text-[10px] font-semibold uppercase tracking-wider">
                        {label}
                      </span>
                    ))}

                    {seasons.map((s: TeamSeasonRow) => (
                      <SeasonRowCells key={s.seasonCode || s.season} s={s} />
                    ))}
                  </div>
                </div>
              </div>
              <p className="t-3 mt-3.5 text-[10.5px] font-medium leading-relaxed">
                {pick(
                  lang,
                  '口径：场次含已排期未开赛场次；胜/平/负只统计已结束的比赛，因此三者之和可能小于场次。',
                  'Scope: played includes scheduled fixtures; W/D/L count finished matches only, so they may sum to less than played.',
                )}
              </p>
            </>
          )}
        </SectionCard>

        {/* ---------- 5. 近期战绩 + 6. 未来赛程 ---------- */}
        <div className="grid grid-cols-[minmax(0,1fr)_minmax(0,1fr)] gap-5">
          <SectionCard
            title={pick(lang, '近期战绩', 'Recent form')}
            hint={pick(lang, '最近 8 场（含各赛事）', 'last 8 matches (all competitions)')}
            right={
              recent.length ? (
                <span className="flex items-center gap-1.5">
                  <Pill tone="green">{recentStat.w}W</Pill>
                  <Pill tone="muted">{recentStat.d}D</Pill>
                  <Pill tone="pink">{recentStat.l}L</Pill>
                  <span className="t-3 text-[10.5px] font-medium tabular-nums">
                    {recentStat.gf}:{recentStat.ga}
                  </span>
                </span>
              ) : undefined
            }
          >
            {!recent.length ? (
              <EmptyState text={pick(lang, '暂无近期战绩', 'No recent matches')} />
            ) : (
              <div className="flex flex-col gap-2">
                {recent.map((m: FormRow) => {
                  const oppName = m.isHome ? pick(lang, m.a, m.a_en) : pick(lang, m.h, m.h_en)
                  const oppId = m.isHome ? m.away_team_id : m.home_team_id
                  return (
                    <button
                      key={m.match_id}
                      type="button"
                      onClick={() => navigate(`/matches/${m.match_id}`)}
                      className="glass-soft line-c card-hover flex w-full items-center gap-2.5 rounded-[18px] border border-transparent px-3 py-2.5 text-left transition-colors duration-300 hover:border-[#F6C945]/40"
                      title={pick(lang, '查看比赛详情', 'Open match detail')}
                    >
                      <ResultDot result={m.result} />
                      <span className="flex min-w-0 flex-1 items-center gap-2">
                        <Crest id={oppId} name={oppName} size={20} />
                        <span className="t-1 min-w-0 flex-1 truncate text-[12.5px] font-medium" title={oppName}>
                          {oppName || '—'}
                        </span>
                        <SidePill home={m.isHome} />
                      </span>
                      <span className="t-1 w-7 shrink-0 text-right text-[13.5px] font-semibold tabular-nums">
                        {m.gf ?? '—'}
                      </span>
                      <span className="t-3 shrink-0 text-[11px]">-</span>
                      <span className="t-1 w-7 shrink-0 text-[13.5px] font-semibold tabular-nums">{m.ga ?? '—'}</span>
                      <span className="t-3 w-[40px] shrink-0 text-right text-[10.5px] tabular-nums">{dayOf(m.date)}</span>
                    </button>
                  )
                })}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title={pick(lang, '未来赛程', 'Upcoming fixtures')}
            hint={pick(lang, '最近 5 场 · 三分类预测概率', 'next 5 · 1X2 probabilities')}
            right={upcoming.length ? <Pill tone="yellow">{upcoming.length}</Pill> : undefined}
          >
            {!upcoming.length ? (
              <EmptyState text={pick(lang, '暂无待赛比赛', 'No upcoming fixtures')} />
            ) : (
              <div className="flex flex-col gap-2">
                {upcoming.map((u: FixtureRow) => {
                  const isHome = u.h_id === teamId
                  const oppName = isHome ? pick(lang, u.a, u.a_en) : pick(lang, u.h, u.h_en)
                  const oppId = isHome ? u.a_id : u.h_id
                  return (
                    <button
                      key={u.match_id}
                      type="button"
                      onClick={() => navigate(`/matches/${u.match_id}`)}
                      className="glass-soft line-c card-hover flex w-full flex-wrap items-center gap-2.5 rounded-[18px] border border-transparent px-3 py-2.5 text-left transition-colors duration-300 hover:border-[#F6C945]/40"
                      title={pick(lang, '查看比赛详情', 'Open match detail')}
                    >
                      <span className="t-3 w-[42px] shrink-0 text-[11.5px] font-semibold tabular-nums">{dayOf(u.date)}</span>
                      <span className="flex w-[168px] shrink-0 items-center gap-2">
                        <Crest id={oppId} name={oppName} size={20} />
                        <span className="t-1 min-w-0 flex-1 truncate text-[12.5px] font-medium" title={oppName}>
                          {oppName || '—'}
                        </span>
                        <SidePill home={isHome} />
                      </span>
                      <span className="flex min-w-0 flex-1 items-center justify-end">
                        <PredictionBars row={u} />
                      </span>
                    </button>
                  )
                })}
              </div>
            )}
          </SectionCard>
        </div>

        {/* ---------- 7. 阵容 ---------- */}
        <SectionCard
          title={pick(lang, '阵容', 'Squad')}
          hint={pick(lang, '按身价排序 · 前 12 人 · 全队位置分布', 'top 12 by market value · full position breakdown')}
          right={
            <span className="flex flex-wrap items-center gap-1.5">
              {GROUP_META.filter((g) => (groups?.[g.key] ?? 0) > 0).map((g) => (
                <Pill key={g.key} tone={g.tone}>
                  {pick(lang, g.zh, g.en)} {groups?.[g.key] ?? 0}
                </Pill>
              ))}
              {groups ? <Pill tone="ink">{pick(lang, '全队', 'Total')} {groups.total}</Pill> : null}
            </span>
          }
        >
          {!squad.length ? (
            <EmptyState text={pick(lang, '暂无阵容数据', 'No squad data')} />
          ) : (
            <>
              <div className="-mx-1 overflow-x-auto">
                <div className="min-w-[640px] px-1">
                  {/* 表头与数据行各自成一条 6 列网格，列宽模板必须完全一致 */}
                  <div className="grid grid-cols-[minmax(0,1.5fr)_88px_repeat(4,minmax(0,0.7fr))] items-center gap-3">
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '球员', 'Player')}</span>
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '位置', 'Position')}</span>
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '年龄', 'Age')}</span>
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '球衣号', 'Shirt')}</span>
                    <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '惯用脚', 'Foot')}</span>
                    <span className="t-3 text-right text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '身价', 'Value')}</span>
                  </div>

                  {squad.map((p: SquadRow) => {
                    const pName = pick(lang, p.name, p.name_en)
                    return (
                      <div
                        key={p.player_id}
                        className="line-c grid grid-cols-[minmax(0,1.5fr)_88px_repeat(4,minmax(0,0.7fr))] items-center gap-3 border-t"
                      >
                        <button
                          type="button"
                          onClick={() => navigate(`/players/${p.player_id}`)}
                          className="flex min-w-0 items-center gap-2 py-2.5 pr-2 text-left"
                          title={pick(lang, '查看球员详情', 'Open player detail')}
                        >
                          <span className="glass-soft t-2 flex w-7 shrink-0 items-center justify-center rounded-full py-0.5 text-[9px] font-bold tabular-nums">
                            {p.group || '—'}
                          </span>
                          <span className="t-1 min-w-0 flex-1 truncate text-[12.5px] font-semibold" title={pName}>
                            {pName || '—'}
                          </span>
                          <span className="t-3 shrink-0 text-[10px]">›</span>
                        </button>
                        <span className="t-2 min-w-0 truncate text-[11.5px] font-medium" title={posLabel(lang, p.position)}>
                          {posLabel(lang, p.position)}
                        </span>
                        <span className="t-2 text-[12px] font-medium tabular-nums">{intOr(p.age)}</span>
                        <span className="t-2 text-[12px] font-medium tabular-nums">
                          {p.number === null || p.number === undefined ? '—' : `#${p.number}`}
                        </span>
                        <span className="t-2 text-[11.5px] font-medium">{p.foot ? footLabel(lang, p.foot) : '—'}</span>
                        <span className="t-1 text-right text-[12.5px] font-semibold text-[#6b4d05] tabular-nums">
                          {valueText(p.market_value, p.valueText)}
                        </span>
                      </div>
                    )
                  })}
                </div>
              </div>
              <p className="t-3 mt-3.5 text-[10.5px] font-medium">
                {pick(
                  lang,
                  '位置分布统计全队球员，上表只列身价最高的 12 人。',
                  'Position breakdown covers the whole squad; the table lists the top 12 by value.',
                )}
              </p>
            </>
          )}
        </SectionCard>
      </div>
    </PageShell>
  )
}

/* ---------- 赛季表的一行：整行占满父级 9 列，内部再按同一模板分列 ---------- */

function SeasonRowCells({ s }: { s: TeamSeasonRow }) {
  return (
    <div className="line-c col-span-9 grid grid-cols-[96px_repeat(8,minmax(0,1fr))] items-center gap-3 border-t">
      <span className="t-1 py-2.5 text-[12.5px] font-semibold tabular-nums">{seasonLabel(s.season)}</span>
      <StatCol label="" value={fmtNum(s.played)} />
      <StatCol label="" value={fmtNum(s.ft)} />
      <StatCol label="" value={fmtNum(s.won)} strong />
      <StatCol label="" value={fmtNum(s.drawn)} />
      <StatCol label="" value={fmtNum(s.lost)} />
      <StatCol label="" value={s.goalsFor === null || s.goalsFor === undefined ? '—' : fmtNum(s.goalsFor)} />
      <StatCol label="" value={s.goalsAgainst === null || s.goalsAgainst === undefined ? '—' : fmtNum(s.goalsAgainst)} />
      <StatCol label="" value={num2(s.xgPg)} />
    </div>
  )
}
