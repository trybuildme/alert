// Elevation cross-section for a drawn LINE.
//
// The line's vertices are resampled into <= 80 evenly-spaced points
// (by path distance), fetched from /api/elevation/profile (real
// Copernicus DEM GLO-90 via Open-Meteo — NOT the simulated terrain
// basemap), and rendered as an SVG profile with derived stats:
// total length, min/max elevation, cumulative gain/loss, straight-line
// A→B distance and initial bearing.

import { useEffect, useMemo, useState } from 'react'
import { useDrawingStore, type DrawnFeature } from '../../stores'

const MAX_SAMPLES = 80

interface ProfileData {
  elevations_m: number[]
  source: string
  resolution_m: number
  disclaimer: string
}

/** Resample polyline into n evenly spaced (by path distance) points. */
export function resampleLine(coords: [number, number][], n: number): [number, number][] {
  if (coords.length < 2 || n < 2) return coords
  const R = 6371.0088
  const hav = (a: number[], b: number[]) => {
    const dLat = ((b[1] - a[1]) * Math.PI) / 180
    const dLon = ((b[0] - a[0]) * Math.PI) / 180
    const la1 = (a[1] * Math.PI) / 180
    const la2 = (b[1] * Math.PI) / 180
    const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
    return 2 * R * Math.asin(Math.sqrt(h))
  }
  // cumulative distances in km
  const cum = [0]
  for (let i = 1; i < coords.length; i++) {
    cum.push(cum[i - 1] + hav(coords[i - 1], coords[i]))
  }
  const total = cum[cum.length - 1]
  if (total === 0) return [coords[0], coords[coords.length - 1]]
  const out: [number, number][] = []
  let seg = 1
  for (let k = 0; k < n; k++) {
    const target = (k / (n - 1)) * total
    while (seg < coords.length - 1 && cum[seg] < target) seg++
    const segLen = cum[seg] - cum[seg - 1] || 1e-12
    const t = Math.min(1, Math.max(0, (target - cum[seg - 1]) / segLen))
    out.push([
      coords[seg - 1][0] + t * (coords[seg][0] - coords[seg - 1][0]),
      coords[seg - 1][1] + t * (coords[seg][1] - coords[seg - 1][1]),
    ])
  }
  return out
}

function haversineKm(a: [number, number], b: [number, number]): number {
  const R = 6371.0088
  const dLat = ((b[1] - a[1]) * Math.PI) / 180
  const dLon = ((b[0] - a[0]) * Math.PI) / 180
  const la1 = (a[1] * Math.PI) / 180
  const la2 = (b[1] * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(h))
}

export function initialBearing(a: [number, number], b: [number, number]): string {
  const φ1 = (a[1] * Math.PI) / 180
  const φ2 = (b[1] * Math.PI) / 180
  const Δλ = ((b[0] - a[0]) * Math.PI) / 180
  const y = Math.sin(Δλ) * Math.cos(φ2)
  const x = Math.cos(φ1) * Math.sin(φ2) - Math.sin(φ1) * Math.cos(φ2) * Math.cos(Δλ)
  const deg = ((Math.atan2(y, x) * 180) / Math.PI + 360) % 360
  const dirs = ['N', 'NE', 'E', 'SE', 'S', 'SW', 'W', 'NW']
  return `${deg.toFixed(0)}° ${dirs[Math.round(deg / 45) % 8]}`
}

function PathStats({ feature, elevations }: {
  feature: DrawnFeature
  elevations: number[] | null
}) {
  const coords = feature.coordinates as [number, number][]
  const a = coords[0]
  const b = coords[coords.length - 1]
  const straightKm = haversineKm(a, b)
  const rows: [string, string][] = [
    ['Length (path)', `${feature.lengthKm?.toFixed(2)} km`],
    ['Straight A to B', `${straightKm.toFixed(2)} km`],
    ['Bearing A to B', initialBearing(a, b)],
  ]
  if (elevations && elevations.length >= 2) {
    const gain = elevations.slice(1).reduce(
      (acc, e, i) => acc + Math.max(0, e - elevations[i]), 0)
    const loss = elevations.slice(1).reduce(
      (acc, e, i) => acc + Math.max(0, elevations[i] - e), 0)
    rows.push(
      ['Elevation A / B',
       `${elevations[0].toFixed(0)} m / ${elevations[elevations.length - 1].toFixed(0)} m`],
      ['Min / Max',
       `${Math.min(...elevations).toFixed(0)} / ${Math.max(...elevations).toFixed(0)} m`],
      ['Gain / Loss', `+${gain.toFixed(0)} / -${loss.toFixed(0)} m`],
    )
  }
  return (
    <>
      {rows.map(([k, v]) => (
        <div key={k} className="kv"><span>{k}</span><b>{v}</b></div>
      ))}
    </>
  )
}

export default function ElevationProfile({
  feature,
  width = 300,
  height = 110,
  showHeader = true,
}: {
  feature: DrawnFeature
  width?: number
  height?: number
  /** false when rendered inside a wrapper that provides its own header */
  showHeader?: boolean
}) {
  const coords = useMemo(
    () => resampleLine(feature.coordinates as [number, number][], MAX_SAMPLES),
    [feature.id, feature.coordinates],
  )
  const [data, setData] = useState<ProfileData | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setError(false)
    ;(async () => {
      try {
        const q = coords.map(([lon, lat]) => `${lat.toFixed(5)},${lon.toFixed(5)}`).join('|')
        const res = await fetch(`/api/elevation/profile?coords=${encodeURIComponent(q)}`)
        if (!res.ok) throw new Error(String(res.status))
        const body: ProfileData = await res.json()
        // Validate shape: a malformed response (proxy hiccup, stale
        // backend, intercepted mock) must degrade to the error note —
        // rendering undefined elevations crashed the whole app once.
        if (!body || !Array.isArray(body.elevations_m) ||
            body.elevations_m.length < 2 ||
            body.elevations_m.some((e) => typeof e !== 'number')) {
          throw new Error('malformed elevation payload')
        }
        if (!cancelled) setData(body)
      } catch {
        if (!cancelled) setError(true)
      }
    })()
    return () => { cancelled = true }
  }, [coords])

  if (!data) {
    return (
      <div className="elev-profile" data-testid="elevation-profile">
        {showHeader && <div className="section-title">Elevation profile</div>}
        {/* Path stats are available immediately, before DEM arrives. */}
        <PathStats feature={feature} elevations={null} />
        {error
          ? <div className="fc-note">DEM source unavailable — no profile.</div>
          : <div className="fc-note">Sampling terrain along line…</div>}
      </div>
    )
  }

  const W = width
  const H = height
  const PAD = 6
  const els = data.elevations_m
  const minEl = Math.min(...els)
  const maxEl = Math.max(...els)
  const span = Math.max(maxEl - minEl, 20)   // avoid flatline at zero height
  const step = (W - 2 * PAD) / (els.length - 1)
  const pts = els.map((e, i) =>
    `${(PAD + i * step).toFixed(1)},${(H - PAD - ((e - minEl) / span) * (H - 2 * PAD)).toFixed(1)}`)
  const linePath = `M${pts.join(' L')}`
  const areaPath = `${linePath} L${W - PAD},${H - PAD} L${PAD},${H - PAD} Z`

  return (
    <div className="elev-profile" data-testid="elevation-profile">
      {showHeader && (
        <div className="section-title">Elevation profile</div>
      )}
      <PathStats feature={feature} elevations={els} />
      <svg width={W} height={H} role="img" aria-label="Elevation cross-section">
        <defs>
          <linearGradient id="elevFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#38bdf8" stopOpacity="0.35" />
            <stop offset="100%" stopColor="#38bdf8" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        <path d={areaPath} fill="url(#elevFill)" />
        <path d={linePath} fill="none" stroke="#38bdf8" strokeWidth="1.5" />
        {/* A / B markers */}
        <circle cx={PAD} cy={H - PAD - ((els[0] - minEl) / span) * (H - 2 * PAD)}
                r={3} fill="#22c55e" />
        <text x={PAD + 5}
              y={H - PAD - ((els[0] - minEl) / span) * (H - 2 * PAD) + 3}
              fill="#22c55e" fontSize={9}>A</text>
        <circle cx={W - PAD} cy={H - PAD - ((els[els.length - 1] - minEl) / span) * (H - 2 * PAD)}
                r={3} fill="#f97316" />
        <text x={W - PAD - 14}
              y={H - PAD - ((els[els.length - 1] - minEl) / span) * (H - 2 * PAD) + 3}
              fill="#f97316" fontSize={9}>B</text>
        <text x={PAD} y={H - 1} fill="#64748b" fontSize={7}>A · start</text>
        <text x={W - PAD} y={H - 1} textAnchor="end" fill="#64748b" fontSize={7}>
          {`${feature.lengthKm?.toFixed(2)} km · B`}
        </text>
      </svg>
      <p className="fc-note" style={{ margin: '2px 0 0', fontSize: 9 }}>
        Copernicus DEM ~{data.resolution_m} m via Open-Meteo — real elevation,
        fine detail below that scale will not resolve.
      </p>
    </div>
  )
}
