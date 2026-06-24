import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useState } from 'react'
import { api } from '../api/client'
import type { Person, WorkAuthorization } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { CardSkeleton } from '../components/LoadingSkeleton'

const WORK_AUTH_OPTIONS: WorkAuthorization[] = [
  'citizen',
  'permanent_resident',
  'work_visa',
  'student_visa',
  'requires_sponsorship',
  'other',
]

const emptyForm: Partial<Person> = {
  full_name: '',
  email: '',
  phone: '',
  location: '',
  headline: '',
  summary: '',
  work_authorization: 'other',
  willing_to_relocate: false,
  salary_currency: 'USD',
}

export function ProfileEditor() {
  const queryClient = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<Person>>(emptyForm)
  const [uploadMsg, setUploadMsg] = useState<string | null>(null)

  const { data: profiles, isLoading, error, refetch } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.listProfiles,
  })

  const createMutation = useMutation({
    mutationFn: (data: Partial<Person>) => api.createProfile(data),
    onSuccess: (person) => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setSelectedId(person.id)
      setForm(person)
    },
  })

  const updateMutation = useMutation({
    mutationFn: ({ id, data }: { id: number; data: Partial<Person> }) =>
      api.updateProfile(id, data),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ['profiles'] }),
  })

  const deleteMutation = useMutation({
    mutationFn: (id: number) => api.deleteProfile(id),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      setSelectedId(null)
      setForm(emptyForm)
    },
  })

  const ingestMutation = useMutation({
    mutationFn: ({ id, file }: { id: number; file: File }) => api.ingestCv(id, file),
    onSuccess: (result) => {
      setUploadMsg(
        `Ingested: +${result.experiences_added} exp, +${result.education_added} edu, +${result.skills_added} skills`,
      )
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
    },
    onError: (err) =>
      setUploadMsg(err instanceof Error ? err.message : 'Upload failed'),
  })

  const selectProfile = async (id: number) => {
    setSelectedId(id)
    const person = await api.getProfile(id)
    setForm(person)
    setUploadMsg(null)
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedId) {
      updateMutation.mutate({ id: selectedId, data: form })
    } else {
      createMutation.mutate(form)
    }
  }

  if (isLoading) return <CardSkeleton count={2} />
  if (error) {
    return (
      <ErrorState
        message={error instanceof Error ? error.message : 'Failed to load profiles'}
        onRetry={() => refetch()}
      />
    )
  }

  return (
    <div>
      <div className="mb-6">
        <h2 className="text-2xl font-bold">Profile Editor</h2>
        <p className="text-sm text-slate-500">
          Manage your candidate profile and upload a master CV for ingestion.
        </p>
      </div>

      <div className="grid gap-6 lg:grid-cols-3">
        <aside className="rounded-xl border border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
          <div className="flex items-center justify-between border-b border-slate-200 px-4 py-3 dark:border-slate-800">
            <h3 className="font-semibold">Profiles</h3>
            <button
              type="button"
              onClick={() => {
                setSelectedId(null)
                setForm(emptyForm)
              }}
              className="text-xs text-indigo-600 hover:underline dark:text-indigo-400"
            >
              + New
            </button>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {profiles?.length === 0 && (
              <li className="px-4 py-6 text-center text-sm text-slate-400">No profiles yet</li>
            )}
            {profiles?.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => selectProfile(p.id)}
                  className={`w-full px-4 py-3 text-left text-sm hover:bg-slate-50 dark:hover:bg-slate-800 ${
                    selectedId === p.id ? 'bg-indigo-50 dark:bg-indigo-950/30' : ''
                  }`}
                >
                  <span className="font-medium">{p.full_name}</span>
                  <span className="block text-xs text-slate-500">{p.email}</span>
                </button>
              </li>
            ))}
          </ul>
        </aside>

        <form
          onSubmit={handleSubmit}
          className="lg:col-span-2 space-y-4 rounded-xl border border-slate-200 bg-white p-4 dark:border-slate-800 dark:bg-slate-900"
        >
          <div className="grid gap-4 sm:grid-cols-2">
            <Field
              label="Full name"
              value={form.full_name ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, full_name: v }))}
              required
            />
            <Field
              label="Email"
              type="email"
              value={form.email ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, email: v }))}
              required
            />
            <Field
              label="Phone"
              value={form.phone ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, phone: v }))}
            />
            <Field
              label="Location"
              value={form.location ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, location: v }))}
            />
            <Field
              label="Headline"
              value={form.headline ?? ''}
              onChange={(v) => setForm((f) => ({ ...f, headline: v }))}
              className="sm:col-span-2"
            />
          </div>

          <div>
            <label className="mb-1 block text-sm font-medium">Summary</label>
            <textarea
              value={form.summary ?? ''}
              onChange={(e) => setForm((f) => ({ ...f, summary: e.target.value }))}
              rows={4}
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800"
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <div>
              <label className="mb-1 block text-sm font-medium">Work authorization</label>
              <select
                value={form.work_authorization ?? 'other'}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    work_authorization: e.target.value as WorkAuthorization,
                  }))
                }
                className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800"
              >
                {WORK_AUTH_OPTIONS.map((opt) => (
                  <option key={opt} value={opt}>
                    {opt.replace(/_/g, ' ')}
                  </option>
                ))}
              </select>
            </div>
            <label className="flex items-center gap-2 pt-6 text-sm">
              <input
                type="checkbox"
                checked={form.willing_to_relocate ?? false}
                onChange={(e) =>
                  setForm((f) => ({ ...f, willing_to_relocate: e.target.checked }))
                }
              />
              Willing to relocate
            </label>
          </div>

          <div className="flex flex-wrap gap-3 pt-2">
            <button
              type="submit"
              disabled={createMutation.isPending || updateMutation.isPending}
              className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-medium text-white hover:bg-indigo-700 disabled:opacity-50"
            >
              {selectedId ? 'Save changes' : 'Create profile'}
            </button>
            {selectedId && (
              <button
                type="button"
                onClick={() => deleteMutation.mutate(selectedId)}
                className="rounded-lg border border-red-300 px-4 py-2 text-sm text-red-600 hover:bg-red-50 dark:border-red-800 dark:hover:bg-red-950/30"
              >
                Delete
              </button>
            )}
          </div>

          {selectedId && (
            <div className="border-t border-slate-200 pt-4 dark:border-slate-800">
              <h4 className="mb-2 text-sm font-medium">Upload CV (PDF, DOCX, TXT)</h4>
              <input
                type="file"
                accept=".pdf,.docx,.txt"
                onChange={(e) => {
                  const file = e.target.files?.[0]
                  if (file) ingestMutation.mutate({ id: selectedId, file })
                }}
                className="text-sm"
              />
              {uploadMsg && <p className="mt-2 text-sm text-slate-600 dark:text-slate-400">{uploadMsg}</p>}
            </div>
          )}
        </form>
      </div>
    </div>
  )
}

function Field({
  label,
  value,
  onChange,
  type = 'text',
  required,
  className = '',
}: {
  label: string
  value: string
  onChange: (v: string) => void
  type?: string
  required?: boolean
  className?: string
}) {
  return (
    <div className={className}>
      <label className="mb-1 block text-sm font-medium">{label}</label>
      <input
        type={type}
        value={value}
        required={required}
        onChange={(e) => onChange(e.target.value)}
        className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm dark:border-slate-600 dark:bg-slate-800"
      />
    </div>
  )
}
