// Click/dblclick interaction routing for the ALERT map.
//
// Click priority: active draw tool > earthquake selection > farm inspect
// > drawn-feature selection > generic inspect. Dblclick finishes open
// line/polygon sketches.

import type maplibregl from 'maplibre-gl'
import { useDrawingStore, useInspectStore, useUIStore } from '../stores'

export function attachInteractions(map: maplibregl.Map): void {
  const openInspect = (lat: number, lon: number) =>
    useInspectStore.getState().openInspect(lat, lon)

  map.on('click', (e) => {
    const drawState = useDrawingStore.getState()
    if (drawState.activeTool) {
      handleDrawClick(map, e.lngLat.lng, e.lngLat.lat)
      return
    }

    const eqHits = map.queryRenderedFeatures(e.point, { layers: ['eq-circle'] })
    if (eqHits.length > 0) {
      const uid = eqHits[0].properties?.uid as string | undefined
      if (uid) {
        map.setFilter('eq-selected', ['==', ['get', 'uid'], uid])
        useUIStore.getState().setEqSelectedUid(uid)
        if (!useUIStore.getState().eqPanelOpen) {
          useUIStore.getState().toggleEqPanel()
        }
      }
      return
    }

    const volcanoHits = map.queryRenderedFeatures(e.point, { layers: ['volcano-circle'] })
    if (volcanoHits.length > 0) {
      const uid = volcanoHits[0].properties?.uid as string | undefined
      if (uid) {
        useUIStore.getState().setVolcanoUid(uid)
        // Bring the edifice fully on screen for the imagery thumbnail.
        map.flyTo({ center: e.lngLat, zoom: Math.max(map.getZoom(), 11), speed: 1.2, essential: true })
      }
      return
    }

    const floodHits = map.queryRenderedFeatures(e.point, {
      layers: ['flood-rain-circle', 'flood-water-circle', 'flood-alert-marker'],
    })
    if (floodHits.length > 0) {
      const uid = floodHits[0].properties?.uid as string | undefined
      if (uid) {
        useUIStore.getState().setFloodStationId(uid)
        map.flyTo({ center: e.lngLat, zoom: Math.max(map.getZoom(), 10), speed: 1.2, essential: true })
      }
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
}

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
