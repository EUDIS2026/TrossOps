import { useSyncExternalStore } from 'react'
import type { EntityDetail, FormationDetail, LiveAircraft, LiveVessel, PlanResult, RoutePlan, Snapshot, SourceStatus, Views } from '../contracts/types'

export type SelectionKind = 'entity' | 'formation' | 'site' | 'track' | 'aircraft' | 'vessel' | 'input' | 'alert' | 'intervention' | 'cell' | 'area' | 'police' | 'warning' | 'cable'
export type Basemap = 'operational' | 'satellite' | 'offline'
export type Panel = 'layers' | 'feed' | 'decisions' | 'scenario' | 'sources' | 'help' | 'search' | 'report'
export type InspectorTab = 'overview' | 'fusion' | 'prediction' | 'deception' | 'sources' | 'actions' | 'units' | 'inventory'

export interface Selection { kind: SelectionKind; id: string; data?: unknown }
export interface Hover { kind: SelectionKind; id: string; x: number; y: number; title: string; lines: string[] }

export interface AppState {
  views: Views | null
  worldReady: boolean
  catalogRevision: number
  roleId: string
  modeId: string
  layerOverrides: Record<string, boolean>
  threeD: boolean
  terrain: boolean
  basemap: Basemap
  basemapStatus: 'loading' | 'online' | 'offline'
  snapshot: Snapshot | null
  selected: Selection | null
  hovered: Hover | null
  follow: boolean
  tab: InspectorTab
  clock: { mode: 'live' | 'sim'; rate: number; paused: boolean; offsetS: number; t: number }
  stream: 'connecting' | 'live' | 'offline'
  panels: Record<Panel, boolean>
  camera: { zoom: number; pitch: number; bearing: number; lng: number; lat: number }
  detail: EntityDetail | FormationDetail | null
  plan: PlanResult | null
  route: { entityId: string; picking: boolean; result: RoutePlan | null; option: string | null; busy: boolean } | null
  live: { aircraft: LiveAircraft[]; vessels: LiveVessel[]; at: number }
  sources: SourceStatus[]
  error: string | null
  toast: string | null
  busy: boolean
  reducedMotion: boolean
  cinematic: boolean
  analysisInfo: { surface: string; unit: string; legend: { color: string; label: string }[]; note: string; cells: number } | null
}

/** The opening national view (the scene fits its zoom to the screen width while this object is untouched). */
export const INITIAL_CAMERA = { zoom: 4.7, pitch: 0, bearing: 0, lng: 17.2, lat: 61.2 }

const initial: AppState = {
  views: null, worldReady: false, catalogRevision: 0, roleId: 'national_commander', modeId: 'overview', layerOverrides: {}, threeD: false, terrain: false,
  basemap: 'operational', basemapStatus: 'loading', snapshot: null, selected: null, hovered: null, follow: false, tab: 'overview',
  clock: { mode: 'live', rate: 1, paused: false, offsetS: 0, t: 0 }, stream: 'connecting',
  panels: { layers: false, feed: false, decisions: false, scenario: false, sources: false, help: false, search: false, report: false },
  camera: INITIAL_CAMERA, detail: null, plan: null, route: null,
  live: { aircraft: [], vessels: [], at: 0 }, sources: [], error: null, toast: null, busy: false,
  reducedMotion: typeof window !== 'undefined' && window.matchMedia('(prefers-reduced-motion: reduce)').matches, cinematic: true, analysisInfo: null,
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
export function analysisLayer(s: AppState): string | null {
  return s.views?.layers.find(l => l.id.startsWith('analysis.') && layerOn(s, l.id))?.id ?? null
}

const PANELS_EXCLUSIVE: Panel[] = ['feed', 'decisions', 'scenario', 'sources', 'help', 'report']

export const actions = {
  setRole(roleId: string) {
    const role = state.views?.roles.find(r => r.id === roleId)
    store.set({ roleId, modeId: role?.defaultModeId ?? state.modeId, layerOverrides: {}, selected: null, detail: null, follow: false, route: null })
  },
  setMode(modeId: string) { store.set({ modeId, layerOverrides: {} }) },
  toggleLayer(layerId: string) {
    store.set(s => {
      const on = !layerOn(s, layerId)
      const o = { ...s.layerOverrides, [layerId]: on }
      if (on && layerId.startsWith('analysis.')) for (const l of s.views?.layers ?? []) if (l.id.startsWith('analysis.') && l.id !== layerId) o[l.id] = false
      return { layerOverrides: o }
    })
  },
  setLayers(ids: string[], on: boolean) {
    store.set(s => { const o = { ...s.layerOverrides }; for (const id of ids) o[id] = on; return { layerOverrides: o } })
  },
  setAnalysis(layerId: string | null) {
    store.set(s => { const o = { ...s.layerOverrides }; for (const l of s.views?.layers ?? []) if (l.id.startsWith('analysis.')) o[l.id] = l.id === layerId; return { layerOverrides: o } })
  },
  select(kind: SelectionKind, id: string, data?: unknown) {
    store.set(s => ({ selected: { kind, id, data }, tab: 'overview', follow: kind === 'entity' || kind === 'track' || kind === 'aircraft' ? s.follow : false, detail: s.selected?.id === id ? s.detail : null }))
  },
  deselect() { store.set({ selected: null, detail: null, follow: false }) },
  setTab(tab: InspectorTab) { store.set({ tab }) },
  hover(h: Hover | null) { store.set({ hovered: h }) },
  togglePanel(panel: Panel) {
    store.set(s => {
      const open = !s.panels[panel]
      const panels = { ...s.panels, [panel]: open }
      if (open && PANELS_EXCLUSIVE.includes(panel)) for (const p of PANELS_EXCLUSIVE) if (p !== panel) panels[p] = false
      return { panels }
    })
  },
  setPanel(panel: Panel, open: boolean) { store.set(s => ({ panels: { ...s.panels, [panel]: open } })) },
  toggle3d() { store.set(s => ({ threeD: !s.threeD, terrain: !s.threeD ? true : s.terrain })) },
  setBasemap(basemap: Basemap) { store.set({ basemap }) },
  toggleTerrain() { store.set(s => ({ terrain: !s.terrain })) },
  toggleFollow() { store.set(s => ({ follow: !s.follow })) },
  setError(error: string | null) { store.set({ error }) },
  toast(msg: string) { store.set({ toast: msg }); window.setTimeout(() => { if (store.get().toast === msg) store.set({ toast: null }) }, 4200) },
  startRoute(entityId: string) { store.set({ route: { entityId, picking: true, result: null, option: null, busy: false } }) },
  cancelRoute() { store.set({ route: null }) },
}
