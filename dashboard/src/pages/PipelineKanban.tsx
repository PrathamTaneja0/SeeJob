import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import type { ApplicationStatus } from '../api/types'
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
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Application Pipeline</h2>
        <p className="text-sm text-slate-500">
          Track applications through approval, document generation, and submission.
        </p>
      </div>

      <div className="flex gap-4 overflow-x-auto pb-4">
        {KANBAN_COLUMNS.map(({ status, label }) => {
          const col = byStatus.get(status)
          const apps = col?.applications ?? []
          const count = col?.count ?? 0

          return (
            <div
              key={status}
              className="flex min-w-[260px] flex-shrink-0 flex-col rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-3 py-2 dark:border-slate-800">
                <h3 className="text-sm font-semibold">{label}</h3>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                  {count}
                </span>
              </div>
              <div className="flex-1 space-y-2 p-2">
                {apps.length === 0 ? (
                  <p className="px-2 py-4 text-center text-xs text-slate-400">Empty</p>
                ) : (
                  apps.map((app) => (
                    <Link
                      key={app.id}
                      to={`/applications/${app.id}`}
                      className="block rounded-lg border border-slate-100 bg-slate-50 p-3 transition hover:border-indigo-300 hover:shadow-sm dark:border-slate-800 dark:bg-slate-800/50 dark:hover:border-indigo-700"
                    >
                      <div className="flex items-start justify-between gap-2">
                        <span className="text-sm font-medium">App #{app.id}</span>
                        <StatusBadge status={app.status} />
                      </div>
                      <p className="mt-1 text-xs text-slate-500">
                        Job #{app.job_id} · Person #{app.person_id}
                      </p>
                      {app.status_message && (
                        <p className="mt-1 line-clamp-2 text-xs text-amber-600 dark:text-amber-400">
                          {app.status_message}
                        </p>
                      )}
                    </Link>
                  ))
                )}
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}
