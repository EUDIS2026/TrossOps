import { useEffect, useRef, useState } from 'react'
import { actions, analysisLayer, currentMode, useApp } from '../core/store'
import { fmtClock, fmtDuration, useRuntime } from './context'
import { Icon } from './icons'

const KPI_LABEL: Record<string, string> = {
  readiness: 'Readiness', airReady: 'Air', seaReady: 'Sea', landReady: 'Land', unavailable: 'Unavailable', degraded: 'Degraded', units: 'Platforms', airborne: 'Airborne', moving: 'Moving',
  unknown: 'Unknown tracks', alerts: 'Open alerts', critical: 'Critical', fuel: 'Fuel', faults: 'Faults', interventions: 'Proposed', committed: 'Committed', infra: 'Infrastructure up',
  incidents: 'Emergencies', weather: 'Weather warnings', inputs: 'Reports', coverage: 'Areas covered', deception: 'Deception flags', plan: 'Plan',
}

export function Kpis() {
  const mode = useApp(currentMode)
  const kpis = useApp(s => s.snapshot?.kpis ?? null)
  const live = useApp(s => s.live)
  if (!mode || !kpis) return null
  return <div className="kpis" aria-label="Key figures">
    {mode.kpis.map(k => {
      const v = kpis[k]
      const num = typeof v === 'number' ? v : null
      const tone = (k === 'critical' || k === 'deception') && num ? 'crit' : (k === 'unknown' || k === 'unavailable' || k === 'alerts') && num ? 'warn' : ''
      const text = v === null || v === undefined ? '—' : ['readiness', 'airReady', 'seaReady', 'landReady'].includes(k) ? `${Math.round((num ?? 0) * 100)}` : k === 'fuel' ? `${v}` : String(v)
      return <div key={k} className={`kpi ${tone}`}><b>{text}<em>{['readiness', 'airReady', 'seaReady', 'landReady', 'fuel'].includes(k) ? '%' : ''}</em></b><small>{KPI_LABEL[k] ?? k}</small></div>
    })}
    {live.aircraft.length > 0 && <div className="kpi real"><b>{live.aircraft.length}</b><small>Live aircraft</small></div>}
    {live.vessels.length > 0 && <div className="kpi real"><b>{live.vessels.length}</b><small>Live ships</small></div>}
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
  return <div className="map-legend">
    <div className="legend-title"><span>{label}</span><button className="icon-button small" title="Hide surface" onClick={() => actions.setAnalysis(null)}><Icon.close width={13} height={13} /></button></div>
    <div className="legend-row">{info.legend.map(x => <span key={x.label} className="swatch"><i style={{ background: x.color }} />{x.label}</span>)}</div>
    <small>{info.note}</small>
  </div>
}

export function RouteBanner() {
  const route = useApp(s => s.route)
  const label = useRuntime()?.session.world?.get(route?.entityId ?? '')?.e.label
  if (!route?.picking) return null
  return <div className="banner"><Icon.route width={16} height={16} /> Click the destination for <b>{label ?? route.entityId}</b><button className="mini" onClick={() => actions.cancelRoute()}>Cancel</button></div>
}

export function Toasts() {
  const error = useApp(s => s.error)
  const toast = useApp(s => s.toast)
  return <>
    {toast && <div className="toast ok" role="status">{toast}</div>}
    {error && <div className="toast" role="alert"><span>{error}</span><button className="mini" onClick={() => actions.setError(null)}>Dismiss</button></div>}
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
  return <div className="timeline" aria-label="Time">
    <div className="tl-clock"><b>{fmtClock(at)}</b><small>{sim ? `${clock.offsetS >= 0 ? 'ahead' : 'behind'} ${fmtDuration(clock.offsetS)}` : 'live'}</small></div>
    <div className="tl-buttons">
      <button className="icon-button" title={sim && !clock.paused ? 'Pause (Space)' : 'Play'} onClick={() => (sim && !clock.paused ? rt?.session.pause() : sim ? rt?.session.resume() : rt?.session.setRate(1))}>
        {sim && !clock.paused ? <Icon.pause /> : <Icon.play />}</button>
      {[10, 60, 300].map(r => <button key={r} className="rate" aria-pressed={sim && !clock.paused && clock.rate === r} onClick={() => rt?.session.setRate(r)}>×{r}</button>)}
    </div>
    <div className="scrub">
      <div className="track"><i className="past" style={{ width: `${frac(liveT)}%` }} /><i className="now" style={{ left: `${frac(liveT)}%` }} />
        {marks.map(m => m.s >= lo && <i key={m.id} className={`mark ${m.sev}`} style={{ left: `${frac(m.s)}%` }} />)}</div>
      <input type="range" min={lo} max={hi} step={10} value={Math.min(hi, Math.max(lo, t))} aria-label="Scenario time" onChange={e => onChange(Number(e.target.value))} />
      <div className="tl-scale"><span>−3 h</span><span>now</span><span>+3 h (simulated)</span></div>
    </div>
    <button className={`btn small ${sim ? 'primary' : ''}`} disabled={!sim} onClick={() => rt?.session.goLive()}><Icon.live width={14} height={14} />Live</button>
  </div>
}
