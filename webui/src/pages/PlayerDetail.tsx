/**
 * 球员详情页 —— 真实数据来自 /api/ui/players/{id}（players × team_radar × appearances）
 *
 * 版式：左列球员卡（头像 / 姓名 / 球队 / 位置 / 基本信息 / 身价），
 * 右列三块：能力画像（7 维分位条）、效率（每 90 分钟）、赛季数据表。
 * 注意：详情接口返回的是 players 表原始行，没有 group / valueText，需要前端自行推导。
 * radar 为 null 时优雅降级为「暂无画像数据」。
 */
import { useState } from 'react'
import { Link, useParams } from 'react-router'
import { PageShell, SectionCard, Pill, Bar, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import { api, logoUrl } from '../lib/api'
import type { PlayerRow, PlayerRadar } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, initials, pct, pick } from '../data/live'
import { posLabel } from '../lib/labels'
import { useLang } from '../i18n'

type DimKey = 's_goals' | 's_assists' | 's_involve' | 's_minutes' | 's_discipline' | 's_value' | 's_experience'

const DIMS: { key: DimKey; zh: string; en: string }[] = [
  { key: 's_goals', zh: '进球', en: 'Goals' },
  { key: 's_assists', zh: '助攻', en: 'Assists' },
  { key: 's_involve', zh: '参与进球', en: 'Involvement' },
  { key: 's_minutes', zh: '出场时间', en: 'Minutes' },
  { key: 's_discipline', zh: '纪律', en: 'Discipline' },
  { key: 's_value', zh: '身价', en: 'Value' },
  { key: 's_experience', zh: '经验', en: 'Experience' },
]

const GROUP_TONE: Record<string, 'yellow' | 'blue' | 'green' | 'pink' | 'muted'> = {
  GK: 'yellow',
  DF: 'blue',
  MF: 'green',
  FW: 'pink',
}

const GROUP_LABEL: Record<string, [string, string]> = {
  GK: ['门将', 'Goalkeeper'],
  DF: ['后卫', 'Defender'],
  MF: ['中场', 'Midfielder'],
  FW: ['前锋', 'Forward'],
}

const FOOT_LABEL: Record<string, [string, string]> = {
  left: ['左脚', 'Left'],
  right: ['右脚', 'Right'],
  both: ['双脚', 'Both'],
}

/** 由原始 position 文案推导位置分组（详情接口不含 group 字段） */
function posGroup(position: string | null | undefined): string {
  const s = (position ?? '').toLowerCase()
  if (s.includes('keeper')) return 'GK'
  if (s.includes('defen') || s.includes('back')) return 'DF'
  if (s.includes('midfield')) return 'MF'
  if (s.includes('attack') || s.includes('forward') || s.includes('wing') || s.includes('striker')) return 'FW'
  return ''
}

/** 身价文本：后端 _fmt_value 同规则（>=1M → xM€，整百万不留小数） */
function valueOf(v: number | null | undefined): string {
  if (v === null || v === undefined || Number.isNaN(v) || v <= 0) return '—'
  if (v >= 1_000_000) return v % 1_000_000 === 0 ? `${v / 1_000_000}M€` : `${(v / 1_000_000).toFixed(1)}M€`
  if (v >= 1_000) return `${Math.round(v / 1_000)}K€`
  return `${Math.round(v)}€`
}

function Photo({ url, name, size = 104 }: { url: string | null; name: string; size?: number }) {
  const [bad, setBad] = useState(false)
  if (!url || bad) {
    return (
      <span
        className="glass-soft t-2 flex shrink-0 items-center justify-center rounded-full font-semibold"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.3) }}
      >
        {initials(name)}
      </span>
    )
  }
  return (
    <img
      src={url}
      alt=""
      onError={() => setBad(true)}
      className="crest shrink-0 rounded-full"
      style={{ width: size, height: size }}
    />
  )
}

function Crest({ id, url, name, size = 20 }: { id: number | null; url: string | null; name: string; size?: number }) {
  const [bad, setBad] = useState(false)
  const src = logoUrl(id) ?? url ?? undefined
  if (!src || bad) {
    return (
      <span
        className="glass-soft t-3 flex shrink-0 items-center justify-center rounded-full font-bold"
        style={{ width: size, height: size, fontSize: Math.round(size * 0.4) }}
      >
        {initials(name)}
      </span>
    )
  }
  return (
    <img
      src={src}
      alt=""
      onError={() => setBad(true)}
      className="crest shrink-0 rounded-full"
      style={{ width: size, height: size }}
    />
  )
}

function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="min-w-0">
      <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{label}</p>
      <p className="t-1 mt-0.5 truncate text-[13px] font-semibold tabular-nums" title={value}>
        {value}
      </p>
    </div>
  )
}

function Tile({ label, value, sub }: { label: string; value: string; sub?: string }) {
  return (
    <div className="glass-soft rounded-2xl px-3 py-2.5">
      <p className="t-3 truncate text-[10px] font-semibold uppercase tracking-wider" title={label}>
        {label}
      </p>
      <p className="t-1 mt-1.5 text-[19px] font-semibold leading-none tabular-nums">{value}</p>
      {sub ? <p className="t-3 mt-1 text-[10px] font-medium">{sub}</p> : null}
    </div>
  )
}

export default function PlayerDetail() {
  const { lang } = useLang()
  const { id } = useParams()
  const { data, loading, error } = useApi(() => api.player(Number(id)), `player:${id}`)

  if (loading && !data) {
    return (
      <PageShell title={pick(lang, '球员详情', 'Player')} subtitle={pick(lang, '正在读取…', 'loading…')} activePath="/players">
        <div className="mt-6">
          <CardSkeleton rows={10} />
        </div>
      </PageShell>
    )
  }

  if (error || !data) {
    return (
      <PageShell title={pick(lang, '球员详情', 'Player')} subtitle={pick(lang, '球员数据', 'player data')} activePath="/players">
        <div className="mt-6">
          <ErrorState text={error ?? pick(lang, '未找到该球员', 'Player not found')} />
        </div>
      </PageShell>
    )
  }

  const p: PlayerRow = data.player
  const radar: PlayerRadar | null = data.radar
  const seasons = data.seasons ?? []

  const name = pick(lang, p.name, p.name_en)
  const teamName = pick(lang, p.team, p.team_en)
  const group = radar?.pos_group || posGroup(p.position)
  const groupLabel = GROUP_LABEL[group]
  const foot = p.foot ? FOOT_LABEL[p.foot.toLowerCase()] : undefined
  const value = p.valueText ?? valueOf(p.market_value)

  const dimValues = DIMS.map((d) => (radar ? Number(radar[d.key] ?? 0) : 0))
  const best = dimValues.length ? Math.max(...dimValues) : 0

  const efficiency = [
    { label: pick(lang, '每 90 分钟进球', 'Goals / 90'), value: fmtNum(radar?.goals_p90, 2) },
    { label: pick(lang, '每 90 分钟助攻', 'Assists / 90'), value: fmtNum(radar?.assists_p90, 2) },
    { label: pick(lang, '每 90 分钟参与', 'Involvement / 90'), value: fmtNum(radar?.involve_p90, 2) },
    {
      label: pick(lang, '出场时间占比', 'Minutes share'),
      value: pct(radar?.minutes_share === null || radar?.minutes_share === undefined ? null : radar.minutes_share * 100),
    },
    { label: pick(lang, '每 90 分钟黄牌', 'Cards / 90'), value: fmtNum(radar?.cards_p90, 2) },
  ]

  const career = [
    { label: pick(lang, '出场', 'Apps'), value: fmtNum(radar?.apps) },
    { label: pick(lang, '进球', 'Goals'), value: fmtNum(radar?.goals) },
    { label: pick(lang, '助攻', 'Assists'), value: fmtNum(radar?.assists) },
    { label: pick(lang, '黄牌', 'Cards'), value: fmtNum(radar?.cards) },
    { label: pick(lang, '出场分钟', 'Minutes'), value: fmtNum(radar?.minutes) },
  ]

  const subtitle = [p.league ? pick(lang, p.league, p.league_en) : '', teamName, groupLabel ? pick(lang, groupLabel[0], groupLabel[1]) : '']
    .filter(Boolean)
    .join(' · ')

  return (
    <PageShell title={name} subtitle={subtitle || pick(lang, '球员数据', 'player data')} activePath="/players">
      <div className="mt-6 grid grid-cols-[380px_minmax(0,1fr)] gap-5">
        {/* 左列：球员卡 */}
        <div className="anim-in" style={{ '--d': '60ms' } as React.CSSProperties}>
          <SectionCard>
            <div className="flex flex-col items-center text-center">
              <Photo url={p.photo_url} name={name} />
              <h2 className="t-1 mt-4 break-words text-[24px] font-semibold leading-tight">{name}</h2>
              {p.name_en && p.name_en !== name ? <p className="t-3 mt-1 text-[12px] font-medium">{p.name_en}</p> : null}
              <Link
                to="/teams"
                className="glass-soft card-hover mt-3.5 flex items-center gap-2 rounded-full px-3.5 py-1.5"
                title={pick(lang, '查看球队页', 'Open teams page')}
              >
                <Crest id={p.team_id} url={p.team_logo} name={teamName} />
                <span className="t-1 max-w-[210px] truncate text-[12px] font-semibold">{teamName || '—'}</span>
              </Link>
              <div className="mt-3 flex items-center gap-2">
                {group ? <Pill tone={GROUP_TONE[group] ?? 'muted'}>{group}</Pill> : null}
                <span className="t-3 text-[11px] font-medium">{posLabel(lang, p.position)}</span>
              </div>
            </div>

            <div className="line-c mt-5 grid grid-cols-2 gap-x-4 gap-y-3.5 border-t pt-4 text-left">
              <InfoRow label={pick(lang, '年龄', 'Age')} value={fmtNum(p.age)} />
              <InfoRow
                label={pick(lang, '身高', 'Height')}
                value={p.height === null || p.height === undefined ? '—' : `${fmtNum(p.height)} cm`}
              />
              <InfoRow label={pick(lang, '惯用脚', 'Foot')} value={foot ? pick(lang, foot[0], foot[1]) : '—'} />
              <InfoRow label={pick(lang, '球衣号', 'Shirt')} value={p.number === null || p.number === undefined ? '—' : `#${p.number}`} />
              <InfoRow label={pick(lang, '国籍', 'Nation')} value={p.nationality ?? '—'} />
              <InfoRow label={pick(lang, '联赛', 'League')} value={pick(lang, p.league, p.league_en) || '—'} />
            </div>

            <div className="line-c mt-4 border-t pt-4 text-left">
              <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{pick(lang, '市场身价', 'Market value')}</p>
              <p className="mt-1 text-[27px] font-semibold leading-none tabular-nums text-[#6b4d05]">{value}</p>
            </div>
          </SectionCard>
        </div>

        {/* 右列：画像 / 效率 / 赛季 */}
        <div className="anim-in flex min-w-0 flex-col gap-5" style={{ '--d': '120ms' } as React.CSSProperties}>
          <SectionCard
            title={pick(lang, '能力画像', 'Ability Profile')}
            hint={pick(lang, '同位置球员分位（0-100）', 'percentile vs same position (0-100)')}
          >
            {!radar ? (
              <EmptyState text={pick(lang, '暂无画像数据', 'No profile data')} />
            ) : (
              <div className="flex flex-col gap-2.5">
                {DIMS.map((d, i) => {
                  const v = dimValues[i]
                  const isBest = v > 0 && v === best
                  return (
                    <div key={d.key} className="flex items-center gap-3">
                      <span className="t-2 w-[68px] shrink-0 text-[11.5px] font-medium">{pick(lang, d.zh, d.en)}</span>
                      <span className="min-w-0 flex-1">
                        <Bar value={v} max={100} tone={isBest ? 'yellow' : 'blue'} height={7} />
                      </span>
                      <span
                        className={`w-8 shrink-0 text-right text-[12px] font-semibold tabular-nums ${isBest ? 'text-[#6b4d05]' : 't-2'}`}
                      >
                        {Math.round(v)}
                      </span>
                    </div>
                  )
                })}
              </div>
            )}
          </SectionCard>

          <SectionCard
            title={pick(lang, '效率（每 90 分钟）', 'Efficiency (per 90)')}
            hint={pick(lang, '生涯累计口径', 'career totals basis')}
          >
            {!radar ? (
              <EmptyState text={pick(lang, '暂无效率数据', 'No efficiency data')} />
            ) : (
              <>
                <div className="grid grid-cols-5 gap-3">
                  {efficiency.map((e) => (
                    <Tile key={e.label} label={e.label} value={e.value} />
                  ))}
                </div>
                <div className="line-c mt-4 grid grid-cols-5 gap-3 border-t pt-4">
                  {career.map((c) => (
                    <div key={c.label} className="min-w-0">
                      <p className="t-3 text-[10px] font-semibold uppercase tracking-wider">{c.label}</p>
                      <p className="t-1 mt-1 text-[15px] font-semibold tabular-nums">{c.value}</p>
                    </div>
                  ))}
                </div>
              </>
            )}
          </SectionCard>

          <SectionCard
            title={pick(lang, '赛季数据', 'Season Stats')}
            hint={`${fmtNum(seasons.length)} ${pick(lang, '条记录', 'records')}`}
          >
            {!seasons.length ? (
              <EmptyState text={pick(lang, '暂无赛季数据', 'No season data')} />
            ) : (
              <div className="-mx-1 overflow-x-auto">
                <table className="w-full border-collapse">
                  <thead>
                    <tr className="t-3 text-left text-[10px] font-semibold uppercase tracking-wider">
                      <th className="pb-3 pr-3">{pick(lang, '赛季', 'Season')}</th>
                      <th className="pb-3 pr-3">{pick(lang, '赛事', 'Competition')}</th>
                      <th className="pb-3 pr-3">{pick(lang, '球队', 'Team')}</th>
                      <th className="pb-3 pr-3 text-right">{pick(lang, '出场', 'Apps')}</th>
                      <th className="pb-3 pr-3 text-right">{pick(lang, '进球', 'Goals')}</th>
                      <th className="pb-3 pr-3 text-right">{pick(lang, '助攻', 'Assists')}</th>
                      <th className="pb-3 pr-3 text-right">{pick(lang, '黄牌', 'YC')}</th>
                      <th className="pb-3 pr-3 text-right">{pick(lang, '红牌', 'RC')}</th>
                      <th className="pb-3 text-right">{pick(lang, '分钟', 'Minutes')}</th>
                    </tr>
                  </thead>
                  <tbody>
                    {seasons.map((s, i) => (
                      <tr
                        key={`${s.season_name}-${s.competition_name ?? ''}-${s.team_name ?? ''}-${i}`}
                        className="line-c border-t transition-colors duration-200 hover:bg-white/35"
                      >
                        <td className="t-1 py-2.5 pr-3 text-[12.5px] font-semibold tabular-nums">
                          {s.season_name || '—'}
                          {s.season_start ? <span className="t-3 ml-1 text-[10px] font-medium">{s.season_start}</span> : null}
                        </td>
                        <td className="t-2 py-2.5 pr-3 text-[12px] font-medium">{s.competition_name ?? '—'}</td>
                        <td className="py-2.5 pr-3">
                          <span className="t-2 block max-w-[150px] truncate text-[12px] font-medium" title={s.team_name ?? ''}>
                            {s.team_name ?? '—'}
                          </span>
                        </td>
                        <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">{fmtNum(s.appearances)}</td>
                        <td className="t-1 py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">{fmtNum(s.goals)}</td>
                        <td className="t-1 py-2.5 pr-3 text-right text-[12.5px] font-semibold tabular-nums">{fmtNum(s.assists)}</td>
                        <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">{fmtNum(s.yellow_cards)}</td>
                        <td className="t-2 py-2.5 pr-3 text-right text-[12.5px] font-medium tabular-nums">{fmtNum(s.red_cards)}</td>
                        <td className="t-2 py-2.5 text-right text-[12.5px] font-medium tabular-nums">{fmtNum(s.minutes)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </SectionCard>
        </div>
      </div>
    </PageShell>
  )
}
