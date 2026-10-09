// Actual custom JSON lobby/setup/3D interactions; Test Tools funding is explicit.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18766';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-s2b-1', 'browser');
const h = require('./game-actions.cjs');
const s2a = require('./seafarers-s2a.cjs');
const report = { profiles: [], checks: [], naturalFullMatch: false, fixtureFunding: true };
const output = process.env.CATAN_E2E_OUTPUT;
const check = name => { report.checks.push(name); console.log('PASS ' + name); };
const edgeKey = edge => [...edge].sort((a, b) => a - b).join(',');
async function act(cs, c, callback, label, rejected = false) {
  return h.action(cs, c, callback, label, rejected);
}
async function run(browser, { preset, root, restricted, bonus, target }) {
  const source = JSON.parse(await fs.readFile(path.join(__dirname, '../../app/assets/maps', preset + '.json')));
  source.name = 'S2B-1 explicit custom ' + preset;
  source.rules.target_vp = target;
  source.rules.scenario = { new_island_vp: bonus, ...(restricted ? { starting_islands: [root] } : {}) };
  const cs = await h.room(browser, 's2b-1', 2, true, preset, { testMode: true, mapData: source });
  const a = cs[0];
  for (const c of cs) await h.open3d(c);
  assert(cs.every(c => c.match.state.rules_config.target_vp === target));
  assert(cs.every(c => c.room.ruleset_compatibility.ruleset_id === 'catan-seafarers-s2b-1'));
  assert.deepEqual(a.match.state.scenario.rules, { starting_islands: restricted ? [root] : null, new_island_vp: bonus });
  const initial = a.match.state, ids = s2a.islands(initial);
  const foreign = Object.entries(initial.vertex_adj_hexes).find(([, tiles]) => tiles.some(i => ids[i] === 13))[0];
  if (restricted) {
    assert(initial.legal.settlements.every(v => initial.vertex_adj_hexes[v].some(i => ids[i] === root)));
    assert.match(await a.page.locator('.context-prompt').innerText(), /starting island/);
    const before = JSON.stringify(initial.scenario);
    await h.invalidNext(a, { type: 'place_settlement', vid: Number(foreign), setup: true });
    await act(cs, a, () => h.clickTarget(a, 'vertex', initial.legal.settlements[0]), 'raw forbidden starting island', true);
    assert.equal(JSON.stringify(a.match.state.scenario), before);
    assert.deepEqual(a.match.state.occupied_v, {});
  } else {
    assert(initial.legal.settlements.some(v => initial.vertex_adj_hexes[v].some(i => ids[i] === 13)));
    assert.doesNotMatch(await a.page.locator('.context-prompt').innerText(), /starting island/);
  }
  await a.page.getByRole('button', { name: 'Game info', exact: true }).click();
  const info = a.page.getByRole('dialog', { name: 'Game info', exact: true });
  await info.waitFor();
  assert.match(await info.innerText(), new RegExp('Earn ' + bonus + ' extra VP'));
  assert.match(await info.innerText(), restricted ? /designated starting islands/ : /any island/);
  assert.match(await info.innerText(), new RegExp(target + ' VP'));
  await h.evidence(a, preset + '-scenario-info');
  await info.getByRole('button', { name: 'Close Game info', exact: true }).click();
  await s2a.setup(cs, root);
  assert.deepEqual(a.match.state.scenario.home_islands, { '0': [root], '1': [root] });
  assert.deepEqual(a.match.state.scenario.awarded_islands, {});
  check(preset + ': explicit JSON confirmed by both clients; legal opening and ship setup; scenario overview');
  await s2a.dice(cs, 1, 1);
  await act(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'real Roll');
  const route = s2a.seaPath(a.match.state);
  await s2a.fund(cs, { wood: route.route.length + 1, sheep: route.route.length + 1, brick: 2, wheat: 4, ore: 4 });
  for (const edge of route.route) if (a.match.state.occupied_ships[edgeKey(edge)] == null) await s2a.place(cs, a, 'Ship', edge);
  const vp = h.own(a).vp;
  await s2a.place(cs, a, 'Settlement', route.destination, 'vertex');
  assert.equal(h.own(a).vp, vp + 1 + bonus);
  for (const c of cs) {
    assert.equal(c.match.state.players[0].special_vp, bonus);
    assert.deepEqual(c.match.state.scenario.awarded_islands, { '0': [13] });
    assert.match(await c.page.locator('.players-strip').innerText(), new RegExp(bonus + ' island VP'));
  }
  const awarded = JSON.stringify(a.match.state.scenario), tick = a.match.tick;
  await a.page.getByRole('button', { name: 'City', exact: true }).click();
  await h.invalidNext(a, { type: 'place_settlement', vid: route.destination });
  await act(cs, a, () => h.clickTarget(a, 'vertex', route.destination), 'duplicate occupied settlement rejection', true);
  assert.equal(JSON.stringify(a.match.state.scenario), awarded);
  assert.equal(h.own(a).vp, vp + 1 + bonus);
  await s2a.place(cs, a, 'City', route.destination, 'vertex');
  assert.equal(h.own(a).vp, vp + 2 + bonus);
  assert.equal(JSON.stringify(a.match.state.scenario), awarded);
  assert(a.match.tick > tick);
  check(preset + ': paid sea crossing and public +' + bonus + ' VP; city does not repeat award');
  await h.evidence(a, preset + '-award-3d');
  await h.layout(a);
  assert(await a.page.locator('.player-hud').evaluateAll(players => players.every(player => {
    const bounds = player.getBoundingClientRect();
    return [...player.querySelectorAll('.player-counters > *')].every(counter => {
      const rect = counter.getBoundingClientRect();
      return rect.right <= bounds.right && rect.bottom <= bounds.bottom;
    });
  })), 'public bonus and existing counters must fit inside the player HUD');
  await a.page.getByRole('button', { name: '2D', exact: true }).click();
  assert.equal(await a.page.locator('svg[height]').count(), 1);
  assert.equal(JSON.stringify(a.match.state.scenario), awarded);
  await h.evidence(a, preset + '-award-2d');
  const preserved = { tick: a.match.tick, vp: h.own(a).vp, scenario: a.match.state.scenario };
  for (const c of cs) {
    const tokens = c.tokens.length;
    await c.page.reload({ waitUntil: 'networkidle' });
    await h.wait(() => c.tokens.length > tokens && c.match.tick === preserved.tick, 'verified credential refresh');
    await c.page.locator('.game-shell').waitFor();
    assert.deepEqual(c.match.state.scenario, preserved.scenario);
    assert.equal(c.match.state.players[0].vp, preserved.vp);
  }
  h.privacy(cs);
  await act(cs, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'real End Turn after award');
  assert.deepEqual(a.match.state.scenario, preserved.scenario);
  assert.equal(a.match.state.turn, 1);
  check(preset + ': 2D/3D, desktop resize, two-client refresh and turn change preserve ledger/privacy');
  for (const c of cs) assert.deepEqual(c.jsErrors, []);
  report.profiles.push({ preset, custom: true, startingIslands: restricted ? [root] : null, bonus, target,
    commands: cs.reduce((n, c) => n + c.sent.length, 0), rejected: cs.reduce((n, c) => n + c.acks.filter(a => !a.applied).length, 0),
    originalDestination: route.destination, paidRouteLength: route.route.length, finalVP: preserved.vp,
    naturalSetup: true, naturalFullMatch: false, testToolsFunding: true });
  for (const c of cs) await c.context.close();
}
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try {
    await run(browser, { preset: 'seafarers_gold_haven', root: 4, restricted: true, bonus: 2, target: 12 });
    await run(browser, { preset: 'seafarers_pirate_lanes', root: 9, restricted: false, bonus: 3, target: 14 });
  } finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
