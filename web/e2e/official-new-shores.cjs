// Real Chrome/WS/PostgreSQL acceptance for the two official Scenario 1 layouts.
// Setup is natural; resource funding and dice are explicit existing Test Tools.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18094';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-official-new-shores');
const h = require('./game-actions.cjs');
const s2a = require('./seafarers-s2a.cjs');
const output = process.env.CATAN_E2E_OUTPUT;
const edgeKey = edge => [...edge].sort((a, b) => a - b).join(',');
const report = { variants: [], checks: [], naturalFullMatch: false, fixtureFunding: true };
function check(label) { report.checks.push(label); console.log('PASS ' + label); }

async function join(c, code) {
  await c.page.getByLabel('Room code').fill(code);
  await c.page.getByRole('button', { name: 'Join', exact: true }).click();
  await h.wait(() => c.room?.room_code === code, 'official participant join');
}

async function create(browser, players, id) {
  const cs = [];
  for (const name of ['Alice', 'Bob', 'Cara', 'Dan'].slice(0, players))
    cs.push(await h.newClient(browser, `official-${players} ${name}`));
  try {
    const a = cs[0], connected = cs.slice(0, -1);
    await a.page.getByLabel('Max players').fill(String(players));
    await a.page.getByRole('button', { name: 'Host', exact: true }).click();
    await h.wait(() => a.room, 'official lobby creation');
    for (const c of connected.slice(1)) await join(c, a.room.room_code);
    await a.page.getByLabel('Starting player').selectOption('host');
    await a.page.getByLabel('Bank resource counts').selectOption('hidden');
    await a.page.getByLabel('Target VP').selectOption('12');
    await a.page.getByLabel('Discard threshold').selectOption('9');
    await h.wait(() => connected.every(c => c.room.settings.starting_player === 'host'
      && c.room.settings.bank_visibility === 'hidden' && c.room.settings.target_vp === 12
      && c.room.settings.discard_threshold === 9), 'confirmed prior custom room settings');
    await a.page.getByRole('button', { name: 'Enable Test Room', exact: true }).click();
    await h.wait(() => connected.every(c => c.room.test_mode), 'explicit official test room');
    assert(a.room.map_presets.every(p => !/fog/i.test(p.id)), 'public Fog is not offered');
    await a.page.getByLabel('Map preset').selectOption(id);
    await h.wait(() => connected.every(c => c.room.map_id === id && c.room.settings.target_vp === 14
      && c.room.settings.discard_threshold === 7), 'official map resets inherited target/discard');
    for (const c of connected) {
      assert.equal(c.room.map_meta.required_players, players);
      assert.equal(c.room.map_meta.official_scenario, 'heading_for_new_shores');
      assert.equal(await c.page.getByLabel('Target VP').isDisabled(), true);
      assert.equal(await c.page.getByLabel('Discard threshold').isDisabled(), true);
      assert.equal(await c.page.getByLabel('Target VP').inputValue(), '14');
    }
    assert.equal(await a.page.getByRole('button', { name: 'Start Match', exact: true }).isDisabled(), true);
    assert.match(await a.page.locator('.room-start').innerText(), new RegExp(`exactly ${players} connected players`));
    const errors = a.errors.length;
    await a.page.evaluate(() => window.__sockets.at(-1).send(JSON.stringify({ type: 'start_match' })));
    await h.wait(() => a.errors.length > errors, 'authoritative incorrect player count rejection');
    assert.equal(a.errors.at(-1).code, 'invalid');
    assert.match(a.errors.at(-1).message, /exactly/);
    assert.equal(a.match, null);
    await join(cs.at(-1), a.room.room_code);
    await h.wait(() => cs.every(c => c.room.map_id === id && c.room.players.filter(p => p.connected).length === players), 'all official participants');
    await a.page.getByRole('button', { name: 'Start Match', exact: true }).click();
    await h.wait(() => cs.every(c => c.match), 'official match start');
    for (const c of cs) await c.page.locator('.game-shell').waitFor();
    return cs;
  } catch (error) {
    for (const c of cs) await c.context.close();
    throw error;
  }
}

async function waitAssets(c, tiles) {
  await c.page.waitForFunction(expected => {
    let loaded = 0;
    window.__scene?.getState().scene.traverse(o => { if (o.userData.terrainAsset) loaded++; });
    return loaded === expected;
  }, tiles);
}

async function run(browser, players) {
  const id = `seafarers_official_new_shores_${players}`;
  const source = JSON.parse(await fs.readFile(path.join(__dirname, '../../app/assets/maps', id + '.json')));
  const cs = await create(browser, players, id), a = cs[0];
  try {
    const initial = a.match.state, root = source.rules.scenario.starting_islands[0];
    for (const c of cs) {
      assert.equal(c.match.state.map_id, id);
      assert.equal(c.room.ruleset_compatibility.ruleset_id, 'catan-seafarers-s3a-new-shores');
      assert.equal(c.match.state.rules_config.target_vp, 14);
      assert.equal(c.match.state.players.length, players);
      assert.deepEqual(c.match.state.scenario.rules, { starting_islands: [root], new_island_vp: 2 });
      await h.open3d(c);
    }
    const ids = s2a.islands(initial);
    assert(initial.legal.settlements.every(v => initial.vertex_adj_hexes[v].some(i => ids[i] === root)));
    assert.match(await a.page.locator('.context-prompt').innerText(), /starting island/);
    assert.equal(initial.robber_tile, source.robber_tile);
    assert.equal(initial.pirate_tile, source.pirate_tile);
    assert.equal(initial.tiles.length, source.tiles.length);
    for (const [index, tile] of source.tiles.entries()) {
      assert.equal(initial.tiles[index].terrain, tile.terrain);
      assert.equal(initial.tiles[index].number, tile.number ?? null);
      assert.equal(initial.tiles[index].q, tile.q);
      assert.equal(initial.tiles[index].r, tile.r);
    }
    await a.page.getByRole('button', { name: 'Game info', exact: true }).click();
    const info = a.page.getByRole('dialog', { name: 'Game info', exact: true });
    assert.match(await info.innerText(), /Earn 2 extra VP/);
    assert.match(await info.innerText(), /14 VP/);
    await info.getByRole('button', { name: 'Close Game info', exact: true }).click();
    check(id + ': exact-count lobby guard, fixed 14/7 settings, shared official layout and scenario summary');

    await s2a.setup(cs, root);
    assert.deepEqual(a.match.state.scenario.home_islands, Object.fromEntries(cs.map((_, pid) => [pid, [root]])));
    assert.deepEqual(a.match.state.scenario.awarded_islands, {});
    assert.equal(Object.keys(a.match.state.occupied_v).length, 2 * players);
    assert.equal(Object.keys(a.match.state.occupied_e).length + Object.keys(a.match.state.occupied_ships).length, 2 * players);
    assert(Object.keys(a.match.state.occupied_ships).length > 0);
    check(id + ': natural snake-order main-island setup with existing Road/Ship controller');

    await s2a.dice(cs, 1, 1);
    await h.action(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'official roll');
    await s2a.chooseGold(cs);
    const route = s2a.seaPath(a.match.state);
    await s2a.fund(cs, { wood: route.route.length + 1, sheep: route.route.length + 1, brick: 2, wheat: 4, ore: 4 });
    for (const edge of route.route) if (a.match.state.occupied_ships[edgeKey(edge)] == null)
      await s2a.place(cs, a, 'Ship', edge);
    assert(a.match.state.legal.settlements.includes(route.destination));
    const vp = h.own(a).vp;
    await s2a.place(cs, a, 'Settlement', route.destination, 'vertex');
    assert.equal(h.own(a).vp, vp + 3);
    const foreign = [...new Set(a.match.state.vertex_adj_hexes[route.destination].map(i => ids[i]).filter(i => i != null))][0];
    const awarded = JSON.stringify(a.match.state.scenario);
    for (const c of cs) {
      assert.equal(c.match.state.players[0].special_vp, 2);
      assert.deepEqual(c.match.state.scenario.awarded_islands, { '0': [foreign] });
      assert.match(await c.page.locator('.players-strip').innerText(), /2 island VP/);
    }
    await s2a.place(cs, a, 'City', route.destination, 'vertex');
    assert.equal(h.own(a).vp, vp + 4);
    assert.equal(JSON.stringify(a.match.state.scenario), awarded);
    await s2a.fund(cs, { wood: 1, brick: 1 });
    const road = a.match.state.legal.roads.find(edge => edge.includes(route.destination)) || a.match.state.legal.roads[0];
    assert(road);
    await s2a.place(cs, a, 'Road', road);
    check(id + ': explicitly funded paid sea crossing, +3 settlement score, city without repeat bonus and paid road');

    await waitAssets(a, initial.tiles.length);
    const metrics = await s2a.sceneChecks(a);
    assert.equal(Object.keys(metrics.terrain).length, initial.tiles.length);
    assert.equal(metrics.assets, initial.tiles.length);
    assert.equal(metrics.seaAssets, initial.tiles.filter(tile => tile.terrain === 'sea').length);
    for (const [index, tile] of initial.tiles.entries()) {
      assert.equal(metrics.terrain[index], tile.terrain);
      if (tile.number != null) assert.equal(metrics.numbers[index], tile.number);
    }
    assert(Object.values(metrics.terrain).includes('gold'));
    assert(metrics.pawns.some(p => p.piece === 'pirate' && p.tile === source.pirate_tile));
    assert(metrics.pawns.some(p => p.piece === 'robber' && p.tile === source.robber_tile));
    assert(metrics.pieces.some(p => p.vertexId === route.destination && p.level === 2 && p.owner === 0));
    assert(metrics.pieces.some(p => p.edge && edgeKey(p.edge) === edgeKey(road) && p.owner === 0));
    assert(metrics.ports.length >= initial.ports.length);
    for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }]) {
      await a.page.setViewportSize(size);
      await a.page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
      await a.page.waitForTimeout(180);
      assert.deepEqual((await s2a.sceneChecks(a)).clipped, [], `${id} framing at ${size.width}`);
    }
    await h.layout(a);
    const canvas = await a.page.locator('canvas').boundingBox();
    await a.page.mouse.move(canvas.x + canvas.width * .45, canvas.y + canvas.height * .5);
    await a.page.mouse.down();
    await a.page.mouse.move(canvas.x + canvas.width * .5, canvas.y + canvas.height * .52);
    await a.page.mouse.up();
    await a.page.mouse.wheel(0, -80);
    await a.page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
    await a.page.waitForTimeout(180);
    assert.deepEqual((await s2a.sceneChecks(a)).clipped, []);
    await h.evidence(a, id + '-3d');
    await a.page.getByRole('button', { name: '2D', exact: true }).click();
    const svg = await a.page.locator('svg[height] [data-tile-index]').evaluateAll(elements => elements.map(el => ({
      index: Number(el.dataset.tileIndex), terrain: el.dataset.terrain,
      number: el.querySelector('[data-number-token]')?.getAttribute('data-number-token') ?? null,
    })));
    assert.equal(svg.length, initial.tiles.length);
    for (const tile of svg) {
      assert.equal(tile.terrain, initial.tiles[tile.index].terrain);
      assert.equal(tile.number == null ? null : Number(tile.number), initial.tiles[tile.index].number);
    }
    assert.equal(JSON.stringify(a.match.state.scenario), awarded);
    await h.evidence(a, id + '-2d');
    await h.open3d(a);
    check(id + ': actual terrain GLBs, Sea/Gold, ports, figures, numbers, SVG parity, camera and three desktop sizes');

    const preserved = { tick: a.match.tick, vp: h.own(a).vp, scenario: a.match.state.scenario,
      occupancy: JSON.stringify([a.match.state.occupied_v, a.match.state.occupied_e, a.match.state.occupied_ships]) };
    for (const c of cs) {
      const tokens = c.tokens.length;
      await c.page.reload({ waitUntil: 'networkidle' });
      await h.wait(() => c.tokens.length > tokens && c.match.tick === preserved.tick, 'official guest credential refresh');
      await c.page.locator('.game-shell').waitFor();
      assert.deepEqual(c.match.state.scenario, preserved.scenario);
      assert.equal(c.match.state.players[0].vp, preserved.vp);
      assert.equal(JSON.stringify([c.match.state.occupied_v, c.match.state.occupied_e, c.match.state.occupied_ships]), preserved.occupancy);
    }
    h.privacy(cs);
    await h.action(cs, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'official end turn');
    assert.equal(a.match.state.turn, 1);
    assert.deepEqual(a.match.state.scenario, preserved.scenario);
    for (const c of cs) assert.deepEqual(c.jsErrors, []);
    check(id + ': all-client refresh, personalized privacy and next-turn ledger preservation without JavaScript errors');
    report.variants.push({ id, players, renderedTiles: initial.tiles.length, componentHexes: source.component_hex_count,
      naturalSetup: true, naturalFullMatch: false, testToolsFunding: true, paidRouteLength: route.route.length,
      commands: cs.reduce((count, c) => count + c.sent.length, 0),
      expectedCountRejections: 1, javascriptErrors: cs.flatMap(c => c.jsErrors),
      consoleWarnings: cs.flatMap(c => c.console), metrics });
  } finally { for (const c of cs) await c.context.close(); }
}

if (require.main === module) (async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try {
    for (const players of [3, 4]) await run(browser, players);
  } catch (error) {
    report.failure = String(error);
    throw error;
  } finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
