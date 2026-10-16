/** Display-rate sprite layer for moving units. MapLibre's own symbol layer re-tiles its source on every
 * `setData`, which cannot keep up with per-frame motion; this custom WebGL layer draws the same icon images as
 * instanced, heading-rotated billboards straight from the interpolated poses. The symbol layer still owns labels,
 * clusters and sites at a low update rate. */
import type { CustomLayerInterface, CustomRenderMethodInput, Map as MlMap } from 'maplibre-gl'
import { MercatorCoordinate } from 'maplibre-gl'
import { drawIcon, parseIconId, SIZE } from './semantics'

export interface SpriteInstance { id: string; lng: number; lat: number; headingDeg: number; icon: string; opacity: number; selected: boolean; hovered: boolean; sizePx: number }

const ATLAS = 2048
const CELL = SIZE * 2 // icons are drawn at 2× for crisp edges
const PER_ROW = ATLAS / CELL

const VS = `#version 300 es
precision highp float;
in vec2 a_corner;            // -0.5..0.5 quad
in vec2 a_pos;               // mercator x,y
in float a_rot;              // radians, screen rotation
in float a_size;             // px
in vec4 a_uv;                // u0 v0 u1 v1
in float a_alpha;
uniform mat4 u_mvp; uniform vec2 u_viewport;
out vec2 v_uv; out float v_alpha;
void main() {
  vec4 clip = u_mvp * vec4(a_pos, 0.0, 1.0);
  float c = cos(a_rot), s = sin(a_rot);
  vec2 off = vec2(a_corner.x * c - a_corner.y * s, a_corner.x * s + a_corner.y * c) * a_size;
  clip.xy += off / u_viewport * 2.0 * clip.w;
  gl_Position = clip;
  v_uv = mix(a_uv.xy, a_uv.zw, a_corner + 0.5);
  v_alpha = a_alpha;
}`
const FS = `#version 300 es
precision highp float;
in vec2 v_uv; in float v_alpha; uniform sampler2D u_atlas; out vec4 fragColor;
void main() { vec4 c = texture(u_atlas, v_uv); fragColor = vec4(c.rgb, c.a) * v_alpha; }`

export class SpriteLayer implements CustomLayerInterface {
  id = 'unit-sprites'
  type = 'custom' as const
  renderingMode = '2d' as const
  instances: SpriteInstance[] = []
  enabled = true
  minZoom = 8.3
  maxZoom = 99
  private map: MlMap | null = null
  private program: WebGLProgram | null = null
  private atlas: WebGLTexture | null = null
  private slots = new Map<string, number>()
  private vao: WebGLVertexArrayObject | null = null
  private instBuf: WebGLBuffer | null = null
  private data = new Float32Array(0)
  private loc: Record<string, number> = {}
  private uni: Record<string, WebGLUniformLocation | null> = {}

  onAdd(map: MlMap, gl: WebGL2RenderingContext) {
    this.map = map
    const compile = (type: number, src: string) => { const s = gl.createShader(type)!; gl.shaderSource(s, src); gl.compileShader(s); if (!gl.getShaderParameter(s, gl.COMPILE_STATUS)) throw new Error(gl.getShaderInfoLog(s) ?? 'shader'); return s }
    const p = gl.createProgram()!
    gl.attachShader(p, compile(gl.VERTEX_SHADER, VS)); gl.attachShader(p, compile(gl.FRAGMENT_SHADER, FS)); gl.linkProgram(p)
    if (!gl.getProgramParameter(p, gl.LINK_STATUS)) throw new Error(gl.getProgramInfoLog(p) ?? 'link')
    this.program = p
    for (const a of ['a_corner', 'a_pos', 'a_rot', 'a_size', 'a_uv', 'a_alpha']) this.loc[a] = gl.getAttribLocation(p, a)
    for (const u of ['u_mvp', 'u_viewport', 'u_atlas']) this.uni[u] = gl.getUniformLocation(p, u)
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
    const stride = 9 * 4
    const attr = (name: string, size: number, offset: number) => { const l = this.loc[name]; gl.enableVertexAttribArray(l); gl.vertexAttribPointer(l, size, gl.FLOAT, false, stride, offset); gl.vertexAttribDivisor(l, 1) }
    attr('a_pos', 2, 0); attr('a_rot', 1, 8); attr('a_size', 1, 12); attr('a_uv', 4, 16); attr('a_alpha', 1, 32)
    gl.bindVertexArray(null)
    this.ensureSlot(gl, 'halo:selected'); this.ensureSlot(gl, 'halo:hovered')
  }

  onRemove(_map: MlMap, gl: WebGL2RenderingContext) {
    if (this.program) gl.deleteProgram(this.program)
    if (this.atlas) gl.deleteTexture(this.atlas)
    if (this.vao) gl.deleteVertexArray(this.vao)
    if (this.instBuf) gl.deleteBuffer(this.instBuf)
    this.program = null; this.atlas = null; this.vao = null; this.instBuf = null; this.slots.clear(); this.map = null
  }

  private ensureSlot(gl: WebGL2RenderingContext, icon: string): number {
    const have = this.slots.get(icon)
    if (have !== undefined) return have
    const slot = this.slots.size
    if (slot >= PER_ROW * PER_ROW) return 0
    let img: ImageData
    if (icon.startsWith('halo:')) img = drawHalo(icon === 'halo:selected')
    else { const spec = parseIconId(icon); img = spec ? drawIcon(spec) : drawIcon({ modelKey: 'unknown_air', affiliation: 'unknown', condition: 'unknown' }) }
    gl.bindTexture(gl.TEXTURE_2D, this.atlas)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, true)
    gl.texSubImage2D(gl.TEXTURE_2D, 0, (slot % PER_ROW) * CELL, Math.floor(slot / PER_ROW) * CELL, CELL, CELL, gl.RGBA, gl.UNSIGNED_BYTE, img)
    gl.pixelStorei(gl.UNPACK_PREMULTIPLY_ALPHA_WEBGL, false)
    this.slots.set(icon, slot)
    return slot
  }

  render(gl: WebGL2RenderingContext, options: CustomRenderMethodInput) {
    if (!this.enabled || !this.program || !this.map || !this.instances.length) return
    const zoom = this.map.getZoom()
    if (zoom < this.minZoom || zoom >= this.maxZoom) return
    const bearing = (this.map.getBearing() * Math.PI) / 180
    const n = this.instances.length
    const rows: number[] = []
    const push = (lng: number, lat: number, rot: number, size: number, slot: number, alpha: number) => {
      const mc = MercatorCoordinate.fromLngLat([lng, lat])
      const u0 = ((slot % PER_ROW) * CELL) / ATLAS, v0 = (Math.floor(slot / PER_ROW) * CELL) / ATLAS
      rows.push(mc.x, mc.y, rot, size, u0, v0, u0 + CELL / ATLAS, v0 + CELL / ATLAS, alpha)
    }
    for (const i of this.instances) {
      if (i.selected || i.hovered) push(i.lng, i.lat, 0, i.sizePx * (i.selected ? 1.9 : 1.6), this.ensureSlot(gl, i.selected ? 'halo:selected' : 'halo:hovered'), 1)
      push(i.lng, i.lat, -((i.headingDeg * Math.PI) / 180 - bearing), i.sizePx, this.ensureSlot(gl, i.icon), i.opacity)
    }
    if (this.data.length < rows.length) this.data = new Float32Array(Math.max(rows.length, n * 18 * 2))
    this.data.set(rows)
    gl.useProgram(this.program)
    gl.bindVertexArray(this.vao)
    gl.bindBuffer(gl.ARRAY_BUFFER, this.instBuf)
    gl.bufferData(gl.ARRAY_BUFFER, this.data.subarray(0, rows.length), gl.DYNAMIC_DRAW)
    gl.uniformMatrix4fv(this.uni.u_mvp, false, options.defaultProjectionData.mainMatrix as Float32Array)
    gl.uniform2f(this.uni.u_viewport, gl.drawingBufferWidth, gl.drawingBufferHeight)
    gl.activeTexture(gl.TEXTURE0); gl.bindTexture(gl.TEXTURE_2D, this.atlas); gl.uniform1i(this.uni.u_atlas, 0)
    gl.disable(gl.DEPTH_TEST)
    gl.enable(gl.BLEND); gl.blendFunc(gl.ONE, gl.ONE_MINUS_SRC_ALPHA)
    gl.drawArraysInstanced(gl.TRIANGLE_STRIP, 0, 4, rows.length / 9)
    gl.bindVertexArray(null)
  }
}

function drawHalo(selected: boolean): ImageData {
  const c = document.createElement('canvas'); c.width = CELL; c.height = CELL
  const ctx = c.getContext('2d')!
  ctx.beginPath(); ctx.arc(CELL / 2, CELL / 2, CELL / 2 - 6, 0, Math.PI * 2)
  ctx.fillStyle = selected ? 'rgba(91,141,239,0.22)' : 'rgba(230,238,245,0.12)'; ctx.fill()
  ctx.lineWidth = selected ? 4 : 2; ctx.strokeStyle = selected ? '#5b8def' : 'rgba(230,238,245,0.6)'; ctx.stroke()
  return ctx.getImageData(0, 0, CELL, CELL)
}
