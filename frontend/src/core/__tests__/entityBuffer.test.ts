import { describe, expect, it } from 'vitest'
import { EntityBuffer, MAX_EXTRAPOLATION_S, wrapHeadingDelta } from '../entityBuffer'

const tick = (atS: number, rows: [string, number, number, number | null, number | null, number | null, 'normal'][]) => ({ atS, atTime: '', worldRevision: 1, rows })

describe('EntityBuffer', () => {
  it('interpolates position and wraps heading through north', () => {
    const b = new EntityBuffer()
    b.ingest(tick(10, [['u', 17.0, 59.0, null, 350, 10, 'normal']]))
    b.ingest(tick(11, [['u', 17.1, 59.1, null, 10, 10, 'normal']]))
    const p = b.poseAt('u', 10.5)!
    expect(p.lng).toBeCloseTo(17.05, 6)
    expect(p.lat).toBeCloseTo(59.05, 6)
    expect(p.heading).toBeCloseTo(0, 6)
    expect(p.stale).toBe(false)
  })
  it('ignores out-of-order samples and never overwrites newer data', () => {
    const b = new EntityBuffer()
    b.ingest(tick(20, [['u', 1, 1, null, 0, 0, 'normal']]))
    b.ingest(tick(19, [['u', 9, 9, null, 0, 0, 'normal']]))
    expect(b.poseAt('u', 20)!.lng).toBe(1)
  })
  it('dead-reckons only briefly, then freezes and flags stale', () => {
    const b = new EntityBuffer()
    b.ingest(tick(0, [['u', 17.0, 59.0, null, 90, 100, 'normal']]))
    const soon = b.poseAt('u', 1)!
    expect(soon.lng).toBeGreaterThan(17.0)
    expect(soon.stale).toBe(false)
    const late = b.poseAt('u', MAX_EXTRAPOLATION_S + 10)!
    const capped = b.poseAt('u', MAX_EXTRAPOLATION_S)!
    expect(late.lng).toBeCloseTo(capped.lng, 9)
    expect(late.stale).toBe(true)
  })
  it('wraps heading deltas to the shortest rotation', () => {
    expect(wrapHeadingDelta(350, 10)).toBe(20)
    expect(wrapHeadingDelta(10, 350)).toBe(-20)
    expect(wrapHeadingDelta(0, 180)).toBe(180)
  })
})
