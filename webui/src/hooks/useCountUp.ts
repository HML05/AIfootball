import { useEffect, useState } from 'react'

/** 数字从 0 缓动递增到目标值（用于统计数字、百分比的可视化入场动效） */
export function useCountUp(target: number, duration = 1200, decimals = 0) {
  const [value, setValue] = useState(0)

  useEffect(() => {
    let raf = 0
    const start = performance.now()
    const tick = (now: number) => {
      const p = Math.min(1, (now - start) / duration)
      const eased = 1 - Math.pow(1 - p, 3)
      setValue(parseFloat((target * eased).toFixed(decimals)))
      if (p < 1) raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [target, duration, decimals])

  return value
}
