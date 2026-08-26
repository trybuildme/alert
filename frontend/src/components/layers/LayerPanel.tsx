import { useLayerStore } from '../../stores'
import { useI18n } from '../../i18n'

export default function LayerPanel() {
  const { layers, toggle, setOpacity, moveUp, moveDown } = useLayerStore()
  const { t, lang } = useI18n()
  // Layer metadata carries optional Filipino variants; English is the
  // fallback so a missing translation can never blank a row.
  const pick = (en: string, fil: string | undefined) =>
    lang === 'fil' && fil ? fil : en

  return (
    <aside className="layer-panel">
      <div className="panel-title">{t('layers.title')}</div>
      <div className="layer-list">
        {layers.map((layer, idx) => (
          <div key={layer.id} className={`layer-row ${layer.visible ? 'on' : ''}`}>
            <div className="layer-main">
              <label className="checkbox">
                <input type="checkbox" checked={layer.visible} onChange={() => toggle(layer.id)} />
                <span className="checkmark" />
                <span className="layer-name">{pick(layer.name, layer.nameFil)}</span>
              </label>
              <div className="layer-actions">
                <button disabled={idx === 0} onClick={() => moveUp(layer.id)} title={t('layers.raise')}>▲</button>
                <button disabled={idx === layers.length - 1} onClick={() => moveDown(layer.id)} title={t('layers.lower')}>▼</button>
              </div>
            </div>
            <div className="layer-meta">{pick(layer.description, layer.descriptionFil)}</div>
            {layer.visible && (
              <div className="layer-extra">
                <label className="opacity-row">
                  {t('layers.opacity')}
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
