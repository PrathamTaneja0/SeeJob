import { useState } from 'react'

interface MemoryMatch {
  chunkType: string
  score: number
  excerpt: string
}

function parseMemoryMatch(rationale: string): MemoryMatch | null {
  const match = rationale.match(
    /^Top memory match \(([^,]+), score=([\d.]+)\):\s*(.+)$/s,
  )
  if (!match) return null
  return {
    chunkType: match[1],
    score: parseFloat(match[2]),
    excerpt: match[3].replace(/\.\.\.$/, '').trim(),
  }
}

export function MatchRationaleCard({ rationale }: { rationale: string }) {
  const [open, setOpen] = useState(false)
  const memoryMatch = parseMemoryMatch(rationale)

  if (memoryMatch) {
    return (
      <div className="mt-3 rounded-lg border border-slate-200 dark:border-slate-700">
        <button
          type="button"
          onClick={() => setOpen((o) => !o)}
          className="flex w-full items-center justify-between px-4 py-3 text-left text-sm font-medium text-slate-900 dark:text-slate-100"
        >
          <span>
            Top memory match
            <span className="ml-2 font-normal text-slate-500">
              ({memoryMatch.chunkType}, {(memoryMatch.score * 100).toFixed(0)}%)
            </span>
          </span>
          <span className="text-slate-400">{open ? '▾' : '▸'}</span>
        </button>
        {open && (
          <div className="border-t border-slate-200 px-4 py-3 text-sm text-slate-600 dark:border-slate-700 dark:text-slate-400">
            {memoryMatch.excerpt}
          </div>
        )}
      </div>
    )
  }

  return (
    <p className="mt-3 text-sm text-slate-600 dark:text-slate-400">{rationale}</p>
  )
}
