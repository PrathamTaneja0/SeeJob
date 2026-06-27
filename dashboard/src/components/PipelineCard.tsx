import { Link } from 'react-router-dom'
import type { Application } from '../api/types'

function formatRelativeTime(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '—'
  const seconds = Math.floor((Date.now() - date.getTime()) / 1000)
  if (seconds < 60) return 'just now'
  const minutes = Math.floor(seconds / 60)
  if (minutes < 60) return `${minutes}m ago`
  const hours = Math.floor(minutes / 60)
  if (hours < 24) return `${hours}h ago`
  const days = Math.floor(hours / 24)
  if (days < 7) return `${days}d ago`
  return date.toLocaleDateString(undefined, { month: 'short', day: 'numeric' })
}

export function PipelineCard({ app }: { app: Application }) {
  const title = app.job?.title ?? `Job #${app.job_id}`
  const company = app.job?.company ?? 'Unknown company'

  return (
    <Link
      to={`/applications/${app.id}`}
      className="flex max-h-[120px] min-h-[88px] flex-col justify-center rounded-lg border border-slate-100 bg-slate-50 p-3 transition hover:border-indigo-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-indigo-700"
    >
      <p className="truncate text-sm font-semibold text-slate-900 dark:text-slate-100">
        {title}
      </p>
      <p className="mt-1 truncate text-xs text-slate-500">{company}</p>
      <div className="mt-1.5 flex items-center gap-2 text-xs">
        {app.job?.fit_score != null && (
          <span className="font-medium text-emerald-600 dark:text-emerald-400">
            {(app.job.fit_score * 100).toFixed(0)}% fit
          </span>
        )}
        <span className="text-slate-400">{formatRelativeTime(app.updated_at)}</span>
      </div>
    </Link>
  )
}
