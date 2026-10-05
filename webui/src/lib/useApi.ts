/**
 * 极简数据请求 hook：模块级缓存 + 同 key 请求合并 + 可手动重载。
 *
 * 用法: const { data, loading, error, reload } = useApi(() => api.home(), 'home')
 *
 * 注意（踩过的坑）: 不要在 effect 的 cleanup 里 abort 请求 —— React StrictMode 会
 * 「挂载→清理→再挂载」，abort 会杀掉唯一那次请求（net::ERR_ABORTED）并让 inflight
 * 里的 promise 变成已 reject，第二次挂载复用同 key 请求就永远拿不到数据。共享请求
 * 与组件生命周期解绑，只用一个 `alive` 标志阻止卸载后 setState。
 */
import { useCallback, useEffect, useRef, useState } from 'react'

interface Entry<T> {
  at: number
  value: T
}

const cache = new Map<string, Entry<unknown>>()
const inflight = new Map<string, Promise<unknown>>()

export interface ApiState<T> {
  data: T | null
  loading: boolean
  error: string | null
  reload: () => void
}

/**
 * @param fetcher 取数函数（内部已由 api.* 处理 URL）
 * @param key     缓存键（同一 key 的并发请求只会发一次）
 * @param ttl     缓存有效期（毫秒），默认 60s
 */
export function useApi<T>(fetcher: (signal?: AbortSignal) => Promise<T>, key: string, ttl = 60_000): ApiState<T> {
  const hit = cache.get(key) as Entry<T> | undefined
  const [data, setData] = useState<T | null>(hit ? hit.value : null)
  const [loading, setLoading] = useState(!hit)
  const [error, setError] = useState<string | null>(null)
  const [nonce, setNonce] = useState(0)
  const fetcherRef = useRef(fetcher)
  fetcherRef.current = fetcher

  const reload = useCallback(() => {
    cache.delete(key)
    inflight.delete(key)
    setNonce((n) => n + 1)
  }, [key])

  useEffect(() => {
    let alive = true
    const fresh = cache.get(key) as Entry<T> | undefined
    if (fresh && Date.now() - fresh.at < ttl) {
      setData(fresh.value)
      setLoading(false)
      setError(null)
      return
    }

    setLoading(true)
    let p = inflight.get(key) as Promise<T> | undefined
    if (!p) {
      p = Promise.resolve()
        .then(() => fetcherRef.current())
        .then((v) => {
          cache.set(key, { at: Date.now(), value: v })
          return v
        })
      inflight.set(key, p)
      const settle = () => {
        if (inflight.get(key) === p) inflight.delete(key)
      }
      p.then(settle, settle)
    }

    p.then((v) => {
      if (!alive) return
      setData(v)
      setError(null)
    })
      .catch((e: unknown) => {
        if (!alive) return
        setError(e instanceof Error ? e.message : String(e))
      })
      .finally(() => {
        if (alive) setLoading(false)
      })

    return () => {
      alive = false
    }
  }, [key, ttl, nonce])

  return { data, loading, error, reload }
}

/** 清空缓存（切换账号或手动刷新时用） */
export function clearApiCache(prefix?: string) {
  if (!prefix) {
    cache.clear()
    return
  }
  for (const k of [...cache.keys()]) if (k.startsWith(prefix)) cache.delete(k)
}
