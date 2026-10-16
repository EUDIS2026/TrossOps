import type { Intervention, InterventionOption } from '../contracts/types'
import { actions, useApp } from '../core/store'
import { useRuntime } from './context'
import { Icon } from './icons'
import { AlertRow } from './Inspector'

export function OptionCard({ iv, o, onCommit, disabled }: { iv: Intervention; o: InterventionOption; onCommit: () => void; disabled: boolean }) {
  const recommended = iv.recommendedOptionId === o.id
  const committed = iv.committedOptionId === o.id
  return <div className="option" data-recommended={recommended} data-committed={committed}>
    <div className="option-head"><strong>{o.title}</strong>{committed ? <span className="tag own">committed</span> : recommended ? <span className="tag advisory">recommended</span> : null}</div>
    <div className="option-meta">
      <span>success <b>{Math.round(o.successLikelihood * 100)} %</b></span>
      <span>time to effect <b>{o.etaMin === null ? '—' : `${Math.round(o.etaMin)} min`}</b></span>
      {o.distanceKm !== null && <span>distance <b>{o.distanceKm} km</b></span>}
      <span>risk <b>{o.riskLevel}</b></span>
    </div>
    <div className="bands">{o.outcomes.map(b => <div key={b.label} className={`band ${b.label}`}><b>{Math.round(b.probability * 100)} %</b>{b.label} · {Math.round(b.timeToEffectMin)} min</div>)}</div>
    <small style={{ display: 'block', marginBottom: 6 }}>{o.rationale}</small>
    <ol className="steps">{o.steps.map(s => <li key={s}>{s}</li>)}</ol>
    <div className="actions" style={{ padding: 0 }}>
      {o.assignedEntityIds.map(id => <button key={id} className="btn small" onClick={() => actions.select('entity', id)}>{id}</button>)}
      {!committed && <button className="btn small primary" disabled={disabled} onClick={onCommit}><Icon.check width={14} height={14} /> Commit</button>}
    </div>
  </div>
}

export function Decisions() {
  const open = useApp(s => s.panels.decisions)
  const snap = useApp(s => s.snapshot)
  const plan = useApp(s => s.plan)
  const busy = useApp(s => s.busy)
  const sel = useApp(s => s.selected)
  const rt = useRuntime()
  const ivs = snap?.interventions ?? []
  const open_ = ivs.filter(i => i.status === 'proposed')
  const active = ivs.filter(i => i.status !== 'proposed')
  const planFresh = plan && snap && plan.worldRevision === snap.worldRevision
  return <aside className={`panel floating ${open ? '' : 'hidden'}`} aria-label="Decisions" aria-hidden={!open}>
    <div className="panel-head"><h2>Decisions</h2><button className="icon-button" title="Close" onClick={() => actions.setPanel('decisions', false)}><Icon.close /></button></div>
    <div className="panel-body">
      <div className="actions" style={{ paddingTop: 0 }}>
        <button className="btn primary" disabled={busy || !open_.length} onClick={() => void rt?.session.optimise()}><Icon.sparkle width={14} height={14} /> Optimise the plan</button>
        <span className="quiet">{open_.length} proposed · {active.length} active</span>
      </div>
      {plan && <div className="section">
        <h4>Optimised assignment <span>{planFresh ? `objective ${plan.objective?.toFixed(2)}` : 'stale — re-run'}</span></h4>
        {plan.plan.map(row => { const iv = ivs.find(i => i.id === row.interventionId); const opt = iv?.options.find(o => o.id === row.optionId)
          return <div key={row.interventionId} className="plan-row"><span>{iv?.title ?? row.interventionId}<br /><small>{row.unassigned ? 'left unassigned' : opt?.title}</small></span><b>{row.cost.toFixed(2)}</b></div> })}
        {plan.alternatives.map(alt => <div key={alt.name} className="plan-row"><span>{alt.name}<br /><small>same interventions, different rule</small></span><b>{alt.objective.toFixed(2)}</b></div>)}
        <small className="quiet">{plan.explanation}</small>
        <div className="actions" style={{ padding: '6px 0 0' }}>
          {planFresh && plan.plan.filter(r => r.optionId).map(r => <button key={r.interventionId} className="btn small" disabled={busy} onClick={() => void rt?.session.commit(r.interventionId, r.optionId!)}>Commit {r.interventionId.replace('iv-', '')}</button>)}
        </div>
      </div>}
      {active.length > 0 && <div className="section"><h4>In progress <span>{active.length}</span></h4><div className="list">
        {active.map(iv => <button key={iv.id} className="item" aria-selected={sel?.id === iv.id} onClick={() => actions.select('intervention', iv.id)}><span className="dot info" /><span><strong>{iv.title}</strong><small>{iv.status.replace('_', ' ')} · {Math.round(iv.progress * 100)} %</small><div className="progress"><i style={{ width: `${iv.progress * 100}%` }} /></div></span><span className="when" /></button>)}
      </div></div>}
      <div className="section"><h4>Proposed <span>{open_.length}</span></h4><div className="list">
        {open_.map(iv => { const a = snap?.alerts.find(x => x.id === iv.alertId); const best = iv.options.find(o => o.id === iv.recommendedOptionId)
          return <button key={iv.id} className="item" aria-selected={sel?.id === iv.id} onClick={() => actions.select('intervention', iv.id)}><span className={`dot ${a?.severity ?? 'info'}`} /><span><strong>{iv.title}</strong><small>{best ? `${best.title} · ${Math.round(best.successLikelihood * 100)} % · ${best.etaMin === null ? '—' : Math.round(best.etaMin) + ' min'}` : 'no feasible option'}</small></span><span className="when">{iv.options.length} opt.</span></button> })}
        {!open_.length && <div className="quiet">No open interventions. Alerts that need action will propose one here.</div>}
      </div></div>
      {snap && <div className="section"><h4>Alerts without a proposal</h4><div className="list">{snap.alerts.filter(a => !a.recommendedInterventionId && !a.acknowledged).slice(0, 6).map(a => <AlertRow key={a.id} a={a} />)}</div></div>}
    </div>
  </aside>
}
