import { useEffect, useRef, useState } from 'react'
import { Session } from './core/session'
import { actions, store, useApp } from './core/store'
import { SceneController } from './scene/controller'
import { RuntimeContext, type Runtime } from './ui/context'
import { Decisions } from './ui/Decisions'
import { Inspector } from './ui/Inspector'
import { Kpis } from './ui/Kpis'
import { LayerRail } from './ui/LayerRail'
import { AlertsPanel, DataNotice, ErrorToast, HelpPanel, ReportComposer, SearchPalette, Timeline } from './ui/Panels'
import { TopBar } from './ui/TopBar'

function useShortcuts(rt: Runtime | null) {
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName
      if (tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT') { if (e.key === 'Escape') (e.target as HTMLElement).blur(); return }
      if (e.metaKey || e.ctrlKey || e.altKey) return
      switch (e.key) {
        case '/': e.preventDefault(); actions.togglePanel('search'); break
        case 'l': case 'L': actions.togglePanel('layers'); break
        case 'a': case 'A': actions.togglePanel('alerts'); break
        case 'd': case 'D': actions.togglePanel('decisions'); break
        case 'r': case 'R': actions.togglePanel('inputs'); break
        case '3': actions.toggle3d(); break
        case 'f': case 'F': if (store.get().selected?.kind === 'entity') actions.toggleFollow(); break
        case '?': actions.togglePanel('help'); break
        case 'Home': rt?.scene.resetOverview(); break
        case 'Escape': {
          const s = store.get()
          const openFloating = (['search', 'alerts', 'decisions', 'inputs', 'help'] as const).find(p => s.panels[p])
          if (openFloating) actions.setPanel(openFloating, false); else actions.deselect()
          break
        }
      }
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [rt])
}

export function App() {
  const mapRef = useRef<HTMLDivElement>(null)
  const [rt, setRt] = useState<Runtime | null>(null)
  const inspectorOpen = useApp(s => s.panels.inspector && !!s.selected)
  useEffect(() => {
    if (!mapRef.current) return
    const scene = new SceneController(mapRef.current)
    const session = new Session(scene)
    setRt({ scene, session })
    return () => { session.dispose(); scene.dispose() }
  }, [])
  useShortcuts(rt)
  return <RuntimeContext.Provider value={rt}>
    <div className={`app ${inspectorOpen ? 'inspector-open' : ''}`}>
      <div className="map-root" ref={mapRef} aria-label="Operational map" role="application" />
      <TopBar />
      <Kpis />
      <LayerRail />
      <Inspector />
      <AlertsPanel />
      <Decisions />
      <ReportComposer />
      <SearchPalette />
      <HelpPanel />
      <Timeline />
      <DataNotice />
      <ErrorToast />
    </div>
  </RuntimeContext.Provider>
}
