import { describe, expect, it } from 'vitest'
import { pathLengthKm, polygonAreaKm2 } from './stores'

describe('pathLengthKm', () => {
  it('returns 0 for a single point', () => {
    expect(pathLengthKm([[121, 16]])).toBe(0)
  })

  it('computes ~111 km per degree of latitude', () => {
    const len = pathLengthKm([[121, 16], [121, 17]])
    expect(len).toBeGreaterThan(110)
    expect(len).toBeLessThan(112)
  })

  it('is symmetric', () => {
    const a: [number, number][] = [[121, 16], [121.5, 16.4]]
    expect(pathLengthKm(a)).toBeCloseTo(pathLengthKm([...a].reverse()), 6)
  })
})

describe('polygonAreaKm2', () => {
  it('returns 0 for degenerate rings', () => {
    expect(polygonAreaKm2([[121, 16]])).toBe(0)
  })

  it('computes a plausible area for a 1-degree box near the equator', () => {
    // ~111km x ~110km square -> roughly 12,300 km^2
    const area = polygonAreaKm2([
      [121, 16], [122, 16], [122, 17], [121, 17],
    ])
    expect(area).toBeGreaterThan(10_000)
    expect(area).toBeLessThan(14_000)
  })

  it('ignores winding direction (absolute value)', () => {
    const cw = polygonAreaKm2([[121, 16], [122, 16], [122, 17], [121, 17]])
    const ccw = polygonAreaKm2([[121, 16], [121, 17], [122, 17], [122, 16]])
    expect(cw).toBeCloseTo(ccw, 3)
  })
})
