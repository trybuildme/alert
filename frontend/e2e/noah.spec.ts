// NOAH critical-flow E2E specs. Hermetic by design: the Vite dev
// server runs, every backend endpoint is intercepted with fixtures,
// so the full UI shell (map, panels, bell, replay) is exercised
// without a backend or live hazard feeds.

import { expect, test, type Page } from '@playwright/test'

const RECENT_QUAKE = {
  type: 'FeatureCollection',
  features: [{
    type: 'Feature',
    id: 'usgs:test1',
    properties: {
      uid: 'usgs:test1', provider: 'usgs', provider_event_id: 'test1',
      origin_time: new Date().toISOString(),
      magnitude: 5.4, magnitude_type: 'mww', depth_km: 32,
      place: 'Test Trench', region: 'Test Region', status: 'reviewed',
      source_url: 'https://example.gov', detected_at: new Date().toISOString(),
      updated_at: new Date().toISOString(),
    },
    geometry: { type: 'Point', coordinates: [122.5, 15.2] },
  }],
}

async function mockBackend(page: Page) {
  // NOTE: Playwright resolves overlapping routes in REVERSE registration
  // order — the generic catch-all must be registered FIRST so the
  // specific mocks below take precedence.
  await page.route('**/tiles/**', (r) => r.fulfill({ status: 204 }))
  await page.route('**/api/**', (r) =>
    r.fulfill({ json: { source: 'unavailable', features: [] } }))
  await page.route('**/api/earthquakes/recent**', (r) =>
    r.fulfill({ json: RECENT_QUAKE }))
  await page.route('**/api/earthquakes/alerts**', (r) =>
    r.fulfill({ json: { alerts: [] } }))
  await page.route('**/api/volcanoes/phivolcs-site*kanlaon*', (r) =>
    r.fulfill({ json: VOLCANO_DETAIL }))
  await page.route('**/api/volcanoes', (r) =>
    r.fulfill({ json: { type: 'FeatureCollection', features: [VOLCANO_FEATURE] } }))
}

const VOLCANO_FEATURE = {
  type: 'Feature',
  id: 'phivolcs-site:kanlaon',
  properties: {
    uid: 'phivolcs-site:kanlaon', name: 'Kanlaon',
    elevation_m: 2435, active_now: true,
    note: 'Negros Island — intermittent eruptions since June 2024',
    provider: 'phivolcs-registry', last_known_eruption: '2024',
  },
  geometry: { type: 'Point', coordinates: [123.132, 10.4119] },
}

const VOLCANO_DETAIL = {
  ...VOLCANO_FEATURE,
  active_status_as_of: '2026-08',
  disclaimer: 'snapshot — not live alert levels',
  seismicity: {
    available: true, radius_km: 30, days: 7,
    total_7d: 12, count_24h: 3,
    strongest: {
      magnitude: 4.6, place: '5 km SW of Kanlaon',
      origin_time: new Date().toISOString(), depth_km: 8,
    },
  },
}

test.beforeEach(async ({ page }) => {
  await mockBackend(page)
})

test('app shell loads with brand, topbar and layer panel', async ({ page }) => {
  await page.goto('/')
  await expect(page.locator('.brand-name')).toHaveText('NOAH')
  await expect(page.locator('.layer-panel')).toBeVisible()
  await expect(page.getByText('LAYERS')).toBeVisible()
})

test('layer panel toggle flips a checkbox and reveals its legend', async ({ page }) => {
  await page.goto('/')
  const roads = page.locator('.layer-row', { hasText: 'Roads' }).first()
  // The native input is visually hidden behind the styled .checkmark —
  // click the wrapping label like a user would.
  const box = roads.locator('label.checkbox')
  await expect(roads.locator('input[type=checkbox]')).not.toBeChecked()
  await box.click()
  await expect(roads.locator('input[type=checkbox]')).toBeChecked()
  await expect(roads).toContainText('Major road')
})

test('earthquake panel opens from the hazard group', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Quakes' }).click()
  // Panel is lazy-loaded; wait for its header to render.
  await expect(
    page.locator('.forecast-panel').filter({ hasText: /Earthquake Monitor/i }),
  ).toBeVisible({ timeout: 10_000 })
})

test('replay mode shows transport controls and exit returns to live', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Replay' }).click()
  const bar = page.getByTestId('replay-bar')
  await expect(bar).toBeVisible()
  await expect(bar).toContainText(/events/)
  await page.getByTitle('Exit replay (returns to live feed)').click()
  await expect(bar).not.toBeVisible()
})

test('notification bell opens an empty feed', async ({ page }) => {
  await page.goto('/')
  await page.getByRole('button', { name: 'Notifications' }).click()
  await expect(page.getByText('NOTIFICATIONS', { exact: true })).toBeVisible()
  await expect(page.getByText('No notifications yet.')).toBeVisible()
})

test('clicking an active volcano marker opens its detail popup', async ({ page }) => {
  test.setTimeout(60_000)
  await page.goto('/')
  // Wait for the map handle AND the volcano markers to be rendered
  // (style load + visibility sync can take a few seconds).
  await page.waitForFunction(() => {
    const m = (window as unknown as {
      __noah_map?: { isStyleLoaded: () => boolean;
        getLayer: (id: string) => { visibility?: string } | undefined }
    }).__noah_map
    return !!m && m.isStyleLoaded() &&
      m.getLayer('volcano-circle')?.visibility === 'visible'
  }, undefined, { timeout: 45_000 })
  const box = await page.locator('.map-container').boundingBox()
  // Kanlaon is off the default Luzon-centred viewport — jump first,
  // then project its summit inside the visible canvas.
  await page.evaluate(() => {
    const m = (window as unknown as {
      __noah_map: { jumpTo: (o: object) => void }
    }).__noah_map
    m.jumpTo({ center: [123.132, 10.4119], zoom: 11 })
  })
  await page.waitForTimeout(600)
  const pt = await page.evaluate(() => {
    const m = (window as unknown as {
      __noah_map: { project: (ll: number[]) => { x: number; y: number } }
    }).__noah_map
    const p = m.project([123.132, 10.4119])
    return { x: p.x, y: p.y }
  })
  await page.mouse.click(box!.x + pt.x, box!.y + pt.y)

  const popup = page.getByTestId('volcano-popup')
  await expect(popup).toBeVisible()
  await expect(popup).toContainText('Kanlaon')
  await expect(popup).toContainText('ACTIVE NOW')
  await expect(popup).toContainText('3 events')
  await expect(popup).toContainText('M4.6')
  // Latest-satellite mosaic requested through the cached tile proxy.
  await expect(popup.locator('.vc-thumb img').first()).toHaveAttribute(
    'src', /\/tiles\/esri\/13\/\d+\/\d+\.jpg$/)
})
