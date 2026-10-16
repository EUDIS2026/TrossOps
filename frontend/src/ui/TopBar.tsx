import { useEffect, useRef, useState } from 'react'
import { actions, currentRole, EMPTY, useApp } from '../core/store'
import { fmtClock } from './context'
import { Icon } from './icons'

function RoleMenu() {
  const views = useApp(s => s.views)
  const roleId = useApp(s => s.roleId)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    const key = (e: KeyboardEvent) => { if (e.key === 'Escape') setOpen(false) }
    window.addEventListener('mousedown', close); window.addEventListener('keydown', key)
    return () => { window.removeEventListener('mousedown', close); window.removeEventListener('keydown', key) }
  }, [open])
  const role = views?.roles.find(r => r.id === roleId)
  return <div className="role-menu" ref={ref}>
    <button className="role-button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(o => !o)} title="Change role">
      <span>{role?.label ?? 'Loading roles'}</span><Icon.chevron width={14} height={14} />
    </button>
    {open && views && <div className="menu" role="listbox" aria-label="Role">
      {views.roles.map(r => <button key={r.id} role="option" aria-selected={r.id === roleId} className="menu-item" onClick={() => { actions.setRole(r.id); setOpen(false) }}>
        <strong>{r.label}</strong><span className="scope">{r.scope}</span><small>{r.description}</small>
      </button>)}
    </div>}
  </div>
}

function ModeTabs() {
  const role = useApp(currentRole)
  const modeId = useApp(s => s.modeId)
  if (!role) return <div className="modes" aria-hidden />
  return <div className="modes" role="tablist" aria-label="Map mode">
    {role.modes.map(m => <button key={m.id} role="tab" aria-selected={m.id === modeId} title={m.description} onClick={() => actions.setMode(m.id)}>{m.label}</button>)}
  </div>
}

export function TopBar() {
  const panels = useApp(s => s.panels)
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const stream = useApp(s => s.stream)
  const time = useApp(s => s.time)
  const snap = useApp(s => s.snapshot)
  const threeD = useApp(s => s.threeD)
  const unacked = alerts.filter(a => !a.acknowledged)
  const critical = unacked.filter(a => a.severity === 'critical').length
  const replay = time.mode === 'replay'
  return <header className="topbar">
    <div className="brand">
      <span className="wordmark"><i />TrossOps</span>
      <RoleMenu />
    </div>
    <ModeTabs />
    <div className="top-actions">
      <span className="status-chip optional" title={snap?.dataNotice ?? ''}>
        <span className={`pip ${replay ? 'replay' : stream}`} />
        {replay ? 'Replay' : stream === 'live' ? 'Live' : stream === 'connecting' ? 'Connecting' : 'Stream offline'}
        <b>{fmtClock(snap?.atTime)}</b>
        <span>rev <b>{snap?.worldRevision ?? '—'}</b></span>
      </span>
      <button className="icon-button" aria-pressed={panels.search} title="Search (/)" onClick={() => actions.togglePanel('search')}><Icon.search /></button>
      <button className="icon-button" aria-pressed={panels.layers} title="Layers (L)" onClick={() => actions.togglePanel('layers')}><Icon.layers /></button>
      <button className="icon-button" aria-pressed={panels.alerts} title="Alerts (A)" onClick={() => actions.togglePanel('alerts')}>
        <Icon.bell />{unacked.length > 0 && <span className={`badge ${critical ? '' : 'warning'}`}>{unacked.length}</span>}
      </button>
      <button className="icon-button" aria-pressed={panels.decisions} title="Decisions (D)" onClick={() => actions.togglePanel('decisions')}><Icon.decide /></button>
      <button className="icon-button" aria-pressed={panels.inputs} title="Submit a report (R)" onClick={() => actions.togglePanel('inputs')}><Icon.report /></button>
      <button className="icon-button" aria-pressed={threeD} title="3D (3)" onClick={() => actions.toggle3d()}><Icon.cube /></button>
      <button className="icon-button" aria-pressed={panels.help} title="Shortcuts (?)" onClick={() => actions.togglePanel('help')}><Icon.help /></button>
    </div>
  </header>
}
