// Draw & Measure: circle and rectangle two-click tools complete on the
// second click and show a live rubber-band preview between clicks.

import { expect, test } from '@playwright/test'

test('circle draws from center+edge click with live preview', async ({ page }) => {
  test.setTimeout(90_000)
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.goto('/')
  await page.waitForFunction(() => {
    const m = (window as unknown as { __alert_map?: { isStyleLoaded: () => boolean } }).__alert_map
    return !!m && m.isStyleLoaded()
  }, undefined, { timeout: 45_000 })
  await page.waitForTimeout(500)

  await page.locator('.tool-btn', { hasText: 'Circle' }).click()
  const box = await page.locator('.map-container').boundingBox()
  const cx = box!.x + box!.width * 0.45
  const cy = box!.y + box!.height * 0.5

  // First click anchors the center; hovering must render the
  // rubber-band preview (this was invisible before — looked broken).
  await page.mouse.click(cx, cy)
  await page.waitForTimeout(300)
  await page.mouse.move(cx + 60, cy - 20)
  await page.waitForTimeout(200)
  await page.mouse.move(cx + 120, cy)
  await page.waitForTimeout(400)
  const previewFeatures = await page.evaluate(() => {
    const m = (window as unknown as {
      __alert_map: { querySourceFeatures: (id: string) => unknown[] }
    }).__alert_map
    return m.querySourceFeatures('draw-sketch').length
  })
  expect(previewFeatures).toBeGreaterThan(0)

  // Second click (edge) completes the circle immediately.
  await page.mouse.click(cx + 120, cy)
  await expect(page.locator('.drawn-item').filter({ hasText: 'CIRCLE' }))
    .toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.drawn-item').filter({ hasText: /r=\d/ }))
    .toContainText('km')
})

test('rectangle completes on second corner click', async ({ page }) => {
  test.setTimeout(90_000)
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.goto('/')
  await page.waitForFunction(() => {
    const m = (window as unknown as { __alert_map?: { isStyleLoaded: () => boolean } }).__alert_map
    return !!m && m.isStyleLoaded()
  }, undefined, { timeout: 45_000 })
  await page.waitForTimeout(500)

  await page.locator('.tool-btn', { hasText: 'Rectangle' }).click()
  const box = await page.locator('.map-container').boundingBox()
  await page.mouse.click(box!.x + box!.width * 0.55, box!.y + box!.height * 0.35)
  await page.waitForTimeout(400)
  await page.mouse.click(box!.x + box!.width * 0.7, box!.y + box!.height * 0.55)
  await expect(page.locator('.drawn-item').filter({ hasText: 'RECTANGLE' }))
    .toBeVisible({ timeout: 10_000 })
  await expect(page.locator('.drawn-item').filter({ hasText: /km²/ }))
    .toBeVisible()
})
