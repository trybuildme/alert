import { useEffect, useState } from 'react'
import { useDrawingStore, useInspectStore, useMapStore } from '../../stores'
import type { DrawTool, InspectData } from '../../stores'
import { measurementFor } from '../../hooks/useDrawing'
import ElevationProfile from './ElevationProfile'

const TOOLS: { id: Exclude<DrawTool, null>; label: string; icon: string; hint: string }[] = [
  { id: 'point', label: 'Point', icon: '●', hint: 'Click to drop a point' },
  { id: 'line', label: 'Line', icon: '／', hint: 'Click vertices · double-click to finish' },
  { id: 'polygon', label: 'Polygon', icon: '⬠', hint: 'Click vertices · double-click to close' },
  { id: 'rectangle', label: 'Rectangle', icon: '▭', hint: 'Click two opposite corners' },
  { id: 'circle', label: 'Circle', icon: '◯', hint: 'Click center, then edge for radius' },
]

export default function MeasurementPanel() {
  const map = useMapStore((s) => s.map)
  const openInspect = useInspectStore((s) => s.openInspect)
  const { activeTool, setTool, features, selectedId, cancelSketch, clearAll, finishSketch } = useDrawingStore()
  const selected = features.find((f) => f.id === selectedId)
  const [analysis, setAnalysis] = useState<InspectData | null>(null)

  useEffect(() => {
    if (!selected || selected.tool === 'point') {
      setAnalysis(null)
      return
    }
    let cancelled = false
    ;(async () => {
      try {
        const res = await fetch(`/api/inspect?lat=${selected.center[1]}&lon=${selected.center[0]}`)
        const body = await res.json()
        if (!cancelled) setAnalysis(body)
      } catch {
        if (!cancelled) setAnalysis(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [selected])

  const cursorClass =
    activeTool === 'point' ? 'crosshair' :
    activeTool === 'line' || activeTool === 'polygon' ? 'crosshair' :
    activeTool === 'rectangle' ? 'crosshair' :
    activeTool === 'circle' ? 'crosshair' : ''

  useEffect(() => {
    if (!map) return
    map.getCanvas().style.cursor = cursorClass ? 'crosshair' : ''
  }, [map, cursorClass])

  return (
    <div className="measure-panel">
      <div className="panel-title">DRAW & MEASURE</div>
      <div className="tool-row">
        {TOOLS.map((t) => (
          <button
            key={t.id}
            className={`tool-btn ${activeTool === t.id ? 'active' : ''}`}
            title={t.hint}
            onClick={() => setTool(activeTool === t.id ? null : t.id)}
          >
            <span className="tool-icon">{t.icon}</span>
            <span>{t.label}</span>
          </button>
        ))}
      </div>

      {(activeTool === 'polygon' || activeTool === 'line') && (
        <div className="sketch-actions">
          <button onClick={() => finishSketch()}>Finish</button>
          <button onClick={cancelSketch}>Cancel</button>
        </div>
      )}

      {features.length > 0 && (
        <div className="drawn-list">
          {features.map((f) => (
            <button
              key={f.id}
              className={`drawn-item ${f.id === selectedId ? 'selected' : ''}`}
              onClick={() => useDrawingStore.getState().selectFeature(f.id === selectedId ? null : f.id)}
            >
              <span>{f.tool.toUpperCase()} #{f.id}</span>
              <span className="drawn-sub">
                {f.areaKm2 != null && `${f.areaKm2.toFixed(2)} km²`}
                {f.lengthKm != null && `${f.lengthKm.toFixed(2)} km`}
                {f.radiusKm != null && `r=${f.radiusKm.toFixed(2)} km`}
                {f.tool === 'point' && `${f.center[1].toFixed(4)}, ${f.center[0].toFixed(4)}`}
              </span>
            </button>
          ))}
          <button className="clear-btn" onClick={clearAll}>Clear all drawings</button>
        </div>
      )}

      {selected && (
        <div className="measurement-detail">
          <div className="section-title">Measurements</div>
          {selected.tool === 'line' && <ElevationProfile feature={selected} />}
          {selected.tool !== 'line' &&
            measurementFor(selected).map((row) => (
              <div key={row} className="kv"><span>·</span><b>{row}</b></div>
            ))}
          {selected.tool !== 'point' && analysis && (
            <>
              <div className="section-title">Area analysis</div>
              <div className="kv"><span>NDVI</span><b>{String(analysis.agriculture?.ndvi_estimate ?? '—')}</b></div>
              <div className="kv"><span>Rainfall 3 h</span><b>{String(analysis.weather?.rainfall_3h_mm ?? '—')} mm</b></div>
              <div className="kv"><span>Flood risk</span><b>{analysis.flood_risk ? String(analysis.flood_risk.risk_level) : 'low'}</b></div>
              <button
                className="mini-btn"
                onClick={() => {
                  map?.flyTo({ center: [selected.center[0], selected.center[1]], zoom: 14, essential: true })
                  openInspect(selected.center[1], selected.center[0])
                }}
              >
                Inspect center
              </button>
            </>
          )}
        </div>
      )}
    </div>
  )
}
