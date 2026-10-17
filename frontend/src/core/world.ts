/** WorldModel: the order of battle on the client, evaluated every frame.
 *
 * - Platforms carry declared motion (`/api/world`) and are evaluated locally with `motion.ts` at any scenario time.
 * - Observed tracks (unknown contacts) have no motion here; their poses come from the stream (`EntityBuffer`).
 * - Formations aggregate their visible platforms bottom-up (centroid, extent, worst condition, count).
 * - `cut()` chooses what to draw: a formation is drawn as one symbol while its platforms fit inside `CUT_PX` on
 *   screen, otherwise it is replaced by its children — so the echelon you see follows physical spread, not an
 *   arbitrary zoom table. A brigade in garrison stays one symbol far longer than one strung out on a road march.
 */
import type { CatalogEntity, Condition, StatusRow, WorldCatalog } from '../contracts/types'
import { motionFromApi, Path, poseAt, type Motion, type Pose } from './motion'
import type { EntityBuffer } from './entityBuffer'

export const CUT_PX = 44
const HYST = 0.18
const COND_RANK: Record<Condition, number> = { normal: 0, degraded: 1, unknown: 2, unavailable: 3 }

export interface WNode {
  i: number
  e: CatalogEntity
  parent: WNode | null
  children: WNode[]
  leaf: boolean
  motion: Motion | null
  pose: Pose
  mx: number; my: number
  visible: boolean
  status: StatusRow | null
  // aggregate (formations) — mercator sums and bounds of visible leaves
  count: number; sx: number; sy: number; sq: number; minx: number; maxx: number; miny: number; maxy: number; worst: number; moving: number
  expanded: boolean
}

export interface DisplayItem { node: WNode; lng: number; lat: number; aggregate: boolean; count: number }

export const mercX = (lng: number) => (lng + 180) / 360
export const mercY = (lat: number) => { const s = Math.sin((lat * Math.PI) / 180); return 0.5 - Math.log((1 + s) / (1 - s)) / (4 * Math.PI) }
export const lngOf = (x: number) => x * 360 - 180
export const latOf = (y: number) => (360 / Math.PI) * Math.atan(Math.exp((1 - 2 * y) * Math.PI)) - 90

export class WorldModel {
  readonly nodes: WNode[] = []
  readonly byId = new Map<string, WNode>()
  readonly roots: WNode[] = []
  readonly leaves: WNode[] = []
  readonly routes = new Map<string, Path>()
  private postOrder: WNode[] = []
  catalog: WorldCatalog
  t = 0

  constructor(catalog: WorldCatalog) {
    this.catalog = catalog
    for (const [id, r] of Object.entries(catalog.routes)) this.routes.set(id, new Path(r.path, r.speeds))
    catalog.entities.forEach((e, i) => {
      const n: WNode = {
        i, e, parent: null, children: [], leaf: e.kind !== 'formation', motion: e.motion ? motionFromApi(e.motion, this.routes) : null,
        pose: { lng: 0, lat: 0, alt: null, heading: 0, pitch: 0, bank: 0, speed: 0, phase: 'static', fuel: null }, mx: 0, my: 0, visible: false, status: null,
        count: 0, sx: 0, sy: 0, sq: 0, minx: 1, maxx: 0, miny: 1, maxy: 0, worst: 0, moving: 0, expanded: false,
      }
      this.nodes.push(n); this.byId.set(e.id, n)
    })
    for (const n of this.nodes) {
      const p = n.e.parentId ? this.byId.get(n.e.parentId) : undefined
      if (p) { n.parent = p; p.children.push(n) } else this.roots.push(n)
      if (n.leaf) this.leaves.push(n)
    }
    const visit = (n: WNode) => { for (const c of n.children) visit(c); this.postOrder.push(n) }
    for (const r of this.roots) visit(r)
  }

  get(id: string) { return this.byId.get(id) }

  /** Platforms below a node (or the node itself if it is a platform). */
  leavesOf(n: WNode): WNode[] {
    if (n.leaf) return [n]
    const out: WNode[] = []
    const walk = (m: WNode) => { if (m.leaf) out.push(m); else m.children.forEach(walk) }
    walk(n)
    return out
  }

  /** Ancestor chain from the root down to (excluding) the node. */
  chain(n: WNode): WNode[] { const out: WNode[] = []; let p = n.parent; while (p) { out.unshift(p); p = p.parent } return out }

  /** Pose of any platform at the last update time, even when its layer is hidden (analysis needs all of them). */
  poseNow(n: WNode): Pose { if (n.visible || !n.motion) return n.pose; return poseAt(n.motion, this.t, n.pose) }

  applyStatus(status: Record<string, StatusRow> | null) {
    for (const n of this.leaves) n.status = status?.[n.e.id] ?? null
  }

  /** Evaluate every platform at scenario time t and aggregate formations. `show` decides layer visibility per leaf. */
  update(t: number, show: (n: WNode) => boolean, observed: EntityBuffer | null, observedT: number) {
    this.t = t
    for (const n of this.postOrder) {
      if (n.leaf) {
        let ok = show(n)
        if (ok) {
          if (n.motion) poseAt(n.motion, t, n.pose)
          else if (observed) {
            const p = observed.poseAt(n.e.id, observedT)
            if (p) { n.pose.lng = p.lng; n.pose.lat = p.lat; n.pose.alt = p.alt; n.pose.heading = p.heading; n.pose.speed = p.speed; n.pose.phase = p.stale ? 'holding' : 'moving' }
            else ok = false
          } else ok = false
        }
        n.visible = ok
        if (ok) { n.mx = mercX(n.pose.lng); n.my = mercY(n.pose.lat) }
        continue
      }
      n.count = 0; n.sx = 0; n.sy = 0; n.sq = 0; n.minx = 1; n.maxx = 0; n.miny = 1; n.maxy = 0; n.worst = 0; n.moving = 0
      for (const c of n.children) {
        if (c.leaf) {
          if (!c.visible) continue
          n.count++; n.sx += c.mx; n.sy += c.my; n.sq += c.mx * c.mx + c.my * c.my
          if (c.mx < n.minx) n.minx = c.mx; if (c.mx > n.maxx) n.maxx = c.mx
          if (c.my < n.miny) n.miny = c.my; if (c.my > n.maxy) n.maxy = c.my
          const rank = c.status ? COND_RANK[c.status[0]] ?? 0 : 0
          if (rank > n.worst) n.worst = rank
          if (c.pose.speed > 0.5) n.moving++
        } else if (c.count) {
          n.count += c.count; n.sx += c.sx; n.sy += c.sy; n.sq += c.sq
          if (c.minx < n.minx) n.minx = c.minx; if (c.maxx > n.maxx) n.maxx = c.maxx
          if (c.miny < n.miny) n.miny = c.miny; if (c.maxy > n.maxy) n.maxy = c.maxy
          if (c.worst > n.worst) n.worst = c.worst
          n.moving += c.moving
        }
      }
      n.visible = n.count > 0
      if (n.visible) { n.mx = n.sx / n.count; n.my = n.sy / n.count; n.pose.lng = lngOf(n.mx); n.pose.lat = latOf(n.my) }
    }
  }

  /** What to draw at this zoom. Greedy, budgeted expansion: the formation spreading widest on screen opens first,
   * replaced by its children, until either everything left fits inside CUT_PX or the symbol budget for this zoom is
   * spent. Density therefore stays readable at every scale while the most dispersed activity is resolved first.
   * `pin` forces expansion along a path (the selection's ancestors) so a selection is never hidden in an aggregate. */
  cut(worldPx: number, view: { minx: number; maxx: number; miny: number; maxy: number }, pin: Set<string>, budget: number): DisplayItem[] {
    const out: DisplayItem[] = []
    const pad = 0.05 * (view.maxx - view.minx)
    const inView = (n: WNode) => n.maxx >= view.minx - pad && n.minx <= view.maxx + pad && n.maxy >= view.miny - pad && n.miny <= view.maxy + pad
    const leafIn = (n: WNode) => n.mx >= view.minx - pad && n.mx <= view.maxx + pad && n.my >= view.miny - pad && n.my <= view.maxy + pad
    // Spread = 2.5 × RMS radius: robust to a single outlier, yet a convoy strung along a road still opens up.
    const extent = (n: WNode) => 2.5 * Math.sqrt(Math.max(0, n.sq / n.count - n.mx * n.mx - n.my * n.my)) * worldPx
    const heap: WNode[] = []
    const push = (n: WNode) => { heap.push(n); let i = heap.length - 1; while (i > 0) { const p = (i - 1) >> 1; if (extent(heap[p]) >= extent(heap[i])) break; [heap[p], heap[i]] = [heap[i], heap[p]]; i = p } }
    const pop = (): WNode => { const top = heap[0]; const last = heap.pop()!; if (heap.length) { heap[0] = last; let i = 0; for (;;) { const l = 2 * i + 1, r = l + 1; let m = i
      if (l < heap.length && extent(heap[l]) > extent(heap[m])) m = l; if (r < heap.length && extent(heap[r]) > extent(heap[m])) m = r; if (m === i) break; [heap[m], heap[i]] = [heap[i], heap[m]]; i = m } } return top }
    const enqueue = (n: WNode) => {
      if (!n.visible) return
      if (n.leaf) { if (leafIn(n)) out.push({ node: n, lng: n.pose.lng, lat: n.pose.lat, aggregate: false, count: 1 }); return }
      if (!inView(n)) return
      if (n.count === 1) { const only = this.firstVisibleLeaf(n); if (only && leafIn(only)) out.push({ node: only, lng: only.pose.lng, lat: only.pose.lat, aggregate: false, count: 1 }); return }
      push(n)
    }
    for (const r of this.roots) enqueue(r)
    while (heap.length) {
      const n = pop()
      const ext = extent(n)
      const threshold = n.expanded ? CUT_PX * (1 - HYST) : CUT_PX * (1 + HYST)
      const kids = n.children.filter(c => c.visible).length
      const fits = out.length + heap.length + kids <= budget
      n.expanded = pin.has(n.e.id) || (ext > threshold && fits)
      if (!n.expanded) { out.push({ node: n, lng: n.pose.lng, lat: n.pose.lat, aggregate: true, count: n.count }); continue }
      for (const c of n.children) enqueue(c)
    }
    return out
  }

  private firstVisibleLeaf(n: WNode): WNode | null {
    for (const c of n.children) { if (c.leaf) { if (c.visible) return c } else if (c.count) { const x = this.firstVisibleLeaf(c); if (x) return x } }
    return null
  }
}
