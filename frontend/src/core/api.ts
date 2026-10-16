import type { AttentionResponse, Clock, EntityDetail, Forecast, InputReport, KinematicsTick, PlanResult, Snapshot, TrackResponse, Views } from '../contracts/types'

export class ApiError extends Error {
  constructor(public status: number, message: string) { super(message) }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, { ...init, headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) } })
  if (!response.ok) {
    let detail = `${response.status}`
    try { detail = (await response.json()).detail ?? detail } catch { /* keep status */ }
    throw new ApiError(response.status, detail)
  }
  return response.json() as Promise<T>
}

const q = (params: Record<string, string | number | null | undefined>) => {
  const s = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) if (v !== null && v !== undefined) s.set(k, String(v))
  const str = s.toString()
  return str ? `?${str}` : ''
}

export const api = {
  views: () => request<Views>('/api/views'),
  clock: () => request<Clock>('/api/clock'),
  snapshot: (at: number | null, role: string | null) => request<Snapshot>(`/api/scene/snapshot${q({ at, role })}`),
  entities: (at: number | null) => request<KinematicsTick>(`/api/scene/entities${q({ at })}`),
  attention: (at: number | null, resolution: string, role: string | null) => request<AttentionResponse>(`/api/scene/attention${q({ at, resolution, role })}`),
  tracks: (id: string, from: number, to: number, step = 30) => request<TrackResponse>(`/api/scene/tracks/${id}${q({ from, to, step })}`),
  entity: (id: string, at: number | null) => request<EntityDetail>(`/api/entities/${id}${q({ at })}`),
  postInput: (body: Record<string, unknown>) => request<{ input: InputReport; worldRevision: number }>('/api/inputs', { method: 'POST', body: JSON.stringify(body) }),
  ack: (id: string) => request<{ worldRevision: number }>(`/api/alerts/${id}/ack`, { method: 'POST' }),
  commit: (id: string, optionId: string, expectedRevision: number) => request<{ worldRevision: number }>(`/api/interventions/${id}/commit`, { method: 'POST', body: JSON.stringify({ optionId, expectedRevision }) }),
  abort: (id: string) => request<{ worldRevision: number }>(`/api/interventions/${id}/abort`, { method: 'POST' }),
  optimise: (at: number | null) => request<PlanResult>(`/api/strategy/optimize${q({ at })}`, { method: 'POST' }),
  event: (assetId: string, kind: string, expectedRevision: number) => request<{ worldRevision: number }>('/api/events', { method: 'POST', body: JSON.stringify({ assetId, kind, expectedRevision }) }),
  forecast: (location: string) => request<Forecast>(`/api/environment/forecast/${location}`),
  points: () => request<{ points: Record<string, { label: string; point: number[] }> }>('/api/environment/points'),
}

export type StreamHandlers = { onTick: (tick: KinematicsTick) => void; onRevision: (revision: number) => void; onState: (state: 'connecting' | 'live' | 'offline') => void }

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
    source.addEventListener('revision', e => h.onRevision(JSON.parse((e as MessageEvent).data).worldRevision))
    source.onerror = () => { h.onState('offline'); source?.close(); source = null; timer = window.setTimeout(connect, 2500) }
  }
  connect()
  return () => { closed = true; if (timer) window.clearTimeout(timer); source?.close() }
}
