import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useEffect, useState } from 'react'
import { api } from '../api/client'
import type { PolicyConfig, RateLimits } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { LoadingSkeleton } from '../components/LoadingSkeleton'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { INPUT_CLASS } from '../components/ui/FormField'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'

export function Settings() {
  const queryClient = useQueryClient()
  const [form, setForm] = useState<Partial<PolicyConfig>>({})
  const [saved, setSaved] = useState(false)

  const { data: policy, isLoading, error, refetch } = useQuery({
    queryKey: ['policy'],
    queryFn: api.getPolicy,
  })

  useEffect(() => {
    if (policy) setForm(policy)
  }, [policy])

  const updateMutation = useMutation({
    mutationFn: (data: Partial<PolicyConfig>) => api.updatePolicy(data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['policy'] })
      setSaved(true)
      setTimeout(() => setSaved(false), 3000)
    },
  })

  const setRateLimit = (key: keyof RateLimits, value: number) => {
    setForm((f) => ({
      ...f,
      rate_limits: { ...(f.rate_limits as RateLimits), [key]: value },
    }))
  }

  if (isLoading) return <LoadingSkeleton lines={12} />
  if (error || !policy) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load policy'}
        onRetry={() => refetch()}
      />
    )
  }

  const limits = (form.rate_limits ?? policy.rate_limits) as RateLimits

  return (
    <PageContainer>
      <PageHeader
        title="Settings"
        subtitle="Configure automation policy, rate limits, and approval gates."
        action={
          <Button
            onClick={() =>
              updateMutation.mutate({
                auto_apply: form.auto_apply,
                require_doc_approval: form.require_doc_approval,
                require_submit_approval: form.require_submit_approval,
                min_fit_score: form.min_fit_score,
                ats_min_score: form.ats_min_score,
                daily_apply_limit: form.daily_apply_limit,
                rate_limits: limits,
                sourcing_enabled: form.sourcing_enabled,
                sourcing_interval_minutes: form.sourcing_interval_minutes,
              })
            }
            disabled={updateMutation.isPending}
          >
            Save settings
          </Button>
        }
      />

      <form
        onSubmit={(e) => {
          e.preventDefault()
          updateMutation.mutate({
            auto_apply: form.auto_apply,
            require_doc_approval: form.require_doc_approval,
            require_submit_approval: form.require_submit_approval,
            min_fit_score: form.min_fit_score,
            ats_min_score: form.ats_min_score,
            daily_apply_limit: form.daily_apply_limit,
            rate_limits: limits,
            sourcing_enabled: form.sourcing_enabled,
            sourcing_interval_minutes: form.sourcing_interval_minutes,
          })
        }}
        className="space-y-6"
      >
        <Card>
          <h3 className="mb-4 font-semibold text-slate-900 dark:text-slate-100">Automation</h3>
          <div className="space-y-3">
            <Toggle
              label="Auto-apply (skip manual job approval when score passes)"
              checked={form.auto_apply ?? false}
              onChange={(v) => setForm((f) => ({ ...f, auto_apply: v }))}
            />
            <Toggle
              label="Require document approval before filling"
              checked={form.require_doc_approval ?? true}
              onChange={(v) => setForm((f) => ({ ...f, require_doc_approval: v }))}
            />
            <Toggle
              label="Require submit approval before final submission"
              checked={form.require_submit_approval ?? true}
              onChange={(v) => setForm((f) => ({ ...f, require_submit_approval: v }))}
            />
            <Toggle
              label="Sourcing enabled"
              checked={form.sourcing_enabled ?? true}
              onChange={(v) => setForm((f) => ({ ...f, sourcing_enabled: v }))}
            />
          </div>
        </Card>

        <Card>
          <h3 className="mb-4 font-semibold text-slate-900 dark:text-slate-100">Thresholds</h3>
          <div className="grid gap-4 sm:grid-cols-2">
            <NumberField
              label="Min fit score (0–1)"
              value={form.min_fit_score ?? 0}
              step={0.05}
              min={0}
              max={1}
              onChange={(v) => setForm((f) => ({ ...f, min_fit_score: v }))}
            />
            <NumberField
              label="ATS min score (0–1)"
              value={form.ats_min_score ?? 0.7}
              step={0.05}
              min={0}
              max={1}
              onChange={(v) => setForm((f) => ({ ...f, ats_min_score: v }))}
            />
            <NumberField
              label="Daily apply limit"
              value={form.daily_apply_limit ?? 10}
              min={0}
              onChange={(v) => setForm((f) => ({ ...f, daily_apply_limit: v }))}
            />
            <NumberField
              label="Sourcing interval (minutes)"
              value={form.sourcing_interval_minutes ?? 60}
              min={1}
              onChange={(v) => setForm((f) => ({ ...f, sourcing_interval_minutes: v }))}
            />
          </div>
        </Card>

        <Card>
          <h3 className="mb-4 font-semibold text-slate-900 dark:text-slate-100">
            Per-platform rate limits
          </h3>
          <div className="grid gap-3 sm:grid-cols-2">
            {(['default', 'linkedin', 'greenhouse', 'lever', 'workday', 'icims'] as const).map(
              (platform) => (
                <NumberField
                  key={platform}
                  label={platform}
                  value={limits[platform] ?? limits.default}
                  min={0}
                  onChange={(v) => setRateLimit(platform, v)}
                />
              ),
            )}
          </div>
        </Card>

        <div className="flex items-center gap-3">
          <Button type="submit" disabled={updateMutation.isPending}>
            Save settings
          </Button>
          {saved && (
            <span className="text-sm text-emerald-600 dark:text-emerald-400">Saved!</span>
          )}
          {updateMutation.isError && (
            <span className="text-sm text-red-600 dark:text-red-400">
              {updateMutation.error instanceof Error
                ? updateMutation.error.message
                : 'Save failed'}
            </span>
          )}
        </div>
      </form>
    </PageContainer>
  )
}

function Toggle({
  label,
  checked,
  onChange,
}: {
  label: string
  checked: boolean
  onChange: (v: boolean) => void
}) {
  return (
    <label className="flex cursor-pointer items-center gap-3 text-sm text-slate-700 dark:text-slate-300">
      <input type="checkbox" checked={checked} onChange={(e) => onChange(e.target.checked)} />
      {label}
    </label>
  )
}

function NumberField({
  label,
  value,
  onChange,
  min,
  max,
  step = 1,
}: {
  label: string
  value: number
  onChange: (v: number) => void
  min?: number
  max?: number
  step?: number
}) {
  return (
    <div>
      <label className="mb-1 block text-sm font-medium capitalize text-slate-700 dark:text-slate-300">
        {label}
      </label>
      <input
        type="number"
        value={value}
        min={min}
        max={max}
        step={step}
        onChange={(e) => onChange(Number(e.target.value))}
        className={INPUT_CLASS}
      />
    </div>
  )
}
