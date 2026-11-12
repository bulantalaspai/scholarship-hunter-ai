import type {
  EligibilityResult,
  EligibilityStatus,
  MatchResult,
  RankedProgramme,
  RequirementResult,
  Scholarship,
  ScholarshipFilters,
  ScholarshipPage,
  StudentProfile,
} from './types'

export type HealthResponse = {
  status: 'ok'
  service: 'scholarship-hunter-ai'
}

export async function getHealth(signal: AbortSignal): Promise<HealthResponse> {
  const response = await fetch('/api/health', {
    headers: { Accept: 'application/json' },
    signal: AbortSignal.any([signal, AbortSignal.timeout(5000)]),
  })

  if (!response.ok) {
    throw new Error(`Health check failed: HTTP ${response.status}`)
  }

  const data: unknown = await response.json()
  if (
    typeof data !== 'object' ||
    data === null ||
    !('status' in data) ||
    data.status !== 'ok' ||
    !('service' in data) ||
    data.service !== 'scholarship-hunter-ai'
  ) {
    throw new Error('Unexpected health response')
  }

  return { status: data.status, service: data.service }
}

type JsonObject = Record<string, unknown>
type Validator<T> = (value: unknown) => value is T

const object = (value: unknown): value is JsonObject =>
  typeof value === 'object' && value !== null && !Array.isArray(value)
const text = (value: unknown): value is string => typeof value === 'string'
const texts = (value: unknown): value is string[] =>
  Array.isArray(value) && value.every(text)
const finite = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value)
const nonnegative = (value: unknown): value is number =>
  finite(value) && value >= 0
const integer = (value: unknown): value is number =>
  nonnegative(value) && Number.isSafeInteger(value)
const positiveInteger = (value: unknown): value is number =>
  integer(value) && value > 0
const nullable = <T>(
  value: unknown,
  validate: Validator<T>,
): value is T | null => value === null || validate(value)
const status = (value: unknown): value is EligibilityStatus =>
  value === 'eligible' ||
  value === 'ineligible' ||
  value === 'needs_verification'

function isoDate(value: unknown): value is string {
  if (!text(value) || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return false
  const parsed = new Date(`${value}T00:00:00Z`)
  return (
    !Number.isNaN(parsed.getTime()) &&
    parsed.toISOString().slice(0, 10) === value
  )
}

function officialUrl(value: unknown): value is string {
  if (!text(value)) return false
  try {
    const url = new URL(value)
    return url.protocol === 'https:' && !url.username && !url.password
  } catch {
    return false
  }
}

function scholarship(value: unknown): value is Scholarship {
  if (!object(value)) return false
  return (
    positiveInteger(value.id) &&
    text(value.scholarship_name) &&
    text(value.university_or_provider) &&
    nullable(value.destination_country, texts) &&
    nullable(value.degree_level, text) &&
    nullable(value.eligible_study_fields, texts) &&
    nullable(value.eligible_nationalities, texts) &&
    nullable(value.minimum_gpa, nonnegative) &&
    nullable(value.gpa_scale, nonnegative) &&
    nullable(
      value.minimum_ielts,
      (score): score is number => finite(score) && score >= 0 && score <= 9,
    ) &&
    text(value.funding_type) &&
    ['fully_funded', 'partially_funded', 'unknown'].includes(
      value.funding_type,
    ) &&
    nullable(value.tuition_coverage, text) &&
    nullable(value.living_stipend, text) &&
    nullable(value.application_deadline, isoDate) &&
    nullable(value.application_cycle, text) &&
    officialUrl(value.official_source_url) &&
    isoDate(value.last_verified_at) &&
    nullable(value.additional_requirements, text) &&
    nullable(value.notes, text)
  )
}

function pagination(value: JsonObject) {
  return (
    integer(value.total) &&
    positiveInteger(value.page) &&
    positiveInteger(value.page_size) &&
    value.page_size <= 100 &&
    value.page <= 1_000_000
  )
}

function scholarshipPage(value: unknown): value is ScholarshipPage {
  return (
    object(value) &&
    pagination(value) &&
    Array.isArray(value.items) &&
    value.items.every(scholarship) &&
    value.items.length <= Number(value.page_size) &&
    value.items.length <= Number(value.total)
  )
}

function requirement(value: unknown): value is RequirementResult {
  return (
    object(value) &&
    text(value.requirement) &&
    text(value.explanation) &&
    text(value.scope) &&
    ['admission', 'funding', 'application'].includes(value.scope) &&
    text(value.status) &&
    ['met', 'failed', 'unknown'].includes(value.status) &&
    nullable(value.suggestion, text)
  )
}

function expectedStatus(requirements: RequirementResult[]): EligibilityStatus {
  if (requirements.some((item) => item.status === 'failed')) return 'ineligible'
  if (
    !requirements.length ||
    requirements.some((item) => item.status === 'unknown')
  )
    return 'needs_verification'
  return 'eligible'
}

function eligibility(value: unknown): value is EligibilityResult {
  if (
    !object(value) ||
    !positiveInteger(value.scholarship_id) ||
    !text(value.scholarship_name) ||
    !status(value.status) ||
    !status(value.admission_status) ||
    !status(value.funding_status) ||
    !status(value.application_status) ||
    !Array.isArray(value.requirements) ||
    !value.requirements.every(requirement) ||
    !texts(value.matched_requirements) ||
    !texts(value.failed_requirements) ||
    !texts(value.unknown_requirements) ||
    !texts(value.suggestions) ||
    !text(value.explanation) ||
    !officialUrl(value.official_source_url) ||
    !isoDate(value.last_verified_at) ||
    !Array.isArray(value.rule_source_urls) ||
    !value.rule_source_urls.every(officialUrl) ||
    !nullable(value.rules_verified_at, isoDate) ||
    !isoDate(value.evaluated_on) ||
    !text(value.disclaimer)
  )
    return false

  // A structurally valid payload must still never turn unknown checks positive.
  if (value.status !== expectedStatus(value.requirements)) return false
  for (const scope of ['admission', 'funding', 'application'] as const) {
    if (
      value[`${scope}_status`] !==
      expectedStatus(value.requirements.filter((item) => item.scope === scope))
    )
      return false
  }
  for (const [state, key] of [
    ['met', 'matched_requirements'],
    ['failed', 'failed_requirements'],
    ['unknown', 'unknown_requirements'],
  ] as const) {
    const expected = value.requirements
      .filter((item) => item.status === state)
      .map((item) => item.requirement)
    const names = value[key]
    if (
      !texts(names) ||
      expected.length !== names.length ||
      expected.some((name, index) => name !== names[index])
    )
      return false
  }
  return true
}

function ranked(value: unknown): value is RankedProgramme {
  return (
    object(value) &&
    eligibility(value.assessment) &&
    texts(value.ranking_reasons)
  )
}

export { ranked as isRankedProgramme }

function matches(value: unknown): value is MatchResult {
  if (!object(value) || !pagination(value) || !object(value.counts))
    return false
  let returned = 0
  let total = 0
  for (const group of [
    'eligible',
    'needs_verification',
    'ineligible',
  ] as const) {
    const items = value[group]
    const count = value.counts[group]
    if (
      !Array.isArray(items) ||
      !items.every(ranked) ||
      !integer(count) ||
      items.length > count ||
      items.some((item) => item.assessment.status !== group)
    )
      return false
    returned += items.length
    total += count
  }
  return total === value.total && returned <= Number(value.page_size)
}

function validationMessage(body: unknown): string {
  if (!object(body) || !Array.isArray(body.detail))
    return 'Check the submitted values and try again.'
  const fields = body.detail.flatMap((item) => {
    if (!object(item) || !Array.isArray(item.loc)) return []
    const path = item.loc.filter(
      (part) => typeof part === 'string' && part !== 'body' && part !== 'query',
    )
    return path.length ? [path.join('.')] : []
  })
  return fields.length
    ? `Check the submitted values for ${[...new Set(fields)].join(', ')}.`
    : 'Check the submitted values and try again.'
}

export async function request<T>(
  url: string,
  signal: AbortSignal,
  validate: Validator<T>,
  body?: unknown,
  timeoutMs = 15_000,
): Promise<T> {
  let response: Response
  try {
    response = await fetch(url, {
      method: body === undefined ? 'GET' : 'POST',
      headers: {
        Accept: 'application/json',
        ...(body === undefined ? {} : { 'Content-Type': 'application/json' }),
      },
      signal: AbortSignal.any([signal, AbortSignal.timeout(timeoutMs)]),
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    })
  } catch (error) {
    if (signal.aborted) throw error
    if (error instanceof DOMException && error.name === 'TimeoutError') {
      throw new Error('The API request timed out. Try again.', { cause: error })
    }
    throw new Error(
      'Cannot reach the API. Make sure the local backend is running and try again.',
      { cause: error },
    )
  }
  if (!response.ok) {
    if (response.status === 404)
      throw new Error(
        'Scholarship not found. It may have been removed from the catalogue.',
      )
    if (response.status === 422) {
      const errorBody: unknown = await response.json().catch(() => null)
      throw new Error(validationMessage(errorBody))
    }
    if (response.status >= 500)
      throw new Error(
        `The API is temporarily unavailable (HTTP ${response.status}). Try again.`,
      )
    throw new Error(`The API rejected this request (HTTP ${response.status}).`)
  }
  let data: unknown
  try {
    data = await response.json()
  } catch {
    throw new Error('The API returned an unreadable response. Try again.')
  }
  if (!validate(data))
    throw new Error(
      'The API returned an unexpected response. No eligibility conclusion can be drawn.',
    )
  return data
}

export function listScholarships(
  filters: ScholarshipFilters,
  signal: AbortSignal,
): Promise<ScholarshipPage> {
  const query = new URLSearchParams()
  for (const key of [
    'country',
    'field',
    'funding_type',
    'page',
    'page_size',
  ] as const) {
    const value = filters[key]
    if (value !== undefined && String(value).trim())
      query.set(key, String(value).trim())
  }
  return request(
    `/api/scholarships${query.size ? `?${query}` : ''}`,
    signal,
    (value): value is ScholarshipPage =>
      scholarshipPage(value) &&
      value.page === (filters.page ?? 1) &&
      value.page_size === (filters.page_size ?? 20),
  )
}

export function getScholarship(
  id: number,
  signal: AbortSignal,
): Promise<Scholarship> {
  return request(
    `/api/scholarships/${id}`,
    signal,
    (value): value is Scholarship => scholarship(value) && value.id === id,
  )
}

export function checkEligibility(
  id: number,
  profile: StudentProfile,
  signal: AbortSignal,
): Promise<EligibilityResult> {
  return request(
    '/api/eligibility/check',
    signal,
    (value): value is EligibilityResult =>
      eligibility(value) && value.scholarship_id === id,
    { scholarship_id: id, profile },
  )
}

export function getMatches(
  profile: StudentProfile,
  page: number,
  signal: AbortSignal,
): Promise<MatchResult> {
  return request(
    '/api/eligibility/matches',
    signal,
    (value): value is MatchResult =>
      matches(value) && value.page === page && value.page_size === 10,
    {
      profile,
      page,
      page_size: 10,
    },
  )
}
