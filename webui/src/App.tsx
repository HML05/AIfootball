import { useEffect } from 'react'
import { Navigate, Route, Routes, useLocation } from 'react-router'
import type { ReactNode } from 'react'
import Home from './pages/Home'
import Admin from './pages/Admin'
import Leagues from './pages/Leagues'
import LeagueDetail from './pages/LeagueDetail'
import Teams from './pages/Teams'
import TeamDetail from './pages/TeamDetail'
import Players from './pages/Players'
import PlayerDetail from './pages/PlayerDetail'
import Matches from './pages/Matches'
import MatchDetail from './pages/MatchDetail'
import Predictions from './pages/Predictions'
import Live from './pages/Live'
import Ask from './pages/Ask'
import Vision from './pages/Vision'
import Switcher from './components/Switcher'
import { pick } from './data/live'
import { consoleLoginUrl } from './lib/base'
import { useAuth } from './lib/auth'
import { LanguageProvider, useLang } from './i18n'
import { ThemeProvider, useTheme } from './theme'

/**
 * 路由结构（登录后可见：用户端 9 个入口 + 管理端 4 个页签）
 *  用户端: /            总览
 *          /matches     赛程与赛果（/matches/:id 比赛详情）
 *          /leagues     联赛（/leagues/:id 联赛详情）
 *          /teams       球队（/teams/:id 球队详情）
 *          /players     球员（/players/:id 球员详情）
 *          /predictions 预测
 *          /live        实时
 *          /ask         检索与问答（?tab=search|ask）
 *          /vision      视频分析（YOLOv8 检测跟踪；处理在本地 .venv-vision 里跑）
 *  管理端: /admin?tab=overview|asset|models|system（仅管理员角色）
 *  旧入口 /reports、/agent 已并入管理端，保留为重定向。
 *
 * 登录页用的是设计稿控制台那一版（docs/console/login.html，由后端挂在 /console），
 * 本 SPA 不再自带登录页：未登录时把用户送到 /console/login.html?next=<原地址>，
 * 两边同源、共用 localStorage.fauth，登录后跳回原地址。
 *
 * 后端 /api/ui/* 需要 Bearer token（见 src/api/ui.py 的 require_ui_login），
 * 因此所有页面都在 RequireAuth 之内。
 */
function Splash() {
  const { theme } = useTheme()
  return (
    <div className={`app-root font-sans-talvex flex min-h-screen items-center justify-center ${theme === 'dark' ? 'theme-dark' : 'theme-light'}`}>
      <div className="flex flex-col items-center gap-3">
        <span className="flex h-11 w-11 animate-pulse items-center justify-center rounded-2xl bg-[#F6C945] text-[19px] font-black text-[#3a2f08]">
          F
        </span>
        <span className="t-3 text-[12px]">FootballAI · loading…</span>
      </div>
    </div>
  )
}

/** 未登录：整页跳到控制台登录页（不用 React 路由，避免与静态页互相打架） */
function GoLogin({ to }: { to: string }) {
  useEffect(() => {
    window.location.replace(to)
  }, [to])
  return <Splash />
}

function RequireAuth({ children }: { children: ReactNode }) {
  const { auth, ready } = useAuth()
  if (!ready) return <Splash />
  if (!auth) return <GoLogin to={consoleLoginUrl()} />
  return <>{children}</>
}

/** 管理端页面仅管理员可进（角色来自登录用户） */
function RequireAdmin({ children }: { children: ReactNode }) {
  const { admin } = useAuth()
  const loc = useLocation()
  const { theme } = useTheme()
  const { lang } = useLang()
  if (admin) return <>{children}</>
  return (
    <div className={`app-root font-sans-talvex flex min-h-screen items-center justify-center px-6 ${theme === 'dark' ? 'theme-dark' : 'theme-light'}`}>
      <div className="glass w-full max-w-[440px] rounded-[28px] p-7 text-center">
        <h1 className="t-1 text-[20px] font-semibold">{pick(lang, '需要管理员权限', 'Administrators only')}</h1>
        <p className="t-3 mt-2 text-[12.5px] leading-relaxed">
          {pick(
            lang,
            `当前账号（${loc.pathname}）没有管理端权限，请用管理员账号登录或返回用户端。`,
            `The current account has no access to the admin console (${loc.pathname}). Sign in as an administrator or return to the user pages.`,
          )}
        </p>
        <div className="mt-5 flex flex-wrap items-center justify-center gap-2">
          <a
            href={consoleLoginUrl(undefined, 'role')}
            className="bg-ink on-ink inline-flex items-center justify-center rounded-2xl px-5 py-2.5 text-[13px] font-semibold"
          >
            {pick(lang, '换管理员账号登录', 'Sign in as an administrator')}
          </a>
          <a
            href="/"
            className="glass-soft t-1 inline-flex items-center justify-center rounded-2xl px-5 py-2.5 text-[13px] font-semibold"
          >
            {pick(lang, '返回总览', 'Back to overview')}
          </a>
        </div>
      </div>
    </div>
  )
}

function Shell() {
  const { theme } = useTheme()
  return (
    <div className={`app-root min-h-screen ${theme === 'dark' ? 'theme-dark' : 'theme-light'}`}>
      <Routes>
        <Route
          path="*"
          element={
            <RequireAuth>
              <Routes>
                <Route path="/" element={<Home />} />
                <Route path="/matches" element={<Matches />} />
                <Route path="/matches/:id" element={<MatchDetail />} />
                <Route path="/leagues" element={<Leagues />} />
                <Route path="/leagues/:id" element={<LeagueDetail />} />
                <Route path="/teams" element={<Teams />} />
                <Route path="/teams/:id" element={<TeamDetail />} />
                <Route path="/players" element={<Players />} />
                <Route path="/players/:id" element={<PlayerDetail />} />
                <Route path="/predictions" element={<Predictions />} />
                <Route path="/live" element={<Live />} />
                <Route path="/ask" element={<Ask />} />
                <Route path="/vision" element={<Vision />} />
                <Route
                  path="/admin"
                  element={
                    <RequireAdmin>
                      <Admin />
                    </RequireAdmin>
                  }
                />
                <Route path="/reports" element={<Navigate to="/admin?tab=asset" replace />} />
                <Route path="/agent" element={<Navigate to="/admin?tab=models" replace />} />
                <Route path="*" element={<Home />} />
              </Routes>
            </RequireAuth>
          }
        />
      </Routes>
      <Switcher />
    </div>
  )
}

export default function App() {
  return (
    <ThemeProvider>
      <LanguageProvider>
        <Shell />
      </LanguageProvider>
    </ThemeProvider>
  )
}
