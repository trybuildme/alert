// Real-time earthquake map data.
//
// Initial window: GET /api/earthquakes (bounded by history-days server
// default + the user's magnitude filter). Updates: EventSource stream —
// hazard.created features are APPENDED to the source; no full reloads.

import { useEffect } from 'react'
import type maplibregl from 'maplibre-gl'
import { useUIStore } from '../stores'
import { useReplayStore } from '../stores/replay'

interface EqFeature {
  type: 'Feature'
  id?: string
  properties: {
    uid: string
    magnitude: number | null
    depth_km: number | null
    origin_time: string
    place: string | null
    region?: string | null
    provider: string
    source_url?: string | null
    distance_km?: number
  }
  geometry: { type: 'Point'; coordinates: [number, number] }
}

function setSourceData(map: maplibregl.Map, features: EqFeature[]) {
  const src = map.getSource('earthquakes') as maplibregl.GeoJSONSource | null
  if (src) src.setData({ type: 'FeatureCollection', features })
}

const MAX_AGE_MS = 24 * 3600_000
const PRUNE_INTERVAL_MS = 10 * 60_000

function isWithin24h(originTimeIso: string | undefined): boolean {
  if (!originTimeIso) return false
  const t = Date.parse(originTimeIso)
  return Number.isFinite(t) && Date.now() - t <= MAX_AGE_MS
}

export function useEarthquakes(map: maplibregl.Map | null) {
  const eqMinMag = useUIStore((s) => s.eqMinMag)
  const eqSelectedUid = useUIStore((s) => s.eqSelectedUid)
  // Replay mode owns the 'earthquakes' source; stand down entirely so
  // live fetch/SSE/prune can't fight the replay frames.
  const replayActive = useReplayStore((s) => s.active)

  // Initial load (last 24 h only — older history never reaches the map)
  // + refetch when the magnitude filter changes. Re-runs on replay exit
  // to restore live data.
  useEffect(() => {
    if (!map || replayActive) return
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(
          `/api/earthquakes?days=1&min_magnitude=${encodeURIComponent(eqMinMag)}&limit=2000`)
        if (!res.ok) return
        const body = await res.json()
        if (!cancelled && body.type === 'FeatureCollection') {
          setSourceData(map, body.features.filter((f: EqFeature) =>
            isWithin24h(f.properties.origin_time)))
        }
      } catch { /* backend down: layer stays empty */ }
    })()
    return () => { cancelled = true }
  }, [map, eqMinMag, replayActive])

  // Age out events as the clock moves: every 10 min drop anything older
  // than 24 h so yesterday's markers quietly disappear without a refetch
  useEffect(() => {
    if (!map || replayActive) return
    const timer = setInterval(() => {
      const src = map.getSource('earthquakes') as maplibregl.GeoJSONSource | null
      if (!src || !map.isStyleLoaded()) return
      src.getData().then((data) => {
        const fc = data as GeoJSON.FeatureCollection
        const kept = fc.features.filter((f) =>
          isWithin24h((f.properties as { origin_time?: string }).origin_time))
        if (kept.length !== fc.features.length) {
          src.setData({ type: 'FeatureCollection', features: kept })
        }
      }).catch(() => { /* source gone; next cycle retries */ })
    }, PRUNE_INTERVAL_MS)
    return () => clearInterval(timer)
  }, [map])

  // Live updates over SSE — append-only for hazard.created
  useEffect(() => {
    if (!map || replayActive) return
    let es: EventSource | null = null
    let retry: ReturnType<typeof setTimeout> | undefined

    const connect = () => {
      es = new EventSource('/api/earthquakes/stream')
      es.addEventListener('hazard.created', (ev) => {
        try {
          const msg = JSON.parse((ev as MessageEvent).data)
          const src = map.getSource('earthquakes') as maplibregl.GeoJSONSource | null
          if (!src) return
          const feature: EqFeature = {
            type: 'Feature',
            properties: msg.properties,
            geometry: msg.geometry,
          }
          // Respect the active magnitude filter on live events too
          const minMag = useUIStore.getState().eqMinMag
          if (feature.properties.magnitude != null
              && feature.properties.magnitude < minMag) return
          // Merge: prepend new event to existing data (bounded growth is
          // handled server-side by the initial window size)
          src.getData().then((data) => {
            const fc = data as GeoJSON.FeatureCollection
            src.setData({
              type: 'FeatureCollection',
              features: [feature, ...fc.features.slice(0, 1999)],
            })
          }).catch(() => { /* source cleared mid-flight; next fetch heals */ })
        } catch { /* malformed stream payload: ignore */ }
      })
      es.onerror = () => {
        // EventSource auto-reconnects; guard against tight retry loops
        es?.close()
        retry = setTimeout(connect, 5000)
      }
    }
    connect()
    return () => {
      es?.close()
      if (retry) clearTimeout(retry)
    }
  }, [map, replayActive])

  // Selection ring filter follows UI selection
  useEffect(() => {
    if (!map || !map.getLayer('eq-selected')) return
    map.setFilter('eq-selected',
      ['==', ['get', 'uid'], eqSelectedUid ?? ['literal', null]])
  }, [map, eqSelectedUid])
}
