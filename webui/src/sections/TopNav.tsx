import { useState } from 'react'
import { createPortal } from 'react-dom'
import { Bell, LogOut, RefreshCw, Settings, ShieldCheck, User as UserIcon } from 'lucide-react'
import { useLocation, useNavigate } from 'react-router'
import { pick, useHome } from '../data/live'
import { useLang, type I18nKey } from '../i18n'
import { consoleLoginUrl } from '../lib/base'
import { avatarSrc, useAuth } from '../lib/auth'
import AccountSettings from './AccountSettings'

/**
 * 顶栏导航：标题 → 路由（用户端 8 个入口）
 * 报告(/reports) 与 AI 分析(/agent) 已并入管理端，管理端入口 = 右侧「设置」按钮 → /admin。
 */
export const NAV_ROUTES: { key: string; path: string; label?: string; zh?: string; en?: string }[] = [
  { key: 'Overview', label: 'nav.Overview', path: '/' },
  { key: 'Matches', path: '/matches', zh: '赛程', en: 'Fixtures' },
  { key: 'Leagues', label: 'nav.Leagues', path: '/leagues' },
  { key: 'Teams', label: 'nav.Teams', path: '/teams' },
  { key: 'Players', label: 'nav.Players', path: '/players' },
  { key: 'Predict', label: 'nav.Predict', path: '/predictions' },
  { key: 'Live', label: 'nav.Live', path: '/live' },
  { key: 'Ask', path: '/ask', zh: '问答', en: 'Ask' },
]

export default function TopNav({ activePath }: { activePath?: string }) {
  const { lang, t } = useLang()
  const { data, reload } = useHome()
  const { user, admin, signOut } = useAuth()
  const nav = useNavigate()
  const loc = useLocation()
  const current = activePath ?? loc.pathname
  const [spinning, setSpinning] = useState(false)
  const [bell, setBell] = useState(false)
  const [menu, setMenu] = useState(false)
  const [account, setAccount] = useState(false)
  const log = data?.updateLog ?? []
  const pending = log.filter((r) => !r.done).length

  const isActive = (path: string) =>
    path === '/' ? current === '/' : current === path || current.startsWith(`${path}/`)

  // 弹层挂在 <header> 外面：顶栏的 backdrop-filter 会让它成为 fixed 后代的 containing block，
  // 弹层留在顶栏里就会被限制在那条胶囊内（弹层自身也做了 createPortal，双保险）。
  return (
    <>
      <header className="glass anim-in sticky top-4 z-40 flex items-center gap-5 rounded-full px-5 py-2.5">
      <button onClick={() => nav('/')} className="flex items-center gap-2.5">
        <span className="t-1 text-[20px] font-extrabold leading-none tracking-tight">
          {data?.brand.name ?? 'FootballAI'}
        </span>
        <span className="t-3 hidden text-[10px] font-medium leading-tight lg:block">
          {pick(lang, '足球数据分析与 AI 预测', 'Football analytics & AI prediction')}
        </span>
      </button>

      <nav className="glass-soft mx-auto flex items-center gap-0.5 rounded-full p-1">
        {NAV_ROUTES.map((item) => (
          <button
            key={item.key}
            onClick={() => nav(item.path)}
            className={
              isActive(item.path)
                ? 'bg-ink on-ink rounded-full px-3.5 py-1.5 text-[13px] font-medium shadow-md transition-all duration-300'
                : 't-2 rounded-full px-3.5 py-1.5 text-[13px] font-medium transition-all duration-300 hover:bg-white/40 hover:text-[var(--c-text)]'
            }
          >
            {item.label ? t(item.label as I18nKey) : pick(lang, item.zh ?? item.key, item.en ?? item.key)}
          </button>
        ))}
      </nav>

      <div className="flex items-center gap-3">
        <span className="t-3 hidden text-[11px] font-medium tabular-nums xl:block">
          {data ? `${pick(lang, '数据截至', 'data as of')} ${data.dataNow.slice(0, 10)}` : ''}
        </span>
        <button
          onClick={() => {
            setSpinning(true)
            reload()
            setTimeout(() => setSpinning(false), 900)
          }}
          className="glass-soft t-1 flex h-9 w-9 items-center justify-center rounded-full transition-transform duration-300 hover:scale-105 active:scale-95"
          title={pick(lang, '刷新数据', 'Refresh data')}
        >
          <RefreshCw size={15} strokeWidth={2.2} className={spinning ? 'animate-spin' : ''} />
        </button>
        {admin && (
          <button
            onClick={() => nav('/admin')}
            className="glass-soft t-1 flex items-center gap-2 rounded-full px-3.5 py-2 text-[13px] font-semibold transition-transform duration-300 hover:scale-105 active:scale-95"
          >
            <Settings size={15} strokeWidth={2.2} className="transition-transform duration-500 hover:rotate-90" />
            {t('topbar.configs')}
          </button>
        )}
        <div className="relative">
          <button
            onClick={() => setBell(!bell)}
            className="bell-hover glass-soft relative flex h-9 w-9 items-center justify-center rounded-full transition-transform duration-300 hover:scale-105 active:scale-95"
            title={pick(lang, '更新日志', 'Update log')}
          >
            <Bell size={16} strokeWidth={2.2} className="t-1" />
            {pending > 0 && (
              <>
                <span className="absolute right-2 top-2 h-2 w-2 animate-pulse rounded-full bg-[#F6C945] ring-2 ring-white" />
                <span className="absolute -right-1 -top-1 flex h-[18px] min-w-[18px] items-center justify-center rounded-full bg-[#F6C945] px-1 text-[10px] font-bold tabular-nums text-[#3a2f08] ring-2 ring-white">
                  {pending}
                </span>
              </>
            )}
          </button>

          {bell && (
            <div className="glass-pop anim-in absolute right-0 top-11 z-50 w-[340px] rounded-[22px] p-3">
              <div className="flex items-center justify-between px-1.5 pb-2">
                <span className="t-1 text-[13px] font-semibold">{pick(lang, '数据更新日志', 'Data update log')}</span>
                <span className="t-3 text-[11px] tabular-nums">
                  {log.filter((r) => r.done).length}/{log.length}
                </span>
              </div>
              <div className="max-h-[320px] space-y-1.5 overflow-auto pr-0.5">
                {log.slice(0, 8).map((row) => (
                  <div key={row.id} className="glass-soft flex items-start gap-2.5 rounded-2xl px-3 py-2">
                    <span
                      className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${
                        row.level === 'warn' ? 'bg-[#F6C945]' : row.level === 'error' ? 'bg-[#E2A0A0]' : 'bg-[#B8D4A8]'
                      }`}
                    />
                    <div className="min-w-0">
                      <p className="t-1 truncate text-[12.5px] font-semibold">{pick(lang, row.title, row.titleEn)}</p>
                      <p className="t-3 truncate text-[11px] tabular-nums">
                        {row.ts} · {pick(lang, row.desc, row.descEn)}
                      </p>
                    </div>
                  </div>
                ))}
                {!log.length && <p className="t-3 px-2 py-3 text-[12px]">{pick(lang, '暂无更新记录', 'No updates yet')}</p>}
              </div>
            </div>
          )}
        </div>
        <div className="relative">
          <button
            onClick={() => setMenu(!menu)}
            className="flex items-center gap-2 transition-transform duration-300 hover:scale-105 active:scale-95"
            title={user ? `${user.display_name} (@${user.username})` : undefined}
          >
            <img
              src={avatarSrc(user)}
              alt="avatar"
              className="h-9 w-9 rounded-full object-cover ring-2 ring-white"
            />
            <span className="t-2 hidden text-[12px] font-semibold xl:block">
              {user?.display_name ?? ''}
            </span>
          </button>

          {menu && (
            <>
              {/* 顶栏的玻璃效果（backdrop-filter）会把它变成 fixed 后代的 containing block，
                  遮罩留在顶栏里就只能盖住顶栏那一条 → 点页面空白处关不掉菜单。挂到 body 上。
                  z 必须低于顶栏的 z-40：顶栏自己成层叠上下文，遮罩若同级又排在后面，会挡住菜单里的按钮。 */}
              {createPortal(<div className="fixed inset-0 z-30" onClick={() => setMenu(false)} />, document.body)}
              <div className="glass-pop anim-in absolute right-0 top-11 z-50 w-[250px] rounded-[22px] p-3">
                <div className="flex items-center gap-3 px-1.5 pb-3">
                  <img src={avatarSrc(user)} alt="avatar" className="h-10 w-10 rounded-full object-cover" />
                  <div className="min-w-0">
                    <p className="t-1 truncate text-[13px] font-semibold">{user?.display_name ?? '—'}</p>
                    <p className="t-3 truncate text-[11px] tabular-nums">@{user?.username ?? '—'}</p>
                  </div>
                </div>

                <div className="glass-soft flex items-center justify-between rounded-2xl px-3 py-2">
                  <span className="t-2 flex items-center gap-1.5 text-[11.5px] font-semibold">
                    {admin ? <ShieldCheck size={13} /> : <UserIcon size={13} />}
                    {admin ? pick(lang, '管理员', 'Administrator') : pick(lang, '普通用户', 'User')}
                  </span>
                  <span className="t-3 text-[10.5px] tabular-nums">
                    {user?.last_login ? user.last_login.slice(0, 10) : ''}
                  </span>
                </div>

                <button
                  onClick={() => {
                    setMenu(false)
                    setAccount(true)
                  }}
                  className="action-row t-1 mt-2 flex w-full items-center gap-2 rounded-2xl px-3 py-2.5 text-[12.5px] font-semibold transition-colors"
                >
                  <Settings size={14} strokeWidth={2.2} />
                  {pick(lang, '账号设置', 'Account settings')}
                </button>

                <button
                  onClick={async () => {
                    setMenu(false)
                    await signOut()
                    // 退出后回控制台登录页（与未登录时的入口一致）
                    window.location.replace(consoleLoginUrl('/'))
                  }}
                  className="action-row t-1 mt-2 flex w-full items-center gap-2 rounded-2xl px-3 py-2.5 text-[12.5px] font-semibold transition-colors"
                >
                  <LogOut size={14} strokeWidth={2.2} />
                  {pick(lang, '退出登录', 'Sign out')}
                </button>
              </div>
            </>
          )}
        </div>
      </div>

      </header>

      <AccountSettings open={account} user={user} onClose={() => setAccount(false)} />
    </>
  )
}
