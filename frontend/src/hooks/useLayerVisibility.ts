import { useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import { useLayerStore, useUIStore } from '../stores'

const LAYER_IDS: Record<string, string[]> = {
  satellite: [],
  'place-labels': ['places-dot', 'places-city', 'places-town', 'places-village'],
  'admin-boundaries': [
    'admin-islands-line', 'admin-regions-line', 'admin-provinces-line',
    'admin-municipalities-line', 'admin-barangays-line',
    'admin-islands-label', 'admin-regions-label', 'admin-provinces-label',
    'admin-municipalities-label', 'admin-barangays-label',
  ],
  roads: ['roads-major', 'roads-farm'],
  rivers: ['rivers-water', 'rivers-outline'],
  elevation: ['elevation'],
  'agricultural-areas': ['farms-fill', 'farms-line', 'farms-labels'],
  'flood-risk': ['flood-risk-fill', 'flood-risk-line', 'flood-risk-province-marker', 'flood-risk-high-marker'],
  'flood-rain-stations': ['flood-rain-circle', 'flood-rain-label'],
  'flood-water-stations': ['flood-water-circle'],
  'flood-alerts-layer': ['flood-alert-marker', 'flood-alert-halo'],
  'weather-stations': ['stations-symbol'],
  rainfall: ['rainfall-circles'],
  alerts: ['alerts-fill', 'alerts-line'],
  cyclones: [
    'cyclone-extent-fill', 'cyclone-extent-line',
    'cyclone-track-line', 'cyclone-pos-circle', 'cyclone-pos-label',
    'cyclone-pulse-a', 'cyclone-pulse-b',
  ],
  'cyclone-forecast': ['cyclone-fcst-line', 'cyclone-fcst-circle', 'cyclone-fcst-label'],
  'cyclone-clouds': ['cyclone-clouds-raster'],
  'rain-radar': ['rain-radar-raster'],
  earthquakes: ['eq-circle', 'eq-selected', 'eq-label'],
  tsunamis: ['tsunami-circle', 'tsunami-label'],
  volcanoes: ['volcano-circle', 'volcano-label'],
  'buildings-3d': ['buildings-fill', 'buildings-line'],
  par: ['par-line'],
}

export function useLayerVisibility(map: maplibregl.Map | null) {
  const layers = useLayerStore((s) => s.layers)
  const basemap = useUIStore((s) => s.basemap)

  // Roads/rivers geometry (backend Overpass proxy) is fetched per
  // viewport on demand — whole-country OSM extraction measured at
  // ~800 MB, so only what the user actually looks at is ever loaded.
  useEffect(() => {
    if (!map) return
    let timer: ReturnType<typeof setTimeout> | undefined

    const fill = async (sourceId: string, url: string) => {
      try {
        const res = await fetch(url)
        if (!res.ok) return
        const data: GeoJSON.FeatureCollection = await res.json()
        if (data.features?.length) {
          const src = map.getSource(sourceId) as maplibregl.GeoJSONSource | null
          if (src && map.isStyleLoaded()) src.setData(data)
        }
      } catch { /* honest empty; next viewport retries */ }
    }

    const refresh = () => {
      const st = useLayerStore.getState().layers
      const wantRoads = st.find((l) => l.id === 'roads')?.visible
      const wantRivers = st.find((l) => l.id === 'rivers')?.visible
      const wantPlaces = st.find((l) => l.id === 'place-labels')?.visible
      if (!wantRoads && !wantRivers && !wantPlaces) return
      const b = map.getBounds()
      const bbox = [b.getWest(), b.getSouth(), b.getEast(), b.getNorth()]
        .map((v) => v.toFixed(3)).join(',')
      const z = map.getZoom()
      // Place labels stay useful from country zoom upward — fetch early
      if (wantPlaces && z >= 4) fill('places', `/api/places?bbox=${bbox}`)
      if (wantRoads && z >= 6) fill('roads', `/api/roads?bbox=${bbox}&tier=major`)
      if (wantRoads && z >= 13) fill('roads-minor', `/api/roads?bbox=${bbox}&tier=minor`)
      if (wantRivers && z >= 8) fill('waterways', `/api/waterways?bbox=${bbox}`)
    }

    const onMoveEnd = () => {
      clearTimeout(timer)
      timer = setTimeout(refresh, 700)
    }
    map.on('moveend', onMoveEnd)
    refresh()
    return () => {
      clearTimeout(timer)
      map.off('moveend', onMoveEnd)
    }
  }, [layers, map])

  useEffect(() => {
    if (!map) return

    const paintProps: Record<string, string> = {
      fill: 'fill-opacity', line: 'line-opacity', circle: 'circle-opacity',
      symbol: 'icon-opacity', raster: 'raster-opacity', background: 'background-opacity',
      heatmap: 'heatmap-opacity', 'fill-extrusion': 'fill-extrusion-opacity', hillshade: 'hillshade-exaggeration',
    }

    const apply = () => {
      for (const layer of useLayerStore.getState().layers) {
        const ids = LAYER_IDS[layer.id] ?? []
        for (const id of ids) {
          if (!map.getLayer(id)) continue
          try {
            map.setLayoutProperty(id, 'visibility', layer.visible ? 'visible' : 'none')
            const type = map.getLayer(id)?.type as keyof typeof paintProps
            const prop = paintProps[type]
            if (prop && prop !== 'hillshade-exaggeration') {
              map.setPaintProperty(id, prop, layer.opacity)
            }
          } catch { /* one stubborn layer must never strand later groups */ }
        }
      }
    }

    // Style may not be loaded when this effect first runs. We can't
    // defer via map.once('load'): the hook receives its map only AFTER
    // App's ready flag flips (which happens in a 'load' handler), so
    // that event has already fired and would strand every layer at
    // buildStyle's default visibility ('none'). Poll for style
    // readiness instead; each store change also retries immediately.
    let retry: ReturnType<typeof setInterval> | undefined
    let stop: ReturnType<typeof setTimeout> | undefined
    if (!map.isStyleLoaded()) {
      retry = setInterval(() => {
        if (map.isStyleLoaded()) {
          clearInterval(retry)
          clearTimeout(stop)
          apply()
        }
      }, 200)
      stop = setTimeout(() => clearInterval(retry), 30_000)
    } else {
      apply()
    }

    Object.keys(LAYER_BASEMAP_MAP).forEach((id) => {
      if (map.getLayer(`basemap-${id}`)) {
        map.setLayoutProperty(`basemap-${id}`, 'visibility', id === basemap ? 'visible' : 'none')
      }
    })
    return () => {
      if (retry) clearInterval(retry)
      if (stop) clearTimeout(stop)
    }
  }, [layers, basemap, map])
}

const LAYER_BASEMAP_MAP: Record<string, null> = {
  satellite: null, street: null, terrain: null, dark: null, light: null,
}
