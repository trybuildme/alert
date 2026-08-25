import { beforeEach, describe, expect, it } from 'vitest'
import { msPerFrame, REPLAY_SPEEDS, REPLAY_WINDOWS, useReplayStore } from './stores/replay'

beforeEach(() => {
  useReplayStore.setState({
    active: false,
    playing: false,
    loading: false,
    windowDays: 30,
    speed: 1,
    cursorMs: null,
    spanStartMs: 0,
    spanEndMs: 0,
    eventCount: 0,
  })
})

describe('replay store transitions', () => {
  it('toggle enters and exits replay mode, resetting transient state', () => {
    const s = useReplayStore.getState()
    s.setSpan(1000, 2000)
    s.setCursorMs(1500)
    s.setPlaying(true)

    s.toggle()
    expect(useReplayStore.getState().active).toBe(true)
    expect(useReplayStore.getState().playing).toBe(false)
    expect(useReplayStore.getState().cursorMs).toBeNull()

    useReplayStore.getState().toggle()
    expect(useReplayStore.getState().active).toBe(false)
  })

  it('changing the window resets cursor and pauses playback', () => {
    const s = useReplayStore.getState()
    s.setSpan(0, 1000)
    s.setCursorMs(500)
    s.setPlaying(true)

    s.setWindowDays(7)
    expect(useReplayStore.getState().windowDays).toBe(7)
    expect(useReplayStore.getState().cursorMs).toBeNull()
    expect(useReplayStore.getState().playing).toBe(false)
  })

  it('setSpan records playback bounds', () => {
    useReplayStore.getState().setSpan(5, 10)
    const s = useReplayStore.getState()
    expect(s.spanStartMs).toBe(5)
    expect(s.spanEndMs).toBe(10)
  })
})

describe('msPerFrame', () => {
  it('covers the full window in BASE_DURATION at speed 1', () => {
    const windowMs = 30 * 86_400_000
    const rate = msPerFrame(windowMs, 1)
    // ms of replay-time per ms wall-clock = window / 45000
    expect(rate * 45_000).toBeCloseTo(windowMs, 0)
  })

  it('scales linearly with speed multiplier', () => {
    expect(msPerFrame(1000, 2)).toBeCloseTo(msPerFrame(1000, 1) / 2, 9)
  })
})

describe('option tables', () => {
  it('expose sane windows and speeds', () => {
    expect(REPLAY_WINDOWS.map((w) => w.days)).toEqual([7, 30, 90])
    for (const s of REPLAY_SPEEDS) expect(s.value).toBeGreaterThan(0)
  })
})
