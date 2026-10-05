import { AlertTriangle, CheckCircle2, Database, Trophy } from 'lucide-react'
import { fmtCompact, fmtNum, pick, useAdmin } from '../../data/live'
import { useLang } from '../../i18n'

/* ---------------- 数据质量检查 ---------------- */

export function QualityChecks() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const checks = data?.checks ?? []

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '440ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 text-[15px] font-semibold">{pick(lang, '数据质量检查', 'Data quality checks')}</span>
        <span className="t-3 text-[11px] font-medium">
          {checks.length ? `${checks.filter((c) => c.status === 'ok').length}/${checks.length} ${pick(lang, '通过', 'passed')}` : ''}
        </span>
      </div>
      <ul className="line-c mt-2 divide-y">
        {checks.map((c) => {
          const ok = c.status === 'ok'
          return (
            <li key={c.name} className="flex items-start gap-3 py-3">
              <span
                className={`mt-0.5 flex h-7 w-7 shrink-0 items-center justify-center rounded-full ${
                  ok ? 'bg-[#B8D4A8]/45 text-[#3E5B2E]' : 'bg-[#F6C945]/35 text-[#8A6413]'
                }`}
              >
                {ok ? <CheckCircle2 size={14} strokeWidth={2.4} /> : <AlertTriangle size={14} strokeWidth={2.4} />}
              </span>
              <div className="min-w-0 flex-1">
                <p className="t-1 text-[13px] font-semibold">{pick(lang, c.name, c.nameEn)}</p>
                <p className="t-3 mt-0.5 text-[11px] font-medium tabular-nums">{pick(lang, c.note, c.noteEn)}</p>
              </div>
            </li>
          )
        })}
        {!checks.length && <div className="skeleton my-3 h-40 w-full rounded-2xl" />}
      </ul>
    </div>
  )
}

/* ---------------- 数据库表规模 ---------------- */

export function DatabaseTablesCard() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const db = data?.dbTables
  const items = (db?.items ?? []).slice(0, 8)
  const max = Math.max(1, ...items.map((i) => i.rows))

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '480ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 flex items-center gap-2 text-[15px] font-semibold">
          <Database size={15} className="t-2" />
          {pick(lang, '数据库表规模', 'Table sizes')}
        </span>
        <span className="t-3 text-[11px] font-medium tabular-nums">
          {db ? `${db.total} ${pick(lang, '张表 · ', 'tables · ')}${fmtCompact(lang, db.records)} ${pick(lang, '条记录', 'rows')}` : ''}
        </span>
      </div>
      <div className="mt-3 space-y-2.5">
        {items.map((t, i) => (
          <div key={t.name} className="group cursor-pointer">
            <div className="flex items-baseline justify-between">
              <span className="t-2 truncate font-mono text-[11px] font-medium" title={t.name}>
                {t.name}
              </span>
              <span className="t-1 ml-2 shrink-0 text-[11px] font-semibold tabular-nums">{fmtNum(t.rows)}</span>
            </div>
            <div className="track-c mt-1 h-[6px] overflow-hidden rounded-full">
              <div
                className="bar-grow-x h-full rounded-full transition-all duration-300 group-hover:brightness-105"
                style={
                  {
                    width: `${(t.rows / max) * 100}%`,
                    '--d': `${500 + i * 70}ms`,
                    backgroundColor: i % 2 === 0 ? '#F6C945' : 'var(--c-text)',
                  } as React.CSSProperties
                }
              />
            </div>
          </div>
        ))}
        {!items.length && <div className="skeleton h-[200px] w-full rounded-2xl" />}
      </div>
    </div>
  )
}

/* ---------------- 联赛统计 ---------------- */

/** 后端可能给 null（样本太少的联赛算不出均值）→ 统一走这个格式化 */
const num = (v: number | null | undefined, digits = 2) =>
  v === null || v === undefined || Number.isNaN(v) ? '—' : v.toFixed(digits)

export function LeagueStatsCard() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const rows = data?.leagueStats ?? []

  return (
    <div className="glass card-hover anim-in rounded-[28px] p-5" style={{ '--d': '520ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="t-1 flex items-center gap-2 text-[15px] font-semibold">
          <Trophy size={15} className="t-2" />
          {pick(lang, '联赛统计', 'League statistics')}
        </span>
        <span className="t-3 text-[11px] font-medium">
          {rows.length ? `${rows.length} ${pick(lang, '个联赛 · 主客平比例与场均数据', 'leagues · outcome split & per-game')}` : ''}
        </span>
      </div>
      <table className="mt-3 w-full border-collapse">
        <thead>
          <tr className="t-3 border-b border-[var(--c-line)] text-left text-[10px] font-semibold uppercase tracking-wider">
            <th className="pb-2 pr-3">{pick(lang, '联赛', 'League')}</th>
            <th className="pb-2 pr-3">{pick(lang, '赛季', 'Season')}</th>
            <th className="pb-2 pr-3 text-right">{pick(lang, '场次', 'Matches')}</th>
            <th className="pb-2 pr-3 text-right">{pick(lang, '球队', 'Teams')}</th>
            <th className="pb-2 pr-3 text-right">{pick(lang, '场均进球', 'Goals/g')}</th>
            <th className="pb-2 pr-3 text-right">{pick(lang, '场均 xG', 'xG/g')}</th>
            <th className="pb-2 text-right">{pick(lang, '主 / 平 / 客', 'H / D / A')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((lg) => (
            <tr key={lg.id} className="table-row border-b border-[var(--c-line)] last:border-0">
              <td className="t-1 py-2.5 pr-3 text-[12px] font-semibold">{pick(lang, lg.name, lg.nameEn)}</td>
              <td className="t-3 py-2.5 pr-3 text-[11px] font-medium tabular-nums">{lg.season}</td>
              <td className="t-2 py-2.5 pr-3 text-right text-[12px] font-medium tabular-nums">{fmtNum(lg.matches ?? 0)}</td>
              <td className="t-3 py-2.5 pr-3 text-right text-[11px] font-medium tabular-nums">{lg.teams ?? 0}</td>
              <td className="t-1 py-2.5 pr-3 text-right text-[12px] font-semibold tabular-nums">{num(lg.goalsPg)}</td>
              <td className="t-2 py-2.5 pr-3 text-right text-[12px] font-medium tabular-nums">{num(lg.xgPg)}</td>
              <td className="py-2.5 text-right text-[11px] font-medium tabular-nums">
                <span className="rounded-full bg-[#F6C945]/35 px-2 py-0.5">{num(lg.homeWinPct, 1)}%</span>
                <span className="t-3 mx-1">/</span>
                <span className="rounded-full bg-[var(--track)] px-2 py-0.5">{num(lg.drawPct, 1)}%</span>
                <span className="t-3 mx-1">/</span>
                <span className="rounded-full bg-[#A8C5E2]/35 px-2 py-0.5">{num(lg.awayWinPct, 1)}%</span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!rows.length && <div className="skeleton mt-3 h-40 w-full rounded-2xl" />}
    </div>
  )
}
