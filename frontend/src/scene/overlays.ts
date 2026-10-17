/** Native MapLibre overlays: everything that is static or slow-changing geometry. Moving platforms are drawn by the
 * sprite and model layers; these sit underneath them. `OVERLAY_LAYERS` maps an operator layer id to map layer ids. */
import type { GeoJSONSource, LayerSpecification, Map as MlMap } from 'maplibre-gl'
import { FONT, FONT_BOLD } from './basemap'
import { eventMarker, palette } from './symbols'

export const empty = (): GeoJSON.FeatureCollection => ({ type: 'FeatureCollection', features: [] })

const SOURCES = ['areas', 'cables', 'predictions', 'prediction-rings', 'plans', 'route-preview', 'trails', 'interventions', 'reports', 'police', 'warnings',
  'stations', 'wind', 'analysis', 'site-detail', 'site-points', 'labels', 'night', 'ranges', 'leaders', 'crisis', 'fires', 'traffic']

export const OVERLAY_LAYERS: Record<string, string[]> = {
  'picture.areas': ['areas-fill', 'areas-line'],
  'infra.cables': ['cables-glow', 'cables-line', 'cables-label'],
  'picture.predictions': ['prediction-rings', 'predictions-line', 'predictions-label'],
  'picture.plans': ['plans-line'],
  'picture.trails': ['trails-line'],
  'picture.interventions': ['interventions-line'],
  'picture.reports': ['reports'],
  'civil.police_events': ['police'],
  'env.warnings': ['warnings-fill', 'warnings-line'],
  'civil.crisis': ['crisis-fill', 'crisis-line'],
  'env.fires': ['fires-glow', 'fires'],
  'civil.traffic': ['traffic'],
  'env.obs': ['stations-dot', 'stations-label'],
  'env.wind': ['wind'],
  'env.radar': ['radar'],
  'env.daylight': ['night'],
  'picture.labels': ['labels'],
}
export const DETAIL_LAYERS: Record<string, string[]> = {
  'detail.infra': ['site-footprint', 'site-surface', 'site-markings', 'site-centerline', 'site-buildings', 'site-buildings-flat', 'site-runway-label', 'site-taxi-lines'],
  'detail.logistics': ['site-logistics', 'site-logistics-flat', 'site-roads', 'site-fill-label'],
  'detail.defence': ['site-fence', 'site-gates'],
  'detail.personnel': ['site-personnel', 'site-personnel-flat'],
}

export function addOverlays(m: MlMap) {
  for (const id of SOURCES) if (!m.getSource(id)) m.addSource(id, { type: 'geojson', data: empty(), ...(id === 'predictions' || id === 'trails' || id === 'route-preview' ? { lineMetrics: true } : {}) })
  for (const [key, color, glyph] of [['rep:info', '#8d99a6', 'i'], ['rep:advisory', '#7aa6d8', '!'], ['rep:warning', '#f2b43a', '!'], ['rep:critical', '#f0545a', '!'], ['pol', '#5fa8ff', 'P'], ['pol:alert', '#ff9a3d', 'P']] as const) {
    if (!m.hasImage(key)) { const c = eventMarker(color, glyph); m.addImage(key, c.getContext('2d')!.getImageData(0, 0, c.width, c.height), { pixelRatio: 4 }) }
  }
  if (!m.hasImage('wind-arrow')) {
    const c = document.createElement('canvas'); c.width = 64; c.height = 64; const x = c.getContext('2d')!
    x.strokeStyle = '#bfe3ff'; x.fillStyle = '#bfe3ff'; x.lineWidth = 4; x.lineCap = 'round'
    x.beginPath(); x.moveTo(32, 56); x.lineTo(32, 14); x.stroke(); x.beginPath(); x.moveTo(32, 6); x.lineTo(22, 22); x.lineTo(42, 22); x.closePath(); x.fill()
    m.addImage('wind-arrow', x.getImageData(0, 0, 64, 64), { pixelRatio: 2, sdf: false })
  }
  const add = (layer: LayerSpecification, before?: string) => { if (!m.getLayer(layer.id)) m.addLayer(layer, before && m.getLayer(before) ? before : undefined) }
  const firstLabel = m.getLayer('water-label') ? 'water-label' : undefined
  // environment under everything operational
  add({ id: 'night', type: 'fill', source: 'night', paint: { 'fill-color': '#000814', 'fill-opacity': 0.32 } }, firstLabel)
  add({ id: 'warnings-fill', type: 'fill', source: 'warnings', paint: { 'fill-color': ['match', ['get', 'level'], 'red', 'rgba(240,70,80,0.18)', 'orange', 'rgba(250,150,50,0.16)', 'yellow', 'rgba(250,215,70,0.12)', 'rgba(150,170,190,0.06)'] } }, firstLabel)
  add({ id: 'crisis-fill', type: 'fill', source: 'crisis', paint: { 'fill-color': 'rgba(240,70,90,0.16)' } }, firstLabel)
  add({ id: 'crisis-line', type: 'line', source: 'crisis', paint: { 'line-color': '#f0465a', 'line-width': 2 } })
  add({ id: 'warnings-line', type: 'line', source: 'warnings', paint: { 'line-color': ['match', ['get', 'level'], 'red', '#f04650', 'orange', '#fa9632', 'yellow', '#fad746', '#8a9aa8'], 'line-width': 1.2, 'line-dasharray': [3, 2] } })
  // Analysis surfaces are a national/regional tool: they fade out before street zoom so they never cover a site.
  add({ id: 'analysis-fill', type: 'fill', source: 'analysis', maxzoom: 11.5, paint: { 'fill-color': ['get', 'color'], 'fill-outline-color': 'rgba(255,255,255,0.10)', 'fill-antialias': true,
    'fill-opacity': ['interpolate', ['linear'], ['zoom'], 9, 1, 11.3, 0] } })
  add({ id: 'analysis-3d', type: 'fill-extrusion', source: 'analysis', maxzoom: 11.5, layout: { visibility: 'none' }, paint: { 'fill-extrusion-color': ['get', 'color'], 'fill-extrusion-opacity': 0.72,
    'fill-extrusion-height': ['interpolate', ['exponential', 2], ['zoom'], 4, ['get', 'height'], 8, ['*', ['get', 'height'], 0.25], 11, ['*', ['get', 'height'], 0.02]] } })
  add({ id: 'areas-fill', type: 'fill', source: 'areas', paint: { 'fill-color': ['match', ['get', 'status'], 'uncovered', 'rgba(240,84,90,0.10)', 'degraded', 'rgba(242,180,58,0.08)', 'rgba(110,160,230,0.04)'] } })
  add({ id: 'areas-line', type: 'line', source: 'areas', paint: { 'line-color': ['match', ['get', 'status'], 'uncovered', palette.unavailable, 'degraded', palette.degraded, ['match', ['get', 'kind'], 'coverage_model', 'rgba(140,190,255,0.35)', 'rgba(140,190,255,0.75)']],
    'line-width': ['match', ['get', 'kind'], 'coverage_model', 1, 1.6], 'line-dasharray': ['match', ['get', 'kind'], 'restricted_zone', ['literal', [2, 2]], 'coverage_model', ['literal', [1, 3]], ['literal', [6, 2]]] } })
  add({ id: 'ranges', type: 'line', source: 'ranges', paint: { 'line-color': ['get', 'color'], 'line-width': 1.4, 'line-dasharray': [2, 2], 'line-opacity': 0.8 } })
  add({ id: 'cables-glow', type: 'line', source: 'cables', paint: { 'line-color': ['match', ['get', 'kind'], 'power', '#f7c948', 'gas', '#ff8f5a', '#5fd3ff'], 'line-width': 7, 'line-opacity': 0.12, 'line-blur': 4 } })
  add({ id: 'cables-line', type: 'line', source: 'cables', paint: { 'line-color': ['match', ['get', 'kind'], 'power', '#f7c948', 'gas', '#ff8f5a', '#5fd3ff'], 'line-width': 1.6, 'line-dasharray': [4, 2] } })
  add({ id: 'cables-label', type: 'symbol', source: 'cables', minzoom: 6, layout: { 'symbol-placement': 'line', 'text-field': ['get', 'label'], 'text-font': FONT, 'text-size': 10, 'text-offset': [0, -0.8] },
    paint: { 'text-color': '#8fcbe6', 'text-halo-color': '#071018', 'text-halo-width': 1.4 } })
  // site detail (synthetic layouts)
  const detailColor = ['match', ['get', 'cls'], 'runway', '#3b434c', 'taxiway', '#30373f', 'apron', '#323940', 'dispersal', '#262c32', 'quay', '#343b42', 'pier', '#3f474f', 'pontoon', '#3a4148',
    'motorpool', '#272d33', 'bund', '#2b2a25', 'footprint', 'rgba(60,70,80,0.18)', '#2c333a']
  add({ id: 'site-footprint', type: 'fill', source: 'site-detail', minzoom: 11, filter: ['==', ['get', 'cls'], 'footprint'], paint: { 'fill-color': 'rgba(70,82,95,0.16)', 'fill-outline-color': 'rgba(150,170,190,0.3)' } })
  add({ id: 'site-surface', type: 'fill', source: 'site-detail', minzoom: 11, filter: ['in', ['get', 'cls'], ['literal', ['runway', 'taxiway', 'apron', 'dispersal', 'quay', 'pier', 'pontoon']]], paint: { 'fill-color': detailColor as never, 'fill-opacity': 0.95 } })
  add({ id: 'site-markings', type: 'fill', source: 'site-detail', minzoom: 14, filter: ['==', ['get', 'cls'], 'runway_marking'], paint: { 'fill-color': '#d9dee3', 'fill-opacity': 0.85 } })
  add({ id: 'site-centerline', type: 'line', source: 'site-detail', minzoom: 13, filter: ['==', ['get', 'cls'], 'runway_centerline'], paint: { 'line-color': '#d9dee3', 'line-width': 1.2, 'line-dasharray': [6, 6], 'line-opacity': 0.8 } })
  add({ id: 'site-taxi-lines', type: 'line', source: 'site-detail', minzoom: 13, filter: ['==', ['get', 'cls'], 'taxiway_line'], paint: { 'line-color': '#c9b14a', 'line-width': 1, 'line-opacity': 0.7 } })
  add({ id: 'site-roads', type: 'line', source: 'site-detail', minzoom: 12, filter: ['==', ['get', 'cls'], 'base_road'], paint: { 'line-color': '#47505a', 'line-width': ['interpolate', ['linear'], ['zoom'], 12, 1, 16, 5] } })
  const extr = (id: string, filter: unknown, color: unknown) => {
    const props = ['all', filter, ['!', ['in', ['coalesce', ['get', 'model'], ''], ['literal', ['shelter', 'hangar', 'tower', 'radar_dome', 'radar_rotating', 'bunker', 'warehouse', 'barracks']]]]]
    add({ id, type: 'fill-extrusion', source: 'site-detail', minzoom: 12, filter: props as never, layout: { visibility: 'none' },
      paint: { 'fill-extrusion-color': color as never, 'fill-extrusion-height': ['get', 'height'], 'fill-extrusion-base': 0, 'fill-extrusion-opacity': 0.92, 'fill-extrusion-vertical-gradient': true } })
    add({ id: `${id}-flat`, type: 'fill', source: 'site-detail', minzoom: 12, filter: filter as never, paint: { 'fill-color': color as never, 'fill-outline-color': 'rgba(10,12,14,0.6)' } })
  }
  extr('site-buildings', ['all', ['==', ['get', 'layer'], 'infra'], ['in', ['get', 'cls'], ['literal', ['hangar', 'shelter', 'tower', 'building', 'warehouse', 'radar']]]],
    ['match', ['get', 'cls'], 'shelter', '#56606a', 'hangar', '#4b545d', 'tower', '#6a737c', 'radar', '#7c8791', '#454e57'])
  extr('site-logistics', ['all', ['==', ['get', 'layer'], 'logistics'], ['in', ['get', 'cls'], ['literal', ['fuel_tank', 'ammo_bunker', 'warehouse', 'fuel_point']]]],
    ['case', ['==', ['get', 'cls'], 'fuel_tank'], ['interpolate', ['linear'], ['coalesce', ['get', 'fill'], 50], 20, '#c0503d', 50, '#c9a24a', 80, '#62a87c'], ['==', ['get', 'cls'], 'ammo_bunker'], '#6b5d48', '#4f5a52'])
  extr('site-personnel', ['==', ['get', 'layer'], 'personnel'], '#3f4a63')
  add({ id: 'site-logistics-bund', type: 'line', source: 'site-detail', minzoom: 13, filter: ['in', ['get', 'cls'], ['literal', ['bund', 'motorpool']]], paint: { 'line-color': '#8a7a4a', 'line-width': 1, 'line-dasharray': [2, 2] } })
  add({ id: 'site-fence', type: 'line', source: 'site-detail', minzoom: 11, filter: ['==', ['get', 'cls'], 'fence'], paint: { 'line-color': '#9aa9b6', 'line-width': 1.2, 'line-dasharray': [1, 2], 'line-opacity': 0.8 } })
  add({ id: 'site-gates', type: 'circle', source: 'site-detail', minzoom: 13, filter: ['==', ['get', 'cls'], 'gate'], paint: { 'circle-radius': 4, 'circle-color': '#f2b43a', 'circle-stroke-color': '#0a0e12', 'circle-stroke-width': 1.5 } })
  add({ id: 'site-runway-label', type: 'symbol', source: 'site-detail', minzoom: 13.5, filter: ['==', ['get', 'cls'], 'runway_label'],
    layout: { 'text-field': ['get', 'name'], 'text-font': FONT_BOLD, 'text-size': 16, 'text-rotate': ['get', 'rotation'], 'text-rotation-alignment': 'map', 'text-pitch-alignment': 'map' }, paint: { 'text-color': '#e6ebef' } })
  add({ id: 'site-fill-label', type: 'symbol', source: 'site-detail', minzoom: 15, filter: ['==', ['get', 'cls'], 'fuel_tank'],
    layout: { 'text-field': ['concat', ['to-string', ['get', 'fill']], ' %'], 'text-font': FONT_BOLD, 'text-size': 10, 'text-allow-overlap': true }, paint: { 'text-color': '#f4e7c4', 'text-halo-color': '#0a0e12', 'text-halo-width': 1.4 } })
  // picture
  add({ id: 'trails-line', type: 'line', source: 'trails', paint: { 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.6, 12, 3], 'line-gradient': ['interpolate', ['linear'], ['line-progress'], 0, 'rgba(160,215,255,0)', 1, 'rgba(160,215,255,0.9)'] }, layout: { 'line-cap': 'round', 'line-join': 'round' } })
  add({ id: 'plans-line', type: 'line', source: 'plans', paint: { 'line-color': palette.planned, 'line-width': ['interpolate', ['linear'], ['zoom'], 5, 1.4, 12, 3], 'line-dasharray': [1, 1.6], 'line-opacity': 0.85 }, layout: { 'line-cap': 'round' } })
  add({ id: 'route-preview', type: 'line', source: 'route-preview', paint: { 'line-color': ['case', ['get', 'selected'], '#4ea1ff', 'rgba(160,190,220,0.55)'], 'line-width': ['case', ['get', 'selected'], 5, 2.5], 'line-opacity': 0.95 }, layout: { 'line-cap': 'round', 'line-join': 'round', 'line-sort-key': ['case', ['get', 'selected'], 1, 0] } })
  add({ id: 'prediction-rings', type: 'fill', source: 'prediction-rings', paint: { 'fill-color': 'rgba(255,217,90,0.08)', 'fill-outline-color': 'rgba(255,217,90,0.4)' } })
  add({ id: 'predictions-line', type: 'line', source: 'predictions', paint: { 'line-color': palette.predicted, 'line-width': ['interpolate', ['linear'], ['get', 'p'], 0, 1, 1, 3.2], 'line-dasharray': [2.5, 2], 'line-opacity': ['interpolate', ['linear'], ['get', 'p'], 0, 0.35, 1, 0.95] } })
  add({ id: 'predictions-label', type: 'symbol', source: 'predictions', minzoom: 5.5, layout: { 'symbol-placement': 'line-center', 'text-field': ['get', 'label'], 'text-font': FONT, 'text-size': 10.5, 'text-offset': [0, -0.8] },
    paint: { 'text-color': palette.predicted, 'text-halo-color': '#0a0e12', 'text-halo-width': 1.5 } })
  add({ id: 'interventions-line', type: 'line', source: 'interventions', paint: { 'line-color': ['case', ['get', 'committed'], '#4ea1ff', 'rgba(78,161,255,0.6)'], 'line-width': ['case', ['get', 'committed'], 2.6, 1.4], 'line-dasharray': ['case', ['get', 'committed'], ['literal', [1, 0]], ['literal', [2, 2]]] } })
  add({ id: 'stations-dot', type: 'circle', source: 'stations', minzoom: 5, paint: { 'circle-radius': 3, 'circle-color': '#9fd3ff', 'circle-stroke-color': '#0a0e12', 'circle-stroke-width': 1 } })
  add({ id: 'stations-label', type: 'symbol', source: 'stations', minzoom: 6.5, layout: { 'text-field': ['get', 'text'], 'text-font': FONT, 'text-size': 10, 'text-offset': [0, 1.1], 'text-anchor': 'top' },
    paint: { 'text-color': '#9fd3ff', 'text-halo-color': '#0a0e12', 'text-halo-width': 1.4 } })
  add({ id: 'wind', type: 'symbol', source: 'wind', layout: { 'icon-image': 'wind-arrow', 'icon-rotate': ['+', ['get', 'dir'], 180], 'icon-rotation-alignment': 'map', 'icon-allow-overlap': true,
    'icon-size': ['interpolate', ['linear'], ['get', 'speed'], 0, 0.35, 10, 0.6, 25, 1.0] }, paint: { 'icon-opacity': ['interpolate', ['linear'], ['get', 'speed'], 0, 0.35, 15, 0.9] } })
  add({ id: 'fires-glow', type: 'circle', source: 'fires', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 4, 6, 10, 18], 'circle-color': '#ff5a1f', 'circle-opacity': 0.18, 'circle-blur': 0.8 } })
  add({ id: 'fires', type: 'circle', source: 'fires', paint: { 'circle-radius': ['interpolate', ['linear'], ['coalesce', ['get', 'frp'], 1], 0, 2.5, 50, 6], 'circle-color': ['case', ['==', ['get', 'daynight'], 'D'], '#ffb020', '#ff5a1f'], 'circle-stroke-color': '#2a0a00', 'circle-stroke-width': 1 } })
  add({ id: 'traffic', type: 'circle', source: 'traffic', paint: { 'circle-radius': ['interpolate', ['linear'], ['zoom'], 5, 3.5, 12, 7], 'circle-color': ['match', ['get', 'type'], 'Olycka', '#f0545a', 'Hinder', '#f2b43a', 'Restriktion', '#c58bff', '#7aa6d8'], 'circle-stroke-color': '#0a0e12', 'circle-stroke-width': 1.5 } })
  add({ id: 'reports', type: 'symbol', source: 'reports', layout: { 'icon-image': ['concat', 'rep:', ['get', 'severity']], 'icon-size': ['interpolate', ['linear'], ['zoom'], 4, 0.55, 10, 0.85], 'icon-allow-overlap': true, 'symbol-sort-key': ['get', 'rank'] } })
  add({ id: 'police', type: 'symbol', source: 'police', layout: { 'icon-image': ['case', ['get', 'alert'], 'pol:alert', 'pol'], 'icon-size': ['interpolate', ['linear'], ['zoom'], 4, 0.45, 10, 0.8], 'icon-allow-overlap': true } })
  add({ id: 'leaders', type: 'line', source: 'leaders', paint: { 'line-color': 'rgba(200,225,240,0.45)', 'line-width': 1 } })
  add({ id: 'labels', type: 'symbol', source: 'labels', layout: {
    'text-field': ['get', 'text'], 'text-font': FONT, 'text-size': ['case', ['get', 'agg'], 11, 10], 'text-offset': [0, 1.9], 'text-anchor': 'top', 'text-optional': true, 'symbol-sort-key': ['get', 'rank'],
    'text-max-width': 14 }, paint: { 'text-color': ['get', 'color'], 'text-halo-color': 'rgba(8,11,14,0.95)', 'text-halo-width': 1.6 } })
}

export function setData(m: MlMap, id: string, fc: GeoJSON.FeatureCollection) { (m.getSource(id) as GeoJSONSource | undefined)?.setData(fc) }

export function circleRing(lng: number, lat: number, radiusM: number, steps = 64): number[][] {
  const out: number[][] = []
  const dLat = radiusM / 111_320, dLng = radiusM / (111_320 * Math.cos((lat * Math.PI) / 180))
  for (let i = 0; i <= steps; i++) { const a = (i / steps) * Math.PI * 2; out.push([lng + dLng * Math.sin(a), lat + dLat * Math.cos(a)]) }
  return out
}

/** Solar terminator: the night side as a polygon (simple solar position model, ±0.5°). */
export function nightPolygon(date: Date): GeoJSON.FeatureCollection {
  const d = date.getTime() / 86_400_000 + 2440587.5 - 2451545.0
  const L = (280.46 + 0.9856474 * d) % 360, g = ((357.528 + 0.9856003 * d) % 360) * Math.PI / 180
  const lambda = (L + 1.915 * Math.sin(g) + 0.02 * Math.sin(2 * g)) * Math.PI / 180
  const eps = (23.439 - 0.0000004 * d) * Math.PI / 180
  const dec = Math.asin(Math.sin(eps) * Math.sin(lambda))
  const ra = Math.atan2(Math.cos(eps) * Math.sin(lambda), Math.cos(lambda))
  const gmst = (18.697374558 + 24.06570982441908 * d) % 24
  const subLng = ((ra * 180 / Math.PI - gmst * 15) % 360 + 540) % 360 - 180
  const pts: number[][] = []
  for (let lng = -180; lng <= 180; lng += 2) {
    const ha = (lng - subLng) * Math.PI / 180
    const lat = Math.atan(-Math.cos(ha) / Math.tan(dec)) * 180 / Math.PI
    pts.push([lng, lat])
  }
  const pole = dec > 0 ? -90 : 90
  const ring = [...pts, [180, pole], [-180, pole], pts[0]]
  return { type: 'FeatureCollection', features: [{ type: 'Feature', properties: {}, geometry: { type: 'Polygon', coordinates: [ring] } }] }
}
