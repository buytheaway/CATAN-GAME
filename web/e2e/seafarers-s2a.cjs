// Natural setup + explicitly funded paid expansion, with real Chrome/WS/PostgreSQL.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18766';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-s2a-hardening', 'browser');
const h = require('./game-actions.cjs');
const output = process.env.CATAN_E2E_OUTPUT;
const report = { maps: [], commands: 0, rejected: 0, checks: [] };
const key = edge => [...edge].sort((a, b) => a - b).join(',');
const check = label => { report.checks.push(label); console.log('PASS ' + label); };
async function act(cs, c, callback, label, rejected = false) {
  await h.action(cs, c, callback, label, rejected);
  report.commands++;
  if (rejected) report.rejected++;
}
function islands(s) {
  const remaining = new Set(s.tiles.flatMap((t, i) => t.terrain === 'sea' ? [] : [i])), ids = {};
  while (remaining.size) {
    const root = Math.min(...remaining), todo = [root];
    while (todo.length) {
      const i = todo.pop();
      if (!remaining.has(i)) continue;
      remaining.delete(i); ids[i] = root;
      for (const adjacent of Object.values(s.edge_adj_hexes)) if (adjacent.includes(i))
        todo.push(...adjacent.filter(t => remaining.has(t)));
    }
  }
  return ids;
}
async function chooseGold(cs) {
  while (cs[0].match.state.pending_action === 'choose_gold') {
    const c = cs[cs[0].match.state.pending_pid];
    const resource = Object.entries(c.match.state.bank_available).find(([, yes]) => yes)[0];
    await c.page.getByLabel('Gold resource').selectOption(resource);
    await c.page.getByLabel('Gold quantity').fill('1');
    await act(cs, c, () => c.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'setup Gold choice');
  }
}
async function tools(cs, callback) {
  const c = cs[0];
  await c.page.getByRole('button', { name: 'Test Tools', exact: true }).click();
  const dialog = c.page.getByRole('dialog', { name: 'Test Tools', exact: true });
  await dialog.waitFor(); await callback(c, dialog);
  await dialog.getByRole('button', { name: 'Close Test Tools', exact: true }).click();
}
async function dice(cs, one, two) {
  await tools(cs, async (c, dialog) => {
    await dialog.getByLabel('Next die 1').selectOption(String(one));
    await dialog.getByLabel('Next die 2').selectOption(String(two));
    await act(cs, c, () => dialog.getByRole('button', { name: 'Set next dice', exact: true }).click(), 'explicit next dice');
  });
}
async function fund(cs, desired) {
  await tools(cs, async (c, dialog) => {
    await dialog.getByLabel('Test player').selectOption('0');
    for (const [resource, amount] of Object.entries(desired)) {
      const missing = amount - h.own(c).res[resource];
      if (missing <= 0) continue;
      await dialog.getByLabel('Test resource').selectOption(resource);
      await dialog.getByLabel('Test amount').fill(String(missing));
      await act(cs, c, () => dialog.getByRole('button', { name: 'Give resources', exact: true }).click(), 'explicit test funding');
    }
  });
}
async function place(cs, c, name, id, type = 'edge') {
  const button = c.page.getByRole('button', { name, exact: true });
  if (await button.getAttribute('aria-pressed') !== 'true') await button.click();
  await act(cs, c, () => h.clickTarget(c, type, id), name + ' real 3D target');
}
function seaPath(s) {
  const ids = islands(s), own = Object.entries(s.occupied_v).filter(([, [pid]]) => pid === 0);
  const viable = v => !s.occupied_v[v] && !s.edges.some(e => e.includes(v)
    && s.occupied_v[e[0] === v ? e[1] : e[0]]);
  for (const [raw] of own) {
    const anchor = Number(raw), home = new Set(s.vertex_adj_hexes[anchor].map(i => ids[i]).filter(i => i != null));
    const queue = [[anchor, []]], seen = new Set([anchor]);
    for (let index = 0; index < queue.length; index++) {
      const [v, route] = queue[index];
      if (route.length && viable(v) && s.vertex_adj_hexes[v].some(i => ids[i] != null && !home.has(ids[i])))
        return { destination: v, route };
      for (const edge of s.edges) {
        const adjacent = s.edge_adj_hexes[key(edge)];
        if (!edge.includes(v) || !adjacent.some(i => s.tiles[i].terrain === 'sea') || adjacent.includes(s.pirate_tile)) continue;
        if (s.occupied_e[key(edge)] != null || (s.occupied_ships[key(edge)] != null && s.occupied_ships[key(edge)] !== 0)) continue;
        const next = edge[0] === v ? edge[1] : edge[0];
        if (seen.has(next) || (s.occupied_v[next] && s.occupied_v[next][0] !== 0)) continue;
        seen.add(next); queue.push([next, [...route, edge]]);
      }
    }
  }
  throw Error('No navigable path between islands');
}
async function setup(cs) {
  while (cs[0].match.state.phase === 'setup') {
    await chooseGold(cs);
    const c = cs[cs[0].match.state.turn], s = c.match.state;
    if (s.setup_need === 'settlement') {
      const ids = islands(s), roots = [...new Set(Object.values(ids))].sort((a, b) => a - b);
      const first = !Object.values(s.occupied_v).some(([pid]) => pid === s.turn);
      const coast = s.legal.settlements.filter(v => s.vertex_adj_hexes[v].some(t => s.tiles[t].terrain === 'sea'));
      const gold = coast.filter(v => s.vertex_adj_hexes[v].some(t => s.tiles[t].terrain === 'gold'));
      const home = coast.filter(v => s.vertex_adj_hexes[v].some(t => ids[t] === roots[0]));
      const targets = first && home.length ? home : gold.length ? gold : coast.length ? coast : s.legal.settlements;
      // Capacity/coordinates choose test starting positions, never client legality.
      targets.sort((a, b) => s.vertices[b][0] - s.vertices[a][0] || a - b);
      await act(cs, c, () => h.clickTarget(c, 'vertex', targets[0]), 'natural starting settlement');
    } else {
      const ship = s.legal.ships[0], road = s.legal.roads[0];
      await place(cs, c, ship ? 'Ship' : 'Road', ship || road);
    }
  }
  await chooseGold(cs);
}
async function sceneChecks(c) {
  return c.page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState();
    scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
    const terrain = {}, ports = [], pieces = [], pawns = [], clipped = [], numbers = {};
    let assets = 0, seaAssets = 0;
    scene.traverse(o => {
      const d = o.userData;
      if (d.tileIndex != null && d.terrain) {
        terrain[d.tileIndex] = d.terrain;
        const p = o.getWorldPosition(o.position.clone()).project(camera);
        if (Math.abs(p.x) > 1 || Math.abs(p.y) > 1) clipped.push(d.tileIndex);
      }
      if (d.kind && d.edge && !d.targetType) ports.push({ edge: d.edge, kind: d.kind });
      if (d.owner != null) pieces.push({ owner: d.owner, edge: d.edge, vertexId: d.vertexId, level: d.level });
      if (d.tileIndex != null && d.piece) pawns.push({ tile: d.tileIndex, piece: d.piece });
      if (d.terrainAsset) { assets++; if (d.terrainAsset === 'sea') seaAssets++; }
      if (d.number != null) {
        let parent = o.parent;
        while (parent && parent.userData.tileIndex == null) parent = parent.parent;
        if (parent) numbers[parent.userData.tileIndex] = d.number;
      }
    });
    return { terrain, ports, pieces, pawns, clipped, assets, seaAssets, numbers,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
  });
}
async function run(browser, preset) {
  const cs = await h.room(browser, 's2a', 2, true, preset, { testMode: true });
  const a = cs[0]; for (const c of cs) await h.open3d(c);
  let s = a.match.state;
  assert.equal(s.tiles.length, 37); assert.equal(new Set(Object.values(islands(s))).size, 2);
  assert.equal(s.ports.length, 9);
  if (preset === 'seafarers_gold_haven') assert.equal(s.robber_tile, -1);
  await setup(cs); check(preset + ': two-client lobby selection and natural setup including ships/Gold');
  await dice(cs, 1, 1);
  await act(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'real Roll');
  await chooseGold(cs);
  const route = seaPath(a.match.state);
  await fund(cs, { wood: route.route.length + 1, sheep: route.route.length + 1, brick: 2, wheat: 4, ore: 4 });
  const first = route.route.find(e => a.match.state.occupied_ships[key(e)] == null);
  assert(first && a.match.state.legal.ships.some(e => key(e) === key(first)));
  const shipButton = a.page.getByRole('button', { name: 'Ship', exact: true });
  if (await shipButton.getAttribute('aria-pressed') !== 'true') await shipButton.click();
  await h.invalidNext(a, { type: 'build_ship', eid: [99998, 99999] });
  const before = JSON.stringify(a.match.state.occupied_ships);
  await act(cs, a, () => h.clickTarget(a, 'edge', first), 'invalid coordinate rejected', true);
  assert.equal(JSON.stringify(a.match.state.occupied_ships), before);
  for (const edge of route.route) if (a.match.state.occupied_ships[key(edge)] == null) await place(cs, a, 'Ship', edge);
  assert(a.match.state.legal.settlements.includes(route.destination));
  const oldVP = h.own(a).vp;
  await place(cs, a, 'Settlement', route.destination, 'vertex');
  assert.equal(h.own(a).vp, oldVP + 1);
  await place(cs, a, 'City', route.destination, 'vertex');
  assert.equal(a.match.state.occupied_v[route.destination][1], 2);
  // A paid road stays attached to the same city; choose the supplied legal edge.
  await fund(cs, { wood: 1, brick: 1 });
  const road = a.match.state.legal.roads.find(e => e.includes(route.destination)) || a.match.state.legal.roads[0];
  assert(road); await place(cs, a, 'Road', road);
  check(preset + ': paid sea crossing, destination settlement/city and road, shared IDs and ordinary VP');
  await tools(cs, async (c, dialog) => {
    await dialog.getByLabel('Test player').selectOption('0');
    await dialog.getByLabel('Test card').selectOption('knight');
    await act(cs, c, () => dialog.getByRole('button', { name: 'Give development card', exact: true }).click(), 'explicit matured Knight');
  });
  await act(cs, a, () => a.page.locator('.dev-mini-card').filter({ hasText: 'Knight' }).click(), 'Knight figure choice');
  const sea = a.match.state.legal.pirate_tiles.find(i => !(a.match.state.legal.pirate_victims[i] || []).length);
  await place(cs, a, 'Pirate', sea, 'tile');
  assert.equal(a.match.state.pirate_tile, sea);
  if (preset === 'seafarers_gold_haven') assert.equal(a.match.state.robber_tile, -1);
  check(preset + ': pirate legal sea movement consumes one event without moving robber');
  const ports = a.match.state.ports, occupied = JSON.stringify(a.match.state.occupied_v);
  const metrics = await sceneChecks(a);
  assert.equal(Object.keys(metrics.terrain).length, 37); assert.equal(metrics.clipped.length, 0);
  assert.equal(metrics.assets, 37);
  assert.equal(metrics.seaAssets, a.match.state.tiles.filter(t => t.terrain === 'sea').length);
  for (const [i, tile] of a.match.state.tiles.entries()) assert.equal(metrics.terrain[i], tile.terrain);
  for (const [i, tile] of a.match.state.tiles.entries()) if (tile.number != null) assert.equal(metrics.numbers[i], tile.number);
  assert(metrics.pieces.some(p => p.vertexId === route.destination && p.level === 2 && p.owner === 0));
  assert(metrics.pieces.some(p => p.edge && key(p.edge) === key(road) && p.owner === 0));
  assert(metrics.ports.length >= ports.length);
  for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }]) {
    await a.page.setViewportSize(size); await a.page.waitForTimeout(150);
    assert.deepEqual((await sceneChecks(a)).clipped, []);
  }
  await h.layout(a);
  const rect = await a.page.locator('canvas').boundingBox();
  await a.page.mouse.move(rect.x + rect.width * .45, rect.y + rect.height * .5);
  await a.page.mouse.down(); await a.page.mouse.move(rect.x + rect.width * .50, rect.y + rect.height * .52); await a.page.mouse.up();
  await a.page.mouse.wheel(0, -80);
  await a.page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
  // Reset is applied by CameraRig's React effect, after the DOM click returns.
  await a.page.waitForFunction(() => {
    const { scene, camera } = window.__scene.getState();
    scene.updateMatrixWorld(true); camera.updateMatrixWorld(true);
    const visible = [];
    scene.traverse(o => {
      if (o.userData.tileIndex == null || !o.userData.terrain) return;
      const p = o.getWorldPosition(o.position.clone()).project(camera);
      visible.push(Math.abs(p.x) <= 1 && Math.abs(p.y) <= 1);
    });
    return visible.length === 37 && visible.every(Boolean);
  });
  assert.deepEqual((await sceneChecks(a)).clipped, []);
  await h.evidence(a, preset + '-3d');
  await a.page.getByRole('button', { name: '2D', exact: true }).click();
  assert.equal(await a.page.locator('svg[height]').count(), 1);
  assert.equal(JSON.stringify(a.match.state.occupied_v), occupied);
  await h.evidence(a, preset + '-2d'); await h.open3d(a);
  const tick = a.match.tick, tokens = a.tokens.length;
  await a.page.reload({ waitUntil: 'networkidle' });
  await h.wait(() => a.tokens.length > tokens && a.match.tick === tick, 'verified guest refresh');
  await a.page.locator('.game-shell').waitFor();
  assert.equal(JSON.stringify(a.match.state.occupied_v), occupied);
  h.privacy(cs);
  check(preset + ': 3D/SVG, port/piece positions, camera/orbit/zoom/resize and durable refresh');
  await act(cs, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'real End Turn');
  await dice(cs, 1, 1);
  await act(cs, cs[1], () => cs[1].page.getByRole('button', { name: 'Roll', exact: true }).click(), 'opponent Roll');
  await chooseGold(cs);
  await act(cs, cs[1], () => cs[1].page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'opponent End Turn');
  await dice(cs, 6, 1);
  await act(cs, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'real Seven');
  while (a.match.state.pending_action === 'discard') {
    const c = cs.find(c => (c.match.state.discard_required[c.match.state.you_pid] || 0) > 0);
    assert(c);
    let need = c.match.state.discard_required[c.match.state.you_pid];
    const hand = h.own(c).res;
    for (const resource of ['wood', 'brick', 'sheep', 'wheat', 'ore']) {
      const count = Math.min(hand[resource], need);
      for (let i = 0; i < count; i++) await c.page.getByRole('button', { name: 'Discard ' + resource, exact: true }).click();
      need -= count;
    }
    assert.equal(need, 0);
    await act(cs, c, () => c.page.getByRole('button', { name: 'Confirm Discard', exact: true }).click(), 'real required discard');
  }
  const land = a.match.state.legal.robber_tiles.find(i => !(a.match.state.legal.robber_victims[i] || []).length);
  assert.notEqual(land, undefined);
  await place(cs, a, 'Robber', land, 'tile');
  assert.equal(a.match.state.robber_tile, land);
  assert.equal(a.match.state.pending_action, null);
  assert((await sceneChecks(a)).pawns.some(p => p.piece === 'robber' && p.tile === land));
  check(preset + ': next turn, Seven/discard and real land placement from initial robber state');
  report.maps.push({ preset, tiles: s.tiles.length, islands: [...new Set(Object.values(islands(s)))].length,
    paidRouteLength: route.route.length, metrics, naturalFullMatch: false });
  for (const c of cs) { assert.deepEqual(c.jsErrors, []); await c.context.close(); }
}
(async () => {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try { for (const preset of ['seafarers_gold_haven', 'seafarers_pirate_lanes']) await run(browser, preset); }
  finally { await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2)); await browser.close(); }
})().catch(error => { console.error(error); process.exitCode = 1; });
