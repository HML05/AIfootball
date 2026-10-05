/**
 * 管理端 ·「系统与接口」页签（无壳，由 Admin.tsx 的 PageShell 承载）
 *
 * 四张卡：数据源 / 实时通道 / 数据库表 / 数据质量。
 * 数字全部来自 /api/ui/reports 与 /api/ui/live，不写死。
 * 实时通道只展示 WebSocket 端点，管理端不建立连接（连接由用户端 /live 负责）。
 */
import { useMemo, useState } from 'react'
import type { ReactNode } from 'react'
import { SectionCard, Pill, Bar, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { useLang } from '../i18n'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtCompact, fmtNum, pick } from '../data/live'

/* ---------- 本地小工具（禁止新建共享文件） ---------- */

/** 默认展示的表行数（超出的用「展开全部」按钮，避免卡片内层滚动条） */
const TABLE_PREVIEW = 12

function pctOf(a: number, b: number): number {
  return b > 0 ? (a / b) * 100 : 0
}

function TableHead({ cols }: { cols: { label: string; right?: boolean }[] }) {
  return (
    <thead>
      <tr className="t-3 text-[10px] uppercase tracking-wider">
        {cols.map((c, i) => (
          <th
            key={`${c.label}-${i}`}
            className={`line-c border-b pb-2 font-semibold ${c.right ? 'text-right' : 'text-left'} ${
              i === cols.length - 1 ? '' : 'pr-3'
            }`}
          >
            {c.label}
          </th>
        ))}
      </tr>
    </thead>
  )
}

/** 键值行（实时通道用） */
function KV({ label, value, mono = false }: { label: string; value: ReactNode; mono?: boolean }) {
  return (
    <div className="glass-soft flex flex-wrap items-baseline justify-between gap-2 rounded-[18px] px-4 py-3">
      <span className="t-3 text-[11px] font-medium">{label}</span>
      <span className={`t-1 text-[12.5px] font-semibold tabular-nums ${mono ? 'font-mono break-all' : ''}`}>
        {value}
      </span>
    </div>
  )
}

/** 覆盖率块（百分比 + 计数 + 口径说明） */
function CoverageBlock({
  label,
  note,
  value,
  total,
}: {
  label: string
  note: string
  value: number
  total: number
}) {
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
      <div className="t-3 mt-1 text-[10.5px] leading-[1.6]">{note}</div>
    </div>
  )
}

/** 计数块 */
function CountBlock({ label, value, note }: { label: string; value: number; note: string }) {
  return (
    <div className="glass-soft rounded-[20px] p-4">
      <div className="t-3 text-[11px] font-medium">{label}</div>
      <div className="t-1 mt-1.5 text-[20px] font-semibold leading-none tabular-nums">{fmtNum(value)}</div>
      <div className="t-3 mt-2 text-[10.5px] leading-[1.6]">{note}</div>
    </div>
  )
}

/* ---------- 页签正文 ---------- */

export function AdminSystem() {
  const { lang } = useLang()
  // 与 Reports.tsx / Live.tsx 共用同一缓存键 → 切换页签不会重复请求
  const reports = useApi(api.reports, 'reports', 120_000)
  const live = useApi(api.live, 'live', 30_000)
  const [showAllTables, setShowAllTables] = useState(false)

  const data = reports.data
  const liveData = live.data
  const core = data?.core
  const quality = data?.quality

  const tables = useMemo(() => (data?.tables ?? []).slice().sort((a, b) => b.rows - a.rows), [data])
  const shownTables = showAllTables ? tables : tables.slice(0, TABLE_PREVIEW)
  const maxRows = tables[0]?.rows ?? 1

  return (
    <div className="flex flex-col gap-4">
      <div className="grid grid-cols-1 gap-4 xl:grid-cols-2">
        {/* 1 · 数据源 */}
        <SectionCard
          title={pick(lang, '数据源', 'Data sources')}
          hint={pick(lang, '外部接口与落库记录数', 'External feeds and stored records')}
        >
          {reports.loading && !data ? <CardSkeleton rows={4} /> : null}
          {reports.error && !data ? <ErrorState text={reports.error} /> : null}
          {data ? (
            data.sources.length ? (
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] border-collapse">
                  <TableHead
                    cols={[
                      { label: pick(lang, '数据源', 'Source') },
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
            ) : (
              <EmptyState text={pick(lang, '暂无数据源', 'No data sources')} />
            )
          ) : null}
        </SectionCard>

        {/* 2 · 实时通道 */}
        <SectionCard
          title={pick(lang, '实时通道', 'Live channel')}
          hint={pick(
            lang,
            '仅展示端点信息，管理端不建立连接（连接由用户端「实时」负责）',
            'Endpoint info only — the admin console does not connect (the user-facing Live page owns the connection)',
          )}
          right={<Pill tone="blue">{pick(lang, '只读展示', 'Read-only')}</Pill>}
        >
          {live.loading && !liveData ? <CardSkeleton rows={4} /> : null}
          {live.error && !liveData ? <ErrorState text={live.error} /> : null}
          {liveData ? (
            <div className="flex flex-col gap-2.5">
              <KV label={pick(lang, '数据源', 'Source')} value={liveData.source} />
              <KV
                label={pick(lang, 'WebSocket 端点', 'WebSocket endpoint')}
                value={liveData.wsEndpoint}
                mono
              />
              <KV label={pick(lang, '最近更新', 'Last update')} value={liveData.lastDay} />
              <KV
                label={pick(lang, '近 24 小时更新条数', 'Updates in the last 24h')}
                value={fmtNum(liveData.lastDayCount)}
              />
            </div>
          ) : null}
        </SectionCard>
      </div>

      {/* 3 · 数据库表 */}
      <SectionCard
        title={pick(lang, '数据库表', 'Database tables')}
        hint={pick(
          lang,
          `共 ${tables.length} 张表 · 按记录数降序`,
          `${tables.length} tables · sorted by row count`,
        )}
      >
        {reports.loading && !data ? <CardSkeleton rows={6} /> : null}
        {reports.error && !data ? <ErrorState text={reports.error} /> : null}
        {data ? (
          tables.length ? (
            <>
              <div className="overflow-x-auto">
                <table className="w-full min-w-[520px] border-collapse">
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
                      const share = core ? pctOf(t.rows, core.records) : 0
                      return (
                        <tr key={t.name} className="table-row transition-colors">
                          <td className="line-c t-3 border-b py-2 pr-3 text-right text-[10.5px] tabular-nums">
                            {i + 1}
                          </td>
                          <td className="line-c border-b py-2 pr-3">
                            <span className="t-1 font-mono text-[12px]">{t.name}</span>
                          </td>
                          <td className="line-c t-1 border-b py-2 pr-3 text-right text-[12px] font-semibold tabular-nums">
                            {fmtNum(t.rows)}
                          </td>
                          <td className="line-c border-b py-2">
                            <div className="flex items-center gap-2">
                              <span className="min-w-0 flex-1">
                                <Bar value={t.rows} max={maxRows} height={6} tone={i < 3 ? 'yellow' : 'blue'} />
                              </span>
                              <span className="t-3 w-[52px] shrink-0 text-right text-[10.5px] tabular-nums">
                                {!core ? '—' : share < 0.05 && share > 0 ? '<0.1%' : `${share.toFixed(1)}%`}
                              </span>
                            </div>
                          </td>
                        </tr>
                      )
                    })}
                  </tbody>
                </table>
              </div>
              <div className="t-3 mt-3 flex flex-wrap items-center gap-3 text-[11px]">
                <span className="tabular-nums">
                  {pick(
                    lang,
                    `显示 ${shownTables.length} / ${tables.length} 张表`,
                    `Showing ${shownTables.length} / ${tables.length} tables`,
                  )}
                </span>
                {tables.length > TABLE_PREVIEW ? (
                  <button
                    type="button"
                    onClick={() => setShowAllTables((v) => !v)}
                    className="glass-soft t-1 rounded-full px-3 py-1.5 text-[11px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
                  >
                    {showAllTables
                      ? pick(lang, `收起（只看前 ${TABLE_PREVIEW} 张）`, `Collapse (top ${TABLE_PREVIEW})`)
                      : pick(lang, `展开全部 ${tables.length} 张`, `Show all ${tables.length}`)}
                  </button>
                ) : null}
                {core ? (
                  <>
                    <Pill tone="muted">
                      {pick(lang, '总记录数', 'Total records')} {fmtCompact(lang, core.records)}
                    </Pill>
                    <span className="t-3">
                      {pick(lang, '记录数最多', 'Largest table')}:{' '}
                      <span className="t-2 font-semibold">{tables[0]?.name ?? '—'}</span>
                    </span>
                  </>
                ) : null}
              </div>
            </>
          ) : (
            <EmptyState text={pick(lang, '暂无库表信息', 'No table inventory')} />
          )
        ) : null}
      </SectionCard>

      {/* 4 · 数据质量 */}
      <SectionCard
        title={pick(lang, '数据质量', 'Data quality')}
        hint={pick(
          lang,
          '官方 xG 覆盖率 = 含 xG 比赛数 / 库内比赛总数；身价覆盖率 = 有身价球员数 / 库内球员总数',
          'Official xG coverage = matches with xG / all matches; market-value coverage = players with a value / all players',
        )}
      >
        {reports.loading && !data ? <CardSkeleton rows={3} /> : null}
        {reports.error && !data ? <ErrorState text={reports.error} /> : null}
        {data && quality ? (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 xl:grid-cols-4">
            <CoverageBlock
              label={pick(lang, '官方 xG 覆盖率', 'Official xG coverage')}
              note={pick(
                lang,
                `含 xG 比赛 ${fmtNum(quality.matchWithXg)} / 比赛总数 ${fmtNum(quality.matchTotal)}`,
                `${fmtNum(quality.matchWithXg)} matches with xG / ${fmtNum(quality.matchTotal)} total`,
              )}
              value={quality.matchWithXg}
              total={quality.matchTotal}
            />
            <CoverageBlock
              label={pick(lang, '身价覆盖率', 'Market-value coverage')}
              note={pick(
                lang,
                `有身价球员 ${fmtNum(quality.playerWithValue)} / 球员总数 ${fmtNum(quality.playerTotal)}`,
                `${fmtNum(quality.playerWithValue)} players with a value / ${fmtNum(quality.playerTotal)} total`,
              )}
              value={quality.playerWithValue}
              total={quality.playerTotal}
            />
            <CountBlock
              label={pick(lang, '伤停记录', 'Injury records')}
              value={quality.injuries}
              note={pick(lang, '来自 Transfermarkt 伤停表', 'From the Transfermarkt injury feed')}
            />
            <CountBlock
              label={pick(lang, '身价历史行', 'Market-value rows')}
              value={quality.marketValueRows}
              note={pick(lang, '球员估值时间序列行数', 'Player valuation time-series rows')}
            />
          </div>
        ) : null}
      </SectionCard>
    </div>
  )
}

export default AdminSystem
