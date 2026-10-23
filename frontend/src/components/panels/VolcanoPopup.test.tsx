// VolcanoPopup tests: registry fetch, seismicity block, active badge,
// imagery thumbnail tiles, close behaviour. fetch is stubbed; the Esri
// thumbnail URLs are asserted rather than rendered.

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { useUIStore } from '../../stores'
import { I18nProvider } from '../../i18n'
import VolcanoPopup from './VolcanoPopup'

const DETAIL = {
  properties: {
    uid: 'phivolcs-site:kanlaon', name: 'Kanlaon', elevation_m: 2435,
    active_now: true,
    note: 'Negros Island — intermittent eruptions since June 2024',
    last_known_eruption: '2024',
  },
  geometry: { coordinates: [123.132, 10.4119] },
  active_status_as_of: '2026-08',
  disclaimer: 'snapshot — not live alert levels',
  seismicity: {
    available: true, total_7d: 12, count_24h: 3,
    strongest: { magnitude: 4.6, place: '5 km SW of Kanlaon',
                 origin_time: new Date().toISOString(), depth_km: 8 },
  },
  assessment: {
    level: 'active-curated', label: 'ACTIVE · PHIVOLCS-curated',
    color: '#22c55e',
    signals: [
      'PHIVOLCS public reporting flags ongoing eruptive/unrest activity (curated snapshot)',
      '12 earthquakes M2.5+ within 30 km in 7 days',
    ],
    context: {
      phivolcs_curated_flag: { active_now: true },
      years_since_last_eruption: 2,
      seismicity: { count_7d: 12, max_magnitude_7d: 4.6,
                    radius_km: 30, window_days: 7 },
    },
    methodology: 'Automated synthesis — NOT the official PHIVOLCS Alert Level.',
    disclaimer: 'ALERT assessment — not an official PHIVOLCS Alert Level.',
  },
}

function open(uid = 'phivolcs-site:kanlaon') {
  useUIStore.getState().setVolcanoUid(uid)
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () =>
    ({ ok: true, json: async () => DETAIL })))
})

afterEach(() => {
  useUIStore.getState().setVolcanoUid(null)
  vi.unstubAllGlobals()
})

describe('VolcanoPopup', () => {
  it('renders nothing when no volcano is selected', () => {
    const { container } = render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    expect(container).toBeEmptyDOMElement()
    expect(fetch).not.toHaveBeenCalled()
  })

  it('fetches detail for the selected uid and shows facts', async () => {
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await waitFor(() => expect(screen.getByText('Kanlaon')).toBeInTheDocument())
    expect(screen.getByText(/ACTIVE NOW/)).toBeInTheDocument()
    expect(screen.getByText('2435 m')).toBeInTheDocument()
    expect(screen.getByText('2024')).toBeInTheDocument()
    expect(fetch).toHaveBeenCalledWith('/api/volcanoes/phivolcs-site%3Akanlaon')
  })

  it('shows nearby seismicity counts and strongest event', async () => {
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await waitFor(() =>
      expect(screen.getByText(/3 events/)).toBeInTheDocument())
    expect(screen.getByText(/12 events/)).toBeInTheDocument()
    expect(screen.getByText('M4.6')).toBeInTheDocument()
    expect(screen.getByText(/5 km SW of Kanlaon/)).toBeInTheDocument()
  })

  it('renders the activity assessment with its basis signals', async () => {
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await screen.findByText('Kanlaon')
    expect(screen.getByText('Assessment')).toBeInTheDocument()
    expect(screen.getByText(/ACTIVE · PHIVOLCS-curated/)).toBeInTheDocument()
    expect(screen.getByText(/curated snapshot/)).toBeInTheDocument()
    expect(screen.getByText(/12 earthquakes M2.5\+ within 30 km/))
      .toBeInTheDocument()
    expect(screen.getByText(/last known eruption 2024/)).toBeInTheDocument()
    expect(screen.getByText(/not an official PHIVOLCS Alert Level/i))
      .toBeInTheDocument()
  })

  it('hides the assessment block when the payload omits it', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      ({ ok: true, json: async () => ({ ...DETAIL, assessment: undefined }) })))
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await screen.findByText('Kanlaon')
    expect(screen.queryByText('Assessment')).not.toBeInTheDocument()
  })

  it('requests a 2x2 Esri tile mosaic around the summit (z13)', async () => {
    const { xf } = { xf: null }
    void xf
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await screen.findByText('latest satellite')
    // Tile math: lon 123.132 -> xf=6897.9 at z13; lat 10.4119 sits near
    // a tile edge vertically, so y is 3857/3858 depending on recentering.
    // (alt="" images are presentational, so query the DOM directly.)
    const thumbEl = screen.getByText('latest satellite')
      .closest('.vc-thumb') as HTMLElement
    const imgs = Array.from(thumbEl.querySelectorAll('img')) as HTMLImageElement[]
    expect(imgs.length).toBe(4)
    for (const img of imgs) {
      expect(img.getAttribute('src')).toMatch(/^\/tiles\/esri\/13\/\d+\/\d+\.jpg$/)
    }
    const xs = imgs.map((i) => i.getAttribute('src')).filter((s) => s!.includes('/13/6897/'))
    expect(xs.length).toBeGreaterThan(0)
  })

  it('renders quiet badge for non-active volcanoes', async () => {
    open('phivolcs-site:pinatubo')
    vi.stubGlobal('fetch', vi.fn(async () =>
      ({ ok: true, json: async () => ({
        ...DETAIL,
        properties: { ...DETAIL.properties, uid: 'phivolcs-site:pinatubo',
                      name: 'Pinatubo', active_now: false },
      }) })))
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    expect(await screen.findByText(/MONITORED/)).toBeInTheDocument()
  })

  it('close button clears the selection and unmounts', async () => {
    const user = userEvent.setup()
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    await screen.findByText('Kanlaon')
    await user.click(screen.getByTitle('Close'))
    expect(useUIStore.getState().volcanoUid).toBeNull()
  })

  it('shows an error note when the registry is unreachable', async () => {
    vi.stubGlobal('fetch', vi.fn(async () =>
      ({ ok: false, json: async () => ({}) })))
    open()
    render(<I18nProvider><VolcanoPopup /></I18nProvider>)
    expect(await screen.findByText('Registry unavailable.')).toBeInTheDocument()
  })
})
