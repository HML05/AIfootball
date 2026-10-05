/**
 * 球队页 —— 真实数据来自 /api/ui/teams（team_radar × teams × leagues）
 *
 * 版式：KPI 条 → 工具条（搜索 / 联赛 / 排序）→ 表格（24/页）→ 分页 → 当前页前三「实力榜」七维。
 * 所有查询参数都进 useApi 的 cache key；null 字段统一显示 —。
 */
import { useEffect, useState } from 'react'
import { PageShell, SectionCard, Pill, Bar, Pager, SearchBox, Tabs, EmptyState, ErrorState, KpiStrip } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api, logoUrl } from '../lib/api'
import type { TeamRow } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, initials, pick } from '../data/live'
import { useLang } from '../i18n'

const PAGE_SIZE = 24

const SORTS = [
  { key: 'elo', zh: 'ELO', en: 'ELO' },
  { key: 'ppg', zh: '场均积分', en: 'PPG' },
  { key: 'xg', zh: '场均 xG', en: 'xG' },
  { key: 'value', zh: '身价', en: 'Value' },
  { key: 'goals', zh: '场均进球', en: 'Goals' },
]

const RADAR_DIMS = [
  { key: 'attack', zh: '进攻', en: 'Attack' },
  { key: 'defense', zh: '防守', en: 'Defense' },
  { key: 'dominance', zh: '控制', en: 'Dominance' },
  { key: 'discipline', zh: '纪律', en: 'Discipline' },
  { key: 'value', zh: '身价', en: 'Value' },
  { key: 'experience', zh: '经验', en: 'Experience' },
  { key: 'stability', zh: '稳定', en: 'Stability' },
]

/** 队徽：优先走后端本地代理（离线可用），失败或缺失时降级成首字母圆片 */
function Crest({ row, size = 24 }: { row: TeamRow; size?: number }) {
  const [bad, setBad] = useState(false)
  const src = logoUrl(row.team_id) ?? row.logo_url ?? undefined
  if (!src || bad) {
    return (
      <span
        className="glass-soft t-2 flex shrink-0 items-center justify-center rounded-full font-bold"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.38) }}
      >
        {initials(row.team)}
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

/** 联赛下拉（选项来自 /api/ui/leagues，不写死联赛数） */
function LeagueSelect({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { id: number; name: string; nameEn: string }[]
}) {
  const { lang } = useLang()
  return (
    <div className="glass-soft flex items-center rounded-full px-3.5 py-[7px]">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="t-1 max-w-[160px] cursor-pointer bg-transparent text-[11.5px] font-semibold outline-none"
        aria-label={pick(lang, '联赛筛选', 'League filter')}
      >
        <option value="">{pick(lang, '全部联赛', 'All leagues')}</option>
        {options.map((o) => (
          <option key={o.id} value={String(o.id)}>
            {pick(lang, o.name, o.nameEn)}
          </option>
        ))}
      </select>
    </div>
  )
}

export default function Teams() {
  const { lang } = useLang()
  const [q, setQ] = useState('')
  const [qDeb, setQDeb] = useState('')
  const [league, setLeague] = useState('')
  const [sort, setSort] = useState('elo')
  const [page, setPage] = useState(1)

  // 搜索 debounce 300ms
  useEffect(() => {
    const t = setTimeout(() => setQDeb(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    setPage(1)
  }, [qDeb, league, sort])

  const teams = useApi(
    () => api.teams({ page, size: PAGE_SIZE, q: qDeb, league: league || undefined, sort, dir: 'desc' }),
    `teams:${page}:${qDeb}:${league}:${sort}`,
  )
  const leagues = useApi(() => api.leagues(), 'leagues', 600_000)

  const items = teams.data?.items ?? []
  const total = teams.data?.total ?? 0
  const pages = teams.data?.pages ?? 1
  const agg = teams.data?.aggregates
  const top5 = teams.data?.top5 ?? []

  const scopeLabel = league
    ? pick(lang, '所选联赛', 'selected league')
    : qDeb
      ? pick(lang, '搜索结果', 'search result')
      : pick(lang, '全库', 'whole database')

  // 行内迷你条按「筛选范围」的上界归一，避免分页时视觉尺度漂移
  const maxGoals = agg?.avgGoalsPg ? Math.max(agg.avgGoalsPg * 2, 1) : 4
  const maxXg = maxGoals

  const kpis = [
    {
      label: pick(lang, '球队总数', 'Teams'),
      value: teams.data ? fmtNum(total) : '—',
      sub: pick(lang, '库内全部球队', 'in database'),
    },
    {
      label: pick(lang, '联赛数', 'Leagues'),
      value: leagues.data ? fmtNum(leagues.data.items.length) : '—',
      sub: pick(lang, '覆盖赛事', 'covered'),
    },
    {
      label: pick(lang, '球队场均进球', 'Goals / match (team)'),
      value: agg?.avgGoalsPg != null ? agg.avgGoalsPg.toFixed(2) : '—',
      sub: scopeLabel,
    },
    {
      label: pick(lang, '最高 ELO', 'Top ELO'),
      value: agg?.maxElo != null ? agg.maxElo.toFixed(1) : '—',
      sub: agg?.maxEloTeam ?? '—',
    },
  ]

  const subtitle = teams.data
    ? `${fmtNum(total)} ${pick(lang, '支球队', 'teams')} · ${pick(lang, '每场均数据 · 身价 · ELO', 'per-match metrics · value · ELO')}`
    : pick(lang, '正在读取球队数据…', 'loading teams…')

  const top3 = (top5.length ? top5 : items).slice(0, 3)

  return (
    <PageShell title={pick(lang, '球队分析', 'Teams')} subtitle={subtitle} activePath="/teams">
      <KpiStrip className="mt-6" items={kpis} />

      <div className="anim-in mt-5 flex flex-wrap items-center gap-3" style={{ '--d': '80ms' } as React.CSSProperties}>
        <SearchBox
          value={q}
          onChange={setQ}
          placeholder={pick(lang, '搜索球队名…', 'Search team…')}
          className="w-[240px]"
        />
        <LeagueSelect value={league} onChange={setLeague} options={leagues.data?.items ?? []} />
        <Tabs items={SORTS.map((s) => ({ key: s.key, label: pick(lang, s.zh, s.en) }))} value={sort} onChange={setSort} />
        <span className="t-3 ml-auto text-[11px] font-medium tabular-nums">
          {teams.data ? `${pick(lang, '第', 'page')} ${teams.data.page} / ${pages} ${pick(lang, '页', '')}` : ''}
        </span>
      </div>

      <SectionCard
        className="mt-4"
        title={pick(lang, '球队明细', 'Team table')}
        hint={pick(lang, '按场均数据对比 · 每页 24 支', 'per-match comparison · 24 per page')}
      >
        {teams.loading && !teams.data ? (
          <CardSkeleton rows={9} />
        ) : teams.error ? (
          <ErrorState text={teams.error} />
        ) : !items.length ? (
          <EmptyState text={pick(lang, '没有匹配的球队', 'No teams match')} />
        ) : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[900px] border-collapse">
              <thead>
                <tr className="t-3 text-left text-[10px] font-semibold uppercase tracking-wider">
                  <th className="w-[42px] pb-3 pr-2">#</th>
                  <th className="pb-3 pr-3">{pick(lang, '球队', 'Team')}</th>
                  <th className="pb-3 pr-3">{pick(lang, '联赛', 'League')}</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '场次', 'MP')}</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '场均进球', 'Gls')}</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '场均失球', 'GA')}</th>
                  <th className="pb-3 pr-3 text-right">xG</th>
                  <th className="pb-3 pr-3 text-right">xGA</th>
                  <th className="pb-3 pr-3 text-right">PPG</th>
                  <th className="pb-3 pr-3 text-right">ELO</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '阵容身价', 'Value')}</th>
                  <th className="pb-3 text-right">{pick(lang, '年龄', 'Age')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((t, i) => {
                  const rank = (page - 1) * PAGE_SIZE + i + 1
                  return (
                    <tr
                      key={t.team_id}
                      className="line-c border-t transition-colors duration-200 hover:bg-white/35"
                    >
                      <td className="py-2.5 pr-2">
                        {rank <= 3 ? (
                          <Pill tone="yellow">{rank}</Pill>
                        ) : (
                          <span className="t-3 text-[11px] font-semibold tabular-nums">{rank}</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2.5">
                          <Crest row={t} />
                          <p
                            className="t-1 max-w-[190px] truncate text-[13px] font-semibold"
                            title={pick(lang, t.team, t.name_en)}
                          >
                            {pick(lang, t.team, t.name_en)}
                          </p>
                        </div>
                      </td>
                      <td className="py-2.5 pr-3">
                        <span className="t-2 block max-w-[72px] truncate text-[11.5px] font-medium">
                          {pick(lang, t.league_name, t.league_name_en)}
                        </span>
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-right text-[12px] font-medium tabular-nums">
                        {fmtNum(t.matches)}
                      </td>
                      <td className="py-2.5 pr-3 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className="t-1 text-[12.5px] font-semibold tabular-nums">
                            {fmtNum(t.goals_pg, 2)}
                          </span>
                          <span className="block w-[46px]">
                            <Bar value={t.goals_pg} max={maxGoals} tone="yellow" height={4} />
                          </span>
                        </div>
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">
                        {fmtNum(t.conceded_pg, 2)}
                      </td>
                      <td className="py-2.5 pr-3 text-right">
                        <div className="flex flex-col items-end gap-1">
                          <span className="t-1 text-[12.5px] font-semibold tabular-nums">{fmtNum(t.xg_pg, 2)}</span>
                          <span className="block w-[46px]">
                            <Bar value={t.xg_pg} max={maxXg} tone="blue" height={4} />
                          </span>
                        </div>
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">
                        {fmtNum(t.xga_pg, 2)}
                      </td>
                      <td className="t-1 py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">
                        {fmtNum(t.ppg, 2)}
                      </td>
                      <td className="t-1 py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">
                        {t.elo_rating === null || t.elo_rating === undefined ? '—' : t.elo_rating.toFixed(1)}
                      </td>
                      <td className="t-1 py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">
                        {t.valueText ?? '—'}
                      </td>
                      <td className="t-2 py-2.5 text-right text-[12.5px] font-medium tabular-nums">
                        {fmtNum(t.avg_age, 1)}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {teams.data && items.length ? (
        <Pager page={teams.data.page} pages={pages} total={total} onPage={setPage} unit={pick(lang, '支球队', 'teams')} />
      ) : null}

      {top3.length ? (
        <SectionCard
          dark
          className="mt-5"
          title={pick(lang, '实力榜', 'Strength Board')}
          hint={pick(lang, '按当前排序取全库前 3 · 七维分位（0-100）', 'top 3 of the filtered set · 7 dimensions (0-100)')}
        >
          <div
            className="grid gap-6"
            style={{ gridTemplateColumns: `repeat(${top3.length}, minmax(0, 1fr))` }}
          >
            {top3.map((t) => {
              const radar = t.radar ?? {}
              const vals = RADAR_DIMS.map((d) => Number(radar[d.key] ?? 0))
              const best = Math.max(...vals)
              return (
                <div key={t.team_id} className="flex flex-col">
                  <div className="flex items-center gap-2.5">
                    <Crest row={t} size={30} />
                    <div className="min-w-0">
                      <p className="on-ink truncate text-[13px] font-semibold" title={pick(lang, t.team, t.name_en)}>
                        {pick(lang, t.team, t.name_en)}
                      </p>
                      <p className="text-[10px] font-medium text-[#8B8672]">
                        {pick(lang, t.league_name, t.league_name_en)} · ELO {t.elo_rating?.toFixed(1) ?? '—'} ·{' '}
                        {t.valueText ?? '—'}
                      </p>
                    </div>
                  </div>
                  <div className="mt-3 flex flex-col gap-2">
                    {RADAR_DIMS.map((d) => {
                      const v = Number(radar[d.key] ?? 0)
                      return (
                        <div key={d.key} className="flex items-center gap-2">
                          <span className="w-[42px] shrink-0 text-[10px] font-medium text-[#8B8672]">
                            {pick(lang, d.zh, d.en)}
                          </span>
                          <span className="flex-1">
                            <Bar value={v} max={100} tone={v > 0 && v === best ? 'yellow' : 'blue'} height={5} />
                          </span>
                          <span className="on-ink w-7 text-right text-[10px] font-semibold tabular-nums">
                            {Math.round(v)}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </div>
              )
            })}
          </div>
        </SectionCard>
      ) : null}
    </PageShell>
  )
}
