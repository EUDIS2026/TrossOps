/** Fixed-wing aircraft and helicopters. Nose along +Y, wheels on z = 0. */
import { COL, Kit, grey, part, segAngle, wing, matrix, type ColorFn, type RGB, type Sta, type WSta } from './kit'
import type { BuiltParts, ModelKey, MovingPart } from './models'

/** Upper/lower two-tone for superellipse bodies (segment j of an n-ring). */
const twoTone = (n: number, top: RGB, bottom: RGB, split = 0): ColorFn => (_i, j) => (Math.sin(segAngle(j, n)) > split ? top : bottom)
/** Airfoil rings: segments 0–3 upper surface, 4–7 lower surface. */
const wingTone = (top: RGB, bottom: RGB): ColorFn => (_i, j) => (j < 4 ? top : bottom)

function gear(k: Kit, x: number, y: number, r: number, w: number, top: number, twin = false, seg = 8) {
  k.rod(COL.metal, [x, y, r * 0.8], [x, y, top], Math.max(0.05, r * 0.16), 6)
  if (twin) { k.wheel(x - w * 0.7, y, r, w, { seg }); k.wheel(x + w * 0.7, y, r, w, { seg }) } else k.wheel(x, y, r, w, { seg })
}

function navLights(k: Kit, x: number, y: number, z: number, s = 0.18) {
  k.box(COL.navGreen, [s, s * 1.6, s], [x, y, z])
  k.box(COL.navRed, [s, s * 1.6, s], [-x, y, z])
}

// ---- fighter: single-engine delta-canard (Gripen class) ---------------------------------------------

function fighter(): BuiltParts {
  const k = new Kit()
  const n = 16
  const top = grey(0.6), bot = grey(0.76)
  const tone = twoTone(n, top, bot, -0.15)
  const fus: Sta[] = [
    { y: 7.3, w: 0.04, h: 0.04, z: 1.8 }, { y: 6.95, w: 0.22, h: 0.22, z: 1.8 }, { y: 6.15, w: 0.4, h: 0.4, z: 1.84 },
    { y: 5.0, w: 0.52, h: 0.54, z: 1.9 }, { y: 3.8, w: 0.58, h: 0.62, z: 1.95 }, { y: 2.4, w: 0.62, h: 0.66, z: 1.98 },
    { y: 0.5, w: 0.66, h: 0.7, z: 2.0 }, { y: -2.5, w: 0.64, h: 0.7, z: 2.02 }, { y: -5.0, w: 0.56, h: 0.62, z: 2.05 },
    { y: -6.6, w: 0.47, h: 0.5, z: 2.08 }, { y: -7.2, w: 0.44, h: 0.45, z: 2.08 },
  ]
  k.body(fus, n, (i, j) => (i < 2 ? grey(0.5) : tone(i, j)), { endColor: COL.darker })
  k.cyl(COL.darker, 0.43, 0.6, 'y', [0, -7.45, 2.08], 12, 0.4)
  k.cyl(COL.metal, 0.025, 0.45, 'y', [0, 7.5, 1.8], 4)
  // intakes (D-shaped, dark opening)
  for (const s of [1, -1]) {
    k.body([
      { x: 0.8 * s, y: 2.75, w: 0.27, h: 0.42, z: 1.72, p: 3 }, { x: 0.8 * s, y: 2.25, w: 0.3, h: 0.45, z: 1.72, p: 3 },
      { x: 0.72 * s, y: 0.0, w: 0.3, h: 0.42, z: 1.78, p: 3 }, { x: 0.55 * s, y: -2.5, w: 0.25, h: 0.35, z: 1.85, p: 3 },
      { x: 0.4 * s, y: -3.8, w: 0.12, h: 0.18, z: 1.9 },
    ], 12, (_i, j) => tone(0, j), { startColor: COL.glass })
  }
  // canopy and spine
  k.body([
    { y: 4.75, w: 0.08, h: 0.08, z: 2.3 }, { y: 4.3, w: 0.3, h: 0.38, z: 2.32 }, { y: 3.5, w: 0.42, h: 0.55, z: 2.35 },
    { y: 2.6, w: 0.4, h: 0.52, z: 2.33 }, { y: 1.8, w: 0.25, h: 0.32, z: 2.3 }, { y: 1.2, w: 0.1, h: 0.1, z: 2.3 },
  ], 12, COL.glass)
  k.body([
    { y: 2.0, w: 0.28, h: 0.28, z: 2.32 }, { y: -1.0, w: 0.38, h: 0.36, z: 2.42 }, { y: -4.5, w: 0.3, h: 0.32, z: 2.48 },
    { y: -6.6, w: 0.14, h: 0.14, z: 2.42 },
  ], 10, top)
  // delta wing with tip rails + IRIS-T
  const wt = wingTone(top, bot)
  k.wing([
    { s: 0.4, y: 1.5, c: 5.9, t: 0.34, o: 1.62 }, { s: 1.3, y: 0.55, c: 4.95, t: 0.28, o: 1.6 }, { s: 4.0, y: -2.45, c: 1.3, t: 0.1, o: 1.55 },
  ], wt, { mirror: true })
  for (const s of [1, -1]) {
    k.box(top, [0.1, 1.6, 0.12], [4.05 * s, -3.0, 1.55])
    k.cyl(COL.light, 0.065, 2.9, 'y', [4.2 * s, -2.7, 1.55], 6)
    k.box(COL.light, [0.38, 0.25, 0.02], [4.2 * s, -4.0, 1.55])
    // underwing pylon + Meteor-class missile
    k.box(bot, [0.08, 1.2, 0.22], [2.4 * s, -1.2, 1.38])
    k.cyl(COL.light, 0.09, 3.6, 'y', [2.4 * s, -1.0, 1.17], 6)
    k.box(COL.light, [0.02, 0.4, 0.34], [2.4 * s, -2.6, 1.17])
  }
  // canards
  k.wing([{ s: 0.7, y: 3.25, c: 1.9, t: 0.12, o: 2.12 }, { s: 2.65, y: 1.75, c: 0.85, t: 0.06, o: 2.12 }], wt, { mirror: true })
  // fin
  k.wing([{ s: 2.45, y: -2.6, c: 4.5, t: 0.22, o: 0 }, { s: 4.5, y: -5.9, c: 1.4, t: 0.08, o: 0 }], top, { vertical: true })
  // centreline drop tank
  k.body([{ y: 2.4, w: 0.05, h: 0.05, z: 0.98 }, { y: 1.6, w: 0.27, h: 0.27, z: 0.98 }, { y: -1.4, w: 0.27, h: 0.27, z: 0.98 }, { y: -2.4, w: 0.05, h: 0.05, z: 0.98 }], 8, COL.light)
  k.box(bot, [0.08, 1.4, 0.25], [0, 0.0, 1.28])
  // gear
  gear(k, 0, 5.2, 0.26, 0.14, 1.45, true)
  for (const s of [1, -1]) {
    gear(k, 1.15 * s, -0.7, 0.33, 0.22, 1.5)
    k.box(bot, [0.03, 0.8, 0.55], [0.92 * s, -0.7, 1.15])
  }
  return { geometry: k.build(), parts: [] }
}

// ---- tactical airlifter (C-130 class) -------------------------------------------------------------

function transport(): BuiltParts {
  const k = new Kit()
  const n = 16
  const top = grey(0.66), bot = grey(0.74)
  const tone = twoTone(n, top, bot, -0.2)
  const p = 2.6
  k.body([
    { y: 14.9, w: 0.35, h: 0.35, z: 2.75, p }, { y: 14.5, w: 1.0, h: 1.0, z: 2.8, p }, { y: 13.7, w: 1.6, h: 1.55, z: 2.95, p },
    { y: 12.6, w: 2.0, h: 1.95, z: 3.05, p }, { y: 11.4, w: 2.15, h: 2.1, z: 3.05, p }, { y: -4.0, w: 2.15, h: 2.1, z: 3.05, p },
    { y: -6.5, w: 2.1, h: 1.85, z: 3.3, p }, { y: -9.5, w: 1.75, h: 1.2, z: 3.95, p }, { y: -12.3, w: 1.05, h: 0.55, z: 4.55, p },
    { y: -14.6, w: 0.35, h: 0.22, z: 4.9 },
  ], n, (i, j) => {
    const sn = Math.sin(segAngle(j, n))
    if (i < 2) return grey(0.48)
    if (i === 2 && sn > 0.25 && sn < 0.93) return COL.glass
    if (i === 3 && sn > 0.55 && sn < 0.95) return COL.glass
    if ((i === 6 || i === 7) && sn < -0.6) return grey(0.58) // ramp
    return tone(i, j)
  })
  // wing (high, straight) + root fairing
  const wt = wingTone(top, bot)
  k.wing([
    { s: 1.0, y: 2.45, c: 4.9, t: 0.75, o: 5.4 }, { s: 10.0, y: 2.3, c: 4.3, t: 0.6, o: 5.5 }, { s: 20.2, y: 1.6, c: 2.5, t: 0.3, o: 5.75 },
  ], wt, { mirror: true })
  k.body([{ y: 4.2, w: 0.3, h: 0.2, z: 5.2 }, { y: 3.4, w: 1.0, h: 0.45, z: 5.25 }, { y: -2.6, w: 1.0, h: 0.45, z: 5.3 }, { y: -4.0, w: 0.3, h: 0.2, z: 5.25 }], 10, top)
  navLights(k, 20.15, 0.4, 5.75)
  // four turboprops
  const parts: MovingPart[] = []
  for (const x of [5.0, 9.8, -5.0, -9.8]) {
    const zc = 5.0
    k.body([
      { x, y: 6.35, w: 0.05, h: 0.05, z: zc }, { x, y: 6.0, w: 0.36, h: 0.36, z: zc }, { x, y: 5.55, w: 0.5, h: 0.5, z: zc },
      { x, y: 5.35, w: 0.6, h: 0.75, z: zc - 0.05 }, { x, y: 3.0, w: 0.62, h: 0.82, z: zc - 0.05 }, { x, y: -0.5, w: 0.55, h: 0.65, z: zc + 0.05 },
      { x, y: -3.0, w: 0.25, h: 0.3, z: zc + 0.25 },
    ], 12, (i, j) => (i < 2 ? COL.dark : tone(i, j)))
    k.box(COL.darker, [0.5, 0.25, 0.3], [x, 5.3, zc - 0.62])
    parts.push(part(pk => pk.rotor(COL.darker, 4, 2.05, 0.34, [x, 5.75, zc], 'y', { thick: 0.07, pitch: 0.35, hubR: 0.2, root: 0.3, phase: x * 0.3 }), [x, 5.75, zc], 'y', 1020))
  }
  // tail: fin, dorsal fillet, stabiliser
  k.wing([{ s: 4.6, y: -8.6, c: 6.2, t: 0.5, o: 0 }, { s: 11.6, y: -12.6, c: 3.0, t: 0.22, o: 0 }], top, { vertical: true })
  k.wing([{ s: 4.7, y: -6.5, c: 3.0, t: 0.3, o: 0 }, { s: 5.6, y: -8.8, c: 1.0, t: 0.2, o: 0 }], top, { vertical: true })
  k.wing([{ s: 0.3, y: -11.2, c: 4.0, t: 0.35, o: 5.0 }, { s: 8.0, y: -12.4, c: 2.4, t: 0.18, o: 5.05 }], wt, { mirror: true })
  // gear sponsons + tandem main wheels, nose gear
  for (const s of [1, -1]) {
    k.body([
      { x: 1.95 * s, y: 3.9, w: 0.2, h: 0.35, z: 1.8, p: 3 }, { x: 2.0 * s, y: 3.0, w: 0.55, h: 0.75, z: 1.65, p: 3 },
      { x: 2.0 * s, y: -3.0, w: 0.55, h: 0.75, z: 1.65, p: 3 }, { x: 1.95 * s, y: -4.4, w: 0.2, h: 0.35, z: 1.8, p: 3 },
    ], 10, bot)
    for (const y of [0.9, -1.3]) k.wheel(1.9 * s, y, 0.6, 0.45, { seg: 12 })
  }
  gear(k, 0, 11.3, 0.42, 0.3, 1.1, true)
  return { geometry: k.build(), parts }
}

// ---- Global/Gulfstream-type twin-jet frame (AEW, SIGINT, bizjet) ---------------------------------

interface JetOpts { scale: number; fr: number; extras?: (k: Kit, R: number, zc: number, top: RGB, bot: RGB) => void; windows?: number; tone?: [RGB, RGB] }

function twinJet(o: JetOpts): BuiltParts {
  const k = new Kit()
  const n = 16
  const [top, bot] = o.tone ?? [grey(0.72), grey(0.78)]
  const tone = twoTone(n, top, bot, -0.25)
  const R = 1.35 * o.fr
  const zc = 2.4 * Math.max(1, o.fr * 0.95)
  k.body([
    { y: 15.15, w: 0.08 * R, h: 0.08 * R, z: zc - 0.3 * R }, { y: 14.6, w: 0.5 * R, h: 0.45 * R, z: zc - 0.2 * R },
    { y: 13.6, w: 0.82 * R, h: 0.8 * R, z: zc - 0.08 * R }, { y: 12.4, w: 0.97 * R, h: 0.97 * R, z: zc },
    { y: 10.5, w: R, h: R, z: zc }, { y: -6.0, w: R, h: R, z: zc }, { y: -9.5, w: 0.9 * R, h: 0.85 * R, z: zc + 0.2 * R },
    { y: -12.5, w: 0.6 * R, h: 0.55 * R, z: zc + 0.45 * R }, { y: -14.6, w: 0.25 * R, h: 0.25 * R, z: zc + 0.65 * R },
    { y: -15.1, w: 0.08 * R, h: 0.08 * R, z: zc + 0.68 * R },
  ], n, (i, j) => {
    const sn = Math.sin(segAngle(j, n))
    if (i === 2 && sn > 0.35 && sn < 0.9) return COL.glass
    if (i === 0) return grey(0.55)
    return tone(i, j)
  })
  // cabin windows
  const nw = o.windows ?? 7
  for (let w = 0; w < nw; w++) for (const s of [1, -1]) k.box(COL.glass, [0.08, 0.38, 0.32], [s * R * 0.94, 9.5 - w * 1.45, zc + 0.3 * R])
  // swept wing with winglets
  const wt = wingTone(top, bot)
  const wz = zc - 0.62 * R
  k.wing([
    { s: 0.8, y: 3.2, c: 6.2, t: 0.65, o: wz }, { s: 4.5, y: 0.6, c: 3.8, t: 0.42, o: wz + 0.25 }, { s: 13.6, y: -5.6, c: 1.5, t: 0.18, o: wz + 0.9 },
  ], wt, { mirror: true })
  k.wing([{ s: wz + 0.85, y: -5.5, c: 1.5, t: 0.12, o: 13.6 }, { s: wz + 2.6, y: -7.0, c: 0.7, t: 0.08, o: 14.15 }], top, { vertical: true, mirror: true })
  k.body([{ y: 4.8, w: 0.3 * R, h: 0.2, z: zc - 0.8 * R }, { y: 3.6, w: 0.95 * R, h: 0.4 * R, z: zc - 0.75 * R }, { y: -3.4, w: 0.95 * R, h: 0.4 * R, z: zc - 0.75 * R }, { y: -4.8, w: 0.3 * R, h: 0.2, z: zc - 0.7 * R }], 10, bot)
  navLights(k, 13.65, -6.3, wz + 0.95, 0.2)
  // rear-mounted engines on stub pylons
  const ez = zc + 0.55 * R
  for (const s of [1, -1]) {
    const x = s * (R + 1.0)
    k.body([
      { x, y: -5.2, w: 0.6, h: 0.6, z: ez }, { x, y: -5.6, w: 0.7, h: 0.7, z: ez }, { x, y: -8.5, w: 0.66, h: 0.66, z: ez }, { x, y: -10.3, w: 0.42, h: 0.42, z: ez },
    ], 12, top, { startColor: COL.darker, endColor: COL.darker })
    k.box(top, [1.0, 2.0, 0.22], [s * (R + 0.25), -7.9, ez])
  }
  // T-tail
  k.wing([{ s: zc + 0.6 * R, y: -9.6, c: 5.6, t: 0.5, o: 0 }, { s: 7.75, y: -13.6, c: 2.3, t: 0.25, o: 0 }], top, { vertical: true })
  k.wing([{ s: 0.2, y: -13.0, c: 2.6, t: 0.25, o: 7.6 }, { s: 4.8, y: -15.0, c: 1.3, t: 0.12, o: 7.7 }], wt, { mirror: true })
  // gear
  gear(k, 0, 12.0, 0.33, 0.2, zc - 0.85 * R, true)
  for (const s of [1, -1]) gear(k, 2.1 * s, -1.6, 0.48, 0.3, wz - 0.1, true)
  o.extras?.(k, R, zc, top, bot)
  const geometry = k.build()
  if (o.scale !== 1) { geometry.scale(o.scale, o.scale, o.scale); geometry.computeBoundingBox(); geometry.computeBoundingSphere() }
  return { geometry, parts: [] }
}

const aew = () => twinJet({
  scale: 1, fr: 1, windows: 3, extras: (k, R, zc, top, bot) => {
    const pz = zc + R + 1.05
    // Erieye-type "plank" AESA radar on two pylons
    k.body([
      { y: 4.7, w: 0.08, h: 0.5, z: pz, p: 6 }, { y: 4.2, w: 0.38, h: 0.72, z: pz, p: 6 }, { y: -4.2, w: 0.38, h: 0.72, z: pz, p: 6 }, { y: -4.7, w: 0.08, h: 0.5, z: pz, p: 6 },
    ], 12, grey(0.8))
    for (const y of [2.4, -2.4]) k.box(top, [0.32, 1.1, 0.6], [0, y, zc + R + 0.2])
    // ventral sea-search radar canoe and tail strakes
    k.body([{ y: 7.8, w: 0.1, h: 0.1, z: zc - R + 0.05 }, { y: 6.6, w: 0.85, h: 0.42, z: zc - R }, { y: 1.8, w: 0.85, h: 0.42, z: zc - R }, { y: 0.6, w: 0.1, h: 0.1, z: zc - R + 0.05 }], 12, bot)
    for (const s of [1, -1]) k.box(bot, [0.08, 2.6, 0.7], [s * 0.6, -11.5, zc - 0.4 * R], [0, s * 0.5, 0])
  },
})

const sigint = () => twinJet({
  scale: 0.89, fr: 1, windows: 6, extras: (k, R, zc, top, bot) => {
    // long dorsal and ventral antenna canoes + blade antennas
    k.body([{ y: 7.2, w: 0.08, h: 0.08, z: zc + R - 0.05 }, { y: 6.0, w: 0.55, h: 0.32, z: zc + R }, { y: -4.0, w: 0.55, h: 0.32, z: zc + R }, { y: -5.4, w: 0.08, h: 0.08, z: zc + R - 0.05 }], 10, grey(0.8))
    k.body([{ y: 9.0, w: 0.1, h: 0.1, z: zc - R + 0.05 }, { y: 7.8, w: 0.75, h: 0.45, z: zc - R }, { y: -0.5, w: 0.75, h: 0.45, z: zc - R }, { y: -1.8, w: 0.1, h: 0.1, z: zc - R + 0.05 }], 10, bot)
    for (const y of [8.6, 4.2, 0.4, -2.8]) k.box(top, [0.06, 0.55, 0.5], [0, y, zc + R + 0.55], [0.35, 0, 0])
    for (const y of [3.6, -3.0]) k.box(bot, [0.06, 0.5, 0.45], [0, y, zc - R - 0.1])
  },
})

const bizjet = () => twinJet({ scale: 0.54, fr: 1.28, windows: 7, tone: [grey(0.92), grey(0.8)] })

// ---- trainer (Sk 60 class): shoulder wing with anhedral, T-tail, side-by-side canopy ---------------

function trainer(): BuiltParts {
  const k = new Kit()
  const n = 14
  const top = grey(0.7), bot = grey(0.8)
  const tone = twoTone(n, top, bot, -0.2)
  k.body([
    { y: 5.25, w: 0.05, h: 0.05, z: 1.12 }, { y: 4.6, w: 0.35, h: 0.32, z: 1.17 }, { y: 3.4, w: 0.62, h: 0.58, z: 1.25 },
    { y: 2.0, w: 0.75, h: 0.7, z: 1.3 }, { y: -0.5, w: 0.78, h: 0.7, z: 1.3 }, { y: -2.8, w: 0.6, h: 0.55, z: 1.4 },
    { y: -4.6, w: 0.3, h: 0.32, z: 1.55 }, { y: -5.25, w: 0.1, h: 0.12, z: 1.6 },
  ], n, (i, j) => (i === 0 ? grey(0.55) : tone(i, j)))
  k.body([{ y: 3.4, w: 0.1, h: 0.1, z: 1.8 }, { y: 2.9, w: 0.5, h: 0.32, z: 1.85 }, { y: 2.0, w: 0.64, h: 0.46, z: 1.88 }, { y: 0.9, w: 0.56, h: 0.4, z: 1.88 }, { y: 0.2, w: 0.2, h: 0.15, z: 1.85 }], 12, COL.glass)
  const wt = wingTone(top, bot)
  k.wing([{ s: 0.5, y: 1.1, c: 2.6, t: 0.3, o: 1.78 }, { s: 4.75, y: 0.05, c: 1.15, t: 0.12, o: 1.3 }], wt, { mirror: true })
  for (const s of [1, -1]) {
    k.body([{ x: 0.85 * s, y: 0.75, w: 0.3, h: 0.3, z: 1.08 }, { x: 0.85 * s, y: 0.4, w: 0.36, h: 0.36, z: 1.08 }, { x: 0.82 * s, y: -2.2, w: 0.34, h: 0.34, z: 1.1 }, { x: 0.8 * s, y: -2.8, w: 0.24, h: 0.24, z: 1.12 }], 10, bot, { startColor: COL.darker, endColor: COL.darker })
    gear(k, 1.15 * s, -0.6, 0.28, 0.16, 1.45)
  }
  navLights(k, 4.75, -0.3, 1.32, 0.14)
  k.wing([{ s: 1.7, y: -3.0, c: 2.2, t: 0.22, o: 0 }, { s: 2.65, y: -4.3, c: 1.05, t: 0.12, o: 0 }], top, { vertical: true })
  k.wing([{ s: 0.1, y: -4.2, c: 1.2, t: 0.12, o: 2.62 }, { s: 1.9, y: -4.7, c: 0.7, t: 0.07, o: 2.62 }], wt, { mirror: true })
  gear(k, 0, 3.5, 0.22, 0.12, 0.9)
  return { geometry: k.build(), parts: [] }
}

// ---- helicopters ---------------------------------------------------------------------------------

interface HeliCockpit { from: number; to: number }
function heliBody(k: Kit, st: Sta[], n: number, color: RGB, cockpit: HeliCockpit, chin = true) {
  k.body(st, n, (i, j) => {
    const a = segAngle(j, n), sn = Math.sin(a)
    if (i >= cockpit.from && i <= cockpit.to && (sn > -0.05 || (chin && i === cockpit.from && sn > -0.75))) return COL.glass
    return color
  })
}

function heliMedium(): BuiltParts {
  const k = new Kit()
  const c = grey(0.68), d = grey(0.6)
  heliBody(k, [
    { y: 7.15, w: 0.25, h: 0.3, z: 1.5, p: 2.5 }, { y: 6.7, w: 0.85, h: 0.72, z: 1.6, p: 2.5 }, { y: 5.6, w: 1.15, h: 1.05, z: 1.8, p: 3 },
    { y: 4.4, w: 1.28, h: 1.15, z: 1.85, p: 3 }, { y: 1.5, w: 1.32, h: 1.15, z: 1.85, p: 3.5 }, { y: -2.6, w: 1.3, h: 1.12, z: 1.88, p: 3.5 },
    { y: -3.9, w: 1.1, h: 0.8, z: 2.2, p: 3 }, { y: -5.2, w: 0.55, h: 0.45, z: 2.65, p: 2.5 }, { y: -8.0, w: 0.36, h: 0.36, z: 2.9 },
    { y: -9.4, w: 0.28, h: 0.32, z: 3.05 },
  ], 16, c, { from: 1, to: 2 })
  // engine and transmission deck
  k.body([{ y: 3.6, w: 0.4, h: 0.2, z: 2.95 }, { y: 2.8, w: 0.95, h: 0.55, z: 3.05, p: 3 }, { y: -2.6, w: 1.0, h: 0.6, z: 3.05, p: 3 }, { y: -4.6, w: 0.45, h: 0.3, z: 2.95 }], 12, d)
  for (const s of [1, -1]) k.box(COL.darker, [0.3, 0.9, 0.35], [s * 0.95, -2.6, 3.35])
  k.cyl(COL.dark, 0.22, 1.0, 'z', [0, 1.0, 4.1], 8)
  // sponsons, cabin windows, sliding door
  for (const s of [1, -1]) {
    k.body([{ x: 1.3 * s, y: 0.9, w: 0.15, h: 0.25, z: 1.0 }, { x: 1.38 * s, y: 0.4, w: 0.32, h: 0.38, z: 0.98, p: 3 }, { x: 1.38 * s, y: -2.4, w: 0.32, h: 0.38, z: 0.98, p: 3 }, { x: 1.3 * s, y: -2.9, w: 0.15, h: 0.25, z: 1.0 }], 10, d)
    for (const y of [2.6, 0.6, -1.3]) k.box(COL.glass, [0.08, 0.7, 0.55], [1.31 * s, y, 2.25])
    k.box(d, [0.05, 1.9, 1.5], [1.33 * s, 0.6, 1.95])
    gear(k, 1.55 * s, -1.0, 0.36, 0.26, 0.95)
  }
  gear(k, 0, 5.0, 0.3, 0.18, 0.9, true)
  // tail
  k.wing([{ s: 2.9, y: -7.7, c: 1.9, t: 0.3, o: 0 }, { s: 4.9, y: -9.0, c: 1.1, t: 0.18, o: 0 }], c, { vertical: true })
  k.add(wing([{ s: 0.25, y: -8.0, c: 1.0, t: 0.12, o: 3.15 }, { s: 1.9, y: -8.2, c: 0.7, t: 0.08, o: 3.15 }], c, { side: -1 }))
  k.box(COL.navRed, [0.15, 0.15, 0.15], [0, -9.5, 4.95])
  const parts = [
    part(pk => pk.rotor(grey(0.3), 4, 8.15, 0.6, [0, 1.0, 4.68], 'z', { thick: 0.1, root: 0.45, hubR: 0.38, pitch: 0.06 }), [0, 1.0, 4.68], 'z', 260),
    part(pk => pk.rotor(grey(0.3), 4, 1.6, 0.22, [0.45, -9.0, 3.7], 'x', { thick: 0.05, root: 0.15, hubR: 0.14, pitch: 0.2 }), [0.45, -9.0, 3.7], 'x', 1100),
  ]
  return { geometry: k.build(), parts }
}

function heliUtility(): BuiltParts {
  const k = new Kit()
  const c = grey(0.62), d = grey(0.55)
  heliBody(k, [
    { y: 6.0, w: 0.2, h: 0.25, z: 1.35, p: 2.5 }, { y: 5.55, w: 0.75, h: 0.6, z: 1.45, p: 2.5 }, { y: 4.6, w: 1.05, h: 0.85, z: 1.6, p: 3 },
    { y: 3.4, w: 1.18, h: 1.0, z: 1.7, p: 3.5 }, { y: -1.6, w: 1.18, h: 0.98, z: 1.72, p: 3.5 }, { y: -3.2, w: 0.9, h: 0.75, z: 1.95, p: 3 },
    { y: -4.6, w: 0.42, h: 0.42, z: 2.25, p: 2.5 }, { y: -8.6, w: 0.3, h: 0.3, z: 2.42 }, { y: -9.9, w: 0.25, h: 0.28, z: 2.55 },
  ], 16, c, { from: 1, to: 2 })
  k.body([{ y: 3.0, w: 0.5, h: 0.2, z: 2.62 }, { y: 2.2, w: 1.1, h: 0.5, z: 2.7, p: 3 }, { y: -2.4, w: 1.15, h: 0.5, z: 2.72, p: 3 }, { y: -3.8, w: 0.4, h: 0.25, z: 2.62 }], 12, d)
  for (const s of [1, -1]) {
    k.body([{ x: 0.78 * s, y: 1.2, w: 0.32, h: 0.32, z: 3.05 }, { x: 0.78 * s, y: 0.9, w: 0.38, h: 0.38, z: 3.05 }, { x: 0.78 * s, y: -2.6, w: 0.36, h: 0.36, z: 3.05 }, { x: 0.85 * s, y: -3.2, w: 0.22, h: 0.22, z: 3.05 }], 10, d, { startColor: COL.darker, endColor: COL.darker })
    for (const y of [1.2, -0.6]) k.box(COL.glass, [0.08, 0.9, 0.6], [1.17 * s, y, 2.0])
    // fixed main gear on drag struts
    k.strut(COL.metal, [0.9 * s, 2.9, 0.95], [1.45 * s, 2.9, 0.4], 0.12)
    k.strut(COL.metal, [0.9 * s, 1.9, 1.0], [1.45 * s, 2.9, 0.4], 0.1)
    k.wheel(1.5 * s, 2.9, 0.38, 0.26, { seg: 8 })
  }
  k.cyl(COL.dark, 0.2, 0.9, 'z', [0, 0, 3.45], 8)
  k.wing([{ s: 2.5, y: -8.1, c: 1.9, t: 0.35, o: 0 }, { s: 4.4, y: -9.4, c: 1.2, t: 0.2, o: 0 }], c, { vertical: true })
  k.wing([{ s: 0.25, y: -8.6, c: 1.25, t: 0.14, o: 2.4 }, { s: 2.25, y: -8.7, c: 1.0, t: 0.1, o: 2.4 }], c, { mirror: true })
  k.rod(COL.metal, [0, -7.6, 2.2], [0, -7.6, 0.25], 0.06)
  k.wheel(0, -7.6, 0.2, 0.14, { seg: 8 })
  const parts = [
    part(pk => pk.rotor(grey(0.28), 4, 8.18, 0.53, [0, 0, 3.98], 'z', { thick: 0.1, root: 0.4, hubR: 0.36, pitch: 0.06 }), [0, 0, 3.98], 'z', 258),
    part(pk => pk.rotor(grey(0.28), 4, 1.68, 0.22, [0.42, -9.6, 3.45], 'x', { thick: 0.05, root: 0.15, hubR: 0.14, pitch: 0.2 }), [0.42, -9.6, 3.45], 'x', 1190),
  ]
  return { geometry: k.build(), parts }
}

function heliLight(): BuiltParts {
  const k = new Kit()
  const c = grey(0.74), d = grey(0.66)
  heliBody(k, [
    { y: 4.7, w: 0.15, h: 0.18, z: 1.2, p: 2.2 }, { y: 4.2, w: 0.55, h: 0.5, z: 1.3 }, { y: 3.2, w: 0.75, h: 0.7, z: 1.45, p: 2.5 },
    { y: 1.8, w: 0.8, h: 0.78, z: 1.5, p: 2.8 }, { y: -0.6, w: 0.78, h: 0.75, z: 1.55, p: 2.8 }, { y: -1.9, w: 0.55, h: 0.55, z: 1.75, p: 2.5 },
    { y: -3.0, w: 0.24, h: 0.26, z: 2.0 }, { y: -6.3, w: 0.15, h: 0.18, z: 2.1 }, { y: -6.7, w: 0.1, h: 0.12, z: 2.15 },
  ], 16, c, { from: 1, to: 2 })
  k.body([{ y: 1.8, w: 0.3, h: 0.15, z: 2.2 }, { y: 1.2, w: 0.55, h: 0.35, z: 2.3 }, { y: -1.8, w: 0.5, h: 0.32, z: 2.3 }, { y: -2.8, w: 0.2, h: 0.15, z: 2.2 }], 12, d)
  for (const s of [1, -1]) {
    k.box(COL.glass, [0.08, 1.4, 0.5], [0.77 * s, 0.6, 1.85])
    k.body([{ x: 0.82 * s, y: 0.2, w: 0.08, h: 0.12, z: 0.95 }, { x: 0.85 * s, y: -0.2, w: 0.18, h: 0.2, z: 0.95 }, { x: 0.85 * s, y: -1.2, w: 0.18, h: 0.2, z: 0.95 }, { x: 0.82 * s, y: -1.6, w: 0.08, h: 0.12, z: 0.95 }], 8, d)
    gear(k, 0.95 * s, -0.7, 0.25, 0.14, 0.9)
  }
  gear(k, 0, 3.0, 0.2, 0.1, 0.85)
  k.cyl(COL.dark, 0.14, 0.75, 'z', [0, 0.4, 2.7], 8)
  k.wing([{ s: 1.9, y: -5.6, c: 0.95, t: 0.14, o: 0 }, { s: 3.15, y: -6.4, c: 0.55, t: 0.08, o: 0 }], c, { vertical: true })
  k.wing([{ s: 1.9, y: -5.7, c: 0.7, t: 0.1, o: 0 }, { s: 1.35, y: -6.0, c: 0.45, t: 0.06, o: 0 }], c, { vertical: true })
  k.wing([{ s: 0.1, y: -4.8, c: 0.65, t: 0.08, o: 2.05 }, { s: 1.45, y: -4.9, c: 0.55, t: 0.06, o: 2.05 }], c, { mirror: true })
  for (const s of [1, -1]) k.box(c, [0.05, 0.55, 0.45], [1.47 * s, -5.15, 2.05])
  const parts = [
    part(pk => pk.rotor(grey(0.3), 4, 5.5, 0.32, [0, 0.4, 3.15], 'z', { thick: 0.07, root: 0.3, hubR: 0.22, pitch: 0.06 }), [0, 0.4, 3.15], 'z', 380),
    part(pk => pk.rotor(grey(0.3), 2, 0.7, 0.14, [-0.22, -6.35, 2.65], 'x', { thick: 0.04, root: 0.08, hubR: 0.08, pitch: 0.2 }), [-0.22, -6.35, 2.65], 'x', 2000),
  ]
  return { geometry: k.build(), parts }
}

// ---- MALE UAV with Y-tail and pusher prop --------------------------------------------------------

function uav(): BuiltParts {
  const k = new Kit()
  const n = 14
  const c = grey(0.74), b = grey(0.8)
  k.body([
    { y: 5.5, w: 0.06, h: 0.06, z: 1.38 }, { y: 5.1, w: 0.42, h: 0.45, z: 1.42 }, { y: 4.2, w: 0.55, h: 0.62, z: 1.48 },
    { y: 2.5, w: 0.5, h: 0.55, z: 1.42 }, { y: -1.0, w: 0.45, h: 0.48, z: 1.36 }, { y: -3.8, w: 0.3, h: 0.34, z: 1.42 },
    { y: -5.0, w: 0.14, h: 0.16, z: 1.45 },
  ], n, twoTone(n, c, b, -0.2))
  k.ball(COL.dark, 0.3, [0, 4.0, 0.82], [1, 1, 1], 1)
  const wt = wingTone(c, b)
  k.wing([{ s: 0.3, y: 0.9, c: 1.4, t: 0.2, o: 1.45 }, { s: 10.0, y: 0.5, c: 0.6, t: 0.07, o: 1.7 }], wt, { mirror: true })
  const tail: WSta[] = [{ s: 0.15, y: -3.5, c: 1.3, t: 0.12, o: 0 }, { s: 2.4, y: -4.4, c: 0.7, t: 0.06, o: 0 }]
  k.add(wing(tail, c, { side: 1 }), undefined, matrix([0, 0, 1.6], [0, -0.7, 0]))
  k.add(wing(tail, c, { side: -1 }), undefined, matrix([0, 0, 1.6], [0, 0.7, 0]))
  k.wing([{ s: 1.15, y: -3.7, c: 1.2, t: 0.1, o: 0 }, { s: 0.35, y: -4.3, c: 0.6, t: 0.06, o: 0 }], c, { vertical: true })
  gear(k, 0, 3.6, 0.18, 0.1, 0.95)
  for (const s of [1, -1]) { k.strut(COL.metal, [0.2 * s, 0.2, 1.0], [1.0 * s, 0.2, 0.25], 0.08); k.wheel(1.05 * s, 0.2, 0.25, 0.14, { seg: 8 }) }
  const parts = [part(pk => pk.rotor(COL.darker, 3, 1.2, 0.18, [0, -5.3, 1.45], 'y', { thick: 0.05, pitch: 0.35, hubR: 0.1 }), [0, -5.3, 1.45], 'y', 1600)]
  return { geometry: k.build(), parts }
}

// ---- jetliners -----------------------------------------------------------------------------------

interface LinerOpts { L: number; R: number; zc: number; semi: number; H: number; wingY: number; rootC: number; engX: number[]; engR: number; bogie: boolean }

function jetliner(o: LinerOpts): BuiltParts {
  const k = new Kit()
  const n = 18
  const white = grey(0.93), belly = grey(0.74)
  const { L, R, zc } = o
  const h = L / 2
  k.body([
    { y: h, w: 0.05, h: 0.05, z: zc - 0.35 * R }, { y: h - 0.04 * L, w: 0.42 * R, h: 0.42 * R, z: zc - 0.25 * R },
    { y: h - 0.045 * L - 1.0, w: 0.72 * R, h: 0.72 * R, z: zc - 0.12 * R }, { y: h - 0.05 * L - 2.4, w: 0.93 * R, h: 0.93 * R, z: zc - 0.03 * R },
    { y: h - 0.07 * L - 3.0, w: R, h: R, z: zc }, { y: -h + 0.32 * L, w: R, h: R, z: zc }, { y: -h + 0.19 * L, w: 0.82 * R, h: 0.78 * R, z: zc + 0.3 * R },
    { y: -h + 0.08 * L, w: 0.45 * R, h: 0.42 * R, z: zc + 0.6 * R }, { y: -h + 0.01 * L, w: 0.16 * R, h: 0.18 * R, z: zc + 0.75 * R },
    { y: -h, w: 0.06, h: 0.06, z: zc + 0.78 * R },
  ], n, (i, j) => {
    const sn = Math.sin(segAngle(j, n))
    if (i === 2 && sn > 0.4 && sn < 0.9) return COL.glass
    if (i === 0) return grey(0.6)
    return sn > -0.3 ? white : belly
  })
  // window lines and doors
  const wy0 = h - 0.07 * L - 3.0, wy1 = -h + 0.33 * L
  for (const s of [1, -1]) {
    k.box(COL.glass, [0.08, wy0 - wy1 - 1.5, 0.3], [s * 0.965 * R, (wy0 + wy1) / 2 - 0.5, zc + 0.25 * R])
    for (const y of [wy0 + 0.6, wy1 - 1.0]) k.box(grey(0.5), [0.08, 0.9, 1.75], [s * 0.94 * R, y, zc + 0.05 * R])
  }
  // swept wing
  const tanS = 0.52
  const wz = zc - 0.7 * R
  const dih = 0.09
  const r0 = 0.8 * R, kink = 0.36 * o.semi, tip = o.semi
  const wt = wingTone(white, belly)
  k.wing([
    { s: r0, y: o.wingY, c: o.rootC, t: 0.13 * o.rootC, o: wz },
    { s: kink, y: o.wingY - (kink - r0) * tanS, c: 0.6 * o.rootC, t: 0.08 * o.rootC, o: wz + (kink - r0) * dih },
    { s: tip, y: o.wingY - (tip - r0) * tanS, c: 0.22 * o.rootC, t: 0.025 * o.rootC, o: wz + (tip - r0) * dih },
  ], wt, { mirror: true })
  const tipY = o.wingY - (tip - r0) * tanS, tipZ = wz + (tip - r0) * dih
  k.wing([{ s: tipZ, y: tipY, c: 0.22 * o.rootC, t: 0.1, o: tip }, { s: tipZ + 0.065 * o.semi * 2, y: tipY - 1.0, c: 0.08 * o.rootC, t: 0.06, o: tip + 0.3 }], white, { vertical: true, mirror: true })
  navLights(k, tip + 0.05, tipY - 0.3, tipZ, 0.25)
  k.body([{ y: o.wingY + 1.5, w: 0.3 * R, h: 0.2 * R, z: zc - 0.82 * R }, { y: o.wingY, w: 0.85 * R, h: 0.38 * R, z: zc - 0.78 * R }, { y: o.wingY - o.rootC * 0.9, w: 0.85 * R, h: 0.38 * R, z: zc - 0.78 * R }, { y: o.wingY - o.rootC * 1.15, w: 0.3 * R, h: 0.2 * R, z: zc - 0.75 * R }], 10, belly)
  // underwing engines on pylons
  for (const ex of o.engX) for (const s of [1, -1]) {
    const x = ex * s
    const wy = o.wingY - (ex - r0) * tanS, wzz = wz + (ex - r0) * dih
    const ez = wzz - o.engR - 0.15 * o.engR
    const e = o.engR, ey = wy + 1.9 * e
    k.body([
      { x, y: ey, w: 0.92 * e, h: 0.92 * e, z: ez }, { x, y: ey - 0.2 * e, w: e, h: e, z: ez }, { x, y: ey - 2.0 * e, w: 0.95 * e, h: 0.95 * e, z: ez },
      { x, y: ey - 3.0 * e, w: 0.65 * e, h: 0.65 * e, z: ez }, { x, y: ey - 3.7 * e, w: 0.3 * e, h: 0.3 * e, z: ez },
    ], 14, (_i, j) => (Math.sin(segAngle(j, 14)) > -0.2 ? white : belly), { startColor: COL.darker, endColor: COL.dark })
    k.box(white, [0.3 * e, 3.0 * e, 0.9 * e], [x, ey - 2.2 * e, ez + 0.95 * e])
  }
  // tail
  const ty = -h
  k.wing([{ s: zc + 0.72 * R, y: ty + 0.25 * L, c: 0.165 * L, t: 0.015 * L, o: 0 }, { s: o.H, y: ty + 0.11 * L, c: 0.065 * L, t: 0.006 * L, o: 0 }], white, { vertical: true })
  k.wing([{ s: 0.4 * R, y: ty + 0.165 * L, c: 0.095 * L, t: 0.008 * L, o: zc + 0.25 * R }, { s: 0.165 * L, y: ty + 0.075 * L, c: 0.035 * L, t: 0.003 * L, o: zc + 0.25 * R + 0.5 }], wt, { mirror: true })
  // gear
  const nr = 0.38 * R / 2
  gear(k, 0, h - 0.13 * L, nr, nr * 0.6, zc - 0.9 * R, true)
  const mr = o.bogie ? 0.6 : 0.57
  const gx = 0.9 * R + 1.6
  for (const s of [1, -1]) {
    if (o.bogie) {
      k.rod(COL.metal, [gx * s, o.wingY - o.rootC * 0.75, mr], [gx * s, o.wingY - o.rootC * 0.75, wz], 0.14)
      for (const dy of [0.75, -0.75]) for (const dx of [-0.42, 0.42]) k.wheel(gx * s + dx, o.wingY - o.rootC * 0.75 + dy, mr, 0.4, { seg: 10 })
    } else gear(k, gx * s, o.wingY - o.rootC * 0.75, mr, 0.38, wz, true, 10)
  }
  return { geometry: k.build(), parts: [] }
}

const airliner = () => jetliner({ L: 37.6, R: 1.98, zc: 3.75, semi: 17.2, H: 11.8, wingY: 3.6, rootC: 6.6, engX: [5.75], engR: 1.05, bogie: false })
const widebody = () => jetliner({ L: 63.7, R: 2.82, zc: 5.1, semi: 29.6, H: 16.8, wingY: 7.5, rootC: 10.6, engX: [9.4], engR: 1.5, bogie: true })

// ---- GA single prop (Cessna 172 class) -----------------------------------------------------------

function gaProp(): BuiltParts {
  const k = new Kit()
  const n = 14
  const c = grey(0.92), b = grey(0.8)
  k.body([
    { y: 3.8, w: 0.4, h: 0.38, z: 1.2, p: 2.6 }, { y: 3.0, w: 0.52, h: 0.5, z: 1.22, p: 2.8 }, { y: 2.1, w: 0.55, h: 0.62, z: 1.32, p: 3 },
    { y: 1.2, w: 0.56, h: 0.7, z: 1.38, p: 3 }, { y: 0.0, w: 0.54, h: 0.66, z: 1.38, p: 3 }, { y: -1.0, w: 0.42, h: 0.52, z: 1.42, p: 2.8 },
    { y: -3.4, w: 0.14, h: 0.25, z: 1.55 }, { y: -4.0, w: 0.08, h: 0.15, z: 1.6 },
  ], n, (i, j) => {
    const sn = Math.sin(segAngle(j, n)), cs = Math.abs(Math.cos(segAngle(j, n)))
    if (i === 2 && sn > 0.1) return COL.glass
    if (i === 3 && sn > 0.0 && cs > 0.55) return COL.glass
    return sn > -0.3 ? c : b
  })
  k.body([{ y: 4.25, w: 0.03, h: 0.03, z: 1.2 }, { y: 4.0, w: 0.16, h: 0.16, z: 1.2 }, { y: 3.8, w: 0.2, h: 0.2, z: 1.2 }], 8, COL.dark)
  const wt = wingTone(c, b)
  k.wing([{ s: 0.3, y: 1.45, c: 1.6, t: 0.2, o: 2.12 }, { s: 2.4, y: 1.45, c: 1.6, t: 0.2, o: 2.15 }, { s: 5.5, y: 1.3, c: 1.15, t: 0.14, o: 2.3 }], wt, { mirror: true })
  navLights(k, 5.5, 0.9, 2.3, 0.12)
  for (const s of [1, -1]) {
    k.strut(c, [0.5 * s, 0.7, 0.95], [2.7 * s, 0.7, 2.12], 0.08, 0.05)
    k.strut(COL.metal, [0.45 * s, 0.0, 0.85], [1.2 * s, 0.0, 0.25], 0.08, 0.06)
    k.wheel(1.22 * s, 0.0, 0.25, 0.14, { seg: 8 })
  }
  k.wing([{ s: 1.5, y: -2.9, c: 1.3, t: 0.12, o: 0 }, { s: 2.7, y: -3.8, c: 0.65, t: 0.07, o: 0 }], c, { vertical: true })
  k.wing([{ s: 0.1, y: -3.0, c: 1.0, t: 0.1, o: 1.5 }, { s: 1.7, y: -3.25, c: 0.72, t: 0.06, o: 1.5 }], wt, { mirror: true })
  gear(k, 0, 3.0, 0.2, 0.1, 0.85)
  const parts = [part(pk => pk.rotor(COL.darker, 2, 0.95, 0.14, [0, 4.1, 1.2], 'y', { thick: 0.04, pitch: 0.35, hubR: 0.06 }), [0, 4.1, 1.2], 'y', 2400)]
  return { geometry: k.build(), parts }
}

export const AIR_BUILDERS: Record<Extract<ModelKey, 'fighter' | 'transport' | 'aew' | 'sigint' | 'trainer' | 'heli_medium' | 'heli_utility' | 'heli_light' | 'uav' | 'airliner' | 'widebody' | 'bizjet' | 'ga_prop'>, () => BuiltParts> = {
  fighter, transport, aew, sigint, trainer, heli_medium: heliMedium, heli_utility: heliUtility, heli_light: heliLight, uav, airliner, widebody, bizjet, ga_prop: gaProp,
}
