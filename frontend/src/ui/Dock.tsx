import { Fragment, useEffect, useState } from 'react'
import type { Alert, InputReport, LayerDef } from '../contracts/types'
import { actions, EMPTY, EMPTY_OBJ, layerOn, store, useApp, type Basemap, type Panel } from '../core/store'
import { ago, channelLabel, Fact, fmtTime, useRuntime } from './context'
import { Icon } from './icons'

const DOCK: { panel: Panel; icon: keyof typeof Icon; label: string; key: string }[] = [
  { panel: 'layers', icon: 'layers', label: 'Layers', key: 'L' },
  { panel: 'feed', icon: 'bell', label: 'Alerts & reports', key: 'A' },
  { panel: 'decisions', icon: 'decide', label: 'Decisions', key: 'D' },
  { panel: 'scenario', icon: 'scenario', label: 'Simulate', key: 'S' },
  { panel: 'report', icon: 'report', label: 'Submit a report', key: 'R' },
  { panel: 'sources', icon: 'plug', label: 'Data sources', key: 'I' },
  { panel: 'help', icon: 'help', label: 'Shortcuts', key: '?' },
]

export function Dock() {
  const panels = useApp(s => s.panels)
  const attention = useApp(s => s.snapshot?.layerAttention ?? EMPTY_OBJ)
  const threeD = useApp(s => s.threeD)
  const basemap = useApp(s => s.basemap)
  const critical = Object.values(attention).some(a => a.severity === 'critical')
  return <nav className="dock" aria-label="Tools">
    {DOCK.map(d => { const I = Icon[d.icon]; return <button key={d.panel} className="dock-btn" aria-pressed={panels[d.panel]} title={`${d.label} (${d.key})`} onClick={() => actions.togglePanel(d.panel)}>
      <I />{d.panel === 'layers' && critical && <span className="dot critical" />}</button> })}
    <span className="dock-sep" />
    <button className="dock-btn" aria-pressed={threeD} title="3D (3)" onClick={() => actions.toggle3d()}><Icon.cube /></button>
    <button className="dock-btn" title={`Basemap: ${basemap}`} onClick={() => actions.setBasemap(({ operational: 'satellite', satellite: 'offline', offline: 'operational' } as Record<Basemap, Basemap>)[basemap])}>
      {basemap === 'satellite' ? <Icon.satellite /> : <Icon.map />}</button>
  </nav>
}

export function Drawer() {
  const panels = useApp(s => s.panels)
  const open = (['layers', 'feed', 'decisions', 'scenario', 'report', 'sources', 'help'] as Panel[]).find(p => panels[p])
  if (!open) return null
  const title = DOCK.find(d => d.panel === open)?.label
  return <aside className="drawer" aria-label={title}>
    <div className="panel-head"><h2>{title}</h2><button className="icon-button" title="Close (Esc)" onClick={() => actions.setPanel(open, false)}><Icon.close /></button></div>
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
  const basemaps: { id: Basemap; label: string }[] = [{ id: 'operational', label: 'Dark' }, { id: 'satellite', label: 'Imagery' }, { id: 'offline', label: 'Offline' }]
  const info = state.analysisInfo
  return <>
    <div className="seg-row">
      <div className="seg">{basemaps.map(b => <button key={b.id} aria-pressed={state.basemap === b.id} onClick={() => actions.setBasemap(b.id)}>{b.label}</button>)}</div>
      <button className="chip" aria-pressed={state.threeD} onClick={() => actions.toggle3d()}><Icon.cube width={14} height={14} />3D</button>
      <button className="chip" aria-pressed={state.terrain} disabled={state.basemap === 'offline'} onClick={() => actions.toggleTerrain()}><Icon.mountain width={14} height={14} />Terrain</button>
    </div>
    {[...groups.entries()].map(([group, layers]) => {
      if (group === 'Analysis') return <div key={group} className="lgroup">
        <div className="lgroup-head static"><span>Analysis surface</span></div>
        <div className="radio-list">
          <button className="radio" aria-pressed={!layers.some(l => layerOn(state, l.id))} onClick={() => actions.setAnalysis(null)}><i />None</button>
          {layers.map(l => <button key={l.id} className="radio" aria-pressed={layerOn(state, l.id)} title={l.description} onClick={() => actions.setAnalysis(l.id)}><i />{l.label}</button>)}
        </div>
        {info && <div className="legend"><div className="legend-row">{info.legend.map(x => <span key={x.label} className="swatch"><i style={{ background: x.color }} />{x.label}</span>)}</div><small>{info.note} Unit: {info.unit}.</small></div>}
      </div>
      const onCount = layers.filter(l => layerOn(state, l.id)).length
      const isOpen = openGroups[group] ?? false
      const att = layers.map(l => attention[l.id]).filter(Boolean)
      const sev = att.some(a => a.severity === 'critical') ? 'critical' : att.some(a => a.severity === 'warning') ? 'warning' : att.length ? 'advisory' : null
      return <div key={group} className="lgroup">
        <div className="lgroup-head">
          <button className="expander" aria-expanded={isOpen} onClick={() => setOpen(o => ({ ...o, [group]: !isOpen }))}><Icon.right width={14} height={14} /></button>
          <button className="lgroup-name" onClick={() => setOpen(o => ({ ...o, [group]: !isOpen }))}>{group}{sev && <span className={`dot ${sev}`} />}<small>{onCount}/{layers.length}</small></button>
          <button className="switch" role="switch" aria-checked={onCount > 0} data-on={onCount > 0} title={onCount ? 'Hide all' : 'Show all'} onClick={() => actions.setLayers(layers.map(l => l.id), onCount === 0)} />
        </div>
        {isOpen && <div className="lgroup-body">{layers.map(l => {
          const on = layerOn(state, l.id)
          const a = attention[l.id]
          return <button key={l.id} className="layer-row" role="switch" aria-checked={on} onClick={() => actions.toggleLayer(l.id)} title={l.description}>
            <span className="name">{l.label}{a && <span className={`dot ${a.severity}`} title={`${a.count} unacknowledged alerts`} />}{l.sourceKinds.includes('public') || l.sourceKinds.includes('observed') ? <em className="real">real</em> : null}</span>
            <span className="switch" data-on={on} />
          </button>
        })}</div>}
      </div>
    })}
    <small className="quiet">Roles and modes set sensible defaults; your switches override them until you change mode.</small>
  </>
}

// ---- alerts and reports -------------------------------------------------------------------------------------
export function AlertRow({ a }: { a: Alert }) {
  const rt = useRuntime()
  const sel = useApp(s => s.selected?.id === a.id)
  return <button className={`item ${a.acknowledged ? 'ack' : ''}`} aria-selected={sel} onClick={() => actions.select('alert', a.id)}>
    <span className={`dot ${a.severity}`} />
    <span><strong>{a.title}</strong><small>{a.ruleId} · {a.entityIds.length} entities{a.recommendedInterventionId ? ' · action proposed' : ''}</small></span>
    {!a.acknowledged && <span role="button" tabIndex={0} className="mini" onClick={e => { e.stopPropagation(); void rt?.session.ack(a.id) }}>Ack</span>}
  </button>
}

export function InputRow({ i }: { i: InputReport }) {
  const sel = useApp(s => s.selected?.id === i.id)
  const dec = useApp(s => s.snapshot?.deception[i.id])
  return <button className="item" aria-selected={sel} onClick={() => actions.select('input', i.id)}>
    <span className={`dot ${i.severity}`} />
    <span><strong>{i.title}</strong><small>{channelLabel[i.channel] ?? i.channel} · {i.author}{i.sourceKind === 'public' || i.sourceKind === 'observed' ? ' · real' : ''}{dec && dec.probability >= 0.5 ? ` · ${dec.band} deceptive` : ''}</small></span>
    <span className="when">{fmtTime(i.effectiveAt)}</span>
  </button>
}

function FeedPanel() {
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const inputs = useApp(s => s.snapshot?.inputs ?? EMPTY)
  const [tab, setTab] = useState<'alerts' | 'feed' | 'public'>('alerts')
  const open = alerts.filter(a => !a.acknowledged)
  return <>
    <div className="seg full"><button aria-pressed={tab === 'alerts'} onClick={() => setTab('alerts')}>Alerts · {open.length}</button><button aria-pressed={tab === 'feed'} onClick={() => setTab('feed')}>Reports · {inputs.length}</button>
      <button aria-pressed={tab === 'public'} onClick={() => setTab('public')}>Public</button></div>
    {tab === 'public' ? <PublicInfo /> : <div className="list">
      {tab === 'alerts' ? (alerts.length ? alerts.map(a => <AlertRow key={a.id} a={a} />) : <div className="quiet">Nothing needs attention.</div>)
        : [...inputs].reverse().map(i => <InputRow key={i.id} i={i} />)}
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
    <div className="section"><h4>Krisinformation <span>{data.vma ? `${data.vma} active VMA` : 'no active VMA'}</span></h4><div className="list">
      {data.crisis.map(x => <div key={String(x.id)} className="note"><b>{String(x.headline)}</b><br /><small>{String(x.preamble ?? '').slice(0, 220)}</small><br /><small className="quiet">{ago(x.published as string)} · {((x.areas as string[] | undefined) ?? []).join(', ')}</small></div>)}
      {!data.crisis.length && <div className="quiet">No national crisis news in the last three days.</div>}
    </div></div>
    <div className="section"><h4>Police events <span>polisen.se</span></h4><div className="list">
      {data.police.map(x => <button key={String(x.id)} className="item" onClick={() => actions.select('police', String(x.id), { lng: x.lng, lat: x.lat, name: x.name, type: x.type })}>
        <span className={`dot ${((x.keywords as string[] | undefined) ?? []).length ? 'warning' : 'info'}`} /><span><strong>{String(x.name)}</strong><small>{String(x.summary ?? '')}</small></span></button>)}
    </div></div>
    {data.kp && <div className="section"><h4>Space weather <span>NOAA SWPC</span></h4>
      <div className="facts"><Fact k="Kp now" v={String(data.kp.kp ?? '—')} /><Fact k="Kp max 24 h" v={String(data.kp.max24h ?? '—')} /></div><small className="quiet">{String(data.kp.impact ?? data.kp.note ?? '')}</small></div>}
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
    <div className="actions"><button className="btn primary" disabled={busy || !proposed.length} onClick={() => void rt?.session.optimise()}><Icon.sparkle width={14} height={14} /> Optimise all</button>
      <span className="quiet">{proposed.length} proposed · {active.length} active</span></div>
    {plan && <div className="section">
      <h4>Optimised assignment <span>{fresh ? `objective ${plan.objective?.toFixed(2)}` : 'stale'}</span></h4>
      {plan.plan.map(row => { const iv = ivs.find(i => i.id === row.interventionId); const opt = iv?.options.find(o => o.id === row.optionId)
        return <div key={row.interventionId} className="plan-row"><span>{iv?.title ?? row.interventionId}<br /><small>{row.unassigned ? 'left unassigned' : opt?.title}</small></span>
          {fresh && row.optionId && <button className="mini" disabled={busy} onClick={() => void rt?.session.commit(row.interventionId, row.optionId!)}>Commit</button>}</div> })}
      {plan.alternatives.map(a => <div key={a.name} className="plan-row"><span>{a.name}<br /><small>alternative rule</small></span><b>{a.objective.toFixed(2)}</b></div>)}
      <small className="quiet">{plan.explanation}</small>
    </div>}
    {active.length > 0 && <div className="section"><h4>In progress <span>{active.length}</span></h4><div className="list">
      {active.map(iv => <button key={iv.id} className="item" onClick={() => actions.select('intervention', iv.id)}><span className="dot info" /><span><strong>{iv.title}</strong><small>{iv.status.replace('_', ' ')} · {Math.round(iv.progress * 100)} %</small><div className="progress"><i style={{ width: `${iv.progress * 100}%` }} /></div></span></button>)}
    </div></div>}
    <div className="section"><h4>Proposed <span>{proposed.length}</span></h4><div className="list">
      {proposed.map(iv => { const a = snap?.alerts.find(x => x.id === iv.alertId); const best = iv.options.find(o => o.id === iv.recommendedOptionId)
        return <button key={iv.id} className="item" onClick={() => actions.select('intervention', iv.id)}><span className={`dot ${a?.severity ?? 'info'}`} /><span><strong>{iv.title}</strong><small>{best ? `${best.title} · ${Math.round(best.successLikelihood * 100)} % · ${best.etaMin === null ? '—' : Math.round(best.etaMin) + ' min'}` : 'no feasible option'}</small></span><span className="when">{iv.options.length}</span></button> })}
      {!proposed.length && <div className="quiet">No open interventions.</div>}
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
    <div className="section"><h4>Time</h4>
      <div className="seg full">
        <button aria-pressed={clock.mode === 'live'} onClick={() => rt?.session.goLive()}><Icon.live width={14} height={14} />Live</button>
        {[1, 10, 60, 300].map(r => <button key={r} aria-pressed={clock.mode === 'sim' && !clock.paused && clock.rate === r} onClick={() => rt?.session.setRate(r)}>×{r}</button>)}
      </div>
      <div className="actions">
        <button className="btn" onClick={() => rt?.session.jump(rt.session.clock.now() + 1800)}>+30 min</button>
        <button className="btn" onClick={() => rt?.session.jump(rt.session.clock.now() + 3600 * 2)}>+2 h</button>
        <button className="btn" onClick={() => rt?.session.jump(Math.max(0, rt.session.clock.now() - 1800))}>−30 min</button>
      </div>
      <small className="quiet">Simulation runs the same deterministic motion model and rule engine at any time. The future shows declared plans and predictions; real feeds are shown only live.</small>
    </div>
    <div className="section"><h4>Inject an event</h4><div className="list">
      {PRESETS.map(p => <button key={p.id} className="item" disabled={busy || clock.mode !== 'live'} onClick={() => void rt?.session.inject(p.id)}><span className="dot warning" /><span><strong>{p.label}</strong><small>{p.desc}</small></span><Icon.play width={14} height={14} /></button>)}
    </div><small className="quiet">Injected events are synthetic inputs and tracks; every rule reacts to them exactly as to real reports.</small></div>
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
    actions.toast(`Report "${form.title}" is in the picture; rules re-evaluated.`)
    setForm(f => ({ ...f, title: '', text: '', entityRefs: '' }))
  }
  return <form className="form" onSubmit={e => void submit(e)}>
    <div className="row">
      <label>Channel<select value={form.channel} onChange={e => setForm({ ...form, channel: e.target.value })}>{(views?.channels ?? []).map(c => <option key={c.id} value={c.id}>{channelLabel[c.id] ?? c.label}</option>)}</select></label>
      <label>Level<select value={form.authorLevel} onChange={e => setForm({ ...form, authorLevel: e.target.value })}>{levels.map(l => <option key={l} value={l}>{l.replace('_', ' ')}</option>)}</select></label>
    </div>
    <label>Author<input required value={form.author} placeholder="Who is reporting" onChange={e => setForm({ ...form, author: e.target.value })} /></label>
    <label>Title<input required value={form.title} placeholder="One line" onChange={e => setForm({ ...form, title: e.target.value })} /></label>
    <label>Text<textarea required value={form.text} placeholder="What was observed. Mention unit ids and places (Visby, Umeå) and the rules link them." onChange={e => setForm({ ...form, text: e.target.value })} /></label>
    <label>Entity ids (optional)<input value={form.entityRefs} placeholder="airbase-syd, coy-n1a-03" onChange={e => setForm({ ...form, entityRefs: e.target.value })} /></label>
    <button className="btn primary" disabled={busy}>Send to the picture</button>
    <small className="quiet">Severity, places and tags are extracted by rules; nothing is guessed by a model.</small>
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
    <div className="list">{sources.map(s => <div key={s.id} className="source">
      <div><span className={`status ${s.status}`}>{s.status}</span><strong>{s.label}</strong></div>
      <small>{s.count != null ? `${s.count} items · ` : ''}{s.lastOkAt ? `updated ${ago(s.lastOkAt)}` : 'not fetched yet'}{s.stale ? ' · stale' : ''}</small>
      {s.lastError && <small className="err">{s.lastError}</small>}
      {s.note && <small>{s.note}</small>}
      <small className="lic">{s.licence}</small>
    </div>)}
      {!sources.length && <div className="quiet">Source status loads in a moment.</div>}
    </div>
    <div className="section"><h4>Synthetic content</h4><small className="quiet">{notice}</small></div>
  </>
}

function HelpPanel() {
  const rows: [string, string][] = [['/', 'Search'], ['L', 'Layers'], ['A', 'Alerts and reports'], ['D', 'Decisions'], ['S', 'Simulate'], ['R', 'Submit a report'], ['I', 'Data sources'], ['3', '3D'], ['F', 'Follow selection'], ['Space', 'Pause / resume simulation'], ['Esc', 'Deselect / close'], ['Home', 'Reset view']]
  return <>
    <div className="help">{rows.map(([k, v]) => <Fragment key={k}><kbd>{k}</kbd><span>{v}</span></Fragment>)}</div>
    <div className="section"><h4>Reading the map</h4><small className="quiet">Symbols follow NATO APP-6: cyan rectangle friend, yellow quatrefoil unknown, red diamond suspect, purple civil. Formations collapse into one symbol while their units fit together on screen and open up as you zoom; the number after a designation is its platform count. A bar under a symbol is its condition (amber degraded, red unavailable). Real public traffic is drawn as plain silhouettes.</small></div>
  </>
}
