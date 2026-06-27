import { useQuery } from '@tanstack/react-query'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { MatchRationaleCard } from '../components/MatchRationaleCard'
import { SourceBadge } from '../components/SourceBadge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'

function formatJobDescription(text: string): string[] {
  return text
    .split(/\n{2,}/)
    .map((p) => p.trim())
    .filter(Boolean)
}

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

  const jdParagraphs = job.jd_text ? formatJobDescription(job.jd_text) : []

  return (
    <PageContainer narrow>
      <Link
        to="/jobs"
        className="text-sm text-indigo-600 hover:underline dark:text-indigo-400"
      >
        ← Back to queue
      </Link>

      <div className="mt-4">
        <PageHeader
          title={job.title}
          subtitle={`${job.company}${job.location ? ` · ${job.location}` : ''}`}
          action={
            application ? (
              <Link to={`/applications/${application.id}`}>
                <Button>View Application #{application.id}</Button>
              </Link>
            ) : (
              <a href={job.url} target="_blank" rel="noopener noreferrer">
                <Button>Open job posting ↗</Button>
              </a>
            )
          }
        />
      </div>

      <div className="mb-6 flex flex-wrap items-center gap-2">
        <SourceBadge source={job.source} />
        {job.is_remote && (
          <span className="rounded bg-blue-100 px-2 py-0.5 text-xs font-medium text-blue-700 dark:bg-blue-900/40 dark:text-blue-300">
            Remote
          </span>
        )}
        <span className="text-sm capitalize text-slate-500">
          {job.status.replace(/_/g, ' ')}
        </span>
      </div>

      <a
        href={job.url}
        target="_blank"
        rel="noopener noreferrer"
        className="mb-6 inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
      >
        Open job posting ↗
      </a>

      {(job.fit_score != null || job.match_rationale) && (
        <Card className="mb-6">
          <h3 className="font-semibold text-slate-900 dark:text-slate-100">Fit Analysis</h3>
          {job.fit_score != null && (
            <div className="mt-3">
              <div className="flex items-center justify-between text-sm text-slate-700 dark:text-slate-300">
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
          {job.match_rationale && <MatchRationaleCard rationale={job.match_rationale} />}
        </Card>
      )}

      {application && (
        <Card className="mb-6">
          <p className="text-sm text-slate-600 dark:text-slate-400">
            Pipeline application{' '}
            <Link
              to={`/applications/${application.id}`}
              className="font-medium text-indigo-600 hover:underline dark:text-indigo-400"
            >
              #{application.id}
            </Link>{' '}
            · <span className="capitalize">{application.status.replace(/_/g, ' ')}</span>
          </p>
        </Card>
      )}

      {jdParagraphs.length > 0 && (
        <Card className="mb-6">
          <h3 className="mb-4 font-semibold text-slate-900 dark:text-slate-100">
            Job Description
          </h3>
          <div className="prose prose-sm max-w-none dark:prose-invert">
            {jdParagraphs.map((para, idx) => (
              <p key={idx} className="text-slate-700 dark:text-slate-300">
                {para}
              </p>
            ))}
          </div>
        </Card>
      )}
    </PageContainer>
  )
}
