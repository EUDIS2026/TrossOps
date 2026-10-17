import { createContext, useContext, useEffect, useRef } from 'react'
import type { Condition } from '../contracts/types'
import type { Session } from '../core/session'
import type { SceneController } from '../scene/controller'
import { natoSymbol } from '../scene/symbols'

export interface Runtime { session: Session; scene: SceneController }
export const RuntimeContext = createContext<Runtime | null>(null)
export function useRuntime(): Runtime | null { return useContext(RuntimeContext) }

/** Arrow keys, Home and End move between the tabs of a tablist and select the tab (WAI-ARIA tabs pattern).
 * Pair with a roving tabIndex (0 on the selected tab, -1 on the rest) so the tablist is one Tab stop. */
export function onTabKeys(e: React.KeyboardEvent<HTMLElement>) {
  if (!['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(e.key)) return
  const tabs = [...e.currentTarget.querySelectorAll<HTMLElement>('[role="tab"]')]
  const i = tabs.indexOf(document.activeElement as HTMLElement)
  if (i < 0) return
  e.preventDefault()
  const n = e.key === 'Home' ? 0 : e.key === 'End' ? tabs.length - 1 : (i + (e.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length
  tabs[n].focus()
  tabs[n].click()
}

const TZ = 'Europe/Stockholm'
export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: TZ })
}
export function fmtClock(iso: string | Date | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', timeZone: TZ })
}
export function fmtDuration(s: number): string {
  const a = Math.abs(s), m = Math.floor(a / 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : m >= 1 ? `${m} min` : `${Math.round(a)} s`
}
export function ago(iso: string | null | undefined): string {
  if (!iso) return '—'
  const s = (Date.now() - new Date(iso).getTime()) / 1000
  return s < 60 ? 'now' : s < 3600 ? `${Math.round(s / 60)} min ago` : s < 86400 ? `${Math.round(s / 3600)} h ago` : `${Math.round(s / 86400)} d ago`
}
export const pct = (v: number | null | undefined, d = 0) => (v === null || v === undefined ? '—' : `${v.toFixed(d)} %`)
export const kindLabel: Record<string, string> = { fixed_wing: 'Fixed-wing aircraft', helicopter: 'Helicopter', multirotor: 'Multirotor drone', ground_vehicle: 'Ground vehicle', vessel: 'Ship', personnel: 'Personnel', facility: 'Site', infrastructure: 'Infrastructure', unknown: 'Unknown track', formation: 'Formation' }

/** Inspector heading per selection kind: the glossary word, never an internal id. */
export const selectionLabel: Record<string, string> = {
  entity: 'Unit', formation: 'Formation', site: 'Site', track: 'Track', aircraft: 'Live aircraft', vessel: 'Live ship', input: 'Report', alert: 'Alert',
  intervention: 'Course of action', cell: 'Analysis cell', area: 'Area', police: 'Police event', warning: 'Weather warning', cable: 'Undersea cable',
}

/** Site kinds as written in a site's first tag. */
export const siteKindLabel: Record<string, string> = {
  airbase: 'Airbase', heliport: 'Heliport', navbase: 'Naval base', garrison: 'Garrison', hq: 'Headquarters', depot: 'Depot', hospital: 'Field hospital',
  radar: 'Sensor site', comms: 'Communications node', power: 'Power grid node', port: 'Port', bridge: 'Fixed crossing', telecom: 'Telecom core',
}

const WORD: Record<string, string> = {
  qra: 'quick-reaction alert', isr: 'surveillance (ISR)', sar: 'search and rescue', asw: 'anti-submarine', aew: 'airborne early warning', sigint: 'signals intelligence',
  medevac: 'medical evacuation', mech_infantry: 'mechanised infantry', comms_hub: 'communications hub', small_uas: 'small drone', low_level: 'low level',
}
/** Capability and tag words in plain language, abbreviations spelled out. */
export const plainWord = (w: string) => WORD[w] ?? w.replace(/_/g, ' ').replace(/\bQRA\b/, 'quick-reaction alert')

export const channelLabel: Record<string, string> = { field_report: 'Field report', unit_sitrep: 'Unit status report (SITREP)', logistics_report: 'Logistics report', maintenance_log: 'Maintenance log', sensor_detection: 'Sensor detection', intel_report: 'Intelligence report', civil_emergency: 'Civil emergency', weather_advisory: 'Weather advisory', infrastructure_status: 'Infrastructure status', public_news: 'Public news', cyber_alert: 'Cyber alert', command_directive: 'Command directive', allied_liaison: 'Allied liaison', head_of_state_directive: 'Head-of-state directive', police_event: 'Police event', crisis_info: 'Crisis information', road_situation: 'Road situation (Trafikverket)', thermal_anomaly: 'Thermal anomaly (NASA FIRMS)' }

/** NATO symbol rendered from its SIDC into a small canvas. */
export function NatoGlyph({ sidc, condition = 'normal', size = 44 }: { sidc: string | null | undefined; condition?: Condition; size?: number }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current
    if (!c) return
    const img = natoSymbol(sidc || 'SUGP--------', condition)
    c.width = img.width; c.height = img.height
    c.getContext('2d')!.drawImage(img, 0, 0)
  }, [sidc, condition])
  return <canvas ref={ref} className="glyph" style={{ width: size, height: size }} aria-hidden />
}

export function Ring({ score, size = 58 }: { score: number; size?: number }) {
  const color = score >= 0.7 ? 'var(--good)' : score >= 0.45 ? 'var(--warning)' : 'var(--critical)'
  return <div className="ring" style={{ width: size, height: size, background: `conic-gradient(${color} ${score * 360}deg, rgba(255,255,255,0.08) 0)` }}><span>{Math.round(score * 100)}</span></div>
}

export function Bar({ value, max = 1, tone }: { value: number; max?: number; tone?: 'good' | 'warn' | 'crit' | 'accent' }) {
  const f = Math.max(0, Math.min(1, value / max))
  const t = tone ?? (f >= 0.6 ? 'good' : f >= 0.3 ? 'warn' : 'crit')
  return <div className={`bar ${t}`}><i style={{ width: `${f * 100}%` }} /></div>
}

export function Fact({ k, v, tone }: { k: string; v: React.ReactNode; tone?: string }) {
  return <div className="fact"><small>{k}</small><b className={tone}>{v}</b></div>
}
