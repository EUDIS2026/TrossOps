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
 *     layer reads (and the DEM itself) reach that invalidation, and rate-limits overlay updates (leader lines are
 *     rewritten ~8 times a second at national zoom). Style changes still invalidate everything.
 *  3. Matching draped source tiles to terrain tiles allocates for every pair (`fastTerrainCoords()`).
 * The two MapLibre internals touched (`_terrainDataCallback`, `_getTerrainCoordsForRegularTile`) are guarded and
 * fall back to stock behaviour if they are missing; maplibre-gl is pinned. */
import type { Map as MlMap, MapSourceDataEvent, MapStyleDataEvent } from 'maplibre-gl'

const DRAPED = new Set(['background', 'fill', 'line', 'raster', 'hillshade', 'color-relief'])
type DataEvent = MapStyleDataEvent | MapSourceDataEvent
const DRAPE_REFRESH_MS = 750
type Callback = ((e: DataEvent) => void) & { filtered?: true }
interface CanonicalLike { equals(o: CanonicalLike): boolean; isChildOf(o: CanonicalLike): boolean }
interface TileIDLike { canonical: CanonicalLike }
interface TerrainTileManagerLike { _renderableTilesKeys: string[]; _tiles: Record<string, { tileID: TileIDLike } | undefined> }
interface TerrainTileManagerProto {
  _getTerrainCoordsForRegularTile: ((this: TerrainTileManagerLike, tileID: TileIDLike) => unknown) & { prefiltered?: true }
}

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
    this.fastTerrainCoords()
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

  /** MapLibre maps every tile of every draped source onto the terrain tiles each frame, cloning the tile id (string
   * key included) and allocating a matrix for every pair before checking that the two overlap: ~1300 pairs per frame
   * over an airbase, ~4 ms. Pre-filter to the overlapping terrain tiles, then let the original do its exact work. */
  private fastTerrainCoords() {
    const tm = (this.map as unknown as { terrain?: { tileManager?: object } }).terrain?.tileManager
    const proto = tm && Object.getPrototypeOf(tm) as TerrainTileManagerProto
    if (!proto || typeof proto._getTerrainCoordsForRegularTile !== 'function' || proto._getTerrainCoordsForRegularTile.prefiltered) return
    const orig = proto._getTerrainCoordsForRegularTile
    const fast: TerrainTileManagerProto['_getTerrainCoordsForRegularTile'] = function (this: TerrainTileManagerLike, tileID: TileIDLike) {
      const all = this._renderableTilesKeys
      const c = tileID.canonical
      const hit: string[] = []
      for (const key of all) { const t = this._tiles[key]?.tileID.canonical; if (t && (t.equals(c) || t.isChildOf(c) || c.isChildOf(t))) hit.push(key) }
      this._renderableTilesKeys = hit
      try { return orig.call(this, tileID) } finally { this._renderableTilesKeys = all }
    }
    fast.prefiltered = true
    proto._getTerrainCoordsForRegularTile = fast
  }

  /** Wrap MapLibre's terrain data handler (internal, pinned 6.14): tile reloads of sources no visible draped layer
   * reads are dropped; reloads of draped overlay sources are coalesced so a source rewritten several times a second
   * (declutter leader lines) re-renders the drape at most every `DRAPE_REFRESH_MS`, an isolated update after ~50 ms.
   * Until then the drape keeps showing the previous version of that overlay. DEM and style events pass at once. */
  private filterTileEvents() {
    const m = this.map as MlMap & { _terrainDataCallback?: Callback }
    const orig = m._terrainDataCallback
    if (!orig || orig.filtered) return
    const dem = m.getTerrain()?.source
    const pending = new Map<string, DataEvent>()
    let timer = 0, lastFlush = 0
    const flush = () => {
      timer = 0; lastFlush = performance.now()
      if (m._terrainDataCallback !== cb) { pending.clear(); return } // terrain switched off or replaced meanwhile
      for (const e of pending.values()) orig(e)
      pending.clear()
      m.triggerRepaint()
    }
    const cb: Callback = e => {
      const se = e as MapSourceDataEvent
      if (e.dataType !== 'source' || !se.tile || se.sourceId === dem) { orig(e); return }
      if (!this.drapedSource(se.sourceId)) return
      pending.set(`${se.sourceId}/${se.tile.tileID.key}`, e)
      if (!timer) timer = window.setTimeout(flush, Math.max(50, lastFlush + DRAPE_REFRESH_MS - performance.now()))
    }
    cb.filtered = true
    m.style.off('data', orig)
    m.style.on('data', cb)
    m._terrainDataCallback = cb
  }
}
