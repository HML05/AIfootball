/**
 * 通用页面外壳与小组件（所有二级页面共用 → 保证版式、圆角、字号、间距一致）。
 *
 * 用法：
 *   <PageShell title={pick(lang,'联赛数据','Leagues')} subtitle="…" activePath="/leagues" right={…}>
 *     <SectionCard title="…" hint="…"> … </SectionCard>
 *   </PageShell>
 */
import type { CSSProperties, ReactNode } from 'react'
import { ChevronLeft, ChevronRight, Search } from 'lucide-react'
import TopNav from '../sections/TopNav'
import { Blobs } from '../pages/Home'
import { pick, fmtNum } from '../data/live'
import { useLang } from '../i18n'

/* ---------------- 页面外壳 ---------------- */

export function PageShell({
  title,
  subtitle,
  activePath,
  right,
  children,
}: {
  title: string
  subtitle?: string
  activePath: string
  right?: ReactNode
  children: ReactNode
}) {
  return (
    <div className="font-sans-talvex relative min-h-screen overflow-x-hidden">
      <Blobs />
      <div className="relative mx-auto max-w-[1400px] px-6 py-5 pb-24">
        <TopNav activePath={activePath} />
        <div
          className="anim-in mt-7 flex flex-wrap items-end justify-between gap-4"
          style={{ '--d': '40ms' } as CSSProperties}
        >
          <div className="flex flex-col">
            <h1 className="t-1 text-[46px] font-medium leading-none tracking-[-0.03em]">{title}</h1>
            {subtitle ? <p className="t-3 mt-2 text-[12px] font-medium tabular-nums">{subtitle}</p> : null}
          </div>
          {right ? <div className="flex flex-wrap items-center gap-2">{right}</div> : null}
        </div>
        {children}
      </div>
    </div>
  )
}

/* ---------------- 卡片 ---------------- */

export function SectionCard({
  title,
  hint,
  right,
  dark = false,
  className = '',
  bodyClass = '',
  children,
}: {
  title?: string
  hint?: string
  right?: ReactNode
  dark?: boolean
  className?: string
  bodyClass?: string
  children: ReactNode
}) {
  return (
    <section
      className={`${dark ? 'glass-dark' : 'glass'} card-hover anim-in rounded-[28px] p-5 ${className}`}
      style={{ '--d': '120ms' } as CSSProperties}
    >
      {title ? (
        <header className="mb-4 flex items-start justify-between gap-3">
          <div className="flex flex-col">
            <h2 className={`text-[15px] font-semibold ${dark ? 'on-ink' : 't-1'}`}>{title}</h2>
            {hint ? (
              <span className={`mt-0.5 text-[10px] font-medium ${dark ? 'on-ink opacity-60' : 't-3'}`}>{hint}</span>
            ) : null}
          </div>
          {right ? <div className="flex shrink-0 items-center gap-2">{right}</div> : null}
        </header>
      ) : null}
      <div className={bodyClass}>{children}</div>
    </section>
  )
}

/* ---------------- 小徽标 / 进度条 ---------------- */

export type Tone = 'yellow' | 'blue' | 'pink' | 'ink' | 'muted' | 'green'

const TONE_CLASS: Record<Tone, string> = {
  yellow: 'bg-[#F6C945]/45 text-[#6b4d05]',
  blue: 'bg-[#A8C5E2]/45 text-[#274b6d]',
  pink: 'bg-[#E8B4B8]/45 text-[#7a3540]',
  ink: 'bg-ink text-white',
  muted: 'bg-[var(--track)] t-2',
  green: 'bg-[#9FD6A8]/50 text-[#255a30]',
}

export function Pill({ children, tone = 'muted', className = '' }: { children: ReactNode; tone?: Tone; className?: string }) {
  return (
    <span className={`rounded-full px-2.5 py-1 text-[10.5px] font-semibold tabular-nums ${TONE_CLASS[tone]} ${className}`}>
      {children}
    </span>
  )
}

export function Bar({
  value,
  max,
  tone = 'yellow',
  height = 7,
  className = '',
}: {
  value: number | null | undefined
  max?: number
  tone?: Tone
  height?: number
  className?: string
}) {
  const v = value ?? 0
  const top = max && max > 0 ? max : Math.max(v, 1)
  const w = Math.max(2, Math.min(100, (v / top) * 100))
  const fill =
    tone === 'ink' ? 'bg-ink' : tone === 'blue' ? 'bg-[#A8C5E2]' : tone === 'pink' ? 'bg-[#E8B4B8]' : tone === 'muted' ? 't-3 bg-current opacity-40' : 'bg-[#F6C945]'
  return (
    <span className={`block w-full overflow-hidden rounded-full bg-[var(--track)] ${className}`} style={{ height }}>
      <span className={`block h-full rounded-full transition-[width] duration-700 ease-out ${fill}`} style={{ width: `${w}%` }} />
    </span>
  )
}

/* ---------------- 分页 / 搜索 / 页签 ---------------- */

export function Pager({
  page,
  pages,
  total,
  onPage,
  unit,
}: {
  page: number
  pages: number
  total: number
  onPage: (p: number) => void
  unit?: string
}) {
  const { lang } = useLang()
  const last = Math.max(1, pages)
  const btn = 'glass-soft flex h-9 w-9 items-center justify-center rounded-full transition-transform duration-300 hover:scale-110 active:scale-90 disabled:opacity-35 disabled:hover:scale-100'
  return (
    <div className="mt-4 flex items-center justify-between gap-3">
      <span className="t-3 text-[11px] font-medium tabular-nums">
        {fmtNum(total)} {unit ?? pick(lang, '条', 'records')} · {pick(lang, '第', 'page')} {page} / {last}
      </span>
      <div className="flex items-center gap-2">
        <button className={btn} disabled={page <= 1} onClick={() => onPage(page - 1)} aria-label="prev">
          <ChevronLeft size={15} className="t-1" />
        </button>
        <button className={btn} disabled={page >= last} onClick={() => onPage(page + 1)} aria-label="next">
          <ChevronRight size={15} className="t-1" />
        </button>
      </div>
    </div>
  )
}

export function SearchBox({
  value,
  onChange,
  placeholder,
  status,
  className = '',
}: {
  value: string
  onChange: (v: string) => void
  placeholder: string
  status?: ReactNode
  className?: string
}) {
  return (
    <div className={`glass-soft flex items-center gap-2 rounded-full px-4 py-2 ${className}`}>
      <Search size={14} className="t-3 shrink-0" />
      <input
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="t-1 w-full min-w-[120px] bg-transparent text-[12.5px] font-medium outline-none placeholder:opacity-45"
      />
      {status}
    </div>
  )
}

export function Tabs({
  items,
  value,
  onChange,
}: {
  items: { key: string; label: string }[]
  value: string
  onChange: (k: string) => void
}) {
  return (
    <div className="glass-soft flex items-center gap-1 rounded-full p-1">
      {items.map((it) => (
        <button
          key={it.key}
          onClick={() => onChange(it.key)}
          className={`rounded-full px-3.5 py-1.5 text-[11.5px] font-semibold transition-all duration-300 ${
            value === it.key ? 'bg-ink text-white shadow-sm' : 't-2 hover:bg-white/45'
          }`}
        >
          {it.label}
        </button>
      ))}
    </div>
  )
}

/* ---------------- 状态块 ---------------- */

export function EmptyState({ text }: { text: string }) {
  return (
    <div className="t-3 flex flex-col items-center justify-center gap-2 py-10 text-[12px] font-medium">
      <span className="glass-soft flex h-12 w-12 items-center justify-center rounded-full text-[18px]">—</span>
      {text}
    </div>
  )
}

export function ErrorState({ text }: { text: string }) {
  return (
    <div className="glass flex items-center gap-3 rounded-[24px] p-4 text-[12px] font-medium">
      <span className="flex h-8 w-8 items-center justify-center rounded-full bg-[#E8B4B8]/50 text-[#7a3540]">!</span>
      <span className="t-2">{text}</span>
    </div>
  )
}

/* ---------------- 指标小条 ---------------- */

export function KpiStrip({
  items,
  className = '',
}: {
  items: { label: string; value: string; sub?: string }[]
  className?: string
}) {
  return (
    <div className={`grid gap-4 ${className}`} style={{ gridTemplateColumns: `repeat(${Math.max(1, items.length)}, minmax(0, 1fr))` }}>
      {items.map((it) => (
        <div key={it.label} className="glass card-hover anim-in rounded-[24px] px-5 py-4">
          <p className="t-3 text-[10.5px] font-semibold uppercase tracking-wide">{it.label}</p>
          <p className="t-1 mt-1.5 text-[26px] font-medium leading-none tabular-nums">{it.value}</p>
          {it.sub ? <p className="t-3 mt-1.5 text-[10.5px] font-medium">{it.sub}</p> : null}
        </div>
      ))}
    </div>
  )
}
