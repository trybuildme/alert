// Bottom-center replay transport bar. Visible only while replay mode is
// active; scrubs/plays historical earthquakes through the map source.

import { REPLAY_SPEEDS, REPLAY_WINDOWS, useReplayStore } from '../../stores/replay'

function fmt(ms: number): string {
  return new Date(ms).toLocaleString(undefined, {
    month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit',
  })
}

export default function ReplayControls() {
  const active = useReplayStore((s) => s.active)
  const playing = useReplayStore((s) => s.playing)
  const loading = useReplayStore((s) => s.loading)
  const windowDays = useReplayStore((s) => s.windowDays)
  const speed = useReplayStore((s) => s.speed)
  const cursorMs = useReplayStore((s) => s.cursorMs)
  const spanStartMs = useReplayStore((s) => s.spanStartMs)
  const spanEndMs = useReplayStore((s) => s.spanEndMs)
  const eventCount = useReplayStore((s) => s.eventCount)
  const store = useReplayStore

  if (!active) return null

  const atEnd = cursorMs != null && cursorMs >= spanEndMs

  return (
    <div className="replay-bar" data-testid="replay-bar">
      <button
        className="rp-play"
        onClick={() => {
          if (atEnd) store.getState().setCursorMs(spanStartMs)
          store.getState().setPlaying(!playing)
        }}
        disabled={loading || spanEndMs === 0}
        title={playing ? 'Pause replay' : 'Play replay'}
      >
        {loading ? '…' : playing ? '❚❚' : '▶'}
      </button>

      <select
        className="rp-select"
        value={windowDays}
        onChange={(e) => store.getState().setWindowDays(Number(e.target.value))}
        title="History window to replay"
      >
        {REPLAY_WINDOWS.map((w) => (
          <option key={w.days} value={w.days}>{w.label}</option>
        ))}
      </select>

      <select
        className="rp-select"
        value={speed}
        onChange={(e) => store.getState().setSpeed(Number(e.target.value))}
        title="Playback speed"
      >
        {REPLAY_SPEEDS.map((s) => (
          <option key={s.value} value={s.value}>{s.label}</option>
        ))}
      </select>

      <input
        className="rp-slider"
        type="range"
        min={spanStartMs}
        max={spanEndMs}
        step={1}
        value={cursorMs ?? spanStartMs}
        onChange={(e) => {
          store.getState().setPlaying(false)
          store.getState().setCursorMs(Number(e.target.value))
        }}
      />

      <div className="rp-readout">
        <span className="rp-date">{cursorMs != null ? fmt(cursorMs) : '—'}</span>
        <span className="rp-count">{loading ? 'loading…' : `${eventCount} events`}</span>
      </div>

      <button
        className="rp-exit"
        onClick={() => store.getState().toggle()}
        title="Exit replay (returns to live feed)"
      >
        ✕
      </button>
    </div>
  )
}
