// Actual production beta admission and lifecycle, not fixture capabilities.
// Only the isolated test launcher controls RNG; all rooms use normal UI/WS/PG.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18771';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-fog-beta-browser-' + Date.now());
const h = require('./game-actions.cjs');
const fog = require('./fog-live.cjs');
const natural = require('./fog-natural.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const root = path.resolve(__dirname, '../..');
const mapId = 'seafarers_fog_beta_2';
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const policy = { admission: false, stopped: false };
Object.assign(natural.report, { publicFog: true, productionAdmission: true,
  fixtureCapabilities: false, controlledServerRng: true, defaultAdmission: false });
function check(label) { natural.report.checks.push(label); console.log('PASS ' + label); }

async function start() {
  assert.equal(new URL(origin).hostname, '127.0.0.1');
  assert(process.env.DATABASE_URL, 'Disposable localhost PostgreSQL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const env = { ...process.env, CATAN_HOST: '127.0.0.1', CATAN_PORT: new URL(origin).port,
    CATAN_PERSISTENCE_MODE: 'durable', CATAN_AUTH_ORIGINS: origin,
    CATAN_ENABLE_TEST_TOOLS: '0', CATAN_FOG_BETA_EMERGENCY_STOP: policy.stopped ? '1' : '0' };
  // The first browser phase checks the real absent-variable default.
  if (policy.admission) env.CATAN_FOG_BETA_ADMISSION = '1';
  else delete env.CATAN_FOG_BETA_ADMISSION;
  const child = spawn(python, ['-B', '-X', 'utf8', '-m', 'tests.fog_beta_support', 'serve'], {
    cwd: root, env, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  // Private backend diagnostics never enter a browser artifact or served file.
  child.stdout.resume(); child.stderr.resume();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Isolated beta backend exited before readiness');
    try { const r = await fetch(origin + '/health'); if (r.ok && (await r.json()).ready) return child; } catch {}
    await pause(100);
  }
  child.kill(); throw Error('Isolated beta startup timeout');
}
async function stop(child) {
  if (!child || child.exitCode != null) return;
  const done = new Promise(resolve => child.once('exit', resolve)); child.kill(); await done;
}
async function raw(c, message) {
  await c.page.evaluate(message => window.__sockets.findLast(s => s.readyState === WebSocket.OPEN)
    .send(JSON.stringify(message)), message);
}
async function host(c) {
  c.room = null;
  await c.page.getByLabel('Max players').fill('2');
  await c.page.getByRole('button', { name: 'Host', exact: true }).click();
  await h.wait(() => c.room, 'ordinary Home Host');
}
async function closeLobby(c) {
  c.page.once('dialog', dialog => dialog.accept());
  await c.page.getByRole('button', { name: 'Close Lobby', exact: true }).click();
  await c.page.getByRole('button', { name: 'Host', exact: true }).waitFor();
  c.room = null;
}
async function disabledLobby(browser) {
  const c = await h.newClient(browser, 'Default disabled beta');
  try {
    await host(c);
    assert(c.room.map_presets.every(p => p.id !== mapId));
    assert.equal(await c.page.getByLabel('Map preset').locator(`option[value="${mapId}"]`).count(), 0);
    const before = { map: c.room.map_id, revision: c.room.map_revision, status: c.room.status };
    const rejected = c.errors.length;
    await raw(c, { type: 'set_map', map_id: mapId });
    await h.wait(() => c.errors.length > rejected, 'forged disabled beta selection rejected');
    assert.equal(c.errors.at(-1).code, 'feature_disabled');
    assert.deepEqual({ map: c.room.map_id, revision: c.room.map_revision, status: c.room.status }, before);
    assert.equal(c.match, null);
    const response = await fetch(origin + '/health');
    assert(response.ok && (await response.json()).ready);
    await closeLobby(c);
    assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []);
    check('default/disabled ordinary Home and lobby omit Fog; forged selection refuses without mutation');
  } finally { await c.context.close(); }
}
async function open(browser, pid, clients) {
  const c = await natural.observedClient(browser, pid);
  // Install observation on a real document, without seeding identity or state.
  await c.page.reload({ waitUntil: 'networkidle' });
  await c.page.getByLabel('Name', { exact: true }).fill(c.name);
  c.wireErrors = [];
  c.page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    const m = JSON.parse(String(payload));
    for (const key of ['assignment_digest', 'fog_pool', 'initially_hidden', 'continuation'])
      if (Object.hasOwn(m, key) || JSON.stringify(m).includes(`"${key}":`)) c.wireErrors.push('private Fog key in wire frame');
    if (m.type === 'match_state') for (const tile of m.state.tiles)
      if (tile.visibility === 'hidden' && (tile.terrain !== 'fog' || tile.number !== null)) c.wireErrors.push('unmasked hidden tile');
  }));
  if (pid === 0) await host(c);
  else {
    await c.page.getByLabel('Room code').fill(clients[0].room.room_code);
    await c.page.getByRole('button', { name: 'Join', exact: true }).click();
    await h.wait(() => c.room, 'ordinary guest Join');
  }
  return c;
}
async function verifyLobby(clients) {
  const host = clients[0];
  await h.wait(() => host.room.players.filter(p => p.connected).length === 2, 'both normal participants');
  assert(host.room.map_presets.some(p => p.id === mapId && p.required_players === 2 && p.target_vp === 12));
  await host.page.getByLabel('Starting player').selectOption('host');
  await host.page.getByLabel('Bank resource counts').selectOption('hidden');
  await h.wait(() => clients.every(c => c.room.settings.starting_player === 'host'
    && c.room.settings.bank_visibility === 'hidden'), 'ordinary confirmed match settings');
  await host.page.getByLabel('Map preset').selectOption(mapId);
  await h.wait(() => clients.every(c => c.room.map_id === mapId), 'public beta preset confirmation');
  for (const c of clients) {
    assert.equal(c.room.map_meta.custom_scenario, 'shared_preassigned_fog_beta');
    for (const [label, value] of [['Target VP', '12'], ['Discard threshold', '7'], ['Turn timer', '0']]) {
      assert.equal(await c.page.getByLabel(label).inputValue(), value);
      assert(await c.page.getByLabel(label).isDisabled());
    }
    await c.page.getByText('Shared exploration reveals unexplored terrain to both players.', { exact: false }).waitFor();
    assert.equal(await c.page.getByRole('button', { name: 'Enable Test Room', exact: true }).count(), 0);
  }
  assert(await host.page.getByRole('button', { name: 'Start Match', exact: true }).isEnabled());
  assert(await clients[1].page.getByRole('button', { name: 'Start Match', exact: true }).isDisabled());
  await host.page.screenshot({ path: path.join(output, 'beta-lobby.png') });
  check('enabled normal Host/Join/preset explains custom two-player beta and pins 12 VP, discard 7, timers off');
}
async function beforeRematch(clients, ref, browser) {
  policy.admission = false;
  await natural.restart(clients, ref, 'admission disabled: committed finished Fog and guest ownership continue unchanged');
  const host = clients[0], epoch = host.match.match_id, tick = host.match.tick;
  const rejected = host.errors.length;
  await host.page.getByRole('dialog', { name: 'Match results', exact: true })
    .getByRole('button', { name: 'Rematch', exact: true }).click();
  await h.wait(() => host.errors.length > rejected, 'disabled new rematch is rejected');
  assert.equal(host.errors.at(-1).code, 'feature_disabled');
  assert(clients.every(c => c.match.match_id === epoch && c.match.tick === tick && c.match.state.game_over));
  await disabledLobby(browser);
  check('disabling admission preserves finished results but blocks new Fog rematch and selection');
  policy.admission = true;
  await natural.restart(clients, ref, 'deliberate admission re-enable preserves old result and permits fresh rematch');
}
async function afterRematch(clients, ref) {
  const before = clients.map(c => c.match.state);
  policy.stopped = true;
  for (const c of clients) c.expectedOutage = true;
  await stop(ref.current);
  for (const c of clients) { c.match = null; c.room = null; }
  ref.current = await start();
  await h.wait(() => clients.every(c => c.room?.ruleset_compatibility?.reason === 'fog_beta_paused'), 'emergency stop metadata');
  for (const c of clients) {
    c.expectedOutage = false;
    await c.page.getByText('Fog beta gameplay is paused', { exact: true }).waitFor();
    assert.equal(c.match, null);
    assert.equal(await c.page.locator('.game-shell').count(), 0);
    assert.equal(await c.page.getByRole('button', { name: 'Roll', exact: true }).count(), 0);
    assert.equal(await c.page.getByRole('button', { name: 'Rematch', exact: true }).count(), 0);
    await c.page.getByRole('button', { name: 'Back to Home', exact: true }).waitFor();
  }
  await clients[0].page.screenshot({ path: path.join(output, 'beta-emergency-paused.png') });
  const guest = clients[1], code = guest.room.room_code;
  await guest.page.getByRole('button', { name: 'Back to Home', exact: true }).click();
  await guest.page.getByRole('button', { name: 'Host', exact: true }).waitFor();
  await host(guest);
  assert.equal(guest.room.map_id, 'base_standard');
  assert(guest.room.map_presets.every(p => p.id !== mapId));
  await closeLobby(guest);
  const saved = guest.page.locator('.recent-game').filter({ hasText: `Room ${code}` });
  await saved.getByRole('button', { name: 'View saved match', exact: true }).click();
  await h.wait(() => guest.room?.room_code === code && guest.room.ruleset_compatibility?.reason === 'fog_beta_paused', 'preserved guest Continue');
  await guest.page.getByText('Fog beta gameplay is paused', { exact: true }).waitFor();
  check('emergency stop hides gameplay, preserves both seats, offers Home/new Base lobby and safe saved Continue');
  policy.stopped = false;
  for (const c of clients) c.expectedOutage = true;
  await stop(ref.current);
  for (const c of clients) { c.match = null; c.room = null; }
  ref.current = await start();
  await h.wait(() => clients.every(c => c.match), 'emergency recovery restores compatible native beta');
  for (let i = 0; i < clients.length; i++) {
    const c = clients[i]; c.expectedOutage = false;
    assert.deepEqual(c.match.state, before[i]);
    assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []);
    assert.deepEqual(c.wireErrors, []);
  }
  fog.privacy(clients);
  check('emergency rollback/resume recovers the exact committed rematch opening without replay or conversion');
}
async function main() {
  assert(process.env.CATAN_NATURAL_TRACE, 'Generate the normal production-beta natural transcript first');
  const trace = JSON.parse(await fs.readFile(process.env.CATAN_NATURAL_TRACE, 'utf8'));
  assert.equal(trace.format, 'catan-natural-fog-match-v1'); assert.equal(trace.map_id, mapId);
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  natural.report.chrome = browser.version();
  const ref = { current: null, start };
  try {
    ref.current = await start();
    await disabledLobby(browser);
    await stop(ref.current); policy.admission = true; ref.current = await start();
    await natural.run(browser, trace, ref, { open, verifyLobby,
      initialLabel: 'ordinary public beta host starts fresh authorized Fog through production lifecycle',
      beforeRematch: (clients, state) => beforeRematch(clients, state, browser), afterRematch });
  } finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(natural.report, null, 2));
    await browser.close(); await stop(ref.current);
  }
}
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
