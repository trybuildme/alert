import { useRef } from 'react'
import { useMap } from './hooks/useMap'
import { useLayerVisibility } from './hooks/useLayerVisibility'
import { useDrawing } from './hooks/useDrawing'
import { useCyclonePulse } from './hooks/useCyclonePulse'
import { useCycloneRefresh } from './hooks/useCycloneRefresh'
import TopBar from './components/controls/TopBar'
import TimeMachine from './components/controls/TimeMachine'
import MapControls from './components/controls/MapControls'
import LayerPanel from './components/layers/LayerPanel'
import InspectPanel from './components/panels/InspectPanel'
import CycloneForecastPanel from './components/panels/CycloneForecastPanel'
import ResolutionIndicator from './components/panels/ResolutionIndicator'
import MapTimestamp from './components/panels/MapTimestamp'
import MeasurementPanel from './components/panels/MeasurementPanel'

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null)
  const { ready, map } = useMap(containerRef)
  useLayerVisibility(ready ? map : null)
  useCyclonePulse(ready ? map : null)
  useCycloneRefresh(ready ? map : null)
  useDrawing(ready ? map : null)

  return (
    <div className="app">
      <TopBar />
      <div className="map-wrap">
        <div ref={containerRef} className="map-container" />
        <LayerPanel />
        <CycloneForecastPanel />
        <InspectPanel />
        <MeasurementPanel />
        <ResolutionIndicator />
        <MapTimestamp />
        <MapControls />
        <TimeMachine />
        {!ready && <div className="map-boot">Initializing AURORA-GIS …</div>}
      </div>
    </div>
  )
}
