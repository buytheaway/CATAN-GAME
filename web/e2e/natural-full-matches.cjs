// Real Chrome clients replay legally generated, naturally funded full matches.
// No mocked snapshots, Test Tools, resource grants or direct GameState changes.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18768';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-natural-full-matches');
const h = require('./game-actions.cjs');
const s2a = require('./seafarers-s2a.cjs');
const origin = process.env.CATAN_E2E_ORIGIN;
const output = process.env.CATAN_E2E_OUTPUT;
assert.equal(new URL(origin).hostname, '127.0.0.1', 'Isolated loopback acceptance only');
const root = path.resolve(__dirname, '../..');
const report = { naturalFullMatches: true, fixtureFunding: false, testTools: false,
  controlledServerRng: true, checks: [], matches: [] };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(label) { report.checks.push(label); console.log('PASS ' + label); }
const key = edge => [...edge].sort((a, b) => a - b).join(',');

async function startServer() {
  assert(process.env.DATABASE_URL, 'Explicit isolated PostgreSQL DATABASE_URL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const child = spawn(python,
    ['-B', '-X', 'utf8', '-m', 'web.e2e.natural_full_match_server', '--port', new URL(origin).port],
    { cwd: root, env: { ...process.env, CATAN_ENABLE_TEST_TOOLS: '0' }, windowsHide: true,
      stdio: ['ignore', 'pipe', 'pipe'] });
  let diagnostics = '';
  child.stdout.on('data', chunk => { diagnostics += String(chunk); });
  child.stderr.on('data', chunk => { diagnostics += String(chunk); });
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Isolated test server exited before health readiness: ' + diagnostics.slice(-2000));
    try {
      const response = await fetch(origin + '/health');
      if (response.ok && (await response.json()).ready === true) return child;
    } catch {}
    await pause(100);
  }
  child.kill();
  throw Error('Isolated test backend did not become ready');
}
async function stopServer(child) {
  if (child.exitCode != null) return;
  const exited = new Promise(resolve => child.once('exit', resolve));
  child.kill();
  await exited;
}
async function raw(c, payload) {
  await c.page.evaluate(message => {
    const socket = window.__sockets.findLast(s => s.readyState === WebSocket.OPEN);
    if (!socket) throw Error('No controlling WebSocket');
    socket.send(JSON.stringify(message));
  }, payload);
}
function publicState(state) {
  return { phase: state.phase, turn: state.turn, rolled: state.rolled, game_over: state.game_over,
    winner_pid: state.winner_pid, tiles: state.tiles, occupied_v: state.occupied_v,
    occupied_e: state.occupied_e, occupied_ships: state.occupied_ships,
    robber_tile: state.robber_tile, pirate_tile: state.pirate_tile,
    longest_road_owner: state.longest_road_owner, longest_road_len: state.longest_road_len,
    largest_army_owner: state.largest_army_owner, largest_army_size: state.largest_army_size,
    scenario: state.scenario,
    players: state.players.map(p => ({ pid: p.pid, name: p.name, color: p.color,
      resource_count: p.resource_count, dev_count: p.dev_count, special_vp: p.special_vp })) };
}
function synchronized(clients) {
  h.privacy(clients);
  const expected = publicState(clients[0].match.state);
  for (const c of clients) {
    const state = c.match.state, own = h.own(c);
    assert.deepEqual(publicState(state), expected);
    assert.equal(Object.values(own.res).reduce((total, amount) => total + amount, 0), own.resource_count);
    assert.equal(own.dev_cards.length, own.dev_count);
    for (const privateField of ['seed', 'dev_deck', 'ships_built_this_turn', 'ship_moved_this_turn', 'bank'])
      assert(!(privateField in state));
    assert(!state.test_mode && !state.test_tools);
    assert(Object.keys(state.pending_gold).every(pid => Number(pid) === state.you_pid));
    assert(Object.keys(state.discard_required).every(pid => Number(pid) === state.you_pid));
  }
}
async function create(browser, fixture) {
  const clients = [];
  for (let pid = 0; pid < fixture.player_count; pid++)
    clients.push(await h.newClient(browser, fixture.names[pid]));
  for (const c of clients) {
    c.expectedOutage = false;
    c.expectedRestartWarnings = [];
    c.page.on('console', message => {
      if (c.expectedOutage && message.type() === 'error' && /WebSocket connection.*ERR_CONNECTION_REFUSED/.test(message.text())) {
        assert.equal(c.console.at(-1), message.text());
        c.expectedRestartWarnings.push(c.console.pop());
      }
    });
  }
  const host = clients[0];
  await host.page.getByLabel('Max players').fill(String(fixture.player_count));
  await host.page.getByRole('button', { name: 'Host', exact: true }).click();
  await h.wait(() => host.room, 'ordinary room creation');
  for (const c of clients.slice(1)) {
    await c.page.getByLabel('Room code').fill(host.room.room_code);
    await c.page.getByRole('button', { name: 'Join', exact: true }).click();
    await h.wait(() => c.room, 'ordinary participant joining');
  }
  await h.wait(() => host.room.players.filter(p => p.connected).length === fixture.player_count, 'all participants');
  await host.page.getByLabel('Starting player').selectOption('host');
  await host.page.getByLabel('Bank resource counts').selectOption('hidden');
  if (fixture.map_id !== 'base_standard') await host.page.getByLabel('Map preset').selectOption(fixture.map_id);
  await h.wait(() => clients.every(c => c.room.map_id === fixture.map_id
    && c.room.settings.starting_player === 'host' && c.room.settings.bank_visibility === 'hidden'), 'confirmed ordinary settings');
  assert(clients.every(c => !c.room.test_mode));
  assert(host.room.map_presets.every(p => !/fog/i.test(p.id)), 'Public Fog remains disabled');
  assert.equal(await host.page.getByRole('button', { name: 'Enable Test Room', exact: true }).count(), 0);
  if (fixture.map_id.includes('official_four_islands')) {
    assert.match(await host.page.locator('body').innerText(), /Start on one or two islands of your choice/);
    assert.equal(await host.page.getByLabel('Target VP').inputValue(), '13');
    assert.equal(await host.page.getByLabel('Target VP').isDisabled(), true);
  }
  await host.page.getByRole('button', { name: 'Start Match', exact: true }).click();
  await h.wait(() => clients.every(c => c.match), 'ordinary match creation');
  for (const c of clients) await c.page.locator('.game-shell').waitFor();
  synchronized(clients);
  return clients;
}
async function command(clients, entry, serial, ui = false) {
  const c = clients[entry.actor_pid], before = c.match.tick;
  const oldState = c.match.state;
  if (ui) {
    if (entry.cmd.type === 'place_road') {
      await c.page.getByRole('button', { name: '2D', exact: true }).click();
      await c.page.getByRole('button', { name: 'Road', exact: true }).click();
      await h.action(clients, c, () => c.page.locator(`[data-target-edge="${key(entry.cmd.eid)}"]`).click(),
        'representative real SVG paid road');
    } else await h.action(clients, c, () => c.page.getByRole('button', { name: entry.cmd.type === 'roll' ? 'Roll' : 'End Turn', exact: true }).click(),
      'representative real UI ' + entry.cmd.type);
  } else {
    const seq = Math.max(0, ...c.acks.map(a => a.last_seq_applied), ...c.tokens.map(t => t.last_seq_applied));
    const cmdId = 'natural-browser-' + serial;
    await raw(c, { type: 'cmd', room_code: c.match.room_code, match_id: c.match.match_id,
      seq: seq + 1, cmd_id: cmdId, cmd: entry.cmd });
    await h.wait(() => c.acks.some(a => a.cmd_id === cmdId), 'normal command durable ACK');
    const ack = c.acks.find(a => a.cmd_id === cmdId);
    assert.equal(ack.applied, true, JSON.stringify({ command: entry.cmd.type, error: c.errors.at(-1) }));
    await h.wait(() => clients.every(client => client.match.tick > before), 'all personalized committed frames');
  }
  synchronized(clients);
  assert.equal(clients[0].match.tick, entry.tick, 'Browser replay has the same accepted-command epoch as the TCP transcript');
  if (oldState.map_id.includes('official_four_islands')) {
    const pid = entry.actor_pid, state = c.match.state;
    const oldAwards = oldState.scenario.awarded_islands[pid] || [];
    const awards = state.scenario.awarded_islands[pid] || [];
    assert.equal(state.players[pid].special_vp, awards.length * 2);
    if (awards.length > oldAwards.length) {
      assert.equal(entry.cmd.type, 'place_settlement');
      assert.equal(oldState.phase, 'main');
      assert.equal(awards.length, oldAwards.length + 1);
      const newlyAwarded = awards.filter(id => !oldAwards.includes(id));
      assert.equal(newlyAwarded.length, 1);
      assert(!state.scenario.home_islands[pid].includes(newlyAwarded[0]));
      await c.page.getByRole('list', { name: 'Players', exact: true }).locator('li').nth(pid)
        .getByText(`${awards.length * 2} island VP`, { exact: true }).waitFor();
    }
    if (oldState.phase === 'setup') assert.equal(awards.length, 0);
  }
}
async function refresh(clients) {
  const tick = clients[0].match.tick, matchId = clients[0].match.match_id;
  for (const c of clients) {
    c.match = null;
    await c.page.reload({ waitUntil: 'networkidle' });
    if (!c.match) await c.page.locator('.recent-game').getByRole('button', { name: 'Continue', exact: true }).click();
    await h.wait(() => c.match?.tick === tick && c.match.match_id === matchId, 'guest refresh/Continue retains committed state');
  }
  synchronized(clients);
}
async function renderChecks(c, label) {
  await h.open3d(c);
  await c.page.waitForFunction(expected => {
    let count = 0;
    window.__scene?.getState().scene.traverse(o => { if (o.userData.terrainAsset) count++; });
    return count === expected;
  }, c.match.state.tiles.length);
  const scene = await s2a.sceneChecks(c);
  assert.equal(scene.assets, c.match.state.tiles.length);
  for (const [index, tile] of c.match.state.tiles.entries()) {
    assert.equal(scene.terrain[index], tile.terrain);
    if (tile.number != null) assert.equal(scene.numbers[index], tile.number);
  }
  for (const [vertex, [owner, level]] of Object.entries(c.match.state.occupied_v))
    assert(scene.pieces.some(p => p.vertexId === Number(vertex) && p.owner === owner && p.level === level));
  for (const [edge, owner] of Object.entries(c.match.state.occupied_e))
    assert(scene.pieces.some(p => p.edge && key(p.edge) === edge && p.owner === owner));
  for (const [edge, owner] of Object.entries(c.match.state.occupied_ships))
    assert(scene.pieces.some(p => p.edge && key(p.edge) === edge && p.owner === owner));
  if (Number.isInteger(c.match.state.robber_tile) && c.match.state.robber_tile >= 0)
    assert(scene.pawns.some(p => p.piece === 'robber' && p.tile === c.match.state.robber_tile));
  if (Number.isInteger(c.match.state.pirate_tile) && c.match.state.pirate_tile >= 0)
    assert(scene.pawns.some(p => p.piece === 'pirate' && p.tile === c.match.state.pirate_tile));
  await c.page.screenshot({ path: path.join(output, label + '-3d.png'), fullPage: true });
  await c.page.getByRole('button', { name: '2D', exact: true }).click();
  await c.page.locator('[data-renderer="2d"] svg').waitFor();
  assert.equal(await c.page.locator('[data-terrain]').count(), c.match.state.tiles.length);
  await c.page.screenshot({ path: path.join(output, label + '-svg.png'), fullPage: true });
  check(label + ': real SVG and Board3D match authoritative terrain, numbers and pieces');
}
async function run(browser, fixture) {
  let server = await startServer();
  let clients = [];
  try {
    clients = await create(browser, fixture);
    const host = clients[0];
    check(fixture.map_id + ': ordinary Home/lobby/start, no Test Tools, private/public projections');
    let serial = 0, refreshed = false, firstRoll = false, paidRoad = false;
    for (const [index, entry] of fixture.commands.entries()) {
      if (index === fixture.commands.length - 1) await renderChecks(host, fixture.map_id + '-late-play');
      if (!firstRoll && entry.cmd.type === 'roll') {
        // Fresh guest reconnect synchronizes the ordinary controller's sequence
        // after test-agent commands. The following Roll uses the real UI owner.
        await refresh(clients);
        await command(clients, entry, ++serial, true);
        firstRoll = true;
      } else if (!paidRoad && entry.cmd.type === 'place_road' && host.match.state.phase === 'main'
                 && !clients[entry.actor_pid].match.state.legal.road_free) {
        await refresh(clients);
        await command(clients, entry, ++serial, true);
        paidRoad = true;
      } else await command(clients, entry, ++serial);
      if (!refreshed && host.match.state.phase === 'main' && host.match.state.roll_count >= 3) {
        await refresh(clients);
        await renderChecks(host, fixture.map_id + '-in-play');
        refreshed = true;
      }
      if (serial % 80 === 0) console.log('Progress ' + fixture.map_id + ': ' + serial + ' accepted actions');
    }
    const final = host.match.state;
    assert(final.game_over, 'Actual server victory must finish the match');
    assert.equal(final.winner_pid, fixture.result.winner_pid);
    assert.deepEqual(final.players.map(p => p.vp), fixture.result.final_vp);
    assert(final.players[final.winner_pid].vp >= final.rules_config.target_vp);
    if (fixture.map_id.includes('official_four_islands')) {
      assert.equal(final.rules_config.target_vp, 13);
      assert.deepEqual(final.scenario.awarded_islands, fixture.result.awarded_islands);
      assert(final.scenario.home_islands[final.winner_pid].length >= 1
        && final.scenario.home_islands[final.winner_pid].length <= 2);
      check(fixture.map_id + ': real personal island awards, HUD bonus, 13 VP and durable expected ledger');
    }
    const postgame = [];
    for (const c of clients) {
      const results = c.page.getByRole('dialog', { name: 'Match results', exact: true });
      await results.waitFor();
      assert.match(await results.innerText(), /VP/);
      postgame.push({ pid: c.match.state.you_pid, text: await results.innerText(),
        rematch_disabled: await results.getByRole('button', { name: 'Rematch', exact: true }).isDisabled(),
        connected_presence: c.room.players.map(p => ({ pid: p.pid, connected: p.connected })) });
      await c.page.screenshot({ path: path.join(output, fixture.map_id + '-results-' + c.match.state.you_pid + '.png'), fullPage: true });
      await fs.writeFile(path.join(output, fixture.map_id + '-postgame.json'), JSON.stringify(postgame, null, 2));
      assert.equal(await results.getByRole('button', { name: 'Rematch', exact: true }).isDisabled(), c !== host);
      assert.equal(await results.getByRole('list', { name: 'Final scores' }).locator('li').count(), clients.length);
    }
    await host.page.screenshot({ path: path.join(output, fixture.map_id + '-results.png'), fullPage: true });
    check(fixture.map_id + ': actual natural-production-funded victory and results for every Chrome client');
    const finished = publicState(final), tick = host.match.tick;
    for (const c of clients) c.expectedOutage = true;
    await stopServer(server);
    for (const c of clients) c.match = null;
    server = await startServer();
    await h.wait(() => clients.every(c => c.match?.tick === tick), 'finished match restored after process restart');
    for (const c of clients) c.expectedOutage = false;
    await refresh(clients);
    assert.deepEqual(publicState(host.match.state), finished);
    for (const c of clients) await c.page.getByRole('dialog', { name: 'Match results', exact: true }).waitFor();
    check(fixture.map_id + ': durable finished result survives backend restart and all-player refresh');
    report.matches.push({ map_id: fixture.map_id, players: clients.length, actions: serial,
      turns: final.roll_count, winner_pid: final.winner_pid,
      final_scores: final.players.map(p => ({ pid: p.pid, vp: p.vp })),
      js_errors: clients.flatMap(c => c.jsErrors), console_warnings: clients.flatMap(c => c.console),
      expected_restart_connection_failures: clients.flatMap(c => c.expectedRestartWarnings) });
    for (const c of clients) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
    const oldMatchId = host.match.match_id;
    await host.page.getByRole('dialog', { name: 'Match results', exact: true })
      .getByRole('button', { name: 'Rematch', exact: true }).click();
    await h.wait(() => clients.every(c => c.match.match_id === oldMatchId + 1 && c.match.state.phase === 'setup'
      && c.match.tick === 0), 'real host rematch starts a fresh epoch');
    synchronized(clients);
    for (const c of clients) {
      assert.equal(await c.page.getByRole('dialog', { name: 'Match results', exact: true }).count(), 0);
      assert.deepEqual(c.match.state.occupied_v, {});
      assert.deepEqual(c.match.state.occupied_e, {});
      assert.deepEqual(c.match.state.occupied_ships, {});
    }
    check(fixture.map_id + ': refreshed host can start a legitimate rematch with fresh setup and epoch');
  } finally {
    for (const c of clients) await c.context.close();
    await stopServer(server);
  }
}
async function main() {
  assert(process.env.CATAN_NATURAL_TRACE, 'Set CATAN_NATURAL_TRACE to the generated legal-command replay');
  const loaded = JSON.parse(await fs.readFile(process.env.CATAN_NATURAL_TRACE, 'utf8'));
  const fixtures = Array.isArray(loaded) ? loaded : [loaded];
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try {
    for (const fixture of fixtures) await run(browser, fixture);
  } finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
