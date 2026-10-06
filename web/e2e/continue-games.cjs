// Actual ordinary-room Chrome/PG/Nginx discovery and Continue, isolated project only.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18081';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-persistence-1c-browser');
const h = require('./game-actions.cjs');
const p = require('./persistence-restart.cjs');
const origin = process.env.CATAN_E2E_ORIGIN;
const project = 'catan-persistence-test';
async function waitAsync(predicate, label) {
  const deadline = Date.now() + 20000;
  while (!(await predicate())) {
    if (Date.now() > deadline) throw Error('Timeout: ' + label);
    await new Promise(resolve => setTimeout(resolve, 40));
  }
}
async function bindings(c) {
  return c.page.evaluate(() => JSON.parse(localStorage.getItem('catan_recent_games') || '{"entries":[]}').entries);
}
async function home(c) {
  await c.page.evaluate(() => sessionStorage.removeItem('catan_current_game'));
  c.match = null; c.room = null;
  await c.page.reload({ waitUntil: 'networkidle' });
  await c.page.getByRole('heading', { name: 'Continue Game', exact: true }).waitFor();
  await waitAsync(async () => !(await c.page.getByRole('region', { name: 'Recent games' }).getAttribute('aria-busy')) ||
    (await c.page.getByRole('region', { name: 'Recent games' }).getAttribute('aria-busy')) === 'false', 'recent games checked');
}
async function inspect(c, entries) {
  return c.page.evaluate(async credentials => {
    const start = performance.now();
    const response = await fetch('/api/reconnect/inspect-many', { method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ credentials }), cache: 'no-store' });
    return { status: response.status, cache: response.headers.get('cache-control'), json: await response.json(), ms: performance.now() - start };
  }, entries.map(({ room_code, reconnect_token }) => ({ room_code, reconnect_token })));
}
function privacy(result, entries) {
  const serialized = JSON.stringify(result.json);
  assert(entries.every(e => !serialized.includes(e.reconnect_token)), 'metadata cannot echo bearer credentials');
  for (const item of result.json.results) {
    if (item.status !== 'available') { assert.deepEqual(Object.keys(item), ['status']); continue; }
    assert.deepEqual(Object.keys(item.game).sort(), ['can_continue', 'connected_count', 'map_name', 'max_players',
      'own_color', 'own_name', 'player_count', 'room_code', 'status', 'target_vp', 'updated_at']);
  }
}
async function continueRoom(c, code) {
  await c.page.locator('.recent-game').filter({ hasText: `Room ${code}` }).getByRole('button', { name: 'Continue', exact: true }).click();
  await h.wait(() => c.room?.room_code === code && c.match, 'Continue recovered match');
  await c.page.locator('.game-shell').waitFor();
}
async function benchmarkProof(name) {
  // Ordinary create_room using Node's native WS; secrets remain only in process memory.
  return new Promise((resolve, reject) => {
    const socket = new WebSocket(origin.replace(/^http/, 'ws') + '/ws');
    const timeout = setTimeout(() => { socket.close(); reject(Error('benchmark room timeout')); }, 12000);
    socket.onopen = () => { socket.send(JSON.stringify({ type: 'hello', version: 1, name }));
      socket.send(JSON.stringify({ type: 'create_room', name, max_players: 2 })); };
    socket.onmessage = event => {
      const m = JSON.parse(event.data);
      if (m.type === 'reconnect_token') { clearTimeout(timeout); socket.close(); resolve({ room_code: m.room_code, reconnect_token: m.reconnect_token }); }
      if (m.type === 'error') { clearTimeout(timeout); socket.close(); reject(Error('benchmark room rejected')); }
    };
    socket.onerror = () => { clearTimeout(timeout); reject(Error('benchmark connection failed')); };
  });
}
async function main() {
  await fs.mkdir(process.env.CATAN_E2E_OUTPUT, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = { date: new Date().toISOString(), chrome: browser.version(), project, checks: [] };
  const check = name => { report.checks.push(name); console.log(JSON.stringify({ passed: true, check: name })); };
  let clients = [];
  try {
    clients = await h.room(browser, 'roomuxhidden', 2, true);
    await p.naturalSetup(clients);
    const [a, b] = clients, code = a.room.room_code, pid = a.match.state.you_pid;
    const saved = await bindings(a);
    assert.equal(saved.length, 1);
    assert.deepEqual(Object.keys(saved[0]).sort(), ['last_known_name', 'last_seen_at', 'reconnect_token', 'room_code', 'server_url']);
    const first = await inspect(a, saved); assert.equal(first.status, 200); assert.equal(first.cache, 'no-store'); privacy(first, saved);
    check('ordinary Host/Join/Start/setup and safe same-origin API through Nginx');
    const before = p.metadata(code), publicBefore = p.stable(a);
    await a.page.evaluate(() => sessionStorage.removeItem('catan_current_game'));
    p.docker(['kill', '--signal', 'KILL', `${project}-backend-1`]);
    p.docker([...p.compose, 'up', '-d', '--wait']);
    await home(a);
    assert.equal(await a.page.locator('.recent-game').count(), 1);
    assert.match(await a.page.locator('.recent-game').innerText(), /Base Standard/);
    await h.evidence(a, 'continue-after-restart');
    await continueRoom(a, code);
    await p.freshReconnect(b, code);
    assert.equal(a.match.state.you_pid, pid);
    assert.deepEqual(p.stable(a), publicBefore);
    const restored = p.metadata(code);
    assert.equal(restored.engine, before.engine); assert.equal(restored.deck, before.deck); assert.equal(restored.bag, before.bag);
    assert.equal(restored.match_uuid, before.match_uuid); h.privacy(clients);
    check('backend SIGKILL/restart → Recent card → Continue → same seat/match/private state');
    const actor = clients[a.match.state.turn];
    await h.action(clients, actor, () => actor.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'command after Continue');
    await p.resolvePending(clients);
    check('ordinary successful Roll and mandatory flow after Continue');
    const afterRoll = p.stable(a);
    await p.freshReconnect(a, code);
    assert.deepEqual(p.stable(a), afterRoll); assert.equal(a.match.state.you_pid, pid);
    check('same-tab refresh reconnects automatically without room/name input');
    const durable = p.metadata(code);
    p.docker([...p.compose, 'down']); // Deliberately NO -v: preserve isolated database volume.
    p.docker([...p.compose, 'up', '-d', '--wait']);
    await home(a); await continueRoom(a, code); await p.freshReconnect(b, code);
    const fullRestart = p.metadata(code);
    assert.equal(fullRestart.engine, durable.engine); assert.equal(fullRestart.match_uuid, durable.match_uuid);
    assert.equal(fullRestart.deck, durable.deck); assert.equal(fullRestart.bag, durable.bag);
    assert.deepEqual(p.stable(a), afterRoll);
    check('full Docker down/up without -v → Continue and automatic peer refresh');

    await home(a);
    await a.page.evaluate(() => {
      const value = JSON.parse(localStorage.getItem('catan_recent_games'));
      value.entries[0].last_known_name = 'Wrong cached nickname';
      localStorage.setItem('catan_recent_games', JSON.stringify(value));
    });
    await a.page.reload({ waitUntil: 'networkidle' });
    assert.match(await a.page.locator('.recent-game').innerText(), /natural Alice/);
    assert(!(await a.page.locator('.recent-game').innerText()).includes('Wrong cached nickname'));
    check('cached nickname overridden by server truth before Continue');
    await a.page.getByLabel('Name', { exact: true }).fill(a.name);
    await a.page.getByRole('button', { name: 'Host', exact: true }).click();
    await h.wait(() => a.room && a.room.room_code !== code, 'second lobby room');
    const secondCode = a.room.room_code;
    await home(a);
    assert.equal(await a.page.locator('.recent-game').count(), 2);
    const lobbyCard = a.page.locator('.recent-game').filter({ hasText: `Room ${secondCode}` });
    assert.match(await lobbyCard.innerText(), /Lobby/);
    await lobbyCard.getByRole('button', { name: 'Continue', exact: true }).click();
    await h.wait(() => a.room?.room_code === secondCode, 'Continue lobby');
    assert.equal(a.match, null);
    await home(a);
    await h.evidence(a, 'two-recent-games');
    check('two local bindings; Continue restores a lobby without a new slot');

    // Hold only validation: ordinary Host/Join must remain usable during loading/outage.
    let release;
    await a.page.route('**/api/reconnect/inspect-many', async route => {
      await new Promise(resolve => { release = resolve; });
      await route.fulfill({ status: 503, contentType: 'application/json', body: '{"status":"temporarily_unavailable"}' });
    });
    await a.page.reload({ waitUntil: 'domcontentloaded' });
    await h.wait(() => release, 'held batch request');
    assert.equal(await a.page.getByRole('button', { name: 'Host', exact: true }).isEnabled(), true);
    assert.equal(await a.page.getByRole('button', { name: 'Join', exact: true }).isEnabled(), true);
    assert.equal(await a.page.getByRole('region', { name: 'Recent games' }).getAttribute('aria-busy'), 'true');
    release(); await a.page.getByText('Temporarily unavailable', { exact: true }).first().waitFor();
    assert.equal((await bindings(a)).length, 2);
    await a.page.unroute('**/api/reconnect/inspect-many');
    await a.page.getByRole('button', { name: 'Check again', exact: true }).click();
    await a.page.locator('.recent-game').filter({ hasText: 'In Game' }).waitFor();
    check('loading/503 confined to Recent section, both bindings kept, explicit retry succeeds');

    // Exercise the existing internal close lifecycle with no new public admin API.
    p.docker([...p.compose, 'stop', 'backend']);
    const closeScript = `import asyncio,sys\nfrom app import server_mp as s\nfrom app.persistence.coordinator import Coordinator\nfrom app.persistence.db import configured_database\nasync def main():\n s.persistence=Coordinator(configured_database())\n await s.persistence.initialize(s.manager)\n await s.close_room(sys.argv[1])\n await s.persistence.close()\n print('closed')\nasyncio.run(main())`;
    p.docker([...p.compose, 'run', '--rm', '--no-deps', 'backend', 'python', '-B', '-c', closeScript, secondCode]);
    p.docker([...p.compose, 'up', '-d', '--wait']);
    await a.page.getByRole('button', { name: 'Check again', exact: true }).click();
    await waitAsync(async () => (await a.page.locator('.recent-game').count()) === 1, 'only closed room removed');
    assert.equal((await bindings(a)).length, 1);
    await continueRoom(a, code); await p.freshReconnect(b, code);
    const next = clients[a.match.state.turn];
    await h.action(clients, next, () => next.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'End after other room closed');
    check('internal durable close removes only its binding; other room remains playable');

    const proofs = [];
    for (let i = 0; i < 5; i++) proofs.push(await benchmarkProof(`Benchmark ${i}`));
    const single = [], batch = [];
    for (let i = 0; i < 12; i++) {
      const one = await inspect(a, proofs.slice(0, 1)), five = await inspect(a, proofs);
      assert.equal(one.status, 200); assert.equal(five.status, 200); privacy(five, proofs);
      single.push(one.ms); batch.push(five.ms);
    }
    const median = values => values.sort((a, b) => a - b)[Math.floor(values.length / 2)];
    report.performance = { samples: 12, single_ms: median(single), batch_5_distinct_valid_ms: median(batch) };
    check('single/batch-5 metadata latencies measured on real distinct valid credentials');
    for (const c of clients) assert.equal(c.jsErrors.length, 0);
    report.passed = true;
  } catch (error) {
    report.passed = false; report.error = String(error);
    if (clients[0]) await h.evidence(clients[0], 'continue-failure');
    throw error;
  } finally {
    await fs.writeFile(path.join(process.env.CATAN_E2E_OUTPUT, 'continue-results.json'), JSON.stringify(report, null, 2));
    for (const c of clients) await c.context.close();
    await browser.close();
  }
}
main().catch(error => { console.error(error); process.exitCode = 1; });
