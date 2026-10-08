// Production React dist + real multiplayer WS + native Chrome/R3F mouse targets.
// Test Tools fund rare actions explicitly; no snapshot/controller/engine mocks.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18765';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-seafarers-s1', 'browser');
const h = require('./game-actions.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const dist = path.resolve(__dirname, '../dist');
const report = { checks: [], commands: 0, rejected: 0, maps: [] };
const check = value => { report.checks.push(value); console.log('PASS ' + value); };
const id = edge => [...edge].sort((a, b) => a - b).join(',');

async function act(cs, c, callback, label, rejected = false) {
  const result = await h.action(cs, c, callback, label, rejected);
  report.commands++;
  if (rejected) report.rejected++;
  for (const client of cs) {
    assert(!('ships_built_this_turn' in client.match.state));
    assert(!('ship_moved_this_turn' in client.match.state));
  }
  return result;
}
async function goldChoices(cs) {
  while (cs[0].match.state.pending_action === 'choose_gold') {
    const c = cs.find(client => (client.match.state.pending_gold[client.match.state.you_pid] || 0) > 0
      && client.match.state.pending_pid === client.match.state.you_pid);
    assert(c, 'only addressed recipient resolves Gold');
    const resource = Object.entries(c.match.state.bank_available).find(([, available]) => available)[0];
    await c.page.getByLabel('Gold resource').selectOption(resource);
    await c.page.getByLabel('Gold quantity').fill('1');
    await act(cs, c, () => c.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'manual Gold choice');
  }
}
async function tools(cs, callback) {
  const c = cs[0];
  await c.page.getByRole('button', { name: 'Test Tools', exact: true }).click();
  const dialog = c.page.getByRole('dialog', { name: 'Test Tools', exact: true });
  await dialog.waitFor();
  await callback(c, dialog);
  await dialog.getByRole('button', { name: 'Close Test Tools', exact: true }).click();
}
async function roll(cs, c) {
  await act(cs, c, () => c.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'real Roll');
  await goldChoices(cs);
  assert.notEqual(c.match.state.pending_action, 'discard'); // Small fixture hands.
  assert.notEqual(c.match.state.pending_action, 'robber_move'); // Server fixture dice=1,1.
}
async function ageTurn(cs) {
  await act(cs, cs[0], () => cs[0].page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'real End Turn');
  for (const c of cs.slice(1)) {
    await roll(cs, c);
    await act(cs, c, () => c.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'other player End Turn');
  }
  await roll(cs, cs[0]);
}
async function place(cs, c, kind, edge) {
  const button = c.page.getByRole('button', { name: kind, exact: true });
  if (await button.getAttribute('aria-pressed') !== 'true') await button.click();
  return act(cs, c, () => h.clickTarget(c, 'edge', edge), kind + ' actual 3D target');
}
async function rejectViaBuild(cs, c, command) {
  const s = c.match.state, edge = s.legal.ships[0], before = JSON.stringify(s.occupied_ships);
  assert(edge);
  const button = c.page.getByRole('button', { name: 'Ship', exact: true });
  if (await button.getAttribute('aria-pressed') !== 'true') await button.click();
  await h.invalidNext(c, command);
  await act(cs, c, () => h.clickTarget(c, 'edge', edge), 'direct illegal ' + command.type, true);
  assert.equal(JSON.stringify(c.match.state.occupied_ships), before);
}
async function naturalGoldSetup(cs) {
  for (const c of cs) await h.open3d(c);
  let ships = 0, choices = 0;
  while (cs[0].match.state.phase === 'setup') {
    if (cs[0].match.state.pending_action === 'choose_gold') {
      choices++; await goldChoices(cs); continue;
    }
    const c = cs[cs[0].match.state.turn], s = c.match.state;
    if (s.setup_need === 'settlement') {
      const targets = s.legal.settlements;
      const nearGold = targets.filter(v => s.vertex_adj_hexes[v].some(t => s.tiles[t].terrain === 'gold'));
      const coastal = targets.filter(v => s.vertex_adj_hexes[v].some(t => s.tiles[t].terrain === 'sea'));
      const unblockedCoast = coastal.filter(v => Object.entries(s.edge_adj_hexes).some(([edge, hexes]) =>
        edge.split(',').map(Number).includes(v) && hexes.some(t => s.tiles[t].terrain === 'sea')
        && !hexes.includes(s.pirate_tile)));
      // Choose a coast with room for subsequent acceptance actions. This is
      // test fixture selection; the UI still receives only authoritative lists.
      const capacity = v => Object.entries(s.edge_adj_hexes).filter(([edge, hexes]) =>
        edge.split(',').map(Number).includes(v) && hexes.some(t => s.tiles[t].terrain === 'sea')
        && !hexes.includes(s.pirate_tile)).length;
      unblockedCoast.sort((a, b) => capacity(b) - capacity(a) || a - b);
      const firstPlacement = !Object.values(s.occupied_v).some(([owner]) => owner === s.turn);
      const vid = (firstPlacement && unblockedCoast.length ? unblockedCoast
        : nearGold.length ? nearGold : unblockedCoast.length ? unblockedCoast : targets)[0];
      await act(cs, c, () => h.clickTarget(c, 'vertex', vid), 'natural Seafarers settlement');
    } else {
      const ship = s.legal.ships[0], edge = ship || s.legal.roads[0];
      assert(edge);
      const command = await place(cs, c, ship ? 'Ship' : 'Road', edge);
      assert.equal(command.setup, true);
      if (ship) ships++;
    }
  }
  assert(ships > 0 && choices > 0);
  check('natural three-player setup: initial ships and second-settlement Gold choices');
}
async function goldFlow(browser) {
  const cs = await h.room(browser, 's1', 3, true, 'seafarers_gold_haven', { testMode: true });
  report.maps.push('seafarers_gold_haven');
  await naturalGoldSetup(cs);
  const a = cs[0];
  await tools(cs, async (c, dialog) => {
    for (const resource of ['wood', 'brick', 'sheep']) {
      await dialog.getByLabel('Test resource').selectOption(resource);
      await dialog.getByLabel('Test amount').fill('4');
      await act(cs, c, () => dialog.getByRole('button', { name: 'Give resources', exact: true }).click(), 'explicit test funding');
    }
    await dialog.getByLabel('Test card').selectOption('road_building');
    await act(cs, c, () => dialog.getByRole('button', { name: 'Give development card', exact: true }).click(), 'test grants matured Road Building');
    await dialog.getByLabel('Test card').selectOption('knight');
    await act(cs, c, () => dialog.getByRole('button', { name: 'Give development card', exact: true }).click(), 'test grants matured Knight');
  });
  const hand = { ...h.own(a).res };
  await act(cs, a, () => a.page.locator('.dev-mini-card').filter({ hasText: 'Road Building' }).click(), 'Road Building before Roll');
  for (let index = 0; index < 2; index++) {
    assert(a.match.state.legal.road_free);
    const edge = a.match.state.legal.ships[0];
    if (!edge) await fs.writeFile(path.join(output, 'no-free-ship.json'), JSON.stringify(a.match, null, 2));
    assert(edge, 'server exposes free ship before Roll, free placement ' + index);
    const command = await place(cs, a, 'Ship', edge);
    assert.equal(command.free, true);
  }
  assert.deepEqual(h.own(a).res, hand);
  assert.equal(a.match.state.free_roads[0], 0);
  check('Road Building builds two free ships before Roll through unchanged shared controller');
  await roll(cs, a);
  const paid = a.match.state.legal.ships[0];
  assert(paid);
  await place(cs, a, 'Ship', paid);
  assert(!a.match.state.legal.move_ship.sources.some(e => id(e) === id(paid)));
  const target = a.match.state.legal.ships[0];
  await rejectViaBuild(cs, a, { type: 'move_ship', from_eid: paid, to_eid: target });
  check('newly built ship excluded from legal moves and rejected by real WebSocket');
  await ageTurn(cs);
  const movements = a.match.state.legal.move_ship;
  const source = movements.sources.find(e => id(e) === id(paid)) || movements.sources[0];
  assert(source, 'old open ship movable after actual turn cycle');
  const targets = movements.targets[id(source)];
  const distant = targets.find(e => !e.some(v => source.includes(v))) || targets[0];
  await a.page.getByRole('button', { name: 'Move Ship', exact: true }).click();
  await h.clickTarget(a, 'edge', source);
  await act(cs, a, () => h.clickTarget(a, 'edge', distant), 'move aged open ship');
  assert.equal(a.match.state.occupied_ships[id(distant)], 0);
  assert.equal(a.match.state.legal.move_ship.sources.length, 0);
  const another = a.match.state.legal.ships[0];
  await rejectViaBuild(cs, a, { type: 'move_ship', from_eid: distant, to_eid: another });
  check('old ship moves to server destination; second move rejected without mutation');
  const tokens = a.tokens.length;
  await a.page.reload({ waitUntil: 'networkidle' });
  await h.wait(() => a.tokens.length > tokens && a.match.state.legal.move_ship.sources.length === 0,
    'fresh reconnect snapshot retains used movement');
  await a.page.locator('.game-shell').waitFor();
  check('guest refresh continues current room and retains used movement');
  await h.open3d(a);
  await act(cs, a, () => a.page.locator('.dev-mini-card').filter({ hasText: 'Knight' }).click(), 'Knight opens one figure choice');
  assert.equal(a.match.state.pending_action, 'robber_move');
  const legal = a.match.state.legal;
  const sea = legal.pirate_tiles.find(tile => (legal.pirate_victims[tile] || []).length === 1)
    ?? legal.pirate_tiles[0];
  assert.notEqual(sea, undefined);
  await a.page.getByRole('button', { name: 'Pirate', exact: true }).click();
  const victims = legal.pirate_victims[sea] || [];
  assert(victims.length > 0, 'browser pirate acceptance includes a real theft victim');
  report.pirateVictims = victims.length;
  if (victims.length <= 1) await act(cs, a, () => h.clickTarget(a, 'tile', sea), 'Knight moves pirate');
  else {
    await h.clickTarget(a, 'tile', sea);
    await act(cs, a, () => a.page.getByRole('button', { name: cs[victims[0]].name, exact: true }).click(), 'pirate victim choice');
  }
  assert.equal(a.match.state.pirate_tile, sea);
  assert.equal(a.match.state.pending_action, null);
  h.privacy(cs);
  assert(cs.some(c => c.match.state.game_events.some(e => e.type === 'theft'
    && ![e.actor_pid, e.victim_pid].includes(c.match.state.you_pid) && !('resource' in e))));
  check('Knight chooses pirate once and personalized three-client feeds retain privacy');
  const before = JSON.stringify(a.match), sent = a.sent.length;
  await a.page.getByRole('button', { name: '2D', exact: true }).click();
  assert.equal(await a.page.locator('svg[height]').count(), 1);
  await h.open3d(a);
  assert.equal(a.sent.length, sent); assert.equal(JSON.stringify(a.match), before);
  await h.layout(a);
  await h.evidence(a, 'gold-haven-s1');
  check('sea/gold/pirate and pieces render in 3D; SVG switch and desktop resize retain state');
  for (const c of cs) { assert.deepEqual(c.jsErrors, []); await c.context.close(); }
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const wrapper = { async newContext(options) {
    const context = await browser.newContext(options);
    await context.grantPermissions(['local-network-access'], { origin });
    await context.route(origin + '/**', async route => {
      const p = new URL(route.request().url()).pathname;
      if (p === '/' || p.startsWith('/assets/') || p.startsWith('/models/')) {
        const file = path.join(dist, p === '/' ? 'index.html' : p);
        return route.fulfill({ body: await fs.readFile(file), contentType:
          file.endsWith('.html') ? 'text/html' : file.endsWith('.js') ? 'application/javascript'
            : file.endsWith('.css') ? 'text/css' : 'model/gltf-binary' });
      }
      return route.continue();
    });
    return context;
  } };
  try {
    const base = await h.room(wrapper, 's1base', 2, true);
    report.maps.push('base_standard');
    for (const c of base) await h.open3d(c);
    while (base[0].match.state.phase === 'setup') {
      const c = base[base[0].match.state.turn], s = c.match.state;
      const settlement = s.setup_need === 'settlement';
      await act(base, c, () => h.clickTarget(c, settlement ? 'vertex' : 'edge',
        settlement ? s.legal.settlements[0] : s.legal.roads[0]), 'Base natural setup');
    }
    assert.equal(base[0].match.tick, 8);
    await roll(base, base[0]);
    const before = JSON.stringify(base[0].match), sent = base[0].sent.length;
    await base[0].page.getByRole('button', { name: '2D', exact: true }).click();
    assert.equal(await base[0].page.locator('svg[height]').count(), 1);
    await h.open3d(base[0]);
    assert.equal(JSON.stringify(base[0].match), before); assert.equal(base[0].sent.length, sent);
    await act(base, base[0], () => base[0].page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'Base End Turn');
    for (const c of base) { assert.deepEqual(c.jsErrors, []); await c.context.close(); }
    check('Base natural setup, Roll, End Turn, 2D/3D compatibility');
    await goldFlow(wrapper);
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    console.log(JSON.stringify(report, null, 2));
  } finally { await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
