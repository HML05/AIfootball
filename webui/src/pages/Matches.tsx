import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { ChevronRight } from 'lucide-react'
import { PageShell, SectionCard, Pill, Bar, Pager, SearchBox, Tabs, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import type { MatchRow } from '../lib/api'
import type { Lang } from '../i18n'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { useLang } from '../i18n'
import { fmtNum, pick, splitDateTime } from '../data/live'

/* =====================================================================
 * 赛程与赛果 —— 数据全部来自 GET /api/ui/matches，页面不写死任何比赛数据。
 * 唯一硬编码的是赛季下拉的候选列表：库里 season_code 为 4 位
 * 「起始年两位 + 结束年两位」（2627 = 2026/27），显示时补成 2026/27。
 * ===================================================================== */

const SIZE = 30

/** 赛季候选（真实赛季码 → 展示标签）—— 见文件头注释 */
const SEASONS: { code: string; label: string }[] = [
  { code: '2627', label: '2026/27' },
  { code: '2526', label: '2025/26' },
  { code: '2425', label: '2024/25' },
  { code: '2324', label: '2023/24' },
  { code: '2223', label: '2022/23' },
]

type StatusKey = 'all' | 'FT' | 'NS'
type SortKey = 'date' | 'goals' | 'xg'

/* ---------- 本地小工具（禁止新建共享文件） ---------- */

function Logo({ src, name, size = 22 }: { src?: string | null; name: string; size?: number }) {
  const [bad, setBad] = useState(false)
  if (!src || bad)
    return (
      <span
        className="glass-soft t-2 flex shrink-0 items-center justify-center rounded-full text-[8px] font-bold"
        style={{ width: size, height: size }}
      >
        {name.slice(0, 2)}
      </span>
    )
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

function probPct(v?: number | null): string {
  return typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—'
}

/** 'H' | 'D' | 'A' → 主胜 / 平局 / 客胜 */
function outcomeLabel(lang: Lang, v?: string | null): string {
  if (v === 'H') return pick(lang, '主胜', 'Home')
  if (v === 'D') return pick(lang, '平局', 'Draw')
  if (v === 'A') return pick(lang, '客胜', 'Away')
  return '—'
}

function predTone(v?: string | null): 'yellow' | 'blue' | 'muted' {
  if (v === 'H') return 'yellow'
  if (v === 'A') return 'blue'
  return 'muted'
}

function statusLabel(lang: Lang, s?: string | null): string {
  if (s === 'FT') return pick(lang, '已完赛', 'Finished')
  if (s === 'NS') return pick(lang, '未开赛', 'Not started')
  return s ?? '—'
}

function statusTone(s?: string | null): 'green' | 'yellow' | 'muted' {
  if (s === 'FT') return 'green'
  if (s === 'NS') return 'yellow'
  return 'muted'
}

/** 由比分推出实际赛果 H/D/A —— 后端未下发 actual_result 时自行判定 */
function actualFromScore(homeGoals?: number | null, awayGoals?: number | null): 'H' | 'D' | 'A' | null {
  if (typeof homeGoals !== 'number' || typeof awayGoals !== 'number') return null
  if (homeGoals > awayGoals) return 'H'
  if (homeGoals < awayGoals) return 'A'
  return 'D'
}

/** 无 xG 时显示 — */
function xgText(v?: number | null): string {
  return typeof v === 'number' ? v.toFixed(2) : '—'
}

/* ---------- 单行比赛 ---------- */

function MatchLine({ m, lang, onOpen }: { m: MatchRow; lang: Lang; onOpen: (id: number) => void }) {
  const dt = splitDateTime(m.date)
  const finished = typeof m.home_goals === 'number' && typeof m.away_goals === 'number'
  const hasPred = typeof m.pred_home_win === 'number' && typeof m.pred_away_win === 'number'
  const hasXg = typeof m.home_xg === 'number' && typeof m.away_xg === 'number'
  const actual = actualFromScore(m.home_goals, m.away_goals)
  const evaluated = hasPred && (m.pred_result ?? null) !== null && actual !== null
  const hit = evaluated ? m.pred_result === actual : null
  const sides = [
    { key: 'h', name: m.h, logo: m.h_logo, p: m.pred_home_win, tone: 'yellow' as const, tag: pick(lang, '主胜', 'Home') },
    { key: 'd', name: null, logo: null, p: m.pred_draw, tone: 'muted' as const, tag: pick(lang, '平局', 'Draw') },
    { key: 'a', name: m.a, logo: m.a_logo, p: m.pred_away_win, tone: 'blue' as const, tag: pick(lang, '客胜', 'Away') },
  ]
  const topPred = hasPred
    ? [m.pred_home_win, m.pred_draw, m.pred_away_win].reduce(
        (best, v, i) => ((v ?? -1) > (best.v ?? -1) ? { v, i } : best),
        { v: -1, i: 0 } as { v: number | null | undefined; i: number },
      ).i
    : 0

  return (
    <div
      role="link"
      tabIndex={0}
      onClick={() => onOpen(m.match_id)}
      onKeyDown={(e) => {
        if (e.key === 'Enter' || e.key === ' ') {
          e.preventDefault()
          onOpen(m.match_id)
        }
      }}
      className="glass-soft card-hover anim-in group flex cursor-pointer flex-col gap-3 rounded-[20px] p-3.5 min-[900px]:flex-row min-[900px]:items-center"
    >
      {/* 日期 · 联赛 · 状态 */}
      <div className="flex w-[132px] shrink-0 flex-col gap-1.5">
        <span className="t-2 text-[12px] font-medium tabular-nums">
          {dt.date} <span className="t-3">{dt.time}</span>
        </span>
        <div className="flex items-center gap-1.5">
          <Pill tone="blue">{pick(lang, m.lg, m.lg_en)}</Pill>
          <Pill tone={statusTone(m.status)}>{statusLabel(lang, m.status)}</Pill>
        </div>
      </div>

      {/* 对阵 + 比分/xG */}
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <Logo src={m.h_logo} name={m.h} />
          <span className="t-1 min-w-0 flex-1 truncate text-[13.5px] font-medium" title={m.h}>
            {pick(lang, m.h, m.h_en)}
          </span>
        </div>
        <div className="mt-1.5 flex items-center gap-2">
          <Logo src={m.a_logo} name={m.a} />
          <span className="t-1 min-w-0 flex-1 truncate text-[13.5px] font-medium" title={m.a}>
            {pick(lang, m.a, m.a_en)}
          </span>
        </div>
        <div className="t-3 mt-1.5 text-[10.5px] tabular-nums">
          {hasXg ? `xG ${xgText(m.home_xg)} – ${xgText(m.away_xg)}` : pick(lang, 'xG 暂无', 'xG n/a')}
          {!hasPred ? ` · ${pick(lang, '本场暂无预测', 'no prediction')}` : ''}
        </div>
      </div>

      {/* 比分 / 开赛时间 */}
      <div className="flex w-[74px] shrink-0 flex-col items-center justify-center gap-0.5">
        {finished ? (
          <>
            <span className="t-1 text-[24px] font-semibold leading-none tabular-nums">{m.home_goals}</span>
            <span className="t-1 text-[24px] font-semibold leading-none tabular-nums">{m.away_goals}</span>
          </>
        ) : (
          <>
            <span className="t-3 text-[10px] font-semibold uppercase tracking-wider">
              {pick(lang, '开赛', 'Kick-off')}
            </span>
            <span className="t-1 text-[15px] font-semibold leading-tight tabular-nums">{dt.time}</span>
          </>
        )}
      </div>

      {/* 预测三分类 + 命中 */}
      <div className="w-[228px] shrink-0">
        {hasPred ? (
          <>
            <div className="flex flex-col gap-[5px]">
              {sides.map((s, i) => (
                <div key={s.key} className="flex items-center gap-1.5">
                  <span className={`w-[34px] shrink-0 text-[10px] ${i === topPred ? 't-1 font-semibold' : 't-3'}`}>
                    {s.tag}
                  </span>
                  <span className="min-w-0 flex-1">
                    <Bar value={(s.p ?? 0) * 100} max={100} height={5} tone={i === topPred ? s.tone : 'muted'} />
                  </span>
                  <span
                    className={`w-[42px] shrink-0 text-right text-[10.5px] tabular-nums ${
                      i === topPred ? 't-1 font-semibold' : 't-2'
                    }`}
                  >
                    {probPct(s.p)}
                  </span>
                </div>
              ))}
            </div>
            <div className="mt-1.5 flex items-center gap-2">
              <Pill tone={predTone(m.pred_result)}>
                {pick(lang, '推荐', 'Pick')} {outcomeLabel(lang, m.pred_result)}
              </Pill>
              <span className="t-3 text-[10.5px]">
                {pick(lang, '实际', 'Actual')}{' '}
                <span className="t-2 font-semibold">{outcomeLabel(lang, actual)}</span>
              </span>
              <span className="t-3 text-[10.5px]">
                {pick(lang, '命中', 'Hit')}{' '}
                {hit === null ? (
                  <span className="t-3">—</span>
                ) : hit ? (
                  <span className="font-bold text-[#8a6a10]">✓</span>
                ) : (
                  <span className="text-[#c07b84]">✗</span>
                )}
              </span>
              {m.model_version ? (
                <span className="t-3 truncate text-[10px]" title={m.model_version}>
                  {m.model_version}
                </span>
              ) : null}
            </div>
          </>
        ) : (
          <span className="t-3 block text-[11px]">{pick(lang, '本场暂无预测', 'No prediction for this match')}</span>
        )}
      </div>

      <ChevronRight size={15} className="t-3 hidden shrink-0 transition-transform duration-300 group-hover:translate-x-0.5 min-[900px]:block" />
    </div>
  )
}

/* ---------- 页面 ---------- */

/**
 * 从 URL 读取筛选（可分享/可直接用 /matches?status=FT 访问）。
 * 非法值一律回落到默认，避免手写 URL 把页面搞坏。
 */
function readFilters(sp: URLSearchParams) {
  const rawStatus = (sp.get('status') ?? '').toUpperCase()
  const status: StatusKey = rawStatus === 'FT' || rawStatus === 'NS' ? (rawStatus as StatusKey) : 'all'
  const rawSort = (sp.get('sort') ?? '').toLowerCase()
  const sort: SortKey = rawSort === 'goals' || rawSort === 'xg' ? (rawSort as SortKey) : 'date'
  const seasonRaw = sp.get('season') ?? ''
  const season = SEASONS.some((s) => s.code === seasonRaw) ? seasonRaw : ''
  const leagueRaw = sp.get('league') ?? ''
  const league = /^\d+$/.test(leagueRaw) ? leagueRaw : ''
  const q = sp.get('q') ?? ''
  const pageRaw = Number(sp.get('page') ?? '1')
  const page = Number.isFinite(pageRaw) && pageRaw >= 1 ? Math.floor(pageRaw) : 1
  return { q, league, status, season, sort, page }
}

export default function Matches() {
  const { lang } = useLang()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const initial = useMemo(() => readFilters(searchParams), []) // 只在挂载时读一次
  const [q, setQ] = useState(initial.q)
  const [debouncedQ, setDebouncedQ] = useState(initial.q)
  const [league, setLeague] = useState(initial.league)
  const [status, setStatus] = useState<StatusKey>(initial.status)
  const [season, setSeason] = useState(initial.season)
  const [sort, setSort] = useState<SortKey>(initial.sort)
  const [page, setPage] = useState(initial.page)

  // 输入防抖，避免每敲一个字母都打一次接口
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 320)
    return () => window.clearTimeout(t)
  }, [q])

  // 把筛选写回 URL（空值不写入，保持地址干净）
  useEffect(() => {
    const next = new URLSearchParams()
    if (q.trim()) next.set('q', q.trim())
    if (league) next.set('league', league)
    if (status !== 'all') next.set('status', status)
    if (season) next.set('season', season)
    if (sort !== 'date') next.set('sort', sort)
    if (page > 1) next.set('page', String(page))
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, league, status, season, sort, page])

  const params = useMemo(
    () => ({ page, size: SIZE, q: debouncedQ, league, season, status: status === 'all' ? '' : status, sort, dir: 'desc' }),
    [page, debouncedQ, league, season, status, sort],
  )
  const key = `matches:${page}:${SIZE}:${debouncedQ}:${league}:${season}:${status}:${sort}`
  const { data, loading, error } = useApi((signal) => api.matches(params, signal), key)

  // URL 里带来的页码可能超出筛选后的总页数（例如 ?status=FT&page=400）→ 拉回最后一页
  const pages = data?.pages ?? 1
  useEffect(() => {
    if (data && data.total > 0 && page > pages) setPage(pages)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, pages, page])

  const leagues = useApi(api.leagues, 'leagues')
  const items = data?.items ?? []
  const stats = data?.stats
  const ft = stats?.ft ?? 0
  const share = (v?: number | null) => (ft > 0 && typeof v === 'number' ? `${((v / ft) * 100).toFixed(1)}%` : '—')
  const scope = pick(
    lang,
    `${status === 'all' ? '全部状态' : status === 'FT' ? '已完赛' : '未开赛'} · 当前筛选范围内`,
    `${status === 'all' ? 'all statuses' : status === 'FT' ? 'finished only' : 'not started only'} · within the current filter`,
  )

  const resetPage = () => setPage(1)

  const kpis = [
    {
      label: pick(lang, '已完赛', 'Finished'),
      value: typeof stats?.ft === 'number' ? fmtNum(stats.ft) : '—',
      sub: pick(lang, '当前筛选范围内', 'Within current filter'),
    },
    {
      label: pick(lang, '主胜 / 平 / 客胜', 'Home / Draw / Away'),
      value: `${share(stats?.hw)} · ${share(stats?.dr)} · ${share(stats?.aw)}`,
      sub: pick(lang, '占已完赛场次比例', 'Share of finished matches'),
    },
    {
      label: pick(lang, '场均进球', 'Goals per match'),
      value: typeof stats?.goals_pg === 'number' ? stats.goals_pg.toFixed(2) : '—',
      sub: pick(lang, '已完赛口径', 'Finished matches only'),
    },
    {
      label: pick(lang, '样本场次', 'Sample size'),
      value: fmtNum(stats?.n ?? 0),
      sub: pick(lang, '用于上述口径', 'Rows behind the figures above'),
    },
  ]

  return (
    <PageShell
      title={pick(lang, '赛程与赛果', 'Fixtures & Results')}
      subtitle={pick(
        lang,
        '按日期 / 联赛 / 状态 / 赛季检索，含比分、xG 与模型预测命中情况',
        'Filter by date, league, status and season — scores, xG and prediction hits',
      )}
      activePath="/matches"
      right={<Pill tone="ink">{fmtNum(data?.total ?? 0)}</Pill>}
    >
      {loading && !data ? <CardSkeleton rows={4} /> : null}
      {error && !data ? <ErrorState text={error} /> : null}

      {data ? (
        <>
          {/* KPI —— 口径随筛选变化（后端 stats 只统计 status='FT'） */}
          <div className="grid grid-cols-2 gap-4 min-[760px]:grid-cols-4">
            {kpis.map((k) => (
              <div key={k.label} className="glass card-hover anim-in rounded-[24px] px-5 py-4">
                <p className="t-3 text-[10.5px] font-semibold uppercase tracking-wide">{k.label}</p>
                <p className="t-1 mt-1.5 truncate text-[22px] font-medium leading-none tabular-nums" title={k.value}>
                  {k.value}
                </p>
                {k.sub ? <p className="t-3 mt-1.5 text-[10.5px] font-medium">{k.sub}</p> : null}
              </div>
            ))}
          </div>

          <SectionCard
            className="mt-4"
            title={pick(lang, '比赛列表', 'Match list')}
            hint={scope}
            right={<Pill tone="yellow">{fmtNum(items.length)}</Pill>}
          >
            {/* 筛选区 */}
            <div className="flex flex-wrap items-center gap-2">
              <SearchBox
                value={q}
                onChange={(v) => {
                  setQ(v)
                  resetPage()
                }}
                placeholder={pick(lang, '搜索球队名…', 'Search team…')}
                className="w-[220px]"
              />
              <select
                value={league}
                onChange={(e) => {
                  setLeague(e.target.value)
                  resetPage()
                }}
                className="glass-soft t-1 rounded-full px-3 py-2 text-[11.5px] font-medium outline-none"
              >
                <option value="">{pick(lang, '全部联赛', 'All leagues')}</option>
                {(leagues.data?.items ?? []).map((l) => (
                  <option key={l.id} value={l.id}>
                    {pick(lang, l.name, l.nameEn)}
                  </option>
                ))}
              </select>
              <select
                value={season}
                onChange={(e) => {
                  setSeason(e.target.value)
                  resetPage()
                }}
                className="glass-soft t-1 rounded-full px-3 py-2 text-[11.5px] font-medium outline-none"
              >
                <option value="">{pick(lang, '全部赛季', 'All seasons')}</option>
                {SEASONS.map((s) => (
                  <option key={s.code} value={s.code}>
                    {s.label}
                  </option>
                ))}
              </select>
              <select
                value={sort}
                onChange={(e) => {
                  setSort(e.target.value as SortKey)
                  resetPage()
                }}
                className="glass-soft t-1 rounded-full px-3 py-2 text-[11.5px] font-medium outline-none"
              >
                <option value="date">{pick(lang, '按日期', 'By date')}</option>
                <option value="goals">{pick(lang, '按总进球', 'By total goals')}</option>
                <option value="xg">{pick(lang, '按总 xG', 'By total xG')}</option>
              </select>
              <span className="t-3 text-[11px]">{pick(lang, '降序排列', 'Descending')}</span>
            </div>

            <div className="mt-2.5 flex flex-wrap items-center gap-2">
              <Tabs
                items={[
                  { key: 'all', label: pick(lang, '全部', 'All') },
                  { key: 'FT', label: pick(lang, '已完赛', 'Finished') },
                  { key: 'NS', label: pick(lang, '未开赛', 'Not started') },
                ]}
                value={status}
                onChange={(k) => {
                  setStatus(k as StatusKey)
                  resetPage()
                }}
              />
              <span className="t-3 ml-auto text-[11px] tabular-nums">
                {pick(lang, `第 ${data.page} / ${Math.max(1, data.pages)} 页`, `Page ${data.page} / ${Math.max(1, data.pages)}`)}
              </span>
            </div>

            {/* 列表 */}
            <div className="mt-3 flex flex-col gap-2.5">
              {items.map((m) => (
                <MatchLine key={m.match_id} m={m} lang={lang} onOpen={(id) => navigate(`/matches/${id}`)} />
              ))}
              {items.length === 0 && !loading ? (
                <EmptyState
                  text={pick(lang, '当前筛选下没有比赛', 'No matches for the current filter')}
                />
              ) : null}
            </div>

            {data.total > 0 ? (
              <Pager
                page={data.page}
                pages={data.pages}
                total={data.total}
                onPage={setPage}
                unit={pick(lang, '场比赛', 'matches')}
              />
            ) : null}
          </SectionCard>
        </>
      ) : null}
    </PageShell>
  )
}
