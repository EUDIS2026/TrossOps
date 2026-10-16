import type { StyleSpecification } from 'maplibre-gl'
import type { Basemap } from '../core/store'

/** Basemap sources. Online styles are free, attributed, key-less public services with no SLA; the offline style
 * is bundled geography only (SCB county polygons as land) and renders with no network at all. */
export const OPERATIONAL_STYLE_URL = 'https://tiles.openfreemap.org/styles/dark'
export const VECTOR_TILES_URL = 'https://tiles.openfreemap.org/planet'
export const TERRAIN_TILEJSON = 'https://tiles.mapterhorn.com/tilejson.json'
export const IMAGERY_TILES = 'https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless-2023_3857/default/g/{z}/{y}/{x}.jpg'

export const ATTRIBUTION: Record<Basemap, string> = {
  operational: 'MapLibre | OpenFreeMap © OpenMapTiles, data from OpenStreetMap contributors',
  satellite: 'Sentinel-2 cloudless by EOX IT Services GmbH (CC BY-NC-SA 4.0), contains modified Copernicus Sentinel data',
  offline: 'Offline geography: SCB county boundaries (CC0). No basemap tiles.',
}

export const offlineStyle: StyleSpecification = {
  version: 8,
  name: 'TrossOps offline',
  sources: {
    counties: { type: 'geojson', data: '/data/sweden_counties.geojson' },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#12181f' } },
    { id: 'land', type: 'fill', source: 'counties', paint: { 'fill-color': '#1d252d', 'fill-opacity': 1 } },
    { id: 'land-outline', type: 'line', source: 'counties', paint: { 'line-color': '#34404b', 'line-width': 0.8 } },
  ],
}

export const satelliteStyle: StyleSpecification = {
  version: 8,
  name: 'TrossOps imagery',
  sources: {
    imagery: { type: 'raster', tiles: [IMAGERY_TILES], tileSize: 256, maxzoom: 14, attribution: ATTRIBUTION.satellite },
    counties: { type: 'geojson', data: '/data/sweden_counties.geojson' },
  },
  layers: [
    { id: 'background', type: 'background', paint: { 'background-color': '#0b1016' } },
    { id: 'imagery', type: 'raster', source: 'imagery', paint: { 'raster-saturation': -0.35, 'raster-brightness-max': 0.85 } },
    { id: 'land-outline', type: 'line', source: 'counties', paint: { 'line-color': 'rgba(255,255,255,0.18)', 'line-width': 0.6 } },
  ],
}

export function styleFor(basemap: Basemap): string | StyleSpecification {
  if (basemap === 'operational') return OPERATIONAL_STYLE_URL
  if (basemap === 'satellite') return satelliteStyle
  return offlineStyle
}
