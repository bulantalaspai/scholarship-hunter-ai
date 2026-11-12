import { act, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import App from './App'
import { demoAssessment, demoMatches, demoScholarship } from './test/fixtures'
import type { EligibilityStatus } from './types'
import { MatchesPage, Pagination } from './pages'

beforeEach(() => window.history.replaceState(null, '', '/'))
afterEach(() => window.history.replaceState(null, '', '/'))

function mockApi(
  overrides: {
    verdict?: EligibilityStatus
    listStatus?: number
    detailStatus?: number
    checkStatus?: number
  } = {},
) {
  const fetchMock = vi.fn((input: string, init?: RequestInit) => {
    const url = new URL(input, 'http://localhost')
    if (url.pathname === '/api/health')
      return Promise.resolve(
        Response.json({ status: 'ok', service: 'scholarship-hunter-ai' }),
      )
    if (url.pathname === '/api/scholarships') {
      if (overrides.listStatus)
        return Promise.resolve(
          Response.json(
            { detail: 'Failure' },
            { status: overrides.listStatus },
          ),
        )
      const empty = url.searchParams.get('field') === 'No match'
      return Promise.resolve(
        Response.json({
          items: empty ? [] : [demoScholarship],
          total: empty ? 0 : 1,
          page: Number(url.searchParams.get('page') ?? 1),
          page_size: 10,
        }),
      )
    }
    if (url.pathname === '/api/scholarships/1')
      return Promise.resolve(
        overrides.detailStatus
          ? Response.json(
              { detail: 'Scholarship not found' },
              { status: overrides.detailStatus },
            )
          : Response.json(demoScholarship),
      )
    if (url.pathname === '/api/eligibility/check') {
      if (overrides.checkStatus)
        return Promise.resolve(
          Response.json(
            { detail: [{ loc: ['body', 'profile', 'gpa'], msg: 'Invalid' }] },
            { status: overrides.checkStatus },
          ),
        )
      expect(JSON.parse(String(init?.body))).toHaveProperty('scholarship_id', 1)
      return Promise.resolve(Response.json(demoAssessment(overrides.verdict)))
    }
    if (url.pathname === '/api/eligibility/matches')
      return Promise.resolve(Response.json(demoMatches()))
    return Promise.resolve(
      Response.json({ detail: 'Scholarship not found' }, { status: 404 }),
    )
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

async function fillProfile(user: ReturnType<typeof userEvent.setup>) {
  await user.type(screen.getByLabelText('Nationality'), 'Kazakhstan')
  await user.selectOptions(screen.getByLabelText('Degree level'), 'bachelor')
  await user.selectOptions(screen.getByLabelText('Degree completion'), 'true')
  await user.type(screen.getByLabelText('Field of study'), 'Engineering')
  await user.type(screen.getByLabelText('GPA', { exact: true }), '3.5')
  await user.type(screen.getByLabelText('GPA scale'), '4')
  await user.type(screen.getByLabelText('IELTS overall'), '7')
  await user.selectOptions(
    screen.getByLabelText('Funding preference'),
    'fully_funded',
  )
}

describe('scholarship discovery journeys', () => {
  it('provides previous and next pagination using the supplied route', () => {
    render(
      <Pagination
        page={2}
        total={25}
        link={(page) => `#/explore?country=Germany&page=${page}`}
      />,
    )
    expect(screen.getByRole('link', { name: 'Previous page' })).toHaveAttribute(
      'href',
      '#/explore?country=Germany&page=1',
    )
    expect(screen.getByRole('link', { name: 'Next page' })).toHaveAttribute(
      'href',
      '#/explore?country=Germany&page=3',
    )
    expect(screen.getByText('Page 2 of 3')).toBeVisible()
  })

  it('explains an out-of-range matches page and offers first-page recovery', async () => {
    vi.stubGlobal(
      'fetch',
      vi
        .fn()
        .mockResolvedValue(
          Response.json({ ...demoMatches(), page: 9, needs_verification: [] }),
        ),
    )
    render(
      <MatchesPage
        page={9}
        profile={{
          nationality: 'Kazakhstan',
          degree_level: 'bachelor',
          field_of_study: 'Engineering',
          intended_start_year: 2027,
          funding_preference: 'any_funding',
        }}
      />,
    )
    expect(
      await screen.findByRole('heading', { name: 'No matches on this page' }),
    ).toBeVisible()
    expect(
      screen.getByRole('link', { name: 'First page' }),
    ).toHaveAttribute('href', '#/matches?page=1')
    expect(
      screen.queryByText(demoScholarship.scholarship_name),
    ).not.toBeInTheDocument()
  })

  it('cancels obsolete detail loads and never replaces the new record with stale data', async () => {
    window.location.hash = '/scholarships/1'
    let resolveFirst: (response: Response) => void = () => {}
    const pending = new Promise<Response>((resolve) => {
      resolveFirst = resolve
    })
    const second = {
      ...demoScholarship,
      id: 2,
      scholarship_name: 'Fictional Second Test Award',
    }
    const fetchMock = vi.fn((url: string) =>
      url === '/api/scholarships/1'
        ? pending
        : Promise.resolve(Response.json(second)),
    )
    vi.stubGlobal('fetch', fetchMock)
    render(<App />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalled())
    await act(async () => {
      window.location.hash = '/scholarships/2'
    })
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: second.scholarship_name,
      }),
    ).toBeVisible()
    await act(async () => {
      resolveFirst(Response.json(demoScholarship))
    })
    expect(
      screen.queryByRole('heading', { name: demoScholarship.scholarship_name }),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('heading', { level: 1, name: second.scholarship_name }),
    ).toBeVisible()
  })
  it('searches from home using the supported field filter', async () => {
    const user = userEvent.setup()
    const fetchMock = mockApi()
    render(<App />)
    await user.type(
      screen.getByLabelText('What would you like to study?'),
      'Engineering',
    )
    await user.click(
      screen.getByRole('button', { name: 'Explore scholarships' }),
    )
    expect(
      await screen.findByRole('link', {
        name: demoScholarship.scholarship_name,
      }),
    ).toBeVisible()
    const calls = fetchMock.mock.calls.map(
      ([input]) => new URL(input, 'http://localhost'),
    )
    expect(
      calls.some(
        (url) =>
          url.searchParams.get('field') === 'Engineering' &&
          url.searchParams.get('page_size') === '10',
      ),
    ).toBe(true)
    expect(calls.every((url) => !url.searchParams.has('q'))).toBe(true)
  })

  it('applies composable catalogue filters and opens details with explicit unknowns', async () => {
    window.location.hash = '/explore'
    const user = userEvent.setup()
    const fetchMock = mockApi()
    render(<App />)
    await screen.findByRole('link', { name: demoScholarship.scholarship_name })
    await user.type(screen.getByLabelText('Destination country'), 'Germany')
    await user.type(screen.getByLabelText('Study field'), 'Engineering')
    await user.selectOptions(
      screen.getByLabelText('Funding type'),
      'fully_funded',
    )
    await user.click(screen.getByRole('button', { name: 'Apply filters' }))
    await waitFor(() =>
      expect(
        fetchMock.mock.calls.some(
          ([url]) =>
            url.includes('country=Germany') &&
            url.includes('funding_type=fully_funded'),
        ),
      ).toBe(true),
    )
    await user.click(
      await screen.findByRole('link', { name: 'View scholarship' }),
    )
    expect(
      await screen.findByRole('heading', {
        level: 1,
        name: demoScholarship.scholarship_name,
      }),
    ).toBeVisible()
    expect(
      screen.getAllByText('Not confirmed — verify with the provider').length,
    ).toBeGreaterThan(0)
    screen
      .getAllByRole('link', { name: /View official source/ })
      .forEach((link) =>
        expect(link).toHaveAttribute(
          'href',
          demoScholarship.official_source_url,
        ),
      )
    expect(screen.getByText('11 Nov 2026')).toBeVisible()
  })

  it('explains empty searches instead of fabricating fallback records', async () => {
    window.location.hash = '/explore?field=No%20match'
    mockApi()
    render(<App />)
    expect(
      await screen.findByRole('heading', { name: 'No scholarships found' }),
    ).toBeVisible()
    expect(
      screen.queryByText(demoScholarship.scholarship_name),
    ).not.toBeInTheDocument()
    expect(
      screen.getByRole('link', { name: 'Browse the full catalogue' }),
    ).toBeVisible()
  })

  it('shows a retryable catalogue error and recovers', async () => {
    window.location.hash = '/explore'
    const user = userEvent.setup()
    mockApi({ listStatus: 503 })
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent('HTTP 503')
    expect(screen.queryByText('No scholarships found')).not.toBeInTheDocument()
    mockApi()
    await user.click(screen.getByRole('button', { name: 'Try again' }))
    expect(
      await screen.findByText(demoScholarship.scholarship_name),
    ).toBeVisible()
  })

  it('handles absent scholarships and invalid navigation links', async () => {
    window.location.hash = '/scholarships/999'
    mockApi()
    render(<App />)
    expect(await screen.findByRole('alert')).toHaveTextContent(
      'Scholarship not found',
    )
    await act(async () => {
      window.location.hash = '/scholarships/not-an-id'
    })
    expect(
      await screen.findByRole('heading', { name: 'Page not found' }),
    ).toBeVisible()
  })

  it.each(['eligible', 'ineligible', 'needs_verification'] as const)(
    'preserves the backend %s verdict through profile submission',
    async (verdict) => {
      window.location.hash = '/profile?scholarship=1'
      const user = userEvent.setup()
      const fetchMock = mockApi({ verdict })
      render(<App />)
      await fillProfile(user)
      await user.click(
        screen.getByRole('button', { name: 'Check my eligibility' }),
      )
      const assessment = await screen.findByRole('region', {
        name: 'Eligibility assessment',
      })
      const label =
        verdict === 'eligible'
          ? 'Eligible'
          : verdict === 'ineligible'
            ? 'Ineligible'
            : 'Needs verification'
      expect(within(assessment).getAllByText(label).length).toBeGreaterThan(0)
      expect(
        within(assessment).getByText(/does not guarantee admission or funding/),
      ).toBeVisible()
      expect(
        within(assessment).getByText('Admission eligibility'),
      ).toBeVisible()
      expect(within(assessment).getByText('Funding eligibility')).toBeVisible()
      if (verdict === 'needs_verification')
        expect(
          within(assessment).queryByText('Eligible'),
        ).not.toBeInTheDocument()
      const check = fetchMock.mock.calls.find(
        ([url]) => url === '/api/eligibility/check',
      )
      expect(JSON.parse(String(check?.[1]?.body)).profile).toMatchObject({
        gpa: 3.5,
        gpa_scale: 4,
        ielts_overall: 7,
        degree_completed: true,
      })
      expect(localStorage.length).toBe(0)
    },
  )

  it('shows backend validation failures without inventing a result', async () => {
    window.location.hash = '/profile?scholarship=1'
    const user = userEvent.setup()
    mockApi({ checkStatus: 422 })
    render(<App />)
    await fillProfile(user)
    await user.click(
      screen.getByRole('button', { name: 'Check my eligibility' }),
    )
    expect(await screen.findByRole('alert')).toHaveTextContent('profile.gpa')
    expect(
      screen.queryByRole('region', { name: 'Eligibility assessment' }),
    ).not.toBeInTheDocument()
    expect(screen.getByRole('link', { name: 'Edit profile' })).toBeVisible()
  })

  it('displays grouped matches and clears the profile on request', async () => {
    window.location.hash = '/profile'
    const user = userEvent.setup()
    mockApi()
    render(<App />)
    await fillProfile(user)
    await user.click(screen.getByRole('button', { name: 'Find my matches' }))
    expect(
      await screen.findByText('Exact documented study-field match.'),
    ).toBeVisible()
    expect(
      screen.getByText(/No fully verified eligible programmes were found/),
    ).toBeVisible()
    await user.click(
      screen.getByRole('link', { name: 'View requirement checks' }),
    )
    expect(
      await screen.findByRole('region', { name: 'Eligibility assessment' }),
    ).toBeVisible()
    await user.click(screen.getByRole('link', { name: 'Edit profile' }))
    expect(await screen.findByLabelText('Nationality')).toHaveValue(
      'Kazakhstan',
    )
    await user.click(screen.getByRole('button', { name: 'Clear profile' }))
    expect(screen.getByLabelText('Nationality')).toHaveValue('')
  })

  it('handles result deep links without a stored profile', async () => {
    window.location.hash = '/results/1'
    mockApi()
    render(<App />)
    expect(
      screen.getByRole('heading', { name: 'Add your profile to continue' }),
    ).toBeVisible()
    expect(
      screen.getByRole('link', { name: 'Add student profile' }),
    ).toHaveAttribute('href', '#/profile?scholarship=1')
  })
})
