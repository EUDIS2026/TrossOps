/** Visual grammar for the scene: NATO APP-6 / MIL-STD-2525C symbols (milsymbol) for the military and civil
 * order of battle, rotated silhouettes for real public traffic, halos and heading arrows. Every image is drawn once
 * into a fixed-size cell (CELL px, 2× device scale) with its anchor at the cell centre, then uploaded to the sprite
 * atlas. One place decides what a colour or outline means. */
import ms from 'milsymbol'
import type { Condition } from '../contracts/types'

export const CELL = 128 // px in the atlas (drawn at 2×, displayed at CELL/2 css px nominal)
export const palette = {
  accent: '#4ea1ff', friend: '#80e0ff', hostile: '#ff8080', unknown: '#ffff80', neutral: '#aaffaa', civil: '#ffa1ff',
  degraded: '#f2b43a', unavailable: '#f0545a', predicted: '#ffd95a', planned: '#9fd0ff', halo: '#0a0e12',
  liveAir: '#9ec7e0', liveMil: '#ffb547', liveEmergency: '#ff5a5a', liveSea: '#7fd1b9',
}
export const conditionColor: Record<Condition, string> = { normal: 'transparent', degraded: palette.degraded, unavailable: palette.unavailable, unknown: palette.unknown }

function cell(): [HTMLCanvasElement, CanvasRenderingContext2D] {
  const c = document.createElement('canvas'); c.width = CELL; c.height = CELL
  return [c, c.getContext('2d')!]
}

/** NATO symbol for an SIDC with an operational-condition bar (amber degraded, red unavailable). */
export function natoSymbol(sidc: string, condition: Condition = 'normal', size = 30): HTMLCanvasElement {
  const sym = new ms.Symbol(sidc, { size, outlineWidth: 3, outlineColor: 'rgba(8,10,12,0.9)', strokeWidth: 3 })
  const img = sym.asCanvas(2)
  const anchor = sym.getAnchor()
  const [c, ctx] = cell()
  const ox = CELL / 2 - anchor.x * 2, oy = CELL / 2 - anchor.y * 2
  ctx.drawImage(img, ox, oy)
  if (condition !== 'normal' && condition !== 'unknown') {
    const w = size * 1.5, y = CELL / 2 + size * 1.05
    ctx.fillStyle = 'rgba(8,10,12,0.9)'; ctx.fillRect(CELL / 2 - w / 2 - 2, y - 2, w + 4, 9)
    ctx.fillStyle = conditionColor[condition]; ctx.fillRect(CELL / 2 - w / 2, y, w, 5)
    if (condition === 'unavailable') { ctx.strokeStyle = palette.unavailable; ctx.lineWidth = 4; ctx.beginPath(); ctx.moveTo(CELL / 2 - size * 0.8, CELL / 2 + size * 0.6); ctx.lineTo(CELL / 2 + size * 0.8, CELL / 2 - size * 0.6); ctx.stroke() }
  }
  return c
}

/** Heading arrow: drawn pointing up from the centre; the sprite layer rotates it. */
export function headingArrow(color = '#e9f1f7'): HTMLCanvasElement {
  const [c, ctx] = cell()
  ctx.strokeStyle = 'rgba(8,10,12,0.85)'; ctx.lineWidth = 6; ctx.lineCap = 'round'
  ctx.beginPath(); ctx.moveTo(CELL / 2, CELL / 2 - 26); ctx.lineTo(CELL / 2, CELL / 2 - 58); ctx.stroke()
  ctx.strokeStyle = color; ctx.lineWidth = 3
  ctx.beginPath(); ctx.moveTo(CELL / 2, CELL / 2 - 26); ctx.lineTo(CELL / 2, CELL / 2 - 58); ctx.stroke()
  ctx.fillStyle = color; ctx.beginPath(); ctx.moveTo(CELL / 2, CELL / 2 - 63); ctx.lineTo(CELL / 2 - 6, CELL / 2 - 51); ctx.lineTo(CELL / 2 + 6, CELL / 2 - 51); ctx.closePath(); ctx.fill()
  return c
}

export function halo(selected: boolean): HTMLCanvasElement {
  const [c, ctx] = cell()
  const r = 44
  if (selected) {
    ctx.strokeStyle = palette.accent; ctx.lineWidth = 4
    const k = 16
    for (const [sx, sy] of [[-1, -1], [1, -1], [1, 1], [-1, 1]]) { // selection brackets
      ctx.beginPath(); ctx.moveTo(CELL / 2 + sx * r, CELL / 2 + sy * (r - k)); ctx.lineTo(CELL / 2 + sx * r, CELL / 2 + sy * r); ctx.lineTo(CELL / 2 + sx * (r - k), CELL / 2 + sy * r); ctx.stroke()
    }
    ctx.fillStyle = 'rgba(78,161,255,0.10)'; ctx.beginPath(); ctx.arc(CELL / 2, CELL / 2, r - 6, 0, Math.PI * 2); ctx.fill()
  } else {
    ctx.strokeStyle = 'rgba(233,241,247,0.55)'; ctx.lineWidth = 2.5; ctx.beginPath(); ctx.arc(CELL / 2, CELL / 2, r - 8, 0, Math.PI * 2); ctx.stroke()
  }
  return c
}

/** Pulsing alert ring (static image; the layer animates scale/alpha). */
export function alertRing(color: string): HTMLCanvasElement {
  const [c, ctx] = cell()
  ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.beginPath(); ctx.arc(CELL / 2, CELL / 2, 50, 0, Math.PI * 2); ctx.stroke()
  return c
}

// ---- real public traffic -------------------------------------------------------------------------------------
const AIRCRAFT = [[0, -30], [4, -22], [4, -8], [28, 4], [28, 9], [4, 4], [3, 20], [11, 26], [11, 29], [0, 26], [-11, 29], [-11, 26], [-3, 20], [-4, 4], [-28, 9], [-28, 4], [-4, -8], [-4, -22]]
const HELI = [[0, -22], [6, -14], [6, 6], [2, 10], [2, 26], [6, 28], [-6, 28], [-2, 26], [-2, 10], [-6, 6], [-6, -14]]
const SHIP = [[0, -28], [9, -12], [9, 24], [-9, 24], [-9, -12]]

export function trafficIcon(kind: 'air' | 'heli' | 'sea', color: string, scale = 1): HTMLCanvasElement {
  const [c, ctx] = cell()
  const pts = kind === 'air' ? AIRCRAFT : kind === 'heli' ? HELI : SHIP
  ctx.translate(CELL / 2, CELL / 2); ctx.scale(scale, scale)
  ctx.beginPath(); pts.forEach(([x, y], i) => (i ? ctx.lineTo(x, y) : ctx.moveTo(x, y))); ctx.closePath()
  ctx.lineJoin = 'round'; ctx.lineWidth = 4; ctx.strokeStyle = 'rgba(6,9,12,0.9)'; ctx.stroke()
  ctx.fillStyle = color; ctx.fill()
  if (kind === 'heli') { ctx.strokeStyle = color; ctx.lineWidth = 2; ctx.beginPath(); ctx.arc(0, -2, 22, 0, Math.PI * 2); ctx.stroke() }
  return c
}

export function vesselColor(type: number | null | undefined): string {
  const t = type ?? 0
  if (t >= 70 && t < 80) return '#7fd1b9' // cargo
  if (t >= 80 && t < 90) return '#f0a35e' // tanker
  if (t >= 60 && t < 70) return '#7fb0ff' // passenger
  if (t === 30) return '#8be0e0' // fishing
  if (t === 35 || t === 55) return '#d79bff' // military / law enforcement
  if (t === 36 || t === 37) return '#c7c7c7' // sailing / pleasure
  if (t === 51 || t === 52) return '#ffd479' // SAR / tug
  return '#9fb0bd'
}

/** Small round marker with a glyph, for events (police, warnings, reports). */
export function eventMarker(color: string, glyph: string): HTMLCanvasElement {
  const [c, ctx] = cell()
  ctx.fillStyle = 'rgba(8,10,12,0.92)'; ctx.beginPath(); ctx.arc(CELL / 2, CELL / 2, 22, 0, Math.PI * 2); ctx.fill()
  ctx.strokeStyle = color; ctx.lineWidth = 4; ctx.stroke()
  ctx.fillStyle = color; ctx.font = '700 22px system-ui, sans-serif'; ctx.textAlign = 'center'; ctx.textBaseline = 'middle'; ctx.fillText(glyph, CELL / 2, CELL / 2 + 1)
  return c
}
