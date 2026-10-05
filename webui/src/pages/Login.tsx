/**
 * 登录页（/login）—— 账号密码 + 手机扫码两种方式
 *
 * 数据来源: FastAPI /api/auth（src/api/auth.py）
 *   POST /login            {username, password, remember} → {token, user, expires_at}
 *   POST /qr/start         → {qr_id, secret, image_url, poll_url, expires_in, ...}
 *   GET  /qr/image?…       → PNG
 *   GET  /qr/poll?…        → {status: pending|scanned|confirmed|expired|consumed, token?, user?}
 *
 * 登录成功后 token 存 localStorage（键 fauth），随后所有 /api/ui/* 请求带 Bearer。
 * 扫码确认页（手机端）由后端直接渲染，登录态与网页端共用同一个键。
 */
import { useCallback, useEffect, useRef, useState, type CSSProperties, type FormEvent } from 'react'
import { useLocation, useNavigate, Navigate } from 'react-router'
import {
  AlertCircle,
  CheckCircle2,
  Eye,
  EyeOff,
  Loader2,
  Lock,
  LogIn,
  QrCode,
  RefreshCw,
  ShieldCheck,
  User as UserIcon,
} from 'lucide-react'
import { Blobs } from './Home'
import { SERVER_ROOT } from '../lib/base'
import { api } from '../lib/api'
import { useApi } from '../lib/useApi'
import { qrPoll, qrStart, useAuth, writeAuth, type QrStatus, type QrTicket } from '../lib/auth'
import { pick } from '../data/live'
import { useLang } from '../i18n'

type Tab = 'pwd' | 'qr'

export default function Login() {
  const { lang } = useLang()
  const nav = useNavigate()
  const loc = useLocation()
  const { signIn, auth } = useAuth()
  const { data } = useApi(() => api.publicSummary(), 'public-summary', 300_000)

  const [tab, setTab] = useState<Tab>('pwd')
  const [username, setUsername] = useState('')
  const [password, setPassword] = useState('')
  const [showPwd, setShowPwd] = useState(false)
  const [remember, setRemember] = useState(true)
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState('')

  /** 登录成功后的落点：被守卫拦下来时记录的原地址 */
  const from = (loc.state as { from?: string } | null)?.from ?? '/'

  // 已登录还打开 /login → 直接回首页
  if (auth) return <Navigate to={from} replace />

  const onSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (busy) return
    setErr('')
    if (!username.trim()) {
      setErr(pick(lang, '请输入账号', 'Please enter your account'))
      return
    }
    if (!password) {
      setErr(pick(lang, '请输入密码', 'Please enter your password'))
      return
    }
    setBusy(true)
    try {
      await signIn(username.trim(), password, remember)
      nav(from, { replace: true })
    } catch (e2) {
      const msg = e2 instanceof Error ? e2.message : String(e2)
      setErr(/401|账号或密码/.test(msg) ? pick(lang, '账号或密码不正确', 'Incorrect account or password') : msg)
      setBusy(false)
    }
  }

  const brand = data?.brand.name ?? 'FootballAI'
  const tagline = pick(lang, '足球数据分析与 AI 预测', 'Football analytics & AI prediction')
  const n = (v?: number) => (typeof v === 'number' ? v.toLocaleString('en-US') : '—')
  const facts: [string, string][] = [
    [n(data?.matches), pick(lang, '收录比赛', 'matches')],
    [n(data?.players), pick(lang, '球员样本', 'players')],
    [n(data?.teams), pick(lang, '收录球队', 'teams')],
    [n(data?.leagues), pick(lang, '联赛', 'leagues')],
  ]

  return (
    <div className="font-sans-talvex relative min-h-screen overflow-hidden">
      <Blobs />
      {/* 球场底图（低透明度当纹理） */}
      <div
        className="pointer-events-none absolute inset-0 bg-cover bg-center opacity-[0.2]"
        style={{ backgroundImage: 'url(/images/hero-stadium.jpg)' }}
      />
      <div
        className="pointer-events-none absolute inset-0"
        style={{ background: 'linear-gradient(120deg, transparent 10%, var(--c-bg) 72%, var(--c-bg) 100%)' }}
      />

      <div className="relative mx-auto flex min-h-screen max-w-[1180px] items-center px-6 py-10 pb-24">
        <div className="grid w-full gap-5 lg:grid-cols-[1.05fr_minmax(0,430px)]">
          {/* ---------- 左：品牌与数据概览 ---------- */}
          <section className="glass-dark on-ink anim-in hidden flex-col justify-between rounded-[32px] p-8 lg:flex">
            <div>
              <div className="flex items-center gap-2.5">
                <span className="flex h-9 w-9 items-center justify-center rounded-2xl bg-[#F6C945] text-[17px] font-black text-[#3a2f08]">
                  F
                </span>
                <span className="text-[22px] font-extrabold leading-none tracking-tight">{brand}</span>
              </div>
              <p className="mt-3 text-[12.5px] font-medium opacity-70">{tagline}</p>

              <h2 className="mt-9 text-[34px] font-medium leading-[1.15] tracking-[-0.02em]">
                {pick(lang, '登录后查看真实数据', 'Sign in to the live dataset')}
              </h2>
              <p className="mt-3 max-w-[430px] text-[12.5px] leading-relaxed opacity-70">
                {pick(
                  lang,
                  '比赛、球队、球员、预测与实时比分全部来自本机 SQLite 数据库；管理端提供数据资产、模型注册表与系统接口视图。',
                  'Matches, teams, players, predictions and live scores all come from the local SQLite database. The admin console exposes data assets, the model registry and system endpoints.',
                )}
              </p>
            </div>

            <div className="mt-10 grid grid-cols-4 gap-3">
              {facts.map(([v, k]) => (
                <div key={k} className="rounded-2xl bg-white/5 px-3 py-2.5">
                  <p className="text-[19px] font-semibold tabular-nums leading-none">{v}</p>
                  <p className="mt-1.5 text-[10.5px] font-medium uppercase tracking-wide opacity-60">{k}</p>
                </div>
              ))}
            </div>

            <div className="mt-8 flex items-center gap-2 text-[11px] opacity-60">
              <ShieldCheck size={13} />
              {pick(lang, '登录态仅保存在本机浏览器，可随时退出', 'Your session is stored locally and can be ended anytime')}
            </div>
          </section>

          {/* ---------- 右：登录表单 ---------- */}
          <section className="glass anim-in rounded-[32px] p-7" style={{ '--d': '80ms' } as CSSProperties}>
            <div className="lg:hidden">
              <div className="flex items-center gap-2.5">
                <span className="flex h-8 w-8 items-center justify-center rounded-xl bg-[#F6C945] text-[15px] font-black text-[#3a2f08]">
                  F
                </span>
                <span className="t-1 text-[19px] font-extrabold leading-none tracking-tight">{brand}</span>
              </div>
              <p className="t-3 mt-2 text-[11.5px]">{tagline}</p>
            </div>

            <h1 className="t-1 mt-6 text-[26px] font-semibold leading-none tracking-[-0.02em] lg:mt-0">
              {pick(lang, '登录', 'Sign in')}
            </h1>
            <p className="t-3 mt-2 text-[12px]">
              {pick(lang, '请使用系统账号登录', 'Use your system account to continue')}
            </p>

            {/* 方式切换 */}
            <div className="glass-soft mt-5 flex items-center gap-0.5 rounded-full p-1">
              {(
                [
                  ['pwd', pick(lang, '账号密码', 'Password'), Lock],
                  ['qr', pick(lang, '扫码登录', 'QR code'), QrCode],
                ] as [Tab, string, typeof Lock][]
              ).map(([key, label, Icon]) => (
                <button
                  key={key}
                  type="button"
                  onClick={() => {
                    setTab(key)
                    setErr('')
                  }}
                  className={`flex flex-1 items-center justify-center gap-1.5 rounded-full px-3 py-2 text-[12.5px] font-semibold transition-all duration-300 ${
                    tab === key ? 'bg-ink on-ink shadow-md' : 't-2 hover:bg-white/40'
                  }`}
                >
                  <Icon size={13} strokeWidth={2.2} />
                  {label}
                </button>
              ))}
            </div>

            {tab === 'pwd' ? (
              <form onSubmit={onSubmit} className="mt-5">
                <label className="t-3 block text-[11px] font-semibold">{pick(lang, '账号', 'Account')}</label>
                <div className="glass-soft mt-1.5 flex items-center gap-2 rounded-2xl px-3.5 py-2.5">
                  <UserIcon size={14} className="t-3 shrink-0" />
                  <input
                    value={username}
                    onChange={(e) => setUsername(e.target.value)}
                    autoComplete="username"
                    autoFocus
                    placeholder={pick(lang, '请输入账号', 'Your account')}
                    className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  />
                </div>

                <label className="t-3 mt-4 block text-[11px] font-semibold">{pick(lang, '密码', 'Password')}</label>
                <div className="glass-soft mt-1.5 flex items-center gap-2 rounded-2xl px-3.5 py-2.5">
                  <Lock size={14} className="t-3 shrink-0" />
                  <input
                    value={password}
                    onChange={(e) => setPassword(e.target.value)}
                    type={showPwd ? 'text' : 'password'}
                    autoComplete="current-password"
                    placeholder={pick(lang, '请输入密码', 'Your password')}
                    className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPwd((v) => !v)}
                    className="t-3 shrink-0 transition-opacity hover:opacity-70"
                    title={pick(lang, showPwd ? '隐藏密码' : '显示密码', showPwd ? 'Hide' : 'Show')}
                  >
                    {showPwd ? <EyeOff size={14} /> : <Eye size={14} />}
                  </button>
                </div>

                <div className="mt-3.5 flex items-center justify-between">
                  <button
                    type="button"
                    onClick={() => setRemember((v) => !v)}
                    className="flex items-center gap-2"
                  >
                    <span
                      className={`flex h-[16px] w-[16px] items-center justify-center rounded-[6px] border transition-colors ${
                        remember ? 'border-transparent bg-[#F6C945]' : 't-3 border-current'
                      }`}
                    >
                      {remember && <CheckCircle2 size={12} className="text-[#3a2f08]" />}
                    </span>
                    <span className="t-2 text-[12px] font-medium">
                      {pick(lang, '记住我（30 天）', 'Keep me signed in (30 days)')}
                    </span>
                  </button>
                </div>

                {err && (
                  <div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#E2A0A0]/30 px-3 py-2.5">
                    <AlertCircle size={14} className="mt-[1px] shrink-0 text-[#c0645f]" />
                    <p className="t-1 text-[12px] font-medium">{err}</p>
                  </div>
                )}

                <button
                  type="submit"
                  disabled={busy}
                  className="bg-ink on-ink mt-5 flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13.5px] font-semibold shadow-lg transition-transform duration-300 hover:scale-[1.015] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-70"
                >
                  {busy ? <Loader2 size={15} className="animate-spin" /> : <LogIn size={15} strokeWidth={2.2} />}
                  {busy ? pick(lang, '登录中…', 'Signing in…') : pick(lang, '登 录', 'Sign in')}
                </button>

                <p className="t-3 mt-4 text-center text-[11px] leading-relaxed">
                  {pick(lang, '演示账号', 'Demo account')}
                  {' · '}
                  <span className="t-2 font-semibold tabular-nums">admin / football2026</span>
                </p>
              </form>
            ) : (
              <QrPanel onDone={(to) => nav(to, { replace: true })} />
            )}
          </section>
        </div>
      </div>
    </div>
  )
}

/* ---------------- 扫码登录面板 ---------------- */

function QrPanel({ onDone }: { onDone: (to: string) => void }) {
  const { lang } = useLang()
  const [ticket, setTicket] = useState<QrTicket | null>(null)
  const [status, setStatus] = useState<QrStatus>('pending')
  const [left, setLeft] = useState(0)
  const [err, setErr] = useState('')
  const [busy, setBusy] = useState(false)
  const timer = useRef<number | null>(null)
  const tick = useRef<number | null>(null)

  const start = useCallback(async () => {
    setBusy(true)
    setErr('')
    try {
      const t = await qrStart()
      setTicket(t)
      setStatus('pending')
      setLeft(t.expires_in)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy(false)
    }
  }, [])

  useEffect(() => {
    void start()
    return () => {
      if (timer.current) window.clearInterval(timer.current)
      if (tick.current) window.clearInterval(tick.current)
    }
  }, [start])

  // 轮询状态
  useEffect(() => {
    if (!ticket) return
    if (timer.current) window.clearInterval(timer.current)
    timer.current = window.setInterval(async () => {
      try {
        const r = await qrPoll(ticket.qr_id, ticket.secret)
        setStatus(r.status)
        if (r.status === 'confirmed' && r.token && r.user) {
          writeAuth({ token: r.token, user: r.user, expires_at: r.expires_at, remember: true })
          if (timer.current) window.clearInterval(timer.current)
          onDone('/')
        }
        if (r.status === 'expired' || r.status === 'consumed') {
          if (timer.current) window.clearInterval(timer.current)
        }
      } catch {
        /* 单次轮询失败忽略，下一轮再试 */
      }
    }, 1500)
    return () => {
      if (timer.current) window.clearInterval(timer.current)
    }
  }, [ticket, onDone])

  // 倒计时
  useEffect(() => {
    if (tick.current) window.clearInterval(tick.current)
    tick.current = window.setInterval(() => setLeft((n) => (n > 0 ? n - 1 : 0)), 1000)
    return () => {
      if (tick.current) window.clearInterval(tick.current)
    }
  }, [ticket])

  const text =
    status === 'scanned'
      ? pick(lang, '已扫描，请在手机上确认登录', 'Scanned — confirm on your phone')
      : status === 'expired' || left === 0
        ? pick(lang, '二维码已过期', 'QR code expired')
        : pick(lang, '请用手机扫描二维码', 'Scan the QR code with your phone')

  return (
    <div className="mt-5 flex flex-col items-center">
      <div className="glass-soft relative flex h-[186px] w-[186px] items-center justify-center rounded-3xl p-3">
        {ticket && status !== 'expired' && left > 0 ? (
          <img src={`${SERVER_ROOT}${ticket.image_url}`} alt="QR" className="h-full w-full rounded-2xl object-contain" />
        ) : (
          <div className="t-3 flex h-full w-full flex-col items-center justify-center gap-2 rounded-2xl bg-white/30 text-center">
            <QrCode size={26} />
            <span className="px-4 text-[11.5px]">{text}</span>
          </div>
        )}
        {(busy || status === 'scanned') && (
          <span className="absolute inset-0 flex items-center justify-center rounded-3xl bg-black/25 text-[11.5px] font-semibold text-white">
            {status === 'scanned' ? pick(lang, '等待手机确认…', 'Waiting for confirmation…') : ''}
          </span>
        )}
      </div>

      <p className="t-2 mt-3 text-[12.5px] font-medium">{text}</p>
      <p className="t-3 mt-1 text-[11px] tabular-nums">
        {left > 0
          ? `${pick(lang, '有效期剩余', 'expires in')} ${left}s`
          : pick(lang, '请刷新二维码', 'please refresh')}
      </p>

      <button
        type="button"
        onClick={() => void start()}
        className="glass-soft t-1 mt-4 flex items-center gap-2 rounded-2xl px-4 py-2.5 text-[12.5px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
      >
        <RefreshCw size={13} className={busy ? 'animate-spin' : ''} />
        {pick(lang, '刷新二维码', 'Refresh code')}
      </button>

      <p className="t-3 mt-4 text-center text-[11px] leading-relaxed">
        {pick(
          lang,
          '手机需与本机在同一局域网：扫码后打开确认页，用手机端账号登录即可放行本设备。',
          'Your phone must be on the same LAN: scan, then sign in on the phone to approve this device.',
        )}
      </p>

      {err && (
        <div className="mt-3 flex w-full items-start gap-2 rounded-2xl bg-[#E2A0A0]/30 px-3 py-2.5">
          <AlertCircle size={14} className="mt-[1px] shrink-0 text-[#c0645f]" />
          <p className="t-1 text-[12px] font-medium">{err}</p>
        </div>
      )}
    </div>
  )
}
