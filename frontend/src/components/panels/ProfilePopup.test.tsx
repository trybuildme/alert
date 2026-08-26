// ProfilePopup tests: the rectangle card appears when a LINE is
// drawn/selected, carries chart + stats, and closes cleanly.

import { beforeEach, afterEach, describe, expect, it, vi } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { useDrawingStore, type DrawnFeature } from '../../stores'
import ProfilePopup from './ProfilePopup'

const LINE: DrawnFeature = {
  id: 3,
  tool: 'line',
  coordinates: [[121.0, 15.0], [121.08, 15.06]] as [number, number][],
  lengthKm: 10.4,
  center: [121.04, 15.03] as [number, number],
}

const POLYGON: DrawnFeature = {
  id: 4,
  tool: 'polygon',
  coordinates: [[121, 15], [122, 15], [121.5, 16], [121, 15]] as [number, number][],
  areaKm2: 3000,
  perimeterKm: 350,
  center: [121.5, 15.3] as [number, number],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn(async () => ({
    ok: true,
    json: async () => ({
      points: [], count: 80, cached: false,
      elevations_m: Array.from({ length: 80 }, (_, i) => 100 + i),
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

describe('ProfilePopup', () => {
  it('hidden when no feature is selected', () => {
    render(<ProfilePopup />)
    expect(screen.queryByTestId('profile-popup')).not.toBeInTheDocument()
  })

  it('pops up as a rectangle card when a line is selected', async () => {
    useDrawingStore.setState({ features: [LINE], selectedId: LINE.id })
    render(<ProfilePopup />)
    const card = screen.getByTestId('profile-popup')
    expect(card).toBeInTheDocument()
    expect(screen.getByText(/ELEVATION PROFILE/)).toBeInTheDocument()
    await screen.findByText('Gain / Loss')
    // measurements + diagram in one rectangle
    expect(screen.getByText('Length (path)')).toBeInTheDocument()
    expect(screen.getByText('Straight A to B')).toBeInTheDocument()
    expect(
      card.querySelector('svg[aria-label="Elevation cross-section"]'),
    ).toBeInTheDocument()
  })

  it('does not appear for polygon selections', () => {
    useDrawingStore.setState({ features: [POLYGON], selectedId: POLYGON.id })
    render(<ProfilePopup />)
    expect(screen.queryByTestId('profile-popup')).not.toBeInTheDocument()
  })

  it('close button deselects the line and unmounts the popup', async () => {
    const user = userEvent.setup()
    useDrawingStore.setState({ features: [LINE], selectedId: LINE.id })
    render(<ProfilePopup />)
    await user.click(screen.getByTitle('Close profile'))
    expect(useDrawingStore.getState().selectedId).toBeNull()
    expect(screen.queryByTestId('profile-popup')).not.toBeInTheDocument()
  })
})
