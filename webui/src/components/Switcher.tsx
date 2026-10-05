import { useLocation, useNavigate } from 'react-router'
import { LayoutDashboard, Moon, ShieldCheck, Sun } from 'lucide-react'
import { useLang } from '../i18n'
import { useAuth } from '../lib/auth'
import { useTheme } from '../theme'

function SegButton({
  active,
  onClick,
  children,
  label,
}: {
  active?: boolean
  onClick: () => void
  children: React.ReactNode
  label: string
}) {
  return (
    <button
      onClick={onClick}
      aria-label={label}
      title={label}
      className={`flex items-center gap-1.5 rounded-full px-3.5 py-1.5 text-[12px] font-semibold transition-all duration-300 ${
        active ? 'bg-ink on-ink shadow-md' : 't-2 hover:bg-white/40 hover:t-1 dark:hover:bg-white/10'
      }`}
    >
      {children}
    </button>
  )
}

export default function Switcher() {
  const { lang, setLang, t } = useLang()
  const { theme, toggle } = useTheme()
  const { user, admin } = useAuth()
  const location = useLocation()
  const navigate = useNavigate()
  const isAdmin = location.pathname.startsWith('/admin')

  return (
    <div className="anim-in fixed bottom-5 left-1/2 z-50 -translate-x-1/2" style={{ '--d': '500ms' } as React.CSSProperties}>
      <div className="glass flex items-center gap-1 rounded-full p-1.5 shadow-2xl">
        {/* 用户 / 管理员视图切换：未登录时隐藏；非管理员不显示管理端入口 */}
        {user ? (
          <>
            <SegButton active={!isAdmin} onClick={() => navigate('/')} label={t('switcher.userView')}>
              <LayoutDashboard size={14} />
              {t('switcher.user')}
            </SegButton>
            {admin && (
              <SegButton active={isAdmin} onClick={() => navigate('/admin')} label={t('switcher.adminView')}>
                <ShieldCheck size={14} />
                {t('switcher.admin')}
              </SegButton>
            )}

            <div className="mx-1 h-5 w-px bg-current opacity-15" />
          </>
        ) : null}

        {/* 中英文切换 */}
        <SegButton active={lang === 'zh'} onClick={() => setLang('zh')} label={t('switcher.lang')}>
          中
        </SegButton>
        <SegButton active={lang === 'en'} onClick={() => setLang('en')} label={t('switcher.lang')}>
          EN
        </SegButton>

        <div className="mx-1 h-5 w-px bg-current opacity-15" />

        {/* 深浅色切换 */}
        <button
          onClick={toggle}
          aria-label={t('switcher.theme')}
          title={t('switcher.theme')}
          className="glass-soft flex h-8 w-8 items-center justify-center rounded-full transition-transform duration-500 hover:scale-110 hover:rotate-12 active:scale-90"
        >
          {theme === 'light' ? <Moon size={14} className="t-1" /> : <Sun size={14} className="t-1" />}
        </button>
      </div>
    </div>
  )
}
