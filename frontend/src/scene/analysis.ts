/** Analysis surfaces on an H3 hexagon grid. One surface at a time; each answers one operational question, carries
 * the unit of its value, and can say for any cell what produced the value:
 *
 *   fusion    — rule-engine attention: Σ rule weight × distance kernel (contributions from /api/scene/attention)
 *   threat    — minutes until any unknown/suspect track could reach the cell (speed, heading penalty)
 *   coverage  — radar horizon for a 1,000 m target (4.12·(√h_radar + √h_target) km, capped by sensor range), AD
 *               engagement envelopes and airborne early warning; cells with nothing are gaps
 *   response  — minutes for the fastest ready responder: QRA fighters (5 min + d/250 m/s), helicopters
 *               (10 min + d/65 m/s), ground units (10 min + 1.35·d/18 m/s)
 *   weather   — flight category from Open-Meteo visibility, low cloud, gusts and precipitation (real data)
 *   gnss      — share of aircraft reporting degraded GNSS integrity (NIC < 7 or NACp < 8, real ADS-B)
 */
import { cellToBoundary, cellToLatLng, gridDisk, latLngToCell, polygonToCells } from 'h3-js'
import type { AttentionContribution, LiveAircraft } from '../contracts/types'
import { haversine, bearing, wrapDelta } from '../core/motion'
import type { WNode, WorldModel } from '../core/world'

export type Surface = 'fusion' | 'threat' | 'coverage' | 'response' | 'weather' | 'gnss'
export interface CellValue { h: string; value: number; label: string; reasons: string[]; color: string; height: number }
export interface SurfaceResult { surface: Surface; res: number; unit: string; legend: { color: string; label: string }[]; cells: CellValue[]; note: string }

const AOI: [number, number][] = [[10.2, 54.6], [25.2, 54.6], [25.2, 69.2], [10.2, 69.2], [10.2, 54.6]] // Sweden + Baltic approaches, [lng, lat]
const aoiCache = new Map<number, string[]>()
function aoi(res: number): string[] {
  let c = aoiCache.get(res)
  if (!c) { c = polygonToCells([AOI.map(([x, y]) => [y, x])], res); aoiCache.set(res, c) }
  return c
}
export const resForZoom = (z: number) => (z < 5.2 ? 3 : z < 6.6 ? 4 : z < 8.2 ? 5 : 6)

const ramp = (stops: [number, string][]) => (v: number) => {
  if (v <= stops[0][0]) return stops[0][1]
  for (let i = 1; i < stops.length; i++) if (v <= stops[i][0]) return stops[i][1]
  return stops[stops.length - 1][1]
}

export function fusion(contribs: AttentionContribution[], res: number): SurfaceResult {
  const acc = new Map<string, { v: number; reasons: Map<string, number> }>()
  const edgeKm = [0, 0, 158, 60, 22.6, 8.5, 3.2][res] ?? 3.2
  for (const c of contribs) {
    const center = latLngToCell(c.lat, c.lng, res)
    const k = Math.min(10, Math.ceil(c.radiusM / 1000 / (edgeKm * 1.5)) + 1)
    for (const h of gridDisk(center, k)) {
      const [lat, lng] = cellToLatLng(h)
      const d = haversine(c.lng, c.lat, lng, lat)
      const x = d / Math.max(c.radiusM, edgeKm * 1000)
      if (x >= 1) continue
      const w = c.weight * (1 - x) ** 1.5
      const cur = acc.get(h) ?? { v: 0, reasons: new Map() }
      cur.v += w; cur.reasons.set(`${c.ruleId} · ${c.reason}`, (cur.reasons.get(`${c.ruleId} · ${c.reason}`) ?? 0) + w)
      acc.set(h, cur)
    }
  }
  const max = Math.max(0.01, ...[...acc.values()].map(a => a.v))
  const col = ramp([[0.12, 'rgba(255,196,92,0.10)'], [0.3, 'rgba(255,165,64,0.2)'], [0.55, 'rgba(255,120,50,0.32)'], [0.8, 'rgba(255,80,55,0.45)'], [1, 'rgba(255,45,80,0.58)']])
  const cells: CellValue[] = []
  for (const [h, a] of acc) {
    if (a.v / max < 0.06) continue
    const reasons = [...a.reasons.entries()].sort((x, y) => y[1] - x[1]).slice(0, 4).map(([r, w]) => `${r} (${w.toFixed(2)})`)
    cells.push({ h, value: a.v, label: `attention ${a.v.toFixed(2)}`, reasons, color: col(a.v / max), height: (a.v / max) * 40_000 })
  }
  return { surface: 'fusion', res, unit: 'Σ rule weight × kernel', note: 'Where the rule engine says to look. Click a cell for the rules and inputs behind it.',
    legend: [{ color: 'rgba(255,196,92,0.5)', label: 'low' }, { color: 'rgba(255,110,48,0.8)', label: 'elevated' }, { color: 'rgba(255,40,70,0.95)', label: `high (${max.toFixed(1)})` }], cells }
}

export function threat(world: WorldModel, res: number): SurfaceResult {
  const tracks = world.leaves.filter(n => n.visible && (n.e.affiliation === 'unknown' || n.e.affiliation === 'hostile_suspected') && n.pose.speed > 0.5)
  const col = ramp([[5, 'rgba(255,48,64,0.78)'], [10, 'rgba(255,96,48,0.62)'], [20, 'rgba(255,150,40,0.45)'], [30, 'rgba(255,210,80,0.28)']])
  const cells: CellValue[] = []
  for (const h of aoi(res)) {
    const [lat, lng] = cellToLatLng(h)
    let best = Infinity, who = ''
    for (const tr of tracks) {
      const d = haversine(tr.pose.lng, tr.pose.lat, lng, lat)
      const turn = Math.abs(wrapDelta(tr.pose.heading, bearing(tr.pose.lng, tr.pose.lat, lng, lat)))
      const eff = d * (1 + 0.6 * (1 - Math.cos((turn * Math.PI) / 180)) / 2)
      const min = eff / tr.pose.speed / 60
      if (min < best) { best = min; who = tr.e.label }
    }
    if (best > 30) continue
    cells.push({ h, value: best, label: `${best.toFixed(0)} min`, reasons: [`${who} could reach this cell in ~${best.toFixed(0)} min at current speed`, 'distance stretched by up to 30 % for the turn required'], color: col(best), height: (30 - best) * 900 })
  }
  return { surface: 'threat', res, unit: 'minutes to reach', note: 'Reach of unknown and suspect tracks at their current speed (30 min horizon).',
    legend: [{ color: 'rgba(255,48,64,0.85)', label: '< 5 min' }, { color: 'rgba(255,150,40,0.7)', label: '20 min' }, { color: 'rgba(255,210,80,0.5)', label: '30 min' }], cells }
}

export function coverage(world: WorldModel, res: number): SurfaceResult {
  const sensors: { n: WNode; km: number; what: string }[] = []
  for (const n of world.leaves) {
    if (n.e.layer === 'infra.sensors') { world.poseNow(n); sensors.push({ n, km: Math.min(n.e.rangeKm ?? 180, 4.12 * (Math.sqrt(30) + Math.sqrt(1000))), what: 'surveillance radar (horizon at 1,000 m)' }) }
    else if (n.e.model === 'ad_launcher' && n.e.rangeKm) { world.poseNow(n); sensors.push({ n, km: n.e.rangeKm, what: 'air-defence envelope' }) }
    else if (n.e.model === 'aew' && (world.poseNow(n).alt ?? 0) > 3000) sensors.push({ n, km: n.e.rangeKm ?? 400, what: 'airborne early warning (airborne)' })
  }
  const cells: CellValue[] = []
  for (const h of aoi(res)) {
    const [lat, lng] = cellToLatLng(h)
    const by: string[] = []
    let ad = 0
    for (const s of sensors) {
      if (haversine(s.n.pose.lng, s.n.pose.lat, lng, lat) <= s.km * 1000) { by.push(`${s.n.e.label}: ${s.what}, ${s.km.toFixed(0)} km`); if (s.what.startsWith('air-defence')) ad++ }
    }
    const radar = by.length - ad
    const color = !by.length ? 'rgba(240,84,90,0.42)' : ad ? 'rgba(72,200,160,0.42)' : radar >= 2 ? 'rgba(80,170,255,0.30)' : 'rgba(80,170,255,0.16)'
    const label = !by.length ? 'gap' : ad ? `defended (${ad} AD)` : `${radar} sensor${radar > 1 ? 's' : ''}`
    cells.push({ h, value: by.length, label, reasons: by.length ? by.slice(0, 6) : ['no modelled radar, AEW or AD coverage at 1,000 m'], color, height: by.length ? 0 : 6000 })
  }
  return { surface: 'coverage', res, unit: 'sensors covering at 1,000 m', note: 'Radar horizon + AD envelopes + airborne AEW. Red cells are gaps.',
    legend: [{ color: 'rgba(240,84,90,0.7)', label: 'gap' }, { color: 'rgba(80,170,255,0.4)', label: 'radar' }, { color: 'rgba(80,170,255,0.6)', label: '2+ radars' }, { color: 'rgba(72,200,160,0.7)', label: 'AD envelope' }], cells }
}

export function response(world: WorldModel, res: number): SurfaceResult {
  const resp: { n: WNode; prep: number; v: number; factor: number; what: string }[] = []
  for (const n of world.leaves) {
    const st = n.status
    if (n.e.affiliation !== 'own' || (st && st[0] === 'unavailable')) continue
    if (!['fighter', 'heli_medium', 'heli_utility', 'heli_light', 'ifv'].includes(n.e.model ?? '')) continue
    world.poseNow(n)
    if (n.e.model === 'fighter' && (n.e.capabilities.includes('qra') || n.pose.alt)) resp.push({ n, prep: n.pose.alt ? 0 : 5, v: 250, factor: 1, what: n.pose.alt ? 'fighter airborne' : 'QRA fighter' })
    else if (n.e.kind === 'helicopter') resp.push({ n, prep: n.pose.alt ? 0 : 10, v: 65, factor: 1, what: 'helicopter' })
    else if (n.e.layer === 'land.manoeuvre' && n.e.model === 'ifv') resp.push({ n, prep: 10, v: 18, factor: 1.35, what: 'mechanised unit (road)' })
  }
  const col = ramp([[15, 'rgba(72,200,140,0.42)'], [30, 'rgba(160,210,90,0.38)'], [45, 'rgba(240,190,70,0.4)'], [60, 'rgba(250,130,60,0.45)'], [1e9, 'rgba(240,70,80,0.5)']])
  const cells: CellValue[] = []
  for (const h of aoi(res)) {
    const [lat, lng] = cellToLatLng(h)
    let best = Infinity, who = ''
    for (const r of resp) {
      const m = r.prep + (haversine(r.n.pose.lng, r.n.pose.lat, lng, lat) * r.factor) / r.v / 60
      if (m < best) { best = m; who = `${r.n.e.label} (${r.what})` }
    }
    cells.push({ h, value: best, label: `${best.toFixed(0)} min`, reasons: [`fastest: ${who}`, 'prep + distance ÷ speed; ground distance × 1.35 for roads'], color: col(best), height: Math.min(best, 90) * 300 })
  }
  return { surface: 'response', res, unit: 'minutes', note: 'Fastest ready responder to each cell (QRA, helicopters, mechanised units).',
    legend: [{ color: 'rgba(72,200,140,0.7)', label: '< 15 min' }, { color: 'rgba(240,190,70,0.7)', label: '45 min' }, { color: 'rgba(240,70,80,0.8)', label: '> 60 min' }], cells }
}

export interface GridPoint { lng: number; lat: number; windMps: number | null; gustMps: number | null; visibilityM: number | null; cloudLowPct: number | null; precipMm: number | null; tempC: number | null; freezingLevelM?: number | null }

export function weather(points: GridPoint[], res: number): SurfaceResult {
  const cells: CellValue[] = []
  if (!points.length) return { surface: 'weather', res, unit: 'flight category', note: 'Waiting for Open-Meteo data.', legend: [], cells }
  for (const h of aoi(res)) {
    const [lat, lng] = cellToLatLng(h)
    let best = points[0], bd = Infinity
    for (const p of points) { const d = (p.lng - lng) ** 2 * 0.3 + (p.lat - lat) ** 2; if (d < bd) { bd = d; best = p } }
    const vis = best.visibilityM ?? 20_000, low = best.cloudLowPct ?? 0, gust = best.gustMps ?? 0, pr = best.precipMm ?? 0
    const why: string[] = []
    let cat = 0
    if (vis < 1500) { cat = 3; why.push(`visibility ${(vis / 1000).toFixed(1)} km`) } else if (vis < 5000) { cat = Math.max(cat, 2); why.push(`visibility ${(vis / 1000).toFixed(1)} km`) }
    if (low > 85) { cat = Math.max(cat, 2); why.push(`low cloud ${low.toFixed(0)} %`) } else if (low > 60) { cat = Math.max(cat, 1); why.push(`low cloud ${low.toFixed(0)} %`) }
    if (gust > 20) { cat = Math.max(cat, 2); why.push(`gusts ${gust.toFixed(0)} m/s`) } else if (gust > 14) { cat = Math.max(cat, 1); why.push(`gusts ${gust.toFixed(0)} m/s`) }
    if (pr > 2) { cat = Math.max(cat, 1); why.push(`precipitation ${pr.toFixed(1)} mm`) }
    if ((best.tempC ?? 5) < 2 && pr > 0.2) { cat = Math.max(cat, 2); why.push('icing risk (precipitation near 0 °C)') }
    const label = ['VFR', 'marginal', 'IFR', 'low IFR'][cat]
    cells.push({ h, value: cat, label, reasons: why.length ? why : ['good visibility, little low cloud, light winds'],
      color: ['rgba(80,200,140,0.18)', 'rgba(90,150,255,0.35)', 'rgba(240,170,60,0.45)', 'rgba(240,70,90,0.55)'][cat], height: cat * 5000 })
  }
  return { surface: 'weather', res, unit: 'flight category', note: 'Open-Meteo (DWD ICON) current values, real. Category from visibility, low cloud, gusts, precipitation and icing.',
    legend: [{ color: 'rgba(80,200,140,0.6)', label: 'VFR' }, { color: 'rgba(90,150,255,0.7)', label: 'marginal' }, { color: 'rgba(240,170,60,0.8)', label: 'IFR' }, { color: 'rgba(240,70,90,0.85)', label: 'low IFR' }], cells }
}

export function gnss(aircraft: LiveAircraft[], res: number): SurfaceResult {
  const acc = new Map<string, { n: number; bad: number }>()
  for (const a of aircraft) {
    if (a.onGround || a.nic === null || a.nacp === null) continue
    const h = latLngToCell(a.lat, a.lng, Math.min(res, 4))
    const cur = acc.get(h) ?? { n: 0, bad: 0 }
    cur.n++; if (a.nic < 7 || a.nacp < 8) cur.bad++
    acc.set(h, cur)
  }
  const cells: CellValue[] = []
  for (const [h, a] of acc) {
    const share = a.bad / a.n
    cells.push({ h, value: share, label: `${Math.round(share * 100)} % degraded`, reasons: [`${a.bad} of ${a.n} aircraft report reduced GNSS integrity`, 'NIC < 7 or NACp < 8 (real ADS-B, adsb.lol)'],
      color: share >= 0.5 ? 'rgba(240,60,90,0.6)' : share >= 0.2 ? 'rgba(250,160,60,0.5)' : 'rgba(90,200,150,0.22)', height: share * 30_000 })
  }
  return { surface: 'gnss', res: Math.min(res, 4), unit: 'share of aircraft degraded', note: 'Real ADS-B integrity reports. Sparse at night; a cell needs aircraft to say anything.',
    legend: [{ color: 'rgba(90,200,150,0.5)', label: 'nominal' }, { color: 'rgba(250,160,60,0.8)', label: '≥ 20 %' }, { color: 'rgba(240,60,90,0.9)', label: '≥ 50 %' }], cells }
}

export function toGeoJSON(r: SurfaceResult): GeoJSON.FeatureCollection {
  return {
    type: 'FeatureCollection',
    features: r.cells.map(c => ({ type: 'Feature', id: undefined, properties: { h: c.h, color: c.color, height: c.height, label: c.label },
      geometry: { type: 'Polygon', coordinates: [cellToBoundary(c.h, true)] } })),
  }
}
