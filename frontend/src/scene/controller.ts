/** SceneController owns the MapLibre map, the frame loop, picking and camera intent. React never re-renders per
 * frame: the controller reads the store, the session's clock and the world model directly. */
import { Map as MlMap, LngLatBounds, NavigationControl, ScaleControl, setWorkerUrl, type MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// MapLibre 6 locates its worker relative to import.meta.url; under Vite that points at the pre-bundled dependency,
// so the worker is resolved as an asset instead (dev, build and offline bundle alike).
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
setWorkerUrl(maplibreWorkerUrl)
import type { Condition, LiveAircraft, LiveVessel, SiteLayout, Snapshot } from '../contracts/types'
import { api } from '../core/api'
import type { Session } from '../core/session'
import { actions, analysisLayer, currentMode, layerOn, store, type AppState, type Basemap, type SelectionKind } from '../core/store'
import { mercX, mercY, type WNode, type WorldModel } from '../core/world'
import * as A from './analysis'
import { ATTRIBUTION, TERRAIN_TILEJSON, styleFor } from './basemap'
import { CinematicCamera } from './camera'
import { ModelLayer, modelZoomFor, type ModelInstance } from './models3d'
import { addOverlays, circleRing, DETAIL_LAYERS, empty, nightPolygon, OVERLAY_LAYERS, setData } from './overlays'
import { SpriteLayer } from './sprites'
import { WindLayer } from './windfield'
import { halo, headingArrow, natoSymbol, palette, trafficIcon, vesselColor } from './symbols'
import { hasTopdown, topdownImage, TOPDOWN_FILL } from './topdown'
import { MODEL_SPECS, type ModelKey } from './three/models'

const ECHELON_PX: Record<string, number> = { service: 60, division: 58, brigade: 56, regiment: 54, battalion: 52, company: 48, platoon: 46 }
const AFF_LABEL: Record<string, string> = { own: '#a6e6ff', allied: '#a6e6ff', civil: '#f2b8f2', unknown: '#ffff8c', hostile_suspected: '#ff9a9a' }
const COND: Condition[] = ['normal', 'degraded', 'unknown', 'unavailable']

interface Drawn { kind: SelectionKind; id: string; lng: number; lat: number; alt: number | null; r: number }

function spriteFactory(key: string): HTMLCanvasElement {
  const [kind, a, b] = key.split('|')
  if (kind === 'ms') return natoSymbol(a, (b as Condition) || 'normal')
  if (kind === 'arrow') return headingArrow(a || '#e9f1f7')
  if (kind === 'halo') return halo(a === '1')
  if (kind === 'ac') return trafficIcon(a === 'heli' ? 'heli' : 'air', a === 'mil' ? palette.liveMil : a === 'emg' ? palette.liveEmergency : palette.liveAir, a === 'heavy' ? 1.25 : 1)
  if (kind === 'vs') return trafficIcon('sea', a, 0.9)
  if (kind === 'td') return topdownImage(a as ModelKey, b)
  return natoSymbol('SUGP--------')
}

export class SceneController {
  readonly map: MlMap
  readonly sprites = new SpriteLayer('symbols', spriteFactory)
  readonly models = new ModelLayer()
  readonly wind = new WindLayer()
  readonly camera: CinematicCamera
  private raf = 0
  private styleReady = false
  private basemap: Basemap
  private prev: Partial<AppState> = {}
  private unsubscribe: () => void
  private drawn: Drawn[] = []
  private lastLabels = 0
  private lastAnalysis = 0
  private analysisKey = ''
  private contributions: Awaited<ReturnType<typeof api.attention>>['contributions'] = []
  private grid: A.GridPoint[] = []
  private layouts = new Map<string, SiteLayout | 'loading'>()
  private layoutsDirty = false
  private envAt: Record<string, number> = {}
  private onLayers = new Set<string>()
  private counties: Promise<GeoJSON.FeatureCollection> | null = null
  private disposed = false

  constructor(container: HTMLElement, private session: Session) {
    const s = store.get()
    this.basemap = s.basemap
    this.map = new MlMap({
      container, style: styleFor(s.basemap), center: [s.camera.lng, s.camera.lat], zoom: s.camera.zoom, pitch: s.camera.pitch, bearing: s.camera.bearing,
      minZoom: 2.5, maxZoom: 19, maxPitch: 80, attributionControl: { compact: true, customAttribution: ATTRIBUTION[s.basemap] }, cancelPendingTileRequestsWhileZooming: false,
      canvasContextAttributes: { antialias: true },
    })
    this.camera = new CinematicCamera(this.map)
    Object.assign(window as unknown as Record<string, unknown>, { __map: this.map, __scene: this, __store: store, __session: session })
    this.map.on('style.load', () => { this.styleReady = true; this.install(); store.set({ basemapStatus: this.basemap === 'offline' ? 'offline' : 'online' }) })
    this.map.on('error', e => {
      const msg = String((e as unknown as { error?: Error }).error?.message ?? '')
      if (this.basemap !== 'offline' && !this.styleReady && !/worker/i.test(msg) && /style|Failed to fetch|NetworkError/i.test(msg)) actions.setBasemap('offline')
    })
    this.map.on('moveend', () => {
      const c = this.map.getCenter()
      store.set({ camera: { zoom: this.map.getZoom(), pitch: this.map.getPitch(), bearing: this.map.getBearing(), lng: c.lng, lat: c.lat } })
      void this.loadLayoutsInView()
    })
    this.map.on('click', e => this.onClick(e))
    this.map.on('mousemove', e => this.onHover(e))
    this.map.on('mouseout', () => actions.hover(null))
    for (const ev of ['dragstart', 'wheel', 'touchstart'] as const) this.map.on(ev, () => { this.camera.interrupt(); if (store.get().follow && ev === 'dragstart') store.set({ follow: false }) })
    this.map.addControl(new NavigationControl({ visualizePitch: true, showCompass: true }), 'bottom-right')
    this.map.addControl(new ScaleControl({ maxWidth: 110, unit: 'metric' }), 'bottom-left')
    this.unsubscribe = store.subscribe(() => this.onStore())
    session.onWorld = w => this.onWorld(w)
    this.raf = requestAnimationFrame(t => this.frame(t))
  }

  dispose() { this.disposed = true; cancelAnimationFrame(this.raf); this.unsubscribe(); this.map.remove() }

  // ---- installation -----------------------------------------------------------------------------------------
  private install() {
    addOverlays(this.map)
    if (!this.map.getLayer(this.models.id)) this.map.addLayer(this.models)
    if (!this.map.getLayer(this.wind.id)) this.map.addLayer(this.wind, 'reports')
    if (!this.map.getLayer(this.sprites.id)) this.map.addLayer(this.sprites, 'labels')
    this.prev = {}
    this.onStore()
    if (this.session.world) this.onWorld(this.session.world)
    this.layoutsDirty = true
    this.applyLayouts()
  }

  private onWorld(w: WorldModel) {
    if (!this.styleReady) return
    setData(this.map, 'cables', { type: 'FeatureCollection', features: w.catalog.cables.map(c => ({ type: 'Feature', properties: { id: c.id, label: c.label, kind: c.kind }, geometry: { type: 'LineString', coordinates: c.coords } })) })
    setData(this.map, 'plans', { type: 'FeatureCollection', features: w.catalog.plans.map(p => ({ type: 'Feature', properties: { id: p.entityId, label: p.label }, geometry: { type: 'LineString', coordinates: p.path.map(v => [v[0], v[1]]) } })) })
  }

  // ---- store reactions ----------------------------------------------------------------------------------------
  private onStore() {
    if (this.disposed) return
    const s = store.get()
    if (s.basemap !== this.basemap) { this.switchBasemap(s.basemap); return }
    if (!this.styleReady) return
    const p = this.prev
    this.prev = s // before reacting: reactions may update the store, which re-enters here
    if (s.views !== p.views || s.roleId !== p.roleId || s.modeId !== p.modeId || s.layerOverrides !== p.layerOverrides || s.threeD !== p.threeD) this.applyLayers(s)
    const modeChanged = (s.modeId !== p.modeId || s.roleId !== p.roleId) && p.modeId !== undefined
    if (s.threeD !== p.threeD) this.apply3d(s, modeChanged)
    if (modeChanged) { const mode = currentMode(s); if (mode) this.camera.fly({ ...mode.camera, pitch: s.threeD ? Math.max(mode.camera.pitch, 50) : mode.camera.pitch }, s.reducedMotion) }
    if (s.terrain !== p.terrain) this.applyTerrain(s)
    if (s.snapshot !== p.snapshot && s.snapshot) this.applySnapshot(s.snapshot)
    if (s.selected !== p.selected) this.applySelection(s)
    if (s.route !== p.route) this.applyRoute(s)
    if (s.live !== p.live && layerOn(s, 'analysis.gnss')) this.analysisKey = ''
  }

  private switchBasemap(next: Basemap) {
    this.basemap = next
    this.styleReady = false
    store.set({ basemapStatus: 'loading' })
    this.map.setStyle(styleFor(next), { diff: false })
    const ctrl = (this.map as unknown as { _controls: { _updateAttributions?: () => void; options?: { customAttribution?: string } }[] })._controls?.find(c => c.options && 'customAttribution' in c.options)
    if (ctrl?.options) { ctrl.options.customAttribution = ATTRIBUTION[next]; ctrl._updateAttributions?.() }
  }

  private vis(id: string, on: boolean) { if (this.map.getLayer(id)) this.map.setLayoutProperty(id, 'visibility', on ? 'visible' : 'none') }

  private applyLayers(s: AppState) {
    this.onLayers = new Set((s.views?.layers ?? []).filter(l => layerOn(s, l.id)).map(l => l.id))
    for (const [layer, ids] of Object.entries(OVERLAY_LAYERS)) for (const id of ids) this.vis(id, this.onLayers.has(layer))
    for (const [layer, ids] of Object.entries(DETAIL_LAYERS)) {
      for (const id of ids) {
        const on = this.onLayers.has(layer)
        if (this.map.getLayer(`${id}-flat`)) { this.vis(id, on && s.threeD); this.vis(`${id}-flat`, on && !s.threeD) } else this.vis(id, on)
      }
    }
    this.vis('site-logistics-bund', this.onLayers.has('detail.logistics'))
    this.wind.enabled = this.onLayers.has('env.wind')
    const an = analysisLayer(s)
    this.vis('analysis-fill', !!an && !s.threeD); this.vis('analysis-3d', !!an && s.threeD)
    if (!an) { setData(this.map, 'analysis', empty()); store.set({ analysisInfo: null }) }
    this.analysisKey = ''
    if (this.onLayers.has('env.radar')) void this.ensureRadar(); else if (this.map.getLayer('radar')) this.vis('radar', false)
    this.envAt = {}
    void this.refreshEnvironment()
  }

  private apply3d(s: AppState, cameraBusy = false) {
    this.models.enabled = s.threeD
    const pitch = this.map.getPitch()
    if (!cameraBusy && !this.map.isMoving()) {
      if (s.threeD && pitch < 35) this.map.easeTo({ pitch: 58, duration: s.reducedMotion ? 0 : 900 })
      if (!s.threeD && pitch > 0) this.map.easeTo({ pitch: 0, duration: s.reducedMotion ? 0 : 600 })
    }
    this.applyLayers(s)
  }

  private applyTerrain(s: AppState) {
    if (s.terrain && this.basemap !== 'offline') {
      if (!this.map.getSource('dem')) this.map.addSource('dem', { type: 'raster-dem', url: TERRAIN_TILEJSON })
      this.map.setTerrain({ source: 'dem', exaggeration: 1.2 })
      if (!this.map.getLayer('hillshade')) this.map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'dem', paint: { 'hillshade-exaggeration': 0.35, 'hillshade-shadow-color': '#05080b', 'hillshade-highlight-color': '#3a4652', 'hillshade-accent-color': '#0d1318' } }, this.map.getLayer('road-minor') ? 'road-minor' : 'night')
      if (!this.map.getLayer('sky')) this.map.setSky({ 'sky-color': '#0b1520', 'horizon-color': '#1a2836', 'fog-color': '#0d151d', 'fog-ground-blend': 0.6, 'horizon-fog-blend': 0.6, 'sky-horizon-blend': 0.7, 'atmosphere-blend': 0.5 })
    } else {
      if (this.map.getTerrain()) this.map.setTerrain(null)
      if (this.map.getLayer('hillshade')) this.map.removeLayer('hillshade')
    }
  }

  // ---- data application ------------------------------------------------------------------------------------------
  private applySnapshot(snap: Snapshot) {
    const m = this.map
    setData(m, 'areas', { type: 'FeatureCollection', features: snap.areas.map(a => ({ type: 'Feature', properties: { id: a.id, label: a.label, kind: a.kind, status: a.status ?? 'n/a' }, geometry: { type: 'Polygon', coordinates: [a.ring] } })) })
    setData(m, 'predictions', { type: 'FeatureCollection', features: snap.predictions.map(p => ({ type: 'Feature', properties: { id: p.entityId, p: p.probability, label: `${p.hypothesis} · ${Math.round(p.probability * 100)} %` },
      geometry: { type: 'LineString', coordinates: p.points.map(q => [q[0], q[1]]) } })) })
    setData(m, 'prediction-rings', { type: 'FeatureCollection', features: snap.predictions.filter(p => p.uncertaintyRing).map(p => ({ type: 'Feature', properties: { id: p.entityId }, geometry: { type: 'Polygon', coordinates: [p.uncertaintyRing!] } })) })
    const rank = { info: 3, advisory: 2, warning: 1, critical: 0 }
    setData(m, 'reports', { type: 'FeatureCollection', features: snap.inputs.filter(i => i.position && i.channel !== 'police_event').map(i => ({ type: 'Feature', properties: { id: i.id, severity: i.severity, title: i.title, rank: rank[i.severity] },
      geometry: { type: 'Point', coordinates: [i.position!.longitudeDeg, i.position!.latitudeDeg] } })) })
    const w = this.session.world
    if (w) {
      const lines: GeoJSON.Feature[] = []
      for (const iv of snap.interventions) {
        const opt = iv.options.find(o => o.id === (iv.committedOptionId ?? iv.recommendedOptionId))
        const unit = opt?.assignedEntityIds[0] ? w.get(opt.assignedEntityIds[0]) : undefined
        if (!iv.position || !unit) continue
        const pose = w.poseNow(unit)
        lines.push({ type: 'Feature', properties: { id: iv.id, committed: !!iv.committedOptionId }, geometry: { type: 'LineString', coordinates: [[pose.lng, pose.lat], iv.position] } })
      }
      setData(m, 'interventions', { type: 'FeatureCollection', features: lines })
    }
    this.analysisKey = ''
    if (analysisLayer(store.get()) === 'analysis.fusion') void this.refreshContributions()
  }

  private async refreshContributions() {
    try {
      const s = store.get()
      const att = await api.attention(this.session.clock.mode === 'sim' ? Math.round(this.session.clock.now()) : null, 'regional', s.roleId)
      this.contributions = att.contributions; this.analysisKey = ''
    } catch { /* keep */ }
  }

  private applyRoute(s: AppState) {
    const r = s.route
    this.map.getCanvas().style.cursor = r?.picking ? 'crosshair' : ''
    if (!r?.result) { setData(this.map, 'route-preview', empty()); return }
    setData(this.map, 'route-preview', { type: 'FeatureCollection', features: r.result.options.map(o => ({ type: 'Feature', properties: { id: o.id, selected: o.id === r.option }, geometry: { type: 'LineString', coordinates: o.path.map(v => [v[0], v[1]]) } })) })
    const b = new LngLatBounds()
    for (const o of r.result.options) for (const v of o.path) b.extend([v[0], v[1]])
    if (!b.isEmpty()) this.map.fitBounds(b, { padding: { top: 120, bottom: 160, left: 120, right: 460 }, duration: s.reducedMotion ? 0 : 1400, pitch: s.threeD ? 45 : 0 })
  }

  // ---- environment (real public feeds) ------------------------------------------------------------------------
  private due(key: string, ms: number) { const now = performance.now(); if (now - (this.envAt[key] ?? -1e12) < ms) return false; this.envAt[key] = now; return true }

  /** Real environment and civil feeds; each source is fetched independently so one failure never starves another. */
  private async refreshEnvironment() {
    const on = this.onLayers
    const m = this.map
    const job = async (key: string, ms: number, enabled: boolean, fn: () => Promise<void>) => {
      if (!enabled || !this.due(key, ms)) return
      try { await fn() } catch { delete this.envAt[key] } // retry on the next pass; Sources shows the feed status
    }
    await Promise.all([
      job('police', 300_000, on.has('civil.police_events'), async () => {
        const r = await api.police()
        setData(m, 'police', { type: 'FeatureCollection', features: (r.items ?? []).filter(e => e.lng != null).map(e => {
          const kw = (e.keywords as string[] | undefined) ?? []
          const jit = ((Number(String(e.id).slice(-3)) || 0) % 360) * Math.PI / 180 // county centroids stack: spread markers a little
          return { type: 'Feature', properties: { id: String(e.id), name: e.name, type: e.type, alert: kw.length > 0 },
            geometry: { type: 'Point', coordinates: [(e.lng as number) + 0.06 * Math.cos(jit), (e.lat as number) + 0.03 * Math.sin(jit)] } }
        }) })
      }),
      job('warnings', 300_000, on.has('env.warnings'), async () => {
        const r = await api.warnings()
        setData(m, 'warnings', { type: 'FeatureCollection', features: (r.items ?? []).filter(w => w.geometry).map(w => ({ type: 'Feature', properties: { id: String(w.id), level: w.level, event: w.event, area: w.areaName }, geometry: w.geometry as GeoJSON.Geometry })) })
      }),
      job('obs', 600_000, on.has('env.obs'), async () => {
        const r = await api.observations()
        const st = ((r as unknown as { stations?: Record<string, unknown>[] }).stations ?? r.items ?? []) as Record<string, number | string | null>[]
        setData(m, 'stations', { type: 'FeatureCollection', features: st.filter(x => x.lng != null).map(x => ({ type: 'Feature', properties: { id: String(x.id), name: x.name,
          text: [x.airTempC != null ? `${Math.round(Number(x.airTempC))}°` : '', x.windMps != null ? `${Math.round(Number(x.windMps))} m/s` : '', x.visibilityM != null && Number(x.visibilityM) < 10000 ? `vis ${(Number(x.visibilityM) / 1000).toFixed(1)} km` : ''].filter(Boolean).join(' · ') },
          geometry: { type: 'Point', coordinates: [Number(x.lng), Number(x.lat)] } })) })
      }),
      job('grid', 900_000, on.has('env.wind') || on.has('analysis.weather'), async () => {
        const r = await api.grid()
        this.grid = (r.points ?? []) as unknown as A.GridPoint[]
        this.wind.setField(this.grid as never)
        setData(m, 'wind', { type: 'FeatureCollection', features: (r.points ?? []).filter(p => p.windDirDeg != null).map(p => ({ type: 'Feature', properties: { dir: p.windDirDeg, speed: p.windMps }, geometry: { type: 'Point', coordinates: [p.lng as number, p.lat as number] } })) })
        this.analysisKey = ''
      }),
      job('night', 60_000, on.has('env.daylight'), async () => { setData(m, 'night', nightPolygon(new Date())) }),
      job('traffic', 300_000, on.has('civil.traffic'), async () => {
        const r = await api.traffic()
        setData(m, 'traffic', { type: 'FeatureCollection', features: (r.items ?? []).filter(t => t.lng != null).map(t => ({ type: 'Feature', properties: { id: String(t.id), type: t.type, name: `${t.type}: ${t.roadNumber ?? ''} ${t.location ?? ''}`.trim(), message: t.message }, geometry: { type: 'Point', coordinates: [t.lng as number, t.lat as number] } })) })
      }),
      job('fires', 900_000, on.has('env.fires'), async () => {
        const r = await api.fires()
        setData(m, 'fires', { type: 'FeatureCollection', features: (r.items ?? []).map(f => ({ type: 'Feature', properties: { id: f.id, frp: f.frpMw, daynight: f.daynight, confidence: f.confidence, acquired: f.acquired }, geometry: { type: 'Point', coordinates: [f.lng as number, f.lat as number] } })) })
      }),
      job('crisis', 300_000, on.has('civil.crisis'), async () => {
        // Active VMA (public warnings) are issued for named counties: draw those counties from the bundled SCB borders.
        const [r, counties] = await Promise.all([api.crisis(), this.counties ??= fetch('/data/sweden_counties.geojson').then(x => x.json() as Promise<GeoJSON.FeatureCollection>)])
        const norm = (x: string) => x.toLowerCase().replace(/ län$/, '').replace(/s$/, '').trim()
        const vma = (r.items ?? []).filter(i => i.kind === 'vma')
        const hit = (f: GeoJSON.Feature) => vma.find(v => ((v.areas as string[] | undefined) ?? []).some(a => norm(a) === norm(String(f.properties?.name ?? ''))))
        const feats = counties.features.filter(f => hit(f)).map(f => ({ ...f, properties: { ...f.properties, headline: hit(f)?.headline } }))
        setData(m, 'crisis', { type: 'FeatureCollection', features: feats })
      }),
    ])
  }

  private async ensureRadar() {
    try {
      const r = await api.radar()
      const frame = r.frames?.[r.frames.length - 1]
      if (!frame) return
      const url = frame.tileUrl
      const src = this.map.getSource('radar') as unknown as { tiles?: string[]; setTiles?: (t: string[]) => void } | undefined
      if (src?.setTiles) src.setTiles([url])
      else {
        this.map.addSource('radar', { type: 'raster', tiles: [url], tileSize: 256, maxzoom: r.maxZoom ?? 7, attribution: 'Radar: RainViewer' })
        this.map.addLayer({ id: 'radar', type: 'raster', source: 'radar', paint: { 'raster-opacity': 0.62, 'raster-fade-duration': 0 } }, 'analysis-fill')
      }
      this.vis('radar', true)
    } catch { /* status in Sources */ }
  }

  // ---- site detail --------------------------------------------------------------------------------------------
  private async loadLayoutsInView() {
    const w = this.session.world
    if (!w || this.map.getZoom() < 10.8) return
    const b = this.map.getBounds()
    // any site whose footprint touches the (slightly padded) viewport, not only those whose centre is visible
    const pad = 0.02, W = b.getWest() - pad, E = b.getEast() + pad, S = b.getSouth() - pad, N = b.getNorth() + pad
    const touches = (fp: number[][]) => fp.some(p => p[0] >= W && p[0] <= E && p[1] >= S && p[1] <= N) || (fp.length > 0 && Math.min(...fp.map(p => p[0])) <= W && Math.max(...fp.map(p => p[0])) >= E && Math.min(...fp.map(p => p[1])) <= S && Math.max(...fp.map(p => p[1])) >= N)
    const want = w.catalog.sites.filter(si => !this.layouts.has(si.id) && (touches(si.footprint) || b.contains([si.center[0], si.center[1]]))).slice(0, 6)
    await Promise.all(want.map(async si => {
      this.layouts.set(si.id, 'loading')
      try { this.layouts.set(si.id, await api.layout(si.id)); this.layoutsDirty = true } catch { this.layouts.delete(si.id) }
    }))
    this.applyLayouts()
  }

  private applyLayouts() {
    if (!this.layoutsDirty || !this.styleReady) return
    this.layoutsDirty = false
    const feats: GeoJSON.Feature[] = []
    for (const l of this.layouts.values()) if (l !== 'loading') feats.push(...l.features.features)
    setData(this.map, 'site-detail', { type: 'FeatureCollection', features: feats })
    this.models.setProps(feats)
  }

  // ---- selection and camera -------------------------------------------------------------------------------------
  private applySelection(s: AppState) {
    const sel = s.selected
    const w = this.session.world
    setData(this.map, 'ranges', empty())
    setData(this.map, 'trails', empty())
    if (!sel || !w) return
    const rm = s.reducedMotion
    if (sel.kind === 'entity' || sel.kind === 'track') {
      const n = w.get(sel.id)
      if (!n) return
      const p = w.poseNow(n)
      const air = n.e.domain === 'air' || (n.pose.alt ?? 0) > 200
      this.camera.focusPoint(p.lng, p.lat, air ? Math.max(this.map.getZoom(), 10.5) : n.e.domain === 'sea' ? 12.8 : 14.2, s.threeD ? (air ? 62 : 58) : this.map.getPitch(), rm, air && s.threeD ? p.alt ?? 0 : 0)
      if (n.e.rangeKm && n.e.kind !== 'formation' && (n.e.capabilities.includes('air_defence') || n.e.layer === 'infra.sensors')) {
        setData(this.map, 'ranges', { type: 'FeatureCollection', features: [{ type: 'Feature', properties: { color: n.e.capabilities.includes('air_defence') ? '#48c8a0' : '#6ab4ff' }, geometry: { type: 'LineString', coordinates: circleRing(p.lng, p.lat, n.e.rangeKm * 1000) } }] })
      }
    } else if (sel.kind === 'formation') {
      const n = w.get(sel.id)
      if (!n) return
      const leaves = w.leavesOf(n)
      const b = new LngLatBounds()
      for (const l of leaves) { const p = w.poseNow(l); b.extend([p.lng, p.lat]) }
      if (!b.isEmpty()) this.camera.focusBounds(b, s.threeD ? 50 : this.map.getPitch(), rm)
    } else if (sel.kind === 'site') {
      const site = w.catalog.sites.find(x => x.id === sel.id)
      const n = w.get(sel.id)
      const c = site?.center ?? (n ? [n.pose.lng, n.pose.lat] : null)
      if (!c) return
      if (!s.threeD) store.set({ threeD: true, terrain: true })
      const zoom = site?.kind === 'airbase' ? 14.3 : site?.kind === 'navbase' ? 15.2 : 15.4
      this.camera.cinematicSite(c[0], c[1], zoom, (site?.axis ?? 0) - 35, rm)
      void this.loadLayoutsInView()
    } else if (sel.kind === 'aircraft' || sel.kind === 'vessel') {
      const it = sel.data as LiveAircraft | LiveVessel | undefined
      if (it) this.camera.focusPoint(it.lng, it.lat, Math.max(this.map.getZoom(), sel.kind === 'aircraft' ? 9 : 11.5), this.map.getPitch(), rm, 0)
    } else if (sel.kind === 'input' || sel.kind === 'alert' || sel.kind === 'police' || sel.kind === 'warning') {
      const snap = s.snapshot
      const pos = sel.kind === 'input' ? snap?.inputs.find(i => i.id === sel.id)?.position : null
      const a = sel.kind === 'alert' ? snap?.alerts.find(x => x.id === sel.id)?.position : null
      const ll = pos ? [pos.longitudeDeg, pos.latitudeDeg] : a ?? (sel.data as { lng?: number; lat?: number } | undefined)?.lng !== undefined ? [(sel.data as { lng: number }).lng, (sel.data as { lat: number }).lat] : null
      if (ll) this.camera.focusPoint(ll[0], ll[1], Math.max(this.map.getZoom(), 7.5), this.map.getPitch(), rm, 0)
    } else if (sel.kind === 'area') {
      const area = s.snapshot?.areas.find(a => a.id === sel.id)
      if (area) { const b = new LngLatBounds(); area.ring.forEach(p => b.extend(p as [number, number])); this.camera.focusBounds(b, this.map.getPitch(), rm) }
    }
  }

  flyToMode() { const mode = currentMode(store.get()); if (mode) this.camera.fly(mode.camera, store.get().reducedMotion) }

  // ---- frame loop ---------------------------------------------------------------------------------------------
  private frame(now: number) {
    if (this.disposed) return
    this.raf = requestAnimationFrame(t => this.frame(t))
    const w = this.session.world
    if (!this.styleReady || !w) return
    const s = store.get()
    const t = this.session.clock.now()
    const live = this.session.clock.mode === 'live'
    const scope = s.snapshot?.scope ? new Set(s.snapshot.scope) : null
    const on = this.onLayers
    w.update(t, n => {
      const layer = n.e.affiliation === 'unknown' ? 'track.unknown' : n.e.layer ?? ''
      return on.has(layer) && (!scope || scope.has(n.e.id))
    }, this.session.buffer, live ? this.session.buffer.renderTime() : t)
    const zoom = this.map.getZoom()
    const worldPx = 512 * 2 ** zoom
    const b = this.map.getBounds()
    const view = { minx: mercX(b.getWest()), maxx: mercX(b.getEast()), miny: mercY(b.getNorth()), maxy: mercY(b.getSouth()) }
    const sel = s.selected
    const pin = new Set<string>()
    if (sel && (sel.kind === 'entity' || sel.kind === 'track')) { const n = w.get(sel.id); if (n) for (const a of w.chain(n)) pin.add(a.e.id) }
    const items = this.declutter(w.cut(worldPx, view, pin, Math.round(Math.min(900, 70 * 1.55 ** Math.max(0, zoom - 4.5)))), zoom, now)
    const c = this.map.getCenter()
    const cx = mercX(c.lng), cy = mercY(c.lat)
    const bearing = this.map.getBearing()
    const zs = Math.max(0.78, Math.min(1.15, 0.8 + (zoom - 5) * 0.035))
    const models3d = s.threeD
    const modelInstances: ModelInstance[] = []
    this.sprites.begin(cx, cy)
    const drawn: Drawn[] = []
    const hovered = s.hovered?.id
    for (const it of items) {
      const n = it.node
      const e = n.e
      const isSite = e.kind === 'facility' || e.kind === 'infrastructure'
      const leafModel = models3d && !it.aggregate && !isSite && !!e.model && zoom >= modelZoomFor(e.model)
      const cond = it.aggregate ? COND[n.worst] ?? 'normal' : (n.status?.[0] ?? 'normal')
      const size = (it.aggregate ? ECHELON_PX[e.echelon ?? 'company'] ?? 48 : isSite ? 52 : 46) * zs * (isSite && (zoom > 13.5 || zoom < 6.5) ? 0.72 : 1)
      const mx = mercX(it.lng), my = mercY(it.lat)
      const alt = !it.aggregate && n.pose.alt && n.pose.alt > 0 ? n.pose.alt : null
      const selected = sel?.id === e.id
      if (selected || hovered === e.id) this.sprites.push(mx, my, alt, it.lat, `halo|${selected ? 1 : 0}`, size * 1.25, 0, 1)
      if (leafModel) {
        modelInstances.push({ id: e.id, lng: it.lng, lat: it.lat, alt: n.pose.alt, heading: n.pose.heading, pitch: n.pose.pitch, bank: n.pose.bank, model: e.model!, affiliation: e.affiliation, condition: cond, selected, speed: n.pose.speed })
      } else if (!s.threeD && zoom >= 14.6 && !it.aggregate && !isSite && hasTopdown(e.model)) {
        // street zoom in 2D: the platform itself, at true scale and heading, instead of its frame symbol
        const spec = MODEL_SPECS[e.model]
        const mpp = (156543.03392 * Math.cos((it.lat * Math.PI) / 180)) / 2 ** zoom
        const px = Math.max(22, Math.max(spec.lengthM, spec.widthM) / TOPDOWN_FILL / mpp)
        this.sprites.push(mx, my, null, it.lat, `td|${e.model}|${e.affiliation}`, px, n.pose.heading - bearing, n.status?.[5] ? 0.55 : 1)
        if (cond !== 'normal') this.sprites.push(mx, my, null, it.lat, `halo|0`, px * 0.8, 0, 1)
      } else {
        this.sprites.push(mx, my, alt, it.lat, `ms|${e.sidc ?? 'SUGP--------'}|${cond}`, size, 0, n.status?.[5] ? 0.55 : 1)
        if (!it.aggregate && n.pose.speed > 0.5) this.sprites.push(mx, my, alt, it.lat, `arrow|${e.affiliation === 'unknown' ? '#ffff8c' : e.affiliation === 'civil' ? '#f2b8f2' : '#d8f4ff'}`, size, n.pose.heading - bearing, 0.95)
      }
      drawn.push({ kind: e.kind === 'formation' ? 'formation' : isSite ? 'site' : e.affiliation === 'unknown' ? 'track' : 'entity', id: e.id, lng: it.lng, lat: it.lat, alt, r: size * 0.36 })
    }
    // real public traffic (dead-reckoned from the last fetch)
    if (live) {
      const dt = Math.min(60, (performance.now() - s.live.at) / 1000)
      const showAir = on.has('live.air'), showMil = on.has('live.air_mil')
      if (showAir || showMil) for (const a of s.live.aircraft) {
        if (!showAir && !a.military) continue
        const [lng, lat] = dr(a.lng, a.lat, a.headingDeg, a.onGround ? 0 : a.speedMps, dt)
        const cls = a.emergency || ['7500', '7600', '7700'].includes(a.squawk ?? '') ? 'emg' : a.military ? 'mil' : a.category === 'A7' ? 'heli' : a.category === 'A5' || a.category === 'A4' ? 'heavy' : 'civil'
        const sz = (a.military ? 46 : 38) * zs
        const mx = mercX(lng), my = mercY(lat)
        if (mx < view.minx - 0.01 || mx > view.maxx + 0.01 || my < view.miny - 0.01 || my > view.maxy + 0.01) continue
        if (sel?.id === a.id || hovered === a.id) this.sprites.push(mx, my, a.altM, lat, `halo|${sel?.id === a.id ? 1 : 0}`, sz * 1.3, 0, 1)
        if (models3d && !a.onGround && zoom >= 9.5) modelInstances.push({ id: a.id, lng, lat, alt: a.altM, heading: a.headingDeg ?? 0, pitch: 0, bank: 0, model: a.category === 'A5' ? 'widebody' : a.category === 'A1' ? 'ga_prop' : a.category === 'A7' ? 'heli_light' : 'airliner', affiliation: 'civil', condition: 'normal', selected: sel?.id === a.id, speed: a.speedMps ?? 0 })
        else this.sprites.push(mx, my, a.altM, lat, `ac|${cls}`, sz, (a.headingDeg ?? 0) - bearing, a.seenS != null && a.seenS > 30 ? 0.5 : 0.95)
        drawn.push({ kind: 'aircraft', id: a.id, lng, lat, alt: a.altM, r: sz * 0.3 })
      }
      if (on.has('live.sea')) for (const v of s.live.vessels) {
        const [lng, lat] = dr(v.lng, v.lat, v.courseDeg, v.speedMps, dt)
        const mx = mercX(lng), my = mercY(lat)
        if (mx < view.minx - 0.01 || mx > view.maxx + 0.01 || my < view.miny - 0.01 || my > view.maxy + 0.01) continue
        const sz = 34 * zs
        if (sel?.id === String(v.id) || hovered === String(v.id)) this.sprites.push(mx, my, null, lat, `halo|${sel?.id === String(v.id) ? 1 : 0}`, sz * 1.3, 0, 1)
        if (models3d && zoom >= 11.5) modelInstances.push({ id: String(v.id), lng, lat, alt: null, heading: v.headingDeg ?? v.courseDeg ?? 0, pitch: 0, bank: 0, model: vesselModel(v.shipType), affiliation: 'civil', condition: 'normal', selected: sel?.id === String(v.id), speed: v.speedMps ?? 0 })
        else this.sprites.push(mx, my, null, lat, `vs|${vesselColor(v.shipType)}`, sz, (v.headingDeg ?? v.courseDeg ?? 0) - bearing, (v.speedMps ?? 0) > 0.3 ? 0.95 : 0.6)
        drawn.push({ kind: 'vessel', id: String(v.id), lng, lat, alt: null, r: sz * 0.3 })
      }
    }
    this.sprites.commit()
    this.models.setInstances(modelInstances, zoom)
    this.drawn = drawn
    if (now - this.lastLabels > 250) { this.lastLabels = now; this.updateLabels(items, s, zoom) }
    if (now - this.lastAnalysis > 1500) { this.lastAnalysis = now; this.updateAnalysis(s, w, zoom); void this.refreshEnvironment(); this.updateTrail(s, w, t) }
    this.followCamera(s, w)
  }

  /** Screen-space declutter for aggregates and sites below street zoom: a symbol that would overlap one already
   * placed is nudged outward on rings of candidate offsets and tied to its true position with a leader line.
   * Placements are remembered per id so symbols do not hop between frames; moving platforms are never displaced. */
  private placed = new Map<string, [number, number]>()
  private leaders: number[][][] = []
  private declutter(items: ReturnType<WorldModel['cut']>, zoom: number, now: number) {
    if (zoom >= 11.5) { if (this.leaders.length && now - this.lastLabels > 250) { this.leaders = []; setData(this.map, 'leaders', empty()) } return items }
    const R = 30
    const occupied: [number, number][] = []
    const order = items.map((it, i) => ({ it, i, pri: it.aggregate ? 1000 + it.count : it.node.e.kind === 'facility' || it.node.e.kind === 'infrastructure' ? 500 : it.node.pose.speed > 0.5 ? 2000 : 100 }))
      .sort((a, b) => b.pri - a.pri || (a.it.node.e.id < b.it.node.e.id ? -1 : 1))
    const leaders: number[][][] = []
    const free = (x: number, y: number) => occupied.every(([ox, oy]) => (ox - x) ** 2 + (oy - y) ** 2 >= R * R)
    for (const o of order) {
      const it = o.it
      const p = this.map.project([it.lng, it.lat])
      const movable = it.aggregate || it.node.e.kind === 'facility' || it.node.e.kind === 'infrastructure'
      let x = p.x, y = p.y
      if (movable && !free(x, y)) {
        const prev = this.placed.get(it.node.e.id)
        let found = false
        if (prev && free(p.x + prev[0], p.y + prev[1])) { x = p.x + prev[0]; y = p.y + prev[1]; found = true }
        for (let ring = 1; ring <= 3 && !found; ring++) for (let k = 0; k < 8 && !found; k++) {
          const a = (k / 8) * Math.PI * 2 + ring * 0.4, dx = Math.cos(a) * R * 1.15 * ring, dy = Math.sin(a) * R * 1.15 * ring
          if (free(p.x + dx, p.y + dy)) { x = p.x + dx; y = p.y + dy; found = true }
        }
        if (found) {
          this.placed.set(it.node.e.id, [x - p.x, y - p.y])
          const ll = this.map.unproject([x, y])
          leaders.push([[it.lng, it.lat], [ll.lng, ll.lat]])
          it.lng = ll.lng; it.lat = ll.lat
        }
      } else if (movable) this.placed.delete(it.node.e.id)
      occupied.push([x, y])
    }
    if (now - this.lastLabels > 250) { this.leaders = leaders; setData(this.map, 'leaders', { type: 'FeatureCollection', features: leaders.map(c => ({ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: c } })) }) }
    return items
  }

  private updateLabels(items: ReturnType<WorldModel['cut']>, s: AppState, zoom: number) {
    if (!this.onLayers.has('picture.labels')) return
    const feats: GeoJSON.Feature[] = []
    for (const it of items) {
      const e = it.node.e
      const isSite = e.kind === 'facility' || e.kind === 'infrastructure'
      if (!it.aggregate && !isSite && zoom < 9 && s.selected?.id !== e.id && e.affiliation !== 'unknown') continue
      if (isSite && zoom < 6.5 && !/^(airbase|navbase)/.test(e.id) && s.selected?.id !== e.id) continue
      const text = it.aggregate ? `${e.short ?? e.label} · ${it.count}` : isSite ? e.label : zoom >= 12 ? e.label : (e.short ?? e.label)
      feats.push({ type: 'Feature', properties: { text, agg: it.aggregate, rank: it.aggregate ? 0 : isSite ? 1 : 2, color: AFF_LABEL[e.affiliation] ?? '#dfe6ec' }, geometry: { type: 'Point', coordinates: [it.lng, it.lat] } })
    }
    if (zoom >= 8) for (const a of s.live.aircraft) if (a.military || zoom >= 9) {
      if (!this.onLayers.has('live.air') && !(a.military && this.onLayers.has('live.air_mil'))) continue
      feats.push({ type: 'Feature', properties: { text: `${a.callsign ?? a.id}${a.altM ? ` FL${Math.round(a.altM / 30.48)}` : ''}`, agg: false, rank: 3, color: a.military ? palette.liveMil : '#9ec7e0' }, geometry: { type: 'Point', coordinates: [a.lng, a.lat] } })
    }
    if (zoom >= 10.5 && this.onLayers.has('live.sea')) for (const v of s.live.vessels) if (v.name) feats.push({ type: 'Feature', properties: { text: v.name, agg: false, rank: 4, color: '#9fe0cc' }, geometry: { type: 'Point', coordinates: [v.lng, v.lat] } })
    setData(this.map, 'labels', { type: 'FeatureCollection', features: feats })
  }

  private updateAnalysis(s: AppState, w: WorldModel, zoom: number) {
    const an = analysisLayer(s)
    if (!an) return
    const res = A.resForZoom(zoom)
    const surface = an.split('.')[1] as A.Surface
    const dynamic = surface === 'threat' || surface === 'response' || surface === 'coverage'
    const key = `${surface}:${res}:${dynamic ? Math.floor(performance.now() / 5000) : ''}`
    if (key === this.analysisKey) return
    this.analysisKey = key
    if (surface === 'fusion' && !this.contributions.length) void this.refreshContributions()
    if (surface === 'weather' && !this.grid.length) { delete this.envAt.grid; void this.refreshEnvironment() }
    const r = surface === 'fusion' ? A.fusion(this.contributions, Math.max(4, Math.min(res, 6))) : surface === 'threat' ? A.threat(w, res) : surface === 'coverage' ? A.coverage(w, Math.min(res, 5))
      : surface === 'response' ? A.response(w, Math.min(res, 4)) : surface === 'weather' ? A.weather(this.grid, Math.min(res, 4)) : A.gnss(s.live.aircraft, res)
    this.lastSurface = r
    setData(this.map, 'analysis', A.toGeoJSON(r))
    store.set({ analysisInfo: { surface: r.surface, unit: r.unit, legend: r.legend, note: r.note, cells: r.cells.length } })
  }
  lastSurface: A.SurfaceResult | null = null

  private trailKey = ''
  private trailFetched = 0
  private updateTrail(s: AppState, w: WorldModel, t: number) {
    const sel = s.selected
    if (sel?.kind === 'aircraft') {
      // real ADS-B history kept by the backend (~30 min)
      if (performance.now() - this.trailFetched > 10_000 || this.trailKey !== sel.id) {
        this.trailFetched = performance.now(); this.trailKey = sel.id
        api.aircraftTrail(sel.id).then(r => { if (store.get().selected?.id === sel.id) setData(this.map, 'trails', { type: 'FeatureCollection', features: r.points.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: r.points.map(q => [q.lng, q.lat]) } }] : [] }) }).catch(() => undefined)
      }
      return
    }
    if (!sel || sel.kind !== 'entity' || !this.onLayers.has('picture.trails')) { if (this.trailKey) { this.trailKey = ''; setData(this.map, 'trails', empty()) } return }
    const n = w.get(sel.id)
    if (!n?.motion) return
    this.trailKey = sel.id
    const coords: number[][] = []
    const pose = { ...n.pose }
    for (let k = 40; k >= 0; k--) { const tt = t - k * 30; if (tt >= 0) coords.push(this.samplePose(n, tt)) }
    Object.assign(n.pose, pose)
    setData(this.map, 'trails', { type: 'FeatureCollection', features: coords.length > 1 ? [{ type: 'Feature', properties: {}, geometry: { type: 'LineString', coordinates: coords } }] : [] })
  }
  private samplePose(n: WNode, t: number): number[] {
    const saved = n.visible
    n.visible = false
    const w = this.session.world!
    const prevT = w.t
    w.t = t
    const p = w.poseNow(n)
    const out = [p.lng, p.lat]
    w.t = prevT
    n.visible = saved
    return out
  }

  private followCamera(s: AppState, w: WorldModel) {
    if (!s.follow || !s.selected || this.map.isMoving()) { if (!s.follow && !this.map.getCenterClampedToGround()) this.map.setCenterClampedToGround(true); return }
    let lng: number | undefined, lat: number | undefined, alt = 0, heading: number | null = null
    if (s.selected.kind === 'entity' || s.selected.kind === 'track') {
      const n = w.get(s.selected.id)
      if (!n) return
      lng = n.pose.lng; lat = n.pose.lat; alt = n.pose.alt ?? 0; heading = n.pose.speed > 0.5 ? n.pose.heading : null
    } else if (s.selected.kind === 'aircraft') {
      const a = s.live.aircraft.find(x => x.id === s.selected!.id)
      if (a) { [lng, lat] = dr(a.lng, a.lat, a.headingDeg, a.speedMps, Math.min(60, (performance.now() - s.live.at) / 1000)); alt = a.altM ?? 0; heading = a.headingDeg }
    }
    if (lng === undefined || lat === undefined) return
    if (s.threeD && alt > 0) { this.map.setCenterClampedToGround(false); this.map.setCenterElevation(alt) }
    else if (!this.map.getCenterClampedToGround()) this.map.setCenterClampedToGround(true)
    const opts: { center: [number, number]; bearing?: number } = { center: [lng, lat] }
    if (s.threeD && s.cinematic && heading !== null) { const cur = this.map.getBearing(); const d = ((heading - cur + 540) % 360) - 180; opts.bearing = cur + d * 0.04 }
    this.map.jumpTo(opts)
  }

  // ---- interaction --------------------------------------------------------------------------------------------
  private pick(x: number, y: number): Drawn | null {
    let best: Drawn | null = null, bestD = Infinity
    for (const d of this.drawn) {
      const p = this.map.project([d.lng, d.lat])
      const dd = (p.x - x) ** 2 + (p.y - y) ** 2
      const r = Math.max(14, d.r)
      if (dd < r * r && dd < bestD) { bestD = dd; best = d }
    }
    return best
  }

  private onClick(e: MapMouseEvent) {
    const s = store.get()
    if (s.route?.picking) { void this.session.planRoute(s.route.entityId, [e.lngLat.lng, e.lngLat.lat]); return }
    const hit = this.pick(e.point.x, e.point.y)
    if (hit) {
      const data = hit.kind === 'aircraft' ? s.live.aircraft.find(a => a.id === hit.id) : hit.kind === 'vessel' ? s.live.vessels.find(v => String(v.id) === hit.id) : undefined
      if (hit.kind === 'formation' && this.session.world) {
        actions.select('formation', hit.id)
        return
      }
      actions.select(hit.kind, hit.id, data)
      return
    }
    const layers = ['police', 'traffic', 'fires', 'reports', 'warnings-fill', 'analysis-fill', 'analysis-3d', 'cables-line', 'areas-fill', 'site-buildings-flat', 'site-buildings', 'site-logistics-flat', 'site-logistics', 'site-footprint'].filter(id => this.map.getLayer(id) && this.map.getLayoutProperty(id, 'visibility') !== 'none')
    const f = this.map.queryRenderedFeatures([[e.point.x - 4, e.point.y - 4], [e.point.x + 4, e.point.y + 4]], { layers })[0]
    if (!f) { if (!s.route) actions.deselect(); return }
    const lid = f.layer.id, p = f.properties as Record<string, unknown>
    if (lid === 'police') actions.select('police', String(p.id), { lng: e.lngLat.lng, lat: e.lngLat.lat })
    else if (lid === 'traffic' || lid === 'fires') actions.select('warning', String(p.id), { ...p, event: lid === 'fires' ? `Thermal anomaly (FRP ${p.frp ?? '?'} MW)` : p.name, level: lid === 'fires' ? 'NASA FIRMS' : 'Trafikverket' })
    else if (lid === 'reports') actions.select('input', String(p.id))
    else if (lid === 'warnings-fill') actions.select('warning', String(p.id), p)
    else if (lid.startsWith('analysis')) { const cell = this.lastSurface?.cells.find(c => c.h === p.h); actions.select('cell', String(p.h), { cell, surface: this.lastSurface?.surface, unit: this.lastSurface?.unit, note: this.lastSurface?.note }) }
    else if (lid === 'cables-line') actions.select('cable', String(p.id), p)
    else if (lid === 'areas-fill') actions.select('area', String(p.id))
    else if (lid.startsWith('site-')) actions.select('site', String(p.siteId), { feature: p })
  }

  private hoverRaf = 0
  private onHover(e: MapMouseEvent) {
    if (this.hoverRaf) return
    this.hoverRaf = requestAnimationFrame(() => {
      this.hoverRaf = 0
      const s = store.get()
      if (s.route?.picking) return
      const hit = this.pick(e.point.x, e.point.y)
      this.map.getCanvas().style.cursor = hit ? 'pointer' : ''
      if (!hit) { if (s.hovered) actions.hover(null); return }
      if (s.hovered?.id === hit.id) return
      actions.hover({ kind: hit.kind, id: hit.id, x: e.point.x, y: e.point.y, ...this.describe(hit, s) })
    })
  }

  private describe(hit: Drawn, s: AppState): { title: string; lines: string[] } {
    const w = this.session.world
    if (hit.kind === 'aircraft') {
      const a = s.live.aircraft.find(x => x.id === hit.id)
      return { title: a?.callsign ?? hit.id, lines: [`${a?.type ?? 'aircraft'} ${a?.registration ?? ''}${a?.military ? ' · military-flagged' : ''}`, `${a?.altM != null ? `${Math.round(a.altM)} m` : '—'} · ${a?.speedMps != null ? `${Math.round(a.speedMps * 1.944)} kt` : '—'} · ${a?.squawk ?? '----'}`, 'Live ADS-B (real)'] }
    }
    if (hit.kind === 'vessel') {
      const v = s.live.vessels.find(x => String(x.id) === hit.id)
      return { title: v?.name ?? `MMSI ${hit.id}`, lines: [`${v?.shipTypeLabel ?? 'vessel'} · ${v?.navStatusLabel ?? ''}`, `${v?.speedMps != null ? `${(v.speedMps * 1.944).toFixed(1)} kn` : '—'}${v?.destination ? ` → ${v.destination}` : ''}`, 'Live AIS (real)'] }
    }
    const n = w?.get(hit.id)
    if (!n) return { title: hit.id, lines: [] }
    const e = n.e
    if (e.kind === 'formation') {
      return { title: e.label, lines: [`${n.count} platforms${n.moving ? ` · ${n.moving} moving` : ''}`, `${e.echelon ?? ''} · ${e.layer ?? ''}`] }
    }
    const st = n.status
    const lines = [e.platform ?? e.kind.replace('_', ' ')]
    if (n.pose.speed > 0.5) lines.push(`${Math.round(n.pose.speed * 3.6)} km/h · hdg ${Math.round(n.pose.heading)}°${n.pose.alt ? ` · ${Math.round(n.pose.alt)} m` : ''}`)
    if (st) lines.push(`${st[0]} · readiness ${st[1] != null ? Math.round(st[1] * 100) : '—'} %${st[2] != null ? ` · fuel ${Math.round(st[2])} %` : ''}`)
    if (e.affiliation === 'unknown') { const d = s.snapshot?.deception[e.id]; if (d) lines.push(`deception: ${d.band} (${Math.round(d.probability * 100)} %)`) }
    return { title: e.label, lines }
  }
}

function dr(lng: number, lat: number, heading: number | null, speed: number | null, dt: number): [number, number] {
  if (!speed || heading == null || dt <= 0) return [lng, lat]
  const d = speed * dt, r = (heading * Math.PI) / 180
  return [lng + (d * Math.sin(r)) / (111_320 * Math.cos((lat * Math.PI) / 180)), lat + (d * Math.cos(r)) / 111_320]
}

function vesselModel(t: number | null): string {
  const x = t ?? 0
  if (x >= 80 && x < 90) return 'tanker'
  if (x >= 70 && x < 80) return 'cargo_ship'
  if (x >= 60 && x < 70) return 'ferry'
  if (x === 30) return 'fishing'
  if (x === 52) return 'tug'
  if (x === 36 || x === 37) return 'sailboat'
  if (x === 55) return 'coast_guard'
  return 'cargo_ship'
}
