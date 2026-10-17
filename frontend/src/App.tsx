import { useEffect, useRef, useState } from 'react'
import { Session } from './core/session'
import { actions, store, useApp, type Panel } from './core/store'
import { SceneController } from './scene/controller'
import { RuntimeContext, type Runtime } from './ui/context'
import { Dock, Drawer } from './ui/Dock'
import { Inspector } from './ui/Inspector'
import { HoverCard, Kpis, Legend, RouteBanner, Timeline, Toasts } from './ui/Overlays'
import { TopBar } from './ui/TopBar'
import { MapToolsLayer } from './ui/tools/ToolsControl'

const KEYS: Record<string, Panel> = { l: 'layers', a: 'feed', d: 'decisions', s: 'scenario', r: 'report', i: 'sources', '?': 'help' }

function useShortcuts(rt: Runtime | null) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') { if (e.key === 'Escape') (e.target as HTMLElement).blur(); return }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      // Space and Enter belong to a focused control (button, switch, tab), not to the clock
      if ((e.key === ' ' || e.key === 'Enter') && (e.target as HTMLElement)?.closest?.('button, [role="button"], a')) return
      const k = e.key.toLowerCase()
      if (k === '/') { e.preventDefault(); (document.querySelector('.search input') as HTMLInputElement | null)?.focus(); return }
      if (KEYS[k]) { actions.togglePanel(KEYS[k]); return }
      if (k === '3') actions.toggle3d()
      else if (k === 'f' && store.get().selected) actions.toggleFollow()
      else if (k === ' ') { e.preventDefault(); const c = rt?.session.clock; if (!c) return; if (c.mode === 'sim' && !c.paused) rt.session.pause(); else if (c.mode === 'sim') rt.session.resume(); else rt.session.pause() }
      else if (e.key === 'Home') rt?.scene.flyToMode()
      else if (e.key === 'Escape') {
        const s = store.get()
        if (s.route) { actions.cancelRoute(); return }
        const open = (Object.keys(s.panels) as Panel[]).find(p => s.panels[p])
        if (open) actions.setPanel(open, false); else actions.deselect()
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rt])
}

export function App() {
  const mapRef = useRef<HTMLDivElement>(null)
  const [rt, setRt] = useState<Runtime | null>(null)
  const inspector = useApp(s => !!s.selected)
  const drawer = useApp(s => Object.entries(s.panels).some(([k, v]) => v && k !== 'search'))
  useEffect(() => {
    if (!mapRef.current) return
    const session = new Session()
    const scene = new SceneController(mapRef.current, session)
    setRt({ session, scene })
    return () => { scene.dispose(); session.dispose() }
  }, [])
  useShortcuts(rt)
  return <RuntimeContext.Provider value={rt}>
    <div className={`app ${inspector ? 'with-inspector' : ''} ${drawer ? 'with-drawer' : ''}`}>
      <div className="map-root" ref={mapRef} aria-label="Operational map" role="application" />
      <TopBar />
      <Kpis />
      <Dock />
      <Drawer />
      <Inspector />
      <Legend />
      <RouteBanner />
      <HoverCard />
      <Timeline />
      <Toasts />
      <MapToolsLayer />
    </div>
  </RuntimeContext.Provider>
}
