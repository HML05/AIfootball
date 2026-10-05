/**
 * 后端地址常量（单独成文件，避免 api.ts ↔ auth.ts 循环依赖）
 *
 * 开发时后端跑在 http://127.0.0.1:8000；生产（打包进 FastAPI 静态目录）时同源。
 * 可用 VITE_API_BASE 覆盖，例如 VITE_API_BASE=/api/ui
 */
const RAW: string =
  (import.meta.env.VITE_API_BASE as string | undefined) ??
  (import.meta.env.DEV ? 'http://127.0.0.1:8000/api/ui' : '/api/ui')

/** 界面数据接口前缀：/api/ui */
export const API_BASE: string = RAW.replace(/\/+$/, '')

/** 服务根地址（开发时是 http://127.0.0.1:8000，生产是空串表示同源） */
export const SERVER_ROOT: string = API_BASE.replace(/\/api\/ui$/, '')

/** 登录接口前缀：/api/auth */
export const AUTH_BASE: string = `${SERVER_ROOT}/api/auth`

/**
 * 设计稿控制台登录页（docs/console/login.html，后端挂在 /console）的地址。
 * next = 登录后跳回的地址（同源时该页直接跳回，登录态 localStorage.fauth 互通；
 * 跨源时它会附加 ?auth_token=，由 lib/auth.ts 的 adoptTokenFromUrl() 接收）。
 * why=role → 该页提示「管理后台控制台只允许管理员进入」。
 *
 * next 默认取当前地址：
 *   · 开发（Vite 3000，登录页在 8000）→ 必须给**绝对地址**，否则该页会把 next 解析到
 *     它自己的源（8000）上，开发服就被顶掉了；跨源时它会带回 ?auth_token= 交接登录态。
 *   · 生产（同源）→ 给相对地址，直接共享 localStorage.fauth。
 */
export function consoleLoginUrl(next?: string, why?: 'role'): string {
  const target =
    next ??
    (SERVER_ROOT && typeof window !== 'undefined'
      ? window.location.href
      : typeof window !== 'undefined'
        ? window.location.pathname + window.location.search
        : '/')
  const q = new URLSearchParams({ next: target })
  if (why) q.set('why', why)
  return `${SERVER_ROOT}/console/login.html?${q.toString()}`
}
