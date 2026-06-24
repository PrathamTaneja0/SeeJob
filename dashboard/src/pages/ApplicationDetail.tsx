import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { StatusBadge } from '../components/StatusBadge'

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>()
  const appId = Number(id)
  const queryClient = useQueryClient()
  const [applyResult, setApplyResult] = useState<string | null>(null)

  const { data: app, isLoading, error, refetch } = useQuery({
    queryKey: ['application', appId],
    queryFn: () => api.getApplication(appId),
    enabled: Number.isFinite(appId),
  })

  const { data: docsView } = useQuery({
    queryKey: ['applicationDocs', appId],
    queryFn: () => api.getApplicationDocuments(appId),
    enabled: Number.isFinite(appId),
  })

  const { data: job } = useQuery({
    queryKey: ['job', app?.job_id],
    queryFn: () => api.getJob(app!.job_id),
    enabled: !!app?.job_id,
  })

  const approveDoc = useMutation({
    mutationFn: ({ docId, approved }: { docId: number; approved: boolean }) =>
      api.approveDocument(appId, docId, approved),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', appId] })
      queryClient.invalidateQueries({ queryKey: ['applicationDocs', appId] })
    },
  })

  const applyMutation = useMutation({
    mutationFn: ({ dryRun, submit }: { dryRun: boolean; submit: boolean }) =>
      api.applyApplication(appId, dryRun, submit),
    onSuccess: (result) => {
      setApplyResult(
        `${result.result}: ${result.fields_filled} fields filled${result.message ? ` — ${result.message}` : ''}`,
      )
      queryClient.invalidateQueries({ queryKey: ['application', appId] })
      queryClient.invalidateQueries({ queryKey: ['pipeline'] })
    },
    onError: (err) => setApplyResult(err instanceof Error ? err.message : 'Apply failed'),
  })

  const resumeMutation = useMutation({
    mutationFn: () => api.resumeApplication(appId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['application', appId] })
      queryClient.invalidateQueries({ queryKey: ['pipeline'] })
    },
  })

  if (isLoading) return <LoadingSkeleton lines={10} />
  if (error || !app) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Application not found'}
        onRetry={() => refetch()}
      />
    )
  }

  const documents = docsView?.documents ?? app.documents

  return (
    <div className="mx-auto max-w-4xl">
      <Link to="/" className="text-sm text-indigo-600 hover:underline dark:text-indigo-400">
        ← Back to pipeline
      </Link>

      <header className="mt-4 flex flex-wrap items-start justify-between gap-4">
        <div>
          <h2 className="text-2xl font-bold">
            Application #{app.id}
            {job && (
              <span className="ml-2 text-lg font-normal text-slate-500">
                — {job.title} at {job.company}
              </span>
            )}
          </h2>
          <div className="mt-2 flex items-center gap-2">
            <StatusBadge status={app.status} />
            {app.platform && (
              <span className="text-sm text-slate-500">{app.platform}</span>
            )}
          </div>
          {app.status_message && (
            <p className="mt-2 text-sm text-amber-600 dark:text-amber-400">
              {app.status_message}
            </p>
          )}
        </div>
        <div className="flex flex-wrap gap-2">
          {app.status === 'needs_manual' && (
            <button
              type="button"
              onClick={() => resumeMutation.mutate()}
              disabled={resumeMutation.isPending}
              className="rounded-lg bg-orange-600 px-4 py-2 text-sm font-medium text-white hover:bg-orange-700 disabled:opacity-50"
            >
              Resume after manual
            </button>
          )}
          <button
            type="button"
            onClick={() => applyMutation.mutate({ dryRun: true, submit: false })}
            disabled={applyMutation.isPending}
            className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium hover:bg-slate-50 dark:border-slate-600 dark:hover:bg-slate-800"
          >
            Dry run
          </button>
          <button
            type="button"
            onClick={() => applyMutation.mutate({ dryRun: false, submit: true })}
            disabled={applyMutation.isPending}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
          >
            Submit
          </button>
        </div>
      </header>

      {applyResult && (
        <p className="mt-4 rounded-lg bg-slate-100 p-3 text-sm dark:bg-slate-800">
          {applyResult}
        </p>
      )}

      {job && (
        <Link
          to={`/jobs/${job.id}`}
          className="mt-4 inline-block text-sm text-indigo-600 hover:underline dark:text-indigo-400"
        >
          View job details →
        </Link>
      )}

      <section className="mt-8 space-y-6">
        <h3 className="text-lg font-semibold">Generated Documents</h3>
        {documents.length === 0 ? (
          <p className="text-sm text-slate-500">No documents generated yet.</p>
        ) : (
          documents.map((doc) => (
            <article
              key={doc.id}
              className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900"
            >
              <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-4 py-3 dark:border-slate-800">
                <div className="flex items-center gap-2">
                  <span className="font-medium capitalize">{doc.doc_type.replace(/_/g, ' ')}</span>
                  <span className="text-xs text-slate-500">v{doc.version}</span>
                  {doc.approved && (
                    <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                      Approved
                    </span>
                  )}
                </div>
                <div className="flex gap-2">
                  {!doc.approved && (
                    <button
                      type="button"
                      onClick={() => approveDoc.mutate({ docId: doc.id, approved: true })}
                      disabled={approveDoc.isPending}
                      className="rounded-lg bg-emerald-600 px-3 py-1 text-xs font-medium text-white hover:bg-emerald-700"
                    >
                      Approve
                    </button>
                  )}
                  {doc.approved && (
                    <button
                      type="button"
                      onClick={() => approveDoc.mutate({ docId: doc.id, approved: false })}
                      className="rounded-lg border border-slate-300 px-3 py-1 text-xs dark:border-slate-600"
                    >
                      Revoke
                    </button>
                  )}
                </div>
              </div>

              {doc.ats_score != null && (
                <div className="border-b border-slate-200 px-4 py-2 dark:border-slate-800">
                  <span className="text-sm">
                    ATS score: <strong>{(doc.ats_score * 100).toFixed(0)}%</strong>
                  </span>
                </div>
              )}

              {doc.critic_report && (
                <div className="border-b border-slate-200 px-4 py-3 dark:border-slate-800">
                  <h4 className="mb-1 text-sm font-medium text-slate-500">ATS Report</h4>
                  <pre className="whitespace-pre-wrap text-sm text-slate-700 dark:text-slate-300">
                    {doc.critic_report}
                  </pre>
                </div>
              )}

              <div className="prose prose-sm max-w-none p-4 dark:prose-invert">
                <ReactMarkdown>{doc.markdown_content}</ReactMarkdown>
              </div>
            </article>
          ))
        )}
      </section>
    </div>
  )
}
