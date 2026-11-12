import { render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'
import { fetchAgentRecommendations } from '../agent'
import type { AgentResponse } from '../agent'
import type { StudentProfile } from '../types'
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

describe('local agent API contract', () => {
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
})

describe('local agent recommendations', () => {
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
})
