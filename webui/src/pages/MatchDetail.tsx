import { useMemo, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import { ArrowLeft, ChevronRight } from 'lucide-react'
import { PageShell, SectionCard, Pill, Bar, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import type { FormRow, MatchDetailPayload, MatchDetailSide, StandingRow } from '../lib/api'
import type { Lang } from '../i18n'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { useLang } from '../i18n'
import { fmtNum, pick, shortTeam, splitDateTime } from '../data/live'

/* =====================================================================
 * 比赛详情 —— 数据全部来自 GET /api/ui/matches/{id}，不写死任何比赛数据。
 * 未开赛场次后端不下发 score / xg / stats，对应区块整体不渲染。
 * ===================================================================== */

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

function num(v?: number | null, digits = 2): string {
  return typeof v === 'number' ? v.toFixed(digits) : '—'
}

function probPct(v?: number | null): string {
  return typeof v === 'number' ? `${v.toFixed(1)}%` : '—'
}

function resultLetter(lang: Lang, v?: string | null): string {
  if (v === 'H') return pick(lang, '主胜', 'Home')
  if (v === 'D') return pick(lang, '平局', 'Draw')
  if (v === 'A') return pick(lang, '客胜', 'Away')
  return '—'
}

function resultTone(v?: string | null): 'yellow' | 'blue' | 'muted' {
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

/** 从积分榜近况字符串取最近 5 场 */
function formChips(v?: string | null): string[] {
  return (v ?? '').toUpperCase().replace(/[^WDL]/g, '').slice(-5).split('')
}

function wdlTone(v: string): 'green' | 'yellow' | 'blue' {
  if (v === 'W') return 'green'
  if (v === 'D') return 'yellow'
  return 'blue'
}

/* ---------- 记分板 ---------- */

function TeamPanel({
  side,
  lang,
  align,
}: {
  side: MatchDetailSide
  lang: Lang
  align: 'left' | 'right'
}) {
  const row = align === 'left' ? '' : 'flex-row-reverse'
  const text = align === 'left' ? 'text-left' : 'text-right'
  return (
    <Link to={`/teams/${side.id}`} className="group min-w-0 flex-1">
      <div className={`flex items-center gap-3 ${row}`}>
        <Logo src={side.logo} name={side.name} size={46} />
        <div className={`min-w-0 ${text}`}>
          <div
            className="t-1 truncate text-[16px] font-semibold group-hover:underline min-[760px]:text-[19px]"
            title={pick(lang, side.name, side.nameEn)}
          >
            {pick(lang, side.name, side.nameEn)}
          </div>
          <div className={`mt-1 flex flex-wrap items-center gap-1.5 ${align === 'left' ? '' : 'justify-end'}`}>
            {typeof side.elo === 'number' ? (
              <Pill tone="ink">ELO {Math.round(side.elo)}</Pill>
            ) : (
              <Pill tone="muted">ELO —</Pill>
            )}
            {side.standing ? (
              <Pill tone="muted">
                {pick(lang, `第 ${side.standing.rank} 名`, `#${side.standing.rank}`)}
              </Pill>
            ) : null}
          </div>
        </div>
      </div>
      {side.stadium ? (
        <div className={`t-3 mt-2 truncate text-[10.5px] ${text}`} title={side.stadium}>
          {side.stadium}
        </div>
      ) : null}
    </Link>
  )
}

/* ---------- 预测卡 ---------- */

function PredictionCard({
  prediction,
  lang,
  status,
  score,
  kickoff,
}: {
  prediction: MatchDetailPayload['prediction']
  lang: Lang
  status: string
  score: { home: number | null; away: number | null }
  kickoff: string
}) {
  if (!prediction) {
    return (
      <SectionCard
        title={pick(lang, '模型预测', 'Model prediction')}
        hint={pick(lang, '三分类胜平负概率', 'Three-way win/draw/away')}
      >
        <div className="t-3 flex flex-col gap-2 py-6 text-[12px]">
          <span className="glass-soft t-2 flex h-10 w-10 items-center justify-center self-center rounded-full text-[16px]">
            —
          </span>
          <span className="text-center">{pick(lang, '本场暂无预测', 'No prediction for this match')}</span>
        </div>
      </SectionCard>
    )
  }

  const segments = prediction.segments ?? []
  const top = segments.reduce(
    (best, s) => (s.pct > (best?.pct ?? -1) ? s : best),
    segments[0] ?? null,
  )
  const actual =
    status === 'FT' && typeof score.home === 'number' && typeof score.away === 'number'
      ? score.home > score.away
        ? 'H'
        : score.home < score.away
          ? 'A'
          : 'D'
      : null
  const hit = prediction.hit === null || prediction.hit === undefined
    ? actual && prediction.pick
      ? prediction.pick === actual
        ? 1
        : 0
      : null
    : prediction.hit

  return (
    <SectionCard
      title={pick(lang, '模型预测', 'Model prediction')}
      hint={pick(lang, '三分类胜平负概率 · 推荐与命中', 'Three-way probabilities · pick and hit')}
      right={<Pill tone="yellow">{pick(lang, '主胜最高', 'Top pick')}</Pill>}
    >
      <div className="flex flex-col gap-2">
        {segments.map((s) => (
          <div key={s.key} className="flex items-center gap-2">
            <span className={`w-[42px] shrink-0 text-[11px] ${s.key === top?.key ? 't-1 font-semibold' : 't-3'}`}>
              {pick(lang, s.label, s.labelEn)}
            </span>
            <span className="min-w-0 flex-1">
              <Bar
                value={s.pct}
                max={100}
                height={8}
                tone={s.key === 'home' ? 'yellow' : s.key === 'away' ? 'blue' : 'muted'}
              />
            </span>
            <span
              className={`w-[52px] shrink-0 text-right text-[12px] tabular-nums ${
                s.key === top?.key ? 't-1 font-semibold' : 't-2'
              }`}
            >
              {probPct(s.pct)}
            </span>
          </div>
        ))}
        {segments.length === 0 ? <EmptyState text={pick(lang, '预测概率缺失', 'Probabilities missing')} /> : null}
      </div>

      <div className="mt-3 grid grid-cols-2 gap-2 min-[520px]:grid-cols-3">
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">
            {pick(lang, '推荐 · 概率', 'Pick · prob.')}
          </div>
          <div className="mt-1 flex items-center gap-1.5">
            <Pill tone={resultTone(prediction.pick)}>{pick(lang, prediction.pickLabel, prediction.pickLabelEn)}</Pill>
            <span className="t-2 text-[11px] tabular-nums">{probPct(prediction.conf)}</span>
          </div>
        </div>
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">{pick(lang, '实际 / 命中', 'Actual / hit')}</div>
          <div className="mt-1 flex items-center gap-1.5">
            <span className="t-2 text-[11.5px] font-medium">{resultLetter(lang, actual)}</span>
            {hit === null ? (
              <span className="t-3 text-[11.5px]">—</span>
            ) : hit === 1 ? (
              <span className="text-[13px] font-bold text-[#8a6a10]">✓</span>
            ) : (
              <span className="text-[13px] text-[#c07b84]">✗</span>
            )}
          </div>
        </div>
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">{pick(lang, '模型版本', 'Model')}</div>
          <div className="t-2 mt-1 truncate text-[11.5px] font-medium" title={prediction.model}>
            {prediction.model}
          </div>
        </div>
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">{pick(lang, '生成时间', 'Created')}</div>
          <div className="t-2 mt-1 text-[11.5px] font-medium tabular-nums">{prediction.createdAt ?? '—'}</div>
        </div>
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">{pick(lang, '来源', 'Source')}</div>
          <div className="t-2 mt-1 text-[11.5px] font-medium">
            {prediction.isBacktest ? pick(lang, '回测', 'Backtest') : pick(lang, '实时预测', 'Live')}
          </div>
        </div>
        <div className="glass-soft rounded-[18px] px-3 py-2.5">
          <div className="t-3 text-[10px] font-semibold uppercase tracking-wide">{pick(lang, '开赛', 'Kick-off')}</div>
          <div className="t-2 mt-1 text-[11.5px] font-medium tabular-nums">{kickoff}</div>
        </div>
      </div>
      {prediction.isBacktest ? (
        <p className="t-3 mt-2.5 text-[10.5px]">
          {pick(
            lang,
            '该条预测为回测产出，仅用于评估，不代表赛前发布。',
            'This prediction comes from a backtest run and is used for evaluation only.',
          )}
        </p>
      ) : null}
    </SectionCard>
  )
}

/* ---------- 数据对比 ---------- */

function CompareRow({
  label,
  home,
  away,
  decimals = 0,
  highlight,
}: {
  label: string
  home: number
  away: number
  decimals?: number
  highlight?: boolean
}) {
  const total = home + away
  const hp = total > 0 ? (home / total) * 100 : 50
  const ap = total > 0 ? (away / total) * 100 : 50
  const win = home === away ? 'none' : home > away ? 'home' : 'away'
  return (
    <div className="flex items-center gap-2.5 py-1.5">
      <span className={`w-[56px] shrink-0 text-right text-[13px] tabular-nums ${win === 'home' ? 't-1 font-semibold' : 't-2'}`}>
        {home.toFixed(decimals)}
      </span>
      <span className="flex h-[22px] min-w-0 flex-1 items-center justify-end overflow-hidden rounded-l-[9px] bg-[var(--track)]">
        <span
          className="block h-full rounded-l-[9px] transition-[width] duration-700 ease-out"
          style={{ width: `${hp}%`, background: highlight ? '#F6C945' : 'rgba(43,43,39,.32)' }}
        />
      </span>
      <span className="t-3 w-[112px] shrink-0 text-center text-[10.5px] font-semibold">{label}</span>
      <span className="flex h-[22px] min-w-0 flex-1 items-center overflow-hidden rounded-r-[9px] bg-[var(--track)]">
        <span
          className="block h-full rounded-r-[9px] transition-[width] duration-700 ease-out"
          style={{ width: `${ap}%`, background: highlight ? '#F6C945' : 'rgba(168,197,226,.85)' }}
        />
      </span>
      <span className={`w-[56px] shrink-0 text-[13px] tabular-nums ${win === 'away' ? 't-1 font-semibold' : 't-2'}`}>
        {away.toFixed(decimals)}
      </span>
    </div>
  )
}

/* ---------- 双方档案 ---------- */

function StandingLine({ standing, lang }: { standing: StandingRow; lang: Lang }) {
  return (
    <div className="glass-soft rounded-[18px] px-3 py-2.5">
      <div className="flex items-center gap-2">
        <Pill tone="yellow">
          {pick(lang, `第 ${standing.rank} 名`, `#${standing.rank}`)}
        </Pill>
        <span className="t-2 text-[11.5px] font-semibold tabular-nums">
          {fmtNum(standing.points)} {pick(lang, '分', 'pts')}
        </span>
        <span className="t-3 ml-auto text-[10.5px] tabular-nums">
          {pick(lang, `${standing.played} 场`, `${standing.played} played`)}
        </span>
      </div>
      <div className="t-2 mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] tabular-nums">
        <span>
          {standing.won}
          <span className="t-3"> {pick(lang, '胜', 'W')}</span>
        </span>
        <span>
          {standing.draw}
          <span className="t-3"> {pick(lang, '平', 'D')}</span>
        </span>
        <span>
          {standing.lost}
          <span className="t-3"> {pick(lang, '负', 'L')}</span>
        </span>
        <span className="t-2">
          {standing.goals_for}
          <span className="t-3">:</span>
          {standing.goals_against}
        </span>
        <span className={standing.goal_diff >= 0 ? 't-2' : 'text-[#c07b84]'}>
          {standing.goal_diff > 0 ? '+' : ''}
          {standing.goal_diff}
        </span>
      </div>
      {formChips(standing.form).length > 0 ? (
        <div className="mt-2 flex items-center gap-1">
          <span className="t-3 mr-1 text-[10px]">{pick(lang, '近况', 'Form')}</span>
          {formChips(standing.form).map((c, i) => (
            <Pill key={`${c}-${i}`} tone={wdlTone(c)}>
              {c}
            </Pill>
          ))}
        </div>
      ) : null}
    </div>
  )
}

function FormList({
  rows,
  lang,
  currentId,
}: {
  rows: FormRow[]
  lang: Lang
  currentId?: number
}) {
  if (rows.length === 0) return <EmptyState text={pick(lang, '暂无近期比赛', 'No recent matches')} />
  return (
    <div className="flex flex-col gap-1.5">
      {rows.map((r) => {
        const dt = splitDateTime(r.date)
        const oppIsHome = !r.isHome
        const opp = oppIsHome ? r.h : r.a
        const oppEn = oppIsHome ? r.h_en : r.a_en
        const oppLogo = oppIsHome ? r.h_logo : r.a_logo
        const isCurrent = currentId !== undefined && r.match_id === currentId
        return (
          <div
            key={r.match_id}
            className={`flex items-center gap-2 rounded-[14px] px-2.5 py-2 ${isCurrent ? 'glass-soft' : ''}`}
          >
            <Pill tone={wdlTone(r.result)}>{r.result}</Pill>
            <span className="t-3 w-[38px] shrink-0 text-[10px] tabular-nums">{dt.date}</span>
            <span className="t-1 min-w-0 flex-1 truncate text-[12px]" title={pick(lang, opp, oppEn)}>
              {pick(lang, opp, oppEn)}
            </span>
            <Logo src={oppLogo} name={opp} size={18} />
            <span className="t-3 shrink-0 text-[10px]">{r.isHome ? pick(lang, '主', 'H') : pick(lang, '客', 'A')}</span>
            <span className="t-1 w-[54px] shrink-0 text-right text-[12px] font-semibold tabular-nums">
              {r.gf ?? '—'} : {r.ga ?? '—'}
            </span>
            {isCurrent ? (
              <span className="t-3 shrink-0 text-[9.5px]">{pick(lang, '本场', 'this')}</span>
            ) : null}
          </div>
        )
      })}
      <span className="t-3 px-2.5 text-[10px]">
        {pick(
          lang,
          '双方视角的最近比赛；含本场（如已入库，行尾标注「本场」）。',
          'Most recent matches from each side’s view; the current match is marked when present.',
        )}
      </span>
    </div>
  )
}

/* ---------- 页面 ---------- */

export default function MatchDetail() {
  const { lang } = useLang()
  const { id } = useParams()
  const navigate = useNavigate()
  const matchId = Number(id)
  const valid = Number.isFinite(matchId) && matchId > 0

  const { data, loading, error } = useApi(
    (signal) => api.matchDetail(matchId, signal),
    `match:${matchId}`,
  )
  const leagues = useApi(api.leagues, 'leagues')

  const compareRows = useMemo(() => {
    if (!data) return []
    const rows = (data.stats ?? []).filter(
      (s) => typeof s.home === 'number' && typeof s.away === 'number',
    )
    return rows.map((s) => ({
      label: pick(lang, s.label, s.labelEn),
      home: s.home as number,
      away: s.away as number,
      decimals: 0,
      highlight: false,
    }))
  }, [data, lang])

  const hasXg = typeof data?.xg.home === 'number' && typeof data?.xg.away === 'number'
  const leagueName = data ? pick(lang, data.league.name, data.league.nameEn) : ''
  const leagueCard = (leagues.data?.items ?? []).find((l) => l.id === data?.league.id)
  const leagueLogoHint = leagueCard?.country ? pick(lang, leagueCard.country, leagueCard.countryEn) : null

  const kickoff = data ? `${splitDateTime(data.date).date} ${splitDateTime(data.date).time}` : '—'
  const finished =
    !!data && typeof data.score.home === 'number' && typeof data.score.away === 'number'

  if (!valid) {
    return (
      <PageShell title={pick(lang, '比赛详情', 'Match Detail')} activePath="/matches">
        <ErrorState text={pick(lang, '比赛 ID 无效', 'Invalid match id')} />
      </PageShell>
    )
  }

  return (
    <PageShell
      title={data ? `${pick(lang, data.home.name, data.home.nameEn)} vs ${pick(lang, data.away.name, data.away.nameEn)}` : pick(lang, '比赛详情', 'Match Detail')}
      subtitle={pick(
        lang,
        '记分板 · 模型预测 · 数据对比 · 双方档案 · 历史交锋',
        'Scoreboard · model prediction · statistics · team profiles · head-to-head',
      )}
      activePath="/matches"
      right={
        <button
          onClick={() => navigate('/matches')}
          className="glass-soft t-1 flex items-center gap-1.5 rounded-full px-3 py-1.5 text-[11.5px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
        >
          <ArrowLeft size={13} />
          {pick(lang, '返回赛程', 'Back to fixtures')}
        </button>
      }
    >
      {loading && !data ? <CardSkeleton rows={4} /> : null}
      {error && !data ? <ErrorState text={error} /> : null}

      {data ? (
        <>
          {/* 比赛标识行 */}
          <div className="mb-4 flex flex-wrap items-center gap-2">
            <Pill tone="blue">{leagueName}</Pill>
            <Pill tone="muted">{data.season}</Pill>
            {typeof data.matchday === 'number' ? (
              <Pill tone="muted">{pick(lang, `第 ${data.matchday} 轮`, `Matchday ${data.matchday}`)}</Pill>
            ) : null}
            <Pill tone={statusTone(data.status)}>{statusLabel(lang, data.status)}</Pill>
            <span className="t-3 text-[11px] tabular-nums">
              {data.date}
              {leagueLogoHint ? ` · ${leagueLogoHint}` : ''}
            </span>
            <span className="t-3 ml-auto text-[11px] tabular-nums">#{data.matchId}</span>
          </div>

          {/* 记分板：整页宽（跨两列） */}
          <SectionCard
            className="self-start"
            title={pick(lang, '记分板', 'Scoreboard')}
            hint={finished ? pick(lang, '最终比分', 'Final score') : pick(lang, '开赛时间', 'Kick-off')}
            right={<Pill tone={statusTone(data.status)}>{statusLabel(lang, data.status)}</Pill>}
          >
                <div className="grid grid-cols-1 items-center gap-4 min-[760px]:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)]">
                  <TeamPanel side={data.home} lang={lang} align="left" />

                  <div className="glass-dark on-ink flex min-w-[168px] flex-col items-center justify-center gap-1.5 self-stretch rounded-[24px] px-6 py-4">
                    {finished ? (
                      <>
                        <div className="text-[38px] font-semibold leading-none tabular-nums">
                          {data.score.home} <span className="opacity-50">:</span> {data.score.away}
                        </div>
                        <div className="on-ink text-[10.5px] tabular-nums opacity-65">
                          {kickoff}
                        </div>
                      </>
                    ) : (
                      <>
                        <div className="on-ink text-[10px] font-semibold uppercase tracking-[.16em] opacity-65">
                          {pick(lang, '开赛', 'Kick-off')}
                        </div>
                        <div className="text-[26px] font-semibold leading-none tabular-nums">{splitDateTime(data.date).time}</div>
                        <div className="on-ink text-[11px] tabular-nums opacity-65">{splitDateTime(data.date).date}</div>
                      </>
                    )}
                    {typeof data.score.htHome === 'number' && typeof data.score.htAway === 'number' ? (
                      <div className="on-ink mt-1 rounded-full px-2.5 py-0.5 text-[10.5px] tabular-nums opacity-80" style={{ background: 'rgba(255,255,255,.14)' }}>
                        {pick(lang, '半场', 'HT')} {data.score.htHome} : {data.score.htAway}
                      </div>
                    ) : null}
                  </div>

                  <TeamPanel side={data.away} lang={lang} align="right" />
                </div>
          </SectionCard>

          {/* 左列：模型预测 → 数据对比 → 双方近期比赛 */}
          <div className="mt-4 grid grid-cols-1 gap-4 lg:grid-cols-[minmax(0,1.35fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
              <PredictionCard
                prediction={data.prediction}
                lang={lang}
                status={data.status}
                score={{ home: data.score.home, away: data.score.away }}
                kickoff={kickoff}
              />

              {/* 数据对比（含 xG） */}
              {compareRows.length > 0 || hasXg ? (
                <SectionCard
                  className="self-start"
                  title={pick(lang, '数据对比', 'Statistics')}
                  hint={pick(lang, '左主队 / 右客队，条长为双方相对占比', 'Home left, away right — bar length is the relative share')}
                  right={hasXg ? <Pill tone="yellow">xG {num(data.xg.home)} – {num(data.xg.away)}</Pill> : undefined}
                >
                  <div className="flex items-center gap-2.5 pb-1">
                    <span className="t-3 w-[56px] shrink-0 text-right text-[10px] font-semibold uppercase">
                      {pick(lang, '主队', 'Home')}
                    </span>
                    <span className="t-3 min-w-0 flex-1 text-right text-[10px]">&nbsp;</span>
                    <span className="t-3 w-[112px] shrink-0 text-center text-[10px]">&nbsp;</span>
                    <span className="t-3 min-w-0 flex-1 text-[10px]">&nbsp;</span>
                    <span className="t-3 w-[56px] shrink-0 text-[10px] font-semibold uppercase">
                      {pick(lang, '客队', 'Away')}
                    </span>
                  </div>
                  <div className="flex flex-col">
                    {hasXg ? (
                      <CompareRow
                        label={pick(lang, '预期进球 xG', 'Expected goals xG')}
                        home={data.xg.home as number}
                        away={data.xg.away as number}
                        decimals={2}
                        highlight
                      />
                    ) : null}
                    {compareRows.map((r) => (
                      <CompareRow
                        key={r.label}
                        label={r.label}
                        home={r.home}
                        away={r.away}
                        decimals={r.decimals}
                      />
                    ))}
                  </div>
                  {data.xg.proxyHome !== null || data.xg.proxyAway !== null ? (
                    <p className="t-3 mt-2 text-[10.5px] tabular-nums">
                      {pick(lang, '代理 xG', 'Proxy xG')} {num(data.xg.proxyHome)} – {num(data.xg.proxyAway)}
                    </p>
                  ) : null}
                </SectionCard>
              ) : null}

              {data.home.form.length > 0 || data.away.form.length > 0 ? (
                <SectionCard
                  className="self-start"
                  title={pick(lang, '双方近期比赛', 'Recent matches')}
                  hint={pick(lang, '各队最近 5 场，按该队视角', 'Last 5 per team, from that team’s view')}
                >
                  <div className="flex flex-col gap-4">
                    {[data.home, data.away].map((side) => (
                      <div key={side.id} className="flex flex-col gap-1.5">
                        <div className="flex items-center gap-2">
                          <Logo src={side.logo} name={side.name} size={20} />
                          <span className="t-1 min-w-0 truncate text-[12.5px] font-semibold" title={side.name}>
                            {pick(lang, side.name, side.nameEn)}
                          </span>
                          <span className="t-3 ml-auto text-[10px] tabular-nums">
                            {pick(lang, `近 ${side.form.length} 场`, `last ${side.form.length}`)}
                          </span>
                        </div>
                        <FormList rows={side.form} lang={lang} currentId={data.matchId} />
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}
            </div>

            {/* 右列：赛季积分榜位置 → 历史交锋 → 快捷入口 */}
            <div className="flex min-w-0 flex-col gap-4">
              {data.home.standing || data.away.standing ? (
                <SectionCard
                  className="self-start"
                  title={pick(lang, '赛季积分榜位置', 'Season standing')}
                  hint={pick(lang, '来自库内积分榜表，两队场次可能不同步', 'From the standings table; games played may differ between sides')}
                >
                  <div className="flex flex-col gap-2.5">
                    {[
                      { side: data.home, label: pick(lang, '主队', 'Home'), align: 'left' as const },
                      { side: data.away, label: pick(lang, '客队', 'Away'), align: 'right' as const },
                    ].map(({ side, label }) => (
                      <div key={side.id} className="flex flex-col gap-1.5">
                        <div className="flex items-center gap-2">
                          <Logo src={side.logo} name={side.name} size={20} />
                          <Link
                            to={`/teams/${side.id}`}
                            className="t-1 min-w-0 truncate text-[12.5px] font-semibold hover:underline"
                            title={pick(lang, side.name, side.nameEn)}
                          >
                            {pick(lang, side.name, side.nameEn)}
                          </Link>
                          <span className="t-3 text-[10px] uppercase">{label}</span>
                        </div>
                        {side.standing ? (
                          <StandingLine standing={side.standing} lang={lang} />
                        ) : (
                          <EmptyState text={pick(lang, '暂无积分榜数据', 'No standing data')} />
                        )}
                      </div>
                    ))}
                  </div>
                </SectionCard>
              ) : null}

              {/* 历史交锋 */}
              {data.h2h.meetings > 0 ? (
                <SectionCard
                  className="self-start"
                  title={pick(lang, '历史交锋', 'Head-to-head')}
                  hint={pick(
                    lang,
                    '交锋记录（已完赛，不含本场），胜负以本场主队视角统计',
                    'Finished meetings excluding this one; W/D/L counted for the home side of this match',
                  )}
                  right={<Pill tone="ink">{data.h2h.meetings}</Pill>}
                >
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="glass-soft t-2 rounded-full px-3 py-1.5 text-[11px] font-semibold">
                      {pick(lang, '主队胜', 'Home wins')} {data.h2h.homeWins}
                    </span>
                    <span className="glass-soft t-2 rounded-full px-3 py-1.5 text-[11px] font-semibold">
                      {pick(lang, '平局', 'Draws')} {data.h2h.draws}
                    </span>
                    <span className="glass-soft t-2 rounded-full px-3 py-1.5 text-[11px] font-semibold">
                      {pick(lang, '客队胜', 'Away wins')} {data.h2h.awayWins}
                    </span>
                    <span className="t-3 ml-auto text-[10.5px]">
                      {pick(lang, '最多展示 8 场', 'Up to 8 shown')}
                    </span>
                  </div>
                  <div className="mt-3 flex flex-col gap-1.5">
                    {data.h2h.items.slice(0, 8).map((h) => {
                      const dt = splitDateTime(h.date)
                      return (
                        <div key={h.match_id} className="flex items-center gap-2 rounded-[14px] px-2.5 py-2">
                          <Pill tone={h.resultForHome === 'W' ? 'green' : h.resultForHome === 'D' ? 'yellow' : 'blue'}>
                            {pick(
                              lang,
                              h.resultForHome === 'W' ? '主胜' : h.resultForHome === 'D' ? '平' : '客胜',
                              h.resultForHome === 'W' ? 'HW' : h.resultForHome === 'D' ? 'D' : 'AW',
                            )}
                          </Pill>
                          <span className="t-3 w-[38px] shrink-0 text-[10px] tabular-nums">{dt.date}</span>
                          <span className="t-2 min-w-0 flex-1 truncate text-[12px]">
                            {h.h} <span className="t-3">vs</span> {h.a}
                          </span>
                          <span className="t-3 hidden shrink-0 text-[10px] min-[620px]:block">
                            {pick(lang, h.lg, h.lg_en)}
                          </span>
                          <span className="t-1 w-[54px] shrink-0 text-right text-[12px] font-semibold tabular-nums">
                            {h.home_goals ?? '—'} : {h.away_goals ?? '—'}
                          </span>
                        </div>
                      )
                    })}
                  </div>
                </SectionCard>
              ) : (
                <SectionCard
                  className="self-start"
                  title={pick(lang, '历史交锋', 'Head-to-head')}
                  hint={pick(lang, '库内没有双方已完赛的交锋记录', 'No finished meetings in the database')}
                >
                  {/* 空状态不撑高：只收紧布局间距，文案与空状态样式保持原样 */}
                  <div className="-my-[26px]">
                    <EmptyState text={pick(lang, '暂无历史交锋', 'No head-to-head records')} />
                  </div>
                </SectionCard>
              )}

              <SectionCard
                className="self-start"
                title={pick(lang, '快捷入口', 'Shortcuts')}
                hint={pick(lang, '跳转到球队与预测页面', 'Jump to team and prediction pages')}
              >
                <div className="flex flex-col gap-2">
                  {[data.home, data.away].map((side) => (
                    <Link
                      key={side.id}
                      to={`/teams/${side.id}`}
                      className="glass-soft card-hover group flex items-center gap-2.5 rounded-[18px] px-3 py-2.5"
                    >
                      <Logo src={side.logo} name={side.name} size={22} />
                      <span className="t-1 min-w-0 flex-1 truncate text-[12.5px] font-medium">
                        {pick(lang, side.name, side.nameEn)}
                      </span>
                      <span className="t-3 text-[10px]">{shortTeam(lang, side.name, side.nameEn)}</span>
                      <ChevronRight size={14} className="t-3 transition-transform duration-300 group-hover:translate-x-0.5" />
                    </Link>
                  ))}
                </div>
              </SectionCard>
            </div>
          </div>
        </>
      ) : null}
    </PageShell>
  )
}
