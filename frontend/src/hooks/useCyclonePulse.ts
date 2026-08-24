import { useEffect } from 'react'
import maplibregl from 'maplibre-gl'
import { useLayerStore } from '../stores'

// Light circling pulse around each observed cyclone position.
// Two circle layers run half a period out of phase so a ring is always
// expanding; per-frame paint updates scale ring size with storm category
// and fade to zero. Runs only while the cyclone group is visible.

const PERIOD_MS = 2800
const PULSE_LAYERS = ['cyclone-pulse-a', 'cyclone-pulse-b'] as const

export function useCyclonePulse(map: maplibregl.Map | null) {
  useEffect(() => {
    if (!map) return
    let raf = 0
    let running = false

    const state = () => {
      const l = useLayerStore.getState().layers.find((x) => x.id === 'cyclones')
      return { visible: l?.visible ?? false, opacity: l?.opacity ?? 1 }
    }

    const frame = (t: number) => {
      const { opacity } = state()
      if (map.isStyleLoaded()) {
        const phase = (t % PERIOD_MS) / PERIOD_MS
        PULSE_LAYERS.forEach((id, i) => {
          if (!map.getLayer(id)) return
          const ph = (phase + i * 0.5) % 1
          const r = 7 + ph * 20
          const radiusExpr = [
            'interpolate', ['linear'], ['coalesce', ['get', 'sshs_category'], -1],
            -1, r * 0.6, 0, r * 0.85, 3, r * 1.15, 5, r * 1.45,
          ] as unknown as maplibregl.ExpressionSpecification
          try {
            map.setPaintProperty(id, 'circle-radius', radiusExpr)
            map.setPaintProperty(id, 'circle-opacity', 0.28 * opacity * (1 - ph))
          } catch { /* style torn down mid-frame */ }
        })
      }
      if (running) raf = requestAnimationFrame(frame)
    }

    const sync = () => {
      const { visible } = state()
      if (visible && !running) {
        running = true
        raf = requestAnimationFrame(frame)
      } else if (!visible && running) {
        running = false
        cancelAnimationFrame(raf)
        for (const id of PULSE_LAYERS) {
          if (map.getLayer(id)) {
            try { map.setPaintProperty(id, 'circle-opacity', 0) } catch { /* gone */ }
          }
        }
      }
    }

    sync()
    const unsub = useLayerStore.subscribe(sync)
    return () => {
      unsub()
      running = false
      cancelAnimationFrame(raf)
    }
  }, [map])
}
