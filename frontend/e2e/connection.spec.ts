import { expect, test } from '@playwright/test'

test('connects React to the real FastAPI server through the proxy', async ({ page }, testInfo) => {
  const pageErrors: string[] = []
  page.on('pageerror', (error) => pageErrors.push(error.message))
  await page.goto('/')

  await expect(page).toHaveTitle('Scholarship Hunter AI')
  await expect(page.getByRole('status')).toContainText('API connected')
  await page.getByRole('button', { name: 'Check again' }).click()
  await expect(page.getByRole('status')).toContainText('API connected')

  const response = await page.request.get('/api/health')
  expect(response.status()).toBe(200)
  expect(await response.json()).toEqual({ status: 'ok', service: 'scholarship-hunter-ai' })
  expect(pageErrors).toEqual([])
  await page.screenshot({ path: testInfo.outputPath('desktop.png'), fullPage: true })
})

test('keeps the connection check usable on mobile', async ({ page }, testInfo) => {
  await page.setViewportSize({ width: 375, height: 812 })
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('API connected')
  await expect(page.getByRole('button', { name: 'Check again' })).toBeInViewport()
  expect(await page.evaluate(() => document.documentElement.scrollWidth)).toBeLessThanOrEqual(375)
  await page.screenshot({ path: testInfo.outputPath('mobile.png'), fullPage: true })
})

test('times out a stalled check and reconnects when retried', async ({ page }) => {
  await page.route('**/api/health', () => {})
  await page.goto('/')
  await expect(page.getByRole('status')).toContainText('Connection check failed', { timeout: 8000 })

  await page.unroute('**/api/health')
  await page.getByRole('button', { name: 'Check again' }).click()
  await expect(page.getByRole('status')).toContainText('API connected')
})
