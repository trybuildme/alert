// Earthquake replay (time-lapse) state.
//
// Replay mode takes ownership of the 'earthquakes' map source: historical
// events are fetched once for the selected window, then an animated cursor
// re-plays them onto the map with a trailing visibility window. Live
// ingestion hooks (useEarthquakes) stand down until replay exits.

import { create } from 'zustand'

// Full window plays in BASE_DURATION_MS at 1x speed
const BASE_DURATION_MS = 45_000

// How far behind the cursor events remain visible
export const TRAIL_HOURS = 48

export const REPLAY_WINDOWS = [
  { days: 7, label: '7 d' },
  { days: 30, label: '30 d' },
  { days: 90, label: '90 d' },
]

export const REPLAY_SPEEDS = [
  { value: 0.5, label: '0.5×' },
  { value: 1, label: '1×' },
  { value: 2, label: '2×' },
  { value: 4, label: '4×' },
]

interface ReplayState {
  active: boolean
  playing: boolean
  loading: boolean
  windowDays: number
  speed: number
  cursorMs: number | null
  spanStartMs: number
  spanEndMs: number
  eventCount: number
  toggle: () => void
  setPlaying: (p: boolean) => void
  setLoading: (l: boolean) => void
  setWindowDays: (d: number) => void
  setSpeed: (s: number) => void
  setCursorMs: (ms: number | null) => void
  setSpan: (startMs: number, endMs: number) => void
  setEventCount: (n: number) => void
}

export const useReplayStore = create<ReplayState>((set) => ({
  active: false,
  playing: false,
  loading: false,
  windowDays: 30,
  speed: 1,
  cursorMs: null,
  spanStartMs: 0,
  spanEndMs: 0,
  eventCount: 0,
  toggle: () =>
    set((s) => ({
      active: !s.active,
      playing: false,
      loading: s.active ? false : s.loading,
      cursorMs: null,
      eventCount: 0,
    })),
  setPlaying: (playing) => set({ playing }),
  setLoading: (loading) => set({ loading }),
  setWindowDays: (windowDays) =>
    set({ windowDays, playing: false, cursorMs: null }),
  setSpeed: (speed) => set({ speed }),
  setCursorMs: (cursorMs) => set({ cursorMs }),
  setSpan: (spanStartMs, spanEndMs) => set({ spanStartMs, spanEndMs }),
  setEventCount: (eventCount) => set({ eventCount }),
}))

// Replay-time ms advanced per wall-clock ms of animation ticks
export function msPerFrame(totalWindowMs: number, speed: number): number {
  return totalWindowMs / (BASE_DURATION_MS * speed)
}
