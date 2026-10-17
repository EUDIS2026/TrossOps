import type { Alert, Deception, EntityDetail, FormationDetail, Fusion, InputReport, Intervention, InterventionOption, LiveAircraft, LiveVessel, PredictedPath, RouteOption } from '../contracts/types'
import { useEffect, useState } from 'react'
import { actions, EMPTY, store, useApp, type InspectorTab } from '../core/store'
import type { WNode } from '../core/world'
import { AlertRow, InputRow } from './Dock'
import { ago, Bar, channelLabel, Fact, fmtTime, kindLabel, NatoGlyph, pct, Ring, useRuntime } from './context'
import { Icon } from './icons'

function Tabs({ tabs }: { tabs: [InspectorTab, string, (number | string)?][] }) {
  const tab = useApp(s => s.tab)
  const active = tabs.some(t => t[0] === tab) ? tab : tabs[0][0]
  return <div className="tabs" role="tablist">{tabs.map(([id, label, badge]) => <button key={id} role="tab" aria-selected={active === id} onClick={() => actions.setTab(id)}>{label}{badge !== undefined && badge !== 0 && <i>{badge}</i>}</button>)}</div>
}
function useTab(tabs: InspectorTab[]): InspectorTab { const t = useApp(s => s.tab); return tabs.includes(t) ? t : tabs[0] }

function Head({ sidc, cond, title, sub, chain }: { sidc?: string | null; cond?: string; title: string; sub: string; chain?: WNode[] }) {
  return <div className="ent-head">
    {sidc !== undefined ? <NatoGlyph sidc={sidc} condition={(cond as 'normal') ?? 'normal'} size={56} /> : <span className="glyph-ph big"><Icon.target /></span>}
    <div>
      {chain && chain.length > 0 && <div className="crumbs">{chain.slice(-3).map(c => <button key={c.e.id} onClick={() => actions.select('formation', c.e.id)}>{c.e.short ?? c.e.label}</button>)}</div>}
      <h3>{title}</h3><p>{sub}</p>
    </div>
  </div>
}

// ---- shared blocks -------------------------------------------------------------------------------------------------
function FusionView({ f }: { f: Fusion | null | undefined }) {
  if (!f) return <div className="quiet">No report or sensor has referenced this subject yet; its status comes from its own unit reporting only.</div>
  return <>
    <div className="facts"><Fact k="Combined confidence" v={`${Math.round(f.confidence * 100)} %`} /><Fact k="Independent channels" v={f.corroboration} /></div>
    <Bar value={f.confidence} tone="accent" />
    {f.identity && <div className="section"><h4>Identity hypotheses</h4>{f.identity.map(h => <div key={h.hypothesis} className="hyp">
      <div className="hyp-head"><strong>{h.hypothesis}</strong><b>{Math.round(h.probability * 100)} %</b></div><Bar value={h.probability} tone="accent" />
      <ul>{h.indicators.map(x => <li key={x}>{x}</li>)}</ul></div>)}</div>}
    <div className="section"><h4>Source ledger <span>Admiralty grading</span></h4><div className="list">
      {f.sources.map((s, k) => <button key={k} className="item src" disabled={!s.inputId} onClick={() => s.inputId && actions.select('input', s.inputId)}>
        <span className={`grade g${s.grading[0]}`}>{s.grading}</span>
        <span><strong>{s.title}</strong><small>{s.channelLabel} · {s.author} · {s.reliability}, {s.credibility}</small></span><span className="when">{fmtTime(s.at)}</span>
      </button>)}
    </div><small className="quiet">{f.method}</small></div>
  </>
}

function DeceptionView({ d }: { d: Deception | null | undefined }) {
  if (!d) return <div className="quiet">No deception indicators apply to this subject.</div>
  const tone = d.probability >= 0.75 ? 'crit' : d.probability >= 0.5 ? 'warn' : 'good'
  return <>
    <div className="gauge"><div><small>{d.hypothesis}</small><b className={tone}>{Math.round(d.probability * 100)} %</b><span className={`tag ${tone}`}>{d.band}</span></div><Bar value={d.probability} tone={tone} /></div>
    <div className="section"><h4>Indicators <span>log-odds weight</span></h4>
      <div className="ind"><span>Prior</span><small>base rate for this kind of subject</small><b>{Math.round(d.prior * 100)} %</b></div>
      {d.indicators.map(i => <div key={i.id} className="ind"><span><em>{i.id}</em> {i.label}</span><small>{i.evidence}</small><b className={i.weight > 0 ? 'warn' : 'good'}>{i.weight > 0 ? '+' : ''}{i.weight.toFixed(1)}</b></div>)}
    </div>
    <div className="section"><h4>Collection that would change this</h4><ul className="plain">{d.wouldChange.map(w => <li key={w}>{w}</li>)}</ul></div>
    <small className="quiet">{d.method}</small>
  </>
}

function PredictionView({ preds, id }: { preds: PredictedPath[]; id: string }) {
  const own = preds.filter(p => p.entityId === id)
  const other = preds.filter(p => p.entityId !== id)
  return <>
    {own.length === 0 && <div className="quiet">No prediction: the platform follows a declared plan (shown under Planned routes) or is stationary.</div>}
    {own.map(p => <div key={p.method} className="hyp">
      <div className="hyp-head"><strong>{p.hypothesis}</strong><b>{Math.round(p.probability * 100)} %</b></div><Bar value={p.probability} tone="accent" />
      <div className="facts"><Fact k="Horizon" v={`${Math.round(p.horizonS / 60)} min`} /><Fact k="Closest own asset" v={p.etaS !== null ? `${Math.round(p.etaS / 60)} min` : 'none in horizon'} /></div>
      {p.threatenedEntityIds.length > 0 && <div className="chips">{p.threatenedEntityIds.map(t => <button key={t} className="chip" onClick={() => actions.select('site', t)}>{t}</button>)}</div>}
      <small>Based on</small><ul>{p.basedOn.map(b => <li key={b}>{b}</li>)}</ul>
      <small className="quiet mono">{p.method}</small>
    </div>)}
    {other.length > 0 && <div className="section"><h4>On the predicted path of</h4><div className="chips">{[...new Set(other.map(p => p.entityId))].map(t => <button key={t} className="chip" onClick={() => actions.select('track', t)}>{t}</button>)}</div></div>}
  </>
}

function OptionCard({ iv, o }: { iv: Intervention; o: InterventionOption }) {
  const rt = useRuntime()
  const busy = useApp(s => s.busy)
  const sim = useApp(s => s.clock.mode === 'sim')
  const rec = iv.recommendedOptionId === o.id, done = iv.committedOptionId === o.id
  return <div className="option" data-recommended={rec}>
    <div className="option-head"><strong>{o.title}</strong>{done ? <span className="tag good">committed</span> : rec ? <span className="tag accent">recommended</span> : null}</div>
    <div className="option-meta"><span>success <b>{Math.round(o.successLikelihood * 100)} %</b></span><span>effect <b>{o.etaMin === null ? '—' : `${Math.round(o.etaMin)} min`}</b></span>{o.distanceKm !== null && <span><b>{o.distanceKm}</b> km</span>}<span>risk <b>{o.riskLevel}</b></span></div>
    <div className="bands">{o.outcomes.map(b => <div key={b.label} className={`band ${b.label}`} style={{ flex: Math.max(0.15, b.probability) }}><b>{Math.round(b.probability * 100)} %</b>{b.label}</div>)}</div>
    <small>{o.rationale}</small>
    <ol className="steps">{o.steps.map(s => <li key={s}>{s}</li>)}</ol>
    <div className="actions">{o.assignedEntityIds.map(id => <button key={id} className="mini" onClick={() => actions.select('entity', id)}>{id}</button>)}
      {!done && iv.status === 'proposed' && <button className="btn small primary" disabled={busy || sim} onClick={() => void rt?.session.commit(iv.id, o.id)}><Icon.check width={14} height={14} />Commit</button>}</div>
  </div>
}

function InterventionView({ iv }: { iv: Intervention }) {
  const rt = useRuntime()
  return <div className="section">
    <h4>{iv.title} <span>{iv.status.replace('_', ' ')}</span></h4>
    <div className="note">{iv.objective}</div>
    {iv.status !== 'proposed' && <div className="progress"><i style={{ width: `${iv.progress * 100}%` }} /></div>}
    {iv.monitorAlerts.length > 0 && <div className="note">{iv.monitorAlerts[iv.monitorAlerts.length - 1]}</div>}
    {iv.options.map(o => <OptionCard key={o.id} iv={iv} o={o} />)}
    {iv.status === 'in_progress' && <button className="btn small danger" onClick={() => void rt?.session.abort(iv.id)}>Abort and re-plan</button>}
  </div>
}

function RoutePlanner({ n }: { n: WNode }) {
  const route = useApp(s => s.route)
  const rt = useRuntime()
  const busy = useApp(s => s.busy)
  if (!route || route.entityId !== n.e.id) return <button className="btn primary wide" onClick={() => actions.startRoute(n.e.id)}><Icon.route width={15} height={15} />Plan a route…</button>
  if (route.picking) return <div className="note accent">Click the destination on the map. <button className="mini" onClick={() => actions.cancelRoute()}>Cancel</button></div>
  if (route.busy || !route.result) return <div className="note">Planning on the {n.e.domain === 'land' ? 'road network' : n.e.domain === 'sea' ? 'water grid' : 'airspace'}…</div>
  const r = route.result
  return <div className="section"><h4>Route options <span>{r.options.length}</span></h4>
    {r.options.map((o: RouteOption) => <button key={o.id} className="route-opt" aria-pressed={route.option === o.id} onClick={() => store_setOption(o.id)}>
      <div className="option-head"><strong>{o.label}</strong>{r.recommended === o.id && <span className="tag accent">recommended</span>}{!o.feasible && <span className="tag crit">infeasible</span>}</div>
      <div className="option-meta"><span><b>{o.distanceKm}</b> km</span><span>ETA <b>{Math.round(o.etaMin)} min</b></span><span>fuel <b>{o.fuelUsePct} %</b>{o.fuelAfterPct !== null && ` → ${o.fuelAfterPct} %`}</span><span>risk <b>{Math.round(o.risk * 100)} %</b></span></div>
      {o.terrain && <TerrainProfile o={o} />}
      {o.notes.map(x => <small key={x} className="warn-text">{x}</small>)}
      <small className="quiet">{o.basedOn.join(' · ')}</small>
    </button>)}
    <div className="actions">
      <button className="btn primary" disabled={busy || !route.option} onClick={() => { const o = r.options.find(x => x.id === route.option); if (o) void rt?.session.commitRoute(n.e.id, o) }}><Icon.check width={14} height={14} />Execute</button>
      <button className="btn" onClick={() => actions.startRoute(n.e.id)}>New destination</button>
      <button className="btn" onClick={() => actions.cancelRoute()}>Cancel</button>
    </div>
    <small className="quiet">{r.method}</small>
  </div>
}
/** Ground elevation under the route (Lantmäteriet); airborne options also draw the flight altitude. */
function TerrainProfile({ o }: { o: RouteOption }) {
  const t = o.terrain!
  const ground = t.groundM
  const alt = o.airborne ? o.path.map(v => v[2] ?? null) : null
  const vals = [...ground, ...(alt ?? [])].filter((v): v is number => v !== null)
  if (vals.length < 2) return null
  const lo = Math.min(0, ...vals), hi = Math.max(...vals) * 1.05 + 1
  const W = 260, H = 44
  const y = (v: number) => H - ((v - lo) / (hi - lo)) * H
  const line = (vs: (number | null)[]) => vs.map((v, i) => v === null ? null : `${(i / Math.max(1, vs.length - 1)) * W},${y(v).toFixed(1)}`).filter(Boolean).join(' ')
  return <div className="terrain-profile" title="Ground elevation along the route (Lantmäteriet Markhöjd)">
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" width="100%" height={H}>
      <polygon points={`0,${H} ${line(ground)} ${W},${H}`} className="ground" />
      {alt && <polyline points={line(alt)} className="alt" />}
    </svg>
    <small className="quiet">terrain {t.minM ?? '?'}–{t.maxM ?? '?'} m{t.climbM != null && ` · climb ${t.climbM} m`}{t.minClearanceM != null && ` · min clearance ${t.minClearanceM} m`}</small>
  </div>
}

const store_setOption = (id: string) => store.set(s => ({ route: s.route ? { ...s.route, option: id } : null }))

// ---- subjects ---------------------------------------------------------------------------------------------------
function PlatformView({ n }: { n: WNode }) {
  const rt = useRuntime()
  const detail = useApp(s => s.detail) as EntityDetail | null
  const follow = useApp(s => s.follow)
  const busy = useApp(s => s.busy)
  const sim = useApp(s => s.clock.mode === 'sim')
  const snapPreds = useApp(s => s.snapshot?.predictions ?? EMPTY)
  const fusion = useApp(s => s.snapshot?.fusion[n.e.id])
  const deception = useApp(s => s.snapshot?.deception[n.e.id])
  useApp(s => Math.floor(s.clock.t))
  const e = n.e
  const d = detail && 'entity' in detail && detail.entity.id === e.id ? detail : null
  const r = d?.entity.readiness
  const unknown = e.affiliation === 'unknown'
  const p = rt?.session.world?.poseNow(n) ?? n.pose
  const chain = rt?.session.world?.chain(n) ?? []
  const tabs: InspectorTab[] = unknown ? ['overview', 'fusion', 'prediction', 'deception', 'actions'] : ['overview', 'fusion', 'prediction', 'actions']
  const tab = useTab(tabs)
  const alerts = d?.alerts ?? []
  return <>
    <Head sidc={e.sidc} cond={n.status?.[0]} title={e.label} sub={`${e.platform ?? kindLabel[e.kind]}${e.siteId ? ` · based ${e.siteId}` : ''}`} chain={chain} />
    <div className="tags">
      <span className={`tag ${e.affiliation}`}>{e.affiliation.replace('_', ' ')}</span>
      {n.status && n.status[0] !== 'normal' && <span className={`tag ${n.status[0] === 'unavailable' ? 'crit' : 'warn'}`}>{n.status[0]}</span>}
      <span className="tag">{e.sourceKind}</span>
      {p.phase !== 'static' && <span className="tag">{p.phase}</span>}
      {deception && deception.probability >= 0.5 && <span className="tag crit">deception {deception.band}</span>}
      {e.tags.filter(t => !t.includes(':') && t !== e.siteId).slice(0, 3).map(t => <span key={t} className="tag">{t.replace(/_/g, ' ')}</span>)}
    </div>
    <Tabs tabs={tabs.map(t => [t, { overview: 'Overview', fusion: 'Why', prediction: 'Prediction', deception: 'Deception', actions: 'Actions' }[t as 'overview'], t === 'actions' ? alerts.length : undefined] as [InspectorTab, string, number?])} />
    {tab === 'overview' && <>
      {r && !unknown && <div className="readiness"><Ring score={r.score} /><div className="facts">
        <Fact k="Fuel" v={pct(p.fuel ?? r.fuelPct)} tone={(p.fuel ?? r.fuelPct ?? 100) < 25 ? 'warn' : ''} /><Fact k="Ammunition" v={pct(r.ammunitionPct)} />
        <Fact k="Crew" v={`${r.crewPresent ?? '—'}${r.crewRequired ? ` / ${r.crewRequired}` : ''}`} /><Fact k="Comms" v={r.commsStatus} tone={r.commsStatus === 'lost' ? 'crit' : r.commsStatus === 'degraded' ? 'warn' : ''} />
        <Fact k="Maintenance due" v={r.maintenanceDueH === null ? '—' : `${r.maintenanceDueH} h`} /><Fact k="Last report" v={ago(r.lastReportAt)} />
      </div></div>}
      <div className="facts">
        <Fact k="Speed" v={p.speed > 0.3 ? `${Math.round(p.speed * 3.6)} km/h${e.domain !== 'land' ? ` · ${Math.round(p.speed * 1.944)} kt` : ''}` : 'stationary'} />
        <Fact k="Heading" v={p.speed > 0.3 ? `${Math.round(p.heading)}°` : '—'} />
        {(e.domain === 'air' || p.alt) && <Fact k="Altitude" v={p.alt ? `${Math.round(p.alt)} m MSL · FL${Math.round(p.alt / 30.48)}` : 'on ground'} />}
        {e.domain === 'air' && p.alt ? <Fact k="Attitude" v={`pitch ${p.pitch.toFixed(0)}° · bank ${p.bank.toFixed(0)}°`} /> : null}
        <Fact k="Position" v={`${p.lat.toFixed(4)}, ${p.lng.toFixed(4)}`} />
        {e.rangeKm && <Fact k="Reach" v={`${e.rangeKm} km`} />}
      </div>
      {r && (r.faults.length > 0 || r.notes.length > 0) && <div className="section"><h4>Faults and notes</h4><div className="list">{[...r.faults, ...r.notes].map(f => <div key={f} className="note">{f}</div>)}</div></div>}
      {e.capabilities.length > 0 && <div className="chips">{e.capabilities.map(c => <span key={c} className="chip static">{c.replace(/_/g, ' ')}</span>)}</div>}
      {d?.plan && <div className="note accent">Executing committed plan "{d.plan.label}" since {fmtTime(d.plan.recordedAt)}.</div>}
    </>}
    {tab === 'fusion' && <FusionView f={fusion ?? d?.fusion} />}
    {tab === 'prediction' && <PredictionView preds={snapPreds.filter(x => x.entityId === e.id || x.threatenedEntityIds.includes(e.id))} id={e.id} />}
    {tab === 'deception' && <DeceptionView d={deception ?? d?.deception} />}
    {tab === 'actions' && <>
      <div className="actions">
        <button className="btn" aria-pressed={follow} onClick={() => actions.toggleFollow()}><Icon.target width={14} height={14} />{follow ? 'Following' : 'Follow'}</button>
        {e.affiliation === 'own' && <>
          {n.status?.[0] !== 'unavailable' ? <button className="btn danger" disabled={busy || sim} onClick={() => void rt?.session.event(e.id, 'fault')}>Record fault</button> : <button className="btn" disabled={busy || sim} onClick={() => void rt?.session.event(e.id, 'repair')}>Record repair</button>}
          <button className="btn" disabled={busy || sim} onClick={() => void rt?.session.event(e.id, 'resupply')}>Resupply</button>
        </>}
        {d?.plan && <button className="btn" disabled={busy} onClick={() => void rt?.session.cancelPlan(e.id)}>Cancel plan</button>}
      </div>
      {!unknown && n.motion && ['land', 'sea', 'air'].includes(e.domain) && e.kind !== 'personnel' && <RoutePlanner n={n} />}
      {alerts.length > 0 && <div className="section"><h4>Alerts <span>{alerts.length}</span></h4><div className="list">{alerts.map(a => <AlertRow key={a.id} a={a} />)}</div></div>}
      {(d?.interventions ?? []).map(iv => <InterventionView key={iv.id} iv={iv} />)}
      {(d?.inputs.length ?? 0) > 0 && <div className="section"><h4>Reports <span>{d!.inputs.length}</span></h4><div className="list">{[...d!.inputs].reverse().slice(0, 8).map(i => <InputRow key={i.id} i={i} />)}</div></div>}
    </>}
  </>
}

function FormationView({ n }: { n: WNode }) {
  const rt = useRuntime()
  const detail = useApp(s => s.detail) as FormationDetail | null
  useApp(s => Math.floor(s.clock.t / 2))
  const d = detail && 'formation' in detail && detail.formation.id === n.e.id ? detail : null
  const w = rt?.session.world
  const tab = useTab(['overview', 'units', 'actions'])
  const chain = w?.chain(n) ?? []
  return <>
    <Head sidc={n.e.sidc} cond={['normal', 'degraded', 'unknown', 'unavailable'][n.worst]} title={n.e.label} sub={`${n.e.echelon ?? 'formation'} · ${n.count} platforms in view layers`} chain={chain} />
    <Tabs tabs={[['overview', 'Overview'], ['units', 'Units', n.children.length], ['actions', 'Alerts', d?.alerts.length]]} />
    {tab === 'overview' && <>
      {d && <div className="readiness">{d.readiness !== null && <Ring score={d.readiness} />}<div className="facts">
        <Fact k="Platforms" v={d.platforms} /><Fact k="Moving" v={d.moving} /><Fact k="Fuel (mean)" v={pct(d.fuel)} /><Fact k="Unavailable" v={d.unavailable} tone={d.unavailable ? 'crit' : ''} /><Fact k="Degraded" v={d.degraded} tone={d.degraded ? 'warn' : ''} />
      </div></div>}
      {d && <div className="section"><h4>Composition</h4>{Object.entries(d.byPlatform).sort((a, b) => b[1] - a[1]).map(([k, v]) => <div key={k} className="comp"><span>{k}</span><b>{v}</b></div>)}</div>}
      <div className="actions"><button className="btn" onClick={() => actions.select('formation', n.e.id)}>Frame on map</button></div>
    </>}
    {tab === 'units' && <div className="list">{n.children.map(c => <button key={c.e.id} className="item" onClick={() => actions.select(c.leaf ? (c.e.affiliation === 'unknown' ? 'track' : 'entity') : 'formation', c.e.id)}>
      <NatoGlyph sidc={c.e.sidc} size={30} /><span><strong>{c.e.label}</strong><small>{c.leaf ? c.e.platform : `${c.count} platforms${c.moving ? ` · ${c.moving} moving` : ''}`}</small></span></button>)}</div>}
    {tab === 'actions' && <div className="list">{(d?.alerts ?? []).map(a => <AlertRow key={a.id} a={a} />)}{!d?.alerts.length && <div className="quiet">No alerts on this formation.</div>}</div>}
  </>
}

function SiteView({ n }: { n: WNode }) {
  const rt = useRuntime()
  const detail = useApp(s => s.detail) as EntityDetail | null
  const d = detail && 'entity' in detail && detail.entity.id === n.e.id ? detail : null
  const w = rt?.session.world
  const tab = useTab(['overview', 'inventory', 'actions'])
  const based = (d?.based ?? []).map(id => w?.get(id)).filter(Boolean) as WNode[]
  const groups = new Map<string, { n: number; airborne: number; away: number }>()
  for (const b of based) {
    const k = b.e.platform ?? b.e.kind
    const g = groups.get(k) ?? { n: 0, airborne: 0, away: 0 }
    const p = w!.poseNow(b)
    g.n++; if ((p.alt ?? 0) > 50) g.airborne++; else if (p.phase !== 'static' && p.phase !== 'holding' && p.phase !== 'waiting') g.away++
    groups.set(k, g)
  }
  const feats = d?.layout?.features.features ?? []
  const tanks = feats.filter(f => f.properties?.cls === 'fuel_tank').map(f => f.properties!.fill as number)
  const r = d?.entity.readiness
  return <>
    <Head sidc={n.e.sidc} cond={n.status?.[0]} title={n.e.label} sub={`${n.e.tags[0] ?? 'site'} · ${n.e.tags[1] ?? ''}`} />
    <Tabs tabs={[['overview', 'Overview'], ['inventory', 'Inventory', based.length], ['actions', 'Alerts', d?.alerts.length]]} />
    {tab === 'overview' && <>
      {r && <div className="readiness"><Ring score={r.score} /><div className="facts"><Fact k="Personnel" v={`${r.crewPresent ?? '—'} / ${r.crewRequired ?? '—'}`} /><Fact k="Comms" v={r.commsStatus} />
        {tanks.length > 0 && <Fact k="Fuel farm" v={`${Math.round(tanks.reduce((a, b) => a + b, 0) / tanks.length)} %`} />}{r.ammunitionPct !== null && <Fact k="Ammunition" v={pct(r.ammunitionPct)} />}</div></div>}
      {d?.layout && <div className="section"><h4>Installation</h4>
        {Object.entries(d.layout.spots).map(([k, v]) => <div key={k} className="comp"><span>{k} positions</span><b>{v.length}</b></div>)}
        {tanks.length > 0 && <><small>Fuel tanks</small><div className="tanks">{tanks.map((t, i) => <div key={i} className="tank"><i style={{ height: `${t}%` }} /><span>{t}</span></div>)}</div></>}
      </div>}
      {r && r.notes.length > 0 && <div className="section"><h4>Notes</h4>{r.notes.map(x => <div key={x} className="note">{x}</div>)}</div>}
      <small className="quiet">Layers → Site detail splits this installation into infrastructure, logistics, defence and personnel.</small>
    </>}
    {tab === 'inventory' && <>
      {[...groups.entries()].map(([k, g]) => <div key={k} className="comp"><span>{k}</span><b>{g.n}</b>{g.airborne > 0 && <em className="air">{g.airborne} airborne</em>}{g.away > 0 && <em>{g.away} moving</em>}</div>)}
      <div className="list">{based.slice(0, 80).map(b => <button key={b.e.id} className="item" onClick={() => actions.select('entity', b.e.id)}><NatoGlyph sidc={b.e.sidc} condition={b.status?.[0]} size={28} /><span><strong>{b.e.label}</strong><small>{b.e.platform} · {w!.poseNow(b).phase}</small></span></button>)}</div>
    </>}
    {tab === 'actions' && <div className="list">{(d?.alerts ?? []).map(a => <AlertRow key={a.id} a={a} />)}{!d?.alerts.length && <div className="quiet">No alerts at this site.</div>}</div>}
  </>
}

function InputView({ i }: { i: InputReport }) {
  const alerts = useApp(s => s.snapshot?.alerts ?? EMPTY).filter(a => a.inputIds.includes(i.id))
  const dec = useApp(s => s.snapshot?.deception[i.id])
  const tab = useTab(['overview', 'deception'])
  return <>
    <Head title={i.title} sub={`${channelLabel[i.channel] ?? i.channel} · ${i.author}`} />
    <div className="tags"><span className={`tag ${i.severity}`}>{i.severity}</span><span className="tag">{i.sourceKind === 'public' || i.sourceKind === 'observed' ? 'real feed' : i.sourceKind}</span>{i.tags.slice(0, 5).map(t => <span key={t} className="tag">{t}</span>)}</div>
    <Tabs tabs={[['overview', 'Report'], ['deception', 'Deception', dec ? `${Math.round(dec.probability * 100)}%` : undefined]]} />
    {tab === 'overview' && <>
      <div className="note body">{i.text}</div>
      <div className="facts"><Fact k="Effective" v={fmtTime(i.effectiveAt)} /><Fact k="Location" v={i.position ? `${i.position.latitudeDeg.toFixed(3)}, ${i.position.longitudeDeg.toFixed(3)}` : 'not geolocated'} /><Fact k="Radius" v={i.radiusM ? `${(i.radiusM / 1000).toFixed(0)} km` : '—'} /></div>
      {i.entityRefs.length > 0 && <div className="chips">{i.entityRefs.map(id => <button key={id} className="chip" onClick={() => actions.select(id.startsWith('unk') ? 'track' : id.startsWith('area') ? 'area' : 'entity', id)}>{id}</button>)}</div>}
      {alerts.length > 0 && <div className="section"><h4>Rules that fired <span>{alerts.length}</span></h4><div className="list">{alerts.map(a => <AlertRow key={a.id} a={a} />)}</div></div>}
    </>}
    {tab === 'deception' && <DeceptionView d={dec} />}
  </>
}

function AlertView({ a }: { a: Alert }) {
  const ivs = useApp(s => s.snapshot?.interventions ?? EMPTY).filter(iv => iv.alertId === a.id)
  const inputs = useApp(s => s.snapshot?.inputs ?? EMPTY).filter(i => a.inputIds.includes(i.id))
  const rule = useApp(s => s.views?.rules.find(r => r.id === a.ruleId))
  const rt = useRuntime()
  const tab = useTab(['overview', 'sources', 'actions'])
  return <>
    <Head title={a.title} sub={`${a.ruleId}${rule ? ` · ${rule.title}` : ''}`} />
    <div className="tags"><span className={`tag ${a.severity}`}>{a.severity}</span>{a.acknowledged && <span className="tag">acknowledged</span>}</div>
    <Tabs tabs={[['overview', 'Overview'], ['sources', 'Why', inputs.length], ['actions', 'Options', ivs[0]?.options.length]]} />
    {tab === 'overview' && <><div className="note body">{a.detail}</div>
      <div className="chips">{a.entityIds.slice(0, 10).map(id => <button key={id} className="chip" onClick={() => actions.select(id.startsWith('unk') ? 'track' : 'entity', id)}>{id}</button>)}</div>
      {!a.acknowledged && <div className="actions"><button className="btn primary" onClick={() => void rt?.session.ack(a.id)}><Icon.check width={14} height={14} />Acknowledge</button></div>}</>}
    {tab === 'sources' && <div className="list">{inputs.map(i => <InputRow key={i.id} i={i} />)}{!inputs.length && <div className="quiet">Derived from world state ({a.ruleId}), not from a report.</div>}</div>}
    {tab === 'actions' && (ivs.length ? ivs.map(iv => <InterventionView key={iv.id} iv={iv} />) : <div className="quiet">This alert has no proposed course of action.</div>)}
  </>
}

function LiveView({ kind, item }: { kind: 'aircraft' | 'vessel'; item: LiveAircraft | LiveVessel | undefined }) {
  if (!item) return <div className="quiet">This contact is no longer in the feed.</div>
  if (kind === 'aircraft') {
    const a = item as LiveAircraft
    return <>
      <Head title={a.callsign ?? a.id.toUpperCase()} sub={`${a.type ?? 'aircraft'} · ${a.registration ?? 'unregistered'} · live ADS-B`} />
      <div className="tags"><span className="tag">real</span>{a.military && <span className="tag warn">military-flagged</span>}{a.emergency && <span className="tag crit">{a.emergency}</span>}</div>
      <div className="facts">
        <Fact k="Altitude" v={a.onGround ? 'on ground' : a.altM != null ? `${Math.round(a.altM)} m · FL${Math.round(a.altM / 30.48)}` : '—'} /><Fact k="Ground speed" v={a.speedMps != null ? `${Math.round(a.speedMps * 1.944)} kt` : '—'} />
        <Fact k="Track" v={a.headingDeg != null ? `${Math.round(a.headingDeg)}°` : '—'} /><Fact k="Vertical rate" v={a.verticalRateMps != null ? `${Math.round(a.verticalRateMps * 196.85)} ft/min` : '—'} />
        <Fact k="Squawk" v={a.squawk ?? '—'} tone={['7500', '7600', '7700'].includes(a.squawk ?? '') ? 'crit' : ''} /><Fact k="Category" v={a.category ?? '—'} />
        <Fact k="GNSS integrity" v={a.nic != null ? `NIC ${a.nic} · NACp ${a.nacp}` : '—'} tone={a.nic != null && (a.nic < 7 || (a.nacp ?? 9) < 8) ? 'warn' : ''} /><Fact k="Position age" v={a.seenS != null ? `${a.seenS.toFixed(0)} s` : '—'} />
      </div>
      <small className="quiet">Source: {a.source} (ODbL). Positions are dead-reckoned between updates.</small>
    </>
  }
  const v = item as LiveVessel
  return <>
    <Head title={v.name ?? `MMSI ${v.id}`} sub={`${v.shipTypeLabel ?? 'vessel'} · live AIS`} />
    <div className="tags"><span className="tag">real</span>{v.navStatusLabel && <span className="tag">{v.navStatusLabel}</span>}</div>
    <div className="facts">
      <Fact k="Speed" v={v.speedMps != null ? `${(v.speedMps * 1.944).toFixed(1)} kn` : '—'} /><Fact k="Course" v={v.courseDeg != null ? `${Math.round(v.courseDeg)}°` : '—'} />
      <Fact k="Destination" v={v.destination ?? '—'} /><Fact k="Call sign" v={v.callsign ?? '—'} /><Fact k="IMO" v={v.imo || '—'} /><Fact k="MMSI" v={String(v.id)} />
      <Fact k="Report age" v={v.timestampMs ? ago(new Date(v.timestampMs).toISOString()) : '—'} />
    </div>
    <small className="quiet">Source: {v.source} (Fintraffic / Digitraffic, CC BY 4.0).</small>
  </>
}

function CellView() {
  const sel = useApp(s => s.selected)
  const d = sel?.data as { cell?: { label: string; reasons: string[] }; surface?: string; unit?: string; note?: string } | undefined
  if (!d?.cell) return <div className="quiet">This cell is no longer on the surface.</div>
  return <>
    <Head title={d.cell.label} sub={`${d.surface} surface · ${d.unit}`} />
    <div className="section"><h4>Why</h4>{d.cell.reasons.map(r => <div key={r} className="note">{r}</div>)}</div>
    <small className="quiet">{d.note}</small>
  </>
}

export function Inspector() {
  const sel = useApp(s => s.selected)
  const snap = useApp(s => s.snapshot)
  const live = useApp(s => s.live)
  const ready = useApp(s => s.worldReady)
  const rt = useRuntime()
  if (!sel) return null
  const w = ready ? rt?.session.world : null
  let body: React.ReactNode = <div className="quiet">Loading…</div>
  const n = w?.get(sel.id)
  if ((sel.kind === 'entity' || sel.kind === 'track') && n) body = <PlatformView n={n} />
  else if (sel.kind === 'formation' && n) body = <FormationView n={n} />
  else if (sel.kind === 'site' && n) body = <SiteView n={n} />
  else if (sel.kind === 'aircraft') body = <LiveView kind="aircraft" item={live.aircraft.find(a => a.id === sel.id) ?? (sel.data as LiveAircraft)} />
  else if (sel.kind === 'vessel') body = <LiveView kind="vessel" item={live.vessels.find(v => String(v.id) === sel.id) ?? (sel.data as LiveVessel)} />
  else if (sel.kind === 'input') { const i = snap?.inputs.find(x => x.id === sel.id); if (i) body = <InputView i={i} /> }
  else if (sel.kind === 'alert') { const a = snap?.alerts.find(x => x.id === sel.id); if (a) body = <AlertView a={a} /> }
  else if (sel.kind === 'intervention') { const iv = snap?.interventions.find(x => x.id === sel.id); if (iv) body = <><Head title={iv.title} sub="Course of action" /><InterventionView iv={iv} /></> }
  else if (sel.kind === 'cell') body = <CellView />
  else if (sel.kind === 'area') { const a = snap?.areas.find(x => x.id === sel.id); if (a) body = <><Head title={a.label} sub={a.kind.replace(/_/g, ' ')} /><div className="tags"><span className={`tag ${a.status === 'covered' ? 'good' : a.status === 'degraded' ? 'warn' : a.status === 'uncovered' ? 'crit' : ''}`}>{a.status}</span></div>
    {(a.blockers ?? []).map(b => <div key={b} className="note">{b}</div>)}<div className="chips">{a.requires.map(r => <button key={r} className="chip" onClick={() => actions.select('entity', r)}>{r}</button>)}</div></> }
  else if (sel.kind === 'police' || sel.kind === 'warning' || sel.kind === 'cable') {
    const p = sel.data as Record<string, unknown> | undefined
    body = <><Head title={String(p?.name ?? p?.event ?? p?.label ?? sel.id)} sub={sel.kind === 'police' ? `Polisen · ${p?.type ?? ''}` : sel.kind === 'warning' ? `SMHI warning · ${p?.level ?? ''} · ${p?.area ?? ''}` : 'Undersea infrastructure (approximate public route)'} />
      <div className="tags"><span className="tag">{sel.kind === 'cable' ? 'public, illustrative' : 'real feed'}</span></div>
      {sel.kind === 'police' && <PoliceDetail id={sel.id} />}</>
  }
  return <aside className="inspector" aria-label="Inspector">
    <div className="panel-head"><span className="kicker">{sel.kind}</span><button className="icon-button" title="Close (Esc)" onClick={() => actions.deselect()}><Icon.close /></button></div>
    <div className="panel-body">{body}</div>
  </aside>
}

function PoliceDetail({ id }: { id: string }) {
  const [ev, setEv] = useState<Record<string, unknown> | null>(null)
  useEffect(() => { void import('../core/api').then(({ api }) => api.police()).then(r => setEv((r.items ?? []).find(x => String(x.id) === id) ?? null)).catch(() => undefined) }, [id])
  if (!ev) return null
  return <><div className="note body">{String(ev.summary ?? '')}</div>
    <div className="facts"><Fact k="Time" v={fmtTime(ev.datetime as string)} /><Fact k="Location" v={String(ev.locationName ?? '—')} /><Fact k="Precision" v={String(ev.precision ?? '—')} /></div>
    {typeof ev.url === 'string' && <small className="quiet">Full text: <span className="mono">{ev.url}</span></small>}</>
}
