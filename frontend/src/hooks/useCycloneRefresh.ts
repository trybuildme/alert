import { useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import { useLayerStore } from '../stores'
import { fetchForecast, forecastToFC } from '../lib/forecast'

// The cyclone overlays load once at page load; if that initial fetch hit a
// restarting backend (or upstream outage) the source stayed empty forever
// and the forecast dashes never appeared. This hook makes them self-heal:
//   - refetch when either cyclone group is toggled on with an empty source
//   - refresh the forecast every REFRESH_MS while visible so stale best-track
//     fixes converge toward the live feed without a manual page reload.

const REFRESH_MS = 5 * 60 * 1000
const MIN_REFETCH_GAP_MS = 30 * 1000

let lastFcstFetch = 0

async function fillSource(map: maplibregl.Map, sourceId: string,
                          data: GeoJSON.FeatureCollection): Promise<void> {
  const src = map.getSource(sourceId) as maplibregl.GeoJSONSource | undefined
  if (!src || !data.features.length) return
  try {
    src.setData(data)
  } catch { /* style not ready; next cycle retries */ }
}

async function sourceFeatureCount(map: maplibregl.Map, sourceId: string): Promise<number> {
  const src = map.getSource(sourceId) as (maplibregl.GeoJSONSource &
    { getData?: () => Promise<GeoJSON.FeatureCollection> }) | undefined
  if (!src?.getData) return Number.POSITIVE_INFINITY // can't inspect -> assume fine
  try {
    const fc = (await src.getData()) as GeoJSON.FeatureCollection
    return fc.features?.length ?? 0
  } catch {
    return 0
  }
}

export function useCycloneRefresh(map: maplibregl.Map | null) {
  useEffect(() => {
    if (!map) return

    const groupVisible = (id: string) =>
      useLayerStore.getState().layers.find((l) => l.id === id)?.visible ?? false

    const refreshForecast = async (force = false) => {
      const now = Date.now()
      if (!force && now - lastFcstFetch < MIN_REFETCH_GAP_MS) return
      lastFcstFetch = now
      const body = await fetchForecast()
      if (body?.storms?.length) await fillSource(map, 'cyclones-fcst', forecastToFC(body.storms))
    }

    const sync = async () => {
      if (!groupVisible('cyclone-forecast')) return
      const count = await sourceFeatureCount(map, 'cyclones-fcst')
      if (count === 0) await refreshForecast(true)
    }

    // Keep the Himawari cloud canopy current: swap tile URLs with a
    // time-bucketed cache-buster so the browser refetches the latest
    // GIBS frame every cycle (backend ignores the extra param).
    const refreshClouds = () => {
      if (!groupVisible('cyclone-clouds')) return
      const src = map.getSource('cyclone-clouds') as maplibregl.RasterTileSource | undefined
      if (!src) return
      try {
        const bust = Math.floor(Date.now() / REFRESH_MS)
        src.setTiles([`/tiles/himawari-clean-ir/{z}/{x}/{y}.png?frame=${bust}`])
      } catch { /* older runtimes recreate via setProductTiles paths */ }
    }

    sync()
    const unsub = useLayerStore.subscribe(() => { void sync() })
    const timer = setInterval(() => {
      if (groupVisible('cyclone-forecast') || groupVisible('cyclones')) {
        void refreshForecast(true)
      }
      refreshClouds()
    }, REFRESH_MS)

    return () => {
      unsub()
      clearInterval(timer)
    }
  }, [map])
}
