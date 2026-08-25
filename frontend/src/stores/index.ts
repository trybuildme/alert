import { create } from 'zustand'
import maplibregl from 'maplibre-gl'

export type DrawTool = 'point' | 'line' | 'polygon' | 'rectangle' | 'circle' | null

interface MapState {
  map: maplibregl.Map | null
  zoom: number
  center: [number, number]
  bearing: number
  setMap: (m: maplibregl.Map | null) => void
  setView: (zoom: number, center: [number, number], bearing?: number) => void
}

export const useMapStore = create<MapState>((set) => ({
  map: null,
  zoom: 7.2,
  center: [120.5936, 16.5],
  bearing: 0,
  setMap: (map) => set({ map }),
  setView: (zoom, center, bearing = 0) => set({ zoom, center, bearing }),
}))

interface SatelliteState {
  activeProduct: string
  currentTime: string | null
  playing: boolean
  times: string[]
  irEnhanced: boolean
  setActiveProduct: (id: string) => void
  setCurrentTime: (t: string | null) => void
  setPlaying: (p: boolean) => void
  setTimes: (ts: string[]) => void
  setIrEnhanced: (v: boolean) => void
}

export const useSatelliteStore = create<SatelliteState>((set) => ({
  activeProduct: 'esri-world',
  currentTime: null,
  playing: false,
  times: [],
  irEnhanced: false,
  setActiveProduct: (id) => set({ activeProduct: id }),
  setCurrentTime: (t) => set({ currentTime: t }),
  setPlaying: (playing) => set({ playing }),
  setTimes: (times) => set({ times }),
  setIrEnhanced: (irEnhanced) => set({ irEnhanced }),
}))

export interface LayerInfo {
  id: string
  name: string
  description: string
  visible: boolean
  opacity: number
  legend?: { label: string; color: string }[]
}

const INITIAL_LAYERS: LayerInfo[] = [
  { id: 'satellite', name: 'Satellite', description: 'Active satellite product', visible: true, opacity: 1 },
  { id: 'place-labels', name: 'Place Labels', description: 'City, town and village names (Google Maps style) — OSM settlements per viewport', visible: true, opacity: 1,
    legend: [{ label: 'City', color: '#ffffff' }, { label: 'Town', color: '#f8fafc' }, { label: 'Village / district', color: '#f1f5f9' }] },
  { id: 'admin-boundaries', name: 'Administrative Boundaries', description: 'Region → province → municipality → barangay hierarchy', visible: true, opacity: 1 },
  {
    id: 'roads', name: 'Roads', description: 'OSM major roads and farm tracks', visible: false, opacity: 1,
    legend: [{ label: 'Major road', color: '#ffffff' }, { label: 'Farm track', color: '#a1887f' }],
  },
  { id: 'rivers', name: 'Rivers', description: 'OSM waterways and water bodies', visible: false, opacity: 1, legend: [{ label: 'Water', color: '#1e88e5' }] },
  { id: 'elevation', name: 'Elevation', description: 'Hypsometric DEM hillshade (30 m class)', visible: false, opacity: 0.85, legend: [{ label: 'Lowland', color: '#3a6e4a' }, { label: 'Upland', color: '#ac845c' }, { label: 'Peak', color: '#ffffff' }] },
  { id: 'agricultural-areas', name: 'Agricultural Areas', description: 'Monitored farm polygons', visible: false, opacity: 1, legend: [{ label: 'Farm boundary', color: '#facc15' }] },
  {
    id: 'flood-risk', name: 'Flood Risk', description: 'Zoom-linked flood risk across Luzon — province squares refine to municipal detail as you zoom', visible: false, opacity: 1,
    legend: [
      { label: 'High-risk province (zoomed out)', color: '#ef4444' },
      { label: 'High-risk municipality (zoomed in)', color: '#ef4444' },
      { label: 'Medium risk', color: '#f59e0b' },
      { label: 'Low risk', color: '#3b82f6' },
    ],
  },
  { id: 'weather-stations', name: 'Weather Stations', description: 'Synoptic station network', visible: false, opacity: 1, legend: [{ label: 'Station', color: '#38bdf8' }] },
  { id: 'rainfall', name: 'Rainfall', description: '3-hour accumulated rainfall estimate', visible: false, opacity: 0.75, legend: [{ label: '< 5 mm', color: '#bae6fd' }, { label: '5–15 mm', color: '#38bdf8' }, { label: '> 15 mm', color: '#1d4ed8' }] },
  { id: 'alerts', name: 'Alerts', description: 'Active weather and crop alerts', visible: false, opacity: 1, legend: [{ label: 'Active alert zone', color: '#fb923c' }] },
  {
    id: 'earthquakes', name: 'Earthquakes · Live', description: 'Detected events from USGS feeds (PH region focus) — real-time, not forecasts or predictions', visible: true, opacity: 1,
    legend: [
      { label: 'Shallow < 70 km', color: '#ff2020' },
      { label: 'Intermediate 70–300 km', color: '#ff9800' },
      { label: 'Deep > 300 km', color: '#38bdf8' },
    ],
  },
  {
    id: 'tsunamis', name: 'Tsunami Bulletins', description: 'Issued tsunami products from NOAA/NWS tsunami.gov — official bulletins, not forecasts', visible: false, opacity: 1,
    legend: [{ label: 'Issued bulletin', color: '#22d3ee' }],
  },
  {
    id: 'volcanoes', name: 'Volcano Sites', description: 'PHIVOLCS-monitored volcano registry (static sites, not live alert levels)', visible: true, opacity: 1,
    legend: [{ label: 'Monitored volcano', color: '#f97316' }],
  },
  {
    id: 'cyclones', name: 'Cyclone Tracks', description: 'Active tropical cyclones — NOAA IBTrACS best-track (~3× weekly, not operational warnings). Colors per PAGASA / panahon.gov.ph classification', visible: false, opacity: 1,
    legend: [
      { label: 'Tropical Depression', color: '#00e400' },
      { label: 'Tropical Storm', color: '#ffe400' },
      { label: 'Severe Tropical Storm', color: '#ff9800' },
      { label: 'Typhoon', color: '#ff2020' },
      { label: 'Super Typhoon', color: '#e000e0' },
    ],
  },
  {
    id: 'cyclone-forecast', name: 'Cyclone Forecast · 7-Day', description: 'Naive persistence extrapolation of best-track motion — NOT an official PAGASA/JTWC forecast. Colors per PAGASA / panahon.gov.ph classification', visible: false, opacity: 1,
    legend: [
      { label: 'Predicted track', color: '#fb923c' },
      { label: 'Tropical Depression', color: '#00e400' },
      { label: 'Tropical Storm', color: '#ffe400' },
      { label: 'Severe Tropical Storm', color: '#ff9800' },
      { label: 'Typhoon', color: '#ff2020' },
      { label: 'Super Typhoon', color: '#e000e0' },
    ],
  },
  {
    id: 'cyclone-clouds', name: 'Cyclone Clouds · Himawari-9 IR', description: 'Live infrared cloud canopy around active systems (latest 10-min frame, qualitative)', visible: false, opacity: 0.75,
    legend: [{ label: 'IR cloud tops', color: '#94a3b8' }],
  },
  {
    id: 'par', name: 'Philippine Area of Responsibility', description: 'PAGASA PAR boundary: 5°N 115°E → 15°N 115°E → 21°N 120°E → 25°N 120°E → 25°N 135°E → 5°N 135°E', visible: true, opacity: 1,
    legend: [{ label: 'PAR boundary (solid)', color: '#facc15' }],
  },
]

interface LayerState {
  layers: LayerInfo[]
  toggle: (id: string) => void
  setOpacity: (id: string, opacity: number) => void
  moveUp: (id: string) => void
  moveDown: (id: string) => void
}

// --- Session persistence -------------------------------------------------
// The last sequence of layers (order, visibility, opacity) survives page
// reloads via localStorage. Metadata (names, descriptions, legends) is NOT
// persisted — it always comes fresh from INITIAL_LAYERS so code changes
// propagate; only user intent (visible/opacity/order) is restored. Layers
// unknown to the stored snapshot keep their defaults.
// v2: bumped 2026-08-24 so pre-existing snapshots (saved while PAR
// defaulted to off) stop overriding the new defaults. Users keep their
// toggles from here forward.
// v3: bumped 2026-08-25 so snapshots saved before the volcano layer
// shipped stop forcing it off; volcano now defaults to visible.
const LAYER_STORAGE_KEY = 'noah.layers.v3'

type SavedLayerState = { visible?: boolean; opacity?: number }

function hydrateLayers(): LayerInfo[] {
  try {
    const raw = localStorage.getItem(LAYER_STORAGE_KEY)
    if (!raw) return INITIAL_LAYERS
    const saved = JSON.parse(raw) as { order?: string[]; state?: Record<string, SavedLayerState> }
    const applySaved = (base: LayerInfo): LayerInfo => {
      const s = saved.state?.[base.id]
      return {
        ...base,
        visible: typeof s?.visible === 'boolean' ? s.visible : base.visible,
        opacity: typeof s?.opacity === 'number' ? Math.min(1, Math.max(0, s.opacity)) : base.opacity,
      }
    }
    const remaining = new Map(INITIAL_LAYERS.map((l) => [l.id, l]))
    const out: LayerInfo[] = []
    for (const id of saved.order ?? []) {
      const base = remaining.get(id)
      if (!base) continue
      out.push(applySaved(base))
      remaining.delete(id)
    }
    // Layers never seen by this browser (or absent from snapshot) keep
    // defaults and trail the remembered ones in stock order.
    for (const base of INITIAL_LAYERS) {
      if (remaining.has(base.id)) out.push(applySaved(base))
    }
    return out
  } catch {
    return INITIAL_LAYERS
  }
}

function persistLayers(layers: LayerInfo[]) {
  try {
    const payload = {
      order: layers.map((l) => l.id),
      state: Object.fromEntries(layers.map((l) => [l.id, { visible: l.visible, opacity: l.opacity }])),
    }
    localStorage.setItem(LAYER_STORAGE_KEY, JSON.stringify(payload))
  } catch { /* private mode / quota: session-only then */ }
}

export const useLayerStore = create<LayerState>((set) => ({
  layers: hydrateLayers(),
  toggle: (id) =>
    set((s) => ({
      layers: s.layers.map((l) => (l.id === id ? { ...l, visible: !l.visible } : l)),
    })),
  setOpacity: (id, opacity) =>
    set((s) => ({ layers: s.layers.map((l) => (l.id === id ? { ...l, opacity } : l)) })),
  moveUp: (id) =>
    set((s) => {
      const idx = s.layers.findIndex((l) => l.id === id)
      if (idx <= 0) return s
      const next = [...s.layers]
      ;[next[idx - 1], next[idx]] = [next[idx], next[idx - 1]]
      return { layers: next }
    }),
  moveDown: (id) =>
    set((s) => {
      const idx = s.layers.findIndex((l) => l.id === id)
      if (idx === -1 || idx === s.layers.length - 1) return s
      const next = [...s.layers]
      ;[next[idx + 1], next[idx]] = [next[idx], next[idx + 1]]
      return { layers: next }
    }),
}))

useLayerStore.subscribe((state) => persistLayers(state.layers))

export interface InspectData {
  location: { latitude: number; longitude: number }
  administrative_context: { level: string; name: string }[]
  satellite: Record<string, unknown>
  agriculture: Record<string, unknown>
  weather: Record<string, unknown>
  flood_risk: Record<string, unknown> | null
  farms_nearby: Record<string, unknown>[]
}

interface InspectState {
  open: boolean
  loading: boolean
  lat: number | null
  lon: number | null
  data: InspectData | null
  openInspect: (lat: number, lon: number) => void
  closeInspect: () => void
  setData: (d: InspectData | null) => void
  setLoading: (b: boolean) => void
}

export const useInspectStore = create<InspectState>((set) => ({
  open: false,
  loading: false,
  lat: null,
  lon: null,
  data: null,
  openInspect: (lat, lon) => set({ open: true, loading: true, lat, lon, data: null }),
  closeInspect: () => set({ open: false }),
  setData: (data) => set({ data, loading: false }),
  setLoading: (loading) => set({ loading }),
}))

export interface DrawnFeature {
  id: number
  tool: Exclude<DrawTool, null>
  coordinates: number[][] | number[][]
  areaKm2?: number
  perimeterKm?: number
  lengthKm?: number
  radiusKm?: number
  center: [number, number]
}

interface DrawingState {
  activeTool: DrawTool
  sketchCoords: [number, number][]
  features: DrawnFeature[]
  selectedId: number | null
  nextId: number
  setTool: (t: DrawTool) => void
  addSketchPoint: (pt: [number, number]) => void
  finishSketch: () => void
  cancelSketch: () => void
  clearAll: () => void
  selectFeature: (id: number | null) => void
}

export const useDrawingStore = create<DrawingState>((set) => ({
  activeTool: null,
  sketchCoords: [],
  features: [],
  selectedId: null,
  nextId: 1,
  setTool: (tool) => set({ activeTool: tool, sketchCoords: [], selectedId: null }),
  addSketchPoint: (pt) => set((s) => ({ sketchCoords: [...s.sketchCoords, pt] })),
  finishSketch: () =>
    set((s) => {
      if (s.sketchCoords.length < 2 || !s.activeTool) return s
      const feature = buildFeature(s.nextId, s.activeTool, s.sketchCoords)
      if (!feature) return s
      return {
        features: [...s.features, feature],
        sketchCoords: [],
        activeTool: null,
        nextId: s.nextId + 1,
        selectedId: feature.id,
      }
    }),
  cancelSketch: () => set({ sketchCoords: [], activeTool: null }),
  clearAll: () => set({ features: [], sketchCoords: [], selectedId: null, activeTool: null }),
  selectFeature: (id) => set({ selectedId: id }),
}))

function haversineKm(a: [number, number], b: [number, number]): number {
  const R = 6371.0088
  const dLat = ((b[1] - a[1]) * Math.PI) / 180
  const dLon = ((b[0] - a[0]) * Math.PI) / 180
  const la1 = (a[1] * Math.PI) / 180
  const la2 = (b[1] * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export function pathLengthKm(coords: [number, number][]): number {
  let total = 0
  for (let i = 1; i < coords.length; i++) total += haversineKm(coords[i - 1], coords[i])
  return total
}

export function polygonAreaKm2(coords: [number, number][]): number {
  // Spherical excess formula (Turf.js-style ring area)
  const R = 6371.0088
  if (coords.length < 3) return 0
  let total = 0
  for (let i = 0; i < coords.length; i++) {
    const [lon1, lat1] = coords[i]
    const [lon2, lat2] = coords[(i + 1) % coords.length]
    total += ((lon2 - lon1) * Math.PI) / 180 * (2 + Math.sin((lat1 * Math.PI) / 180) + Math.sin((lat2 * Math.PI) / 180))
  }
  return Math.abs((total * R * R) / 2)
}

function buildFeature(id: number, tool: Exclude<DrawTool, null>, coords: [number, number][]): DrawnFeature | null {
  if (tool === 'point') {
    return { id, tool, coordinates: coords, center: coords[0] }
  }
  if (tool === 'line') {
    return { id, tool, coordinates: coords, lengthKm: pathLengthKm(coords), center: coords[Math.floor(coords.length / 2)] }
  }
  if (tool === 'polygon') {
    const ring = [...coords, coords[0]]
    return {
      id, tool, coordinates: ring,
      areaKm2: polygonAreaKm2(ring),
      perimeterKm: pathLengthKm(ring),
      center: centroid(coords),
    }
  }
  if (tool === 'rectangle' && coords.length >= 2) {
    const [a, b] = coords
    const ring: [number, number][] = [
      a, [b[0], a[1]], b, [a[0], b[1]], a,
    ]
    return {
      id, tool: 'rectangle', coordinates: ring,
      areaKm2: polygonAreaKm2(ring),
      perimeterKm: pathLengthKm(ring),
      center: [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2],
    }
  }
  if (tool === 'circle' && coords.length >= 2) {
    const [c, edge] = coords
    const radiusKm = haversineKm(c, edge)
    const pts: [number, number][] = []
    for (let i = 0; i < 64; i++) {
      const bearing = (i / 64) * 2 * Math.PI
      const latR = (c[1] * Math.PI) / 180
      const lonR = (c[0] * Math.PI) / 180
      const brg = bearing
      const dr = radiusKm / 6371.0088
      const lat2 = Math.asin(Math.sin(latR) * Math.cos(dr) + Math.cos(latR) * Math.sin(dr) * Math.cos(brg))
      const lon2 = lonR + Math.atan2(Math.sin(brg) * Math.sin(dr) * Math.cos(latR), Math.cos(dr) - Math.sin(latR) * Math.sin(lat2))
      pts.push([(lon2 * 180) / Math.PI, (lat2 * 180) / Math.PI])
    }
    pts.push(pts[0])
    return {
      id, tool: 'circle', coordinates: pts,
      areaKm2: Math.PI * radiusKm ** 2,
      perimeterKm: 2 * Math.PI * radiusKm,
      radiusKm,
      center: c,
    }
  }
  return null
}

function centroid(coords: [number, number][]): [number, number] {
  const n = coords.length
  return [coords.reduce((s, c) => s + c[0], 0) / n, coords.reduce((s, c) => s + c[1], 0) / n]
}

interface UIState {
  basemap: string
  mode2D: boolean
  layerPanelOpen: boolean
  searchQuery: string
  gpsAccuracyM: number | null
  gpsError: string | null
  forecastPanelOpen: boolean
  forecastMeta: { generatedAt: string | null; methodology: string | null; unavailable: boolean }
  eqPanelOpen: boolean
  eqMinMag: number
  eqSelectedUid: string | null
  setBasemap: (b: string) => void
  setMode2D: (v: boolean) => void
  toggleLayerPanel: () => void
  setSearchQuery: (q: string) => void
  setGpsFix: (accuracyM: number | null, error?: string | null) => void
  toggleForecastPanel: () => void
  setForecastMeta: (m: { generatedAt: string | null; methodology: string | null; unavailable: boolean }) => void
  toggleEqPanel: () => void
  setEqMinMag: (v: number) => void
  setEqSelectedUid: (uid: string | null) => void
}

export const useUIStore = create<UIState>((set) => ({
  basemap: 'satellite',
  mode2D: true,
  layerPanelOpen: true,
  searchQuery: '',
  gpsAccuracyM: null,
  gpsError: null,
  forecastPanelOpen: false,
  forecastMeta: { generatedAt: null, methodology: null, unavailable: false },
  setBasemap: (basemap) => set({ basemap }),
  setMode2D: (mode2D) => set({ mode2D }),
  toggleLayerPanel: () => set((s) => ({ layerPanelOpen: !s.layerPanelOpen })),
  setSearchQuery: (searchQuery) => set({ searchQuery }),
  setGpsFix: (accuracyM, error = null) => set({ gpsAccuracyM: accuracyM, gpsError: error }),
  toggleForecastPanel: () => set((s) => ({ forecastPanelOpen: !s.forecastPanelOpen })),
  setForecastMeta: (forecastMeta) => set({ forecastMeta }),
  eqPanelOpen: false,
  eqMinMag: 2.5,
  eqSelectedUid: null,
  toggleEqPanel: () => set((s) => ({ eqPanelOpen: !s.eqPanelOpen })),
  setEqMinMag: (eqMinMag) => set({ eqMinMag }),
  setEqSelectedUid: (eqSelectedUid) => set({ eqSelectedUid }),
}))
