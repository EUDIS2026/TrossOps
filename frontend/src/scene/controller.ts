/** SceneController owns the MapLibre map, every scene source/layer, the render loop and camera intents.
 * React never re-renders per frame: the controller reads the store and the entity buffer directly. */
import { Map as MlMap, LngLatBounds, NavigationControl, ScaleControl, setWorkerUrl, type GeoJSONSource, type LayerSpecification, type LngLatLike, type MapMouseEvent } from 'maplibre-gl'
import 'maplibre-gl/dist/maplibre-gl.css'
// MapLibre 6 locates its worker relative to import.meta.url. Under Vite (dev and build) that URL points at the
// pre-bundled dependency, where no worker file exists, so every GeoJSON/vector source silently fails to load.
// Resolving the worker as an asset makes it correct in dev, in the production build and in the offline bundle.
import maplibreWorkerUrl from 'maplibre-gl/dist/maplibre-gl-worker.mjs?url'
setWorkerUrl(maplibreWorkerUrl)
import type { Feature, FeatureCollection, Point } from 'geojson'
import type { AttentionResponse, Condition, SceneEntity, Snapshot } from '../contracts/types'
import { api } from '../core/api'
import { EntityBuffer } from '../core/entityBuffer'
import { actions, currentMode, layerOn, store, type AppState, type Basemap } from '../core/store'
import { ATTRIBUTION, TERRAIN_TILEJSON, VECTOR_TILES_URL, styleFor } from './basemap'
import { ModelLayer, type ModelInstance } from './models3d'
import { SpriteLayer, type SpriteInstance } from './sprites'
import { drawCount, drawIcon, drawIncident, drawLabel, iconId, modelKeyFor, palette, parseIconId, SIZE } from './semantics'

type FC = FeatureCollection
const empty = (): FC => ({ type: 'FeatureCollection', features: [] })
const SEV_RANK: Record<Condition, number> = { normal: 0, degraded: 1, unknown: 2, unavailable: 3 }
const MOBILE = new Set(['fixed_wing', 'helicopter', 'multirotor', 'ground_vehicle', 'vessel', 'personnel', 'unknown'])

export const SPRITE_MIN_ZOOM = 8.3
export const MODEL_MIN_ZOOM = 13
export function iconScale(zoom: number): number { return zoom <= 4 ? 0.4 : zoom <= 8 ? 0.4 + ((zoom - 4) / 4) * 0.12 : zoom <= 12 ? 0.52 + ((zoom - 8) / 4) * 0.18 : zoom <= 16 ? 0.7 + ((zoom - 12) / 4) * 0.25 : 0.95 }

export function attentionResolutionFor(zoom: number): AppState['attentionResolution'] {
  return zoom < 5.6 ? 'national' : zoom < 8.6 ? 'regional' : 'local'
}

export class SceneController {
  readonly map: MlMap
  readonly buffer = new EntityBuffer()
  readonly models = new ModelLayer()
  readonly sprites = new SpriteLayer()
  private lastSourceUpdate = 0
  private lastPoses = new Map<string, { lng: number; lat: number }>()
  private raf = 0
  private styleReady = false
  private basemap: Basemap
  private unsubscribe: () => void
  private prev: Partial<AppState> = {}
  private entities = new Map<string, SceneEntity>()
  private trails = new Map<string, number[][]>()
  private trailTimer = 0
  private attentionKey = ''
  private disposed = false

  constructor(container: HTMLElement) {
    const s = store.get()
    this.basemap = s.basemap
    this.map = new MlMap({
      container, style: styleFor(s.basemap), center: [s.camera.lng, s.camera.lat], zoom: s.camera.zoom, pitch: s.camera.pitch, bearing: s.camera.bearing,
      minZoom: 2.2, maxZoom: 19, attributionControl: { compact: true, customAttribution: ATTRIBUTION[s.basemap] }, maxPitch: 75, cancelPendingTileRequestsWhileZooming: false,
    })
    this.map.setMissingStyleImageResolver(id => this.ensureImage(id))
    Object.assign(window as unknown as Record<string, unknown>, { __map: this.map, __scene: this, __store: store }) // handles for browser verification scripts
    this.map.on('style.load', () => { this.styleReady = true; this.ensureLayers(); this.applyAll(); store.set({ basemapStatus: this.basemap === 'offline' ? 'offline' : 'online' }) })
    this.map.on('error', e => {
      const msg = String((e as unknown as { error?: Error }).error?.message ?? '')
      // Only a failure to fetch the style itself falls back to offline geography; a worker or tile error must not.
      if (this.basemap !== 'offline' && !this.styleReady && !/worker/i.test(msg) && /style|Failed to fetch|NetworkError|load/i.test(msg)) {
        actions.setBasemap('offline')
      }
    })
    this.map.on('moveend', () => {
      const c = this.map.getCenter()
      store.set({ camera: { zoom: this.map.getZoom(), pitch: this.map.getPitch(), bearing: this.map.getBearing(), lng: c.lng, lat: c.lat } })
      void this.refreshAttention()
    })
    this.map.on('click', e => this.onClick(e))
    this.map.on('mousemove', e => this.onHover(e))
    this.map.on('dragstart', () => { if (store.get().follow) store.set({ follow: false }) })
    this.map.addControl(new NavigationControl({ visualizePitch: true, showCompass: true }), 'bottom-right')
    this.map.addControl(new ScaleControl({ maxWidth: 120, unit: 'metric' }), 'bottom-left')
    this.unsubscribe = store.subscribe(() => this.onStore())
    this.raf = requestAnimationFrame(t => this.frame(t))
  }

  dispose() {
    this.disposed = true
    cancelAnimationFrame(this.raf)
    window.clearInterval(this.trailTimer)
    this.unsubscribe()
    this.map.remove()
  }

  // ---- images ---------------------------------------------------------------------------------
  private ensureImage(id: string) {
    if (this.map.hasImage(id)) return
    const add = (img: ImageData) => this.map.addImage(id, img, { pixelRatio: 2 })
    if (id.startsWith('ent:')) { const spec = parseIconId(id); if (spec) add(drawIcon(spec)); return }
    if (id.startsWith('lbl:')) { add(drawLabel(id.slice(4))); return }
    if (id.startsWith('lblu:')) { add(drawLabel(id.slice(5), { color: palette.unknown })); return }
    if (id.startsWith('count:')) { add(drawCount(Number(id.slice(6)))); return }
    if (id.startsWith('inc:')) { add(drawIncident(id.slice(4) as 'info')); return }
  }

  // ---- sources and layers -----------------------------------------------------------------------
  private ensureLayers() {
    const m = this.map
    const geo = (id: string, extra: Record<string, unknown> = {}) => { if (!m.getSource(id)) m.addSource(id, { type: 'geojson', data: empty(), ...extra }) }
    if (!m.getSource('counties-src')) m.addSource('counties-src', { type: 'geojson', data: '/data/sweden_counties.geojson' })
    geo('attention-points'); geo('areas'); geo('attention'); geo('prediction-rings'); geo('predictions', { lineMetrics: true }); geo('plans'); geo('trails', { lineMetrics: true })
    geo('interventions'); geo('incidents'); geo('weather')
    geo('units', {
      cluster: true, clusterMaxZoom: 8, clusterRadius: 46, promoteId: 'id',
      clusterProperties: {
        air: ['+', ['case', ['==', ['get', 'domain'], 'air'], 1, 0]], land: ['+', ['case', ['==', ['get', 'domain'], 'land'], 1, 0]],
        sea: ['+', ['case', ['==', ['get', 'domain'], 'sea'], 1, 0]], sites: ['+', ['case', ['get', 'isSite'], 1, 0]], worst: ['max', ['get', 'sevRank']],
      },
    })
    const add = (layer: LayerSpecification, before?: string) => { if (!m.getLayer(layer.id)) m.addLayer(layer, before && m.getLayer(before) ? before : undefined) }

    add({ id: 'counties-line', type: 'line', source: 'counties-src', paint: { 'line-color': 'rgba(170,195,215,0.55)', 'line-width': 1 }, layout: { visibility: 'none' } })
    add({ id: 'areas-fill', type: 'fill', source: 'areas', paint: { 'fill-color': ['match', ['get', 'status'], 'uncovered', 'rgba(229,72,77,0.16)', 'degraded', 'rgba(224,164,59,0.14)', 'covered', 'rgba(91,141,239,0.07)', 'rgba(160,180,200,0.05)'] } })
    add({ id: 'areas-line', type: 'line', source: 'areas', paint: { 'line-color': ['match', ['get', 'status'], 'uncovered', palette.critical, 'degraded', palette.warning, 'covered', 'rgba(140,170,215,0.9)', 'rgba(160,180,200,0.6)'], 'line-width': ['match', ['get', 'kind'], 'coverage_model', 1, 1.6], 'line-dasharray': ['match', ['get', 'kind'], 'restricted_zone', ['literal', [2, 2]], 'coverage_model', ['literal', [1, 3]], ['literal', [1, 0]]] } })
    add({ id: 'attention-fill', type: 'fill', source: 'attention', paint: { 'fill-color': ['interpolate', ['linear'], ['get', 'norm'], 0, 'rgba(255,150,70,0.0)', 1, 'rgba(255,100,50,0.1)'], 'fill-antialias': false } })
    add({ id: 'attention-heat', type: 'heatmap', source: 'attention-points', paint: {
      'heatmap-weight': ['get', 'w'],
      'heatmap-radius': ['interpolate', ['linear'], ['zoom'], 2, ['get', 'r2'], 6, ['get', 'r6'], 10, ['get', 'r10'], 14, ['get', 'r14']],
      'heatmap-intensity': ['interpolate', ['linear'], ['zoom'], 2, 0.9, 10, 1.4],
      'heatmap-color': ['interpolate', ['linear'], ['heatmap-density'], 0, 'rgba(255,150,70,0)', 0.15, 'rgba(255,160,80,0.18)', 0.4, 'rgba(255,130,60,0.42)', 0.7, 'rgba(255,95,50,0.62)', 1, 'rgba(255,60,40,0.82)'],
      'heatmap-opacity': 0.85 } })
    add({ id: 'attention-3d', type: 'fill-extrusion', source: 'attention', layout: { visibility: 'none' }, paint: { 'fill-extrusion-color': ['interpolate', ['linear'], ['get', 'norm'], 0, '#f7a86b', 0.5, '#ff7f4d', 1, '#ff4a35'], 'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.55, 'fill-extrusion-vertical-gradient': true } })
    add({ id: 'prediction-rings', type: 'fill', source: 'prediction-rings', paint: { 'fill-color': 'rgba(227,139,199,0.12)', 'fill-outline-color': 'rgba(227,139,199,0.45)' } })
    add({ id: 'predictions-line', type: 'line', source: 'predictions', paint: { 'line-color': palette.predicted, 'line-width': 2, 'line-dasharray': [3, 2.5], 'line-opacity': 0.9 } })
    add({ id: 'plans-line', type: 'line', source: 'plans', paint: { 'line-color': palette.planned, 'line-width': 1.4, 'line-dasharray': [0.6, 2.2], 'line-opacity': 0.8 }, layout: { 'line-cap': 'round' } })
    add({ id: 'trails-line', type: 'line', source: 'trails', paint: { 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.5, 12, 3], 'line-gradient': ['interpolate', ['linear'], ['line-progress'], 0, 'rgba(230,238,245,0)', 1, 'rgba(230,238,245,0.9)'] }, layout: { 'line-cap': 'round', 'line-join': 'round' } })
    add({ id: 'interventions-line', type: 'line', source: 'interventions', paint: { 'line-color': ['case', ['get', 'committed'], palette.accent, 'rgba(91,141,239,0.75)'], 'line-width': ['case', ['get', 'committed'], 2.6, 1.6], 'line-dasharray': ['case', ['get', 'committed'], ['literal', [1, 0]], ['literal', [2, 2]]] } })
    add({ id: 'incidents', type: 'symbol', source: 'incidents', layout: { 'icon-image': ['concat', 'inc:', ['get', 'severity']], 'icon-size': ['interpolate', ['linear'], ['zoom'], 4, 0.55, 10, 0.9], 'icon-allow-overlap': true, 'icon-ignore-placement': true, 'symbol-sort-key': ['get', 'rank'] } })
    add({ id: 'incident-radius', type: 'line', source: 'incidents', filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'line-color': ['match', ['get', 'severity'], 'critical', palette.critical, 'warning', palette.warning, palette.advisory], 'line-width': 1, 'line-dasharray': [2, 2], 'line-opacity': 0.7 } }, 'incidents')
    add({ id: 'weather-points', type: 'circle', source: 'weather', paint: { 'circle-radius': 5, 'circle-color': '#79c6ff', 'circle-stroke-color': '#0e1419', 'circle-stroke-width': 1.5 }, layout: { visibility: 'none' } })
    add({ id: 'weather-labels', type: 'symbol', source: 'weather', layout: { 'icon-image': ['get', 'labelIcon'], 'icon-anchor': 'bottom', 'icon-offset': [0, -8], 'icon-allow-overlap': false, visibility: 'none' } })
    add({ id: 'clusters', type: 'circle', source: 'units', filter: ['has', 'point_count'], paint: {
      'circle-radius': ['interpolate', ['linear'], ['get', 'point_count'], 2, 15, 10, 20, 40, 28],
      'circle-color': ['match', ['get', 'worst'], 3, 'rgba(229,72,77,0.82)', 2, 'rgba(227,139,199,0.82)', 1, 'rgba(224,164,59,0.84)', 'rgba(52,66,84,0.9)'],
      'circle-stroke-color': 'rgba(230,238,245,0.9)', 'circle-stroke-width': 1.5 } })
    add({ id: 'cluster-count', type: 'symbol', source: 'units', filter: ['has', 'point_count'], layout: { 'icon-image': ['concat', 'count:', ['get', 'point_count']], 'icon-allow-overlap': true, 'icon-ignore-placement': true } })
    add({ id: 'unit-halo', type: 'circle', source: 'units', filter: ['all', ['!', ['has', 'point_count']], ['any', ['get', 'selected'], ['get', 'hovered']]], paint: {
      'circle-radius': ['case', ['get', 'selected'], ['interpolate', ['linear'], ['zoom'], 5, 16, 12, 26], 14], 'circle-color': ['case', ['get', 'selected'], 'rgba(91,141,239,0.22)', 'rgba(230,238,245,0.12)'],
      'circle-stroke-color': ['case', ['get', 'selected'], palette.accent, 'rgba(230,238,245,0.6)'], 'circle-stroke-width': ['case', ['get', 'selected'], 2, 1],
      'circle-opacity': ['interpolate', ['linear'], ['zoom'], 8.2, 1, 8.4, ['case', ['get', 'isSite'], 1, 0]], 'circle-stroke-opacity': ['interpolate', ['linear'], ['zoom'], 8.2, 1, 8.4, ['case', ['get', 'isSite'], 1, 0]] } })
    if (!m.getLayer(this.sprites.id)) m.addLayer(this.sprites)
    if (!m.getLayer(this.models.id)) m.addLayer(this.models)
    add({ id: 'unit-icons', type: 'symbol', source: 'units', filter: ['!', ['has', 'point_count']], layout: {
      'icon-image': ['get', 'icon'], 'icon-rotate': ['get', 'heading'], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true, 'icon-ignore-placement': true,
      'icon-size': ['interpolate', ['linear'], ['zoom'], 4, 0.4, 8, 0.52, 12, 0.7, 16, 0.95], 'symbol-sort-key': ['-', 10, ['get', 'priority']] },
      paint: { 'icon-opacity': ['interpolate', ['linear'], ['zoom'], 8.2, ['case', ['get', 'stale'], 0.45, 1], 8.4, ['case', ['get', 'isSite'], 1, 0]] } })
    add({ id: 'labels-important', type: 'symbol', source: 'units', minzoom: 5.5, filter: ['all', ['!', ['has', 'point_count']], ['get', 'important']], layout: {
      'icon-image': ['get', 'labelIcon'], 'icon-anchor': 'top', 'icon-offset': [0, 20], 'icon-allow-overlap': false, 'icon-optional': true, 'symbol-sort-key': ['-', 10, ['get', 'priority']] } })
    add({ id: 'labels-all', type: 'symbol', source: 'units', minzoom: 8.5, filter: ['all', ['!', ['has', 'point_count']], ['!', ['get', 'important']]], layout: {
      'icon-image': ['get', 'labelIcon'], 'icon-anchor': 'top', 'icon-offset': [0, 20], 'icon-allow-overlap': false, 'icon-optional': true } })
    if (this.basemap === 'operational') {
      if (!m.getSource('ofm')) m.addSource('ofm', { type: 'vector', url: VECTOR_TILES_URL })
      add({ id: 'buildings-3d', type: 'fill-extrusion', source: 'ofm', 'source-layer': 'building', minzoom: 14, layout: { visibility: 'none' }, filter: ['!=', ['get', 'hide_3d'], true], paint: {
        'fill-extrusion-color': '#3a4653', 'fill-extrusion-height': ['coalesce', ['get', 'render_height'], 0], 'fill-extrusion-base': ['coalesce', ['get', 'render_min_height'], 0], 'fill-extrusion-opacity': 0.8 } }, 'areas-fill')
    }
    window.clearInterval(this.trailTimer)
    this.trailTimer = window.setInterval(() => void this.refreshTrails(), 20_000)
  }

  // ---- store reactions --------------------------------------------------------------------------
  private onStore() {
    if (this.disposed) return
    const s = store.get()
    const p = this.prev
    if (s.basemap !== this.basemap) { this.switchBasemap(s.basemap); return }
    if (!this.styleReady) return
    if (s.snapshot !== p.snapshot) { this.applySnapshot(s.snapshot); void this.refreshAttention(true); void this.refreshTrails() }
    if (s.attention !== p.attention) this.applyAttention(s.attention)
    if (s.views !== p.views || s.roleId !== p.roleId || s.modeId !== p.modeId || s.layerOverrides !== p.layerOverrides || s.threeD !== p.threeD) this.applyLayers(s)
    if (s.modeId !== p.modeId || s.roleId !== p.roleId) { const mode = currentMode(s); if (mode && p.modeId !== undefined) this.flyTo(mode.camera) }
    if (s.threeD !== p.threeD) this.apply3d(s)
    if (s.terrain !== p.terrain) this.applyTerrain(s)
    if (s.selected !== p.selected) { this.applySelection(s); void this.refreshTrails() }
    if (s.time !== p.time && s.time.mode === 'replay') this.renderStatic()
    this.prev = s
  }

  private applyAll() { const s = store.get(); this.prev = {}; this.onStore(); this.applyLayers(s); this.apply3d(s); this.applyTerrain(s); this.applySnapshot(s.snapshot); this.applyAttention(s.attention) }

  private switchBasemap(next: Basemap) {
    this.basemap = next
    this.styleReady = false
    store.set({ basemapStatus: 'loading' })
    this.map.setStyle(styleFor(next), { diff: false })
    const ctrl = (this.map as unknown as { _controls: { _updateAttributions?: () => void; options?: { customAttribution?: string } }[] })._controls?.find(c => c.options && 'customAttribution' in c.options)
    if (ctrl?.options) { ctrl.options.customAttribution = ATTRIBUTION[next]; ctrl._updateAttributions?.() }
  }

  private setVisible(layerId: string, on: boolean) { if (this.map.getLayer(layerId)) this.map.setLayoutProperty(layerId, 'visibility', on ? 'visible' : 'none') }

  private applyLayers(s: AppState) {
    const on = (id: string) => layerOn(s, id)
    const units = on('units_air') || on('units_land') || on('units_sea') || on('sites') || on('infrastructure') || on('unknown_tracks')
    for (const id of ['clusters', 'cluster-count', 'unit-halo', 'unit-icons']) this.setVisible(id, units)
    this.setVisible('labels-important', units && on('labels')); this.setVisible('labels-all', units && on('labels'))
    this.setVisible('areas-fill', on('areas')); this.setVisible('areas-line', on('areas'))
    this.setVisible('attention-fill', on('attention') && !s.threeD); this.setVisible('attention-heat', on('attention') && !s.threeD); this.setVisible('attention-3d', on('attention') && s.threeD)
    this.setVisible('prediction-rings', on('predictions')); this.setVisible('predictions-line', on('predictions'))
    this.setVisible('plans-line', on('plans')); this.setVisible('trails-line', on('trails'))
    this.setVisible('interventions-line', on('interventions')); this.setVisible('incidents', on('incidents')); this.setVisible('incident-radius', on('incidents'))
    this.setVisible('counties-line', on('counties')); this.setVisible('weather-points', on('weather')); this.setVisible('weather-labels', on('weather'))
    // Domain filters are applied to the unit features themselves (see buildUnitFeatures), so clusters count only visible domains.
    this.renderStatic()
  }

  private apply3d(s: AppState) {
    this.models.enabled = s.threeD
    this.setVisible('buildings-3d', s.threeD && this.basemap === 'operational')
    this.sprites.maxZoom = s.threeD ? MODEL_MIN_ZOOM : 99
    const pitch = this.map.getPitch()
    if (s.threeD && pitch < 30) this.map.easeTo({ pitch: 58, duration: s.reducedMotion ? 0 : 700 })
    if (!s.threeD && pitch > 0) this.map.easeTo({ pitch: 0, duration: s.reducedMotion ? 0 : 500 })
    this.map.triggerRepaint()
  }

  private applyTerrain(s: AppState) {
    if (s.terrain && this.basemap !== 'offline') {
      if (!this.map.getSource('dem')) this.map.addSource('dem', { type: 'raster-dem', url: TERRAIN_TILEJSON })
      this.map.setTerrain({ source: 'dem', exaggeration: 1.15 })
      if (!this.map.getLayer('hillshade')) this.map.addLayer({ id: 'hillshade', type: 'hillshade', source: 'dem', paint: { 'hillshade-exaggeration': 0.22, 'hillshade-shadow-color': '#0a1218', 'hillshade-highlight-color': '#cfdbe3' } }, 'areas-fill')
    } else {
      if (this.map.getTerrain()) this.map.setTerrain(null)
      if (this.map.getLayer('hillshade')) this.map.removeLayer('hillshade')
    }
  }

  private applySelection(s: AppState) {
    this.renderStatic()
    if (s.selected?.kind === 'entity') {
      const e = this.entities.get(s.selected.id)
      const pose = s.time.mode === 'live' ? this.buffer.poseAt(s.selected.id, this.buffer.renderTime()) : null
      const lng = pose?.lng ?? e?.position?.longitudeDeg, lat = pose?.lat ?? e?.position?.latitudeDeg
      if (lng !== undefined && lat !== undefined) this.map.flyTo({ center: [lng, lat], zoom: Math.max(this.map.getZoom(), 8.5), duration: s.reducedMotion ? 0 : 900, essential: true })
    } else if (s.selected?.kind === 'input') {
      const inp = s.snapshot?.inputs.find(i => i.id === s.selected!.id)
      if (inp?.position) this.map.flyTo({ center: [inp.position.longitudeDeg, inp.position.latitudeDeg], zoom: Math.max(this.map.getZoom(), 7.5), duration: s.reducedMotion ? 0 : 900 })
    } else if (s.selected?.kind === 'alert') {
      const a = s.snapshot?.alerts.find(a => a.id === s.selected!.id)
      if (a?.position) this.map.flyTo({ center: a.position as LngLatLike, zoom: Math.max(this.map.getZoom(), 6.5), duration: s.reducedMotion ? 0 : 900 })
    } else if (s.selected?.kind === 'area') {
      const area = s.snapshot?.areas.find(a => a.id === s.selected!.id)
      if (area) { const b = new LngLatBounds(); area.ring.forEach(p => b.extend(p as [number, number])); this.map.fitBounds(b, { padding: 120, duration: s.reducedMotion ? 0 : 900 }) }
    }
  }

  flyTo(cam: { lng: number; lat: number; zoom: number; pitch: number; bearing: number }) {
    const s = store.get()
    this.map.flyTo({ center: [cam.lng, cam.lat], zoom: cam.zoom, pitch: s.threeD ? Math.max(cam.pitch, 55) : cam.pitch, bearing: cam.bearing, duration: s.reducedMotion ? 0 : 1300, essential: true })
  }

  resetOverview() { const mode = currentMode(store.get()); if (mode) this.flyTo(mode.camera) }

  // ---- data application --------------------------------------------------------------------------
  private applySnapshot(snap: Snapshot | null) {
    this.entities.clear()
    if (!snap) return
    for (const e of snap.entities) this.entities.set(e.id, e)
    this.buffer.speed = snap.speed
    const src = (id: string) => this.map.getSource(id) as GeoJSONSource | undefined
    src('areas')?.setData({ type: 'FeatureCollection', features: snap.areas.map(a => ({ type: 'Feature', id: a.id, properties: { id: a.id, label: a.label, kind: a.kind, status: a.status }, geometry: { type: 'Polygon', coordinates: [a.ring] } })) })
    src('predictions')?.setData({ type: 'FeatureCollection', features: snap.predictions.map(p => ({ type: 'Feature', properties: { id: p.entityId }, geometry: { type: 'LineString', coordinates: p.points.map(q => [q[0], q[1]]) } })) })
    src('prediction-rings')?.setData({ type: 'FeatureCollection', features: snap.predictions.filter(p => p.uncertaintyRing).map(p => ({ type: 'Feature', properties: { id: p.entityId }, geometry: { type: 'Polygon', coordinates: [p.uncertaintyRing!] } })) })
    src('plans')?.setData({ type: 'FeatureCollection', features: snap.entities.filter(e => e.track && e.affiliation !== 'unknown').map(e => ({ type: 'Feature', properties: { id: e.id }, geometry: { type: 'LineString', coordinates: e.track!.waypoints.map(w => [w[0], w[1]]) } })) })
    const sevRank = { info: 0, advisory: 1, warning: 2, critical: 3 }
    const incidents: Feature[] = []
    for (const i of snap.inputs) {
      if (!i.position) continue
      incidents.push({ type: 'Feature', properties: { id: i.id, severity: i.severity, channel: i.channel, title: i.title, rank: 4 - sevRank[i.severity] }, geometry: { type: 'Point', coordinates: [i.position.longitudeDeg, i.position.latitudeDeg] } })
      if (i.radiusM && i.radiusM >= 2000) incidents.push({ type: 'Feature', properties: { id: i.id, severity: i.severity }, geometry: { type: 'Polygon', coordinates: [circle([i.position.longitudeDeg, i.position.latitudeDeg], i.radiusM)] } })
    }
    src('incidents')?.setData({ type: 'FeatureCollection', features: incidents })
    const lines: Feature[] = []
    for (const iv of snap.interventions) {
      const opt = iv.options.find(o => o.id === (iv.committedOptionId ?? iv.recommendedOptionId))
      const unit = opt?.assignedEntityIds[0] ? this.entities.get(opt.assignedEntityIds[0]) : null
      if (!iv.position || !unit?.position) continue
      lines.push({ type: 'Feature', properties: { id: iv.id, committed: !!iv.committedOptionId }, geometry: { type: 'LineString', coordinates: [[unit.position.longitudeDeg, unit.position.latitudeDeg], iv.position] } })
    }
    src('interventions')?.setData({ type: 'FeatureCollection', features: lines })
    this.renderStatic()
  }

  private applyAttention(att: AttentionResponse | null) {
    const src = this.map.getSource('attention') as GeoJSONSource | undefined
    const pts = this.map.getSource('attention-points') as GeoJSONSource | undefined
    if (!src || !pts) return
    if (!att || !att.cells.length) { src.setData(empty()); pts.setData(empty()); return }
    const maxW = Math.max(...att.contributions.map(c => c.weight), 0.01)
    const rpx = (radiusM: number, lat: number, z: number) => Math.min(420, Math.max(6, radiusM / ((156543.03392 * Math.cos((lat * Math.PI) / 180)) / 2 ** z)))
    pts.setData({ type: 'FeatureCollection', features: att.contributions.map(c => ({ type: 'Feature', properties: { w: c.weight / maxW, reason: c.reason, r2: rpx(c.radiusM, c.lat, 2), r6: rpx(c.radiusM, c.lat, 6), r10: rpx(c.radiusM, c.lat, 10), r14: rpx(c.radiusM, c.lat, 14) }, geometry: { type: 'Point', coordinates: [c.lng, c.lat] } })) })
    const max = att.maxScore || 1
    const scale = { national: 55_000, regional: 16_000, local: 3_500 }[att.resolution as 'national'] ?? 16_000
    src.setData({ type: 'FeatureCollection', features: att.cells.map(c => ({ type: 'Feature', properties: { key: c.key, score: c.score, norm: c.score / max, height: (c.score / max) * scale, reasons: c.reasons.join(' · ') }, geometry: { type: 'Polygon', coordinates: [c.ring] } })) })
  }

  async refreshAttention(force = false) {
    const s = store.get()
    if (!s.snapshot) return
    const res = attentionResolutionFor(this.map.getZoom())
    const key = `${res}:${s.snapshot.worldRevision}:${s.time.mode === 'replay' ? s.time.atS : 'live'}:${s.roleId}`
    if (!force && key === this.attentionKey) return
    this.attentionKey = key
    try {
      const att = await api.attention(s.time.mode === 'replay' ? s.time.atS : null, res, s.roleId)
      if (this.attentionKey === key) store.set({ attention: att, attentionResolution: res })
    } catch { /* keep the previous surface; the status strip reports stream state */ }
  }

  async refreshTrails() {
    const s = store.get()
    if (!layerOn(s, 'trails') || !s.snapshot) { this.trails.clear(); this.renderTrails(); return }
    const ids = new Set<string>()
    if (s.selected?.kind === 'entity' && MOBILE.has(this.entities.get(s.selected.id)?.kind ?? '')) ids.add(s.selected.id)
    for (const e of this.entities.values()) if (e.affiliation === 'unknown') ids.add(e.id)
    if (s.trailsForAll) for (const e of this.entities.values()) if (MOBILE.has(e.kind)) ids.add(e.id)
    const to = s.time.mode === 'replay' ? s.time.atS : s.snapshot.nowS
    const results = await Promise.allSettled([...ids].map(async id => [id, (await api.tracks(id, Math.max(0, to - 1200), to, 20)).samples] as const))
    this.trails.clear()
    for (const r of results) if (r.status === 'fulfilled') this.trails.set(r.value[0], r.value[1].map(sm => [sm[0]!, sm[1]!]))
    this.renderTrails()
  }

  private renderTrails() {
    const src = this.map.getSource('trails') as GeoJSONSource | undefined
    src?.setData({ type: 'FeatureCollection', features: [...this.trails.entries()].filter(([, pts]) => pts.length > 1).map(([id, pts]) => ({ type: 'Feature', properties: { id }, geometry: { type: 'LineString', coordinates: pts } })) })
  }

  // ---- per-frame rendering -------------------------------------------------------------------------
  private buildUnitFeatures(poseOf: (e: SceneEntity) => { lng: number; lat: number; heading: number; condition: Condition; stale: boolean; alt: number | null } | null): { fc: FC; instances: ModelInstance[]; sprites: SpriteInstance[] } {
    const s = store.get()
    const sel = s.selected?.kind === 'entity' ? s.selected.id : null
    const features: Feature[] = []
    const instances: ModelInstance[] = []
    const sprites: SpriteInstance[] = []
    const sizePx = SIZE * iconScale(this.map.getZoom())
    this.lastPoses.clear()
    const show = { air: layerOn(s, 'units_air'), land: layerOn(s, 'units_land'), sea: layerOn(s, 'units_sea'), site: layerOn(s, 'sites'), infra: layerOn(s, 'infrastructure'), unknown: layerOn(s, 'unknown_tracks') }
    for (const e of this.entities.values()) {
      if (!show[e.domain]) continue
      const pose = poseOf(e)
      if (!pose) continue
      const isSite = !MOBILE.has(e.kind)
      const modelKey = modelKeyFor(e.kind, e.modelKey)
      const condition = pose.condition
      const important = isSite || e.affiliation === 'unknown' || e.id === sel || condition !== 'normal'
      features.push({ type: 'Feature', id: e.id, properties: {
        id: e.id, icon: iconId({ modelKey, affiliation: e.affiliation, condition }), heading: isSite ? 0 : pose.heading, label: e.label,
        labelIcon: `${e.affiliation === 'unknown' ? 'lblu' : 'lbl'}:${e.label}`, condition, domain: e.domain, affiliation: e.affiliation, kind: e.kind,
        priority: e.visualPriority + (e.id === sel ? 5 : 0), sevRank: Math.max(SEV_RANK[condition], e.affiliation === 'unknown' ? 2 : 0), isSite, important,
        selected: e.id === sel, hovered: e.id === s.hovered, stale: pose.stale || e.stale },
        geometry: { type: 'Point', coordinates: [pose.lng, pose.lat] } })
      if (!isSite) {
        instances.push({ id: e.id, lng: pose.lng, lat: pose.lat, altM: pose.alt, headingDeg: pose.heading, modelKey, affiliation: e.affiliation, condition, selected: e.id === sel })
        sprites.push({ id: e.id, lng: pose.lng, lat: pose.lat, headingDeg: pose.heading, icon: iconId({ modelKey, affiliation: e.affiliation, condition }), opacity: pose.stale || e.stale ? 0.45 : 1, selected: e.id === sel, hovered: e.id === s.hovered, sizePx })
        this.lastPoses.set(e.id, { lng: pose.lng, lat: pose.lat })
      }
    }
    return { fc: { type: 'FeatureCollection', features }, instances, sprites }
  }

  /** Static render (replay, or before the first tick): positions from the snapshot itself. */
  private renderStatic() {
    if (!this.styleReady) return
    const s = store.get()
    if (s.time.mode === 'live' && this.buffer.lastTickWall) return // the frame loop owns live rendering
    const { fc, instances, sprites } = this.buildUnitFeatures(e => e.position ? { lng: e.position.longitudeDeg, lat: e.position.latitudeDeg, heading: e.kinematics?.headingDeg ?? 0, condition: e.condition, stale: e.stale, alt: e.position.altitudeM } : null)
    ;(this.map.getSource('units') as GeoJSONSource | undefined)?.setData(fc)
    this.models.instances = instances
    this.sprites.instances = sprites
    this.map.triggerRepaint()
  }

  private frame(now: number) {
    if (this.disposed) return
    this.raf = requestAnimationFrame(t => this.frame(t))
    const s = store.get()
    if (!this.styleReady || s.time.mode !== 'live' || !this.buffer.lastTickWall) return
    const t = this.buffer.renderTime()
    const { fc, instances, sprites } = this.buildUnitFeatures(e => {
      if (!MOBILE.has(e.kind)) return e.position ? { lng: e.position.longitudeDeg, lat: e.position.latitudeDeg, heading: 0, condition: e.condition, stale: false, alt: e.position.altitudeM } : null
      const p = this.buffer.poseAt(e.id, t)
      if (!p) return e.position ? { lng: e.position.longitudeDeg, lat: e.position.latitudeDeg, heading: e.kinematics?.headingDeg ?? 0, condition: e.condition, stale: true, alt: e.position.altitudeM } : null
      return { lng: p.lng, lat: p.lat, heading: p.heading, condition: p.condition === 'unknown' ? e.condition : p.condition, stale: p.stale, alt: p.alt }
    })
    // The symbol source re-tiles on every setData, so it is refreshed at 2 Hz (labels, clusters, picking fallback);
    // the sprite and model layers take the display-rate poses directly.
    if (now - this.lastSourceUpdate > 500) { this.lastSourceUpdate = now; (this.map.getSource('units') as GeoJSONSource | undefined)?.setData(fc) }
    this.models.instances = instances
    this.sprites.instances = sprites
    if (s.follow && s.selected?.kind === 'entity') {
      const p = this.buffer.poseAt(s.selected.id, t)
      if (p && !this.map.isMoving()) {
        // In 3D the camera orbits the unit at its reported altitude, so an aircraft stays centred instead of the ground below it.
        if (s.threeD && p.alt !== null && p.alt > 0) { this.map.setCenterClampedToGround(false); this.map.setCenterElevation(p.alt) }
        else if (!this.map.getCenterClampedToGround()) { this.map.setCenterClampedToGround(true) }
        this.map.jumpTo({ center: [p.lng, p.lat] })
      }
    } else if (!this.map.getCenterClampedToGround()) this.map.setCenterClampedToGround(true)
    if (this.map.getZoom() >= SPRITE_MIN_ZOOM) this.map.triggerRepaint()
  }

  /** Screen-space hit test against the live poses of moving units (exact, independent of tile state). */
  private hitTestUnit(x: number, y: number, radiusPx = 18): string | null {
    let best: string | null = null, bestD = radiusPx * radiusPx
    for (const [id, p] of this.lastPoses) {
      const pt = this.map.project([p.lng, p.lat])
      const d = (pt.x - x) ** 2 + (pt.y - y) ** 2
      if (d < bestD) { bestD = d; best = id }
    }
    return best
  }

  // ---- interaction ---------------------------------------------------------------------------------
  private pickable() { return ['unit-icons', 'unit-halo', 'clusters', 'incidents', 'attention-fill', 'attention-3d', 'areas-fill'].filter(id => this.map.getLayer(id)) }

  private onClick(e: MapMouseEvent, retry = true) {
    if (this.map.getZoom() >= SPRITE_MIN_ZOOM) {
      const hit = this.hitTestUnit(e.point.x, e.point.y)
      if (hit) { actions.select('entity', hit); return }
    }
    const feats = this.map.queryRenderedFeatures(e.point, { layers: this.pickable() })
    if (!feats.length) {
      // The symbol source may be mid-reload (it is refreshed at 2 Hz); one short retry before treating it as empty map.
      if (retry) { window.setTimeout(() => this.onClick(e, false), 160); return }
      actions.deselect(); return
    }
    const unit = feats.find(f => f.layer.id === 'unit-icons' || f.layer.id === 'unit-halo')
    if (unit) { actions.select('entity', String(unit.properties.id)); return }
    const cluster = feats.find(f => f.layer.id === 'clusters')
    if (cluster) {
      const src = this.map.getSource('units') as GeoJSONSource
      void src.getClusterExpansionZoom(cluster.properties.cluster_id as number).then(zoom => {
        const geom = cluster.geometry as Point
        this.map.easeTo({ center: geom.coordinates as [number, number], zoom: Math.min(zoom + 0.3, 14), duration: store.get().reducedMotion ? 0 : 700 })
      })
      return
    }
    const inc = feats.find(f => f.layer.id === 'incidents')
    if (inc) { actions.select('input', String(inc.properties.id)); return }
    const cell = feats.find(f => f.layer.id === 'attention-fill' || f.layer.id === 'attention-3d')
    if (cell) { actions.select('cell', String(cell.properties.key)); return }
    const area = feats.find(f => f.layer.id === 'areas-fill')
    if (area) { actions.select('area', String(area.properties.id)); return }
  }

  private onHover(e: MapMouseEvent) {
    const feats = this.map.queryRenderedFeatures(e.point, { layers: this.pickable() })
    const unit = feats.find(f => f.layer.id === 'unit-icons')
    const id = (this.map.getZoom() >= SPRITE_MIN_ZOOM ? this.hitTestUnit(e.point.x, e.point.y) : null) ?? (unit ? String(unit.properties.id) : null)
    this.map.getCanvas().style.cursor = feats.length || id ? 'pointer' : ''
    if (id !== store.get().hovered) store.set({ hovered: id })
  }
}

function circle(center: [number, number], radiusM: number, steps = 40): number[][] {
  const out: number[][] = []
  const dLat = radiusM / 111_320, dLng = radiusM / (111_320 * Math.cos((center[1] * Math.PI) / 180))
  for (let i = 0; i <= steps; i++) { const a = (i / steps) * Math.PI * 2; out.push([center[0] + dLng * Math.cos(a), center[1] + dLat * Math.sin(a)]) }
  return out
}
