/**
 * Browser smoke / acceptance run. Drives the real UI in Chromium (Playwright) against a running frontend + API and
 * asserts on what was rendered, using the runtime handles the app exposes for verification
 * (window.__store, __session, __scene, __map).
 *
 * Usage:  node scripts/verify-browser.mjs [outputDir]          (npm run verify)
 * Env:
 *   TROSSOPS_UI          UI base URL (default http://127.0.0.1:5173/). The UI must proxy /api to the backend.
 *   BROWSER_CHANNEL      Playwright channel, e.g. msedge or chrome (default: bundled Chromium)
 *   HEADED=1             show the browser;  SOFTWARE_GL=1  force SwiftShader WebGL (CI without a GPU)
 *   VERIFY_READONLY=1    skip steps that mutate the shared backend (execute a route plan, inject a scenario)
 *   VERIFY_ONLY=E2E-01,E2E-05   run only these steps (load + console check always run)
 *   VERIFY_STEP_TIMEOUT_MS      per-step timeout (default 90000)
 *   PLAYWRIGHT_MODULE    alternative module path for playwright
 * Writes screenshots and results.json to outputDir (default test-results); exits non-zero when a step fails or the
 * page logged errors.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const ui = (process.env.TROSSOPS_UI || 'http://127.0.0.1:5173/').replace(/\/?$/, '/')
const out = resolve(process.argv[2] || 'test-results')
const readonly = /^(1|true|yes)$/i.test(process.env.VERIFY_READONLY ?? '')
const only = (process.env.VERIFY_ONLY ?? '').split(',').map(s => s.trim()).filter(Boolean)
const STEP_TIMEOUT = Number(process.env.VERIFY_STEP_TIMEOUT_MS || 90_000)
const VOCAB = ['working', 'partial', 'simulated', 'adapter-only', 'planned', 'blocked']
mkdirSync(out, { recursive: true })

// ---- pre-flight: fail fast with an actionable message ----------------------------------------------------------------
async function preflight() {
  const get = async path => {
    const ctl = new AbortController(); const t = setTimeout(() => ctl.abort(), 15_000)
    try { return await fetch(new URL(path, ui), { signal: ctl.signal }) } finally { clearTimeout(t) }
  }
  try { await get('') } catch (e) {
    console.error(`FATAL UI not reachable at ${ui} (${e.cause?.code ?? e.message}). Start it with: cd frontend && npx vite --host 127.0.0.1 [--port N] and set TROSSOPS_UI.`)
    process.exit(2)
  }
  try {
    const r = await get('api/health'); if (!r.ok) throw new Error(`HTTP ${r.status}`)
    const h = await r.json(); console.log(`API ${h.status} v${h.apiVersion}: ${h.entities} entities, ${h.rules} rules, feeds router ${h.feeds ? 'on' : 'off'}`)
  } catch (e) {
    console.error(`FATAL ${ui}api/health failed (${e.message}). Is the backend running (uvicorn app.main:app --port 8000) and does the UI proxy /api to it?`)
    process.exit(2)
  }
}
await preflight()

let pw
try { pw = await import(process.env.PLAYWRIGHT_MODULE || 'playwright') } catch (e) {
  console.error(`FATAL cannot import playwright (${e.message}). Run npm ci in frontend/.`); process.exit(2)
}
const launch = { headless: !process.env.HEADED, args: process.env.SOFTWARE_GL ? ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : ['--ignore-gpu-blocklist'] }
if (process.env.BROWSER_CHANNEL) launch.channel = process.env.BROWSER_CHANNEL
let browser
try { browser = await pw.chromium.launch(launch) } catch (e) {
  console.error(`FATAL browser launch failed (${String(e.message).split('\n')[0]}). Try BROWSER_CHANNEL=msedge or npx playwright install chromium.`); process.exit(2)
}
const page = await browser.newPage({ viewport: { width: 1600, height: 950 } })
page.setDefaultTimeout(20_000)

// Console errors fail the run. Network noise (tiles, aborted fetches, upstream feeds that are down) does not: feed
// health is asserted through /api/sources instead.
const pageErrors = []
let currentStep = 'load'
const BENIGN = /ERR_|Failed to load resource|404|net::|AbortError|the server responded with a status of/
page.on('pageerror', e => pageErrors.push(`[${currentStep}] pageerror: ${String(e).slice(0, 300)}`))
page.on('console', m => { if (m.type() === 'error' && !BENIGN.test(m.text())) pageErrors.push(`[${currentStep}] console: ${m.text().slice(0, 300)}`) })

const results = []
const wait = ms => page.waitForTimeout(ms)
const run = (fn, arg) => page.evaluate(fn, arg)
const shot = n => page.screenshot({ path: `${out}/${n}.png` }).catch(() => undefined)
const until = (fn, arg, timeout = 15_000, what = 'condition') => page.waitForFunction(fn, arg, { timeout, polling: 250 }).catch(() => { throw new Error(`timed out after ${timeout} ms waiting for ${what}`) })
const reset = async () => {
  // stop a cinematic site orbit left over from a previous step (a user drag or wheel does the same)
  await run(() => window.__scene.camera?.interrupt?.())
  await run(() => window.__store.set({ selected: null, detail: null, route: null, follow: false, panels: Object.fromEntries(Object.keys(window.__store.get().panels).map(k => [k, false])) }))
  await wait(300)
}
const expect = (cond, msg, info) => { if (!cond) throw new Error(`${msg} :: ${JSON.stringify(info)}`) }
const step = async (id, name, fn, { mutates = false, timeout = STEP_TIMEOUT } = {}) => {
  if (only.length && !only.includes(id)) return
  if (mutates && readonly) { results.push({ id, name, status: 'skip', detail: 'VERIFY_READONLY' }); console.log(`SKIP ${id} ${name} (VERIFY_READONLY)`); return }
  currentStep = id
  const t0 = Date.now()
  const errorsBefore = pageErrors.length
  try {
    await reset()
    let timer
    const detail = await Promise.race([fn(), new Promise((_, rej) => { timer = setTimeout(() => rej(new Error(`step timed out after ${timeout} ms`)), timeout) })]).finally(() => clearTimeout(timer))
    const errs = pageErrors.slice(errorsBefore)
    results.push({ id, name, status: 'pass', ms: Date.now() - t0, detail, pageErrors: errs })
    console.log(`PASS ${id} ${name} (${Date.now() - t0} ms)`, JSON.stringify(detail ?? '').slice(0, 220))
  } catch (e) {
    results.push({ id, name, status: 'fail', ms: Date.now() - t0, error: String(e).slice(0, 800), pageErrors: pageErrors.slice(errorsBefore) })
    console.log(`FAIL ${id} ${name}: ${String(e).slice(0, 600)}`)
    await shot(`fail-${id}`)
  }
}
const setRole = async (roleId, modeId, extra = {}) => {
  await run(([r, m, x]) => window.__store.set({ roleId: r, modeId: m, layerOverrides: {}, ...x }), [roleId, modeId, extra])
  await wait(3000)
}

// ---- load -------------------------------------------------------------------------------------------------------------
const tLoad = Date.now()
try {
  await page.goto(ui, { waitUntil: 'load', timeout: 60_000 })
  await until(() => window.__session?.world && window.__store?.get().snapshot && window.__store.get().views, null, 60_000, 'world catalog, views and first snapshot')
} catch (e) {
  console.log(`FAIL load: ${String(e).slice(0, 400)}`); await shot('fail-load')
  if (pageErrors.length) console.log(pageErrors.slice(0, 8).join('\n'))
  writeFileSync(`${out}/results.json`, JSON.stringify({ ui, at: new Date().toISOString(), results: [{ id: 'load', status: 'fail', error: String(e) }], pageErrors }, null, 2))
  await browser.close(); process.exit(1)
}
await wait(3000)
console.log(`loaded in ${Date.now() - tLoad} ms`)

await step('E2E-01', 'National picture loads from the live API', async () => {
  const info = await run(() => ({ entities: window.__session.world.nodes.length, drawn: window.__scene.drawn.length, stream: window.__store.get().stream, kpis: document.querySelectorAll('.kpi').length,
    roles: window.__store.get().views.roles.length, attribution: document.querySelector('.maplibregl-ctrl-attrib')?.textContent?.slice(0, 60) }))
  expect(info.entities > 1000, 'world catalog has fewer than 1000 entities', info)
  expect(info.drawn > 20, 'fewer than 20 symbols drawn at national zoom', info)
  expect(info.kpis >= 3, 'KPI strip missing', info)
  expect(info.stream !== 'offline', 'SSE stream offline', info)
  await shot('01-national'); return info
})

await step('E2E-02', 'Every role and every mode can be selected from the top bar', async () => {
  const roles = await run(() => window.__store.get().views.roles.map(r => ({ id: r.id, label: r.label, modes: r.modes.map(m => m.id) })))
  const seen = []
  for (let i = 0; i < roles.length; i++) {
    const r = roles[i]
    await page.locator('.role-button').click()
    const opt = page.locator('.role-menu [role="option"]').nth(i)
    await opt.waitFor({ state: 'visible', timeout: 5000 }).catch(() => { throw new Error(`role menu option ${i} (${r.id}) not visible`) })
    await opt.click()
    await until(id => window.__store.get().roleId === id, r.id, 5000, `roleId=${r.id}`)
    const tabs = page.locator('.modes [role="tab"]')
    const n = await tabs.count()
    expect(n === r.modes.length, `role ${r.id} shows ${n} mode tabs, API defines ${r.modes.length}`, r)
    for (let k = 0; k < n; k++) {
      await tabs.nth(k).click()
      await until(id => window.__store.get().modeId === id, r.modes[k], 5000, `modeId=${r.modes[k]} in role ${r.id}`)
      expect(await tabs.nth(k).getAttribute('aria-selected') === 'true', `mode tab ${r.modes[k]} not marked selected`, r)
      await wait(400)
      seen.push(`${r.id}/${r.modes[k]}`)
    }
  }
  await setRole('national_commander', 'overview')
  return { roles: roles.length, modes: seen.length }
})

await step('E2E-03', 'Each Dock panel opens a drawer with content', async () => {
  const buttons = page.locator('.dock > .dock-btn')
  const sep = await run(() => [...document.querySelectorAll('.dock > *')].findIndex(el => el.classList.contains('dock-sep')))
  const count = sep > 0 ? sep : await buttons.count()
  const opened = {}
  for (let i = 0; i < count; i++) {
    await buttons.nth(i).click(); await wait(500)
    const open = await run(() => Object.entries(window.__store.get().panels).filter(([, v]) => v).map(([k]) => k))
    expect(open.length >= 1, `dock button ${i} opened no panel`, open)
    const drawer = await run(() => ({ title: document.querySelector('.drawer h2')?.textContent ?? '', body: document.querySelector('.drawer .panel-body')?.children.length ?? 0 }))
    expect(drawer.title && drawer.body > 0, `dock button ${i} (${open.join(',')}) shows an empty drawer`, drawer)
    for (const p of open) opened[p] = drawer.title
    await buttons.nth(i).click(); await wait(300)
    expect(await run(() => !document.querySelector('.drawer')), `drawer for ${open.join(',')} did not close on second click`, {})
  }
  const want = ['layers', 'feed', 'decisions', 'scenario', 'report', 'sources', 'help']
  const missing = want.filter(p => !(p in opened))
  expect(!missing.length, 'panels never opened from the dock', { missing, opened })
  return opened
})

await step('E2E-04', 'Sources panel lists every feed with a status from the vocabulary', async () => {
  const api = await run(async () => (await (await fetch('/api/sources?probe=false')).json()).sources.map(s => ({ id: s.id, label: s.label, status: s.status })))
  expect(api.length >= 10, 'fewer than 10 feeds in /api/sources', api)
  const bad = api.filter(s => !VOCAB.includes(s.status))
  expect(!bad.length, 'feeds with a status outside the vocabulary', bad)
  await run(() => window.__store.set(s => ({ panels: { ...s.panels, sources: true } })))
  await until(n => document.querySelectorAll('.drawer .source').length >= n, api.length, 20_000, `${api.length} source rows in the panel`)
  const rows = await run(() => [...document.querySelectorAll('.drawer .source')].map(el => ({ status: el.querySelector('.status')?.textContent?.trim(), label: el.querySelector('strong')?.textContent?.trim() })))
  const missing = api.filter(s => !rows.some(r => r.label === s.label))
  expect(!missing.length, 'feeds missing from the Sources panel', missing.map(s => s.id))
  const rowBad = rows.filter(r => !VOCAB.includes(r.status))
  expect(!rowBad.length, 'panel shows statuses outside the vocabulary', rowBad)
  await shot('04-sources')
  return Object.fromEntries(api.map(s => [s.id, s.status]))
})

await step('E2E-05', 'Searching and selecting an entity opens the Inspector', async () => {
  const target = await run(() => { const n = window.__session.world.get('fl-s-cor3'); return n ? { id: n.e.id, label: n.e.label } : null })
  expect(target, 'entity fl-s-cor3 missing from the world', {})
  const search = page.locator('input[aria-label="Search"]')
  await search.click(); await search.fill(target.id)
  const first = page.locator('.search-results [role="option"]').first()
  await first.waitFor({ state: 'visible', timeout: 5000 }).catch(() => { throw new Error(`no search results for ${target.id}`) })
  await search.press('Enter')
  await until(id => window.__store.get().selected?.id === id, target.id, 5000, `selection of ${target.id}`)
  await page.locator('.inspector').waitFor({ state: 'visible', timeout: 10_000 }).catch(() => { throw new Error('Inspector did not open') })
  await until(() => window.__store.get().detail, null, 15_000, 'entity detail from /api/entities')
  const info = await run(() => ({ title: document.querySelector('.inspector')?.textContent?.slice(0, 120), tabs: document.querySelectorAll('.inspector [role="tab"]').length }))
  expect(info.tabs >= 2, 'Inspector shows fewer than two tabs', info)
  await shot('05-inspector'); return info
})

await step('E2E-06', 'Echelon aggregation stays inside the symbol budget and resolves to vehicles when zoomed', async () => {
  await run(() => window.__map.jumpTo({ center: [16.5, 61.5], zoom: 4.8, pitch: 0, bearing: 0 })); await wait(1500)
  const far = await run(() => ({ drawn: window.__scene.drawn.length, aggregates: window.__scene.drawn.filter(d => d.kind === 'formation').length }))
  await run(() => { const w = window.__session.world; const n = w.get('coy-n1a-05'); const p = w.poseNow(n); window.__map.jumpTo({ center: [p.lng, p.lat], zoom: 13.2, pitch: 0 }) }); await wait(1500)
  const near = await run(() => window.__scene.drawn.filter(d => d.id.startsWith('coy-n1a-')).length)
  expect(far.aggregates > 5 && far.drawn < 200, 'national view not aggregated into formations', far)
  expect(near >= 5, 'company does not resolve into vehicles at zoom 13', { near })
  await shot('06-convoy-vehicles'); return { far, near }
})

await step('E2E-07', 'Ground vehicles drive on rendered roads', async () => {
  const r = await run(async () => {
    const w = window.__session.world, m = window.__map
    const out = []
    for (const id of ['coy-n1a-02', 'coy-n1a-06', 'sup-n-03', 'pol-stockholm-01']) {
      const n = w.get(id); if (!n) { out.push([id, -1]); continue }
      const p = w.poseNow(n)
      m.jumpTo({ center: [p.lng, p.lat], zoom: 15.5, pitch: 0 })
      await new Promise(res => { m.once('idle', res); setTimeout(res, 8000) })
      const q = w.poseNow(n); const s = m.project([q.lng, q.lat])
      const roads = m.queryRenderedFeatures([[s.x - 9, s.y - 9], [s.x + 9, s.y + 9]], { layers: ['road-minor', 'road-secondary', 'road-primary', 'road-trunk', 'road-motorway'].filter(l => m.getLayer(l)) })
      out.push([id, roads.length])
    }
    return out
  })
  expect(r.filter(([, k]) => k > 0).length >= 3, 'fewer than 3 of 4 vehicles sit on a rendered road', r)
  return r
})

await step('E2E-08', 'Selecting an airbase flies in and loads its layout', async () => {
  await setRole('air_ops', 'airbases')
  await run(() => window.__store.set({ selected: { kind: 'site', id: 'airbase-syd' } }))
  await until(() => window.__map.getZoom() > 13 && !window.__map.isMoving(), null, 20_000, 'camera to settle on the airbase')
  await wait(1500)
  const info = await run(() => ({ zoom: +window.__map.getZoom().toFixed(1), pitch: Math.round(window.__map.getPitch()), layout: !!window.__scene.layouts?.has?.('airbase-syd'),
    detail: window.__map.querySourceFeatures('site-detail').length, tabs: document.querySelectorAll('.inspector [role="tab"]').length }))
  expect(info.layout || info.detail > 50, 'site layout not loaded', info)
  expect(info.tabs >= 2, 'site Inspector not open', info)
  await shot('08-airbase'); return info
})

await step('E2E-09', '3D toggle switches the scene to perspective with 3D models and back', async () => {
  const btn = page.locator('.dock > .dock-sep ~ .dock-btn').first()
  // Selecting a site (previous step) switches 3D on by itself; start from a settled top-down camera. The app only
  // re-pitches a camera that is not already easing, so every transition below waits for the camera to settle.
  const settled = () => until(() => !window.__map.isMoving(), null, 15_000, 'camera to stop moving').then(() => wait(700))
  if (await run(() => window.__store.get().threeD)) { await btn.click(); await until(() => window.__store.get().threeD === false, null, 3000, '3D off'); await settled() }
  await run(() => { const c = window.__session.world.catalog.sites.find(s => s.id === 'airbase-syd'); window.__map.jumpTo({ center: [c.center[0] + 0.012, c.center[1] + 0.006], zoom: 16, pitch: 0, bearing: -50 }) })
  await settled()
  await btn.click()
  await until(() => window.__store.get().threeD === true, null, 3000, 'store.threeD after clicking the 3D button')
  await until(() => window.__map.getPitch() >= 35, null, 5000, 'camera pitch >= 35 in 3D').catch(async e => {
    throw new Error(`${e.message}; state ${JSON.stringify(await run(() => ({ pitch: window.__map.getPitch(), moving: window.__map.isMoving(), zoom: window.__map.getZoom(), s: window.__store.get().threeD, sel: window.__store.get().selected, follow: window.__store.get().follow, mode: window.__store.get().modeId })))}`)
  })
  await wait(3000)
  const on = await run(() => ({ pressed: document.querySelector('.dock > .dock-sep ~ .dock-btn')?.getAttribute('aria-pressed'), pitch: Math.round(window.__map.getPitch()),
    models: window.__scene.models?.enabled, instances: window.__scene.models?.instances?.length ?? null, terrain: !!window.__map.getTerrain?.() }))
  expect(on.pressed === 'true' && on.models === true, '3D button not pressed or model layer not enabled', on)
  expect(on.instances === null || on.instances > 3, 'fewer than 4 3D model instances at the airbase', on)
  await shot('09-3d')
  await btn.click()
  await until(() => window.__store.get().threeD === false, null, 3000, 'store.threeD false after second click')
  await until(() => window.__map.getPitch() < 5, null, 5000, 'camera back to top-down')
  return on
})

await step('E2E-10', 'Unknown track explains itself: fusion, prediction and deception tabs', async () => {
  await setRole('national_commander', 'threat', { threeD: false })
  await run(() => window.__store.set({ selected: { kind: 'track', id: 'unk-sea-03' }, tab: 'fusion' }))
  await until(() => document.querySelectorAll('.inspector .grade').length >= 2, null, 15_000, 'fusion source grades')
  const grades = await page.locator('.inspector .grade').count()
  await run(() => window.__store.set({ tab: 'prediction' })); await wait(500)
  const hyps = await page.locator('.inspector .hyp').count()
  await run(() => window.__store.set({ tab: 'deception' })); await wait(500)
  const indicators = await page.locator('.inspector .ind').count()
  expect(grades >= 2 && hyps >= 2 && indicators >= 3, 'explanation tabs incomplete', { grades, hyps, indicators })
  await shot('10-deception'); return { grades, hyps, indicators }
})

await step('E2E-11', 'Every analysis surface computes cells with reasons', async () => {
  await run(() => window.__map.jumpTo({ center: [17.5, 58.5], zoom: 5.8, pitch: 0 }))
  const res = {}
  for (const s of ['fusion', 'threat', 'coverage', 'response']) {
    await run(id => window.__store.set(st => { const o = { ...st.layerOverrides }; for (const l of st.views.layers) if (l.id.startsWith('analysis.')) o[l.id] = l.id === id; return { layerOverrides: o } }), `analysis.${s}`)
    await until(id => window.__scene.lastSurface?.surface === id, s, 15_000, `analysis surface ${s}`)
    await wait(1500)
    res[s] = await run(() => ({ cells: window.__scene.lastSurface?.cells.length ?? 0, reasons: window.__scene.lastSurface?.cells[0]?.reasons.length ?? 0,
      movingUnknown: window.__session.world.leaves.filter(n => n.visible && (n.e.affiliation === 'unknown' || n.e.affiliation === 'hostile_suspected') && n.pose.speed > 0.5).length }))
  }
  // threat reach is legitimately empty when no unknown track is moving at this instant
  const bad = Object.entries(res).filter(([s, v]) => !(v.cells > 0 && v.reasons > 0) && !(s === 'threat' && v.movingUnknown === 0))
  expect(!bad.length, 'analysis surfaces without cells or reasons', res)
  await run(() => window.__store.set({ layerOverrides: {} }))
  await shot('11-analysis'); return res
})

await step('E2E-12', 'Route planning returns options for a selected ship', async () => {
  const ENTITY = 'fl-s-cor3', DEST = [17.5, 56.9] // open water between Öland and Gotland
  const direct = await run(async ([id, to]) => { const r = await fetch('/api/plan/route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entityId: id, to }) }); return { status: r.status, body: r.ok ? (await r.json()).options.map(o => o.id) : await r.text() } }, [ENTITY, DEST])
  expect(direct.status === 200 && direct.body.length >= 1, 'POST /api/plan/route returned no options', direct)
  await run(id => window.__store.set({ selected: { kind: 'entity', id }, tab: 'actions' }), ENTITY)
  await page.locator('.inspector').waitFor({ state: 'visible' })
  await until(() => window.__store.get().detail, null, 15_000, 'entity detail')
  await run(id => window.__store.set({ route: { entityId: id, picking: true, result: null, option: null, busy: false }, follow: false }), ENTITY)
  await run(to => window.__map.jumpTo({ center: to, zoom: 6.5, pitch: 0, bearing: 0 }), DEST); await wait(1500)
  const box = await page.locator('.map-root').boundingBox()
  const pt = await run(to => window.__map.project(to), DEST)
  await page.mouse.click(box.x + pt.x, box.y + pt.y)
  await until(() => window.__store.get().route?.result || window.__store.get().error, null, 60_000, 'route result after picking a destination on the map')
  const err = await run(() => window.__store.get().error)
  expect(!err, 'route planning reported an error', err)
  await until(() => document.querySelectorAll('.inspector .route-opt').length >= 1, null, 5000, 'route options in the Inspector')
  const opts = await page.locator('.inspector .route-opt').count()
  await shot('12-route-options')
  return { api: direct.body, opts }
}, { timeout: Math.max(STEP_TIMEOUT, 150_000) })

await step('E2E-13', 'Executing a planned route records the plan', async () => {
  const ENTITY = 'fl-s-cor3', DEST = [17.5, 56.9]
  const result = await run(async ([id, to]) => {
    const r = await (await fetch('/api/plan/route', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ entityId: id, to }) })).json()
    const o = r.options.find(x => x.id === r.recommended) ?? r.options[0]
    await window.__session.commitRoute(id, o)
    return o.id
  }, [ENTITY, DEST])
  await until(id => window.__session.world.catalog.plans.some(p => p.entityId === id), ENTITY, 15_000, 'plan in the world catalog')
  return { committed: result }
}, { mutates: true })

await step('E2E-14', 'Simulation clock runs ahead of live and returns', async () => {
  const t0 = await run(() => window.__session.clock.now())
  await run(() => window.__session.setRate(60)); await wait(3000)
  const t1 = await run(() => window.__session.clock.now())
  const mode = await run(() => window.__store.get().clock.mode)
  await run(() => window.__session.goLive()); await wait(800)
  const back = await run(() => Math.abs(window.__session.clock.offset()))
  expect(t1 - t0 > 120 && mode === 'sim' && back < 5, 'clock did not advance at 60x or return to live', { advanced: t1 - t0, mode, back })
  return { advanced: Math.round(t1 - t0), back }
})

await step('E2E-15', 'Injected drone swarm raises a counter-UAS alert', async () => {
  await run(() => window.__session.inject('drone_swarm'))
  await until(() => window.__store.get().snapshot.alerts.some(a => a.ruleId === 'R16'), null, 20_000, 'an R16 alert in the snapshot')
  return await run(() => window.__store.get().snapshot.alerts.filter(a => a.ruleId === 'R16').map(a => a.id))
}, { mutates: true })

await step('E2E-16', 'Police role shows patrol cars on Stockholm streets', async () => {
  await setRole('police', 'patrol', { threeD: false })
  await until(() => window.__scene.drawn.filter(d => d.id.startsWith('pol-stockholm')).length >= 10, null, 20_000, '10 Stockholm patrol cars drawn')
  const n = await run(() => window.__scene.drawn.filter(d => d.id.startsWith('pol-stockholm')).length)
  await shot('16-police'); return { n }
})

// ---- console errors over the whole run ------------------------------------------------------------------------------
currentStep = 'E2E-99'
results.push(pageErrors.length
  ? { id: 'E2E-99', name: 'No page or console errors during the run', status: 'fail', error: pageErrors.slice(0, 10).join('\n') }
  : { id: 'E2E-99', name: 'No page or console errors during the run', status: 'pass' })
console.log(`${pageErrors.length ? 'FAIL' : 'PASS'} E2E-99 No page or console errors during the run${pageErrors.length ? `: ${pageErrors.length} errors` : ''}`)

const failed = results.filter(r => r.status === 'fail')
const skipped = results.filter(r => r.status === 'skip')
writeFileSync(`${out}/results.json`, JSON.stringify({ ui, readonly, at: new Date().toISOString(), results, pageErrors }, null, 2))
console.log(`\n${results.length - failed.length - skipped.length}/${results.length - skipped.length} passed${skipped.length ? `, ${skipped.length} skipped` : ''}${pageErrors.length ? `, ${pageErrors.length} page errors` : ''} -> ${out}`)
if (pageErrors.length) console.log(pageErrors.slice(0, 8).join('\n'))
if (failed.length) console.log('Failed: ' + failed.map(f => f.id).join(', '))
await browser.close()
process.exit(failed.length ? 1 : 0)
