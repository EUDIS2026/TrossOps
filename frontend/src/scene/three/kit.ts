/** Procedural modelling kit: every TrossOps 3D model is generated in code from these primitives (no third-party assets).
 * Frame: metres, +X starboard, +Y forward (nose), +Z up. All output geometry is non-indexed with
 * `position`, `normal` and `color` (Float32 RGB 0..1) so it merges into one BufferGeometry per model. */
import { BoxGeometry, BufferGeometry, CylinderGeometry, ExtrudeGeometry, Float32BufferAttribute, IcosahedronGeometry, Matrix4, Euler, Quaternion, Shape, Vector2, Vector3 } from 'three'
import { mergeGeometries } from 'three/examples/jsm/utils/BufferGeometryUtils.js'

export type RGB = readonly [number, number, number]
export type V2 = readonly [number, number]
export type V3 = readonly [number, number, number]
export type Axis = 'x' | 'y' | 'z'
export type ColorFn = (band: number, seg: number) => RGB

export const grey = (v: number): RGB => [v, v, v]

/** Material palette. Neutral greys carry the shape (the renderer multiplies by an affiliation tint); a few saturated accents survive tinting. */
export const COL = {
  white: grey(0.93), light: grey(0.85), hull: grey(0.75), paint: grey(0.7), mid: grey(0.62), deck: grey(0.55),
  metal: grey(0.5), dark: grey(0.38), darker: grey(0.26), glass: grey(0.12), tyre: grey(0.1), track: grey(0.14), hub: grey(0.42),
  concrete: grey(0.74), earth: grey(0.5),
  navRed: [0.9, 0.12, 0.1] as RGB, navGreen: [0.1, 0.8, 0.3] as RGB, tail: [0.8, 0.1, 0.08] as RGB, amber: [1.0, 0.65, 0.1] as RGB,
  policeBlue: [0.08, 0.22, 0.78] as RGB, hiVisYellow: [0.95, 0.92, 0.12] as RGB, hiVisGreen: [0.2, 0.75, 0.25] as RGB,
  lightBlue: [0.2, 0.45, 1.0] as RGB, cgYellow: [0.98, 0.8, 0.1] as RGB, cgBlue: [0.12, 0.3, 0.7] as RGB,
} as const

/** Deterministic hash in [0,1). */
export function hash(a: number, b: number, seed = 0): number {
  let h = (Math.imul(a | 0, 374761393) + Math.imul(b | 0, 668265263) + Math.imul(seed | 0, 2246822519)) | 0
  h = Math.imul(h ^ (h >>> 13), 1274126177)
  h ^= h >>> 16
  return (h >>> 0) / 4294967296
}

/** Subtle three-tone grey splinter camouflage (Swedish M90-like pattern rendered as grey variation). */
export function camo(seed: number, base = 0.68, spread = 0.12): ColorFn {
  return (i, j) => { const r = hash(i, j, seed); return grey(r < 0.4 ? base : r < 0.75 ? base - spread : base + spread * 0.6) }
}

// ---- low-level geometry helpers ------------------------------------------------------------------

function stripToCore(geo: BufferGeometry): BufferGeometry {
  let g = geo.index ? geo.toNonIndexed() : geo
  if (g === geo) g = geo.clone()
  for (const name of Object.keys(g.attributes)) if (name !== 'position' && name !== 'normal' && name !== 'color') g.deleteAttribute(name)
  g.clearGroups()
  g.morphAttributes = {}
  if (!g.getAttribute('normal')) g.computeVertexNormals()
  return g
}

/** Make the mesh outward-facing: flip winding if the signed volume is negative, then make every triangle's normals agree with its winding. */
function orient(g: BufferGeometry) {
  const p = g.getAttribute('position').array as Float32Array
  const nArr = g.getAttribute('normal').array as Float32Array
  const cArr = g.getAttribute('color')?.array as Float32Array | undefined
  const tris = p.length / 9
  let cx = 0, cy = 0, cz = 0
  for (let i = 0; i < p.length; i += 3) { cx += p[i]; cy += p[i + 1]; cz += p[i + 2] }
  const nv = p.length / 3 || 1
  cx /= nv; cy /= nv; cz /= nv
  let vol = 0, absVol = 0
  for (let t = 0; t < tris; t++) {
    const o = t * 9
    const ax = p[o] - cx, ay = p[o + 1] - cy, az = p[o + 2] - cz
    const bx = p[o + 3] - cx, by = p[o + 4] - cy, bz = p[o + 5] - cz
    const qx = p[o + 6] - cx, qy = p[o + 7] - cy, qz = p[o + 8] - cz
    const v = ax * (by * qz - bz * qy) - ay * (bx * qz - bz * qx) + az * (bx * qy - by * qx)
    vol += v; absVol += Math.abs(v)
  }
  const swap = (arr: Float32Array, o: number) => { for (let k = 0; k < 3; k++) { const tmp = arr[o + 3 + k]; arr[o + 3 + k] = arr[o + 6 + k]; arr[o + 6 + k] = tmp } }
  if (absVol > 0 && vol < -0.05 * absVol) {
    for (let t = 0; t < tris; t++) { swap(p, t * 9); swap(nArr, t * 9); if (cArr) swap(cArr, t * 9) }
  }
  const a = new Vector3(), b = new Vector3(), c = new Vector3()
  for (let t = 0; t < tris; t++) {
    const o = t * 9
    a.set(p[o], p[o + 1], p[o + 2]); b.set(p[o + 3], p[o + 4], p[o + 5]); c.set(p[o + 6], p[o + 7], p[o + 8])
    b.sub(a); c.sub(a); b.cross(c)
    const dot = b.x * (nArr[o] + nArr[o + 3] + nArr[o + 6]) + b.y * (nArr[o + 1] + nArr[o + 4] + nArr[o + 7]) + b.z * (nArr[o + 2] + nArr[o + 5] + nArr[o + 8])
    if (dot < 0) for (let k = 0; k < 9; k++) nArr[o + k] = -nArr[o + k]
  }
  g.getAttribute('position').needsUpdate = true
}

function paint(g: BufferGeometry, color: RGB) {
  const n = g.getAttribute('position').count
  const arr = new Float32Array(n * 3)
  for (let i = 0; i < n; i++) { arr[i * 3] = color[0]; arr[i * 3 + 1] = color[1]; arr[i * 3 + 2] = color[2] }
  g.setAttribute('color', new Float32BufferAttribute(arr, 3))
}

export function matrix(t: V3 = [0, 0, 0], r: V3 = [0, 0, 0], s: V3 = [1, 1, 1]): Matrix4 {
  return new Matrix4().compose(new Vector3(...t), new Quaternion().setFromEuler(new Euler(r[0], r[1], r[2], 'ZYX')), new Vector3(...s))
}

// ---- lofting -------------------------------------------------------------------------------------

export interface LoftOpts {
  color: RGB | ColorFn
  smooth?: boolean
  capStart?: boolean
  capEnd?: boolean
  startColor?: RGB
  endColor?: RGB
}

/** Skin a sequence of rings (equal point counts, consistent order) into a solid. Band i spans ring i→i+1, segment j spans point j→j+1. */
export function loft(rings: V3[][], o: LoftOpts): BufferGeometry {
  const n = rings[0].length
  const pos: number[] = []
  const idx: number[] = []
  const triCol: RGB[] = []
  const colAt: ColorFn = typeof o.color === 'function' ? o.color : () => o.color as RGB
  for (const r of rings) for (const p of r) pos.push(p[0], p[1], p[2])
  for (let i = 0; i < rings.length - 1; i++) {
    for (let j = 0; j < n; j++) {
      const a = i * n + j, b = i * n + ((j + 1) % n), c = (i + 1) * n + ((j + 1) % n), d = (i + 1) * n + j
      const col = colAt(i, j)
      idx.push(a, b, c, a, c, d)
      triCol.push(col, col)
    }
  }
  const cap = (ring: V3[], col: RGB, flip: boolean) => {
    const base = pos.length / 3
    let cx = 0, cy = 0, cz = 0
    for (const p of ring) { pos.push(p[0], p[1], p[2]); cx += p[0]; cy += p[1]; cz += p[2] }
    pos.push(cx / n, cy / n, cz / n)
    for (let j = 0; j < n; j++) {
      if (flip) idx.push(base + n, base + ((j + 1) % n), base + j)
      else idx.push(base + n, base + j, base + ((j + 1) % n))
      triCol.push(col)
    }
  }
  const fallback = typeof o.color === 'function' ? o.color(0, 0) : o.color
  if (o.capStart) cap(rings[0], o.startColor ?? fallback, true)
  if (o.capEnd) cap(rings[rings.length - 1], o.endColor ?? fallback, false)
  let g = new BufferGeometry()
  g.setAttribute('position', new Float32BufferAttribute(pos, 3))
  g.setIndex(idx)
  if (o.smooth) { g.computeVertexNormals(); g = g.toNonIndexed() } else { g = g.toNonIndexed(); g.computeVertexNormals() }
  const cols = new Float32Array(triCol.length * 9)
  triCol.forEach((c, t) => { for (let k = 0; k < 3; k++) cols.set(c, t * 9 + k * 3) })
  g.setAttribute('color', new Float32BufferAttribute(cols, 3))
  return g
}

/** Body station: centre (x, y, z), half-width w, half-height h, superellipse exponent p (2 = ellipse, 4+ = rounded box). */
export interface Sta { y: number; w: number; h: number; z: number; x?: number; p?: number }

/** Ring of a superellipse in the x-z plane at station y; point 0 is at +x, counter-clockwise towards +z. */
export function superRing(s: Sta, n: number): V3[] {
  const p = s.p ?? 2
  const out: V3[] = []
  for (let k = 0; k < n; k++) {
    const th = (k / n) * Math.PI * 2
    const c = Math.cos(th), sn = Math.sin(th)
    out.push([(s.x ?? 0) + s.w * Math.sign(c) * Math.abs(c) ** (2 / p), s.y, s.z + s.h * Math.sign(sn) * Math.abs(sn) ** (2 / p)])
  }
  return out
}

/** Centre angle of segment j of an n-ring (0 = +x side, π/2 = top). */
export const segAngle = (j: number, n: number) => ((j + 0.5) / n) * Math.PI * 2

/** Ring from a list of (x, z) points at station y. */
export const ringXZ = (y: number, pts: readonly V2[]): V3[] => pts.map(([x, z]) => [x, y, z] as V3)
/** Ring from a list of (x, y) points at height z. */
export const ringXY = (z: number, pts: readonly V2[]): V3[] => pts.map(([x, y]) => [x, y, z] as V3)

/** Mirror a list of right-hand (x ≥ 0) (x, z) points into a closed symmetric ring: right side bottom→top, then left side top→bottom. */
export function symRing(right: readonly V2[]): V2[] {
  const left = [...right].reverse().map(([x, z]) => [-x, z] as V2)
  return [...right, ...left]
}

// ---- wings and fins ------------------------------------------------------------------------------

/** Wing station: span position (x for wings, z for fins), leading-edge y, chord c, max thickness t, and the other offset (z for wings, x for fins). */
export interface WSta { s: number; y: number; c: number; t: number; o: number }
const AIRFOIL: V2[] = [[0, 0], [0.06, 0.62], [0.25, 1], [0.6, 0.72], [1, 0], [0.6, -0.5], [0.25, -0.72], [0.06, -0.45]]

export function wing(st: WSta[], color: RGB | ColorFn, opts: { vertical?: boolean; side?: 1 | -1 } = {}): BufferGeometry {
  const side = opts.side ?? 1
  const rings = st.map(w => AIRFOIL.map(([u, v]) => (opts.vertical
    ? [w.o + (v * w.t) / 2, w.y - u * w.c, w.s] as V3
    : [side * w.s, w.y - u * w.c, w.o + (v * w.t) / 2] as V3)))
  return loft(rings, { color, smooth: true, capStart: true, capEnd: true })
}

/** Flat-sided plate from a planform polygon (x, y) with thickness, centred on z. */
export function plate(pts: readonly V2[], z: number, t: number): BufferGeometry { return extrude(pts, 'z', z - t / 2, z + t / 2) }

// ---- extrusions ----------------------------------------------------------------------------------

/** Extrude a 2D polygon along an axis. 'x': points are (y, z); 'y': points are (x, z); 'z': points are (x, y). */
export function extrude(pts: readonly V2[], axis: Axis, a0: number, a1: number, holes: readonly (readonly V2[])[] = []): BufferGeometry {
  const shape = new Shape(pts.map(p => new Vector2(p[0], p[1])))
  for (const h of holes) shape.holes.push(new Shape(h.map(p => new Vector2(p[0], p[1]))))
  const g = new ExtrudeGeometry(shape, { depth: a1 - a0, bevelEnabled: false, curveSegments: 6 })
  const m = new Matrix4()
  if (axis === 'z') m.set(1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, a0, 0, 0, 0, 1)
  else if (axis === 'x') m.set(0, 0, 1, a0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 0, 1)
  else m.set(1, 0, 0, 0, 0, 0, 1, a0, 0, 1, 0, 0, 0, 0, 0, 1)
  g.applyMatrix4(m)
  return g
}

// ---- kit -----------------------------------------------------------------------------------------

export class Kit {
  private geos: BufferGeometry[] = []

  /** Add a geometry. Keeps an existing colour attribute when `color` is omitted. */
  add(geo: BufferGeometry, color?: RGB, m?: Matrix4): this {
    const g = stripToCore(geo)
    if (m) g.applyMatrix4(m)
    if (color || !g.getAttribute('color')) paint(g, color ?? COL.hull)
    orient(g)
    this.geos.push(g)
    return this
  }

  box(color: RGB, size: V3, at: V3, rot?: V3): this {
    return this.add(new BoxGeometry(size[0], size[1], size[2]), color, matrix(at, rot))
  }

  /** Cylinder along an axis centred at `at`; rTop is the radius at the +axis end. */
  cyl(color: RGB, r: number, len: number, axis: Axis, at: V3, seg = 10, rTop = r, rot?: V3): this {
    const g = new CylinderGeometry(rTop, r, len, seg, 1)
    if (axis === 'z') g.rotateX(Math.PI / 2)
    else if (axis === 'x') g.rotateZ(-Math.PI / 2)
    return this.add(g, color, matrix(at, rot))
  }

  /** Sphere/ellipsoid (faceted icosphere when detail is low — good for geodesic radomes). */
  ball(color: RGB, r: number, at: V3, scale: V3 = [1, 1, 1], detail = 1): this {
    return this.add(new IcosahedronGeometry(r, detail), color, matrix(at, [0, 0, 0], scale))
  }

  loft(rings: V3[][], o: LoftOpts): this { return this.add(loft(rings, o)) }

  /** Smooth body of revolution-like solid through superellipse stations. */
  body(st: Sta[], n: number, color: RGB | ColorFn, o: Partial<LoftOpts> = {}): this {
    return this.add(loft(st.map(s => superRing(s, n)), { smooth: true, capStart: true, capEnd: true, ...o, color }))
  }

  wing(st: WSta[], color: RGB | ColorFn, opts: { vertical?: boolean; mirror?: boolean } = {}): this {
    this.add(wing(st, color, { vertical: opts.vertical, side: 1 }))
    if (opts.mirror) this.add(opts.vertical ? wing(st.map(w => ({ ...w, o: -w.o })), color, { vertical: true }) : wing(st, color, { side: -1 }))
    return this
  }

  extrude(color: RGB, pts: readonly V2[], axis: Axis, a0: number, a1: number, holes: readonly (readonly V2[])[] = []): this {
    return this.add(extrude(pts, axis, a0, a1, holes), color)
  }

  /** Road wheel / tyre with a lighter hub on both faces. Axis x. */
  wheel(x: number, y: number, r: number, w: number, o: { seg?: number; hub?: RGB; tyre?: RGB; hubR?: number; z?: number } = {}): this {
    const seg = o.seg ?? 10
    const z = o.z ?? r
    this.cyl(o.tyre ?? COL.tyre, r, w, 'x', [x, y, z], seg)
    return this.cyl(o.hub ?? COL.hub, r * (o.hubR ?? 0.55), w + 0.04, 'x', [x, y, z], Math.max(6, seg - 2))
  }

  /** Rotor/propeller blades around `axis` through `at`. */
  rotor(color: RGB, blades: number, radius: number, chord: number, at: V3, axis: Axis, o: { thick?: number; hubR?: number; pitch?: number; phase?: number; root?: number; hubLen?: number } = {}): this {
    const t = o.thick ?? 0.08
    const root = o.root ?? 0.25
    for (let b = 0; b < blades; b++) {
      const g = new BoxGeometry(radius - root, chord, t)
      g.translate((radius + root) / 2, 0, 0)
      g.rotateX(o.pitch ?? 0.12)
      g.rotateZ((o.phase ?? 0) + (b / blades) * Math.PI * 2)
      this.add(orientAxis(g, axis, at), color)
    }
    const hub = new CylinderGeometry(o.hubR ?? radius * 0.07, o.hubR ?? radius * 0.07, o.hubLen ?? t * 3, 8)
    hub.rotateX(Math.PI / 2)
    return this.add(orientAxis(hub, axis, at), COL.dark)
  }

  /** Square-section member between two points (struts, gear legs, lattice members). */
  strut(color: RGB, a: V3, b: V3, w: number, d = w): this {
    const dir = new Vector3(b[0] - a[0], b[1] - a[1], b[2] - a[2])
    const len = dir.length()
    const q = new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), dir.normalize())
    const m = new Matrix4().compose(new Vector3((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2), q, new Vector3(1, 1, 1))
    return this.add(new BoxGeometry(w, len, d), color, m)
  }

  /** Round member between two points. */
  rod(color: RGB, a: V3, b: V3, r: number, seg = 6, rEnd = r): this {
    const dir = new Vector3(b[0] - a[0], b[1] - a[1], b[2] - a[2])
    const len = dir.length()
    const q = new Quaternion().setFromUnitVectors(new Vector3(0, 1, 0), dir.normalize())
    const m = new Matrix4().compose(new Vector3((a[0] + b[0]) / 2, (a[1] + b[1]) / 2, (a[2] + b[2]) / 2), q, new Vector3(1, 1, 1))
    return this.add(new CylinderGeometry(rEnd, r, len, seg, 1), color, m)
  }

  /** Faceted solid lofted vertically through scaled copies of a plan polygon (turrets, masts, superstructures). */
  stack(color: RGB | ColorFn, plan: readonly V2[], levels: readonly { z: number; s?: number; sx?: number; sy?: number; dy?: number }[], center: V2 = [0, 0]): this {
    const rings = levels.map(l => plan.map(([x, y]) => [
      center[0] + (x - center[0]) * (l.sx ?? l.s ?? 1),
      center[1] + (y - center[1]) * (l.sy ?? l.s ?? 1) + (l.dy ?? 0),
      l.z,
    ] as V3))
    return this.loft(rings, { color, capStart: true, capEnd: true })
  }

  /** Merge everything into one non-indexed geometry with bounding volumes. */
  build(): BufferGeometry {
    const merged = this.geos.length === 1 ? this.geos[0] : mergeGeometries(this.geos, false)
    if (!merged) throw new Error('mergeGeometries failed')
    merged.computeBoundingBox()
    merged.computeBoundingSphere()
    return merged
  }

  get triangles(): number { return this.geos.reduce((s, g) => s + g.getAttribute('position').count / 3, 0) }
}

/** Build a moving part in model space. */
export function part(build: (k: Kit) => void, pivot: V3, axis: Axis, rpm: number): { geometry: BufferGeometry; pivot: [number, number, number]; axis: Axis; rpm: number } {
  const k = new Kit()
  build(k)
  return { geometry: k.build(), pivot: [pivot[0], pivot[1], pivot[2]], axis, rpm }
}

/** Rotate geometry built around +z so that its axis points along `axis`, then translate to `at`. */
function orientAxis(g: BufferGeometry, axis: Axis, at: V3): BufferGeometry {
  if (axis === 'y') g.rotateX(-Math.PI / 2)
  else if (axis === 'x') g.rotateY(Math.PI / 2)
  g.translate(at[0], at[1], at[2])
  return g
}

/** Linear interpolation helper. */
export const lerp = (a: number, b: number, t: number) => a + (b - a) * t
