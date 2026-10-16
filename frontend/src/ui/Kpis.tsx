import { currentMode, useApp } from '../core/store'

const LABELS: Record<string, string> = {
  readiness: 'Readiness', airReady: 'Air readiness', seaReady: 'Sea readiness', unavailable: 'Unavailable', degraded: 'Degraded', units: 'Units', unknown: 'Unknown tracks',
  alerts: 'Open alerts', critical: 'Critical', fuel: 'Fuel', faults: 'Faults', interventions: 'Proposed', committed: 'Committed', infra: 'Infrastructure', incidents: 'Emergencies',
  weather: 'Weather advisories', inputs: 'Reports', coverage: 'Areas covered', plan: 'Plan',
}

export function Kpis() {
  const mode = useApp(currentMode)
  const kpis = useApp(s => s.snapshot?.kpis ?? null)
  if (!mode || !kpis) return null
  return <div className="kpis" aria-label="Key figures">
    {mode.kpis.map(k => {
      const v = kpis[k]
      const num = typeof v === 'number' ? v : null
      const cls = k === 'critical' && num ? 'alert' : (k === 'unknown' || k === 'unavailable' || k === 'alerts') && num ? 'warn' : ''
      const text = v === null || v === undefined ? '—' : k === 'readiness' || k === 'airReady' || k === 'seaReady' ? `${Math.round((num ?? 0) * 100)} %` : k === 'fuel' ? `${v} %` : String(v)
      return <div key={k} className={`kpi ${cls}`}><b>{text}</b><small>{LABELS[k] ?? k}</small></div>
    })}
  </div>
}
