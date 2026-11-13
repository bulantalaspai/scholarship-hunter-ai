import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type { AgentResponse } from '../src/agent'
import type {
  EligibilityResult,
  MatchResult,
  ScholarshipPage,
  StudentProfile,
} from '../src/types'

const profile: StudentProfile = {
  nationality: 'Kazakhstan',
  degree_level: 'bachelor',
  degree_completed: true,
  field_of_study: 'Computer Science',
  gpa: 3.5,
  gpa_scale: 4,
  ielts_overall: 7,
  intended_start_year: 2027,
  funding_preference: 'any_funding',
}

async function openAgentWithProfile(page: Page) {
  await page.goto('/#/agent')
  await page
    .getByRole('link', { name: 'Add student profile', exact: true })
    .click()
  await expect(page).toHaveURL(/#\/profile\?mode=ai$/)
  await page
    .getByLabel('Nationality', { exact: true })
    .fill(profile.nationality)
  await page
    .getByLabel('Degree level', { exact: true })
    .selectOption(profile.degree_level)
  await page
    .getByLabel('Degree completion', { exact: true })
    .selectOption('true')
  await page
    .getByLabel('Field of study', { exact: true })
    .fill(profile.field_of_study)
  await page.getByLabel('GPA', { exact: true }).fill('3.5')
  await page.getByLabel('GPA scale', { exact: true }).fill('4')
  await page.getByLabel('IELTS overall', { exact: true }).fill('7')
  await page.getByLabel('Intended start year', { exact: true }).fill('2027')
  await page
    .getByLabel('Funding preference', { exact: true })
    .selectOption('any_funding')
  await page
    .getByRole('button', { name: 'Continue to local AI', exact: true })
    .click()
  await expect(
    page.getByRole('heading', {
      name: 'Local AI recommendations',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page
      .getByRole('navigation', { name: 'Main navigation' })
      .getByRole('link', { name: 'Local AI', exact: true }),
  ).toHaveAttribute('aria-current', 'page')
}

test('requests local AI explicitly and renders a mocked plan with a real deterministic assessment', async ({
  page,
}, testInfo) => {
  // Only the AI endpoint is simulated. Catalogue and eligibility still use the real test API.
  const catalogueResponse = await page.request.get(
    '/api/scholarships?field=Engineering',
  )
  expect(catalogueResponse.ok()).toBe(true)
  const catalogue: ScholarshipPage = await catalogueResponse.json()
  const scholarship = catalogue.items[0]
  expect(scholarship.scholarship_name).toContain('SMACCs')
  const checkResponse = await page.request.post('/api/eligibility/check', {
    data: { scholarship_id: scholarship.id, profile },
  })
  expect(checkResponse.ok()).toBe(true)
  const assessment: EligibilityResult = await checkResponse.json()
  expect(assessment.status).toBe('needs_verification')
  const response: AgentResponse = {
    status: 'completed',
    model: 'qwen3:4b-instruct',
    evaluated_on: assessment.evaluated_on,
    steps: 3,
    tool_calls: 2,
    recommendations: [
      {
        assessment,
        ranking_reasons: ['Eligibility group: needs_verification.'],
      },
    ],
    message:
      'A source-backed candidate was selected using deterministic checks.',
    warnings: ['Missing requirements still need official confirmation.'],
    tool_trace: [
      {
        step: 1,
        name: 'search_scholarships',
        status: 'ok',
        arguments: { field: 'Engineering' },
        summary: 'Retrieved one catalogue candidate.',
        source_url: null,
        fetched_at: null,
      },
      {
        step: 2,
        name: 'rank_scholarships',
        status: 'ok',
        arguments: { scholarship_ids: [scholarship.id] },
        summary: 'Ranked one programme without changing eligibility.',
        source_url: null,
        fetched_at: null,
      },
    ],
    disclaimer: assessment.disclaimer,
  }
  const requests: unknown[] = []
  await page.route('**/api/agent/recommend', async (route) => {
    requests.push(route.request().postDataJSON())
    await route.fulfill({ json: response })
  })
  await openAgentWithProfile(page)
  expect(requests).toEqual([])
  await page
    .getByLabel('What would you like to find?')
    .fill('Find Engineering scholarships and explain missing evidence.')
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  const output = page.getByRole('region', { name: 'Local AI response' })
  await expect(
    output.getByText(response.message, { exact: true }),
  ).toBeVisible()
  const result = output.getByRole('region', { name: 'Eligibility assessment' })
  await expect(
    result.getByRole('heading', {
      name: scholarship.scholarship_name,
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    result.getByText('Needs verification', { exact: true }).first(),
  ).toBeVisible()
  await expect(result.getByText('Eligible', { exact: true })).toHaveCount(0)
  await expect(
    result.getByRole('link', { name: /View official source/ }).first(),
  ).toHaveAttribute('href', scholarship.official_source_url)
  await expect(
    output.getByRole('heading', { name: 'Step 1: search scholarships' }),
  ).toBeVisible()
  await expect(
    output.getByRole('heading', { name: 'Step 2: rank scholarships' }),
  ).toBeVisible()
  await expect(output.getByText(/2 of 8 tool calls/)).toBeVisible()
  expect(requests).toEqual([
    {
      profile,
      goal: 'Find Engineering scholarships and explain missing evidence.',
    },
  ])
  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([])
  await page.screenshot({
    path: testInfo.outputPath('local-ai-results.png'),
    fullPage: true,
  })
})

test('shows a separately labeled deterministic fallback after the model abstains', async ({
  page,
}, testInfo) => {
  const matchingResponse = await page.request.post('/api/eligibility/matches', {
    data: { profile, page_size: 10 },
  })
  expect(matchingResponse.ok()).toBe(true)
  const matches: MatchResult = await matchingResponse.json()
  const candidate = matches.needs_verification[0]
  expect(candidate.assessment.status).toBe('needs_verification')
  const response: AgentResponse = {
    status: 'no_matches',
    model: 'qwen3:4b-instruct',
    evaluated_on: candidate.assessment.evaluated_on,
    steps: 3,
    tool_calls: 1,
    recommendations: [],
    fallback_recommendations: [candidate],
    fallback_reason:
      'The model returned no grounded selection. Deterministic checks identified retrieved candidates requiring verification.',
    message: 'The model selected no grounded recommendations.',
    warnings: ['A model selection failed grounding validation.'],
    tool_trace: [
      {
        step: 1,
        name: 'search_scholarships',
        status: 'ok',
        arguments: { field: 'Computer Science' },
        summary: 'Retrieved catalogue candidates.',
        source_url: null,
        fetched_at: null,
      },
    ],
    disclaimer: candidate.assessment.disclaimer,
  }
  await page.route('**/api/agent/recommend', (route) =>
    route.fulfill({ json: response }),
  )
  await openAgentWithProfile(page)
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  const fallback = page.getByRole('region', {
    name: 'Deterministic candidates to verify',
  })
  await expect(fallback).toBeVisible()
  await expect(
    fallback.getByRole('heading', {
      name: candidate.assessment.scholarship_name,
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    fallback.getByText('Needs verification', { exact: true }).first(),
  ).toBeVisible()
  await expect(fallback.getByText('Eligible', { exact: true })).toHaveCount(0)
  await expect(
    fallback.getByRole('link', { name: /View official source/ }).first(),
  ).toHaveAttribute('href', candidate.assessment.official_source_url)
  await expect(page.getByText(response.message, { exact: true })).toBeVisible()
  await expect(page.getByText(/1 of 8 tool calls/)).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Step 1: search scholarships' }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Step 2: rank scholarships' }),
  ).toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('deterministic-candidates.png'),
    fullPage: true,
  })
})

test('keeps real deterministic matching available during a simulated Ollama outage', async ({
  page,
}) => {
  const matchingResponse = await page.request.post('/api/eligibility/matches', {
    data: { profile, page_size: 10 },
  })
  expect(matchingResponse.ok()).toBe(true)
  const matches: MatchResult = await matchingResponse.json()
  await page.route('**/api/agent/recommend', (route) =>
    route.fulfill({
      status: 503,
      json: {
        detail:
          'Ollama is unavailable. The catalogue and deterministic checks remain available.',
      },
    }),
  )
  await openAgentWithProfile(page)
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  await expect(page.getByRole('alert')).toContainText('HTTP 503')
  await page
    .getByRole('link', {
      name: 'Continue with deterministic matches',
      exact: true,
    })
    .click()
  await expect(
    page.getByRole('heading', {
      name: 'Your scholarship matches',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', {
      name: `Needs verification (${matches.counts.needs_verification})`,
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('link', {
      name: 'SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships',
      exact: true,
    }),
  ).toBeVisible()
})

test('retains real catalogue candidates in a typed model outage response', async ({
  page,
}) => {
  const matchingResponse = await page.request.post('/api/eligibility/matches', {
    data: { profile, page_size: 100 },
  })
  expect(matchingResponse.ok()).toBe(true)
  const matches: MatchResult = await matchingResponse.json()
  const candidates = matches.needs_verification.slice(0, 3)
  expect(candidates).toHaveLength(3)
  const response: AgentResponse = {
    status: 'model_error',
    model_error: 'unavailable',
    model: 'qwen3:4b-instruct',
    evaluated_on: candidates[0].assessment.evaluated_on,
    steps: 1,
    tool_calls: 0,
    recommendations: [],
    discovery_candidates: candidates,
    discovery_candidate_ids: matches.needs_verification.map(
      (item) => item.assessment.scholarship_id,
    ),
    discovery_scope: 'catalogue',
    model_explanations: [],
    fallback_recommendations: candidates,
    fallback_reason: 'These candidates require official verification.',
    message: 'Local inference is unavailable. Deterministic discovery completed.',
    warnings: [],
    tool_trace: [],
    disclaimer: candidates[0].assessment.disclaimer,
  }
  await page.route('**/api/agent/recommend', (route) =>
    route.fulfill({ json: response }),
  )
  await openAgentWithProfile(page)
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Local AI could not finish' }),
  ).toBeVisible()
  const retained = page.getByRole('region', {
    name: 'Deterministic discovery candidates',
  })
  await expect(
    retained.getByRole('region', { name: 'Eligibility assessment' }),
  ).toHaveCount(3)
  for (const candidate of candidates) {
    await expect(
      retained.getByRole('heading', {
        name: candidate.assessment.scholarship_name,
        exact: true,
      }),
    ).toBeVisible()
  }
  await expect(
    page.getByRole('region', { name: 'Eligibility assessment' }),
  ).toHaveCount(3)
  await expect(page.getByText('No tool calls were executed.')).toBeVisible()
})

test('retains the named negative target and the actual deadline failure', async ({
  page,
}) => {
  const catalogueResponse = await page.request.get(
    '/api/scholarships?country=Japan',
  )
  expect(catalogueResponse.ok()).toBe(true)
  const catalogue: ScholarshipPage = await catalogueResponse.json()
  const target = catalogue.items.find((item) =>
    item.scholarship_name.startsWith('MEXT Research Students'),
  )!
  expect(target).toBeDefined()
  const checkResponse = await page.request.post('/api/eligibility/check', {
    data: { scholarship_id: target.id, profile },
  })
  expect(checkResponse.ok()).toBe(true)
  const assessment: EligibilityResult = await checkResponse.json()
  expect(assessment.status).toBe('ineligible')
  expect(assessment.failed_requirements).toContain('deadline')
  const failure = assessment.requirements.find(
    (item) => item.requirement === 'deadline',
  )!
  const response: AgentResponse = {
    status: 'no_matches',
    model: 'qwen3:4b-instruct',
    evaluated_on: assessment.evaluated_on,
    steps: 1,
    tool_calls: 0,
    recommendations: [],
    discovery_candidates: [{ assessment, ranking_reasons: [] }],
    discovery_candidate_ids: [target.id],
    discovery_scope: 'named_target',
    model_explanations: [],
    message: 'The requested programme has a confirmed requirement failure.',
    warnings: [],
    tool_trace: [],
    disclaimer: assessment.disclaimer,
  }
  await page.route('**/api/agent/recommend', (route) =>
    route.fulfill({ json: response }),
  )
  await openAgentWithProfile(page)
  await page.getByLabel('What would you like to find?').fill(
    `Assess ${target.scholarship_name} for my profile.`,
  )
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  const retained = page.getByRole('region', {
    name: 'Requested programme assessments',
  })
  await expect(
    retained.getByRole('heading', {
      name: target.scholarship_name,
      exact: true,
    }),
  ).toBeVisible()
  await expect(retained.getByText(failure.explanation, { exact: true })).toBeVisible()
  await expect(retained.getByText('Ineligible', { exact: true }).first()).toBeVisible()
  await expect(retained.getByText('Eligible', { exact: true })).toHaveCount(0)
})

test('supports a mobile AI profile handoff and forgets the profile on refresh', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 })
  let calls = 0
  await page.route('**/api/agent/recommend', () => {
    calls += 1
  })
  await openAgentWithProfile(page)
  await expect(page.getByLabel('What would you like to find?')).toBeVisible()
  await expect(
    page.getByRole('button', {
      name: 'Generate AI recommendations',
      exact: true,
    }),
  ).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375)
  expect(calls).toBe(0)
  await page.screenshot({
    path: testInfo.outputPath('local-ai-mobile.png'),
    fullPage: true,
  })
  await page.reload()
  await expect(
    page.getByRole('heading', {
      name: 'Add your profile for local AI',
      exact: true,
    }),
  ).toBeVisible()
  expect(calls).toBe(0)
})

test('can leave a pending AI request and continue browsing the real catalogue', async ({
  page,
}) => {
  await page.route('**/api/agent/recommend', () => {})
  await openAgentWithProfile(page)
  await page
    .getByRole('button', { name: 'Generate AI recommendations', exact: true })
    .click()
  await expect(page.getByRole('status')).toContainText(
    'This can take up to 90 seconds',
  )
  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'Explore scholarships', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Scholarship explorer', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', {
      name: 'SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Local AI is unavailable', exact: true }),
  ).toHaveCount(0)
})
