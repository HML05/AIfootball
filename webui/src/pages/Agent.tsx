import { useMemo, useState } from 'react'
import { CartesianGrid, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { PageShell, SectionCard, Pill, Bar } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { ErrorState } from '../components/kit'
import type { I18nKey, Lang } from '../i18n'
import { useLang } from '../i18n'
import type { ModelRow, PredictionRow } from '../lib/api'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, pick, splitDateTime } from '../data/live'

/* ---------- 本地小工具（与其它页面保持一致，禁止新建共享文件） ---------- */

type TFn = (key: I18nKey) => string
type Outcome = '主胜' | '平局' | '客胜'

const OUTCOME_KEY: Record<Outcome, I18nKey> = {
  主胜: 'match.home',
  平局: 'match.draw',
  客胜: 'match.away',
}

const OUTCOME_ORDER: Outcome[] = ['主胜', '平局', '客胜']

const STATUS_KEY: Record<string, I18nKey> = {
  production: 'admin.status.production',
  challenger: 'admin.status.challenger',
  baseline: 'admin.status.baseline',
}

function statusLabel(t: TFn, status: string): string {
  const key = STATUS_KEY[status]
  return key ? t(key) : status
}

function statusTone(status: string): 'yellow' | 'blue' | 'muted' {
  if (status === 'production') return 'yellow'
  if (status === 'challenger') return 'blue'
  return 'muted'
}

function outcomeLabel(t: TFn, v?: string | null): string {
  const key = OUTCOME_KEY[v as Outcome]
  return key ? t(key) : (v ?? '—')
}

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

function Logo({ src, name, size = 24 }: { src?: string | null; name: string; size?: number }) {
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

/* ---------- 概率校准曲线 ---------- */

function CalibrationChart({
  rows,
  lang,
}: {
  rows: { outcome: string; predicted: number; actual: number }[]
  lang: Lang
}) {
  const data = useMemo(
    () => rows.slice().sort((a, b) => a.predicted - b.predicted).map((r) => ({ ...r, ideal: r.predicted })),
    [rows],
  )
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
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 4, left: 0 }}>
          <CartesianGrid stroke={grid} vertical={false} />
          <XAxis
            dataKey="predicted"
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => v.toFixed(2)}
            stroke={axis}
            tick={{ fill: axis, fontSize: 10 }}
          />
          <YAxis
            type="number"
            domain={[0, 1]}
            ticks={[0, 0.25, 0.5, 0.75, 1]}
            tickFormatter={(v: number) => v.toFixed(2)}
            stroke={axis}
            tick={{ fill: axis, fontSize: 10 }}
            width={34}
          />
          <Tooltip contentStyle={tip} />
          <Line
            type="linear"
            dataKey="ideal"
            name={pick(lang, '理想校准', 'Perfect')}
            stroke={axis}
            strokeDasharray="4 4"
            strokeWidth={1}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="actual"
            name={pick(lang, '实际频率', 'Actual')}
            stroke="#A8C5E2"
            strokeWidth={2.4}
            dot={{ r: 2.4, fill: '#A8C5E2', strokeWidth: 0 }}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}

/* ---------- 特征重要性 ---------- */

function FeatureImportance({ rows, limit = 12 }: { rows: { feature: string; importance: number }[]; limit?: number }) {
  const top = useMemo(() => rows.slice().sort((a, b) => b.importance - a.importance).slice(0, limit), [rows, limit])
  const max = top.reduce((s, r) => Math.max(s, r.importance), 0.0001)
  return (
    <div className="flex flex-col gap-2">
      {top.map((r, i) => (
        <div key={r.feature} className="flex items-center gap-2.5">
          <span className="t-3 w-[16px] shrink-0 text-right text-[10px] tabular-nums">{i + 1}</span>
          <span className="t-2 w-[178px] shrink-0 truncate text-[11.5px]" title={r.feature}>
            {r.feature}
          </span>
          <span className="min-w-0 flex-1">
            <Bar value={r.importance} max={max} height={7} tone={i < 3 ? 'yellow' : 'blue'} />
          </span>
          <span className="t-2 w-[52px] shrink-0 text-right text-[10.5px] tabular-nums">
            {(r.importance * 100).toFixed(2)}
          </span>
        </div>
      ))}
      {top.length === 0 ? <span className="t-3 text-[11.5px]">—</span> : null}
    </div>
  )
}

/* ---------- 生产模型大卡 ---------- */

function ProductionCard({ m, t, lang }: { m: ModelRow; t: TFn; lang: Lang }) {
  const cells: { label: string; value: string; hint: string }[] = [
    { label: t('admin.table.acc'), value: `${m.acc.toFixed(2)}%`, hint: pick(lang, '三分类总体', '3-way overall') },
    { label: 'F1 Macro', value: `${(m.f1_macro * 100).toFixed(1)}%`, hint: pick(lang, '宏平均', 'Macro avg') },
    { label: t('admin.table.logloss'), value: m.logloss.toFixed(4), hint: pick(lang, '越低越好', 'Lower is better') },
    { label: `${t('match.draw')} ${pick(lang, '召回', 'recall')}`, value: `${m.draw_recall.toFixed(1)}%`, hint: pick(lang, '平局最难', 'Draws are hardest') },
  ]
  return (
    <SectionCard dark>
      <div className="flex flex-wrap items-center gap-3">
        <span className="on-ink text-[24px] font-semibold leading-none">{m.model}</span>
        <Pill tone={statusTone(m.status)}>{statusLabel(t, m.status)}</Pill>
        <span className="on-ink opacity-60 text-[11.5px]">
          {pick(
            lang,
            `样本外测试 ${fmtNum(m.test_n)} 场 · 与挑战者同口径比较`,
            `Out-of-sample n=${fmtNum(m.test_n)} · same protocol as challengers`,
          )}
        </span>
      </div>
      <div className="mt-5 grid grid-cols-1 gap-5 min-[560px]:grid-cols-2 lg:grid-cols-4">
        {cells.map((c) => (
          <div key={c.label}>
            <div className="on-ink opacity-60 text-[11px] font-medium">{c.label}</div>
            <div className="on-ink mt-1 text-[28px] font-semibold leading-none tabular-nums">{c.value}</div>
            <div className="on-ink opacity-50 mt-1.5 text-[10.5px]">{c.hint}</div>
          </div>
        ))}
      </div>
    </SectionCard>
  )
}

/* ---------- 模型版本对比 ---------- */

function VersionTable({ rows, t }: { rows: ModelRow[]; t: TFn }) {
  const best = rows.reduce<ModelRow | null>((a, b) => (a === null || b.acc > a.acc ? b : a), null)
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[620px] border-collapse text-left">
        <thead>
          <tr className="t-3 text-[10px] uppercase tracking-wider">
            <th className="line-c border-b pb-2 pr-3 font-semibold">{t('admin.table.name')}</th>
            <th className="line-c border-b pb-2 pr-3 text-right font-semibold">{t('admin.table.acc')}</th>
            <th className="line-c border-b pb-2 pr-3 text-right font-semibold">F1</th>
            <th className="line-c border-b pb-2 pr-3 text-right font-semibold">{t('admin.table.logloss')}</th>
            <th className="line-c border-b pb-2 font-semibold">{t('admin.table.status')}</th>
          </tr>
        </thead>
        <tbody>
          {rows.map((m) => (
            <tr key={m.model} className="table-row transition-colors">
              <td className="line-c border-b py-2.5 pr-3">
                <div className="flex items-center gap-2">
                  <span className={`text-[12.5px] ${m.model === best?.model ? 't-1 font-semibold' : 't-1'}`}>{m.model}</span>
                  {m.model === best?.model ? <Pill tone="yellow">Top</Pill> : null}
                </div>
              </td>
              <td className="line-c t-1 border-b py-2.5 pr-3 text-right text-[12.5px] tabular-nums">{m.acc.toFixed(2)}%</td>
              <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12.5px] tabular-nums">
                {(m.f1_macro * 100).toFixed(1)}%
              </td>
              <td className="line-c t-2 border-b py-2.5 pr-3 text-right text-[12.5px] tabular-nums">{m.logloss.toFixed(4)}</td>
              <td className="line-c border-b py-2.5">
                <Pill tone={statusTone(m.status)}>{statusLabel(t, m.status)}</Pill>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/* ---------- 最近预测 ---------- */

function confidence(row: PredictionRow): number {
  const vals = [row.pred_home_win, row.pred_draw, row.pred_away_win].filter((v): v is number => typeof v === 'number')
  return vals.length ? Math.max(...vals) : 0
}

function RecentPicks({ rows, t, lang }: { rows: PredictionRow[]; t: TFn; lang: Lang }) {
  if (rows.length === 0) return <Empty text={pick(lang, '暂无预测记录', 'No predictions yet')} />
  return (
    <div className="flex flex-col divide-y" style={{ borderColor: 'var(--c-line)' }}>
      {rows.map((r) => {
        const dt = splitDateTime(r.date)
        const conf = confidence(r)
        return (
          <div key={r.pred_id} className="flex items-center gap-3 py-2.5">
            <div className="w-[46px] shrink-0">
              <div className="t-2 text-[11.5px] tabular-nums">{dt.date}</div>
              <div className="t-3 text-[10px] tabular-nums">{dt.time}</div>
            </div>
            <div className="flex min-w-0 flex-1 items-center gap-2">
              <Logo src={r.h_logo} name={r.h} />
              <span className="t-1 max-w-[118px] truncate text-[12.5px] font-medium">{r.h}</span>
              <span className="t-3 text-[10px]">vs</span>
              <Logo src={r.a_logo} name={r.a} />
              <span className="t-1 max-w-[118px] truncate text-[12.5px] font-medium">{r.a}</span>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <span className="t-3 text-[10.5px] tabular-nums">
                {prob(r.pred_home_win)} / {prob(r.pred_draw)} / {prob(r.pred_away_win)}
              </span>
              <Pill tone={r.pred_result === 'H' ? 'yellow' : r.pred_result === 'D' ? 'muted' : 'blue'}>
                {resultLabel(t, r.pred_result)}
              </Pill>
              <span className="t-2 w-[46px] text-right text-[11.5px] font-semibold tabular-nums">
                {(conf * 100).toFixed(1)}%
              </span>
            </div>
          </div>
        )
      })}
    </div>
  )
}

function Empty({ text }: { text: string }) {
  return (
    <div className="t-3 flex items-center justify-center py-8 text-[12px] font-medium">
      <span className="glass-soft mr-2 flex h-9 w-9 items-center justify-center rounded-full text-[14px]">—</span>
      {text}
    </div>
  )
}

/* ---------- 正文（无壳，供 /admin?tab=models 复用） ---------- */

export function AgentBody() {
  const { lang, t } = useLang()
  const { data, loading, error } = useApi(
    () => Promise.all([api.models(), api.predictions({ page: 1, size: 8 })]),
    'agent:models+picks',
  )

  const modelsPayload = data?.[0] ?? null
  const picksPayload = data?.[1] ?? null

  const list = modelsPayload?.items ?? []
  const production = list.find((m) => m.status === 'production') ?? null
  const calibration = modelsPayload?.calibration ?? []
  const importance = modelsPayload?.featureImportance ?? []
  const recent = picksPayload?.items ?? []
  const hitRate = picksPayload?.hitRate ?? null
  const evaluated = picksPayload?.evaluated ?? null
  const totalPreds = picksPayload?.total ?? null

  const topFeature = useMemo(
    () => importance.slice().sort((a, b) => b.importance - a.importance)[0],
    [importance],
  )

  const steps: { title: string; desc: string }[] = [
    {
      title: pick(lang, '特征来源', 'Feature sources'),
      desc: pick(
        lang,
        '联赛与赛程来自 football-data.org；进攻质量用 Understat 期望进球（xG/xGA）；阵容价值与伤停来自 Transfermarkt 身价表与伤停记录；再叠加 Elo 与近期状态窗口。',
        'Fixtures from football-data.org; attacking quality from Understat expected goals (xG/xGA); squad value and injuries from Transfermarkt; plus Elo and rolling form windows.',
      ),
    },
    {
      title: pick(lang, '评估口径', 'Evaluation protocol'),
      desc: production
        ? pick(
            lang,
            `三分类（主胜/平局/客胜）样本外评估，测试集 ${fmtNum(production.test_n)} 场，生产模型 ${production.model} 准确率 ${production.acc.toFixed(2)}%、LogLoss ${production.logloss.toFixed(4)}。`,
            `Three-way (home/draw/away) out-of-sample evaluation on ${fmtNum(production.test_n)} matches; production model ${production.model} scores ${production.acc.toFixed(2)}% accuracy and ${production.logloss.toFixed(4)} LogLoss.`,
          )
        : '—',
    },
    {
      title: pick(lang, '线上表现', 'Live performance'),
      desc:
        hitRate !== null && evaluated !== null && totalPreds !== null
          ? pick(
              lang,
              `已入库 ${fmtNum(totalPreds)} 条预测，其中 ${fmtNum(evaluated)} 条已有实际结果，命中率 ${hitRate.toFixed(1)}%（以推荐项与实际结果比对）。`,
              `${fmtNum(totalPreds)} predictions stored, ${fmtNum(evaluated)} already resolved, hit rate ${hitRate.toFixed(1)}% (recommended outcome vs actual result).`,
            )
          : '—',
    },
    {
      title: pick(lang, '可解释性', 'Explainability'),
      desc: topFeature
        ? pick(
            lang,
            `特征重要性由梯度提升模型给出：当前最强特征是 ${topFeature.feature}（${(topFeature.importance * 100).toFixed(2)}），其次是期望进球差值、Elo 优势与阵容价值比。`,
            `Feature importance comes from the gradient-boosting model: the strongest signal is ${topFeature.feature} (${(topFeature.importance * 100).toFixed(2)}), followed by expected-goal differentials, Elo advantage and squad-value ratio.`,
          )
        : '—',
    },
  ]

  return (
    <>
      {loading ? <CardSkeleton rows={5} /> : null}
      {error ? <ErrorState text={error} /> : null}

      {production ? <ProductionCard m={production} t={t} lang={lang} /> : null}

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SectionCard
          title={pick(lang, '概率校准曲线', 'Probability calibration')}
          hint={pick(
            lang,
            '横轴为预测概率分箱 · 蓝色为实际频率 · 虚线为理想对角线',
            'X = predicted probability bins; blue = observed frequency; dashed = perfect calibration',
          )}
        >
          {calibration.length ? (
            <>
              <CalibrationChart rows={calibration} lang={lang} />
              <div className="mt-2 flex flex-wrap gap-x-5 gap-y-1">
                {OUTCOME_ORDER.filter((o) => calibration.some((c) => c.outcome === o)).map((o) => (
                  <span key={o} className="t-3 text-[10.5px]">
                    <span className="t-2 font-semibold">{outcomeLabel(t, o)}</span> ·{' '}
                    {calibration.filter((c) => c.outcome === o).length} {pick(lang, '个分箱', 'bins')}
                  </span>
                ))}
              </div>
            </>
          ) : (
            <Empty text={pick(lang, '暂无校准数据', 'No calibration data')} />
          )}
        </SectionCard>

        <SectionCard
          title={pick(lang, '特征重要性 Top 12', 'Feature importance — top 12')}
          hint={pick(lang, '数值为归一化重要性 ×100', 'Normalised importance ×100')}
        >
          <FeatureImportance rows={importance} />
        </SectionCard>
      </div>

      <div className="mt-4 grid grid-cols-1 gap-4 xl:grid-cols-2">
        <SectionCard
          title={pick(lang, '模型版本对比', 'Model version comparison')}
          hint={
            production
              ? pick(
                  lang,
                  `共 ${list.length} 个版本 · 全部在 ${fmtNum(production.test_n)} 场样本外测试`,
                  `${list.length} versions · all evaluated on ${fmtNum(production.test_n)} out-of-sample matches`,
                )
              : undefined
          }
        >
          <VersionTable rows={list} t={t} />
        </SectionCard>

        <SectionCard
          title={pick(lang, '最近预测', 'Recent predictions')}
          hint={pick(
            lang,
            `按比赛日期倒序 · 概率顺序为 ${t('match.home')} / ${t('match.draw')} / ${t('match.away')}`,
            'Newest fixtures first · probabilities as home / draw / away',
          )}
        >
          <RecentPicks rows={recent} t={t} lang={lang} />
        </SectionCard>
      </div>

      <SectionCard
        className="mt-4"
        title={pick(lang, '模型如何工作', 'How the model works')}
        hint={pick(lang, '全部数字取自当前接口返回', 'Every figure comes from the live API response')}
        right={
          production ? <Pill tone={statusTone(production.status)}>{statusLabel(t, production.status)}</Pill> : undefined
        }
      >
        <div className="grid grid-cols-1 gap-4 md:grid-cols-2 xl:grid-cols-4">
          {steps.map((s, i) => (
            <div key={s.title} className="glass-soft rounded-[20px] p-4">
              <div className="flex items-center gap-2">
                <span className="flex h-6 w-6 items-center justify-center rounded-full bg-ink text-[11px] font-bold text-white">
                  {i + 1}
                </span>
                <span className="t-1 text-[12.5px] font-semibold">{s.title}</span>
              </div>
              <p className="t-2 mt-2 text-[11.5px] leading-[1.7]">{s.desc}</p>
            </div>
          ))}
        </div>
      </SectionCard>
    </>
  )
}

/* ---------- 旧入口外壳（/agent 已重定向到 /admin?tab=models，保留直链兜底） ---------- */

export default function Agent() {
  const { lang } = useLang()

  return (
    <PageShell
      title={pick(lang, 'AI 分析', 'AI Analysis')}
      subtitle={pick(
        lang,
        '生产模型全貌 · 校准曲线 · 特征归因 · 版本对比',
        'Production model in full · calibration · feature attribution · version comparison',
      )}
      activePath="/agent"
    >
      <AgentBody />
    </PageShell>
  )
}
