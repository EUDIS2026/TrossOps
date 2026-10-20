import { describe, expect, it } from 'vitest'
import { Box3, Vector3 } from 'three'
import { MODEL_KEYS, MODEL_SPECS, buildModel, triangleBudget, type BuiltModel } from '../models'

function bounds(m: BuiltModel): Box3 {
  const box = new Box3()
  for (const g of [m.geometry, ...m.parts.map(p => p.geometry)]) { g.computeBoundingBox(); box.union(g.boundingBox!) }
  return box
}
const tris = (m: BuiltModel) => [m.geometry, ...m.parts.map(p => p.geometry)].reduce((s, g) => s + g.getAttribute('position').count / 3, 0)

describe('procedural model library', () => {
  it('covers every key with a spec', () => {
    expect(MODEL_KEYS.length).toBe(57)
    for (const k of MODEL_KEYS) expect(MODEL_SPECS[k].key).toBe(k)
  })

  for (const key of MODEL_KEYS) {
    it(`${key} builds within spec, budget and attribute contract`, () => {
      const m = buildModel(key)
      const size = bounds(m).getSize(new Vector3())
      const spec = m.spec
      expect(size.y / spec.lengthM, `${key} length ${size.y.toFixed(2)} vs ${spec.lengthM}`).toBeGreaterThan(0.8)
      expect(size.y / spec.lengthM, `${key} length ${size.y.toFixed(2)} vs ${spec.lengthM}`).toBeLessThan(1.2)
      expect(size.x / spec.widthM, `${key} width ${size.x.toFixed(2)} vs ${spec.widthM}`).toBeGreaterThan(0.8)
      expect(size.x / spec.widthM, `${key} width ${size.x.toFixed(2)} vs ${spec.widthM}`).toBeLessThan(1.2)
      expect(size.z / spec.heightM, `${key} height ${size.z.toFixed(2)} vs ${spec.heightM}`).toBeGreaterThan(0.8)
      expect(size.z / spec.heightM, `${key} height ${size.z.toFixed(2)} vs ${spec.heightM}`).toBeLessThan(1.2)
      expect(tris(m)).toBeLessThanOrEqual(triangleBudget(key))
      for (const g of [m.geometry, ...m.parts.map(p => p.geometry)]) {
        expect(g.index).toBeNull()
        const pos = g.getAttribute('position'), nor = g.getAttribute('normal'), col = g.getAttribute('color')
        expect(col).toBeDefined()
        expect(col.itemSize).toBe(3)
        expect(nor.count).toBe(pos.count)
        expect(col.count).toBe(pos.count)
        const arr = col.array as Float32Array
        for (let i = 0; i < arr.length; i++) expect(arr[i] >= 0 && arr[i] <= 1).toBe(true)
        const p = pos.array as Float32Array
        for (let i = 0; i < p.length; i++) if (!Number.isFinite(p[i])) throw new Error(`${key}: non-finite position`)
      }
      for (const part of m.parts) {
        expect(part.pivot.every(Number.isFinite)).toBe(true)
        expect(['x', 'y', 'z']).toContain(part.axis)
        expect(part.rpm).toBeGreaterThan(0)
      }
      // ground/waterline contact: nothing far below z = 0
      expect(bounds(m).min.z).toBeGreaterThan(-0.6)
    })
  }

  it('is outward-facing: stored normals agree with triangle winding', () => {
    for (const key of MODEL_KEYS) {
      const g = buildModel(key).geometry
      const p = g.getAttribute('position').array as Float32Array
      const n = g.getAttribute('normal').array as Float32Array
      let bad = 0, total = 0
      const a = new Vector3(), b = new Vector3(), c = new Vector3()
      for (let o = 0; o < p.length; o += 9) {
        a.set(p[o], p[o + 1], p[o + 2]); b.set(p[o + 3], p[o + 4], p[o + 5]).sub(a); c.set(p[o + 6], p[o + 7], p[o + 8]).sub(a)
        const f = b.cross(c)
        if (f.lengthSq() < 1e-12) continue
        total++
        if (f.x * (n[o] + n[o + 3] + n[o + 6]) + f.y * (n[o + 1] + n[o + 4] + n[o + 7]) + f.z * (n[o + 2] + n[o + 5] + n[o + 8]) < 0) bad++
      }
      expect(bad / total, key).toBeLessThan(0.01)
    }
  })

  it('is deterministic', () => {
    const a = buildModel('mbt').geometry.getAttribute('position').array as Float32Array
    const b = buildModel('mbt').geometry.getAttribute('position').array as Float32Array
    expect(a.length).toBe(b.length)
    expect(Array.from(a.slice(0, 300))).toEqual(Array.from(b.slice(0, 300)))
  })
})
