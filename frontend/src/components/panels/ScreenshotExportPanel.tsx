import { useState } from 'react'
import { useDrawingStore, useMapStore, useUIStore } from '../../stores'
import { useScreenshotExport, type ScreenshotOptions } from '../../hooks/useScreenshotExport'

export default function ScreenshotExportPanel() {
  const { features, selectedId } = useDrawingStore()
  const map = useMapStore((s) => s.map)
  const panelOpen = useUIStore((s) => s.screenshotPanelOpen)
  const togglePanel = useUIStore((s) => s.toggleScreenshotPanel)
  const { exportScreenshot } = useScreenshotExport()

  const selected = features.find((f) => f.id === selectedId)
  const canExport = selected && selected.tool !== 'point' && selected.tool !== 'line'

  const [format, setFormat] = useState<'jpg' | 'png'>('jpg')
  const [quality, setQuality] = useState(0.85)
  const [scale, setScale] = useState<1 | 2 | 4>(2)

  if (!panelOpen || !canExport || !map) return null

  return (
    <div className="screenshot-panel">
      <div className="panel-title">EXPORT SCREENSHOT</div>
      <div className="screenshot-row">
        <span>Format</span>
        <div className="screenshot-toggle">
          <button className={format === 'jpg' ? 'active' : ''} onClick={() => setFormat('jpg')}>JPG</button>
          <button className={format === 'png' ? 'active' : ''} onClick={() => setFormat('png')}>PNG</button>
        </div>
      </div>
      {format === 'jpg' && (
        <div className="screenshot-row">
          <span>Quality</span>
          <div className="screenshot-slider">
            <input
              type="range"
              min={0.5}
              max={1}
              step={0.05}
              value={quality}
              onChange={(e) => setQuality(parseFloat(e.target.value))}
            />
            <span>{Math.round(quality * 100)}%</span>
          </div>
        </div>
      )}
      <div className="screenshot-row">
        <span>Scale</span>
        <div className="screenshot-toggle">
          {[1, 2, 4].map((s) => (
            <button key={s} className={scale === s ? 'active' : ''} onClick={() => setScale(s as 1 | 2 | 4)}>{s}x</button>
          ))}
        </div>
      </div>
      <div className="screenshot-meta">
        Bbox: [{selected.center[1].toFixed(3)}, {selected.center[0].toFixed(3)}] · Zoom {map.getZoom().toFixed(1)}
      </div>
      <button
        className="screenshot-export-btn"
        onClick={() => {
          const opts: ScreenshotOptions = { format, quality, scale }
          exportScreenshot(selected, opts)
          togglePanel()
        }}
      >
        Export {format.toUpperCase()}
      </button>
    </div>
  )
}
