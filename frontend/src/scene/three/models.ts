/** TrossOps procedural 3D model library. Every model is generated in code (no third-party assets).
 *
 * Frame: metres, +X starboard, +Y forward (nose), +Z up. Origin at ground/wheel contact centre (ground vehicles,
 * parked aircraft, sites) or waterline centre (vessels). Each model is one merged, non-indexed BufferGeometry with
 * `position`, `normal` and `color` (RGB 0..1) — mostly neutral greys so the renderer can multiply by an affiliation tint.
 *
 * Moving parts are positioned in model space (they render correctly when drawn unrotated). To animate, rotate the part
 * about the line through `pivot` parallel to `axis`: M = T(pivot) · R(axis, rpm · t) · T(−pivot). */
import type { BufferGeometry } from 'three'
import { AIR_BUILDERS } from './aircraft'
import { GROUND_BUILDERS } from './ground'
import { SEA_BUILDERS } from './sea'
import { SITE_BUILDERS } from './sites'

export type ModelKey =
  | 'fighter' | 'transport' | 'aew' | 'sigint' | 'trainer' | 'heli_medium' | 'heli_utility' | 'heli_light' | 'uav'
  | 'airliner' | 'widebody' | 'bizjet' | 'ga_prop'
  | 'mbt' | 'ifv' | 'apc_wheeled' | 'spg_wheeled' | 'bv'
  | 'truck' | 'fuel_truck' | 'recovery' | 'ambulance' | 'command_post' | 'radar_vehicle' | 'ad_launcher' | 'engineer'
  | 'police_car' | 'car' | 'bus'
  | 'corvette' | 'patrol_ship' | 'mcm' | 'submarine' | 'cb90' | 'support_ship'
  | 'cargo_ship' | 'tanker' | 'container_ship' | 'ferry' | 'fishing' | 'tug' | 'icebreaker' | 'coast_guard' | 'sailboat'
  | 'hangar' | 'shelter' | 'tower' | 'fuel_tank' | 'radar_dome' | 'radar_rotating' | 'barracks' | 'warehouse' | 'bunker'

/** Overall dimensions in metres (length along Y, width along X, height along Z), including rotors/masts. */
export interface ModelSpec { key: ModelKey; lengthM: number; widthM: number; heightM: number; domain: 'air' | 'rotor' | 'ground' | 'sea' | 'site' }
/** A separately drawn part that spins about `axis` through `pivot` (model space). */
export interface MovingPart { geometry: BufferGeometry; pivot: [number, number, number]; axis: 'x' | 'y' | 'z'; rpm: number }
export interface BuiltModel { geometry: BufferGeometry; parts: MovingPart[]; spec: ModelSpec }
/** What each category builder returns. */
export interface BuiltParts { geometry: BufferGeometry; parts: MovingPart[] }

const S = (key: ModelKey, lengthM: number, widthM: number, heightM: number, domain: ModelSpec['domain']): ModelSpec => ({ key, lengthM, widthM, heightM, domain })

export const MODEL_SPECS: Record<ModelKey, ModelSpec> = {
  fighter: S('fighter', 15.2, 8.6, 4.5, 'air'),
  transport: S('transport', 29.8, 40.4, 11.6, 'air'),
  aew: S('aew', 30.4, 28.7, 7.8, 'air'),
  sigint: S('sigint', 26.9, 25.0, 7.0, 'air'),
  trainer: S('trainer', 10.5, 9.5, 2.7, 'air'),
  heli_medium: S('heli_medium', 19.6, 16.3, 5.2, 'rotor'),
  heli_utility: S('heli_utility', 19.8, 16.4, 5.1, 'rotor'),
  heli_light: S('heli_light', 13.0, 11.0, 3.5, 'rotor'),
  uav: S('uav', 11.0, 20.0, 3.2, 'air'),
  airliner: S('airliner', 37.6, 35.8, 11.8, 'air'),
  widebody: S('widebody', 63.7, 60.3, 16.8, 'air'),
  bizjet: S('bizjet', 16.4, 15.2, 4.2, 'air'),
  ga_prop: S('ga_prop', 8.3, 11.0, 2.7, 'air'),
  mbt: S('mbt', 10.0, 3.75, 3.0, 'ground'),
  ifv: S('ifv', 7.0, 3.1, 2.7, 'ground'),
  apc_wheeled: S('apc_wheeled', 7.7, 2.8, 2.6, 'ground'),
  spg_wheeled: S('spg_wheeled', 14.1, 3.0, 3.3, 'ground'),
  bv: S('bv', 6.9, 1.9, 2.4, 'ground'),
  truck: S('truck', 8.5, 2.55, 3.3, 'ground'),
  fuel_truck: S('fuel_truck', 8.5, 2.55, 3.1, 'ground'),
  recovery: S('recovery', 9.2, 2.55, 3.4, 'ground'),
  ambulance: S('ambulance', 6.6, 2.1, 2.8, 'ground'),
  command_post: S('command_post', 8.5, 2.55, 6.0, 'ground'),
  radar_vehicle: S('radar_vehicle', 8.5, 2.55, 4.8, 'ground'),
  ad_launcher: S('ad_launcher', 8.5, 2.55, 4.6, 'ground'),
  engineer: S('engineer', 9.0, 4.0, 3.1, 'ground'),
  police_car: S('police_car', 4.94, 1.9, 1.6, 'ground'),
  car: S('car', 4.6, 1.85, 1.48, 'ground'),
  bus: S('bus', 12.0, 2.55, 3.2, 'ground'),
  corvette: S('corvette', 72.6, 10.4, 13.5, 'sea'),
  patrol_ship: S('patrol_ship', 50.0, 7.5, 14.0, 'sea'),
  mcm: S('mcm', 47.5, 9.6, 14.0, 'sea'),
  submarine: S('submarine', 60.4, 6.2, 5.8, 'sea'),
  cb90: S('cb90', 15.9, 3.8, 4.1, 'sea'),
  support_ship: S('support_ship', 64.0, 12.0, 19.0, 'sea'),
  cargo_ship: S('cargo_ship', 120.0, 20.0, 26.0, 'sea'),
  tanker: S('tanker', 183.0, 32.0, 32.0, 'sea'),
  container_ship: S('container_ship', 170.0, 27.0, 34.0, 'sea'),
  ferry: S('ferry', 190.0, 28.0, 38.0, 'sea'),
  fishing: S('fishing', 30.0, 8.0, 13.0, 'sea'),
  tug: S('tug', 30.0, 11.0, 13.0, 'sea'),
  icebreaker: S('icebreaker', 105.0, 24.0, 30.0, 'sea'),
  coast_guard: S('coast_guard', 52.0, 10.3, 16.0, 'sea'),
  sailboat: S('sailboat', 12.0, 4.0, 17.0, 'sea'),
  hangar: S('hangar', 45.0, 66.0, 15.0, 'site'),
  shelter: S('shelter', 30.0, 22.0, 8.0, 'site'),
  tower: S('tower', 10.0, 10.0, 30.0, 'site'),
  fuel_tank: S('fuel_tank', 20.0, 20.0, 12.0, 'site'),
  radar_dome: S('radar_dome', 12.0, 12.0, 18.0, 'site'),
  radar_rotating: S('radar_rotating', 6.5, 12.0, 19.0, 'site'),
  barracks: S('barracks', 40.0, 13.0, 9.0, 'site'),
  warehouse: S('warehouse', 60.0, 30.0, 12.0, 'site'),
  bunker: S('bunker', 20.0, 15.0, 4.6, 'site'),
}

export const MODEL_KEYS = Object.keys(MODEL_SPECS) as ModelKey[]

const SMALL = new Set<ModelKey>(['truck', 'fuel_truck', 'recovery', 'ambulance', 'command_post', 'radar_vehicle', 'ad_launcher', 'police_car', 'car', 'bus', 'cb90', 'fishing', 'tug', 'sailboat'])
/** Triangle budget per model (geometry plus moving parts): hundreds are instanced. */
export const triangleBudget = (key: ModelKey): number => (SMALL.has(key) ? 1200 : 3000)

const BUILDERS: Record<ModelKey, () => BuiltParts> = { ...AIR_BUILDERS, ...GROUND_BUILDERS, ...SEA_BUILDERS, ...SITE_BUILDERS }

/** Build a model. Pure and deterministic — callers may cache by key. */
export function buildModel(key: ModelKey): BuiltModel {
  const b = BUILDERS[key]
  if (!b) throw new Error(`unknown model key ${key}`)
  const { geometry, parts } = b()
  return { geometry, parts, spec: MODEL_SPECS[key] }
}
