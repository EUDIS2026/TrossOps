/** 3D layer: the procedural model library (`three/models.ts`) drawn inside MapLibre with three.js, one InstancedMesh
 * per model key (plus one per moving part — rotors, propellers, radar antennas — animated per frame).
 *
 * Frames: models are built in ENU metres (x east, y north/nose, z up). MapLibre's mercator space has y pointing south,
 * so the instance matrix includes a reflection. Instead of fighting face culling, a small two-sided shader lights
 * with the model's true outward normals (reflected consistently with the light), so shading is correct either way.
 * Precision: instances are positioned relative to an anchor snapped to a ~2.4 km grid near the camera (float64 on
 * the CPU), so float32 offsets stay small while static site props keep valid matrices as the camera moves locally.
 * Cost: static props (shelters, hangars, barracks …) live in their own instance buffers, rebuilt only when the
 * props, the anchor or the terrain under them change; per frame only moving platforms are re-uploaded. The layer
 * never schedules repaints itself: `wantsFrame()` tells the scene controller when something animates.
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
type Built = ReturnType<typeof buildModel>
const ANCHOR_GRID = 16384 // anchor cell = 1/16384 of the world (~2.4 km at the equator)

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
  private geoms = new Map<ModelKey, Built>()
  private dyn = new Map<string, Bucket>()   // platforms: rewritten every frame
  private stat = new Map<string, Bucket>()  // site props: rewritten only when stale
  private instances: ModelInstance[] = []
  private props: { model: ModelKey; lng: number; lat: number; heading: number; sx: number; sy: number; sz: number }[] = []
  private propsVersion = 0
  private statKey = ''
  private statBuiltAt = 0
  private statGroundAt = 0
  private zoom = 0
  private sig = NaN
  private changed = true
  private animating = false
  private t0 = performance.now()
  private tmp = new THREE.Matrix4(); private tmp2 = new THREE.Matrix4(); private tmp3 = new THREE.Matrix4(); private tmp4 = new THREE.Matrix4()
  private q = new THREE.Quaternion(); private e = new THREE.Euler(); private v = new THREE.Vector3(); private s = new THREE.Vector3()
  private reflect = new THREE.Matrix4().makeScale(1, -1, 1)

  constructor() {
    this.material = new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, vertexColors: true, side: THREE.DoubleSide,
      uniforms: { uSun: { value: new THREE.Vector3(0.45, 0.35, 0.82).normalize() }, uFill: { value: new THREE.Vector3(-0.6, -0.5, 0.3).normalize() } } })
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    this.renderer = new THREE.WebGLRenderer({ canvas: map.getCanvas(), context: gl, antialias: true })
    this.renderer.autoClear = false
    this.scene.matrixWorldAutoUpdate = false
    for (const set of [this.dyn, this.stat]) for (const b of set.values()) this.scene.add(b.mesh, ...b.parts.map(p => p.mesh))
    this.statKey = ''
  }

  onRemove() { this.renderer?.dispose(); this.renderer = null; this.map = null }

  setInstances(list: ModelInstance[], zoom: number) {
    // cheap fingerprint: a parked fleet produces the same list every frame and needs no repaint
    let sig = list.length + zoom * 1e-3
    for (const it of list) sig += it.lng * 7.13 + it.lat * 3.17 + it.heading * 1e-3 + (it.selected ? 0.5 : 0)
    if (sig !== this.sig) { this.sig = sig; this.changed = true }
    this.instances = list; this.zoom = zoom
  }

  /** True when the next frame would look different: platforms moved, a rotor or radar spins, or props changed. */
  wantsFrame() { return this.enabled && !!this.map && (this.changed || this.animating) }

  /** Site props from layout features carrying a `model` property; fitted to the feature's footprint. */
  setProps(features: GeoJSON.Feature[]) {
    this.props = []
    this.propsVersion++
    this.changed = true
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
      this.props.push({ model: m as ModelKey, lng: cx, lat: cy, heading: m === 'shelter' ? heading : along,
        sx: isRound ? 1 : Math.max(0.5, Math.min(2, len2 / spec.widthM)), sy: isRound ? 1 : Math.max(0.5, Math.min(2, len1 / spec.lengthM)),
        sz: isRound ? 1 : Math.max(0.5, Math.min(2, ((f.properties?.height as number) || spec.heightM) / spec.heightM)) })
    }
  }

  private built(key: ModelKey): Built {
    let b = this.geoms.get(key)
    if (!b) { b = buildModel(key); this.geoms.set(key, b) }
    return b
  }

  private mkMesh(geom: THREE.BufferGeometry, cap: number, dynamic: boolean) {
    const mesh = new THREE.InstancedMesh(geom, this.material, cap)
    mesh.instanceMatrix.setUsage(dynamic ? THREE.DynamicDrawUsage : THREE.StaticDrawUsage)
    mesh.instanceColor = new THREE.InstancedBufferAttribute(new Float32Array(cap * 3), 3)
    mesh.frustumCulled = false; mesh.matrixAutoUpdate = false; mesh.count = 0
    return mesh
  }

  private bucket(set: Map<string, Bucket>, key: ModelKey): Bucket {
    let b = set.get(key)
    if (b) return b
    const built = this.built(key)
    const dynamic = set === this.dyn
    const cap = 64
    b = { key, cap, count: 0, mesh: this.mkMesh(built.geometry, cap, dynamic),
      parts: built.parts.map(p => ({ mesh: this.mkMesh(p.geometry, cap, dynamic), pivot: new THREE.Vector3(...p.pivot), axis: new THREE.Vector3(p.axis === 'x' ? 1 : 0, p.axis === 'y' ? 1 : 0, p.axis === 'z' ? 1 : 0), rpm: p.rpm })) }
    set.set(key, b)
    this.scene.add(b.mesh, ...b.parts.map(p => p.mesh))
    return b
  }

  private grow(set: Map<string, Bucket>, b: Bucket, need: number) {
    if (need <= b.cap) return
    const cap = Math.max(need, b.cap * 2)
    const dynamic = set === this.dyn
    const regrow = (old: THREE.InstancedMesh) => {
      const mesh = this.mkMesh(old.geometry, cap, dynamic)
      ;(mesh.instanceMatrix.array as Float32Array).set((old.instanceMatrix.array as Float32Array).subarray(0, old.instanceMatrix.array.length))
      ;(mesh.instanceColor!.array as Float32Array).set((old.instanceColor!.array as Float32Array).subarray(0, old.instanceColor!.array.length))
      mesh.visible = old.visible
      this.scene.remove(old); this.scene.add(mesh)
      return mesh
    }
    b.mesh = regrow(b.mesh)
    for (const p of b.parts) p.mesh = regrow(p.mesh)
    b.cap = cap
  }

  /** Write one instance into a bucket set, relative to the anchor (ax, ay). */
  private place(set: Map<string, Bucket>, ax: number, ay: number, now: number, key: ModelKey, lng: number, lat: number, altM: number | null,
                heading: number, pitch: number, bank: number, tint: [number, number, number], scale: [number, number, number], spin: boolean) {
    const map = this.map!
    const spec = MODEL_SPECS[key]
    const b = this.bucket(set, key)
    this.grow(set, b, b.count + 1)
    const mpp = (156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** this.zoom
    const lenPx = spec.lengthM / mpp
    // Parked or taxiing aircraft sit in dense layouts: enlarge them far less than aircraft in flight.
    const parked = (spec.domain === 'air' || spec.domain === 'rotor') && (altM === null || altM < 30)
    const boost = parked ? Math.min(2.5, Math.max(1, 14 / lenPx)) : Math.min(MAX_BOOST[spec.domain] ?? 1, Math.max(1, (MIN_PX[spec.domain] ?? 0) / lenPx))
    const mPerUnit = 1 / (EARTH * Math.cos((lat * Math.PI) / 180))
    const sn = Math.sin((lat * Math.PI) / 180)
    const x = (lng + 180) / 360 - ax, y = 0.5 - Math.log((1 + sn) / (1 - sn)) / (4 * Math.PI) - ay
    const ground = map.getTerrain() ? map.queryTerrainElevation([lng, lat]) ?? 0 : 0
    const z = (altM !== null && AIRBORNE.has(key) ? Math.max(altM, ground + 1) : ground) * mPerUnit
    const k = mPerUnit * boost
    // ENU orientation: yaw (clockwise from north) about z, pitch about the wing (x), bank about the nose (y).
    this.e.set((pitch * Math.PI) / 180, (bank * Math.PI) / 180, (-heading * Math.PI) / 180, 'ZXY')
    this.q.setFromEuler(this.e)
    this.tmp.compose(this.v.set(x, y, z), this.q, this.s.set(k * scale[0], k * scale[1], k * scale[2]))
    this.tmp.premultiply(this.reflect) // ENU → mercator (y south): reflect …
    this.tmp.elements[13] = y // … but keep the translation's own sign
    const i = b.count++
    b.mesh.setMatrixAt(i, this.tmp)
    b.mesh.instanceColor!.setXYZ(i, tint[0], tint[1], tint[2])
    for (const p of b.parts) {
      const ang = spin ? ((p.rpm / 60) * Math.PI * 2 * now) % (Math.PI * 2) : 0
      if (spin && p.rpm) this.animating = true
      this.tmp2.makeTranslation(p.pivot.x, p.pivot.y, p.pivot.z).multiply(this.tmp3.makeRotationAxis(p.axis, ang)).multiply(this.tmp4.makeTranslation(-p.pivot.x, -p.pivot.y, -p.pivot.z))
      p.mesh.setMatrixAt(i, this.tmp3.multiplyMatrices(this.tmp, this.tmp2))
      p.mesh.instanceColor!.setXYZ(i, tint[0], tint[1], tint[2])
    }
  }

  private flush(set: Map<string, Bucket>) {
    for (const b of set.values()) {
      b.mesh.count = b.count; b.mesh.instanceMatrix.needsUpdate = true; if (b.mesh.instanceColor) b.mesh.instanceColor.needsUpdate = true
      for (const p of b.parts) { p.mesh.count = b.count; p.mesh.instanceMatrix.needsUpdate = true; if (p.mesh.instanceColor) p.mesh.instanceColor.needsUpdate = true }
    }
  }

  private showSet(set: Map<string, Bucket>, on: boolean) {
    for (const b of set.values()) { b.mesh.visible = on; for (const p of b.parts) p.mesh.visible = on }
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    const map = this.map, renderer = this.renderer
    this.changed = false
    this.animating = false
    if (!map || !renderer || !this.enabled || (!this.instances.length && !this.props.length)) return
    const c = map.getCenter()
    const sinc = Math.sin((c.lat * Math.PI) / 180)
    const ax = Math.round(((c.lng + 180) / 360) * ANCHOR_GRID) / ANCHOR_GRID
    const ay = Math.round((0.5 - Math.log((1 + sinc) / (1 - sinc)) / (4 * Math.PI)) * ANCHOR_GRID) / ANCHOR_GRID
    const m = options.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    const proj = this.camera.projectionMatrix
    for (let i = 0; i < 16; i++) proj.elements[i] = m[i]
    proj.multiply(this.tmp.makeTranslation(ax, ay, 0))
    this.camera.projectionMatrixInverse.copy(proj).invert()
    const now = (performance.now() - this.t0) / 1000
    const wall = performance.now()
    // site props: static buffers, rebuilt when stale (new props, anchor moved, or terrain still loading under them)
    const showProps = this.zoom >= 12 && this.props.length > 0
    if (showProps) {
      const terrain = !!map.getTerrain()
      const key = `${this.propsVersion}|${ax}|${ay}|${terrain}`
      const settling = terrain && wall - this.statBuiltAt < 12_000 && wall - this.statGroundAt > 1500
      if (key !== this.statKey || settling) {
        if (key !== this.statKey) this.statBuiltAt = wall
        this.statKey = key; this.statGroundAt = wall
        for (const b of this.stat.values()) b.count = 0
        for (const p of this.props) if (p.model !== 'radar_rotating') this.place(this.stat, ax, ay, now, p.model, p.lng, p.lat, null, p.heading, 0, 0, TINT.prop, [p.sx, p.sy, p.sz], false)
        this.flush(this.stat)
      }
    }
    this.showSet(this.stat, showProps)
    // platforms (and the few spinning props): every frame
    for (const b of this.dyn.values()) b.count = 0
    for (const it of this.instances) {
      const key = (ALIAS[it.model] ?? it.model) as ModelKey
      if (!MODEL_SPECS[key]) continue
      const base = TINT[it.affiliation] ?? TINT.own
      const dim = it.condition === 'unavailable' ? 0.55 : it.condition === 'degraded' ? 0.82 : 1
      const tint: [number, number, number] = it.selected ? [0.55, 0.8, 1.25] : [base[0] * dim, base[1] * dim, base[2] * dim]
      if (it.speed > 0.5) this.animating = true
      this.place(this.dyn, ax, ay, now, key, it.lng, it.lat, it.alt, it.heading, it.pitch, it.bank, tint, [1, 1, 1], it.speed > 0.5 || key.startsWith('radar') || key === 'transport')
    }
    if (showProps) for (const p of this.props) if (p.model === 'radar_rotating') this.place(this.dyn, ax, ay, now, p.model, p.lng, p.lat, null, p.heading, 0, 0, TINT.prop, [p.sx, p.sy, p.sz], true)
    this.flush(this.dyn)
    renderer.resetState()
    renderer.render(this.scene, this.camera)
    void gl
  }
}
