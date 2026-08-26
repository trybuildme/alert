// Flood monitoring: clicking a live rain-station marker must open the
// info popup (readings, trend, source attribution).

import { expect, test } from '@playwright/test'

const STATION_FEATURE = {
  type: 'Feature',
  id: 'rain-mactan-cebu',
  properties: {
    uid: 'rain-mactan-cebu', name: 'Mactan (Cebu) Synoptic',
    kind: 'rainfall', provider: 'open-meteo',
    level: 'NORMAL', data_status: 'live',
    latest: { metric: 'rainfall_mm_h', value: 1.4,
              observed_at: new Date().toISOString(), quality: 'ok',
              source: 'open-meteo', age_minutes: 5 },
    mmh: 1.4, mmhLabel: '1.4',
  },
  geometry: { type: 'Point', coordinates: [124.0167, 10.3167] },
}

test('rain station click opens info popup', async ({ page }) => {
  test.setTimeout(90_000)
  // Catch-alls FIRST (reverse-registration precedence).
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.route('**/api/flood/stations**', (r) =>
    r.fulfill({ json: {
      type: 'FeatureCollection', features: [STATION_FEATURE],
      source: 'noah-flood-monitoring',
    } }))
  await page.route('**/api/flood/observations/**', (r) =>
    r.fulfill({ json: {
      station: { id: 'rain-mactan-cebu', name: 'Mactan (Cebu) Synoptic',
                 kind: 'rainfall', latitude: 10.3167, longitude: 124.0167,
                 river_basin: 'Cebu', provider: 'open-meteo' },
      series: {
        rainfall_mm_h: [
          { observed_at: '2026-08-26T04:00:00Z', value: 0.5,
            quality: 'ok', source: 'open-meteo' },
          { observed_at: '2026-08-26T05:00:00Z', value: 1.4,
            quality: 'ok', source: 'open-meteo' },
        ],
      },
      hours: 48,
    } }))
  page.on('pageerror', (err) => console.log('PAGEERROR:', err.message))

  await page.goto('/')
  await page.waitForFunction(() => {
    const m = (window as unknown as {
      __noah_map?: { isStyleLoaded: () => boolean;
        getLayer: (id: string) => { visibility?: string } | undefined }
    }).__noah_map
    return !!m && m.isStyleLoaded() &&
      m.getLayer('flood-rain-circle')?.visibility === 'visible'
  }, undefined, { timeout: 45_000 })

  // Jump to Cebu and click the marker.
  await page.evaluate(() => {
    const m = (window as unknown as {
      __noah_map: { jumpTo: (o: object) => void }
    }).__noah_map
    m.jumpTo({ center: [124.0167, 10.3167], zoom: 10 })
  })
  await page.waitForTimeout(600)
  const box = await page.locator('.map-container').boundingBox()
  const pt = await page.evaluate(() => {
    const m = (window as unknown as {
      __noah_map: { project: (ll: number[]) => { x: number; y: number } }
    }).__noah_map
    const p = m.project([124.0167, 10.3167])
    return { x: p.x, y: p.y }
  })
  const probe = await page.evaluate(([x, y]) => {
    const m = (window as any).__noah_map
    const hits = m.queryRenderedFeatures([x, y])
    return {
      all: hits.map((f: any) => f.layer.id),
      flood: hits.filter((f: any) => f.layer.id.startsWith('flood')).length,
      vis: m.getLayer('flood-rain-circle')?.visibility,
      srcFeatures: m.querySourceFeatures('flood-rain-stations').length,
    }
  }, [Math.round(pt.x), Math.round(pt.y)])
  console.log('PROBE:', JSON.stringify(probe))

  await page.mouse.click(box!.x + pt.x, box!.y + pt.y)
  await page.waitForTimeout(800)

  const popup = page.getByTestId('flood-popup')
  await expect(popup).toBeVisible({ timeout: 10_000 })
  await expect(popup).toContainText('Mactan (Cebu) Synoptic')
  await expect(popup).toContainText('Rainfall (1 h)')
  await expect(popup).toContainText(/2\.80|↑/)   // reading or trend arrow
})
