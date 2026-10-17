/** 3D layer: the procedural model library (`three/models.ts`) drawn inside MapLibre with three.js, one InstancedMesh
 * per model key (plus one per moving part — rotors, propellers, radar antennas — animated per frame).
 *
 * Frames: models are built in ENU metres (x east, y north/nose, z up). MapLibre's mercator space has y pointing south,
 * so the instance matrix includes a reflection. Instead of fighting face culling, a small two-sided shader lights
 * with the model's true outward normals (reflected consistently with the light), so shading is correct either way.
 * Precision: instances are positioned relative to a per-frame centre (float64 on the CPU), like the sprite layer.
 * Attitude: heading, pitch and bank come from the motion model, so aircraft climb, turn and bank as they fly.
 * Legibility: below real scale a model is enlarged to a minimum on-screen length (capped), never shrunk. */
import * as THREE from 'three'
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MlMap } from 'maplibre-gl'
import type { Affiliation, Condition } from '../contracts/types'
import { buildModel, MODEL_SPECS, type ModelKey } from './three/models'

export interface ModelInstance { id: string; lng: number; lat: number; alt: number | null; heading: number; pitch: number; bank: number; model: string; affiliation: Affiliation; condition: Condition; selected: boolean; speed: number }

const EARTH = 40_075_016.686
const TINT: Record<string, [number, number, number]> = { own: [0.78, 0.9, 1.0], allied: [0.7, 1.0, 0.8], civil: [0.92, 0.9, 0.95], unknown: [1.0, 1.0, 0.62], hostile_suspected: [1.0, 0.62, 0.6], prop: [0.86, 0.88, 0.9] }
const AIRBORNE = new Set(['fighter', 'transport', 'aew', 'sigint', 'trainer', 'uav', 'airliner', 'widebody', 'bizjet', 'ga_prop', 'heli_medium', 'heli_utility', 'heli_light', 'unknown_air'])
const ALIAS: Record<string, ModelKey> = { unknown_air: 'fighter', unknown_sea: 'patrol_ship', personnel: 'command_post', cb90: 'cb90' }
const PROP_MODELS = new Set(['shelter', 'hangar', 'tower', 'radar_dome', 'radar_rotating', 'bunker', 'warehouse', 'barracks'])

/** Zoom from which a domain switches from symbol to model (models are enlarged to stay legible below real scale). */
export function modelZoomFor(model: string): number {
  const spec = MODEL_SPECS[(ALIAS[model] ?? model) as ModelKey]
  if (!spec) return 99
  if (spec.domain === 'air' || spec.domain === 'rotor') return 9.5
  if (spec.domain === 'sea') return spec.lengthM > 60 ? 10.5 : 12
  return 14
}
const MIN_PX: Record<string, number> = { air: 34, rotor: 30, sea: 28, ground: 20, site: 0 }
const MAX_BOOST: Record<string, number> = { air: 60, rotor: 60, sea: 30, ground: 6, site: 1 }

const VS = /* glsl */`
varying vec3 vN; varying vec3 vColor; varying float vZ;
void main() {
  vec4 wp = instanceMatrix * vec4(position, 1.0);
  vN = normalize(mat3(instanceMatrix) * normal);
  #ifdef USE_INSTANCING_COLOR
    vColor = color * instanceColor;
  #else
    vColor = color;
  #endif
  vZ = position.z;
  gl_Position = projectionMatrix * wp;
}`
const FS = /* glsl */`
uniform vec3 uSun; uniform vec3 uFill;
varying vec3 vN; varying vec3 vColor; varying float vZ;
void main() {
  vec3 n = normalize(vN);
  float key = max(dot(n, uSun), 0.0);
  float fill = max(dot(n, uFill), 0.0);
  float sky = 0.5 + 0.5 * n.z;
  vec3 c = vColor * (0.28 + 0.18 * sky + 0.78 * key + 0.22 * fill);
  c = pow(c, vec3(0.92));
  gl_FragColor = vec4(c, 1.0);
}`

interface Bucket { key: ModelKey; mesh: THREE.InstancedMesh; parts: { mesh: THREE.InstancedMesh; pivot: THREE.Vector3; axis: THREE.Vector3; rpm: number }[]; cap: number; count: number }

export class ModelLayer implements CustomLayerInterface {
  id = 'models3d'
  type = 'custom' as const
  renderingMode = '3d' as const
  enabled = false
  private map: MlMap | null = null
  private renderer: THREE.WebGLRenderer | null = null
  private scene = new THREE.Scene()
  private camera = new THREE.Camera()
  private material: THREE.ShaderMaterial
  private buckets = new Map<string, Bucket>()
  private instances: ModelInstance[] = []
  private props: { model: ModelKey; lng: number; lat: number; heading: number; sx: number; sy: number; sz: number }[] = []
  private zoom = 0
  private t0 = performance.now()
  private tmp = new THREE.Matrix4(); private tmp2 = new THREE.Matrix4(); private q = new THREE.Quaternion(); private e = new THREE.Euler(); private v = new THREE.Vector3(); private s = new THREE.Vector3()

  constructor() {
    this.material = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, vertexColors: true, side: THREE.DoubleSide,
      uniforms: { uSun: { value: new THREE.Vector3(0.45, 0.35, 0.82).normalize() }, uFill: { value: new THREE.Vector3(-0.6, -0.5, 0.3).normalize() } } })
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true })
    this.renderer.autoClear = false
    this.scene.matrixWorldAutoUpdate = false
    for (const b of this.buckets.values()) this.scene.add(b.mesh, ...b.parts.map(p => p.mesh))
  }

  onRemove() { this.renderer?.dispose(); this.renderer = null; this.map = null }

  setInstances(list: ModelInstance[], zoom: number) { this.instances = list; this.zoom = zoom }

  /** Site props from layout features carrying a `model` property; fitted to the feature's footprint. */
  setProps(features: GeoJSON.Feature[]) {
    this.props = []
    for (const f of features) {
      const m = f.properties?.model as string | undefined
      if (!m || !PROP_MODELS.has(m) || f.geometry.type !== 'Polygon') continue
      const ring = f.geometry.coordinates[0]
      const [a, b, c] = ring
      const kx = 111_320 * Math.cos((a[1] * Math.PI) / 180)
      const len1 = Math.hypot((b[0] - a[0]) * kx, (b[1] - a[1]) * 110_540)
      const len2 = Math.hypot((c[0] - b[0]) * kx, (c[1] - b[1]) * 110_540)
      const cx = ring.slice(0, -1).reduce((s, p) => s + p[0], 0) / (ring.length - 1), cy = ring.slice(0, -1).reduce((s, p) => s + p[1], 0) / (ring.length - 1)
      const spec = MODEL_SPECS[m as ModelKey]
      const along = (Math.atan2((b[0] - a[0]) * kx, (b[1] - a[1]) * 110_540) * 180) / Math.PI
      const heading = typeof f.properties?.heading === 'number' ? f.properties.heading as number : along
      const isRound = m === 'radar_dome' || m === 'radar_rotating'
      const L = typeof f.properties?.heading === 'number' ? len1 : len1, W = len2
      this.props.push({ model: m as ModelKey, lng: cx, lat: cy, heading: m === 'shelter' ? heading : along,
        sx: isRound ? 1 : Math.max(0.5, Math.min(2, W / spec.widthM)), sy: isRound ? 1 : Math.max(0.5, Math.min(2, L / spec.lengthM)),
        sz: isRound ? 1 : Math.max(0.5, Math.min(2, ((f.properties?.height as number) || spec.heightM) / spec.heightM)) })
    }
  }

  private bucket(key: ModelKey): Bucket {
    let b = this.buckets.get(key)
    if (b) return b
    const built = buildModel(key)
    const mk = (geom: THREE.BufferGeometry, cap: number) => {
      const mesh = new THREE.InstancedMesh(geom, this.material, cap)
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cap * 3), 3)
      mesh.frustumCulled = false; mesh.matrixAutoUpdate = false; mesh.count = 0
      return mesh
    }
    const cap = 64
    b = { key, cap, count: 0, mesh: mk(built.geometry, cap),
      parts: built.parts.map(p => ({ mesh: mk(p.geometry, cap), pivot: new THREE.Vector3(...p.pivot), axis: new THREE.Vector3(p.axis === 'x' ? 1 : 0, p.axis === 'y' ? 1 : 0, p.axis === 'z' ? 1 : 0), rpm: p.rpm })) }
    this.buckets.set(key, b)
    this.scene.add(b.mesh, ...b.parts.map(p => p.mesh))
    return b
  }

  private grow(b: Bucket, need: number) {
    if (need <= b.cap) return
    const cap = Math.max(need, b.cap * 2)
    const regrow = (old: THREE.InstancedMesh) => {
      const mesh = new THREE.InstancedMesh(old.geometry, this.material, cap)
      mesh.instanceMatrix.setUsage(THREE.DynamicDrawUsage)
      mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cap * 3), 3)
      mesh.frustumCulled = false; mesh.matrixAutoUpdate = false; mesh.count = 0
      this.scene.remove(old); this.scene.add(mesh)
      return mesh
    }
    b.mesh = regrow(b.mesh)
    for (const p of b.parts) p.mesh = regrow(p.mesh)
    b.cap = cap
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    const map = this.map, renderer = this.renderer
    if (!map || !renderer || !this.enabled || (!this.instances.length && !this.props.length)) return
    const c = map.getCenter()
    const cx = (c.lng + 180) / 360
    const sinc = Math.sin((c.lat * Math.PI) / 180)
    const cy = 0.5 - Math.log((1 + sinc) / (1 - sinc)) / (4 * Math.PI)
    const m = options.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    const proj = this.camera.projectionMatrix
    proj.fromArray(Array.from(m) as number[])
    proj.multiply(this.tmp.makeTranslation(cx, cy, 0))
    this.camera.projectionMatrixInverse.copy(proj).invert()
    for (const b of this.buckets.values()) b.count = 0
    const terrain = !!map.getTerrain()
    const zoom = this.zoom
    const now = (performance.now() - this.t0) / 1000
    const place = (key: ModelKey, lng: number, lat: number, altM: number | null, heading: number, pitch: number, bank: number, tint: [number, number, number], scale: [number, number, number], spin: boolean) => {
      const spec = MODEL_SPECS[key]
      const b = this.bucket(key)
      this.grow(b, b.count + 1)
      const mpp = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** zoom
      const lenPx = spec.lengthM / mpp
      // Parked or taxiing aircraft sit in dense layouts: enlarge them far less than aircraft in flight.
      const parked = (spec.domain === 'air' || spec.domain === 'rotor') && (altM === null || altM < 30)
      const boost = parked ? Math.min(2.5, Math.max(1, 14 / lenPx)) : Math.min(MAX_BOOST[spec.domain] ?? 1, Math.max(1, (MIN_PX[spec.domain] ?? 0) / lenPx))
      const mPerUnit = 1 / (EARTH * Math.cos((lat * Math.PI) / 180))
      const sn = Math.sin((lat * Math.PI) / 180)
      const x = (lng + 180) / 360 - cx, y = 0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI) - cy
      const ground = terrain ? map.queryTerrainElevation([lng, lat]) ?? 0 : 0
      const z = (altM !== null && AIRBORNE.has(key) ? Math.max(altM, ground + 1) : ground) * mPerUnit
      const k = mPerUnit * boost
      // ENU orientation: yaw (clockwise from north) about z, pitch about the wing (x), bank about the nose (y).
      this.e.set((pitch * Math.PI) / 180, (bank * Math.PI) / 180, (-heading * Math.PI) / 180, 'ZXY')
      this.q.setFromEuler(this.e)
      this.tmp.compose(this.v.set(x, y, z), this.q, this.s.set(k * scale[0], k * scale[1], k * scale[2]))
      this.tmp.premultiply(this.tmp2.makeScale(1, -1, 1).setPosition(0, 0, 0)) // ENU → mercator (y south): reflect …
      this.tmp.elements[13] = y // … but keep the translation's own sign
      const i = b.count++
      b.mesh.setMatrixAt(i, this.tmp)
      b.mesh.instanceColor!.setXYZ(i, tint[0], tint[1], tint[2])
      for (const p of b.parts) {
        const ang = spin ? ((p.rpm / 60) * Math.PI * 2 * now) % (Math.PI * 2) : 0
        const r = this.tmp2.makeTranslation(p.pivot.x, p.pivot.y, p.pivot.z).multiply(new THREE.Matrix4().makeRotationAxis(p.axis, ang)).multiply(new THREE.Matrix4().makeTranslation(-p.pivot.x, -p.pivot.y, -p.pivot.z))
        p.mesh.setMatrixAt(i, new THREE.Matrix4().multiplyMatrices(this.tmp, r))
        p.mesh.instanceColor!.setXYZ(i, tint[0], tint[1], tint[2])
      }
    }
    for (const it of this.instances) {
      const key = (ALIAS[it.model] ?? it.model) as ModelKey
      if (!MODEL_SPECS[key]) continue
      const base = TINT[it.affiliation] ?? TINT.own
      const dim = it.condition === 'unavailable' ? 0.55 : it.condition === 'degraded' ? 0.82 : 1
      const tint: [number, number, number] = it.selected ? [0.55, 0.8, 1.25] : [base[0] * dim, base[1] * dim, base[2] * dim]
      place(key, it.lng, it.lat, it.alt, it.heading, it.pitch, it.bank, tint, [1, 1, 1], it.speed > 0.5 || key.startsWith('radar') || key === 'transport')
    }
    if (zoom >= 12) for (const p of this.props) place(p.model, p.lng, p.lat, null, p.heading, 0, 0, TINT.prop, [p.sx, p.sy, p.sz], p.model === 'radar_rotating')
    for (const b of this.buckets.values()) {
      b.mesh.count = b.count; b.mesh.instanceMatrix.needsUpdate = true; if (b.mesh.instanceColor) b.mesh.instanceColor.needsUpdate = true
      for (const p of b.parts) { p.mesh.count = b.count; p.mesh.instanceMatrix.needsUpdate = true; if (p.mesh.instanceColor) p.mesh.instanceColor.needsUpdate = true }
    }
    renderer.resetState()
    renderer.render(this.scene, this.camera)
    map.triggerRepaint()
    void gl
  }
}
