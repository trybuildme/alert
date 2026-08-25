// Replay engine: fetches the historical window once, then animates a
// cursor that filters cached features into the 'earthquakes' map source.
// Owns the source exclusively while replay.active — useEarthquakes
// stands down (see its replayActive guard).

import { useEffect, useRef } from 'react'
import type maplibregl from 'maplibre-gl'
import { msPerFrame, TRAIL_HOURS, useReplayStore } from '../stores/replay'
import { useUIStore } from '../stores'

interface EqFeature {
  type: 'Feature'
  properties: { uid: string; origin_time: string; magnitude: number | null }
  geometry: { type: 'Point'; coordinates: [number, number] }
}

function originMs(f: EqFeature): number {
  return Date.parse(f.properties.origin_time)
}

function setSourceData(map: maplibregl.Map, features: EqFeature[]) {
  const src = map.getSource('earthquakes') as maplibregl.GeoJSONSource | null
  if (src) src.setData({ type: 'FeatureCollection', features })
}

export function useReplay(map: maplibregl.Map | null) {
  const active = useReplayStore((s) => s.active)
  const playing = useReplayStore((s) => s.playing)
  const windowDays = useReplayStore((s) => s.windowDays)
  const speed = useReplayStore((s) => s.speed)
  const cursorMs = useReplayStore((s) => s.cursorMs)
  const eqMinMag = useUIStore((s) => s.eqMinMag)
  const featuresRef = useRef<EqFeature[]>([])
  const fetchSeqRef = useRef(0)

  // Fetch the window whenever replay activates or its parameters change.
  // On success the cursor resets to the window start and playback begins.
  useEffect(() => {
    if (!map || !active) return
    const seq = ++fetchSeqRef.current
    const store = useReplayStore.getState()
    store.setLoading(true)
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(
          `/api/earthquakes?days=${windowDays}&min_magnitude=${encodeURIComponent(eqMinMag)}&limit=2000`)
        if (!res.ok) throw new Error(String(res.status))
        const body = await res.json()
        if (cancelled || seq !== fetchSeqRef.current) return
        const feats: EqFeature[] = body.type === 'FeatureCollection'
          ? (body.features as EqFeature[])
              .filter((f) => Number.isFinite(originMs(f)))
              .sort((a, b) => originMs(a) - originMs(b))
          : []
        featuresRef.current = feats
        const times = feats.map(originMs)
        const end = Math.max(Date.now(), ...(times.length ? times : [Date.now()]))
        const start = end - windowDays * 86_400_000
        store.setSpan(start, end)
        store.setEventCount(feats.length)
        store.setCursorMs(start)
        store.setLoading(false)
        store.setPlaying(true)
      } catch {
        if (!cancelled && seq === fetchSeqRef.current) {
          store.setLoading(false)
          store.setPlaying(false)
        }
      }
    })()
    return () => { cancelled = true }
  }, [map, active, windowDays, eqMinMag])

  // Playback loop. Reads live state via getState() so changing speed
  // mid-flight doesn't restart the loop.
  useEffect(() => {
    if (!active || !playing) return
    let raf = 0
    let last = performance.now()
    const tick = (now: number) => {
      const dt = now - last
      last = now
      const s = useReplayStore.getState()
      if (s.cursorMs == null || s.spanEndMs <= s.spanStartMs) return
      const step = dt * msPerFrame(s.spanEndMs - s.spanStartMs, s.speed)
      const next = s.cursorMs + step
      if (next >= s.spanEndMs) {
        s.setCursorMs(s.spanEndMs)
        s.setPlaying(false)
        return
      }
      s.setCursorMs(next)
      raf = requestAnimationFrame(tick)
    }
    raf = requestAnimationFrame(tick)
    return () => cancelAnimationFrame(raf)
  }, [active, playing])

  // Render frame: events within [cursor - TRAIL_HOURS, cursor].
  useEffect(() => {
    if (!map || !active || cursorMs == null) return
    const trailMs = TRAIL_HOURS * 3_600_000
    setSourceData(map, featuresRef.current.filter((f) => {
      const t = originMs(f)
      return t <= cursorMs && t > cursorMs - trailMs
    }))
  }, [map, active, cursorMs])

  // Hand the source back to live mode on exit; useEarthquakes refetches.
  useEffect(() => {
    if (active || !map) return
    featuresRef.current = []
  }, [active, map])
}
