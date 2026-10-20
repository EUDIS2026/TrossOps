import { describe, expect, it } from 'vitest'
import type { LayerSpecification } from 'maplibre-gl'
import { operationalStyle, satelliteStyle } from '../basemap'
import { terrainExaggeration } from '../terrain'

describe('basemap 3D buildings', () => {
  for (const [name, style] of [['operational', operationalStyle], ['satellite', satelliteStyle]] as const) {
    it(`${name}: extruded buildings and contact shadow sit below the first label, hidden until 3D, honouring hide_3d`, () => {
      const ids = style.layers.map(l => l.id)
      const firstSymbol = style.layers.findIndex(l => l.type === 'symbol')
      for (const id of ['building-3d', 'building-contact']) {
        const i = ids.indexOf(id)
        expect(i, id).toBeGreaterThan(-1)
        expect(i, id).toBeLessThan(firstSymbol)
        const l = style.layers[i] as LayerSpecification & { filter?: unknown; layout?: { visibility?: string } }
        expect(l.layout?.visibility).toBe('none')
        expect(JSON.stringify(l.filter)).toContain('hide_3d')
      }
      expect(style.layers[ids.indexOf('building-3d')].type).toBe('fill-extrusion')
      expect(style.light?.anchor).toBe('map')
    })
  }
})

describe('terrainExaggeration', () => {
  it('exaggerates relief at national scale and is true scale at city zoom', () => {
    expect(terrainExaggeration(6)).toBe(1.2)
    expect(terrainExaggeration(11)).toBe(1.2)
    expect(terrainExaggeration(12)).toBe(1.1)
    expect(terrainExaggeration(13)).toBe(1)
    expect(terrainExaggeration(17)).toBe(1)
  })
})
