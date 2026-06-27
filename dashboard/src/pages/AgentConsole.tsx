import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '../api/client'
import { useEventStream } from '../hooks/useEventStream'
import { Card } from '../components/ui/Card'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'

export function AgentConsole() {
  const { events, connected, error } = useEventStream()

  const { data: manualApps } = useQuery({
    queryKey: ['applications', 'needs_manual'],
    queryFn: () => api.listApplications('needs_manual'),
    refetchInterval: 10_000,
  })

  const paused = (manualApps?.length ?? 0) > 0

  return (
    <PageContainer>
      <PageHeader
        title="Agent Console"
        subtitle="Live orchestration events via SSE"
        action={
          <div className="flex items-center gap-3">
            {paused && (
              <div className="flex items-center gap-2 rounded-lg border border-orange-300 bg-orange-50 px-3 py-2 text-sm text-orange-800 dark:border-orange-800 dark:bg-orange-950/40 dark:text-orange-200">
                <span className="relative flex h-2 w-2">
                  <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-orange-400 opacity-75" />
                  <span className="relative inline-flex h-2 w-2 rounded-full bg-orange-500" />
                </span>
                Paused — {manualApps!.length} need manual
                {manualApps!.slice(0, 3).map((app) => (
                  <Link
                    key={app.id}
                    to={`/applications/${app.id}`}
                    className="ml-1 font-medium underline"
                  >
                    #{app.id}
                  </Link>
                ))}
              </div>
            )}
            <span
              className={`inline-flex items-center gap-1.5 rounded-full px-3 py-1 text-xs font-medium ${
                connected
                  ? 'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-300'
                  : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
              }`}
            >
              <span
                className={`h-2 w-2 rounded-full ${connected ? 'bg-emerald-500' : 'bg-slate-400'}`}
              />
              {connected ? 'Connected' : 'Disconnected'}
            </span>
          </div>
        }
      />

      {error && (
        <p className="mb-4 rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-800 dark:border-amber-900/50 dark:bg-amber-950/30 dark:text-amber-300">
          {error}
        </p>
      )}

      <Card padding={false} className="flex h-[calc(100vh-14rem)] flex-col overflow-hidden bg-slate-950">
        <div className="h-full overflow-y-auto p-6 font-mono text-sm">
          {events.length === 0 ? (
            <p className="text-slate-500">Waiting for events…</p>
          ) : (
            <ul className="space-y-2">
              {[...events].reverse().map((event) => (
                <li key={event.id} className="text-slate-300">
                  <span className="text-slate-500">
                    [{event.timestamp?.slice(11, 19) ?? '??:??:??'}]
                  </span>{' '}
                  <span className="text-indigo-400">{event.event_type}</span>{' '}
                  {event.application_id != null && (
                    <Link
                      to={`/applications/${event.application_id}`}
                      className="text-cyan-400 hover:underline"
                    >
                      app#{event.application_id}
                    </Link>
                  )}{' '}
                  <span>{event.message}</span>
                  {event.worker_name && (
                    <span className="text-slate-500"> ({event.worker_name})</span>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      </Card>
    </PageContainer>
  )
}
