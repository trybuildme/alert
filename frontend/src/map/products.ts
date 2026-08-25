// Satellite product layer management: visibility switching (with the
// Sentinel-2/Esri deep-zoom underlay stack) and tile URL updates.

import type maplibregl from 'maplibre-gl'
import { ALL_PRODUCTS, getProduct } from '../config/mapConfig'

export const SAT_PREFIX = 'sat-product-'

const UNDERLAYS: Record<string, string> = {
  'esri-world': 'sentinel2-cloudless',
}

export function applyProductVisibility(map: maplibregl.Map, activeProduct: string) {
  const underlay = UNDERLAYS[activeProduct] ?? null
  // Deep-zoom assist: viewing Sentinel-2 (~10 m) past z15 would show
  // 32x over-stretched pixels even though ~1 m Esri imagery exists.
  // Stack Esri ON TOP from z15 so the sharpest real source wins; S2
  // remains visible beneath, filling Esri's clouds and coverage gaps.
  const deepZoomEsri = activeProduct === 'sentinel2-cloudless'
  for (const p of ALL_PRODUCTS) {
    const layerId = `${SAT_PREFIX}${p.id}`
    if (!map.getLayer(layerId)) continue
    let visible = p.id === activeProduct || p.id === underlay
    if (deepZoomEsri && p.id === 'esri-world') {
      visible = map.getZoom() >= 15
    }
    map.setLayoutProperty(layerId, 'visibility', visible ? 'visible' : 'none')
  }
}

export function setProductTiles(map: maplibregl.Map, productId: string, time: string | null,
                                 palette?: string) {
  const product = getProduct(productId)
  const source = map.getSource(`${SAT_PREFIX}${productId}`) as maplibregl.RasterTileSource | undefined
  if (!product || !source) return
  try {
    source.setTiles(product.tiles(time ?? undefined, palette))
  } catch {
    // older runtimes: recreate source
    map.removeSource(`${SAT_PREFIX}${productId}`)
    map.addSource(`${SAT_PREFIX}${productId}`, {
      type: 'raster',
      tiles: product.tiles(time ?? undefined, palette),
      tileSize: product.tileSize,
      maxzoom: product.maxzoom,
      attribution: product.attribution,
    })
  }
}
