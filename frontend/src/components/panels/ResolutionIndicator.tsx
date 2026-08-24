import { useMapStore, useSatelliteStore } from '../../stores'
import { getProduct, metersPerPixel } from '../../config/mapConfig'

export default function ResolutionIndicator() {
  const zoom = useMapStore((s) => s.zoom)
  const center = useMapStore((s) => s.center)
  const activeProduct = useSatelliteStore((s) => s.activeProduct)
  const product = getProduct(activeProduct)

  if (!product) return null

  const beyondNative = zoom > product.maxNativeZoom
  const effectiveZoom = Math.min(zoom, product.maxNativeZoom)
  const groundResM = metersPerPixel(effectiveZoom, center[1])
  const mapScaleM = metersPerPixel(zoom, center[1])

  const scaleLabel =
    mapScaleM >= 1000 ? `${(mapScaleM / 1000).toFixed(1)} km/px`
    : mapScaleM >= 1 ? `${mapScaleM.toFixed(0)} m/px`
    : `${(mapScaleM * 100).toFixed(1)} cm/px`

  return (
    <div className={`resolution-indicator ${beyondNative ? 'warn' : ''}`}>
      <div className="res-row"><span>Satellite native resolution</span><b>{product.resolutionLabel}</b></div>
      <div className="res-row"><span>Current map scale</span><b>{scaleLabel}</b></div>
      <div className="res-row"><span>Current zoom</span><b>z{zoom.toFixed(1)}</b></div>
      {beyondNative && (
        <div className="res-warning">Viewing beyond native satellite resolution — imagery is over-zoomed, not new data.</div>
      )}
    </div>
  )
}
