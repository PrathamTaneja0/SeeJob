import type {
  Application,
  ApplicationApplyResponse,
  ApplicationDocumentsView,
  ApplicationPipelineView,
  ApplicationStatus,
  IngestionResult,
  Job,
  JobQueueView,
  Person,
  PolicyConfig,
  ProfileDocument,
  ProfileDocumentUploadResult,
  RateLimits,
} from './types'

const API_BASE =
  import.meta.env.VITE_API_URL?.replace(/\/$/, '') ||
  (import.meta.env.DEV ? '' : 'http://127.0.0.1:8000')

class ApiError extends Error {
  status: number

  constructor(message: string, status: number) {
    super(message)
    this.name = 'ApiError'
    this.status = status
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: {
      ...(init?.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...init?.headers,
    },
  })

  if (!res.ok) {
    let detail = res.statusText
    try {
      const body = await res.json()
      detail = body.detail ?? JSON.stringify(body)
    } catch {
      /* ignore */
    }
    throw new ApiError(String(detail), res.status)
  }

  if (res.status === 204) {
    return undefined as T
  }

  return res.json() as Promise<T>
}

export const api = {
  health: () => request<{ status: string }>('/health'),

  getPipeline: () =>
    request<ApplicationPipelineView[]>('/api/v1/applications/pipeline'),

  listApplications: (status?: ApplicationStatus) => {
    const q = status ? `?status=${status}` : ''
    return request<Application[]>(`/api/v1/applications${q}`)
  },

  getApplication: (id: number) =>
    request<Application>(`/api/v1/applications/${id}`),

  getApplicationDocuments: (id: number) =>
    request<ApplicationDocumentsView>(`/api/v1/applications/${id}/documents`),

  approveDocument: (applicationId: number, docId: number, approved: boolean) =>
    request(`/api/v1/applications/${applicationId}/documents/${docId}/approve`, {
      method: 'PATCH',
      body: JSON.stringify({ approved }),
    }),

  documentDownloadUrl: (applicationId: number, docId: number) =>
    `${API_BASE}/api/v1/applications/${applicationId}/documents/${docId}/download`,

  applyApplication: (
    id: number,
    dryRun: boolean,
    submitApproved = false,
  ) => {
    const params = new URLSearchParams({
      dry_run: String(dryRun),
      submit_approved: String(submitApproved),
    })
    return request<ApplicationApplyResponse>(
      `/api/v1/applications/${id}/apply?${params}`,
      { method: 'POST' },
    )
  },

  resumeApplication: (id: number, note?: string) =>
    request<Application>(`/api/v1/applications/${id}/resume`, {
      method: 'POST',
      body: JSON.stringify(note ? { note } : {}),
    }),

  getJobQueue: () => request<JobQueueView>('/api/v1/jobs/queue'),

  getJob: (id: number) => request<Job>(`/api/v1/jobs/${id}`),

  updateJobStatus: (
    jobId: number,
    action: 'approve' | 'skip',
    personId?: number,
  ) =>
    request<Job>(`/api/v1/jobs/${jobId}/status`, {
      method: 'PATCH',
      body: JSON.stringify({ action, person_id: personId ?? null }),
    }),

  getPolicy: () => request<PolicyConfig>('/api/v1/policy'),

  updatePolicy: (data: Partial<PolicyConfig> & { rate_limits?: RateLimits }) =>
    request<PolicyConfig>('/api/v1/policy', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  listProfiles: () => request<Person[]>('/api/v1/profiles'),

  getProfile: (id: number) => request<Person>(`/api/v1/profiles/${id}`),

  createProfile: (data: Partial<Person>) =>
    request<Person>('/api/v1/profiles', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateProfile: (id: number, data: Partial<Person>) =>
    request<Person>(`/api/v1/profiles/${id}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteProfile: (id: number) =>
    request<void>(`/api/v1/profiles/${id}`, { method: 'DELETE' }),

  ingestCv: (personId: number, file: File) => {
    const form = new FormData()
    form.append('file', file)
    return request<IngestionResult>(`/api/v1/profiles/${personId}/ingest`, {
      method: 'POST',
      body: form,
    })
  },

  listProfileDocuments: (personId: number) =>
    request<ProfileDocument[]>(`/api/v1/profiles/${personId}/documents`),

  uploadProfileDocument: (personId: number, file: File, label?: string) => {
    const form = new FormData()
    form.append('file', file)
    if (label) form.append('label', label)
    return request<ProfileDocumentUploadResult>(`/api/v1/profiles/${personId}/documents`, {
      method: 'POST',
      body: form,
    })
  },

  deleteProfileDocument: (personId: number, documentId: number) =>
    request<void>(`/api/v1/profiles/${personId}/documents/${documentId}`, {
      method: 'DELETE',
    }),

  getEvents: (afterId = 0, limit = 100) =>
    request<import('./types').AgentEvent[]>(
      `/api/v1/events?after_id=${afterId}&limit=${limit}`,
    ),
}

export { ApiError, API_BASE }
