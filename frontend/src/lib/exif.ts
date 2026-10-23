import piexif from 'piexifjs'

export interface ScreenshotMeta {
  timestamp: string
  centerLat: number
  centerLon: number
  zoom: number
  basemap: string
  description: string
  layers: string[]
}

function decToDms(dec: number): [[number, number], [number, number], [number, number]] {
  const abs = Math.abs(dec)
  const d = Math.floor(abs)
  const mFloat = (abs - d) * 60
  const m = Math.floor(mFloat)
  const s = Math.round((mFloat - m) * 60 * 100)
  return [[d, 1], [m, 1], [s, 100]]
}

export function embedJpgExif(dataUrl: string, meta: ScreenshotMeta): string {
  const ts = meta.timestamp.replace('T', ' ').replace(/\.\d{3}Z$/, '')
  const comment = `ALERT GIS — zoom ${meta.zoom.toFixed(1)}, basemap: ${meta.basemap}, layers: ${meta.layers.join(', ')}`

  const exifObj = {
    '0th': {
      270: meta.description,               // ImageDescription
      305: 'A.L.E.R.T GIS',               // Software
    },
    'Exif': {
      36867: ts,                            // DateTimeOriginal
      37510: comment,                       // UserComment
    },
    'GPS': {
      1: meta.centerLat >= 0 ? 'N' : 'S',  // GPSLatitudeRef
      2: decToDms(meta.centerLat),          // GPSLatitude
      3: meta.centerLon >= 0 ? 'E' : 'W',  // GPSLongitudeRef
      4: decToDms(meta.centerLon),          // GPSLongitude
    },
  } as const

  try {
    const exifBytes = piexif.dump(exifObj as any)
    return piexif.insert(exifBytes, dataUrl)
  } catch (e) {
    console.warn('[exif] piexif.dump failed, returning untagged:', e)
    return dataUrl
  }
}

export function embedPngMetadata(blob: Blob, meta: ScreenshotMeta): Promise<Blob> {
  return blob.arrayBuffer().then((buf) => {
    const src = new Uint8Array(buf)
    const chunks: Uint8Array[] = []
    let pos = 8
    while (pos < src.length) {
      const len = (src[pos] << 24 | src[pos + 1] << 16 | src[pos + 2] << 8 | src[pos + 3]) >>> 0
      const type = String.fromCharCode(src[pos + 4], src[pos + 5], src[pos + 6], src[pos + 7])
      chunks.push(src.slice(pos, pos + 12 + len))
      pos += 12 + len
      if (type === 'IEND') break
    }

    const keyword = 'Description'
    const text = JSON.stringify(meta)
    const textBytes = new TextEncoder().encode(keyword + '\0' + text)
    const texChunk = new Uint8Array(4 + 4 + textBytes.length + 4)
    texChunk[0] = (textBytes.length >> 24) & 0xff
    texChunk[1] = (textBytes.length >> 16) & 0xff
    texChunk[2] = (textBytes.length >> 8) & 0xff
    texChunk[3] = textBytes.length & 0xff
    texChunk[4] = 0x74; texChunk[5] = 0x45; texChunk[6] = 0x58; texChunk[7] = 0x74
    texChunk.set(textBytes, 8)
    const crcData = texChunk.slice(4, 8 + textBytes.length)
    let crc = 0xffffffff
    for (let i = 0; i < crcData.length; i++) {
      crc ^= crcData[i]
      for (let j = 0; j < 8; j++) crc = (crc >>> 1) ^ (crc & 1 ? 0xedb88320 : 0)
    }
    crc = (crc ^ 0xffffffff) >>> 0
    texChunk[8 + textBytes.length] = (crc >> 24) & 0xff
    texChunk[8 + textBytes.length + 1] = (crc >> 16) & 0xff
    texChunk[8 + textBytes.length + 2] = (crc >> 8) & 0xff
    texChunk[8 + textBytes.length + 3] = crc & 0xff

    const iendIdx = chunks.length - 1
    chunks.splice(iendIdx, 0, texChunk)
    const totalLen = chunks.reduce((s, c) => s + c.length, 0)
    const out = new Uint8Array(totalLen)
    let wp = 0
    for (const chunk of chunks) { out.set(chunk, wp); wp += chunk.length }
    return new Blob([out], { type: 'image/png' })
  })
}
