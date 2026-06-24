import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { CardSkeleton } from '../components/LoadingSkeleton'

export function JobQueue() {
  const queryClient = useQueryClient()

  const { data: queue, isLoading, error, refetch } = useQuery({
    queryKey: ['jobQueue'],
    queryFn: api.getJobQueue,
    refetchInterval: 15_000,
  })

  const { data: profiles } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.listProfiles,
  })

  const defaultPersonId = profiles?.[0]?.id

  const approveMutation = useMutation({
    mutationFn: ({ jobId, personId }: { jobId: number; personId: number }) =>
      api.updateJobStatus(jobId, 'approve', personId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['jobQueue'] })
      queryClient.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })

  const skipMutation = useMutation({
    mutationFn: (jobId: number) => api.updateJobStatus(jobId, 'skip'),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['jobQueue'] }),
  })

  if (isLoading) return <CardSkeleton count={6} />
  if (error || !queue) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load job queue'}
        onRetry={() => refetch()}
      />
    )
  }

  const buckets = [
    { key: 'to_review', label: 'To Review', data: queue.to_review },
    { key: 'approved', label: 'Approved', data: queue.approved },
    { key: 'skipped', label: 'Skipped', data: queue.skipped },
    { key: 'applied', label: 'Applied', data: queue.applied },
  ]

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Job Queue</h2>
        <p className="text-sm text-slate-500">
          Review discovered jobs and approve targeting for your profile.
        </p>
        {!defaultPersonId && (
          <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
            Create a profile first to approve jobs.
          </p>
        )}
      </div>

      <div className="grid gap-6 lg:grid-cols-2">
        {buckets.map(({ key, label, data }) => (
          <section
            key={key}
            className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
              <h3 className="font-semibold">{label}</h3>
              <span className="text-sm text-slate-500">{data.count}</span>
            </div>
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.jobs.length === 0 ? (
                <li className="px-4 py-6 text-center text-sm text-slate-400">No jobs</li>
              ) : (
                data.jobs.map((job) => (
                  <li key={job.id} className="px-4 py-3">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0 flex-1">
                        <Link
                          to={`/jobs/${job.id}`}
                          className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
                        >
                          {job.title}
                        </Link>
                        <p className="text-sm text-slate-500">
                          {job.company}
                          {job.fit_score != null && (
                            <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                              {(job.fit_score * 100).toFixed(0)}% fit
                            </span>
                          )}
                        </p>
                      </div>
                      {key === 'to_review' && (
                        <div className="flex flex-shrink-0 gap-2">
                          <button
                            type="button"
                            disabled={!defaultPersonId || approveMutation.isPending}
                            onClick={() =>
                              defaultPersonId &&
                              approveMutation.mutate({
                                jobId: job.id,
                                personId: defaultPersonId,
                              })
                            }
                            className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700 disabled:opacity-50"
                          >
                            Approve
                          </button>
                          <button
                            type="button"
                            disabled={skipMutation.isPending}
                            onClick={() => skipMutation.mutate(job.id)}
                            className="rounded-lg border border-slate-300 px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-50 dark:border-slate-600 dark:text-slate-300 dark:hover:bg-slate-800"
                          >
                            Skip
                          </button>
                        </div>
                      )}
                    </div>
                  </li>
                ))
              )}
            </ul>
          </section>
        ))}
      </div>
    </div>
  )
}
