import { jobSourceBadgeClass, jobSourceLabel } from '../utils/jobSource'

export function SourceBadge({ source }: { source: string }) {
  const label = jobSourceLabel(source)
  return (
    <span
      className={`rounded px-2 py-0.5 text-xs font-medium ${jobSourceBadgeClass(source)}`}
      title={`Job source: ${label}`}
    >
      {label}
    </span>
  )
}
