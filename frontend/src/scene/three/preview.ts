/** Dev-only preview of the procedural model library: /model-preview.html
 * Params: ?key=fighter&close=1 (single model, true scale) · ?cat=air|rotor|ground|sea|site · &tint=own|allied|civil|unknown|hostile|none
 *         &az=45&el=30 (camera azimuth/elevation, degrees) · &dist=… (close-up distance factor) · &real=1 (grid at true scale) · &spin=0 */
import { ACESFilmicToneMapping, Box3, Color, DirectionalLight, Group, HemisphereLight, Mesh, MeshStandardMaterial, PCFShadowMap, PerspectiveCamera, PlaneGeometry, Scene, SRGBColorSpace, Vector3, WebGLRenderer, GridHelper } from 'three'
import { OrbitControls } from 'three/examples/jsm/controls/OrbitControls.js'
import { CSS2DObject, CSS2DRenderer } from 'three/examples/jsm/renderers/CSS2DRenderer.js'
import { MODEL_KEYS, MODEL_SPECS, buildModel, type ModelKey } from './models'

const TINTS: Record<string, string> = { own: '#b0c4de', allied: '#9fd8a4', civil: '#cfcfcf', unknown: '#e8a6ec', hostile: '#f28b82', none: '#ffffff' }
const q = new URLSearchParams(location.search)
const keyParam = q.get('key') as ModelKey | null
const close = q.get('close') === '1' && keyParam !== null
const cat = q.get('cat')
const tint = new Color(TINTS[q.get('tint') ?? 'own'] ?? TINTS.own)
const az = (Number(q.get('az') ?? (close ? 140 : 0)) * Math.PI) / 180
const el = (Number(q.get('el') ?? (close ? 28 : 50)) * Math.PI) / 180
const spin = q.get('spin') !== '0'
const real = q.get('real') === '1'

const renderer = new WebGLRenderer({ antialias: true })
renderer.setPixelRatio(Math.min(2, devicePixelRatio))
renderer.setSize(innerWidth, innerHeight)
renderer.outputColorSpace = SRGBColorSpace
renderer.toneMapping = ACESFilmicToneMapping
renderer.shadowMap.enabled = true
renderer.shadowMap.type = PCFShadowMap
document.body.appendChild(renderer.domElement)
const labels = new CSS2DRenderer()
labels.setSize(innerWidth, innerHeight)
Object.assign(labels.domElement.style, { position: 'fixed', top: '0', left: '0', pointerEvents: 'none' })
document.body.appendChild(labels.domElement)

const scene = new Scene()
scene.background = new Color('#0b0f14')
const camera = new PerspectiveCamera(close ? 26 : 35, innerWidth / innerHeight, 0.1, 5000)
camera.up.set(0, 0, 1)
scene.add(new HemisphereLight('#dfe8f5', '#30353d', 0.85))
const sun = new DirectionalLight('#ffffff', 1.6)
sun.castShadow = true
sun.shadow.mapSize.set(4096, 4096)
sun.shadow.bias = -0.0004
sun.shadow.normalBias = 0.02
scene.add(sun, sun.target)

const material = new MeshStandardMaterial({ vertexColors: true, color: tint, roughness: 0.72, metalness: 0.08 })
const spinners: { g: Group; axis: 'x' | 'y' | 'z'; rpm: number }[] = []

const list = q.get('keys')?.split(',').filter((k): k is ModelKey => k in MODEL_SPECS)
const keys = keyParam ? [keyParam] : list?.length ? list : MODEL_KEYS.filter(k => !cat || MODEL_SPECS[k].domain === cat)
const order = ['air', 'rotor', 'ground', 'sea', 'site']
if (!list?.length) keys.sort((a, b) => order.indexOf(MODEL_SPECS[a].domain) - order.indexOf(MODEL_SPECS[b].domain))

const cell = 14
const cols = Math.max(1, Math.ceil(Math.sqrt(keys.length * 1.6)))
const world = new Box3()
let triTotal = 0
keys.forEach((key, i) => {
  const m = buildModel(key)
  const root = new Group()
  const mesh = new Mesh(m.geometry, material)
  mesh.castShadow = mesh.receiveShadow = true
  root.add(mesh)
  let tris = m.geometry.getAttribute('position').count / 3
  for (const p of m.parts) {
    const pivot = new Group()
    pivot.position.set(...p.pivot)
    const pm = new Mesh(p.geometry, material)
    pm.position.set(-p.pivot[0], -p.pivot[1], -p.pivot[2])
    pm.castShadow = true
    pivot.add(pm)
    root.add(pivot)
    spinners.push({ g: pivot, axis: p.axis, rpm: p.rpm })
    tris += p.geometry.getAttribute('position').count / 3
  }
  triTotal += tris
  const s = m.spec
  if (!close) {
    const scale = real ? 0.25 : (cell * 0.72) / Math.max(s.lengthM, s.widthM, s.heightM * 1.3)
    root.scale.setScalar(scale)
    const c = i % cols, r = Math.floor(i / cols)
    root.position.set((c - (cols - 1) / 2) * cell, -r * cell, 0)
    const lbl = document.createElement('div')
    lbl.className = 'lbl'
    lbl.innerHTML = `${key}<small>${s.lengthM}×${s.widthM}×${s.heightM} m · ${tris} tris</small>`
    const o = new CSS2DObject(lbl)
    o.position.set(0, -cell * 0.42 / scale, 0)
    root.add(o)
  }
  scene.add(root)
  root.updateMatrixWorld(true)
  world.expandByObject(root)
})

const size = world.getSize(new Vector3()), center = world.getCenter(new Vector3())
const span = Math.max(size.x, size.y, size.z * 1.5)
const ground = new Mesh(new PlaneGeometry(span * 6 + 50, span * 6 + 50), new MeshStandardMaterial({ color: '#1c222b', roughness: 1 }))
ground.position.set(center.x, center.y, -0.02)
ground.receiveShadow = true
scene.add(ground)
const grid = new GridHelper(span * 4 + 40, close ? Math.round(span * 4 + 40) / (span > 60 ? 10 : 1) : 40, '#2a3340', '#222a34')
grid.rotation.x = Math.PI / 2
grid.position.set(center.x, center.y, -0.01)
scene.add(grid)

const vf = (camera.fov * Math.PI) / 360, hf = Math.atan(Math.tan(vf) * camera.aspect)
const fit = (size.length() / 2) / Math.sin(Math.min(vf, hf)) * (close ? 0.95 : 0.6)
const dist = fit * Number(q.get('dist') ?? 1)
const target = close ? center.clone().setZ(center.z * 0.8) : center.clone().setZ(0)
camera.position.set(target.x + dist * Math.cos(el) * Math.sin(az), target.y - dist * Math.cos(el) * Math.cos(az), target.z + dist * Math.sin(el))
const controls = new OrbitControls(camera, labels.domElement)
labels.domElement.style.pointerEvents = 'auto'
controls.target.copy(target)
controls.update()

const saz = az - 0.6
sun.position.set(center.x + span * Math.sin(saz), center.y - span * Math.cos(saz), span * 1.3)
sun.target.position.copy(center)
const sc = sun.shadow.camera
sc.left = sc.bottom = -span * 0.8
sc.right = sc.top = span * 0.8
sc.near = 0.1
sc.far = span * 4
sc.updateProjectionMatrix()

const hud = document.getElementById('hud')!
hud.innerHTML = `<b>TrossOps procedural models</b> — ${keys.length} models, ${triTotal} tris · tint ${q.get('tint') ?? 'own'} · ` +
  ['air', 'rotor', 'ground', 'sea', 'site'].map(c => `<a href="?cat=${c}">${c}</a>`).join('') + '<a href="?">all</a>'

addEventListener('resize', () => {
  camera.aspect = innerWidth / innerHeight
  camera.updateProjectionMatrix()
  renderer.setSize(innerWidth, innerHeight)
  labels.setSize(innerWidth, innerHeight)
})

let last = performance.now()
renderer.setAnimationLoop(now => {
  const dt = (now - last) / 1000
  last = now
  if (spin) for (const s of spinners) s.g.rotation[s.axis] += (Math.min(s.rpm, 90) / 60) * Math.PI * 2 * dt
  controls.update()
  renderer.render(scene, camera)
  labels.render(scene, camera)
  ;(window as unknown as { __ready?: boolean }).__ready = true
})
