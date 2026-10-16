import { useEffect, useRef } from 'react'
import type { Alert, InputReport, Intervention, SceneEntity } from '../contracts/types'
import { actions, EMPTY, useApp } from '../core/store'
import { drawIcon, modelKeyFor } from '../scene/semantics'
import { channelLabel, fmtTime, kindLabel, pct, useRuntime } from './context'
import { Icon } from './icons'
import { OptionCard } from './Decisions'

function EntityGlyph({ e }: { e: SceneEntity }) {
  const ref = useRef<HTMLCanvasElement>(null)
  useEffect(() => {
    const c = ref.current; if (!c) return
    const img = drawIcon({ modelKey: modelKeyFor(e.kind, e.modelKey), affiliation: e.affiliation, condition: e.condition })
    c.width = img.width; c.height = img.height
    c.getContext('2d')!.putImageData(img, 0, 0)
  }, [e.kind, e.modelKey, e.affiliation, e.condition])
  return <canvas ref={ref} aria-hidden />
}

function Ring({ score }: { score: number }) {
  const color = score >= 0.7 ? 'var(--good)' : score >= 0.45 ? 'var(--warning)' : 'var(--critical)'
  return <div className="ring" style={{ background: `conic-gradient(${color} ${score * 360}deg, rgba(255,255,255,0.08) 0)` }}><span>{Math.round(score * 100)}</span></div>
}

export function AlertRow({ a, selected }: { a: Alert; selected?: boolean }) {
  const rt = useRuntime()
  return <button className={`item ${a.acknowledged ? 'ack' : ''}`} aria-selected={selected} onClick={() => actions.select('alert', a.id)}>
    <span className={`dot ${a.severity}`} />
    <span><strong>{a.title}</strong><small>{a.ruleId} · {a.entityIds.length} entities{a.recommendedInterventionId ? ' · intervention proposed' : ''}</small></span>
    <span className="when">{a.acknowledged ? 'seen' : <span role="button" tabIndex={0} className="btn small" onClick={e => { e.stopPropagation(); void rt?.session.ack(a.id) }} onKeyDown={e => { if (e.key === 'Enter') { e.stopPropagation(); void rt?.session.ack(a.id) } }}>Ack</span>}</span>
  </button>
}

export function InputRow({ i, selected }: { i: InputReport; selected?: boolean }) {
  return <button className="item" aria-selected={selected} onClick={() => actions.select('input', i.id)}>
    <span className={`dot ${i.severity}`} />
    <span><strong>{i.title}</strong><small>{channelLabel[i.channel]} · {i.author}</small></span>
    <span className="when">{fmtTime(i.effectiveAt)}</span>
  </button>
}

function EntityView({ e }: { e: SceneEntity }) {
  const detail = useApp(s => s.detail)
  const follow = useApp(s => s.follow)
  const busy = useApp(s => s.busy)
  const replay = useApp(s => s.time.mode === 'replay')
  const rt = useRuntime()
  const r = e.readiness
  const mobile = !['facility', 'infrastructure'].includes(e.kind)
  const pos = e.position
  const k = e.kinematics
  return <>
    <div className="ent-head"><EntityGlyph e={e} /><div><h3>{e.label}</h3><p>{kindLabel[e.kind]}{e.unit ? ` · ${e.unit}` : ''}</p></div></div>
    <div className="tags">
      <span className={`tag ${e.affiliation}`}>{e.affiliation.replace('_', ' ')}</span>
      <span className={`tag ${e.condition}`}>{e.condition}</span>
      <span className={`tag ${e.sourceKind}`}>{e.sourceKind}</span>
      {e.stale && <span className="tag warning">stale</span>}
      {e.capabilities.map(c => <span key={c} className="tag">{c.replace('_', ' ')}</span>)}
    </div>
    {r && e.affiliation !== 'unknown' && <div className="readiness">
      <Ring score={r.score} />
      <div className="facts">
        <div className="fact"><small>Fuel</small><b className={r.fuelPct !== null && r.fuelPct < 30 ? 'warn' : ''}>{pct(r.fuelPct)}</b></div>
        <div className="fact"><small>Ammunition</small><b>{pct(r.ammunitionPct)}</b></div>
        <div className="fact"><small>Crew</small><b>{r.crewPresent ?? '—'}{r.crewRequired ? ` / ${r.crewRequired}` : ''}</b></div>
        <div className="fact"><small>Comms</small><b className={r.commsStatus === 'lost' ? 'crit' : r.commsStatus === 'degraded' ? 'warn' : ''}>{r.commsStatus}</b></div>
        <div className="fact"><small>Maintenance due</small><b>{r.maintenanceDueH === null ? '—' : `${r.maintenanceDueH} h`}</b></div>
        <div className="fact"><small>Last report</small><b>{fmtTime(r.lastReportAt)}</b></div>
      </div>
    </div>}
    <div className="facts" style={{ padding: '0 6px' }}>
      <div className="fact"><small>Position</small><b>{pos ? `${pos.latitudeDeg.toFixed(4)}, ${pos.longitudeDeg.toFixed(4)}` : 'unknown'}</b></div>
      <div className="fact"><small>Altitude</small><b>{pos?.altitudeM === null || pos?.altitudeM === undefined ? 'not reported' : `${pos.altitudeM} m ${pos.altitudeDatum}`}</b></div>
      {mobile && <div className="fact"><small>Heading</small><b>{k?.headingDeg === null || k?.headingDeg === undefined ? '—' : `${k.headingDeg.toFixed(0)}°`}</b></div>}
      {mobile && <div className="fact"><small>Speed</small><b>{k?.speedMps === null || k?.speedMps === undefined ? '—' : `${k.speedMps.toFixed(0)} m/s`}</b></div>}
      {pos?.horizontalAccuracyM && <div className="fact"><small>Position accuracy</small><b>± {pos.horizontalAccuracyM} m</b></div>}
      <div className="fact"><small>Observed</small><b>{fmtTime(e.observedAt)}</b></div>
    </div>
    {(r?.faults.length || r?.notes.length) ? <div className="section"><h4>Faults and notes</h4><div className="list">
      {r.faults.map(f => <div key={f} className="note">{f}</div>)}{r.notes.map(n => <div key={n} className="note">{n}</div>)}
    </div></div> : null}
    <div className="actions">
      {mobile && <button className="btn small" aria-pressed={follow} disabled={replay} onClick={() => actions.toggleFollow()}><Icon.target width={14} height={14} /> {follow ? 'Following' : 'Follow'}</button>}
      {e.affiliation === 'own' && <>
        {e.condition !== 'unavailable' ? <button className="btn small danger" disabled={busy || replay} onClick={() => void rt?.session.event(e.id, 'fault')}>Record fault</button>
          : <button className="btn small" disabled={busy || replay} onClick={() => void rt?.session.event(e.id, 'repair')}>Record repair</button>}
        <button className="btn small" disabled={busy || replay} onClick={() => void rt?.session.event(e.id, 'resupply')}>Record resupply</button>
        {r?.commsStatus === 'lost' ? <button className="btn small" disabled={busy || replay} onClick={() => void rt?.session.event(e.id, 'comms_restored')}>Comms restored</button>
          : <button className="btn small" disabled={busy || replay} onClick={() => void rt?.session.event(e.id, 'comms_loss')}>Comms lost</button>}
      </>}
    </div>
    {e.track && <div className="section"><h4>Declared movement <span>planned</span></h4><div className="note">{e.track.waypoints.length} waypoints at {e.track.speedMps} m/s{e.track.loop ? ', repeating' : ''}, starts at scenario second {e.track.startAtS}.</div></div>}
    {detail?.entity.id === e.id && <>
      {detail.predictions.length > 0 && <div className="section"><h4>Prediction <span>dead reckoning</span></h4>
        {detail.predictions.map(p => <div key={p.entityId + p.method} className="note">{p.entityId === e.id ? `${p.method}. ` : `On the predicted path of ${p.entityId}. `}{p.etaS !== null ? `Closest approach to own assets in ${Math.round(p.etaS / 60)} min.` : 'No own asset within the 30 min horizon.'}{p.threatenedEntityIds.length ? ` Affected: ${p.threatenedEntityIds.join(', ')}.` : ''}</div>)}
      </div>}
      {detail.alerts.length > 0 && <div className="section"><h4>Alerts <span>{detail.alerts.length}</span></h4><div className="list">{detail.alerts.map(a => <AlertRow key={a.id} a={a} />)}</div></div>}
      {detail.interventions.length > 0 && <div className="section"><h4>Interventions <span>{detail.interventions.length}</span></h4>
        {detail.interventions.map(iv => <button key={iv.id} className="item" onClick={() => { actions.select('intervention', iv.id); actions.setPanel('decisions', true) }}><span className="dot advisory" /><span><strong>{iv.title}</strong><small>{iv.status} · {iv.options.length} options</small></span><span className="when" /></button>)}
      </div>}
      {detail.inputs.length > 0 && <div className="section"><h4>Reports <span>{detail.inputs.length}</span></h4><div className="list">{[...detail.inputs].reverse().slice(0, 8).map(i => <InputRow key={i.id} i={i} />)}</div></div>}
      {detail.areas.length > 0 && <div className="section"><h4>Required by</h4><div className="actions" style={{ padding: 0 }}>{detail.areas.map(a => <button key={a} className="btn small" onClick={() => actions.select('area', a)}>{a}</button>)}</div></div>}
      {detail.events.length > 0 && <div className="section"><h4>Recorded events</h4><div className="list">{detail.events.map(ev => <div key={ev.id} className="note">{ev.kind} at revision {ev.worldRevision}, {fmtTime(ev.recordedAt)}</div>)}</div></div>}
    </>}
  </>
}

function InputView({ i }: { i: InputReport }) {
  const allAlerts = useApp(s => s.snapshot?.alerts ?? EMPTY)
  const alerts = allAlerts.filter(a => a.inputIds.includes(i.id))
  return <>
    <div className="ent-head"><div className="ent-icon" style={{ display: 'grid', placeItems: 'center' }}><span className={`dot ${i.severity}`} style={{ width: 12, height: 12 }} /></div><div><h3>{i.title}</h3><p>{channelLabel[i.channel]} · {i.author}</p></div></div>
    <div className="tags"><span className={`tag ${i.severity}`}>{i.severity}</span><span className={`tag ${i.sourceKind}`}>{i.sourceKind}</span><span className="tag">{i.authorLevel.replace('_', ' ')}</span>{i.tags.map(t => <span key={t} className="tag">{t}</span>)}</div>
    <div className="note" style={{ fontSize: 13, color: 'var(--text)' }}>{i.text}</div>
    <div className="facts" style={{ padding: '10px 6px 0' }}>
      <div className="fact"><small>Effective</small><b>{fmtTime(i.effectiveAt)}</b></div>
      <div className="fact"><small>Received</small><b>{fmtTime(i.receivedAt)}</b></div>
      <div className="fact"><small>Location</small><b>{i.position ? `${i.position.latitudeDeg.toFixed(3)}, ${i.position.longitudeDeg.toFixed(3)}` : 'not geolocated'}</b></div>
      <div className="fact"><small>Radius</small><b>{i.radiusM ? `${(i.radiusM / 1000).toFixed(0)} km` : '—'}</b></div>
    </div>
    {i.entityRefs.length > 0 && <div className="section"><h4>Referenced entities</h4><div className="actions" style={{ padding: 0 }}>{i.entityRefs.map(id => <button key={id} className="btn small" onClick={() => actions.select('entity', id)}>{id}</button>)}</div></div>}
    {alerts.length > 0 && <div className="section"><h4>Rules that fired <span>{alerts.length}</span></h4><div className="list">{alerts.map(a => <AlertRow key={a.id} a={a} />)}</div></div>}
  </>
}

function AlertView({ a }: { a: Alert }) {
  const allIvs = useApp(s => s.snapshot?.interventions ?? EMPTY)
  const allInputs = useApp(s => s.snapshot?.inputs ?? EMPTY)
  const ivs = allIvs.filter(iv => iv.alertId === a.id)
  const inputs = allInputs.filter(i => a.inputIds.includes(i.id))
  const rule = useApp(s => s.views?.rules.find(r => r.id === a.ruleId))
  const rt = useRuntime()
  return <>
    <div className="ent-head"><div className="ent-icon" style={{ display: 'grid', placeItems: 'center' }}><span className={`dot ${a.severity}`} style={{ width: 12, height: 12 }} /></div><div><h3>{a.title}</h3><p>{a.ruleId} {rule ? `· ${rule.title}` : ''}</p></div></div>
    <div className="tags"><span className={`tag ${a.severity}`}>{a.severity}</span>{a.acknowledged && <span className="tag">acknowledged</span>}{a.layerIds.map(l => <span key={l} className="tag">{l.replace('_', ' ')}</span>)}</div>
    <div className="note" style={{ fontSize: 13, color: 'var(--text)' }}>{a.detail}</div>
    <div className="actions">{!a.acknowledged && <button className="btn small primary" onClick={() => void rt?.session.ack(a.id)}><Icon.check width={14} height={14} /> Acknowledge</button>}{a.entityIds.slice(0, 6).map(id => <button key={id} className="btn small" onClick={() => actions.select('entity', id)}>{id}</button>)}</div>
    {ivs.map(iv => <InterventionBlock key={iv.id} iv={iv} />)}
    {inputs.length > 0 && <div className="section"><h4>Derived from <span>{inputs.length} reports</span></h4><div className="list">{inputs.map(i => <InputRow key={i.id} i={i} />)}</div></div>}
  </>
}

export function InterventionBlock({ iv }: { iv: Intervention }) {
  const rev = useApp(s => s.snapshot?.worldRevision ?? 1)
  const busy = useApp(s => s.busy)
  const replay = useApp(s => s.time.mode === 'replay')
  const rt = useRuntime()
  return <div className="section">
    <h4>{iv.title} <span>{iv.status.replace('_', ' ')}</span></h4>
    <div className="note">{iv.objective}</div>
    {iv.status !== 'proposed' && <div className="progress" aria-label="Progress"><i style={{ width: `${iv.progress * 100}%` }} /></div>}
    {iv.monitorAlerts.length > 0 && <div className="note">{iv.monitorAlerts[iv.monitorAlerts.length - 1]}</div>}
    <div style={{ marginTop: 8 }}>
      {iv.options.map(o => <OptionCard key={o.id} iv={iv} o={o} onCommit={() => void rt?.session.commit(iv.id, o.id)} disabled={busy || replay || iv.status !== 'proposed'} />)}
    </div>
    {iv.status !== 'proposed' && iv.status !== 'completed' && <div className="actions"><button className="btn small danger" disabled={busy || replay} onClick={() => void rt?.session.abort(iv.id)}>Abort and re-plan</button></div>}
    <small className="quiet">Revision {rev}. Options are ranked by success likelihood, then time to effect.</small>
  </div>
}

function CellView({ cellKey }: { cellKey: string }) {
  const att = useApp(s => s.attention)
  const cell = att?.cells.find(c => c.key === cellKey)
  if (!cell) return <div className="quiet">This cell is no longer in the attention surface at the current resolution.</div>
  return <>
    <div className="ent-head"><div className="ent-icon" style={{ background: 'linear-gradient(135deg, rgba(255,150,70,0.3), rgba(255,74,53,0.8))' }} /><div><h3>Attention {cell.score.toFixed(2)}</h3><p>{att?.resolution} cell · peak contribution {cell.peak.toFixed(2)}</p></div></div>
    <div className="section"><h4>Why</h4><div className="list">{cell.reasons.map(r => <div key={r} className="note">{r}</div>)}</div></div>
    <div className="section"><h4>Contributors</h4><div className="actions" style={{ padding: 0 }}>{cell.contributors.map(c => <button key={c} className="btn small" onClick={() => actions.select(c.startsWith('in-') ? 'input' : 'entity', c)}>{c}</button>)}</div></div>
    <div className="note">Score = Σ rule weight × distance kernel over contributions within the cell. Centre {cell.center[1].toFixed(2)}, {cell.center[0].toFixed(2)}.</div>
  </>
}

function AreaView({ id }: { id: string }) {
  const area = useApp(s => s.snapshot?.areas.find(a => a.id === id))
  const priority = useApp(s => s.snapshot?.priorities[id])
  if (!area) return null
  return <>
    <div className="ent-head"><div className="ent-icon" /><div><h3>{area.label}</h3><p>{area.kind.replace('_', ' ')}</p></div></div>
    <div className="tags"><span className={`tag ${area.status === 'covered' ? 'own' : area.status === 'degraded' ? 'warning' : area.status === 'uncovered' ? 'critical' : ''}`}>{area.status}</span>{priority && priority !== 1 && <span className="tag warning">priority ×{priority.toFixed(1)}</span>}</div>
    {area.blockers.length > 0 && <div className="section"><h4>Blockers</h4><div className="list">{area.blockers.map(b => <div key={b} className="note">{b}</div>)}</div></div>}
    {area.requires.length > 0 && <div className="section"><h4>Requires</h4><div className="actions" style={{ padding: 0 }}>{area.requires.map(r => <button key={r} className="btn small" onClick={() => actions.select('entity', r)}>{r}</button>)}</div></div>}
    {area.kind === 'coverage_model' && <div className="note">Modelled coverage: a nominal radius, not a measured sensor footprint.</div>}
  </>
}

export function Inspector() {
  const sel = useApp(s => s.selected)
  const open = useApp(s => s.panels.inspector && !!s.selected)
  const snap = useApp(s => s.snapshot)
  let body: React.ReactNode = null
  let title = 'Inspector'
  if (sel && snap) {
    if (sel.kind === 'entity') { const e = snap.entities.find(x => x.id === sel.id); body = e ? <EntityView e={e} /> : <div className="quiet">This entity is outside the current role's scope.</div>; title = 'Entity' }
    if (sel.kind === 'input') { const i = snap.inputs.find(x => x.id === sel.id); body = i ? <InputView i={i} /> : null; title = 'Report' }
    if (sel.kind === 'alert') { const a = snap.alerts.find(x => x.id === sel.id); body = a ? <AlertView a={a} /> : null; title = 'Alert' }
    if (sel.kind === 'intervention') { const iv = snap.interventions.find(x => x.id === sel.id); body = iv ? <InterventionBlock iv={iv} /> : null; title = 'Intervention' }
    if (sel.kind === 'cell') { body = <CellView cellKey={sel.id} />; title = 'Attention' }
    if (sel.kind === 'area') { body = <AreaView id={sel.id} />; title = 'Area' }
  }
  return <aside className={`panel inspector ${open ? '' : 'hidden'}`} aria-label={title} aria-hidden={!open}>
    <div className="panel-head"><h2>{title}</h2><button className="icon-button" title="Close (Esc)" onClick={() => actions.deselect()}><Icon.close /></button></div>
    <div className="panel-body">{body}</div>
  </aside>
}
