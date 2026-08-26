// LayerPanel component tests: rendering from the layer store, toggle
// wiring, opacity reveal, reorder-button disabled states and legends.
// maplibre-gl is mocked because stores/index.ts imports it at module
// scope (real map instantiation never happens under jsdom).

import { act } from 'react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

vi.mock('maplibre-gl', () => ({ default: {} }))

import { useLayerStore } from '../../stores'
import { I18nProvider } from '../../i18n'
import LayerPanel from './LayerPanel'

const renderPanel = () =>
  render(<I18nProvider><LayerPanel /></I18nProvider>)

function renderInLang(lang: 'en' | 'fil') {
  localStorage.setItem('noah.lang', lang)
  return render(<I18nProvider><LayerPanel /></I18nProvider>)
}

function resetStore() {
  const layers = useLayerStore.getState().layers
  useLayerStore.setState({
    layers: layers.map((l) => ({ ...l, visible: false, opacity: 1 })),
  })
}

beforeEach(resetStore)

describe('LayerPanel', () => {
  it('renders the panel title and one row per layer', () => {
    renderPanel()
    expect(screen.getByText('LAYERS')).toBeInTheDocument()
    const boxes = screen.getAllByRole('checkbox')
    expect(boxes.length).toBe(useLayerStore.getState().layers.length)
  })

  it('toggling a layer checks its box and reveals the opacity slider', async () => {
    const user = userEvent.setup()
    renderPanel()
    const box = screen.getAllByRole('checkbox')[0]
    expect(box).not.toBeChecked()
    expect(screen.queryByText(/Opacity/)).not.toBeInTheDocument()

    await user.click(box)
    expect(box).toBeChecked()
    const sliders = screen.getAllByRole('slider')
    expect(sliders.length).toBeGreaterThan(0)
  })

  it('shows legend entries for visible layers that define one', async () => {
    const user = userEvent.setup()
    renderPanel()
    // Roads has a two-entry legend.
    await user.click(screen.getByText('Roads'))
    expect(screen.getByText('Major road')).toBeInTheDocument()
    expect(screen.getByText('Farm track')).toBeInTheDocument()
  })

  it('disables Raise on the first row and Lower on the last row', () => {
    renderPanel()
    const raise = screen.getAllByTitle('Raise')
    const lower = screen.getAllByTitle('Lower')
    expect(raise[0]).toBeDisabled()
    expect(lower[lower.length - 1]).toBeDisabled()
    expect(raise[1]).not.toBeDisabled()
    expect(lower[0]).not.toBeDisabled()
  })

  it('moveDown swaps the first layer with its neighbour', async () => {
    const before = useLayerStore.getState().layers.map((l) => l.id)
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getAllByTitle('Lower')[0])
    const after = useLayerStore.getState().layers.map((l) => l.id)
    expect(after[0]).toBe(before[1])
    expect(after[1]).toBe(before[0])
  })

  it('renders Filipino layer names and descriptions when lang=fil', () => {
    renderInLang('fil')
    expect(screen.getByText('MGA PATONG')).toBeInTheDocument()
    expect(screen.getByText('Mga Daan')).toBeInTheDocument()
    expect(screen.getByText(/Pangunahing daan at landas ng bukid/))
      .toBeInTheDocument()
  })

  it('falls back to English metadata when no Filipino variant exists', () => {
    renderInLang('fil')
    // PAR has no nameFil/descriptionFil by design.
    expect(screen.getByText('Philippine Area of Responsibility'))
      .toBeInTheDocument()
  })

  it('setOpacity updates the visible percentage readout', async () => {
    const user = userEvent.setup()
    renderPanel()
    await user.click(screen.getAllByRole('checkbox')[0])
    const slider = screen.getAllByRole('slider')[0]
    expect(screen.getByText('100%')).toBeInTheDocument()
    // jsdom range-input event simulation is unreliable; drive the
    // store directly (inside act) and assert the component reflects it.
    act(() => {
      useLayerStore.getState().setOpacity(
        useLayerStore.getState().layers[0].id, 0.5)
    })
    expect(slider).toHaveValue('0.5')
    expect(screen.getByText('50%')).toBeInTheDocument()
  })
})
