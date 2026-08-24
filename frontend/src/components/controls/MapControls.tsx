import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapStore, useUIStore } from '../../stores'

export default function MapControls() {
  const map = useMapStore((s) => s.map)
  const bearing = useMapStore((s) => s.bearing)
  const gpsAccuracyM = useUIStore((s) => s.gpsAccuracyM)
  const gpsError = useUIStore((s) => s.gpsError)
  const [cursor, setCursor] = useState<[number, number] | null>(null)

  useEffect(() => {
    if (!map) return
    const onMove = (e: maplibregl.MapMouseEvent) => {
      setCursor([e.lngLat.lat, e.lngLat.lng])
    }
    const onOut = () => setCursor(null)
    map.on('mousemove', onMove)
    map.getCanvas().addEventListener('mouseleave', onOut)
    return () => {
      map.off('mousemove', onMove)
      map.getCanvas().removeEventListener('mouseleave', onOut)
    }
  }, [map])

  const showGps = gpsAccuracyM !== null || gpsError !== null
  const gpsColor = gpsError !== null || (gpsAccuracyM ?? 0) > 1000 ? '#f59e0b' : '#4ade80'
  const gpsTitle = gpsError ??
    (gpsAccuracyM !== null && gpsAccuracyM > 1000
      ? 'Coarse fix — browser IP-based estimate, not a GPS receiver'
      : 'Browser-reported position accuracy')
  const gpsLabel = gpsError !== null
    ? `GPS: ${gpsError}`
    : gpsAccuracyM !== null
      ? `GPS ±${gpsAccuracyM >= 1000 ? `${(gpsAccuracyM / 1000).toFixed(1)} km` : `${Math.round(gpsAccuracyM)} m`}`
      : ''

  return (
    <>
      <button
        className="north-indicator"
        style={{ transform: `rotate(${-bearing}deg)` }}
        onClick={() => map?.easeTo({ bearing: 0, duration: 400 })}
        title="Reset north"
        aria-label="Reset north"
      >
        <svg width="34" height="34" viewBox="0 0 34 34">
          <polygon points="17,3 22,20 17,16 12,20" fill="#ef4444" />
          <polygon points="17,31 12,14 17,18 22,14" fill="#e2e8f0" />
          <text x="17" y="12" textAnchor="middle" fontSize="7" fill="#fff" fontWeight="bold">N</text>
        </svg>
      </button>

      <div className="status-bar">
        <span className="status-item">
          {cursor
            ? `${cursor[0].toFixed(5)}°, ${cursor[1].toFixed(5)}°`
            : 'move cursor over map'}
        </span>
        <span className="status-sep">|</span>
        <span className="status-item">EPSG:3857 · WGS84 readout</span>
        {showGps && (
          <>
            <span className="status-sep">|</span>
            <span className="status-item" style={{ color: gpsColor }} title={gpsTitle}>
              {gpsLabel}
            </span>
          </>
        )}
      </div>
    </>
  )
}
