/** Map backend job.source values to dashboard badge labels. */
const SOURCE_LABELS: Record<string, string> = {
  manual: 'manual',
  manual_url: 'ingest-url',
  rss: 'rss',
  board_api: 'board-api',
}

const SOURCE_COLORS: Record<string, string> = {
  manual: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  'ingest-url': 'bg-violet-100 text-violet-700 dark:bg-violet-900/40 dark:text-violet-300',
  rss: 'bg-sky-100 text-sky-700 dark:bg-sky-900/40 dark:text-sky-300',
  'board-api': 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
}

export function jobSourceLabel(source: string): string {
  return SOURCE_LABELS[source] ?? source.replace(/_/g, '-')
}

export function jobSourceBadgeClass(source: string): string {
  const label = jobSourceLabel(source)
  return SOURCE_COLORS[label] ?? SOURCE_COLORS.manual
}
