/** Per-entity sample ring with bounded interpolation and extrapolation. Positions are only ever derived from
 * server samples; after MAX_EXTRAPOLATION_S without a sample the entity freezes and is marked stale. */
import type { Condition, KinematicsTick } from '../contracts/types'

export interface Sample { t: number; lng: number; lat: number; alt: number | null; heading: number | null; speed: number | null }
export interface Pose { lng: number; lat: number; alt: number | null; heading: number; speed: number; stale: boolean; condition: Condition }

const MAX_SAMPLES = 8
export const MAX_EXTRAPOLATION_S = 3

export function wrapHeadingDelta(from: number, to: number): number {
  const d = ((to - from + 180) % 360 + 360) % 360 - 180
  return d === -180 ? 180 : d
}

export class EntityBuffer {
  private samples = new Map<string, Sample[]>()
  private conditions = new Map<string, Condition>()
  lastTickAtS = 0
  lastTickWall = 0
  speed = 1

  ingest(tick: KinematicsTick) {
    this.lastTickAtS = tick.atS
    this.lastTickWall = performance.now()
    for (const [id, lng, lat, alt, heading, speed, condition] of tick.rows) {
      const ring = this.samples.get(id) ?? []
      if (ring.length && ring[ring.length - 1].t >= tick.atS) continue // out-of-order or duplicate: never overwrite newer data
      ring.push({ t: tick.atS, lng, lat, alt, heading, speed })
      if (ring.length > MAX_SAMPLES) ring.shift()
      this.samples.set(id, ring)
      this.conditions.set(id, condition)
    }
  }

  reset() { this.samples.clear(); this.conditions.clear() }

  /** Estimated scenario time now, from the last tick plus elapsed wall time (buffered by delay). */
  renderTime(delayS = 1.0): number {
    if (!this.lastTickWall) return 0
    return this.lastTickAtS + ((performance.now() - this.lastTickWall) / 1000) * this.speed - delayS
  }

  ids(): string[] { return [...this.samples.keys()] }

  poseAt(id: string, t: number): Pose | null {
    const ring = this.samples.get(id)
    if (!ring || !ring.length) return null
    const condition = this.conditions.get(id) ?? 'unknown'
    let i = ring.length - 1
    while (i > 0 && ring[i].t > t) i--
    const a = ring[i]
    const b = ring[i + 1]
    if (b && b.t > a.t) {
      const f = Math.min(1, Math.max(0, (t - a.t) / (b.t - a.t)))
      const ha = a.heading ?? b.heading ?? 0
      const hb = b.heading ?? ha
      return { lng: a.lng + (b.lng - a.lng) * f, lat: a.lat + (b.lat - a.lat) * f, alt: a.alt === null ? null : a.alt + ((b.alt ?? a.alt) - a.alt) * f,
        heading: (ha + wrapHeadingDelta(ha, hb) * f + 360) % 360, speed: a.speed ?? 0, stale: false, condition }
    }
    // Beyond the newest sample: short dead reckoning, then freeze.
    const last = ring[ring.length - 1]
    const dt = Math.min(Math.max(0, t - last.t), MAX_EXTRAPOLATION_S)
    const stale = t - last.t > MAX_EXTRAPOLATION_S
    if (!last.speed || last.heading === null || dt <= 0) return { lng: last.lng, lat: last.lat, alt: last.alt, heading: last.heading ?? 0, speed: last.speed ?? 0, stale, condition }
    const d = last.speed * dt
    const rad = (last.heading * Math.PI) / 180
    const dLat = (d * Math.cos(rad)) / 111_320
    const dLng = (d * Math.sin(rad)) / (111_320 * Math.cos((last.lat * Math.PI) / 180))
    return { lng: last.lng + dLng, lat: last.lat + dLat, alt: last.alt, heading: last.heading, speed: last.speed, stale, condition }
  }
}
