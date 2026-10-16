import { createContext, useContext } from 'react'
import type { Session } from '../core/session'
import type { SceneController } from '../scene/controller'

export interface Runtime { session: Session; scene: SceneController }
export const RuntimeContext = createContext<Runtime | null>(null)
export function useRuntime(): Runtime | null { return useContext(RuntimeContext) }

export function fmtTime(iso: string | null | undefined): string {
  if (!iso) return '—'
  const d = new Date(iso)
  return d.toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', second: '2-digit', timeZone: 'Europe/Stockholm' })
}
export function fmtClock(iso: string | null | undefined): string {
  if (!iso) return '—'
  return new Date(iso).toLocaleTimeString('sv-SE', { hour: '2-digit', minute: '2-digit', timeZone: 'Europe/Stockholm' })
}
export function fmtDuration(s: number): string {
  const m = Math.floor(s / 60), sec = Math.floor(s % 60)
  return m >= 60 ? `${Math.floor(m / 60)} h ${m % 60} min` : `${m} min ${sec.toString().padStart(2, '0')} s`
}
export function pct(v: number | null | undefined, digits = 0): string { return v === null || v === undefined ? '—' : `${v.toFixed(digits)} %` }
export const kindLabel: Record<string, string> = { fixed_wing: 'Fixed-wing aircraft', helicopter: 'Helicopter', multirotor: 'Multirotor drone', ground_vehicle: 'Ground vehicle', vessel: 'Vessel', personnel: 'Personnel', facility: 'Site', infrastructure: 'Infrastructure', unknown: 'Unknown track' }
export const channelLabel: Record<string, string> = { field_report: 'Field report', unit_sitrep: 'Unit SITREP', logistics_report: 'Logistics report', maintenance_log: 'Maintenance log', sensor_detection: 'Sensor detection', intel_report: 'Intelligence report', civil_emergency: 'Civil emergency', weather_advisory: 'Weather advisory', infrastructure_status: 'Infrastructure status', public_news: 'Public news', cyber_alert: 'Cyber alert', command_directive: 'Command directive', allied_liaison: 'Allied liaison', head_of_state_directive: 'Head-of-state directive' }
