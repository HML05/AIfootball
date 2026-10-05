/**
 * 球员列表页 —— 真实数据来自 /api/ui/players（players × teams × leagues）
 *
 * 版式：KPI 条 → 工具条（搜索 / 位置 / 联赛 / 排序）→ 表格（30/页）→ 分页。
 * 整行可点击进入 /players/:id；身价最高者琥珀高亮；空值统一 —。
 */
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router'
import { PageShell, SectionCard, Pill, Pager, SearchBox, Tabs, EmptyState, ErrorState, KpiStrip } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api, logoUrl } from '../lib/api'
import type { PlayerRow } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, initials, pick } from '../data/live'
import { posLabel } from '../lib/labels'
import { useLang } from '../i18n'

const PAGE_SIZE = 30

const GROUPS = [
  { key: '', zh: '全部', en: 'All' },
  { key: 'GK', zh: '门将', en: 'GK' },
  { key: 'DF', zh: '后卫', en: 'DF' },
  { key: 'MF', zh: '中场', en: 'MF' },
  { key: 'FW', zh: '前锋', en: 'FW' },
]

const SORTS = [
  { key: 'value', zh: '身价', en: 'Value' },
  { key: 'age', zh: '年龄', en: 'Age' },
  { key: 'name', zh: '姓名', en: 'Name' },
]

const GROUP_TONE: Record<string, 'yellow' | 'blue' | 'green' | 'pink' | 'muted'> = {
  GK: 'yellow',
  DF: 'blue',
  MF: 'green',
  FW: 'pink',
}

const FOOT_LABEL: Record<string, [string, string]> = {
  left: ['左', 'Left'],
  right: ['右', 'Right'],
  both: ['双', 'Both'],
}

/** 头像：加载失败/无图时降级成首字母圆片 */
function Avatar({ row }: { row: PlayerRow }) {
  const [bad, setBad] = useState(false)
  if (!row.photo_url || bad) {
    return (
      <span className="glass-soft t-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full text-[10px] font-bold">
        {initials(row.name)}
      </span>
    )
  }
  return (
    <img
      src={row.photo_url}
      alt=""
      loading="lazy"
      onError={() => setBad(true)}
      className="crest h-8 w-8 shrink-0 rounded-full"
    />
  )
}

/** 队徽：优先本地代理，失败时字母圆片 */
function TeamCrest({ id, url, name }: { id: number | null; url: string | null; name: string | null }) {
  const [bad, setBad] = useState(false)
  const src = logoUrl(id) ?? url ?? undefined
  if (!src || bad) {
    return (
      <span className="glass-soft t-3 flex h-5 w-5 shrink-0 items-center justify-center rounded-full text-[8px] font-bold">
        {initials(name ?? '?')}
      </span>
    )
  }
  return <img src={src} alt="" loading="lazy" onError={() => setBad(true)} className="crest h-5 w-5 shrink-0 rounded-full" />
}

function LeagueSelect({
  value,
  onChange,
  options,
}: {
  value: string
  onChange: (v: string) => void
  options: { id: number; name: string; nameEn: string }[]
}) {
  const { lang } = useLang()
  return (
    <div className="glass-soft flex items-center rounded-full px-3.5 py-[7px]">
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="t-1 max-w-[160px] cursor-pointer bg-transparent text-[11.5px] font-semibold outline-none"
        aria-label={pick(lang, '联赛筛选', 'League filter')}
      >
        <option value="">{pick(lang, '全部联赛', 'All leagues')}</option>
        {options.map((o) => (
          <option key={o.id} value={String(o.id)}>
            {pick(lang, o.name, o.nameEn)}
          </option>
        ))}
      </select>
    </div>
  )
}

/** 身价文本：后端 valueText 优先，缺失时按欧元数值现场格式化 */
function valueText(row: PlayerRow): string {
  if (row.valueText) return row.valueText
  const v = row.market_value
  if (!v) return '—'
  if (v >= 1_000_000) return v % 1_000_000 === 0 ? `${v / 1_000_000}M€` : `${(v / 1_000_000).toFixed(1)}M€`
  if (v >= 1_000) return `${Math.round(v / 1_000)}K€`
  return `${Math.round(v)}€`
}

export default function Players() {
  const { lang } = useLang()
  const navigate = useNavigate()
  const [mode, setMode] = useState<'players' | 'transfers'>('players')
  const [q, setQ] = useState('')
  const [qDeb, setQDeb] = useState('')
  const [group, setGroup] = useState('')
  const [league, setLeague] = useState('')
  const [sort, setSort] = useState('value')
  const [page, setPage] = useState(1)
  // 转会记录（tm_transfers，17.6 万行）
  const [tq, setTq] = useState('')
  const [tqDeb, setTqDeb] = useState('')
  const [tseason, setTseason] = useState('')
  const [tfee, setTfee] = useState('')
  const [tpage, setTpage] = useState(1)

  useEffect(() => {
    const t = setTimeout(() => setQDeb(q.trim()), 300)
    return () => clearTimeout(t)
  }, [q])

  useEffect(() => {
    const t = setTimeout(() => setTqDeb(tq.trim()), 300)
    return () => clearTimeout(t)
  }, [tq])

  useEffect(() => {
    setPage(1)
  }, [qDeb, group, league, sort])

  useEffect(() => {
    setTpage(1)
  }, [tqDeb, tseason, tfee])

  // 后端已修好 sort=name（PLAYER_SORTS 用 p.name_en 消歧义）→ 姓名排序同样走服务端全局排序
  const reqSort = sort
  const dir = sort === 'name' ? 'asc' : 'desc'
  const players = useApi(
    () => api.players({ page, size: PAGE_SIZE, q: qDeb, group, league: league || undefined, sort: reqSort, dir }),
    `players:${page}:${qDeb}:${group}:${league}:${sort}:${dir}`,
  )
  const leagues = useApi(() => api.leagues(), 'leagues', 600_000)
  const transfers = useApi(
    () =>
      api.transfers({
        page: tpage,
        size: PAGE_SIZE,
        q: tqDeb || undefined,
        season: tseason || undefined,
        min_fee: tfee || undefined,
      }),
    `transfers:${tpage}:${tqDeb}:${tseason}:${tfee}`,
    600_000,
  )

  const items = players.data?.items ?? []
  const total = players.data?.total ?? 0
  const pages = players.data?.pages ?? 1

  const pAgg = players.data?.aggregates
  const scopeLabel = group
    ? pick(lang, `${group} 位置`, `${group} only`)
    : league
      ? pick(lang, '所选联赛', 'selected league')
      : qDeb
        ? pick(lang, '搜索结果', 'search result')
        : pick(lang, '全库', 'whole database')

  const kpis = [
    {
      label: pick(lang, '球员总数', 'Players'),
      value: players.data ? fmtNum(total) : '—',
      sub: pick(lang, '库内全部球员', 'in database'),
    },
    {
      label: pick(lang, '含身价人数', 'With market value'),
      value: pAgg ? fmtNum(pAgg.withValue) : '—',
      sub: scopeLabel,
    },
    {
      label: pick(lang, '最高身价', 'Top value'),
      value: pAgg?.topValueText ?? '—',
      sub: pAgg ? pick(lang, pAgg.topValueName ?? '—', pAgg.topValueNameEn ?? '—') : '—',
    },
    {
      label: pick(lang, '平均年龄', 'Avg age'),
      value: pAgg?.avgAge != null ? pAgg.avgAge.toFixed(1) : '—',
      sub: pAgg ? `${scopeLabel} · ${pick(lang, '15-45 岁样本', 'ages 15-45')}` : '—',
    },
  ]

  const subtitle = players.data
    ? `${fmtNum(total)} ${pick(lang, '名球员', 'players')} · ${pick(lang, '身价 · 位置 · 球队', 'value · position · club')}`
    : pick(lang, '正在读取球员数据…', 'loading players…')

  /* ---------------- 转会记录（tm_transfers） ---------------- */
  const tItems = transfers.data?.items ?? []
  const tTotal = transfers.data?.total ?? 0
  const tPages = transfers.data?.pages ?? 1
  const tSeasons = (transfers.data?.seasons ?? []).slice(0, 8)
  const tTop = transfers.data?.top ?? []
  // 转会费统一用 €/M 口径（足球圈习惯），<1M 用 K
  const feeText = (v: string | null) => {
    const n = Number(v)
    if (!v || Number.isNaN(n) || n <= 0) return pick(lang, '未披露', 'undisclosed')
    if (n >= 1e6) {
      const m = n / 1e6
      const s = m >= 100 ? m.toFixed(0) : m >= 10 ? m.toFixed(1).replace(/\.0$/, '') : m.toFixed(2).replace(/\.?0+$/, '')
      return `€${s}M`
    }
    return `€${Math.round(n / 1e3)}K`
  }
  const FEE_STEPS = [
    { key: '', zh: '全部', en: 'All' },
    { key: '1000000', zh: '≥100 万€', en: '≥€1M' },
    { key: '10000000', zh: '≥1000 万€', en: '≥€10M' },
    { key: '50000000', zh: '≥5000 万€', en: '≥€50M' },
  ]
  const tKpis = [
    { label: pick(lang, '转会记录', 'Transfers'), value: transfers.data ? fmtNum(tTotal) : '—', sub: pick(lang, 'Transfermarkt 全库', 'whole dataset') },
    { label: pick(lang, '覆盖赛季', 'Seasons'), value: transfers.data ? fmtNum(transfers.data.seasons.length) : '—', sub: pick(lang, '按日期倒序取前 20', 'latest 20') },
    { label: pick(lang, '最大单笔', 'Record fee'), value: tTop.length ? feeText(tTop[0].transfer_fee) : '—', sub: tTop.length ? tTop[0].player_name : '—' },
    { label: pick(lang, '本页最高', 'Top on page'), value: tItems.length ? feeText(tItems[0].transfer_fee) : '—', sub: tItems.length ? tItems[0].player_name : '—' },
  ]

  return (
    <PageShell title={pick(lang, '球员分析', 'Players')} subtitle={subtitle} activePath="/players">
      <div className="anim-in mt-6 flex flex-wrap items-center gap-3">
        <Tabs
          items={[
            { key: 'players', label: pick(lang, '球员名单', 'Squad list') },
            { key: 'transfers', label: pick(lang, '转会记录', 'Transfers') },
          ]}
          value={mode}
          onChange={(k) => setMode(k === 'transfers' ? 'transfers' : 'players')}
        />
        <span className="t-3 text-[10.5px] font-medium">
          {mode === 'players'
            ? pick(lang, '4,745 名球员 · 身价 / 位置 / 球队', '4,745 players · value / position / club')
            : pick(lang, '17.6 万笔转会 · 按转会费倒序', '176k transfers · sorted by fee')}
        </span>
      </div>

      {mode === 'players' ? (
        <>
          <KpiStrip className="mt-4" items={kpis} />

          <div className="anim-in mt-5 flex flex-wrap items-center gap-3" style={{ '--d': '80ms' } as React.CSSProperties}>
            <SearchBox
              value={q}
              onChange={setQ}
              placeholder={pick(lang, '搜索球员姓名…', 'Search player…')}
              className="w-[240px]"
            />
            <Tabs items={GROUPS.map((g) => ({ key: g.key, label: pick(lang, g.zh, g.en) }))} value={group} onChange={setGroup} />
            <LeagueSelect value={league} onChange={setLeague} options={leagues.data?.items ?? []} />
            <Tabs items={SORTS.map((s) => ({ key: s.key, label: pick(lang, s.zh, s.en) }))} value={sort} onChange={setSort} />
          </div>

      <SectionCard
        className="mt-4"
        title={pick(lang, '球员明细', 'Player table')}
        hint={pick(lang, '点击任意一行查看详情 · 每页 30 名', 'click a row for detail · 30 per page')}
      >
        {players.loading && !players.data ? (
          <CardSkeleton rows={10} />
        ) : players.error ? (
          <ErrorState text={players.error} />
        ) : !items.length ? (
          <EmptyState text={pick(lang, '没有匹配的球员', 'No players match')} />
        ) : (
          <div className="-mx-1 overflow-x-auto">
            <table className="w-full min-w-[880px] border-collapse">
              <thead>
                <tr className="t-3 text-left text-[10px] font-semibold uppercase tracking-wider">
                  <th className="w-[42px] pb-3 pr-2">#</th>
                  <th className="pb-3 pr-3">{pick(lang, '球员', 'Player')}</th>
                  <th className="pb-3 pr-3">{pick(lang, '球队', 'Club')}</th>
                  <th className="pb-3 pr-3">{pick(lang, '位置', 'Position')}</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '年龄', 'Age')}</th>
                  <th className="pb-3 pr-3 text-right">{pick(lang, '身高', 'Height')}</th>
                  <th className="pb-3 pr-3">{pick(lang, '国籍', 'Nation')}</th>
                  <th className="pb-3 pr-3">{pick(lang, '惯用脚', 'Foot')}</th>
                  <th className="pb-3 text-right">{pick(lang, '身价', 'Value')}</th>
                </tr>
              </thead>
              <tbody>
                {items.map((p, i) => {
                  const rank = (page - 1) * PAGE_SIZE + i + 1
                  const isTop = (pAgg?.topValue ?? 0) > 0 && (p.market_value ?? 0) === pAgg?.topValue
                  const foot = p.foot ? FOOT_LABEL[p.foot.toLowerCase()] : undefined
                  const label = pick(lang, p.name, p.name_en)
                  return (
                    <tr
                      key={p.player_id}
                      onClick={() => navigate(`/players/${p.player_id}`)}
                      className="line-c cursor-pointer border-t transition-colors duration-200 hover:bg-white/35"
                    >
                      <td className="py-2.5 pr-2">
                        {rank <= 3 ? (
                          <Pill tone="yellow">{rank}</Pill>
                        ) : (
                          <span className="t-3 text-[11px] font-semibold tabular-nums">{rank}</span>
                        )}
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2.5">
                          <Avatar row={p} />
                          <div className="min-w-0">
                            <p
                              className="t-1 max-w-[170px] truncate text-[13px] font-semibold"
                              title={label}
                            >
                              {label}
                            </p>
                            {p.name_en && p.name_en !== label ? (
                              <p className="t-3 max-w-[170px] truncate text-[10px] font-medium">{p.name_en}</p>
                            ) : null}
                          </div>
                        </div>
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2">
                          <TeamCrest id={p.team_id} url={p.team_logo} name={pick(lang, p.team, p.team_en)} />
                          <span className="t-2 max-w-[110px] truncate text-[11.5px] font-medium" title={pick(lang, p.team, p.team_en)}>
                            {p.team ? pick(lang, p.team, p.team_en) : '—'}
                          </span>
                        </div>
                      </td>
                      <td className="py-2.5 pr-3">
                        <div className="flex items-center gap-2">
                          <Pill tone={GROUP_TONE[p.group] ?? 'muted'}>{p.group || '—'}</Pill>
                          <span className="t-3 max-w-[86px] truncate text-[10px] font-medium">
                            {posLabel(lang, p.position)}
                          </span>
                        </div>
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">
                        {fmtNum(p.age)}
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">
                        {p.height === null || p.height === undefined ? '—' : `${fmtNum(p.height)} cm`}
                      </td>
                      <td className="py-2.5 pr-3">
                        <span className="t-2 block max-w-[110px] truncate text-[11.5px] font-medium" title={p.nationality ?? ''}>
                          {p.nationality ?? '—'}
                        </span>
                      </td>
                      <td className="t-2 py-2.5 pr-3 text-[11.5px] font-medium">
                        {foot ? pick(lang, foot[0], foot[1]) : '—'}
                      </td>
                      <td className="py-2.5 text-right">
                        {isTop ? (
                          <span className="rounded-full bg-[#F6C945]/45 px-2.5 py-1 text-[11.5px] font-semibold tabular-nums text-[#6b4d05]">
                            {valueText(p)}
                          </span>
                        ) : (
                          <span className="t-1 text-[12.5px] font-semibold tabular-nums">{valueText(p)}</span>
                        )}
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}
      </SectionCard>

      {players.data && items.length ? (
        <Pager page={players.data.page} pages={pages} total={total} onPage={setPage} unit={pick(lang, '名球员', 'players')} />
      ) : null}
        </>
      ) : (
        <>
          <KpiStrip className="mt-4" items={tKpis} />

          <div className="anim-in mt-5 flex flex-wrap items-center gap-3">
            <SearchBox
              value={tq}
              onChange={setTq}
              placeholder={pick(lang, '搜索球员 / 球队…', 'Search player / club…')}
              className="w-[240px]"
            />
            <Tabs
              items={tSeasons.map((s) => ({ key: s, label: s }))}
              value={tseason}
              onChange={(k) => setTseason(k === tseason ? '' : k)}
            />
            <Tabs items={FEE_STEPS.map((f) => ({ key: f.key, label: pick(lang, f.zh, f.en) }))} value={tfee} onChange={setTfee} />
          </div>

          <div className="mt-4 grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
            <SectionCard
              title={pick(lang, '转会流水', 'Transfer log')}
              hint={pick(lang, '按转会费倒序 · 每页 30 笔', 'by fee desc · 30 per page')}
            >
              {transfers.loading && !transfers.data ? (
                <CardSkeleton rows={10} />
              ) : transfers.error ? (
                <ErrorState text={transfers.error} />
              ) : !tItems.length ? (
                <EmptyState text={pick(lang, '没有匹配的转会记录', 'No transfers match')} />
              ) : (
                <div className="-mx-1 overflow-x-auto">
                  <table className="w-full min-w-[760px] border-collapse">
                    <thead>
                      <tr className="t-3 text-left text-[10px] font-semibold uppercase tracking-wider">
                        <th className="w-[92px] pb-3 pr-2">{pick(lang, '日期', 'Date')}</th>
                        <th className="pb-3 pr-3">{pick(lang, '球员', 'Player')}</th>
                        <th className="pb-3 pr-3">{pick(lang, '转出 → 转入', 'From → To')}</th>
                        <th className="pb-3 pr-3">{pick(lang, '类型', 'Type')}</th>
                        <th className="pb-3 pr-3 text-right">{pick(lang, '当时身价', 'Value then')}</th>
                        <th className="pb-3 text-right">{pick(lang, '转会费', 'Fee')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tItems.map((t, i) => (
                        <tr key={`${t.player_id}-${t.transfer_date}-${i}`} className="line-c border-t">
                          <td className="t-3 py-2.5 pr-2 text-[11px] font-medium tabular-nums">
                            {(t.transfer_date ?? '').slice(0, 10) || '—'}
                          </td>
                          <td className="py-2.5 pr-3">
                            <button
                              type="button"
                              onClick={() => navigate(`/players/${t.player_id}`)}
                              className="t-1 max-w-[160px] truncate text-[12.5px] font-semibold hover:underline"
                              title={t.player_name}
                            >
                              {t.player_name}
                            </button>
                            <p className="t-3 text-[10px] font-medium">{t.season_name}</p>
                          </td>
                          <td className="py-2.5 pr-3">
                            <span className="t-2 text-[11.5px] font-medium">{t.from_team_name ?? '—'}</span>
                            <span className="t-3 mx-1 text-[11px]">→</span>
                            <span className="t-1 text-[11.5px] font-semibold">{t.to_team_name ?? '—'}</span>
                          </td>
                          <td className="t-3 py-2.5 pr-3 text-[10.5px] font-medium">{t.transfer_type ?? '—'}</td>
                          <td className="t-2 py-2.5 pr-3 text-right text-[11.5px] font-medium tabular-nums">
                            {t.value_at_transfer ? feeText(t.value_at_transfer) : '—'}
                          </td>
                          <td className="py-2.5 text-right">
                            {Number(t.transfer_fee) > 0 ? (
                              <span className="rounded-full bg-[#F6C945]/45 px-2.5 py-1 text-[11.5px] font-semibold tabular-nums text-[#6b4d05]">
                                {feeText(t.transfer_fee)}
                              </span>
                            ) : (
                              <span className="t-3 text-[11.5px] font-medium">{feeText(t.transfer_fee)}</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </SectionCard>

            <SectionCard
              dark
              title={pick(lang, '历史标王', 'Record fees')}
              hint={pick(lang, '全库转会费 Top 10', 'top 10 all-time')}
            >
              {!tTop.length ? (
                <CardSkeleton rows={5} />
              ) : (
                <ul className="flex flex-col">
                  {tTop.slice(0, 10).map((t, i) => (
                    <li key={`${t.player_name}-${i}`} className={`flex items-center gap-2.5 py-2 ${i > 0 ? 'border-t border-white/10' : ''}`}>
                      <span className="on-ink w-4 shrink-0 text-[11px] font-semibold tabular-nums opacity-60">{i + 1}</span>
                      <div className="min-w-0 flex-1">
                        <p className="on-ink truncate text-[12.5px] font-semibold" title={t.player_name}>
                          {t.player_name}
                        </p>
                        <p className="on-ink truncate text-[10px] font-medium opacity-65">
                          {t.from_team_name ?? '—'} → {t.to_team_name ?? '—'} · {t.season_name}
                        </p>
                      </div>
                      <span className="on-ink shrink-0 text-[12px] font-semibold tabular-nums text-[#F6C945]">
                        {feeText(t.transfer_fee)}
                      </span>
                    </li>
                  ))}
                </ul>
              )}
            </SectionCard>
          </div>

          {transfers.data && tItems.length ? (
            <Pager page={transfers.data.page} pages={tPages} total={tTotal} onPage={setTpage} unit={pick(lang, '笔转会', 'transfers')} />
          ) : null}
        </>
      )}
    </PageShell>
  )
}
