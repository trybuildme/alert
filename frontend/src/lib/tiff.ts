/**
 * Minimal uncompressed RGB TIFF writer — pure TypeScript, no dependencies.
 *
 * Produces a valid baseline TIFF 6.0 file with:
 *   - 8-bit RGB (SamplesPerPixel=3, BitsPerSample=8)
 *   - No compression (Compression=1)
 *   - Single strip
 *   - ImageDescription + Software tags
 *   - GPS IFD (ExifIFD) with lat/lon
 *   - GeoTIFF ModelPixelScale + ModelTiepoint for basic georeferencing
 *
 * Byte order: little-endian (Intel).
 */

import type { ScreenshotMeta } from './exif'

const LE = true // little-endian

function writeU16(buf: DataView, off: number, v: number) { buf.setUint16(off, v, LE) }
function writeU32(buf: DataView, off: number, v: number) { buf.setUint32(off, v, LE) }

/** Compute a TIFF IFD entry size for a given tag. */
function ifdEntrySize(tag: number, count: number): number {
  // 4 bytes value inline if ≤4 bytes; otherwise 4-byte offset + data elsewhere
  const dataBytes = tag === 3 || tag === 4 ? 8 : count * dataTypeSize(tag)
  return dataBytes <= 4 ? 0 : dataBytes
}

function dataTypeSize(tag: number): number {
  // We only use types 2 (ASCII), 3 (SHORT), 4 (LONG), 5 (RATIONAL)
  if (tag === 33550 || tag === 33922) return 8 // RATIONAL or DOUBLE
  return 0
}

/** Tag IDs we use */
const TAG = {
  IMAGE_WIDTH: 256,
  IMAGE_LENGTH: 257,
  BITS_PER_SAMPLE: 258,
  COMPRESSION: 259,
  PHOTOMETRIC: 262,
  IMAGE_DESCRIPTION: 270,
  STRIP_OFFSETS: 273,
  SAMPLES_PER_PIXEL: 277,
  ROWS_PER_STRIP: 278,
  STRIP_BYTE_COUNTS: 279,
  X_RESOLUTION: 282,
  Y_RESOLUTION: 283,
  RESOLUTION_UNIT: 296,
  SOFTWARE: 305,
  // GeoTIFF
  MODEL_PIXEL_SCALE: 33550,
  MODEL_TIEPOINT: 33922,
  // Exif IFD pointer
  EXIF_IFD: 34665,
} as const

/** Data type codes */
const DT = {
  SHORT: 3,
  LONG: 4,
  ASCII: 2,
  RATIONAL: 5,
  DOUBLE: 12,
} as const

interface IfdEntry {
  tag: number
  type: number
  count: number
  valueOrOffset: number
  extraData?: Uint8Array
}

/**
 * Build a TIFF file from canvas pixel data and metadata.
 */
export function writeTiff(
  pixels: Uint8ClampedArray,
  width: number,
  height: number,
  meta: ScreenshotMeta,
): Blob {
  // --- String data (written after IFD) ---
  const desc = `ALERT GIS — zoom ${meta.zoom.toFixed(1)}, basemap: ${meta.basemap}, layers: ${meta.layers.join(', ')}`
  const software = 'A.L.E.R.T GIS'
  const descBytes = new TextEncoder().encode(desc + '\0')
  const swBytes = new TextEncoder().encode(software + '\0')

  // --- GPS rational values ---
  const gpsLat = toRationalArray(meta.centerLat)
  const gpsLon = toRationalArray(meta.centerLon)
  const gpsLatRef = meta.centerLat >= 0 ? 'N\0' : 'S\0'
  const gpsLonRef = meta.centerLon >= 0 ? 'E\0' : 'W\0'
  const gpsLatRefBytes = new TextEncoder().encode(gpsLatRef)
  const gpsLonRefBytes = new TextEncoder().encode(gpsLonRef)

  // --- GeoTIFF values ---
  // ModelPixelScale: [pixelWidthDegrees, pixelHeightDegrees, 0]
  const degPerPixel = 360 / (256 * Math.pow(2, meta.zoom))
  const pixelScale = new Float64Array([degPerPixel, degPerPixel, 0])
  // ModelTiepoint: [0, 0, 0, tiepointLon, tiepointLat, 0]
  const tiepoint = new Float64Array([0, 0, 0, meta.centerLon, meta.centerLat, 0])

  // --- Pixel data (uncompressed RGB) ---
  const rowBytes = width * 3
  const pixelData = new Uint8Array(width * height * 3)
  for (let y = 0; y < height; y++) {
    const srcRow = y * width * 4 // RGBA
    const dstRow = y * rowBytes
    for (let x = 0; x < width; x++) {
      const si = srcRow + x * 4
      const di = dstRow + x * 3
      pixelData[di] = pixels[si]
      pixelData[di + 1] = pixels[si + 1]
      pixelData[di + 2] = pixels[si + 2]
    }
  }

  // --- Layout offsets ---
  const IFD_ENTRIES = 17
  const IFD_SIZE = 2 + IFD_ENTRIES * 12 + 4 // count + entries + nextIFD
  const HEADER_SIZE = 8

  // After header + IFD: extra data region
  let extraOff = HEADER_SIZE + IFD_SIZE
  const extraChunks: Uint8Array[] = []

  function allocExtra(data: Uint8Array): number {
    const off = extraOff
    extraChunks.push(data)
    extraOff += data.length
    return off
  }

  // Allocate extra data for variable-length fields
  const descOff = allocExtra(descBytes)
  const swOff = allocExtra(swBytes)
  const gpsLatRefOff = allocExtra(gpsLatRefBytes)
  const gpsLonRefOff = allocExtra(gpsLonRefBytes)
  const gpsLatOff = allocExtra(new Uint8Array(gpsLat.buffer))
  const gpsLonOff = allocExtra(new Uint8Array(gpsLon.buffer))
  const psOff = allocExtra(new Uint8Array(pixelScale.buffer))
  const tpOff = allocExtra(new Uint8Array(tiepoint.buffer))

  // GPS IFD (Exif sub-IFD): 7 entries
  const GPS_IFD_ENTRIES = 7
  const GPS_IFD_SIZE = 2 + GPS_IFD_ENTRIES * 12 + 4
  const gpsIfdOff = extraOff
  extraOff += GPS_IFD_SIZE

  // --- Build main IFD entries ---
  const entries: IfdEntry[] = [
    { tag: TAG.IMAGE_WIDTH, type: DT.LONG, count: 1, valueOrOffset: width },
    { tag: TAG.IMAGE_LENGTH, type: DT.LONG, count: 1, valueOrOffset: height },
    { tag: TAG.BITS_PER_SAMPLE, type: DT.SHORT, count: 3, valueOrOffset: 0,
      extraData: new Uint8Array([8, 0, 8, 0, 8, 0]) }, // 3 × SHORT 8
    { tag: TAG.COMPRESSION, type: DT.SHORT, count: 1, valueOrOffset: 1 },
    { tag: TAG.PHOTOMETRIC, type: DT.SHORT, count: 1, valueOrOffset: 2 },
    { tag: TAG.IMAGE_DESCRIPTION, type: DT.ASCII, count: descBytes.length, valueOrOffset: descOff },
    { tag: TAG.STRIP_OFFSETS, type: DT.LONG, count: 1, valueOrOffset: extraOff }, // pixel data starts here
    { tag: TAG.SAMPLES_PER_PIXEL, type: DT.SHORT, count: 1, valueOrOffset: 3 },
    { tag: TAG.ROWS_PER_STRIP, type: DT.LONG, count: 1, valueOrOffset: height },
    { tag: TAG.STRIP_BYTE_COUNTS, type: DT.LONG, count: 1, valueOrOffset: pixelData.length },
    { tag: TAG.X_RESOLUTION, type: DT.RATIONAL, count: 1, valueOrOffset: allocExtra(
      new Uint8Array(new Uint32Array([300, 1]).buffer)) },
    { tag: TAG.Y_RESOLUTION, type: DT.RATIONAL, count: 1, valueOrOffset: allocExtra(
      new Uint8Array(new Uint32Array([300, 1]).buffer)) },
    { tag: TAG.RESOLUTION_UNIT, type: DT.SHORT, count: 1, valueOrOffset: 2 },
    { tag: TAG.SOFTWARE, type: DT.ASCII, count: swBytes.length, valueOrOffset: swOff },
    { tag: TAG.MODEL_PIXEL_SCALE, type: DT.DOUBLE, count: 3, valueOrOffset: psOff },
    { tag: TAG.MODEL_TIEPOINT, type: DT.DOUBLE, count: 6, valueOrOffset: tpOff },
    { tag: TAG.EXIF_IFD, type: DT.LONG, count: 1, valueOrOffset: gpsIfdOff },
  ]

  // --- Compute total file size ---
  const totalSize = extraOff + pixelData.length
  const buf = new ArrayBuffer(totalSize)
  const view = new DataView(buf)
  const bytes = new Uint8Array(buf)

  // --- Write TIFF header ---
  bytes[0] = 0x49; bytes[1] = 0x49 // 'II' = little-endian
  writeU16(view, 2, 42) // TIFF magic
  writeU32(view, 4, HEADER_SIZE) // offset to first IFD

  // --- Write IFD ---
  let ifdPos = HEADER_SIZE
  writeU16(view, ifdPos, IFD_ENTRIES)
  ifdPos += 2

  for (const entry of entries) {
    writeU16(view, ifdPos, entry.tag)
    writeU16(view, ifdPos + 2, entry.type)
    writeU32(view, ifdPos + 4, entry.count)

    const val = entry.valueOrOffset
    if (entry.extraData) {
      // Inline if ≤4 bytes, otherwise write offset
      if (entry.extraData.length <= 4) {
        for (let i = 0; i < entry.extraData.length; i++) bytes[ifdPos + 8 + i] = entry.extraData[i]
      } else {
        writeU32(view, ifdPos + 8, val)
        bytes.set(entry.extraData, val)
      }
    } else if (entry.type === DT.SHORT && entry.count === 1) {
      writeU16(view, ifdPos + 8, val)
    } else {
      writeU32(view, ifdPos + 8, val)
    }
    ifdPos += 12
  }
  writeU32(view, ifdPos, 0) // no next IFD

  // --- Write GPS sub-IFD ---
  const gpsEntries = [
    { tag: 1, type: DT.ASCII, count: 2, val: gpsLatRefOff, data: gpsLatRefBytes },
    { tag: 2, type: DT.RATIONAL, count: 3, val: gpsLatOff, data: new Uint8Array(gpsLat.buffer) },
    { tag: 3, type: DT.ASCII, count: 2, val: gpsLonRefOff, data: gpsLonRefBytes },
    { tag: 4, type: DT.RATIONAL, count: 3, val: gpsLonOff, data: new Uint8Array(gpsLon.buffer) },
  ]
  let gp = gpsIfdOff
  writeU16(view, gp, gpsEntries.length)
  gp += 2
  for (const ge of gpsEntries) {
    writeU16(view, gp, ge.tag)
    writeU16(view, gp + 2, ge.type)
    writeU32(view, gp + 4, ge.count)
    if (ge.data.length <= 4) {
      for (let i = 0; i < ge.data.length; i++) bytes[gp + 8 + i] = ge.data[i]
    } else {
      writeU32(view, gp + 8, ge.val)
      bytes.set(ge.data, ge.val)
    }
    gp += 12
  }
  writeU32(view, gp, 0) // no next IFD

  // --- Write pixel data ---
  bytes.set(pixelData, extraOff)

  return new Blob([buf], { type: 'image/tiff' })
}

/** Convert decimal degrees to TIFF GPS RATIONAL array [deg, min, sec×100] × 2 values = 6 values */
function toRationalArray(dec: number): Uint32Array {
  const abs = Math.abs(dec)
  const d = Math.floor(abs)
  const mFloat = (abs - d) * 60
  const m = Math.floor(mFloat)
  const s = Math.round((mFloat - m) * 60 * 100)
  // Each RATIONAL is [numerator, denominator] × 3 components
  return new Uint32Array([d, 1, m, 1, s, 100])
}
