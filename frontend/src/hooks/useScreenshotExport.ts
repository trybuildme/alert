import { useCallback } from 'react'
import maplibregl from 'maplibre-gl'
import { useMapStore, useSatelliteStore, useLayerStore } from '../stores'
import { embedJpgExif, embedPngMetadata, type ScreenshotMeta } from '../lib/exif'
import { writeTiff } from '../lib/tiff'

export interface ScreenshotOptions {
  format: 'jpg' | 'png' | 'tiff'
  quality: number
  scale: 1 | 2 | 4
}

function buildFilename(meta: ScreenshotMeta, ext: string): string {
  const lonDir = meta.centerLon >= 0 ? 'E' : 'W'
  const latDir = meta.centerLat >= 0 ? 'N' : 'S'
  const ts = meta.timestamp.replace(/[:.]/g, '-').slice(0, 19)
  const z = meta.zoom.toFixed(1)
  return `alert-map-export_${ts}_z${z}_${Math.abs(meta.centerLon).toFixed(2)}${lonDir}_${Math.abs(meta.centerLat).toFixed(2)}${latDir}.${ext}`
}

function getBbox(coordinates: number[][]): [number, number, number, number] {
  const coords = coordinates as unknown as [number, number][]
  let minLon = Infinity, maxLon = -Infinity, minLat = Infinity, maxLat = -Infinity
  for (const [lon, lat] of coords) {
    if (lon < minLon) minLon = lon
    if (lon > maxLon) maxLon = lon
    if (lat < minLat) minLat = lat
    if (lat > maxLat) maxLat = lat
  }
  return [minLon, minLat, maxLon, maxLat]
}

function triggerDownload(blob: Blob, filename: string) {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.style.display = 'none'
  document.body.appendChild(a)
  a.click()
  setTimeout(() => {
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }, 500)
}

function loadImage(src: string): Promise<HTMLImageElement> {
  return new Promise((resolve, reject) => {
    const img = new Image()
    img.onload = () => resolve(img)
    img.onerror = () => reject(new Error('image load failed'))
    img.src = src
  })
}

/** Wait for a render + idle, then resolve. */
function waitForRender(map: maplibregl.Map, timeoutMs = 3000): Promise<void> {
  return new Promise((resolve) => {
    let done = false
    const finish = () => {
      if (done) return
      done = true
      clearTimeout(timer)
      resolve()
    }
    const timer = setTimeout(finish, timeoutMs)
    map.once('idle', finish)
  })
}

export function useScreenshotExport() {
  const exportScreenshot = useCallback(async (
    feature: { coordinates: number[][]; tool: string; center: [number, number]; id: number },
    opts: ScreenshotOptions,
  ) => {
    const map = useMapStore.getState().map
    if (!map) { alert('Map not ready.'); return }

    const bbox = getBbox(feature.coordinates)
    const centerLon = (bbox[0] + bbox[2]) / 2
    const centerLat = (bbox[1] + bbox[3]) / 2
    const zoom = map.getZoom()

    const topLeft = map.project(new maplibregl.LngLat(bbox[0], bbox[3]))
    const bottomRight = map.project(new maplibregl.LngLat(bbox[2], bbox[1]))

    const cropX = Math.round(topLeft.x)
    const cropY = Math.round(topLeft.y)
    const cropW = Math.round(bottomRight.x - topLeft.x)
    const cropH = Math.round(bottomRight.y - topLeft.y)

    if (cropW <= 0 || cropH <= 0) { alert('Selection too small.'); return }

    // Wait for map to finish rendering tiles
    await waitForRender(map)

    // Force a synchronous render
    map.triggerRepaint()

    // Wait one frame for the paint to flush
    await new Promise<void>((r) => requestAnimationFrame(() => r()))

    // Read canvas via toDataURL (preserveDrawingBuffer must be true)
    const srcCanvas = map.getCanvas()
    let fullDataUrl: string
    try {
      fullDataUrl = srcCanvas.toDataURL('image/png')
    } catch (e) {
      console.error('[screenshot] toDataURL failed:', e)
      alert('Canvas read failed.')
      return
    }

    // Check if the data URL is suspiciously small (blank canvas)
    if (fullDataUrl.length < 5000) {
      console.warn('[screenshot] canvas appears blank, data URL length:', fullDataUrl.length)
      alert('Map canvas is blank — please try again.')
      return
    }

    // Load into an Image, then crop via 2D canvas
    const fullImg = await loadImage(fullDataUrl)
    const scaledW = cropW * opts.scale
    const scaledH = cropH * opts.scale
    const METADATA_BAR = 64

    const offscreen = document.createElement('canvas')
    offscreen.width = scaledW
    offscreen.height = scaledH + METADATA_BAR
    const ctx = offscreen.getContext('2d')!
    if (!ctx) return

    // Crop from the loaded Image (pure 2D → 2D)
    ctx.drawImage(fullImg, cropX, cropY, cropW, cropH, 0, 0, scaledW, scaledH)

    // Metadata bar
    ctx.fillStyle = 'rgba(10, 14, 23, 0.92)'
    ctx.fillRect(0, scaledH, scaledW, METADATA_BAR)

    const activeBasemap = useSatelliteStore.getState().activeProduct
    const visibleLayers = useLayerStore.getState().layers
      .filter((l) => l.visible).map((l) => l.name).join(', ')

    ctx.fillStyle = '#e2e8f0'
    ctx.font = '13px monospace'
    const ts = new Date().toISOString()
    const bboxStr = `[${bbox[1].toFixed(4)}, ${bbox[0].toFixed(4)}] → [${bbox[3].toFixed(4)}, ${bbox[2].toFixed(4)}]`
    ctx.fillText(`COORDS: ${bboxStr}   ZOOM: ${zoom.toFixed(1)}   DATE: ${ts.slice(0, 10)}`, 12, scaledH + 24)
    ctx.fillStyle = '#94a3b8'
    ctx.font = '11px monospace'
    ctx.fillText(`A.L.E.R.T GIS · ${activeBasemap}${visibleLayers ? ' · ' + visibleLayers : ''}`, 12, scaledH + 46)

    // Watermark
    ctx.fillStyle = 'rgba(34, 211, 238, 0.7)'
    ctx.font = 'bold 14px monospace'
    ctx.textAlign = 'right'
    ctx.fillText('A.L.E.R.T', scaledW - 12, 24)
    ctx.textAlign = 'left'

    const meta: ScreenshotMeta = {
      timestamp: ts, centerLat, centerLon, zoom, basemap: activeBasemap,
      description: `ALERT GIS export — bbox: ${bboxStr}`,
      layers: visibleLayers ? visibleLayers.split(', ') : [],
    }

    const ext = opts.format === 'jpg' ? 'jpg' : opts.format === 'tiff' ? 'tiff' : 'png'
    const filename = buildFilename(meta, ext)

    if (opts.format === 'tiff') {
      try {
        const imgData = ctx.getImageData(0, 0, scaledW, scaledH)
        const tiffBlob = writeTiff(imgData.data, scaledW, scaledH, meta)
        triggerDownload(tiffBlob, filename)
      } catch (e) {
        console.error('[screenshot] TIFF export failed:', e)
        alert('Export failed — try PNG.')
      }
    } else if (opts.format === 'jpg') {
      try {
        const dataUrl = offscreen.toDataURL('image/jpeg', opts.quality)
        let finalDataUrl: string
        try { finalDataUrl = embedJpgExif(dataUrl, meta) } catch { finalDataUrl = dataUrl }
        const binStr = atob(finalDataUrl.split(',')[1])
        const arr = new Uint8Array(binStr.length)
        for (let i = 0; i < binStr.length; i++) arr[i] = binStr.charCodeAt(i)
        triggerDownload(new Blob([arr], { type: 'image/jpeg' }), filename)
      } catch (e) {
        console.error('[screenshot] JPG export failed:', e)
        alert('Export failed — try PNG.')
      }
    } else {
      try {
        offscreen.toBlob((blob) => {
          if (!blob) { alert('Export failed.'); return }
          embedPngMetadata(blob, meta)
            .then((fb) => triggerDownload(fb, filename))
            .catch(() => triggerDownload(blob, filename))
        }, 'image/png')
      } catch (e) {
        console.error('[screenshot] PNG export failed:', e)
        alert('Export failed.')
      }
    }
  }, [])

  return { exportScreenshot }
}
