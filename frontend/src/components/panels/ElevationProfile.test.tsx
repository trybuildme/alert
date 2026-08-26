// ElevationProfile tests: path stats immediately, DEM rows after fetch,
// honest error state. fetch is stubbed.

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'

import { useDrawingStore } from '../../stores'
import ElevationProfile from './ElevationProfile'
import { resampleLine } from './ElevationProfile'

const LINE = {
  id: 7,
  tool: 'line' as const,
  coordinates: [[121.0, 15.0], [121.05, 15.05], [121.1, 15.02]] as [number, number][],
  lengthKm: 9.12,
  center: [121.05, 15.03] as [number, number],
}

function openLine() {
  useDrawingStore.setState({
    activeTool: null, sketchCoords: [],
    features: [LINE], selectedId: LINE.id, nextId: 8,
  })
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async (url: string) => ({
    ok: true,
    json: async () => ({
      points: [], count: 80, cached: false,
      elevations_m: Array.from({ length: 80 }, (_, i) =>
        100 + Math.round(50 * Math.sin(i / 6))),
      source: 'open-meteo-copernicus-dem-glo-90',
      resolution_m: 90,
      disclaimer: 'real',
    }),
  })))
})

afterEach(() => {
  useDrawingStore.getState().selectFeature(null)
  vi.unstubAllGlobals()
})

describe('ElevationProfile', () => {
  it('shows path stats immediately while DEM loads', () => {
    openLine()
    render(<ElevationProfile feature={LINE} />)
    expect(screen.getByText('Sampling terrain along line…')).toBeInTheDocument()
    expect(screen.getByText('Length (path)')).toBeInTheDocument()
    expect(screen.getByText('9.12 km')).toBeInTheDocument()
    expect(screen.getByText('Bearing A to B')).toBeInTheDocument()
  })

  it('renders DEM-derived stats and the chart after fetch', async () => {
    openLine()
    const { container } = render(<ElevationProfile feature={LINE} />)
    await screen.findByText('Gain / Loss')
    expect(screen.getByText('Min / Max')).toBeInTheDocument()
    // mock elevations are 100 + 50*sin → span 50..150
    expect(screen.getByText('50 / 150 m')).toBeInTheDocument()
    expect(screen.getByText('Elevation A / B')).toBeInTheDocument()
    // requested <=100 sampled points from the backend
    const calledWith = (fetch as ReturnType<typeof vi.fn>).mock.calls[0][0] as string
    const n = decodeURIComponent(calledWith.split('coords=')[1]).split('|').length
    expect(n).toBeLessThanOrEqual(100)
    expect(n).toBeGreaterThanOrEqual(2)
    // chart rendered
    expect(container.querySelector('svg[aria-label="Elevation cross-section"]'))
      .toBeInTheDocument()
  })

  it('discloses the DEM source and resolution', async () => {
    openLine()
    render(<ElevationProfile feature={LINE} />)
    await screen.findByText('Gain / Loss')
    expect(screen.getByText(/Copernicus DEM ~90 m via Open-Meteo/))
      .toBeInTheDocument()
  })

  it('shows an honest error when the DEM source is down', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, json: async () => ({}) })))
    openLine()
    render(<ElevationProfile feature={LINE} />)
    expect(await screen.findByText('DEM source unavailable — no profile.'))
      .toBeInTheDocument()
  })
})

describe('resampleLine', () => {
  it('keeps endpoints and produces n points', () => {
    const out = resampleLine(LINE.coordinates, 10)
    expect(out.length).toBe(10)
    expect(out[0]).toEqual(LINE.coordinates[0])
    expect(out[out.length - 1]).toEqual(LINE.coordinates[LINE.coordinates.length - 1])
  })

  it('degenerate line collapses to two endpoints', () => {
    const out = resampleLine([[121, 15], [121, 15]], 5)
    expect(out.length).toBe(2)
  })
})
