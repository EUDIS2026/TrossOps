/** Top-down silhouettes rendered from the procedural 3D models (orthographic, nose up) into sprite-atlas cells.
 * In 2D at street zoom a platform is drawn at true scale as what it is — a fighter on its shelter apron, a column of
 * IFVs on the road — instead of a frame symbol. One small offscreen WebGL renderer is created lazily and reused. */
import * as THREE from 'three'
import { buildModel, MODEL_SPECS, type ModelKey } from './three/models'
import { CELL } from './symbols'

const TINT: Record<string, number> = { own: 0xc9e6ff, allied: 0xb6f0cc, civil: 0xf0dcf0, unknown: 0xfff59a, hostile_suspected: 0xffa0a0 }
let renderer: THREE.WebGLRenderer | null = null
const geoms = new Map<string, THREE.BufferGeometry>()

export function hasTopdown(model: string | null | undefined): model is ModelKey { return !!model && model in MODEL_SPECS }

/** Fraction of the cell the model's longest side occupies (the sprite layer scales the cell to true size). */
export const TOPDOWN_FILL = 0.9

export function topdownImage(model: ModelKey, affiliation: string, selected = false): HTMLCanvasElement {
  const out = document.createElement('canvas'); out.width = CELL; out.height = CELL
  try {
    if (!renderer) {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true, preserveDrawingBuffer: true })
      renderer.setPixelRatio(1); renderer.setSize(CELL, CELL, false); renderer.setClearColor(0x000000, 0)
    }
    let g = geoms.get(model)
    if (!g) {
      const b = buildModel(model)
      g = b.geometry.clone()
      geoms.set(model, g)
    }
    const spec = MODEL_SPECS[model]
    const half = Math.max(spec.lengthM, spec.widthM) / 2 / TOPDOWN_FILL
    const cam = new THREE.OrthographicCamera(-half, half, half, -half, -500, 500)
    cam.position.set(0, 0, 200); cam.up.set(0, 1, 0); cam.lookAt(0, 0, 0)
    const scene = new THREE.Scene()
    const mat = new THREE.MeshLambertMaterial({ vertexColors: true, color: TINT[affiliation] ?? TINT.own })
    const mesh = new THREE.Mesh(g, mat)
    scene.add(mesh, new THREE.HemisphereLight(0xffffff, 0x404850, 1.6))
    const sun = new THREE.DirectionalLight(0xffffff, 1.4); sun.position.set(-0.6, 0.8, 1); scene.add(sun)
    renderer.render(scene, cam)
    const ctx = out.getContext('2d')!
    // dark outline for legibility on any basemap: draw the silhouette offset in eight directions, then the colour pass
    ctx.filter = 'brightness(0)'; ctx.globalAlpha = 0.85
    for (const [dx, dy] of [[-2, 0], [2, 0], [0, -2], [0, 2], [-1.5, -1.5], [1.5, 1.5], [-1.5, 1.5], [1.5, -1.5]]) ctx.drawImage(renderer.domElement, dx, dy)
    ctx.filter = 'none'; ctx.globalAlpha = 1
    ctx.drawImage(renderer.domElement, 0, 0)
    if (selected) { ctx.strokeStyle = '#4ea1ff'; ctx.lineWidth = 3; ctx.strokeRect(4, 4, CELL - 8, CELL - 8) }
    mat.dispose()
  } catch { /* no WebGL: the caller falls back to the frame symbol */ }
  return out
}
