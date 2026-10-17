/** Session: owns the client runtime outside React — view model, world catalog, clock, observed-track buffer, live
 * public feeds, the evaluated picture, the selection's detail and every command. Components only read the store. */
import { api, ApiError, openStream } from './api'
import { SimClock } from './clock'
import { EntityBuffer } from './entityBuffer'
import { actions, layerOn, store } from './store'
import { WorldModel } from './world'
import type { RouteOption } from '../contracts/types'

const SNAPSHOT_GRID_S = 10 // scenario seconds between evaluated pictures while simulating
const LIVE_REFRESH_MS = 6000

export class Session {
  readonly clock = new SimClock()
  readonly buffer = new EntityBuffer()
  world: WorldModel | null = null
  private disposeStream: (() => void) | null = null
  private timers: number[] = []
  private inflight = false
  private lastSnapAt = -1
  private lastRole: string | null = null
  private lastSelected: string | null = null
  private catalogRevision = 0
  private feedAt: Record<string, number> = {}
  private unsubscribe: () => void
  onWorld: ((w: WorldModel) => void) | null = null

  constructor() {
    this.unsubscribe = store.subscribe(() => this.onStore())
    void this.start()
  }

  dispose() { this.disposeStream?.(); this.timers.forEach(t => window.clearInterval(t)); this.unsubscribe() }

  private async start() {
    try {
      const [views, clock] = await Promise.all([api.views(), api.clock()])
      this.clock.sync(clock.nowS, clock.speed)
      store.set({ views })
      await this.loadWorld()
      await this.refreshSnapshot(true)
    } catch (e) {
      actions.setError(e instanceof ApiError ? `The scene API answered ${e.status}: ${e.message}` : 'The scene API is not reachable. Start the backend on port 8000.')
    }
    this.disposeStream = openStream({
      onTick: tick => {
        this.buffer.speed = this.clock.speed
        this.buffer.ingest(tick)
        if (tick.catalogRevision !== this.catalogRevision) void this.loadWorld()
      },
      onRevision: msg => { if (msg.catalogRevision !== this.catalogRevision) void this.loadWorld(); void this.refreshSnapshot(true) },
      onState: state => { if (state !== store.get().stream) store.set({ stream: state }) },
    })
    this.timers.push(window.setInterval(() => this.tick(), 500))
    this.timers.push(window.setInterval(() => void this.resync(), 60_000))
  }

  private async resync() { try { const c = await api.clock(); this.clock.sync(c.nowS, c.speed) } catch { /* keep extrapolating */ } }

  async loadWorld() {
    const cat = await api.world()
    this.catalogRevision = cat.catalogRevision
    this.world = new WorldModel(cat)
    this.world.applyStatus(store.get().snapshot?.status ?? null)
    store.set({ worldReady: true, catalogRevision: cat.catalogRevision })
    this.onWorld?.(this.world)
  }

  /** Called twice a second: keeps the clock mirror, the evaluated picture and the live feeds current. */
  private tick() {
    const s = store.get()
    const t = this.clock.now()
    store.set({ clock: { mode: this.clock.mode, rate: this.clock.rate, paused: this.clock.paused, offsetS: this.clock.offset(), t } })
    const grid = this.clock.mode === 'live' ? -1 : Math.floor(t / SNAPSHOT_GRID_S)
    if (this.clock.mode === 'sim' && grid !== this.lastSnapAt) void this.refreshSnapshot()
    if (this.clock.mode === 'live' && performance.now() - (this.feedAt.snapshot ?? 0) > LIVE_REFRESH_MS) void this.refreshSnapshot()
    if (this.clock.mode === 'live') void this.pollFeeds(s)
  }

  private due(key: string, ms: number) {
    const now = performance.now()
    if (now - (this.feedAt[key] ?? -1e12) < ms) return false
    this.feedAt[key] = now
    return true
  }

  private async pollFeeds(s = store.get()) {
    const on = (id: string) => layerOn(s, id)
    if ((on('live.air') || on('live.air_mil') || on('analysis.gnss')) && this.due('aircraft', 10_000)) {
      api.aircraft().then(r => store.set(st => ({ live: { ...st.live, aircraft: r.items ?? [], at: performance.now() } }))).catch(() => undefined)
    }
    if (on('live.sea') && this.due('vessels', 30_000)) {
      api.vessels().then(r => store.set(st => ({ live: { ...st.live, vessels: r.items ?? [], at: performance.now() } }))).catch(() => undefined)
    }
    if (this.due('sources', 120_000)) api.sources(false).then(r => store.set({ sources: r.sources })).catch(() => undefined)
  }

  async refreshSnapshot(force = false) {
    if (this.inflight && !force) return
    this.inflight = true
    this.feedAt.snapshot = performance.now()
    try {
      const s = store.get()
      const sim = this.clock.mode === 'sim'
      const t = this.clock.now()
      this.lastSnapAt = Math.floor(t / SNAPSHOT_GRID_S)
      const snap = await api.snapshot(sim ? Math.max(0, Math.round(t)) : null, s.roleId)
      if (!sim) this.clock.sync(snap.nowS + (performance.now() - this.feedAt.snapshot) / 2000, snap.speed)
      this.world?.applyStatus(snap.status)
      if (sim) { this.buffer.reset(); this.buffer.ingest({ atS: snap.atS, atTime: snap.atTime, worldRevision: snap.worldRevision, catalogRevision: snap.catalogRevision, rows: snap.observed }) }
      store.set({ snapshot: snap, error: null })
      if (s.selected && ['entity', 'formation', 'site', 'track'].includes(s.selected.kind)) void this.refreshDetail(s.selected.id)
    } catch (e) {
      actions.setError(e instanceof ApiError ? `Snapshot failed: ${e.message}` : 'Lost contact with the scene API.')
    } finally { this.inflight = false }
  }

  async refreshDetail(id: string) {
    try {
      const sim = this.clock.mode === 'sim'
      const detail = await api.entity(id, sim ? Math.round(this.clock.now()) : null)
      if (store.get().selected?.id === id) store.set({ detail })
    } catch { if (store.get().selected?.id === id) store.set({ detail: null }) }
  }

  private onStore() {
    const s = store.get()
    if (s.roleId !== this.lastRole) { this.lastRole = s.roleId; if (s.views) void this.refreshSnapshot(true) }
    const sel = s.selected && ['entity', 'formation', 'site', 'track'].includes(s.selected.kind) ? s.selected.id : null
    if (sel !== this.lastSelected) { this.lastSelected = sel; if (sel) void this.refreshDetail(sel); else if (s.detail) store.set({ detail: null }) }
  }

  // ---- time ----------------------------------------------------------------------------------------------
  goLive() { this.clock.goLive(); this.buffer.reset(); void this.refreshSnapshot(true) }
  setRate(rate: number) { this.clock.setRate(rate); void this.refreshSnapshot(true) }
  pause() { this.clock.pause() }
  resume() { this.clock.resume() }
  jump(t: number) { this.clock.jumpTo(t); void this.refreshSnapshot(true) }

  // ---- commands (all go through the API; the map never mutates state itself) --------------------------------
  async commit(interventionId: string, optionId: string) { await this.guard(() => api.commit(interventionId, optionId, store.get().snapshot?.worldRevision ?? 1)) }
  async abort(interventionId: string) { await this.guard(() => api.abort(interventionId)) }
  async ack(alertId: string) { await this.guard(() => api.ack(alertId)) }
  async event(assetId: string, kind: string) { await this.guard(() => api.event(assetId, kind, store.get().snapshot?.worldRevision ?? 1)) }
  async submitInput(body: Record<string, unknown>) { await this.guard(() => api.postInput(body)) }
  async inject(preset: string) {
    await this.guard(async () => { const r = await api.inject(preset); actions.toast(r.message) })
  }
  async optimise() {
    store.set({ busy: true })
    try { store.set({ plan: await api.optimise(this.clock.mode === 'sim' ? Math.round(this.clock.now()) : null) }) }
    catch (e) { actions.setError(e instanceof ApiError ? e.message : 'Optimisation failed.') }
    finally { store.set({ busy: false }) }
  }

  async planRoute(entityId: string, to: [number, number]) {
    store.set(s => ({ route: s.route ? { ...s.route, picking: false, busy: true } : null }))
    try {
      const result = await api.planRoute(entityId, to)
      store.set(s => ({ route: s.route ? { ...s.route, result, option: result.recommended, busy: false } : null }))
    } catch (e) {
      actions.setError(e instanceof ApiError ? `Planning failed: ${e.message}` : 'Planning failed.')
      store.set(s => ({ route: s.route ? { ...s.route, picking: true, busy: false } : null }))
    }
  }

  async commitRoute(entityId: string, opt: RouteOption) {
    await this.guard(async () => {
      await api.commitPlan({ entityId, path: opt.path, speeds: opt.speeds, airborne: opt.airborne, label: opt.label, expectedRevision: store.get().snapshot?.worldRevision ?? 1 })
      store.set({ route: null })
      await this.loadWorld()
      actions.toast(`${opt.label} committed: ${opt.distanceKm} km, ETA ${Math.round(opt.etaMin)} min. The unit is executing it now.`)
    })
  }
  async cancelPlan(entityId: string) { await this.guard(async () => { await api.cancelPlan(entityId); await this.loadWorld() }) }

  private async guard(fn: () => Promise<unknown>) {
    store.set({ busy: true })
    try { await fn(); await this.refreshSnapshot(true) }
    catch (e) {
      if (e instanceof ApiError && e.status === 409) { await this.refreshSnapshot(true); actions.setError('The world changed in another session. The latest revision is loaded; review and retry.') }
      else actions.setError(e instanceof ApiError ? e.message : 'The command could not be sent.')
    } finally { store.set({ busy: false }) }
  }
}
