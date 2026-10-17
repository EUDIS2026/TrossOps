import type { LayerSpecification, StyleSpecification } from 'maplibre-gl'
import type { Basemap } from '../core/store'

/** Basemaps. All online sources are free, attributed, key-less public services with no SLA. The operational style
 * is our own (not a stock style) so the road hierarchy, water and labels sit underneath the operational picture
 * instead of competing with it. Offline is bundled geography only and renders with no network at all. */
export const VECTOR_TILES_URL = 'https://tiles.openfreemap.org/planet'
export const GLYPHS = 'https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf'
export const TERRAIN_TILEJSON = 'https://tiles.mapterhorn.com/tilejson.json'
export const IMAGERY_TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg'
export const FONT = ['Noto Sans Regular']
export const FONT_BOLD = ['Noto Sans Bold']

export const ATTRIBUTION: Record<Basemap, string> = {
  operational: '© OpenStreetMap contributors · OpenMapTiles · OpenFreeMap',
  satellite: 'Sentinel-2 cloudless by EOX IT Services GmbH (CC BY-NC-SA 4.0) · © OpenStreetMap contributors',
  offline: 'Offline geography: SCB county boundaries (CC0). No basemap tiles.',
}

const C = {
  bg: '#141a20', land: '#151b21', wood: '#141d19', grass: '#161e19', wet: '#131c1f', ice: '#1d252c', urban: '#1c2229', industrial: '#1e232a',
  water: '#0a1822', waterLine: '#16324a', river: '#10273a', border: '#71808e', admin: '#323c46',
  motorway: '#6d6553', trunk: '#5b5a52', primary: '#4a4f55', secondary: '#3a3f45', minor: '#2a3036', rail: '#2c3238',
  building: '#1c2229', label: '#c3ccd4', labelDim: '#8794a0', halo: '#0b0f13', aeroway: '#2a3037',
}

const roadWidth = (base: number): unknown => ['interpolate', ['exponential', 1.6], ['zoom'], 5, base * 0.3, 10, base * 1.1, 14, base * 3.4, 18, base * 14]

function vectorLayers(sat: boolean): LayerSpecification[] {
  const v = 'ofm'
  const roads: LayerSpecification[] = [
    { id: 'road-minor', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 11, filter: ['in', ['get', 'class'], ['literal', ['minor', 'service', 'tertiary']]],
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.18)' : C.minor, 'line-width': roadWidth(0.9) as never }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    { id: 'road-secondary', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 8, filter: ['==', ['get', 'class'], 'secondary'],
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.25)' : C.secondary, 'line-width': roadWidth(1.1) as never }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    { id: 'road-primary', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 6, filter: ['==', ['get', 'class'], 'primary'],
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.32)' : C.primary, 'line-width': roadWidth(1.3) as never }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    { id: 'road-trunk', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 5, filter: ['==', ['get', 'class'], 'trunk'],
      paint: { 'line-color': sat ? 'rgba(255,236,200,0.38)' : C.trunk, 'line-width': roadWidth(1.5) as never }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    { id: 'road-motorway', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 4, filter: ['==', ['get', 'class'], 'motorway'],
      paint: { 'line-color': sat ? 'rgba(255,220,160,0.45)' : C.motorway, 'line-width': roadWidth(1.8) as never }, layout: { 'line-cap': 'round', 'line-join': 'round' } },
    { id: 'rail', type: 'line', source: v, 'source-layer': 'transportation', minzoom: 9, filter: ['==', ['get', 'class'], 'rail'],
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.15)' : C.rail, 'line-width': 1, 'line-dasharray': [3, 3] } },
  ]
  const base: LayerSpecification[] = sat ? [] : [
    { id: 'landcover', type: 'fill', source: v, 'source-layer': 'landcover', paint: { 'fill-color': ['match', ['get', 'class'], 'wood', C.wood, 'grass', C.grass, 'wetland', C.wet, 'ice', C.ice, C.land], 'fill-opacity': 0.9 } },
    { id: 'landuse', type: 'fill', source: v, 'source-layer': 'landuse', minzoom: 8, filter: ['in', ['get', 'class'], ['literal', ['residential', 'suburb', 'neighbourhood', 'industrial', 'commercial', 'retail', 'military']]],
      paint: { 'fill-color': ['match', ['get', 'class'], 'industrial', C.industrial, 'military', '#1b1d22', C.urban], 'fill-opacity': ['interpolate', ['linear'], ['zoom'], 8, 0.4, 12, 0.9] } },
    { id: 'water', type: 'fill', source: v, 'source-layer': 'water', paint: { 'fill-color': C.water } },
    { id: 'water-edge', type: 'line', source: v, 'source-layer': 'water', minzoom: 6, paint: { 'line-color': C.waterLine, 'line-width': ['interpolate', ['linear'], ['zoom'], 6, 0.4, 12, 1.2] } },
    { id: 'waterway', type: 'line', source: v, 'source-layer': 'waterway', minzoom: 8, paint: { 'line-color': C.river, 'line-width': ['interpolate', ['linear'], ['zoom'], 8, 0.5, 14, 2] } },
    { id: 'aeroway-area', type: 'fill', source: v, 'source-layer': 'aeroway', minzoom: 10, filter: ['==', ['geometry-type'], 'Polygon'], paint: { 'fill-color': C.aeroway } },
    { id: 'aeroway-line', type: 'line', source: v, 'source-layer': 'aeroway', minzoom: 10, filter: ['==', ['geometry-type'], 'LineString'],
      paint: { 'line-color': C.aeroway, 'line-width': ['interpolate', ['exponential', 2], ['zoom'], 10, 1, 16, 30] } },
    { id: 'building', type: 'fill', source: v, 'source-layer': 'building', minzoom: 13, paint: { 'fill-color': C.building, 'fill-opacity': 0.9 } },
  ]
  const borders: LayerSpecification[] = [
    { id: 'admin', type: 'line', source: v, 'source-layer': 'boundary', filter: ['all', ['>=', ['get', 'admin_level'], 3], ['<=', ['get', 'admin_level'], 4], ['!=', ['get', 'maritime'], 1]], minzoom: 5,
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.25)' : C.admin, 'line-width': 0.8, 'line-dasharray': [3, 2] } },
    { id: 'border', type: 'line', source: v, 'source-layer': 'boundary', filter: ['all', ['==', ['get', 'admin_level'], 2], ['!=', ['get', 'maritime'], 1]],
      paint: { 'line-color': sat ? 'rgba(255,255,255,0.6)' : C.border, 'line-width': ['interpolate', ['linear'], ['zoom'], 3, 0.8, 10, 2] } },
  ]
  const labels: LayerSpecification[] = [
    { id: 'water-label', type: 'symbol', source: v, 'source-layer': 'water_name', minzoom: 4,
      layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 11, 'text-letter-spacing': 0.15, 'text-max-width': 8 },
      paint: { 'text-color': '#3f5e78', 'text-halo-color': C.halo, 'text-halo-width': 1 } },
    { id: 'road-label', type: 'symbol', source: v, 'source-layer': 'transportation_name', minzoom: 12,
      layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 10, 'symbol-placement': 'line' },
      paint: { 'text-color': C.labelDim, 'text-halo-color': C.halo, 'text-halo-width': 1.2 } },
    { id: 'road-shield', type: 'symbol', source: v, 'source-layer': 'transportation_name', minzoom: 7, filter: ['all', ['has', 'ref'], ['in', ['get', 'class'], ['literal', ['motorway', 'trunk', 'primary']]]],
      layout: { 'text-field': ['get', 'ref'], 'text-font': FONT_BOLD, 'text-size': 9.5, 'symbol-placement': 'line', 'symbol-spacing': 420, 'text-rotation-alignment': 'viewport' },
      paint: { 'text-color': '#c9b98a', 'text-halo-color': '#1b1a15', 'text-halo-width': 2.2 } },
    { id: 'place-minor', type: 'symbol', source: v, 'source-layer': 'place', minzoom: 9, filter: ['in', ['get', 'class'], ['literal', ['village', 'suburb', 'hamlet', 'neighbourhood']]],
      layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': 10.5 }, paint: { 'text-color': C.labelDim, 'text-halo-color': C.halo, 'text-halo-width': 1.2 } },
    { id: 'place-town', type: 'symbol', source: v, 'source-layer': 'place', minzoom: 6.5, filter: ['==', ['get', 'class'], 'town'],
      layout: { 'text-field': ['get', 'name'], 'text-font': FONT, 'text-size': ['interpolate', ['linear'], ['zoom'], 7, 10.5, 12, 13] },
      paint: { 'text-color': C.label, 'text-halo-color': C.halo, 'text-halo-width': 1.4 } },
    { id: 'place-city', type: 'symbol', source: v, 'source-layer': 'place', minzoom: 3.5, filter: ['==', ['get', 'class'], 'city'],
      layout: { 'text-field': ['get', 'name'], 'text-font': FONT_BOLD, 'text-size': ['interpolate', ['linear'], ['zoom'], 4, 10.5, 10, 15], 'text-letter-spacing': 0.03 },
      paint: { 'text-color': '#dfe6ec', 'text-halo-color': C.halo, 'text-halo-width': 1.6 } },
    { id: 'place-country', type: 'symbol', source: v, 'source-layer': 'place', maxzoom: 6, filter: ['==', ['get', 'class'], 'country'],
      layout: { 'text-field': ['upcase', ['get', 'name:en']], 'text-font': FONT_BOLD, 'text-size': 11, 'text-letter-spacing': 0.35 },
      paint: { 'text-color': '#5b6874', 'text-halo-color': C.halo, 'text-halo-width': 1 } },
  ]
  return [...base, ...roads, ...borders, ...labels]
}

export const operationalStyle: StyleSpecification = {
  version: 8, name: 'TrossOps operational', glyphs: GLYPHS,
  sources: { ofm: { type: 'vector', url: VECTOR_TILES_URL } },
  layers: [{ id: 'background', type: 'background', paint: { 'background-color': C.bg } }, ...vectorLayers(false)],
}

export const satelliteStyle: StyleSpecification = {
  version: 8, name: 'TrossOps imagery', glyphs: GLYPHS,
  sources: { imagery: { type: 'raster', tiles: [IMAGERY_TILES], tileSize: 256, maxzoom: 14, attribution: ATTRIBUTION.satellite }, ofm: { type: 'vector', url: VECTOR_TILES_URL } },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#0b1016' } },
    { id: 'imagery', type: 'raster', source: 'imagery', paint: { 'raster-saturation': -0.25, 'raster-brightness-max': 0.82, 'raster-contrast': 0.08 } },
    ...vectorLayers(true),
  ],
}

export const offlineStyle: StyleSpecification = {
  version: 8, name: 'TrossOps offline',
  sources: { counties: { type: 'geojson', data: '/data/sweden_counties.geojson' } },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#0b1218' } },
    { id: 'land', type: 'fill', source: 'counties', paint: { 'fill-color': '#151c23', 'fill-opacity': 1 } },
    { id: 'land-outline', type: 'line', source: 'counties', paint: { 'line-color': '#2e3a45', 'line-width': 0.8 } },
  ],
}

export function styleFor(basemap: Basemap): StyleSpecification {
  if (basemap === 'satellite') return satelliteStyle
  if (basemap === 'offline') return offlineStyle
  return operationalStyle
}
