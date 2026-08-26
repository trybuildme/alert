// Elevation profile popup — the rectangle card that appears over the
// map as soon as a line (A → B) is drawn or selected in Draw & Measure.
// Wraps the shared ElevationProfile chart + stats at popup size.

import { useDrawingStore } from '../../stores'
import ElevationProfile from './ElevationProfile'

export default function ProfilePopup() {
  const features = useDrawingStore((s) => s.features)
  const selectedId = useDrawingStore((s) => s.selectedId)
  const selectFeature = useDrawingStore((s) => s.selectFeature)
  const selected = features.find((f) => f.id === selectedId)

  if (!selected || selected.tool !== 'line') return null

  return (
    <aside className="profile-popup" data-testid="profile-popup">
      <div className="panel-head">
        <span>ELEVATION PROFILE · A → B</span>
        <button
          className="close-btn"
          onClick={() => selectFeature(null)}
          title="Close profile"
        >✕</button>
      </div>
      <div className="profile-popup-body">
        <ElevationProfile feature={selected} width={352} height={130} showHeader={false} />
      </div>
    </aside>
  )
}
