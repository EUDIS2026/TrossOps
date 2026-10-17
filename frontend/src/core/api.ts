import type {
  AttentionResponse, Clock, EntityDetail, FeedPayload, FormationDetail, InputReport, KinematicsTick, LiveAircraft, LiveVessel, PlanResult, RoutePlan,
  SiteLayout, Snapshot, SourceStatus, TrackResponse, Views, WorldCatalog,
} from '../contracts/types'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } })
  if (!response.ok) {
    let detail = `${response.status}`
    try { detail = (await response.json()).detail ?? detail } catch { /* keep status */ }
    throw new ApiError(response.status, typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  return response.json() as Promise<T>
}

const q = (params: Record<string, string | number | boolean | null | undefined>) => {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined) s.set(k, String(v))
  const str = s.toString()
  return str ? `?${str}` : ''
}
const post = (body: unknown): RequestInit => ({ method: 'POST', body: JSON.stringify(body) })

export const api = {
  views: () => request<Views>('/api/views'),
  clock: () => request<Clock>('/api/clock'),
  world: () => request<WorldCatalog>('/api/world'),
  layout: (siteId: string) => request<SiteLayout>(`/api/sites/${siteId}/layout`),
  snapshot: (at: number | null, role: string | null) => request<Snapshot>(`/api/scene/snapshot${q({ at, role })}`),
  observed: (at: number | null) => request<KinematicsTick>(`/api/scene/entities${q({ at })}`),
  attention: (at: number | null, resolution: string, role: string | null) => request<AttentionResponse>(`/api/scene/attention${q({ at, resolution, role })}`),
  tracks: (id: string, from: number, to: number, step = 30) => request<TrackResponse>(`/api/scene/tracks/${id}${q({ from, to, step })}`),
  entity: (id: string, at: number | null) => request<EntityDetail | FormationDetail>(`/api/entities/${id}${q({ at })}`),
  postInput: (body: Record<string, unknown>) => request<{ input: InputReport; worldRevision: number }>('/api/inputs', post(body)),
  ack: (id: string) => request<{ worldRevision: number }>(`/api/alerts/${id}/ack`, { method: 'POST' }),
  commit: (id: string, optionId: string, expectedRevision: number) => request<{ worldRevision: number }>(`/api/interventions/${id}/commit`, post({ optionId, expectedRevision })),
  abort: (id: string) => request<{ worldRevision: number }>(`/api/interventions/${id}/abort`, { method: 'POST' }),
  optimise: (at: number | null) => request<PlanResult>(`/api/strategy/optimize${q({ at })}`, { method: 'POST' }),
  event: (assetId: string, kind: string, expectedRevision: number) => request<{ worldRevision: number }>('/api/events', post({ assetId, kind, expectedRevision })),
  planRoute: (entityId: string, to: [number, number]) => request<RoutePlan>('/api/plan/route', post({ entityId, to })),
  commitPlan: (body: { entityId: string; path: unknown; speeds: number[]; airborne: boolean; label: string; expectedRevision: number }) =>
    request<{ worldRevision: number; catalogRevision: number }>('/api/plan/commit', post(body)),
  cancelPlan: (entityId: string) => request<{ worldRevision: number }>(`/api/plan/${entityId}/cancel`, { method: 'POST' }),
  inject: (preset: string) => request<{ worldRevision: number; message: string }>('/api/scenario/inject', post({ preset })),
  // real public feeds
  sources: (probe = false) => request<{ disabled: boolean; sources: SourceStatus[]; attribution: string[] }>(`/api/sources${q({ probe })}`),
  aircraft: () => request<FeedPayload<LiveAircraft>>('/api/live/aircraft'),
  aircraftTrail: (hex: string) => request<{ points: { lng: number; lat: number; altM: number | null; t: number }[] }>(`/api/live/aircraft/${hex}/trail`),
  vessels: () => request<FeedPayload<LiveVessel>>('/api/live/vessels'),
  vesselHistory: (mmsi: string) => request<{ points: { lng: number; lat: number; t: number }[] }>(`/api/live/vessels/${mmsi}/history`),
  gnss: () => request<FeedPayload<{ lng: number; lat: number; degraded: boolean; hex: string }>>('/api/live/gnss'),
  observations: () => request<FeedPayload<Record<string, unknown>>>('/api/env/observations'),
  warnings: () => request<FeedPayload<Record<string, unknown>>>('/api/env/warnings'),
  grid: () => request<FeedPayload<never> & { points?: Record<string, number | null>[]; lngStep?: number; latStep?: number }>('/api/env/grid'),
  radar: () => request<FeedPayload<never> & { frames?: { time: number; tileUrl: string }[]; maxZoom?: number }>('/api/env/radar'),
  traffic: () => request<FeedPayload<Record<string, unknown>>>('/api/civil/traffic'),
  fires: () => request<FeedPayload<Record<string, unknown>>>('/api/env/fires'),
  space: () => request<FeedPayload<never> & { kp?: number; note?: string }>('/api/env/space'),
  police: () => request<FeedPayload<Record<string, unknown>>>('/api/civil/police'),
  crisis: () => request<FeedPayload<Record<string, unknown>>>('/api/civil/crisis'),
}

export type StreamHandlers = { onTick: (tick: KinematicsTick) => void; onRevision: (msg: { worldRevision: number; catalogRevision: number }) => void; onState: (state: 'connecting' | 'live' | 'offline') => void }

/** Server-sent events with automatic reconnect. Returns a disposer. */
export function openStream(h: StreamHandlers): () => void {
  let source: EventSource | null = null
  let timer: number | null = null
  let closed = false
  const connect = () => {
    if (closed) return
    h.onState('connecting')
    source = new EventSource('/api/stream?interval=1')
    source.addEventListener('hello', () => h.onState('live'))
    source.addEventListener('tick', e => { h.onState('live'); h.onTick(JSON.parse((e as MessageEvent).data)) })
    source.addEventListener('revision', e => h.onRevision(JSON.parse((e as MessageEvent).data)))
    source.onerror = () => { h.onState('offline'); source?.close(); source = null; timer = window.setTimeout(connect, 2500) }
  }
  connect()
  return () => { closed = true; if (timer) window.clearTimeout(timer); source?.close() }
}
