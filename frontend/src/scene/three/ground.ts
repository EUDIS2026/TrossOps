/** Ground vehicles. Front along +Y, ground contact on z = 0. */
import { BoxGeometry } from 'three'
import { COL, Kit, camo, grey, part, matrix, ringXZ, symRing, type ColorFn, type RGB, type V2, type V3 } from './kit'
import type { BuiltParts, ModelKey } from './models'

// ---- tracked running gear -----------------------------------------------------------------------

interface TrackO { xIn: number; xOut: number; y0: number; y1: number; h: number; r: number; n: number; wheel?: RGB }
function tracks(k: Kit, o: TrackO) {
  const w = o.xOut - o.xIn, xc = (o.xIn + o.xOut) / 2
  const pts: V2[] = [[o.y0 + o.r * 1.1, 0], [o.y1 - o.r * 1.1, 0], [o.y1 + 0.05, o.h * 0.55], [o.y1 - o.r * 0.35, o.h], [o.y0 + o.r * 0.3, o.h], [o.y0 - 0.05, o.h * 0.55]]
  for (const s of [1, -1]) {
    k.extrude(COL.track, pts, 'x', s > 0 ? o.xIn : -o.xOut, s > 0 ? o.xOut : -o.xIn)
    for (let i = 0; i < o.n; i++) {
      const y = o.y0 + o.r * 1.15 + ((o.y1 - o.y0 - o.r * 2.3) * i) / (o.n - 1)
      k.wheel(s * xc, y, o.r, w + 0.05, { seg: 10, tyre: COL.darker, hub: o.wheel ?? grey(0.5), hubR: 0.72 })
    }
    k.cyl(COL.dark, o.h * 0.3, w + 0.07, 'x', [s * xc, o.y1 - o.r * 0.25, o.h * 0.62], 8)
    k.cyl(COL.dark, o.h * 0.3, w + 0.07, 'x', [s * xc, o.y0 + o.r * 0.25, o.h * 0.6], 8)
  }
}

/** Tracked hull ring: lower hull (wb) between the tracks, sponsons (ws at zs, wt at zt) over them. Segments 0–3 right side + deck, 4–6 left, 7 belly. */
const tHull = (y: number, zb: number, zs: number, zt: number, wb: number, ws: number, wt: number): V3[] => ringXZ(y, symRing([[wb, zb], [wb, zs], [ws, zs], [wt, zt]]))

// ---- MBT (Leopard 2 / Strv 122 class) ------------------------------------------------------------

function mbt(): BuiltParts {
  const k = new Kit()
  const cam = camo(11, 0.66, 0.12)
  const H = (y: number, zb: number, zt: number, zs = 1.0) => tHull(y, zb, zs, zt, 1.12, 1.8, 1.72)
  k.loft([H(-3.86, 0.62, 1.62), H(-3.72, 0.45, 1.72), H(2.75, 0.45, 1.72), H(3.35, 0.45, 1.38), H(3.86, 1.0, 1.14)], { color: cam, capStart: true, capEnd: true })
  tracks(k, { xIn: 1.15, xOut: 1.78, y0: -3.62, y1: 3.58, h: 0.95, r: 0.34, n: 7 })
  for (const s of [1, -1]) {
    k.box(grey(0.62), [0.07, 5.1, 0.5], [1.86 * s, -1.05, 0.77])
    k.box(grey(0.66), [0.16, 2.1, 0.62], [1.88 * s, 2.55, 0.72])
    k.box(COL.dark, [0.6, 0.06, 0.4], [1.48 * s, 3.66, 0.82]) // mudflaps
    k.box(COL.light, [0.18, 0.06, 0.12], [1.45 * s, 3.8, 1.25])
    k.box(COL.dark, [0.6, 0.08, 0.25], [1.2 * s, -3.86, 1.35]) // exhaust grilles
  }
  // engine deck grilles, driver hatch
  for (const y of [-2.2, -3.1]) k.box(COL.dark, [2.6, 0.55, 0.03], [0, y, 1.73])
  k.box(grey(0.55), [0.55, 0.65, 0.06], [-0.65, 2.55, 1.66], [-0.5, 0, 0])
  // turret: wedge-armoured front, flat sides, long bustle
  const ty = -0.15
  const plan: V2[] = [[-1.55, -2.95], [1.55, -2.95], [1.78, -2.3], [1.78, 0.5], [1.25, 1.95], [0.45, 2.85], [-0.45, 2.85], [-1.25, 1.95], [-1.78, 0.5], [-1.78, -2.3]].map(([x, y]) => [x, y + ty] as V2)
  k.stack(camo(23, 0.68, 0.12), plan, [{ z: 1.72, s: 0.92 }, { z: 1.84, s: 1 }, { z: 2.5, s: 0.98 }, { z: 2.62, s: 0.9 }], [0, -0.3])
  // gun: mantlet, sleeved tube, bore evacuator, muzzle
  k.box(grey(0.6), [0.8, 0.5, 0.6], [0, 2.85, 2.15])
  k.cyl(grey(0.6), 0.11, 3.1, 'y', [0, 4.6, 2.15], 10)
  k.cyl(grey(0.64), 0.135, 0.9, 'y', [0, 3.55, 2.15], 10)
  k.cyl(grey(0.64), 0.17, 0.55, 'y', [0, 4.35, 2.15], 10)
  k.cyl(grey(0.64), 0.13, 0.9, 'y', [0, 5.1, 2.15], 10)
  k.cyl(grey(0.55), 0.125, 0.18, 'y', [0, 6.05, 2.15], 10)
  // roof: commander's panoramic sight, gunner's sight, hatches, MG, smoke dischargers, bustle basket
  k.cyl(grey(0.55), 0.2, 0.32, 'z', [-0.75, -0.4, 2.78], 10)
  k.box(grey(0.5), [0.36, 0.42, 0.24], [-0.75, -0.4, 3.0])
  k.box(COL.glass, [0.28, 0.04, 0.12], [-0.75, -0.18, 3.0])
  k.box(grey(0.58), [0.6, 0.7, 0.28], [0.95, 1.45, 2.72])
  k.box(COL.glass, [0.45, 0.04, 0.16], [0.95, 1.81, 2.74])
  k.cyl(grey(0.56), 0.36, 0.08, 'z', [0.65, -0.75, 2.65], 10)
  k.cyl(grey(0.56), 0.36, 0.08, 'z', [-0.7, -1.3, 2.65], 10)
  k.box(COL.dark, [0.08, 1.2, 0.08], [0.65, -0.2, 2.85])
  for (const s of [1, -1]) for (let i = 0; i < 4; i++) k.cyl(COL.dark, 0.06, 0.32, 'y', [s * (1.7 + 0.02 * i), -0.6 - i * 0.16, 2.48 + (i % 2) * 0.1], 6, 0.06, [0.5, 0, 0])
  k.box(grey(0.5), [2.9, 0.35, 0.45], [0, -3.22, 2.2])
  return { geometry: k.build(), parts: [] }
}

// ---- tracked IFV (CV90 class) --------------------------------------------------------------------

function ifv(): BuiltParts {
  const k = new Kit()
  const cam = camo(31, 0.66, 0.12)
  const H = (y: number, zb: number, zt: number) => tHull(y, zb, 0.95, zt, 0.95, 1.52, 1.38)
  k.loft([H(-3.28, 0.55, 1.9), H(1.55, 0.45, 1.9), H(2.6, 0.45, 1.52), H(3.27, 0.85, 1.05)], { color: cam, capStart: true, capEnd: true })
  tracks(k, { xIn: 0.97, xOut: 1.5, y0: -3.15, y1: 3.05, h: 0.9, r: 0.3, n: 7 })
  for (const s of [1, -1]) {
    k.box(grey(0.6), [0.06, 5.6, 0.3], [1.54 * s, -0.25, 0.86])
    k.box(COL.light, [0.16, 0.06, 0.1], [1.2 * s, 3.08, 1.12])
    k.box(grey(0.58), [0.42, 0.9, 0.42], [1.25 * s, -2.75, 2.1]) // rear stowage bins
  }
  k.box(grey(0.6), [1.05, 0.06, 1.15], [0, -3.3, 1.25]) // rear door
  k.box(COL.dark, [0.75, 0.9, 0.03], [0.85, 1.9, 1.86], [-0.33, 0, 0]) // engine grille
  k.box(grey(0.56), [0.5, 0.5, 0.06], [-0.75, 2.25, 1.75], [-0.33, 0, 0])
  // angular turret
  const ty = -0.15
  const plan: V2[] = [[-1.1, -1.65], [1.1, -1.65], [1.3, -0.9], [1.3, 0.5], [0.75, 1.45], [-0.75, 1.45], [-1.3, 0.5], [-1.3, -0.9]].map(([x, y]) => [x, y + ty] as V2)
  k.stack(camo(37, 0.68, 0.12), plan, [{ z: 1.9, s: 0.95 }, { z: 2.0, s: 1 }, { z: 2.52, sx: 0.84, sy: 0.92 }, { z: 2.6, sx: 0.76, sy: 0.84 }], [0, ty])
  // 40 mm autocannon with perforated jacket and flash hider
  k.box(grey(0.58), [0.55, 0.45, 0.45], [0, 1.45, 2.25])
  k.cyl(grey(0.55), 0.075, 2.3, 'y', [0, 2.75, 2.25], 8)
  k.cyl(grey(0.6), 0.11, 1.0, 'y', [0, 2.1, 2.25], 8)
  k.cyl(grey(0.5), 0.1, 0.32, 'y', [0, 3.82, 2.25], 8)
  // sights, hatches, smoke dischargers
  k.cyl(grey(0.55), 0.18, 0.4, 'z', [0.55, -0.9, 2.78], 8)
  k.box(grey(0.5), [0.32, 0.36, 0.22], [0.55, -0.9, 3.0])
  k.box(grey(0.58), [0.42, 0.55, 0.22], [-0.65, 0.65, 2.68])
  k.cyl(grey(0.56), 0.3, 0.07, 'z', [-0.5, -0.85, 2.63], 10)
  for (const s of [1, -1]) for (let i = 0; i < 3; i++) k.cyl(COL.dark, 0.055, 0.28, 'y', [s * (1.0 + i * 0.12), 1.0, 2.38 + i * 0.03], 6, 0.055, [0.6, 0, 0])
  return { geometry: k.build(), parts: [] }
}

// ---- 8x8 wheeled APC (Patria AMV class) ----------------------------------------------------------

function apcWheeled(): BuiltParts {
  const k = new Kit()
  const cam = camo(43, 0.66, 0.12)
  // V-shaped belly, side sponsons over the wheels, inward-sloped upper sides
  const R = (y: number, zk: number, z1: number, z2: number, zt: number, sc = 1) => ringXZ(y, symRing([[0.55 * sc, zk], [1.05 * sc, z1], [1.38 * sc, z2], [1.18 * sc, zt]]))
  k.loft([
    R(-3.85, 0.62, 0.85, 1.35, 2.05, 0.97), R(-3.7, 0.5, 0.78, 1.35, 2.12), R(2.2, 0.5, 0.78, 1.35, 2.12), R(3.25, 0.62, 0.85, 1.33, 1.7),
    R(3.85, 0.92, 1.0, 1.2, 1.32, 0.86),
  ], { color: cam, capStart: true, capEnd: true })
  for (const y of [2.6, 1.15, -0.95, -2.4]) for (const s of [1, -1]) k.wheel(1.12 * s, y, 0.6, 0.5, { seg: 12, hubR: 0.5 })
  // remote weapon station
  k.box(grey(0.6), [0.8, 0.9, 0.3], [0.35, 0.2, 2.27])
  k.box(grey(0.56), [0.45, 0.55, 0.3], [0.35, 0.25, 2.55])
  k.cyl(COL.dark, 0.045, 1.6, 'y', [0.35, 1.25, 2.55], 6)
  k.box(grey(0.5), [0.22, 0.25, 0.25], [0.68, 0.45, 2.6])
  k.box(COL.glass, [0.16, 0.03, 0.12], [0.68, 0.58, 2.6])
  // hatches, periscopes, engine grille, rear door, lights, stowage, smoke dischargers
  k.cyl(grey(0.56), 0.3, 0.07, 'z', [-0.55, 2.3, 2.0], 10)
  k.box(COL.glass, [0.6, 0.05, 0.08], [-0.55, 2.7, 1.95], [-0.6, 0, 0])
  k.box(COL.dark, [0.8, 0.9, 0.03], [0.6, 2.75, 1.93], [-0.55, 0, 0])
  k.cyl(grey(0.56), 0.3, 0.07, 'z', [-0.4, -1.6, 2.14], 10)
  k.cyl(grey(0.56), 0.3, 0.07, 'z', [0.4, -2.5, 2.14], 10)
  k.box(grey(0.6), [1.2, 0.06, 1.2], [0, -3.87, 1.35])
  for (const s of [1, -1]) {
    k.box(COL.light, [0.2, 0.06, 0.12], [0.85 * s, 3.85, 1.25])
    k.box(grey(0.58), [0.12, 1.8, 0.4], [1.33 * s, 0.1, 1.65])
    for (let i = 0; i < 3; i++) k.cyl(COL.dark, 0.05, 0.25, 'y', [s * (1.0 + i * 0.1), 1.8, 2.15], 6, 0.05, [0.6, 0, 0])
  }
  k.cyl(COL.dark, 0.02, 0.6, 'z', [-1.0, -3.4, 2.4], 4)
  return { geometry: k.build(), parts: [] }
}

// ---- 6x6 truck-mounted 155 mm howitzer (Archer class) --------------------------------------------

function spgWheeled(): BuiltParts {
  const k = new Kit()
  const cam = camo(53, 0.66, 0.12)
  // armoured cab on the front unit
  const C = (y: number, zt: number, sc = 1, zb = 0.95) => ringXZ(y, symRing([[1.25 * sc, zb], [1.42 * sc, 1.85], [1.38 * sc, 2.35], [1.28 * sc, zt]]))
  const cabCol: ColorFn = (i, j) => {
    if (j === 3 && i === 2) return COL.glass // windscreen
    if ((j === 2 || j === 4) && i >= 1) return COL.glass // side windows
    return cam(i, j)
  }
  k.loft([C(3.75, 2.95), C(4.0, 3.05), C(5.65, 3.05), C(6.55, 2.55, 0.97), C(7.05, 2.1, 0.92, 1.0)], { color: cabCol, capStart: true, capEnd: true })
  k.box(COL.dark, [1.6, 0.05, 0.5], [0, 7.06, 1.45])
  k.box(grey(0.45), [2.5, 0.3, 0.3], [0, 7.0, 0.95])
  for (const s of [1, -1]) {
    k.box(COL.light, [0.25, 0.06, 0.14], [0.95 * s, 7.07, 1.85])
    k.box(grey(0.58), [0.7, 1.9, 0.08], [1.18 * s, 5.3, 1.7])
  }
  // articulation, rear chassis, wheels
  k.box(COL.dark, [0.9, 0.8, 0.7], [0, 3.35, 1.15])
  k.box(grey(0.45), [1.7, 10.2, 0.6], [0, -1.9, 1.2])
  for (const [y, s] of [[5.3, 1], [5.3, -1], [-2.2, 1], [-2.2, -1], [-4.05, 1], [-4.05, -1]] as const) k.wheel(1.12 * s, y, 0.8, 0.62, { seg: 12, hubR: 0.45 })
  for (const s of [1, -1]) k.box(grey(0.55), [0.75, 4.0, 0.08], [1.15 * s, -3.1, 1.72])
  // gun module: tall armoured box with sloped front
  const G = (y: number, zt: number) => ringXZ(y, symRing([[1.4, 1.5], [1.5, 2.45], [1.25, zt]]))
  k.loft([G(-0.85, 2.55), G(-1.65, 3.0), G(-6.95, 3.0), G(-7.05, 2.85)], { color: camo(59, 0.68, 0.12), capStart: true, capEnd: true })
  k.box(grey(0.6), [0.9, 2.2, 0.35], [0, -1.6, 3.15])
  // 155 mm L52 barrel in travel position over the cab, muzzle brake, travel lock
  k.cyl(grey(0.6), 0.2, 1.6, 'y', [0, -0.2, 3.18], 10)
  k.cyl(grey(0.6), 0.125, 6.6, 'y', [0, 3.3, 3.18], 10)
  k.box(grey(0.55), [0.42, 0.45, 0.32], [0, 6.75, 3.18])
  k.strut(grey(0.5), [0.5, 4.05, 3.02], [0, 4.05, 3.08], 0.1)
  k.strut(grey(0.5), [-0.5, 4.05, 3.02], [0, 4.05, 3.08], 0.1)
  // module details
  k.box(grey(0.58), [1.4, 0.06, 1.0], [0, -7.08, 2.1])
  for (const s of [1, -1]) k.box(grey(0.6), [0.06, 2.0, 0.6], [1.5 * s, -4.4, 2.05])
  k.box(COL.dark, [0.3, 0.3, 0.3], [-0.8, -6.3, 3.15])
  return { geometry: k.build(), parts: [] }
}

// ---- articulated tracked carrier (Bv 206 class) --------------------------------------------------

function bv(): BuiltParts {
  const k = new Kit()
  const body = grey(0.66)
  const R = (y: number, zt: number, zb = 0.62, sc = 1) => ringXZ(y, symRing([[0.95 * sc, zb], [0.95 * sc, 1.55], [0.82 * sc, zt]]))
  // segments: 0 lower right, 1 window right, 2 roof, 3 window left, 4 lower left, 5 belly
  k.loft([R(0.5, 2.25), R(2.0, 2.32), R(2.65, 1.62), R(3.45, 1.3, 0.75, 0.92)], { color: (i, j) => ((j === 2 && i === 1) || ((j === 1 || j === 3) && i <= 1) ? COL.glass : body), capStart: true, capEnd: true })
  k.loft([R(-3.45, 2.2, 0.66), R(-3.3, 2.32), R(-0.1, 2.32)], { color: (i, j) => ((j === 1 || j === 3) && i === 1 ? COL.glass : body), capStart: true, capEnd: true })
  k.box(COL.glass, [1.2, 0.05, 0.4], [0, -3.43, 1.85])
  k.box(COL.dark, [0.5, 0.7, 0.4], [0, 0.2, 0.75])
  for (const [y0, y1] of [[0.55, 3.35], [-3.35, -0.15]] as const) tracks(k, { xIn: 0.3, xOut: 0.93, y0, y1, h: 0.7, r: 0.22, n: 5, wheel: grey(0.4) })
  k.box(COL.light, [1.1, 0.06, 0.1], [0, 3.42, 1.35])
  k.box(grey(0.55), [1.4, 2.4, 0.1], [0, -1.75, 2.38])
  return { geometry: k.build(), parts: [] }
}

// ---- trucks --------------------------------------------------------------------------------------

interface TruckO { mil: boolean; cab?: RGB; front?: number; rear?: number[]; r?: number; back?: number }
/** Cab-over 6x6 chassis. Returns nothing; the rear body is added by the variant. */
function truckBase(k: Kit, o: TruckO) {
  const cab = o.cab ?? (o.mil ? grey(0.64) : grey(0.85))
  const r = o.r ?? 0.56
  const back = o.back ?? -4.15
  const C = (y: number, zt: number, sc = 1) => ringXZ(y, symRing([[1.2 * sc, 1.05], [1.25 * sc, 2.0], [1.2 * sc, 2.9], [1.05 * sc, zt]]))
  // segments: 0 lower right, 1 window right, 2 roof edge, 3 roof, 4 roof edge, 5 window left, 6 lower left, 7 floor
  k.loft([C(2.35, 3.05), C(3.0, 3.05), C(3.95, 3.05), C(4.25, 2.98, 0.97)], { color: (i, j) => ((j === 1 || j === 5) && i >= 1 ? COL.glass : cab), capStart: true, capEnd: true })
  k.box(COL.glass, [2.15, 0.05, 0.85], [0, 4.26, 2.45])
  k.box(COL.dark, [1.6, 0.05, 0.5], [0, 4.27, 1.45])
  k.box(o.mil ? grey(0.4) : grey(0.5), [2.45, 0.28, 0.32], [0, 4.3, 0.85])
  for (const s of [1, -1]) {
    k.box(COL.light, [0.28, 0.05, 0.16], [0.9 * s, 4.32, 0.92])
    k.box(COL.dark, [0.06, 0.12, 0.3], [1.3 * s, 4.05, 2.4])
  }
  k.box(COL.darker, [1.0, 4.25 - back, 0.3], [0, (4.25 + back) / 2, 1.0])
  for (const y of [o.front ?? 3.3, ...(o.rear ?? [-1.35, -2.75])]) for (const s of [1, -1]) k.wheel(1.02 * s, y, r, 0.5, { seg: 10, hubR: 0.5 })
  for (const s of [1, -1]) {
    k.cyl(grey(0.55), 0.28, 1.0, 'y', [1.0 * s, 1.5, 0.95], 8)
    k.box(COL.tail, [0.2, 0.05, 0.1], [1.05 * s, back - 0.02, 1.0])
  }
}

function truck(): BuiltParts {
  const k = new Kit()
  truckBase(k, { mil: true })
  k.box(grey(0.55), [2.45, 6.3, 0.25], [0, -1.0, 1.32])
  const T = (y: number) => ringXZ(y, symRing([[1.22, 1.45], [1.22, 2.75], [1.05, 3.15], [0.6, 3.28]]))
  k.loft([T(2.15), T(0.6), T(-0.9), T(-2.5), T(-4.15)], { color: (i) => (i % 2 ? grey(0.6) : grey(0.64)), capStart: true, capEnd: true })
  return { geometry: k.build(), parts: [] }
}

function fuelTruck(): BuiltParts {
  const k = new Kit()
  truckBase(k, { mil: true })
  k.body([
    { y: 2.05, w: 0.85, h: 0.6, z: 2.15, p: 2.4 }, { y: 1.9, w: 1.15, h: 0.8, z: 2.15, p: 2.4 }, { y: -3.9, w: 1.15, h: 0.8, z: 2.15, p: 2.4 },
    { y: -4.05, w: 0.85, h: 0.6, z: 2.15, p: 2.4 },
  ], 14, grey(0.72))
  for (const y of [1.0, -0.6, -2.2]) k.cyl(grey(0.6), 0.26, 0.16, 'z', [0, y, 2.98], 10)
  k.box(grey(0.5), [0.5, 5.6, 0.04], [0.45, -1.0, 2.98])
  k.box(grey(0.55), [2.3, 0.5, 0.9], [0, -4.35, 1.5])
  k.box(COL.amber, [0.4, 0.04, 0.3], [0, 4.29, 1.95])
  k.box(COL.amber, [0.4, 0.04, 0.3], [0, -4.62, 1.75])
  return { geometry: k.build(), parts: [] }
}

function recovery(): BuiltParts {
  const k = new Kit()
  truckBase(k, { mil: true, back: -4.4 })
  for (const s of [1, -1]) k.box(grey(0.6), [0.8, 2.6, 1.15], [0.82 * s, 0.75, 1.75])
  k.box(grey(0.5), [2.4, 5.0, 0.22], [0, -1.8, 1.3])
  k.cyl(grey(0.58), 0.45, 0.9, 'z', [0, -0.8, 1.85], 10)
  k.strut(grey(0.62), [0, -0.8, 2.3], [0, -4.0, 3.15], 0.5, 0.55)
  k.strut(grey(0.55), [0, -4.0, 3.15], [0, -4.3, 2.4], 0.2)
  k.box(grey(0.52), [2.3, 0.4, 0.9], [0, -4.25, 1.15])
  k.box(grey(0.45), [0.5, 0.9, 0.25], [0, -4.6, 0.75])
  k.cyl(COL.dark, 0.3, 1.2, 'x', [0, -2.2, 1.75], 10)
  for (const s of [1, -1]) k.box(COL.amber, [0.25, 0.25, 0.15], [0.7 * s, 3.2, 3.12])
  return { geometry: k.build(), parts: [] }
}

function shelterTruck(k: Kit, len: number, y: number, h = 2.1) {
  truckBase(k, { mil: true })
  k.box(grey(0.66), [2.4, len, h], [0, y, 1.35 + h / 2])
  k.box(grey(0.6), [2.42, len - 0.3, 0.08], [0, y, 1.35 + h - 0.15])
  k.box(grey(0.55), [0.9, 0.05, 1.7], [0, y - len / 2 - 0.02, 1.35 + 0.95])
}

function commandPost(): BuiltParts {
  const k = new Kit()
  shelterTruck(k, 5.6, -1.35)
  k.cyl(grey(0.55), 0.12, 2.6, 'z', [0.75, -3.7, 4.75], 8, 0.08)
  k.box(grey(0.55), [1.4, 0.08, 0.08], [0.75, -3.7, 5.9])
  for (const s of [1, -1]) k.cyl(COL.dark, 0.025, 0.9, 'z', [0.75 + 0.7 * s, -3.7, 5.5], 4)
  k.cyl(grey(0.6), 0.45, 0.08, 'x', [0.75, -3.45, 5.55], 12, 0.45, [0, 0, 0.4])
  k.cyl(grey(0.58), 0.5, 0.5, 'z', [-0.6, -0.2, 3.7], 10, 0.15)
  for (const [x, y] of [[-1.0, -3.8], [-1.0, 1.0]] as const) k.cyl(COL.dark, 0.02, 1.4, 'z', [x, y, 4.15], 4)
  k.box(grey(0.6), [1.0, 1.0, 0.6], [0.55, 1.4, 3.75])
  return { geometry: k.build(), parts: [] }
}

function radarVehicle(): BuiltParts {
  const k = new Kit()
  shelterTruck(k, 4.4, -0.55, 1.9)
  k.box(grey(0.6), [2.2, 1.6, 0.9], [0, -3.4, 1.8])
  k.cyl(grey(0.55), 0.3, 0.5, 'z', [0, -3.4, 2.5], 10)
  k.cyl(grey(0.5), 0.18, 1.0, 'z', [0, -3.4, 3.2], 8)
  const pv: V3 = [0, -3.4, 3.7]
  const ant = part(pk => {
    pk.add(new BoxGeometry(2.7, 0.3, 1.25), grey(0.82), matrix([0, -3.4, 4.25], [-0.3, 0, 0]))
    pk.box(grey(0.6), [2.5, 0.06, 1.05], [0, -3.25, 4.28], [-0.3, 0, 0])
    pk.box(grey(0.5), [0.5, 0.5, 0.3], [0, -3.55, 3.75])
  }, pv, 'z', 30)
  return { geometry: k.build(), parts: [ant] }
}

function adLauncher(): BuiltParts {
  const k = new Kit()
  truckBase(k, { mil: true })
  k.box(grey(0.5), [2.4, 6.2, 0.3], [0, -1.0, 1.4])
  k.box(grey(0.55), [2.4, 0.8, 0.8], [0, 1.6, 1.9])
  // elevated 2×4 canister launcher on a rear pivot
  const pv: V3 = [0, -3.8, 1.75]
  const m = matrix(pv, [0.62, 0, 0])
  for (const x of [-0.81, -0.27, 0.27, 0.81]) for (const z of [0.3, 0.84]) {
    k.add(new BoxGeometry(0.5, 3.9, 0.5).translate(x, 1.95, z), grey(0.72), m)
    k.add(new BoxGeometry(0.42, 0.04, 0.42).translate(x, 3.91, z), COL.dark, m)
  }
  k.add(new BoxGeometry(2.3, 0.3, 1.2).translate(0, 0.2, 0.55), grey(0.55), m)
  k.add(new BoxGeometry(2.3, 0.3, 1.2).translate(0, 3.0, 0.55), grey(0.55), m)
  k.strut(grey(0.5), [0, -1.0, 1.55], [0, -2.0, 2.6], 0.2)
  for (const s of [1, -1]) k.strut(grey(0.5), [1.15 * s, -4.0, 0.9], [1.25 * s, -4.1, 0.15], 0.18)
  return { geometry: k.build(), parts: [] }
}

function ambulance(): BuiltParts {
  const k = new Kit()
  const yel: RGB = [0.95, 0.88, 0.3]
  // van nose and cab
  const N = (y: number, zb: number, zt: number, w: number) => ringXZ(y, symRing([[w * 0.95, 0.42], [w, zb], [w * 0.97, zb + 0.08], [w * 0.88, zt]]))
  k.loft([N(3.3, 0.85, 0.95, 0.9), N(2.9, 1.05, 1.15, 1.0), N(2.25, 1.15, 1.3, 1.02), N(1.4, 1.2, 2.45, 1.02), N(1.2, 1.2, 2.5, 1.02)], {
    color: (i, j) => ((j === 2 || j === 4) && i === 3) ? COL.glass : (j === 3 && i === 2) ? COL.glass : (j === 1 || j === 5) && i === 3 ? COL.glass : yel, capStart: true, capEnd: true,
  })
  // box body with battenburg sides
  const ys = [1.2, 0.55, -0.1, -0.75, -1.4, -2.05, -2.7, -3.3]
  const B = (y: number) => ringXZ(y, symRing([[1.0, 0.55], [1.05, 0.95], [1.05, 1.35], [1.05, 1.75], [0.95, 2.8]]))
  k.loft(ys.map(B), {
    color: (i, j) => {
      const row = j === 1 || j === 7 ? 0 : j === 2 || j === 6 ? 1 : -1
      if (row < 0) return yel
      return (i + row) % 2 ? COL.hiVisGreen : yel
    }, capStart: true, capEnd: true,
  })
  for (const y of [2.3, -1.9]) for (const s of [1, -1]) k.wheel(0.86 * s, y, 0.38, 0.26, { seg: 10 })
  k.box(COL.lightBlue, [1.2, 0.25, 0.12], [0, 1.15, 2.86])
  k.box(COL.lightBlue, [0.3, 0.2, 0.12], [0.75, -3.2, 2.86])
  k.box(COL.lightBlue, [0.3, 0.2, 0.12], [-0.75, -3.2, 2.86])
  k.box(COL.dark, [0.9, 0.05, 0.3], [0, 3.31, 0.7])
  for (const s of [1, -1]) { k.box(COL.light, [0.3, 0.05, 0.12], [0.62 * s, 3.3, 0.92]); k.box(COL.tail, [0.1, 0.05, 0.5], [0.95 * s, -3.32, 1.0]) }
  k.box(COL.glass, [1.2, 0.04, 0.7], [0, -3.32, 1.95])
  return { geometry: k.build(), parts: [] }
}

// ---- armoured engineer vehicle (Kodiak class) ----------------------------------------------------

function engineer(): BuiltParts {
  const k = new Kit()
  const cam = camo(71, 0.66, 0.12)
  const H = (y: number, zb: number, zt: number) => tHull(y, zb, 1.0, zt, 1.12, 1.78, 1.72)
  k.loft([H(-3.8, 0.6, 1.65), H(-3.65, 0.45, 1.75), H(2.7, 0.45, 1.75), H(3.3, 0.45, 1.4), H(3.8, 1.0, 1.15)], { color: cam, capStart: true, capEnd: true })
  tracks(k, { xIn: 1.15, xOut: 1.78, y0: -3.55, y1: 3.5, h: 0.95, r: 0.34, n: 7 })
  for (const s of [1, -1]) k.box(grey(0.62), [0.07, 7.0, 0.45], [1.85 * s, -0.05, 0.78])
  // crew cab (front left) with vision blocks
  const cab: V2[] = [[-1.7, -0.6], [-0.2, -0.6], [-0.2, 2.2], [-0.6, 2.7], [-1.7, 2.7]]
  k.stack((_i, j) => (j === 2 || j === 3 ? grey(0.62) : grey(0.66)), cab, [{ z: 1.74 }, { z: 2.75, sx: 0.96, sy: 0.95 }], [-0.95, 1.05])
  k.box(COL.glass, [1.2, 0.05, 0.25], [-1.0, 2.67, 2.45], [-0.25, 0, 0])
  for (const s of [-1.7]) k.box(COL.glass, [0.05, 1.6, 0.22], [s, 1.2, 2.45])
  // engine deck, stowage
  k.box(COL.dark, [1.6, 1.4, 0.04], [0.6, -2.6, 1.77])
  k.box(grey(0.6), [1.2, 2.0, 0.7], [1.0, -1.0, 2.1])
  // dozer blade on push arms
  const bladeY = 4.2
  k.add(new BoxGeometry(4.0, 0.25, 1.15), grey(0.6), matrix([0, bladeY, 0.65], [0.25, 0, 0]))
  k.box(grey(0.5), [4.0, 0.1, 0.12], [0, bladeY + 0.18, 0.12])
  for (const s of [1, -1]) k.strut(grey(0.5), [1.45 * s, 3.4, 0.75], [1.45 * s, bladeY - 0.1, 0.65], 0.2)
  // excavator arm folded along the right side, bucket forward
  k.cyl(grey(0.55), 0.38, 0.5, 'z', [1.0, -2.6, 2.0], 10)
  k.strut(grey(0.64), [1.0, -2.5, 2.2], [1.05, 2.3, 2.95], 0.38, 0.5)
  k.strut(grey(0.6), [1.05, 2.3, 2.95], [1.05, 4.25, 2.0], 0.3, 0.4)
  k.strut(COL.dark, [0.85, -1.2, 2.2], [0.85, 1.4, 2.9], 0.12)
  k.add(new BoxGeometry(0.9, 0.6, 0.7), grey(0.5), matrix([1.05, 4.45, 1.55], [0.6, 0, 0]))
  return { geometry: k.build(), parts: [] }
}

// ---- cars and bus --------------------------------------------------------------------------------

interface CarSta { y: number; z0: number; z1: number; z2: number; zb: number; zr: number; w0: number; w1: number; wr: number }
/** Car body ring, segments: 0 floor, 1 sill R, 2 lower flank R, 3 upper flank R, 4 glass R, 5 roof/hood, 6 glass L, 7 upper flank L, 8 lower flank L, 9 sill L. */
const carRing = (s: CarSta): V3[] => ringXZ(s.y, [[-s.w0, s.z0], [s.w0, s.z0], [s.w1, s.z1], [s.w1, s.z2], [s.w1 * 0.97, s.zb], [s.wr, s.zr], [-s.wr, s.zr], [-s.w1 * 0.97, s.zb], [-s.w1, s.z2], [-s.w1, s.z1]])

function carBody(k: Kit, st: CarSta[], glassBands: number[], flank: (i: number, j: number, yMid: number) => RGB) {
  k.loft(st.map(carRing), {
    color: (i, j) => {
      if (j === 4 || j === 6) return COL.glass
      if (j === 5) return glassBands.includes(i) ? COL.glass : flank(i, j, (st[i].y + st[i + 1].y) / 2)
      return flank(i, j, (st[i].y + st[i + 1].y) / 2)
    }, capStart: true, capEnd: true,
  })
}

function carDetails(k: Kit, front: number, rear: number, wb: [number, number], halfW: number, tail = 0.42) {
  for (const y of wb) for (const s of [1, -1]) k.wheel(0.84 * s, y, 0.33, 0.24, { seg: 12, hub: grey(0.7), hubR: 0.62 })
  for (const s of [1, -1]) {
    k.box(COL.white, [0.34, 0.06, 0.1], [0.58 * s, front - 0.04, 0.7])
    k.box(COL.tail, [0.14, 0.06, tail], [(halfW - 0.1) * s, rear + 0.01, 0.86 + (tail - 0.42) / 2])
    k.box(COL.dark, [0.08, 0.14, 0.1], [(halfW + 0.04) * s, 0.85, 1.0])
  }
  k.box(COL.darker, [0.7, 0.05, 0.16], [0, front - 0.02, 0.52])
}

const estate: CarSta[] = [
  { y: 2.47, z0: 0.32, z1: 0.4, z2: 0.55, zb: 0.72, zr: 0.72, w0: 0.7, w1: 0.8, wr: 0.8 },
  { y: 2.3, z0: 0.25, z1: 0.33, z2: 0.55, zb: 0.82, zr: 0.82, w0: 0.82, w1: 0.92, wr: 0.9 },
  { y: 1.6, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.9, zr: 0.9, w0: 0.84, w1: 0.94, wr: 0.9 },
  { y: 0.95, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.96, zr: 0.96, w0: 0.84, w1: 0.94, wr: 0.86 },
  { y: 0.05, z0: 0.22, z1: 0.3, z2: 0.55, zb: 1.0, zr: 1.44, w0: 0.84, w1: 0.94, wr: 0.72 },
  { y: -0.55, z0: 0.22, z1: 0.3, z2: 0.55, zb: 1.0, zr: 1.47, w0: 0.84, w1: 0.94, wr: 0.72 },
  { y: -1.15, z0: 0.22, z1: 0.3, z2: 0.55, zb: 1.0, zr: 1.47, w0: 0.84, w1: 0.94, wr: 0.72 },
  { y: -1.75, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.99, zr: 1.45, w0: 0.84, w1: 0.94, wr: 0.71 },
  { y: -2.38, z0: 0.27, z1: 0.35, z2: 0.55, zb: 0.97, zr: 1.38, w0: 0.82, w1: 0.92, wr: 0.68 },
  { y: -2.47, z0: 0.34, z1: 0.4, z2: 0.55, zb: 0.94, zr: 0.94, w0: 0.78, w1: 0.88, wr: 0.78 },
]

function policeCar(): BuiltParts {
  const k = new Kit()
  const white = COL.white
  carBody(k, estate, [3, 8], (_i, j, y) => {
    const row = j === 2 || j === 8 ? 0 : j === 3 || j === 7 ? 1 : -1
    if (row < 0) return white
    const cell = Math.floor((y + 10) / 0.62)
    return (cell + row) % 2 ? COL.policeBlue : COL.hiVisYellow
  })
  carDetails(k, 2.47, -2.47, [1.45, -1.5], 0.94)
  // roof light bar, blue ends
  k.box(grey(0.3), [1.2, 0.28, 0.08], [0, -0.25, 1.52])
  for (const s of [1, -1]) k.box(COL.lightBlue, [0.4, 0.26, 0.1], [0.38 * s, -0.25, 1.58])
  return { geometry: k.build(), parts: [] }
}

function car(): BuiltParts {
  const k = new Kit()
  const c = grey(0.8)
  const sedan: CarSta[] = [
    { y: 2.3, z0: 0.32, z1: 0.4, z2: 0.55, zb: 0.7, zr: 0.7, w0: 0.7, w1: 0.8, wr: 0.8 },
    { y: 2.15, z0: 0.25, z1: 0.33, z2: 0.55, zb: 0.8, zr: 0.8, w0: 0.8, w1: 0.9, wr: 0.88 },
    { y: 1.45, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.88, zr: 0.88, w0: 0.82, w1: 0.92, wr: 0.88 },
    { y: 0.85, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.94, zr: 0.94, w0: 0.82, w1: 0.92, wr: 0.84 },
    { y: -0.05, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.98, zr: 1.42, w0: 0.82, w1: 0.92, wr: 0.7 },
    { y: -0.95, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.98, zr: 1.43, w0: 0.82, w1: 0.92, wr: 0.7 },
    { y: -1.55, z0: 0.22, z1: 0.3, z2: 0.55, zb: 0.98, zr: 1.3, w0: 0.82, w1: 0.92, wr: 0.68 },
    { y: -1.95, z0: 0.24, z1: 0.32, z2: 0.55, zb: 0.97, zr: 0.98, w0: 0.82, w1: 0.92, wr: 0.82 },
    { y: -2.3, z0: 0.32, z1: 0.4, z2: 0.55, zb: 0.92, zr: 0.92, w0: 0.78, w1: 0.88, wr: 0.8 },
  ]
  carBody(k, sedan, [3, 6], () => c)
  carDetails(k, 2.3, -2.3, [1.35, -1.4], 0.92, 0.16)
  return { geometry: k.build(), parts: [] }
}

function bus(): BuiltParts {
  const k = new Kit()
  const c = grey(0.86)
  const B = (y: number, sc = 1) => ringXZ(y, symRing([[1.2 * sc, 0.32], [1.27 * sc, 0.5], [1.27 * sc, 1.2], [1.27 * sc, 2.65], [1.24 * sc, 2.95], [1.1 * sc, 3.15]]))
  // segments: 0 chamfer R, 1 skirt R, 2 windows R, 3 header R, 4 roof edge R, 5 roof, 6..10 mirrored, 11 floor
  k.loft([B(-6.0, 0.98), B(-5.85), B(5.85), B(6.0, 0.98)], { color: (i, j) => ((j === 2 || j === 8) && i === 1 ? COL.glass : c), capStart: true, capEnd: true })
  k.box(COL.glass, [2.3, 0.05, 1.8], [0, 6.0, 1.95])
  k.box(COL.glass, [2.0, 0.05, 1.1], [0, -6.0, 2.15])
  k.box(COL.darker, [0.08, 1.2, 2.2], [1.28, 4.6, 1.3])
  k.box(COL.darker, [0.08, 1.2, 2.2], [1.28, -0.2, 1.3])
  for (const y of [3.9, -2.1]) for (const s of [1, -1]) k.wheel(1.0 * s, y, 0.5, 0.36, { seg: 12 })
  k.box(grey(0.6), [1.8, 2.6, 0.3], [0, -3.8, 3.3])
  for (const s of [1, -1]) { k.box(COL.white, [0.35, 0.05, 0.15], [0.9 * s, 6.02, 0.6]); k.box(COL.tail, [0.15, 0.05, 0.5], [1.1 * s, -6.02, 0.9]) }
  return { geometry: k.build(), parts: [] }
}

export const GROUND_BUILDERS: Record<Extract<ModelKey, 'mbt' | 'ifv' | 'apc_wheeled' | 'spg_wheeled' | 'bv' | 'truck' | 'fuel_truck' | 'recovery' | 'ambulance' | 'command_post' | 'radar_vehicle' | 'ad_launcher' | 'engineer' | 'police_car' | 'car' | 'bus'>, () => BuiltParts> = {
  mbt, ifv, apc_wheeled: apcWheeled, spg_wheeled: spgWheeled, bv, truck, fuel_truck: fuelTruck, recovery, ambulance, command_post: commandPost,
  radar_vehicle: radarVehicle, ad_launcher: adLauncher, engineer, police_car: policeCar, car, bus,
}
