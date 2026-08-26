// Volcano detail popup — opens when a volcano marker is clicked.
//
// Content: registry facts (elevation, last known eruption, curated
// active_now snapshot), nearby seismicity from the live earthquake
// store (7 days / 30 km), and a latest-satellite-picture thumbnail
// composed from the cached Esri World Imagery tiles the backend
// already proxies (/tiles/esri/{z}/{x}/{y}.jpg).

import { useEffect, useState } from 'react'
import { useUIStore } from '../../stores'

interface VolcanoDetail {
  properties: {
    uid: string
    name: string
    elevation_m: number
    active_now: boolean
    note: string
    last_known_eruption?: string
  }
  geometry: { coordinates: [number, number] }   // [lon, lat]
  active_status_as_of?: string
  disclaimer?: string
  seismicity?: {
    available: boolean
    total_7d?: number
    count_24h?: number
    strongest?: {
      magnitude: number | null
      place: string | null
      origin_time: string
      depth_km: number | null
    } | null
  }
}

const THUMB_ZOOM = 13          // ~4.9 km across a 2x2 tile mosaic
const BOX_W = 300
const BOX_H = 200

function mercatorPixels(lat: number, lon: number, z: number) {
  const n = 2 ** z
  const xf = ((lon + 180) / 360) * n
  const latR = (lat * Math.PI) / 180
  const yf = ((1 - Math.log(Math.tan(latR) + 1 / Math.cos(latR)) / Math.PI) / 2) * n
  return { xf, yf }
}

export default function VolcanoPopup() {
  const volcanoUid = useUIStore((s) => s.volcanoUid)
  const setVolcanoUid = useUIStore((s) => s.setVolcanoUid)
  const map = null // fly-to handled in interactions; kept for symmetry
  void map
  const [detail, setDetail] = useState<VolcanoDetail | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!volcanoUid) {
      setDetail(null)
      setError(false)
      return
    }
    let cancelled = false
    setDetail(null)
    setError(false)
    ;(async () => {
      try {
        const res = await fetch(`/api/volcanoes/${encodeURIComponent(volcanoUid)}`)
        if (!res.ok) throw new Error(String(res.status))
        const body: VolcanoDetail = await res.json()
        if (!cancelled) setDetail(body)
      } catch {
        if (!cancelled) setError(true)
      }
    })()
    return () => { cancelled = true }
  }, [volcanoUid])

  // Esc closes, like the other panels.
  useEffect(() => {
    if (!volcanoUid) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setVolcanoUid(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [volcanoUid, setVolcanoUid])

  if (!volcanoUid) return null

  return (
    <aside className="volcano-popup" data-testid="volcano-popup">
      <div className="panel-head">
        VOLCANO
        <button className="close-btn" onClick={() => setVolcanoUid(null)} title="Close">✕</button>
      </div>

      {!detail && !error && <div className="inspect-loading">Querying volcano registry…</div>}
      {error && <div className="inspect-loading">Registry unavailable.</div>}

      {detail && (
        <>
          <SatelliteThumb lat={detail.geometry.coordinates[1]}
                          lon={detail.geometry.coordinates[0]} />
          <div className="vc-head">
            <span className={`eq-badge ${detail.properties.active_now ? 'eq-live' : 'vc-quiet'}`}>
              ● {detail.properties.active_now ? 'ACTIVE NOW' : 'MONITORED'}
            </span>
            <span className="vc-name">{detail.properties.name}</span>
          </div>

          <div className="inspect-section">
            <div className="section-title">Registry</div>
            <div className="kv"><span>Elevation</span><b>{detail.properties.elevation_m} m</b></div>
            <div className="kv"><span>Last known eruption</span>
              <b>{detail.properties.last_known_eruption ?? 'no record'}</b></div>
            <div className="kv"><span>Location</span>
              <b>{detail.geometry.coordinates[1].toFixed(3)}, {detail.geometry.coordinates[0].toFixed(3)}</b></div>
            <p className="fc-note" style={{ margin: '4px 0 0' }}>{detail.properties.note}</p>
          </div>

          <div className="inspect-section">
            <div className="section-title">Nearby seismicity · 30 km / 7 d</div>
            {detail.seismicity?.available ? (
              <>
                <div className="kv"><span>Last 24 hours</span><b>{detail.seismicity.count_24h ?? 0} events</b></div>
                <div className="kv"><span>Last 7 days</span><b>{detail.seismicity.total_7d ?? 0} events</b></div>
                {detail.seismicity.strongest && (
                  <div className="kv"><span>Strongest</span>
                    <b>M{Number(detail.seismicity.strongest.magnitude).toFixed(1)}</b></div>
                )}
                {detail.seismicity.strongest?.place && (
                  <p className="fc-note" style={{ margin: '4px 0 0' }}>
                    {detail.seismicity.strongest.place}
                  </p>
                )}
              </>
            ) : (
              <div className="fc-note">Earthquake module offline — no seismic context.</div>
            )}
          </div>

          <p className="fc-note vc-disclaimer">
            Status snapshot as of {detail.active_status_as_of ?? 'n/a'} — not a live
            alert level. Current warnings via official PHIVOLCS channels.
          </p>
        </>
      )}
    </aside>
  )
}

/** 2x2 Esri World Imagery mosaic centered on the volcano. */
function SatelliteThumb({ lat, lon }: { lat: number; lon: number }) {
  const { xf, yf } = mercatorPixels(lat, lon, THUMB_ZOOM)
  let bx = Math.floor(xf)
  let by = Math.floor(yf)
  let px = (xf - bx) * 256
  let py = (yf - by) * 256
  // Shift the mosaic window so the summit sits inside the visible box.
  while (px < BOX_W / 2) { bx -= 1; px += 256 }
  while (px > 512 - BOX_W / 2) { bx += 1; px -= 256 }
  while (py < BOX_H / 2) { by -= 1; py += 256 }
  while (py > 512 - BOX_H / 2) { by += 1; py -= 256 }

  const tiles: string[] = []
  for (let dy = 0; dy < 2; dy++)
    for (let dx = 0; dx < 2; dx++)
      tiles.push(`/tiles/esri/${THUMB_ZOOM}/${bx + dx}/${by + dy}.jpg`)

  return (
    <div className="vc-thumb" style={{ width: BOX_W, height: BOX_H }}
         title={`Esri World Imagery · z${THUMB_ZOOM}`}>
      <div style={{
        position: 'absolute',
        left: -(px - BOX_W / 2),
        top: -(py - BOX_H / 2),
        width: 512,
        height: 512,
      }}>
        {tiles.map((src, i) => (
          <img key={i} src={src} alt="" width={256} height={256}
               style={{ position: 'absolute', left: (i % 2) * 256, top: i < 2 ? 0 : 256 }} />
        ))}
      </div>
      <span className="vc-thumb-label">latest satellite</span>
    </div>
  )
}
