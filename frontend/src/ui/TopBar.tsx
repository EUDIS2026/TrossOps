import { useEffect, useMemo, useRef, useState } from 'react'
import { actions, currentRole, EMPTY, useApp } from '../core/store'
import { fmtClock, fmtDuration, NatoGlyph, useRuntime } from './context'
import { Icon } from './icons'

const PLACES: [string, number, number][] = [['Stockholm', 18.07, 59.33], ['Göteborg', 11.97, 57.71], ['Malmö', 13.0, 55.61], ['Uppsala', 17.64, 59.86], ['Visby', 18.29, 57.64], ['Luleå', 22.15, 65.58],
  ['Kiruna', 20.22, 67.86], ['Umeå', 20.26, 63.83], ['Karlskrona', 15.59, 56.16], ['Östersund', 14.64, 63.18], ['Sundsvall', 17.31, 62.39], ['Kalmar', 16.36, 56.66], ['Linköping', 15.62, 58.41],
  ['Örebro', 15.21, 59.27], ['Helsingborg', 12.69, 56.05], ['Boden', 21.69, 65.82], ['Haparanda', 24.14, 65.84], ['Ystad', 13.82, 55.43], ['Gotland', 18.6, 57.45], ['Öland', 16.6, 56.7]]

function RoleMenu() {
  const views = useApp(s => s.views)
  const roleId = useApp(s => s.roleId)
  const [open, setOpen] = useState(false)
  const ref = useRef<HTMLDivElement>(null)
  useEffect(() => {
    if (!open) return
    const close = (e: MouseEvent) => { if (!ref.current?.contains(e.target as Node)) setOpen(false) }
    window.addEventListener('mousedown', close)
    return () => window.removeEventListener('mousedown', close)
  }, [open])
  const role = views?.roles.find(r => r.id === roleId)
  return <div className="role-menu" ref={ref}>
    <button className="role-button" aria-haspopup="listbox" aria-expanded={open} onClick={() => setOpen(o => !o)} title="Change role">
      <span className="role-kicker">Role</span><span>{role?.label ?? 'Loading'}</span><Icon.chevron width={14} height={14} />
    </button>
    {open && views && <div className="menu" role="listbox" aria-label="Role">
      {views.roles.map(r => <button key={r.id} role="option" aria-selected={r.id === roleId} className="menu-item" onClick={() => { actions.setRole(r.id); setOpen(false) }}>
        <strong>{r.label}</strong><small>{r.description}</small>
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

interface Result { kind: 'entity' | 'formation' | 'site' | 'track' | 'aircraft' | 'vessel' | 'place'; id: string; title: string; sub: string; sidc?: string | null; data?: unknown }

function Search() {
  const rt = useRuntime()
  const open = useApp(s => s.panels.search)
  const ready = useApp(s => s.worldReady)
  const live = useApp(s => s.live)
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (open) setTimeout(() => input.current?.focus(), 20) }, [open])
  const results = useMemo<Result[]>(() => {
    const t = q.trim().toLowerCase()
    const w = rt?.session.world
    if (!t || !w) return []
    const out: Result[] = []
    for (const n of w.nodes) {
      const e = n.e
      if (e.label.toLowerCase().includes(t) || e.id.toLowerCase().includes(t) || (e.platform ?? '').toLowerCase().includes(t) || (e.short ?? '').toLowerCase() === t) {
        const kind = e.kind === 'formation' ? 'formation' : e.kind === 'facility' || e.kind === 'infrastructure' ? 'site' : e.affiliation === 'unknown' ? 'track' : 'entity'
        out.push({ kind, id: e.id, title: e.label, sub: kind === 'formation' ? `${e.echelon} · ${e.layer}` : `${e.platform ?? e.kind} · ${e.unit ?? ''}`, sidc: e.sidc })
      }
      if (out.length > 30) break
    }
    for (const a of live.aircraft) if ((a.callsign ?? '').toLowerCase().includes(t) || (a.registration ?? '').toLowerCase().includes(t)) out.push({ kind: 'aircraft', id: a.id, title: a.callsign ?? a.id, sub: `${a.type ?? 'aircraft'} · live ADS-B`, data: a })
    for (const v of live.vessels) if ((v.name ?? '').toLowerCase().includes(t)) out.push({ kind: 'vessel', id: String(v.id), title: v.name ?? String(v.id), sub: `${v.shipTypeLabel ?? 'vessel'} · live AIS`, data: v })
    for (const [name, lng, lat] of PLACES) if (name.toLowerCase().includes(t)) out.push({ kind: 'place', id: name, title: name, sub: 'place', data: [lng, lat] })
    const rank = { formation: 0, site: 1, place: 2, entity: 3, track: 3, aircraft: 4, vessel: 5 }
    return out.sort((a, b) => rank[a.kind] - rank[b.kind]).slice(0, 12)
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [q, ready, live, rt])
  const pick = (r: Result) => {
    actions.setPanel('search', false); setQ('')
    if (r.kind === 'place') { const [lng, lat] = r.data as number[]; rt?.scene.camera.focusPoint(lng, lat, 10.5, rt.scene.map.getPitch(), false); return }
    actions.select(r.kind, r.id, r.data)
  }
  return <div className={`search ${open ? 'open' : ''}`}>
    <Icon.search width={15} height={15} />
    <input ref={input} placeholder="Search units, sites, callsigns, ships, places" value={q} aria-label="Search"
      onFocus={() => actions.setPanel('search', true)} onBlur={() => setTimeout(() => actions.setPanel('search', false), 150)}
      onChange={e => { setQ(e.target.value); setCursor(0) }}
      onKeyDown={e => {
        if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) }
        if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) }
        if (e.key === 'Enter' && results[cursor]) pick(results[cursor])
        if (e.key === 'Escape') { setQ(''); (e.target as HTMLInputElement).blur() }
      }} />
    <kbd>/</kbd>
    {open && results.length > 0 && <div className="search-results" role="listbox">
      {results.map((r, i) => <button key={`${r.kind}:${r.id}`} role="option" aria-selected={i === cursor} className="item" onMouseDown={() => pick(r)}>
        {r.sidc ? <NatoGlyph sidc={r.sidc} size={30} /> : <span className="glyph-ph">{r.kind === 'aircraft' ? <Icon.plane /> : r.kind === 'vessel' ? <Icon.ship /> : <Icon.map />}</span>}
        <span><strong>{r.title}</strong><small>{r.sub}</small></span>
      </button>)}
    </div>}
  </div>
}

function ClockChip() {
  const clock = useApp(s => s.clock)
  const stream = useApp(s => s.stream)
  const epoch = useApp(s => s.snapshot?.atTime)
  const nowS = useApp(s => s.snapshot?.atS ?? 0)
  const at = epoch ? new Date(new Date(epoch).getTime() + (clock.t - nowS) * 1000) : null
  const sim = clock.mode === 'sim'
  return <span className={`status-chip ${sim ? 'sim' : ''}`} title="Scenario clock">
    <span className={`pip ${sim ? 'replay' : stream}`} />
    {sim ? (clock.offsetS > 5 ? 'Simulation' : 'Replay') : stream === 'live' ? 'Live' : stream === 'connecting' ? 'Connecting' : 'Offline'}
    <b>{fmtClock(at)}</b>
    {sim && <small>{clock.offsetS >= 0 ? '+' : '−'}{fmtDuration(clock.offsetS)}{clock.paused ? ' · paused' : ` · ×${clock.rate}`}</small>}
  </span>
}

export function TopBar() {
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const panels = useApp(s => s.panels)
  const unacked = alerts.filter(a => !a.acknowledged)
  const critical = unacked.filter(a => a.severity === 'critical').length
  return <header className="topbar">
    <div className="brand">
      <span className="wordmark"><i />TrossOps</span>
      <RoleMenu />
    </div>
    <ModeTabs />
    <div className="top-actions">
      <Search />
      <ClockChip />
      <button className="icon-button" aria-pressed={panels.feed} title="Alerts and reports (A)" onClick={() => actions.togglePanel('feed')}>
        <Icon.bell />{unacked.length > 0 && <span className={`badge ${critical ? '' : 'warning'}`}>{unacked.length}</span>}
      </button>
    </div>
  </header>
}
