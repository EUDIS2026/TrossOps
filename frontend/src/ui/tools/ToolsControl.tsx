/** Map tools UI: one dock entry (T) opening Measure (M), Line of sight (V), Range ring (C) and the cursor elevation
 * readout (E); a compact card for the active tool; a corner readout. The map side lives in scene/tools.ts. */
import { useEffect, useState, type SVGProps } from 'react'
import type { LineOfSight, TerrainProfile } from '../../contracts/types'
import { useApp } from '../../core/store'
import { MapTools, toolActions, useTools, type Fetched, type ToolId } from '../../scene/tools'
import { bearingDeg, distanceM, fmtBearing, fmtDist, fmtLngLat, fmtNm } from '../../scene/toolGeo'
import { useRuntime } from '../context'
import { Icon } from '../icons'
import './tools.css'

type P = SVGProps<SVGSVGElement>
const svg = (p: P) => ({ width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true, ...p })
export const ToolIcon = {
  tools: (p: P) => <svg {...svg(p)}><path d="M3 17 17 3l4 4L7 21H3v-4Z" /><path d="m13 7 1.5 1.5M10 10l1.5 1.5M7 13l1.5 1.5" /></svg>,
  measure: (p: P) => <svg {...svg(p)}><circle cx="5" cy="18" r="2" /><circle cx="12" cy="8" r="2" /><circle cx="19" cy="15" r="2" /><path d="m6.2 16.4 4.6-6.8M13.4 9.4l4.2 4.2" /></svg>,
  los: (p: P) => <svg {...svg(p)}><circle cx="4.5" cy="9" r="2" /><path d="M6.5 8.6 21 5" /><path d="m3 20 5-6 4 3 3-4 6 7H3Z" /></svg>,
  ring: (p: P) => <svg {...svg(p)}><circle cx="12" cy="12" r="8.5" strokeDasharray="3 2.4" /><circle cx="12" cy="12" r="1.6" /><path d="M12 12h8.5" /></svg>,
  readout: (p: P) => <svg {...svg(p)}><path d="m3 19 6-10 4 6 2-3 6 7H3Z" /><path d="M15 3v5M12.5 5.5h5" /></svg>,
}

const TOOLS: { id: ToolId; label: string; key: string; hint: string }[] = [
  { id: 'measure', label: 'Measure', key: 'M', hint: 'Distance and bearing between clicked points' },
  { id: 'los', label: 'Line of sight', key: 'V', hint: 'Can an observer see a target over the ground?' },
  { id: 'ring', label: 'Range ring', key: 'C', hint: 'Circle of a given radius, e.g. a sensor or weapon range' },
]

/** Dock entry: opens the tools menu; shows the active tool's icon while one is running. */
export function ToolsDockButton() {
  const tool = useTools(s => s.tool)
  const menu = useTools(s => s.menu)
  const readout = useTools(s => s.readout)
  const I = tool ? ToolIcon[tool] : ToolIcon.tools
  return <div className="tools-anchor">
    <button className="dock-btn" aria-pressed={!!tool || menu} aria-haspopup="menu" aria-expanded={menu} title="Map tools (T)" onClick={() => toolActions.toggleMenu()}>
      <I />{readout && <span className="dot info" />}</button>
    {menu && <div className="tools-menu" role="menu" aria-label="Map tools">
      {TOOLS.map(t => { const TI = ToolIcon[t.id]; return <button key={t.id} role="menuitemradio" aria-checked={tool === t.id} className="tools-item" title={`${t.hint} (${t.key})`} onClick={() => toolActions.setTool(t.id)}>
        <TI width={16} height={16} /><span>{t.label}<small>{t.hint}</small></span><kbd>{t.key}</kbd></button> })}
      <div className="tools-sep" />
      <button role="menuitemcheckbox" aria-checked={readout} className="tools-item" title="Ground elevation under the cursor (E)" onClick={() => toolActions.toggleReadout()}>
        <ToolIcon.readout width={16} height={16} /><span>Elevation readout<small>Ground height under the cursor</small></span><span className="switch" data-on={readout} /><kbd>E</kbd></button>
    </div>}
  </div>
}

/** Owns the MapTools instance for the scene's map and renders the active tool card and the readout. */
export function MapToolsLayer() {
  const rt = useRuntime()
  useEffect(() => {
    if (!rt) return
    const t = new MapTools(rt.scene.map)
    return () => t.dispose()
  }, [rt])
  // close the menu on an outside click
  const menu = useTools(s => s.menu)
  useEffect(() => {
    if (!menu) return
    const off = (e: PointerEvent) => { if (!(e.target as HTMLElement).closest?.('.tools-anchor')) toolActions.toggleMenu(false) }
    window.addEventListener('pointerdown', off)
    return () => window.removeEventListener('pointerdown', off)
  }, [menu])
  return <><ToolCard /><Readout /></>
}

function ToolCard() {
  const tool = useTools(s => s.tool)
  const source = useApp(s => s.sources.find(x => x.id === 'lm-markhojd'))
  const seen = useTools(s => s.terrain)
  if (!tool) return null
  // Prefer what the service answered this session; the sources row says adapter-only until it is first probed.
  const terrain = seen === 'working' ? { status: 'working', label: 'working', title: 'Lantmäteriet Markhöjd answered' }
    : seen === 'not configured' ? { status: 'adapter-only', label: 'not configured', title: 'Lantmäteriet Markhöjd credentials are not set on this server' }
    : source?.status === 'working' || source?.status === 'blocked' ? { status: source.status, label: source.status, title: `${source.label}${source.note ? ': ' + source.note : ''}` } : null
  const def = TOOLS.find(t => t.id === tool)!
  const I = ToolIcon[tool]
  return <section className="tool-card" aria-label={def.label}>
    <div className="tool-head">
      <I width={16} height={16} /><h3>{def.label}</h3><kbd title="Shortcut">{def.key}</kbd>
      {tool !== 'ring' && terrain && <span className={`status ${terrain.status}`} title={terrain.title}>terrain {terrain.label}</span>}
      <button className="icon-button small" title="Close tool (Esc)" onClick={() => toolActions.setTool(null)}><Icon.close width={14} height={14} /></button>
    </div>
    {tool === 'measure' && <MeasureCard />}
    {tool === 'los' && <LosCard />}
    {tool === 'ring' && <RingCard />}
  </section>
}

function MeasureCard() {
  const m = useTools(s => s.measure)
  const cursor = useTools(s => s.cursor)
  const pts = m.points
  const segs = pts.slice(1).map((p, i) => ({ d: distanceM(pts[i], p), b: bearingDeg(pts[i], p) }))
  const live = !m.done && cursor && pts.length ? { d: distanceM(pts[pts.length - 1], cursor), b: bearingDeg(pts[pts.length - 1], cursor) } : null
  const total = segs.reduce((a, s) => a + s.d, 0)
  return <>
    <p className="tool-hint">{!pts.length ? 'Click the map to start measuring.' : m.done ? 'Done. Click the map to start a new measurement.' : 'Click to add points · double-click or Enter to finish · Backspace removes the last point · Esc cancels.'}</p>
    {pts.length > 0 && <div className="tool-total"><b>{fmtDist(total + (live?.d ?? 0))}</b><small>{fmtNm(total + (live?.d ?? 0))}{live ? ' · to cursor' : ''}</small></div>}
    {segs.length > 0 && <ol className="tool-segs">{segs.map((s, i) => <li key={i}><span>{i + 1}–{i + 2}</span><b>{fmtDist(s.d)}</b><span>{fmtBearing(s.b)}</span></li>)}
      {live && <li className="live"><span>{pts.length}–·</span><b>{fmtDist(live.d)}</b><span>{fmtBearing(live.b)}</span></li>}</ol>}
    {m.done && <ProfileBlock f={m.profile} />}
    <div className="tool-actions">
      {!m.done && pts.length >= 2 && <button className="btn small primary" onClick={() => toolActions.finishMeasure()}>Finish (Enter)</button>}
      {pts.length > 0 && <button className="btn small" onClick={() => toolActions.clear()}>Clear</button>}
    </div>
    <small className="quiet">Great-circle distance; bearings are true (from north) at the start of each leg.</small>
  </>
}

function ProfileBlock({ f }: { f: Fetched<TerrainProfile> }) {
  if (f.state === 'loading') return <small className="quiet">Loading ground profile…</small>
  if (f.state === 'unavailable' || f.state === 'error') return <small className={f.state === 'error' ? 'err' : 'quiet'}>Ground profile: {f.note}</small>
  if (f.state !== 'ok') return null
  const p = f.data
  return <div className="terrain-profile" title="Ground elevation along the measured line (Lantmäteriet Markhöjd)">
    <ProfileSvg distanceM={p.distanceM} groundM={p.groundM} />
    <small className="quiet">ground {p.minM ?? '?'}–{p.maxM ?? '?'} m · climb {p.climbM} m · Lantmäteriet Markhöjd (RH 2000)</small>
  </div>
}

/** Ground fill plus an optional sight line (absolute metres), red where it runs below the ground. */
function ProfileSvg({ distanceM: d, groundM: g, sight, blockedFrom, marker }: { distanceM: number[]; groundM: (number | null)[]; sight?: (number | null)[]; blockedFrom?: number; marker?: number }) {
  const vals = [...g, ...(sight ?? [])].filter((v): v is number => v !== null)
  if (vals.length < 2) return null
  const total = d[d.length - 1] || 1
  const lo = Math.min(...vals), hi = Math.max(...vals)
  const pad = Math.max(2, (hi - lo) * 0.08)
  const W = 280, H = 70
  const x = (i: number) => (d[i] / total) * W
  const y = (v: number) => H - ((v - (lo - pad)) / (hi - lo + 2 * pad)) * H
  const poly = (vs: (number | null)[], from = 0, to = vs.length - 1) => vs.slice(from, to + 1).map((v, j) => v === null ? null : `${x(from + j).toFixed(1)},${y(v).toFixed(1)}`).filter(Boolean).join(' ')
  const last = g.length - 1
  return <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H}>
    <polygon points={`0,${H} ${poly(g)} ${W},${H}`} className="ground" />
    {sight && (blockedFrom === undefined || blockedFrom < 0
      ? <polyline points={poly(sight)} className="sight ok" />
      : <><polyline points={poly(sight, 0, blockedFrom)} className="sight ok" /><polyline points={poly(sight, blockedFrom, last)} className="sight blocked" /></>)}
    {marker !== undefined && g[marker] !== null && <circle cx={x(marker)} cy={y(g[marker]!)} r={3.2} className="obstruction" />}
  </svg>
}

const OBS_PRESETS = [{ label: 'Standing 2 m', h: 2 }, { label: '10 m mast', h: 10 }, { label: '30 m tower', h: 30 }]
const TGT_PRESETS = [{ label: 'Person 2 m', h: 2 }, { label: 'Vehicle 3 m', h: 3 }, { label: 'Aircraft 150 m', h: 150 }]

function HeightInput({ label, value, onChange }: { label: string; value: number; onChange: (v: number) => void }) {
  const [text, setText] = useState(String(value))
  useEffect(() => setText(String(value)), [value])
  const commit = (t: string) => { const v = Number(t.replace(',', '.')); if (Number.isFinite(v) && v >= 0 && v <= 20_000) onChange(Math.round(v * 10) / 10); else setText(String(value)) }
  return <label className="tool-field">{label}
    <span><input type="number" inputMode="decimal" min={0} max={20000} step={1} value={text} onChange={e => setText(e.target.value)} onBlur={e => commit(e.target.value)}
      onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }} /><em>m</em></span></label>
}

function LosCard() {
  const l = useTools(s => s.los)
  const r = l.result
  return <>
    <p className="tool-hint">{!l.a ? 'Click the observer position.' : !l.b ? 'Click the target position.' : 'Click the map to pick a new observer. Heights are above the ground.'}</p>
    <div className="tool-row">
      <HeightInput label="Observer height" value={l.ha} onChange={v => toolActions.setHeights(v, null)} />
      <HeightInput label="Target height" value={l.hb} onChange={v => toolActions.setHeights(null, v)} />
    </div>
    <div className="tool-presets-grid">
      <small>Observer</small><div className="chips tool-presets">{OBS_PRESETS.map(p => <button key={p.label} className="chip" aria-pressed={l.ha === p.h} title={`Observer ${p.h} m above ground`} onClick={() => toolActions.setHeights(p.h, null)}>{p.label}</button>)}</div>
      <small>Target</small><div className="chips tool-presets">{TGT_PRESETS.map(p => <button key={p.label} className="chip" aria-pressed={l.hb === p.h} title={`Target ${p.h} m above ground`} onClick={() => toolActions.setHeights(null, p.h)}>{p.label}</button>)}</div>
    </div>
    {l.a && l.b && <LosResult r={r} />}
    {l.a && <div className="tool-actions"><button className="btn small" onClick={() => toolActions.clear()}>Clear</button></div>}
  </>
}

function LosResult({ r }: { r: Fetched<LineOfSight> }) {
  if (r.state === 'loading' || r.state === 'idle') return <small className="quiet">Checking terrain…</small>
  if (r.state !== 'ok') return <div className="tool-note"><b>No line-of-sight answer.</b><small>{r.note}</small></div>
  const x = r.data
  const p = x.profile
  const last = p.groundM.length - 1
  const sight = p.groundM.map((g, i) => i === 0 ? (g === null ? null : g + x.observerM) : i === last ? (g === null ? null : g + x.targetM) : (g === null || p.clearanceM[i] === null ? null : g + p.clearanceM[i]!))
  const blockedFrom = p.clearanceM.findIndex(c => c !== null && c <= 0)
  const obsIdx = x.obstruction ? p.distanceM.indexOf(x.obstruction.distanceM) : -1
  return <>
    <div className={`los-verdict ${x.visible ? 'ok' : 'blocked'}`}><b>{x.visible ? 'Visible' : 'Masked by terrain'}</b>
      <small>{fmtDist(x.distanceM)} · {x.visible ? `min clearance ${x.minClearanceM} m` : `ground ${Math.abs(x.minClearanceM ?? 0)} m above the sight line`}</small></div>
    <div className="terrain-profile los" title="Ground (brown) and sight line (green visible, red masked)">
      <ProfileSvg distanceM={p.distanceM} groundM={p.groundM} sight={sight} blockedFrom={blockedFrom} marker={obsIdx >= 0 ? obsIdx : undefined} />
    </div>
    <div className="facts tool-facts">
      <div className="fact"><small>Observer ground</small><b>{p.groundM[0] ?? '?'} m</b></div>
      <div className="fact"><small>Target ground</small><b>{p.groundM[last] ?? '?'} m</b></div>
      {x.obstruction && <div className="fact"><small>Worst obstruction</small><b className="crit">{fmtDist(x.obstruction.distanceM)} out, {Math.round(x.obstruction.groundM)} m</b></div>}
      {blockedFrom > 0 && <div className="fact"><small>Line breaks at</small><b>{fmtDist(p.distanceM[blockedFrom])}</b></div>}
    </div>
    <small className="quiet">Lantmäteriet Markhöjd · bare earth (no trees or buildings) · {x.method}</small>
  </>
}

const RING_PRESETS = [5_000, 10_000, 25_000, 50_000, 100_000]

function RingCard() {
  const r = useTools(s => s.ring)
  const cursor = useTools(s => s.cursor)
  const [text, setText] = useState(String(r.radiusM / 1000))
  useEffect(() => setText(String(Math.round(r.radiusM) / 1000)), [r.radiusM])
  const commit = (t: string) => { const v = Number(t.replace(',', '.')); if (Number.isFinite(v) && v > 0) toolActions.setRadius(v * 1000); else setText(String(r.radiusM / 1000)) }
  const radius = r.center && !r.fixed && cursor ? distanceM(r.center, cursor) : r.radiusM
  return <>
    <p className="tool-hint">{!r.center ? 'Click the centre of the ring.' : !r.fixed ? 'Click again to set the radius, or type it below.' : 'Click the map to place a new ring.'}</p>
    <div className="tool-row">
      <label className="tool-field">Radius<span><input type="number" min={0} step={1} value={text} onChange={e => setText(e.target.value)} onBlur={e => commit(e.target.value)}
        onKeyDown={e => { if (e.key === 'Enter') commit((e.target as HTMLInputElement).value) }} /><em>km</em></span></label>
      <div className="tool-total"><b>{fmtDist(radius)}</b><small>{fmtNm(radius)} · Ø {fmtDist(radius * 2)}</small></div>
    </div>
    <div className="chips tool-presets">{RING_PRESETS.map(m => <button key={m} className="chip" aria-pressed={r.fixed && Math.abs(r.radiusM - m) < 1} onClick={() => toolActions.setRadius(m)}>{m / 1000} km</button>)}</div>
    {r.center && <small className="quiet">Centre {fmtLngLat(r.center)} · flat ground range, ignores terrain masking (use Line of sight).</small>}
    {r.center && <div className="tool-actions"><button className="btn small" onClick={() => toolActions.clear()}>Clear</button></div>}
  </>
}

function Readout() {
  const on = useTools(s => s.readout)
  const cursor = useTools(s => s.cursor)
  const e = useTools(s => s.elevation)
  if (!on) return null
  return <div className="tool-readout" role="status" aria-live="off">
    <ToolIcon.readout width={14} height={14} />
    {cursor ? <><span className="mono-coord">{fmtLngLat(cursor)}</span>
      <b>{e.state === 'ok' ? (e.data === null ? 'no data' : `${e.data.toFixed(1)} m`) : e.state === 'loading' ? '…' : e.state === 'idle' ? '' : '—'}</b>
      {(e.state === 'unavailable' || e.state === 'error') && <small title={e.note}>{e.note}</small>}
      {e.state === 'ok' && <small>ground, RH 2000</small>}</>
      : <small>Move the cursor over the map</small>}
    <button className="icon-button small" title="Hide elevation readout (E)" onClick={() => toolActions.toggleReadout()}><Icon.close width={12} height={12} /></button>
  </div>
}
