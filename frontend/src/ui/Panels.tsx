import { Fragment, useEffect, useMemo, useRef, useState } from 'react'
import { actions, EMPTY, useApp } from '../core/store'
import { channelLabel, fmtClock, fmtDuration, kindLabel, useRuntime } from './context'
import { Icon } from './icons'
import { AlertRow, InputRow } from './Inspector'

export function AlertsPanel() {
  const open = useApp(s => s.panels.alerts)
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const inputs = useApp(s => s.snapshot?.inputs ?? EMPTY)
  const sel = useApp(s => s.selected)
  const [tab, setTab] = useState<'alerts' | 'feed'>('alerts')
  return <aside className={`panel floating ${open ? '' : 'hidden'}`} aria-label="Alerts" aria-hidden={!open}>
    <div className="panel-head">
      <div className="modes" role="tablist"><button role="tab" aria-selected={tab === 'alerts'} onClick={() => setTab('alerts')}>Alerts · {alerts.filter(a => !a.acknowledged).length}</button><button role="tab" aria-selected={tab === 'feed'} onClick={() => setTab('feed')}>Input feed · {inputs.length}</button></div>
      <button className="icon-button" title="Close" onClick={() => actions.setPanel('alerts', false)}><Icon.close /></button>
    </div>
    <div className="panel-body"><div className="list">
      {tab === 'alerts' ? (alerts.length ? alerts.map(a => <AlertRow key={a.id} a={a} selected={sel?.id === a.id} />) : <div className="quiet">No alerts. The rule engine has nothing that needs attention.</div>)
        : [...inputs].reverse().map(i => <InputRow key={i.id} i={i} selected={sel?.id === i.id} />)}
    </div></div>
  </aside>
}

export function ReportComposer() {
  const open = useApp(s => s.panels.inputs)
  const views = useApp(s => s.views)
  const busy = useApp(s => s.busy)
  const rt = useRuntime()
  const [form, setForm] = useState({ channel: 'field_report', authorLevel: 'soldier', author: '', title: '', text: '', entityRefs: '' })
  const [done, setDone] = useState<string | null>(null)
  const levels = ['soldier', 'platoon', 'company', 'battalion', 'brigade', 'regional', 'joint', 'national', 'civil_authority', 'operator', 'sensor', 'media', 'allied', 'head_of_state']
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    await rt?.session.submitInput({ ...form, entityRefs: form.entityRefs.split(/[\s,]+/).filter(Boolean) })
    setDone(`Report "${form.title}" is in the picture. Rules re-evaluated.`)
    setForm(f => ({ ...f, title: '', text: '', entityRefs: '' }))
  }
  return <aside className={`panel floating ${open ? '' : 'hidden'}`} aria-label="Submit a report" aria-hidden={!open}>
    <div className="panel-head"><h2>Submit a report</h2><button className="icon-button" title="Close" onClick={() => actions.setPanel('inputs', false)}><Icon.close /></button></div>
    <div className="panel-body">
      <form className="form" onSubmit={e => void submit(e)}>
        <div className="row">
          <label>Channel<select value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })}>{(views?.channels ?? []).map(c => <option key={c.id} value={c.id}>{channelLabel[c.id] ?? c.label}</option>)}</select></label>
          <label>Author level<select value={form.authorLevel} onChange={e => setForm({ ...form, authorLevel: e.target.value })}>{levels.map(l => <option key={l} value={l}>{l.replace('_', ' ')}</option>)}</select></label>
        </div>
        <label>Author<input required value={form.author} placeholder="Who is reporting" onChange={e => setForm({ ...form, author: e.target.value })} /></label>
        <label>Title<input required value={form.title} placeholder="One line" onChange={e => setForm({ ...form, title: e.target.value })} /></label>
        <label>Text<textarea required value={form.text} placeholder="What was observed. Mention unit ids (gv-07) and places (Umeå) and the rules will link them." onChange={e => setForm({ ...form, text: e.target.value })} /></label>
        <label>Entity ids (optional)<input value={form.entityRefs} placeholder="gv-07, depot-mitt" onChange={e => setForm({ ...form, entityRefs: e.target.value })} /></label>
        <div className="actions" style={{ padding: 0 }}><button className="btn primary" disabled={busy}>Send to the picture</button><small className="quiet">Severity, places and tags are extracted by rules; nothing is guessed by a model.</small></div>
        {done && <div className="note">{done}</div>}
      </form>
    </div>
  </aside>
}

export function Timeline() {
  const snap = useApp(s => s.snapshot)
  const time = useApp(s => s.time)
  const [drag, setDrag] = useState<number | null>(null)
  const timer = useRef(0)
  const nowS = snap?.nowS ?? 0
  const atS = time.mode === 'replay' ? time.atS : nowS
  const value = drag ?? atS
  const marks = useMemo(() => (snap?.inputs ?? []).filter(i => i.severity === 'critical' || i.severity === 'warning').map(i => ({ id: i.id, s: (new Date(i.effectiveAt).getTime() - new Date(snap!.atTime).getTime()) / 1000 * (snap!.speed || 1) + snap!.atS, sev: i.severity })), [snap])
  const onChange = (v: number) => {
    setDrag(v)
    window.clearTimeout(timer.current)
    timer.current = window.setTimeout(() => { setDrag(null); if (v >= nowS - 2) actions.goLive(); else actions.replayAt(v) }, 220)
  }
  if (!snap) return null
  return <div className="timeline" aria-label="Time">
    <div className="clock"><span>{fmtClock(snap.atTime)}</span><small>{time.mode === 'replay' ? `replay · ${fmtDuration(nowS - atS)} ago` : `live · T+${fmtDuration(nowS)}`}</small></div>
    <div className="scrub">
      <input type="range" min={0} max={Math.max(1, Math.ceil(nowS))} step={1} value={Math.min(value, nowS)} aria-label="Scenario time" style={{ ['--fill' as string]: `${(Math.min(value, nowS) / Math.max(1, nowS)) * 100}%` }} onChange={e => onChange(Number(e.target.value))} />
      <div className="marks">{marks.map(m => <i key={m.id} className={m.sev} style={{ left: `${(m.s / Math.max(1, nowS)) * 100}%` }} title={m.id} />)}</div>
    </div>
    <div className="controls">
      {time.mode === 'replay' ? <button className="btn small primary" onClick={() => actions.goLive()}><Icon.live width={14} height={14} /> Return to live</button> : <span className="status-chip"><span className="pip" />×{snap.speed}</span>}
    </div>
  </div>
}

export function SearchPalette() {
  const open = useApp(s => s.panels.search)
  const entities = useApp(s => s.snapshot?.entities ?? EMPTY)
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  const input = useRef<HTMLInputElement>(null)
  useEffect(() => { if (open) { setQ(''); setCursor(0); setTimeout(() => input.current?.focus(), 30) } }, [open])
  const results = useMemo(() => {
    const t = q.trim().toLowerCase()
    if (!t) return entities.filter(e => e.affiliation === 'unknown' || e.condition !== 'normal').slice(0, 8)
    return entities.filter(e => e.label.toLowerCase().includes(t) || e.id.includes(t) || e.kind.includes(t) || (e.unit ?? '').toLowerCase().includes(t)).slice(0, 10)
  }, [q, entities])
  const pick = (id: string) => { actions.select('entity', id); actions.setPanel('search', false) }
  return <aside className={`panel floating ${open ? '' : 'hidden'}`} aria-label="Search" aria-hidden={!open}>
    <div className="panel-body" style={{ paddingTop: 12 }}>
      {open && <input ref={input} autoFocus className="search-input" placeholder="Find a unit, site, track or formation" value={q} onChange={e => { setQ(e.target.value); setCursor(0) }}
        onKeyDown={e => { if (e.key === 'ArrowDown') { e.preventDefault(); setCursor(c => Math.min(c + 1, results.length - 1)) } if (e.key === 'ArrowUp') { e.preventDefault(); setCursor(c => Math.max(c - 1, 0)) } if (e.key === 'Enter' && results[cursor]) pick(results[cursor].id); if (e.key === 'Escape') actions.setPanel('search', false) }} />}
      <div className="results" role="listbox">
        {results.map((e, i) => <button key={e.id} role="option" aria-selected={i === cursor} className="item" onClick={() => pick(e.id)}><span className={`dot ${e.condition === 'unavailable' ? 'critical' : e.condition === 'degraded' ? 'warning' : e.affiliation === 'unknown' ? 'advisory' : 'info'}`} /><span><strong>{e.label}</strong><small>{kindLabel[e.kind]} · {e.unit ?? e.id} · {e.condition}</small></span><span className="when">{e.id}</span></button>)}
        {!results.length && <div className="quiet">Nothing matches in the current role's scope.</div>}
      </div>
    </div>
  </aside>
}

export function HelpPanel() {
  const open = useApp(s => s.panels.help)
  const rows: [string, string][] = [['/', 'Search'], ['L', 'Layers'], ['A', 'Alerts and input feed'], ['D', 'Decisions'], ['R', 'Submit a report'], ['3', 'Toggle 3D'], ['F', 'Follow the selected unit'], ['Esc', 'Deselect / close'], ['Home', 'Reset the view for this mode'], ['?', 'This list']]
  return <aside className={`panel floating ${open ? '' : 'hidden'}`} aria-label="Shortcuts" aria-hidden={!open}>
    <div className="panel-head"><h2>Shortcuts</h2><button className="icon-button" title="Close" onClick={() => actions.setPanel('help', false)}><Icon.close /></button></div>
    <div className="panel-body"><div className="help">{rows.map(([k, v]) => <Fragment key={k}><kbd>{k}</kbd><span>{v}</span></Fragment>)}</div>
      <div className="note">Click a cluster to open it, a unit to inspect it, an attention cell to see which rules raised it, and an area to see its blockers. Drag the time slider to replay; return to live at any point.</div>
    </div>
  </aside>
}

export function ErrorToast() {
  const error = useApp(s => s.error)
  if (!error) return null
  return <div className="toast" role="alert"><span>{error}</span><button className="btn small" onClick={() => actions.setError(null)}>Dismiss</button></div>
}

export function DataNotice() {
  const notice = useApp(s => s.snapshot?.dataNotice)
  const basemap = useApp(s => s.basemapStatus)
  if (!notice) return null
  return <div className="notice">{notice}{basemap === 'offline' ? ' Basemap: offline geography.' : ''}</div>
}
