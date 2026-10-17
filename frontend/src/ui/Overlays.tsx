import { useEffect, useRef, useState } from 'react'
import { actions, analysisLayer, currentMode, store, useApp, type Panel } from '../core/store'
import { fmtClock, fmtDuration, useRuntime } from './context'
import { Icon } from './icons'

/** Key figures: short label, what it counts, and the panel that explains it (if any). */
const KPI: Record<string, [string, string, Panel?]> = {
  readiness: ['Readiness', 'Mean readiness of own units in scope'], airReady: ['Air ready', 'Mean readiness of own aircraft'], seaReady: ['Sea ready', 'Mean readiness of own ships'],
  landReady: ['Land ready', 'Mean readiness of own ground units'], unavailable: ['Unavailable', 'Own units that cannot be used now'], degraded: ['Degraded', 'Own units with reduced capability'],
  units: ['Platforms', 'Moving platforms in scope'], airborne: ['Airborne', 'Own aircraft in the air now'], moving: ['Moving', 'Platforms on the move now'],
  unknown: ['Unknown tracks', 'Tracks whose identity is not resolved'], alerts: ['Open alerts', 'Alerts not yet acknowledged', 'feed'], critical: ['Critical', 'Critical alerts not yet acknowledged', 'feed'],
  fuel: ['Fuel (mean)', 'Mean fuel level of own units'], faults: ['With faults', 'Own units with at least one recorded fault'], interventions: ['Awaiting decision', 'Courses of action waiting for a decision', 'decisions'],
  committed: ['Committed', 'Courses of action in progress or completed', 'decisions'], infra: ['Infrastructure up', 'Infrastructure sites working normally / all', 'feed'],
  incidents: ['Emergencies', 'Civil emergency reports', 'feed'], weather: ['Weather warnings', 'Weather advisory reports', 'feed'], inputs: ['Reports', 'Reports from every channel', 'feed'],
  coverage: ['Areas covered', 'Defence areas with the coverage they need / all'], deception: ['Possible deception', 'Tracks and reports assessed 50 % or more likely deceptive'],
}
const PCT = ['readiness', 'airReady', 'seaReady', 'landReady', 'fuel']

export function Kpis() {
  const mode = useApp(currentMode)
  const kpis = useApp(s => s.snapshot?.kpis ?? null)
  const live = useApp(s => s.live)
  if (!mode || !kpis) return null
  return <div className="kpis" role="group" aria-label="Key figures">
    {mode.kpis.map(k => {
      const v = kpis[k]
      const num = typeof v === 'number' ? v : null
      const tone = (k === 'critical' || k === 'deception') && num ? 'crit' : (k === 'unknown' || k === 'unavailable' || k === 'alerts') && num ? 'warn' : ''
      const text = v === null || v === undefined ? '—' : ['readiness', 'airReady', 'seaReady', 'landReady'].includes(k) ? `${Math.round((num ?? 0) * 100)}` : k === 'fuel' ? `${v}` : String(v)
      const [label, hint, panel] = KPI[k] ?? [k, k]
      const body = <><b>{text}<em>{PCT.includes(k) ? '%' : ''}</em></b><small>{label}</small></>
      return panel ? <button key={k} className={`kpi ${tone}`} title={`${hint}. Click to open.`} onClick={() => { if (!store.get().panels[panel]) actions.togglePanel(panel) }}>{body}</button>
        : <div key={k} className={`kpi ${tone}`} title={hint}>{body}</div>
    })}
    {live.aircraft.length > 0 && <div className="kpi real" title="Real aircraft from public ADS-B (Layers → Live traffic)"><b>{live.aircraft.length}</b><small>Live aircraft</small></div>}
    {live.vessels.length > 0 && <div className="kpi real" title="Real ships from public AIS (Layers → Live traffic)"><b>{live.vessels.length}</b><small>Live ships</small></div>}
  </div>
}

export function HoverCard() {
  const h = useApp(s => s.hovered)
  const sel = useApp(s => s.selected?.id)
  if (!h || h.id === sel) return null
  return <div className="hover" style={{ left: h.x + 18, top: h.y + 12 }}>
    <strong>{h.title}</strong>{h.lines.map(l => <small key={l}>{l}</small>)}
  </div>
}

export function Legend() {
  const info = useApp(s => s.analysisInfo)
  const on = useApp(s => analysisLayer(s))
  const label = useApp(s => s.views?.layers.find(l => l.id === on)?.label)
  const drawer = useApp(s => s.panels.layers)
  if (!on || !info || drawer) return null
  return <div className="map-legend" role="region" aria-label={`Analysis legend: ${label}`}>
    <div className="legend-title"><span><small>Analysis</small> {label}</span><button className="icon-button small" title="Turn off this analysis" aria-label="Turn off this analysis" onClick={() => actions.setAnalysis(null)}><Icon.close width={13} height={13} /></button></div>
    <div className="legend-row">{info.legend.map(x => <span key={x.label} className="swatch"><i style={{ background: x.color }} />{x.label}</span>)}</div>
    <small>{info.note}</small>
  </div>
}

export function RouteBanner() {
  const route = useApp(s => s.route)
  const label = useRuntime()?.session.world?.get(route?.entityId ?? '')?.e.label
  if (!route?.picking) return null
  return <div className="banner" role="status" aria-live="polite"><Icon.route width={16} height={16} /> Click the destination for <b>{label ?? route.entityId}</b><button className="mini" title="Cancel (Esc)" onClick={() => actions.cancelRoute()}>Cancel</button></div>
}

/** Toasts and errors, plus a screen-reader announcement when new alerts arrive. The live regions are always in
 * the DOM (only their content changes) so assistive technology announces every update. */
export function Toasts() {
  const error = useApp(s => s.error)
  const toast = useApp(s => s.toast)
  const alerts = useApp(s => s.snapshot?.alerts)
  const seen = useRef<Set<string> | null>(null)
  const [news, setNews] = useState('')
  useEffect(() => {
    if (!alerts) return
    if (!seen.current) { seen.current = new Set(alerts.map(a => a.id)); return } // the first picture is not news
    const fresh = alerts.filter(a => !a.acknowledged && !seen.current!.has(a.id))
    for (const a of alerts) seen.current.add(a.id)
    if (!fresh.length) return
    const crit = fresh.filter(a => a.severity === 'critical').length
    setNews(`${fresh.length} new alert${fresh.length === 1 ? '' : 's'}${crit ? `, ${crit} critical` : ''}: ${fresh.slice(0, 3).map(a => a.title).join('; ')}${fresh.length > 3 ? '; and more in Alerts & reports' : ''}`)
  }, [alerts])
  return <>
    <div role="status" aria-live="polite">{toast && <div className="toast ok">{toast}</div>}</div>
    <div role="alert">{error && <div className="toast"><span>{error}</span><button className="mini" onClick={() => actions.setError(null)}>Dismiss</button></div>}</div>
    <div className="sr-only" role="status" aria-live="polite">{news}</div>
  </>
}

export function Timeline() {
  const rt = useRuntime()
  const clock = useApp(s => s.clock)
  const snapAt = useApp(s => s.snapshot?.atTime)
  const snapS = useApp(s => s.snapshot?.atS ?? 0)
  const inputs = useApp(s => s.snapshot?.inputs)
  const [drag, setDrag] = useState<number | null>(null)
  const timer = useRef(0)
  const liveT = rt?.session.clock.liveNow() ?? 0
  const lo = Math.max(0, liveT - 3 * 3600), hi = liveT + 3 * 3600
  const t = drag ?? clock.t
  const frac = (x: number) => ((x - lo) / (hi - lo)) * 100
  const at = snapAt ? new Date(new Date(snapAt).getTime() + (t - snapS) * 1000) : null
  const marks = (inputs ?? []).filter(i => i.severity === 'critical' || i.severity === 'warning').map(i => ({ id: i.id, sev: i.severity, s: snapAt ? snapS + (new Date(i.effectiveAt).getTime() - new Date(snapAt).getTime()) / 1000 : 0 }))
  const onChange = (v: number) => {
    setDrag(v)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => { setDrag(null); if (Math.abs(v - liveT) < 20) rt?.session.goLive(); else { rt?.session.jump(v); rt?.session.pause() } }, 180)
  }
  useEffect(() => () => window.clearTimeout(timer.current), [])
  const sim = clock.mode === 'sim'
  const running = sim && !clock.paused
  return <div className="timeline" role="group" aria-label="Timeline">
    <div className="tl-clock"><b>{fmtClock(at)}</b><small>{sim ? `${clock.offsetS > 5 ? 'simulation' : 'replay'} · ${clock.offsetS >= 0 ? '+' : '−'}${fmtDuration(clock.offsetS)}` : 'live'}</small></div>
    <div className="tl-buttons">
      <button className="icon-button" title={running ? 'Pause (Space)' : sim ? 'Resume (Space)' : 'Run the clock from now in simulation (Space pauses)'} aria-label={running ? 'Pause' : 'Play'}
        onClick={() => (running ? rt?.session.pause() : sim ? rt?.session.resume() : rt?.session.setRate(1))}>
        {running ? <Icon.pause /> : <Icon.play />}</button>
      {[10, 60, 300].map(r => <button key={r} className="rate" aria-pressed={running && clock.rate === r} title={`Simulate ${r} times faster than real time`} onClick={() => rt?.session.setRate(r)}>×{r}</button>)}
    </div>
    <div className="scrub">
      <div className="track"><i className="past" style={{ width: `${frac(liveT)}%` }} /><i className="now" style={{ left: `${frac(liveT)}%` }} />
        {marks.map(m => m.s >= lo && <i key={m.id} className={`mark ${m.sev}`} style={{ left: `${frac(m.s)}%` }} />)}</div>
      <input type="range" min={lo} max={hi} step={10} value={Math.min(hi, Math.max(lo, t))} aria-label="Picture time: drag left to replay, right to simulate" aria-valuetext={fmtClock(at)}
        title="Drag left to replay the last 3 hours, right to simulate the next 3; marks are warning and critical reports" onChange={e => onChange(Number(e.target.value))} />
      <div className="tl-scale"><span>−3 h replay</span><span>now</span><span>+3 h simulated</span></div>
    </div>
    <button className={`btn small ${sim ? 'primary' : ''}`} disabled={!sim} title={sim ? 'Back to now, with real feeds' : 'Already live'} onClick={() => rt?.session.goLive()}><Icon.live width={14} height={14} />Live</button>
  </div>
}
