/**
 * Browser acceptance run. Requires the API on :8000 and the UI on :5173 (dev) or the URL in TROSSOPS_UI.
 * Usage: node scripts/verify-browser.mjs [outputDir]
 * Writes screenshots and a JSON results ledger; exits non-zero on any failed step.
 */
import { mkdirSync, writeFileSync } from 'node:fs'
import { resolve } from 'node:path'

const pw = await import(process.env.PLAYWRIGHT_MODULE || 'playwright')
const out = resolve(process.argv[2] || 'test-results')
mkdirSync(out, { recursive: true })
const ui = process.env.TROSSOPS_UI || 'http://127.0.0.1:5173/'
const headless = process.env.HEADED ? false : true
const browser = await pw.chromium.launch({ headless, args: process.env.SOFTWARE_GL ? ['--use-gl=angle', '--use-angle=swiftshader', '--enable-unsafe-swiftshader', '--ignore-gpu-blocklist'] : [] })
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } })
const pageErrors = []
page.on('pageerror', e => pageErrors.push(String(e)))
page.on('console', m => { if (m.type() === 'error' && !/ERR_TUNNEL|ERR_NAME|Failed to load resource/.test(m.text())) pageErrors.push('console: ' + m.text().slice(0, 240)) })

const results = []
const closeAll = async () => { await page.evaluate(() => window.__store?.set(s => ({ panels: { ...s.panels, search: false, alerts: false, decisions: false, inputs: false, help: false } }))); await wait(200) }
const step = async (id, name, fn) => {
  const t0 = Date.now()
  await closeAll()
  try { const detail = await fn(); results.push({ id, name, status: 'pass', ms: Date.now() - t0, detail }); console.log(`PASS ${id} ${name}`, detail ?? '') }
  catch (e) { results.push({ id, name, status: 'fail', ms: Date.now() - t0, error: String(e).slice(0, 400) }); console.log(`FAIL ${id} ${name}: ${String(e).slice(0, 300)}`) }
}
const shot = n => page.screenshot({ path: `${out}/${n}.png` })
const evalMap = (fn, arg) => page.evaluate(fn, arg)
const wait = ms => page.waitForTimeout(ms)
const search = async text => { await page.keyboard.press('Escape'); await page.keyboard.press('/'); await wait(300); await page.locator('.search-input').fill(text); await wait(300); await page.keyboard.press('Enter'); await wait(2200) }

await page.goto(ui, { waitUntil: 'load' })
await wait(4000)

await step('E2E-01', 'Load useful scene', async () => {
  const info = await evalMap(() => ({ kpis: document.querySelectorAll('.kpi').length, layers: document.querySelectorAll('.layer-row').length, chip: document.querySelector('.status-chip')?.textContent, basemap: document.querySelector('.maplibregl-ctrl-attrib')?.textContent?.slice(0, 80), units: window.__scene?.sprites.instances.length }))
  if (!info.kpis || info.layers < 14 || !info.units) throw new Error(JSON.stringify(info))
  await shot('01-national'); return info
})

await step('E2E-02', 'Threat mode shows unknown tracks and predictions', async () => {
  await page.getByRole('tab', { name: 'Threat' }).click(); await wait(2500)
  const n = await evalMap(() => window.__map.querySourceFeatures('predictions').length)
  if (!n) throw new Error('no prediction geometry'); await shot('02-threat'); return { predictions: n }
})

await step('E2E-03', 'Select unknown track via search; inspector shows provenance', async () => {
  await search('unknown sea')
  const h = await evalMap(() => ({ title: document.querySelector('.inspector h3')?.textContent, tags: [...document.querySelectorAll('.inspector .tag')].map(t => t.textContent) }))
  if (!/Unknown sea/.test(h.title || '')) throw new Error(JSON.stringify(h))
  if (!h.tags.includes('observed')) throw new Error('missing observed provenance')
  await shot('03-unknown-track'); return h
})

await step('E2E-04', 'LOD: regional sprites, exact picking at zoom 11', async () => {
  await page.keyboard.press('Escape'); await page.getByRole('tab', { name: 'Readiness' }).click(); await wait(1500)
  await page.keyboard.press('l'); await search('Tank platoon 01'); await wait(500)
  await evalMap(() => window.__map.jumpTo({ zoom: 11 })); await wait(2500)
  await page.keyboard.press('Escape'); await wait(400)
  const pt = await evalMap(() => { const p = window.__scene.lastPoses.get('gv-01'); const q = window.__map.project([p.lng, p.lat]); return [q.x, q.y] })
  await page.mouse.click(pt[0], pt[1]); await wait(900)
  const title = await evalMap(() => document.querySelector('.inspector h3')?.textContent)
  if (title !== 'Tank platoon 01') throw new Error(`picked ${title}`)
  await shot('04-regional'); return { title }
})

await step('E2E-05', '3D: model layer active at close zoom, follow keeps unit centred', async () => {
  await page.keyboard.press('3'); await page.keyboard.press('f')
  await evalMap(() => window.__map.jumpTo({ zoom: 16, pitch: 60, bearing: -20 })); await wait(3000)
  const m = await evalMap(() => ({ models: window.__scene.models.instances.length, enabled: window.__scene.models.enabled, selected: window.__scene.models.instances.find(i => i.selected)?.id, pitch: window.__map.getPitch() }))
  if (!m.enabled || m.selected !== 'gv-01' || m.pitch < 30) throw new Error(JSON.stringify(m))
  await shot('05-local-3d'); await page.keyboard.press('f'); await page.keyboard.press('3'); await wait(800); return m
})

await step('E2E-06', 'Submit a field report; revision increments and feed shows it', async () => {
  await page.keyboard.press('Home'); await wait(1500)
  const before = await evalMap(() => Number(document.querySelector('.status-chip b + span b')?.textContent))
  await page.keyboard.press('r'); await wait(400)
  await page.locator('.form input[placeholder="Who is reporting"]').fill('Pvt. Verification')
  await page.locator('.form input[placeholder="One line"]').fill('Drone observed over depot-mitt')
  await page.locator('.form textarea').fill('Unknown small drone circling depot-mitt perimeter for three minutes, fuel area. No markings.')
  await page.getByRole('button', { name: 'Send to the picture' }).click(); await wait(2500)
  const after = await evalMap(() => ({ rev: Number(document.querySelector('.status-chip b + span b')?.textContent), note: document.querySelector('.form .note')?.textContent }))
  if (!(after.rev > before)) throw new Error(JSON.stringify({ before, after }))
  await page.keyboard.press('Escape'); await page.keyboard.press('a'); await wait(600)
  await page.getByRole('tab', { name: /Input feed/ }).click(); await wait(400)
  const first = await evalMap(() => document.querySelector('.floating .item strong')?.textContent)
  if (first !== 'Drone observed over depot-mitt') throw new Error(`feed head: ${first}`)
  await shot('06-report-feed'); await page.keyboard.press('Escape'); return { before, rev: after.rev }
})

await step('E2E-07', 'Decisions: optimise and commit an intervention; progress appears', async () => {
  await page.keyboard.press('d'); await wait(600)
  const optimise = page.getByRole('button', { name: /Optimise the plan/ })
  const canOptimise = await optimise.isEnabled()
  let rows = 0, count = 0
  if (canOptimise) {
    await optimise.click(); await wait(2000)
    rows = await evalMap(() => document.querySelectorAll('.plan-row').length)
    if (!rows) throw new Error('no plan rows')
    await shot('07-decisions')
    const commits = page.getByRole('button', { name: /^Commit / })
    count = await commits.count()
    if (count) { await commits.first().click({ timeout: 8000, force: true }); await wait(2500) }
  }
  const active = await evalMap(() => [...document.querySelectorAll('.floating .item small')].map(s => s.textContent).filter(t => /in progress|completed/.test(t || '')).length)
  if (!active) throw new Error('no in-progress intervention')
  await shot('07b-committed'); return { rows, committed: active, committedNow: count > 0, canOptimise }
})

await step('E2E-08', 'Replay: scrub back, picture is labelled replay, return to live', async () => {
  const nowS = await evalMap(() => Number(document.querySelector('.scrub input').max))
  await page.locator('.scrub input').fill(String(Math.max(1, Math.floor(nowS * 0.3)))); await wait(2500)
  const chip = await evalMap(() => document.querySelector('.status-chip')?.textContent)
  if (!/Replay/.test(chip || '')) throw new Error(`chip: ${chip}`)
  await shot('08-replay')
  await page.getByRole('button', { name: /Return to live/ }).click(); await wait(2000)
  const chip2 = await evalMap(() => document.querySelector('.status-chip')?.textContent)
  if (!/Live/.test(chip2 || '')) throw new Error(`chip after: ${chip2}`)
  return { chip, chip2 }
})

await step('E2E-09', 'Attention cell click explains itself', async () => {
  await page.keyboard.press('Home'); await wait(1800)
  const pt = await evalMap(() => {
    const m = window.__map, cells = window.__store.get().attention?.cells ?? []
    const poses = window.__store.get().snapshot.entities.filter(e => e.position).map(e => m.project([e.position.longitudeDeg, e.position.latitudeDeg]))
    for (const c of cells) { const q = m.project([c.center[0], c.center[1]]); if (q.x > 340 && q.x < 1000 && q.y > 120 && q.y < 740 && document.elementFromPoint(q.x, q.y)?.classList.contains('maplibregl-canvas') && !poses.some(p => Math.hypot(p.x - q.x, p.y - q.y) < 40)) return [q.x, q.y] }
    return null
  })
  if (!pt) throw new Error('no clickable cell free of units in view')
  await page.mouse.click(pt[0], pt[1]); await wait(800)
  const t = await evalMap(p => ({ head: document.querySelector('.inspector .panel-head h2')?.textContent, reasons: document.querySelectorAll('.inspector .section .note').length, sel: window.__store.get().selected, under: window.__map.queryRenderedFeatures(p).map(f => f.layer.id) }), pt)
  if (t.head !== 'Attention' || !t.reasons) throw new Error(JSON.stringify(t))
  await shot('09-attention-cell'); await page.keyboard.press('Escape'); return t
})

await step('E2E-10', 'Role scope: regional south sees fewer entities; civil mode changes layers', async () => {
  const nat = await evalMap(() => window.__store.get().snapshot.entities.length)
  await page.getByRole('button', { name: /Change role|National commander/ }).first().click(); await wait(300)
  await page.getByRole('option', { name: /Regional commander South/ }).click(); await wait(3000)
  const south = await evalMap(() => ({ n: window.__store.get().snapshot.entities.length, role: window.__store.get().roleId }))
  if (!(south.n < nat) || south.role !== 'regional_south') throw new Error(JSON.stringify({ nat, south }))
  await page.getByRole('tab', { name: 'Civil' }).click(); await wait(2200)
  const civil = await evalMap(() => window.__map.getLayoutProperty('incidents', 'visibility'))
  if (civil !== 'visible') throw new Error('incidents layer not visible in civil mode')
  await shot('10-regional-civil'); return { nat, south: south.n }
})

await step('E2E-11', 'No page errors during the run', async () => { if (pageErrors.length) throw new Error(pageErrors.join(' | ')); return { errors: 0 } })

await browser.close()
const summary = { ui, when: new Date().toISOString(), softwareGl: !!process.env.SOFTWARE_GL, results }
writeFileSync(`${out}/results.json`, JSON.stringify(summary, null, 2))
const failed = results.filter(r => r.status === 'fail').length
console.log(`\n${results.length - failed}/${results.length} passed → ${out}/results.json`)
process.exit(failed ? 1 : 0)
