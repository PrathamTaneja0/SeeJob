export type ApplicationStatus =
  | 'discovered'
  | 'scored'
  | 'pending_approval'
  | 'generating_docs'
  | 'docs_ready'
  | 'auth_required'
  | 'filling'
  | 'submitted'
  | 'failed'
  | 'needs_manual'

export type JobStatus = 'new' | 'reviewed' | 'archived' | 'applied' | 'rejected'

export type DocumentType = 'cv' | 'cover_letter' | 'other'

export interface GeneratedDocument {
  id: number
  doc_type: DocumentType
  markdown_content: string
  pdf_path: string | null
  ats_score: number | null
  critic_report: string | null
  version: number
  approved: boolean
  created_at: string
}

export interface ApplicationJobSummary {
  id: number
  title: string
  company: string
  url: string
  fit_score: number | null
}

export interface Application {
  id: number
  person_id: number
  job_id: number
  status: ApplicationStatus
  status_message: string | null
  interrupt_metadata_json: string | null
  platform: string | null
  submitted_at: string | null
  created_at: string
  updated_at: string
  documents: GeneratedDocument[]
  job: ApplicationJobSummary | null
}

export interface ApplicationPipelineView {
  status: ApplicationStatus
  count: number
  applications: Application[]
}

export interface Job {
  id: number
  url: string
  title: string
  company: string
  location: string | null
  is_remote: boolean
  jd_text: string | null
  source: string
  fit_score: number | null
  match_rationale: string | null
  status: JobStatus
  created_at: string
  updated_at: string
}

export interface JobQueueBucket {
  bucket: string
  count: number
  jobs: Job[]
}

export interface JobQueueView {
  to_review: JobQueueBucket
  approved: JobQueueBucket
  skipped: JobQueueBucket
  applied: JobQueueBucket
}

export interface RateLimits {
  default: number
  linkedin?: number | null
  greenhouse?: number | null
  lever?: number | null
  workday?: number | null
  icims?: number | null
}

export interface JobFilters {
  min_fit_score?: number | null
  remote_only: boolean
  locations: string[]
  titles_include: string[]
  titles_exclude: string[]
  must_have_skills: string[]
  seniority_exclude: string[]
}

export interface PolicyConfig {
  id: number
  auto_apply: boolean
  require_doc_approval: boolean
  require_submit_approval: boolean
  min_fit_score: number
  ats_min_score: number
  daily_apply_limit: number
  rate_limits: RateLimits
  job_filters: JobFilters | null
  blocked_companies: string[]
  blocked_keywords: string[]
  sourcing_enabled: boolean
  sourcing_schedule: string
  sourcing_interval_minutes: number
  rss_feeds: string[]
  created_at: string
  updated_at: string
}

export interface Experience {
  id: number
  company: string
  title: string
  location: string | null
  start_date: string
  end_date: string | null
  is_current: boolean
  description: string | null
  created_at: string
  updated_at: string
}

export interface Education {
  id: number
  institution: string
  degree: string | null
  field_of_study: string | null
  start_date: string | null
  end_date: string | null
  gpa: string | null
  created_at: string
  updated_at: string
}

export interface Skill {
  id: number
  name: string
  level: string | null
  years: number | null
  created_at: string
  updated_at: string
}

export type WorkAuthorization =
  | 'citizen'
  | 'permanent_resident'
  | 'work_visa'
  | 'student_visa'
  | 'requires_sponsorship'
  | 'other'

export interface Person {
  id: number
  full_name: string
  email: string
  phone: string | null
  location: string | null
  headline: string | null
  summary: string | null
  linkedin_url: string | null
  github_url: string | null
  portfolio_url: string | null
  work_authorization: WorkAuthorization
  willing_to_relocate: boolean
  remote_preference: string | null
  desired_roles: string | null
  salary_min: number | null
  salary_currency: string
  created_at: string
  updated_at: string
  experiences: Experience[]
  education: Education[]
  skills: Skill[]
}

export interface AgentEvent {
  id: number
  event_type: string
  message: string
  application_id: number | null
  worker_name: string | null
  metadata: Record<string, unknown>
  timestamp: string
}

export interface ApplicationApplyResponse {
  application_id: number
  status: ApplicationStatus
  result: string
  fields_filled: number
  message: string | null
  screenshot_path: string | null
  page_url: string | null
  dry_run: boolean
  submitted: boolean
}

export interface ApplicationDocumentsView {
  application_id: number
  status: ApplicationStatus
  documents: GeneratedDocument[]
}

export interface IngestionResult {
  person_id: number
  raw_text_length: number
  chunks_stored: number
  experiences_added: number
  education_added: number
  skills_added: number
  fields_updated: string[]
  project_chunks: number
  behavioral_chunks: number
}
