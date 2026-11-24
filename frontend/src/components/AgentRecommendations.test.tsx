import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { fetchAgentRecommendations } from '../agent'
import type { AgentResponse, RequestPreference } from '../agent'
import type { RankedProgramme, StudentProfile } from '../types'
import { demoAssessment } from '../test/fixtures'
import AgentRecommendations from './AgentRecommendations'

const profile: StudentProfile = {
  nationality: 'Kazakhstan',
  degree_level: 'bachelor',
  degree_completed: true,
  field_of_study: 'Engineering',
  gpa: 3.5,
  gpa_scale: 4,
  intended_start_year: 2027,
  funding_preference: 'fully_funded',
}

function response(): AgentResponse {
  return {
    status: 'completed',
    model: 'qwen3:4b-instruct',
    evaluated_on: '2026-11-12',
    steps: 3,
    tool_calls: 2,
    recommendations: [
      {
        assessment: demoAssessment(),
        ranking_reasons: ['Eligibility group: needs_verification.'],
      },
    ],
    message:
      'The model selected a source-backed candidate. Mandatory conditions remain unverified.',
    warnings: [
      'Fetched webpages are untrusted and do not update eligibility rules.',
    ],
    tool_trace: [
      {
        step: 1,
        name: 'search_scholarships',
        status: 'ok',
        arguments: { field: 'Engineering' },
        summary: 'Found one catalogue record.',
        source_url: null,
        fetched_at: null,
      },
      {
        step: 2,
        name: 'rank_scholarships',
        status: 'ok',
        arguments: { scholarship_ids: [1] },
        summary: 'Ranked one candidate using deterministic rules.',
        source_url: null,
        fetched_at: null,
      },
    ],
    disclaimer:
      'AI planning does not guarantee admission or funding. Deterministic checks are authoritative.',
  }
}

function mockResponse(body: unknown, status = 200) {
  const mock = vi.fn().mockResolvedValue(Response.json(body, { status }))
  vi.stubGlobal('fetch', mock)
  return mock
}

function fallbackResponse(): AgentResponse {
  return {
    ...response(),
    status: 'no_matches',
    recommendations: [],
    message: 'The model returned no grounded recommendations.',
    fallback_recommendations: response().recommendations,
    fallback_reason:
      'These retrieved candidates were assessed with deterministic rules and need further verification.',
  }
}

function candidate(id: number): RankedProgramme {
  return {
    assessment: {
      ...demoAssessment('needs_verification', id),
      scholarship_name: `Fictional Candidate ${id}`,
    },
    ranking_reasons: ['Mandatory evidence remains unresolved.'],
  }
}

function reliabilityResponse(): AgentResponse {
  const selected = candidate(1)
  return {
    ...response(),
    status: 'needs_verification',
    recommendations: [selected],
    discovery_candidates: [selected, candidate(2), candidate(3)],
    discovery_candidate_ids: [1, 2, 3, 4],
    discovery_scope: 'catalogue',
    model_error: null,
    model_explanations: [
      {
        scholarship_id: 1,
        requirements: [selected.assessment.requirements[0]],
      },
    ],
  }
}

function scopedResponse(destination: 'Germany' | 'Japan'): AgentResponse {
  const isGermany = destination === 'Germany'
  const records = isGermany
    ? [candidate(1), candidate(2), candidate(3)]
    : [candidate(4)]
  const location = {
    kind: 'destination',
    label: destination,
    mode: 'required',
  } satisfies RequestPreference
  const partial = {
    kind: 'funding',
    label: 'Partially funded',
    mode: 'preferred',
  } satisfies RequestPreference
  const fundingChecks = [
    { status: 'unmatched', evidence: 'The catalogue records full funding.' },
    { status: 'confirmed', evidence: 'The catalogue records partial funding.' },
    { status: 'unverified', evidence: 'The catalogue funding type is unknown.' },
  ] as const
  return {
    ...response(),
    recommendations: records.slice(0, 1),
    discovery_candidates: records,
    discovery_candidate_ids: records.map((item) => item.assessment.scholarship_id),
    discovery_scope: 'catalogue',
    request_preferences: isGermany ? [location, partial] : [location],
    request_matches: records.map((item, index) => ({
      scholarship_id: item.assessment.scholarship_id,
      checks: [
        {
          ...location,
          status: 'confirmed',
          evidence: `The catalogue records ${destination} as a study destination.`,
        },
        ...(isGermany ? [{ ...partial, ...fundingChecks[index] }] : []),
      ],
    })),
  }
}

function outageResponse(): AgentResponse {
  const original = reliabilityResponse()
  return {
    ...original,
    status: 'model_error',
    model_error: 'unavailable',
    steps: 1,
    tool_calls: 0,
    tool_trace: [],
    recommendations: [],
    model_explanations: [],
    fallback_recommendations: original.discovery_candidates,
    fallback_reason:
      'Local inference was unavailable. These candidates need verification.',
    message: 'The local model is unavailable. Catalogue discovery completed.',
  }
}

function nameResponse(
  status: 'matched' | 'ambiguous' | 'not_found' = 'ambiguous',
  method: 'exact' | 'alias' | 'fuzzy' = 'alias',
): AgentResponse {
  const records = status === 'not_found' ? [] :
    status === 'ambiguous' ? [candidate(1), candidate(2)] : [candidate(1)]
  const selected = status === 'matched' ? records : []
  const message = status === 'ambiguous'
    ? 'This name refers to multiple catalogue programmes.'
    : status === 'not_found'
      ? 'No catalogue programme matches this name. Check its spelling.'
      : `Interpreted the requested name as Fictional Candidate 1 using ${method} matching.`
  return {
    ...response(),
    status: status === 'matched' ? 'needs_verification' :
      status === 'ambiguous' ? 'ambiguous_match' : 'no_matches',
    steps: status === 'matched' ? 2 : 0,
    tool_calls: 0,
    tool_trace: [],
    recommendations: selected,
    discovery_candidates: selected,
    discovery_candidate_ids: selected.map((item) => item.assessment.scholarship_id),
    discovery_scope: status === 'matched' ? 'named_target' : 'catalogue',
    model_error: null,
    message,
    name_resolution: {
      status,
      query: status === 'not_found' ? 'Fictional Missing Award' : 'Fictional Award',
      method: status === 'not_found' ? null : method,
      candidate_ids: records.map((item) => item.assessment.scholarship_id),
      options: records.map((item) => ({
        scholarship_id: item.assessment.scholarship_id,
        scholarship_name: item.assessment.scholarship_name,
        official_source_url: item.assessment.official_source_url,
        last_verified_at: item.assessment.last_verified_at,
      })),
      message,
    },
  }
}

function overrideResolution(fields: Record<string, unknown>) {
  const payload = nameResponse()
  return {
    ...payload,
    name_resolution: { ...payload.name_resolution, ...fields },
  }
}

describe('local agent API contract', () => {
  it('accepts scoped named results with no confirmed match', async () => {
    const payload = {
      ...nameResponse('matched'),
      status: 'no_matches',
      steps: 0,
      recommendations: [],
      discovery_candidates: [],
      discovery_candidate_ids: [],
      request_preferences: scopedResponse('Germany').request_preferences,
      request_matches: [],
    }
    mockResponse(payload)
    await expect(
      fetchAgentRecommendations(
        profile,
        'Fictional Award in Germany',
        new AbortController().signal,
      ),
    ).resolves.toEqual(payload)
  })

  it.each([
    ['missing evidence for visible results', { request_matches: [] }],
    ['evidence for an unrelated scholarship', {
      request_matches: [
        ...scopedResponse('Japan').request_matches!,
        { ...scopedResponse('Japan').request_matches![0], scholarship_id: 5 },
      ],
    }],
    ['a required destination that lacks confirmation', {
      request_matches: [{
        scholarship_id: 4,
        checks: [{
          ...scopedResponse('Japan').request_preferences![0],
          status: 'unverified',
          evidence: 'Japan has no confirmed destination evidence.',
        }],
      }],
    }],
  ])('rejects %s', async (_label, fields) => {
    mockResponse({ ...scopedResponse('Japan'), ...fields })
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find programmes in Japan',
        new AbortController().signal,
      ),
    ).rejects.toThrow('unexpected response')
  })

  it('accepts unrequested names and legacy responses with a null resolution', async () => {
    for (const resolution of [null, {
      status: 'not_requested', query: null, method: null,
      candidate_ids: [], options: [], message: 'General catalogue discovery.',
    }]) {
      const payload = { ...reliabilityResponse(), name_resolution: resolution }
      mockResponse(payload)
      await expect(fetchAgentRecommendations(profile, 'Find candidates.',
        new AbortController().signal)).resolves.toEqual(payload)
    }
  })

  it('preserves deterministic ranking when multiple resolved names have another display order', async () => {
    const records = [candidate(1), candidate(2)]
    const original = nameResponse('matched')
    const payload = {
      ...original,
      discovery_candidates: records,
      discovery_candidate_ids: [1, 2],
      name_resolution: {
        ...original.name_resolution!,
        candidate_ids: [2, 1],
        options: records.toReversed().map((item) => ({
          scholarship_id: item.assessment.scholarship_id,
          scholarship_name: item.assessment.scholarship_name,
          official_source_url: item.assessment.official_source_url,
          last_verified_at: item.assessment.last_verified_at,
        })),
      },
    }
    mockResponse(payload)
    await expect(fetchAgentRecommendations(profile, 'Compare two programmes.',
      new AbortController().signal)).resolves.toEqual(payload)
  })
  it.each(['ambiguous', 'not_found', 'matched'] as const)(
    'accepts a consistent %s programme resolution', async (status) => {
      const payload = nameResponse(status)
      mockResponse(payload)
      await expect(fetchAgentRecommendations(profile, 'Check a name.',
        new AbortController().signal)).resolves.toEqual(payload)
    },
  )

  it.each(['alias', 'fuzzy'] as const)(
    'accepts an explained %s match with canonical source metadata', async (method) => {
      const payload = nameResponse('matched', method)
      mockResponse(payload)
      await expect(fetchAgentRecommendations(profile, 'Check a name.',
        new AbortController().signal)).resolves.toEqual(payload)
    },
  )

  it.each([
    { ...nameResponse(), name_resolution: undefined },
    { ...nameResponse(), name_resolution: null },
    { ...nameResponse(), status: 'completed' },
    { ...nameResponse(), steps: 1 },
    { ...nameResponse(), discovery_candidates: [candidate(1)], discovery_candidate_ids: [1] },
    { ...nameResponse(), recommendations: [candidate(1)] },
    overrideResolution({ status: 'invented' }),
    overrideResolution({ method: null }),
    overrideResolution({ method: 'probable' }),
    overrideResolution({ query: 'x'.repeat(301) }),
    overrideResolution({ query: '' }),
    overrideResolution({ candidate_ids: [1, 1] }),
    overrideResolution({ candidate_ids: [2, 1] }),
    overrideResolution({ options: [] }),
    overrideResolution({
      candidate_ids: [1],
      options: nameResponse().name_resolution!.options.slice(0, 1),
    }),
    overrideResolution({
      options: nameResponse().name_resolution!.options.map((option) => ({
        ...option,
        official_source_url: 'javascript:alert(1)',
      })),
    }),
    overrideResolution({
      options: nameResponse().name_resolution!.options.map((option) => ({
        ...option,
        last_verified_at: '2026-02-30',
      })),
    }),
    { ...nameResponse('not_found'), status: 'needs_verification' },
    { ...nameResponse('not_found'), name_resolution: { ...nameResponse().name_resolution, status: 'not_found' } },
    { ...nameResponse('matched'), discovery_scope: 'catalogue' },
    { ...nameResponse('matched'), discovery_candidates: [] },
    { ...nameResponse('matched'), name_resolution: { ...nameResponse('matched').name_resolution, candidate_ids: [2] } },
    { ...nameResponse('matched'), name_resolution: {
      ...nameResponse('matched').name_resolution,
      options: [{ ...nameResponse('matched').name_resolution!.options[0], scholarship_name: 'Fictional Substitute' }],
    } },
  ])('rejects unsafe or inconsistent programme resolution %j', async (payload) => {
    mockResponse(payload)
    await expect(fetchAgentRecommendations(profile, 'Check a name.',
      new AbortController().signal)).rejects.toThrow('unexpected response')
  })
  it('posts the profile and request only to the existing local endpoint', async () => {
    const expected = response()
    const mock = mockResponse(expected)
    const timeout = vi.spyOn(AbortSignal, 'timeout')
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find candidates.',
        new AbortController().signal,
      ),
    ).resolves.toEqual(expected)
    expect(mock.mock.calls[0][0]).toBe('/api/agent/recommend')
    expect(mock.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(mock.mock.calls[0][1].body)).toEqual({
      profile,
      goal: 'Find candidates.',
    })
    expect(timeout).toHaveBeenCalledWith(95_000)
  })

  it.each([
    null,
    { ...response(), model: 'cloud-model' },
    { ...response(), steps: 5 },
    { ...response(), tool_calls: 9 },
    { ...response(), tool_calls: 1 },
    {
      ...response(),
      recommendations: Array.from({ length: 4 }, (_, index) => ({
        assessment: { ...demoAssessment(), scholarship_id: index + 1 },
        ranking_reasons: [],
      })),
    },
    {
      ...response(),
      recommendations: [
        response().recommendations[0],
        response().recommendations[0],
      ],
    },
    {
      ...response(),
      recommendations: [
        {
          assessment: { ...demoAssessment(), status: 'eligible' },
          ranking_reasons: [],
        },
      ],
    },
    {
      ...response(),
      tool_trace: [
        { ...response().tool_trace[0], source_url: 'http://127.0.0.1/private' },
        response().tool_trace[1],
      ],
    },
    {
      ...response(),
      tool_trace: [
        { ...response().tool_trace[0], step: 4 },
        response().tool_trace[1],
      ],
    },
    { ...response(), evaluated_on: '2026-02-30' },
  ])('rejects malformed or unsafe agent responses: %j', async (payload) => {
    mockResponse(payload)
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find candidates.',
        new AbortController().signal,
      ),
    ).rejects.toThrow('unexpected response')
  })

  it.each([502, 503, 504])(
    'surfaces agent HTTP %i failures',
    async (status) => {
      mockResponse({ detail: 'Local inference unavailable' }, status)
      await expect(
        fetchAgentRecommendations(
          profile,
          'Find candidates.',
          new AbortController().signal,
        ),
      ).rejects.toThrow(`HTTP ${status}`)
    },
  )

  it('does not hide request cancellation as an outage', async () => {
    const controller = new AbortController()
    controller.abort()
    const error = new DOMException('Request aborted', 'AbortError')
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(error))
    await expect(
      fetchAgentRecommendations(profile, 'Find candidates.', controller.signal),
    ).rejects.toBe(error)
  })

  it('accepts separately identified deterministic candidates', async () => {
    const payload = fallbackResponse()
    mockResponse(payload)
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find candidates.',
        new AbortController().signal,
      ),
    ).resolves.toEqual(payload)
  })

  it.each([
    { ...fallbackResponse(), fallback_reason: undefined },
    { ...fallbackResponse(), fallback_reason: null },
    { ...fallbackResponse(), fallback_reason: '   ' },
    { ...fallbackResponse(), fallback_recommendations: null },
    { ...fallbackResponse(), fallback_recommendations: {} },
    {
      ...fallbackResponse(),
      fallback_recommendations: Array.from({ length: 4 }, (_, index) => ({
        assessment: demoAssessment('needs_verification', index + 1),
        ranking_reasons: [],
      })),
    },
    {
      ...fallbackResponse(),
      fallback_recommendations: [
        response().recommendations[0],
        response().recommendations[0],
      ],
    },
    {
      ...fallbackResponse(),
      fallback_recommendations: [
        { assessment: demoAssessment('eligible'), ranking_reasons: [] },
      ],
    },
    {
      ...fallbackResponse(),
      fallback_recommendations: [
        { assessment: demoAssessment('ineligible'), ranking_reasons: [] },
      ],
    },
    { ...fallbackResponse(), recommendations: response().recommendations },
    { ...fallbackResponse(), status: 'completed' },
    { ...fallbackResponse(), status: 'needs_verification' },
  ])('rejects inconsistent fallback data: %j', async (payload) => {
    mockResponse(payload)
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find candidates.',
        new AbortController().signal,
      ),
    ).rejects.toThrow('unexpected response')
  })

  it('accepts persistent candidates and server-grounded model explanation points', async () => {
    const payload = reliabilityResponse()
    mockResponse(payload)
    await expect(
      fetchAgentRecommendations(
        profile,
        'Find candidates.',
        new AbortController().signal,
      ),
    ).resolves.toEqual(payload)
  })

  it.each(['unavailable', 'timeout', 'invalid_response', 'busy'] as const)(
    'accepts a typed %s result with deterministic recovery',
    async (model_error) => {
      const payload = { ...outageResponse(), model_error }
      mockResponse(payload)
      await expect(
        fetchAgentRecommendations(
          profile,
          'Find candidates.',
          new AbortController().signal,
        ),
      ).resolves.toEqual(payload)
    },
  )

  it.each([
    { ...reliabilityResponse(), model_error: 'cloud_error' },
    { ...reliabilityResponse(), model_error: 'unavailable' },
    { ...outageResponse(), model_error: null },
    { ...outageResponse(), model_error: undefined },
    { ...outageResponse(), recommendations: [candidate(1)] },
    { ...reliabilityResponse(), discovery_candidates: null },
    { ...reliabilityResponse(), discovery_candidates: {} },
    {
      ...reliabilityResponse(),
      discovery_candidates: [candidate(1), candidate(2), candidate(3), candidate(4)],
    },
    {
      ...reliabilityResponse(),
      discovery_candidates: [candidate(1), candidate(1)],
    },
    { ...reliabilityResponse(), discovery_candidate_ids: [1, 2, 2, 3] },
    { ...reliabilityResponse(), discovery_candidate_ids: [1, 2, 0] },
    {
      ...reliabilityResponse(),
      discovery_candidate_ids: [1, 2, Number.MAX_SAFE_INTEGER + 1],
    },
    { ...reliabilityResponse(), discovery_candidate_ids: [1, 2, '3'] },
    { ...reliabilityResponse(), discovery_candidate_ids: [1, 2] },
    { ...reliabilityResponse(), discovery_candidate_ids: undefined },
    { ...reliabilityResponse(), discovery_scope: undefined },
    { ...reliabilityResponse(), discovery_scope: 'model' },
    { ...reliabilityResponse(), discovery_scope: ['catalogue'] },
    {
      ...reliabilityResponse(),
      discovery_candidates: [
        { assessment: demoAssessment('ineligible'), ranking_reasons: [] },
      ],
    },
    {
      ...reliabilityResponse(),
      discovery_scope: 'named_target',
      recommendations: [candidate(5)],
      model_explanations: [],
    },
    {
      ...reliabilityResponse(),
      discovery_scope: 'named_target',
      discovery_candidates: [
        { assessment: demoAssessment('ineligible'), ranking_reasons: [] },
      ],
    },
    {
      ...reliabilityResponse(),
      discovery_candidates: [{
        ...candidate(1),
        assessment: {
          ...candidate(1).assessment,
          official_source_url: 'https://example.org/different-source',
        },
      }],
    },
    { ...reliabilityResponse(), model_explanations: null },
    { ...reliabilityResponse(), model_explanations: {} },
    {
      ...reliabilityResponse(),
      model_explanations: Array(4).fill(
        reliabilityResponse().model_explanations![0],
      ),
    },
    {
      ...reliabilityResponse(),
      model_explanations: Array(2).fill(
        reliabilityResponse().model_explanations![0],
      ),
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{
        scholarship_id: 2,
        requirements: [candidate(2).assessment.requirements[0]],
      }],
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{ scholarship_id: 1, requirements: [] }],
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{
        scholarship_id: 1,
        requirements: Array(5).fill(candidate(1).assessment.requirements[0]),
      }],
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{
        scholarship_id: 1,
        requirements: Array(2).fill(candidate(1).assessment.requirements[0]),
      }],
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{
        scholarship_id: 1,
        requirements: [{
          ...candidate(1).assessment.requirements[0],
          explanation: 'Invented eligibility guarantee.',
        }],
      }],
    },
    {
      ...reliabilityResponse(),
      model_explanations: [{
        scholarship_id: 1,
        requirements: [{
          ...candidate(1).assessment.requirements[0],
          status: 'met',
        }],
      }],
    },
  ])(
    'rejects invalid discovery or ungrounded explanation fields: %j',
    async (payload) => {
      mockResponse(payload)
      await expect(
        fetchAgentRecommendations(
          profile,
          'Find candidates.',
          new AbortController().signal,
        ),
      ).rejects.toThrow('unexpected response')
    },
  )
})

describe('local agent recommendations', () => {
  it('displays different request fits for Germany and Japan with the same profile', async () => {
    const user = userEvent.setup()
    const mock = vi.fn(async (url: string, options: RequestInit) => {
      if (url === '/api/agent/recommend') {
        const { goal } = JSON.parse(String(options.body)) as { goal: string }
        return Response.json(scopedResponse(goal.includes('Germany') ? 'Germany' : 'Japan'))
      }
      return Response.json({}, { status: 404 })
    })
    vi.stubGlobal('fetch', mock)
    render(<AgentRecommendations profile={profile} />)
    const input = screen.getByLabelText('What would you like to find?')
    const submit = screen.getByRole('button', {
      name: 'Generate AI recommendations',
    })
    const germany = 'Find programmes in Germany, including partial funding options.'
    const japan = 'Find programmes in Japan.'

    await user.clear(input)
    await user.type(input, germany)
    await user.click(submit)
    const selections = await screen.findByRole('region', {
      name: 'Model selections',
    })
    const selectedFit = within(selections).getByRole('region', {
      name: 'Request fit',
    })
    expect(within(selectedFit).getByText('Required destination')).toBeVisible()
    expect(within(selectedFit).getByText('Germany')).toBeVisible()
    expect(within(selectedFit).getByText('Confirmed')).toBeVisible()
    expect(within(selectedFit).getByText('Preferred funding')).toBeVisible()
    expect(within(selectedFit).getByText('Unmatched')).toBeVisible()
    await user.click(within(selections).getByText('Assessment details'))
    expect(within(selections).getByRole('region', { name: 'Request evidence' }))
      .toHaveTextContent('The catalogue records full funding.')
    const discovery = screen.getByRole('region', {
      name: 'Deterministic discovery candidates',
    })
    const retainedFits = within(discovery).getAllByRole('region', {
      name: 'Request fit',
    })
    expect(retainedFits[0]).toHaveTextContent('Confirmed')
    expect(retainedFits[1]).toHaveTextContent('Needs verification')
    for (const summary of within(discovery).getAllByText('Assessment details')) {
      await user.click(summary)
    }
    const evidence = within(discovery).getAllByRole('region', { name: 'Request evidence' })
    expect(evidence[0]).toHaveTextContent('The catalogue records partial funding.')
    expect(evidence[1]).toHaveTextContent('The catalogue funding type is unknown.')

    await user.click(screen.getByRole('button', { name: 'Edit request' }))
    expect(input).toHaveValue(germany)
    expect(screen.queryByRole('region', { name: 'Local AI response' })).not.toBeInTheDocument()
    await user.clear(input)
    await user.type(input, japan)
    await user.click(submit)
    const japanFit = await screen.findByRole('region', { name: 'Request fit' })
    expect(japanFit).toHaveTextContent('Japan')
    await user.click(screen.getByText('Assessment details'))
    expect(screen.getByRole('region', { name: 'Request evidence' }))
      .toHaveTextContent('The catalogue records Japan as a study destination.')
    expect(
      screen.getByRole('heading', { name: 'Fictional Candidate 4' }),
    ).toBeVisible()
    expect(
      screen.queryByRole('heading', { name: 'Fictional Candidate 1' }),
    ).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: 'Deterministic discovery candidates' }),
    ).not.toBeInTheDocument()
    expect(mock.mock.calls.filter(([url]) => url === '/api/agent/recommend')
      .map(([, options]) => JSON.parse(String(options.body)))).toEqual([
      { goal: germany, profile },
      { goal: japan, profile },
    ])
  })

  it('preserves a required no-match response without presenting unrelated programmes', async () => {
    const user = userEvent.setup()
    const message =
      'The catalogue has no confirmed scholarship for both Germany and partial funding.'
    mockResponse({
      ...scopedResponse('Germany'),
      status: 'no_matches',
      recommendations: [],
      discovery_candidates: [],
      discovery_candidate_ids: [],
      request_matches: [],
      request_preferences: scopedResponse('Germany').request_preferences?.map(
        (preference) => ({ ...preference, mode: 'required' }),
      ),
      message,
    })
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'No confirmed matches' }),
    ).toBeVisible()
    expect(screen.getByText(message)).toBeVisible()
    expect(screen.queryByText(/Try a simpler request/)).not.toBeInTheDocument()
    expect(
      screen.queryByRole('region', { name: 'Eligibility assessment' }),
    ).not.toBeInTheDocument()
  })

  it('waits for an explicit request and preserves unverified eligibility', async () => {
    const user = userEvent.setup()
    const mock = mockResponse(response())
    const storage = vi.spyOn(Storage.prototype, 'setItem')
    render(<AgentRecommendations profile={profile} />)
    expect(
      screen.getByRole('heading', { name: 'Local AI recommendations' }),
    ).toBeVisible()
    expect(mock).not.toHaveBeenCalled()
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    const output = await screen.findByRole('region', {
      name: 'Local AI response',
    })
    expect(within(output).getByText(response().message)).toBeVisible()
    expect(within(output).getByText('Tools actually attempted')).toBeVisible()
    expect(
      within(output).getByText('Step 1: search scholarships'),
    ).toBeVisible()
    const assessment = within(output).getByRole('region', {
      name: 'Eligibility assessment',
    })
    expect(
      within(assessment).getAllByText('Needs verification').length,
    ).toBeGreaterThan(0)
    expect(
      within(assessment).queryByText('Eligible', { exact: true }),
    ).not.toBeInTheDocument()
    expect(storage).not.toHaveBeenCalled()
  })

  it('validates a blank request before contacting the model', async () => {
    const user = userEvent.setup()
    const mock = mockResponse(response())
    render(<AgentRecommendations profile={profile} />)
    await user.clear(screen.getByLabelText('What would you like to find?'))
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(screen.getByRole('alert')).toHaveTextContent('1–300 characters')
    expect(screen.getByLabelText('What would you like to find?')).toHaveFocus()
    expect(mock).not.toHaveBeenCalled()
  })

  it('fills an editable example, clears validation and waits for explicit submission', async () => {
    const user = userEvent.setup()
    const mock = mockResponse(response())
    render(<AgentRecommendations profile={profile} />)
    const input = screen.getByLabelText('What would you like to find?')
    await user.clear(input)
    await user.click(screen.getByRole('button', { name: 'Generate AI recommendations' }))
    await user.click(screen.getByRole('button', { name: 'Study in Germany' }))
    expect(input).toHaveFocus()
    expect(input).toHaveValue('Find scholarships in Germany, including partial funding options.')
    expect(input).toHaveAttribute('aria-invalid', 'false')
    expect(mock).not.toHaveBeenCalled()
    await user.click(screen.getByRole('button', { name: 'Generate AI recommendations' }))
    expect(JSON.parse(mock.mock.calls[0][1].body).goal).toBe(
      'Find scholarships in Germany, including partial funding options.',
    )
  })

  it('stops waiting without losing the request and ignores late responses', async () => {
    const user = userEvent.setup()
    let finish!: (response: Response) => void
    const fetchMock = vi.fn().mockReturnValue(new Promise<Response>((resolve) => { finish = resolve }))
    vi.stubGlobal('fetch', fetchMock)
    render(<AgentRecommendations profile={profile} />)
    await user.click(screen.getByRole('button', { name: 'Check SMACCs' }))
    await user.click(screen.getByRole('button', { name: 'Generate AI recommendations' }))
    expect(screen.getByRole('button', { name: 'Check SMACCs' })).toBeDisabled()
    await user.click(screen.getByRole('button', { name: 'Stop waiting' }))
    expect(fetchMock.mock.calls[0][1].signal.aborted).toBe(true)
    finish(Response.json(response()))
    await user.tab()
    expect(screen.getByRole('status')).toHaveTextContent('You stopped waiting')
    expect(screen.queryByRole('region', { name: 'Local AI response' })).toBeNull()
    expect(screen.getByLabelText('What would you like to find?')).toHaveValue(
      'Assess SMACCs for my profile and explain what needs verification.',
    )
  })

  it.each(['no_matches', 'limit_reached'] as const)(
    'displays deterministic candidates after %s while preserving the model trace',
    async (status) => {
      const user = userEvent.setup()
      const payload = { ...fallbackResponse(), status }
      mockResponse(payload)
      render(<AgentRecommendations profile={profile} />)
      await user.click(
        screen.getByRole('button', { name: 'Generate AI recommendations' }),
      )
      const fallback = await screen.findByRole('region', {
        name: 'Deterministic candidates to verify',
      })
      expect(
        within(fallback).getByText(payload.fallback_reason!),
      ).toBeVisible()
      const assessment = within(fallback).getByRole('region', {
        name: 'Eligibility assessment',
      })
      expect(
        within(assessment).getAllByText('Needs verification').length,
      ).toBeGreaterThan(0)
      expect(
        within(assessment).queryByText('Eligible', { exact: true }),
      ).not.toBeInTheDocument()
      expect(
        within(assessment).getByRole('link', { name: /View official source/ }),
      ).toHaveAttribute('href', demoAssessment().official_source_url)
      expect(screen.getByText(payload.message)).toBeVisible()
      expect(screen.getByText(/2 of 8 tool calls/)).toBeVisible()
      expect(screen.getByText('Step 1: search scholarships')).toBeVisible()
      expect(screen.getByText('Step 2: rank scholarships')).toBeVisible()
    },
  )

  it('shows a pending state and cancels waiting on navigation', async () => {
    const user = userEvent.setup()
    const mock = vi.fn().mockReturnValue(new Promise(() => {}))
    vi.stubGlobal('fetch', mock)
    const { unmount } = render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(screen.getByRole('status')).toHaveTextContent('up to 90 seconds')
    expect(
      screen.getByRole('button', { name: 'Local AI is working…' }),
    ).toBeDisabled()
    const signal: AbortSignal = mock.mock.calls[0][1].signal
    expect(signal.aborted).toBe(false)
    unmount()
    expect(signal.aborted).toBe(true)
  })

  it('keeps deterministic matches available during an Ollama outage and can retry', async () => {
    const user = userEvent.setup()
    const mock = vi
      .fn()
      .mockResolvedValueOnce(
        Response.json({ detail: 'Ollama offline' }, { status: 503 }),
      )
      .mockResolvedValueOnce(Response.json(response()))
    vi.stubGlobal('fetch', mock)
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(
      screen.getByRole('link', { name: 'Continue with deterministic matches' }),
    ).toHaveAttribute('href', '#/matches')
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(
      await screen.findByRole('region', { name: 'Local AI response' }),
    ).toBeVisible()
  })

  it.each(['needs_verification', 'limit_reached', 'no_matches'] as const)(
    'explains %s without manufacturing programme cards',
    async (status) => {
      const user = userEvent.setup()
      mockResponse({ ...response(), status, recommendations: [] })
      render(<AgentRecommendations profile={profile} />)
      await user.click(
        screen.getByRole('button', { name: 'Generate AI recommendations' }),
      )
      const output = await screen.findByRole('region', {
        name: 'Local AI response',
      })
      expect(
        within(output).queryByRole('region', {
          name: 'Eligibility assessment',
        }),
      ).not.toBeInTheDocument()
      expect(
        within(output).getByText(/No grounded recommendation was returned/),
      ).toBeVisible()
    },
  )

  it('renders blocked tools as blocked, never as successful execution', async () => {
    const user = userEvent.setup()
    const payload = response()
    payload.tool_trace[0].status = 'blocked'
    payload.tool_trace[0].summary = 'URL was not approved.'
    mockResponse(payload)
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    await waitFor(() =>
      expect(screen.getByText(/URL was not approved/)).toBeVisible(),
    )
    expect(screen.getByText('blocked')).toBeVisible()
  })

  it('retains discovery candidates when the model selects a subset and avoids duplicate cards', async () => {
    const user = userEvent.setup()
    mockResponse(reliabilityResponse())
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    const selected = await screen.findByRole('region', { name: 'Model selections' })
    const retained = screen.getByRole('region', {
      name: 'Deterministic discovery candidates',
    })
    expect(within(selected).getByText('Fictional Candidate 1')).toBeVisible()
    expect(within(retained).getByText('Fictional Candidate 2')).toBeVisible()
    expect(within(retained).getByText('Fictional Candidate 3')).toBeVisible()
    expect(
      screen.getAllByRole('region', { name: 'Eligibility assessment' }),
    ).toHaveLength(3)
    const disclosure = within(selected).getByText('Assessment details').closest('summary')!
    expect(disclosure.parentElement).not.toHaveAttribute('open')
    await user.click(disclosure)
    expect(disclosure.parentElement).toHaveAttribute('open')
    const explanation = within(selected).getByRole('region', {
      name: 'Model-selected explanation points',
    })
    expect(
      within(explanation).getByText(
        candidate(1).assessment.requirements[0].explanation,
      ),
    ).toBeVisible()
    expect(
      within(retained).queryByRole('region', {
        name: 'Model-selected explanation points',
      }),
    ).not.toBeInTheDocument()
  })

  it('retains candidates and verified source dates after an empty model selection', async () => {
    const user = userEvent.setup()
    mockResponse({
      ...reliabilityResponse(),
      status: 'no_matches',
      recommendations: [],
      model_explanations: [],
    })
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    const retained = await screen.findByRole('region', {
      name: 'Deterministic discovery candidates',
    })
    expect(
      within(retained).getAllByRole('region', { name: 'Eligibility assessment' }),
    ).toHaveLength(3)
    expect(
      within(retained).getAllByRole('link', { name: /View official source/ }),
    ).toHaveLength(3)
    expect(
      within(retained).getAllByText(/Last verified 11 Nov 2026/),
    ).toHaveLength(3)
    expect(
      screen.queryByRole('region', { name: 'Model selections' }),
    ).not.toBeInTheDocument()
  })

  it('shows deterministic recovery after an Ollama outage without duplicating fallback candidates', async () => {
    const user = userEvent.setup()
    mockResponse(outageResponse())
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(
      await screen.findByRole('heading', { name: 'Local AI could not finish' }),
    ).toBeVisible()
    expect(screen.getByText(outageResponse().message)).toBeVisible()
    expect(
      screen.getAllByRole('region', { name: 'Eligibility assessment' }),
    ).toHaveLength(3)
    expect(screen.getByText('No tool calls were executed.')).toBeVisible()
    expect(
      screen.queryByRole('region', {
        name: 'Deterministic candidates to verify',
      }),
    ).not.toBeInTheDocument()
  })

  it('preserves a named negative target and its disqualifying requirement', async () => {
    const user = userEvent.setup()
    const negative = demoAssessment('ineligible', 5)
    negative.scholarship_name = 'Fictional Closed Programme'
    negative.requirements[2].explanation =
      'The published application deadline has passed.'
    mockResponse({
      ...reliabilityResponse(),
      status: 'no_matches',
      recommendations: [],
      model_explanations: [],
      discovery_scope: 'named_target',
      discovery_candidate_ids: [5],
      discovery_candidates: [{
        assessment: negative,
        ranking_reasons: ['Confirmed deadline failure.'],
      }],
    })
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    const retained = await screen.findByRole('region', {
      name: 'Requested programme assessments',
    })
    expect(within(retained).getByText('Fictional Closed Programme')).toBeVisible()
    expect(within(retained).getAllByText('Ineligible').length).toBeGreaterThan(0)
    expect(within(retained).getByText('Unmet requirements')).toBeVisible()
    await user.click(within(retained).getByText('Assessment details'))
    expect(
      within(retained).getByText('The published application deadline has passed.'),
    ).toBeVisible()
    expect(
      within(retained).queryByText('Eligible', { exact: true }),
    ).not.toBeInTheDocument()
  })

  it('asks for a full programme name and shows sourced ambiguity options', async () => {
    const user = userEvent.setup()
    mockResponse(nameResponse())
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(await screen.findByRole('heading', { name: 'Choose a programme' })).toBeVisible()
    const choices = screen.getByRole('region', { name: 'Matching programmes' })
    expect(within(choices).getByText('Enter the full programme name in your request.')).toBeVisible()
    expect(within(choices).getByText('Fictional Candidate 1')).toBeVisible()
    expect(within(choices).getByText('Fictional Candidate 2')).toBeVisible()
    expect(within(choices).getAllByRole('link', { name: /Official source for/ })).toHaveLength(2)
    expect(within(choices).getAllByText(/Last verified 11 Nov 2026/)).toHaveLength(2)
    expect(screen.queryByRole('region', { name: 'Eligibility assessment' })).not.toBeInTheDocument()
    expect(screen.queryByText(/No grounded recommendation was returned/)).not.toBeInTheDocument()
    expect(screen.getByText('No tool calls were executed.')).toBeVisible()
  })

  it('shows a specific unknown-programme state without unrelated cards', async () => {
    const user = userEvent.setup()
    const payload = nameResponse('not_found')
    mockResponse(payload)
    render(<AgentRecommendations profile={profile} />)
    await user.click(
      screen.getByRole('button', { name: 'Generate AI recommendations' }),
    )
    expect(await screen.findByRole('heading', { name: 'Programme not found' })).toBeVisible()
    expect(screen.getByText(payload.message)).toBeVisible()
    expect(screen.queryByRole('region', { name: 'Eligibility assessment' })).not.toBeInTheDocument()
    expect(screen.queryByRole('region', { name: 'Matching programmes' })).not.toBeInTheDocument()
    expect(screen.queryByText(/No grounded recommendation was returned/)).not.toBeInTheDocument()
  })

  it.each(['alias', 'fuzzy'] as const)(
    'explains the %s name interpretation before the canonical assessment',
    async (method) => {
      const user = userEvent.setup()
      const payload = nameResponse('matched', method)
      mockResponse(payload)
      render(<AgentRecommendations profile={profile} />)
      await user.click(
        screen.getByRole('button', { name: 'Generate AI recommendations' }),
      )
      const interpretation = await screen.findByRole('region', {
        name: 'Programme-name interpretation',
      })
      expect(within(interpretation).getByText(payload.name_resolution!.message)).toBeVisible()
      expect(screen.getByRole('heading', { name: 'Fictional Candidate 1' })).toBeVisible()
      expect(screen.getAllByRole('region', { name: 'Eligibility assessment' })).toHaveLength(1)
    },
  )
})
