import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapStore, useSatelliteStore, useInspectStore, useDrawingStore, useUIStore } from '../stores'
import { ALL_PRODUCTS, BASEMAPS, DEFAULT_CENTER, DEFAULT_ZOOM, getProduct, PAR_FEATURES } from '../config/mapConfig'
import { forecastToFC, fetchForecast } from '../lib/forecast'

const SAT_PREFIX = 'sat-product-'

async function fetchGeoJSON(url: string): Promise<GeoJSON.FeatureCollection> {
  try {
    const res = await fetch(url)
    if (!res.ok) return { type: 'FeatureCollection', features: [] }
    return await res.json()
  } catch {
    return { type: 'FeatureCollection', features: [] }
  }
}

function buildStyle() {
  const sources: Record<string, maplibregl.SourceSpecification> = {}
  const layers: maplibregl.LayerSpecification[] = []

  // --- Base maps (bottom of stack; exactly one visible) ---
  Object.values(BASEMAPS).forEach((bm) => {
    sources[`basemap-${bm.id}`] = {
      type: 'raster',
      tiles: bm.tiles,
      tileSize: 256,
      maxzoom: bm.maxzoom,
      attribution: bm.attribution,
    }
    layers.push({
      id: `basemap-${bm.id}`,
      type: 'raster',
      source: `basemap-${bm.id}`,
      layout: { visibility: bm.id === 'satellite' ? 'visible' : 'none' },
      paint: { 'raster-opacity': 1 },
    })
  })

  // --- Satellite products (independent overlay above base map) ---
  ALL_PRODUCTS.forEach((p) => {
    sources[`${SAT_PREFIX}${p.id}`] = {
      type: 'raster',
      tiles: p.tiles(),
      tileSize: p.tileSize,
      maxzoom: p.maxzoom,
      attribution: p.attribution,
    }
    layers.push({
      id: `${SAT_PREFIX}${p.id}`,
      type: 'raster',
      source: `${SAT_PREFIX}${p.id}`,
      layout: { visibility: p.id === 'esri-world' ? 'visible' : 'none' },
      paint: { 'raster-opacity': 1, 'raster-fade-duration': 300 },
    })
  })

  // --- Elevation (backend DEM hillshade product) ---
  sources['elevation-dem'] = {
    type: 'raster',
    tiles: ['/tiles/elevation/{z}/{x}/{y}.png'],
    tileSize: 256,
    maxzoom: 18,
    attribution: 'AURORA-GIS synthetic DEM',
  }
  layers.push({
    id: 'elevation',
    type: 'raster',
    source: 'elevation-dem',
    layout: { visibility: 'none' },
    paint: { 'raster-opacity': 0.85 },
  })

  // --- Cyclone clouds (live Himawari-9 Clean IR, latest frame) ---
  // Sits above basemap/satellite rasters but below all vector overlays so
  // tracks, extents and labels stay readable over the cloud canopy.
  sources['cyclone-clouds'] = {
    type: 'raster',
    tiles: ['/tiles/himawari-clean-ir/{z}/{x}/{y}.png'],
    tileSize: 256,
    maxzoom: 6,
    attribution: 'NASA GIBS / JMA Himawari-9 AHI B13',
  }
  layers.push({
    id: 'cyclone-clouds-raster',
    type: 'raster',
    source: 'cyclone-clouds',
    layout: { visibility: 'none' },
    paint: { 'raster-opacity': 0.7, 'raster-fade-duration': 300 },
  } as unknown as maplibregl.RasterLayerSpecification)

  // --- Philippine Area of Responsibility (official PAGASA polygon) ---
  sources['par'] = { type: 'geojson', data: PAR_FEATURES }
  layers.push(
    {
      id: 'par-line',
      type: 'line',
      source: 'par',
      filter: ['==', ['get', 'kind'], 'boundary'],
      layout: { visibility: 'none' },
      paint: { 'line-color': '#facc15', 'line-width': 2, 'line-opacity': 0.9 },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'par-label',
      type: 'symbol',
      source: 'par',
      filter: ['==', ['get', 'kind'], 'label'],
      minzoom: 1,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': 12,
        'text-font': ['Noto Sans Bold'],
        'text-letter-spacing': 0.25,
      },
      paint: { 'text-color': '#fde047', 'text-halo-color': '#422006', 'text-halo-width': 1.6 },
    } as unknown as maplibregl.SymbolLayerSpecification,
  )

  // --- OSM roads + rivers (real geometry via backend Overpass proxy,
  // lazily fetched on first layer toggle — see useLayerVisibility) ---
  layers.push(
    {
      id: 'roads-major',
      type: 'line',
      source: 'roads',
      minzoom: 6,
      layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': '#f8fafc',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.8, 14, 3],
        'line-opacity': 0.85,
      },
      filter: ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary']]],
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'roads-farm',
      type: 'line',
      source: 'roads-minor',
      minzoom: 11,
      layout: { visibility: 'none', 'line-cap': 'round' },
      paint: {
        'line-color': '#a1887f',
        'line-width': ['interpolate', ['linear'], ['zoom'], 12, 0.6, 16, 2],
        'line-dasharray': [2, 2],
        'line-opacity': 0.7,
      },
      filter: ['in', ['get', 'class'], ['literal', ['secondary', 'tertiary', 'unclassified', 'track']]],
    } as unknown as maplibregl.LineLayerSpecification,
    {
      // Overpass waterways arrive as LineStrings -> render as a wide
      // blue casing beneath the thinner bright outline.
      id: 'rivers-water',
      type: 'line',
      source: 'waterways',
      minzoom: 6,
      layout: { visibility: 'none', 'line-cap': 'round', 'line-join': 'round' },
      paint: {
        'line-color': '#1e88e5',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8, 1.5, 12, 6],
        'line-opacity': 0.45,
      },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'rivers-outline',
      type: 'line',
      source: 'waterways',
      minzoom: 6,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#1565c0', 'line-width': 0.6, 'line-opacity': 0.7 },
    } as unknown as maplibregl.LineLayerSpecification,
  )

  // --- Thematic GeoJSON placeholders (data loaded post-style) ---
  const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
  ;['flood-risk', 'rainfall', 'alerts', 'farms', 'weather-stations', 'cyclones',
    'cyclones-fcst',
    // roads/waterways: geometry lazy-loaded per viewport on moveend
    'roads', 'roads-minor', 'waterways'].forEach((id) => {
    sources[id] = { type: 'geojson', data: empty }
  })

  layers.push(
    {
      id: 'flood-risk-fill',
      type: 'fill',
      source: 'flood-risk',
      layout: { visibility: 'none' },
      paint: {
        'fill-color': ['match', ['get', 'risk_level'], 'high', '#ef4444', 'medium', '#f59e0b', 'low', '#3b82f6', '#94a3b8'],
        'fill-opacity': 0.25,
      },
    } as unknown as maplibregl.FillLayerSpecification,
    {
      id: 'flood-risk-line',
      type: 'line',
      source: 'flood-risk',
      layout: { visibility: 'none' },
      paint: {
        'line-color': ['match', ['get', 'risk_level'], 'high', '#ef4444', 'medium', '#f59e0b', 'low', '#3b82f6', '#94a3b8'],
        'line-width': 1.5,
        'line-dasharray': [4, 3],
      },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      // Zoom-linked hierarchy: big province squares guide at country
      // zoom, then hand off to smaller municipal squares for precise
      // locations. Municipal polygons are squares, so outlining them
      // thick and dash-free IS the marker.
      id: 'flood-risk-province-marker',
      type: 'line',
      source: 'flood-risk',
      maxzoom: 9.5,
      filter: ['all', ['==', ['get', 'granularity'], 'province'], ['==', ['get', 'risk_level'], 'high']],
      layout: { visibility: 'none' },
      paint: {
        'line-color': '#ef4444',
        'line-width': 3,
        'line-opacity': 0.95,
      },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'flood-risk-high-marker',
      type: 'line',
      source: 'flood-risk',
      minzoom: 8.5,
      filter: ['==', ['get', 'risk_level'], 'high'],
      layout: { visibility: 'none' },
      paint: {
        'line-color': '#ef4444',
        'line-width': ['interpolate', ['linear'], ['zoom'], 8.5, 2.5, 12, 7],
        'line-opacity': 0.95,
      },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'rainfall-circles',
      type: 'circle',
      source: 'rainfall',
      minzoom: 5,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['get', 'mm'], 0, 6, 10, 18, 30, 34],
        'circle-color': ['step', ['get', 'mm'], '#bae6fd', 5, '#38bdf8', 15, '#1d4ed8'],
        'circle-opacity': 0.45,
        'circle-stroke-color': '#0c4a6e',
        'circle-stroke-width': 1,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'alerts-fill',
      type: 'fill',
      source: 'alerts',
      layout: { visibility: 'none' },
      paint: { 'fill-color': '#fb923c', 'fill-opacity': 0.2 },
    } as unknown as maplibregl.FillLayerSpecification,
    {
      id: 'alerts-line',
      type: 'line',
      source: 'alerts',
      layout: { visibility: 'none' },
      paint: { 'line-color': '#fb923c', 'line-width': 2, 'line-dasharray': [3, 2] },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'cyclone-extent-fill',
      type: 'fill',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'extent'],
      layout: { visibility: 'none' },
      paint: { 'fill-color': '#f43f5e', 'fill-opacity': 0.07 },
    } as unknown as maplibregl.FillLayerSpecification,
    {
      id: 'cyclone-extent-line',
      type: 'line',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'extent'],
      layout: { visibility: 'none' },
      paint: {
        'line-color': '#fb7185', 'line-width': 1,
        'line-dasharray': [2, 2], 'line-opacity': 0.35,
      },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'cyclone-track-line',
      type: 'line',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'track'],
      layout: { visibility: 'none' },
      paint: { 'line-color': '#f43f5e', 'line-width': 2, 'line-dasharray': [2, 1.5] },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'cyclone-pos-circle',
      type: 'circle',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'position'],
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        // Size by Saffir-Simpson category (-1 TD → 5 Cat5); null-safe via coalesce
        'circle-radius': ['interpolate', ['linear'], ['coalesce', ['get', 'sshs_category'], -1],
          -1, 5, 0, 7, 1, 9, 2, 11, 3, 13, 4, 15, 5, 17],
        'circle-color': ['step', ['coalesce', ['get', 'wind_kt'], 0],
          '#fb923c', 34, '#f97316', 64, '#ef4444', 96, '#dc2626'],
        'circle-opacity': 0.95,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'cyclone-pos-label',
      type: 'symbol',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'position'],
      minzoom: 3,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, 1.8],
        'text-anchor': 'top',
        'text-transform': 'uppercase',
      },
      paint: { 'text-color': '#fecdd3', 'text-halo-color': '#4c0519', 'text-halo-width': 1.5 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      // Light circling pulse: radius+opacity driven per-frame by
      // useCyclonePulse; two layers run half a period out of phase.
      id: 'cyclone-pulse-a',
      type: 'circle',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'position'],
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 0,
        'circle-color': '#f43f5e',
        'circle-opacity': 0,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'cyclone-pulse-b',
      type: 'circle',
      source: 'cyclones',
      filter: ['==', ['get', 'kind'], 'position'],
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 0,
        'circle-color': '#f43f5e',
        'circle-opacity': 0,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'cyclone-fcst-line',
      type: 'line',
      source: 'cyclones-fcst',
      filter: ['==', ['get', 'kind'], 'track'],
      layout: { visibility: 'none' },
      // Dashes are baked into the geometry (dashedMultiLine) — solid
      // paint here, so the pattern survives any projection/renderer.
      paint: { 'line-color': '#fb923c', 'line-width': 2.2 },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'cyclone-fcst-circle',
      type: 'circle',
      source: 'cyclones-fcst',
      filter: ['==', ['get', 'kind'], 'point'],
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        // Predicted daily positions; size by projected SSHS category
        'circle-radius': ['interpolate', ['linear'], ['coalesce', ['get', 'sshs_category'], -1],
          -1, 4, 0, 6, 1, 8, 2, 10, 3, 12, 4, 14, 5, 16],
        // Amber TD -> orange TS -> red typhoon -> rose super typhoon
        'circle-color': ['step', ['coalesce', ['get', 'wind_kt'], 0],
          '#fbbf24', 34, '#f97316', 64, '#ef4444', 100, '#e11d48'],
        'circle-opacity': 0.9,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'cyclone-fcst-label',
      type: 'symbol',
      source: 'cyclones-fcst',
      filter: ['==', ['get', 'kind'], 'point'],
      minzoom: 3,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'label'],
        'text-size': 9.5,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, 1.6],
        'text-anchor': 'top',
        'text-transform': 'uppercase',
      },
      paint: { 'text-color': '#fed7aa', 'text-halo-color': '#431407', 'text-halo-width': 1.4 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      id: 'farms-fill',
      type: 'fill',
      source: 'farms',
      minzoom: 9,
      layout: { visibility: 'none' },
      paint: { 'fill-color': '#facc15', 'fill-opacity': 0.22 },
    } as unknown as maplibregl.FillLayerSpecification,
    {
      id: 'farms-line',
      type: 'line',
      source: 'farms',
      minzoom: 9,
      layout: { visibility: 'none' },
      paint: { 'line-color': '#facc15', 'line-width': 2 },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'farms-labels',
      type: 'symbol',
      source: 'farms',
      minzoom: 11,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': 11,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, 1.2],
        'text-anchor': 'top',
      },
      paint: { 'text-color': '#fde047', 'text-halo-color': '#1c1917', 'text-halo-width': 1.5 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      id: 'stations-symbol',
      type: 'symbol',
      source: 'weather-stations',
      minzoom: 5,
      layout: {
        visibility: 'none',
        'icon-image': 'station-marker',
        'icon-size': 0.9,
        'text-field': ['get', 'name'],
        'text-size': 10,
        'text-font': ['Noto Sans Regular'],
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
      },
      paint: { 'text-color': '#bae6fd', 'text-halo-color': '#082f49', 'text-halo-width': 1.5 },
    } as unknown as maplibregl.SymbolLayerSpecification,
  )

  // --- Administrative boundaries (loaded post-style) ---
  ;['islands', 'regions', 'provinces', 'municipalities', 'barangays'].forEach((id) => {
    sources[`admin-${id}`] = { type: 'geojson', data: empty }
  })
  const adminLineCfg: [string, number, number, string, number][] = [
    ['islands', 3, 7, '#94a3b8', 1.6],
    ['regions', 4, 9, '#fbbf24', 1.8],
    ['provinces', 7, 12, '#f59e0b', 1.4],
    ['municipalities', 10, 15, '#60a5fa', 1.0],
    ['barangays', 13, 22, '#a5b4fc', 0.9],
  ]
  adminLineCfg.forEach(([id, minz, maxz, color, width]) => {
    layers.push({
      id: `admin-${id}-line`,
      type: 'line',
      source: `admin-${id}`,
      minzoom: minz,
      maxzoom: maxz,
      layout: { visibility: 'visible' },
      paint: { 'line-color': color, 'line-width': width, 'line-opacity': 0.55, 'line-dasharray': [3, 2] },
    } as unknown as maplibregl.LineLayerSpecification)
  })
  const adminLabelCfg: [string, number, number, number, string][] = [
    ['islands', 3, 6, 13, '#cbd5e1'],
    ['regions', 4, 8, 12, '#fbbf24'],
    ['provinces', 7, 11, 11, '#fdba74'],
    ['municipalities', 10, 14, 10, '#93c5fd'],
    ['barangays', 13, 22, 9, '#c7d2fe'],
  ]
  adminLabelCfg.forEach(([id, minz, maxz, size, color]) => {
    layers.push({
      id: `admin-${id}-label`,
      type: 'symbol',
      source: `admin-${id}`,
      minzoom: minz,
      maxzoom: maxz,
      layout: {
        visibility: 'visible',
        'text-field': ['get', 'name'],
        'text-size': size,
        'text-font': ['Noto Sans Bold'],
        'text-allow-overlap': false,
      },
      paint: { 'text-color': color, 'text-halo-color': '#0a0e17', 'text-halo-width': 2 },
    } as unknown as maplibregl.SymbolLayerSpecification)
  })

  // --- Drawing layers (topmost) ---
  sources['draw-fill'] = { type: 'geojson', data: empty }
  sources['draw-line'] = { type: 'geojson', data: empty }
  sources['draw-point'] = { type: 'geojson', data: empty }
  sources['draw-sketch'] = { type: 'geojson', data: empty }

  layers.push(
    {
      id: 'draw-fill',
      type: 'fill',
      source: 'draw-fill',
      paint: { 'fill-color': '#22d3ee', 'fill-opacity': ['case', ['boolean', ['feature-state', 'selected'], false], 0.35, 0.18] },
    } as unknown as maplibregl.FillLayerSpecification,
    {
      id: 'draw-outline',
      type: 'line',
      source: 'draw-fill',
      paint: { 'line-color': '#22d3ee', 'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3, 1.8] },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'draw-line',
      type: 'line',
      source: 'draw-line',
      paint: { 'line-color': '#f472b6', 'line-width': ['case', ['boolean', ['feature-state', 'selected'], false], 3.5, 2.2] },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'draw-point',
      type: 'circle',
      source: 'draw-point',
      paint: {
        'circle-radius': 6,
        'circle-color': '#f472b6',
        'circle-stroke-color': '#fff',
        'circle-stroke-width': 1.5,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'draw-sketch-line',
      type: 'line',
      source: 'draw-sketch',
      paint: { 'line-color': '#fde047', 'line-width': 2, 'line-dasharray': [2, 2] },
    } as unknown as maplibregl.LineLayerSpecification,
    {
      id: 'draw-sketch-points',
      type: 'circle',
      source: 'draw-sketch',
      paint: { 'circle-radius': 4, 'circle-color': '#fde047', 'circle-stroke-color': '#78350f', 'circle-stroke-width': 1 },
    } as unknown as maplibregl.CircleLayerSpecification,
  )

  return {
    style: {
      version: 8,
      glyphs: 'https://demotiles.maplibre.org/font/{fontstack}/{range}.pbf',
      sprite: 'https://demotiles.maplibre.org/sprite/sprite',
      sources,
      layers,
    } as maplibregl.StyleSpecification,
  }
}

export function useMap(containerRef: React.RefObject<HTMLDivElement | null>) {
  const [ready, setReady] = useState(false)
  const mapRef = useRef<maplibregl.Map | null>(null)
  const { setMap, setView } = useMapStore()
  const { openInspect } = useInspectStore()

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
      setReady(true)
    })

    // ---- Click routing: draw tools > farms > drawn features > inspect ----
    map.on('click', (e) => {
      const drawState = useDrawingStore.getState()
      if (drawState.activeTool) {
        handleDrawClick(map, e.lngLat.lng, e.lngLat.lat)
        return
      }

      const farmHits = map.queryRenderedFeatures(e.point, { layers: ['farms-fill'] })
      if (farmHits.length > 0) {
        const f = farmHits[0]
        const props = f.properties as Record<string, number>
        const center: [number, number] = [props.center_lon, props.center_lat]
        map.flyTo({ center, zoom: 14, speed: 1.4, essential: true })
        openInspect(props.center_lat, props.center_lon)
        return
      }

      const drawnHits = map.queryRenderedFeatures(e.point, {
        layers: ['draw-fill', 'draw-line', 'draw-point'],
      })
      if (drawnHits.length > 0) {
        const fid = drawnHits[0].properties?.__fid as number | undefined
        useDrawingStore.getState().selectFeature(fid ?? null)
        return
      }
      if (useDrawingStore.getState().selectedId !== null) {
        useDrawingStore.getState().selectFeature(null)
        return
      }
      openInspect(e.lngLat.lat, e.lngLat.lng)
    })

    map.on('dblclick', (e) => {
      const { activeTool, finishSketch } = useDrawingStore.getState()
      if (activeTool === 'polygon' || activeTool === 'line') {
        e.preventDefault()
        finishSketch()
      }
    })

    mapRef.current = map
    setMap(map)

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

// --------------------------------------------------------------------------
// Draw interaction
// --------------------------------------------------------------------------

function handleDrawClick(map: maplibregl.Map, lng: number, lat: number) {
  const state = useDrawingStore.getState()
  const tool = state.activeTool
  if (!tool) return

  if (tool === 'point') {
    state.addSketchPoint([lng, lat])
    setTimeout(() => useDrawingStore.getState().finishSketch(), 0)
    return
  }
  if ((tool === 'rectangle' || tool === 'circle') && state.sketchCoords.length >= 2) {
    state.finishSketch()
    return
  }
  state.addSketchPoint([lng, lat])
  if (tool === 'rectangle' || tool === 'circle') {
    if (useDrawingStore.getState().sketchCoords.length === 2) {
      setTimeout(() => useDrawingStore.getState().finishSketch(), 0)
    }
  }
}

// --------------------------------------------------------------------------
// Product visibility (with Sentinel-2 underlay beneath Esri deep zoom)
// --------------------------------------------------------------------------

const UNDERLAYS: Record<string, string> = {
  'esri-world': 'sentinel2-cloudless',
}

function applyProductVisibility(map: maplibregl.Map, activeProduct: string) {
  const underlay = UNDERLAYS[activeProduct] ?? null
  // Deep-zoom assist: viewing Sentinel-2 (~10 m) past z15 would show
  // 32x over-stretched pixels even though ~1 m Esri imagery exists.
  // Stack Esri ON TOP from z15 so the sharpest real source wins; S2
  // remains visible beneath, filling Esri's clouds and coverage gaps.
  const deepZoomEsri = activeProduct === 'sentinel2-cloudless'
  for (const p of ALL_PRODUCTS) {
    const layerId = `${SAT_PREFIX}${p.id}`
    if (!map.getLayer(layerId)) continue
    let visible = p.id === activeProduct || p.id === underlay
    if (deepZoomEsri && p.id === 'esri-world') {
      visible = map.getZoom() >= 15
    }
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
  }
}

export function setProductTiles(map: maplibregl.Map, productId: string, time: string | null,
                                 palette?: string) {
  const product = getProduct(productId)
  const source = map.getSource(`${SAT_PREFIX}${productId}`) as maplibregl.RasterTileSource | undefined
  if (!product || !source) return
  try {
    source.setTiles(product.tiles(time ?? undefined, palette))
  } catch {
    // older runtimes: recreate source
    map.removeSource(`${SAT_PREFIX}${productId}`)
    map.addSource(`${SAT_PREFIX}${productId}`, {
      type: 'raster',
      tiles: product.tiles(time ?? undefined, palette),
      tileSize: product.tileSize,
      maxzoom: product.maxzoom,
      attribution: product.attribution,
    })
  }
}
