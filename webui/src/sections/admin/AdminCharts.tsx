import { useMemo, useState } from 'react'
import { Activity, Target, Trophy, Users } from 'lucide-react'
import { fmtCompact, fmtNum, pick, useAdmin } from '../../data/live'
import { useCountUp } from '../../hooks/useCountUp'
import { useLang, type I18nKey } from '../../i18n'

/* ---------------- KPI 卡片（真实库内规模） ---------------- */

const KPI_ICONS: Record<string, React.ReactNode> = {
  matches: <Trophy size={17} strokeWidth={2.2} />,
  players: <Users size={17} strokeWidth={2.2} />,
  events: <Activity size={17} strokeWidth={2.2} />,
  predictions: <Target size={17} strokeWidth={2.2} />,
}

export function KpiCard({
  kpi,
  delay,
}: {
  kpi: { id: string; value: number; unit: string; unitEn: string; delta: string; sub: string; subEn: string }
  delay: number
}) {
  const { lang, t } = useLang()
  const value = useCountUp(kpi.value, 1300, 0)
  const shown = kpi.value >= 100000 ? fmtCompact(lang, value) : Math.round(value).toLocaleString()

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': `${delay}ms` } as React.CSSProperties}>
      <div className="flex items-center justify-between">
        <span className="glass-soft t-1 flex h-9 w-9 items-center justify-center rounded-xl">{KPI_ICONS[kpi.id]}</span>
        <span className="rounded-full bg-[#B8D4A8]/50 px-2.5 py-1 text-[11px] font-semibold tabular-nums text-[#3E5B2E]">
          {kpi.delta}
        </span>
      </div>
      <p className="t-1 mt-4 text-[38px] font-light leading-none tracking-tight tabular-nums">
        {shown}
        <span className="t-2 ml-1 text-[16px] font-medium">{pick(lang, kpi.unit, kpi.unitEn)}</span>
      </p>
      <p className="t-2 mt-1.5 text-[12px] font-medium">
        {t(`admin.kpi.${kpi.id}` as I18nKey)} · <span className="t-3">{pick(lang, kpi.sub, kpi.subEn)}</span>
      </p>
    </div>
  )
}

/* ---------------- 入库趋势（近 12 个月，可悬停） ---------------- */

export function IngestTrendChart() {
  const { lang, t } = useLang()
  const { data } = useAdmin()
  const labels = data?.trend.labels ?? []
  const data_ = data?.trend.values ?? []
  const finished = data?.trend.finished ?? []
  const W = 560
  const H = 220
  const PAD = { t: 18, r: 12, b: 26, l: 34 }
  const min = data_.length ? Math.max(0, Math.min(...data_) - 8) : 0
  const max = data_.length ? Math.max(...data_) + 8 : 10
  const x = (i: number) => PAD.l + (i / Math.max(1, data_.length - 1)) * (W - PAD.l - PAD.r)
  const y = (v: number) => PAD.t + (1 - (v - min) / Math.max(1, max - min)) * (H - PAD.t - PAD.b)
  const [hover, setHover] = useState<number | null>(null)

  const { line, area, len } = useMemo(() => {
    if (!data_.length) return { line: '', area: '', len: 0 }
    const pts = data_.map((v, i) => [x(i), y(v)] as const)
    let d = `M ${pts[0][0]} ${pts[0][1]}`
    for (let i = 0; i < pts.length - 1; i++) {
      const p0 = pts[Math.max(0, i - 1)]
      const p1 = pts[i]
      const p2 = pts[i + 1]
      const p3 = pts[Math.min(pts.length - 1, i + 2)]
      d += ` C ${p1[0] + (p2[0] - p0[0]) / 6} ${p1[1] + (p2[1] - p0[1]) / 6}, ${p2[0] - (p3[0] - p1[0]) / 6} ${
        p2[1] - (p3[1] - p1[1]) / 6
      }, ${p2[0]} ${p2[1]}`
    }
    const areaPath = `${d} L ${pts[pts.length - 1][0]} ${H - PAD.b} L ${pts[0][0]} ${H - PAD.b} Z`
    let length = 0
    for (let i = 0; i < pts.length - 1; i++) length += Math.hypot(pts[i + 1][0] - pts[i][0], pts[i + 1][1] - pts[i][1])
    return { line: d, area: areaPath, len: Math.ceil(length * 1.2) }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data_])

  const onMove = (e: React.MouseEvent<SVGSVGElement>) => {
    if (!data_.length) return
    const rect = e.currentTarget.getBoundingClientRect()
    const px = ((e.clientX - rect.left) / rect.width) * W
    let best = 0
    let bestDist = Infinity
    data_.forEach((_, i) => {
      const d = Math.abs(x(i) - px)
      if (d < bestDist) {
        bestDist = d
        best = i
      }
    })
    setHover(best)
  }

  const gridVals = [Math.round(min), Math.round((min + max) / 2), Math.round(max)]

  return (
    <div className="glass card-hover anim-in flex flex-col rounded-[28px] p-5" style={{ '--d': '120ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 text-[15px] font-semibold">{t('admin.trend.title')}</span>
        <span className="t-3 text-[11px] font-medium">
          {data ? `${data.trend.caption} · ${pick(lang, '月度', 'monthly')}` : ''}
        </span>
      </div>
      <div className="relative mt-2">
        {data_.length ? (
          <svg viewBox={`0 0 ${W} ${H}`} className="w-full" onMouseMove={onMove} onMouseLeave={() => setHover(null)}>
            <defs>
              <linearGradient id="va-fill" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#F6C945" stopOpacity="0.45" />
                <stop offset="100%" stopColor="#F6C945" stopOpacity="0.02" />
              </linearGradient>
            </defs>
            {gridVals.map((v) => (
              <g key={v}>
                <line x1={PAD.l} x2={W - PAD.r} y1={y(v)} y2={y(v)} stroke="var(--c-line)" strokeDasharray="3 5" />
                <text x={PAD.l - 6} y={y(v) + 3} textAnchor="end" fontSize="9" fill="var(--c-faint)" fontWeight={500}>
                  {v}
                </text>
              </g>
            ))}
            {data_.map((_, i) => (
              <text key={i} x={x(i)} y={H - 8} textAnchor="middle" fontSize="9" fill="var(--c-faint)" fontWeight={500}>
                {i % 3 === 0 || i === data_.length - 1 ? (labels[i] ?? '').slice(2) : ''}
              </text>
            ))}
            <path d={area} fill="url(#va-fill)" className="fade-slow" style={{ '--d': '600ms' } as React.CSSProperties} />
            <path
              d={line}
              fill="none"
              stroke="#F6C945"
              strokeWidth={2.5}
              strokeLinecap="round"
              className="draw-line"
              style={{ '--path-len': len, '--d': '200ms' } as React.CSSProperties}
            />
            {hover !== null && (
              <g>
                <line
                  x1={x(hover)}
                  x2={x(hover)}
                  y1={PAD.t}
                  y2={H - PAD.b}
                  stroke="var(--c-muted)"
                  strokeWidth={1}
                  strokeDasharray="3 3"
                />
                <circle cx={x(hover)} cy={y(data_[hover])} r={5} fill="#F6C945" stroke="var(--c-bg)" strokeWidth={2.5} />
              </g>
            )}
          </svg>
        ) : (
          <div className="skeleton h-[200px] w-full rounded-2xl" />
        )}
        {hover !== null && data_.length > 0 && (
          <div
            className="glass-dark pointer-events-none absolute rounded-xl px-3 py-1.5 text-center"
            style={{
              left: `${(x(hover) / W) * 100}%`,
              top: `${(y(data_[hover]) / H) * 100}%`,
              transform: 'translate(-50%, -130%)',
            }}
          >
            <p className="on-ink text-[13px] font-bold tabular-nums">
              {data_[hover].toLocaleString()} {pick(lang, '场', 'matches')}
            </p>
            <p className="text-[9px] font-medium text-[#B3AD97]">
              {labels[hover]} · {pick(lang, '已完赛', 'finished')} {finished[hover] ?? 0}
            </p>
          </div>
        )}
      </div>
    </div>
  )
}

/* ---------------- 数据分布（环形图，真实记录类型） ---------------- */

const DONUT_COLORS = ['#F6C945', '#2B2B27', '#A8C5E2', '#8a8672']

export function DataDonut() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const dist = data?.distribution ?? []
  const total = dist.reduce((s, d) => s + d.count, 0) || 1
  const R = 52
  const C = 2 * Math.PI * R
  const [hover, setHover] = useState<number | null>(null)
  let acc = 0

  return (
    <div className="glass card-hover anim-in flex flex-col rounded-[28px] p-5" style={{ '--d': '200ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 text-[15px] font-semibold">{pick(lang, '数据分布', 'Data Distribution')}</span>
        <span className="t-3 text-[11px] font-medium">{pick(lang, '按记录类型', 'by record type')}</span>
      </div>
      <div className="mt-3 flex flex-1 items-center gap-5">
        <div className="relative h-[148px] w-[148px] shrink-0">
          <svg viewBox="0 0 132 132" className="h-full w-full -rotate-90">
            {dist.map((d, i) => {
              const frac = d.count / total
              const dash = frac * C
              const offset = acc
              acc += dash
              return (
                <circle
                  key={d.key}
                  cx={66}
                  cy={66}
                  r={R}
                  fill="none"
                  stroke={DONUT_COLORS[i % DONUT_COLORS.length]}
                  strokeWidth={hover === i ? 20 : 15}
                  strokeDasharray={`${Math.max(dash - 2.5, 1)} ${C - Math.max(dash - 2.5, 1)}`}
                  strokeDashoffset={-offset}
                  strokeLinecap="round"
                  className="cursor-pointer transition-all duration-300"
                  style={{ opacity: hover === null || hover === i ? 1 : 0.35 }}
                  onMouseEnter={() => setHover(i)}
                  onMouseLeave={() => setHover(null)}
                />
              )
            })}
          </svg>
          <div className="absolute inset-0 flex flex-col items-center justify-center">
            <span className="t-1 text-[20px] font-medium leading-none tabular-nums">
              {fmtCompact(lang, hover !== null ? dist[hover].count : total)}
            </span>
            <span className="t-3 mt-1 max-w-[100px] text-center text-[9px] font-medium leading-tight">
              {hover !== null ? pick(lang, dist[hover].label, dist[hover].labelEn) : pick(lang, '总记录', 'total')}
            </span>
          </div>
        </div>
        <ul className="flex-1 space-y-3">
          {dist.map((d, i) => (
            <li
              key={d.key}
              className="cursor-pointer transition-opacity duration-300"
              style={{ opacity: hover === null || hover === i ? 1 : 0.4 }}
              onMouseEnter={() => setHover(i)}
              onMouseLeave={() => setHover(null)}
            >
              <div className="flex items-center gap-2">
                <span className="h-2.5 w-2.5 rounded-full" style={{ backgroundColor: DONUT_COLORS[i % DONUT_COLORS.length] }} />
                <span className="t-2 flex-1 truncate text-[12px] font-medium">{pick(lang, d.label, d.labelEn)}</span>
                <span className="t-1 text-[12px] font-semibold tabular-nums">{fmtCompact(lang, d.count)}</span>
              </div>
              <div className="track-c ml-[18px] mt-1 h-[5px] overflow-hidden rounded-full">
                <div
                  className="bar-grow-x h-full rounded-full"
                  style={
                    {
                      width: `${(d.count / total) * 100}%`,
                      backgroundColor: DONUT_COLORS[i % DONUT_COLORS.length],
                      '--d': `${400 + i * 90}ms`,
                    } as React.CSSProperties
                  }
                />
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  )
}

/* ---------------- 数据管道（漏斗，真实表规模） ---------------- */

export function PipelineFunnel() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const pipeline = data?.pipeline ?? []
  const max = pipeline[0]?.value ?? 1
  const [hover, setHover] = useState<number | null>(null)
  const shown = useCountUp(max, 900)

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '280ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 text-[15px] font-semibold">{pick(lang, '数据管道', 'Data Pipeline')}</span>
        <span className="t-3 text-[11px] font-medium">{pick(lang, '明细 → 预测', 'raw → predictions')}</span>
      </div>
      <div className="mt-4 space-y-3">
        {pipeline.map((stage, i) => {
          const pct = (stage.value / max) * 100
          return (
            <div key={stage.key} className="group cursor-pointer" onMouseEnter={() => setHover(i)} onMouseLeave={() => setHover(null)}>
              <div className="mb-1 flex items-baseline justify-between">
                <span className="t-2 text-[11px] font-medium">{pick(lang, stage.label, stage.labelEn)}</span>
                <span className="t-1 text-[11px] font-semibold tabular-nums">
                  {fmtNum(Math.round((stage.value / max) * shown))}
                </span>
              </div>
              <div className="track-c h-[26px] overflow-hidden rounded-full">
                <div
                  className="bar-grow-x flex h-full items-center rounded-full px-3 transition-all duration-300 group-hover:brightness-110"
                  style={
                    {
                      width: `${Math.max(pct, 8)}%`,
                      '--d': `${300 + i * 110}ms`,
                      backgroundColor: hover === i ? '#F6C945' : i === 0 ? 'var(--c-text)' : '#F6C945',
                      opacity: hover === null || hover === i ? 1 : 0.45,
                    } as React.CSSProperties
                  }
                >
                  {i > 0 && (
                    <span className="text-[10px] font-semibold tabular-nums text-[#26251F]">
                      {pct < 0.1 ? pct.toFixed(2) : pct.toFixed(1)}%
                    </span>
                  )}
                </div>
              </div>
            </div>
          )
        })}
        {!pipeline.length && <div className="skeleton h-[180px] w-full rounded-2xl" />}
      </div>
    </div>
  )
}

/* ---------------- 进球数分布（真实 FT 比赛） ---------------- */

export function GoalBands() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const bands = data?.goalBands ?? []
  const max = Math.max(1, ...bands.map((b) => b.count))
  const [hover, setHover] = useState<number | null>(null)

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '340ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 text-[15px] font-semibold">{pick(lang, '总进球分布', 'Goals per match')}</span>
        <span className="t-3 text-[11px] font-medium">{pick(lang, '已完赛比赛', 'finished matches')}</span>
      </div>
      <div className="mt-4 space-y-3">
        {bands.map((band, i) => (
          <div
            key={band.band}
            className="flex cursor-pointer items-center gap-3"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          >
            <span className="t-2 w-[86px] shrink-0 text-[11px] font-medium tabular-nums">
              {band.band} {pick(lang, '球', 'goals')}
            </span>
            <div className="track-c h-[22px] flex-1 overflow-hidden rounded-full">
              <div
                className="bar-grow-x h-full rounded-full transition-all duration-300"
                style={
                  {
                    width: `${(band.count / max) * 100}%`,
                    '--d': `${300 + i * 100}ms`,
                    backgroundColor: hover === i ? '#F6C945' : 'var(--c-text)',
                    opacity: hover === null || hover === i ? 1 : 0.4,
                  } as React.CSSProperties
                }
              />
            </div>
            <span className="t-1 w-14 text-right text-[11px] font-semibold tabular-nums">
              {band.count.toLocaleString()}
            </span>
          </div>
        ))}
        {!bands.length && <div className="skeleton h-[180px] w-full rounded-2xl" />}
      </div>
    </div>
  )
}
