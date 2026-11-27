import { expect, test, type Page } from '@playwright/test'

const reviewKey = 'browser-test-only-local-review-key-not-a-secret'
const northRidge = 'North Ridge Graduate Scholarship'
const lakeview = 'Lakeview Graduate Scholarship'

async function unlock(page: Page) {
  await page.goto('/#/review')
  await page.getByLabel('Local access key').fill(reviewKey)
  await page.getByRole('button', { name: 'Unlock review' }).click()
  await expect(page.getByRole('region', { name: 'Review queue' })).toBeVisible()
}

test('keeps local review data behind the access key', async ({ page, request }) => {
  const response = await request.get('/api/review/drafts')
  expect(response.status()).toBe(401)

  await page.goto('/#/review')
  await expect(page.getByLabel('Local access key')).toBeVisible()
  await expect(page.getByText(northRidge)).toHaveCount(0)
  await unlock(page)
  await expect(page.getByRole('button', { name: new RegExp(northRidge) })).toBeVisible()
  expect(
    await page.evaluate(() => [
      ...Object.values(localStorage),
      ...Object.values(sessionStorage),
    ]),
  ).not.toContain(reviewKey)
  await page.reload()
  await expect(page.getByLabel('Local access key')).toBeVisible()
  await expect(page.getByText(northRidge)).toHaveCount(0)
})

test('records a synthetic field decision and blocks publication of the pending draft', async ({
  page,
  request,
}) => {
  await unlock(page)
  await page.getByRole('button', { name: new RegExp(northRidge) }).click()
  const programmeField = page.locator('details').filter({
    has: page.getByText('Programme name', { exact: true }),
  })
  await programmeField.locator('summary').click()
  await expect(programmeField.locator('blockquote')).toHaveText(northRidge)
  await page.getByLabel('Reviewer name or ID').fill('Synthetic browser reviewer')
  await programmeField.getByLabel('Decision').selectOption('accepted')
  await programmeField.getByLabel('Reviewed value').fill(northRidge)
  await programmeField.getByRole('button', { name: 'Use extracted excerpt' }).click()
  await expect(programmeField.getByLabel('Source excerpt')).toHaveValue(northRidge)
  await programmeField.getByLabel('Field rationale').fill('Title matches the staged excerpt.')

  const write = page.waitForResponse((response) => {
    return response.url().includes('/fields/scholarship_name') &&
      response.request().method() === 'POST'
  })
  await programmeField.getByRole('button', { name: 'Save field decision' }).click()
  const saved = await write
  expect(saved.ok()).toBe(true)
  await expect(programmeField.locator('summary')).toContainText('Accepted')
  const latest = programmeField.getByRole('region', { name: 'Latest decision for Programme name' })
  await expect(latest).toContainText('Synthetic browser reviewer')
  await expect(latest).toContainText('Title matches the staged excerpt.')
  const draftUrl = new URL(saved.url())
  draftUrl.pathname = draftUrl.pathname.replace(/\/fields\/scholarship_name$/, '/publish')
  const publication = await request.post(draftUrl.toString(), {
    headers: {
      Authorization: `Bearer ${reviewKey}`,
      Origin: draftUrl.origin,
    },
    data: {
      reviewer: 'Synthetic browser reviewer',
      rationale: 'The pending draft must remain unpublished.',
      confirm: true,
    },
  })
  expect(publication.status()).toBe(409)
})

for (const [layout, size] of [
  ['desktop', { width: 1440, height: 960 }],
  ['mobile', { width: 390, height: 844 }],
] as const) {
  test(`shows staged evidence and conflicts on ${layout}`, async ({ page }, testInfo) => {
    await page.setViewportSize(size)
    await unlock(page)
    await page.getByRole('button', { name: new RegExp(lakeview) }).click()
    const stipends = page.getByRole('region', { name: 'Stipend evidence' })
    await expect(stipends).toContainText(/conflicting figures/i)
    await expect(stipends.locator('blockquote')).toHaveText([
      'Living stipend: CAD 2,500 per month during academic terms',
      'Living stipend: CAD 3,100 per month during academic terms',
    ])
    await page.getByRole('button', { name: 'Funding & dates' }).click()
    const livingStipend = page.locator('details').filter({
      has: page.getByText('Living stipend', { exact: true }),
    })
    await livingStipend.locator('summary').click()
    await expect(livingStipend.getByRole('option', { name: 'Accept', exact: true })).toBeDisabled()
    expect(
      await page.evaluate(() => document.documentElement.scrollWidth),
    ).toBeLessThanOrEqual(size.width)
    await page.evaluate(async () => { await document.fonts.ready })
    await page.screenshot({
      path: testInfo.outputPath(`review-${layout}.png`),
      fullPage: true,
    })
    await stipends.screenshot({ path: testInfo.outputPath(`review-${layout}-evidence.png`) })
  })
}
