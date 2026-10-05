/**
 * 登录态（token + 用户）—— 与后端 src/api/auth.py 对接
 *
 * 存储键用 `fauth`，与后端扫码确认页（src/auth/qr_page.py）一致：
 * 手机扫码确认后写的就是这个键，所以「PC 扫码登录」与「本页账号密码登录」共享同一份登录态。
 *
 * 事件
 *   fa-auth-changed   登录态变化（登录/退出/校验失败）→ 顶栏用户菜单、路由守卫重渲染
 *   fa-unauthorized   任一 /api/ui/* 请求返回 401 → 守卫生成跳转到控制台登录页
 *
 * 登录页不在本 SPA 里：未登录时整页跳到 /console/login.html（docs/console/login.html），
 * 见 lib/base.ts 的 consoleLoginUrl()。
 */
import { useCallback, useEffect, useState } from 'react'
import { AUTH_BASE } from './base'
import { clearApiCache } from './useApi'

export interface AuthUser {
  user_id: number
  username: string
  display_name: string
  role: string
  phone?: string
  last_login?: string
}

export interface AuthState {
  token: string
  user: AuthUser
  expires_at?: string
  remember?: boolean
}

export const AUTH_KEY = 'fauth'
export const AUTH_EVENT = 'fa-auth-changed'
export const UNAUTHORIZED_EVENT = 'fa-unauthorized'

/* ---------------- 读写 ---------------- */

/** 解析 "2026-11-04 00:33:54"（服务器本地时间）为时间戳；解析不了当没过期 */
function expiry(a: AuthState): number {
  if (!a.expires_at) return Infinity
  const t = Date.parse(a.expires_at.replace(' ', 'T'))
  return Number.isNaN(t) ? Infinity : t
}

export function readAuth(): AuthState | null {
  try {
    const raw = localStorage.getItem(AUTH_KEY)
    if (!raw) return null
    const s = JSON.parse(raw) as AuthState
    if (!s || !s.token || !s.user) return null
    if (expiry(s) <= Date.now()) {
      localStorage.removeItem(AUTH_KEY)
      return null
    }
    return s
  } catch {
    return null
  }
}

export function getToken(): string | null {
  return readAuth()?.token ?? null
}

export function authHeader(): Record<string, string> {
  const t = getToken()
  return t ? { Authorization: `Bearer ${t}` } : {}
}

export function isAdmin(a: AuthState | null = readAuth()): boolean {
  return (a?.user.role ?? 'user') === 'admin'
}

function notify() {
  window.dispatchEvent(new Event(AUTH_EVENT))
}

export function writeAuth(s: AuthState) {
  localStorage.setItem(AUTH_KEY, JSON.stringify(s))
  notify()
}

/** 退出登录（清 token + 清所有接口缓存，避免下一个账号看到上一个账号的数据） */
export function clearAuth() {
  localStorage.removeItem(AUTH_KEY)
  clearApiCache()
  notify()
}

/* ---------------- 请求 ---------------- */

async function request<T>(path: string, init: RequestInit & { token?: string | null } = {}): Promise<T> {
  const { token, ...rest } = init
  const headers: Record<string, string> = {
    Accept: 'application/json',
    ...(rest.body ? { 'Content-Type': 'application/json' } : {}),
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  }
  let res: Response
  try {
    res = await fetch(`${AUTH_BASE}${path}`, { ...rest, headers })
  } catch {
    throw new Error('无法连接服务器，请确认后端已启动')
  }
  const text = await res.text()
  let body: unknown = null
  try {
    body = text ? JSON.parse(text) : null
  } catch {
    body = null
  }
  if (!res.ok) {
    const detail = (body as { detail?: unknown } | null)?.detail
    const msg =
      typeof detail === 'string'
        ? detail
        : Array.isArray(detail) && detail.length
          ? '请求参数不正确'
          : `${res.status} ${res.statusText}`
    throw new Error(msg)
  }
  return body as T
}

export interface LoginResult {
  ok: boolean
  token: string
  user: AuthUser
  expires_at?: string
}

export async function login(username: string, password: string, remember: boolean): Promise<AuthState> {
  const r = await request<LoginResult>('/login', {
    method: 'POST',
    body: JSON.stringify({ username, password, remember }),
  })
  const s: AuthState = { token: r.token, user: r.user, expires_at: r.expires_at, remember }
  writeAuth(s)
  return s
}

/** 退出：先让服务端删掉这个会话，再清本地（服务端失败也照样清本地） */
export async function logout(): Promise<void> {
  const token = getToken()
  try {
    if (token) await request('/logout', { method: 'POST', token })
  } catch {
    /* 离线也允许本地退出 */
  }
  clearAuth()
}

/** 用当前 token 换用户信息；token 失效返回 null */
export async function fetchMe(): Promise<AuthUser | null> {
  const token = getToken()
  if (!token) return null
  try {
    const r = await request<{ user: AuthUser }>('/me', { token })
    return r.user
  } catch (e) {
    if (e instanceof Error && /401|未登录|过期/.test(e.message)) return null
    return null
  }
}

/* ---------------- 扫码登录 ---------------- */

export interface QrTicket {
  qr_id: string
  secret: string
  expires_in: number
  expires_at: string
  scan_url: string
  image_url: string
  poll_url: string
  lan_url: string
}

export type QrStatus = 'pending' | 'scanned' | 'confirmed' | 'expired' | 'consumed'

export async function qrStart(): Promise<QrTicket> {
  return request<QrTicket>('/qr/start', { method: 'POST', body: '{}' })
}

export async function qrPoll(qrId: string, secret: string): Promise<{ status: QrStatus; token?: string; user?: AuthUser; expires_at?: string; expires_in?: number }> {
  const q = new URLSearchParams({ qr_id: qrId, secret })
  return request(`/qr/poll?${q.toString()}`)
}

/* ---------------- 与设计稿控制台登录页的衔接 ---------------- */

/**
 * 控制台登录页（docs/console/login.html，挂在 /console）跳回本页时，
 * 若目标跨源（如 3000 开发服）会带上 ?auth_token=<token>（见其 nextUrl()）；
 * 这里把 token 收进 fauth，随后由 fetchMe() 换成真实用户（同源时不需要，直接共享 fauth）。
 */
export function adoptTokenFromUrl(): void {
  try {
    const u = new URL(window.location.href)
    const t = u.searchParams.get('auth_token')
    if (!t) return
    const cur = readAuth()
    if (!cur || cur.token !== t) {
      writeAuth({ token: t, user: { user_id: 0, username: '', display_name: '', role: 'user' } })
    }
    u.searchParams.delete('auth_token')
    window.history.replaceState(null, '', u.pathname + (u.search || '') + u.hash)
  } catch {
    /* 解析失败就什么都不做 */
  }
}

/* ---------------- React 绑定 ---------------- */

export interface AuthHook {
  auth: AuthState | null
  user: AuthUser | null
  admin: boolean
  /** 启动时用 token 校验一次登录态，完成前 ready=false */
  ready: boolean
  signIn: (username: string, password: string, remember: boolean) => Promise<AuthState>
  signOut: () => Promise<void>
}

let booted = false

export function useAuth(): AuthHook {
  const [auth, setAuth] = useState<AuthState | null>(() => readAuth())
  const [ready, setReady] = useState(booted)

  useEffect(() => {
    const sync = () => setAuth(readAuth())
    const onUnauthorized = () => setAuth(null)
    window.addEventListener(AUTH_EVENT, sync)
    window.addEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(AUTH_EVENT, sync)
      window.removeEventListener(UNAUTHORIZED_EVENT, onUnauthorized)
      window.removeEventListener('storage', sync)
    }
  }, [])

  useEffect(() => {
    if (booted) return
    booted = true
    adoptTokenFromUrl()
    const cur = readAuth()
    if (!cur) {
      setReady(true)
      return
    }
    fetchMe()
      .then((u) => {
        if (u) writeAuth({ ...cur, user: u })
        else clearAuth()
      })
      .finally(() => setReady(true))
  }, [])

  const signIn = useCallback(async (username: string, password: string, remember: boolean) => login(username, password, remember), [])
  const signOut = useCallback(async () => {
    await logout()
  }, [])

  return { auth, user: auth?.user ?? null, admin: isAdmin(auth), ready, signIn, signOut }
}
