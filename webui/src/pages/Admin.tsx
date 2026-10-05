/**
 * 管理端宿主 —— 4 个页签，URL 可直达、可分享。
 *
 *   /admin?tab=overview  数据总览    原 /admin 正文
 *   /admin?tab=asset     数据资产    原 /reports 正文（ReportsBody）
 *   /admin?tab=models    模型注册表  原 /agent 正文（AgentBody）
 *   /admin?tab=system    系统与接口  AdminSystem
 *
 * 只渲染一个 PageShell（旧页面 /reports、/agent 已由 App.tsx 重定向到这里）。
 * 页签切换只换正文，数据走 useApi 的模块级缓存 → 不会整页重新请求。
 */
import { useSearchParams } from 'react-router'
import type { CSSProperties } from 'react'
import { PageShell, Tabs, ErrorState } from '../components/kit'
import { DataDonut, GoalBands, IngestTrendChart, KpiCard, PipelineFunnel } from '../sections/admin/AdminCharts'
import { DatabaseTablesCard, LeagueStatsCard, QualityChecks } from '../sections/admin/AdminExtra'
import ModelRegistryTable from '../sections/admin/RecentHiresTable'
import { pick, useAdmin } from '../data/live'
import { useLang } from '../i18n'
import { ReportsBody } from './Reports'
import { AgentBody } from './Agent'
import AdminSystem from './AdminSystem'

const TABS = ['overview', 'asset', 'models', 'system'] as const
type AdminTab = (typeof TABS)[number]

/* ---------- 数据总览（原 Admin 正文，无壳） ---------- */

function AdminOverviewBody() {
  const { data, error } = useAdmin()

  return (
    <>
      {error && !data ? (
        <div className="mb-4">
          <ErrorState text={error} />
        </div>
      ) : null}

      {/* KPI 行 */}
      <div className="grid grid-cols-4 gap-5">
        {(data?.modules ?? []).map((kpi, i) => (
          <KpiCard key={kpi.id} kpi={kpi} delay={i * 80} />
        ))}
        {!data && [0, 1, 2, 3].map((i) => <div key={i} className="skeleton h-[168px] rounded-[28px]" />)}
      </div>

      {/* 入库趋势 + 数据分布 */}
      <div className="mt-5 grid grid-cols-[minmax(0,1fr)_380px] gap-5">
        <IngestTrendChart />
        <DataDonut />
      </div>

      {/* 数据管道 + 进球时段 */}
      <div className="mt-5 grid grid-cols-2 gap-5">
        <PipelineFunnel />
        <GoalBands />
      </div>

      {/* 模型注册表 */}
      <div className="mt-5">
        <ModelRegistryTable />
      </div>

      {/* 质量检查 + 表规模 */}
      <div className="mt-5 grid grid-cols-2 gap-5">
        <QualityChecks />
        <DatabaseTablesCard />
      </div>

      {/* 联赛统计 */}
      <div className="mt-5">
        <LeagueStatsCard />
      </div>
    </>
  )
}

/* ---------- 页签宿主 ---------- */

export default function Admin() {
  const { lang } = useLang()
  // 与 AdminOverviewBody 共用缓存键 'admin' → 只发一次请求
  const { data } = useAdmin()
  const [searchParams, setSearchParams] = useSearchParams()

  const raw = searchParams.get('tab')
  const tab: AdminTab = (TABS as readonly string[]).includes(raw ?? '') ? (raw as AdminTab) : 'overview'

  const items = [
    { key: 'overview', label: pick(lang, '数据总览', 'Overview') },
    { key: 'asset', label: pick(lang, '数据资产', 'Data assets') },
    { key: 'models', label: pick(lang, '模型注册表', 'Model registry') },
    { key: 'system', label: pick(lang, '系统与接口', 'System & API') },
  ]

  return (
    <PageShell
      title={pick(lang, '管理端', 'Admin')}
      subtitle={pick(
        lang,
        '足球数据分析与 AI 预测系统 · 管理端',
        'Football analytics & AI prediction system · admin console',
      )}
      activePath="/admin"
      right={
        data ? (
          <span className="t-3 text-[11px] font-medium tabular-nums">
            {pick(lang, '数据截至', 'data as of')} {data.dataNow}
          </span>
        ) : undefined
      }
    >
      <div className="anim-in mt-6 flex flex-wrap items-center gap-3" style={{ '--d': '80ms' } as CSSProperties}>
        <Tabs items={items} value={tab} onChange={(k) => setSearchParams({ tab: k })} />
      </div>

      <div className="mt-5">
        {tab === 'overview' ? <AdminOverviewBody /> : null}
        {tab === 'asset' ? <ReportsBody /> : null}
        {tab === 'models' ? <AgentBody /> : null}
        {tab === 'system' ? <AdminSystem /> : null}
      </div>
    </PageShell>
  )
}
