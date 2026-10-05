import { Database, Trophy, UserPlus } from 'lucide-react'
import { useCountUp } from '../hooks/useCountUp'
import { fmtCompact, pick, useHome } from '../data/live'
import { useLang } from '../i18n'

type Variant = 'dark' | 'yellow' | 'light'

const PILL_STYLES: Record<Variant, string> = {
  dark: 'bg-ink on-ink shadow-lg shadow-black/20',
  yellow: 'bg-[#F6C945] text-[#26251F] shadow-lg shadow-[#F6C945]/40',
  light: 'glass-soft t-1',
}

interface Pill {
  key: string
  label: string
  value: number
  decimals?: number
  suffix?: string
  variant: Variant
  sub?: string
}

function StatPill({ data, delay }: { data: Pill; delay: number }) {
  const value = useCountUp(data.value, 1100, data.decimals ?? 0)
  return (
    <div className="anim-in flex flex-col items-start gap-1.5" style={{ '--d': `${delay}ms` } as React.CSSProperties}>
      <span className="t-2 text-[12px] font-medium">{data.label}</span>
      <span
        className={`rounded-full px-5 py-2 text-[13px] font-semibold tabular-nums transition-transform duration-300 hover:scale-105 ${PILL_STYLES[data.variant]}`}
      >
        {data.decimals ? value.toFixed(data.decimals) : Math.round(value).toLocaleString()}
        {data.suffix}
      </span>
    </div>
  )
}

const BIG_ICONS: Record<string, React.ReactNode> = {
  trophy: <Trophy size={18} strokeWidth={2} />,
  players: <UserPlus size={18} strokeWidth={2} />,
  records: <Database size={18} strokeWidth={2} />,
}

function BigStat({
  icon,
  label,
  value,
  display,
  delay,
}: {
  icon: keyof typeof BIG_ICONS
  label: string
  value: number
  display?: string
  delay: number
}) {
  const counted = useCountUp(value, 1400, 0)
  return (
    <div
      className="anim-in group flex cursor-default flex-col items-center gap-0.5"
      style={{ '--d': `${delay}ms` } as React.CSSProperties}
    >
      <div className="flex items-start gap-2">
        <span className="t-2 mt-2.5 transition-colors duration-300 group-hover:text-[var(--c-text)]">{BIG_ICONS[icon]}</span>
        <span className="t-1 whitespace-nowrap text-[56px] font-light leading-none tracking-tight tabular-nums">
          {display ?? Math.round(counted).toLocaleString()}
        </span>
      </div>
      <span className="t-2 whitespace-nowrap text-[12px] font-medium">{label}</span>
    </div>
  )
}

export default function StatsRow() {
  const { lang } = useLang()
  const { data } = useHome()
  const s = data?.stats

  const accuracy = s?.accuracy.value ?? 0
  const sprint = useCountUp(accuracy, 1300, 2)

  const pills: Pill[] = [
    { key: 'leagues', label: pick(lang, s?.leagues.label, s?.leagues.labelEn), value: s?.leagues.value ?? 0, variant: 'dark', sub: pick(lang, s?.leagues.sub, s?.leagues.subEn) },
    { key: 'teams', label: pick(lang, s?.teams.label, s?.teams.labelEn), value: s?.teams.value ?? 0, variant: 'yellow', sub: pick(lang, s?.teams.sub, s?.teams.subEn) },
    { key: 'models', label: pick(lang, s?.models.label, s?.models.labelEn), value: s?.models.value ?? 0, variant: 'light', sub: pick(lang, s?.models.sub, s?.models.subEn) },
  ]

  const bigs = [
    { key: 'matches', icon: 'trophy' as const, label: pick(lang, s?.matches.label, s?.matches.labelEn), value: s?.matches.value ?? 0 },
    { key: 'players', icon: 'players' as const, label: pick(lang, s?.players.label, s?.players.labelEn), value: s?.players.value ?? 0 },
    { key: 'records', icon: 'records' as const, label: pick(lang, s?.records.label, s?.records.labelEn), value: s?.records.value ?? 0, display: s ? fmtCompact(lang, s.records.value) : undefined },
  ]

  return (
    <div className="mt-2 flex items-end justify-between">
      <div className="flex items-end gap-10">
        {pills.map((p, i) => (
          <StatPill key={p.key} data={p} delay={i * 90} />
        ))}

        {/* 预测准确率：斜纹刻度条 + 滑块 */}
        <div className="anim-in flex w-[300px] flex-col items-start gap-1.5" style={{ '--d': '180ms' } as React.CSSProperties}>
          <span className="t-2 text-[12px] font-medium">
            {pick(lang, s?.accuracy.label, s?.accuracy.labelEn)}
            {s ? <span className="t-3 ml-2 font-normal">{pick(lang, s.accuracy.sub, s.accuracy.subEn)}</span> : null}
          </span>
          <div className="hatch-bar glass-soft relative flex h-[37px] w-full items-center overflow-hidden rounded-full px-1.5">
            <span
              className="glass t-1 rounded-full px-4 py-1.5 text-[13px] font-semibold tabular-nums transition-all duration-700"
              style={{ marginLeft: `${Math.min(52, (sprint / 100) * 100)}%` }}
            >
              {s ? `${sprint.toFixed(2)}%` : '—'}
            </span>
          </div>
        </div>
      </div>

      <div className="flex items-start gap-10 pr-2">
        {bigs.map((b, i) => (
          <BigStat key={b.key} icon={b.icon} label={b.label} value={b.value} display={b.display} delay={i * 120} />
        ))}
      </div>
    </div>
  )
}
