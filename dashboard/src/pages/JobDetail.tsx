import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'

export function JobDetail() {
  const { id } = useParams<{ id: string }>()
  const jobId = Number(id)

  const { data: job, isLoading, error, refetch } = useQuery({
    queryKey: ['job', jobId],
    queryFn: () => api.getJob(jobId),
    enabled: Number.isFinite(jobId),
  })

  const { data: applications } = useQuery({
    queryKey: ['applications'],
    queryFn: () => api.listApplications(),
    enabled: Number.isFinite(jobId),
  })

  const application = applications?.find((a) => a.job_id === jobId)

  if (isLoading) return <LoadingSkeleton lines={8} />
  if (error || !job) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Job not found'}
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div className="mx-auto max-w-3xl">
      <Link to="/jobs" className="text-sm text-indigo-600 hover:underline dark:text-indigo-400">
        ← Back to queue
      </Link>

      <header className="mt-4">
        <h2 className="text-2xl font-bold">{job.title}</h2>
        <p className="text-lg text-slate-600 dark:text-slate-400">{job.company}</p>
        <div className="mt-2 flex flex-wrap gap-2 text-sm text-slate-500">
          {job.location && <span>{job.location}</span>}
          {job.is_remote && (
            <span className="rounded bg-blue-100 px-2 py-0.5 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
              Remote
            </span>
          )}
          <span className="capitalize">{job.status.replace(/_/g, ' ')}</span>
          <span>· {job.source}</span>
        </div>
      </header>

      {(job.fit_score != null || job.match_rationale) && (
        <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="font-semibold">Fit Analysis</h3>
          {job.fit_score != null && (
            <div className="mt-2">
              <div className="flex items-center justify-between text-sm">
                <span>Fit score</span>
                <span className="font-medium">{(job.fit_score * 100).toFixed(0)}%</span>
              </div>
              <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-200 dark:bg-slate-700">
                <div
                  className="h-full rounded-full bg-emerald-500"
                  style={{ width: `${job.fit_score * 100}%` }}
                />
              </div>
            </div>
          )}
          {job.match_rationale && (
            <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">
              {job.match_rationale}
            </p>
          )}
        </section>
      )}

      {application && (
        <section className="mt-4">
          <Link
            to={`/applications/${application.id}`}
            className="inline-flex items-center rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700"
          >
            View Application #{application.id}
          </Link>
        </section>
      )}

      {job.jd_text && (
        <section className="mt-6 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900">
          <h3 className="mb-3 font-semibold">Job Description</h3>
          <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
            {job.jd_text}
          </pre>
        </section>
      )}

      <p className="mt-4">
        <a
          href={job.url}
          target="_blank"
          rel="noopener noreferrer"
          className="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
        >
          Open posting ↗
        </a>
      </p>
    </div>
  )
}
