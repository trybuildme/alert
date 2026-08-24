// Earthquake Monitor panel — operational dashboard for detected events.
//
// HONESTY: everything shown comes from real ingested data. The LIVE/STALE
// badge reflects actual provider health from /api/earthquakes/health,
// never mere frontend connectivity. These are DETECTED EVENTS — no
// forecasts or predictions.

import { useCallback, useEffect, useState } from 'react'
import { useMapStore, useUIStore } from '../../stores'

interface EqProps {
  uid: string
  magnitude: number | null
  magnitude_type?: string | null
  depth_km: number | null
  origin_time: string
  place: string | null
  region?: string | null
  provider: string
  source_url?: string | null
  distance_km?: number
  /** Viewport helpers appended client-side from feature geometry */
  _lon?: number
  _lat?: number
}

interface Stats {
  last_hour?: number
  today?: number
  strongest_24h?: { magnitude: number | null; place: string | null; origin_time: string } | null
  deepest_24h?: { depth_km: number | null; place: string | null } | null
  nearest_reference?: { uid: string; magnitude: number | null; place: string | null; distance_km: number } | null
  reference_region_last_24h?: number
  magnitude_histogram_7d?: { bin_low: number; count: number }[]
  total_stored?: number
  disclaimer?: string
}

interface Health {
  overall?: 'live' | 'stale'
  providers_configured?: string[]
  stream_clients?: number
  phivolcs_note?: string
}

const SEV_COLOR: Record<string, string> = {
  INFO: '#38bdf8', LOW: '#00e400', MODERATE: '#ffe400',
  HIGH: '#ff9800', CRITICAL: '#ff2020',
}

function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString([], {
    hour: '2-digit', minute: '2-digit', second: '2-digit',
  })
}

function magLabel(mag: number | null): string {
  return mag != null ? `M ${mag.toFixed(1)}` : 'M ?'
}

export default function EarthquakePanel() {
  const open = useUIStore((s) => s.eqPanelOpen)
  const toggle = useUIStore((s) => s.toggleEqPanel)
  const layerPanelOpen = useUIStore((s) => s.layerPanelOpen)
  const eqMinMag = useUIStore((s) => s.eqMinMag)
  const setEqMinMag = useUIStore((s) => s.setEqMinMag)
  const eqSelectedUid = useUIStore((s) => s.eqSelectedUid)
  const setEqSelectedUid = useUIStore((s) => s.setEqSelectedUid)
  const map = useMapStore((s) => s.map)

  // Select + fly the map to the event location
  const focusEvent = (e: EqProps) => {
    setEqSelectedUid(e.uid === eqSelectedUid ? null : e.uid)
    if (e._lon != null && e._lat != null && map) {
      map.flyTo({ center: [e._lon, e._lat], zoom: 9, speed: 1.5, essential: true })
    }
  }

  const [stats, setStats] = useState<Stats | null>(null)
  const [health, setHealth] = useState<Health | null>(null)
  const [events, setEvents] = useState<EqProps[]>([])
  const [lastAlert, setLastAlert] = useState<{ severity: string; summary: string } | null>(null)

  const refresh = useCallback(async () => {
    try {
      const [st, h, ev, al] = await Promise.all([
        fetch('/api/earthquakes/statistics').then((r) => r.ok ? r.json() : null),
        fetch('/api/earthquakes/health').then((r) => r.ok ? r.json() : null),
        fetch(`/api/earthquakes/recent?hours=24&min_magnitude=${eqMinMag}`)
          .then((r) => r.ok ? r.json() : null),
        fetch('/api/earthquakes/alerts?limit=5').then((r) => r.ok ? r.json() : null),
      ])
      if (st) setStats(st)
      if (h) setHealth(h)
      if (ev?.features) {
        setEvents(ev.features.map((f: {
          properties: EqProps
          geometry: { coordinates: [number, number] }
        }) => ({
          ...f.properties,
          _lon: f.geometry.coordinates[0],
          _lat: f.geometry.coordinates[1],
        })))
      }
      if (al?.alerts?.length) setLastAlert(al.alerts[al.alerts.length - 1])
    } catch { /* backend unreachable: keep previous values */ }
  }, [eqMinMag])

  useEffect(() => {
    if (!open) return
    refresh()
    const t = setInterval(refresh, 60_000)
    return () => clearInterval(t)
  }, [open, refresh])

  // Live alert ticker while the panel is open
  useEffect(() => {
    if (!open) return
    const es = new EventSource('/api/earthquakes/stream')
    es.addEventListener('hazard.alert', (ev) => {
      try {
        const msg = JSON.parse((ev as MessageEvent).data)
        setLastAlert({ severity: msg.severity, summary: msg.summary })
        refresh()
      } catch { /* ignore malformed */ }
    })
    return () => { es.close() }
  }, [open, refresh])

  if (!open) return null

  const histMax = Math.max(1, ...(stats?.magnitude_histogram_7d ?? []).map((b) => b.count))
  const selected = events.find((e) => e.uid === eqSelectedUid)

  return (
    <div className={`forecast-panel ${layerPanelOpen ? '' : 'docked-left'}`}>
      <div className="panel-head">
        EARTHQUAKE MONITOR
        <button className="close-btn" onClick={toggle} title="Close">✕</button>
      </div>

      <div className="fc-sub" style={{ padding: '6px 12px 0' }}>
        <span className={`eq-badge ${health?.overall === 'live' ? 'eq-live' : 'eq-stale'}`}>
          ● {health?.overall === 'live' ? 'LIVE' : 'STALE'}
        </span>
        {' '}· providers: {(health?.providers_configured ?? []).join(', ') || '—'}
        {' '}· stream clients: {health?.stream_clients ?? 0}
      </div>
      <p className="fc-note" style={{ marginTop: 4 }}>
        Detected events only. This system does not forecast or predict earthquakes.
      </p>

      {lastAlert && (
        <div className="eq-alert" style={{ borderLeftColor: SEV_COLOR[lastAlert.severity] ?? '#888' }}>
          <b>{lastAlert.severity}</b> · {lastAlert.summary}
        </div>
      )}

      <div className="eq-stats">
        <div><span>Last hour</span><b>{stats?.last_hour ?? '—'}</b></div>
        <div><span>24 hours</span><b>{stats?.today ?? '—'}</b></div>
        <div><span>Aurora region 24h</span><b>{stats?.reference_region_last_24h ?? '—'}</b></div>
        <div><span>Strongest 24h</span><b title={stats?.strongest_24h?.place ?? ''}>
          {magLabel(stats?.strongest_24h?.magnitude ?? null)}</b></div>
        <div><span>Deepest 24h</span><b>{stats?.deepest_24h?.depth_km != null ? `${Math.round(stats.deepest_24h.depth_km)} km` : '—'}</b></div>
        <div><span>Stored events</span><b>{stats?.total_stored ?? '—'}</b></div>
      </div>

      {stats?.nearest_reference && (
        <div className="fc-sub" style={{ padding: '4px 12px' }}>
          Nearest to Aurora (7d): {magLabel(stats.nearest_reference.magnitude)} at{' '}
          {stats.nearest_reference.distance_km} km
        </div>
      )}

      <div className="eq-hist">
        {(stats?.magnitude_histogram_7d ?? [])
          .filter((b) => b.bin_low >= 2 && b.count > 0)
          .map((b) => (
            <div key={b.bin_low} className="eq-hist-row" title={`M ${b.bin_low}–${b.bin_low + 0.5}: ${b.count}`}>
              <span className="eq-hist-label">{b.bin_low.toFixed(1)}</span>
              <span className="eq-hist-bar">
                <i style={{ width: `${(b.count / histMax) * 100}%` }} />
              </span>
              <span className="eq-hist-count">{b.count}</span>
            </div>
          ))}
        <div className="tm-note">Magnitude distribution · last 7 days</div>
      </div>

      <div className="eq-filter">
        <label htmlFor="eq-minmag">Min magnitude filter</label>
        <input
          id="eq-minmag" type="range" min="1" max="7" step="0.5"
          value={eqMinMag}
          onChange={(e) => setEqMinMag(parseFloat(e.target.value))}
        />
        <b>M {eqMinMag.toFixed(1)}</b>
      </div>

      <div className="eq-list">
        {events.length === 0 && (
          <div className="inspect-loading">No events in the last 24 h at this filter.</div>
        )}
        {events.slice(0, 40).map((e) => (
          <button
            key={e.uid}
            className={`eq-item ${eqSelectedUid === e.uid ? 'selected' : ''}`}
            onClick={() => focusEvent(e)}
          >
            <span className={`eq-mag ${e.magnitude != null && e.magnitude >= 5 ? 'strong' : ''}`}>
              {magLabel(e.magnitude)}
            </span>
            <span className="eq-place" title={e.place ?? ''}>{e.place ?? 'location unknown'}</span>
            <span className="eq-meta">
              {fmtTime(e.origin_time)} · {e.depth_km != null ? `${Math.round(e.depth_km)} km` : '?'} deep
              {e.distance_km != null ? ` · ${e.distance_km} km away` : ''}
            </span>
          </button>
        ))}
      </div>

      {selected && (
        <div className="eq-detail">
          <div className="panel-head" style={{ background: 'transparent' }}>
            EVENT DETAIL<button className="close-btn" onClick={() => setEqSelectedUid(null)}>✕</button>
          </div>
          <div className="kv-grid">
            <div><span>Magnitude</span><b>{magLabel(selected.magnitude)} ({selected.magnitude_type ?? '?'})</b></div>
            <div><span>Depth</span><b>{selected.depth_km != null ? `${selected.depth_km} km` : '—'}</b></div>
            <div><span>Origin time</span><b>{new Date(selected.origin_time).toLocaleString()}</b></div>
            <div><span>Location</span><b title={selected.place ?? ''}>{selected.place ?? '—'}</b></div>
            <div><span>Region</span><b>{selected.region ?? '—'}</b></div>
            <div><span>Provider</span><b>{selected.provider}</b></div>
            <div><span>Event ID</span><b style={{ wordBreak: 'break-all' }}>{selected.uid}</b></div>
          </div>
          {selected.source_url && (
            <a className="eq-link" href={selected.source_url} target="_blank" rel="noreferrer">
              Provider Source ↗
            </a>
          )}
          <div className="fc-note">
            Intensity estimates are not fabricated: felt intensity depends on
            site conditions and requires official ShakeMap products.
          </div>
        </div>
      )}
    </div>
  )
}
