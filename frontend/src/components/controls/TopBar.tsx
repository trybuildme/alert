import { useEffect, useRef, useState } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapStore, useSatelliteStore, useUIStore, useInspectStore, useLayerStore } from '../../stores'
import { ALL_PRODUCTS, BASEMAPS } from '../../config/mapConfig'

interface SearchResult {
  name: string
  level: string
  parent: string | null
  lat: number
  lon: number
  zoom: number
}

export default function TopBar() {
  const map = useMapStore((s) => s.map)
  const { activeProduct, setActiveProduct, irEnhanced, setIrEnhanced } = useSatelliteStore()
  const { basemap, setBasemap, mode2D, setMode2D } = useUIStore()
  const forecastPanelOpen = useUIStore((s) => s.forecastPanelOpen)
  const toggleForecastPanel = useUIStore((s) => s.toggleForecastPanel)
  const openInspect = useInspectStore((s) => s.openInspect)

  return (
    <header className="topbar">
      <div className="topbar-brand">
        <span className="brand-mark" />
        <div>
          <div className="brand-name">AURORA-GIS</div>
          <div className="brand-sub">Interactive Satellite Platform</div>
        </div>
      </div>

      <SearchBox onPick={(r) => {
        if (!map) return
        map.flyTo({ center: [r.lon, r.lat], zoom: r.zoom, speed: 1.5, essential: true })
        if (r.level === 'coordinates') openInspect(r.lat, r.lon)
      }} />

      <div className="topbar-group">
        <span className="group-label">BASE MAP</span>
        <div className="switcher">
          {Object.values(BASEMAPS).map((bm) => (
            <button
              key={bm.id}
              className={`switch-btn ${basemap === bm.id ? 'active' : ''}`}
              onClick={() => setBasemap(bm.id)}
              title={bm.attribution}
            >
              {bm.name}
            </button>
          ))}
        </div>
      </div>

      <div className="topbar-group">
        <span className="group-label">SATELLITE</span>
        <select
          className="product-select"
          value={activeProduct}
          onChange={(e) => setActiveProduct(e.target.value)}
        >
          <optgroup label="Himawari-class products">
            {ALL_PRODUCTS.filter((p) => p.timeDependent).map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.resolutionLabel})</option>
            ))}
          </optgroup>
          <optgroup label="High-resolution optical">
            {ALL_PRODUCTS.filter((p) => !p.timeDependent).map((p) => (
              <option key={p.id} value={p.id}>{p.name} ({p.resolutionLabel})</option>
            ))}
          </optgroup>
        </select>
        {activeProduct === 'himawari-clean-ir' && (
          <button
            className={`switch-btn ${irEnhanced ? 'active' : ''}`}
            onClick={() => setIrEnhanced(!irEnhanced)}
            title="Windy-style color enhancement: cold cloud tops flare yellow → red → violet"
          >
            Enhanced
          </button>
        )}
      </div>

      <div className="topbar-group">
        <span className="group-label">TROPICAL</span>
        <button
          className={`switch-btn ${forecastPanelOpen ? 'active' : ''}`}
          onClick={() => {
            toggleForecastPanel()
            const ls = useLayerStore.getState()
            for (const id of ['cyclones', 'cyclone-forecast']) {
              const l = ls.layers.find((x) => x.id === id)
              if (l && !l.visible) ls.toggle(id)
            }
          }}
          title="7-day cyclone outlook: predicted track, typhoon status and PAGASA signal numbers"
        >
          Cyclone 7-Day
        </button>
      </div>

      <div className="mode-toggle">
        <button className={!mode2D ? 'active' : ''} onClick={() => setMode2D(false)}>3D EARTH</button>
        <button className={mode2D ? 'active' : ''} onClick={() => setMode2D(true)}>2D MAP</button>
      </div>
    </header>
  )
}

function SearchBox({ onPick }: { onPick: (r: SearchResult) => void }) {
  const [query, setQuery] = useState('')
  const [results, setResults] = useState<SearchResult[]>([])
  const [open, setOpen] = useState(false)
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null)

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current)
    if (query.trim().length < 2) {
      setResults([])
      return
    }
    debounceRef.current = setTimeout(async () => {
      try {
        const res = await fetch(`/api/search?q=${encodeURIComponent(query.trim())}`)
        const body = await res.json()
        setResults(body.results ?? [])
        setOpen(true)
      } catch {
        setResults([])
      }
    }, 250)
    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current)
    }
  }, [query])

  return (
    <div className="searchbox">
      <input
        type="text"
        placeholder="Search place or lat, lon …"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 180)}
        onKeyDown={(e) => {
          if (e.key === 'Enter' && results.length > 0) onPick(results[0])
        }}
      />
      {open && results.length > 0 && (
        <ul className="search-results">
          {results.map((r, i) => (
            <li key={`${r.name}-${i}`} onMouseDown={() => onPick(r)}>
              <span className="result-name">{r.name}</span>
              <span className="result-meta">{r.parent ? `${r.level} · ${r.parent}` : r.level}</span>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}
