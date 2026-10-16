import { actions, EMPTY_OBJ, layerOn, useApp, type Basemap } from '../core/store'
import { useRuntime } from './context'
import { Icon } from './icons'

export function LayerRail() {
  const open = useApp(s => s.panels.layers)
  const views = useApp(s => s.views)
  const state = useApp(s => s)
  const attention = useApp(s => s.snapshot?.layerAttention ?? EMPTY_OBJ)
  const att = useApp(s => s.attention)
  const rt = useRuntime()
  const groups = new Map<string, typeof views extends null ? never : NonNullable<typeof views>['layers']>()
  for (const l of views?.layers ?? []) groups.set(l.group, [...(groups.get(l.group) ?? []), l])
  const basemaps: { id: Basemap; label: string }[] = [{ id: 'operational', label: 'Dark' }, { id: 'satellite', label: 'Imagery' }, { id: 'offline', label: 'Offline' }]
  return <aside className={`panel rail ${open ? '' : 'hidden'}`} aria-label="Layers" aria-hidden={!open}>
    <div className="panel-head">
      <h2>Layers</h2>
      <div style={{ display: 'flex', gap: 4 }}>
        <button className="icon-button" title="Reset view" onClick={() => rt?.scene.resetOverview()}><Icon.target /></button>
        <button className="icon-button" title="Close" onClick={() => actions.setPanel('layers', false)}><Icon.close /></button>
      </div>
    </div>
    <div className="panel-body">
      <div className="group-title"><span>Map</span></div>
      <div className="actions" style={{ paddingTop: 0 }}>
        {basemaps.map(b => <button key={b.id} className="btn small" aria-pressed={state.basemap === b.id} onClick={() => actions.setBasemap(b.id)}>{b.label}</button>)}
        <button className="btn small" aria-pressed={state.terrain} disabled={state.basemap === 'offline'} onClick={() => actions.toggleTerrain()} title="Mapterhorn elevation (public)"><Icon.mountain width={14} height={14} /> Terrain</button>
        <button className="btn small" aria-pressed={state.threeD} onClick={() => actions.toggle3d()}><Icon.cube width={14} height={14} /> 3D</button>
      </div>
      {[...groups.entries()].map(([group, layers]) => <div key={group}>
        <div className="group-title"><span>{group}</span></div>
        {layers.map(l => {
          const on = layerOn(state, l.id)
          const a = attention[l.id]
          return <button key={l.id} className="layer-row" role="switch" aria-checked={on} onClick={() => actions.toggleLayer(l.id)} title={l.description}>
            <span>
              <span className="name">{l.label}{a && !on && <span className={`dot ${a.severity}`} title={`${a.count} alerts touch this layer`} />}</span>
              <small>{l.description}</small>
            </span>
            <span className="switch-wrap">
              <span className="switch" data-on={on} />
              {a && on && <span className={`dot ${a.severity}`} title={`${a.count} unacknowledged alerts on this layer`} />}
            </span>
          </button>
        })}
      </div>)}
      {layerOn(state, 'attention') && <div className="legend">
        <div className="legend-row"><span>Attention surface</span><span>{att ? `${att.resolution} · ${att.cells.length} cells` : '—'}</span></div>
        <div className="legend-bar" />
        <div className="legend-row"><span>0</span><span>peak {att?.maxScore.toFixed(1) ?? '—'}</span></div>
        <small>Unit: {att?.unit ?? 'attention weight'}. Click a cell to see which rules and inputs raised it.</small>
      </div>}
      <div className="legend">
        <div className="swatches">
          <span className="swatch"><i style={{ background: 'var(--own)' }} />Own</span>
          <span className="swatch"><i style={{ background: 'var(--allied)' }} />Allied</span>
          <span className="swatch"><i style={{ background: '#aeb8c2' }} />Civil</span>
          <span className="swatch"><i style={{ borderColor: 'var(--unknown)', background: 'rgba(227,139,199,0.2)' }} />Unknown</span>
          <span className="swatch"><i style={{ borderColor: 'var(--warning)' }} />Degraded ring</span>
          <span className="swatch"><i style={{ borderColor: 'var(--critical)' }} />Unavailable</span>
          <span className="swatch"><i style={{ background: 'none', borderStyle: 'dashed', borderColor: 'var(--unknown)' }} />Predicted</span>
          <span className="swatch"><i style={{ background: 'none', borderStyle: 'dotted' }} />Planned</span>
        </div>
      </div>
      <button className="layer-row" role="switch" aria-checked={state.trailsForAll} onClick={() => { actions.setTrailsForAll(!state.trailsForAll); void rt?.scene.refreshTrails() }}>
        <span><span className="name">Trails for every unit</span><small>Default: selected unit and unknown tracks</small></span>
        <span className="switch" data-on={state.trailsForAll} />
      </button>
    </div>
  </aside>
}
