import { useSyncExternalStore } from 'react'
import type { AttentionResponse, EntityDetail, PlanResult, Snapshot, Views } from '../contracts/types'

export type SelectionKind = 'entity' | 'input' | 'alert' | 'intervention' | 'cell' | 'area'
export type Basemap = 'operational' | 'satellite' | 'offline'
export type Panel = 'layers' | 'inspector' | 'alerts' | 'decisions' | 'search' | 'inputs' | 'help'

export interface AppState {
  views: Views | null
  roleId: string
  modeId: string
  layerOverrides: Record<string, boolean>
  threeD: boolean
  weatherStatus: 'idle' | 'connected' | 'unavailable'
  terrain: boolean
  basemap: Basemap
  basemapStatus: 'loading' | 'online' | 'offline'
  snapshot: Snapshot | null
  attention: AttentionResponse | null
  attentionResolution: 'national' | 'regional' | 'local'
  selected: { kind: SelectionKind; id: string } | null
  hovered: string | null
  follow: boolean
  time: { mode: 'live' | 'replay'; atS: number }
  stream: 'connecting' | 'live' | 'offline'
  panels: Record<Panel, boolean>
  camera: { zoom: number; pitch: number; bearing: number; lng: number; lat: number }
  detail: EntityDetail | null
  plan: PlanResult | null
  error: string | null
  busy: boolean
  trailsForAll: boolean
  reducedMotion: boolean
}

const initial: AppState = {
  views: null, roleId: 'national_commander', modeId: 'readiness', layerOverrides: {}, threeD: false, terrain: false, basemap: 'operational', basemapStatus: 'loading', weatherStatus: 'idle',
  snapshot: null, attention: null, attentionResolution: 'national', selected: null, hovered: null, follow: false, time: { mode: 'live', atS: 0 }, stream: 'connecting',
  panels: { layers: true, inspector: false, alerts: false, decisions: false, search: false, inputs: false, help: false },
  camera: { zoom: 4.4, pitch: 0, bearing: 0, lng: 17, lat: 62.3 }, detail: null, plan: null, error: null, busy: false, trailsForAll: false,
  reducedMotion: typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches,
}

export const EMPTY: never[] = []
export const EMPTY_OBJ: Record<string, never> = {}

type Listener = () => void
let state: AppState = initial
const listeners = new Set<Listener>()

export const store = {
  get: () => state,
  set(patch: Partial<AppState> | ((s: AppState) => Partial<AppState>)) {
    const next = typeof patch === 'function' ? patch(state) : patch
    state = { ...state, ...next }
    listeners.forEach(l => l())
  },
  subscribe(l: Listener) { listeners.add(l); return () => { listeners.delete(l) } },
}

export function useApp<T>(selector: (s: AppState) => T): T {
  return useSyncExternalStore(store.subscribe, () => selector(state), () => selector(state))
}

export function currentRole(s: AppState) { return s.views?.roles.find(r => r.id === s.roleId) ?? null }
export function currentMode(s: AppState) { return currentRole(s)?.modes.find(m => m.id === s.modeId) ?? null }

/** Effective layer visibility: mode defaults overridden by the operator's own switches. */
export function layerOn(s: AppState, layerId: string): boolean {
  if (layerId in s.layerOverrides) return s.layerOverrides[layerId]
  return currentMode(s)?.layers.includes(layerId) ?? false
}

export const actions = {
  setRole(roleId: string) {
    const role = state.views?.roles.find(r => r.id === roleId)
    store.set({ roleId, modeId: role?.defaultModeId ?? state.modeId, layerOverrides: {}, selected: null, detail: null, follow: false })
  },
  setMode(modeId: string) { store.set({ modeId, layerOverrides: {} }) },
  toggleLayer(layerId: string) { store.set(s => ({ layerOverrides: { ...s.layerOverrides, [layerId]: !layerOn(s, layerId) } })) },
  setLayer(layerId: string, on: boolean) { store.set(s => ({ layerOverrides: { ...s.layerOverrides, [layerId]: on } })) },
  select(kind: SelectionKind, id: string) { store.set(s => ({ selected: { kind, id }, panels: { ...s.panels, inspector: true }, follow: kind === 'entity' ? s.follow : false })) },
  deselect() { store.set(s => ({ selected: null, detail: null, follow: false, panels: { ...s.panels, inspector: false } })) },
  togglePanel(panel: Panel) { store.set(s => ({ panels: { ...s.panels, [panel]: !s.panels[panel] } })) },
  setPanel(panel: Panel, open: boolean) { store.set(s => ({ panels: { ...s.panels, [panel]: open } })) },
  toggle3d() { store.set(s => ({ threeD: !s.threeD })) },
  setBasemap(basemap: Basemap) { store.set({ basemap }) },
  toggleTerrain() { store.set(s => ({ terrain: !s.terrain })) },
  toggleFollow() { store.set(s => ({ follow: !s.follow })) },
  goLive() { store.set({ time: { mode: 'live', atS: state.snapshot?.nowS ?? 0 } }) },
  replayAt(atS: number) { store.set({ time: { mode: 'replay', atS }, follow: false }) },
  setError(error: string | null) { store.set({ error }) },
  setTrailsForAll(v: boolean) { store.set({ trailsForAll: v }) },
}
