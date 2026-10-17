/** Map tools: measure, line of sight, range ring and a cursor elevation readout.
 *
 * One small external store (React reads it with `useTools`) and one `MapTools` instance that owns its own GeoJSON
 * source and layers on top of the operational picture and its own map listeners. While a tool is active the scene
 * controller ignores clicks and hover (see `toolCapturesMap`); while no tool is active nothing here consumes input.
 * Terrain answers come from the backend (Lantmäteriet Markhöjd Direkt); a 503 means the service is not configured
 * and every tool says so instead of guessing. */
import type { GeoJSONSource, Map as MlMap, MapMouseEvent } from 'maplibre-gl'
import { useSyncExternalStore } from 'react'
import type { LineOfSight, TerrainProfile } from '../contracts/types'
import { api, ApiError } from '../core/api'
import { actions, store } from '../core/store'
import { FONT_BOLD } from './basemap'
import { bearingDeg, destination, distanceM, fmtBearing, fmtDist, geoCircle, greatCircle, type LngLat } from './toolGeo'

export type ToolId = 'measure' | 'los' | 'ring'
export type Fetched<T> = { state: 'idle' } | { state: 'loading' } | { state: 'ok'; data: T } | { state: 'unavailable' | 'error'; note: string }

export interface ToolsState {
  tool: ToolId | null
  menu: boolean
  readout: boolean
  /** What the terrain service actually answered this session (the /api/sources row says adapter-only until probed). */
  terrain: 'working' | 'not configured' | null
  cursor: LngLat | null
  elevation: Fetched<number | null>
  measure: { points: LngLat[]; done: boolean; profile: Fetched<TerrainProfile> }
  los: { a: LngLat | null; b: LngLat | null; ha: number; hb: number; result: Fetched<LineOfSight> }
  ring: { center: LngLat | null; radiusM: number; bearing: number; fixed: boolean }
}

const initial: ToolsState = {
  tool: null, menu: false, readout: false, terrain: null, cursor: null, elevation: { state: 'idle' },
  measure: { points: [], done: false, profile: { state: 'idle' } },
  los: { a: null, b: null, ha: 2, hb: 2, result: { state: 'idle' } },
  ring: { center: null, radiusM: 25_000, bearing: 90, fixed: false },
}

let state = initial
const listeners = new Set<() => void>()
export const tools = {
  get: () => state,
  set(patch: Partial<ToolsState> | ((s: ToolsState) => Partial<ToolsState>)) {
    state = { ...state, ...(typeof patch === 'function' ? patch(state) : patch) }
    listeners.forEach(l => l())
  },
  subscribe(l: () => void) { listeners.add(l); return () => { listeners.delete(l) } },
}
export function useTools<T>(sel: (s: ToolsState) => T): T {
  return useSyncExternalStore(tools.subscribe, () => sel(state), () => sel(state))
}

/** True while a tool owns map clicks and hover (the scene controller returns early). */
export const toolCapturesMap = () => state.tool !== null

/** Human wording for terrain failures: 503 = not configured, 422 = outside coverage, 404 = older server. */
export function terrainNote(e: unknown): { state: 'unavailable' | 'error'; note: string } {
  if (e instanceof ApiError) {
    if (e.status === 503) return { state: 'unavailable', note: 'Terrain service not configured on this server (Lantmäteriet Markhöjd: adapter-only).' }
    if (e.status === 422) return { state: 'unavailable', note: /outside/i.test(e.message) ? 'Outside Sweden: Lantmäteriet elevation covers Sweden only.' : e.message }
    if (e.status === 404) return { state: 'unavailable', note: 'This server has no terrain profile endpoint yet.' }
    return { state: 'error', note: `Terrain service error (${e.status}): ${e.message}` }
  }
  return { state: 'error', note: `Terrain request failed: ${String((e as Error)?.message ?? e)}` }
}

const seen = (f: Fetched<unknown>, prev: ToolsState['terrain']): ToolsState['terrain'] =>
  f.state === 'ok' ? 'working' : f.state === 'unavailable' && /not configured/.test(f.note) ? 'not configured' : prev

export const toolActions = {
  setTool(tool: ToolId | null) {
    const s = state
    const next = s.tool === tool ? null : tool
    tools.set({ tool: next, menu: false, measure: initial.measure, los: { ...initial.los, ha: s.los.ha, hb: s.los.hb }, ring: { ...initial.ring, radiusM: s.ring.radiusM } })
    if (next) {
      if (store.get().route?.picking) actions.cancelRoute()
      if (store.get().hovered) actions.hover(null)
    }
  },
  toggleMenu(open?: boolean) { tools.set(s => ({ menu: open ?? !s.menu })) },
  toggleReadout() { tools.set(s => ({ readout: !s.readout, elevation: { state: 'idle' }, menu: false })) },
  finishMeasure() {
    const m = state.measure
    if (m.done || m.points.length < 2) return
    tools.set({ measure: { ...m, done: true } })
  },
  undoPoint() {
    const m = state.measure
    if (m.done || !m.points.length) return
    tools.set({ measure: { ...m, points: m.points.slice(0, -1) } })
  },
  clear() {
    const t = state.tool
    if (t === 'measure') tools.set({ measure: initial.measure })
    if (t === 'los') tools.set(s => ({ los: { ...s.los, a: null, b: null, result: { state: 'idle' } } }))
    if (t === 'ring') tools.set(s => ({ ring: { ...s.ring, center: null, fixed: false } }))
  },
  setHeights(ha: number | null, hb: number | null) {
    tools.set(s => ({ los: { ...s.los, ha: ha ?? s.los.ha, hb: hb ?? s.los.hb } }))
  },
  setRadius(radiusM: number) {
    if (!(radiusM > 0)) return
    tools.set(s => ({ ring: { ...s.ring, radiusM: Math.min(radiusM, 2_000_000), fixed: s.ring.center ? true : s.ring.fixed } }))
  },
  /** Escape: drop work in progress first, then leave the tool. Returns false when there was nothing to do. */
  escape(): boolean {
    const s = state
    if (s.menu) { tools.set({ menu: false }); return true }
    if (!s.tool) return false
    const inProgress = (s.tool === 'measure' && s.measure.points.length > 0 && !s.measure.done)
      || (s.tool === 'los' && s.los.a !== null && s.los.b === null) || (s.tool === 'ring' && s.ring.center !== null && !s.ring.fixed)
    if (inProgress) toolActions.clear(); else toolActions.setTool(null)
    return true
  },
}

// ---- drawing -------------------------------------------------------------------------------------------------
const SRC = 'tools'
const LAYERS = ['tools-fill', 'tools-casing', 'tools-line', 'tools-dash', 'tools-vertex', 'tools-label']
const TOP = LAYERS[LAYERS.length - 1]
const C = { measure: '#ffd95a', ok: '#4fd09a', blocked: '#f0545a', ring: '#4ea1ff', rubber: '#e6edf2' }
type Feat = GeoJSON.Feature
const line = (coords: LngLat[], color: string, extra: Record<string, unknown> = {}): Feat => ({ type: 'Feature', properties: { color, width: 2.5, ...extra }, geometry: { type: 'LineString', coordinates: coords } })
const point = (p: LngLat, props: Record<string, unknown>): Feat => ({ type: 'Feature', properties: props, geometry: { type: 'Point', coordinates: p } })
const mid = (a: LngLat, b: LngLat): LngLat => { const gc = greatCircle(a, b, distanceM(a, b) / 2 + 1); return gc.length > 2 ? gc[1] : [(a[0] + b[0]) / 2, (a[1] + b[1]) / 2] }

/** Pure: the tool drawing for a state (exported for tests). */
export function toolFeatures(s: ToolsState): Feat[] {
  const f: Feat[] = []
  if (s.tool === 'measure') {
    const pts = s.measure.points
    const live = !s.measure.done && s.cursor && pts.length ? s.cursor : null
    for (let i = 1; i < pts.length; i++) {
      f.push(line(greatCircle(pts[i - 1], pts[i]), C.measure))
      f.push(point(mid(pts[i - 1], pts[i]), { label: `${fmtDist(distanceM(pts[i - 1], pts[i]))} · ${fmtBearing(bearingDeg(pts[i - 1], pts[i]))}`, size: 11 }))
    }
    if (live) {
      f.push(line(greatCircle(pts[pts.length - 1], live), C.rubber, { dashed: true, width: 1.5 }))
      f.push(point(mid(pts[pts.length - 1], live), { label: `${fmtDist(distanceM(pts[pts.length - 1], live))} · ${fmtBearing(bearingDeg(pts[pts.length - 1], live))}`, size: 11, dim: true }))
    }
    pts.forEach((p, i) => f.push(point(p, { vertex: true, color: C.measure, r: i === 0 ? 5 : 4 })))
    if (pts.length >= 2 || live) {
      let total = 0
      for (let i = 1; i < pts.length; i++) total += distanceM(pts[i - 1], pts[i])
      if (live) total += distanceM(pts[pts.length - 1], live)
      f.push(point(live ?? pts[pts.length - 1], { label: `Total ${fmtDist(total)}`, size: 13, bold: true, anchor: 'top', roff: 1.1 }))
    }
  }
  if (s.tool === 'los') {
    const { a, b } = s.los
    const r = s.los.result.state === 'ok' ? s.los.result.data : null
    if (a && b && r) {
      const cl = r.profile.clearanceM, pts = r.profile.points
      const k = cl.findIndex(c => c !== null && c <= 0)
      if (k < 0) f.push(line([a, b], C.ok, { width: 3 }))
      else { f.push(line([a, pts[k]], C.ok, { width: 3 })); f.push(line([pts[k], b], C.blocked, { width: 3 })) }
      if (r.obstruction) f.push(point([r.obstruction.lng, r.obstruction.lat], { vertex: true, color: C.blocked, r: 6, label: `Masked by ground ${Math.round(r.obstruction.groundM)} m`, size: 11, anchor: 'top', roff: 1.1 }))
    } else if (a && b) f.push(line([a, b], C.rubber, { dashed: true, width: 1.5 }))
    else if (a && s.cursor) {
      f.push(line([a, s.cursor], C.rubber, { dashed: true, width: 1.5 }))
      f.push(point(mid(a, s.cursor), { label: fmtDist(distanceM(a, s.cursor)), size: 11, dim: true }))
    }
    if (a) f.push(point(a, { vertex: true, color: '#80e0ff', r: 6, label: `Observer +${s.los.ha} m`, size: 11, anchor: 'bottom', roff: 1.1 }))
    if (b) f.push(point(b, { vertex: true, color: r ? (r.visible ? C.ok : C.blocked) : '#e6edf2', r: 6, label: `Target +${s.los.hb} m`, size: 11, anchor: 'bottom', roff: 1.1 }))
  }
  if (s.tool === 'ring' && s.ring.center) {
    const c = s.ring.center
    const radius = s.ring.fixed || !s.cursor ? s.ring.radiusM : distanceM(c, s.cursor)
    const brg = s.ring.fixed || !s.cursor ? s.ring.bearing : bearingDeg(c, s.cursor)
    if (radius > 0) {
      const ring = geoCircle(c, radius)
      f.push({ type: 'Feature', properties: { fill: true }, geometry: { type: 'Polygon', coordinates: [ring] } })
      f.push(line(ring, C.ring, { width: 2, dashed: !s.ring.fixed }))
      const end = destination(c, brg, radius)
      f.push(line([c, end], C.ring, { width: 1.5, dashed: true }))
      f.push(point(mid(c, end), { label: `r ${fmtDist(radius)}`, size: 12, bold: true }))
    }
    f.push(point(c, { vertex: true, color: C.ring, r: 4 }))
  }
  return f
}

export class MapTools {
  private unsubTools: () => void
  private unsubApp: () => void
  private readoutTimer = 0
  private moveRaf = 0
  private losTimer = 0
  private losAbort: AbortController | null = null
  private profileAbort: AbortController | null = null
  private elevAbort: AbortController | null = null
  private elevCache = new Map<string, Fetched<number | null>>()
  private terrainMissing = false
  private dblZoomWas: boolean | null = null
  private prevTool: ToolId | null = null
  private lastLos = ''
  private lastProfile = ''

  constructor(private map: MlMap) {
    this.map.on('styledata', this.ensure)
    this.ensure()
    this.map.on('click', this.onClick)
    this.map.on('dblclick', this.onDblClick)
    this.map.on('mousemove', this.onMove)
    this.map.on('mouseout', this.onOut)
    window.addEventListener('keydown', this.onKey, true)
    this.unsubTools = tools.subscribe(() => this.onState())
    Object.assign(window as unknown as Record<string, unknown>, { __tools: tools }) // like __store: for smoke scripts
    // Route picking (Inspector) owns the next click: a tool would swallow it, so step aside.
    this.unsubApp = store.subscribe(() => { if (state.tool && store.get().route?.picking) toolActions.setTool(null) })
    this.onState()
  }

  dispose() {
    this.map.off('styledata', this.ensure)
    this.map.off('click', this.onClick); this.map.off('dblclick', this.onDblClick)
    this.map.off('mousemove', this.onMove); this.map.off('mouseout', this.onOut)
    window.removeEventListener('keydown', this.onKey, true)
    this.unsubTools(); this.unsubApp()
    window.clearTimeout(this.readoutTimer); window.clearTimeout(this.losTimer); cancelAnimationFrame(this.moveRaf)
    this.losAbort?.abort(); this.profileAbort?.abort(); this.elevAbort?.abort()
  }

  /** (Re)install after any style change (basemap switch replaces the style) and keep the tool layers on top. */
  private ensure = () => {
    const m = this.map
    try {
      if (!m.getSource(SRC) || !m.getLayer(TOP)) { this.install(); return }
      const order = m.getLayersOrder()
      if (order[order.length - 1] !== TOP) for (const id of LAYERS) m.moveLayer(id)
    } catch { /* style still loading: the next styledata event retries */ }
  }

  private install() {
    const m = this.map
    if (!m.getSource(SRC)) m.addSource(SRC, { type: 'geojson', data: { type: 'FeatureCollection', features: [] } })
    const add = (layer: Parameters<MlMap['addLayer']>[0]) => { if (!m.getLayer(layer.id)) m.addLayer(layer) }
    add({ id: 'tools-fill', type: 'fill', source: SRC, filter: ['has', 'fill'], paint: { 'fill-color': 'rgba(78,161,255,0.07)' } })
    add({ id: 'tools-casing', type: 'line', source: SRC, filter: ['all', ['==', ['geometry-type'], 'LineString'], ['!', ['has', 'dashed']]],
      layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': '#05080b', 'line-opacity': 0.75, 'line-width': ['+', ['get', 'width'], 3] } })
    add({ id: 'tools-line', type: 'line', source: SRC, filter: ['all', ['==', ['geometry-type'], 'LineString'], ['!', ['has', 'dashed']]],
      layout: { 'line-cap': 'round', 'line-join': 'round' }, paint: { 'line-color': ['get', 'color'], 'line-width': ['get', 'width'] } })
    add({ id: 'tools-dash', type: 'line', source: SRC, filter: ['all', ['==', ['geometry-type'], 'LineString'], ['has', 'dashed']],
      paint: { 'line-color': ['get', 'color'], 'line-width': ['get', 'width'], 'line-opacity': 0.85, 'line-dasharray': [2, 2] } })
    add({ id: 'tools-vertex', type: 'circle', source: SRC, filter: ['has', 'vertex'],
      paint: { 'circle-radius': ['get', 'r'], 'circle-color': ['get', 'color'], 'circle-stroke-color': '#05080b', 'circle-stroke-width': 2, 'circle-pitch-alignment': 'map' } })
    add({ id: 'tools-label', type: 'symbol', source: SRC, filter: ['has', 'label'],
      layout: { 'text-field': ['get', 'label'], 'text-font': FONT_BOLD, 'text-size': ['coalesce', ['get', 'size'], 11], 'text-anchor': ['coalesce', ['get', 'anchor'], 'center'], 'text-radial-offset': ['coalesce', ['get', 'roff'], 0],
        'text-allow-overlap': true, 'text-ignore-placement': true, 'text-padding': 0 },
      paint: { 'text-color': ['case', ['has', 'dim'], '#c9d3db', '#ffffff'], 'text-halo-color': '#05080b', 'text-halo-width': 1.8 } })
    this.draw(true)
  }

  private drawnEmpty = false
  private draw(force = false) {
    const features = toolFeatures(state)
    if (!features.length && this.drawnEmpty && !force) return
    this.drawnEmpty = !features.length
    ;(this.map.getSource(SRC) as GeoJSONSource | undefined)?.setData({ type: 'FeatureCollection', features })
  }

  private onState() {
    const s = state
    if (s.tool !== this.prevTool) {
      const canvas = this.map.getCanvas()
      if (s.tool && !this.prevTool) { this.dblZoomWas = this.map.doubleClickZoom.isEnabled(); this.map.doubleClickZoom.disable() }
      if (!s.tool && this.prevTool) { if (this.dblZoomWas) this.map.doubleClickZoom.enable(); this.dblZoomWas = null }
      canvas.style.cursor = s.tool ? 'crosshair' : ''
      this.prevTool = s.tool
    }
    // line of sight: (re)query when both ends or the heights change
    const { a, b, ha, hb } = s.los
    const losKey = s.tool === 'los' && a && b ? `${a}|${b}|${ha}|${hb}` : ''
    if (losKey !== this.lastLos) {
      this.lastLos = losKey
      window.clearTimeout(this.losTimer); this.losAbort?.abort()
      if (losKey) {
        if (s.los.result.state !== 'loading') tools.set(t => ({ los: { ...t.los, result: { state: 'loading' } } }))
        this.losTimer = window.setTimeout(() => void this.runLos(a!, b!, ha, hb), 250)
      }
    }
    // measure: ground profile once the line is finished
    const m = s.measure
    const profKey = s.tool === 'measure' && m.done ? m.points.map(p => p.join(',')).join(';') : ''
    if (profKey !== this.lastProfile) {
      this.lastProfile = profKey
      this.profileAbort?.abort()
      if (profKey) void this.runProfile(m.points)
    }
    this.draw()
  }

  private async runLos(a: LngLat, b: LngLat, ha: number, hb: number) {
    const ctl = new AbortController(); this.losAbort = ctl
    let result: Fetched<LineOfSight>
    try { result = { state: 'ok', data: await api.lineOfSight(a, b, ha, hb, ctl.signal) } } catch (e) { if (ctl.signal.aborted) return; result = terrainNote(e) }
    if (ctl.signal.aborted) return
    tools.set(s => ({ los: { ...s.los, result }, terrain: seen(result, s.terrain) }))
  }

  private async runProfile(points: LngLat[]) {
    const ctl = new AbortController(); this.profileAbort = ctl
    tools.set(s => ({ measure: { ...s.measure, profile: { state: 'loading' } } }))
    let profile: Fetched<TerrainProfile>
    try { profile = { state: 'ok', data: await api.terrainProfile(points, 160, ctl.signal) } } catch (e) { if (ctl.signal.aborted) return; profile = terrainNote(e) }
    if (ctl.signal.aborted) return
    tools.set(s => ({ measure: { ...s.measure, profile }, terrain: seen(profile, s.terrain) }))
  }

  private onClick = (e: MapMouseEvent) => {
    const s = state
    if (!s.tool) return
    const p: LngLat = [e.lngLat.lng, e.lngLat.lat]
    if (s.tool === 'measure') {
      const m = s.measure
      tools.set({ measure: m.done ? { points: [p], done: false, profile: { state: 'idle' } } : { ...m, points: [...m.points, p] } })
    } else if (s.tool === 'los') {
      const l = s.los
      tools.set({ los: !l.a || l.b ? { ...l, a: p, b: null, result: { state: 'idle' } } : { ...l, b: p } })
    } else if (s.tool === 'ring') {
      const r = s.ring
      if (!r.center || r.fixed) tools.set({ ring: { ...r, center: p, fixed: false } })
      else tools.set({ ring: { ...r, radiusM: Math.max(1, distanceM(r.center, p)), bearing: bearingDeg(r.center, p), fixed: true } })
    }
  }

  private onDblClick = (e: MapMouseEvent) => {
    if (!state.tool) return
    e.preventDefault()
    if (state.tool !== 'measure') return
    // the two clicks of a double-click each added a vertex: drop near-duplicates (within 6 px)
    const pts = state.measure.points.slice()
    const px = (p: LngLat) => this.map.project(p)
    while (pts.length > 2) {
      const q1 = px(pts[pts.length - 1]), q0 = px(pts[pts.length - 2])
      if (Math.hypot(q1.x - q0.x, q1.y - q0.y) > 6) break
      pts.pop()
    }
    tools.set(s => ({ measure: { ...s.measure, points: pts } }))
    toolActions.finishMeasure()
  }

  private onMove = (e: MapMouseEvent) => {
    if (!state.tool && !state.readout) return
    const p: LngLat = [e.lngLat.lng, e.lngLat.lat]
    this.pending = p
    if (!this.moveRaf) this.moveRaf = requestAnimationFrame(() => { this.moveRaf = 0; tools.set({ cursor: this.pending }) })
    if (state.readout) this.scheduleReadout(p)
  }
  private pending: LngLat | null = null
  private onOut = () => { tools.set({ cursor: null }); window.clearTimeout(this.readoutTimer) }

  /** Elevation under the cursor 250 ms after it stops; cached by ~10 m cells; stops asking once the service says 503. */
  private scheduleReadout(p: LngLat) {
    window.clearTimeout(this.readoutTimer)
    const key = `${p[0].toFixed(4)},${p[1].toFixed(4)}`
    const hit = this.elevCache.get(key)
    if (hit) { if (state.elevation !== hit) tools.set({ elevation: hit }); return }
    if (this.terrainMissing) { tools.set({ elevation: { state: 'unavailable', note: 'Terrain service not configured (Lantmäteriet Markhöjd: adapter-only).' } }); return }
    if (state.elevation.state !== 'loading') tools.set({ elevation: { state: 'loading' } })
    this.readoutTimer = window.setTimeout(async () => {
      this.elevAbort?.abort()
      const ctl = new AbortController(); this.elevAbort = ctl
      let v: Fetched<number | null>
      try { v = { state: 'ok', data: (await api.elevation(p[0], p[1], ctl.signal)).groundM } } catch (e) {
        if (ctl.signal.aborted) return
        v = terrainNote(e)
        if (e instanceof ApiError && e.status === 503) this.terrainMissing = true
      }
      if (v.state !== 'error') { this.elevCache.set(key, v); if (this.elevCache.size > 600) this.elevCache.delete(this.elevCache.keys().next().value!) }
      const cur = state.cursor
      tools.set(s => ({ terrain: seen(v, s.terrain) }))
      if (!ctl.signal.aborted && cur && `${cur[0].toFixed(4)},${cur[1].toFixed(4)}` === key) tools.set({ elevation: v })
    }, 250)
  }

  private onKey = (e: KeyboardEvent) => {
    const el = e.target as HTMLElement | null
    const tag = el?.tagName
    if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT' || el?.isContentEditable) return
    if (e.metaKey || e.ctrlKey || e.altKey) return
    const k = e.key.toLowerCase()
    const take = () => { e.preventDefault(); e.stopImmediatePropagation() }
    if (e.key === 'Escape') { if (toolActions.escape()) take(); return }
    if (k === 'm') { take(); toolActions.setTool('measure') }
    else if (k === 'v') { take(); toolActions.setTool('los') }
    else if (k === 'c') { take(); toolActions.setTool('ring') }
    else if (k === 'e') { take(); toolActions.toggleReadout() }
    else if (k === 't') { take(); toolActions.toggleMenu() }
    else if (e.key === 'Enter' && state.tool === 'measure' && tag !== 'BUTTON') { take(); toolActions.finishMeasure() }
    else if (e.key === 'Backspace' && state.tool === 'measure') { take(); toolActions.undoPoint() }
  }
}
