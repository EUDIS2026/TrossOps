/** Terrain cost control (measured on an integrated GPU, Iris Xe via ANGLE/D3D11).
 *
 * With 3D terrain MapLibre drapes fill, line, raster and hillshade layers into per-tile textures (2048² each here)
 * and paints them onto the terrain mesh. Two things make that expensive in our style:
 *  1. Every run of draped layers interrupted by a symbol, circle, extrusion or custom layer becomes its own drape:
 *     its own texture per terrain tile and its own full terrain-mesh pass every frame. Basemap labels, site
 *     extrusions, gates, prediction labels and the sprite/model layers cut the style into seven drapes.
 *     `compact()` moves draped layers below the first non-draped one (keeping their relative order), so there is
 *     one drape: an airbase at pitch 60 goes from ~50 ms to ~17 ms per frame. Labels and symbols end up above all
 *     ground layers, which is how they read on terrain anyway. The original order is restored when terrain goes off.
 *  2. MapLibre throws away the drape of every terrain tile under any tile of any source that reloads — including
 *     sources that are never draped, such as the operational labels updated a few times per second. That re-renders
 *     every drape every frame (~300 ms frames). `filterTileEvents()` lets only events from sources a visible draped
 *     layer reads (and the DEM itself) reach that invalidation. Style changes still invalidate everything. */
import type { Map as MlMap, MapSourceDataEvent, MapStyleDataEvent } from 'maplibre-gl'

const DRAPED = new Set(['background', 'fill', 'line', 'raster', 'hillshade', 'color-relief'])
type DataEvent = MapStyleDataEvent | MapSourceDataEvent
type Callback = ((e: DataEvent) => void) & { filtered?: true }

export class TerrainDrape {
  private saved: string[] | null = null
  private busy = false
  private hooked = false

  constructor(private map: MlMap) {}

  /** Call right after `map.setTerrain(...)`. */
  enable() {
    this.saved = null
    this.compact()
    this.filterTileEvents()
    if (!this.hooked) { this.hooked = true; this.map.on('styledata', () => this.compact()) } // layers added later
  }

  /** Call after `map.setTerrain(null)`: put the layers back in the order the style had. */
  disable() {
    const saved = this.saved
    this.saved = null
    if (!saved) return
    const present = saved.filter(id => this.map.getLayer(id))
    this.busy = true
    try { for (let i = present.length - 2; i >= 0; i--) this.map.moveLayer(present[i], present[i + 1]) } finally { this.busy = false }
  }

  private isDraped(id: string) { const l = this.map.getLayer(id); return !!l && DRAPED.has(l.type) }

  /** One drape: every draped layer directly above the previous one, below the first non-draped layer. */
  compact() {
    const m = this.map
    if (this.busy || !m.getTerrain() || !m.style) return
    const order = m.getLayersOrder()
    const first = order.findIndex(id => !this.isDraped(id))
    if (first < 0) return
    const late = order.slice(first + 1).filter(id => this.isDraped(id))
    if (!late.length) return
    if (!this.saved) this.saved = order
    this.busy = true
    try { for (const id of late) m.moveLayer(id, order[first]) } finally { this.busy = false }
  }

  private drapedSource(sourceId: string) {
    const m = this.map
    const z = m.getZoom()
    for (const id of m.getLayersOrder()) {
      const l = m.getLayer(id)
      if (l && l.source === sourceId && DRAPED.has(l.type) && !l.isHidden(z)) return true
    }
    return false
  }

  /** Wrap MapLibre's terrain data handler (internal, pinned 6.14) so tile reloads of non-draped sources are ignored. */
  private filterTileEvents() {
    const m = this.map as MlMap & { _terrainDataCallback?: Callback }
    const orig = m._terrainDataCallback
    if (!orig || orig.filtered) return
    const dem = m.getTerrain()?.source
    const cb: Callback = e => {
      if (e.dataType === 'source' && (e as MapSourceDataEvent).tile && e.sourceId !== dem && !this.drapedSource((e as MapSourceDataEvent).sourceId)) return
      orig(e)
    }
    cb.filtered = true
    m.style.off('data', orig)
    m.style.on('data', cb)
    m._terrainDataCallback = cb
  }
}
