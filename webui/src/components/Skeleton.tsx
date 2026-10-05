/** 载入占位：保持卡片尺寸，避免布局跳动 */
export function Skeleton({ className = '' }: { className?: string }) {
  return <span className={`skeleton block rounded-full ${className}`} aria-hidden />
}

/** 卡片内部的通用载入骨架 */
export function CardSkeleton({ rows = 3, className = '' }: { rows?: number; className?: string }) {
  return (
    <div className={`flex flex-col gap-3 ${className}`} aria-busy="true">
      {Array.from({ length: rows }).map((_, i) => (
        <Skeleton key={i} className="h-4 w-full" />
      ))}
    </div>
  )
}
