import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router'
import { ArrowUpRight, Pause, Play, RotateCcw } from 'lucide-react'
import { useCountUp } from '../hooks/useCountUp'
import { fmtNum, pick, useHome } from '../data/live'
import { api, type PredictionPayload } from '../lib/api'
import { useApi } from '../lib/useApi'
import { useLang } from '../i18n'

function CardHeader({ title, hint }: { title: string; hint?: string }) {
  return (
    <div className="flex items-start justify-between gap-2">
      <div className="flex flex-col">
        <span className="t-1 text-[15px] font-semibold">{title}</span>
        {hint ? <span className="t-3 mt-0.5 text-[10px] font-medium">{hint}</span> : null}
      </div>
      <button className="glass-soft flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-transform duration-300 hover:rotate-45 hover:scale-110 active:scale-95">
        <ArrowUpRight size={15} className="t-1" />
      </button>
    </div>
  )
}

/* ---------------- 射手榜（真实：Transfermarkt 完整赛季） ---------------- */

export function ActivityCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const items = data?.topScorers.items ?? []
  const total = useCountUp(items[0]?.goals ?? 0, 1300)
  const maxVal = Math.max(1, ...items.map((b) => b.goals))
  const [hovered, setHovered] = useState<number | null>(null)

  const lastName = (full: string) => {
    const parts = (full || '').split(' ')
    return parts.length > 1 ? parts.slice(1).join(' ') : full
  }

  return (
    <div className="glass card-hover anim-in flex h-[292px] flex-col rounded-[28px] p-5" style={{ '--d': '100ms' } as React.CSSProperties}>
      <CardHeader
        title={pick(lang, '射手榜', 'Top Scorers')}
        hint={data ? `${data.topScorers.season} ${pick(lang, '完整赛季 · 进球数', 'full season · goals')}` : undefined}
      />
      <div className="mt-1 flex items-baseline gap-2.5">
        <span className="t-1 text-[38px] font-medium leading-none tracking-tight tabular-nums">
          {items.length ? total.toLocaleString() : '—'}
        </span>
        <span className="t-2 whitespace-pre-line text-[11px] font-medium leading-tight">
          {pick(lang, '榜首进球\nTop 7 射手', 'Goals by leader\nTop 7 scorers')}
        </span>
      </div>
      <div className="mt-auto flex items-end justify-between px-1">
        {items.map((bar, i) => (
          <div
            key={bar.name}
            className="group relative flex flex-col items-center gap-1.5"
            onMouseEnter={() => setHovered(i)}
            onMouseLeave={() => setHovered(null)}
          >
            <span
              className={`glass-dark pointer-events-none absolute -top-9 z-10 whitespace-nowrap rounded-full px-2.5 py-1 text-[10px] font-semibold text-[#FBF6E9] transition-all duration-200 ${
                hovered === i ? 'translate-y-0 opacity-100' : 'translate-y-1 opacity-0'
              }`}
            >
              {bar.name} · {bar.goals} {lang === 'zh' ? '球' : 'g'}
            </span>
            <div
              className={`bar-grow w-[13px] rounded-full ${i === 0 ? 'bg-[#F6C945]' : ''}`}
              style={
                {
                  height: (bar.goals / maxVal) * 128,
                  '--d': `${300 + i * 70}ms`,
                  ...(i === 0 ? {} : { backgroundColor: 'var(--c-text)' }),
                } as React.CSSProperties
              }
            />
            <span className={`text-[9px] font-semibold transition-colors ${hovered === i ? 't-1' : 't-2'}`}>
              {lastName(bar.name).slice(0, 9)}
            </span>
          </div>
        ))}
        {!items.length && <div className="skeleton h-[128px] w-full rounded-2xl" />}
      </div>
    </div>
  )
}

/* ---------------- 预测准确率（环形仪表盘） ---------------- */

function AccuracyRing({ progress, label, mode }: { progress: number; label: string; mode: string }) {
  const size = 148
  const center = size / 2
  const ringR = 56
  const circumference = 2 * Math.PI * ringR
  const ticks = Array.from({ length: 60 })
  return (
    <div className="relative" style={{ width: size, height: size }}>
      <svg width={size} height={size}>
        {ticks.map((_, i) => {
          const angle = (i / ticks.length) * Math.PI * 2 - Math.PI / 2
          const r1 = ringR + 8
          const r2 = ringR + (i % 5 === 0 ? 15 : 12)
          return (
            <line
              key={i}
              x1={center + r1 * Math.cos(angle)}
              y1={center + r1 * Math.sin(angle)}
              x2={center + r2 * Math.cos(angle)}
              y2={center + r2 * Math.sin(angle)}
              stroke={i / ticks.length <= progress ? '#E3B53C' : 'var(--c-hatch)'}
              strokeWidth={1.6}
              className="transition-colors duration-500"
            />
          )
        })}
        <circle cx={center} cy={center} r={ringR} fill="none" stroke="var(--track)" strokeWidth={9} />
        <circle
          cx={center}
          cy={center}
          r={ringR}
          fill="none"
          stroke="#F6C945"
          strokeWidth={9}
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={circumference * (1 - progress)}
          transform={`rotate(-90 ${center} ${center})`}
          style={{ transition: 'stroke-dashoffset 0.1s linear' }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="t-1 text-[26px] font-medium leading-none tracking-tight tabular-nums">{label}</span>
        <span className="t-2 mt-1.5 max-w-[110px] text-center text-[10px] font-medium leading-tight">{mode}</span>
      </div>
    </div>
  )
}

export function FocusTimerCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const [progress, setProgress] = useState(0)
  const [running, setRunning] = useState(false)
  const target = (data?.stats.accuracy.value ?? 0) / 100
  const raf = useRef<number | null>(null)

  const replay = () => {
    if (raf.current !== null) cancelAnimationFrame(raf.current)
    setRunning(true)
    setProgress(0)
    const start = performance.now()
    const dur = 1600
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / dur)
      const eased = 1 - Math.pow(1 - p, 3)
      setProgress(target * eased)
      if (p < 1) raf.current = requestAnimationFrame(tick)
      else {
        raf.current = null
        setRunning(false)
      }
    }
    raf.current = requestAnimationFrame(tick)
  }

  // 数据是异步到的：target 从 0 变成真实值后再跑一次动画（否则环永远停在 0.00%）
  useEffect(() => {
    if (target <= 0) return
    const timer = setTimeout(replay, 250)
    return () => clearTimeout(timer)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [target])

  useEffect(() => () => { if (raf.current !== null) cancelAnimationFrame(raf.current) }, [])

  const acc = data?.stats.accuracy
  return (
    <div className="glass card-hover anim-in flex h-[292px] flex-col rounded-[28px] p-5" style={{ '--d': '180ms' } as React.CSSProperties}>
      <CardHeader
        title={pick(lang, '预测准确率', 'Model Accuracy')}
        hint={acc ? pick(lang, acc.sub, acc.subEn) : undefined}
      />
      <div className="flex flex-1 items-center justify-center">
        <div className={running ? 'ring-running' : ''}>
          <AccuracyRing
            progress={progress}
            label={acc ? `${(progress * 100).toFixed(2)}%` : '—'}
            mode={acc ? `${acc.sub?.split(' · ')[0] ?? ''}` : ''}
          />
        </div>
      </div>
      <div className="flex items-center gap-3">
        <button
          onClick={replay}
          className="glass-soft flex h-10 w-10 items-center justify-center rounded-full transition-transform duration-300 hover:scale-110 active:scale-90"
          aria-label="replay"
        >
          <Play size={15} className="t-1 ml-0.5" fill="currentColor" />
        </button>
        <button className="glass-soft flex h-10 w-10 items-center justify-center rounded-full opacity-60 transition-transform duration-300 hover:scale-110 active:scale-90">
          <Pause size={15} className="t-1" fill="currentColor" />
        </button>
        <span className="t-3 ml-1 text-[10px] font-medium leading-tight">
          {lang === 'zh' ? '样本外评估\n概率校准已启用' : 'Out-of-sample\ncalibrated'}
        </span>
        <button
          onClick={replay}
          className="bg-ink ml-auto flex h-11 w-11 items-center justify-center rounded-full shadow-lg shadow-black/25 transition-transform duration-500 hover:-rotate-180 hover:scale-110 active:scale-90"
          aria-label="restart"
        >
          <RotateCcw size={16} className="on-ink" />
        </button>
      </div>
    </div>
  )
}

/* ---------------- 预测可信度 ---------------- */

/**
 * 预测可信度卡（口径说明 + 两个关键指标）
 * 「命中率」= 全部已评估预测（含历史回测）命中比例；
 * 「准确率」= 生产模型的样本外（out-of-sample）评估准确率。两者样本不同，必须分开展示。
 */
export function PredictionTrustCard() {
  const { lang } = useLang()
  const { data } = useHome()
  const { data: pred } = useApi<PredictionPayload>(() => api.predictions({ size: 1 }), 'predictions:trust')
  const acc = data?.stats?.accuracy
  const models = data?.stats?.models

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '220ms' } as React.CSSProperties}>
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <span className="t-1 text-[15px] font-semibold">{pick(lang, '预测可信度', 'Prediction quality')}</span>
          <p className="t-3 mt-0.5 text-[10px] font-medium">{pick(lang, '两类指标的样本不同，分开展示', 'Two metrics, two samples')}</p>
        </div>
      </div>

      <div className="mt-3.5 space-y-3">
        <div>
          <div className="flex items-baseline justify-between gap-2">
            <span className="t-2 text-[11.5px] font-medium">{pick(lang, '命中率（全部已评估）', 'Hit rate (evaluated)')}</span>
            <span className="t-1 text-[22px] font-light leading-none tabular-nums">
              {pred ? `${pred.hitRate.toFixed(1)}%` : '—'}
            </span>
          </div>
          <p className="t-3 mt-1 text-[10px] font-medium tabular-nums">
            {pred ? `${fmtNum(pred.evaluated)} ${pick(lang, '条含实际结果', 'with result')}` : ''}
          </p>
        </div>

        <div className="hairline-t pt-3">
          <div className="flex items-baseline justify-between gap-2">
            <span className="t-2 text-[11.5px] font-medium">{pick(lang, '准确率（样本外）', 'Accuracy (out-of-sample)')}</span>
            <span className="t-1 text-[22px] font-light leading-none tabular-nums">
              {acc ? `${acc.value.toFixed(acc.decimals ?? 2)}%` : '—'}
            </span>
          </div>
          <p className="t-3 mt-1 text-[10px] font-medium">{acc ? acc.sub : ''}</p>
        </div>
      </div>

      <Link
        to="/predictions"
        className="glass-soft mt-4 flex items-center justify-between rounded-full px-3.5 py-2 text-[11.5px] font-semibold transition hover:brightness-105"
      >
        <span>{pick(lang, '查看全部预测', 'All predictions')}</span>
        <span className="t-3 tabular-nums">
          {models ? `${models.value} ${pick(lang, '个模型版本', 'model versions')}` : '→'}
        </span>
      </Link>
    </div>
  )
}
