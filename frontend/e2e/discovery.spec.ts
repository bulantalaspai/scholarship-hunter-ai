import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'
import type {
  FundingPreference,
  MatchResult,
  ScholarshipPage,
  StudentProfile,
} from '../src/types'

const daadName =
  'Study Scholarships - Master Studies for All Academic Disciplines'
const smaccsName = 'SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships'

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

function scholarshipCard(page: Page, name: string) {
  return page.getByRole('article').filter({
    has: page.getByRole('heading', { name, exact: true }),
  })
}

async function catalogueSearch(page: Page, query: string): Promise<ScholarshipPage> {
  const response = await page.request.get(`/api/scholarships?${query}&page_size=10`)
  expect(response.ok()).toBe(true)
  return response.json()
}

async function fillProfile(
  page: Page,
  funding: FundingPreference = 'any_funding',
) {
  await page.getByLabel('Nationality', { exact: true }).fill('Kazakhstan')
  await page
    .getByLabel('Degree level', { exact: true })
    .selectOption('bachelor')
  await page
    .getByLabel('Degree completion', { exact: true })
    .selectOption('true')
  await page
    .getByLabel('Field of study', { exact: true })
    .fill('Computer Science')
  await page.getByLabel('GPA', { exact: true }).fill('3.5')
  await page.getByLabel('GPA scale', { exact: true }).fill('4')
  await page.getByLabel('IELTS overall', { exact: true }).fill('7')
  await page.getByLabel('Intended start year', { exact: true }).fill('2027')
  await page
    .getByLabel('Funding preference', { exact: true })
    .selectOption(funding)
}

test('searches from home and opens a real source-backed scholarship', async ({
  page,
}, testInfo) => {
  const search = await catalogueSearch(page, 'field=Engineering')
  await page.goto('/')
  await page.getByLabel('What would you like to study?').fill('Engineering')
  await page
    .getByRole('button', { name: 'Explore scholarships', exact: true })
    .click()

  await expect(page).toHaveURL(/#\/explore\?field=Engineering$/)
  await expect(
    page.getByRole('heading', { name: 'Scholarship explorer', exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: smaccsName, exact: true }),
  ).toBeVisible()
  await expect(
    page.getByText(
      `${search.total} ${search.total === 1 ? 'opportunity' : 'opportunities'} in this search`,
      { exact: true },
    ),
  ).toBeVisible()
  await expect(page.getByRole('article')).toHaveCount(search.items.length)
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('explorer-desktop.png'),
    fullPage: true,
  })

  await scholarshipCard(page, smaccsName)
    .getByRole('link', { name: 'View scholarship', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { level: 1, name: smaccsName }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: 'Requirements and important notes' }),
  ).toBeVisible()
  await expect(
    page.getByText(/IELTS is one evidence route, not universally mandatory/),
  ).toBeVisible()
  await expect(
    page.getByRole('link', { name: /View official source/ }).first(),
  ).toHaveAttribute('href', 'https://www.smaccs.eu/practical/scholarships/')
  await page.screenshot({
    path: testInfo.outputPath('scholarship-details.png'),
    fullPage: true,
  })
})

test('filters Germany and checks eligibility without turning unknown conditions into a pass', async ({
  page,
}, testInfo) => {
  const search = await catalogueSearch(page, 'country=Germany')
  await page.goto('/#/explore')
  await page.getByLabel('Destination country').fill('Germany')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: smaccsName, exact: true }),
  ).toHaveCount(0)
  await expect(page.getByRole('article')).toHaveCount(search.items.length)
  await scholarshipCard(page, daadName)
    .getByRole('link', { name: 'View scholarship', exact: true })
    .click()
  await expect(
    page.getByText('Minimum GPA', { exact: true }).locator('..'),
  ).toContainText('Not confirmed')
  await page
    .getByRole('link', { name: 'Check my eligibility', exact: true })
    .click()
  await fillProfile(page)
  await page
    .getByRole('button', { name: 'Check my eligibility', exact: true })
    .click()

  const assessment = page.getByRole('region', {
    name: 'Eligibility assessment',
  })
  await expect(
    assessment.getByRole('heading', { name: daadName }),
  ).toBeVisible()
  await expect(
    assessment.getByText('Needs verification', { exact: true }).first(),
  ).toBeVisible()
  await expect(
    assessment.getByRole('heading', { name: 'Admission eligibility' }),
  ).toBeVisible()
  await expect(
    assessment.getByRole('heading', { name: 'Funding eligibility' }),
  ).toBeVisible()
  await expect(
    assessment.getByRole('heading', { name: 'Application availability' }),
  ).toBeVisible()
  await expect(
    assessment.getByRole('heading', { name: 'Information still to verify' }),
  ).toBeVisible()
  await expect(
    assessment.getByText(/not an admission decision or a scholarship award/),
  ).toBeVisible()
  await expect(assessment.getByText('Eligible', { exact: true })).toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('eligibility-results.png'),
    fullPage: true,
  })
})

test('separates unresolved matches from confirmed full-funding preference failures', async ({
  page,
}, testInfo) => {
  const response = await page.request.post('/api/eligibility/matches', {
    data: {
      profile: { ...profile, funding_preference: 'fully_funded' },
      page_size: 100,
    },
  })
  expect(response.ok()).toBe(true)
  const matches: MatchResult = await response.json()
  expect(matches.counts.eligible).toBe(0)
  const ordered = [
    ...matches.eligible,
    ...matches.needs_verification,
    ...matches.ineligible,
  ]
  expect(ordered).toHaveLength(matches.total)
  const daadIndex = ordered.findIndex(
    (item) => item.assessment.scholarship_name === daadName,
  )
  expect(daadIndex).toBeGreaterThanOrEqual(0)
  // The UI pages the global ranking in groups of ten, unlike this full snapshot.
  const daadPage = Math.floor(daadIndex / 10) + 1
  await page.goto('/#/profile')
  await fillProfile(page, 'fully_funded')
  await page
    .getByRole('button', { name: 'Find my matches', exact: true })
    .click()

  await expect(
    page.getByRole('heading', {
      name: 'Your scholarship matches',
      exact: true,
    }),
  ).toBeVisible()
  await expect(
    page.getByText(/No fully verified eligible programmes were found/),
  ).toBeVisible()
  for (const [status, label] of [
    ['eligible', 'Eligible'],
    ['needs_verification', 'Needs verification'],
    ['ineligible', 'Ineligible'],
  ] as const) {
    const summary = page
      .locator('.match-summary')
      .getByText(label, { exact: true })
      .locator('..')
    await expect(summary.locator('strong')).toHaveText(
      String(matches.counts[status]),
    )
  }
  const unresolved = page
    .getByRole('heading', {
      name: `Needs verification (${matches.counts.needs_verification})`,
      exact: true,
    })
    .locator('..')
  await expect(
    unresolved.getByRole('link', { name: smaccsName, exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: /^Eligible \(/ })).toHaveCount(
    0,
  )
  for (let next = 2; next <= daadPage; next += 1) {
    const pagination = page.getByRole('navigation', { name: 'Results pages' })
    await pagination.getByRole('link', { name: 'Next page', exact: true }).click()
    await expect(page).toHaveURL(new RegExp(`#/matches\\?page=${next}$`))
    await expect(
      pagination.getByText(`Page ${next} of ${Math.ceil(matches.total / 10)}`, {
        exact: true,
      }),
    ).toBeVisible()
  }
  const ineligible = page
    .getByRole('heading', {
      name: `Ineligible (${matches.counts.ineligible})`,
      exact: true,
    })
    .locator('..')
  const daad = ineligible.getByRole('article').filter({
    has: page.getByRole('link', { name: daadName, exact: true }),
  })
  await expect(daad.getByRole('link', { name: daadName, exact: true })).toBeVisible()
  await expect(
    daad.getByText(/Published funding: partially funded/),
  ).toBeVisible()
  await page.screenshot({
    path: testInfo.outputPath('ranked-matches.png'),
    fullPage: true,
  })
})

test('shows an empty search and lets users return to the catalogue', async ({
  page,
}) => {
  await page.goto('/#/explore?country=NoSuchDestination')
  await expect(
    page.getByRole('heading', { name: 'No scholarships found', exact: true }),
  ).toBeVisible()
  await expect(page.getByText('0 opportunities in this search')).toBeVisible()
  await page
    .getByRole('link', { name: 'Browse the full catalogue', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: smaccsName, exact: true }),
  ).toBeVisible()
})

test('handles a real detail 404 without fabricating a record', async ({
  page,
}) => {
  await page.goto('/#/scholarships/999999')
  await expect(page.getByRole('alert')).toContainText('Scholarship not found')
  await expect(page.getByRole('heading', { name: daadName })).toHaveCount(0)
  await page
    .getByRole('link', { name: 'Back to explorer', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
})

test('keeps profiles only in memory and requires a new profile after refresh', async ({
  page,
}) => {
  await page.goto('/#/profile')
  await fillProfile(page)
  await page
    .getByRole('button', { name: 'Find my matches', exact: true })
    .click()
  await expect(
    page.getByRole('heading', {
      name: 'Your scholarship matches',
      exact: true,
    }),
  ).toBeVisible()

  expect(await page.evaluate(() => Object.keys(localStorage))).toEqual([])
  expect(await page.evaluate(() => Object.keys(sessionStorage))).toEqual([])
  await page.reload()
  await expect(
    page.getByRole('heading', {
      name: 'Add your profile to continue',
      exact: true,
    }),
  ).toBeVisible()
  await page
    .getByRole('link', { name: 'Add student profile', exact: true })
    .click()
  await expect(page.getByLabel('Nationality', { exact: true })).toHaveValue('')
  await expect(page.getByLabel('GPA', { exact: true })).toHaveValue('')
})

test('supports a mobile explorer and profile without horizontal overflow', async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/#/explore')
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
  await expect(page.getByLabel('Destination country')).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375)
  await page.screenshot({
    path: testInfo.outputPath('explorer-mobile.png'),
    fullPage: true,
  })

  await page
    .getByRole('navigation', { name: 'Main navigation' })
    .getByRole('link', { name: 'My profile', exact: true })
    .click()
  await expect(
    page.getByRole('heading', { name: 'Your student profile', exact: true }),
  ).toBeVisible()
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(375)
  await page.screenshot({
    path: testInfo.outputPath('profile-mobile.png'),
    fullPage: true,
  })
})

test('supports skip navigation and submitting a search with the keyboard', async ({
  page,
}) => {
  await page.goto('/')
  await page.getByRole('link', { name: 'Skip to content', exact: true }).focus()
  await page.keyboard.press('Enter')
  await expect(page.locator('#main-content')).toBeFocused()
  await page.getByLabel('What would you like to study?').fill('Engineering')
  await page.getByLabel('What would you like to study?').press('Enter')
  await expect(
    page.getByRole('heading', { name: smaccsName, exact: true }),
  ).toBeVisible()
  await expect(page.locator('#main-content')).toBeFocused()
})

test('recovers from an explicit simulated catalogue outage', async ({
  page,
}) => {
  await page.route('**/api/scholarships?**', (route) =>
    route.fulfill({ status: 503, body: 'Temporarily unavailable' }),
  )
  await page.goto('/#/explore')
  await expect(page.getByRole('alert')).toContainText('HTTP 503')
  await page.unroute('**/api/scholarships?**')
  await page.getByRole('button', { name: 'Try again', exact: true }).click()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
})
