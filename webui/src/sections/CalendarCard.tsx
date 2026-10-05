import { useState } from 'react'
import { pick, useHome, weekdayShort } from '../data/live'
import { useLang } from '../i18n'

/* ---------------- 赛程日历（真实 6 天赛程） ---------------- */

function Crest({ src, ring }: { src?: string | null; ring: string }) {
  if (!src) return null
  return (
    <span
      className="flex h-[22px] w-[22px] items-center justify-center overflow-hidden rounded-full transition-transform duration-300 hover:-translate-y-1"
      style={{ boxShadow: `0 0 0 2px ${ring}` }}
    >
      <img src={src} alt="" className="crest h-full w-full rounded-full" loading="lazy" />
    </span>
  )
}

export default function CalendarCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const cal = data?.calendar
  const days = cal?.days ?? []
  const hours = cal?.hours ?? []
  const colW = days.length ? 100 / days.length : 25
  const [selectedDay, setSelectedDay] = useState<number | null>(null)
  const [hover, setHover] = useState<string | null>(null)

  return (
    <div className="glass card-hover anim-in flex-1 rounded-[28px] p-5" style={{ '--d': '260ms' } as React.CSSProperties}>
      <div className="grid grid-cols-3 items-center">
        <span className="t-3 text-[13px] font-medium">{pick(lang, '未来 6 天', 'Next 6 days')}</span>
        <span className="t-1 text-center text-[16px] font-bold">{cal?.month ?? '—'}</span>
        <span className="t-3 text-right text-[13px] font-medium tabular-nums">
          {data ? `${cal?.events.length ?? 0} ${pick(lang, '场', 'fixtures')}` : ''}
        </span>
      </div>

      {/* 日期表头 */}
      <div className="mt-3 flex">
        <div className="w-[52px] shrink-0" />
        {days.map((day, i) => (
          <button
            key={day.date}
            onClick={() => setSelectedDay(selectedDay === i ? null : i)}
            className={`flex-1 rounded-xl py-1 text-center transition-all duration-300 ${
              selectedDay === i ? 'bg-[#F6C945]/70' : 'hover:bg-white/30'
            }`}
          >
            <p className="t-1 text-[11px] font-semibold">{weekdayShort(lang, day.date)}</p>
            <p className="t-2 text-[11px] font-medium tabular-nums">{day.n}</p>
          </button>
        ))}
      </div>

      {/* 时间轴网格 */}
      <div className="relative mt-2 flex">
        <div className="w-[52px] shrink-0">
          {hours.map((h) => (
            <p key={h} className="t-3 flex h-[64px] items-start text-[10px] font-medium tabular-nums">
              {String(h).padStart(2, '0')}:00
            </p>
          ))}
        </div>
        <div className="relative flex-1">
          {hours.map((h) => (
            <div key={h} className="line-c h-[64px] border-t" />
          ))}
          {selectedDay !== null && (
            <div
              className="pointer-events-none absolute inset-y-0 rounded-xl bg-[#F6C945]/15 transition-all duration-300"
              style={{ left: `${colW * selectedDay}%`, width: `${colW}%` }}
            />
          )}
          {(cal?.events ?? []).map((event) => {
            const dark = event.theme === 'dark'
            const active = hover === event.id
            // 真实赛程稀疏：单列卡片放不下标题 → 至少占 2 列
            const span = Math.max(2, Math.min(event.span || 1, days.length - event.startDay))
            return (
              <div
                key={event.id}
                onMouseEnter={() => setHover(event.id)}
                onMouseLeave={() => setHover(null)}
                className={`event-card absolute flex h-[86px] flex-col gap-1 rounded-2xl px-4 pt-3.5 transition-transform duration-300 ${
                  dark ? 'glass-dark' : 'glass-pop'
                } ${active ? 'z-20 scale-[1.03]' : 'z-10'}`}
                style={{
                  top: (event.startHour - hours[0]) * 64 + 6,
                  left: `calc(${colW * event.startDay}% + 8px)`,
                  width: `calc(${colW * span}% - 22px)`,
                }}
              >
                <p className={`truncate text-[13px] font-bold leading-tight ${dark ? 'on-ink' : 't-1'}`}>{event.title}</p>
                <p className={`truncate text-[10px] font-medium leading-tight ${dark ? 'on-ink opacity-60' : 't-2'}`}>
                  {event.subtitle}
                </p>
                <div className="absolute bottom-2.5 right-3 flex -space-x-2">
                  {event.logos.slice(0, 3).map((l, i) => (
                    <Crest key={`${event.id}-${i}`} src={l} ring={dark ? '#2B2B27' : 'rgba(255,255,255,0.9)'} />
                  ))}
                </div>
              </div>
            )
          })}
          {!cal && (
            <div className="absolute inset-0 flex flex-col gap-3 pt-2">
              <div className="skeleton h-[86px] w-[40%] rounded-2xl" />
              <div className="skeleton ml-[30%] h-[86px] w-[36%] rounded-2xl" />
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
