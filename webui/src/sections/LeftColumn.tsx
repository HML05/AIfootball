import { useState } from 'react'
import { ChevronDown, ChevronRight } from 'lucide-react'
import { pick, splitDateTime, useHome } from '../data/live'
import { useLang } from '../i18n'

/* ---------------- 焦点赛事卡（真实下一场 + 预测） ---------------- */

export function ProfileCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const m = data?.focusMatch
  const { date, time } = splitDateTime(m?.date ?? '')
  const segs = m?.segments ?? []
  const topKey = segs.length ? segs.reduce((a, b) => (b.pct > a.pct ? b : a)).key : ''

  return (
    <div
      className="card-hover anim-in group relative h-[300px] overflow-hidden rounded-[28px] border border-white/40 shadow-lg shadow-black/10"
      style={{ '--d': '60ms' } as React.CSSProperties}
    >
      <img
        src="/images/hero-stadium.jpg"
        alt="stadium"
        className="h-full w-full object-cover object-center transition-transform duration-700 ease-out group-hover:scale-105"
      />
      <div className="absolute inset-0 bg-gradient-to-t from-[#2b2b27]/85 via-[#2b2b27]/25 to-transparent" />
      <div className="absolute inset-0 bg-[#F6C945]/10 mix-blend-soft-light" />

      <div className="absolute left-4 right-4 top-4 flex items-center justify-between">
        <span className="rounded-full border border-white/25 bg-black/25 px-3 py-1 text-[11px] font-semibold text-white backdrop-blur-md">
          {m ? pick(lang, m.league, m.leagueEn) : '—'}
        </span>
        <span className="rounded-full border border-white/25 bg-black/25 px-3 py-1 text-[11px] font-medium tabular-nums text-white backdrop-blur-md">
          {date} {time}
        </span>
      </div>

      <div className="absolute inset-x-0 bottom-0 p-4">
        <div className="flex items-center justify-between gap-2">
          <div className="flex min-w-0 flex-col items-center gap-1.5">
            {m?.home.logo ? <img src={m.home.logo} alt="" className="crest h-9 w-9 rounded-full" loading="lazy" /> : null}
            <span className="max-w-[86px] truncate text-[12px] font-semibold text-white">
              {m ? pick(lang, m.home.name, m.home.nameEn) : '—'}
            </span>
          </div>
          <div className="flex flex-col items-center">
            <span className="text-[22px] font-light leading-none text-white/90">VS</span>
            <span className="mt-1 rounded-full border border-white/25 bg-white/15 px-2.5 py-0.5 text-[10px] font-semibold text-white backdrop-blur-md">
              {m ? `${pick(lang, '推荐 ', 'Pick ')}${m.pick}` : '—'}
            </span>
          </div>
          <div className="flex min-w-0 flex-col items-center gap-1.5">
            {m?.away.logo ? <img src={m.away.logo} alt="" className="crest h-9 w-9 rounded-full" loading="lazy" /> : null}
            <span className="max-w-[86px] truncate text-[12px] font-semibold text-white">
              {m ? pick(lang, m.away.name, m.away.nameEn) : '—'}
            </span>
          </div>
        </div>

        {/* 三分类概率（与推荐同源，直接给结论） */}
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          {segs.map((seg) => (
            <div
              key={seg.key}
              className={`rounded-full py-1 text-center text-[10.5px] font-semibold tabular-nums ${
                seg.key === topKey ? 'bg-[#F6C945] text-[#26251F]' : 'border border-white/20 bg-black/30 text-white/85'
              }`}
            >
              {pick(lang, seg.label, seg.labelEn)} {seg.pct}%
            </div>
          ))}
          {!segs.length && <div className="skeleton col-span-3 h-[22px] rounded-full" />}
        </div>
        <p className="mt-2 text-[10px] font-medium text-white/70 tabular-nums">{m ? `${m.model} · ${pick(lang, '样本外评估', 'out-of-sample')}` : ''}</p>
      </div>
    </div>
  )
}

/* ---------------- 联赛榜（真实积分榜 Top3） ---------------- */

export function SideMenu() {
  const { lang } = useLang()
  const { data } = useHome()
  const leagues = data?.leagueCards ?? []
  const [openId, setOpenId] = useState<number | null>(null)
  const opened = openId ?? leagues[0]?.id ?? null

  return (
    <div className="glass card-hover anim-in flex-1 rounded-[28px] px-5 py-2.5" style={{ '--d': '140ms' } as React.CSSProperties}>
      <div className="flex items-center justify-between py-2">
        <span className="t-1 text-[13px] font-semibold">{pick(lang, '联赛积分榜', 'League tables')}</span>
        <span className="t-3 text-[10px] font-medium">
          {data ? `${leagues.length} ${pick(lang, '个联赛', 'leagues')}` : ''}
        </span>
      </div>
      <div className="line-c divide-y">
        {leagues.map((item) => {
          const open = opened === item.id
          const top3 = item.top3 ?? []
          return (
            <div key={item.id}>
              <button
                onClick={() => setOpenId(open ? null : item.id)}
                className="flex w-full items-center justify-between py-3 text-left"
              >
                <span className="flex flex-col">
                  <span className="t-1 text-[14px] font-semibold">{pick(lang, item.name, item.nameEn)}</span>
                  <span className="t-3 text-[10px] font-medium tabular-nums">
                    {item.season} · {(item.matches ?? 0).toLocaleString()} {pick(lang, '场', 'matches')} · {item.teams ?? 0}{' '}
                    {pick(lang, '队', 'teams')}
                  </span>
                </span>
                <ChevronDown size={16} className={`t-2 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
              </button>
              <div
                className="grid transition-[grid-template-rows] duration-500 ease-out"
                style={{ gridTemplateRows: open && top3.length ? '1fr' : '0fr' }}
              >
                <div className="overflow-hidden">
                  <div className="flex flex-col gap-2 pb-4">
                    {top3.map((t) => (
                      <div key={t.team} className="flex items-center gap-2.5">
                        <span className="t-3 w-3 text-[10px] font-bold tabular-nums">{t.rank}</span>
                        {t.logo ? (
                          <img src={t.logo} alt="" className="crest h-6 w-6 rounded-full" loading="lazy" />
                        ) : (
                          <span className="glass-soft flex h-6 w-6 items-center justify-center rounded-full text-[9px] font-bold">
                            {t.team.slice(0, 2)}
                          </span>
                        )}
                        <span className="t-1 min-w-0 flex-1 truncate text-[12px] font-semibold">{t.team}</span>
                        <span className="t-3 text-[10px] font-medium tabular-nums">
                          {t.played}
                          {pick(lang, ' 场', ' p')}
                        </span>
                        <span className="t-1 text-[12px] font-bold tabular-nums">{t.points}</span>
                      </div>
                    ))}
                    <div className="t-3 mt-1 flex items-center gap-1 text-[10px] font-medium">
                      {pick(lang, '查看完整积分榜', 'Full standings')}
                      <ChevronRight size={11} />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          )
        })}
        {!leagues.length && (
          <div className="flex flex-col gap-3 py-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="skeleton h-9 w-full rounded-xl" />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
