import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { Application, ApplicationStatus } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { KanbanSkeleton } from '../components/LoadingSkeleton'
import { StatusBadge } from '../components/StatusBadge'

const KANBAN_COLUMNS: { status: ApplicationStatus; label: string }[] = [
  { status: 'pending_approval', label: 'To Review' },
  { status: 'generating_docs', label: 'Generating' },
  { status: 'docs_ready', label: 'Docs Ready' },
  { status: 'filling', label: 'Filling' },
  { status: 'submitted', label: 'Submitted' },
  { status: 'needs_manual', label: 'Needs Manual' },
  { status: 'failed', label: 'Failed' },
]

function formatTimestamp(value: string | null | undefined): string {
  if (!value) return '—'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.slice(0, 16)
  return date.toLocaleString(undefined, {
    month: 'short',
    day: 'numeric',
    hour: '2-digit',
    minute: '2-digit',
  })
}

function PipelineCard({ app }: { app: Application }) {
  const title = app.job?.title ?? `Job #${app.job_id}`
  const company = app.job?.company ?? 'Unknown company'

  return (
    <article className="flex flex-col rounded-lg border border-slate-100 bg-slate-50 transition hover:border-indigo-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-indigo-700">
      <Link to={`/applications/${app.id}`} className="flex flex-col gap-2 p-3">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <p className="line-clamp-2 text-sm font-semibold leading-snug text-slate-900 dark:text-slate-100">
              {title}
            </p>
            <p className="mt-0.5 truncate text-xs text-slate-500">{company}</p>
          </div>
          <StatusBadge status={app.status} className="flex-shrink-0" />
        </div>

        <div className="flex flex-wrap items-center gap-2 text-xs">
          {app.job?.fit_score != null && (
            <span className="rounded bg-emerald-100 px-1.5 py-0.5 font-medium text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
              {(app.job.fit_score * 100).toFixed(0)}% fit
            </span>
          )}
          {app.platform && (
            <span className="rounded bg-slate-200/80 px-1.5 py-0.5 text-slate-600 dark:bg-slate-700 dark:text-slate-300">
              {app.platform}
            </span>
          )}
          <span className="text-slate-400">App #{app.id}</span>
        </div>

        <div className="space-y-0.5 text-[11px] text-slate-400">
          <p>Updated {formatTimestamp(app.updated_at)}</p>
          {app.submitted_at && <p>Submitted {formatTimestamp(app.submitted_at)}</p>}
        </div>

        {app.status_message && (
          <p className="line-clamp-2 text-xs text-amber-600 dark:text-amber-400">
            {app.status_message}
          </p>
        )}
      </Link>

      <div className="flex flex-wrap gap-2 border-t border-slate-200/80 px-3 pb-3 pt-2 dark:border-slate-700">
        {app.job?.url && (
          <a
            href={app.job.url}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            Job posting ↗
          </a>
        )}
        <Link
          to={`/jobs/${app.job_id}`}
          className="text-xs font-medium text-slate-500 hover:text-indigo-600 hover:underline dark:hover:text-indigo-400"
        >
          Job details
        </Link>
      </div>
    </article>
  )
}

export function PipelineKanban() {
  const { data, isLoading, error, refetch } = useQuery({
    queryKey: ['pipeline'],
    queryFn: api.getPipeline,
    refetchInterval: 15_000,
  })

  if (isLoading) return <KanbanSkeleton />
  if (error) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load pipeline'}
        onRetry={() => refetch()}
      />
    )
  }

  const byStatus = new Map(data?.map((col) => [col.status, col]) ?? [])

  return (
    <div className="flex min-h-0 flex-1 flex-col">
      <div className="mb-6 flex-shrink-0">
        <h2 className="text-2xl font-bold">Application Pipeline</h2>
        <p className="text-sm text-slate-500">
          Track applications through approval, document generation, and submission.
        </p>
      </div>

      <div className="-mx-1 flex min-h-0 flex-1 flex-nowrap gap-4 overflow-x-auto px-1 pb-4">
        {KANBAN_COLUMNS.map(({ status, label }) => {
          const col = byStatus.get(status)
          const apps = col?.applications ?? []
          const count = col?.count ?? 0

          return (
            <div
              key={status}
              className="flex min-h-[320px] min-w-[280px] max-w-[340px] flex-1 flex-shrink-0 flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex flex-shrink-0 items-center justify-between border-b border-slate-200 px-3 py-2.5 dark:border-slate-800">
                <h3 className="text-sm font-semibold">{label}</h3>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                  {count}
                </span>
              </div>
              <div className="flex min-h-0 flex-1 flex-col gap-2 overflow-y-auto p-2">
                {apps.length === 0 ? (
                  <p className="px-2 py-6 text-center text-xs text-slate-400">Empty</p>
                ) : (
                  apps.map((app) => <PipelineCard key={app.id} app={app} />)
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
