import { useEffect, useMemo, useRef, useState } from 'react'
import { useMapStore, useSatelliteStore } from '../../stores'
import { getProduct, metersPerPixel } from '../../config/mapConfig'

const VISIBLE_TICKS = 12
const PLAY_INTERVAL_MS = 800

export default function TimeMachine() {
  const map = useMapStore((s) => s.map)
  const { activeProduct, currentTime, setCurrentTime, playing, setPlaying, times, setTimes, irEnhanced } = useSatelliteStore()
  const [error, setError] = useState(false)
  const playRef = useRef<ReturnType<typeof setInterval> | null>(null)
  const palette = activeProduct === 'himawari-clean-ir' && irEnhanced ? 'windy' : undefined

  const product = getProduct(activeProduct)

  // Fetch available timestamps for time-dependent products
  useEffect(() => {
    if (!product?.timeDependent) {
      setTimes([])
      setError(false)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`/api/products/${activeProduct}/times`)
        const body = await res.json()
        if (!cancelled) {
          setTimes(body.timestamps ?? [])
          setError(false)
          if (body.timestamps?.length > 0) setCurrentTime(body.timestamps[0])
        }
      } catch {
        if (!cancelled) setError(true)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [activeProduct, product?.timeDependent, setTimes, setCurrentTime])

  const index = useMemo(() => (currentTime ? times.indexOf(currentTime) : -1), [times, currentTime])

  // Playback loop — geographic extent is preserved; only tiles change
  useEffect(() => {
    if (!playing || times.length === 0) return
    playRef.current = setInterval(() => {
      const store = useSatelliteStore.getState()
      const idx = store.currentTime ? store.times.indexOf(store.currentTime) : 0
      const next = idx <= 0 ? store.times.length - 1 : idx - 1
      store.setCurrentTime(store.times[next])
    }, PLAY_INTERVAL_MS)
    return () => {
      if (playRef.current) clearInterval(playRef.current)
    }
  }, [playing, times.length])

  // Preload upcoming frames so playback never flashes
  useEffect(() => {
    if (!map || !product?.timeDependent || index < 0) return
    const center = map.getCenter()
    const z = Math.min(Math.floor(map.getZoom()), product.maxNativeZoom)
    const n = 1 << z
    const worldX = ((center.lng + 180) / 360) * n
    const worldY = ((1 - Math.log(Math.tan((center.lat * Math.PI) / 180) + 1 / Math.cos((center.lat * Math.PI) / 180)) / Math.PI) / 2) * n
    const cx = Math.floor(worldX)
    const cy = Math.floor(worldY)

    for (let step = 1; step <= 3; step++) {
      const t = times[Math.max(0, index - step)]
      if (!t) continue
      for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]] as const) {
        const img = new Image()
        const pal = palette ? `&palette=${palette}` : ''
        img.src = `/tiles/${activeProduct}/${z}/${(cx + dx) % n}/${Math.min(n - 1, cy + dy)}.png?time=${encodeURIComponent(t)}${pal}`
      }
    }
  }, [index, times, map, activeProduct, product, palette])

  if (!product?.timeDependent) {
    return (
      <div className="timemachine static">
        <span className="tm-note">{product?.name} — static mosaic (no time axis)</span>
      </div>
    )
  }

  const start = Math.max(0, Math.min(index - VISIBLE_TICKS + 1, times.length - VISIBLE_TICKS))
  const visible = index >= 0 ? times.slice(start, start + VISIBLE_TICKS).reverse() : []
  const scaleKm = metersPerPixel(Math.min(useMapStore.getState().zoom, product.maxNativeZoom), useMapStore.getState().center[1]) * 256 / 1000

  return (
    <div className="timemachine">
      <div className="tm-controls">
        <button title="Previous" onClick={() => index >= 0 && index < times.length - 1 && setCurrentTime(times[index + 1])}>◀</button>
        <button title={playing ? 'Pause' : 'Play'} onClick={() => setPlaying(!playing)}>{playing ? '⏸' : '▶'}</button>
        <button title="Next" onClick={() => index > 0 && setCurrentTime(times[index - 1])}>▶</button>
      </div>

      <div className="tm-timeline">
        <div className="tm-date">
          {currentTime ? currentTime.slice(0, 10) : '----'}
          <span className="tm-clock">{currentTime && currentTime.length >= 19 ? ` ${currentTime.slice(11, 16)} UTC` : ''}</span>
        </div>
        <div className="tm-ticks">
          {visible.map((t) => (
            <button
              key={t}
              className={`tick ${t === currentTime ? 'current' : ''}`}
              onClick={() => setCurrentTime(t)}
              title={t}
            >
              {t.length >= 16 ? t.slice(11, 16) : t.slice(5, 10)}
            </button>
          ))}
        </div>
      </div>

      <div className="tm-info">
        <span>{product.name}</span>
        <span>frame ≈ {scaleKm < 1 ? `${Math.round(scaleKm * 1000)} m` : `${scaleKm.toFixed(0)} km`} wide</span>
        {error && <span className="tm-error">time index unavailable</span>}
      </div>

      {palette && (
        <div className="tm-legend" title="Qualitative enhancement with per-frame auto-contrast — GIBS pre-renders its own normalization, so exact Kelvin values are not recoverable">
          <span>warmer surface</span>
          <div
            className="tm-legend-bar"
            style={{
              background: 'linear-gradient(to right,' +
                '#0a0c18 0%,#3a425c 55%,#e1e6ee 78%,#ffffff 84%,' +
                '#ffe878 89%,#ff8c32 93%,#eb3250 96%,#b428c8 98.5%,#6e14a0 100%)',
            }}
          />
          <span>colder tops</span>
        </div>
      )}
    </div>
  )
}
