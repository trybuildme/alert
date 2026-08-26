// FloodStationPopup tests: current readings with trend arrows,
// quality/source attribution, offline honesty, close behaviour.

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { useUIStore } from '../../stores'
import { I18nProvider } from '../../i18n'
import FloodStationPopup from './FloodStationPopup'

const DETAIL = {
  station: {
    id: 'rain-mactan-cebu', name: 'Mactan (Cebu) Synoptic',
    kind: 'rainfall', latitude: 10.3167, longitude: 124.0167,
    river_basin: 'Cebu', provider: 'open-meteo',
  },
  series: {
    rainfall_mm_h: [
      { observed_at: '2026-08-26T04:00:00Z', value: 0.5, quality: 'ok',
        source: 'open-meteo' },
      { observed_at: '2026-08-26T05:00:00Z', value: 2.8, quality: 'ok',
        source: 'open-meteo' },
    ],
    rainfall_mm_24h: [
      { observed_at: '2026-08-26T05:00:00Z', value: 18.4, quality: 'ok',
        source: 'open-meteo' },
    ],
  },
  generated_at: '2026-08-26T05:05:00Z',
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true, json: async () => DETAIL,
  })))
})

afterEach(() => {
  useUIStore.getState().setFloodStationId(null)
  vi.unstubAllGlobals()
})

describe('FloodStationPopup', () => {
  it('hidden when no station selected', () => {
    const { container } = render(<I18nProvider><FloodStationPopup /></I18nProvider>)
    expect(container).toBeEmptyDOMElement()
  })

  it('shows readings with rising-trend arrow and attribution', async () => {
    useUIStore.getState().setFloodStationId('rain-mactan-cebu')
    render(<I18nProvider><FloodStationPopup /></I18nProvider>)
    await screen.findByText('Rainfall (1 h)')
    expect(screen.getByText(/2.80 mm\/h/)).toBeInTheDocument()
    expect(screen.getByText(/↑ 2\.3/)).toBeInTheDocument()   // rose vs prev hour
    expect(screen.getByText('open-meteo')).toBeInTheDocument()
    expect(screen.getByText('OBSERVED'.toLowerCase() in {} ? 'x' : 'ok'))
      .toBeInTheDocument()
    expect(screen.getByText(/real model data via Open-Meteo/i))
      .toBeInTheDocument()
  })

  it('discloses offline gauges honestly instead of fabricating values', async () => {
    useUIStore.getState().setFloodStationId('wl-marikina-sto-nino')
    vi.stubGlobal('fetch', vi.fn(async () => ({
      ok: true,
      json: async () => ({
        station: {
          id: 'wl-marikina-sto-nino', name: 'Marikina River · Sto. Niño',
          kind: 'water_level', latitude: 14.63, longitude: 121.1,
          river_basin: 'Marikina', provider: 'none',
        },
        series: {},
        generated_at: '2026-08-26T05:05:00Z',
      }),
    })))
    render(<I18nProvider><FloodStationPopup /></I18nProvider>)
    expect(await screen.findByText(/awaits an authorized PAGASA\/DENR feed/))
      .toBeInTheDocument()
  })

  it('close button clears selection and unmounts', async () => {
    const user = userEvent.setup()
    useUIStore.getState().setFloodStationId('rain-mactan-cebu')
    render(<I18nProvider><FloodStationPopup /></I18nProvider>)
    await screen.findByText('Rainfall (1 h)')
    await user.click(screen.getByTitle('Close'))
    expect(useUIStore.getState().floodStationId).toBeNull()
  })
})
