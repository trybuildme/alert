import { useEffect } from 'react'
import { useInspectStore, useSatelliteStore, useMapStore } from '../../stores'

export default function InspectPanel() {
  const { open, loading, lat, lon, data, closeInspect, setData } = useInspectStore()
  const activeProduct = useSatelliteStore((s) => s.activeProduct)
  const currentTime = useSatelliteStore((s) => s.currentTime)
  const map = useMapStore((s) => s.map)

  useEffect(() => {
    if (!open || lat == null || lon == null) return
    let cancelled = false
    ;(async () => {
      try {
        const params = new URLSearchParams({ lat: String(lat), lon: String(lon), product: activeProduct })
        if (currentTime) params.set('time', currentTime)
        const res = await fetch(`/api/inspect?${params}`)
        const body = await res.json()
        if (!cancelled) setData(body)
      } catch {
        if (!cancelled) setData(null)
      }
    })()
    return () => {
      cancelled = true
    }
  }, [open, lat, lon, activeProduct, currentTime, setData])

  if (!open) return null

  return (
    <aside className="inspect-panel">
      <div className="panel-head">
        <span>LOCATION INSPECTOR</span>
        <button className="close-btn" onClick={closeInspect}>✕</button>
      </div>

      <div className="inspect-section">
        <div className="section-title">Location</div>
        <div className="kv"><span>Latitude</span><b>{lat?.toFixed(6)}</b></div>
        <div className="kv"><span>Longitude</span><b>{lon?.toFixed(6)}</b></div>
        <button
          className="mini-btn"
          onClick={() => map?.flyTo({ center: [lon!, lat!], zoom: Math.max(map.getZoom(), 13), essential: true })}
        >
          Zoom to location
        </button>
      </div>

      {loading && <div className="inspect-loading">Querying satellite archive…</div>}

      {data && (
        <>
          {data.administrative_context.length > 0 && (
            <div className="inspect-section">
              <div className="section-title">Administrative context</div>
              {data.administrative_context.map((c) => (
                <div key={c.name} className="kv"><span>{c.level}</span><b>{c.name}</b></div>
              ))}
            </div>
          )}

          <div className="inspect-section">
            <div className="section-title">Satellite observation</div>
            <div className="kv"><span>Satellite</span><b>{String(data.satellite.satellite)}</b></div>
            <div className="kv"><span>Product</span><b>{String(data.satellite.product)}</b></div>
            <div className="kv"><span>Resolution</span><b>{String(data.satellite.resolution_label)}</b></div>
            {data.satellite.latest_observation != null && (
              <div className="kv"><span>Latest observation</span><b>{String(data.satellite.latest_observation)}</b></div>
            )}
            {data.satellite.data_age_minutes != null && (
              <div className="kv"><span>Data age</span><b>{String(data.satellite.data_age_minutes)} min</b></div>
            )}
            <div className="kv small"><span>Source</span><b>{String(data.satellite.data_source)}</b></div>
          </div>

          <div className="inspect-section">
            <div className="section-title">Agricultural analysis</div>
            <div className="kv"><span>NDVI estimate</span><b>{String(data.agriculture.ndvi_estimate)}</b></div>
            <div className="kv"><span>30-day trend</span><b>{Number(data.agriculture.ndvi_30d_trend) >= 0 ? '+' : ''}{String(data.agriculture.ndvi_30d_trend)}</b></div>
            <div className="kv"><span>Soil moisture idx</span><b>{String(data.agriculture.soil_moisture_index)}</b></div>
            <div className="note">{String(data.agriculture.interpretation)}</div>
          </div>

          <div className="inspect-section">
            <div className="section-title">Weather</div>
            <div className="kv"><span>Rainfall (3 h)</span><b>{String(data.weather.rainfall_3h_mm)} mm</b></div>
            <div className="kv"><span>Temperature</span><b>{String(data.weather.temperature_c)} °C</b></div>
            <div className="kv"><span>Humidity</span><b>{String(data.weather.humidity_pct)} %</b></div>
            <div className="kv"><span>Wind</span><b>{String(data.weather.wind_kph)} km/h</b></div>
            <div className="kv small"><span>Nearest station</span><b>{String(data.weather.nearest_station)} ({String(data.weather.station_distance_km)} km)</b></div>
          </div>

          {data.flood_risk && (
            <div className={`inspect-section flood ${String(data.flood_risk.risk_level)}`}>
              <div className="section-title">Flood risk: {String(data.flood_risk.risk_level).toUpperCase()}</div>
              <div className="note">{String(data.flood_risk.description)}</div>
            </div>
          )}

          {data.farms_nearby.length > 0 && (
            <div className="inspect-section">
              <div className="section-title">Monitored farms nearby</div>
              {data.farms_nearby.map((f) => (
                <div key={String(f.name)} className="kv">
                  <span>{String(f.crop)}</span><b>{String(f.name)} · {String(f.area_hectares)} ha</b>
                </div>
              ))}
            </div>
          )}
        </>
      )}
    </aside>
  )
}
