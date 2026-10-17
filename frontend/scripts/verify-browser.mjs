/**
 * Browser acceptance run (v2). Requires the API on :8000 and the UI on :5173 (dev) or the URL in TROSSOPS_UI.
 * Usage: node scripts/verify-browser.mjs [outputDir]
 * Writes screenshots and a JSON results ledger; exits non-zero on any failed step. Each step drives the real UI
 * (or the runtime handles the app exposes for verification: __store, __session, __scene, __map) and asserts on
 * what was actually rendered, not on what the API returned.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const pw = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const out = resolve(process.argv[2] || 'test-results')
mkdirSync(out, { recursive: true })
const ui = process.env.TROSSOPS_UI || 'http://127.0.0.1:5173/'
const launch = { headless: !process.env.HEADED, args: process.env.SOFTWARE_GL ? ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : ['--ignore-gpu-blocklist'] }
if (process.env.BROWSER_CHANNEL) launch.channel = process.env.BROWSER_CHANNEL
const browser = await pw.chromium.launch(launch)
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
const pageErrors = []
page.on('pageerror', e => pageErrors.push(String(e)))
page.on('console', m => { if (m.type() === 'error' && !/ERR_|Failed to load resource|404/.test(m.text())) pageErrors.push('console: ' + m.text().slice(0, 240)) })

const results = []
const wait = ms => page.waitForTimeout(ms)
const run = (fn, arg) => page.evaluate(fn, arg)
const shot = n => page.screenshot({ path: `${out}/${n}.png` })
const reset = async () => { await run(() => window.__store.set({ selected: null, route: null, panels: Object.fromEntries(Object.keys(window.__store.get().panels).map(k => [k, false])) })); await wait(300) }
const step = async (id, name, fn) => {
  const t0 = Date.now()
  await reset()
  try { const detail = await fn(); results.push({ id, name, status: 'pass', ms: Date.now() - t0, detail }); console.log(`PASS ${id} ${name}`, JSON.stringify(detail ?? '').slice(0, 200)) }
  catch (e) { results.push({ id, name, status: 'fail', ms: Date.now() - t0, error: String(e).slice(0, 500) }); console.log(`FAIL ${id} ${name}: ${String(e).slice(0, 400)}`) }
}
const expect = (cond, info) => { if (!cond) throw new Error(JSON.stringify(info)) }
const role = async (roleId, modeId, extra = {}) => { await run(([r, m, x]) => window.__store.set({ roleId: r, modeId: m, layerOverrides: {}, ...x }), [roleId, modeId, extra]); await wait(3500) }

await page.goto(ui, { waitUntil: 'load' })
await page.waitForFunction(() => window.__session?.world && window.__store?.get().snapshot, null, { timeout: 45000 })
await wait(4000)

await step('E2E-01', 'National picture loads from the live API', async () => {
  const info = await run(() => ({ entities: window.__session.world.nodes.length, drawn: window.__scene.drawn.length, stream: window.__store.get().stream, kpis: document.querySelectorAll('.kpi').length,
    attribution: document.querySelector('.maplibregl-ctrl-attrib')?.textContent?.slice(0, 60) }))
  expect(info.entities > 1000 && info.drawn > 20 && info.kpis >= 3, info)
  await shot('01-national'); return info
})

await step('E2E-02', 'Echelon aggregation stays inside the symbol budget and resolves to vehicles when zoomed', async () => {
  await run(() => window.__map.jumpTo({ center: [16.5, 61.5], zoom: 4.8, pitch: 0, bearing: 0 })); await wait(1500)
  const far = await run(() => ({ drawn: window.__scene.drawn.length, aggregates: window.__scene.drawn.filter(d => d.kind === 'formation').length }))
  await run(() => { const w = window.__session.world; const n = w.get('coy-n1a-05'); const p = w.poseNow(n); window.__map.jumpTo({ center: [p.lng, p.lat], zoom: 13.2, pitch: 0 }) }); await wait(1500)
  const near = await run(() => window.__scene.drawn.filter(d => d.id.startsWith('coy-n1a-')).length)
  expect(far.aggregates > 5 && far.drawn < 200 && near >= 5, { far, near })
  await shot('02-convoy-vehicles'); return { far, near }
})

await step('E2E-03', 'Ground vehicles drive on rendered roads', async () => {
  const r = await run(async () => {
    const w = window.__session.world, m = window.__map
    const ids = ['coy-n1a-02', 'coy-n1a-06', 'sup-n-03', 'pol-stockholm-01']
    const out = []
    for (const id of ids) {
      const n = w.get(id); const p = w.poseNow(n)
      m.jumpTo({ center: [p.lng, p.lat], zoom: 15.5, pitch: 0 })
      await new Promise(res => m.once('idle', res))
      const q = w.poseNow(n); const s = m.project([q.lng, q.lat])
      const roads = m.queryRenderedFeatures([[s.x - 9, s.y - 9], [s.x + 9, s.y + 9]], { layers: ['road-minor', 'road-secondary', 'road-primary', 'road-trunk', 'road-motorway'].filter(l => m.getLayer(l)) })
      out.push([id, roads.length])
    }
    return out
  })
  expect(r.filter(([, k]) => k > 0).length >= 3, r)
  return r
})

await step('E2E-04', 'Selecting an airbase flies in cinematically and loads its layout', async () => {
  await role('air_ops', 'airbases')
  await run(() => window.__store.set({ selected: { kind: 'site', id: 'airbase-syd' } }))
  await wait(11000)
  const info = await run(() => ({ zoom: window.__map.getZoom(), pitch: window.__map.getPitch(), detail: window.__map.querySourceFeatures('site-detail').length, tab: document.querySelectorAll('.inspector .tabs button').length,
    models: window.__scene.models.instances.length }))
  expect(info.zoom > 13 && info.pitch > 45 && info.detail > 50 && info.tab >= 3, info)
  await shot('04-airbase'); return info
})

await step('E2E-05', '3D models render with attitude at the airbase', async () => {
  await run(() => { const c = window.__session.world.catalog.sites.find(s => s.id === 'airbase-syd'); window.__store.set({ threeD: true }); window.__map.jumpTo({ center: [c.center[0] + 0.012, c.center[1] + 0.006], zoom: 16, pitch: 62, bearing: -50 }) })
  await wait(4000)
  const info = await run(() => ({ instances: window.__scene.models.instances.length, buckets: [...window.__scene.models.buckets.values()].filter(b => b.count).map(b => b.key) }))
  expect(info.instances > 3 && info.buckets.includes('fighter') && info.buckets.includes('shelter'), info)
  await shot('05-airbase-3d'); return info
})

await step('E2E-06', 'Unknown track explains itself: fusion, prediction and deception tabs', async () => {
  await role('national_commander', 'threat', { threeD: false })
  await run(() => window.__store.set({ selected: { kind: 'track', id: 'unk-sea-03' }, tab: 'fusion' })); await wait(2500)
  const grades = await page.locator('.inspector .grade').count()
  await page.locator('.inspector .tabs button', { hasText: 'Prediction' }).click(); await wait(500)
  const hyps = await page.locator('.inspector .hyp').count()
  await page.locator('.inspector .tabs button', { hasText: 'Deception' }).click(); await wait(500)
  const indicators = await page.locator('.inspector .ind').count()
  const prob = await page.locator('.inspector .gauge b').textContent()
  expect(grades >= 2 && hyps >= 2 && indicators >= 3, { grades, hyps, indicators, prob })
  await shot('06-deception'); return { grades, hyps, indicators, prob }
})

await step('E2E-07', 'Every analysis surface computes cells with reasons', async () => {
  await run(() => window.__map.jumpTo({ center: [17.5, 58.5], zoom: 5.8, pitch: 0 }))
  const out = {}
  for (const s of ['fusion', 'threat', 'coverage', 'response']) {
    await run(id => window.__store.get() && (window.__store.set(st => { const o = { ...st.layerOverrides }; for (const l of st.views.layers) if (l.id.startsWith('analysis.')) o[l.id] = l.id === id; return { layerOverrides: o } })), `analysis.${s}`)
    await wait(3500)
    out[s] = await run(() => ({ cells: window.__scene.lastSurface?.cells.length ?? 0, surface: window.__scene.lastSurface?.surface, reasons: window.__scene.lastSurface?.cells[0]?.reasons.length ?? 0 }))
  }
  expect(Object.values(out).every(v => v.cells > 0 && v.reasons > 0), out)
  await shot('07-analysis'); return out
})

await step('E2E-08', 'Trajectory planning: pick a destination, compare options, execute', async () => {
  await run(() => { window.__store.set({ selected: { kind: 'entity', id: 'fl-s-cor3' }, tab: 'actions' }) }); await wait(2500)
  await page.locator('.inspector button', { hasText: 'Plan a route' }).click(); await wait(400)
  await run(() => window.__map.jumpTo({ center: [17.5, 56.8], zoom: 6.5, pitch: 0 })); await wait(1200)
  const box = await page.locator('.map-root').boundingBox()
  const pt = await run(() => window.__map.project([18.3, 57.1]))
  await page.mouse.click(box.x + pt.x, box.y + pt.y); await wait(3500)
  const opts = await page.locator('.inspector .route-opt').count()
  await shot('08-route-options')
  await page.locator('.inspector button', { hasText: 'Execute' }).click()
  await page.waitForFunction(() => window.__session.world.catalog.plans.some(p => p.entityId === 'fl-s-cor3'), null, { timeout: 15000 }).catch(() => undefined)
  const plans = await run(() => window.__session.world.catalog.plans.map(p => p.entityId))
  expect(opts >= 1 && plans.includes('fl-s-cor3'), { opts, plans })
  return { opts, plans }
})

await step('E2E-09', 'Simulation clock runs ahead of live and returns', async () => {
  const t0 = await run(() => window.__session.clock.now())
  await run(() => window.__session.setRate(60)); await wait(3000)
  const t1 = await run(() => window.__session.clock.now())
  const chip = await page.locator('.status-chip').textContent()
  await run(() => window.__session.goLive()); await wait(800)
  const back = await run(() => Math.abs(window.__session.clock.offset()))
  expect(t1 - t0 > 120 && /Simulation|Replay/.test(chip ?? '') && back < 5, { advanced: t1 - t0, chip, back })
  return { advanced: Math.round(t1 - t0), back }
})

await step('E2E-10', 'Injected drone swarm raises a counter-UAS alert', async () => {
  await run(() => window.__session.inject('drone_swarm')); await wait(5000)
  const alerts = await run(() => window.__store.get().snapshot.alerts.filter(a => a.ruleId === 'R16').map(a => a.id))
  expect(alerts.includes('al-R16-airbase-norr'), alerts)
  return alerts
})

await step('E2E-11', 'Real public sources report honest status', async () => {
  const r = await run(async () => (await (await fetch('/api/sources?probe=false')).json()).sources.map(s => [s.id, s.status]))
  const vocab = ['working', 'partial', 'simulated', 'adapter-only', 'planned', 'blocked']
  expect(r.length >= 10 && r.every(([, s]) => vocab.includes(s)), r)
  return r
})

await step('E2E-12', 'Police role shows patrol cars on Stockholm streets', async () => {
  await role('police', 'patrol', { threeD: false }); await wait(4000)
  const n = await run(() => window.__scene.drawn.filter(d => d.id.startsWith('pol-stockholm')).length)
  expect(n >= 10, { n })
  await shot('12-police'); return { n }
})

const failed = results.filter(r => r.status === 'fail')
writeFileSync(`${out}/results.json`, JSON.stringify({ ui, at: new Date().toISOString(), results, pageErrors }, null, 2))
console.log(`\n${results.length - failed.length}/${results.length} passed${pageErrors.length ? `, ${pageErrors.length} page errors` : ''}`)
if (pageErrors.length) console.log(pageErrors.slice(0, 8).join('\n'))
await browser.close()
process.exit(failed.length ? 1 : 0)
