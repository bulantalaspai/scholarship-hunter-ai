import { expect, test } from '@playwright/test'
import type { Page } from '@playwright/test'

const daadName =
  'Study Scholarships - Master Studies for All Academic Disciplines'
const smaccsName = 'SMACCs Erasmus Mundus Joint Master (EMJM) Scholarships'

async function fillProfile(page: Page, funding = 'any_funding') {
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
  await expect(page.getByText('1 opportunity in this search')).toBeVisible()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toHaveCount(0)
  await page.screenshot({
    path: testInfo.outputPath('explorer-desktop.png'),
    fullPage: true,
  })

  await page
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
  await page.goto('/#/explore')
  await page.getByLabel('Destination country').fill('Germany')
  await page.getByRole('button', { name: 'Apply filters' }).click()
  await expect(
    page.getByRole('heading', { name: daadName, exact: true }),
  ).toBeVisible()
  await expect(
    page.getByRole('heading', { name: smaccsName, exact: true }),
  ).toHaveCount(0)
  await page
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
  const unresolved = page
    .getByRole('heading', { name: /^Needs verification \(1\)/ })
    .locator('..')
  const ineligible = page
    .getByRole('heading', { name: /^Ineligible \(1\)/ })
    .locator('..')
  await expect(
    unresolved.getByRole('link', { name: smaccsName, exact: true }),
  ).toBeVisible()
  await expect(
    ineligible.getByRole('link', { name: daadName, exact: true }),
  ).toBeVisible()
  await expect(page.getByRole('heading', { name: /^Eligible \(/ })).toHaveCount(
    0,
  )
  await expect(
    ineligible.getByText(/Published funding: partially funded/),
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
