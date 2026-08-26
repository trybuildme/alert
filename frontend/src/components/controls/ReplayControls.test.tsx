// ReplayControls component tests: transport bar only exists in replay
// mode, play/pause wiring, window/speed selects, exit behaviour.

import { beforeEach, describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'

import { useReplayStore } from '../../stores/replay'
import { I18nProvider } from '../../i18n'
import ReplayControls from './ReplayControls'

const renderBar = () =>
  render(<I18nProvider><ReplayControls /></I18nProvider>)

beforeEach(() => {
  useReplayStore.setState({
    active: false, playing: false, loading: false,
    windowDays: 30, speed: 1, cursorMs: null,
    spanStartMs: 0, spanEndMs: 0, eventCount: 0,
  })
})

describe('ReplayControls', () => {
  it('renders nothing while replay mode is off', () => {
    const { container } = renderBar()
    expect(container).toBeEmptyDOMElement()
  })

  it('renders the transport bar once replay is active', () => {
    useReplayStore.setState({ active: true })
    renderBar()
    expect(screen.getByTestId('replay-bar')).toBeInTheDocument()
    // Window + speed selects expose their options.
    expect(screen.getByTitle('History window to replay')).toBeInTheDocument()
    expect(screen.getByTitle('Playback speed')).toBeInTheDocument()
    expect(screen.getByText(/0 events/)).toBeInTheDocument()
  })

  it('play button toggles playback state', async () => {
    const user = userEvent.setup()
    useReplayStore.setState({
      active: true,
      spanStartMs: 0,
      spanEndMs: Date.now() + 3_600_000,
      cursorMs: null,
      eventCount: 42,
    })
    renderBar()
    const play = screen.getByTitle('Play replay')
    await user.click(play)
    expect(useReplayStore.getState().playing).toBe(true)
    expect(screen.getByTitle('Pause replay')).toBeInTheDocument()
    expect(screen.getByText(/42 events/)).toBeInTheDocument()
    await user.click(screen.getByTitle('Pause replay'))
    expect(useReplayStore.getState().playing).toBe(false)
  })

  it('changing the history window pauses playback and drops the cursor', async () => {
    const user = userEvent.setup()
    useReplayStore.setState({
      active: true, playing: true, cursorMs: 500,
      spanStartMs: 0, spanEndMs: 10_000,
    })
    renderBar()
    await user.selectOptions(screen.getByTitle('History window to replay'), '7')
    expect(useReplayStore.getState().windowDays).toBe(7)
    expect(useReplayStore.getState().playing).toBe(false)
    expect(useReplayStore.getState().cursorMs).toBeNull()
  })

  it('exit leaves replay mode and unmounts the bar', async () => {
    const user = userEvent.setup()
    useReplayStore.setState({ active: true })
    renderBar()
    await user.click(screen.getByTitle('Exit replay (returns to live feed)'))
    expect(useReplayStore.getState().active).toBe(false)
    expect(screen.queryByTestId('replay-bar')).not.toBeInTheDocument()
  })

  it('play stays disabled while the span has not loaded', () => {
    useReplayStore.setState({ active: true, spanEndMs: 0 })
    renderBar()
    expect(screen.getByRole('button', { name: '▶' })).toBeDisabled()
  })
})
