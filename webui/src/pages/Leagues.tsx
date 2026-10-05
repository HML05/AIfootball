/**
 * 联赛数据 —— 真实数据来自 GET /api/ui/leagues
 *
 * 顶部 KPI（联赛数 / 总比赛 / 球队数 / 场均进球）+ 联赛卡片网格：
 * 每张卡 = 双语联赛名 + 赛季 + 核心场均指标 + 主胜/平/客胜占比条 + 积分榜前三。
 * 整卡可点击进入 /leagues/:id。
 */
import { useMemo, useState } from 'react'
import { useNavigate } from 'react-router'
import {
  PageShell,
  SectionCard,
  Pill,
  SearchBox,
  EmptyState,
  ErrorState,
  KpiStrip,
} from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api } from '../lib/api'
import type { LeagueCard } from '../lib/api'
import { useApi } from '../lib/useApi'
import { pick, fmtNum, pct } from '../data/live'
import { useLang } from '../i18n'

/* ---------------- 主胜 / 平 / 客胜 横向堆叠占比条 ---------------- */

const SEG: { key: 'homeWinPct' | 'drawPct' | 'awayWinPct'; color: string; zh: string; en: string }[] = [
  { key: 'homeWinPct', color: '#F6C945', zh: '主胜', en: 'Home' },
  { key: 'drawPct', color: '#b3ad97', zh: '平局', en: 'Draw' },
  { key: 'awayWinPct', color: '#A8C5E2', zh: '客胜', en: 'Away' },
]

function OutcomeBar({ card }: { card: LeagueCard }) {
  const { lang } = useLang()
  const total = SEG.reduce((s, g) => s + (card[g.key] ?? 0), 0)
  const scale = total > 0 ? 100 / total : 0
  return (
    <div>
      <div className="track-c flex h-[9px] w-full gap-[2px] overflow-hidden rounded-full">
        {SEG.map((g) => (
          <span
            key={g.key}
            className="bar-grow-x h-full rounded-full"
            style={{ width: `${(card[g.key] ?? 0) * scale}%`, backgroundColor: g.color, '--d': '320ms' } as React.CSSProperties}
          />
        ))}
      </div>
      <div className="mt-2 flex items-center justify-between">
        {SEG.map((g) => (
          <span key={g.key} className="flex items-center gap-1.5">
            <span className="h-1.5 w-1.5 rounded-full" style={{ backgroundColor: g.color }} />
            <span className="t-3 text-[10px] font-medium">{pick(lang, g.zh, g.en)}</span>
            <span className="t-2 text-[10.5px] font-semibold tabular-nums">{pct(card[g.key])}</span>
          </span>
        ))}
      </div>
    </div>
  )
}

/* ---------------- 单张联赛卡 ---------------- */

function LeagueTile({ card }: { card: LeagueCard }) {
  const { lang } = useLang()
  const nav = useNavigate()
  const metrics: { label: string; value: string }[] = [
    { label: pick(lang, '场次', 'Matches'), value: fmtNum(card.matches) },
    { label: pick(lang, '球队', 'Teams'), value: fmtNum(card.teams) },
    { label: pick(lang, '场均进球', 'Goals / match'), value: card.goalsPg === null ? '—' : card.goalsPg.toFixed(2) },
    { label: pick(lang, '场均 xG', 'xG / match'), value: card.xgPg === null ? '—' : card.xgPg.toFixed(2) },
  ]
  return (
    <SectionCard
      title={pick(lang, card.name, card.nameEn)}
      hint={pick(lang, '积分榜前三', 'Top three')}
      right={<Pill tone="muted">{card.season}</Pill>}
      className="group relative cursor-pointer transition-transform duration-300 hover:scale-[1.015]"
    >
      <button
        type="button"
        aria-label={pick(lang, card.name, card.nameEn)}
        className="absolute inset-0 z-0 cursor-pointer rounded-[28px] focus:outline-none"
        onClick={() => nav(`/leagues/${card.id}`)}
      />
      <div className="pointer-events-none relative z-10">
        <div className="grid grid-cols-4 gap-2">
          {metrics.map((m) => (
            <div key={m.label}>
              <p className="t-3 text-[9.5px] font-semibold uppercase leading-tight tracking-wide">{m.label}</p>
              <p className="t-1 mt-1 text-[16px] font-medium leading-none tabular-nums">{m.value}</p>
            </div>
          ))}
        </div>

        <div className="line-c my-4 border-t" />

        <OutcomeBar card={card} />

        <div className="line-c my-4 border-t" />

        <div className="flex flex-col gap-2">
          {card.top3.map((t) => (
            <div key={t.rank} className="flex items-center gap-2.5">
              <span className="t-3 w-3 text-[10.5px] font-semibold tabular-nums">{t.rank}</span>
              {t.logo ? (
                <img src={t.logo} alt="" className="crest h-5 w-5 shrink-0 rounded-full" loading="lazy" />
              ) : (
                <span className="h-5 w-5 shrink-0 rounded-full bg-[var(--track)]" />
              )}
              <span className="t-2 min-w-0 flex-1 truncate text-[12px] font-medium">{pick(lang, t.team, t.teamEn)}</span>
              <span className="t-3 text-[10px] font-medium tabular-nums">
                {fmtNum(t.played)} {pick(lang, '场', 'P')}
              </span>
              <span className="t-1 w-8 text-right text-[12.5px] font-semibold tabular-nums">{fmtNum(t.points)}</span>
            </div>
          ))}
        </div>
      </div>
    </SectionCard>
  )
}

/* ---------------- 页面 ---------------- */

export default function Leagues() {
  const { lang } = useLang()
  const { data, loading, error } = useApi(() => api.leagues(), 'leagues')
  const [q, setQ] = useState('')

  const items = data?.items ?? []
  const filtered = useMemo(() => {
    const kw = q.trim().toLowerCase()
    if (!kw) return items
    return items.filter((l) =>
      [l.name, l.nameEn].some((s) => (s || '').toLowerCase().includes(kw)),
    )
  }, [items, q])

  // 优先用后端给的库内去重口径（totals），没有再退回家各联赛求和
  const { totalMatches, totalTeams, goalsPg, teamsScope } = useMemo(() => {
    const t = data?.totals
    if (t) {
      return {
        totalMatches: t.matches,
        totalTeams: t.teams,
        goalsPg: t.goalsPg ?? null,
        teamsScope: pick(lang, '库内去重', 'unique in DB'),
      }
    }
    const matches = items.reduce((s, l) => s + (l.matches || 0), 0)
    const teams = items.reduce((s, l) => s + (l.teams || 0), 0)
    const goals = items.reduce((s, l) => s + (l.goalsPg || 0) * (l.matches || 0), 0)
    return {
      totalMatches: matches,
      totalTeams: teams,
      goalsPg: matches > 0 ? goals / matches : null,
      teamsScope: pick(lang, '各联赛求和', 'sum of leagues'),
    }
  }, [items, data?.totals, lang])

  const kpis = useMemo(
    () => [
      { label: pick(lang, '联赛数', 'Leagues'), value: fmtNum(items.length), sub: pick(lang, '当前赛季', 'current season') },
      { label: pick(lang, '总比赛场次', 'Matches'), value: fmtNum(totalMatches) },
      { label: pick(lang, '球队总数', 'Teams'), value: fmtNum(totalTeams), sub: teamsScope },
      {
        label: pick(lang, '平均场均进球', 'Goals / match'),
        value: goalsPg === null ? '—' : goalsPg.toFixed(2),
        sub: pick(lang, '按场次加权', 'weighted by matches'),
      },
    ],
    [lang, items.length, totalMatches, totalTeams, teamsScope, goalsPg],
  )

  return (
    <PageShell
      title={pick(lang, '联赛数据', 'Leagues')}
      subtitle={`${fmtNum(items.length)} ${pick(lang, '个联赛', 'leagues')} · ${fmtNum(totalMatches)} ${pick(
        lang,
        '场比赛',
        'matches',
      )} · ${fmtNum(totalTeams)} ${pick(lang, '支球队', 'teams')}`}
      activePath="/leagues"
      right={
        <SearchBox
          value={q}
          onChange={setQ}
          placeholder={pick(lang, '搜索联赛名称…', 'Search leagues…')}
          status={<span className="t-3 text-[10.5px] font-medium tabular-nums">{fmtNum(filtered.length)}</span>}
        />
      }
    >
      {error ? (
        <div className="mt-6">
          <ErrorState text={error} />
        </div>
      ) : null}

      <div className="mt-6">
        <KpiStrip items={kpis} />
      </div>

      <div className="mt-6">
        {loading && !data ? (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {Array.from({ length: 6 }).map((_, i) => (
              <SectionCard key={i}>
                <CardSkeleton rows={5} />
              </SectionCard>
            ))}
          </div>
        ) : filtered.length === 0 ? (
          <SectionCard>
            <EmptyState text={pick(lang, '没有匹配的联赛', 'No league matched')} />
          </SectionCard>
        ) : (
          <div className="grid grid-cols-1 gap-5 md:grid-cols-2 xl:grid-cols-3">
            {filtered.map((c) => (
              <LeagueTile key={c.id} card={c} />
            ))}
          </div>
        )}
      </div>
    </PageShell>
  )
}
