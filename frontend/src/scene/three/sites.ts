/** Site props (airbase, depot and radar infrastructure). Ground on z = 0, main opening/front towards +Y. */
import { COL, Kit, grey, part, ringXZ, type V2, type V3 } from './kit'
import type { BuiltParts, ModelKey } from './models'

/** Half-arch ring in the x-z plane, closed along the ground. Segment 0 = floor, 1..n = arch from +x over the top to −x. */
function archPts(hw: number, h: number, n: number, base = 0): V2[] {
  const pts: V2[] = [[-hw, 0], [hw, 0]]
  if (base > 0) pts.push([hw, base])
  for (let i = 1; i < n; i++) { const a = (i / n) * Math.PI; pts.push([hw * Math.cos(a), base + h * Math.sin(a)]) }
  if (base > 0) pts.push([-hw, base])
  return pts
}

function hangar(): BuiltParts {
  const k = new Kit()
  const ring: V2[] = [[-30, 0], [30, 0], [30, 10]]
  for (let i = 1; i < 8; i++) { const x = 30 - (60 * i) / 8; ring.push([x, 10 + 5 * (1 - (x / 30) ** 2)]) }
  ring.push([-30, 10])
  k.loft([ringXZ(-22.5, ring), ringXZ(22.5, ring)], { color: (_i, j) => (j === 1 || j === ring.length - 1 ? grey(0.76) : j === 0 ? grey(0.5) : j % 2 ? grey(0.6) : grey(0.64)), capStart: true, capEnd: true })
  // sliding door leaves with panel seams, apron strip
  k.box(grey(0.55), [54, 0.3, 9.6], [0, 22.6, 4.8])
  for (let i = -3; i <= 3; i++) k.box(grey(0.42), [0.25, 0.4, 9.6], [i * 7.7, 22.65, 4.8])
  k.box(grey(0.66), [60.4, 0.6, 1.0], [0, 22.6, 10.0])
  // side annex with windows
  k.stack((i, j) => (i === 1 && j !== 3 ? COL.glass : grey(0.78)), [[30, -18], [36, -18], [36, 10], [30, 10]], [{ z: 0 }, { z: 1.6 }, { z: 3.0 }, { z: 5.0 }], [33, -4])
  k.box(grey(0.5), [6.4, 28.4, 0.2], [33, -4, 5.05])
  return { geometry: k.build(), parts: [] }
}

function shelter(): BuiltParts {
  const k = new Kit()
  const concrete = COL.concrete
  // hardened arch, dark open front (recessed), thick portal frame
  const outer = archPts(11, 8, 12)
  k.loft([ringXZ(-15, outer), ringXZ(12, outer)], { color: (_i, j) => (j === 0 ? grey(0.5) : j > 4 && j < 9 ? grey(0.7) : concrete), capStart: true, capEnd: true, endColor: COL.glass, startColor: grey(0.7) })
  const frame: V2[] = []
  for (let i = 0; i <= 12; i++) { const a = (i / 12) * Math.PI; frame.push([11.25 * Math.cos(a), 8.2 * Math.sin(a)]) }
  for (let i = 12; i >= 0; i--) { const a = (i / 12) * Math.PI; frame.push([9.4 * Math.cos(a), 6.6 * Math.sin(a)]) }
  k.extrude(grey(0.8), frame, 'y', 12, 15)
  // door leaves parked on the sides, rear vent
  for (const s of [1, -1]) { k.box(grey(0.6), [4.6, 1.1, 6.2], [9.9 * s, 15.6, 3.1]); k.box(grey(0.45), [5.2, 0.5, 0.25], [9.9 * s, 15.6, 0.12]) }
  k.box(grey(0.6), [3, 2.5, 1.6], [0, -12.5, 7.6])
  k.box(COL.darker, [2.4, 0.1, 0.8], [0, -11.2, 7.8])
  return { geometry: k.build(), parts: [] }
}

function tower(): BuiltParts {
  const k = new Kit()
  const c = grey(0.8)
  k.stack((i, j) => (i === 1 && j !== 0 ? COL.glass : c), [[-5, -5], [5, -5], [5, 5], [-5, 5]], [{ z: 0 }, { z: 1.2 }, { z: 2.6 }, { z: 4.2 }])
  k.box(grey(0.55), [10.2, 10.2, 0.25], [0, 0, 4.3])
  k.stack((i, j) => (i % 2 === 1 && j === 2 ? COL.glass : c), [[-2.2, -2.2], [2.2, -2.2], [2.2, 2.2], [-2.2, 2.2]], [{ z: 4.2 }, { z: 8 }, { z: 9 }, { z: 13 }, { z: 14 }, { z: 21 }])
  const oct: V2[] = Array.from({ length: 8 }, (_, i) => { const a = ((i + 0.5) / 8) * Math.PI * 2; return [3.3 * Math.cos(a), 3.3 * Math.sin(a)] as V2 })
  k.stack((i) => (i === 1 ? COL.glass : i === 2 ? grey(0.5) : c), oct, [{ z: 21, s: 0.85 }, { z: 21.8, s: 1.0 }, { z: 24.6, s: 1.18 }, { z: 25.3, s: 1.32 }])
  k.cyl(grey(0.55), 4.5, 0.25, 'z', [0, 0, 25.4], 8)
  k.cyl(grey(0.7), 0.12, 4.4, 'z', [0, 0, 27.7], 6)
  k.box(grey(0.7), [2.2, 0.1, 0.1], [0, 0, 28.6])
  k.box(COL.navRed, [0.3, 0.3, 0.3], [0, 0, 30])
  return { geometry: k.build(), parts: [] }
}

function fuelTank(): BuiltParts {
  const k = new Kit()
  k.cyl(grey(0.86), 10, 11, 'z', [0, 0, 5.5], 28)
  k.cyl(grey(0.8), 10.05, 1.0, 'z', [0, 0, 11.5], 28, 1.2)
  for (const z of [3.7, 7.4]) k.cyl(grey(0.74), 10.12, 0.3, 'z', [0, 0, z], 28)
  // spiral stair approximated by stair stringer, roof rail
  k.strut(grey(0.5), [9.6, -3, 0.2], [6.8, 7.4, 11.0], 0.8, 0.3)
  k.box(grey(0.55), [1.6, 1.6, 0.2], [6.9, 7.4, 11.1])
  k.cyl(grey(0.6), 0.45, 0.6, 'z', [0, 0, 12.2], 8)
  return { geometry: k.build(), parts: [] }
}

function radarDome(): BuiltParts {
  const k = new Kit()
  k.stack((i, j) => (i === 1 && j === 2 ? COL.glass : COL.concrete), [[-4, -4], [4, -4], [4, 4], [-4, 4]], [{ z: 0 }, { z: 2.2 }, { z: 3.2 }, { z: 6 }])
  k.box(grey(0.5), [1.6, 0.1, 2.4], [0, 4.02, 1.2])
  k.cyl(grey(0.7), 4.6, 0.6, 'z', [0, 0, 6.2], 16)
  // geodesic radome: faceted icosphere
  k.ball(grey(0.92), 6, [0, 0, 11.4], [1, 1, 1], 2)
  return { geometry: k.build(), parts: [] }
}

function radarRotating(): BuiltParts {
  const k = new Kit()
  const st = grey(0.6)
  const legs: [number, number][] = [[1, 1], [1, -1], [-1, -1], [-1, 1]]
  for (const [sx, sy] of legs) k.strut(st, [3 * sx, 3 * sy, 0], [1.6 * sx, 1.6 * sy, 14], 0.3)
  for (const z of [4.5, 9.5]) {
    const w = 3 - (1.4 * z) / 14
    for (let i = 0; i < 4; i++) {
      const [ax, ay] = legs[i], [bx, by] = legs[(i + 1) % 4]
      k.strut(st, [w * ax, w * ay, z], [w * bx, w * by, z], 0.18)
      const w2 = 3 - (1.4 * (z - 4.5)) / 14
      k.strut(st, [w2 * ax, w2 * ay, z - 4.5], [w * bx, w * by, z], 0.12)
    }
  }
  k.box(grey(0.66), [4.6, 4.6, 0.4], [0, 0, 14.2])
  k.box(grey(0.72), [2.6, 2.6, 2.2], [-0.6, -0.6, 15.5])
  k.cyl(grey(0.5), 0.8, 0.8, 'z', [0, 0, 14.8], 10)
  const pv: V3 = [0, 0, 15.2]
  const ant = part(pk => {
    // shallow curved reflector built from three tilted panels, feed boom and horn
    const zc = 17.2
    const rings: V3[][] = []
    for (let x = -6; x <= 6.01; x += 2) {
      const y0 = 0.5 + 0.045 * x * x
      rings.push([[x, y0, zc - 1.7], [x, y0 - 0.22, zc - 1.7], [x, y0 - 0.82, zc + 1.7], [x, y0 - 0.6, zc + 1.7]])
    }
    pk.loft(rings, { color: grey(0.86), capStart: true, capEnd: true })
    pk.strut(grey(0.5), [0, 0.4, zc - 1.6], [0, 2.8, zc - 0.6], 0.2)
    pk.box(grey(0.5), [0.6, 0.5, 0.6], [0, 2.9, zc - 0.5])
    pk.cyl(grey(0.5), 0.5, 0.8, 'z', [0, 0, 15.6], 8)
    pk.strut(grey(0.5), [0, 0, 15.9], [0, 0.4, zc - 1.6], 0.4)
  }, pv, 'z', 12)
  return { geometry: k.build(), parts: [ant] }
}

function barracks(): BuiltParts {
  const k = new Kit()
  const wall = grey(0.82)
  // two storeys with window bands on the long sides, gable roof
  k.stack((i, j) => ((i === 1 || i === 4) && (j === 1 || j === 3) ? COL.glass : wall), [[-6, -20], [6, -20], [6, 20], [-6, 20]], [{ z: 0 }, { z: 1.0 }, { z: 2.3 }, { z: 3.25 }, { z: 4.25 }, { z: 5.55 }, { z: 6.5 }])
  k.extrude(grey(0.45), [[-6.6, 6.4], [6.6, 6.4], [0, 9.0]], 'y', -20.5, 20.5)
  k.extrude(wall, [[-6, 6.45], [6, 6.45], [0, 8.85]], 'y', -20.02, 20.02)
  for (const y of [-8, 8]) { k.box(grey(0.5), [1.6, 0.1, 2.4], [6.02, y, 1.2]); k.box(grey(0.6), [1.2, 2.4, 0.2], [6.6, y, 2.7]) }
  for (const y of [-12, 12]) k.box(grey(0.6), [0.8, 0.8, 2.0], [2, y, 8.2])
  return { geometry: k.build(), parts: [] }
}

function warehouse(): BuiltParts {
  const k = new Kit()
  const wall = grey(0.76)
  k.stack((i, j) => (i === 2 && (j === 1 || j === 3) ? grey(0.55) : wall), [[-15, -30], [15, -30], [15, 30], [-15, 30]], [{ z: 0 }, { z: 6 }, { z: 9.2 }, { z: 10 }])
  k.extrude(grey(0.6), [[-15.5, 9.9], [15.5, 9.9], [0, 12.0]], 'y', -30.4, 30.4)
  k.extrude(wall, [[-15, 9.95], [15, 9.95], [0, 11.9]], 'y', -30.02, 30.02)
  for (let i = 0; i < 5; i++) k.box(grey(0.48), [0.15, 4.6, 5.0], [15.05, -20 + i * 10, 2.5])
  k.box(grey(0.62), [3, 52, 1.2], [16.5, 0, 0.6])
  k.box(grey(0.5), [6, 0.15, 5], [0, 30.05, 2.5])
  return { geometry: k.build(), parts: [] }
}

function bunker(): BuiltParts {
  const k = new Kit()
  const earth = grey(0.52)
  const ring = (y: number, s: number, h = 4) => ringXZ(y, archPts(7.5 * s, h * s, 10))
  k.loft([ring(-10, 0.55, 3.6), ring(-8.5, 0.9), ring(-6, 1), ring(6, 1), ring(7.5, 0.95)], { color: (_i, j) => (j === 0 ? grey(0.45) : earth), smooth: true, capStart: true, capEnd: true })
  // concrete portal with blast door and splayed wing walls
  k.box(COL.concrete, [8, 1.2, 3.8], [0, 8.2, 1.9])
  k.box(grey(0.4), [3.2, 0.1, 2.6], [0, 8.85, 1.3])
  for (const s of [1, -1]) k.box(COL.concrete, [0.6, 3.0, 2.6], [4.6 * s, 9.6, 1.3], [0, 0, -0.5 * s])
  for (const [x, y] of [[2, -2], [-2.5, 2.5]] as const) k.cyl(grey(0.6), 0.35, 1.3, 'z', [x, y, 4.3], 8)
  return { geometry: k.build(), parts: [] }
}

function guardTower(): BuiltParts {
  const k = new Kit()
  const st = grey(0.55)
  const legs: [number, number][] = [[1, 1], [1, -1], [-1, -1], [-1, 1]]
  // four splayed legs with two levels of cross bracing, glazed cab, overhanging roof, ladder, antenna
  for (const [sx, sy] of legs) k.strut(st, [1.75 * sx, 1.75 * sy, 0], [1.35 * sx, 1.35 * sy, 8], 0.22)
  for (const z of [2.7, 5.4]) {
    const w = 1.75 - (0.4 * z) / 8
    for (let i = 0; i < 4; i++) { const [ax, ay] = legs[i], [bx, by] = legs[(i + 1) % 4]; k.strut(st, [w * ax, w * ay, z], [w * bx, w * by, z], 0.12) }
  }
  k.box(grey(0.6), [3.4, 3.4, 0.25], [0, 0, 8.1])
  k.stack((i) => (i === 1 ? COL.glass : grey(0.78)), [[-1.6, -1.6], [1.6, -1.6], [1.6, 1.6], [-1.6, 1.6]], [{ z: 8.2 }, { z: 9.1 }, { z: 10.3 }, { z: 10.6 }])
  k.box(grey(0.45), [4, 4, 0.3], [0, 0, 10.75])
  k.strut(grey(0.5), [1.9, 0, 0], [1.6, 0, 8.1], 0.5, 0.08)
  k.cyl(grey(0.6), 0.06, 1.2, 'z', [1.2, 1.2, 11.5], 6)
  k.box(grey(0.7), [0.5, 0.5, 0.3], [-1.2, -1.2, 11.05])
  return { geometry: k.build(), parts: [] }
}

function hushHouse(): BuiltParts {
  const k = new Kit()
  const wall = grey(0.74)
  // enclosed engine test cell: aircraft hall (door at −Y), augmenter tube and vertical exhaust stack at +Y
  k.stack((i, j) => (i === 0 && j === 0 ? grey(0.5) : wall), [[-11, -20], [11, -20], [11, 6], [-11, 6]], [{ z: 0 }, { z: 7.5 }, { z: 9.5 }])
  k.extrude(grey(0.62), [[-11.2, 9.4], [11.2, 9.4], [6, 10.6], [-6, 10.6]], 'y', -20.3, 6.3)
  k.box(grey(0.5), [16, 0.3, 7.5], [0, -20.15, 3.75])
  for (let i = -3; i <= 3; i++) k.box(grey(0.42), [0.2, 0.4, 7.5], [i * 2.3, -20.2, 3.75])
  for (const y of [-14, -8, -2]) k.box(grey(0.55), [14, 1.2, 1.0], [0, y, 11.0])
  k.cyl(grey(0.66), 3.2, 12, 'y', [0, 12, 4.2], 14)
  for (const y of [8.5, 12, 15.5]) k.cyl(grey(0.56), 3.35, 0.4, 'y', [0, y, 4.2], 14)
  k.box(grey(0.7), [8, 4, 12], [0, 18, 6])
  k.box(COL.darker, [6.4, 3.4, 0.1], [0, 18, 12.02])
  return { geometry: k.build(), parts: [] }
}

function ilsArray(): BuiltParts {
  const k = new Kit()
  const st = grey(0.62)
  // localizer: a 36 m row of log-periodic dipole antennas on a low frame, booms pointing down the runway (+Y)
  for (const z of [1.2, 3.0]) k.box(st, [36, 0.2, 0.2], [0, 0, z])
  for (let x = -18; x <= 18.01; x += 6) { k.box(st, [0.25, 0.25, 3.2], [x, 0, 1.6]); k.box(COL.concrete, [0.8, 0.8, 0.2], [x, 0, 0.1]) }
  for (let i = 0; i < 13; i++) {
    const x = -17.4 + i * 2.9
    k.box(grey(0.8), [0.12, 4, 0.12], [x, 0, 3.3])
    for (const y of [-1.4, -0.2, 1.0]) k.box(grey(0.75), [1.6 - y * 0.35, 0.08, 0.08], [x, y, 3.3])
    k.box(grey(0.4), [0.2, 0.2, 0.5], [x, 1.9, 3.7])
  }
  return { geometry: k.build(), parts: [] }
}

function mast(): BuiltParts {
  const k = new Kit()
  const st = grey(0.6)
  const legs: [number, number][] = [[1, 1], [1, -1], [-1, -1], [-1, 1]]
  // tapering lattice mast: glideslope, TACAN or weather instruments at the top (height scaled per site)
  for (const [sx, sy] of legs) k.strut(st, [1.35 * sx, 1.35 * sy, 0], [0.45 * sx, 0.45 * sy, 12.5], 0.14)
  for (const z of [2.5, 5, 7.5, 10]) {
    const w = 1.35 - (0.9 * z) / 12.5
    for (let i = 0; i < 4; i++) { const [ax, ay] = legs[i], [bx, by] = legs[(i + 1) % 4]; k.strut(st, [w * ax, w * ay, z], [w * bx, w * by, z], 0.08) }
  }
  k.box(grey(0.55), [1.6, 1.6, 0.15], [0, 0, 12.55])
  k.box(grey(0.82), [0.9, 0.6, 0.8], [0, 0.6, 13.0])
  k.cyl(grey(0.7), 0.06, 1.4, 'z', [-0.5, -0.5, 13.3], 6)
  for (const [x, y] of [[1.4, 0], [-1.4, 0]] as const) k.box(COL.concrete, [0.6, 0.6, 0.3], [x, y, 0.15])
  return { geometry: k.build(), parts: [] }
}

export const SITE_BUILDERS: Record<Extract<ModelKey, 'hangar' | 'shelter' | 'tower' | 'fuel_tank' | 'radar_dome' | 'radar_rotating' | 'barracks' | 'warehouse' | 'bunker' | 'guard_tower' | 'hush_house' | 'ils_array' | 'mast'>, () => BuiltParts> = {
  hangar, shelter, tower, fuel_tank: fuelTank, radar_dome: radarDome, radar_rotating: radarRotating, barracks, warehouse, bunker,
  guard_tower: guardTower, hush_house: hushHouse, ils_array: ilsArray, mast,
}
