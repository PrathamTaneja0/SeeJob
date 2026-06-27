import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { useRef, useState } from 'react'
import { api } from '../api/client'
import type { Person, WorkAuthorization } from '../api/types'
import { ErrorState } from '../components/ErrorState'
import { CardSkeleton } from '../components/LoadingSkeleton'
import { Button } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { FormField, INPUT_CLASS, TextAreaField } from '../components/ui/FormField'
import { PageContainer } from '../components/ui/PageContainer'
import { PageHeader } from '../components/ui/PageHeader'

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
  linkedin_url: '',
  github_url: '',
  portfolio_url: '',
  work_authorization: 'other',
  willing_to_relocate: false,
  salary_currency: 'USD',
}

function formatIngestMessage(result: {
  experiences_added: number
  education_added: number
  skills_added: number
  fields_updated: string[]
  chunks_stored: number
}) {
  const parts = [
    `+${result.experiences_added} experience`,
    `+${result.education_added} education`,
    `+${result.skills_added} skills`,
    `${result.chunks_stored} chunks indexed`,
  ]
  let msg = `CV ingested: ${parts.join(', ')}`
  if (result.fields_updated.length > 0) {
    msg += `. Updated fields: ${result.fields_updated.join(', ')}`
  }
  return msg
}

export function ProfileEditor() {
  const queryClient = useQueryClient()
  const cvInputRef = useRef<HTMLInputElement>(null)
  const docInputRef = useRef<HTMLInputElement>(null)
  const [selectedId, setSelectedId] = useState<number | null>(null)
  const [form, setForm] = useState<Partial<Person>>(emptyForm)
  const [uploadMsg, setUploadMsg] = useState<{ text: string; ok: boolean } | null>(null)
  const [docLabel, setDocLabel] = useState('')
  const [cvDragOver, setCvDragOver] = useState(false)
  const [lastCvIngestAt, setLastCvIngestAt] = useState<string | null>(null)

  const { data: profiles, isLoading, error, refetch } = useQuery({
    queryKey: ['profiles'],
    queryFn: api.listProfiles,
  })

  const { data: documents } = useQuery({
    queryKey: ['profileDocuments', selectedId],
    queryFn: () => api.listProfileDocuments(selectedId!),
    enabled: selectedId != null,
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
      setLastCvIngestAt(new Date().toISOString())
      setUploadMsg({ text: formatIngestMessage(result), ok: true })
      queryClient.invalidateQueries({ queryKey: ['profiles'] })
      if (selectedId) {
        api.getProfile(selectedId).then(setForm)
      }
    },
    onError: (err) =>
      setUploadMsg({
        text: err instanceof Error ? err.message : 'CV upload failed',
        ok: false,
      }),
  })

  const uploadDocMutation = useMutation({
    mutationFn: ({ id, file, label }: { id: number; file: File; label?: string }) =>
      api.uploadProfileDocument(id, file, label),
    onSuccess: (result) => {
      setUploadMsg({
        text: `Document "${result.document.label ?? result.document.filename}" uploaded — ${result.chunks_stored} chunks indexed`,
        ok: true,
      })
      setDocLabel('')
      queryClient.invalidateQueries({ queryKey: ['profileDocuments', selectedId] })
    },
    onError: (err) =>
      setUploadMsg({
        text: err instanceof Error ? err.message : 'Document upload failed',
        ok: false,
      }),
  })

  const deleteDocMutation = useMutation({
    mutationFn: ({ personId, docId }: { personId: number; docId: number }) =>
      api.deleteProfileDocument(personId, docId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['profileDocuments', selectedId] })
    },
  })

  const selectProfile = async (id: number) => {
    setSelectedId(id)
    const person = await api.getProfile(id)
    setForm(person)
    setUploadMsg(null)
    setLastCvIngestAt(null)
  }

  const hasMasterCv =
    (form.experiences?.length ?? 0) > 0 ||
    (form.skills?.length ?? 0) > 0 ||
    Boolean(form.summary?.trim())

  const cvIngestDate = lastCvIngestAt ?? (hasMasterCv ? form.updated_at : null)

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (selectedId) {
      updateMutation.mutate({ id: selectedId, data: form })
    } else {
      createMutation.mutate(form)
    }
  }

  const handleCvFile = (file: File | undefined) => {
    if (file && selectedId) ingestMutation.mutate({ id: selectedId, file })
  }

  const handleDocFile = (file: File | undefined) => {
    if (file && selectedId) {
      uploadDocMutation.mutate({ id: selectedId, file, label: docLabel || undefined })
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
    <PageContainer>
      <PageHeader
        title="Profiles"
        subtitle="Manage your candidate profile, upload a master CV, and add supporting documents."
        action={
          <Button
            variant="secondary"
            onClick={() => {
              setSelectedId(null)
              setForm(emptyForm)
              setUploadMsg(null)
            }}
          >
            + New profile
          </Button>
        }
      />

      <div className="grid gap-6 lg:grid-cols-3">
        <Card padding={false}>
          <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4 dark:border-slate-700">
            <h3 className="font-semibold text-slate-900 dark:text-slate-100">Profiles</h3>
          </div>
          <ul className="divide-y divide-slate-100 dark:divide-slate-800">
            {profiles?.length === 0 && (
              <li className="px-6 py-6 text-center text-sm text-slate-400">No profiles yet</li>
            )}
            {profiles?.map((p) => (
              <li key={p.id}>
                <button
                  type="button"
                  onClick={() => selectProfile(p.id)}
                  className={`w-full px-6 py-3 text-left text-sm transition-colors hover:bg-slate-50 dark:hover:bg-slate-800 ${
                    selectedId === p.id ? 'bg-indigo-50 dark:bg-indigo-950/30' : ''
                  }`}
                >
                  <span className="font-medium text-slate-900 dark:text-slate-100">
                    {p.full_name}
                  </span>
                  <span className="block text-xs text-slate-500">{p.email}</span>
                </button>
              </li>
            ))}
          </ul>
        </Card>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <form onSubmit={handleSubmit} className="space-y-4">
              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  label="Full name"
                  value={form.full_name ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, full_name: v }))}
                  required
                />
                <FormField
                  label="Email"
                  type="email"
                  value={form.email ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, email: v }))}
                  required
                />
                <FormField
                  label="Phone"
                  value={form.phone ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, phone: v }))}
                />
                <FormField
                  label="Location"
                  value={form.location ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, location: v }))}
                />
                <FormField
                  label="Headline"
                  value={form.headline ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, headline: v }))}
                  className="sm:col-span-2"
                />
              </div>

              <TextAreaField
                label="Summary"
                value={form.summary ?? ''}
                onChange={(v) => setForm((f) => ({ ...f, summary: v }))}
              />

              <div className="grid gap-4 sm:grid-cols-2">
                <FormField
                  label="LinkedIn URL"
                  type="url"
                  value={form.linkedin_url ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, linkedin_url: v }))}
                  placeholder="https://linkedin.com/in/..."
                />
                <FormField
                  label="GitHub URL"
                  type="url"
                  value={form.github_url ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, github_url: v }))}
                  placeholder="https://github.com/..."
                />
                <FormField
                  label="Portfolio URL"
                  type="url"
                  value={form.portfolio_url ?? ''}
                  onChange={(v) => setForm((f) => ({ ...f, portfolio_url: v }))}
                  placeholder="https://..."
                  className="sm:col-span-2"
                />
              </div>

              <div className="grid gap-4 sm:grid-cols-2">
                <div>
                  <label className="mb-1 block text-sm font-medium text-slate-700 dark:text-slate-300">
                    Work authorization
                  </label>
                  <select
                    value={form.work_authorization ?? 'other'}
                    onChange={(e) =>
                      setForm((f) => ({
                        ...f,
                        work_authorization: e.target.value as WorkAuthorization,
                      }))
                    }
                    className={INPUT_CLASS}
                  >
                    {WORK_AUTH_OPTIONS.map((opt) => (
                      <option key={opt} value={opt}>
                        {opt.replace(/_/g, ' ')}
                      </option>
                    ))}
                  </select>
                </div>
                <label className="flex items-center gap-2 pt-6 text-sm text-slate-700 dark:text-slate-300">
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
                <Button
                  type="submit"
                  disabled={createMutation.isPending || updateMutation.isPending}
                >
                  {selectedId ? 'Save changes' : 'Create profile'}
                </Button>
                {selectedId && (
                  <Button
                    variant="danger"
                    onClick={() => deleteMutation.mutate(selectedId)}
                    disabled={deleteMutation.isPending}
                  >
                    Delete
                  </Button>
                )}
              </div>
            </form>
          </Card>

          {selectedId && (
            <Card>
              <h4 className="mb-4 text-sm font-semibold text-slate-900 dark:text-slate-100">
                Your documents
              </h4>

              <div className="mb-6 rounded-lg border border-slate-200 p-4 dark:border-slate-700">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <div>
                    <p className="text-sm font-medium text-slate-900 dark:text-slate-100">
                      Master CV
                    </p>
                    <p className="text-xs text-slate-500">
                      {hasMasterCv
                        ? cvIngestDate
                          ? `Ingested ${new Date(cvIngestDate).toLocaleString(undefined, {
                              dateStyle: 'medium',
                              timeStyle: 'short',
                            })}`
                          : 'Ingested — profile populated from CV'
                        : 'Not ingested yet — upload your master CV below'}
                    </p>
                  </div>
                  <span
                    className={`rounded px-2 py-0.5 text-xs font-medium ${
                      hasMasterCv
                        ? 'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300'
                        : 'bg-slate-100 text-slate-600 dark:bg-slate-800 dark:text-slate-400'
                    }`}
                  >
                    {hasMasterCv ? 'Ingested' : 'Missing'}
                  </span>
                </div>
              </div>

              <h5 className="mb-3 text-sm font-medium text-slate-700 dark:text-slate-300">
                Upload CV (PDF, DOCX, TXT)
              </h5>
              <input
                ref={cvInputRef}
                type="file"
                accept=".pdf,.docx,.txt"
                className="hidden"
                onChange={(e) => {
                  handleCvFile(e.target.files?.[0])
                  e.target.value = ''
                }}
              />
              <div
                onDragOver={(e) => {
                  e.preventDefault()
                  setCvDragOver(true)
                }}
                onDragLeave={() => setCvDragOver(false)}
                onDrop={(e) => {
                  e.preventDefault()
                  setCvDragOver(false)
                  handleCvFile(e.dataTransfer.files[0])
                }}
                className={`rounded-lg border-2 border-dashed p-6 text-center transition-colors ${
                  cvDragOver
                    ? 'border-indigo-400 bg-indigo-50 dark:border-indigo-500 dark:bg-indigo-950/30'
                    : 'border-slate-300 dark:border-slate-600'
                }`}
              >
                <p className="text-sm text-slate-600 dark:text-slate-400">
                  Drag and drop your master CV here, or
                </p>
                <Button
                  className="mt-3"
                  onClick={() => cvInputRef.current?.click()}
                  disabled={ingestMutation.isPending}
                >
                  {ingestMutation.isPending ? 'Uploading…' : 'Upload CV'}
                </Button>
              </div>

              <div className="mt-8 border-t border-slate-200 pt-6 dark:border-slate-700">
                <h5 className="mb-2 text-sm font-medium text-slate-700 dark:text-slate-300">
                  Supporting documents
                </h5>
                <p className="mb-4 text-sm text-slate-500 dark:text-slate-400">
                  Portfolio writeups, certifications, cover letter templates, or project docs
                  (PDF, DOCX, TXT). Indexed for RAG during document generation.
                </p>
                <div className="mb-4 grid gap-4 sm:grid-cols-2">
                  <FormField
                    label="Label (optional)"
                    value={docLabel}
                    onChange={setDocLabel}
                    placeholder="e.g. AWS certification"
                  />
                  <div className="flex items-end">
                    <input
                      ref={docInputRef}
                      type="file"
                      accept=".pdf,.docx,.txt"
                      className="hidden"
                      onChange={(e) => {
                        handleDocFile(e.target.files?.[0])
                        e.target.value = ''
                      }}
                    />
                    <Button
                      variant="secondary"
                      className="w-full sm:w-auto"
                      onClick={() => docInputRef.current?.click()}
                      disabled={uploadDocMutation.isPending}
                    >
                      {uploadDocMutation.isPending ? 'Uploading…' : 'Upload document'}
                    </Button>
                  </div>
                </div>

                {documents && documents.length > 0 ? (
                  <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200 dark:divide-slate-800 dark:border-slate-700">
                    {documents.map((doc) => (
                      <li
                        key={doc.id}
                        className="flex items-center justify-between gap-3 px-4 py-3"
                      >
                        <div className="min-w-0">
                          <p className="truncate text-sm font-medium text-slate-900 dark:text-slate-100">
                            {doc.label ?? doc.filename}
                          </p>
                          <p className="truncate text-xs text-slate-500">
                            {doc.filename}
                            {' · '}
                            {new Date(doc.uploaded_at).toLocaleDateString(undefined, {
                              month: 'short',
                              day: 'numeric',
                              year: 'numeric',
                            })}
                          </p>
                        </div>
                        <Button
                          variant="danger"
                          size="sm"
                          onClick={() =>
                            deleteDocMutation.mutate({ personId: selectedId, docId: doc.id })
                          }
                          disabled={deleteDocMutation.isPending}
                        >
                          Delete
                        </Button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="text-sm text-slate-400">No supporting documents yet.</p>
                )}
              </div>
            </Card>
          )}

          {uploadMsg && (
            <div
              className={`rounded-lg border p-4 text-sm ${
                uploadMsg.ok
                  ? 'border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-900/50 dark:bg-emerald-950/30 dark:text-emerald-300'
                  : 'border-red-200 bg-red-50 text-red-800 dark:border-red-900/50 dark:bg-red-950/30 dark:text-red-300'
              }`}
            >
              {uploadMsg.text}
            </div>
          )}
        </div>
      </div>
    </PageContainer>
  )
}
