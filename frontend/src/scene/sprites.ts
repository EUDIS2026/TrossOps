/** Display-rate sprite layer: instanced, screen-aligned billboards from an image atlas (NATO symbols, traffic
 * silhouettes, halos, heading arrows). Positions are rendered relative to a per-frame centre — offsets are taken in
 * float64 on the CPU and the centre translation is folded into the matrix — so symbols stay rock-steady at street
 * zoom where raw float32 mercator coordinates would jitter. Airborne items sit at their altitude in pitched views. */
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MlMap } from 'maplibre-gl'
import { CELL } from './symbols'

const ATLAS = 2048
const PER_ROW = ATLAS / CELL
const STRIDE = 11 // dx dy dz rot size u0 v0 u1 v1 alpha yoff

const VS = `#version 300 es
precision highp float;
in vec2 a_corner;
in vec3 a_pos; in float a_rot; in float a_size; in vec4 a_uv; in float a_alpha; in float a_yoff;
uniform mat4 u_mvp; uniform vec2 u_viewport; uniform float u_dpr;
out vec2 v_uv; out float v_alpha;
void main() {
  vec4 clip = u_mvp * vec4(a_pos, 1.0);
  float c = cos(a_rot), s = sin(a_rot);
  vec2 off = vec2(a_corner.x * c - a_corner.y * s, a_corner.x * s + a_corner.y * c) * a_size * u_dpr;
  off.y += a_yoff * u_dpr;
  clip.xy += off / u_viewport * 2.0 * clip.w;
  gl_Position = clip;
  v_uv = mix(a_uv.xy, a_uv.zw, vec2(a_corner.x + 0.5, 0.5 - a_corner.y));
  v_alpha = a_alpha;
}`
const FS = `#version 300 es
precision highp float;
in vec2 v_uv; in float v_alpha; uniform sampler2D u_atlas; out vec4 fragColor;
void main() { vec4 c = texture(u_atlas, v_uv); if (c.a < 0.01) discard; fragColor = c * v_alpha; }`

const EARTH_CIRC = 40_075_016.686

export class SpriteLayer implements CustomLayerInterface {
  readonly id: string
  type = 'custom' as const
  renderingMode = '2d' as const
  enabled = true
  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private atlas: WebGLTexture | null = null
  private slots = new Map<string, number>()
  private pending: string[] = []
  private vao: WebGLVertexArrayObject | null = null
  private instBuf: WebGLBuffer | null = null
  private data = new Float32Array(STRIDE * 4096)
  private n = 0
  private cx = 0.5; private cy = 0.5
  private stage: number[] = []
  private loc: Record<string, number> = {}
  private uni: Record<string, WebGLUniformLocation | null> = {}

  constructor(id: string, private factory: (key: string) => HTMLCanvasElement) { this.id = id }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map; this.gl = gl
    const compile = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader'); return s }
    const p = gl.createProgram()!
    gl.attachShader(p, compile(gl.VERTEX_SHADER, VS)); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link')
    this.program = p
    for (const a of ['a_corner', 'a_pos', 'a_rot', 'a_size', 'a_uv', 'a_alpha', 'a_yoff']) this.loc[a] = gl.getAttribLocation(p, a)
    for (const u of ['u_mvp', 'u_viewport', 'u_atlas', 'u_dpr']) this.uni[u] = gl.getUniformLocation(p, u)
    this.atlas = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, this.atlas)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, ATLAS, ATLAS, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.LINEAR); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.LINEAR)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    this.vao = gl.createVertexArray()
    gl.bindVertexArray(this.vao)
    const quad = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, quad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([-0.5, -0.5, 0.5, -0.5, -0.5, 0.5, 0.5, 0.5]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(this.loc.a_corner); gl.vertexAttribPointer(this.loc.a_corner, 2, gl.FLOAT, false, 0, 0)
    this.instBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf)
    const stride = STRIDE * 4
    const attr = (name: string, size: number, offset: number) => { const l = this.loc[name]; if (l < 0) return; gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, stride, offset); gl.vertexAttribDivisor(l, 1) }
    attr('a_pos', 3, 0); attr('a_rot', 1, 12); attr('a_size', 1, 16); attr('a_uv', 4, 20); attr('a_alpha', 1, 36); attr('a_yoff', 1, 40)
    gl.bindVertexArray(null)
    this.slots.clear()
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program) gl.deleteProgram(this.program)
    if (this.atlas) gl.deleteTexture(this.atlas)
    if (this.vao) gl.deleteVertexArray(this.vao)
    if (this.instBuf) gl.deleteBuffer(this.instBuf)
    this.program = null; this.atlas = null; this.vao = null; this.instBuf = null; this.slots.clear(); this.map = null; this.gl = null
  }

  private slot(key: string): number {
    const have = this.slots.get(key)
    if (have !== undefined) return have
    if (this.slots.size >= PER_ROW * PER_ROW) this.slots.clear() // atlas full: rebuild lazily (rare)
    const s = this.slots.size
    this.slots.set(key, s)
    this.pending.push(key)
    return s
  }

  private upload() {
    const gl = this.gl
    if (!gl || !this.pending.length) return
    gl.bindTexture(gl.TEXTURE_2D, this.atlas)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true)
    for (const key of this.pending) {
      const s = this.slots.get(key)
      if (s === undefined) continue
      gl.texSubImage2D(gl.TEXTURE_2D, 0, (s % PER_ROW) * CELL, Math.floor(s / PER_ROW) * CELL, gl.RGBA, gl.UNSIGNED_BYTE, this.factory(key))
    }
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
    this.pending = []
  }

  /** Start a frame; the centre should be near the camera centre (mercator 0..1). */
  begin(cx: number, cy: number) { this.cx = cx; this.cy = cy; this.stage.length = 0; this.n = 0 }

  /** Queue one sprite. rotDeg is the screen rotation (clockwise), sizePx the cell's displayed size in css px. */
  push(mx: number, my: number, altM: number | null, lat: number, key: string, sizePx: number, rotDeg: number, alpha: number, yoffPx = 0) {
    const s = this.slot(key)
    const u0 = ((s % PER_ROW) * CELL) / ATLAS, v0 = (Math.floor(s / PER_ROW) * CELL) / ATLAS
    const z = altM ? altM / (EARTH_CIRC * Math.cos((lat * Math.PI) / 180)) : 0
    this.stage.push(mx - this.cx, my - this.cy, z, (-rotDeg * Math.PI) / 180, sizePx, u0, v0 + CELL / ATLAS, u0 + CELL / ATLAS, v0, alpha, yoffPx)
    this.n++
  }

  commit() {
    if (this.data.length < this.stage.length) this.data = new Float32Array(this.stage.length * 2)
    this.data.set(this.stage)
    this.map?.triggerRepaint()
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    if (!this.enabled || !this.program || !this.map || !this.n) return
    this.upload()
    const m = options.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
    // Fold translate(cx, cy, 0) into the matrix in float64 so the instance offsets stay small.
    const mvp = new Float32Array(16)
    for (let i = 0; i < 16; i++) mvp[i] = m[i]
    for (let r = 0; r < 4; r++) mvp[12 + r] = m[r] * this.cx + m[4 + r] * this.cy + m[12 + r]
    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf)
    gl.bufferData(gl.ARRAY_BUFFER, this.data.subarray(0, this.n * STRIDE), gl.DYNAMIC_DRAW)
    gl.uniformMatrix4fv(this.uni.u_mvp, false, mvp)
    gl.uniform2f(this.uni.u_viewport, gl.drawingBufferWidth, gl.drawingBufferHeight)
    gl.uniform1f(this.uni.u_dpr, window.devicePixelRatio || 1)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.atlas); gl.uniform1i(this.uni.u_atlas, 0)
    gl.disable(gl.DEPTH_TEST)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.n)
    gl.bindVertexArray(null)
  }
}
