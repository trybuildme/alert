import { useEffect, useState } from 'react'
import { useUIStore } from '../../stores'
import {
  fetchForecast, type ForecastResponse, type ForecastStorm,
} from '../../lib/forecast'

const SIGNAL_CLASS = ['sig-0', 'sig-1', 'sig-2', 'sig-3', 'sig-4', 'sig-5']

function StatusCell({ status }: { status: string | null }) {
  if (!status) return <td className="fc-status muted">—</td>
  return (
    <td className={`fc-status ${status === 'Super Typhoon' ? 'status-sty' : ''}`}>
      {status === 'Super Typhoon' ? 'SUPER TYPHOON' : status}
    </td>
  )
}

function SignalCell({ no }: { no: number | null }) {
  if (no == null || no === 0) return <td><span className="sig-badge sig-0">—</span></td>
  return <td><span className={`sig-badge ${SIGNAL_CLASS[no]}`}>#{no}</span></td>
}

function StormCard({ storm }: { storm: ForecastStorm }) {
  const cur = storm.current
  return (
    <div className="fc-storm">
      <div className="fc-head">
        <span className="fc-name">
          {storm.pagasa_name ? `${storm.pagasa_name} (${storm.name})` : storm.name}
        </span>
        {cur?.status && (
          <span className={`fc-now ${cur.status === 'Super Typhoon' ? 'status-sty' : ''}`}>
            NOW: {cur.status.toUpperCase()}
            {cur.signal_no ? ` · SIG #${cur.signal_no}` : ''}
            {cur.wind_radius_km ? ` · R34 ${Math.round(cur.wind_radius_km)} km` : ''}
          </span>
        )}
      </div>
      <div className="fc-sub">
        {storm.motion && (
          <>Moving {storm.motion.bearing_compass} at {storm.motion.speed_kmh} km/h · </>
        )}
        {storm.intensity_trend_kt_per_day != null && (
          <>
            trend {storm.intensity_trend_kt_per_day > 0 ? '+' : ''}
            {storm.intensity_trend_kt_per_day} kt/day
          </>
        )}
        {storm.stale && <span className="fc-stale"> · stale fix ({Math.round(storm.age_hours ?? 0)} h)</span>}
      </div>
      <table className="fc-table">
        <thead>
          <tr>
            <th>DAY</th><th>DATE</th><th>STATUS</th><th>SIGNAL</th><th>WIND</th>
          </tr>
        </thead>
        <tbody>
          {storm.daily.map((d) => (
            <tr key={d.date}>
              <td className="fc-day">{d.day}</td>
              <td className="fc-date">{d.date.slice(5)}</td>
              <StatusCell status={d.status} />
              <SignalCell no={d.signal_no} />
              <td className="fc-wind">{d.wind_kmh != null ? `${d.wind_kmh} km/h` : '—'}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default function CycloneForecastPanel() {
  const open = useUIStore((s) => s.forecastPanelOpen)
  const toggle = useUIStore((s) => s.toggleForecastPanel)
  const layerPanelOpen = useUIStore((s) => s.layerPanelOpen)
  const meta = useUIStore((s) => s.forecastMeta)
  const [data, setData] = useState<ForecastResponse | null>(null)

  useEffect(() => {
    if (!open || data) return
    let cancelled = false
    ;(async () => {
      const body = await fetchForecast()
      if (!cancelled) setData(body)
    })()
    return () => { cancelled = true }
  }, [open, data])

  if (!open) return null

  const storms = data?.storms ?? []
  return (
    <div className={`forecast-panel ${layerPanelOpen ? '' : 'docked-left'}`}>
      <div className="panel-head">
        CYCLONE OUTLOOK · NEXT 7 DAYS
        <button className="close-btn" onClick={toggle} title="Close">✕</button>
      </div>
      {!data && <div className="inspect-loading">Loading outlook …</div>}
      {data && data.source !== 'unavailable' && storms.length === 0 && (
        <div className="inspect-loading">No active tropical cyclones.</div>
      )}
      {data && data.source === 'unavailable' && (
        <div className="inspect-loading">Upstream NOAA feed unreachable — no outlook available.</div>
      )}
      {storms.map((st) => <StormCard key={st.sid} storm={st} />)}
      <div className="fc-note">
        Extrapolation of IBTrACS best-track motion with damped intensity
        trend — not an official PAGASA/JTWC forecast. Signal numbers show
        the peak PAGASA wind signal implied by forecast sustained winds;
        actual signals depend on landfall. Consult PAGASA bulletins.
      </div>
    </div>
  )
}
