import { useMemo, useState } from 'react'
import { Area, AreaChart, CartesianGrid, Line, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PageShell, SectionCard, Pill, Bar, SearchBox, KpiStrip, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { useLang } from '../i18n'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtCompact, fmtNum, pick } from '../data/live'

/* ---------- 本地小工具（禁止新建共享文件） ---------- */

function TableHead({ cols }: { cols: { label: string; right?: boolean }[] }) {
  return (
    <thead>
      <tr className="t-3 text-[10px] uppercase tracking-wider">
        {cols.map((c, i) => (
          <th
            key={`${c.label}-${i}`}
            className={`line-c border-b pb-2 font-semibold ${c.right ? 'text-right' : 'text-left'} ${i === cols.length - 1 ? '' : 'pr-3'}`}
          >
            {c.label}
          </th>
        ))}
      </tr>
    </thead>
  )
}

function pctOf(a: number, b: number): number {
  return b > 0 ? (a / b) * 100 : 0
}

/** 后端部分联赛的场均指标为 null（该联赛未接入 xG），统一降级为 — */
function fix(v?: number | null, digits = 2, suffix = ''): string {
  return typeof v === 'number' && Number.isFinite(v) ? `${v.toFixed(digits)}${suffix}` : '—'
}

/* ---------- 月度入库趋势 ---------- */

function MonthTrend({ rows, lang }: { rows: { m: string; n: number; ft: number }[]; lang: 'zh' | 'en' }) {
  const axis = '#8a8672'
  const grid = 'rgba(0,0,0,.07)'
  const tip = {
    background: 'rgba(255,255,255,.96)',
    border: '1px solid rgba(0,0,0,.07)',
    borderRadius: 12,
    fontSize: 11.5,
    color: '#2B2B27',
  }
  return (
    <div className="h-[300px] w-full">
      <ResponsiveContainer width="100%" height={300}>
        <AreaChart data={rows} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <defs>
            <linearGradient id="repN" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#F6C945" stopOpacity={0.55} />
              <stop offset="100%" stopColor="#F6C945" stopOpacity={0.05} />
            </linearGradient>

          </defs>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis
            dataKey="m"
            interval={2}
            stroke={axis}
            tick={{ fill: axis, fontSize: 10 }}
            tickFormatter={(v: string) => (typeof v === 'string' ? v.slice(2) : String(v))}
          />
          <YAxis
            stroke={axis}
            tick={{ fill: axis, fontSize: 10 }}
            width={44}
            tickFormatter={(v: number) => fmtCompact(lang, v)}
          />
          <Tooltip contentStyle={tip} />
          <Area
            type="monotone"
            dataKey="n"
            name={pick(lang, '入库比赛', 'Matches ingested')}
            stroke="#F6C945"
            strokeWidth={2}
            fill="url(#repN)"
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="ft"
            name={pick(lang, '已完赛', 'Finished')}
            stroke="#A8C5E2"
            strokeWidth={2.2}
            dot={false}
            isAnimationActive={false}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}

function QualityMini({ label, value, total }: { label: string; value: number; total: number }) {
  const p = pctOf(value, total)
  return (
    <div className="glass-soft rounded-[20px] p-4">
      <div className="flex items-baseline justify-between gap-2">
        <span className="t-2 text-[12px] font-semibold">{label}</span>
        <span className="t-1 text-[20px] font-semibold leading-none tabular-nums">{p.toFixed(1)}%</span>
      </div>
      <div className="mt-2.5">
        <Bar value={p} max={100} height={8} tone="yellow" />
      </div>
      <div className="t-3 mt-2 text-[10.5px] tabular-nums">
        {fmtNum(value)} / {fmtNum(total)}
      </div>
    </div>
  )
}

function StatMini({ label, value, hint }: { label: string; value: string; hint?: string }) {
  return (
    <div className="glass-soft rounded-[20px] p-4">
      <div className="t-3 text-[11px] font-medium">{label}</div>
      <div className="t-1 mt-1.5 text-[20px] font-semibold leading-none tabular-nums">{value}</div>
      {hint ? <div className="t-3 mt-2 text-[10.5px]">{hint}</div> : null}
    </div>
  )
}

/* ---------- 正文（无壳，供 /admin?tab=asset 复用） ---------- */

export function ReportsBody() {
  const { lang } = useLang()
  const { data, loading, error } = useApi(api.reports, 'reports', 120_000)
  const [tq, setTq] = useState('')
  const [showAllTables, setShowAllTables] = useState(false)

  const tables = useMemo(() => (data?.tables ?? []).slice().sort((a, b) => b.rows - a.rows), [data])
  const filteredTables = useMemo(() => {
    const k = tq.trim().toLowerCase()
    return k ? tables.filter((t) => t.name.toLowerCase().includes(k)) : tables
  }, [tables, tq])
  // 避免「页面滚动 + 卡片内滚动」双层滚动：默认只渲染前 12 张，其余用展开
  const shownTables = showAllTables || tq.trim() ? filteredTables : filteredTables.slice(0, 12)
  const leagues = useMemo(
    () => (data?.leagues ?? []).slice().sort((a, b) => b.matches - a.matches),
    [data],
  )

  const core = data?.core
  const quality = data?.quality

  return (
    <>
      {loading && !data ? <CardSkeleton rows={5} /> : null}
      {error && !data ? <ErrorState text={error} /> : null}

      {data && core && quality ? (
        <>
          <KpiStrip
            items={[
              { label: pick(lang, '收录比赛', 'Matches'), value: fmtNum(core.matches), sub: pick(lang, '含未来赛程', 'incl. fixtures') },
              { label: pick(lang, '已完赛', 'Finished'), value: fmtNum(core.finished), sub: pick(lang, `待赛 ${fmtNum(core.upcoming)}`, `${fmtNum(core.upcoming)} upcoming`) },
              { label: pick(lang, '球员', 'Players'), value: fmtNum(core.players) },
              { label: pick(lang, '球队', 'Teams'), value: fmtNum(core.teams), sub: pick(lang, `${core.leagues} 个联赛`, `${core.leagues} leagues`) },
              { label: pick(lang, '数据表', 'Tables'), value: fmtNum(core.tables) },
              { label: pick(lang, '总记录数', 'Total records'), value: fmtCompact(lang, core.records) },
            ]}
          />

          <SectionCard
            className="mt-4"
            title={pick(lang, '月度入库趋势', 'Monthly ingestion')}
            hint={pick(
              lang,
              `近 ${data.months.length} 个月 · 琥珀为入库比赛数，蓝色为其中已完赛`,
              `Last ${data.months.length} months · amber = matches ingested, blue = finished`,
            )}
          >
            <MonthTrend rows={data.months} lang={lang} />
            <div className="t-3 mt-2 text-[10.5px] tabular-nums">
              {pick(lang, '数据范围', 'Range')}: {core.first_date} → {core.last_date}
            </div>
          </SectionCard>

          <SectionCard
            className="mt-4"
            title={pick(lang, '数据质量', 'Data quality')}
            hint={pick(
              lang,
              '官方 xG 覆盖率与球员身价覆盖率按库内总量归一',
              'Official xG and market-value coverage normalised by warehouse totals',
            )}
          >
            <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
              <QualityMini
                label={pick(lang, '官方 xG 覆盖', 'Official xG coverage')}
                value={quality.matchWithXg}
                total={quality.matchTotal}
              />
              <QualityMini
                label={pick(lang, '身价覆盖', 'Market-value coverage')}
                value={quality.playerWithValue}
                total={quality.playerTotal}
              />
              <StatMini
                label={pick(lang, '伤停记录', 'Injury records')}
                value={fmtNum(quality.injuries)}
                hint={pick(lang, '来自 Transfermarkt', 'From Transfermarkt')}
              />
              <StatMini
                label={pick(lang, '身价历史行', 'Market-value rows')}
                value={fmtNum(quality.marketValueRows)}
                hint={pick(lang, '球员估值时间序列', 'Player valuation time series')}
              />
            </div>
          </SectionCard>

          <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-[1.1fr_1fr]">
            <SectionCard
              title={pick(lang, '数据来源', 'Data sources')}
              hint={pick(lang, '外部接口与落库记录数', 'External feeds and stored records')}
            >
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] border-collapse">
                  <TableHead
                    cols={[
                      { label: pick(lang, '来源', 'Source') },
                      { label: pick(lang, '记录数', 'Records'), right: true },
                      { label: pick(lang, '说明', 'Detail') },
                    ]}
                  />
                  <tbody>
                    {data.sources.map((s) => (
                      <tr key={s.name} className="table-row transition-colors align-top">
                        <td className="line-c border-b py-2.5 pr-3">
                          <div className="t-1 text-[12.5px] font-semibold">{s.name}</div>
                          {s.nameEn && s.nameEn !== s.name ? (
                            <div className="t-3 text-[10.5px]">{s.nameEn}</div>
                          ) : null}
                        </td>
                        <td className="line-c t-1 border-b py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">
                          {fmtCompact(lang, s.records)}
                        </td>
                        <td className="line-c t-2 border-b py-2.5 text-[11.5px] leading-[1.6]">
                          {pick(lang, s.detail, s.detailEn)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </SectionCard>

            <SectionCard
              title={pick(lang, '联赛对比', 'League comparison')}
              hint={pick(lang, '场均进球 / 场均 xG / 胜平负占比', 'Goals per game / xG per game / outcome share')}
            >
              <div className="max-h-[420px] overflow-auto">
                <table className="w-full min-w-[560px] border-collapse">
                  <TableHead
                    cols={[
                      { label: pick(lang, '联赛', 'League') },
                      { label: pick(lang, '赛季', 'Season') },
                      { label: pick(lang, '比赛', 'Matches'), right: true },
                      { label: pick(lang, '球队', 'Teams'), right: true },
                      { label: pick(lang, '场均进球', 'Goals/G'), right: true },
                      { label: pick(lang, '场均 xG', 'xG/G'), right: true },
                      { label: pick(lang, '主胜', 'Home'), right: true },
                      { label: pick(lang, '平局', 'Draw'), right: true },
                      { label: pick(lang, '客胜', 'Away'), right: true },
                    ]}
                  />
                  <tbody>
                    {leagues.map((l) => (
                      <tr key={l.id} className="table-row transition-colors">
                        <td className="line-c t-1 border-b py-2.5 pr-3 text-[12.5px] font-semibold">{pick(lang, l.name, l.nameEn)}</td>
                        <td className="line-c t-3 border-b py-2.5 pr-3 text-[11.5px] tabular-nums">{l.season}</td>
                        <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12px] tabular-nums">{fmtNum(l.matches)}</td>
                        <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12px] tabular-nums">{l.teams}</td>
                        <td className="line-c t-1 border-b py-2.5 pr-3 text-right text-[12px] font-semibold tabular-nums">{fix(l.goalsPg)}</td>
                        <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12px] tabular-nums">{fix(l.xgPg)}</td>
                        <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12px] tabular-nums">{fix(l.homeWinPct, 1, '%')}</td>
                        <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12px] tabular-nums">{fix(l.drawPct, 1, '%')}</td>
                        <td className="line-c t-2 border-b py-2.5 text-right text-[12px] tabular-nums">{fix(l.awayWinPct, 1, '%')}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                {leagues.length === 0 ? <EmptyState text={pick(lang, '暂无联赛数据', 'No league data')} /> : null}
              </div>
            </SectionCard>
          </div>

          <SectionCard
            className="mt-4"
            title={pick(lang, '全库表清单', 'Warehouse tables')}
            hint={pick(lang, `共 ${tables.length} 张表 · 按记录数降序`, `${tables.length} tables · sorted by row count`)}
            right={<SearchBox value={tq} onChange={setTq} placeholder={pick(lang, '筛选表名…', 'Filter table…')} />}
          >
            <div>
              <table className="w-full min-w-[560px] border-collapse">
                <TableHead
                  cols={[
                    { label: '#', right: true },
                    { label: pick(lang, '表名', 'Table') },
                    { label: pick(lang, '记录数', 'Rows'), right: true },
                    { label: pick(lang, '占比', 'Share') },
                  ]}
                />
                <tbody>
                  {shownTables.map((t, i) => {
                    const max = tables[0]?.rows ?? 1
                    const share = pctOf(t.rows, core.records)
                    return (
                      <tr key={t.name} className="table-row transition-colors">
                        <td className="line-c t-3 border-b py-2 pr-3 text-right text-[10.5px] tabular-nums">{i + 1}</td>
                        <td className="line-c border-b py-2 pr-3">
                          <span className="t-1 font-mono text-[12px]">{t.name}</span>
                        </td>
                        <td className="line-c t-1 border-b py-2 pr-3 text-right text-[12px] font-semibold tabular-nums">
                          {fmtNum(t.rows)}
                        </td>
                        <td className="line-c border-b py-2">
                          <div className="flex items-center gap-2">
                            <span className="min-w-0 flex-1">
                              <Bar value={t.rows} max={max} height={6} tone={i < 3 ? 'yellow' : 'blue'} />
                            </span>
                            <span className="t-3 w-[52px] shrink-0 text-right text-[10.5px] tabular-nums">
                              {share < 0.05 && share > 0 ? '<0.1%' : `${share.toFixed(1)}%`}
                            </span>
                          </div>
                        </td>
                      </tr>
                    )
                  })}
                </tbody>
              </table>
              {filteredTables.length === 0 ? (
                <EmptyState text={pick(lang, '没有匹配的表名', 'No table matches')} />
              ) : null}
            </div>
            <div className="t-3 mt-3 flex flex-wrap items-center gap-3 text-[11px]">
              <span className="tabular-nums">
                {pick(lang, `显示 ${shownTables.length} / ${tables.length} 张表`, `Showing ${shownTables.length} / ${tables.length} tables`)}
              </span>
              {!tq.trim() && filteredTables.length > 12 ? (
                <button
                  type="button"
                  onClick={() => setShowAllTables((v) => !v)}
                  className="glass-soft t-1 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
                >
                  {showAllTables
                    ? pick(lang, '收起（只看前 12 张）', 'Collapse (top 12)')
                    : pick(lang, `展开全部 ${filteredTables.length} 张`, `Show all ${filteredTables.length}`)}
                </button>
              ) : null}
              <Pill tone="muted">
                {pick(lang, '保存期限', 'Retention')} {core.first_date?.slice(0, 7)} → {core.last_date?.slice(0, 7)}
              </Pill>
              <span className="t-3">
                {pick(lang, '记录数最多', 'Largest table')}: <span className="t-2 font-semibold">{tables[0]?.name ?? '—'}</span>
              </span>
            </div>
          </SectionCard>
        </>
      ) : null}
    </>
  )
}

/* ---------- 旧入口外壳（/reports 已重定向到 /admin?tab=asset，保留直链兜底） ---------- */

export default function Reports() {
  const { lang } = useLang()
  // 与 ReportsBody 共用同一缓存键 → 不会多发一次请求
  const { data } = useApi(api.reports, 'reports', 120_000)

  return (
    <PageShell
      title={pick(lang, '数据报告', 'Data Reports')}
      subtitle={pick(
        lang,
        '全库规模 · 月度入库 · 数据质量与来源清单',
        'Warehouse scale · monthly ingestion · quality and source inventory',
      )}
      activePath="/reports"
      right={
        data ? (
          <span className="t-3 text-[11px] tabular-nums">
            {pick(lang, '报告生成时间', 'Report generated')} {data.generatedAt}
          </span>
        ) : undefined
      }
    >
      <ReportsBody />
    </PageShell>
  )
}
