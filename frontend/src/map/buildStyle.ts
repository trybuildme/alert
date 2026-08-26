// MapLibre style construction: sources and layers for every NOAH overlay.
// Pure data — no map instance required. Layer order here defines paint
// order: basemaps at the bottom, satellite rasters above, then cloud
// canopy, vector themes, admin boundaries, drawing tools on top.

import type maplibregl from 'maplibre-gl'
import { ALL_PRODUCTS, BASEMAPS, PAR_FEATURES } from '../config/mapConfig'

const SAT_PREFIX = 'sat-product-'

export function buildStyle() {
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
    attribution: 'NOAH synthetic DEM',
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

  // --- Place labels (Google Maps style: white text, dark halo, sized
  // by settlement class, revealed progressively with zoom) ---
  const placeHalo = ['interpolate', ['linear'], ['zoom'],
    3, 1.1, 8, 1.4, 14, 1.8] as unknown as maplibregl.ExpressionInputType
  layers.push(
    {
      // Settlement dot beneath the label — Google's satellite-view cue
      id: 'places-dot',
      type: 'circle',
      source: 'places',
      filter: ['in', ['get', 'class'],
        ['literal', ['city', 'town', 'village', 'borough', 'suburb',
                     'quarter', 'neighbourhood']]],
      minzoom: 5,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['match', ['get', 'class'], 'city', 2.6, 2],
        'circle-color': '#ffffff',
        'circle-stroke-color': 'rgba(0,0,0,0.55)',
        'circle-stroke-width': 1,
        'circle-opacity': 0.9,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'places-city',
      type: 'symbol',
      source: 'places',
      filter: ['==', ['get', 'class'], 'city'],
      minzoom: 3,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 3, 12, 8, 14.5, 13, 17],
        'text-font': ['Noto Sans Bold'],
        'text-letter-spacing': 0.08,
        'text-offset': [0, -1.4],
        'text-anchor': 'bottom',
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(0,0,0,0.75)',
        'text-halo-width': placeHalo,
      },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      id: 'places-town',
      type: 'symbol',
      source: 'places',
      filter: ['==', ['get', 'class'], 'town'],
      minzoom: 6,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 6, 10.5, 11, 13, 15, 15],
        'text-font': ['Noto Sans Bold'],
        'text-letter-spacing': 0.05,
        'text-offset': [0, -1.35],
        'text-anchor': 'bottom',
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(0,0,0,0.75)',
        'text-halo-width': placeHalo,
      },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      id: 'places-village',
      type: 'symbol',
      source: 'places',
      filter: ['in', ['get', 'class'],
        ['literal', ['village', 'borough', 'suburb', 'quarter',
                     'neighbourhood']]],
      minzoom: 10,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 10, 9.5, 15, 13],
        'text-font': ['Noto Sans Regular'],
        'text-letter-spacing': 0.03,
        'text-offset': [0, -1.3],
        'text-anchor': 'bottom',
      },
      paint: {
        'text-color': '#f1f5f9',
        'text-halo-color': 'rgba(0,0,0,0.75)',
        'text-halo-width': placeHalo,
      },
    } as unknown as maplibregl.SymbolLayerSpecification,
  )

  // --- Thematic GeoJSON placeholders (data loaded post-style) ---
  const empty: GeoJSON.FeatureCollection = { type: 'FeatureCollection', features: [] }
  ;['flood-risk', 'rainfall', 'alerts', 'farms', 'weather-stations', 'cyclones',
    'cyclones-fcst', 'earthquakes', 'tsunamis', 'volcanoes',
    'flood-rain-stations', 'flood-water-stations', 'flood-alerts',
    // roads/waterways/places: geometry lazy-loaded per viewport on moveend
    'roads', 'roads-minor', 'waterways', 'places'].forEach((id) => {
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
      paint: {
        // panahon.gov.ph category palette, keyed on peak PAGASA code
        'line-color': ['match', ['get', 'pagasa_code_peak'],
          'TD', '#00e400', 'TS', '#ffe400', 'STS', '#ff9800',
          'TY', '#ff2020', 'ST', '#e000e0', '#f43f5e'],
        'line-width': 2, 'line-dasharray': [2, 1.5],
      },
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
        // PAGASA classification colors (panahon.gov.ph): TD green,
        // TS yellow, STS orange, TY red, STY magenta; grey fallback
        'circle-color': ['match', ['get', 'pagasa_code'],
          'TD', '#00e400', 'TS', '#ffe400', 'STS', '#ff9800',
          'TY', '#ff2020', 'ST', '#e000e0', '#9aa5b1'],
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
        // PAGASA local name leads once the storm is inside the PAR
        'text-field': ['coalesce', ['get', 'display_name'], ['get', 'name']],
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
        'circle-color': ['match', ['get', 'pagasa_code'],
          'TD', '#00e400', 'TS', '#ffe400', 'STS', '#ff9800',
          'TY', '#ff2020', 'ST', '#e000e0', '#f43f5e'],
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
        'circle-color': ['match', ['get', 'pagasa_code'],
          'TD', '#00e400', 'TS', '#ffe400', 'STS', '#ff9800',
          'TY', '#ff2020', 'ST', '#e000e0', '#f43f5e'],
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
        // PAGASA category colors (panahon.gov.ph) keyed on the daily
        // day-max classification code emitted by /api/cyclones/forecast
        'circle-color': ['match', ['get', 'code'],
          'TD', '#00e400', 'TS', '#ffe400', 'STS', '#ff9800',
          'TY', '#ff2020', 'ST', '#e000e0', '#9aa5b1'],
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
    // --- Earthquakes: detected events (USGS), magnitude-scaled,
    // depth-colored; selected event gets a bright ring via 'eq-selected'.
    {
      id: 'eq-circle',
      type: 'circle',
      source: 'earthquakes',
      minzoom: 2,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'],
          ['coalesce', ['get', 'magnitude'], 0],
          2, 4, 4, 8, 5, 12, 6, 17, 7, 23, 8, 30],
        // Seismological depth convention: shallow hot -> deep cool
        'circle-color': ['step', ['coalesce', ['get', 'depth_km'], 0],
          '#ff2020', 70, '#ff9800', 300, '#38bdf8'],
        'circle-opacity': 0.55,
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.2,
        'circle-stroke-opacity': ['case',
          ['boolean', ['feature-state', 'fresh'], false], 1, 0.7],
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'eq-selected',
      type: 'circle',
      source: 'earthquakes',
      filter: ['==', ['get', 'uid'], ['literal', null]],
      minzoom: 2,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'],
          ['coalesce', ['get', 'magnitude'], 0], 2, 10, 6, 26, 8, 38],
        'circle-color': 'rgba(255,255,255,0)',
        'circle-stroke-color': '#fbbf24',
        'circle-stroke-width': 2.5,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      // Magnitude label above each marker ("M 4.8"), Google-style
      // white-on-dark-halo so it reads over satellite imagery
      id: 'eq-label',
      type: 'symbol',
      source: 'earthquakes',
      minzoom: 3,
      layout: {
        visibility: 'none',
        'text-field': ['case',
          ['!=', ['get', 'magnitude'], null],
          ['concat', 'M ', ['to-string', ['get', 'magnitude']]],
          'M ?'],
        'text-size': ['interpolate', ['linear'], ['zoom'], 3, 9.5, 7, 11.5, 12, 13],
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, -1.15],
        'text-anchor': 'bottom',
        'text-letter-spacing': 0.04,
      },
      paint: {
        'text-color': '#ffffff',
        'text-halo-color': 'rgba(0,0,0,0.8)',
        'text-halo-width': 1.4,
      },
    } as unknown as maplibregl.SymbolLayerSpecification,
    // --- Tsunamis: issued bulletins from NOAA/NWS tsunami.gov (CAP
    // feed) — cyan rings; label carries the product title.
    {
      id: 'tsunami-circle',
      type: 'circle',
      source: 'tsunamis',
      minzoom: 2,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 2, 7, 8, 16],
        'circle-color': 'rgba(34,211,238,0.25)',
        'circle-stroke-color': '#22d3ee',
        'circle-stroke-width': 2,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'tsunami-label',
      type: 'symbol',
      source: 'tsunamis',
      minzoom: 3,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'title'],
        'text-size': 10,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, 1.4],
        'text-anchor': 'top',
      },
      paint: { 'text-color': '#a5f3fc', 'text-halo-color': '#083344', 'text-halo-width': 1.4 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    // --- Volcanoes: PHIVOLCS-monitored site registry (static) —
    // orange markers; registry only, NOT live alert levels.
    {
      id: 'volcano-circle',
      type: 'circle',
      source: 'volcanoes',
      minzoom: 4,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 4.5, 10, 9],
        // green while flagged currently active, orange otherwise
        // (active_now is a curated manual snapshot, not a live feed)
        'circle-color': ['case',
          ['boolean', ['get', 'active_now'], false], '#22c55e', '#f97316'],
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.4,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'volcano-label',
      type: 'symbol',
      source: 'volcanoes',
      minzoom: 6,
      layout: {
        visibility: 'none',
        'text-field': ['get', 'name'],
        'text-size': 10,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, -1.3],
        'text-anchor': 'bottom',
      },
      paint: { 'text-color': '#fdba74', 'text-halo-color': '#431407', 'text-halo-width': 1.4 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    // --- Flood monitoring: live station markers (real Open-Meteo
    // rainfall; water gauges offline until an authorized feed exists) ---
    {
      id: 'flood-rain-circle',
      type: 'circle',
      source: 'flood-rain-stations',
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 4, 10, 9],
        'circle-color': ['case',
          ['>=', ['get', 'mmh'], 30], '#a855f7',
          ['>=', ['get', 'mmh'], 15], '#ef4444',
          ['>=', ['get', 'mmh'], 7.5], '#fb923c',
          ['>=', ['get', 'mmh'], 2.5], '#facc15',
          '#38bdf8'],
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.2,
        'circle-opacity': 0.95,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'flood-rain-label',
      type: 'symbol',
      source: 'flood-rain-stations',
      minzoom: 7,
      layout: {
        visibility: 'none',
        'text-field': ['concat', ['get', 'mmhLabel'], ' mm/h'],
        'text-size': 9,
        'text-font': ['Noto Sans Bold'],
        'text-offset': [0, 1.3],
        'text-anchor': 'top',
      },
      paint: { 'text-color': '#bae6fd', 'text-halo-color': '#082f49', 'text-halo-width': 1.2 },
    } as unknown as maplibregl.SymbolLayerSpecification,
    {
      id: 'flood-water-circle',
      type: 'circle',
      source: 'flood-water-stations',
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 5,
        'circle-color': '#64748b',
        'circle-stroke-color': '#cbd5e1',
        'circle-stroke-width': 1,
        'circle-opacity': 0.8,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'flood-alert-halo',
      type: 'circle',
      source: 'flood-alerts',
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': ['interpolate', ['linear'], ['zoom'], 3, 12, 10, 26],
        'circle-color': '#ef4444',
        'circle-opacity': 0.18,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
    {
      id: 'flood-alert-marker',
      type: 'circle',
      source: 'flood-alerts',
      minzoom: 3,
      layout: { visibility: 'none' },
      paint: {
        'circle-radius': 7,
        'circle-color': ['match', ['get', 'level'],
          'CRITICAL', '#a855f7',
          'WARNING', '#ef4444',
          'WATCH', '#fb923c',
          'ADVISORY', '#facc15',
          '#94a3b8'],
        'circle-stroke-color': '#ffffff',
        'circle-stroke-width': 1.5,
      },
    } as unknown as maplibregl.CircleLayerSpecification,
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
