// Flood station popup — opens when a rain/water-level/alert marker is
// clicked. Shows current measurement, trend context, quality, source
// and data status with NOAH's honesty contract baked in.

import { useEffect, useState } from 'react'
import { useI18n } from '../../i18n'
import { useUIStore } from '../../stores'

interface FloodStationDetail {
  station: {
    id: string
    name: string
    kind: string
    latitude: number
    longitude: number
    river_basin: string | null
    provider: string
  }
  series: Record<string, { observed_at: string; value: number; quality: string; source: string }[]>
  generated_at?: string
}

const LEVEL_COLORS: Record<string, string> = {
  NORMAL: '#38bdf8', ADVISORY: '#facc15', WATCH: '#fb923c',
  WARNING: '#ef4444', CRITICAL: '#a855f7',
}

function metricLabel(metric: string): string {
  if (metric === 'rainfall_mm_h') return 'Rainfall (1 h)'
  if (metric === 'rainfall_mm_3h') return 'Rainfall (3 h)'
  if (metric === 'rainfall_mm_24h') return 'Rainfall (24 h)'
  if (metric === 'water_level_m') return 'Water level'
  return metric
}

export default function FloodStationPopup() {
  const stationId = useUIStore((s) => s.floodStationId)
  const setStationId = useUIStore((s) => s.setFloodStationId)
  const { t } = useI18n()
  const [detail, setDetail] = useState<FloodStationDetail | null>(null)
  const [error, setError] = useState(false)

  useEffect(() => {
    if (!stationId) {
      setDetail(null)
      setError(false)
      return
    }
    let cancelled = false
    setDetail(null)
    setError(false)
    ;(async () => {
      try {
        const res = await fetch(
          `/api/flood/observations/${encodeURIComponent(stationId)}`)
        if (!res.ok) throw new Error(String(res.status))
        if (!cancelled) setDetail(await res.json())
      } catch {
        if (!cancelled) setError(true)
      }
    })()
    return () => { cancelled = true }
  }, [stationId])

  useEffect(() => {
    if (!stationId) return
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setStationId(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [stationId, setStationId])

  if (!stationId) return null

  return (
    <aside className="profile-popup" data-testid="flood-popup">
      <div className="panel-head">
        FLOOD STATION
        <button className="close-btn" onClick={() => setStationId(null)}
                title="Close">✕</button>
      </div>

      {!detail && !error && (
        <div className="fc-note" style={{ padding: '8px 14px' }}>
          Querying station records…
        </div>
      )}
      {error && (
        <div className="fc-note" style={{ padding: '8px 14px' }}>
          Station records unavailable.
        </div>
      )}

      {detail && (
        <>
          <div className="vc-head">
            <span className="eq-badge eq-live">
              ● {detail.station.kind === 'rainfall' ? 'RAIN GAUGE' : 'RIVER GAUGE'}
            </span>
            <span className="vc-name">{detail.station.name}</span>
          </div>

          <div className="inspect-section">
            <div className="section-title">Current readings</div>
            {Object.keys(detail.series).length === 0 && (
              <div className="fc-note">
                No observations yet.
                {detail.station.provider === 'none' &&
                  ' This gauge awaits an authorized PAGASA/DENR feed — no values are fabricated.'}
              </div>
            )}
            {Object.entries(detail.series).map(([metric, series]) => {
              const latestRow = series[series.length - 1]
              const prev = series.length > 1 ? series[series.length - 2] : null
              const delta = prev ? latestRow.value - prev.value : null
              const unit = metric.startsWith('water') ? 'm'
                : metric === 'rainfall_mm_h' ? 'mm/h' : `mm / ${metric.slice(-2)}`
              return (
                <div key={metric} className="kv">
                  <span>{metricLabel(metric)}</span>
                  <b>
                    {latestRow.value.toFixed(latestRow.value < 10 ? 2 : 0)}{' '}
                    {unit}
                    {delta != null && delta !== 0 && (
                      <span style={{ color: delta > 0 ? '#ef4444' : '#22c55e' }}>
                        {' '}({delta > 0 ? '↑' : '↓'} {Math.abs(delta).toFixed(1)})
                      </span>
                    )}
                  </b>
                </div>
              )
            })}
            {Object.entries(detail.series).length > 0 && (() => {
              const anySeries = Object.values(detail.series)[0]
              const latestRow = anySeries[anySeries.length - 1]
              return (
                <>
                  <div className="kv"><span>Timestamp</span><b>{latestRow.observed_at}</b></div>
                  <div className="kv"><span>Data source</span><b>{latestRow.source}</b></div>
                  <div className="kv"><span>Quality</span><b>{latestRow.quality}</b></div>
                  <p className="fc-note" style={{ margin: '4px 0 0' }}>
                    Rainfall is real model data via Open-Meteo · risk levels are
                    NOAH's classification of OBSERVED data — official warnings
                    via PAGASA.
                  </p>
                </>
              )
            })()}
          </div>

          <p className="fc-note vc-disclaimer">
            {t('volcano.basis') && ''}Basin: {detail.station.river_basin ?? '—'} ·
            {' '}provider: {detail.station.provider} · generated {detail.generated_at}
          </p>
        </>
      )}
    </aside>
  )
}
