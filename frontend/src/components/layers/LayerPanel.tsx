import { useLayerStore } from '../../stores'

export default function LayerPanel() {
  const { layers, toggle, setOpacity, moveUp, moveDown } = useLayerStore()

  return (
    <aside className="layer-panel">
      <div className="panel-title">LAYERS</div>
      <div className="layer-list">
        {layers.map((layer, idx) => (
          <div key={layer.id} className={`layer-row ${layer.visible ? 'on' : ''}`}>
            <div className="layer-main">
              <label className="checkbox">
                <input type="checkbox" checked={layer.visible} onChange={() => toggle(layer.id)} />
                <span className="checkmark" />
                <span className="layer-name">{layer.name}</span>
              </label>
              <div className="layer-actions">
                <button disabled={idx === 0} onClick={() => moveUp(layer.id)} title="Raise">▲</button>
                <button disabled={idx === layers.length - 1} onClick={() => moveDown(layer.id)} title="Lower">▼</button>
              </div>
            </div>
            <div className="layer-meta">{layer.description}</div>
            {layer.visible && (
              <div className="layer-extra">
                <label className="opacity-row">
                  Opacity
                  <input
                    type="range" min={0.05} max={1} step={0.05}
                    value={layer.opacity}
                    onChange={(e) => setOpacity(layer.id, Number(e.target.value))}
                  />
                  <span>{Math.round(layer.opacity * 100)}%</span>
                </label>
                {layer.legend && (
                  <div className="legend">
                    {layer.legend.map((item) => (
                      <span key={item.label} className="legend-item">
                        <i style={{ background: item.color }} /> {item.label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </aside>
  )
}
