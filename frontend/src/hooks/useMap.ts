// Slim map lifecycle hook: creates the MapLibre instance, registers
// controls, loads post-style GeoJSON data, and subscribes stores to the
// product/projection state.
//
// Heavy lifting lives in sibling modules:
//   src/map/buildStyle.ts    sources + layers definition
//   src/map/products.ts      satellite visibility / tile swapping
//   src/map/interactions.ts  click routing + draw tool handling

import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapStore, useSatelliteStore, useUIStore } from '../stores'
import { DEFAULT_CENTER, DEFAULT_ZOOM } from '../config/mapConfig'
import { forecastToFC, fetchForecast } from '../lib/forecast'
import { buildStyle } from '../map/buildStyle'
import { applyProductVisibility, SAT_PREFIX, setProductTiles } from '../map/products'
import { attachInteractions } from '../map/interactions'

async function fetchGeoJSON(url: string): Promise<GeoJSON.FeatureCollection> {
  try {
    const res = await fetch(url)
    if (!res.ok) return { type: 'FeatureCollection', features: [] }
    return await res.json()
  } catch {
    return { type: 'FeatureCollection', features: [] }
  }
}

export function useMap(containerRef: React.RefObject<HTMLDivElement | null>) {
  const [ready, setReady] = useState(false)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const { setMap, setView } = useMapStore()

  useEffect(() => {
    if (!containerRef.current || mapRef.current) return

    const { style } = buildStyle()
    const map = new maplibregl.Map({
      container: containerRef.current,
      style,
      center: DEFAULT_CENTER,
      zoom: DEFAULT_ZOOM,
      minZoom: 1,
      maxZoom: 19,
      attributionControl: { compact: true },
      fadeDuration: 150,
      maxPitch: 70,
      canvasContextAttributes: { antialias: true },
    } as maplibregl.MapOptions)

    addControls(map)

    const syncView = () => {
      setView(map.getZoom(), [map.getCenter().lng, map.getCenter().lat], map.getBearing())
      // Keep the Sentinel-2 deep-zoom Esri stack in sync while zooming
      if (useSatelliteStore.getState().activeProduct === 'sentinel2-cloudless'
          && map.getLayer(`${SAT_PREFIX}esri-world`)) {
        map.setLayoutProperty(`${SAT_PREFIX}esri-world`, 'visibility',
          map.getZoom() >= 15 ? 'visible' : 'none')
      }
    }
    map.on('move', syncView)

    map.on('load', async () => {
      await loadPostStyleData(map)
      setReady(true)
    })

    attachInteractions(map)

    mapRef.current = map
    setMap(map)
    // Debug/test hook: lets Playwright project coordinates and drive
    // the map in E2E specs (window.__noah_map.project(...)).
    ;(window as unknown as { __noah_map?: maplibregl.Map }).__noah_map = map

    return () => {
      map.remove()
      mapRef.current = null
      setMap(null)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    if (!mapRef.current || !ready) return
    const map = mapRef.current
    const { activeProduct, currentTime } = useSatelliteStore.getState()
    applyProductVisibility(map, activeProduct)
    setProductTiles(map, activeProduct, currentTime)
  }, [ready])

  useEffect(() => {
    const unsub = useSatelliteStore.subscribe((state) => {
      const map = mapRef.current
      if (!map || !map.isStyleLoaded()) return
      const palette = state.activeProduct === 'himawari-clean-ir' && state.irEnhanced ? 'windy' : undefined
      applyProductVisibility(map, state.activeProduct)
      setProductTiles(map, state.activeProduct, state.currentTime, palette)
    })
    return unsub
  }, [])

  // ---- Globe projection (3D Earth mode; CesiumJS-compatible data stack) ----
  useEffect(() => {
    const unsub = useUIStore.subscribe((state) => {
      const map = mapRef.current
      if (!map) return
      try {
        ;(map as unknown as { setProjection: (p: { type: string }) => void }).setProjection(
          state.mode2D ? { type: 'mercator' } : { type: 'globe' },
        )
      } catch {
        /* projection unsupported in this runtime */
      }
    })
    return unsub
  }, [])

  return { ready, map: mapRef.current }
}

function addControls(map: maplibregl.Map) {
  map.addControl(new maplibregl.NavigationControl({ showCompass: true, showZoom: true, visualizePitch: true }), 'top-right')
  map.addControl(new maplibregl.ScaleControl({ maxWidth: 160, unit: 'metric' }), 'bottom-right')
  map.addControl(new maplibregl.FullscreenControl(), 'top-right')
  const geolocate = new maplibregl.GeolocateControl({
    positionOptions: { enableHighAccuracy: true },
    trackUserLocation: true,
    showAccuracyCircle: true,
    showUserLocation: true,
  })
  geolocate.on('geolocate', (e) => {
    useUIStore.getState().setGpsFix(e.coords.accuracy)
  })
  geolocate.on('error', (e) => {
    const messages: Record<number, string> = {
      1: 'location permission denied — using coarse IP estimate',
      2: 'position unavailable',
      3: 'location request timed out',
    }
    const err = e as GeolocationPositionError
    useUIStore.getState().setGpsFix(null, messages[err.code] ?? 'location unavailable')
  })
  map.addControl(geolocate, 'top-right')
}

async function loadPostStyleData(map: maplibregl.Map) {
  // Station marker image
  const size = 32
  const canvas = document.createElement('canvas')
  canvas.width = canvas.height = size
  const ctx = canvas.getContext('2d')!
  ctx.beginPath()
  ctx.arc(size / 2, size / 2, 9, 0, Math.PI * 2)
  ctx.fillStyle = '#38bdf8'
  ctx.fill()
  ctx.lineWidth = 3
  ctx.strokeStyle = '#082f49'
  ctx.stroke()
  ctx.beginPath()
  ctx.arc(size / 2, size / 2, 3, 0, Math.PI * 2)
  ctx.fillStyle = '#ffffff'
  ctx.fill()
  map.addImage('station-marker', ctx.getImageData(0, 0, size, size))

  const loads: [string, string][] = [
    ['admin-islands', '/api/admin/islands'],
    ['admin-regions', '/api/admin/regions'],
    ['admin-provinces', '/api/admin/provinces'],
    ['admin-municipalities', '/api/admin/municipalities'],
    ['admin-barangays', '/api/admin/barangays'],
    ['farms', '/api/farms'],
    ['weather-stations', '/api/weather-stations'],
    ['flood-risk', '/api/flood-zones'],
    ['rainfall', '/api/rainfall'],
    ['alerts', '/api/alerts'],
    ['cyclones', '/api/cyclones'],
    ['volcanoes', '/api/volcanoes'],
    // tsunami feed may be temporarily unavailable -> honest empty layer
    ['tsunamis', '/api/tsunamis'],
  ]
  for (const [sourceId, url] of loads) {
    const data = await fetchGeoJSON(url)
    const src = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined
    if (src && data.features.length > 0) src.setData(data)
  }
  // 7-day cyclone outlook: JSON -> FeatureCollection (daily points)
  try {
    const fcst = await fetchForecast()
    const src = map.getSource('cyclones-fcst') as maplibregl.GeoJSONSource | undefined
    if (src && fcst?.storms?.length) src.setData(forecastToFC(fcst.storms))
    useUIStore.getState().setForecastMeta({
      generatedAt: fcst?.generated_at ?? null,
      methodology: fcst?.methodology ?? null,
      unavailable: !fcst || fcst.source === 'unavailable',
    })
  } catch { /* honest empty overlay */ }
}
