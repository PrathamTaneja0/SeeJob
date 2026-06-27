import { useState } from 'react'
import type { CriticReport } from '../api/types'

const SEVERITY_STYLES: Record<string, string> = {
  error: 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300',
  warning: 'bg-amber-100 text-amber-700 dark:bg-amber-900/40 dark:text-amber-300',
  info: 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400',
}

export function parseCriticReport(raw: string | null): CriticReport | null {
  if (!raw?.trim()) return null
  try {
    const parsed = JSON.parse(raw) as CriticReport
    if (typeof parsed.score !== 'number') return null
    return parsed
  } catch {
    return null
  }
}

export function AtsReport({ report }: { report: CriticReport }) {
  const [notesOpen, setNotesOpen] = useState(false)
  const scorePct = (report.score * 100).toFixed(0)
  const coveragePct = ((report.keyword_coverage ?? 0) * 100).toFixed(0)

  const revisionLines = [
    ...report.issues.map((i) => i.message),
    ...(report.missing_keywords?.length
      ? [`Integrate these JD keywords where truthful: ${report.missing_keywords.slice(0, 15).join(', ')}`]
      : []),
  ]

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-center gap-2">
        <span
          className={`rounded px-2 py-0.5 text-xs font-semibold ${
            report.passed
              ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
              : 'bg-red-100 text-red-700 dark:bg-red-900/40 dark:text-red-300'
          }`}
        >
          {report.passed ? 'Passed' : 'Failed'}
        </span>
        <span className="rounded bg-indigo-100 px-2 py-0.5 text-xs font-medium text-indigo-700 dark:bg-indigo-900/40 dark:text-indigo-300">
          Score {scorePct}%
        </span>
        <span className="text-xs text-slate-500">Keyword coverage {coveragePct}%</span>
      </div>

      {report.issues.length > 0 && (
        <ul className="space-y-2">
          {report.issues.map((issue, idx) => (
            <li
              key={`${issue.code}-${idx}`}
              className="flex items-start gap-2 text-sm text-slate-700 dark:text-slate-300"
            >
              <span
                className={`mt-0.5 shrink-0 rounded px-1.5 py-0.5 text-xs font-medium capitalize ${
                  SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.info
                }`}
              >
                {issue.severity}
              </span>
              <span>{issue.message}</span>
            </li>
          ))}
        </ul>
      )}

      {revisionLines.length > 0 && (
        <div>
          <button
            type="button"
            onClick={() => setNotesOpen((o) => !o)}
            className="text-sm font-medium text-indigo-600 hover:underline dark:text-indigo-400"
          >
            {notesOpen ? 'Hide revision notes' : 'Show revision notes'}
          </button>
          {notesOpen && (
            <ul className="mt-2 list-inside list-disc space-y-1 text-sm text-slate-600 dark:text-slate-400">
              {revisionLines.map((line, idx) => (
                <li key={idx}>{line}</li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  )
}
