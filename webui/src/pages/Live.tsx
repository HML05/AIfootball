import { useState } from 'react'
import { RefreshCw } from 'lucide-react'
import { PageShell, SectionCard, Pill, Bar, Tabs, KpiStrip, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import type { MatchRow, UpcomingRow } from '../lib/api'
import type { Lang } from '../i18n'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { useLang } from '../i18n'
import { pick, splitDateTime } from '../data/live'

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

function TeamRow({ side, name, logo }: { side: 'h' | 'a'; name: string; logo?: string | null }) {
  return (
    <div className="flex items-center gap-2">
      <Logo src={logo} name={name} />
      <span className="t-1 min-w-0 flex-1 truncate text-[13.5px] font-medium">{name}</span>
      <span className="t-3 text-[9.5px] font-semibold uppercase">{side === 'h' ? 'H' : 'A'}</span>
    </div>
  )
}

function num(v?: number | null): string {
  return typeof v === 'number' ? v.toFixed(1) : '—'
}

function prob(v?: number | null): string {
  return typeof v === 'number' ? `${(v * 100).toFixed(1)}%` : '—'
}

function resultLabel(lang: 'zh' | 'en', v?: string | null): string {
  if (v === 'H') return pick(lang, '主胜', 'Home')
  if (v === 'D') return pick(lang, '平局', 'Draw')
  if (v === 'A') return pick(lang, '客胜', 'Away')
  return '—'
}

/* ---------- 最近完赛 ---------- */

function RecentCard({ rows, lastDay, lang }: { rows: MatchRow[]; lastDay?: string; lang: Lang }) {
  return (
    <SectionCard
      title={pick(lang, '最近完赛', 'Recently finished')}
      hint={pick(lang, `最近比赛日 ${lastDay ?? '—'} · 含最终比分`, `Matchday ${lastDay ?? '—'} · final scores`)}
      right={<Pill tone="green">{rows.length}</Pill>}
    >
      <div className="flex flex-col gap-2.5">
        {rows.map((m) => {
          const dt = splitDateTime(m.date)
          const hasXg = typeof m.home_xg === 'number' && typeof m.away_xg === 'number'
          return (
            <div key={m.match_id} className="glass-soft anim-in rounded-[20px] p-3.5">
              <div className="mb-2 flex items-center gap-2">
                <Pill tone="blue">{m.lg ?? '—'}</Pill>
                <span className="t-3 text-[10.5px] tabular-nums">
                  {dt.date} {dt.time}
                </span>
                {m.status ? <span className="t-3 text-[10px] font-semibold">{m.status}</span> : null}
              </div>
              <div className="flex items-center gap-3">
                <div className="flex min-w-0 flex-1 flex-col gap-1.5">
                  <TeamRow side="h" name={m.h} logo={m.h_logo} />
                  <TeamRow side="a" name={m.a} logo={m.a_logo} />
                </div>
                <div className="flex shrink-0 flex-col items-end gap-1.5">
                  <span className="t-1 text-[22px] font-semibold leading-none tabular-nums">{m.home_goals ?? '—'}</span>
                  <span className="t-1 text-[22px] font-semibold leading-none tabular-nums">{m.away_goals ?? '—'}</span>
                </div>
              </div>
              {hasXg ? (
                <div className="t-3 mt-2 text-[10.5px] tabular-nums">
                  xG {num(m.home_xg)} – {num(m.away_xg)}
                </div>
              ) : null}
            </div>
          )
        })}
        {rows.length === 0 ? <EmptyState text={pick(lang, '暂无完赛记录', 'No finished matches')} /> : null}
      </div>
    </SectionCard>
  )
}

/* ---------- 即将开始 ---------- */

function UpcomingCard({ rows, lang }: { rows: UpcomingRow[]; lang: 'zh' | 'en' }) {
  return (
    <SectionCard
      title={pick(lang, '即将开始', 'Upcoming')}
      hint={pick(lang, '按开赛时间升序 · 有预测则显示三分类概率', 'Sorted by kick-off · probabilities when a prediction exists')}
      right={<Pill tone="yellow">{rows.length}</Pill>}
    >
      <div className="flex flex-col gap-2.5">
        {rows.map((u) => {
          const dt = splitDateTime(u.date)
          const has = typeof u.pred_home_win === 'number' && typeof u.pred_away_win === 'number'
          return (
            <div key={u.match_id} className="glass-soft anim-in rounded-[20px] p-3.5">
              <div className="mb-2 flex items-center gap-2">
                <Pill tone="blue">{u.lg ?? '—'}</Pill>
                <span className="t-3 text-[10.5px] tabular-nums">
                  {dt.date} {dt.time}
                </span>
              </div>
              <div className="flex items-center gap-2">
                <Logo src={u.h_logo} name={u.h} />
                <span className="t-1 w-[128px] shrink-0 truncate text-[13px] font-medium" title={u.h}>
                  {u.h}
                </span>
                <span className="t-3 shrink-0 text-[10px]">vs</span>
                <Logo src={u.a_logo} name={u.a} />
                <span className="t-1 min-w-0 flex-1 truncate text-[13px] font-medium" title={u.a}>
                  {u.a}
                </span>
              </div>
              {has ? (
                <div className="mt-2.5 flex items-center gap-2.5">
                  <div className="flex min-w-0 flex-1 items-center gap-2">
                    <span className="t-3 w-[30px] shrink-0 text-[10px]">{pick(lang, '主胜', 'Home')}</span>
                    <span className="min-w-0 flex-1">
                      <Bar value={(u.pred_home_win ?? 0) * 100} max={100} height={6} tone="yellow" />
                    </span>
                    <span className="t-2 w-[38px] shrink-0 text-right text-[10.5px] tabular-nums">{prob(u.pred_home_win)}</span>
                    <span className="t-3 w-[30px] shrink-0 text-[10px]">{pick(lang, '平局', 'Draw')}</span>
                    <span className="min-w-0 flex-1">
                      <Bar value={(u.pred_draw ?? 0) * 100} max={100} height={6} tone="muted" />
                    </span>
                    <span className="t-2 w-[38px] shrink-0 text-right text-[10.5px] tabular-nums">{prob(u.pred_draw)}</span>
                    <span className="t-3 w-[30px] shrink-0 text-[10px]">{pick(lang, '客胜', 'Away')}</span>
                    <span className="min-w-0 flex-1">
                      <Bar value={(u.pred_away_win ?? 0) * 100} max={100} height={6} tone="blue" />
                    </span>
                    <span className="t-2 w-[38px] shrink-0 text-right text-[10.5px] tabular-nums">{prob(u.pred_away_win)}</span>
                  </div>
                  <Pill tone={u.pred_result === 'H' ? 'yellow' : u.pred_result === 'D' ? 'muted' : 'blue'}>
                    {resultLabel(lang, u.pred_result)}
                  </Pill>
                </div>
              ) : (
                <div className="t-3 mt-2 text-[11px]">{pick(lang, '暂无预测', 'No prediction yet')}</div>
              )}
            </div>
          )
        })}
        {rows.length === 0 ? <EmptyState text={pick(lang, '暂无待赛比赛', 'No upcoming matches')} /> : null}
      </div>
    </SectionCard>
  )
}

/* ---------- 数据通道 ---------- */

function ChannelCard({
  source,
  endpoint,
  generatedAt,
  onRefresh,
  busy,
  lang,
}: {
  source: string
  endpoint: string
  generatedAt: string
  onRefresh: () => void
  busy: boolean
  lang: Lang
}) {
  return (
    <SectionCard
      title={pick(lang, '数据通道', 'Data channel')}
      hint={pick(lang, '接口与增量写入状态', 'Endpoint and incremental-write status')}
      right={
        <button
          onClick={onRefresh}
          className="glass-soft t-1 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
        >
          <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
          {pick(lang, '刷新', 'Refresh')}
        </button>
      }
    >
      <div className="flex flex-col gap-2.5">
        <div className="glass-soft flex items-center justify-between gap-3 rounded-[18px] px-3.5 py-2.5">
          <span className="t-3 text-[11px]">{pick(lang, '实时通道', 'Realtime channel')}</span>
          <span className="t-1 text-[12px] font-semibold tabular-nums">{endpoint}</span>
        </div>
        <div className="glass-soft flex items-center justify-between gap-3 rounded-[18px] px-3.5 py-2.5">
          <span className="t-3 text-[11px]">{pick(lang, '数据源', 'Source')}</span>
          <span className="t-1 text-[12px] font-semibold">{source}</span>
        </div>
        <div className="glass-soft flex items-center justify-between gap-3 rounded-[18px] px-3.5 py-2.5">
          <span className="t-3 text-[11px]">{pick(lang, '数据截至', 'Data as of')}</span>
          <span className="t-1 text-[12px] font-semibold tabular-nums">{generatedAt || '—'}</span>
        </div>
      </div>
      <p className="t-3 mt-3 text-[11px] leading-[1.7]">
        {pick(
          lang,
          '比分与赛程按比赛日轮询入库，页面每次进入或点击刷新都会重新读取一次最新快照；通道地址即上方 WebSocket 端点，仅在对局进行中推送增量事件。',
          'Scores and fixtures are ingested per matchday; the page re-reads the latest snapshot on entry or on refresh. The channel address above is the WebSocket endpoint used for in-play incremental events.',
        )}
      </p>
    </SectionCard>
  )
}

/* ---------- 页面 ---------- */

type RecentFilter = 'all' | 'score' | 'today'

export default function Live() {
  const { lang } = useLang()
  const [filter, setFilter] = useState<RecentFilter>('all')
  const { data, loading, error, reload } = useApi(api.live, 'live', 30_000)
  const [busy, setBusy] = useState(false)

  const recent = data?.recent ?? []
  const upcoming = data?.upcoming ?? []
  const scored = recent.filter((m) => typeof m.home_goals === 'number' && typeof m.away_goals === 'number')
  const today = recent.filter((m) => (data?.lastDay ? m.date.startsWith(data.lastDay) : false))
  const visible = filter === 'score' ? scored : filter === 'today' ? today : recent
  const nextKickoff = upcoming[0]?.date ?? null

  const refresh = () => {
    setBusy(true)
    reload()
    window.setTimeout(() => setBusy(false), 900)
  }

  return (
    <PageShell
      title={pick(lang, '实时比分', 'Live Scores')}
      subtitle={pick(
        lang,
        '最近完赛结果与即将开始的赛程 · 数据来自 football-data.org',
        'Latest results and upcoming fixtures · sourced from football-data.org',
      )}
      activePath="/live"
      right={<Pill tone="ink">{data?.source ?? '—'}</Pill>}
    >
      {loading && !data ? <CardSkeleton rows={4} /> : null}
      {error && !data ? <ErrorState text={error} /> : null}

      {data ? (
        <>
          <KpiStrip
            items={[
              { label: pick(lang, '最近比赛日', 'Matchday'), value: data.lastDay ?? '—' },
              {
                label: pick(lang, '当日场次', 'Matches that day'),
                value: String(data.lastDayCount ?? '—'),
                sub: pick(lang, '已入库结果', 'Results stored'),
              },
              { label: pick(lang, '近 12 场', 'Recent results'), value: String(recent.length) },
              {
                label: pick(lang, '即将开始', 'Upcoming'),
                value: String(upcoming.length),
                sub: nextKickoff ? pick(lang, `最近 ${nextKickoff}`, `next ${nextKickoff}`) : undefined,
              },
            ]}
          />

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
            <div className="flex flex-col gap-3">
              <div className="flex flex-wrap items-center gap-2">
                <div className="min-w-0 max-w-[340px] overflow-x-auto">
                  <Tabs
                    items={[
                      { key: 'all', label: pick(lang, '全部', 'All') },
                      { key: 'score', label: pick(lang, '有比分', 'With score') },
                      { key: 'today', label: pick(lang, `${data.lastDay} 当天`, `On ${data.lastDay}`) },
                    ]}
                    value={filter}
                    onChange={(k) => setFilter(k as RecentFilter)}
                  />
                </div>
                <span className="t-3 text-[11px] tabular-nums">
                  {pick(lang, `显示 ${visible.length} / ${recent.length} 场`, `Showing ${visible.length} / ${recent.length}`)}
                </span>
              </div>
              <RecentCard rows={visible} lastDay={data.lastDay} lang={lang} />
            </div>

            <div className="flex flex-col gap-4">
              <UpcomingCard rows={upcoming} lang={lang} />
              <ChannelCard
                source={data.source}
                endpoint={data.wsEndpoint}
                generatedAt={data.generatedAt}
                onRefresh={refresh}
                busy={busy}
                lang={lang}
              />
            </div>
          </div>
        </>
      ) : null}
    </PageShell>
  )
}
