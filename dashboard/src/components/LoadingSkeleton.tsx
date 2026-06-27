interface Props {
  lines?: number
  className?: string
}

export function LoadingSkeleton({ lines = 3, className = '' }: Props) {
  return (
    <div className={`animate-pulse space-y-3 ${className}`}>
      {Array.from({ length: lines }).map((_, i) => (
        <div
          key={i}
          className="h-4 rounded bg-slate-200 dark:bg-slate-800"
          style={{ width: `${90 - i * 15}%` }}
        />
      ))}
    </div>
  )
}

export function CardSkeleton({ count = 3 }: { count?: number }) {
  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {Array.from({ length: count }).map((_, i) => (
        <div
          key={i}
          className="animate-pulse rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="mb-3 h-5 w-2/3 rounded bg-slate-200 dark:bg-slate-800" />
          <div className="h-3 w-1/2 rounded bg-slate-200 dark:bg-slate-800" />
        </div>
      ))}
    </div>
  )
}

export function KanbanSkeleton() {
  return (
    <div className="flex flex-nowrap gap-4 overflow-x-auto pb-4">
      {Array.from({ length: 5 }).map((_, i) => (
        <div
          key={i}
          className="flex min-h-[320px] min-w-[280px] max-w-[340px] flex-1 flex-shrink-0 flex-col animate-pulse rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="border-b border-slate-200 px-3 py-2.5 dark:border-slate-800">
            <div className="h-5 w-24 rounded bg-slate-200 dark:bg-slate-800" />
          </div>
          <div className="flex flex-1 flex-col gap-2 p-2">
            <div className="h-28 rounded-lg bg-slate-100 dark:bg-slate-800" />
            <div className="h-28 rounded-lg bg-slate-100 dark:bg-slate-800" />
          </div>
        </div>
      ))}
    </div>
  )
}
