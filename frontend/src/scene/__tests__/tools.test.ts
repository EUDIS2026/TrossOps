import { beforeEach, describe, expect, it } from 'vitest'
import { ApiError } from '../../core/api'
import { terrainNote, toolActions, toolCapturesMap, toolFeatures, tools } from '../tools'

const kinds = (fs: GeoJSON.Feature[]) => fs.map(f => f.geometry.type + (f.properties?.dashed ? ':dashed' : '') + (f.properties?.label ? `:${f.properties.label}` : ''))

describe('map tools state', () => {
  beforeEach(() => { toolActions.setTool(null); tools.set({ cursor: null }) })

  it('tools are mutually exclusive and only capture the map while active', () => {
    expect(toolCapturesMap()).toBe(false)
    toolActions.setTool('measure'); expect(tools.get().tool).toBe('measure'); expect(toolCapturesMap()).toBe(true)
    toolActions.setTool('los'); expect(tools.get().tool).toBe('los')
    toolActions.setTool('los'); expect(tools.get().tool).toBeNull()
    expect(toolCapturesMap()).toBe(false)
  })

  it('Escape drops work in progress first, then leaves the tool', () => {
    toolActions.setTool('measure')
    tools.set(s => ({ measure: { ...s.measure, points: [[15, 60], [15.1, 60]] } }))
    expect(toolActions.escape()).toBe(true); expect(tools.get().tool).toBe('measure'); expect(tools.get().measure.points).toEqual([])
    expect(toolActions.escape()).toBe(true); expect(tools.get().tool).toBeNull()
    expect(toolActions.escape()).toBe(false)
  })

  it('measure draws legs with distance and bearing, a rubber band to the cursor and a total', () => {
    toolActions.setTool('measure')
    tools.set(s => ({ cursor: [15.2, 60], measure: { ...s.measure, points: [[15, 60], [15, 60.1]] } }))
    const k = kinds(toolFeatures(tools.get()))
    expect(k).toContain('LineString')
    expect(k.some(x => x.startsWith('Point:11.1 km · 000°'))).toBe(true)
    expect(k.some(x => x.startsWith('LineString:dashed'))).toBe(true)
    expect(k.some(x => x.startsWith('Point:Total'))).toBe(true)
    toolActions.finishMeasure()
    expect(kinds(toolFeatures(tools.get())).some(x => x.includes('dashed'))).toBe(false)
  })

  it('range ring is solid once the radius is fixed', () => {
    toolActions.setTool('ring')
    tools.set(s => ({ ring: { ...s.ring, center: [15, 60] } }))
    toolActions.setRadius(10_000)
    const fs = toolFeatures(tools.get())
    expect(fs.some(f => f.geometry.type === 'Polygon')).toBe(true)
    expect(fs.some(f => f.properties?.label === 'r 10.0 km')).toBe(true)
    expect(fs.filter(f => f.geometry.type === 'LineString' && !f.properties?.dashed).length).toBe(1)
  })

  it('reports terrain failures honestly', () => {
    expect(terrainNote(new ApiError(503, 'terrain not configured: x'))).toMatchObject({ state: 'unavailable', note: expect.stringContaining('not configured') })
    expect(terrainNote(new ApiError(422, 'point outside Sweden'))).toMatchObject({ state: 'unavailable', note: expect.stringContaining('Sweden only') })
    expect(terrainNote(new ApiError(502, 'upstream'))).toMatchObject({ state: 'error' })
  })
})
