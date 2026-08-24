import maplibregl from 'maplibre-gl'

export interface SatelliteProduct {
  id: string
  name: string
  satellite: string
  color: string
  tiles: (time?: string, palette?: string) => string[]
  tileSize: number
  maxzoom: number
  maxNativeZoom: number
  nativeResolutionKm: number
  resolutionLabel: string
  temporalResolution: string
  timeDependent: boolean
  attribution: string
  live?: boolean
}

const backendTile = (product: string, time?: string, palette?: string) => {
  const params: string[] = []
  if (time) params.push(`time=${encodeURIComponent(time)}`)
  if (palette) params.push(`palette=${palette}`)
  return `/tiles/${product}/{z}/{x}/{y}.png${params.length ? '?' + params.join('&') : ''}`
}

export const SATELLITE_PRODUCTS: SatelliteProduct[] = [
  {
    id: 'modis-true-color',
    name: 'True Color · Live',
    satellite: 'NASA Terra MODIS',
    color: '#22c55e',
    tiles: (time) => [backendTile('modis-true-color', time)],
    tileSize: 256,
    maxzoom: 9,
    maxNativeZoom: 9,
    nativeResolutionKm: 0.25,
    resolutionLabel: '250 m',
    temporalResolution: 'daily',
    timeDependent: true,
    live: true,
    attribution: 'NASA GIBS / LANCE MODIS Terra corrected reflectance',
  },
  {
    id: 'himawari-clean-ir',
    name: 'Clean Infrared · Live',
    satellite: 'Himawari-9',
    color: '#ef4444',
    tiles: (time, palette) => [backendTile('himawari-clean-ir', time, palette)],
    tileSize: 256,
    // Raster-source maxzoom = deepest GIBS matrix level; MapLibre
    // over-zooms client-side beyond this (server returns blanks past it).
    maxzoom: 6,
    maxNativeZoom: 6,
    nativeResolutionKm: 2.0,
    resolutionLabel: '2 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    live: true,
    attribution: 'NASA GIBS / JMA Himawari-9 AHI B13',
  },
  {
    id: 'himawari-air-mass',
    name: 'Air Mass · Live',
    satellite: 'Himawari-9',
    color: '#f97316',
    tiles: (time) => [backendTile('himawari-air-mass', time)],
    tileSize: 256,
    maxzoom: 6,
    maxNativeZoom: 6,
    nativeResolutionKm: 2.0,
    resolutionLabel: '2 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    live: true,
    attribution: 'NASA GIBS / JMA Himawari-9 AHI RGB composite',
  },
  {
    id: 'himawari-visible-red',
    name: 'Visible Red · Live',
    satellite: 'Himawari-9',
    color: '#84cc16',
    tiles: (time) => [backendTile('himawari-visible-red', time)],
    tileSize: 256,
    maxzoom: 7,
    maxNativeZoom: 7,
    nativeResolutionKm: 1.0,
    resolutionLabel: '1 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    live: true,
    attribution: 'NASA GIBS / JMA Himawari-9 AHI B3 (daytime only)',
  },
  {
    id: 'true-color',
    name: 'True Color · Simulated',
    satellite: 'Himawari-9 (synthetic)',
    color: '#22c55e',
    tiles: (time) => [backendTile('true-color', time)],
    tileSize: 256,
    maxzoom: 18,
    maxNativeZoom: 8,
    nativeResolutionKm: 1.0,
    resolutionLabel: '1 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    attribution: 'AURORA-GIS synthetic Himawari-class feed',
  },
  {
    id: 'infrared',
    name: 'Infrared',
    satellite: 'Himawari-9',
    color: '#ef4444',
    tiles: (time) => [backendTile('infrared', time)],
    tileSize: 256,
    maxzoom: 18,
    maxNativeZoom: 7,
    nativeResolutionKm: 2.0,
    resolutionLabel: '2 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    attribution: 'AURORA-GIS synthetic Himawari-class feed',
  },
  {
    id: 'water-vapor',
    name: 'Water Vapor',
    satellite: 'Himawari-9',
    color: '#3b82f6',
    tiles: (time) => [backendTile('water-vapor', time)],
    tileSize: 256,
    maxzoom: 18,
    maxNativeZoom: 7,
    nativeResolutionKm: 2.0,
    resolutionLabel: '2 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    attribution: 'AURORA-GIS synthetic Himawari-class feed',
  },
  {
    id: 'cloud-temp',
    name: 'Cloud Temperature',
    satellite: 'Himawari-9',
    color: '#8b5cf6',
    tiles: (time) => [backendTile('cloud-temp', time)],
    tileSize: 256,
    maxzoom: 18,
    maxNativeZoom: 7,
    nativeResolutionKm: 2.0,
    resolutionLabel: '2 km',
    temporalResolution: '10 minutes',
    timeDependent: true,
    attribution: 'AURORA-GIS synthetic Himawari-class feed',
  },
]

export const REAL_IMAGERY: SatelliteProduct[] = [
  {
    id: 'sentinel2-cloudless',
    name: 'Sentinel-2 Cloudless',
    satellite: 'Copernicus Sentinel-2',
    color: '#06b6d4',
    tiles: () => ['https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2024_3857/default/g/{z}/{y}/{x}.jpg'],
    tileSize: 256,
    maxzoom: 14,
    maxNativeZoom: 13,
    nativeResolutionKm: 0.01,
    resolutionLabel: '~10 m',
    temporalResolution: 'annual mosaic',
    timeDependent: false,
    attribution: 'EOX IT Services / Copernicus Sentinel data',
  },
  {
    id: 'esri-world',
    name: 'Esri World Imagery',
    satellite: 'Esri/Maxar composite',
    color: '#eab308',
    // Proxied through AURORA-GIS: placeholder tiles ("Map data not yet
    // available.") are detected and dropped, revealing the S2 underlay.
    tiles: () => ['/tiles/esri/{z}/{x}/{y}.jpg'],
    tileSize: 256,
    maxzoom: 19,
    maxNativeZoom: 18,
    nativeResolutionKm: 0.001,
    resolutionLabel: '~1 m',
    temporalResolution: 'static mosaic',
    timeDependent: false,
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
]

export const ALL_PRODUCTS = [...SATELLITE_PRODUCTS, ...REAL_IMAGERY]

export function getProduct(id: string): SatelliteProduct | undefined {
  return ALL_PRODUCTS.find((p) => p.id === id)
}

export interface BaseMapDef {
  id: string
  name: string
  tiles: string[]
  maxzoom: number
  attribution: string
}

export const BASEMAPS: Record<string, BaseMapDef> = {
  satellite: {
    id: 'satellite',
    name: 'Satellite',
    tiles: ['/tiles/esri/{z}/{x}/{y}.jpg'],
    maxzoom: 19,
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
  street: {
    id: 'street',
    name: 'Street',
    tiles: ['https://a.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}@2x.png'],
    maxzoom: 19,
    attribution: 'OpenStreetMap contributors, CARTO',
  },
  terrain: {
    id: 'terrain',
    name: 'Terrain',
    tiles: ['https://tile.opentopomap.org/{z}/{x}/{y}.png'],
    maxzoom: 17,
    attribution: 'OpenTopoMap (CC-BY-SA), OpenStreetMap contributors',
  },
  dark: {
    id: 'dark',
    name: 'Dark GIS',
    tiles: ['https://a.basemaps.cartocdn.com/dark_all/{z}/{x}/{y}@2x.png'],
    maxzoom: 19,
    attribution: 'OpenStreetMap contributors, CARTO',
  },
  light: {
    id: 'light',
    name: 'Light GIS',
    tiles: ['https://a.basemaps.cartocdn.com/light_all/{z}/{x}/{y}@2x.png'],
    maxzoom: 19,
    attribution: 'OpenStreetMap contributors, CARTO',
  },
}

export const DEFAULT_CENTER: [number, number] = [120.5936, 16.5]
export const DEFAULT_ZOOM = 7.2

// Official PAGASA PAR boundary (pagasa.dost.gov.ph, learning-tools):
// imaginary lines connecting 5°N 115°E, 15°N 115°E, 21°N 120°E,
// 25°N 120°E, 25°N 135°E and 5°N 135°E.
export const PAR_FEATURES: GeoJSON.FeatureCollection = {
  type: 'FeatureCollection',
  features: [
    {
      type: 'Feature',
      properties: { kind: 'boundary', name: 'Philippine Area of Responsibility' },
      geometry: {
        type: 'Polygon',
        coordinates: [[
          [115, 5], [115, 15], [120, 21], [120, 25],
          [135, 25], [135, 5], [115, 5],
        ]],
      },
    },
    {
      type: 'Feature',
      properties: { kind: 'label', name: 'PAR' },
      geometry: { type: 'Point', coordinates: [129.5, 22.5] },
    },
  ],
}

export function metersPerPixel(zoom: number, lat: number): number {
  return (156543.03392 * Math.cos((lat * Math.PI) / 180)) / Math.pow(2, zoom)
}
