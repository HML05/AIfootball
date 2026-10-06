import { useEffect, useMemo, useState } from 'react'
import { Link, useSearchParams } from 'react-router'
import { ChevronDown } from 'lucide-react'
import { PageShell, SectionCard, Pill, Pager, SearchBox, Tabs, EmptyState, ErrorState } from '../components/kit'
import { CardSkeleton } from '../components/Skeleton'
import type { Lang } from '../i18n'
import { useLang } from '../i18n'
import type { AskPayload, SearchHit, SearchPayload } from '../lib/api'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { fmtNum, pick } from '../data/live'

/* =====================================================================
 * 检索与问答 —— 一个页面两个页签：
 *   1) 全文检索：GET /api/ui/search（后端 jieba 索引，snippet 用【】标命中词）
 *   2) 智能问答：POST /api/ui/ask（库内事实 + 检索片段；配了 LLM_API_KEY 则走大模型）
 * 页面不写死任何数据，状态全部来自 /api/ui/ask/status 与实测返回。
 * ===================================================================== */

const LIMIT = 20

type TabKey = 'search' | 'ask'

/** 类型筛选（kind 为空串 = 全部，后端不带该参数） */
const KINDS: { value: string; zh: string; en: string }[] = [
  { value: '', zh: '全部', en: 'All' },
  { value: 'match', zh: '比赛', en: 'Matches' },
  { value: 'team', zh: '球队', en: 'Teams' },
  { value: 'player', zh: '球员', en: 'Players' },
  { value: 'prediction', zh: '预测', en: 'Predictions' },
  { value: 'doc', zh: '文档', en: 'Docs' },
]

/** 无关键词时用的空载荷（不发请求，避免空查询打接口） */
const EMPTY_SEARCH: SearchPayload = {
  query: '',
  tokens: [],
  operator: null,
  mode: '',
  kind: null,
  count: 0,
  returned: 0,
  kinds: [],
  hits: [],
}

/* ---------- 本地小工具 ---------- */

/** 站内路径（/matches/123、/teams/60…）可直接路由跳转；其余只展示来源表名 */
function stationPath(url: string | null): string | null {
  return url && url.startsWith('/') ? url : null
}

function modeLabel(lang: Lang, mode: string): string {
  if (mode === 'llm') return pick(lang, '大模型作答', 'LLM answer')
  if (mode === 'retrieval') return pick(lang, '检索摘要', 'Retrieval summary')
  if (mode === 'empty') return pick(lang, '未匹配到内容', 'No match')
  return mode
}

/** 后端 intent 为英文枚举 → 中文映射 */
function intentLabel(lang: Lang, intent: string | null): string | null {
  if (!intent) return null
  const map: Record<string, [string, string]> = {
    predict: ['胜负预测', 'Prediction'],
    h2h: ['历史交锋', 'Head-to-head'],
    form: ['近期状态', 'Recent form'],
    standings: ['积分榜', 'Standings'],
    player: ['球员资料', 'Player'],
    team: ['球队资料', 'Team'],
    search: ['全文检索', 'Full-text search'],
    compare: ['对比', 'Comparison'],
  }
  const hit = map[intent]
  return hit ? pick(lang, hit[0], hit[1]) : intent
}

/** 工具参数：字符串直出，其余 JSON 化（后端 args 为数组）；过长截断防止撑破布局 */
function argsText(args: unknown[]): string {
  if (!Array.isArray(args) || args.length === 0) return '—'
  const s = args.map((a) => (typeof a === 'string' ? a : JSON.stringify(a))).join(' · ')
  return s.length > 160 ? `${s.slice(0, 160)}…` : s
}

/** snippet 里的【命中词】→ 高亮 span，其余纯文本（不用 dangerouslySetInnerHTML） */
function Snippet({ text }: { text: string }) {
  const parts = text.split(/【([^】]*)】/)
  return (
    <>
      {parts.map((p, i) =>
        i % 2 === 1 ? (
          <span key={i} className="rounded-[5px] bg-[#F6C945]/55 px-0.5 font-semibold text-[#6b4d05]">
            {p}
          </span>
        ) : (
          <span key={i}>{p}</span>
        ),
      )}
    </>
  )
}

/* ---------- 单条检索结果 ---------- */

function HitLine({ hit, lang }: { hit: SearchHit; lang: Lang }) {
  const to = stationPath(hit.source.url)
  return (
    <div className="glass-soft card-hover anim-in flex flex-col gap-1.5 rounded-[20px] p-3.5">
      <div className="flex flex-wrap items-center gap-x-2 gap-y-1.5">
        <Pill tone="blue">{hit.kind_label}</Pill>
        <span className="t-3 shrink-0 text-[10.5px] tabular-nums">
          {pick(lang, '相关度', 'Score')} {hit.score.toFixed(2)}
        </span>
        <span className="t-3 ml-auto shrink-0 text-[10.5px]">{hit.source.table}</span>
      </div>

      {to ? (
        <Link
          to={to}
          title={hit.title}
          className="t-1 text-[13.5px] font-medium break-words underline decoration-dotted underline-offset-4 transition-opacity duration-300 hover:opacity-75"
        >
          {hit.title}
        </Link>
      ) : (
        <span className="t-1 text-[13.5px] font-medium break-words" title={hit.title}>
          {hit.title}
        </span>
      )}

      <p className="t-2 text-[11.5px] leading-relaxed break-words">
        <Snippet text={hit.snippet} />
      </p>

      <span className="t-3 text-[10px] tabular-nums">
        {hit.ref}
        {hit.source.id !== undefined && hit.source.id !== null ? ` · #${hit.source.id}` : ''}
      </span>
    </div>
  )
}

/* ---------- 问答结果 ---------- */

function AnswerView({ data, lang }: { data: AskPayload; lang: Lang }) {
  const [open, setOpen] = useState(false)
  const intent = intentLabel(lang, data.intent ?? data.plan.intent)

  return (
    <div className="mt-4">
      {/* missing：缺 key / 索引不可用等——放在回答上方醒目列出 */}
      {data.missing.length > 0 ? (
        <div className="mb-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[20px] bg-[#E8B4B8]/40 px-4 py-2.5 text-[11.5px] leading-relaxed text-[#7a3540]">
          <span className="font-semibold">{pick(lang, '注意', 'Notice')}</span>
          {data.missing.map((m) => (
            <span key={m}>· {m}</span>
          ))}
        </div>
      ) : null}

      <div className="flex flex-wrap items-center gap-2">
        <Pill tone={data.mode === 'llm' ? 'green' : 'muted'}>{modeLabel(lang, data.mode)}</Pill>
        {intent ? <Pill tone="blue">{intent}</Pill> : null}
        <span className="t-3 text-[10.5px] tabular-nums">{data.elapsed_ms} ms</span>
        {data.llm.ok && data.llm.model ? <span className="t-3 text-[10.5px]">{data.llm.model}</span> : null}
      </div>

      <div className="glass-soft mt-2.5 rounded-[20px] px-4 py-3.5">
        {data.answer ? (
          <p className="t-1 text-[12.5px] leading-relaxed whitespace-pre-wrap break-words">{data.answer}</p>
        ) : (
          <p className="t-3 text-[12px]">{pick(lang, '本次没有生成回答', 'No answer was produced')}</p>
        )}
      </div>

      {/* 可折叠：执行了哪些步骤 + 耗时 */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="glass-soft t-2 mt-2.5 flex w-full items-center gap-2 rounded-[20px] px-4 py-2.5 text-[11.5px] font-semibold transition-colors duration-300 hover:bg-white/45"
      >
        <ChevronDown size={14} className={`shrink-0 transition-transform duration-300 ${open ? 'rotate-180' : ''}`} />
        {pick(lang, '执行了哪些步骤', 'What the assistant ran')}
        <span className="t-3 ml-auto shrink-0 text-[10.5px] font-medium tabular-nums">
          {data.plan.steps.length} {pick(lang, '步', 'steps')} · {data.timing.total_ms} ms
        </span>
      </button>

      {open ? (
        <div className="mt-2 flex flex-col gap-2">
          {data.plan.keywords.length > 0 ? (
            <p className="t-3 text-[10.5px] break-words">
              {pick(lang, '关键词', 'Keywords')}：{data.plan.keywords.join(' · ')}
            </p>
          ) : null}

          {data.plan.steps.length > 0 ? (
            data.plan.steps.map((s, i) => (
              <div key={`${s.tool}-${i}`} className="glass-soft flex flex-col gap-1 rounded-[16px] px-3.5 py-2.5">
                <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
                  <Pill tone="ink">{s.tool}</Pill>
                  <span className="t-3 text-[10.5px] break-words tabular-nums">{argsText(s.args)}</span>
                </div>
                <span className="t-2 text-[11px] leading-relaxed">{s.reason}</span>
              </div>
            ))
          ) : (
            <p className="t-3 text-[11px]">{pick(lang, '本次未调用工具（纯检索摘要）', 'No tool was called (retrieval only)')}</p>
          )}

          <div className="flex flex-wrap items-center gap-1.5">
            <Pill tone="muted">
              {pick(lang, '工具', 'Tools')} {data.timing.tools_ms} ms
            </Pill>
            <Pill tone="muted">
              {pick(lang, '检索', 'Search')} {data.timing.search_ms} ms
            </Pill>
            <Pill tone="muted">
              {pick(lang, '大模型', 'LLM')} {data.timing.llm_ms} ms
            </Pill>
            <Pill tone="muted">
              {pick(lang, '合计', 'Total')} {data.timing.total_ms} ms
            </Pill>
          </div>

          {!data.llm.ok && data.llm.error ? (
            <p className="text-[11px] leading-relaxed break-words text-[#7a3540]">
              {pick(lang, '大模型调用失败', 'LLM call failed')}：{data.llm.error}
            </p>
          ) : null}

          {data.facts.length > 0 ? (
            <div className="flex flex-col gap-1.5">
              <p className="t-3 text-[10.5px] font-semibold uppercase tracking-wide">
                {pick(lang, '工具返回', 'Tool results')}
              </p>
              {data.facts.map((f, i) => (
                <div
                  key={`${f.tool}-${i}`}
                  className="glass-soft flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[16px] px-3.5 py-2 text-[11px]"
                >
                  <span className={`shrink-0 font-semibold ${f.ok ? 'text-[#255a30]' : 'text-[#7a3540]'}`}>
                    {f.ok ? '✓' : '✗'}
                  </span>
                  <span className="t-2 shrink-0">{f.tool}</span>
                  <span className="t-2 break-words">{f.summary}</span>
                </div>
              ))}
            </div>
          ) : null}
        </div>
      ) : null}

      {/* 引用来源 */}
      <div className="mt-3">
        <p className="t-3 text-[10.5px] font-semibold uppercase tracking-wide">
          {pick(lang, '引用来源', 'Sources')} ({data.sources.length})
        </p>
        <div className="mt-1.5 flex flex-col gap-1.5">
          {data.sources.map((s) => {
            const to = stationPath(s.url)
            return (
              <div
                key={`${s.n}-${s.table}-${s.id}`}
                className="glass-soft flex flex-wrap items-center gap-x-2 gap-y-1 rounded-[16px] px-3.5 py-2 text-[11.5px]"
              >
                <span className="t-3 shrink-0 tabular-nums">[{s.n}]</span>
                <span className="t-2 shrink-0">{s.table}</span>
                <span className="t-3 shrink-0 tabular-nums">#{s.id}</span>
                <span className="t-1 font-medium break-words">{s.label}</span>
                {to ? (
                  <Link
                    to={to}
                    className="t-2 ml-auto shrink-0 underline decoration-dotted underline-offset-4"
                  >
                    {pick(lang, '打开 →', 'Open →')}
                  </Link>
                ) : (
                  <span className="t-3 ml-auto shrink-0 text-[10px]">{s.via}</span>
                )}
              </div>
            )
          })}
          {data.sources.length === 0 ? (
            <span className="t-3 text-[11px]">{pick(lang, '本次没有引用来源', 'No sources for this answer')}</span>
          ) : null}
        </div>
      </div>
    </div>
  )
}

/* ---------- 页面 ---------- */

/** 从 URL 读取状态（可分享/可直接访问 /ask?tab=ask&q=皇马&kind=team&page=2） */
function readState(sp: URLSearchParams) {
  const tabRaw = (sp.get('tab') ?? '').toLowerCase()
  const tab: TabKey = tabRaw === 'ask' ? 'ask' : 'search'
  const rawKind = (sp.get('kind') ?? '').toLowerCase()
  const kind = KINDS.some((k) => k.value !== '' && k.value === rawKind) ? rawKind : ''
  const q = sp.get('q') ?? ''
  const pageRaw = Number(sp.get('page') ?? '1')
  const page = Number.isFinite(pageRaw) && pageRaw >= 1 ? Math.floor(pageRaw) : 1
  return { tab, q, kind, page }
}

export default function Ask() {
  const { lang } = useLang()
  const [searchParams, setSearchParams] = useSearchParams()
  const initial = useMemo(() => readState(searchParams), []) // 只在挂载时读一次
  const [tab, setTab] = useState<TabKey>(initial.tab)
  const [q, setQ] = useState(initial.q)
  const [debouncedQ, setDebouncedQ] = useState(initial.q)
  const [kind, setKind] = useState(initial.kind)
  const [page, setPage] = useState(initial.page)

  // 输入防抖，避免每敲一个字母都打一次接口
  useEffect(() => {
    const t = window.setTimeout(() => setDebouncedQ(q.trim()), 320)
    return () => window.clearTimeout(t)
  }, [q])

  // 状态写回 URL（空值不写入，保持地址干净）
  useEffect(() => {
    const next = new URLSearchParams()
    if (tab !== 'search') next.set('tab', tab)
    if (q.trim()) next.set('q', q.trim())
    if (kind) next.set('kind', kind)
    if (page > 1) next.set('page', String(page))
    setSearchParams(next, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tab, q, kind, page])

  const status = useApi(api.askStatus, 'ask:status')

  const key = `search:${debouncedQ}:${kind}:${page}`
  const { data, loading, error } = useApi(
    (signal) =>
      debouncedQ
        ? api.search(debouncedQ, { kind, limit: LIMIT, offset: (page - 1) * LIMIT }, signal)
        : Promise.resolve(EMPTY_SEARCH),
    key,
  )

  const total = data?.count ?? 0
  const pages = Math.max(1, Math.ceil(total / LIMIT))
  // URL 带来的页码可能超出总页数 → 拉回最后一页
  useEffect(() => {
    if (data && total > 0 && page > pages) setPage(pages)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [data, total, pages, page])

  /* 问答：直接调 POST /api/ui/ask，不用 useApi（GET 缓存不适用） */
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<AskPayload | null>(null)
  const [asking, setAsking] = useState(false)
  const [askError, setAskError] = useState<string | null>(null)

  const ask = async () => {
    const text = question.trim()
    if (!text || asking) return
    setAsking(true)
    setAskError(null)
    try {
      setAnswer(await api.ask(text, { useLlm: true, topK: 5 }))
    } catch (e) {
      setAskError(e instanceof Error ? e.message : String(e))
    } finally {
      setAsking(false)
    }
  }

  const st = status.data
  const hits = data?.hits ?? []

  return (
    <PageShell
      title={pick(lang, '检索与问答', 'Search & Ask')}
      subtitle={pick(
        lang,
        '在库内全文检索（比赛 / 球队 / 球员 / 预测 / 文档），或直接向问答助手提问',
        'Full-text search across the database — or ask the assistant directly',
      )}
      activePath="/ask"
      right={st ? <Pill tone={st.mode === 'llm' ? 'green' : 'muted'}>{modeLabel(lang, st.mode)}</Pill> : null}
    >
      {/* 状态条：作答模式 + 索引规模 */}
      {status.error && !st ? <ErrorState text={status.error} /> : null}
      {st ? (
        <div className="glass-soft flex flex-wrap items-center gap-x-4 gap-y-2 rounded-[24px] px-5 py-3">
          <Pill tone={st.mode === 'llm' ? 'green' : 'muted'}>{modeLabel(lang, st.mode)}</Pill>
          {st.llm_ready ? (
            <span className="t-3 text-[11px]">
              {pick(lang, '模型', 'Model')} {st.llm_model}
            </span>
          ) : null}
          <span className="t-2 flex flex-wrap items-center gap-x-4 gap-y-1 text-[11px] min-[760px]:ml-auto">
            <span>
              {pick(lang, '中文别名球队', 'Teams with CN alias')}{' '}
              <span className="t-1 font-semibold tabular-nums">{fmtNum(st.alias_teams)}</span>
            </span>
            <span>
              {pick(lang, '球员索引', 'Players indexed')}{' '}
              <span className="t-1 font-semibold tabular-nums">{fmtNum(st.players_indexed)}</span>
            </span>
            <span>
              {pick(lang, '联赛', 'Leagues')}{' '}
              <span className="t-1 font-semibold tabular-nums">{fmtNum(st.leagues_indexed)}</span>
            </span>
          </span>
        </div>
      ) : null}

      {st && !st.llm_ready ? (
        <div className="mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1 rounded-[20px] bg-[#E8B4B8]/40 px-4 py-2.5 text-[11.5px] leading-relaxed text-[#7a3540]">
          <span className="font-semibold">{pick(lang, '未配置 LLM_API_KEY', 'LLM_API_KEY is not configured')}</span>
          <span>
            {pick(
              lang,
              '当前为「检索摘要」模式（库内事实 + 检索片段）；填写 key 后自动切到大模型作答。',
              'Currently in retrieval-summary mode (in-database facts + search snippets); fill in the key to switch to LLM answers automatically.',
            )}
          </span>
        </div>
      ) : null}

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Tabs
          items={[
            { key: 'search', label: pick(lang, '全文检索', 'Full-text search') },
            { key: 'ask', label: pick(lang, '智能问答', 'Ask the assistant') },
          ]}
          value={tab}
          onChange={(k) => setTab(k === 'ask' ? 'ask' : 'search')}
        />
      </div>

      {tab === 'search' ? (
        <SectionCard
          className="mt-3"
          title={pick(lang, '全文检索', 'Full-text search')}
          hint={
            debouncedQ && data
              ? pick(
                  lang,
                  `命中 ${fmtNum(total)} 条 · 分词 ${data.mode || '—'}`,
                  `${fmtNum(total)} matches · tokenizer ${data.mode || '—'}`,
                )
              : pick(lang, '输入关键词开始检索', 'Type a keyword to search')
          }
          right={<Pill tone="yellow">{fmtNum(data?.returned ?? 0)}</Pill>}
        >
          <div className="flex flex-wrap items-center gap-2">
            <SearchBox
              value={q}
              onChange={(v) => {
                setQ(v)
                setPage(1)
              }}
              placeholder={pick(lang, '搜索球队 / 球员 / 比赛 / 文档…', 'Search teams, players, matches, docs…')}
              className="w-full min-[760px]:w-[320px]"
            />
            {data && data.tokens.length > 0 ? (
              <span className="t-3 text-[10.5px] break-words">
                {pick(lang, '分词', 'Tokens')}：{data.tokens.join(' · ')}
              </span>
            ) : null}
          </div>

          <div className="mt-2.5 flex flex-wrap items-center gap-1.5">
            {KINDS.map((k) => (
              <button
                key={k.value || 'all'}
                type="button"
                onClick={() => {
                  setKind(k.value)
                  setPage(1)
                }}
                className="transition-transform duration-300 hover:scale-105 active:scale-95"
              >
                <Pill tone={kind === k.value ? 'ink' : 'muted'}>{pick(lang, k.zh, k.en)}</Pill>
              </button>
            ))}
            {data && data.operator ? (
              <span className="t-3 ml-auto text-[10.5px]">{pick(lang, `运算符 ${data.operator}`, `operator ${data.operator}`)}</span>
            ) : null}
          </div>

          {loading && !data ? <CardSkeleton rows={3} /> : null}
          {error && !data ? <ErrorState text={error} /> : null}

          <div className="mt-3 flex flex-col gap-2.5">
            {hits.map((h) => (
              <HitLine key={`${h.kind}:${h.id}`} hit={h} lang={lang} />
            ))}
          </div>

          {!debouncedQ ? (
            <EmptyState text={pick(lang, '输入关键词开始检索', 'Type a keyword to start searching')} />
          ) : null}
          {debouncedQ && data && hits.length === 0 && !loading ? (
            <EmptyState
              text={pick(lang, '没有匹配结果，换个关键词或类型试试', 'No matches — try another keyword or type')}
            />
          ) : null}

          {total > 0 ? (
            <Pager
              page={Math.min(page, pages)}
              pages={pages}
              total={total}
              onPage={setPage}
              unit={pick(lang, '条结果', 'results')}
            />
          ) : null}
        </SectionCard>
      ) : (
        <SectionCard
          className="mt-3"
          title={pick(lang, '智能问答', 'Ask the assistant')}
          hint={pick(
            lang,
            '基于库内事实与检索片段作答；证据不足时会明确说明',
            'Answers from in-database facts and retrieved snippets',
          )}
          right={answer ? <Pill tone={answer.mode === 'llm' ? 'green' : 'muted'}>{modeLabel(lang, answer.mode)}</Pill> : null}
        >
          <div className="flex flex-col gap-2.5">
            <textarea
              value={question}
              onChange={(e) => setQuestion(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
                  e.preventDefault()
                  void ask()
                }
              }}
              rows={3}
              placeholder={pick(
                lang,
                '例如：英超积分榜 / 皇马最近 5 场战绩 / 姆巴佩本赛季数据',
                'e.g. Premier League table / Real Madrid last 5 / Mbappé season stats',
              )}
              className="glass-soft t-1 w-full resize-y rounded-[20px] px-4 py-3 text-[12.5px] font-medium leading-relaxed outline-none placeholder:opacity-45"
            />
            <div className="flex flex-wrap items-center gap-3">
              <button
                type="button"
                onClick={() => void ask()}
                disabled={asking || !question.trim()}
                className="bg-ink rounded-full px-5 py-2 text-[12px] font-semibold text-white transition-transform duration-300 hover:scale-[1.03] active:scale-95 disabled:cursor-not-allowed disabled:opacity-40 disabled:hover:scale-100"
              >
                {asking ? pick(lang, '提问中…', 'Asking…') : pick(lang, '提问', 'Ask')}
              </button>
              <span className="t-3 text-[10.5px]">{pick(lang, 'Ctrl / ⌘ + Enter 快捷提问', 'Ctrl / ⌘ + Enter to ask')}</span>
            </div>
          </div>

          {askError ? <ErrorState text={askError} /> : null}
          {asking ? <CardSkeleton rows={2} /> : null}
          {answer && !asking ? <AnswerView data={answer} lang={lang} /> : null}
          {!answer && !asking && !askError ? (
            <EmptyState
              text={pick(lang, '输入问题后点「提问」', 'Type a question and press Ask')}
            />
          ) : null}
        </SectionCard>
      )}
    </PageShell>
  )
}
