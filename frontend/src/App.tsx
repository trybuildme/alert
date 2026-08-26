import { lazy, Suspense, useRef } from 'react'
import { useI18n } from './i18n'
import { useMap } from './hooks/useMap'
import { useLayerVisibility } from './hooks/useLayerVisibility'
import { useDrawing } from './hooks/useDrawing'
import { useCyclonePulse } from './hooks/useCyclonePulse'
import { useCycloneRefresh } from './hooks/useCycloneRefresh'
import { useEarthquakes } from './hooks/useEarthquakes'
import { useReplay } from './hooks/useReplay'
import { useNotificationFeeds } from './hooks/useNotificationFeeds'
import TopBar from './components/controls/TopBar'
import TimeMachine from './components/controls/TimeMachine'
import MapControls from './components/controls/MapControls'
import ReplayControls from './components/controls/ReplayControls'
import LayerPanel from './components/layers/LayerPanel'

// Panels render conditionally — code-split them so first paint only
// pays for the map shell.
const InspectPanel = lazy(() => import('./components/panels/InspectPanel'))
const CycloneForecastPanel = lazy(() => import('./components/panels/CycloneForecastPanel'))
const EarthquakePanel = lazy(() => import('./components/panels/EarthquakePanel'))
const MeasurementPanel = lazy(() => import('./components/panels/MeasurementPanel'))
import VolcanoPopup from './components/panels/VolcanoPopup'
import ResolutionIndicator from './components/panels/ResolutionIndicator'
import MapTimestamp from './components/panels/MapTimestamp'
import ProfilePopup from './components/panels/ProfilePopup'
import PanelErrorBoundary from './components/PanelErrorBoundary'

export default function App() {
  const containerRef = useRef<HTMLDivElement>(null)
  const { ready, map } = useMap(containerRef)
  const { t } = useI18n()
  useLayerVisibility(ready ? map : null)
  useCyclonePulse(ready ? map : null)
  useCycloneRefresh(ready ? map : null)
  useEarthquakes(ready ? map : null)
  useReplay(ready ? map : null)
  useNotificationFeeds()
  useDrawing(ready ? map : null)

  return (
    <div className="app">
      <TopBar />
      <div className="map-wrap">
        <div ref={containerRef} className="map-container" />
        <PanelErrorBoundary label="Layer panel"><LayerPanel /></PanelErrorBoundary>
        <Suspense fallback={null}>
          <PanelErrorBoundary label="Cyclone forecast"><CycloneForecastPanel /></PanelErrorBoundary>
          <PanelErrorBoundary label="Earthquake monitor"><EarthquakePanel /></PanelErrorBoundary>
          <PanelErrorBoundary label="Location inspector"><InspectPanel /></PanelErrorBoundary>
          <PanelErrorBoundary label="Draw & measure"><MeasurementPanel /></PanelErrorBoundary>
        </Suspense>
        <PanelErrorBoundary label="Volcano popup"><VolcanoPopup /></PanelErrorBoundary>
        <PanelErrorBoundary label="Elevation profile"><ProfilePopup /></PanelErrorBoundary>
        <ResolutionIndicator />
        <MapTimestamp />
        <MapControls />
        <ReplayControls />
        <TimeMachine />
        {!ready && <div className="map-boot">{t('app.booting')}</div>}
      </div>
    </div>
  )
}
