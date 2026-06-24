import type { ApplicationStatus } from '../api/types'

const STATUS_COLORS: Record<string, string> = {
  pending_approval:
    'bg-amber-100 text-amber-800 dark:bg-amber-900/40 dark:text-amber-200',
  generating_docs:
    'bg-blue-100 text-blue-800 dark:bg-blue-900/40 dark:text-blue-200',
  docs_ready:
    'bg-emerald-100 text-emerald-800 dark:bg-emerald-900/40 dark:text-emerald-200',
  filling: 'bg-indigo-100 text-indigo-800 dark:bg-indigo-900/40 dark:text-indigo-200',
  submitted:
    'bg-green-100 text-green-800 dark:bg-green-900/40 dark:text-green-200',
  needs_manual:
    'bg-orange-100 text-orange-800 dark:bg-orange-900/40 dark:text-orange-200',
  failed: 'bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200',
  auth_required:
    'bg-purple-100 text-purple-800 dark:bg-purple-900/40 dark:text-purple-200',
  discovered: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
  scored: 'bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300',
}

interface Props {
  status: ApplicationStatus | string
  className?: string
}

export function StatusBadge({ status, className = '' }: Props) {
  const colors = STATUS_COLORS[status] ?? STATUS_COLORS.discovered
  const label = status.replace(/_/g, ' ')

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium capitalize ${colors} ${className}`}
    >
      {label}
    </span>
  )
}
