/** Vessels. Bow along +Y, waterline on z = 0 (hull drawn only slightly below it). */
import { BoxGeometry } from 'three'
import { COL, Kit, grey, hash, part, matrix, plate, type RGB, type V2, type V3 } from './kit'
import type { BuiltParts, ModelKey, MovingPart } from './models'

// ---- hull ----------------------------------------------------------------------------------------

interface HullO {
  L: number; B: number; fb: number; hull: RGB; deck: RGB
  bowRise?: number; rake?: number; transom?: number; entry?: number; draft?: number; boot?: number; bootCol?: RGB
  bowW?: number; flare?: number; sternRise?: number; stripe?: (u: number, j: number) => RGB | null
}
interface HullInfo { deckZ: (y: number) => number; halfBeam: (y: number) => number }

const smooth = (t: number) => { const c = Math.min(1, Math.max(0, t)); return c * c * (3 - 2 * c) }

/** Ship hull lofted from transom to stem. Ring: deck L/R, boot-top, waterline, keel. Segment 0 = deck. */
function hull(k: Kit, o: HullO): HullInfo {
  const { L, B } = o
  const entry = o.entry ?? 0.55, transom = o.transom ?? 0.8, rake = o.rake ?? L * 0.04, draft = o.draft ?? 0.4
  const boot = o.boot ?? Math.min(1.2, o.fb * 0.22), bowW = o.bowW ?? 0, flare = o.flare ?? 0.2
  const half = (u: number) => {
    if (u < 0.15) return (B / 2) * (transom + (1 - transom) * Math.sin((u / 0.15) * Math.PI / 2))
    if (u <= entry) return B / 2
    const t = (u - entry) / (1 - entry)
    return (B / 2) * (bowW + (1 - bowW) * Math.cos((t * Math.PI) / 2) ** 0.85)
  }
  const deckZ = (u: number) => o.fb + (o.bowRise ?? 0) * Math.max(0, (u - 0.55) / 0.45) ** 2 + (o.sternRise ?? 0) * Math.max(0, (0.12 - u) / 0.12)
  const us = [0, 0.03, 0.08, 0.15, 0.3, 0.45, 0.55, 0.65, 0.73, 0.8, 0.86, 0.91, 0.95, 0.98, 1]
  const rings = us.map(u => {
    const b = half(u), y = -L / 2 + u * L, zd = deckZ(u)
    const bowF = smooth((u - 0.7) / 0.3)
    const rk = rake * smooth((u - 0.82) / 0.18)
    const yAt = (z: number) => y - rk * (1 - z / zd)
    const bw = b * (1 - flare * bowF), bk = bw * (0.72 - 0.3 * bowF)
    const pts: [number, number][] = [[-b, zd], [b, zd], [bw, boot], [bw * 0.98, 0], [bk, -draft], [-bk, -draft], [-bw * 0.98, 0], [-bw, boot]]
    return pts.map(([x, z]) => [x, yAt(z), z] as V3)
  })
  const bootCol = o.bootCol ?? COL.darker
  k.loft(rings, {
    color: (i, j) => {
      if (j === 0) return o.deck
      const s = o.stripe?.((us[i] + us[i + 1]) / 2, j)
      if (s) return s
      if (j === 1 || j === 7) return o.hull
      return bootCol
    }, capStart: true, capEnd: bowW > 0, startColor: o.hull, endColor: o.hull,
  })
  const toU = (y: number) => Math.min(1, Math.max(0, (y + L / 2) / L))
  return { deckZ: y => deckZ(toU(y)), halfBeam: y => half(toU(y)) }
}

// ---- superstructure helpers ----------------------------------------------------------------------

interface HouseO { color?: RGB; win?: number[] | 'all' | 'none'; chamfer?: number; top?: RGB; winCol?: RGB }
/** Multi-deck block from y0 (aft) to y1 (fore), half-width w, with a window band on each deck. */
function house(k: Kit, w: number, y0: number, y1: number, z0: number, decks: number, deckH: number, o: HouseO = {}) {
  const c = o.chamfer ?? 0
  const plan: V2[] = c > 0
    ? [[-w, y0], [w, y0], [w, y1 - c], [w - c * 0.8, y1], [-w + c * 0.8, y1], [-w, y1 - c]]
    : [[-w, y0], [w, y0], [w, y1], [-w, y1]]
  const levels: { z: number }[] = []
  for (let d = 0; d < decks; d++) { const z = z0 + d * deckH; levels.push({ z }, { z: z + 0.4 * deckH }, { z: z + 0.82 * deckH }) }
  levels.push({ z: z0 + decks * deckH })
  const col = o.color ?? COL.white
  const faces = o.win === 'none' ? [] : o.win === 'all' || !o.win ? plan.map((_, j) => j) : o.win
  k.stack((i, j) => (i % 3 === 1 && faces.includes(j) ? (o.winCol ?? COL.glass) : col), plan, levels)
  if (o.top) k.box(o.top, [w * 2 - 0.2, y1 - y0 - 0.2, 0.05], [0, (y0 + y1) / 2, z0 + decks * deckH + 0.02])
}

function funnel(k: Kit, y: number, z0: number, h: number, w: number, l: number, color: RGB = COL.white, x = 0) {
  const plan: V2[] = [[-w, -l], [w, -l], [w, l * 0.6], [w * 0.6, l], [-w * 0.6, l], [-w, l * 0.6]].map(([px, py]) => [px + x, py + y] as V2)
  k.stack((i) => (i === 2 ? COL.darker : color), plan, [{ z: z0 }, { z: z0 + h * 0.85, dy: -h * 0.12 }, { z: z0 + h * 0.86, dy: -h * 0.12 }, { z: z0 + h, dy: -h * 0.15 }], [x, y])
}

function mast(k: Kit, y: number, z0: number, h: number, color: RGB = COL.light, yard = 2.5) {
  k.cyl(color, 0.2, h, 'z', [0, y, z0 + h / 2], 6, 0.12)
  k.box(color, [yard * 2, 0.15, 0.15], [0, y, z0 + h * 0.72])
  k.box(color, [1.2, 0.8, 0.12], [0, y, z0 + h * 0.55])
}

function radarPart(y: number, z: number, w: number, rpm = 24): MovingPart {
  return part(pk => { pk.box(grey(0.5), [w, 0.35, 0.3], [0, y, z + 0.25]); pk.box(grey(0.4), [0.35, 0.35, 0.25], [0, y, z + 0.05]) }, [0, y, z], 'z', rpm)
}

function gun(k: Kit, y: number, z: number, s = 1, color: RGB = grey(0.7)) {
  k.stack(color, [[-1.1 * s, -1.2 * s], [1.1 * s, -1.2 * s], [1.0 * s, 0.6 * s], [0.5 * s, 1.3 * s], [-0.5 * s, 1.3 * s], [-1.0 * s, 0.6 * s]].map(([x, yy]) => [x, yy + y] as V2), [{ z }, { z: z + 1.1 * s, s: 0.8 }], [0, y])
  k.cyl(grey(0.6), 0.09 * s, 3.2 * s, 'y', [0, y + 2.6 * s, z + 0.55 * s], 6)
}

function crane(k: Kit, x: number, y: number, z: number, h: number, jib: number, dir: number, color: RGB = grey(0.75)) {
  k.cyl(color, 0.5, h, 'z', [x, y, z + h / 2], 8)
  k.box(color, [1.3, 1.6, 1.0], [x, y, z + h + 0.4])
  const a = Math.cos(dir), b = Math.sin(dir)
  k.strut(color, [x, y, z + h + 0.5], [x + jib * 0.85 * b, y + jib * 0.85 * a, z + h + jib * 0.5], 0.4, 0.5)
}

function boat(k: Kit, x: number, y: number, z: number, len: number, color: RGB = COL.amber) {
  k.body([{ x, y: y + len / 2, w: 0.05, h: 0.05, z }, { x, y: y + len * 0.3, w: len * 0.16, h: len * 0.1, z }, { x, y: y - len * 0.4, w: len * 0.17, h: len * 0.1, z }, { x, y: y - len / 2, w: len * 0.12, h: len * 0.08, z }], 8, color)
}

/** Slanted livery band on both hull sides, following the hull's half-beam. */
function hullStripe(k: Kit, h: HullInfo, y: number, w: number, slant: number, color: RGB, z0 = 0.5) {
  for (const s of [1, -1]) {
    const ring = (yy: number): V3[] => {
      const zt = h.deckZ(yy + slant) - 0.25
      const xb = s * (h.halfBeam(yy) + 0.03), xt = s * (h.halfBeam(yy + slant) + 0.03)
      return [[xb, yy, z0], [xb + s * 0.05, yy, z0], [xt + s * 0.05, yy + slant, zt], [xt, yy + slant, zt]]
    }
    k.loft([ring(y), ring(y + w)], { color, capStart: true, capEnd: true })
  }
}

// ---- naval ---------------------------------------------------------------------------------------

function corvette(): BuiltParts {
  const k = new Kit()
  const hullC = grey(0.7), deckC = grey(0.52), sup = grey(0.72)
  hull(k, { L: 72.6, B: 10.4, fb: 3.6, bowRise: 0.9, rake: 4.5, transom: 0.92, entry: 0.5, flare: 0.25, hull: hullC, deck: deckC })
  // faceted superstructure: sloped sides, glacis front with bridge window strip, aft slope
  const S = (y: number, zt: number, wt = 3.55, wb = 4.75): V3[] => [[wb, y, 3.6], [wt, y, zt], [-wt, y, zt], [-wb, y, 3.6]]
  k.loft([S(-12, 5.2, 3.3), S(-6, 7.4), S(11.5, 7.4), S(14.3, 7.05, 3.4, 4.6), S(15.2, 6.4, 3.45, 4.5), S(18.8, 4.35, 3.0, 4.2)], {
    color: (i, j) => (i === 3 && j === 1 ? COL.glass : sup), capStart: true, capEnd: true,
  })
  // integrated pyramidal mast
  k.stack(sup, [[-3.2, 0.5], [3.2, 0.5], [3.2, 9.5], [-3.2, 9.5]], [{ z: 7.35 }, { z: 11.6, sx: 0.55, sy: 0.52 }, { z: 12.9, sx: 0.3, sy: 0.28 }], [0, 5])
  k.cyl(grey(0.6), 0.12, 0.8, 'z', [0, 5, 13.3], 6)
  // stealth gun cupola (57 mm) with retracted barrel
  k.stack(sup, [[-1.55, 22.4], [1.55, 22.4], [1.75, 24.4], [0.85, 26.0], [-0.85, 26.0], [-1.75, 24.4]], [{ z: 3.9 }, { z: 5.15, sx: 0.72, sy: 0.8 }], [0, 24])
  k.cyl(grey(0.6), 0.1, 1.2, 'y', [0, 26.2, 4.55], 6)
  // helicopter deck marking, waterjets, hatches
  k.cyl(grey(0.66), 4.2, 0.03, 'z', [0, -25, 3.62], 16)
  k.cyl(deckC, 3.8, 0.04, 'z', [0, -25, 3.63], 16)
  for (const s of [1, -1]) k.box(COL.darker, [1.4, 0.06, 0.9], [2.6 * s, -36.32, 0.7])
  k.box(grey(0.45), [2.2, 2.2, 0.05], [0, 18.5 + 3.0, 3.85])
  return { geometry: k.build(), parts: [] }
}

function patrolShip(): BuiltParts {
  const k = new Kit()
  const hullC = grey(0.72), deckC = grey(0.52), sup = grey(0.76)
  const h = hull(k, { L: 50, B: 7.5, fb: 3.0, bowRise: 1.2, rake: 3.0, hull: hullC, deck: deckC })
  house(k, 3.1, -6, 9, h.deckZ(0), 1, 2.6, { color: sup, win: 'none' })
  house(k, 2.8, 2, 9.5, h.deckZ(0) + 2.6, 1, 2.4, { color: sup, chamfer: 1.0, win: [2, 3, 4], top: grey(0.6) })
  k.box(sup, [7.2, 1.6, 0.2], [0, 8.2, h.deckZ(0) + 4.3])
  mast(k, 4.0, h.deckZ(0) + 5.0, 6.5, sup)
  funnel(k, -3.0, h.deckZ(0) + 2.6, 2.2, 1.0, 1.4, sup)
  gun(k, 15.5, h.deckZ(15.5), 0.85)
  boat(k, 2.6, -9, h.deckZ(-9) + 0.5, 5.5, COL.darker)
  k.box(grey(0.55), [5.5, 10, 0.05], [0, -18, h.deckZ(-18) + 0.03])
  return { geometry: k.build(), parts: [radarPart(4.0, h.deckZ(0) + 11.5, 3.0)] }
}

function mcm(): BuiltParts {
  const k = new Kit()
  const hullC = grey(0.74), deckC = grey(0.55), sup = grey(0.78)
  const h = hull(k, { L: 47.5, B: 9.6, fb: 3.2, bowRise: 1.0, rake: 2.5, transom: 0.9, hull: hullC, deck: deckC })
  const z = h.deckZ(0)
  house(k, 4.0, -6, 12, z, 1, 2.6, { color: sup, win: 'none' })
  house(k, 3.4, 4, 11.5, z + 2.6, 1, 2.5, { color: sup, chamfer: 1.2, win: [2, 3, 4], top: grey(0.6) })
  // tripod mast
  const mz = z + 5.1
  for (const [x, y] of [[-1.6, 3.0], [1.6, 3.0], [0, 7.5]] as const) k.strut(sup, [x, y, mz], [0, 5.0, mz + 5.6], 0.25)
  k.box(sup, [5, 0.2, 0.2], [0, 5.0, mz + 4.6])
  funnel(k, -3.5, z + 2.6, 2.2, 1.1, 1.6, sup)
  gun(k, 16.5, h.deckZ(16.5), 0.7)
  // aft deck: A-frame and ROVs
  for (const s of [1, -1]) k.strut(grey(0.6), [3.6 * s, -20, z], [2.6 * s, -22.5, z + 4.2], 0.35)
  k.box(grey(0.6), [5.6, 0.4, 0.4], [0, -22.5, z + 4.2])
  for (const s of [1, -1]) k.box(COL.amber, [1.0, 2.6, 0.9], [2.0 * s, -15, z + 0.45])
  crane(k, -3.0, -9.0, z, 1.6, 6, Math.PI * 0.85)
  return { geometry: k.build(), parts: [radarPart(5.0, mz + 5.6, 2.8)] }
}

function submarine(): BuiltParts {
  const k = new Kit()
  const c = grey(0.45)
  const wl = -0.35, L = 60.4
  const rAt = (u: number) => {
    if (u > 0.9) return 3.1 * Math.sqrt(Math.max(0, 1 - ((u - 0.9) / 0.1) ** 2)) // rounded bow
    if (u > 0.35) return 3.1
    return 3.1 * (0.12 + 0.88 * Math.sin((u / 0.35) * Math.PI / 2)) // conical tail
  }
  const N = 12
  const us = [0, 0.04, 0.1, 0.18, 0.27, 0.35, 0.6, 0.9, 0.94, 0.97, 0.99, 1]
  const topAt = (u: number) => (u >= 0.35 ? 1.5 : 0.15 + 1.35 * Math.sin((u / 0.35) * Math.PI / 2))
  const rings = us.map(u => {
    const y = -L / 2 + u * L, r = rAt(u)
    const zc = u < 0.35 ? topAt(u) - r : -1.6
    const s0 = (wl - zc) / Math.max(r, 1e-3)
    if (s0 >= 0.999) return Array.from({ length: N + 2 }, () => [0, y, wl] as V3)
    const a0 = Math.asin(Math.max(-1, s0))
    const arc: V3[] = []
    for (let i = 0; i <= N; i++) { const a = a0 + ((Math.PI - 2 * a0) * i) / N; arc.push([r * Math.cos(a), y, zc + r * Math.sin(a)]) }
    arc.push([0, y, wl])
    return arc
  })
  k.loft(rings, { color: c, smooth: true, capStart: true, capEnd: true })
  // casing deck strip
  k.box(grey(0.4), [1.6, 30, 0.05], [0, 4, 1.5])
  // sail with sail planes, masts
  const sail: V2[] = [[0, 12.2], [0.55, 11.8], [0.7, 10.8], [0.7, 6.4], [0.4, 5.6], [-0.4, 5.6], [-0.7, 6.4], [-0.7, 10.8], [-0.55, 11.8]]
  k.stack(c, sail, [{ z: 1.2 }, { z: 5.4, sy: 0.97 }], [0, 9])
  k.box(c, [5.6, 1.6, 0.18], [0, 9.6, 4.3])
  for (const [x, y, hh] of [[0, 9.6, 0.5], [0.2, 8.4, 0.35], [-0.2, 7.6, 0.3]] as const) k.cyl(grey(0.35), 0.13, hh, 'z', [x, y, 5.4 + hh / 2], 6)
  // X-rudders breaking the surface aft
  for (const s of [1, -1]) k.add(new BoxGeometry(0.18, 2.4, 2.6), c, matrix([0.8 * s, -27.6, 0.5], [0, s * 0.75, 0]))
  return { geometry: k.build(), parts: [] }
}

function cb90(): BuiltParts {
  const k = new Kit()
  const c = grey(0.66), d = grey(0.5)
  const h = hull(k, { L: 15.9, B: 3.8, fb: 1.1, bowRise: 0.45, rake: 0.9, transom: 0.95, entry: 0.5, bowW: 0.36, flare: 0.12, hull: c, deck: d, draft: 0.3, boot: 0.35 })
  const z = h.deckZ(0)
  // bow ramp
  k.add(new BoxGeometry(1.3, 0.12, 0.9), grey(0.6), matrix([0, 7.55, h.deckZ(7.5) + 0.25], [-0.45, 0, 0]))
  // low troop compartment forward, raised faceted wheelhouse aft of it
  k.stack(c, [[-1.5, -0.8], [1.5, -0.8], [1.5, 2.3], [0.85, 3.3], [-0.85, 3.3], [-1.5, 2.3]], [{ z }, { z: z + 0.9, sx: 0.93, sy: 0.96 }], [0, 1.25])
  k.stack((i, j) => (i === 1 && j !== 0 ? COL.glass : c), [[-1.6, -4.6], [1.6, -4.6], [1.6, -1.7], [1.0, -0.5], [-1.0, -0.5], [-1.6, -1.7]], [{ z }, { z: z + 1.2, sx: 0.96 }, { z: z + 1.7, sx: 0.84, sy: 0.9 }, { z: z + 1.9, sx: 0.74, sy: 0.84 }], [0, -2.55])
  // weapon stations: twin MG on the wheelhouse, single MG on the troop compartment, forward pintle
  k.cyl(grey(0.55), 0.42, 0.32, 'z', [0, -2.6, z + 2.05], 8)
  for (const s of [1, -1]) k.cyl(COL.dark, 0.04, 1.3, 'y', [0.12 * s, -1.9, z + 2.15], 4)
  k.cyl(grey(0.55), 0.36, 0.28, 'z', [0, 1.1, z + 1.03], 8)
  k.cyl(COL.dark, 0.04, 1.1, 'y', [0, 1.75, z + 1.12], 4)
  k.cyl(grey(0.6), 0.05, 1.1, 'z', [0, 5.0, h.deckZ(5) + 0.55], 4)
  // mast, engine vents, waterjets
  k.cyl(grey(0.6), 0.06, 1.1, 'z', [0.6, -4.0, z + 2.45], 4)
  for (const s of [1, -1]) { k.box(COL.dark, [0.5, 1.2, 0.18], [0.85 * s, -6.0, z + 0.09]); k.box(COL.darker, [0.8, 0.1, 0.5], [0.9 * s, -7.96, 0.3]) }
  return { geometry: k.build(), parts: [] }
}

function supportShip(): BuiltParts {
  const k = new Kit()
  const hullC = grey(0.72), deckC = grey(0.52), sup = grey(0.78)
  const h = hull(k, { L: 64, B: 12, fb: 4.2, bowRise: 1.4, rake: 3.5, transom: 0.9, entry: 0.6, hull: hullC, deck: deckC })
  const z = h.deckZ(10)
  house(k, 5.2, 2, 20, z, 2, 2.7, { color: sup })
  house(k, 4.6, 10, 19.5, z + 5.4, 1, 2.6, { color: sup, chamfer: 1.4, top: grey(0.6) })
  k.box(sup, [11.4, 2.0, 0.2], [0, 17.8, z + 7.4])
  mast(k, 14, z + 8.0, 6.0, sup, 2.8)
  funnel(k, 4.5, z + 5.4, 2.6, 1.3, 1.8, sup)
  crane(k, 3.8, -6, z, 2.0, 11, Math.PI * 0.9)
  gun(k, 25, h.deckZ(25), 0.7)
  boat(k, 4.8, 6, z + 3.2, 6, COL.darker)
  for (let i = 0; i < 3; i++) k.box(grey(0.62), [2.4, 6, 2.4], [-2.6, -12 - i * 6.6, z + 1.2])
  return { geometry: k.build(), parts: [radarPart(14, z + 14.0, 3.2)] }
}

function coastGuard(): BuiltParts {
  const k = new Kit()
  const white = grey(0.92), deckC = grey(0.55)
  const h = hull(k, { L: 52, B: 10.3, fb: 3.4, bowRise: 1.3, rake: 3.0, entry: 0.58, hull: white, deck: deckC, bootCol: grey(0.3) })
  hullStripe(k, h, 9.5, 2.6, 2.2, COL.cgYellow)
  hullStripe(k, h, 7.4, 1.2, 2.2, COL.cgBlue)
  const z = h.deckZ(6)
  house(k, 4.4, -2, 14, z, 1, 2.6, { color: white })
  house(k, 4.0, 7, 13.5, z + 2.6, 1, 2.6, { color: white, chamfer: 1.4, win: 'all', top: grey(0.6) })
  mast(k, 9, z + 5.2, 6.5, white, 2.4)
  crane(k, -3.2, -9, z, 1.8, 7, Math.PI * 0.8)
  boat(k, 3.4, -4.5, z + 0.6, 6, COL.amber)
  for (const s of [1, -1]) k.box(COL.darker, [0.05, 1.0, 1.4], [s * 4.45, 5, z + 1.2])
  k.box(grey(0.6), [8, 14, 0.05], [0, -17, h.deckZ(-17) + 0.03])
  return { geometry: k.build(), parts: [radarPart(9, z + 10.5, 3.0)] }
}

// ---- merchant and civil --------------------------------------------------------------------------

function cargoShip(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 120, B: 20, fb: 6.0, bowRise: 2.5, rake: 5, transom: 0.75, entry: 0.72, hull: grey(0.55), deck: grey(0.5), bootCol: grey(0.3) })
  const z = h.deckZ(0)
  // holds with hatch covers
  for (let i = 0; i < 4; i++) k.box(grey(0.62), [15, 17, 1.6], [0, 42 - i * 20, z + 0.8])
  // three deck cranes on the centreline between hatches
  for (const y of [32, 12, -8]) crane(k, 0, y, z, 7, 18, Math.PI * 0.08)
  // accommodation aft + funnel, forecastle mast
  house(k, 8.5, -56, -44, z, 5, 2.8, { color: COL.white, win: [2, 1, 3] })
  k.box(COL.white, [19.5, 2, 0.3], [0, -45, z + 14])
  funnel(k, -54, z + 14, 5, 2.2, 2.6, grey(0.7))
  mast(k, -49, z + 14, 5.5, COL.white, 3)
  k.cyl(COL.light, 0.3, 9, 'z', [0, 54, z + 2.5 + 4.5], 6, 0.2)
  return { geometry: k.build(), parts: [] }
}

function tanker(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 183, B: 32, fb: 7.0, bowRise: 2.5, rake: 6, transom: 0.8, entry: 0.78, hull: grey(0.58), deck: grey(0.5), bootCol: grey(0.3) })
  const z = h.deckZ(0)
  // pipe rack, catwalk, midship manifold with hose cranes, tank hatches
  k.box(grey(0.62), [1.6, 140, 1.0], [0, 5, z + 1.0])
  k.box(grey(0.7), [1.0, 140, 0.15], [0, 5, z + 2.4])
  k.box(grey(0.6), [26, 3.5, 1.4], [0, 0, z + 0.9])
  for (const s of [1, -1]) crane(k, 9 * s, 4, z, 4, 9, s > 0 ? Math.PI * 0.5 : -Math.PI * 0.5, grey(0.7))
  for (let i = 0; i < 6; i++) for (const s of [1, -1]) k.cyl(grey(0.6), 0.7, 0.8, 'z', [7 * s, 60 - i * 22, z + 0.4], 8)
  house(k, 13, -82, -66, z, 6, 2.8, { color: COL.white, win: [1, 2, 3] })
  k.box(COL.white, [30, 2.2, 0.3], [0, -67.2, z + 16.8])
  funnel(k, -80, z + 16.8, 6, 3, 3.6, grey(0.7))
  mast(k, -72, z + 16.8, 6, COL.white, 4)
  k.cyl(COL.light, 0.4, 12, 'z', [0, 80, z + 2.5 + 6], 6, 0.25)
  k.box(grey(0.62), [14, 10, 2.5], [0, 84, z + 2.5 + 1.25])
  return { geometry: k.build(), parts: [] }
}

const CONTAINERS: RGB[] = [[0.62, 0.3, 0.26], [0.27, 0.4, 0.6], [0.32, 0.52, 0.38], [0.78, 0.78, 0.78], [0.82, 0.58, 0.28], [0.5, 0.52, 0.56], [0.68, 0.66, 0.6]]

function containerShip(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 170, B: 27, fb: 8.0, bowRise: 3, rake: 7, transom: 0.85, entry: 0.72, hull: grey(0.5), deck: grey(0.48), bootCol: grey(0.28) })
  const z = h.deckZ(0)
  // container bays (40 ft = 12.2 m), stacked in blocks across the beam
  const bays = [70, 56.5, 43, 29.5, 16, 2.5, -11, -24.5, -38, -72]
  bays.forEach((y, bi) => {
    const hb = Math.min(h.halfBeam(y + 6), h.halfBeam(y - 6)) - 0.6
    const blocks = 5
    for (let b = 0; b < blocks; b++) {
      const x0 = -hb + (2 * hb * b) / blocks, x1 = -hb + (2 * hb * (b + 1)) / blocks
      const tiers = 2 + Math.floor(hash(bi, b, 5) * 4) - (bi === 0 ? 1 : 0)
      const col = CONTAINERS[Math.floor(hash(bi, b, 9) * CONTAINERS.length)]
      k.box(col, [x1 - x0 - 0.25, 12.2, tiers * 2.6], [(x0 + x1) / 2, y, z + (tiers * 2.6) / 2])
    }
  })
  k.box(grey(0.5), [h.halfBeam(80) * 2, 2.5, 3], [0, 79.5, z + 1.5])
  house(k, 11, -62, -52, z, 7, 2.8, { color: COL.white, win: [1, 2, 3] })
  k.box(COL.white, [26.5, 2.2, 0.3], [0, -53, z + 19.6])
  funnel(k, -60, z + 19.6, 5, 2.5, 3.5, grey(0.7))
  mast(k, -57, z + 19.6, 5.5, COL.white, 3)
  return { geometry: k.build(), parts: [] }
}

function ferry(): BuiltParts {
  const k = new Kit()
  const white = COL.white
  const h = hull(k, { L: 190, B: 28, fb: 9.0, bowRise: 2, rake: 8, transom: 0.9, entry: 0.62, hull: grey(0.88), deck: grey(0.6), bootCol: grey(0.3) })
  const z = h.deckZ(0)
  // hull window row and long multi-deck superstructure
  for (const s of [1, -1]) k.box(COL.glass, [0.1, 120, 0.9], [s * 13.95, -5, z - 2.5])
  house(k, 13.5, -78, 62, z, 2, 3.0, { color: white, chamfer: 6 })
  house(k, 11.8, -74, 60, z + 6, 2, 3.0, { color: white, chamfer: 5 })
  house(k, 12.5, -40, 58, z + 12, 2, 3.0, { color: white, chamfer: 5 })
  k.box(white, [28, 4, 0.5], [0, 56, z + 17.8])
  for (const s of [1, -1]) funnel(k, -55, z + 18, 7, 2.4, 4.5, white, 6 * s)
  mast(k, 45, z + 18, 8, white, 3)
  for (let i = 0; i < 5; i++) for (const s of [1, -1]) boat(k, 13.0 * s, 30 - i * 16, z + 7.5, 9, COL.amber)
  return { geometry: k.build(), parts: [] }
}

function fishing(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 30, B: 8, fb: 2.6, bowRise: 1.8, rake: 1.5, transom: 0.8, entry: 0.55, hull: grey(0.6), deck: grey(0.55), bootCol: grey(0.3) })
  const z = h.deckZ(6)
  house(k, 3.0, 4, 11, z, 1, 2.4, { color: COL.white, win: 'none' })
  house(k, 2.6, 6, 10.5, z + 2.4, 1, 2.2, { color: COL.white, chamfer: 0.8, win: 'all' })
  k.cyl(COL.light, 0.15, 6, 'z', [0, 8, z + 4.6 + 3], 6)
  k.box(COL.light, [3.4, 0.12, 0.12], [0, 8, z + 9])
  // stern gantry, net drum, outriggers
  for (const s of [1, -1]) k.strut(grey(0.62), [3.2 * s, -14, z], [2.6 * s, -14.4, z + 5.4], 0.3)
  k.box(grey(0.62), [5.6, 0.35, 0.35], [0, -14.4, z + 5.4])
  k.cyl(grey(0.5), 1.0, 4.0, 'x', [0, -9, z + 1.2], 10)
  k.cyl(grey(0.6), 0.12, 6.5, 'z', [0, -2, z + 3.25], 6)
  return { geometry: k.build(), parts: [] }
}

function tug(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 30, B: 11, fb: 2.4, bowRise: 1.5, rake: 1.2, transom: 0.85, entry: 0.45, hull: grey(0.62), deck: grey(0.52), bootCol: grey(0.3) })
  const z = h.deckZ(2)
  // fender belt
  k.stack(COL.darker, [[-5.75, -15.0], [5.75, -15.0], [5.75, 6.5], [3.4, 14.6], [-3.4, 14.6], [-5.75, 6.5]], [{ z: 1.5 }, { z: 2.3 }], [0, 0])
  house(k, 3.8, -3, 7, z, 1, 2.4, { color: COL.white, win: 'none' })
  house(k, 3.0, 0, 6.2, z + 2.4, 1, 2.6, { color: COL.white, chamfer: 1.0, win: 'all', top: grey(0.6) })
  k.cyl(COL.light, 0.18, 5, 'z', [0, 2, z + 5 + 2.5], 6)
  k.box(COL.light, [3, 0.15, 0.15], [0, 2, z + 9])
  k.cyl(grey(0.5), 1.1, 3.0, 'x', [0, -7, z + 1.2], 10)
  k.box(grey(0.55), [4.5, 0.4, 2.2], [0, -10, z + 1.1])
  for (const s of [1, -1]) funnel(k, -1.5, z + 2.4, 2.2, 0.5, 0.7, COL.white, 2.6 * s)
  return { geometry: k.build(), parts: [] }
}

function icebreaker(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 105, B: 24, fb: 7.0, bowRise: 2.5, rake: 14, transom: 0.85, entry: 0.48, flare: 0.3, hull: grey(0.36), deck: grey(0.5), bootCol: grey(0.25) })
  const z = h.deckZ(15)
  house(k, 10, 5, 34, z, 3, 2.8, { color: COL.white })
  house(k, 8.5, 18, 33, z + 8.4, 2, 2.8, { color: COL.white, chamfer: 3, top: grey(0.6) })
  k.box(COL.white, [23.6, 3, 0.4], [0, 31, z + 13.8])
  funnel(k, 10, z + 8.4, 6, 2.6, 3.5, COL.white)
  mast(k, 26, z + 14, 7, COL.white, 3)
  // helideck aft, crane
  k.box(grey(0.55), [18, 20, 0.6], [0, -36, h.deckZ(-36) + 2.8])
  for (const s of [1, -1]) k.box(grey(0.45), [0.6, 18, 2.6], [7 * s, -36, h.deckZ(-36) + 1.3])
  k.cyl(grey(0.7), 5.5, 0.05, 'z', [0, -36, h.deckZ(-36) + 3.12], 16)
  crane(k, 8, -12, h.deckZ(-12), 3, 14, Math.PI * 0.9)
  return { geometry: k.build(), parts: [] }
}

function sailboat(): BuiltParts {
  const k = new Kit()
  const h = hull(k, { L: 12, B: 4, fb: 1.15, bowRise: 0.25, rake: 1.2, transom: 0.75, entry: 0.45, flare: 0.15, hull: COL.white, deck: grey(0.75), bootCol: grey(0.3), draft: 0.25, boot: 0.2 })
  const z = h.deckZ(0)
  k.stack((i, j) => (i === 0 && (j === 1 || j === 3) ? COL.glass : COL.white), [[-1.2, -2.0], [1.2, -2.0], [1.1, 1.8], [0.6, 2.8], [-0.6, 2.8], [-1.1, 1.8]], [{ z }, { z: z + 0.55, sx: 0.92, sy: 0.96 }], [0, 0])
  // mast, boom, mainsail and jib (thin plates)
  k.cyl(grey(0.7), 0.09, 16.0, 'z', [0, 1.2, z + 8], 6)
  k.cyl(grey(0.7), 0.06, 4.6, 'y', [0, -1.1, z + 1.6], 6)
  const sail = (pts: V2[], ox: number) => k.add(plate(pts, ox, 0.04), COL.white, matrix([0, 0, 0], [0, -Math.PI / 2, 0]))
  // plate() builds in (x,y) at height z; rotate it into the y-z plane
  sail([[z + 1.7, 1.1], [z + 15.5, 1.1], [z + 1.7, -3.3]], 0)
  sail([[z + 0.9, 1.4], [z + 14.2, 1.35], [z + 0.9, 5.4]], 0.08)
  return { geometry: k.build(), parts: [] }
}

export const SEA_BUILDERS: Record<Extract<ModelKey, 'corvette' | 'patrol_ship' | 'mcm' | 'submarine' | 'cb90' | 'support_ship' | 'cargo_ship' | 'tanker' | 'container_ship' | 'ferry' | 'fishing' | 'tug' | 'icebreaker' | 'coast_guard' | 'sailboat'>, () => BuiltParts> = {
  corvette, patrol_ship: patrolShip, mcm, submarine, cb90, support_ship: supportShip, cargo_ship: cargoShip, tanker, container_ship: containerShip,
  ferry, fishing, tug, icebreaker, coast_guard: coastGuard, sailboat,
}
