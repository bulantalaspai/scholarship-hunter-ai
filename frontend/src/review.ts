export type ReviewState = 'pending_review' | 'needs_more_evidence' | 'approved' | 'rejected'
export type FieldDecision = 'accepted' | 'rejected' | 'unresolved'
export type ReviewedValue = string | number | string[]

export interface ReviewSummary {
  draft_id: string
  state: ReviewState
  source_kind: string
  published_id: number | null
  scholarship_name: string | null
  university_or_provider: string | null
  official_source_url: string
  candidate_label?: string
}

export interface FieldAudit {
  field: string
  decision: FieldDecision
  value: ReviewedValue | null
  evidence: string[]
  reviewer: string
  rationale: string
  decided_at: string
}

export interface FundingObservation {
  amount: string | number
  currency: string | null
  period: string | null
  payment_scope: string | null
  qualifier: string
  quote: string
  source_url: string
  publication_year: number | null
  cycle: string | null
  retrieved_on: string | null
}

export interface ReviewDetail extends ReviewSummary {
  source_text: string
  created_at: string
  draft: {
    official_source_url: string
    retrieved_on: string
    fields: Record<string, { quote: string; scope: string } | null>
    funding_observations?: FundingObservation[]
    ambiguous_fields?: string[]
    unsupported_fields?: string[]
  }
  expired_deadline: boolean | null
  duplicate_candidates: { name: string; cycle: string | null; funding_type: string }[]
  conflicts: { field: string; catalogue: unknown; excerpt: string }[]
  wording_checks: { field: string; catalogue: unknown; excerpt: string }[]
  missing_fields: string[]
  related_draft_ids: string[]
  field_reviews: Record<string, FieldAudit>
  field_history: FieldAudit[]
  blocked_fields: string[]
  dashboard_approved: boolean
  supplemental_funding?: FundingObservation[]
  supplemental_funding_missing?: boolean
  funding_conflicts?: { status: string; left: FundingObservation; right: FundingObservation }[]
  history: {
    action: string
    reviewer: string
    rationale: string
    decided_at: string
    approved_record?: Record<string, ReviewedValue | null> | null
  }[]
}

export class ReviewRequestError extends Error {
  readonly status: number

  constructor(status: number, message: string) {
    super(message)
    this.status = status
  }
}

function object(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

function summary(value: unknown): value is ReviewSummary {
  return object(value) &&
    typeof value.draft_id === 'string' && /^[a-f0-9]{64}$/.test(value.draft_id) &&
    ['pending_review', 'needs_more_evidence', 'approved', 'rejected'].includes(String(value.state)) &&
    typeof value.source_kind === 'string' &&
    (value.published_id === null || typeof value.published_id === 'number') &&
    typeof value.official_source_url === 'string' &&
    (value.scholarship_name === null || typeof value.scholarship_name === 'string') &&
    (value.university_or_provider === null || typeof value.university_or_provider === 'string')
}

function detail(value: unknown): value is ReviewDetail {
  if (!summary(value)) return false
  const data = value as unknown as Record<string, unknown>
  return typeof data.source_text === 'string' &&
    typeof data.created_at === 'string' &&
    object(data.draft) &&
    typeof data.draft.official_source_url === 'string' &&
    typeof data.draft.retrieved_on === 'string' &&
    object(data.draft.fields) &&
    object(data.field_reviews) &&
    typeof data.dashboard_approved === 'boolean' &&
    ['history', 'field_history', 'blocked_fields', 'duplicate_candidates', 'missing_fields', 'conflicts', 'wording_checks', 'related_draft_ids']
      .every((key) => Array.isArray(data[key]))
}

const queueUrl = '/api/review/drafts'

async function reviewRequest<T>(
  path: string,
  key: string,
  signal: AbortSignal,
  validate: (data: unknown) => data is T,
  body?: unknown,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(path, {
      method: body === undefined ? 'GET' : 'POST',
      credentials: 'omit',
      cache: 'no-store',
      redirect: 'error',
      referrerPolicy: 'no-referrer',
      headers: {
        Authorization: 'Bearer ' + key,
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
      signal: AbortSignal.any([signal, AbortSignal.timeout(15_000)]),
    })
  } catch (error) {
    if (signal.aborted) throw error
    throw new ReviewRequestError(0, 'Could not reach the local review service. Check the backend and try again.')
  }
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    let message = 'The local review service could not complete the request.'
    if (response.status === 401) message = 'The local access key was rejected.'
    if (response.status === 403) message = 'Open the dashboard from the configured local address.'
    if (response.status === 404 && path === queueUrl) message = 'Local review is disabled. Start the backend with the review settings first.'
    if (response.status === 422) message = 'Check the submitted values and required fields.'
    if (response.status === 409 && object(data) && typeof data.detail === 'string') message = data.detail
    throw new ReviewRequestError(response.status, message)
  }
  if (!validate(data)) throw new ReviewRequestError(0, 'The review service returned an unexpected response.')
  return data
}

export function loadReviewQueue(key: string, signal: AbortSignal) {
  return reviewRequest(queueUrl, key, signal, (data): data is ReviewSummary[] =>
    Array.isArray(data) && data.every(summary),
  )
}

export function loadReviewDraft(id: string, key: string, signal: AbortSignal) {
  return reviewRequest(queueUrl + '/' + id, key, signal, detail)
}

export function submitReview(
  id: string,
  action: string,
  body: unknown,
  key: string,
  signal: AbortSignal,
) {
  return reviewRequest(queueUrl + '/' + id + '/' + action, key, signal, detail, body)
}

export type FieldKind = 'text' | 'list' | 'number' | 'date' | 'degree' | 'funding'

export interface FieldDefinition {
  key: string
  label: string
  kind: FieldKind
  required?: boolean
  evidenceOnly?: boolean
  hint?: string
}

export const groups: { label: string; fields: FieldDefinition[] }[] = [
  {
    label: 'Programme',
    fields: [
      { key: 'scholarship_name', label: 'Programme name', kind: 'text', required: true },
      { key: 'university_or_provider', label: 'Provider', kind: 'text', required: true },
      { key: 'destination_country', label: 'Study destinations', kind: 'list', required: true },
      { key: 'degree_level', label: 'Degree level', kind: 'degree', required: true },
      { key: 'eligible_study_fields', label: 'Study fields', kind: 'list' },
    ],
  },
  {
    label: 'Funding & dates',
    fields: [
      { key: 'funding_type', label: 'Funding type', kind: 'funding' },
      { key: 'funding_amount', label: 'Extracted funding amount', kind: 'text', evidenceOnly: true },
      { key: 'tuition_coverage', label: 'Tuition coverage', kind: 'text', hint: 'Keep the exact wording, including any exclusions or conditions.' },
      { key: 'living_stipend', label: 'Living stipend', kind: 'text', hint: 'Use the exact wording for the amount, currency, payment period and any conditions.' },
      { key: 'application_cycle', label: 'Intake cycle', kind: 'text' },
      { key: 'application_deadline', label: 'Application deadline', kind: 'date' },
    ],
  },
  {
    label: 'Eligibility',
    fields: [
      { key: 'eligible_nationalities', label: 'Eligible nationalities', kind: 'list' },
      { key: 'gpa_requirement', label: 'Extracted GPA requirement', kind: 'text', evidenceOnly: true },
      { key: 'minimum_gpa', label: 'Minimum GPA', kind: 'number' },
      { key: 'gpa_scale', label: 'GPA scale', kind: 'number' },
      { key: 'language_requirement', label: 'Extracted language requirement', kind: 'text', evidenceOnly: true },
      { key: 'minimum_ielts', label: 'Minimum IELTS', kind: 'number' },
      { key: 'prior_degree_requirement', label: 'Extracted prior degree requirement', kind: 'text', evidenceOnly: true },
      { key: 'additional_requirements', label: 'Additional requirements', kind: 'text', hint: 'Use the exact wording, including conditions and alternatives.' },
      { key: 'notes', label: 'Catalogue notes', kind: 'text', hint: 'Keep the exact source wording.' },
    ],
  },
]

export const requiredFields = groups.flatMap(
  (group) => group.fields.filter((field) => field.required),
)

export const decisionLabels: Record<FieldDecision, string> = {
  accepted: 'Accepted',
  rejected: 'Rejected',
  unresolved: 'Unresolved',
}

export function fieldLabel(key: string) {
  return groups.flatMap((group) => group.fields)
    .find((field) => field.key === key)?.label ?? key.replaceAll('_', ' ')
}

export function valueLabel(value: ReviewedValue | null) {
  return Array.isArray(value) ? value.join(', ') : value ?? ''
}

export function auditDate(value: string) {
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? 'Date unavailable' : new Intl.DateTimeFormat('en-GB', {
    dateStyle: 'medium', timeStyle: 'short', timeZone: 'UTC',
  }).format(date) + ' UTC'
}
