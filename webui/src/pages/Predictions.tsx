import { useMemo, useState } from 'react'
import { Link } from 'react-router'
import { PageShell, SectionCard, Pill, Bar, Pager, SearchBox, Tabs, EmptyState, ErrorState, KpiStrip } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import type { ModelRow, PredictionRow } from '../lib/api'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import type { I18nKey, Lang } from '../i18n'
import { useLang } from '../i18n'
import { fmtNum, pick, splitDateTime } from '../data/live'

/* ---------- 共用小工具（本文件内） ---------- */

type TFn = (key: I18nKey) => string

/** 'H' | 'D' | 'A' → 主胜/平局/客胜 */
function resultLabel(t: TFn, v?: string | null): string {
  if (v === 'H') return t('match.home')
  if (v === 'D') return t('match.draw')
  if (v === 'A') return t('match.away')
  return '—'
}

function prob(v?: number | null): string {
  if (v === null || v === undefined) return '—'
  return `${(v * 100).toFixed(1)}%`
}

function Logo({ src, name, size = 26 }: { src?: string | null; name: string; size?: number }) {
  const [bad, setBad] = useState(false)
  if (!src || bad)
    return (
      <span
        className="glass-soft t-2 flex shrink-0 items-center justify-center rounded-full text-[9px] font-bold"
        style={{ width: size, height: size }}
      >
        {name.slice(0, 2)}
      </span>
    )
  return (
    <img
      src={src}
      alt=""
      loading="lazy"
      onError={() => setBad(true)}
      className="crest shrink-0 rounded-full"
      style={{ width: size, height: size }}
    />
  )
}

function TopThree({ row, t }: { row: PredictionRow; t: TFn }) {
  const items: { key: I18nKey; v: number | null }[] = [
    { key: 'match.home', v: row.pred_home_win },
    { key: 'match.draw', v: row.pred_draw },
    { key: 'match.away', v: row.pred_away_win },
  ]
  const top = items.reduce((a, b) => ((b.v ?? -1) > (a.v ?? -1) ? b : a), items[0])
  const tone = top.key === 'match.home' ? 'yellow' : top.key === 'match.draw' ? 'muted' : 'blue'
  return (
    <div className="flex w-[128px] flex-col gap-[3px]">
      {items.map((it) => (
        <div key={it.key} className="flex items-center gap-1.5">
          <span className={`w-[34px] shrink-0 text-[10px] ${it.key === top.key ? 't-1 font-semibold' : 't-3'}`}>
            {t(it.key)}
          </span>
          <span className={`w-[42px] shrink-0 text-right tabular-nums text-[10.5px] ${it.key === top.key ? 't-1 font-semibold' : 't-2'}`}>
            {prob(it.v)}
          </span>
          <span className="min-w-0 flex-1">
            <Bar value={(it.v ?? 0) * 100} max={100} height={4} tone={it.key === top.key ? tone : 'muted'} />
          </span>
        </div>
      ))}
    </div>
  )
}


/* ---------- 视图 1：预测列表 ---------- */

function ListView({
  rows,
  model,
  result,
  onModel,
  onResult,
  models,
  t,
  lang,
}: {
  rows: PredictionRow[]
  model: string
  result: string
  onModel: (v: string) => void
  onResult: (v: string) => void
  models: ModelRow[]
  t: TFn
  lang: Lang
}) {
  const [q, setQ] = useState('')
  const filtered = useMemo(() => {
    const k = q.trim().toLowerCase()
    if (!k) return rows
    return rows.filter((r) => `${r.h} ${r.a} ${r.lg} ${r.lg_en ?? ''}`.toLowerCase().includes(k))
  }, [rows, q])

  return (
    <>
      <div className="mb-3 flex flex-wrap items-center gap-2">
        <SearchBox value={q} onChange={setQ} placeholder={pick(lang, '筛选队名…', 'Filter team…')} />
        <div className="min-w-0 max-w-[380px] overflow-x-auto">
          <Tabs
            items={[
              { key: '', label: pick(lang, '全部', 'All') },
              { key: 'H', label: t('match.home') },
              { key: 'D', label: t('match.draw') },
              { key: 'A', label: t('match.away') },
            ]}
            value={result}
            onChange={onResult}
          />
        </div>
        <span className="t-3 text-[11px]">{pick(lang, '模型版本', 'Model')}</span>
        <select
          value={model}
          onChange={(e) => onModel(e.target.value)}
          className="glass-soft t-1 rounded-full px-3 py-1.5 text-[11.5px] outline-none"
        >
          <option value="">{pick(lang, '全部模型', 'All models')}</option>
          {models.map((m) => (
            <option key={m.model} value={m.model}>
              {m.model}
            </option>
          ))}
        </select>
        <span className="t-3 ml-auto text-[11px] tabular-nums">
          {pick(lang, `${filtered.length} / ${rows.length} 行`, `${filtered.length} / ${rows.length} rows`)}
        </span>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full min-w-[1000px] border-collapse text-left">
          <thead>
            <tr className="t-3 text-[10px] uppercase tracking-wider">
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '日期', 'Date')}</th>
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '联赛', 'League')}</th>
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '对阵', 'Match')}</th>
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '三分类概率', 'Probabilities')}</th>
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '推荐', 'Pick')}</th>
              <th className="line-c border-b pb-2 pr-3 font-semibold">{pick(lang, '实际', 'Actual')}</th>
              <th className="line-c border-b pb-2 pr-3 text-center font-semibold">{pick(lang, '命中', 'Hit')}</th>
              <th className="line-c border-b pb-2 font-semibold">{pick(lang, '版本', 'Version')}</th>
            </tr>
          </thead>
          <tbody>
            {filtered.map((r) => {
              const dt = splitDateTime(r.date)
              const hitTone = r.hit === 1 ? 'text-[#8a6a10] font-bold' : r.hit === 0 ? 'text-[#c07b84]' : 't-3'
              return (
                <tr key={r.pred_id} className="table-row transition-colors">
                  <td className="line-c border-b py-2.5 pr-3">
                    <div className="t-2 text-[12px] tabular-nums">{dt.date}</div>
                    <div className="t-3 text-[10px] tabular-nums">{dt.time}</div>
                  </td>
                  <td className="line-c border-b py-2.5 pr-3">
                    <span className="t-2 block max-w-[86px] truncate text-[11.5px]" title={r.lg ?? ''}>
                      {r.lg ?? '—'}
                    </span>
                  </td>
                  <td className="line-c border-b py-2.5 pr-3">
                    <div className="flex items-center gap-2">
                      <Logo src={r.h_logo} name={r.h} size={24} />
                      <span className="t-1 max-w-[124px] truncate text-[12.5px] font-medium">{r.h}</span>
                      <span className="t-3 text-[10px]">vs</span>
                      <Logo src={r.a_logo} name={r.a} size={24} />
                      <span className="t-1 max-w-[124px] truncate text-[12.5px] font-medium">{r.a}</span>
                    </div>
                  </td>
                  <td className="line-c border-b py-2 pl-0 pr-3">
                    <TopThree row={r} t={t} />
                  </td>
                  <td className="line-c border-b py-2.5 pr-3">
                    <Pill tone={r.pred_result === 'H' ? 'yellow' : r.pred_result === 'D' ? 'muted' : 'blue'}>
                      {resultLabel(t, r.pred_result)}
                    </Pill>
                  </td>
                  <td className="line-c t-2 border-b py-2.5 pr-3 text-[12px]">{resultLabel(t, r.actual_result)}</td>
                  <td className={`line-c border-b py-2.5 pr-3 text-center text-[13px] tabular-nums ${hitTone}`}>
                    {r.hit === 1 ? '✓' : r.hit === 0 ? '✗' : '—'}
                  </td>
                  <td className="line-c border-b py-2.5">
                    <span className="t-3 block max-w-[132px] truncate text-[10.5px]" title={r.model_version}>
                      {r.model_version}
                    </span>
                  </td>
                </tr>
              )
            })}
          </tbody>
        </table>
      </div>

      {filtered.length === 0 ? (
        <EmptyState text={pick(lang, '当前筛选下没有预测记录', 'No predictions for the current filter')} />
      ) : null}
    </>
  )
}

/* ---------- 页面 ---------- */

export default function Predictions() {
  const { lang, t } = useLang()
  const [page, setPage] = useState(1)
  const [model, setModel] = useState('')
  const [result, setResult] = useState('')
  const [backtest, setBacktest] = useState<'all' | '0' | '1'>('all')

  const { data, loading, error } = useApi(
    () => api.predictions({ page, size: 25, model, result }),
    `pred:${page}:25:${model}:${result}`,
  )

  const models = data?.models ?? []
  const production = models.find((m) => m.status === 'production')
  const rows = useMemo(() => {
    const all = data?.items ?? []
    if (backtest === 'all') return all
    return all.filter((r) => String(r.is_backtest) === backtest)
  }, [data, backtest])


  return (
    <PageShell
      title={pick(lang, '比赛预测', 'Match Predictions')}
      subtitle={pick(
        lang,
        '三分类胜平负概率 · 样本外评估与概率校准',
        'Three-way win/draw/away probabilities · out-of-sample evaluation and calibration',
      )}
      activePath="/predictions"
    >
      {loading && !data ? <CardSkeleton /> : null}
      {error && !data ? <ErrorState text={error} /> : null}

      {data ? (
        <>
          <KpiStrip
            items={[
              {
                label: pick(lang, '命中率', 'Hit rate'),
                value: `${data.hitRate.toFixed(1)}%`,
                sub: pick(lang, '全部已评估预测（含回测）', 'All evaluated, incl. backtests'),
              },
              {
                label: pick(lang, '已评估', 'Evaluated'),
                value: fmtNum(data.evaluated),
                sub: pick(lang, '含实际结果', 'With actual result'),
              },
              {
                label: pick(lang, '预测总数', 'Predictions'),
                value: fmtNum(data.total),
                sub: pick(lang, `${data.pages} 页`, `${data.pages} pages`),
              },
              {
                label: pick(lang, '生产模型', 'Production'),
                value: production?.model ?? '—',
                sub: production
                  ? `${t('admin.table.acc')}（样本外 ${fmtNum(production.test_n)} 场）`
                  : '—',
              },
              {
                label: pick(lang, '模型数', 'Models'),
                value: fmtNum(models.length),
                sub: pick(lang, '样本外测试', 'Out-of-sample'),
              },
            ]}
          />

          {/* 术语口径：命中率与准确率样本不同，只在这里定义一次 */}
          <div className="glass-soft mt-3 flex flex-wrap items-center gap-x-3 gap-y-1.5 rounded-[20px] px-4 py-2.5 text-[11px] leading-relaxed">
            <span className="t-2">
              {pick(
                lang,
                '命中率 = 全部已评估预测（含历史回测）中推荐结果正确的比例；',
                'Hit rate = share of all evaluated predictions whose recommended outcome was correct; ',
              )}
            </span>
            <span className="t-3">
              {pick(
                lang,
                '准确率 = 生产模型的样本外（out-of-sample）三分类准确率。两者样本不同，不能直接比较。',
                'accuracy = the production model’s out-of-sample three-way accuracy. Different samples — not comparable.',
              )}
            </span>
            <Link
              to="/admin?tab=models"
              className="t-1 ml-auto font-semibold whitespace-nowrap underline decoration-dotted underline-offset-4"
            >
              {pick(lang, '模型评估与概率校准 →', 'Model evaluation & calibration →')}
            </Link>
          </div>

          <SectionCard
            className="mt-4"
            title={pick(lang, '预测工作台', 'Prediction workbench')}
            hint={pick(
              lang,
              '服务端分页 25 行/页；筛选条件与模型版本直接作用于接口查询',
              'Server-side paging, 25 rows/page; filters apply to the API query',
            )}
          >
              <>
                <ListView
                  rows={rows}
                  models={models}
                  model={model}
                  result={result}
                  onModel={(v) => {
                    setModel(v)
                    setPage(1)
                  }}
                  onResult={(v) => {
                    setResult(v)
                    setPage(1)
                  }}
                  t={t}
                  lang={lang}
                />
                <div className="mt-4 flex flex-wrap items-center gap-3">
                  <div className="min-w-0 max-w-[320px] overflow-x-auto">
                    <Tabs
                      items={[
                        { key: 'all', label: pick(lang, '全部来源', 'All sources') },
                        { key: '0', label: pick(lang, '实时预测', 'Live') },
                        { key: '1', label: pick(lang, '回测', 'Backtest') },
                      ]}
                      value={backtest}
                      onChange={(v) => setBacktest(v as 'all' | '0' | '1')}
                    />
                  </div>
                  <span className="t-3 text-[11px]">
                    {pick(lang, '回测筛选作用于当前页', 'Backtest filter applies to the current page')}
                  </span>
                  <div className="ml-auto">
                    <Pager
                      page={data.page}
                      pages={data.pages}
                      total={data.total}
                      onPage={setPage}
                      unit={pick(lang, '条预测', 'predictions')}
                    />
                  </div>
                </div>
              </>
          </SectionCard>
        </>
      ) : null}
    </PageShell>
  )
}
