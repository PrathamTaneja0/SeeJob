import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { Link } from 'react-router-dom'
import { api, ApiError } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { CardSkeleton } from '../components/LoadingSkeleton'
import { SourceBadge } from '../components/SourceBadge'
import { Button } from '../components/ui/Button'
import { FormField } from '../components/ui/FormField'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'

export function JobQueue() {
  const queryClient = useQueryClient()
  const [ingestOpen, setIngestOpen] = useState(false)
  const [ingestUrl, setIngestUrl] = useState('')
  const [ingestMsg, setIngestMsg] = useState<{ text: string; ok: boolean } | null>(null)

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

  const ingestMutation = useMutation({
    mutationFn: ({ url, personId }: { url: string; personId?: number }) =>
      api.ingestJobUrl(url, personId),
    onSuccess: (job) => {
      setIngestMsg({
        text: `Added "${job.title}" at ${job.company}${job.fit_score != null ? ` (${(job.fit_score * 100).toFixed(0)}% fit)` : ''}`,
        ok: true,
      })
      setIngestUrl('')
      queryClient.invalidateQueries({ queryKey: ['jobQueue'] })
    },
    onError: (err) => {
      setIngestMsg({
        text: err instanceof ApiError ? err.message : 'Failed to ingest URL',
        ok: false,
      })
    },
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

  const closeIngestModal = () => {
    setIngestOpen(false)
    setIngestMsg(null)
    setIngestUrl('')
  }

  return (
    <PageContainer>
      <PageHeader
        title="Job Queue"
        subtitle="Review discovered jobs and approve targeting for your profile. Jobs are added via manual POST, Ingest URL, RSS feeds (policy), or seejob-sourcing — not auto LinkedIn unless you configure RSS."
        action={
          <Button onClick={() => setIngestOpen(true)}>Ingest URL</Button>
        }
      />

      {!defaultPersonId && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          Create a profile first to approve jobs.
        </p>
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        {buckets.map(({ key, label, data }) => (
          <section
            key={key}
            className="rounded-lg border border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900"
          >
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700">
              <h3 className="font-semibold text-slate-900 dark:text-slate-100">{label}</h3>
              <span className="text-sm text-slate-500">{data.count}</span>
            </div>
            <ul className="divide-y divide-slate-100 dark:divide-slate-800">
              {data.jobs.length === 0 ? (
                <li className="px-6 py-6 text-center text-sm text-slate-400">
                  {key === 'to_review' ? (
                    <>
                      No jobs yet.
                      <br />
                      Add jobs via Ingest URL or run seejob-sourcing.
                    </>
                  ) : (
                    'No jobs'
                  )}
                </li>
              ) : (
                data.jobs.map((job) => (
                  <li key={job.id} className="px-6 py-3">
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
                          {job.location && (
                            <span className="ml-1 text-slate-400">· {job.location}</span>
                          )}
                          <span className="ml-2 inline-flex align-middle">
                            <SourceBadge source={job.source} />
                          </span>
                          {job.fit_score != null && (
                            <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                              {(job.fit_score * 100).toFixed(0)}% fit
                            </span>
                          )}
                        </p>
                        <p className="mt-1 text-xs text-slate-400">
                          {new Date(job.updated_at).toLocaleDateString(undefined, {
                            month: 'short',
                            day: 'numeric',
                          })}
                        </p>
                      </div>
                      {key === 'to_review' && (
                        <div className="flex flex-shrink-0 gap-2">
                          <Button
                            variant="success"
                            size="sm"
                            disabled={!defaultPersonId || approveMutation.isPending}
                            onClick={() =>
                              defaultPersonId &&
                              approveMutation.mutate({
                                jobId: job.id,
                                personId: defaultPersonId,
                              })
                            }
                          >
                            Approve
                          </Button>
                          <Button
                            variant="secondary"
                            size="sm"
                            disabled={skipMutation.isPending}
                            onClick={() => skipMutation.mutate(job.id)}
                          >
                            Skip
                          </Button>
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

      {ingestOpen && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
          role="dialog"
          aria-modal="true"
          aria-labelledby="ingest-url-title"
        >
          <div className="w-full max-w-lg rounded-lg border border-slate-200 bg-white p-6 shadow-xl dark:border-slate-700 dark:bg-slate-900">
            <h2
              id="ingest-url-title"
              className="text-lg font-semibold text-slate-900 dark:text-slate-100"
            >
              Ingest job URL
            </h2>
            <p className="mt-2 text-sm text-slate-500">
              Paste a public job posting URL. SeeJob fetches the page, parses title/company/JD, and
              adds it to the review queue
              {defaultPersonId ? ' with fit scoring against your profile.' : '.'}
            </p>

            <form
              className="mt-4 space-y-4"
              onSubmit={(e) => {
                e.preventDefault()
                const trimmed = ingestUrl.trim()
                if (!trimmed) return
                setIngestMsg(null)
                ingestMutation.mutate({
                  url: trimmed,
                  personId: defaultPersonId,
                })
              }}
            >
              <FormField
                label="Job posting URL"
                type="url"
                required
                value={ingestUrl}
                onChange={setIngestUrl}
                placeholder="https://boards.example.com/jobs/12345"
              />

              {ingestMsg && (
                <p
                  className={`rounded-lg px-3 py-2 text-sm ${
                    ingestMsg.ok
                      ? 'border border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300'
                      : 'border border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
                  }`}
                >
                  {ingestMsg.text}
                </p>
              )}

              <div className="flex justify-end gap-2">
                <Button type="button" variant="secondary" onClick={closeIngestModal}>
                  {ingestMsg?.ok ? 'Done' : 'Cancel'}
                </Button>
                {!ingestMsg?.ok && (
                  <Button type="submit" disabled={ingestMutation.isPending || !ingestUrl.trim()}>
                    {ingestMutation.isPending ? 'Fetching…' : 'Ingest'}
                  </Button>
                )}
              </div>
            </form>
          </div>
        </div>
      )}
    </PageContainer>
  )
}
