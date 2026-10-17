/** Geodesy for the map tools: great-circle distance and bearing on a sphere (mean Earth radius), good to ~0.5 %
 * against the ellipsoid, which is plenty for a planning measure. Pure functions, no map dependency. */
export type LngLat = [number, number]

export const EARTH_R = 6_371_008.8
const RAD = Math.PI / 180

export function distanceM(a: LngLat, b: LngLat): number {
  const dLat = (b[1] - a[1]) * RAD, dLng = (b[0] - a[0]) * RAD
  const h = Math.sin(dLat / 2) ** 2 + Math.cos(a[1] * RAD) * Math.cos(b[1] * RAD) * Math.sin(dLng / 2) ** 2
  return 2 * EARTH_R * Math.asin(Math.min(1, Math.sqrt(h)))
}

/** Initial true bearing from a to b, degrees 0..360. */
export function bearingDeg(a: LngLat, b: LngLat): number {
  const p1 = a[1] * RAD, p2 = b[1] * RAD, dl = (b[0] - a[0]) * RAD
  const y = Math.sin(dl) * Math.cos(p2), x = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (Math.atan2(y, x) / RAD + 360) % 360
}

/** Point at a distance along a true bearing (great circle). */
export function destination(p: LngLat, bearing: number, dist: number): LngLat {
  const d = dist / EARTH_R, t = bearing * RAD, p1 = p[1] * RAD, l1 = p[0] * RAD
  const p2 = Math.asin(Math.sin(p1) * Math.cos(d) + Math.cos(p1) * Math.sin(d) * Math.cos(t))
  const l2 = l1 + Math.atan2(Math.sin(t) * Math.sin(d) * Math.cos(p1), Math.cos(d) - Math.sin(p1) * Math.sin(p2))
  return [((l2 / RAD + 540) % 360) - 180, p2 / RAD]
}

export function pathLengthM(pts: LngLat[]): number {
  let s = 0
  for (let i = 1; i < pts.length; i++) s += distanceM(pts[i - 1], pts[i])
  return s
}

/** Great-circle vertices between a and b (so long lines on the Mercator map follow the measured path). */
export function greatCircle(a: LngLat, b: LngLat, stepM = 10_000): LngLat[] {
  const d = distanceM(a, b)
  const n = Math.min(64, Math.max(1, Math.ceil(d / stepM)))
  if (n === 1) return [a, b]
  const brg = bearingDeg(a, b)
  const out: LngLat[] = [a]
  for (let i = 1; i < n; i++) out.push(destination(a, brg, (d * i) / n))
  out.push(b)
  return out
}

/** Geodesic circle (true radius on the ground), closed ring. */
export function geoCircle(c: LngLat, radiusM: number, steps = 96): LngLat[] {
  const out: LngLat[] = []
  for (let i = 0; i <= steps; i++) out.push(destination(c, (i / steps) * 360, radiusM))
  return out
}

export function fmtDist(m: number): string {
  if (m < 1000) return `${Math.round(m)} m`
  if (m < 10_000) return `${(m / 1000).toFixed(2)} km`
  if (m < 100_000) return `${(m / 1000).toFixed(1)} km`
  return `${Math.round(m / 1000)} km`
}
export const fmtNm = (m: number) => `${(m / 1852).toFixed(m < 18_520 ? 2 : 1)} NM`
export const fmtBearing = (deg: number) => `${String(Math.round(deg) % 360).padStart(3, '0')}°`
export const fmtLngLat = (p: LngLat) => `${Math.abs(p[1]).toFixed(4)}° ${p[1] >= 0 ? 'N' : 'S'} ${Math.abs(p[0]).toFixed(4)}° ${p[0] >= 0 ? 'E' : 'W'}`
