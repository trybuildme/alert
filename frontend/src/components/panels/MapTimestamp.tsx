import { useSatelliteStore } from '../../stores'
import { getProduct } from '../../config/mapConfig'

function formatTimestamp(iso: string | null): { date: string; time: string } | null {
  if (!iso || iso.length < 16) return null
  return { date: iso.slice(0, 10), time: `${iso.slice(11, 16)} UTC` }
}

export default function MapTimestamp() {
  const activeProduct = useSatelliteStore((s) => s.activeProduct)
  const currentTime = useSatelliteStore((s) => s.currentTime)
  const playing = useSatelliteStore((s) => s.playing)

  const product = getProduct(activeProduct)
  if (!product?.timeDependent) return null

  const ts = formatTimestamp(currentTime)
  if (!ts) return null

  return (
    <div className="map-timestamp" aria-live="off">
      <span className="mt-product">{product.name}</span>
      <span className="mt-date">{ts.date}</span>
      <span className="mt-clock">{ts.time}</span>
      {playing && <span className="mt-live">PLAYING</span>}
    </div>
  )
}
