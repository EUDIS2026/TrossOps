/** Display-rate label layer: map labels for units, aggregates, sites and live traffic drawn as GPU text sprites.
 * Each distinct (text, colour, size) is rasterised once with its dark halo into a shelf-packed atlas at the map's
 * device pixel ratio; every frame the controller queues labels at the same positions as their symbols, a
 * screen-space grid keeps them from overlapping (priority first, labels already on screen win ties), and one
 * instanced draw renders them snapped to whole device pixels so they stay crisp while their symbols move.
 * Nothing goes through MapLibre's GeoJSON/symbol pipeline, so a moving picture never triggers worker re-tiling,
 * bucket rebuilds or symbol re-placement. LeaderLayer does the same for declutter leader lines. */
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MlMap } from 'maplibre-gl'

const AW = 2048, AH = 1024 // atlas in device px
const STRIDE = 12 // dx dy dz bx by bw bh u0 v0 u1 v1 alpha
const HALO = 'rgba(8,11,14,0.95)'
const HALO_W = 1.6 // css px, as the former MapLibre text-halo-width
const CELL_PX = 64 // collision grid cell, css px

const VS = `#version 300 es
precision highp float;
in vec2 a_corner;
in vec3 a_pos; in vec4 a_box; in vec4 a_uv; in float a_alpha;
uniform mat4 u_mvp; uniform vec2 u_viewport;
out vec2 v_uv; out float v_alpha;
void main() {
  vec4 clip = u_mvp * vec4(a_pos, 1.0);
  if (clip.w <= 0.0) { gl_Position = vec4(2.0, 2.0, 2.0, 1.0); return; }
  vec2 px = floor((clip.xy / clip.w * 0.5 + 0.5) * u_viewport + 0.5);
  vec2 p = px + vec2(a_box.x + a_corner.x * a_box.z, -(a_box.y + a_corner.y * a_box.w));
  gl_Position = vec4((p / u_viewport * 2.0 - 1.0) * clip.w, clip.z, clip.w);
  v_uv = mix(a_uv.xy, a_uv.zw, a_corner);
  v_alpha = a_alpha;
}`
const FS = `#version 300 es
precision highp float;
in vec2 v_uv; in float v_alpha; uniform sampler2D u_atlas; out vec4 fragColor;
void main() { vec4 c = texture(u_atlas, v_uv); if (c.a < 0.004) discard; fragColor = c * v_alpha; }`

interface Slot { x: number; y: number; w: number; h: number; uploaded: boolean; text: string; color: string; size: number; bold: boolean }
interface Cand { mx: number; my: number; z: number; sx: number; sy: number; slot: Slot; key: string; pri: number; yoff: number; alpha: number }

export class TextLayer implements CustomLayerInterface {
  readonly id: string
  type = 'custom' as const
  renderingMode = '2d' as const
  enabled = true
  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private atlas: WebGLTexture | null = null
  private vao: WebGLVertexArrayObject | null = null
  private instBuf: WebGLBuffer | null = null
  private loc: Record<string, number> = {}
  private uni: Record<string, WebGLUniformLocation | null> = {}
  // atlas bookkeeping (shelf packing; the whole atlas is rebuilt when it fills or the pixel ratio changes)
  private slots = new Map<string, Slot>()
  private shelves: { y: number; h: number; x: number }[] = []
  private shelfTop = 0
  private overflow = false
  private dpr = 1
  private fontFamily = 'system-ui, sans-serif'
  private measureCtx: CanvasRenderingContext2D | null = null
  private scratch: HTMLCanvasElement | null = null
  // frame state
  private cx = 0.5; private cy = 0.5; private worldPx = 512
  private cands: Cand[] = []
  private data = new Float32Array(STRIDE * 512)
  n = 0
  private shownKeys = new Set<string>()
  private shown = new Float64Array(0)
  private shownN = -1

  constructor(id: string) {
    this.id = id
    if (typeof document !== 'undefined') {
      this.fontFamily = getComputedStyle(document.body).fontFamily || this.fontFamily
      // web fonts arriving late change metrics: rasterise again with the real face
      void document.fonts?.ready.then(() => { this.fontFamily = getComputedStyle(document.body).fontFamily || this.fontFamily; this.reset(); this.map?.triggerRepaint() })
    }
  }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program && this.gl === gl) { this.map = map; return } // re-added after a style switch: keep GL objects
    this.map = map; this.gl = gl
    const p = this.program = link(gl, VS, FS)
    for (const a of ['a_corner', 'a_pos', 'a_box', 'a_uv', 'a_alpha']) this.loc[a] = gl.getAttribLocation(p, a)
    for (const u of ['u_mvp', 'u_viewport', 'u_atlas']) this.uni[u] = gl.getUniformLocation(p, u)
    this.atlas = gl.createTexture()
    gl.bindTexture(gl.TEXTURE_2D, this.atlas)
    gl.texImage2D(gl.TEXTURE_2D, 0, gl.RGBA, AW, AH, 0, gl.RGBA, gl.UNSIGNED_BYTE, null)
    // texels map 1:1 to device pixels (quads are pixel-snapped), so nearest sampling keeps glyphs sharp
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MIN_FILTER, gl.NEAREST); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_MAG_FILTER, gl.NEAREST)
    gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_S, gl.CLAMP_TO_EDGE); gl.texParameteri(gl.TEXTURE_2D, gl.TEXTURE_WRAP_T, gl.CLAMP_TO_EDGE)
    this.vao = gl.createVertexArray()
    gl.bindVertexArray(this.vao)
    const quad = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, quad)
    gl.bufferData(gl.ARRAY_BUFFER, new Float32Array([0, 0, 1, 0, 0, 1, 1, 1]), gl.STATIC_DRAW)
    gl.enableVertexAttribArray(this.loc.a_corner); gl.vertexAttribPointer(this.loc.a_corner, 2, gl.FLOAT, false, 0, 0)
    this.instBuf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf)
    const stride = STRIDE * 4
    const attr = (name: string, size: number, offset: number) => { const l = this.loc[name]; if (l < 0) return; gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, stride, offset); gl.vertexAttribDivisor(l, 1) }
    attr('a_pos', 3, 0); attr('a_box', 4, 12); attr('a_uv', 4, 28); attr('a_alpha', 1, 44)
    gl.bindVertexArray(null)
    this.reset()
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program) gl.deleteProgram(this.program)
    if (this.atlas) gl.deleteTexture(this.atlas)
    if (this.vao) gl.deleteVertexArray(this.vao)
    if (this.instBuf) gl.deleteBuffer(this.instBuf)
    this.program = null; this.atlas = null; this.vao = null; this.instBuf = null
    this.map = null; this.gl = null; this.reset()
  }

  private reset() { this.slots.clear(); this.shelves = []; this.shelfTop = 0; this.shownN = -1 }

  private font(size: number, bold: boolean) { return `${bold ? 600 : 500} ${size * this.dpr}px ${this.fontFamily}` }

  /** Atlas slot for a label, allocated (and measured) on first use; null when the atlas is full. */
  private slot(text: string, color: string, size: number, bold: boolean): Slot | null {
    const key = `${size}|${bold ? 1 : 0}|${color}|${text}`
    const have = this.slots.get(key)
    if (have) return have
    const ctx = this.measureCtx ??= document.createElement('canvas').getContext('2d')!
    ctx.font = this.font(size, bold)
    const pad = Math.ceil(HALO_W * this.dpr) + 1
    const w = Math.min(AW, Math.ceil(ctx.measureText(text).width) + pad * 2)
    const h = Math.ceil(size * 1.3 * this.dpr) + pad * 2
    let shelf = this.shelves.find(s => s.h === h && s.x + w <= AW)
    if (!shelf) {
      if (this.shelfTop + h > AH) { this.overflow = true; return null }
      shelf = { y: this.shelfTop, h, x: 0 }
      this.shelves.push(shelf); this.shelfTop += h + 1
    }
    const s: Slot = { x: shelf.x, y: shelf.y, w, h, uploaded: false, text, color, size, bold }
    shelf.x += w + 1
    this.slots.set(key, s)
    return s
  }

  private upload() {
    const gl = this.gl
    if (!gl) return
    let bound = false
    for (const s of this.slots.values()) {
      if (s.uploaded) continue
      s.uploaded = true
      const c = this.scratch ??= document.createElement('canvas')
      c.width = s.w; c.height = s.h
      const ctx = c.getContext('2d')!
      ctx.font = this.font(s.size, s.bold); ctx.textBaseline = 'middle'; ctx.textAlign = 'center'
      ctx.lineJoin = 'round'; ctx.lineWidth = HALO_W * 2 * this.dpr; ctx.strokeStyle = HALO
      ctx.strokeText(s.text, s.w / 2, s.h / 2)
      ctx.fillStyle = s.color; ctx.fillText(s.text, s.w / 2, s.h / 2)
      if (!bound) { gl.bindTexture(gl.TEXTURE_2D, this.atlas); gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true); bound = true }
      gl.texSubImage2D(gl.TEXTURE_2D, 0, s.x, s.y, gl.RGBA, gl.UNSIGNED_BYTE, c)
    }
    if (bound) gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
  }

  /** Start a frame (same centre convention as SpriteLayer.begin). */
  begin(cx: number, cy: number, worldPx: number) {
    this.cx = cx; this.cy = cy; this.worldPx = worldPx
    this.cands.length = 0
    const dpr = this.map?.getPixelRatio() ?? 1
    if (dpr !== this.dpr) { this.dpr = dpr; this.reset() }
  }

  /** Queue a label under a symbol. (sx, sy) is the symbol's screen position in css px, used for collision;
   * pri: lower places first; yoff: css px from the anchor down to the top of the text box. */
  push(mx: number, my: number, altM: number | null, lat: number, sx: number, sy: number, text: string, color: string, size: number, pri: number, yoff: number, alpha = 1, bold = false) {
    if (!text) return
    const slot = this.slot(text, color, size, bold)
    if (!slot) return
    const z = altM ? altM / (40_075_016.686 * Math.cos((lat * Math.PI) / 180)) : 0
    this.cands.push({ mx: mx - this.cx, my: my - this.cy, z, sx, sy, slot, key: `${slot.x},${slot.y}`, pri, yoff, alpha })
  }

  /** Collide, build the instance buffer; returns true when what is on screen changed. */
  commit(): boolean {
    // atlas full (texts change: counts, flight levels): start over with only what is wanted, from the next frame
    if (this.overflow) { this.overflow = false; this.reset() }
    const before = this.shownKeys
    const cands = this.cands.sort((a, b) => a.pri - b.pri || (before.has(b.key) ? 1 : 0) - (before.has(a.key) ? 1 : 0))
    const grid = new Map<number, number[]>()
    const now = new Set<string>()
    const dpr = this.dpr
    if (this.data.length < cands.length * STRIDE) this.data = new Float32Array(cands.length * STRIDE * 2)
    const d = this.data
    let n = 0
    for (const c of cands) {
      const s = c.slot
      const w = s.w / dpr, h = s.h / dpr
      // the halo padding may touch; the glyphs may not
      const x0 = c.sx - w / 2 + 3, x1 = c.sx + w / 2 - 3, y0 = c.sy + c.yoff + 2, y1 = c.sy + c.yoff + h - 2
      const gx0 = Math.floor(x0 / CELL_PX), gx1 = Math.floor(x1 / CELL_PX), gy0 = Math.floor(y0 / CELL_PX), gy1 = Math.floor(y1 / CELL_PX)
      let hit = false
      for (let gx = gx0; gx <= gx1 && !hit; gx++) for (let gy = gy0; gy <= gy1 && !hit; gy++) {
        const r = grid.get(gx * 8192 + gy)
        if (r) for (let k = 0; k < r.length; k += 4) if (x0 < r[k + 2] && x1 > r[k] && y0 < r[k + 3] && y1 > r[k + 1]) { hit = true; break }
      }
      if (hit) continue
      for (let gx = gx0; gx <= gx1; gx++) for (let gy = gy0; gy <= gy1; gy++) {
        const id = gx * 8192 + gy
        const r = grid.get(id)
        if (r) r.push(x0, y0, x1, y1); else grid.set(id, [x0, y0, x1, y1])
      }
      now.add(c.key)
      const o = n * STRIDE
      d[o] = c.mx; d[o + 1] = c.my; d[o + 2] = c.z
      d[o + 3] = -Math.round(s.w / 2); d[o + 4] = Math.round(c.yoff * dpr); d[o + 5] = s.w; d[o + 6] = s.h
      d[o + 7] = s.x / AW; d[o + 8] = s.y / AH; d[o + 9] = (s.x + s.w) / AW; d[o + 10] = (s.y + s.h) / AH
      d[o + 11] = c.alpha
      n++
    }
    this.shownKeys = now
    this.n = n
    // changed on screen? (moved ≥ 0.35 px, another text, offset or alpha)
    let dirty = n !== this.shownN
    const px = 0.35 / this.worldPx
    const sh = this.shown
    if (!dirty) {
      for (let i = 0; i < n * STRIDE; i += STRIDE) {
        if (Math.abs(d[i] + this.cx - sh[i]) > px || Math.abs(d[i + 1] + this.cy - sh[i + 1]) > px || Math.abs(d[i + 2] - sh[i + 2]) > px ||
            d[i + 4] !== sh[i + 4] || d[i + 7] !== sh[i + 7] || d[i + 8] !== sh[i + 8] || Math.abs(d[i + 11] - sh[i + 11]) > 0.02) { dirty = true; break }
      }
    }
    if (dirty) {
      if (this.shown.length < n * STRIDE) this.shown = new Float64Array(n * STRIDE * 2)
      const out = this.shown
      for (let i = 0; i < n * STRIDE; i++) out[i] = d[i]
      for (let i = 0; i < n * STRIDE; i += STRIDE) { out[i] += this.cx; out[i + 1] += this.cy }
      this.shownN = n
    }
    return dirty
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    if (!this.enabled || !this.program || !this.map || !this.n) return
    this.upload()
    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf)
    gl.bufferData(gl.ARRAY_BUFFER, this.data.subarray(0, this.n * STRIDE), gl.DYNAMIC_DRAW)
    gl.uniformMatrix4fv(this.uni.u_mvp, false, centred(options, this.cx, this.cy))
    gl.uniform2f(this.uni.u_viewport, gl.drawingBufferWidth, gl.drawingBufferHeight)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.atlas); gl.uniform1i(this.uni.u_atlas, 0)
    gl.disable(gl.DEPTH_TEST)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, this.n)
    gl.bindVertexArray(null)
  }
}

const LVS = `#version 300 es
precision highp float;
in vec2 a_pos; uniform mat4 u_mvp;
void main() { gl_Position = u_mvp * vec4(a_pos, 0.0, 1.0); }`
const LFS = `#version 300 es
precision highp float;
uniform vec4 u_color; out vec4 fragColor;
void main() { fragColor = u_color; }`

/** Leader lines from decluttered symbols back to their true position: one GL_LINES draw, queued per frame. */
export class LeaderLayer implements CustomLayerInterface {
  readonly id: string
  type = 'custom' as const
  renderingMode = '2d' as const
  private map: MlMap | null = null
  private gl: WebGL2RenderingContext | null = null
  private program: WebGLProgram | null = null
  private vao: WebGLVertexArrayObject | null = null
  private buf: WebGLBuffer | null = null
  private uni: Record<string, WebGLUniformLocation | null> = {}
  private cx = 0.5; private cy = 0.5; private worldPx = 512
  private lines: number[] = []
  private data = new Float32Array(0)
  private n = 0
  private sig = ''

  constructor(id: string) { this.id = id }

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program && this.gl === gl) { this.map = map; this.sig = ''; return }
    this.map = map; this.gl = gl
    const p = this.program = link(gl, LVS, LFS)
    for (const u of ['u_mvp', 'u_color']) this.uni[u] = gl.getUniformLocation(p, u)
    this.vao = gl.createVertexArray()
    gl.bindVertexArray(this.vao)
    this.buf = gl.createBuffer()
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf)
    const la = gl.getAttribLocation(p, 'a_pos')
    gl.enableVertexAttribArray(la); gl.vertexAttribPointer(la, 2, gl.FLOAT, false, 0, 0)
    gl.bindVertexArray(null)
    this.sig = ''
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program) gl.deleteProgram(this.program)
    if (this.vao) gl.deleteVertexArray(this.vao)
    if (this.buf) gl.deleteBuffer(this.buf)
    this.program = null; this.vao = null; this.buf = null; this.map = null; this.gl = null
  }

  begin(cx: number, cy: number, worldPx: number) { this.cx = cx; this.cy = cy; this.worldPx = worldPx; this.lines.length = 0 }

  /** Queue a leader between two mercator points (true position → displaced symbol). */
  line(mx0: number, my0: number, mx1: number, my1: number) { this.lines.push(mx0 - this.cx, my0 - this.cy, mx1 - this.cx, my1 - this.cy) }

  /** Returns true when the leaders on screen changed (by ≥ ~0.5 px). */
  commit(): boolean {
    const L = this.lines
    if (this.data.length < L.length) this.data = new Float32Array(L.length * 2)
    this.data.set(L)
    this.n = L.length / 2
    const k = this.worldPx * 2
    let sig = ''
    for (let i = 0; i < L.length; i += 2) sig += `${Math.round((L[i] + this.cx) * k)},${Math.round((L[i + 1] + this.cy) * k)};`
    if (sig === this.sig) return false
    this.sig = sig
    return true
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    if (!this.program || !this.map || !this.n) return
    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.buf)
    gl.bufferData(gl.ARRAY_BUFFER, this.data.subarray(0, this.n * 2), gl.DYNAMIC_DRAW)
    gl.uniformMatrix4fv(this.uni.u_mvp, false, centred(options, this.cx, this.cy))
    gl.uniform4f(this.uni.u_color, 0.784 * 0.45, 0.882 * 0.45, 0.941 * 0.45, 0.45) // rgba(200,225,240,0.45), premultiplied
    gl.disable(gl.DEPTH_TEST)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.drawArrays(gl.LINES, 0, this.n)
    gl.bindVertexArray(null)
  }
}

function link(gl: WebGL2RenderingContext, vs: string, fs: string): WebGLProgram {
  const compile = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader'); return s }
  const p = gl.createProgram()!
  gl.attachShader(p, compile(gl.VERTEX_SHADER, vs)); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, fs)); gl.linkProgram(p)
  if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link')
  return p
}

/** The map's main matrix with translate(cx, cy, 0) folded in (float64), so per-instance offsets stay small. */
function centred(options: CustomRenderMethodInput, cx: number, cy: number): Float32Array {
  const m = options.defaultProjectionData.mainMatrix as unknown as ArrayLike<number>
  const out = new Float32Array(16)
  for (let i = 0; i < 16; i++) out[i] = m[i]
  for (let r = 0; r < 4; r++) out[12 + r] = m[r] * cx + m[4 + r] * cy + m[12 + r]
  return out
}
