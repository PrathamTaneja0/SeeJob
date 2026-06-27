import { useQuery } from '@tanstack/react-query'
import { api } from '../api/client'
import type { ApplicationStatus } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { KanbanSkeleton } from '../components/LoadingSkeleton'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'
import { PipelineCard } from '../components/PipelineCard'

const PIPELINE_SECTIONS: { status: ApplicationStatus; label: string }[] = [
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
    <PageContainer>
      <PageHeader
        title="Application Pipeline"
        subtitle="Track applications through approval, document generation, and submission."
      />

      <div className="flex flex-col gap-5 pb-4">
        {PIPELINE_SECTIONS.map(({ status, label }) => {
          const col = byStatus.get(status)
          const apps = col?.applications ?? []
          const count = col?.count ?? 0

          return (
            <section
              key={status}
              className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
            >
              <div className="flex items-center justify-between border-b border-slate-200 px-6 py-3 dark:border-slate-700">
                <h3 className="text-sm font-semibold text-slate-900 dark:text-slate-100">
                  {label}
                </h3>
                <span className="rounded-full bg-slate-100 px-2 py-0.5 text-xs font-medium text-slate-600 dark:bg-slate-800 dark:text-slate-400">
                  {count}
                </span>
              </div>
              <div className="p-4">
                {apps.length === 0 ? (
                  <p className="py-1 text-center text-xs text-slate-400">No applications</p>
                ) : (
                  <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
                    {apps.map((app) => (
                      <PipelineCard key={app.id} app={app} />
                    ))}
                  </div>
                )}
              </div>
            </section>
          )
        })}
      </div>
    </PageContainer>
  )
}
