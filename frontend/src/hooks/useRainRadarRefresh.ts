import { useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import { useLayerStore } from '../stores'

const REFRESH_MS = 10 * 60 * 1000  // RainViewer updates ~every 10 min
const RAINVIEWER_META = 'https://api.rainviewer.com/public/weather-maps.json'
const TILE_BASE = 'https://tilecache.rainviewer.com'
const COLOR_SCHEME = 2   // classic
const SMOOTH = 1
const SNOW = 1

function groupVisible(map: maplibregl.Map, id: string): boolean {
  return useLayerStore.getState().layers.find((l) => l.id === id)?.visible ?? false
}

export function useRainRadarRefresh(map: maplibregl.Map | null) {
  useEffect(() => {
    if (!map) return

    let timer: ReturnType<typeof setInterval> | undefined

    const refresh = async () => {
      if (!groupVisible(map, 'rain-radar')) return
      try {
        const res = await fetch(RAINVIEWER_META)
        if (!res.ok) return
        const data = await res.json()
        const past: Array<{ path: string }> = data?.radar?.past ?? []
        if (!past.length) return
        const latest = past[past.length - 1]
        const tileUrl = `${TILE_BASE}${latest.path}/256/{z}/{x}/{y}/${COLOR_SCHEME}_${SMOOTH}_${SNOW}.png`
        const src = map.getSource('rain-radar') as maplibregl.RasterTileSource | undefined
        if (src) src.setTiles([tileUrl])
      } catch { /* honest empty; next cycle retries */ }
    }

    // Initial fetch when toggled on
    const unsub = useLayerStore.subscribe(() => { void refresh() })
    refresh()

    timer = setInterval(refresh, REFRESH_MS)
    return () => { unsub(); clearInterval(timer) }
  }, [map])
}
