// Real production React + raw WS/HTTP + PostgreSQL, scoped localhost fixtures.
// No mocked transport/snapshots, public activation, Test Tools or trusted maps in DOM.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18769';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-fog-live-' + Date.now());
const h = require('./game-actions.cjs');
const s2a = require('./seafarers-s2a.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const manifestPath = path.join(output, 'fixture-bindings.json');
const root = path.resolve(__dirname, '../..');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { scope: 'scoped internal live Fog only; public disabled', syntheticFundedFixtures: true, checks: [], cases: [] };
function check(label) { report.checks.push(label); console.log('PASS ' + label); }

async function start() {
  assert.equal(new URL(origin).hostname, '127.0.0.1');
  assert(process.env.DATABASE_URL, 'Isolated PostgreSQL DATABASE_URL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const child = spawn(python, ['-B', '-X', 'utf8', '-m', 'tests.fog_live_support',
    '--port', new URL(origin).port, '--manifest', manifestPath], {
    cwd: root, env: { ...process.env, CATAN_ENABLE_TEST_TOOLS: '0' }, windowsHide: true,
    stdio: ['ignore', 'pipe', 'pipe'],
  });
  // Never log the manifest, credentials, private hands or database diagnostics.
  child.stdout.resume(); child.stderr.resume();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Guarded Fog fixture backend failed to start');
    try { const r = await fetch(origin + '/health'); if (r.ok && (await r.json()).ready) return child; } catch {}
    await pause(80);
  }
  child.kill(); throw Error('Fixture backend readiness timeout');
}
async function stop(child) {
  if (!child || child.exitCode != null) return;
  const done = new Promise(resolve => child.once('exit', resolve)); child.kill(); await done;
}
async function raw(c, message) {
  await c.page.evaluate(message => window.__sockets.findLast(s => s.readyState === WebSocket.OPEN)
    .send(JSON.stringify(message)), message);
}
async function open(browser, entry, pid) {
  const c = await h.newClient(browser, pid ? 'Bob' : 'Alice');
  c.expectedOutage = false; c.expectedWarnings = [];
  c.page.on('console', m => {
    if (c.expectedOutage && m.type() === 'error' && /WebSocket connection.*ERR_CONNECTION_REFUSED/.test(m.text())) {
      assert.equal(c.console.at(-1), m.text()); c.expectedWarnings.push(c.console.pop());
    }
  });
  c.page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    const m = JSON.parse(String(payload)); if (m.type === 'hello') c.nonce = m.connection_nonce;
  }));
  // Only ordinary guest proof/binding is seeded. All gameplay is received from
  // the actual server; no snapshot, pid, hidden terrain or access flag is stored.
  await c.page.evaluate(({ code, proof, name, server }) => {
    const entry = { room_code: code, reconnect_token: proof, last_known_name: name, last_seen_at: Date.now(), server_url: server };
    localStorage.setItem('catan_recent_games', JSON.stringify({ version: 1, entries: [entry] }));
    sessionStorage.setItem('catan_current_game', JSON.stringify({ room_code: code, last_known_name: name, server_url: server }));
  }, { code: entry.room_code, proof: entry.proofs[pid], name: c.name, server: origin.replace(/^http/, 'ws') + '/ws' });
  await c.page.reload({ waitUntil: 'networkidle' });
  await h.wait(() => c.match && c.nonce, 'native owning reconnect');
  await c.page.locator('.game-shell').waitFor();
  assert.equal(c.room.ruleset_compatibility.status, 'compatible');
  return c;
}
function privacy(cs) {
  h.privacy(cs);
  const expected = cs[0].match.state.tiles;
  for (const c of cs) {
    const state = c.match.state;
    assert.deepEqual(state.tiles, expected);
    assert(!state.test_mode && !state.test_tools);
    for (const key of ['assignment_digest', 'initially_hidden', 'fog_pool', 'continuation', 'discoveries'])
      assert(!JSON.stringify(state).includes(key));
    assert(Object.keys(state.pending_gold).every(p => Number(p) === state.you_pid));
    assert(state.pending_gold_queue.every(p => p === state.you_pid));
    for (const t of state.tiles) if (t.visibility === 'hidden') {
      assert.equal(t.terrain, 'fog'); assert.equal(t.number, null);
    }
  }
}
async function refresh(cs) {
  const before = cs.map(c => c.match.state);
  for (const c of cs) {
    c.match = null; await c.page.reload({ waitUntil: 'networkidle' });
    await h.wait(() => c.match, 'ordinary refresh/Continue');
    await c.page.locator('.game-shell').waitFor();
  }
  privacy(cs);
  for (let i = 0; i < cs.length; i++) assert.deepEqual(cs[i].match.state, before[i]);
}
async function renderer(c, label) {
  await h.open3d(c);
  const state = c.match.state, count = state.tiles.filter(t => t.visibility !== 'hidden').length;
  await c.page.waitForFunction(expected => {
    let n = 0; window.__scene?.getState().scene.traverse(o => { if (o.userData.terrainAsset) n++; });
    return n === expected;
  }, count);
  const scene = await s2a.sceneChecks(c);
  for (let i = 0; i < state.tiles.length; i++) {
    assert.equal(scene.terrain[i], state.tiles[i].terrain);
    if (state.tiles[i].number != null) assert.equal(scene.numbers[i], state.tiles[i].number);
    else assert(!(i in scene.numbers));
  }
  const unknown = await c.page.evaluate(() => {
    const result = [];
    window.__scene.getState().scene.traverse(o => {
      if (o.userData.terrain !== 'fog') return;
      let asset = false, number = false, visual = false;
      o.traverse(n => { asset ||= !!n.userData.terrainAsset; number ||= n.userData.number != null; visual ||= !!n.userData.fogVisual; });
      result.push({ asset, number, visual });
    }); return result;
  });
  assert.equal(unknown.length, state.tiles.filter(t => t.visibility === 'hidden').length);
  assert(unknown.every(t => !t.asset && !t.number && t.visual));
  await c.page.screenshot({ path: path.join(output, label + '-3d.png') });
  await c.page.getByRole('button', { name: '2D', exact: true }).click();
  await c.page.locator('[data-renderer="2d"] svg').waitFor();
  assert.equal(await c.page.locator('[data-terrain="fog"]').count(), unknown.length);
  await c.page.screenshot({ path: path.join(output, label + '-svg.png') });
  check(label + ': actual safe SVG/Board3D terrain, tokens, GLBs and uniform hidden tiles');
}
async function claimAccount(c, entry) {
  const credentials = { username: 'fog_' + Date.now(), display_name: 'Fog account participant', password: 'synthetic-fog-live-password' };
  const status = await c.page.evaluate(async ({ credentials, code, proof, nonce }) => {
    const signup = await fetch('/api/auth/register', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(credentials) });
    if (!signup.ok) return signup.status;
    const claim = await fetch('/api/games/claim', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ room_code: code, reconnect_token: proof, connection_nonce: nonce }) });
    return claim.status;
  }, { credentials, code: entry.room_code, proof: entry.proofs[1], nonce: c.nonce });
  assert.equal(status, 200);
  await pause(100); await refresh([c]);
  check('actual HTTP registration/guest claim and cookie-owned account Continue');
}
async function run(browser, entry, index, processRef) {
  const cs = [];
  try {
    for (const pid of [0, 1]) cs.push(await open(browser, entry, pid));
    privacy(cs);
    if (index) await claimAccount(cs[1], entry);
    await renderer(cs[0], 'case-' + index + '-initial');
    await h.open3d(cs[1]);
    const a = cs[0], edge = [...entry.route.eid].sort((x, y) => x - y).join(',');
    if (!entry.setup) {
      await h.open3d(a);
      await a.page.getByRole('button', { name: 'Ship', exact: true }).click();
    }
    await h.action(cs, a, () => entry.setup
      ? a.page.locator(`[data-target-edge="${edge}"]`).click()
      : h.clickTarget(a, 'edge', entry.route.eid), 'real live ' + entry.route.type);
    await h.wait(() => a.match.state.pending_action === 'choose_gold', 'committed discovery Gold');
    privacy(cs);
    const discovered = a.match.state.game_events.filter(e => e.type === 'discover_tile');
    assert(discovered.length && new Set(discovered.map(e => e.tile)).size === discovered.length);
    assert(a.match.state.tiles.some(t => t.visibility === 'hidden'));
    assert.equal(await cs[1].page.getByRole('dialog', { name: /Gold Choice/ }).count(), 0);
    await a.page.getByRole('dialog', { name: /Gold Choice/ }).waitFor();
    await cs[1].page.waitForFunction(() => {
      let active = false; window.__scene?.getState().scene.traverse(o => { active ||= !!o.userData.fogReveal && o.visible; }); return !active;
    });
    check('case-' + index + ': real ' + entry.route.type + ', shared discovery, finite reveal, actor-only Gold');
    await refresh(cs);
    check('case-' + index + ': refresh during pending exploration preserves latest snapshot and ownership');
    const pending = cs.map(c => c.match.state);
    for (const c of cs) c.expectedOutage = true;
    await stop(processRef.current);
    for (const c of cs) c.match = null;
    processRef.current = await start();
    await h.wait(() => cs.every(c => c.match), 'native PostgreSQL recovery and reconnect');
    for (let i = 0; i < cs.length; i++) { cs[i].expectedOutage = false; assert.deepEqual(cs[i].match.state, pending[i]); }
    privacy(cs);
    check('case-' + index + ': actual backend restart preserves private assignment/Gold history without replay');
    await h.invalidNext(a, { type: 'choose_gold', res: 'gold' });
    await h.action(cs, a, () => a.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'atomic invalid Gold choice', true);
    let quantity = 0;
    while (a.match.state.pending_action === 'choose_gold') {
      const n = a.match.state.pending_gold[a.match.state.you_pid]; quantity += n;
      await a.page.getByLabel('Gold resource').selectOption('ore');
      await a.page.getByLabel('Gold quantity').fill(String(n));
      await h.action(cs, a, () => a.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'real Gold choice');
    }
    privacy(cs);
    assert.equal(h.own(a).res.ore, quantity);
    assert.equal(a.match.state.game_events.filter(e => e.type === 'discover_tile').length, discovered.length);
    await refresh(cs);
    check('case-' + index + ': rejected choice, real reward once and post-discovery refresh');
    await renderer(a, 'case-' + index + '-revealed');
    for (const c of cs) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
    report.cases.push({ setup: entry.setup, route: entry.route.type, revealed: discovered.length,
      awarded: quantity, js_errors: [], unexpected_console: [], expected_restart_refusals: cs.flatMap(c => c.expectedWarnings).length });
  } finally { for (const c of cs) await c.context.close(); }
}
async function publicGate(browser) {
  const c = await h.newClient(browser, 'Public guest');
  try {
    await c.page.getByRole('button', { name: 'Host', exact: true }).click();
    await h.wait(() => c.room, 'normal guest lobby');
    assert(c.room.map_presets.every(p => !/fog/i.test(p.id)));
    await raw(c, { type: 'set_map', trusted_fog: true, fog_access: true,
      map_data: { version: 2, name: 'SYNTHETIC_NO_ECHO', tiles: [{ q: 0, r: 0, terrain: 'fog' }], fog_pool: {} } });
    await h.wait(() => c.errors.some(e => e.code === 'feature_disabled'), 'public Fog gate');
    assert.equal(c.room.map_id, 'base_standard'); assert.equal(c.match, null);
    assert(!JSON.stringify(c.errors).includes('SYNTHETIC_NO_ECHO'));
    const response = await c.page.request.get(origin + '/fixture-bindings.json');
    const text = await response.text(); assert(!text.includes('reconnect_token') && !text.includes('proofs'));
    c.page.once('dialog', dialog => dialog.accept());
    await c.page.getByRole('button', { name: 'Close Lobby', exact: true }).click();
    await c.page.getByText(/was closed by its host/).waitFor();
    check('normal Home/lobby has no Fog preset; forged flags/upload denied; manifest not served');
  } finally { await c.context.close(); }
}
async function main() {
  await fs.mkdir(output, { recursive: true });
  const processRef = { current: await start() };
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
  try {
    const manifest = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    for (let i = 0; i < manifest.length; i++) await run(browser, manifest[i], i, processRef);
    await publicGate(browser);
  } finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close(); await stop(processRef.current);
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { privacy, refresh, renderer };
