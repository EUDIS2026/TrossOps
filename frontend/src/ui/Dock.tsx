import { Fragment, useEffect, useRef, useState } from 'react'
import type { Alert, InputReport, LayerDef } from '../contracts/types'
import { actions, currentMode, EMPTY, EMPTY_OBJ, layerOn, store, useApp, type Basemap, type Panel } from '../core/store'
import { ago, channelLabel, Fact, fmtTime, onTabKeys, useRuntime } from './context'
import { Icon } from './icons'
import { ToolsDockButton } from './tools/ToolsControl'

/** Dock order = how often an operator needs it: picture, attention, decisions, time, input, provenance, help. */
const DOCK: { panel: Panel; icon: keyof typeof Icon; label: string; key: string; hint: string }[] = [
  { panel: 'layers', icon: 'layers', label: 'Layers', key: 'L', hint: 'What the map shows: layers, base map and analysis' },
  { panel: 'feed', icon: 'bell', label: 'Alerts & reports', key: 'A', hint: 'Alerts raised by the rules and every incoming report' },
  { panel: 'decisions', icon: 'decide', label: 'Decisions', key: 'D', hint: 'Courses of action waiting for a decision' },
  { panel: 'scenario', icon: 'scenario', label: 'Time & scenarios', key: 'S', hint: 'Replay, run ahead in simulation, or start a scenario' },
  { panel: 'report', icon: 'report', label: 'New report', key: 'R', hint: 'Send a report into the picture' },
  { panel: 'sources', icon: 'plug', label: 'Data sources', key: 'I', hint: 'Status of every real feed and what is synthetic' },
  { panel: 'help', icon: 'help', label: 'Help', key: '?', hint: 'Keyboard shortcuts and how to read the map' },
]

const BASEMAP_LABEL: Record<Basemap, string> = { operational: 'Dark', satellite: 'Imagery', offline: 'Offline' }
const NEXT_BASEMAP: Record<Basemap, Basemap> = { operational: 'satellite', satellite: 'offline', offline: 'operational' }

export function Dock() {
  const panels = useApp(s => s.panels)
  const attention = useApp(s => s.snapshot?.layerAttention ?? EMPTY_OBJ)
  const threeD = useApp(s => s.threeD)
  const basemap = useApp(s => s.basemap)
  const critical = Object.values(attention).some(a => a.severity === 'critical')
  return <nav className="dock" aria-label="Tools">
    {DOCK.map(d => { const I = Icon[d.icon]; return <button key={d.panel} className="dock-btn" data-panel={d.panel} aria-pressed={panels[d.panel]} aria-controls={panels[d.panel] ? 'drawer' : undefined} aria-label={d.label} aria-keyshortcuts={d.key}
      data-tip={`${d.label} (${d.key})\n${d.hint}`} onClick={() => actions.togglePanel(d.panel)}>
      <I />{d.panel === 'layers' && critical && <span className="dot critical" />}</button> })}
    <ToolsDockButton />
    <span className="dock-sep" />
    <button className="dock-btn" aria-pressed={threeD} aria-label="3D view" aria-keyshortcuts="3" data-tip={'3D view (3)\nTilt the map and show terrain and 3D models'} onClick={() => actions.toggle3d()}><Icon.cube /></button>
    <button className="dock-btn" aria-label={`Base map: ${BASEMAP_LABEL[basemap]}`} data-tip={`Base map: ${BASEMAP_LABEL[basemap]}\nClick for ${BASEMAP_LABEL[NEXT_BASEMAP[basemap]]}`} onClick={() => actions.setBasemap(NEXT_BASEMAP[basemap])}>
      {basemap === 'satellite' ? <Icon.satellite /> : <Icon.map />}</button>
  </nav>
}

export function Drawer() {
  const panels = useApp(s => s.panels)
  const open = (['layers', 'feed', 'decisions', 'scenario', 'report', 'sources', 'help'] as Panel[]).find(p => panels[p])
  const ref = useRef<HTMLElement>(null)
  // Focus follows the drawer: into it on open (keyboard users land in the panel), back to its dock button on close.
  useEffect(() => {
    if (!open) return
    const prev = document.activeElement as HTMLElement | null
    if (!prev || prev === document.body || prev.closest('.dock')) ref.current?.focus({ preventScroll: true })
    return () => { if (ref.current?.contains(document.activeElement) || document.activeElement === document.body) (document.querySelector(`.dock-btn[data-panel="${open}"]`) as HTMLElement | null)?.focus({ preventScroll: true }) }
  }, [open])
  if (!open) return null
  const d = DOCK.find(x => x.panel === open)
  return <aside className="drawer" id="drawer" role="region" aria-labelledby="drawer-title" ref={ref} tabIndex={-1}>
    <div className="panel-head"><h2 id="drawer-title">{d?.label}</h2><button className="icon-button" title="Close (Esc)" aria-label={`Close ${d?.label}`} onClick={() => actions.setPanel(open, false)}><Icon.close /></button></div>
    <div className="panel-body">
      {open === 'layers' && <LayersPanel />}
      {open === 'feed' && <FeedPanel />}
      {open === 'decisions' && <DecisionsPanel />}
      {open === 'scenario' && <ScenarioPanel />}
      {open === 'report' && <ReportPanel />}
      {open === 'sources' && <SourcesPanel />}
      {open === 'help' && <HelpPanel />}
    </div>
  </aside>
}

// ---- layers -------------------------------------------------------------------------------------------------
function LayersPanel() {
  const views = useApp(s => s.views)
  const state = useApp(s => s)
  const attention = useApp(s => s.snapshot?.layerAttention ?? EMPTY_OBJ)
  const [openGroups, setOpen] = useState<Record<string, boolean>>({})
  const groups = new Map<string, LayerDef[]>()
  for (const l of views?.layers ?? []) groups.set(l.group, [...(groups.get(l.group) ?? []), l])
  const basemaps: Basemap[] = ['operational', 'satellite', 'offline']
  const basemapHint: Record<Basemap, string> = { operational: 'Dark operational map (vector tiles)', satellite: 'Aerial and satellite imagery', offline: 'Bundled outline map; works without internet' }
  const info = state.analysisInfo
  const mode = currentMode(state)
  const overrides = Object.keys(state.layerOverrides).length
  return <>
    <div className="seg-row">
      <div className="seg" role="group" aria-label="Base map">{basemaps.map(b => <button key={b} aria-pressed={state.basemap === b} title={basemapHint[b]} onClick={() => actions.setBasemap(b)}>{BASEMAP_LABEL[b]}</button>)}</div>
      <button className="chip" aria-pressed={state.threeD} title="Tilt the map and show 3D models (3)" onClick={() => actions.toggle3d()}><Icon.cube width={14} height={14} />3D</button>
      <button className="chip" aria-pressed={state.terrain} disabled={state.basemap === 'offline'} title={state.basemap === 'offline' ? 'Terrain needs the Dark or Imagery base map' : 'Show terrain relief'} onClick={() => actions.toggleTerrain()}><Icon.mountain width={14} height={14} />Terrain</button>
    </div>
    {[...groups.entries()].map(([group, layers]) => {
      if (layers[0]?.id.startsWith('analysis.')) return <div key={group} className="lgroup">
        <div className="lgroup-head static"><span>{group}</span><small>one at a time</small></div>
        <div className="radio-list" role="radiogroup" aria-label={group}>
          <button className="radio" role="radio" aria-checked={!layers.some(l => layerOn(state, l.id))} aria-pressed={!layers.some(l => layerOn(state, l.id))} onClick={() => actions.setAnalysis(null)}><i />None</button>
          {layers.map(l => <button key={l.id} className="radio" role="radio" aria-checked={layerOn(state, l.id)} aria-pressed={layerOn(state, l.id)} title={l.description} onClick={() => actions.setAnalysis(l.id)}><i />{l.label}</button>)}
        </div>
        {info && <div className="legend"><div className="legend-row">{info.legend.map(x => <span key={x.label} className="swatch"><i style={{ background: x.color }} />{x.label}</span>)}</div><small>{info.note}</small></div>}
      </div>
      const onCount = layers.filter(l => layerOn(state, l.id)).length
      const isOpen = openGroups[group] ?? false
      const att = layers.map(l => attention[l.id]).filter(Boolean)
      const sev = att.some(a => a.severity === 'critical') ? 'critical' : att.some(a => a.severity === 'warning') ? 'warning' : att.length ? 'advisory' : null
      return <div key={group} className="lgroup">
        <div className="lgroup-head">
          <button className="expander" aria-expanded={isOpen} aria-label={`${isOpen ? 'Collapse' : 'Expand'} ${group}`} onClick={() => setOpen(o => ({ ...o, [group]: !isOpen }))}><Icon.right width={14} height={14} /></button>
          <button className="lgroup-name" aria-expanded={isOpen} title={sev ? `${group}: some layers have alerts not acknowledged` : undefined} onClick={() => setOpen(o => ({ ...o, [group]: !isOpen }))}>{group}{sev && <span className={`dot ${sev}`} />}<small aria-label={`${onCount} of ${layers.length} on`}>{onCount}/{layers.length}</small></button>
          <button className="switch" role="switch" aria-checked={onCount > 0} aria-label={`${onCount ? 'Hide' : 'Show'} all ${group}`} data-on={onCount > 0} title={onCount ? `Hide all ${group}` : `Show all ${group}`} onClick={() => actions.setLayers(layers.map(l => l.id), onCount === 0)} />
        </div>
        {isOpen && <div className="lgroup-body">{layers.map(l => {
          const on = layerOn(state, l.id)
          const a = attention[l.id]
          return <button key={l.id} className="layer-row" role="switch" aria-checked={on} onClick={() => actions.toggleLayer(l.id)} title={l.description}>
            <span className="name">{l.label}{a && <span className={`dot ${a.severity}`} title={`${a.count} alert${a.count === 1 ? '' : 's'} not acknowledged`} />}{l.sourceKinds.includes('public') || l.sourceKinds.includes('observed') ? <em className="real" title="Real public data">real</em> : null}</span>
            <span className="switch" data-on={on} />
          </button>
        })}</div>}
      </div>
    })}
    <div className="layers-foot">
      <small className="quiet">Each mode switches on its own layers. Your changes last until you change mode.</small>
      {overrides > 0 && mode && <button className="btn small" onClick={() => actions.setMode(mode.id)} title={`Back to the layers of ${mode.label}`}>Reset to mode</button>}
    </div>
  </>
}

// ---- alerts and reports -------------------------------------------------------------------------------------
export function AlertRow({ a }: { a: Alert }) {
  const rt = useRuntime()
  const sel = useApp(s => s.selected?.id === a.id)
  const n = a.entityIds.length
  // Row and Ack are sibling buttons: a button may not contain another interactive control.
  return <div className={`item-row ${a.acknowledged ? 'ack' : ''}`}>
    <button className="item" aria-current={sel || undefined} onClick={() => actions.select('alert', a.id)}>
      <span className={`dot ${a.severity}`} title={a.severity} />
      <span><strong>{a.title}</strong><small><span className="sr-only">{a.severity} alert · </span>Rule {a.ruleId}{n ? ` · ${n} linked` : ''}{a.recommendedInterventionId ? ' · decision pending' : ''}{a.acknowledged ? ' · acknowledged' : ''}</small></span>
    </button>
    {!a.acknowledged && <button className="mini" title="Acknowledge: mark as seen" aria-label={`Acknowledge ${a.title}`} onClick={() => void rt?.session.ack(a.id)}>Ack</button>}
  </div>
}

export function InputRow({ i }: { i: InputReport }) {
  const sel = useApp(s => s.selected?.id === i.id)
  const dec = useApp(s => s.snapshot?.deception[i.id])
  return <button className="item" aria-current={sel || undefined} onClick={() => actions.select('input', i.id)}>
    <span className={`dot ${i.severity}`} />
    <span><strong>{i.title}</strong><small>{channelLabel[i.channel] ?? i.channel} · {i.author}{i.sourceKind === 'public' || i.sourceKind === 'observed' ? ' · real feed' : ''}{dec && dec.probability >= 0.5 ? ` · possible deception (${dec.band})` : ''}</small></span>
    <span className="when">{fmtTime(i.effectiveAt)}</span>
  </button>
}

function FeedPanel() {
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const inputs = useApp(s => s.snapshot?.inputs ?? EMPTY)
  const [tab, setTab] = useState<'alerts' | 'feed' | 'public'>('alerts')
  const open = alerts.filter(a => !a.acknowledged)
  return <>
    <div className="seg full" role="tablist" aria-label="Alerts and reports" onKeyDown={onTabKeys}>
      <button role="tab" aria-selected={tab === 'alerts'} tabIndex={tab === 'alerts' ? 0 : -1} title="Raised by the rule engine; the number counts those not yet acknowledged" onClick={() => setTab('alerts')}>Alerts · {open.length}</button>
      <button role="tab" aria-selected={tab === 'feed'} tabIndex={tab === 'feed' ? 0 : -1} title="Every incoming report from every channel, newest first" onClick={() => setTab('feed')}>Reports · {inputs.length}</button>
      <button role="tab" aria-selected={tab === 'public'} tabIndex={tab === 'public' ? 0 : -1} title="Real public information: crisis news, police events, space weather" onClick={() => setTab('public')}>Public info</button></div>
    {tab === 'public' ? <PublicInfo /> : <div className="list">
      {tab === 'alerts' ? (alerts.length ? alerts.map(a => <AlertRow key={a.id} a={a} />) : <div className="quiet empty">No alerts. The rules raise one when a report, track or unit needs attention.</div>)
        : inputs.length ? [...inputs].reverse().map(i => <InputRow key={i.id} i={i} />) : <div className="quiet empty">No reports yet. Use New report (R) or run a scenario (S) to add one.</div>}
    </div>}
  </>
}

/** Real public information: Krisinformation news and VMA, notable police events, space weather. */
function PublicInfo() {
  const [data, setData] = useState<{ crisis: Record<string, unknown>[]; vma: number; police: Record<string, unknown>[]; kp: Record<string, unknown> | null } | null>(null)
  useEffect(() => {
    let alive = true
    void import('../core/api').then(async ({ api }) => {
      const [c, p, k] = await Promise.allSettled([api.crisis(), api.police(), api.space()])
      if (!alive) return
      const crisis = c.status === 'fulfilled' ? c.value.items ?? [] : []
      const kw = (x: Record<string, unknown>) => ((x.keywords as string[] | undefined) ?? []).length
      const police = p.status === 'fulfilled' ? (p.value.items ?? []).slice().sort((a, b) => kw(b) - kw(a) || String(b.datetime).localeCompare(String(a.datetime))).slice(0, 12) : []
      setData({ crisis, vma: crisis.filter(x => x.kind === 'vma').length, police, kp: k.status === 'fulfilled' ? (k.value as unknown as Record<string, unknown>) : null })
    })
    return () => { alive = false }
  }, [])
  if (!data) return <div className="quiet">Loading public sources…</div>
  return <>
    <div className="section"><h4>Krisinformation <span title="VMA: Viktigt meddelande till allmänheten, the national public warning">{data.vma ? `${data.vma} active public warning${data.vma === 1 ? '' : 's'} (VMA)` : 'no active public warning (VMA)'}</span></h4><div className="list">
      {data.crisis.map(x => <div key={String(x.id)} className="note"><b>{String(x.headline)}</b><br /><small>{String(x.preamble ?? '').slice(0, 220)}</small><br /><small className="quiet">{ago(x.published as string)} · {((x.areas as string[] | undefined) ?? []).join(', ')}</small></div>)}
      {!data.crisis.length && <div className="quiet">No national crisis news in the last three days.</div>}
    </div></div>
    <div className="section"><h4>Police events <span>polisen.se</span></h4><div className="list">
      {data.police.map(x => <button key={String(x.id)} className="item" onClick={() => actions.select('police', String(x.id), { lng: x.lng, lat: x.lat, name: x.name, type: x.type })}>
        <span className={`dot ${((x.keywords as string[] | undefined) ?? []).length ? 'warning' : 'info'}`} /><span><strong>{String(x.name)}</strong><small>{String(x.summary ?? '')}</small></span></button>)}
      {!data.police.length && <div className="quiet">No police events available right now.</div>}
    </div></div>
    {data.kp && <div className="section"><h4>Space weather <span>NOAA SWPC</span></h4>
      <div className="facts"><Fact k="Geomagnetic Kp now" v={String(data.kp.kp ?? '—')} /><Fact k="Kp max, last 24 h" v={String(data.kp.max24h ?? '—')} /></div><small className="quiet">{String(data.kp.impact ?? data.kp.note ?? '')}</small></div>}
  </>
}

// ---- decisions ---------------------------------------------------------------------------------------------
function DecisionsPanel() {
  const snap = useApp(s => s.snapshot)
  const plan = useApp(s => s.plan)
  const busy = useApp(s => s.busy)
  const rt = useRuntime()
  const ivs = snap?.interventions ?? []
  const proposed = ivs.filter(i => i.status === 'proposed')
  const active = ivs.filter(i => i.status !== 'proposed')
  const fresh = plan && snap && plan.worldRevision === snap.worldRevision
  return <>
    <div className="actions"><button className="btn primary" disabled={busy || !proposed.length} title="Assign units to every waiting course of action at once, so no unit is given two tasks (deterministic optimiser)" onClick={() => void rt?.session.optimise()}><Icon.sparkle width={14} height={14} /> Optimise all</button>
      <span className="quiet">{proposed.length} waiting · {active.length} in progress</span></div>
    {plan && <div className="section">
      <h4>Optimised assignment <span title={fresh ? 'Lower is better' : 'The picture changed since this was computed'}>{fresh ? `objective ${plan.objective?.toFixed(2)}` : 'out of date: optimise again'}</span></h4>
      {plan.plan.map(row => { const iv = ivs.find(i => i.id === row.interventionId); const opt = iv?.options.find(o => o.id === row.optionId)
        return <div key={row.interventionId} className="plan-row"><span>{iv?.title ?? row.interventionId}<br /><small>{row.unassigned ? 'left unassigned' : opt?.title}</small></span>
          {fresh && row.optionId && <button className="mini" disabled={busy} onClick={() => void rt?.session.commit(row.interventionId, row.optionId!)}>Commit</button>}</div> })}
      {plan.alternatives.map(a => <div key={a.name} className="plan-row"><span>{a.name}<br /><small>alternative rule</small></span><b>{a.objective.toFixed(2)}</b></div>)}
      <small className="quiet">{plan.explanation}</small>
    </div>}
    {active.length > 0 && <div className="section"><h4>In progress <span>{active.length}</span></h4><div className="list">
      {active.map(iv => <button key={iv.id} className="item" onClick={() => actions.select('intervention', iv.id)}><span className="dot info" /><span><strong>{iv.title}</strong><small>{iv.status.replace('_', ' ')} · {Math.round(iv.progress * 100)} %</small><div className="progress"><i style={{ width: `${iv.progress * 100}%` }} /></div></span></button>)}
    </div></div>}
    <div className="section"><h4>Waiting for a decision <span>{proposed.length}</span></h4><div className="list">
      {proposed.map(iv => { const a = snap?.alerts.find(x => x.id === iv.alertId); const best = iv.options.find(o => o.id === iv.recommendedOptionId)
        return <button key={iv.id} className="item" onClick={() => actions.select('intervention', iv.id)}><span className={`dot ${a?.severity ?? 'info'}`} /><span><strong>{iv.title}</strong><small>{best ? `${best.title} · ${Math.round(best.successLikelihood * 100)} % · ${best.etaMin === null ? '—' : Math.round(best.etaMin) + ' min'}` : 'no feasible option'}</small></span><span className="when" title={`${iv.options.length} option${iv.options.length === 1 ? '' : 's'}`}>{iv.options.length} opt.</span></button> })}
      {!proposed.length && <div className="quiet empty">No decisions waiting. When an alert needs a response, the rules propose a course of action here with ranked options.</div>}
    </div></div>
  </>
}

// ---- scenario / simulation ------------------------------------------------------------------------------------
const PRESETS: { id: string; label: string; desc: string }[] = [
  { id: 'drone_swarm', label: 'Drone swarm over an airbase', desc: 'Six small UAS orbit Airbase Norr at night; guard reports follow.' },
  { id: 'cable_cut', label: 'Undersea cable damage', desc: 'Operator reports loss of the Gotland–mainland link; a vessel was loitering nearby.' },
  { id: 'air_raid', label: 'Inbound air raid from the south-east', desc: 'Four fast unknown tracks over the Baltic heading for Skåne and Blekinge.' },
  { id: 'gnss_jamming', label: 'GNSS jamming in the southern Baltic', desc: 'Aircraft and ships report position errors; navigation advisory issued.' },
  { id: 'power_outage', label: 'Regional power outage', desc: 'Grid Node Mälardalen trips; command and comms sites on backup power.' },
  { id: 'disinformation', label: 'Disinformation wave', desc: 'Coordinated posts claim an attack on a port with no sensor corroboration.' },
]

function ScenarioPanel() {
  const rt = useRuntime()
  const clock = useApp(s => s.clock)
  const busy = useApp(s => s.busy)
  return <>
    <div className="section"><h4>Clock <span>{clock.mode === 'live' ? 'live' : clock.offsetS > 5 ? 'simulation' : 'replay'}</span></h4>
      <div className="seg full" role="group" aria-label="Clock speed">
        <button aria-pressed={clock.mode === 'live'} title="Back to now, with real feeds" onClick={() => rt?.session.goLive()}><Icon.live width={14} height={14} />Live</button>
        {[1, 10, 60, 300].map(r => <button key={r} aria-pressed={clock.mode === 'sim' && !clock.paused && clock.rate === r} title={r === 1 ? 'Run in real time from here' : `Run ${r} times faster than real time`} onClick={() => rt?.session.setRate(r)}>×{r}</button>)}
      </div>
      <div className="actions" role="group" aria-label="Jump in time">
        <button className="btn" title="Replay: 30 minutes back" onClick={() => rt?.session.jump(Math.max(0, rt.session.clock.now() - 1800))}>−30 min</button>
        <button className="btn" title="Simulate: 30 minutes ahead" onClick={() => rt?.session.jump(rt.session.clock.now() + 1800)}>+30 min</button>
        <button className="btn" title="Simulate: 2 hours ahead" onClick={() => rt?.session.jump(rt.session.clock.now() + 3600 * 2)}>+2 h</button>
      </div>
      <small className="quiet">Replay goes back, simulation runs ahead; both use the same motion model and rules as live. Ahead of now you see declared plans and predictions; real feeds appear only live. Space pauses.</small>
    </div>
    <div className="section"><h4>Run a scenario</h4><div className="list">
      {PRESETS.map(p => <button key={p.id} className="item" disabled={busy || clock.mode !== 'live'} onClick={() => void rt?.session.inject(p.id)}><span className="dot warning" /><span><strong>{p.label}</strong><small>{p.desc}</small></span><Icon.play width={14} height={14} /></button>)}
    </div><small className="quiet">{clock.mode !== 'live' ? 'Return to Live to run a scenario. ' : ''}A scenario adds synthetic reports and tracks; the rules react to them exactly as to real ones.</small></div>
  </>
}

// ---- report submission ------------------------------------------------------------------------------------------
function ReportPanel() {
  const views = useApp(s => s.views)
  const busy = useApp(s => s.busy)
  const rt = useRuntime()
  const [form, setForm] = useState({ channel: 'field_report', authorLevel: 'soldier', author: '', title: '', text: '', entityRefs: '' })
  const levels = ['soldier', 'platoon', 'company', 'battalion', 'brigade', 'regional', 'joint', 'national', 'civil_authority', 'operator', 'sensor', 'media', 'allied', 'head_of_state']
  const submit = async (e: React.FormEvent) => {
    e.preventDefault()
    await rt?.session.submitInput({ ...form, entityRefs: form.entityRefs.split(/[\s,]+/).filter(Boolean) })
    actions.toast(`Report "${form.title}" submitted; the rules have re-run. See Alerts & reports (A).`)
    setForm(f => ({ ...f, title: '', text: '', entityRefs: '' }))
  }
  return <form className="form" onSubmit={e => void submit(e)}>
    <div className="row">
      <label>Channel<select value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })}>{(views?.channels ?? []).map(c => <option key={c.id} value={c.id}>{channelLabel[c.id] ?? c.label}</option>)}</select></label>
      <label>Reported by<select value={form.authorLevel} title="Who is reporting, from a single soldier to national level, a sensor or a civil authority"onChange={e => setForm({ ...form, authorLevel: e.target.value })}>{levels.map(l => <option key={l} value={l}>{l.replace(/_/g, ' ')}</option>)}</select></label>
    </div>
    <label>Author<input required value={form.author} placeholder="Name or call sign" onChange={e => setForm({ ...form, author: e.target.value })} /></label>
    <label>Title<input required value={form.title} placeholder="One line: what and where" onChange={e => setForm({ ...form, title: e.target.value })} /></label>
    <label>Text<textarea required value={form.text} placeholder="What was observed. Name units and places (Visby, Umeå); the rules link them to the map." onChange={e => setForm({ ...form, text: e.target.value })} /></label>
    <label>Related unit or site ids (optional)<input value={form.entityRefs} placeholder="airbase-syd, coy-n1a-03" onChange={e => setForm({ ...form, entityRefs: e.target.value })} /></label>
    <button className="btn primary" disabled={busy}>Submit report</button>
    <small className="quiet">Severity, places and tags are extracted by fixed rules; nothing is guessed by a model.</small>
  </form>
}

// ---- sources ---------------------------------------------------------------------------------------------------
function SourcesPanel() {
  const sources = useApp(s => s.sources)
  const notice = useApp(s => s.snapshot?.dataNotice)
  const [probing, setProbing] = useState(false)
  const probe = async () => { setProbing(true); try { const { api } = await import('../core/api'); store.set({ sources: (await api.sources(true)).sources }) } finally { setProbing(false) } }
  return <>
    <div className="actions"><button className="btn" disabled={probing} onClick={() => void probe()}>{probing ? 'Checking…' : 'Check all sources now'}</button></div>
    <small className="quiet">Status: <b>working</b> data arriving · <b>partial</b> some data or delayed · <b>adapter-only</b> built, needs an access key · <b>blocked</b> not reachable or turned off.</small>
    <div className="list">{sources.map(s => <div key={s.id} className="source">
      <div><span className={`status ${s.status}`}>{s.status}</span><strong>{s.label}</strong></div>
      <small>{s.count != null ? `${s.count} items · ` : ''}{s.lastOkAt ? `updated ${ago(s.lastOkAt)}` : 'not fetched yet'}{s.stale ? ' · out of date' : ''}</small>
      {s.lastError && <small className="err">{s.lastError}</small>}
      {s.note && <small>{s.note}</small>}
      <small className="lic">{s.licence}</small>
    </div>)}
      {!sources.length && <div className="quiet">Loading source status…</div>}
    </div>
    <div className="section"><h4>What is synthetic</h4><small className="quiet">{notice}</small></div>
  </>
}

function HelpPanel() {
  const panels: [string, string][] = DOCK.map(d => [d.key, d.label])
  const map: [string, string][] = [['/', 'Search (↑ ↓ to choose, Enter to go)'], ['3', '3D view on / off'], ['F', 'Follow the selected unit'], ['Home', 'Back to the mode’s view'], ['Space', 'Pause / resume the clock'], ['Esc', 'Cancel tool or route, close panel, then clear selection']]
  const tools: [string, string][] = [['T', 'Map tools menu'], ['M', 'Measure distance and bearing'], ['V', 'Line of sight over real terrain'], ['C', 'Range ring'], ['E', 'Ground elevation under the cursor']]
  return <>
    <div className="section first"><h4>Getting started</h4><ol className="steps">
      <li>Pick a <b>role</b> (top left); its <b>modes</b> (top centre) each set the map and layers for one question.</li>
      <li>Click any symbol, alert or report to open it on the right; <b>Why</b> tabs show the evidence behind it.</li>
      <li>Alerts come from numbered rules; those that need a response wait in <b>Decisions</b>.</li>
      <li>Drag the timeline to replay the past or simulate ahead; <b>Live</b> returns to now.</li>
    </ol></div>
    <div className="section"><h4>Panels</h4><div className="help">{panels.map(([k, v]) => <Fragment key={k}><kbd>{k}</kbd><span>{v}</span></Fragment>)}</div></div>
    <div className="section"><h4>Map</h4><div className="help">{map.map(([k, v]) => <Fragment key={k}><kbd>{k}</kbd><span>{v}</span></Fragment>)}</div></div>
    <div className="section"><h4>Map tools</h4><div className="help">{tools.map(([k, v]) => <Fragment key={k}><kbd>{k}</kbd><span>{v}</span></Fragment>)}</div></div>
    <div className="section"><h4>Reading the map</h4><small className="quiet">Symbols follow NATO APP-6: cyan rectangle own forces, yellow quatrefoil unknown, red diamond suspect, purple civil. A formation is one symbol until its units spread apart on screen, then opens as you zoom; the number after a designation counts its platforms. A bar under a symbol shows condition (amber degraded, red unavailable). Real air and ship traffic is drawn as plain silhouettes; the tag <em className="real">real</em> marks public data, everything else is synthetic.</small></div>
  </>
}
