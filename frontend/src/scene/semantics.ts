/** Visual grammar for the scene. One place decides what a colour, outline or shape means. */
import type { Affiliation, Condition, Severity } from '../contracts/types'

export const palette = {
  canvas: '#171b20',
  accent: '#5b8def',      // selection, interactive
  own: '#e6eef5',
  allied: '#8ccbb8',
  civil: '#aeb8c2',
  unknown: '#e38bc7',
  hostile: '#f0665b',
  outline: '#1b2129',
  warning: '#e0a43b',
  critical: '#e5484d',
  advisory: '#7aa6d8',
  info: '#8d99a6',
  predicted: '#e38bc7',
  planned: '#9fb4c9',
  attentionLow: 'rgba(240,164,76,0.0)',
  attentionHigh: '#ff6a3d',
}

export const severityColor: Record<Severity, string> = { info: palette.info, advisory: palette.advisory, warning: palette.warning, critical: palette.critical }
export const affiliationColor: Record<Affiliation, string> = { own: palette.own, allied: palette.allied, civil: palette.civil, unknown: palette.unknown, hostile_suspected: palette.hostile }
export const conditionColor: Record<Condition, string> = { normal: 'transparent', degraded: palette.warning, unavailable: palette.critical, unknown: palette.unknown }

export const SIZE = 64
type Ctx = CanvasRenderingContext2D

function rr(ctx: Ctx, x: number, y: number, w: number, h: number, r: number) {
  ctx.beginPath(); ctx.roundRect(x, y, w, h, r); ctx.closePath()
}
function poly(ctx: Ctx, pts: number[][]) {
  ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath()
}

// All silhouettes are drawn nose-up in a 64×64 box centred at (32,32); icon-rotate applies the heading.
const silhouettes: Record<string, (ctx: Ctx) => void> = {
  fighter: ctx => poly(ctx, [[32, 6], [36, 20], [54, 36], [54, 41], [37, 36], [38, 50], [45, 55], [45, 58], [32, 54], [19, 58], [19, 55], [26, 50], [27, 36], [10, 41], [10, 36], [28, 20]]),
  transport: ctx => poly(ctx, [[32, 7], [36, 18], [58, 30], [58, 35], [36, 31], [36, 48], [46, 54], [46, 57], [32, 53], [18, 57], [18, 54], [28, 48], [28, 31], [6, 35], [6, 30], [28, 18]]),
  isr: ctx => { poly(ctx, [[32, 8], [35, 20], [60, 29], [60, 33], [35, 31], [35, 50], [42, 55], [42, 57], [32, 54], [22, 57], [22, 55], [29, 50], [29, 31], [4, 33], [4, 29], [29, 20]]); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 36, 4, 0, Math.PI * 2) },
  helicopter: ctx => { poly(ctx, [[32, 14], [38, 22], [38, 40], [34, 54], [33, 58], [31, 58], [30, 54], [26, 40], [26, 22]]); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 30, 17, 0, Math.PI * 2); ctx.globalAlpha = 0.55; ctx.stroke(); ctx.globalAlpha = 1; ctx.beginPath() },
  multirotor: ctx => { ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(18, 18); ctx.lineTo(46, 46); ctx.moveTo(46, 18); ctx.lineTo(18, 46); ctx.stroke(); ctx.lineWidth = 2; for (const [x, y] of [[18, 18], [46, 18], [18, 46], [46, 46]]) { ctx.beginPath(); ctx.arc(x, y, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke() } ctx.beginPath(); ctx.arc(32, 32, 6, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(32, 22); ctx.lineTo(32, 12); ctx.lineWidth = 3; ctx.stroke(); ctx.beginPath() },
  tank: ctx => { rr(ctx, 18, 14, 28, 38, 5); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 34, 8, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.rect(30, 6, 4, 22); ctx.fill(); ctx.stroke(); ctx.beginPath() },
  apc: ctx => { poly(ctx, [[22, 12], [42, 12], [46, 20], [46, 52], [18, 52], [18, 20]]); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 30, 5, 0, Math.PI * 2) },
  truck: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.rect(21, 13, 22, 11); ctx.fillStyle = 'rgba(0,0,0,0.25)'; ctx.fill(); ctx.beginPath() },
  fuel: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(32, 28); ctx.bezierCurveTo(26, 36, 26, 44, 32, 46); ctx.bezierCurveTo(38, 44, 38, 36, 32, 28); ctx.fillStyle = 'rgba(0,0,0,0.35)'; ctx.fill(); ctx.beginPath() },
  ambulance: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.rect(29, 24, 6, 20); ctx.rect(22, 31, 20, 6); ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.fill(); ctx.beginPath() },
  engineer: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(22, 46); ctx.lineTo(42, 26); ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.stroke(); ctx.beginPath() },
  airdef: ctx => { rr(ctx, 18, 14, 28, 40, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(32, 8); ctx.lineTo(32, 30); ctx.moveTo(26, 14); ctx.lineTo(32, 8); ctx.lineTo(38, 14); ctx.lineWidth = 3; ctx.stroke(); ctx.beginPath() },
  recovery: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 36, 7, 0, Math.PI * 1.5); ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.stroke(); ctx.beginPath() },
  cp: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(32, 20); ctx.lineTo(32, 44); ctx.moveTo(24, 20); ctx.lineTo(40, 20); ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.stroke(); ctx.beginPath() },
  signals: ctx => { rr(ctx, 18, 10, 28, 44, 4); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.moveTo(36, 22); ctx.lineTo(28, 34); ctx.lineTo(36, 34); ctx.lineTo(28, 46); ctx.lineWidth = 3; ctx.strokeStyle = 'rgba(0,0,0,0.4)'; ctx.stroke(); ctx.beginPath() },
  personnel: ctx => { ctx.beginPath(); ctx.arc(32, 32, 16, 0, Math.PI * 2); ctx.fill(); ctx.stroke(); ctx.beginPath(); ctx.arc(32, 26, 4, 0, Math.PI * 2); ctx.fillStyle = 'rgba(0,0,0,0.4)'; ctx.fill(); ctx.beginPath(); ctx.moveTo(25, 42); ctx.lineTo(32, 31); ctx.lineTo(39, 42); ctx.fill(); ctx.beginPath() },
  corvette: ctx => poly(ctx, [[32, 6], [39, 20], [40, 50], [36, 58], [28, 58], [24, 50], [25, 20]]),
  patrol_boat: ctx => poly(ctx, [[32, 10], [38, 24], [38, 52], [26, 52], [26, 24]]),
  logistics_ship: ctx => poly(ctx, [[32, 6], [42, 18], [43, 54], [21, 54], [22, 18]]),
  mcm: ctx => poly(ctx, [[32, 8], [38, 22], [38, 48], [34, 56], [30, 56], [26, 48], [26, 22]]),
  icebreaker: ctx => poly(ctx, [[32, 4], [44, 18], [44, 54], [20, 54], [20, 18]]),
  ferry: ctx => poly(ctx, [[32, 8], [44, 14], [44, 56], [20, 56], [20, 14]]),
  unknown_air: ctx => { poly(ctx, [[32, 8], [54, 32], [32, 56], [10, 32]]); ctx.lineWidth = 3 },
  unknown_sea: ctx => { poly(ctx, [[32, 8], [54, 32], [32, 56], [10, 32]]); ctx.lineWidth = 3 },
}

const siteGlyph: Record<string, (ctx: Ctx) => void> = {
  hq: ctx => { ctx.moveTo(22, 44); ctx.lineTo(22, 20); ctx.lineTo(32, 32); ctx.lineTo(42, 20); ctx.lineTo(42, 44) },
  garrison: ctx => { ctx.rect(22, 22, 20, 20); ctx.moveTo(32, 22); ctx.lineTo(32, 42) },
  airfield: ctx => { ctx.moveTo(18, 40); ctx.lineTo(46, 24); ctx.moveTo(26, 44); ctx.lineTo(44, 34) },
  navbase: ctx => { ctx.moveTo(32, 18); ctx.lineTo(32, 46); ctx.moveTo(22, 28); ctx.lineTo(42, 28); ctx.moveTo(20, 40); ctx.quadraticCurveTo(32, 50, 44, 40) },
  depot: ctx => { ctx.rect(20, 26, 24, 16); ctx.moveTo(20, 34); ctx.lineTo(44, 34); ctx.moveTo(32, 26); ctx.lineTo(32, 42) },
  hospital: ctx => { ctx.moveTo(32, 20); ctx.lineTo(32, 44); ctx.moveTo(20, 32); ctx.lineTo(44, 32) },
  radar: ctx => { ctx.arc(32, 36, 12, Math.PI * 1.1, Math.PI * 1.9); ctx.moveTo(32, 36); ctx.lineTo(32, 48) },
  comms: ctx => { ctx.moveTo(32, 48); ctx.lineTo(32, 26); ctx.moveTo(24, 22); ctx.quadraticCurveTo(32, 14, 40, 22); ctx.moveTo(27, 27); ctx.quadraticCurveTo(32, 22, 37, 27) },
  power: ctx => { ctx.moveTo(36, 18); ctx.lineTo(26, 34); ctx.lineTo(34, 34); ctx.lineTo(28, 48) },
  port: ctx => { ctx.moveTo(32, 18); ctx.lineTo(32, 40); ctx.moveTo(22, 34); ctx.quadraticCurveTo(32, 48, 42, 34); ctx.arc(32, 22, 3, 0, Math.PI * 2) },
  bridge: ctx => { ctx.moveTo(18, 40); ctx.quadraticCurveTo(32, 20, 46, 40); ctx.moveTo(18, 44); ctx.lineTo(46, 44) },
  telecom: ctx => { ctx.moveTo(32, 46); ctx.lineTo(32, 24); ctx.moveTo(26, 46); ctx.lineTo(38, 46); ctx.moveTo(22, 20); ctx.quadraticCurveTo(32, 10, 42, 20) },
}

export const SITE_KEYS = new Set(Object.keys(siteGlyph))

export interface IconSpec { modelKey: string; affiliation: Affiliation; condition: Condition; selected?: boolean }

export function iconId(spec: IconSpec): string {
  return `ent:${spec.modelKey}:${spec.affiliation}:${spec.condition}`
}

export function parseIconId(id: string): IconSpec | null {
  const [tag, modelKey, affiliation, condition] = id.split(':')
  if (tag !== 'ent' || !modelKey) return null
  return { modelKey, affiliation: (affiliation as Affiliation) ?? 'own', condition: (condition as Condition) ?? 'normal' }
}

/** Draw one icon variant. Returns ImageData at 2× pixel ratio for crisp rendering. */
export function drawIcon(spec: IconSpec): ImageData {
  const px = 2
  const canvas = document.createElement('canvas')
  canvas.width = SIZE * px; canvas.height = SIZE * px
  const ctx = canvas.getContext('2d')!
  ctx.scale(px, px)
  ctx.lineJoin = 'round'; ctx.lineCap = 'round'
  const fill = affiliationColor[spec.affiliation]
  const isSite = SITE_KEYS.has(spec.modelKey)
  const hollow = spec.affiliation === 'unknown'
  // condition ring
  if (spec.condition !== 'normal') {
    ctx.beginPath(); ctx.arc(32, 32, 29, 0, Math.PI * 2)
    ctx.strokeStyle = conditionColor[spec.condition]; ctx.lineWidth = 3.5; ctx.stroke()
  }
  ctx.fillStyle = spec.condition === 'unavailable' ? 'rgba(230,238,245,0.45)' : hollow ? 'rgba(227,139,199,0.18)' : fill
  ctx.strokeStyle = hollow ? palette.unknown : palette.outline
  ctx.lineWidth = hollow ? 3 : 2.2
  if (isSite) {
    const civil = spec.affiliation === 'civil'
    ctx.beginPath()
    if (civil) { for (let i = 0; i < 6; i++) { const a = (Math.PI / 3) * i - Math.PI / 6; const x = 32 + 20 * Math.cos(a); const y = 32 + 20 * Math.sin(a); i ? ctx.lineTo(x, y) : ctx.moveTo(x, y) } ctx.closePath() }
    else rr(ctx, 13, 13, 38, 38, 7)
    ctx.fillStyle = spec.condition === 'unavailable' ? 'rgba(27,33,41,0.5)' : civil ? '#2a3440' : '#243040'
    ctx.fill(); ctx.strokeStyle = spec.condition === 'normal' ? fill : conditionColor[spec.condition]; ctx.lineWidth = 2.2; ctx.stroke()
    ctx.beginPath(); (siteGlyph[spec.modelKey] ?? siteGlyph.garrison)(ctx); ctx.strokeStyle = fill; ctx.lineWidth = 2.6; ctx.stroke()
  } else {
    const draw = silhouettes[spec.modelKey] ?? silhouettes.unknown_air
    draw(ctx)
    ctx.fill(); ctx.stroke()
    if (hollow) { ctx.fillStyle = palette.unknown; ctx.font = '600 20px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText('?', 32, 33) }
    if (spec.condition === 'unavailable') { ctx.beginPath(); ctx.moveTo(14, 50); ctx.lineTo(50, 14); ctx.strokeStyle = palette.critical; ctx.lineWidth = 3.5; ctx.stroke() }
  }
  return ctx.getImageData(0, 0, SIZE * px, SIZE * px)
}

/** Small glyphs for incidents (inputs) by channel. */
export function drawIncident(severity: Severity): ImageData {
  const px = 2, S = 32
  const canvas = document.createElement('canvas'); canvas.width = S * px; canvas.height = S * px
  const ctx = canvas.getContext('2d')!; ctx.scale(px, px)
  ctx.beginPath(); ctx.moveTo(16, 3); ctx.lineTo(29, 26); ctx.lineTo(3, 26); ctx.closePath()
  ctx.fillStyle = severityColor[severity]; ctx.fill(); ctx.strokeStyle = palette.outline; ctx.lineWidth = 2; ctx.lineJoin = 'round'; ctx.stroke()
  ctx.fillStyle = palette.outline; ctx.fillRect(15, 11, 2.4, 8); ctx.fillRect(15, 21, 2.4, 2.4)
  return ctx.getImageData(0, 0, S * px, S * px)
}

export function modelKeyFor(kind: string, modelKey: string | null): string {
  if (modelKey && (silhouettes[modelKey] || siteGlyph[modelKey])) return modelKey
  return { fixed_wing: 'fighter', helicopter: 'helicopter', multirotor: 'multirotor', ground_vehicle: 'truck', vessel: 'patrol_boat', personnel: 'personnel', facility: 'garrison', infrastructure: 'comms', unknown: 'unknown_air' }[kind] ?? 'unknown_air'
}

/** Text baked into an image so labels render identically online and offline (no glyph server needed). */
export function drawLabel(text: string, opts: { size?: number; color?: string; weight?: number } = {}): ImageData {
  const px = 2, size = opts.size ?? 12, pad = 6
  const probe = document.createElement('canvas').getContext('2d')!
  probe.font = `${opts.weight ?? 600} ${size}px system-ui, -apple-system, "Segoe UI", sans-serif`
  const w = Math.ceil(probe.measureText(text).width) + pad * 2, h = size + pad * 2
  const canvas = document.createElement('canvas'); canvas.width = w * px; canvas.height = h * px
  const ctx = canvas.getContext('2d')!; ctx.scale(px, px)
  ctx.font = probe.font; ctx.textBaseline = 'middle'; ctx.textAlign = 'center'
  ctx.lineJoin = 'round'; ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(16,20,25,0.92)'; ctx.strokeText(text, w / 2, h / 2)
  ctx.fillStyle = opts.color ?? '#e8ecef'; ctx.fillText(text, w / 2, h / 2)
  return ctx.getImageData(0, 0, w * px, h * px)
}

export function drawCount(n: number): ImageData {
  return drawLabel(String(n), { size: 13, weight: 700, color: '#f4f7f9' })
}
