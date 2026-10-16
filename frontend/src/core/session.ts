/** Session: loads the view model, keeps the snapshot current (live stream + revision refreshes, or a fixed replay
 * time), and fetches detail for the selection. Runs outside React; components only read the store. */
import { api, ApiError, openStream } from './api'
import type { SceneController } from '../scene/controller'
import { store, actions } from './store'

export class Session {
  private disposeStream: (() => void) | null = null
  private snapshotTimer = 0
  private inflight = false
  private lastRevision = 0
  private prevSelected: string | null = null
  private prevTime: unknown = null
  private prevRole: string | null = null
  private unsubscribe: () => void

  constructor(private scene: SceneController) {
    this.unsubscribe = store.subscribe(() => this.onStore())
    void this.start()
  }

  dispose() { this.disposeStream?.(); window.clearInterval(this.snapshotTimer); this.unsubscribe() }

  private async start() {
    try {
      const views = await api.views()
      store.set({ views })
      await this.refreshSnapshot()
    } catch (e) {
      actions.setError(e instanceof ApiError ? `The scene API answered ${e.status}: ${e.message}` : 'The scene API is not reachable. Start the backend on port 8000.')
    }
    this.disposeStream = openStream({
      onTick: tick => {
        if (store.get().time.mode !== 'live') return
        this.scene.buffer.ingest(tick)
        if (tick.worldRevision !== this.lastRevision && this.lastRevision) void this.refreshSnapshot()
      },
      onRevision: () => void this.refreshSnapshot(),
      onState: state => { if (state !== store.get().stream) store.set({ stream: state }) },
    })
    // Rules react to time (new scripted inputs, predictions move): refresh the evaluated picture every 15 s even without a revision change.
    this.snapshotTimer = window.setInterval(() => { if (store.get().time.mode === 'live') void this.refreshSnapshot() }, 15_000)
  }

  async refreshSnapshot() {
    if (this.inflight) return
    this.inflight = true
    try {
      const s = store.get()
      const snap = await api.snapshot(s.time.mode === 'replay' ? s.time.atS : null, s.roleId)
      this.lastRevision = snap.worldRevision
      store.set({ snapshot: snap, error: null })
      if (s.selected?.kind === 'entity') void this.refreshDetail(s.selected.id)
    } catch (e) {
      actions.setError(e instanceof ApiError ? `Snapshot failed: ${e.message}` : 'Lost contact with the scene API.')
    } finally { this.inflight = false }
  }

  async refreshDetail(id: string) {
    try {
      const s = store.get()
      const detail = await api.entity(id, s.time.mode === 'replay' ? s.time.atS : null)
      if (store.get().selected?.id === id) store.set({ detail })
    } catch { store.set({ detail: null }) }
  }

  private onStore() {
    const s = store.get()
    if (s.roleId !== this.prevRole) { this.prevRole = s.roleId; if (s.views) void this.refreshSnapshot() }
    if (s.time !== this.prevTime) {
      this.prevTime = s.time
      if (s.time.mode === 'replay') void this.refreshSnapshot()
      else { this.scene.buffer.reset(); void this.refreshSnapshot() }
    }
    const sel = s.selected?.kind === 'entity' ? s.selected.id : null
    if (sel !== this.prevSelected) {
      this.prevSelected = sel
      if (sel) void this.refreshDetail(sel); else if (s.detail) store.set({ detail: null })
    }
  }

  // ---- commands (all go through the API; the map never mutates state itself) ---------------------
  async commit(interventionId: string, optionId: string) {
    const rev = store.get().snapshot?.worldRevision ?? 1
    await this.guard(() => api.commit(interventionId, optionId, rev))
  }
  async abort(interventionId: string) { await this.guard(() => api.abort(interventionId)) }
  async ack(alertId: string) { await this.guard(() => api.ack(alertId)) }
  async event(assetId: string, kind: string) {
    const rev = store.get().snapshot?.worldRevision ?? 1
    await this.guard(() => api.event(assetId, kind, rev))
  }
  async submitInput(body: Record<string, unknown>) { await this.guard(() => api.postInput(body)) }
  async optimise() {
    store.set({ busy: true })
    try { const plan = await api.optimise(store.get().time.mode === 'replay' ? store.get().time.atS : null); store.set({ plan }) }
    catch (e) { actions.setError(e instanceof ApiError ? e.message : 'Optimisation failed.') }
    finally { store.set({ busy: false }) }
  }

  private async guard(fn: () => Promise<unknown>) {
    store.set({ busy: true })
    try { await fn(); await this.refreshSnapshot() }
    catch (e) {
      if (e instanceof ApiError && e.status === 409) { await this.refreshSnapshot(); actions.setError('The world changed in another session. The latest revision is loaded; review and retry.') }
      else actions.setError(e instanceof ApiError ? e.message : 'The command could not be sent.')
    } finally { store.set({ busy: false }) }
  }
}
