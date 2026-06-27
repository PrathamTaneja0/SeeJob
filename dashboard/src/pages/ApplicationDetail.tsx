import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import ReactMarkdown from 'react-markdown'
import { Link, useParams } from 'react-router-dom'
import { api } from '../api/client'
import { AtsReport, parseCriticReport } from '../components/AtsReport'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { StatusBadge } from '../components/StatusBadge'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'
import { stripMarkdownComments } from '../utils/markdown'

export function ApplicationDetail() {
  const { id } = useParams<{ id: string }>()
  const appId = Number(id)
  const queryClient = useQueryClient()
  const [applyResult, setApplyResult] = useState<string | null>(null)
  const [downloadMsg, setDownloadMsg] = useState<string | null>(null)

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
  const jobUrl = job?.url ?? app.job?.url
  const title = job
    ? `${job.title} at ${job.company}`
    : app.job
      ? `${app.job.title} at ${app.job.company}`
      : `Application #${app.id}`

  return (
    <PageContainer narrow>
      <nav className="text-sm text-slate-500">
        <Link to="/" className="text-indigo-600 hover:underline dark:text-indigo-400">
          Pipeline
        </Link>
        <span className="mx-2">→</span>
        <span className="text-slate-700 dark:text-slate-300">Application #{app.id}</span>
      </nav>

      <div className="mt-4">
        <PageHeader
          title={title}
          subtitle={`Application #${app.id}${app.platform ? ` · ${app.platform}` : ''}`}
          action={
            <div className="flex flex-wrap gap-2">
              {app.status === 'needs_manual' && (
                <Button
                  className="bg-orange-600 hover:bg-orange-700 dark:bg-orange-500 dark:hover:bg-orange-600"
                  onClick={() => resumeMutation.mutate()}
                  disabled={resumeMutation.isPending}
                >
                  Resume after manual
                </Button>
              )}
              <Button
                variant="secondary"
                onClick={() => applyMutation.mutate({ dryRun: true, submit: false })}
                disabled={applyMutation.isPending}
              >
                Dry run
              </Button>
              <Button
                onClick={() => applyMutation.mutate({ dryRun: false, submit: true })}
                disabled={applyMutation.isPending}
              >
                Submit
              </Button>
            </div>
          }
        />
      </div>

      <div className="mb-4 flex flex-wrap items-center gap-3">
        <StatusBadge status={app.status} />
        {jobUrl && (
          <a
            href={jobUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="inline-flex items-center gap-1 rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 dark:bg-indigo-500 dark:hover:bg-indigo-600"
          >
            Open job posting ↗
          </a>
        )}
      </div>

      {app.status_message && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          {app.status_message}
        </p>
      )}

      {applyResult && (
        <p className="mb-4 rounded-lg border border-slate-200 bg-slate-100 p-4 text-sm dark:border-slate-700 dark:bg-slate-800">
          {applyResult}
        </p>
      )}

      <div className="mb-6 flex flex-wrap gap-4 text-sm">
        {job && (
          <Link
            to={`/jobs/${job.id}`}
            className="text-indigo-600 hover:underline dark:text-indigo-400"
          >
            View job details →
          </Link>
        )}
        <Link
          to="/profiles"
          className="text-indigo-600 hover:underline dark:text-indigo-400"
        >
          View profile documents →
        </Link>
      </div>

      {downloadMsg && (
        <p className="mb-4 rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300">
          {downloadMsg}
        </p>
      )}

      <section className="space-y-6">
        <h3 className="text-lg font-semibold text-slate-900 dark:text-slate-100">
          Generated Documents
        </h3>
        {documents.length === 0 ? (
          <p className="text-sm text-slate-500">No documents generated yet.</p>
        ) : (
          documents.map((doc) => {
            const criticReport = parseCriticReport(doc.critic_report)
            const displayMarkdown = stripMarkdownComments(doc.markdown_content)

            return (
              <Card key={doc.id} padding={false}>
                <div className="flex flex-wrap items-center justify-between gap-2 border-b border-slate-200 px-6 py-4 dark:border-slate-700">
                  <div className="flex items-center gap-2">
                    <span className="font-medium capitalize text-slate-900 dark:text-slate-100">
                      {doc.doc_type.replace(/_/g, ' ')}
                    </span>
                    <span className="text-xs text-slate-500">v{doc.version}</span>
                    {doc.approved && (
                      <span className="rounded bg-emerald-100 px-2 py-0.5 text-xs text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300">
                        Approved
                      </span>
                    )}
                  </div>
                  <div className="flex gap-2">
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        setDownloadMsg(null)
                        const base =
                          doc.doc_type === 'cv' ? 'cv' : 'cover_letter'
                        try {
                          await api.downloadDocument(appId, doc.id, base)
                        } catch (err) {
                          setDownloadMsg(
                            err instanceof Error ? err.message : 'Download failed',
                          )
                        }
                      }}
                    >
                      Download PDF
                    </Button>
                    <Button
                      variant="secondary"
                      size="sm"
                      onClick={async () => {
                        setDownloadMsg(null)
                        const base =
                          doc.doc_type === 'cv' ? 'cv' : 'cover_letter'
                        try {
                          const url = api.documentDownloadUrl(appId, doc.id, 'md')
                          const res = await fetch(url)
                          if (!res.ok) throw new Error('Markdown download failed')
                          const blob = await res.blob()
                          const objectUrl = URL.createObjectURL(blob)
                          const anchor = document.createElement('a')
                          anchor.href = objectUrl
                          anchor.download = `${base}.md`
                          anchor.click()
                          URL.revokeObjectURL(objectUrl)
                        } catch (err) {
                          setDownloadMsg(
                            err instanceof Error ? err.message : 'Download failed',
                          )
                        }
                      }}
                    >
                      Download .md
                    </Button>
                    {!doc.approved && (
                      <Button
                        variant="success"
                        size="sm"
                        onClick={() => approveDoc.mutate({ docId: doc.id, approved: true })}
                        disabled={approveDoc.isPending}
                      >
                        Approve
                      </Button>
                    )}
                    {doc.approved && (
                      <Button
                        variant="secondary"
                        size="sm"
                        onClick={() => approveDoc.mutate({ docId: doc.id, approved: false })}
                      >
                        Revoke
                      </Button>
                    )}
                  </div>
                </div>

                {criticReport && (
                  <div className="border-b border-slate-200 px-6 py-4 dark:border-slate-700">
                    <h4 className="mb-3 text-sm font-medium text-slate-500">ATS Report</h4>
                    <AtsReport report={criticReport} />
                  </div>
                )}

                <div className="prose prose-sm max-w-none p-6 dark:prose-invert">
                  <ReactMarkdown>{displayMarkdown}</ReactMarkdown>
                </div>
              </Card>
            )
          })
        )}
      </section>
    </PageContainer>
  )
}
