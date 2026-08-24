import { useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import { useDrawingStore, polygonAreaKm2, pathLengthKm } from '../stores'
import type { DrawnFeature } from '../stores'

function featureToGeoJSON(features: DrawnFeature[]): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: features.map((f) => ({
      type: 'Feature',
      id: f.id,
      properties: { __fid: f.id, tool: f.tool },
      geometry:
        f.tool === 'point'
          ? { type: 'Point', coordinates: f.coordinates[0] }
          : { type: 'Polygon', coordinates: [f.coordinates as number[][]] },
    })),
  }
}

export function useDrawing(map: maplibregl.Map | null) {
  const { features, sketchCoords, activeTool, selectedId } = useDrawingStore()

  useEffect(() => {
    if (!map || !map.isStyleLoaded()) return

    const polygons = features.filter((f) => f.tool !== 'point' && f.tool !== 'line')
    const lines = features.filter((f) => f.tool === 'line')
    const points = features.filter((f) => f.tool === 'point')

    const fillSrc = map.getSource('draw-fill') as maplibregl.GeoJSONSource | undefined
    const lineSrc = map.getSource('draw-line') as maplibregl.GeoJSONSource | undefined
    const pointSrc = map.getSource('draw-point') as maplibregl.GeoJSONSource | undefined
    const sketchSrc = map.getSource('draw-sketch') as maplibregl.GeoJSONSource | undefined
    if (!fillSrc || !lineSrc || !pointSrc || !sketchSrc) return

    fillSrc.setData(featureToGeoJSON(polygons))
    lineSrc.setData({
      type: 'FeatureCollection',
      features: lines.map((f) => ({
        type: 'Feature', id: f.id, properties: { __fid: f.id },
        geometry: { type: 'LineString', coordinates: f.coordinates },
      })),
    })
    pointSrc.setData(featureToGeoJSON(points))

    // Sketch preview while drawing
    if (activeTool && sketchCoords.length > 0) {
      sketchSrc.setData({
        type: 'FeatureCollection',
        features: [
          ...(sketchCoords.length >= 2 && activeTool !== 'rectangle' && activeTool !== 'circle'
            ? [{
                type: 'Feature' as const, properties: {},
                geometry: { type: 'LineString' as const, coordinates: sketchCoords },
              }]
            : []),
          ...sketchCoords.map((c) => ({
            type: 'Feature' as const, properties: {},
            geometry: { type: 'Point' as const, coordinates: c },
          })),
        ],
      })
    } else {
      sketchSrc.setData({ type: 'FeatureCollection', features: [] })
    }

    // Selected highlight via feature-state
    if (map.getLayer('draw-fill')) {
      polygons.forEach((f) => {
        try { map.setFeatureState({ source: 'draw-fill', id: f.id }, { selected: f.id === selectedId }) } catch { /* noop */ }
      })
    }
  }, [features, sketchCoords, activeTool, selectedId, map])
}

export function measurementFor(feature: DrawnFeature | undefined): string[] {
  if (!feature) return []
  const rows: string[] = []
  if (feature.tool === 'point') {
    rows.push(`Lat: ${feature.center[1].toFixed(6)}`)
    rows.push(`Lon: ${feature.center[0].toFixed(6)}`)
  }
  if (feature.lengthKm != null) rows.push(`Length: ${feature.lengthKm.toFixed(3)} km`)
  if (feature.perimeterKm != null) rows.push(`Perimeter: ${feature.perimeterKm.toFixed(3)} km`)
  if (feature.radiusKm != null) rows.push(`Radius: ${feature.radiusKm.toFixed(3)} km`)
  if (feature.areaKm2 != null) {
    rows.push(`Area: ${feature.areaKm2.toFixed(4)} km² (${(feature.areaKm2 * 100).toFixed(1)} ha)`)
  }
  return rows
}

export { polygonAreaKm2, pathLengthKm }
