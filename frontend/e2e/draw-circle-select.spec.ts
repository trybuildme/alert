// Regression: a drawn circle must SURVIVE being selected (click inside)
// and deselected (click elsewhere). Selection is list-highlight +
// outline emphasis only — geometry never disappears.

import { expect, test } from '@playwright/test'

test('circle survives select and deselect clicks', async ({ page }) => {
  test.setTimeout(90_000)
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.goto('/')
  await page.waitForFunction(() => {
    const m = (window as unknown as { __noah_map?: { isStyleLoaded: () => boolean } }).__noah_map
    return !!m && m.isStyleLoaded()
  }, undefined, { timeout: 45_000 })
  await page.waitForTimeout(500)

  await page.locator('.tool-btn', { hasText: 'Circle' }).click()
  const box = await page.locator('.map-container').boundingBox()
  const cx = box!.x + box!.width * 0.45
  const cy = box!.y + box!.height * 0.5
  await page.mouse.click(cx, cy)
  await page.waitForTimeout(300)
  await page.mouse.click(cx + 150, cy)
  await page.waitForTimeout(800)

  const snap = () => page.evaluate(() => ({
    drawnCount: document.querySelectorAll('.drawn-item').length,
    fillFeatures: (window as unknown as {
      __noah_map: { querySourceFeatures: (id: string) => unknown[] }
    }).__noah_map.querySourceFeatures('draw-fill').length,
    selected: !!document.querySelector('.drawn-item.selected'),
  }))

  // Drawn and auto-selected; geometry rendered.
  const afterDraw = await snap()
  expect(afterDraw.drawnCount).toBe(1)

  // Click INSIDE the circle: stays selected, geometry stays.
  await page.mouse.click(cx + 60, cy)
  await page.waitForTimeout(600)
  const afterSelect = await snap()
  expect(afterSelect.drawnCount).toBe(1)
  expect(afterSelect.selected).toBe(true)
  expect(afterSelect.fillFeatures).toBeGreaterThan(0)

  // Click elsewhere on empty map: deselects but the circle STAYS.
  await page.mouse.click(box!.x + box!.width * 0.12, box!.y + box!.height * 0.88)
  await page.waitForTimeout(600)
  const afterDeselect = await snap()
  expect(afterDeselect.drawnCount).toBe(1)
  expect(afterDeselect.fillFeatures).toBeGreaterThan(0)
})
