import { ArrowUpRight, Clock } from 'lucide-react'
import { pick, splitDateTime, useHome } from '../data/live'
import type { MatchRow, UpcomingRow } from '../lib/api'
import { useLang } from '../i18n'

function Crest({ src, alt, size = 22 }: { src?: string | null; alt?: string; size?: number }) {
  if (!src)
    return (
      <span
        className="glass-soft flex items-center justify-center rounded-full text-[8px] font-bold"
        style={{ width: size, height: size }}
      >
        {(alt ?? '?').slice(0, 2)}
      </span>
    )
  return <img src={src} alt={alt ?? ''} className="crest rounded-full" style={{ width: size, height: size }} loading="lazy" />
}

function CardHead({ title, hint, onMore }: { title: string; hint?: string; onMore?: () => void }) {
  return (
    <div className="flex items-start justify-between">
      <div className="flex flex-col">
        <span className="t-1 text-[15px] font-semibold">{title}</span>
        {hint ? <span className="t-3 mt-0.5 text-[10px] font-medium">{hint}</span> : null}
      </div>
      <button
        onClick={onMore}
        className="glass-soft flex h-8 w-8 items-center justify-center rounded-full transition-transform duration-300 hover:rotate-45 hover:scale-110 active:scale-95"
      >
        <ArrowUpRight size={15} className="t-1" />
      </button>
    </div>
  )
}

/** 最近完赛（真实比分） */
export function RecentMatchesCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const rows: MatchRow[] = data?.recent ?? []

  return (
    <div className="glass card-hover anim-in flex flex-col rounded-[28px] p-5" style={{ '--d': '300ms' } as React.CSSProperties}>
      <CardHead
        title={pick(lang, '最近完赛', 'Latest results')}
        hint={data ? `${pick(lang, '截至', 'as of')} ${data.dataNow}` : undefined}
      />
      <div className="line-c mt-2 divide-y">
        {rows.slice(0, 6).map((m) => {
          const { date } = splitDateTime(m.date)
          return (
            <div key={m.match_id} className="flex items-center gap-3 py-2.5">
              <span className="t-3 w-[38px] shrink-0 text-[10px] font-medium tabular-nums">{date}</span>
              <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
                <span className="t-2 min-w-0 truncate text-right text-[12px] font-medium">
                  {pick(lang, m.h, m.h_en)}
                </span>
                <Crest src={m.h_logo} alt={m.h_en} />
              </div>
              <span className="t-1 w-[46px] shrink-0 rounded-full bg-[var(--track)] py-0.5 text-center text-[12px] font-bold tabular-nums">
                {m.home_goals ?? 0}:{m.away_goals ?? 0}
              </span>
              <div className="flex min-w-0 flex-1 items-center gap-2">
                <Crest src={m.a_logo} alt={m.a_en} />
                <span className="t-2 min-w-0 truncate text-[12px] font-medium">{pick(lang, m.a, m.a_en)}</span>
              </div>
            </div>
          )
        })}
        {!rows.length && <div className="skeleton my-3 h-40 w-full rounded-2xl" />}
      </div>
    </div>
  )
}

/** 待赛 + 预测（真实概率） */
export function UpcomingCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const rows: UpcomingRow[] = data?.upcoming ?? []

  return (
    <div className="glass card-hover anim-in flex flex-col rounded-[28px] p-5" style={{ '--d': '340ms' } as React.CSSProperties}>
      <CardHead
        title={pick(lang, '未来赛程', 'Upcoming fixtures')}
        hint={data ? `${pick(lang, '共', 'total')} ${data.coverage.upcoming.toLocaleString()} ${pick(lang, '场待赛', 'upcoming')}` : undefined}
      />
      <div className="line-c mt-2 divide-y">
        {rows.slice(0, 6).map((m) => {
          const { date, time } = splitDateTime(m.date)
          const probs = [m.pred_home_win, m.pred_draw, m.pred_away_win]
          const hasPred = probs.every((p) => p !== null && p !== undefined)
          return (
            <div key={m.match_id} className="flex flex-col gap-1.5 py-2.5">
              <div className="flex items-center gap-3">
                <span className="t-3 flex w-[62px] shrink-0 items-center gap-1 text-[10px] font-medium tabular-nums">
                  <Clock size={10} />
                  {date} {time}
                </span>
                <div className="flex min-w-0 flex-1 items-center justify-end gap-2">
                  <span className="t-2 min-w-0 truncate text-right text-[12px] font-medium">
                    {pick(lang, m.h, m.h_en)}
                  </span>
                  <Crest src={m.h_logo} alt={m.h_en} />
                </div>
                <span className="t-3 w-[22px] shrink-0 text-center text-[10px] font-bold">VS</span>
                <div className="flex min-w-0 flex-1 items-center gap-2">
                  <Crest src={m.a_logo} alt={m.a_en} />
                  <span className="t-2 min-w-0 truncate text-[12px] font-medium">{pick(lang, m.a, m.a_en)}</span>
                </div>
              </div>
              {hasPred ? (
                <div className="flex items-center gap-2 pl-[62px]">
                  <div className="flex h-[5px] flex-1 overflow-hidden rounded-full bg-[var(--track)]">
                    <span style={{ width: `${probs[0]}%`, backgroundColor: '#F6C945' }} />
                    <span style={{ width: `${probs[1]}%`, backgroundColor: 'var(--c-ink)' }} />
                    <span style={{ width: `${probs[2]}%`, backgroundColor: 'var(--c-hatch)' }} />
                  </div>
                  <span className="t-3 text-[10px] font-semibold tabular-nums">
                    {Math.max(probs[0]!, probs[1]!, probs[2]!).toFixed(1)}%
                  </span>
                </div>
              ) : (
                <span className="t-3 pl-[62px] text-[10px] font-medium">{pick(lang, '预测待生成', 'no prediction yet')}</span>
              )}
            </div>
          )
        })}
        {!rows.length && <div className="skeleton my-3 h-40 w-full rounded-2xl" />}
      </div>
    </div>
  )
}
