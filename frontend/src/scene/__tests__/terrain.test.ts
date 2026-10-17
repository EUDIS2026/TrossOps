import { describe, expect, it } from 'vitest'
import type { Map as MlMap } from 'maplibre-gl'
import { TerrainDrape } from '../terrain'

/** Minimal stand-in for the parts of the MapLibre map TerrainDrape uses. */
function fakeMap(layers: [string, string][], terrain = true) {
  let order = layers.map(l => l[0])
  const types = new Map(layers)
  const handlers: (() => void)[] = []
  const map = {
    getTerrain: () => (terrain ? { source: 'dem' } : null),
    style: {},
    getLayersOrder: () => order.slice(),
    getLayer: (id: string) => (types.has(id) ? { id, type: types.get(id) } : undefined),
    moveLayer: (id: string, before?: string) => {
      order = order.filter(x => x !== id)
      if (before === undefined) order.push(id); else order.splice(order.indexOf(before), 0, id)
    },
    on: (_: string, f: () => void) => { handlers.push(f) },
  }
  return { map: map as unknown as MlMap, order: () => order, setTerrain: (on: boolean) => { terrain = on } }
}

const STYLE: [string, string][] = [
  ['background', 'background'], ['water', 'fill'], ['roads', 'line'], ['place-label', 'symbol'], ['ranges', 'line'],
  ['site-surface', 'fill'], ['site-buildings', 'fill-extrusion'], ['site-flat', 'fill'], ['gates', 'circle'], ['routes', 'line'],
  ['sprites', 'custom'], ['leaders', 'line'], ['labels', 'symbol'],
]

describe('TerrainDrape', () => {
  it('moves every draped layer below the first non-draped one, keeping relative order', () => {
    const f = fakeMap(STYLE)
    new TerrainDrape(f.map).enable()
    expect(f.order()).toEqual(['background', 'water', 'roads', 'ranges', 'site-surface', 'site-flat', 'routes', 'leaders',
      'place-label', 'site-buildings', 'gates', 'sprites', 'labels'])
  })

  it('restores the original order when terrain goes off', () => {
    const f = fakeMap(STYLE)
    const d = new TerrainDrape(f.map)
    d.enable()
    f.setTerrain(false)
    d.disable()
    expect(f.order()).toEqual(STYLE.map(l => l[0]))
  })

  it('leaves the order alone without terrain', () => {
    const f = fakeMap(STYLE, false)
    new TerrainDrape(f.map).compact()
    expect(f.order()).toEqual(STYLE.map(l => l[0]))
  })
})
