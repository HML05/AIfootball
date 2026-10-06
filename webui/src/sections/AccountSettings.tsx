/**
 * 账号设置弹层 —— 顶栏头像 → 「账号设置」
 *
 * 对接 FastAPI /api/auth（见 lib/auth.ts 的同名封装）：
 *   GET    /me        → 当前资料
 *   PATCH  /profile   {username?, display_name?, phone?} → 只传要改的字段
 *   POST   /avatar    multipart/form-data，字段名 file（≤2 MB，后端自动裁方压缩）
 *   DELETE /avatar    → 恢复默认头像
 *   POST   /password  {old_password, new_password}
 *
 * 每次成功都会把新的 user 写回本地登录态（updateStoredUser），
 * 顶栏头像与昵称随之更新；本组件也把结果写进本地基线，避免"改了却又显示未保存"。
 */
import { useCallback, useEffect, useRef, useState, type ChangeEvent, type FormEvent, type ReactNode } from 'react'
import { createPortal } from 'react-dom'
import {
  AlertCircle,
  CheckCircle2,
  ImageUp,
  KeyRound,
  Loader2,
  RotateCcw,
  Save,
  Trash2,
  UserRound,
  X,
} from 'lucide-react'
import { pick } from '../data/live'
import { useLang } from '../i18n'
import { changePassword, avatarSrc, removeAvatar, updateProfile, uploadAvatar, type AuthUser } from '../lib/auth'

/** 后端限制：图片 ≤2 MB */
const MAX_BYTES = 2 * 1024 * 1024

type Tab = 'avatar' | 'profile' | 'password'

const fmtSize = (bytes: number): string =>
  bytes >= 1024 * 1024 ? `${(bytes / 1024 / 1024).toFixed(2)} MB` : `${Math.max(1, Math.round(bytes / 1024))} KB`

/** 「上限 2 MB」提示；超限时按语言给出具体数值 */
const limitText = (lang: 'en' | 'zh', bytes?: number): string => {
  const cap = bytes !== undefined ? ` ${fmtSize(bytes)} → 2 MB` : ' 2 MB'
  return lang === 'zh' ? `上限 2 MB${cap}` : `Max 2 MB${cap}`
}

export default function AccountSettings({
  open,
  user,
  onClose,
}: {
  open: boolean
  user: AuthUser | null
  onClose: () => void
}) {
  const { lang } = useLang()
  const [tab, setTab] = useState<Tab>('avatar')

  /* 头像页 */
  const [file, setFile] = useState<File | null>(null)
  const [preview, setPreview] = useState('')
  const fileRef = useRef<HTMLInputElement | null>(null)

  /* 资料页 */
  const [username, setUsername] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [phone, setPhone] = useState('')
  const [base, setBase] = useState<{ username: string; display_name: string; phone: string }>({
    username: '',
    display_name: '',
    phone: '',
  })

  /* 密码页 */
  const [oldPwd, setOldPwd] = useState('')
  const [newPwd, setNewPwd] = useState('')
  const [newPwd2, setNewPwd2] = useState('')

  /* 状态 */
  const [busy, setBusy] = useState('')
  const [err, setErr] = useState('')
  const [ok, setOk] = useState('')

  /* ---------------- 打开时初始化：资料基线 + 清空上一轮的临时状态 ---------------- */

  /**
   * 只在弹层打开这一刻取一次 user 快照作为输入框与「未改动」基线。
   * 用 ref 而不是把 user.username/display_name/phone 挂进依赖：
   * 挂在依赖里会在输入过程中反复重置表单，也不好区分「用户改了」与「后端回了新值」。
   */
  const initRef = useRef(user)
  initRef.current = user

  useEffect(() => {
    if (!open) return
    const u = initRef.current
    const init = { username: u?.username ?? '', display_name: u?.display_name ?? '', phone: u?.phone ?? '' }
    setTab('avatar')
    setUsername(init.username)
    setDisplayName(init.display_name)
    setPhone(init.phone)
    setBase(init)
    setFile(null)
    setPreview('')
    setOldPwd('')
    setNewPwd('')
    setNewPwd2('')
    setBusy('')
    setErr('')
    setOk('')
  }, [open, user?.user_id])

  /* 本地预览的 blob URL 用完即撤（换图、关闭、卸载都要撤，否则内存泄漏） */
  useEffect(() => {
    if (!file) return
    const url = URL.createObjectURL(file)
    setPreview(url)
    return () => URL.revokeObjectURL(url)
  }, [file])

  /* Esc 关闭 */
  useEffect(() => {
    if (!open) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  /** 统一跑一次接口调用：错误取后端 detail（lib/auth.ts 的 request 已解析），成功给反馈 */
  const run = useCallback(async (key: string, fn: () => Promise<void>, done: string) => {
    setBusy(key)
    setErr('')
    setOk('')
    try {
      await fn()
      setOk(done)
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e))
    } finally {
      setBusy('')
    }
  }, [])

  if (!open) return null

  const shown = preview || avatarSrc(user)
  const selectedBytes = file?.size ?? 0
  const tooBig = selectedBytes > MAX_BYTES

  /* ---------------- 头像 ---------------- */

  const onPick = (e: ChangeEvent<HTMLInputElement>) => {
    setErr('')
    setOk('')
    const f = e.target.files?.[0] ?? null
    if (!f) return
    if (f.size > MAX_BYTES) {
      setFile(null)
      setPreview('')
      if (fileRef.current) fileRef.current.value = ''
      setErr(limitText(lang, f.size))
      return
    }
    setFile(f)
  }

  const onUpload = () =>
    run(
      'avatar',
      async () => {
        if (!file) return
        await uploadAvatar(file)
        setFile(null)
        setPreview('')
        if (fileRef.current) fileRef.current.value = ''
      },
      pick(lang, '头像已更新', 'Avatar updated'),
    )

  const onRemoveAvatar = () =>
    run(
      'remove',
      async () => {
        await removeAvatar()
        setFile(null)
        setPreview('')
        if (fileRef.current) fileRef.current.value = ''
      },
      pick(lang, '已恢复默认头像', 'Default avatar restored'),
    )

  const onClearPick = () => {
    setFile(null)
    setPreview('')
    if (fileRef.current) fileRef.current.value = ''
    setErr('')
    setOk('')
  }

  /* ---------------- 资料 ---------------- */

  const dirty =
    username !== base.username || displayName !== base.display_name || phone !== base.phone

  const onSaveProfile = (e: FormEvent) => {
    e.preventDefault()
    if (!dirty) return
    const patch: { username?: string; display_name?: string; phone?: string } = {}
    if (username !== base.username) patch.username = username.trim()
    if (displayName !== base.display_name) patch.display_name = displayName.trim()
    if (phone !== base.phone) patch.phone = phone.trim()
    void run(
      'profile',
      async () => {
        const u = await updateProfile(patch)
        setUsername(u.username ?? '')
        setDisplayName(u.display_name ?? '')
        setPhone(u.phone ?? '')
        setBase({
          username: u.username ?? '',
          display_name: u.display_name ?? '',
          phone: u.phone ?? '',
        })
      },
      pick(lang, '资料已保存', 'Profile saved'),
    )
  }

  /* ---------------- 密码 ---------------- */

  const pwdTooShort = newPwd.length > 0 && newPwd.length < 6
  const pwdMismatch = newPwd2.length > 0 && newPwd2 !== newPwd

  const onChangePwd = (e: FormEvent) => {
    e.preventDefault()
    if (!oldPwd) {
      setErr(pick(lang, '请输入原密码', 'Please enter your current password'))
      setOk('')
      return
    }
    if (newPwd.length < 6) {
      setErr(pick(lang, '新密码至少 6 位', 'New password must be at least 6 characters'))
      setOk('')
      return
    }
    if (newPwd !== newPwd2) {
      setErr(pick(lang, '两次输入的新密码不一致', 'The two new passwords do not match'))
      setOk('')
      return
    }
    void run('password', async () => {
      await changePassword(oldPwd, newPwd)
      setOldPwd('')
      setNewPwd('')
      setNewPwd2('')
    }, pick(lang, '密码已更新', 'Password updated'))
  }

  const TABS: { key: Tab; label: string; Icon: typeof UserRound }[] = [
    { key: 'avatar', label: pick(lang, '头像', 'Avatar'), Icon: ImageUp },
    { key: 'profile', label: pick(lang, '资料', 'Profile'), Icon: UserRound },
    { key: 'password', label: pick(lang, '密码', 'Password'), Icon: KeyRound },
  ]

  const disabled = !!busy

  // 弹层挂到 document.body：顶栏用 backdrop-filter 做玻璃效果，而 backdrop-filter 会让元素
  // 成为 fixed 后代的 containing block —— 直接挂在顶栏里，inset-0 会被限制在顶栏那条胶囊内，
  // 页面滚动后弹层标题/页签会跑到视口外（Playwright 报 element is outside of the viewport）。
  return createPortal(
    <div
      className="fixed inset-0 z-[80] flex items-center justify-center bg-black/35 p-4 backdrop-blur-[3px]"
      onClick={onClose}
      role="dialog"
      aria-modal="true"
    >
      <div
        className="glass-pop anim-in flex max-h-[88vh] w-full max-w-[520px] flex-col overflow-hidden rounded-[22px]"
        onClick={(e) => e.stopPropagation()}
      >
        {/* 头部 */}
        <div className="flex items-center justify-between px-5 pb-3 pt-5">
          <div className="min-w-0">
            <h2 className="t-1 text-[16px] font-semibold tracking-[-0.01em]">
              {pick(lang, '账号设置', 'Account settings')}
            </h2>
            <p className="t-3 mt-1 truncate text-[11.5px] tabular-nums">
              @{user?.username ?? '—'} · {user?.display_name ?? '—'}
            </p>
          </div>
          <button
            onClick={onClose}
            className="glass-soft t-2 flex h-8 w-8 shrink-0 items-center justify-center rounded-full transition-transform duration-300 hover:scale-105 active:scale-95"
            title={pick(lang, '关闭', 'Close')}
            aria-label={pick(lang, '关闭', 'Close')}
          >
            <X size={15} strokeWidth={2.4} />
          </button>
        </div>

        {/* 页签 */}
        <div className="px-5">
          <div className="glass-soft flex items-center gap-0.5 rounded-full p-1">
            {TABS.map(({ key, label, Icon }) => (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setTab(key)
                  setErr('')
                  setOk('')
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
        </div>

        {/* 内容 */}
        <div className="min-h-0 flex-1 overflow-auto px-5 pb-5 pt-4">
          {tab === 'avatar' && (
            <div className="flex flex-col items-center">
              <img
                src={shown}
                alt="avatar"
                className="h-[112px] w-[112px] rounded-full object-cover ring-4 ring-white/70"
              />

              <label className="glass-soft t-1 mt-4 flex cursor-pointer items-center gap-2 rounded-2xl px-4 py-2.5 text-[12.5px] font-semibold transition-transform duration-300 hover:scale-[1.02] active:scale-[0.98]">
                <ImageUp size={14} strokeWidth={2.2} />
                {pick(lang, '选择本地图片', 'Choose a local image')}
                <input
                  ref={fileRef}
                  type="file"
                  accept="image/png,image/jpeg,image/webp"
                  className="hidden"
                  onChange={onPick}
                />
              </label>

              <p className="t-3 mt-2.5 text-center text-[11px] tabular-nums">
                {file
                  ? `${file.name} · ${fmtSize(file.size)} · ${limitText(lang, file.size)}`
                  : pick(lang, '支持 PNG / JPG / WebP，上限 2 MB', 'PNG / JPG / WebP, max 2 MB')}
              </p>
              <p className="t-3 mt-1 text-center text-[11px]">
                {pick(lang, '后端会自动居中裁方并压缩', 'It is centre-cropped and compressed automatically')}
              </p>

              {tooBig && (
                <div className="mt-3 flex w-full items-start gap-2 rounded-2xl bg-[#E2A0A0]/30 px-3 py-2.5">
                  <AlertCircle size={14} className="mt-[1px] shrink-0 text-[#c0645f]" />
                  <p className="t-1 text-[12px] font-medium">
                    {pick(
                      lang,
                      `图片 ${fmtSize(selectedBytes)} 超过 2 MB 上限，请换一张`,
                      `Image is ${fmtSize(selectedBytes)} — over the 2 MB limit, pick another`,
                    )}
                  </p>
                </div>
              )}

              <div className="mt-4 flex w-full flex-col gap-2 sm:flex-row">
                <button
                  type="button"
                  onClick={onUpload}
                  disabled={!file || tooBig || disabled}
                  className="bg-ink on-ink flex flex-1 items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13px] font-semibold shadow-lg transition-transform duration-300 hover:scale-[1.015] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy === 'avatar' ? <Loader2 size={15} className="animate-spin" /> : <ImageUp size={15} strokeWidth={2.2} />}
                  {busy === 'avatar' ? pick(lang, '上传中…', 'Uploading…') : pick(lang, '上传头像', 'Upload avatar')}
                </button>
                <button
                  type="button"
                  onClick={onRemoveAvatar}
                  disabled={disabled || !user?.avatar_url}
                  className="glass-soft t-1 flex flex-1 items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13px] font-semibold transition-transform duration-300 hover:scale-[1.015] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
                >
                  {busy === 'remove' ? <Loader2 size={15} className="animate-spin" /> : <RotateCcw size={15} strokeWidth={2.2} />}
                  {busy === 'remove'
                    ? pick(lang, '恢复中…', 'Restoring…')
                    : pick(lang, '恢复默认头像', 'Restore default')}
                </button>
              </div>

              {file && (
                <button
                  type="button"
                  onClick={onClearPick}
                  disabled={disabled}
                  className="t-3 mt-3 flex items-center gap-1.5 text-[11.5px] font-medium transition-opacity hover:opacity-70 disabled:opacity-50"
                >
                  <Trash2 size={12} />
                  {pick(lang, '取消这次选择', 'Discard this selection')}
                </button>
              )}
            </div>
          )}

          {tab === 'profile' && (
            <form onSubmit={onSaveProfile}>
              <Field
                label={pick(lang, '账号名', 'Account name')}
                hint={pick(
                  lang,
                  '3~20 位，字母开头，可用字母/数字/下划线/点/横线',
                  '3–20 chars, starts with a letter; letters, digits, _ . - only',
                )}
              >
                <input
                  value={username}
                  onChange={(e) => setUsername(e.target.value)}
                  autoComplete="username"
                  className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  placeholder="username"
                />
              </Field>

              <Field label={pick(lang, '昵称', 'Display name')} hint={pick(lang, '最多 50 个字', 'Up to 50 characters')}>
                <input
                  value={displayName}
                  onChange={(e) => setDisplayName(e.target.value)}
                  autoComplete="nickname"
                  className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  placeholder={pick(lang, '显示名称', 'Display name')}
                />
              </Field>

              <Field label={pick(lang, '手机号', 'Phone')} hint={pick(lang, '可留空', 'Optional')}>
                <input
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  autoComplete="tel"
                  inputMode="tel"
                  className="t-1 w-full bg-transparent text-[13px] tabular-nums outline-none placeholder:opacity-50"
                  placeholder={pick(lang, '可留空', 'Optional')}
                />
              </Field>

              <button
                type="submit"
                disabled={!dirty || disabled}
                className="bg-ink on-ink mt-1 flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13px] font-semibold shadow-lg transition-transform duration-300 hover:scale-[1.015] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === 'profile' ? <Loader2 size={15} className="animate-spin" /> : <Save size={15} strokeWidth={2.2} />}
                {busy === 'profile' ? pick(lang, '保存中…', 'Saving…') : pick(lang, '保存修改', 'Save changes')}
              </button>
            </form>
          )}

          {tab === 'password' && (
            <form onSubmit={onChangePwd}>
              <Field label={pick(lang, '原密码', 'Current password')}>
                <input
                  type="password"
                  value={oldPwd}
                  onChange={(e) => setOldPwd(e.target.value)}
                  autoComplete="current-password"
                  className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  placeholder="••••••"
                />
              </Field>

              <Field
                label={pick(lang, '新密码', 'New password')}
                hint={pick(lang, '至少 6 位', 'At least 6 characters')}
                tone={pwdTooShort ? 'warn' : 'muted'}
              >
                <input
                  type="password"
                  value={newPwd}
                  onChange={(e) => setNewPwd(e.target.value)}
                  autoComplete="new-password"
                  className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  placeholder="••••••"
                />
              </Field>

              <Field
                label={pick(lang, '确认新密码', 'Confirm new password')}
                hint={pwdMismatch ? pick(lang, '两次输入不一致', 'Does not match') : undefined}
                tone={pwdMismatch ? 'warn' : 'muted'}
              >
                <input
                  type="password"
                  value={newPwd2}
                  onChange={(e) => setNewPwd2(e.target.value)}
                  autoComplete="new-password"
                  className="t-1 w-full bg-transparent text-[13px] outline-none placeholder:opacity-50"
                  placeholder="••••••"
                />
              </Field>

              <p className="t-3 mb-3 text-[11px] leading-relaxed">
                {pick(
                  lang,
                  '改完密码后，其它设备上的登录会失效，本设备保持登录。',
                  'Other devices will be signed out; this device stays signed in.',
                )}
              </p>

              <button
                type="submit"
                disabled={disabled}
                className="bg-ink on-ink flex w-full items-center justify-center gap-2 rounded-2xl px-4 py-3 text-[13px] font-semibold shadow-lg transition-transform duration-300 hover:scale-[1.015] active:scale-[0.99] disabled:cursor-not-allowed disabled:opacity-50"
              >
                {busy === 'password' ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} strokeWidth={2.2} />}
                {busy === 'password'
                  ? pick(lang, '提交中…', 'Submitting…')
                  : pick(lang, '修改密码', 'Change password')}
              </button>
            </form>
          )}

          {/* 反馈：错误显示后端 detail 原文 */}
          {err && (
            <div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#E2A0A0]/30 px-3 py-2.5">
              <AlertCircle size={14} className="mt-[1px] shrink-0 text-[#c0645f]" />
              <p className="t-1 text-[12px] font-medium">{err}</p>
            </div>
          )}
          {ok && (
            <div className="mt-4 flex items-start gap-2 rounded-2xl bg-[#B8D4A8]/35 px-3 py-2.5">
              <CheckCircle2 size={14} className="mt-[1px] shrink-0 text-[#4d7a3a]" />
              <p className="t-1 text-[12px] font-medium">{ok}</p>
            </div>
          )}
        </div>
      </div>
    </div>,
    document.body,
  )
}

/* ---------------- 表单字段（沿用登录页的 glass-soft 输入框风格） ---------------- */

function Field({
  label,
  hint,
  tone = 'muted',
  children,
}: {
  label: string
  hint?: string
  tone?: 'muted' | 'warn'
  children: ReactNode
}) {
  return (
    <div className="mb-3.5">
      <div className="flex items-baseline justify-between gap-3">
        <span className="t-3 text-[11px] font-semibold">{label}</span>
        {hint && (
          <span className={`text-[10.5px] font-medium ${tone === 'warn' ? 'text-[#c0645f]' : 't-3'}`}>{hint}</span>
        )}
      </div>
      <div className="glass-soft mt-1.5 flex items-center gap-2 rounded-2xl px-3.5 py-2.5">{children}</div>
    </div>
  )
}
