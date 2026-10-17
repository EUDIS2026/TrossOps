/** Animated wind streamlines from the real Open-Meteo 10 m wind grid. Particles are advected through the
 * bilinearly interpolated field (time-lapsed so motion is visible) and drawn as short fading streaks coloured by
 * speed. Positions are rendered relative to the camera centre, like the sprite layer. */
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MlMap } from 'maplibre-gl'

export interface WindPoint { lng: number; lat: number; windMps: number | null; windDirDeg: number | null }

const N = 2600
const TAIL = 12
const PX_PER_S_AT_10MPS = 45 // screen-relative time-lapse: a 10 m/s wind moves ~45 px per second at any zoom
const VS = `#version 300 es
precision highp float;
in vec3 a_pos; in float a_alpha; in float a_speed;
uniform mat4 u_mvp;
out float v_alpha; out float v_speed;
void main() { gl_Position = u_mvp * vec4(a_pos, 1.0); v_alpha = a_alpha; v_speed = a_speed; }`
const FS = `#version 300 es
precision highp float;
in float v_alpha; in float v_speed; out vec4 o;
void main() {
  vec3 calm = vec3(0.35, 0.62, 0.95), mid = vec3(0.55, 0.95, 0.85), strong = vec3(1.0, 0.92, 0.55), gale = vec3(1.0, 0.45, 0.4);
  float s = v_speed;
  vec3 c = s < 6.0 ? mix(calm, mid, s / 6.0) : s < 14.0 ? mix(mid, strong, (s - 6.0) / 8.0) : mix(strong, gale, clamp((s - 14.0) / 8.0, 0.0, 1.0));
  o = vec4(c * v_alpha, v_alpha);
}`

export class WindLayer implements CustomLayerInterface {
  id = 'wind-particles'
  type = 'custom' as const
  renderingMode = '2d' as const
  enabled = false
  private map: MlMap | null = null
  private prog: WebGLProgram | null = null
  private buf: WebGLBuffer | null = null
  private vao: WebGLVertexArrayObject | null = null
  private loc: Record<string, number> = {}
  private uni: WebGLUniformLocation | null = null
  private grid: { lng0: number; lat0: number; dlng: number; dlat: number; nx: number; ny: number; u: Float32Array; v: Float32Array } | null = null
  private px = new Float64Array(N * TAIL); private py = new Float64Array(N * TAIL)
  private age = new Float32Array(N)
  private last = 0
  private frame = 0

  setField(points: WindPoint[]) {
    const pts = points.filter(p => p.windMps != null && p.windDirDeg != null)
    if (pts.length < 4) { this.grid = null; return }
    const lngs = [...new Set(pts.map(p => +p.lng.toFixed(4)))].sort((a, b) => a - b)
    const lats = [...new Set(pts.map(p => +p.lat.toFixed(4)))].sort((a, b) => a - b)
    const nx = lngs.length, ny = lats.length
    const u = new Float32Array(nx * ny), v = new Float32Array(nx * ny)
    for (const p of pts) {
      const i = lngs.indexOf(+p.lng.toFixed(4)), j = lats.indexOf(+p.lat.toFixed(4))
      const r = ((p.windDirDeg as number) * Math.PI) / 180, s = p.windMps as number
      u[j * nx + i] = -s * Math.sin(r); v[j * nx + i] = -s * Math.cos(r) // meteorological "from" → flow vector
    }
    this.grid = { lng0: lngs[0], lat0: lats[0], dlng: (lngs[nx - 1] - lngs[0]) / (nx - 1), dlat: (lats[ny - 1] - lats[0]) / (ny - 1), nx, ny, u, v }
    for (let k = 0; k < N; k++) this.respawn(k)
  }

  private sample(lng: number, lat: number): [number, number] {
    const g = this.grid!
    const fx = (lng - g.lng0) / g.dlng, fy = (lat - g.lat0) / g.dlat
    if (fx < 0 || fy < 0 || fx > g.nx - 1 || fy > g.ny - 1) return [NaN, NaN]
    const i = Math.min(Math.floor(fx), g.nx - 2), j = Math.min(Math.floor(fy), g.ny - 2), tx = fx - i, ty = fy - j
    const at = (a: Float32Array, ii: number, jj: number) => a[jj * g.nx + ii]
    const lerp = (a: Float32Array) => (at(a, i, j) * (1 - tx) + at(a, i + 1, j) * tx) * (1 - ty) + (at(a, i, j + 1) * (1 - tx) + at(a, i + 1, j + 1) * tx) * ty
    return [lerp(g.u), lerp(g.v)]
  }

  private respawn(k: number) {
    const g = this.grid!
    const lng = g.lng0 + Math.random() * g.dlng * (g.nx - 1), lat = g.lat0 + Math.random() * g.dlat * (g.ny - 1)
    for (let t = 0; t < TAIL; t++) { this.px[k * TAIL + t] = lng; this.py[k * TAIL + t] = lat }
    this.age[k] = Math.random() * 80
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    const sh = (t: number, src: string) => { const s = gl.createShader(t)!; gl.shaderSource(s, src); gl.compileShader(s); return s }
    const p = gl.createProgram()!
    gl.attachShader(p, sh(gl.VERTEX_SHADER, VS)); gl.attachShader(p, sh(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p)
    this.prog = p
    for (const a of ['a_pos', 'a_alpha', 'a_speed']) this.loc[a] = gl.getAttribLocation(p, a)
    this.uni = gl.getUniformLocation(p, 'u_mvp')
    this.vao = gl.createVertexArray(); gl.bindVertexArray(this.vao)
    this.buf = gl.createBuffer(); gl.bindBuffer(gl.ARRAY_BUFFER, this.buf)
    const st = 5 * 4
    gl.enableVertexAttribArray(this.loc.a_pos); gl.vertexAttribPointer(this.loc.a_pos, 3, gl.FLOAT, false, st, 0)
    gl.enableVertexAttribArray(this.loc.a_alpha); gl.vertexAttribPointer(this.loc.a_alpha, 1, gl.FLOAT, false, st, 12)
    gl.enableVertexAttribArray(this.loc.a_speed); gl.vertexAttribPointer(this.loc.a_speed, 1, gl.FLOAT, false, st, 16)
    gl.bindVertexArray(null)
  }

  onRemove(_m: MlMap, gl: WebGL2RenderingContext) { if (this.prog) gl.deleteProgram(this.prog); if (this.buf) gl.deleteBuffer(this.buf); this.map = null }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    const map = this.map
    if (!this.enabled || !map || !this.grid || !this.prog) return
    const now = performance.now()
    const dt = Math.min(0.05, this.last ? (now - this.last) / 1000 : 0.016)
    this.last = now
    const c = map.getCenter()
    const mpp = (156543.03392 * Math.cos((c.lat * Math.PI) / 180)) / 2 ** map.getZoom()
    const speedup = (PX_PER_S_AT_10MPS * mpp) / 10
    this.frame = (this.frame + 1) % 2
    const cx = (c.lng + 180) / 360, sinc = Math.sin((c.lat * Math.PI) / 180), cy = 0.5 - Math.log((1 + sinc) / (1 - sinc)) / (4 * Math.PI)
    const verts = new Float32Array(N * (TAIL - 1) * 2 * 5)
    let o = 0
    for (let k = 0; k < N; k++) {
      const b = k * TAIL
      const [u, v] = this.sample(this.px[b], this.py[b])
      this.age[k] += dt * 10
      if (Number.isNaN(u) || this.age[k] > 100) { this.respawn(k); continue }
      if (this.frame === 0) for (let t = TAIL - 1; t > 0; t--) { this.px[b + t] = this.px[b + t - 1]; this.py[b + t] = this.py[b + t - 1] }
      const lat = this.py[b]
      this.px[b] += (u * dt * speedup) / (111_320 * Math.cos((lat * Math.PI) / 180))
      this.py[b] += (v * dt * speedup) / 110_540
      const speed = Math.hypot(u, v)
      const fade = Math.min(1, this.age[k] / 8) * Math.min(1, (100 - this.age[k]) / 10)
      for (let t = 0; t < TAIL - 1; t++) {
        for (const q of [t, t + 1]) {
          const lng = this.px[b + q], la = this.py[b + q]
          const s = Math.sin((la * Math.PI) / 180)
          verts[o++] = (lng + 180) / 360 - cx; verts[o++] = 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI) - cy; verts[o++] = 0
          verts[o++] = 0.9 * fade * (1 - q / TAIL); verts[o++] = speed
        }
      }
    }
    const m = options.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    const mvp = new Float32Array(16)
    for (let i = 0; i < 16; i++) mvp[i] = m[i]
    for (let r = 0; r < 4; r++) mvp[12 + r] = m[r] * cx + m[4 + r] * cy + m[12 + r]
    gl.useProgram(this.prog); gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf); gl.bufferData(gl.ARRAY_BUFFER, verts.subarray(0, o), gl.DYNAMIC_DRAW)
    gl.uniformMatrix4fv(this.uni, false, mvp)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA); gl.disable(gl.DEPTH_TEST)
    gl.drawArrays(gl.LINES, 0, o / 5)
    gl.bindVertexArray(null)
    map.triggerRepaint()
  }
}
