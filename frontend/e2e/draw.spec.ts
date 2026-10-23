// Draw & Measure: line A→B produces the elevation profile popup
// (rectangle card over the map with diagram + measurements).

import { expect, test, type Page } from '@playwright/test'

test('line A->B opens the elevation profile popup', async ({ page }) => {
  test.setTimeout(90_000)
  await mockBackend(page)
  await page.goto('/')
  await page.waitForFunction(() => {
    const m = (window as unknown as { __alert_map?: { isStyleLoaded: () => boolean } }).__alert_map
    return !!m && m.isStyleLoaded()
  }, undefined, { timeout: 45_000 })
  await page.waitForTimeout(500)

  await page.getByRole('button', { name: 'Line' }).click()
  const box = await page.locator('.map-container').boundingBox()
  await page.mouse.click(box!.x + box!.width * 0.4, box!.y + box!.height * 0.5)
  await page.waitForTimeout(300)
  await page.mouse.click(box!.x + box!.width * 0.6, box!.y + box!.height * 0.6)
  await page.waitForTimeout(300)
  await page.getByRole('button', { name: 'Finish' }).click()

  const popup = page.getByTestId('profile-popup')
  await expect(popup).toBeVisible({ timeout: 10_000 })
  await expect(popup).toContainText('ELEVATION PROFILE')
  // measurements + diagram share the one rectangle card
  await expect(popup).toContainText('Gain / Loss')
  await expect(popup).toContainText('Straight A to B')
  expect(await popup.locator('svg[aria-label="Elevation cross-section"]').count())
    .toBe(1)
})

async function mockBackend(page: Page) {
  // Catch-alls FIRST (Playwright resolves overlaps in REVERSE order).
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.route('**/api/elevation/profile**', (r) =>
    r.fulfill({ json: {
      points: [], count: 80, cached: false,
      elevations_m: Array.from({ length: 80 }, (_, i) =>
        Math.round(100 + 120 * Math.sin(i / 5))),
      source: 'open-meteo-copernicus-dem-glo-90', resolution_m: 90,
      disclaimer: 'real',
    } }))
}
