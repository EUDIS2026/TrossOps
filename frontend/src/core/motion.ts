/** Motion model v2 — the client twin of `backend/app/motion.py`. Read that module's docstring for the definitions;
 * any change here must be mirrored there (the paired tests pin identical sample values). Evaluated at display rate
 * for every synthetic platform, so it avoids allocation in the hot path. */

export type Vertex = [number, number, number | null]
export interface MotionApi {
  kind: 'static' | 'path'
  pos?: Vertex; heading?: number
  routeId?: string; path?: Vertex[]; speeds?: number[]
  startS?: number; offsetS?: number; holdS?: number; mode?: 'loop' | 'pingpong' | 'once'; airborne?: boolean
  fuelStart?: number | null; fuelBurnPerKm?: number; trim?: [number, number]; endHeading?: number
}
export interface Pose { lng: number; lat: number; alt: number | null; heading: number; pitch: number; bank: number; speed: number; phase: Phase; fuel: number | null }
export type Phase = 'static' | 'waiting' | 'moving' | 'holding' | 'returning' | 'done'

const R = 6_371_008.8
const D2R = Math.PI / 180
const G = 9.81

export function haversine(aLng: number, aLat: number, bLng: number, bLat: number): number {
  const p1 = aLat * D2R, p2 = bLat * D2R, dp = p2 - p1, dl = (bLng - aLng) * D2R
  const h = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2
  return 2 * R * Math.asin(Math.sqrt(Math.min(1, h)))
}
export function bearing(aLng: number, aLat: number, bLng: number, bLat: number): number {
  const p1 = aLat * D2R, p2 = bLat * D2R, dl = (bLng - aLng) * D2R
  const x = Math.sin(dl) * Math.cos(p2), y = Math.cos(p1) * Math.sin(p2) - Math.sin(p1) * Math.cos(p2) * Math.cos(dl)
  return (Math.atan2(x, y) / D2R + 360) % 360
}
export function wrapDelta(from: number, to: number): number { const d = ((to - from + 180) % 360 + 360) % 360 - 180; return d === -180 ? 180 : d }

export class Path {
  readonly lng: Float64Array; readonly lat: Float64Array; readonly alt: (number | null)[]
  readonly speeds: Float64Array; readonly cumD: Float64Array; readonly cumT: Float64Array; readonly segLen: Float64Array
  constructor(pts: Vertex[], speeds: number[]) {
    const n = pts.length
    if (!n) throw new Error('empty path')
    const sp = speeds.length === 1 && n > 2 ? new Array(n - 1).fill(speeds[0]) : speeds
    this.lng = new Float64Array(n); this.lat = new Float64Array(n); this.alt = new Array(n)
    pts.forEach((p, i) => { this.lng[i] = p[0]; this.lat[i] = p[1]; this.alt[i] = p[2] })
    this.speeds = Float64Array.from(sp)
    this.cumD = new Float64Array(n); this.cumT = new Float64Array(n); this.segLen = new Float64Array(Math.max(0, n - 1))
    let d = 0, t = 0
    for (let i = 0; i < n - 1; i++) {
      let seg = haversine(this.lng[i], this.lat[i], this.lng[i + 1], this.lat[i + 1])
      const a0 = this.alt[i], a1 = this.alt[i + 1]
      if (a0 !== null && a1 !== null) seg = Math.hypot(seg, a1 - a0)
      this.segLen[i] = seg
      d += seg; t += seg / Math.max(this.speeds[i], 0.01)
      this.cumD[i + 1] = d; this.cumT[i + 1] = t
    }
  }
  get n() { return this.lng.length }
  get length() { return this.cumD[this.n - 1] }
  get duration() { return this.cumT[this.n - 1] }

  private static search(arr: Float64Array, v: number): number {
    let lo = 0, hi = arr.length - 1
    while (lo < hi) { const mid = (lo + hi + 1) >> 1; if (arr[mid] <= v) lo = mid; else hi = mid - 1 }
    return lo
  }

  /** Writes [lng, lat, alt|NaN] for distance d into out; returns the segment index. */
  at(d: number, out: Float64Array): number {
    const n = this.n
    if (n === 1 || d <= 0) { out[0] = this.lng[0]; out[1] = this.lat[0]; out[2] = this.alt[0] ?? NaN; return 0 }
    if (d >= this.length) { out[0] = this.lng[n - 1]; out[1] = this.lat[n - 1]; out[2] = this.alt[n - 1] ?? NaN; return n - 2 }
    const i = Math.min(Math.max(Path.search(this.cumD, d), 0), n - 2)
    const f = (d - this.cumD[i]) / (this.segLen[i] || 1)
    out[0] = this.lng[i] + (this.lng[i + 1] - this.lng[i]) * f
    out[1] = this.lat[i] + (this.lat[i + 1] - this.lat[i]) * f
    const a = this.alt[i], b = this.alt[i + 1]
    out[2] = a === null && b === null ? NaN : a === null ? (b as number) * f : b === null ? a * (1 - f) : a + (b - a) * f
    return i
  }

  timeAtDistance(d: number): number {
    const n = this.n
    if (n === 1 || d <= 0) return 0
    if (d >= this.length) return this.duration
    const i = Math.min(Math.max(Path.search(this.cumD, d), 0), n - 2)
    return this.cumT[i] + (d - this.cumD[i]) / Math.max(this.speeds[i], 0.01)
  }

  /** [distance, speed] after t seconds of travel. */
  distanceAtTime(t: number): [number, number] {
    const n = this.n
    if (n === 1 || t <= 0) return [0, this.speeds[0] ?? 0]
    if (t >= this.duration) return [this.length, 0]
    const i = Math.min(Math.max(Path.search(this.cumT, t), 0), n - 2)
    return [this.cumD[i] + (t - this.cumT[i]) * this.speeds[i], this.speeds[i]]
  }
}

export interface Motion {
  kind: 'static' | 'path'
  pos: Vertex | null; heading: number
  path: Path | null; startS: number; offsetS: number; holdS: number; mode: 'loop' | 'pingpong' | 'once'; airborne: boolean
  fuelStart: number | null; fuelBurnPerKm: number; trim: [number, number]; endHeading: number | null
}

export function motionFromApi(m: MotionApi, routes: Map<string, Path>): Motion {
  let path: Path | null = null
  if (m.kind === 'path') path = m.routeId ? routes.get(m.routeId) ?? null : m.path && m.speeds ? new Path(m.path, m.speeds) : null
  return {
    kind: path ? 'path' : 'static', pos: m.pos ?? (path ? [path.lng[0], path.lat[0], path.alt[0]] : null), heading: m.heading ?? 0, path,
    startS: m.startS ?? 0, offsetS: m.offsetS ?? 0, holdS: m.holdS ?? 0, mode: m.mode ?? 'loop', airborne: !!m.airborne,
    fuelStart: m.fuelStart ?? null, fuelBurnPerKm: m.fuelBurnPerKm ?? 0, trim: m.trim ?? [0, 0], endHeading: m.endHeading ?? null,
  }
}

const tmpA = new Float64Array(3), tmpB = new Float64Array(3), tmpP = new Float64Array(3)

function phaseDistance(m: Motion, t: number): [number, number, number, Phase, number] {
  const p = m.path!
  const d0 = Math.min(Math.max(m.trim[0], 0), p.length)
  const d1 = Math.max(Math.min(p.length - m.trim[1], p.length), d0)
  const t0 = p.timeAtDistance(d0), t1 = p.timeAtDistance(d1)
  const run = t1 - t0
  const fwd = (tt: number): [number, number] => {
    if (tt >= run) return [d1, 0]
    const [d, v] = p.distanceAtTime(t0 + Math.max(tt, 0))
    return [Math.min(Math.max(d, d0), d1), v]
  }
  const tau = t - m.startS + m.offsetS
  if (tau < 0) return [d0, 0, 1, 'waiting', 0]
  if (m.mode === 'once') { const [d, v] = fwd(tau); return [d, v, 1, tau < run ? 'moving' : 'done', d - d0] }
  if (m.mode === 'pingpong') {
    const cycle = 2 * (run + m.holdS)
    const ph = cycle > 0 ? tau % cycle : 0
    if (ph < run) { const [d, v] = fwd(ph); return [d, v, 1, 'moving', d - d0] }
    if (ph < run + m.holdS) return [d1, 0, 1, 'holding', d1 - d0]
    const ph2 = ph - run - m.holdS
    if (ph2 < run) { const [d, v] = fwd(run - ph2); return [d, v, -1, 'returning', (d1 - d0) + (d1 - d)] }
    return [d0, 0, -1, 'holding', 2 * (d1 - d0)]
  }
  const cycle = run + m.holdS
  const ph = cycle > 0 ? tau % cycle : 0
  if (ph < run) { const [d, v] = fwd(ph); return [d, v, 1, 'moving', d - d0] }
  return [d1, 0, 1, 'holding', d1 - d0]
}

/** Pose at scenario time t. `out` is reused to avoid allocation when given. */
export function poseAt(m: Motion, t: number, out?: Pose): Pose {
  const o = out ?? { lng: 0, lat: 0, alt: null, heading: 0, pitch: 0, bank: 0, speed: 0, phase: 'static', fuel: null }
  if (m.kind === 'static' || !m.path) {
    const p = m.pos ?? [0, 0, null]
    o.lng = p[0]; o.lat = p[1]; o.alt = p[2]; o.heading = m.heading; o.pitch = 0; o.bank = 0; o.speed = 0; o.phase = 'static'; o.fuel = m.fuelStart
    return o
  }
  const p = m.path
  const [d, v, dir, phase, travelled] = phaseDistance(m, t)
  p.at(d, tmpP)
  const lng = tmpP[0], lat = tmpP[1], alt = Number.isNaN(tmpP[2]) ? null : tmpP[2]
  const w = Math.min(Math.max(2 * Math.max(v, 3), 6), 600)
  p.at(d - w * dir, tmpA); p.at(d + w * dir, tmpB)
  if (haversine(tmpA[0], tmpA[1], tmpB[0], tmpB[1]) < 0.5) {
    if (p.n > 1) {
      let i = 0
      while (i < p.n - 2 && p.cumD[i + 1] <= d) i++
      const [ia, ib] = dir < 0 ? [i + 1, i] : [i, i + 1]
      tmpA[0] = p.lng[ia]; tmpA[1] = p.lat[ia]; tmpA[2] = p.alt[ia] ?? NaN
      tmpB[0] = p.lng[ib]; tmpB[1] = p.lat[ib]; tmpB[2] = p.alt[ib] ?? NaN
    } else { tmpA.set(tmpP); tmpB.set(tmpP) }
  }
  let heading = haversine(tmpA[0], tmpA[1], tmpB[0], tmpB[1]) > 0.01 ? bearing(tmpA[0], tmpA[1], tmpB[0], tmpB[1]) : 0
  if (m.endHeading !== null && phase === 'holding' && dir > 0) heading = m.endHeading
  let pitch = 0, bank = 0
  if (m.airborne && alt !== null && v > 0) {
    if (!Number.isNaN(tmpA[2]) && !Number.isNaN(tmpB[2])) pitch = Math.atan2(tmpB[2] - tmpA[2], 2 * w) / D2R
    const h1 = haversine(tmpA[0], tmpA[1], lng, lat) > 0.01 ? bearing(tmpA[0], tmpA[1], lng, lat) : heading
    const h2 = haversine(lng, lat, tmpB[0], tmpB[1]) > 0.01 ? bearing(lng, lat, tmpB[0], tmpB[1]) : heading
    const rate = (wrapDelta(h1, h2) * D2R) / Math.max(w / v, 0.05)
    bank = Math.max(-65, Math.min(65, Math.atan((v * rate) / G) / D2R))
  }
  let fuel: number | null = null
  if (m.fuelStart !== null) fuel = phase !== 'holding' || m.mode === 'pingpong' ? Math.max(0, m.fuelStart - (m.fuelBurnPerKm * travelled) / 1000) : m.fuelStart
  o.lng = lng; o.lat = lat; o.alt = alt; o.heading = heading; o.pitch = pitch; o.bank = bank; o.speed = v; o.phase = phase; o.fuel = fuel
  return o
}
