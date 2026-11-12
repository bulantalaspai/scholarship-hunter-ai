import { describe, expect, it, vi } from 'vitest'
import {
  checkEligibility,
  getMatches,
  getScholarship,
  listScholarships,
} from './api'
import type {
  EligibilityResult,
  MatchResult,
  Scholarship,
  ScholarshipPage,
  StudentProfile,
} from './types'

const profile: StudentProfile = {
  nationality: 'Kazakhstan',
  degree_level: 'bachelor',
  degree_completed: true,
  field_of_study: 'Computer Science',
  gpa: 3.5,
  gpa_scale: 4.0,
  ielts_overall: null,
  intended_start_year: 2027,
  funding_preference: 'fully_funded',
}

const record: Scholarship = {
  id: 7,
  scholarship_name: 'Fictional Test Award',
  university_or_provider: 'Fictional Test University',
  destination_country: ['Germany', 'Finland'],
  degree_level: 'master',
  eligible_study_fields: ['Computer Science'],
  eligible_nationalities: null,
  minimum_gpa: null,
  gpa_scale: null,
  minimum_ielts: null,
  funding_type: 'unknown',
  tuition_coverage: null,
  living_stipend: null,
  application_deadline: null,
  application_cycle: null,
  official_source_url: 'https://example.org/fictional-award',
  last_verified_at: '2026-11-11',
  additional_requirements: null,
  notes: 'Fictional fixture only; not a real scholarship.',
}

const assessment: EligibilityResult = {
  scholarship_id: 7,
  scholarship_name: record.scholarship_name,
  status: 'needs_verification',
  admission_status: 'needs_verification',
  funding_status: 'needs_verification',
  application_status: 'needs_verification',
  requirements: [
    {
      requirement: 'language',
      scope: 'admission',
      status: 'unknown',
      explanation: 'Accepted language evidence is unverified.',
      suggestion: 'Check the official requirements.',
    },
    {
      requirement: 'funding_availability',
      scope: 'funding',
      status: 'unknown',
      explanation: 'Funding availability is unverified.',
      suggestion: null,
    },
    {
      requirement: 'deadline',
      scope: 'application',
      status: 'unknown',
      explanation: 'Deadline is unknown.',
      suggestion: null,
    },
  ],
  matched_requirements: [],
  failed_requirements: [],
  unknown_requirements: ['language', 'funding_availability', 'deadline'],
  suggestions: ['Check the official requirements.'],
  explanation: 'Mandatory conditions remain unverified.',
  official_source_url: record.official_source_url,
  last_verified_at: '2026-11-11',
  rule_source_urls: [],
  rules_verified_at: null,
  evaluated_on: '2026-11-12',
  disclaimer: 'This assessment does not guarantee admission or funding.',
}

function mockResponse(body: unknown, status = 200) {
  const fetchMock = vi.fn().mockResolvedValue(Response.json(body, { status }))
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

const signal = () => new AbortController().signal

describe('catalogue API', () => {
  it('rejects a detail response for a different scholarship', async () => {
    mockResponse({ ...record, id: 8 })
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'unexpected response',
    )
  })
  it('sends only supported encoded filters and retains nullable requirements', async () => {
    const page: ScholarshipPage = {
      items: [record],
      total: 1,
      page: 1,
      page_size: 10,
    }
    const fetchMock = mockResponse(page)
    const result = await listScholarships(
      {
        country: ' Germany ',
        field: 'Computer Science',
        funding_type: 'unknown',
        page: 1,
        page_size: 10,
      },
      signal(),
    )
    expect(result).toEqual(page)
    expect(result.items[0].minimum_gpa).toBeNull()
    const url = new URL(fetchMock.mock.calls[0][0], 'http://localhost')
    expect(url.pathname).toBe('/api/scholarships')
    expect(Object.fromEntries(url.searchParams)).toEqual({
      country: 'Germany',
      field: 'Computer Science',
      funding_type: 'unknown',
      page: '1',
      page_size: '10',
    })
  })

  it('supports empty pages without inventing records', async () => {
    mockResponse({ items: [], total: 0, page: 1, page_size: 20 })
    expect((await listScholarships({}, signal())).items).toEqual([])
  })

  it('loads the individual record contract', async () => {
    const fetchMock = mockResponse(record)
    await expect(getScholarship(7, signal())).resolves.toEqual(record)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/scholarships/7')
  })

  it.each([
    { ...record, destination_country: 'Germany' },
    { ...record, official_source_url: 'javascript:alert(1)' },
    { ...record, official_source_url: 'https://name:secret@example.org' },
    { ...record, last_verified_at: '2026-02-30' },
    { ...record, funding_type: 'guaranteed' },
    { ...record, funding_type: ['unknown'] },
    { ...record, id: Number.MAX_SAFE_INTEGER + 1 },
    { scholarship_name: 'Incomplete data' },
  ])('rejects malformed or unsafe scholarship data', async (body) => {
    mockResponse(body)
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'unexpected response',
    )
  })

  it('shows a clear missing-record error', async () => {
    mockResponse({ detail: 'Scholarship not found' }, 404)
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'Scholarship not found',
    )
  })

  it('rejects impossible pagination metadata', async () => {
    mockResponse({ items: [record], total: 0, page: 1, page_size: 10 })
    await expect(listScholarships({}, signal())).rejects.toThrow(
      'unexpected response',
    )
  })
})

describe('eligibility API', () => {
  it('rejects an assessment for a different scholarship', async () => {
    mockResponse({ ...assessment, scholarship_id: 8 })
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'unexpected response',
    )
  })
  it('posts the exact profile/check contract without changing unknown results', async () => {
    const fetchMock = mockResponse(assessment)
    await expect(checkEligibility(7, profile, signal())).resolves.toEqual(
      assessment,
    )
    expect(fetchMock.mock.calls[0][0]).toBe('/api/eligibility/check')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      scholarship_id: 7,
      profile,
    })
  })

  it('loads correctly grouped matching results and supplies pagination', async () => {
    const body: MatchResult = {
      eligible: [],
      ineligible: [],
      needs_verification: [
        { assessment, ranking_reasons: ['Conditions need verification.'] },
      ],
      counts: { eligible: 0, needs_verification: 1, ineligible: 0 },
      total: 1,
      page: 1,
      page_size: 10,
    }
    const fetchMock = mockResponse(body)
    await expect(getMatches(profile, 1, signal())).resolves.toEqual(body)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/eligibility/matches')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      profile,
      page: 1,
      page_size: 10,
    })
  })

  it('rejects a positive status that conceals unknown conditions', async () => {
    mockResponse({ ...assessment, status: 'eligible' })
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'No eligibility conclusion can be drawn',
    )
  })

  it('rejects a positive scoped status that conceals unknown conditions', async () => {
    mockResponse({ ...assessment, admission_status: 'eligible' })
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'unexpected response',
    )
  })

  it('rejects inconsistent requirement name summaries', async () => {
    mockResponse({ ...assessment, unknown_requirements: [] })
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'unexpected response',
    )
  })

  it('rejects an unknown result in an eligible ranking group', async () => {
    mockResponse({
      eligible: [{ assessment, ranking_reasons: [] }],
      needs_verification: [],
      ineligible: [],
      counts: { eligible: 1, needs_verification: 0, ineligible: 0 },
      total: 1,
      page: 1,
      page_size: 10,
    })
    await expect(getMatches(profile, 1, signal())).rejects.toThrow(
      'unexpected response',
    )
  })

  it('rejects malformed nested requirements', async () => {
    mockResponse({
      ...assessment,
      requirements: [{ ...assessment.requirements[0], status: 'passed' }],
    })
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'unexpected response',
    )
  })

  it('reports validation field paths without repeating submitted student data', async () => {
    mockResponse(
      {
        detail: [
          {
            loc: ['body', 'profile', 'gpa'],
            msg: 'Invalid input',
            input: 'private-value',
          },
        ],
      },
      422,
    )
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'Check the submitted values for profile.gpa.',
    )
  })

  it('uses a safe validation fallback for model-level failures', async () => {
    mockResponse({ detail: 'raw debug output' }, 422)
    await expect(checkEligibility(7, profile, signal())).rejects.toThrow(
      'Check the submitted values and try again.',
    )
  })
})

describe('request failure handling', () => {
  it('rejects mismatched catalogue pagination', async () => {
    mockResponse({ items: [], total: 0, page: 2, page_size: 10 })
    await expect(
      listScholarships({ page: 1, page_size: 10 }, signal()),
    ).rejects.toThrow('unexpected response')
  })

  it('rejects mismatched match pagination', async () => {
    mockResponse({
      eligible: [],
      needs_verification: [],
      ineligible: [],
      counts: { eligible: 0, needs_verification: 0, ineligible: 0 },
      total: 0,
      page: 2,
      page_size: 10,
    })
    await expect(getMatches(profile, 1, signal())).rejects.toThrow(
      'unexpected response',
    )
  })
  it('provides a recovery message for network failures', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new TypeError('Failed to fetch')),
    )
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'Make sure the local backend is running',
    )
  })

  it('provides a recovery message for server failures without exposing the body', async () => {
    mockResponse({ detail: 'internal traceback' }, 503)
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'temporarily unavailable (HTTP 503)',
    )
  })

  it('rejects unreadable success responses', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(new Response('<html>Unexpected page</html>')),
    )
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'unreadable response',
    )
  })

  it('preserves cancellation rather than converting it into a connection warning', async () => {
    const controller = new AbortController()
    controller.abort()
    const abort = new DOMException('Cancelled', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(abort))
    await expect(getScholarship(7, controller.signal)).rejects.toBe(abort)
  })

  it('combines request cancellation with a bounded timeout', async () => {
    const fetchMock = mockResponse(record)
    const controller = new AbortController()
    await getScholarship(7, controller.signal)
    const requestSignal: AbortSignal = fetchMock.mock.calls[0][1].signal
    expect(requestSignal.aborted).toBe(false)
    controller.abort()
    expect(requestSignal.aborted).toBe(true)
  })

  it('explains a timed-out request', async () => {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockRejectedValue(new DOMException('Timed out', 'TimeoutError')),
    )
    await expect(getScholarship(7, signal())).rejects.toThrow(
      'request timed out',
    )
  })
})
