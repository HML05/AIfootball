import { useState } from 'react'
import { Activity, BrainCircuit, CalendarSync, Check, Coins, Database, Radio, ShieldCheck, Users } from 'lucide-react'
import { pick, useHome } from '../data/live'
import { useLang } from '../i18n'

/* ---------------- 数据更新日志（真实） ---------------- */

const ICONS: Record<string, React.ReactNode> = {
  sync: <CalendarSync size={15} />,
  live: <Radio size={15} />,
  api: <ShieldCheck size={15} />,
  retrain: <BrainCircuit size={15} />,
  odds: <Coins size={15} />,
  value: <Coins size={15} />,
  injury: <Activity size={15} />,
  xg: <Database size={15} />,
  squad: <Users size={15} />,
}

export default function PendingActions() {
  const { lang } = useLang()
  const { data } = useHome()
  const log = data?.updateLog ?? []
  const [collapsed, setCollapsed] = useState<Record<string, boolean>>({})

  const doneCount = log.filter((i) => i.done && !collapsed[i.id]).length
  const total = log.length

  const toggle = (id: string) => setCollapsed((prev) => ({ ...prev, [id]: !prev[id] }))

  return (
    <div className="glass-dark card-hover anim-in flex-1 rounded-[28px] p-5" style={{ '--d': '300ms' } as React.CSSProperties}>
      <div className="flex items-center justify-between">
        <span className="on-ink text-[16px] font-bold">{pick(lang, '更新日志', 'Update Log')}</span>
        <span className="rounded-full bg-white/[0.08] px-2.5 py-0.5 text-[12px] font-medium tabular-nums text-[#B3AD97]">
          {total ? `${Math.max(doneCount, total - Object.values(collapsed).filter(Boolean).length)}/${total}` : '—'}
        </span>
      </div>
      <div className="mt-2 divide-y divide-white/[0.07]">
        {log.map((row) => {
          const done = row.done
          return (
            <div
              key={row.id}
              className="action-row flex items-center gap-3 py-3.5"
              onClick={() => toggle(row.id)}
              role="checkbox"
              aria-checked={done}
              tabIndex={0}
              onKeyDown={(e) => e.key === 'Enter' && toggle(row.id)}
            >
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/[0.07] text-[#B3AD97] transition-colors duration-300">
                {ICONS[row.level] ?? <Database size={15} />}
              </span>
              <div className="min-w-0 flex-1">
                <p
                  className={`truncate text-[14px] font-semibold leading-tight transition-all duration-300 ${
                    done ? 'text-[#D8D2BC]' : 'text-[#8B8672]'
                  }`}
                >
                  {pick(lang, row.title, row.titleEn)}
                </p>
                <p className="mt-0.5 truncate text-[11px] font-medium text-[#8B8672]" title={pick(lang, row.desc, row.descEn)}>
                  {row.ts} · {pick(lang, row.desc, row.descEn)}
                </p>
              </div>
              <span
                className={`flex h-[26px] w-[26px] shrink-0 items-center justify-center rounded-full transition-all duration-300 ${
                  done ? 'scale-100 bg-[#F6C945] shadow-md shadow-[#F6C945]/30' : 'scale-95 border border-white/20 hover:border-[#F6C945]/60'
                }`}
              >
                {done && <Check size={14} strokeWidth={3} className="text-[#2B2B27]" />}
              </span>
            </div>
          )
        })}
        {!total && (
          <div className="flex flex-col gap-3 py-4">
            {[0, 1, 2, 3].map((i) => (
              <div key={i} className="h-12 w-full animate-pulse rounded-2xl bg-white/[0.05]" />
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
