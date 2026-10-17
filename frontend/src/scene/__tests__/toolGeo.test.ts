import { describe, expect, it } from 'vitest'
import { bearingDeg, destination, distanceM, fmtBearing, fmtDist, geoCircle, greatCircle, pathLengthM, type LngLat } from '../toolGeo'

const STHLM: LngLat = [18.0686, 59.3293]
const GBG: LngLat = [11.9746, 57.7089]

describe('tool geodesy', () => {
  it('measures Stockholm–Göteborg like a reference great-circle calculator', () => {
    // sphere vs ellipsoid (~397.6 km): within 0.5 %
    expect(Math.abs(distanceM(STHLM, GBG) / 1000 - 397.6) / 397.6).toBeLessThan(0.005)
    expect(bearingDeg(STHLM, GBG)).toBeGreaterThan(243)
    expect(bearingDeg(STHLM, GBG)).toBeLessThan(248)
  })
  it('cardinal bearings and round trips', () => {
    expect(bearingDeg([15, 60], [15, 61])).toBeCloseTo(0, 6)
    expect(bearingDeg([15, 60], [16, 60])).toBeCloseTo(89.57, 1)
    const p = destination(STHLM, 123, 25_000)
    expect(distanceM(STHLM, p)).toBeCloseTo(25_000, 3)
    expect(bearingDeg(STHLM, p)).toBeCloseTo(123, 6)
  })
  it('densified lines and circles keep true lengths', () => {
    const gc = greatCircle(STHLM, GBG)
    expect(gc[0]).toEqual(STHLM); expect(gc[gc.length - 1]).toEqual(GBG)
    expect(pathLengthM(gc)).toBeCloseTo(distanceM(STHLM, GBG), 0)
    const ring = geoCircle(STHLM, 50_000)
    for (const v of ring) expect(distanceM(STHLM, v)).toBeCloseTo(50_000, 3)
  })
  it('formats for operators', () => {
    expect(fmtDist(842)).toBe('842 m'); expect(fmtDist(3421)).toBe('3.42 km'); expect(fmtDist(42_150)).toBe('42.1 km'); expect(fmtDist(397_600)).toBe('398 km')
    expect(fmtBearing(7.2)).toBe('007°'); expect(fmtBearing(359.7)).toBe('000°')
  })
})
