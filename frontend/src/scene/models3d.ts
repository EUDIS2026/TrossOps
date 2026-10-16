/** Custom MapLibre WebGL layer drawing procedural low-poly 3D models for close-range inspection.
 * Geometry is generated in code (no third-party assets), metre-scaled, nose along +Y (north) before heading rotation.
 * Rendering mode "3d" shares MapLibre's depth buffer so models sit correctly against terrain and buildings. */
import { MercatorCoordinate, type CustomLayerInterface, type CustomRenderMethodInput, type Map as MlMap } from 'maplibre-gl'
import type { Condition, Affiliation } from '../contracts/types'

export interface ModelInstance { id: string; lng: number; lat: number; altM: number | null; headingDeg: number; modelKey: string; affiliation: Affiliation; condition: Condition; selected: boolean }


// ---- geometry builders (x east, y north, z up, metres) -----------------------------------------
function box(out: number[], cx: number, cy: number, cz: number, sx: number, sy: number, sz: number) {
  const x0 = cx - sx / 2, x1 = cx + sx / 2, y0 = cy - sy / 2, y1 = cy + sy / 2, z0 = cz - sz / 2, z1 = cz + sz / 2
  const faces: [number[], number[], number[], number[], number[]][] = [
    [[x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1], [0, 0, 1]], [[x0, y1, z0], [x1, y1, z0], [x1, y0, z0], [x0, y0, z0], [0, 0, -1]],
    [[x0, y1, z0], [x0, y1, z1], [x1, y1, z1], [x1, y1, z0], [0, 1, 0]], [[x1, y0, z0], [x1, y0, z1], [x0, y0, z1], [x0, y0, z0], [0, -1, 0]],
    [[x1, y1, z0], [x1, y1, z1], [x1, y0, z1], [x1, y0, z0], [1, 0, 0]], [[x0, y0, z0], [x0, y0, z1], [x0, y1, z1], [x0, y1, z0], [-1, 0, 0]],
  ]
  for (const [a, b, c, d, n] of faces) out.push(...a, ...n, ...b, ...n, ...c, ...n, ...a, ...n, ...c, ...n, ...d, ...n)
}
function prism(out: number[], pts: number[][], z0: number, z1: number) {
  // extruded convex polygon (counter-clockwise in x/y)
  const n = pts.length
  for (let i = 1; i < n - 1; i++) {
    out.push(pts[0][0], pts[0][1], z1, 0, 0, 1, pts[i][0], pts[i][1], z1, 0, 0, 1, pts[i + 1][0], pts[i + 1][1], z1, 0, 0, 1)
    out.push(pts[0][0], pts[0][1], z0, 0, 0, -1, pts[i + 1][0], pts[i + 1][1], z0, 0, 0, -1, pts[i][0], pts[i][1], z0, 0, 0, -1)
  }
  for (let i = 0; i < n; i++) {
    const a = pts[i], b = pts[(i + 1) % n]
    const nx = b[1] - a[1], ny = -(b[0] - a[0]), len = Math.hypot(nx, ny) || 1
    const N = [nx / len, ny / len, 0]
    out.push(a[0], a[1], z0, ...N, b[0], b[1], z0, ...N, b[0], b[1], z1, ...N, a[0], a[1], z0, ...N, b[0], b[1], z1, ...N, a[0], a[1], z1, ...N)
  }
}
function disc(out: number[], cx: number, cy: number, cz: number, r: number, h: number, segments = 14) {
  const pts: number[][] = []
  for (let i = 0; i < segments; i++) pts.push([cx + r * Math.cos((i / segments) * Math.PI * 2), cy + r * Math.sin((i / segments) * Math.PI * 2)])
  prism(out, pts, cz - h / 2, cz + h / 2)
}

const builders: Record<string, () => number[]> = {
  tank: () => { const o: number[] = []; box(o, 0, 0, 1.0, 3.6, 7.5, 1.6); box(o, 0, 0.6, 2.4, 2.4, 3.2, 1.0); box(o, 0, 5.5, 2.4, 0.3, 6.0, 0.3); box(o, -1.9, 0, 0.7, 0.5, 7.0, 1.0); box(o, 1.9, 0, 0.7, 0.5, 7.0, 1.0); return o },
  apc: () => { const o: number[] = []; prism(o, [[-1.6, -3.5], [1.6, -3.5], [1.6, 2.6], [0.9, 3.8], [-0.9, 3.8], [-1.6, 2.6]], 0.5, 2.4); box(o, 0, 0.5, 2.7, 1.2, 1.4, 0.6); return o },
  truck: () => { const o: number[] = []; box(o, 0, -1.4, 1.7, 2.5, 6.2, 2.6); box(o, 0, 3.0, 1.5, 2.4, 2.2, 2.3); return o },
  fuel: () => { const o: number[] = []; disc(o, 0, -1.4, 1.8, 1.2, 6.0, 10); box(o, 0, 3.0, 1.5, 2.4, 2.2, 2.3); box(o, 0, -1.4, 0.6, 2.4, 6.4, 0.5); return o },
  ambulance: () => { const o: number[] = []; box(o, 0, -0.8, 1.5, 2.3, 5.0, 2.4); box(o, 0, 2.5, 1.1, 2.2, 1.6, 1.7); return o },
  engineer: () => { const o: number[] = []; box(o, 0, -1.0, 1.6, 2.6, 6.0, 2.4); box(o, 0, 3.6, 0.9, 3.0, 1.2, 1.4); return o },
  airdef: () => { const o: number[] = []; box(o, 0, -0.8, 1.4, 2.6, 6.0, 2.0); box(o, 0, 0.0, 3.2, 1.0, 3.6, 0.9); box(o, 0, 0.0, 4.2, 0.2, 5.0, 0.2); return o },
  recovery: () => { const o: number[] = []; box(o, 0, -0.8, 1.6, 2.6, 6.4, 2.4); box(o, 0, -3.2, 3.6, 0.3, 0.3, 3.0); return o },
  cp: () => { const o: number[] = []; box(o, 0, -0.8, 1.7, 2.5, 6.0, 2.8); box(o, 0, 0, 4.0, 0.15, 0.15, 2.0); return o },
  signals: () => { const o: number[] = []; box(o, 0, -0.8, 1.6, 2.5, 6.0, 2.6); box(o, 0, -2.0, 5.0, 0.15, 0.15, 4.6); return o },
  fighter: () => { const o: number[] = []; prism(o, [[-0.9, -7], [0.9, -7], [0.7, 7.5], [-0.7, 7.5]], 0.6, 2.4); prism(o, [[-6, -4.5], [-0.8, 1.5], [0.8, 1.5], [6, -4.5], [6, -5.5], [-6, -5.5]], 1.0, 1.3); prism(o, [[-0.2, -6.5], [0.2, -6.5], [0.2, -3.5], [-0.2, -3.5]], 2.4, 5.0); return o },
  transport: () => { const o: number[] = []; prism(o, [[-1.6, -11], [1.6, -11], [1.3, 11], [-1.3, 11]], 1.0, 4.4); prism(o, [[-15, -1], [-1.5, 2], [1.5, 2], [15, -1], [15, -2.5], [-15, -2.5]], 3.6, 4.0); prism(o, [[-6, -10.5], [6, -10.5], [6, -9], [-6, -9]], 3.6, 4.0); prism(o, [[-0.3, -11], [0.3, -11], [0.3, -7], [-0.3, -7]], 4.4, 9.5); return o },
  isr: () => { const o: number[] = []; prism(o, [[-1.2, -9], [1.2, -9], [1.0, 9], [-1.0, 9]], 1.0, 3.4); prism(o, [[-18, -0.5], [-1.2, 1.5], [1.2, 1.5], [18, -0.5], [18, -1.8], [-18, -1.8]], 2.6, 3.0); disc(o, 0, 0, 0.4, 2.2, 0.8, 12); return o },
  helicopter: () => { const o: number[] = []; prism(o, [[-1.3, -3], [1.3, -3], [1.0, 4.5], [-1.0, 4.5]], 0.8, 3.4); prism(o, [[-0.4, -10], [0.4, -10], [0.6, -3], [-0.6, -3]], 2.0, 2.9); disc(o, 0, 0.5, 3.8, 7.2, 0.12, 18); box(o, 0, -9.6, 3.6, 0.1, 1.4, 1.4); return o },
  multirotor: () => { const o: number[] = []; box(o, 0, 0, 0.3, 0.5, 0.5, 0.25); for (const [x, y] of [[-0.6, 0.6], [0.6, 0.6], [-0.6, -0.6], [0.6, -0.6]]) { box(o, x / 2, y / 2, 0.3, Math.abs(x), 0.08, 0.08); disc(o, x, y, 0.4, 0.32, 0.03, 10) } return o },
  personnel: () => { const o: number[] = []; for (const [x, y] of [[-1.5, 0], [0, 1.2], [1.5, 0], [0, -1.2], [0, 0]]) { box(o, x, y, 0.9, 0.5, 0.35, 1.8); disc(o, x, y, 1.95, 0.16, 0.3, 8) } return o },
  corvette: () => { const o: number[] = []; prism(o, [[-5, -35], [5, -35], [5, 20], [0, 36], [-5, 20]], 0, 5); prism(o, [[-3.5, -12], [3.5, -12], [3.5, 10], [-3.5, 10]], 5, 11); box(o, 0, 2, 14, 1.2, 1.2, 6); return o },
  patrol_boat: () => { const o: number[] = []; prism(o, [[-3, -12], [3, -12], [3, 7], [0, 13], [-3, 7]], 0, 3); prism(o, [[-2, -5], [2, -5], [2, 3], [-2, 3]], 3, 6); return o },
  logistics_ship: () => { const o: number[] = []; prism(o, [[-8, -45], [8, -45], [8, 32], [0, 45], [-8, 32]], 0, 7); box(o, 0, -34, 13, 12, 14, 12); box(o, 0, 5, 9.5, 12, 40, 5); return o },
  mcm: () => { const o: number[] = []; prism(o, [[-4.5, -22], [4.5, -22], [4.5, 14], [0, 23], [-4.5, 14]], 0, 4); prism(o, [[-3, -6], [3, -6], [3, 6], [-3, 6]], 4, 9); return o },
  icebreaker: () => { const o: number[] = []; prism(o, [[-9, -38], [9, -38], [9, 26], [0, 40], [-9, 26]], 0, 8); box(o, 0, 5, 15, 12, 20, 14); return o },
  ferry: () => { const o: number[] = []; prism(o, [[-12, -70], [12, -70], [12, 55], [0, 72], [-12, 55]], 0, 8); box(o, 0, 0, 16, 22, 120, 16); return o },
  unknown_air: () => { const o: number[] = []; prism(o, [[-1.4, -9], [1.4, -9], [1.0, 9], [-1.0, 9]], 1.0, 4.0); prism(o, [[-9, -2], [-1.2, 1], [1.2, 1], [9, -2], [9, -3.5], [-9, -3.5]], 2.6, 3.2); return o },
  unknown_sea: () => { const o: number[] = []; prism(o, [[-4, -20], [4, -20], [4, 12], [0, 22], [-4, 12]], 0, 4); box(o, 0, -4, 7, 5, 8, 6); return o },
}

// Approximate length of each class in metres (used to keep models legible: never smaller than MIN_PX on screen).
const LENGTH_M: Record<string, number> = { tank: 10, apc: 8, truck: 9, fuel: 9, ambulance: 7, engineer: 8, airdef: 8, recovery: 9, cp: 8, signals: 8, fighter: 15, transport: 22, isr: 18, helicopter: 18, multirotor: 1.6, personnel: 4, corvette: 72, patrol_boat: 26, logistics_ship: 90, mcm: 46, icebreaker: 78, ferry: 140, unknown_air: 18, unknown_sea: 42 }
export const MIN_PX = 34

const VS = `#version 300 es
precision highp float;
in vec3 a_pos; in vec3 a_norm;
uniform mat4 u_mvp; uniform mat4 u_model; uniform vec3 u_light;
out float v_light; out vec3 v_norm;
void main() {
  vec3 n = normalize(mat3(u_model) * a_norm);
  v_light = 0.55 + 0.45 * max(dot(n, normalize(u_light)), 0.0);
  gl_Position = u_mvp * u_model * vec4(a_pos, 1.0);
}`
const FS = `#version 300 es
precision highp float;
in float v_light; uniform vec4 u_color; out vec4 fragColor;
void main() { fragColor = vec4(u_color.rgb * v_light, 1.0) * u_color.a; }`

const COLORS: Record<Affiliation, [number, number, number]> = { own: [0.86, 0.9, 0.94], allied: [0.55, 0.8, 0.72], civil: [0.68, 0.72, 0.76], unknown: [0.89, 0.55, 0.78], hostile_suspected: [0.94, 0.4, 0.36] }

export class ModelLayer implements CustomLayerInterface {
  id = 'entity-models'
  type = 'custom' as const
  renderingMode = '3d' as const
  instances: ModelInstance[] = []
  enabled = false
  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private meshes = new Map<string, { vao: WebGLVertexArrayObject; count: number }>()
  private uniforms: Record<string, WebGLUniformLocation | null> = {}

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map; this.gl = gl
    const compile = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader'); return s }
    const p = gl.createProgram()!
    gl.attachShader(p, compile(gl.VERTEX_SHADER, VS)); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link')
    this.program = p
    for (const name of ['u_mvp', 'u_model', 'u_light', 'u_color']) this.uniforms[name] = gl.getUniformLocation(p, name)
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    for (const m of this.meshes.values()) gl.deleteVertexArray(m.vao)
    this.meshes.clear()
    if (this.program) gl.deleteProgram(this.program)
    this.program = null; this.gl = null; this.map = null
  }

  private mesh(key: string): { vao: WebGLVertexArrayObject; count: number } {
    const gl = this.gl!
    const cached = this.meshes.get(key)
    if (cached) return cached
    const data = new Float32Array((builders[key] ?? builders.truck)())
    const vao = gl.createVertexArray()!
    gl.bindVertexArray(vao)
    const buf = gl.createBuffer()!
    gl.bindBuffer(gl.ARRAY_BUFFER, buf); gl.bufferData(gl.ARRAY_BUFFER, data, gl.STATIC_DRAW)
    const aPos = gl.getAttribLocation(this.program!, 'a_pos'), aNorm = gl.getAttribLocation(this.program!, 'a_norm')
    gl.enableVertexAttribArray(aPos); gl.vertexAttribPointer(aPos, 3, gl.FLOAT, false, 24, 0)
    gl.enableVertexAttribArray(aNorm); gl.vertexAttribPointer(aNorm, 3, gl.FLOAT, false, 24, 12)
    gl.bindVertexArray(null)
    const m = { vao, count: data.length / 6 }
    this.meshes.set(key, m)
    return m
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    if (!this.enabled || !this.program || !this.map || !this.instances.length) return
    const zoom = this.map.getZoom()
    if (zoom < 12.5) return
    gl.useProgram(this.program)
    gl.enable(gl.DEPTH_TEST); gl.depthFunc(gl.LEQUAL)
    gl.disable(gl.CULL_FACE)
    gl.uniformMatrix4fv(this.uniforms.u_mvp, false, options.defaultProjectionData.mainMatrix as Float32Array)
    gl.uniform3f(this.uniforms.u_light, 0.4, -0.6, 1.0)
    const hasTerrain = !!this.map.getTerrain()
    for (const inst of this.instances) {
      let ground = 0
      if (hasTerrain) ground = this.map.queryTerrainElevation([inst.lng, inst.lat]) ?? 0
      const alt = inst.altM === null ? ground : (['fighter', 'transport', 'isr', 'helicopter', 'multirotor', 'unknown_air'].includes(inst.modelKey) ? Math.max(inst.altM, ground + 2) : ground)
      const mc = MercatorCoordinate.fromLngLat([inst.lng, inst.lat], alt)
      // metres per screen pixel at this latitude and zoom; scale the model up when it would be smaller than MIN_PX
      const mpp = (156543.03392 * Math.cos((inst.lat * Math.PI) / 180)) / 2 ** zoom
      const lengthPx = (LENGTH_M[inst.modelKey] ?? 10) / mpp
      const boost = lengthPx < MIN_PX ? MIN_PX / lengthPx : 1
      const s = mc.meterInMercatorCoordinateUnits() * boost
      // Local frame: x east, y north (nose), z up, metres. Heading θ clockwise from north.
      // Mercator frame: x east, y south, z up. The matrix below maps e_x→(cosθ, sinθ), e_y→(sinθ, −cosθ) so the
      // nose points along the heading and north maps to −y. The mapping mirrors handedness, so face culling is off.
      const th = (inst.headingDeg * Math.PI) / 180
      const c = Math.cos(th), si = Math.sin(th)
      const model = new Float32Array([
        s * c, s * si, 0, 0,
        s * si, -s * c, 0, 0,
        0, 0, s, 0,
        mc.x, mc.y, mc.z, 1,
      ])
      gl.uniformMatrix4fv(this.uniforms.u_model, false, model)
      const col = COLORS[inst.affiliation]
      const dim = inst.condition === 'unavailable' ? 0.55 : inst.condition === 'degraded' ? 0.85 : 1
      const sel = inst.selected ? [0.36, 0.55, 0.94] : col
      gl.uniform4f(this.uniforms.u_color, sel[0] * dim, sel[1] * dim, sel[2] * dim, 1)
      const m = this.mesh(inst.modelKey)
      gl.bindVertexArray(m.vao)
      gl.drawArrays(gl.TRIANGLES, 0, m.count)
    }
    gl.bindVertexArray(null)
  }
}
