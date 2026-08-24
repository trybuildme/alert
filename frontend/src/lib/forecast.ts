// Shared client model for /api/cyclones/forecast + GeoJSON conversion
// used by both the map overlay source and the outlook panel.

export interface ForecastDay {
  valid_utc: string
  date: string      // PHT calendar date, YYYY-MM-DD
  day: string       // Monday ... Sunday (PHT)
  lat: number
  lon: number
  wind_kt: number | null
  wind_kmh: number | null
  status: string | null
  code?: string | null         // PAGASA classification code (TD/TS/STS/TY/ST)
  signal_no: number | null  // PAGASA TCWS 0..5 implied by day-max winds
  sshs_category: number | null
}

export interface ForecastStorm {
  sid: string
  name: string
  pagasa_name?: string | null
  basin?: string
  n_obs?: number
  last_fix?: string
  age_hours?: number
  stale?: boolean
  current?: {
    lat: number
    lon: number
    wind_kt: number | null
    wind_kmh: number | null
    status: string | null
    signal_no: number | null
    wind_radius_nm?: number | null   // max USA_R34 quadrant (JTWC)
    wind_radius_km?: number | null
  }
  motion?: {
    bearing_deg: number
    bearing_compass: string
    speed_kmh: number
  }
  intensity_trend_kt_per_day?: number
  daily: ForecastDay[]
}

export interface ForecastResponse {
  source: string
  generated_at: string
  horizon_days: number
  methodology: string
  storms: ForecastStorm[]
}

const EARTH_R_KM = 6371.0088

function haversineKm(a: [number, number], b: [number, number]): number {
  const dLat = ((b[1] - a[1]) * Math.PI) / 180
  const dLon = ((b[0] - a[0]) * Math.PI) / 180
  const la1 = (a[1] * Math.PI) / 180
  const la2 = (b[1] * Math.PI) / 180
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(la1) * Math.cos(la2) * Math.sin(dLon / 2) ** 2
  return 2 * EARTH_R_KM * Math.asin(Math.sqrt(h))
}

function lerpPt(a: [number, number], b: [number, number], t: number): [number, number] {
  return [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t]
}

/**
 * Dashes baked into geometry: densify the polyline at ~stepKm and emit a
 * MultiLineString of alternating dash/gap runs. Unlike line-dasharray this
 * renders identically in mercator AND globe projection on every MapLibre
 * build — the reported "missing dashes" failure mode becomes impossible.
 */
export function dashedMultiLine(
  coords: [number, number][],
  dashKm = 70,
  gapKm = 50,
  stepKm = 24,
): GeoJSON.MultiLineString {
  // Densify along great-circle-ish linear interpolation in lon/lat
  const samples: [number, number][] = []
  for (let i = 0; i < coords.length - 1; i++) {
    const seg = coords[i + 1] === coords[i] ? stepKm : haversineKm(coords[i], coords[i + 1])
    const n = Math.max(1, Math.round(seg / stepKm))
    for (let k = 0; k < n; k++) samples.push(lerpPt(coords[i], coords[i + 1], k / n))
  }
  if (coords.length > 0) samples.push(coords[coords.length - 1])

  // Chunk consecutive sample pairs into dashes by cumulative distance
  const lines: [number, number][][] = []
  let current: [number, number][] | null = null
  let acc = 0
  for (let i = 0; i < samples.length - 1; i++) {
    const a = samples[i]
    const b = samples[i + 1]
    const phase = acc % (dashKm + gapKm)
    const on = phase < dashKm
    if (on) {
      if (!current) current = [a]
      current.push(b)
    } else if (current) {
      lines.push(current)
      current = null
    }
    acc += haversineKm(a, b)
  }
  if (current) lines.push(current)
  return { type: 'MultiLineString', coordinates: lines }
}

export function forecastToFC(storms: ForecastStorm[]): GeoJSON.FeatureCollection {
  const features: GeoJSON.Feature[] = []
  for (const st of storms) {
    const trackCoords: [number, number][] = []
    if (st.current) trackCoords.push([st.current.lon, st.current.lat])
    for (const d of st.daily) trackCoords.push([d.lon, d.lat])
    if (trackCoords.length >= 2) {
      features.push({
        type: 'Feature',
        properties: { kind: 'track', sid: st.sid, name: st.name },
        geometry: dashedMultiLine(trackCoords),
      })
    }
    for (const d of st.daily) {
      features.push({
        type: 'Feature',
        properties: {
          kind: 'point',
          sid: st.sid,
          name: st.name,
          day: d.day,
          date: d.date,
          label: `${d.day.slice(0, 3).toUpperCase()} ${d.date.slice(5)} · SIG ${d.signal_no ?? '—'}`,
          status: d.status,
          code: d.code ?? null,
          signal_no: d.signal_no,
          wind_kt: d.wind_kt,
          wind_kmh: d.wind_kmh,
          sshs_category: d.sshs_category,
        },
        geometry: { type: 'Point', coordinates: [d.lon, d.lat] },
      })
    }
  }
  return { type: 'FeatureCollection', features }
}

export async function fetchForecast(): Promise<ForecastResponse | null> {
  try {
    const res = await fetch('/api/cyclones/forecast')
    if (!res.ok) return null
    return (await res.json()) as ForecastResponse
  } catch {
    return null
  }
}
