import { BrainCircuit } from 'lucide-react'
import { pick, useAdmin } from '../../data/live'
import { useLang } from '../../i18n'

const STATUS_STYLES: Record<string, string> = {
  production: 'bg-[#F6C945]/25 text-[#F6C945]',
  challenger: 'bg-[#A8C5E2]/30 text-[#AECBE8]',
  baseline: 'bg-white/[0.08] text-[#B3AD97]',
}

const STATUS_LABEL: Record<string, [string, string]> = {
  production: ['生产', 'Production'],
  challenger: ['挑战者', 'Challenger'],
  baseline: ['基线', 'Baseline'],
}

/** 模型注册表（真实模型评估，样本外测试集） */
export default function ModelRegistryTable() {
  const { lang } = useLang()
  const { data } = useAdmin()
  const models = (data?.models ?? []).slice(0, 8)

  return (
    <div className="glass-dark card-hover anim-in rounded-[28px] p-5" style={{ '--d': '400ms' } as React.CSSProperties}>
      <div className="flex items-baseline justify-between">
        <span className="on-ink text-[16px] font-bold">{pick(lang, '模型注册表', 'Model Registry')}</span>
        <span className="text-[11px] font-medium text-[#8B8672]">
          {data ? `${data.models.length} ${pick(lang, '个模型 · 样本外评估', 'models · out-of-sample')}` : ''}
        </span>
      </div>

      <table className="mt-3 w-full border-collapse">
        <thead>
          <tr className="text-left text-[10px] font-semibold uppercase tracking-wider text-[#8B8672]">
            <th className="pb-2.5 pr-3">{pick(lang, '模型', 'Model')}</th>
            <th className="pb-2.5 pr-3 text-right">{pick(lang, '样本外', 'Test n')}</th>
            <th className="pb-2.5 pr-3 text-right">{pick(lang, '准确率', 'Accuracy')}</th>
            <th className="pb-2.5 pr-3 text-right">F1-macro</th>
            <th className="pb-2.5 pr-3 text-right">{pick(lang, '平局召回', 'Draw recall')}</th>
            <th className="pb-2.5 pr-3 text-right">LogLoss</th>
            <th className="pb-2.5 text-right">{pick(lang, '状态', 'Status')}</th>
          </tr>
        </thead>
        <tbody>
          {models.map((m, i) => (
            <tr key={`${m.model}-${i}`} className="table-row cursor-pointer border-t border-white/[0.07]">
              <td className="py-3 pr-3">
                <div className="flex items-center gap-2.5">
                  <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-white/[0.07] text-[#F6C945] ring-2 ring-white/10 transition-transform duration-300 hover:scale-110">
                    <BrainCircuit size={14} strokeWidth={2.2} />
                  </span>
                  <p className="on-ink max-w-[190px] truncate text-[13px] font-semibold" title={pick(lang, m.name, m.nameEn)}>
                    {pick(lang, m.name, m.nameEn)}
                  </p>
                </div>
              </td>
              <td className="py-3 pr-3 text-right text-[12px] font-medium tabular-nums text-[#B3AD97]">
                {m.test_n.toLocaleString()}
              </td>
              <td className="on-ink py-3 pr-3 text-right text-[13px] font-semibold tabular-nums">{m.acc.toFixed(2)}%</td>
              <td className="py-3 pr-3 text-right text-[12px] font-medium tabular-nums text-[#B3AD97]">
                {m.f1_macro.toFixed(4)}
              </td>
              <td className="py-3 pr-3 text-right text-[12px] font-medium tabular-nums text-[#B3AD97]">
                {m.draw_recall.toFixed(1)}%
              </td>
              <td className="py-3 pr-3 text-right text-[12px] font-medium tabular-nums text-[#B3AD97]">
                {m.logloss.toFixed(4)}
              </td>
              <td className="py-3 text-right">
                <span className={`whitespace-nowrap rounded-full px-2.5 py-1 text-[11px] font-semibold ${STATUS_STYLES[m.status] ?? STATUS_STYLES.baseline}`}>
                  {pick(lang, ...(STATUS_LABEL[m.status] ?? STATUS_LABEL.baseline))}
                </span>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
      {!models.length && <div className="mt-3 h-40 w-full animate-pulse rounded-2xl bg-white/[0.05]" />}
    </div>
  )
}
