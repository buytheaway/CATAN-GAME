// Real Chrome + nginx/WebSocket integration. No mocked snapshots or application test hooks.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const origin = process.env.CATAN_E2E_ORIGIN || 'http://127.0.0.1:18080';
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-game-ux-2-1');
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
async function wait(predicate, label) {
  const deadline = Date.now() + 20000;
  while (!predicate()) {
    if (Date.now() > deadline) throw Error('Timeout: ' + label);
    await sleep(40);
  }
}
function observe() {
  let id = 0;
  const Native = window.WebSocket;
  window.__sockets = [];
  window.WebSocket = class extends Native {
    constructor(...args) { super(...args); window.__sockets.push(this); }
    send(raw) {
      const message = JSON.parse(raw);
      if (message.type === 'rematch' && window.__dropNextRematch) {
        delete window.__dropNextRematch;
        this.close(); // Deliberately lose this control request; reconnect must permit a retry.
        return;
      }
      // Explicit fault injection for rejection tests, preserving real command identity/sequence.
      if (message.type === 'cmd' && window.__nextInvalidCommand) {
        message.cmd = window.__nextInvalidCommand;
        delete window.__nextInvalidCommand;
      }
      return super.send(JSON.stringify(message));
    }
  };
  // Read-only React DevTools observation of the real Three scene for mouse hit testing.
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, inject: () => ++id, checkDCE() {},
    onCommitFiberRoot(_, root) {
      const store = root.current?.stateNode?.containerInfo;
      if (store?.getState && store.getState().scene) window.__scene = store;
    },
    onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
  };
}
async function newClient(browser, name) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 720 } });
  await context.addInitScript(observe);
  const page = await context.newPage();
  page.setDefaultTimeout(12000);
  const c = { context, page, name, match: null, room: null, sent: [], acks: [], errors: [], jsErrors: [], console: [], tokens: [] };
  page.on('pageerror', e => c.jsErrors.push(e.message));
  page.on('console', m => { if (m.type() === 'error' || m.type() === 'warning') c.console.push(m.text()); });
  page.on('websocket', socket => {
    assert.equal(socket.url(), origin.replace(/^http/, 'ws') + '/ws');
    socket.on('framereceived', ({ payload }) => {
      const m = JSON.parse(String(payload));
      if (m.type === 'match_state') c.match = m;
      if (m.type === 'room_state') c.room = m;
      if (m.type === 'error') c.errors.push(m);
      if (m.type === 'cmd_ack') c.acks.push(m);
      if (m.type === 'reconnect_token') c.tokens.push(m);
    });
    socket.on('framesent', ({ payload }) => { const m = JSON.parse(String(payload)); if (m.type === 'cmd') c.sent.push(m); });
  });
  await page.goto(origin, { waitUntil: 'networkidle' });
  await page.getByLabel('Name', { exact: true }).fill(name);
  return c;
}
const own = c => c.match.state.players.find(p => p.pid === c.match.state.you_pid);
function privacy(clients) {
  for (const c of clients) {
    const s = c.match.state;
    assert(!('seed' in s)); assert(!('bank' in s)); assert(!('dev_deck' in s));
    assert(s.bank_available && Object.values(s.bank_available).every(v => typeof v === 'boolean'));
    for (const p of s.players) if (p.pid !== s.you_pid) {
      assert(!('res' in p)); assert(!('dev_cards' in p));
      assert.equal(typeof p.resource_count, 'number'); assert.equal(typeof p.dev_count, 'number');
    }
  }
}
async function room(browser, mode, count = 2, natural = false, mapId = 'base_standard') {
  const clients = [];
  for (const name of ['Alice', 'Bob', 'Cara'].slice(0, count)) clients.push(await newClient(browser, `${natural ? 'natural' : 'fixture-' + mode} ${name}`));
  const a = clients[0];
  await a.page.getByLabel('Max players').fill(String(count));
  await a.page.getByRole('button', { name: 'Host', exact: true }).click();
  await wait(() => a.room, 'create room');
  for (const c of clients.slice(1)) {
    await c.page.getByLabel('Room code').fill(a.room.room_code);
    await c.page.getByRole('button', { name: 'Join', exact: true }).click();
    await wait(() => c.room, 'join');
  }
  await wait(() => a.room.players.filter(p => p.connected).length === count, 'all participants');
  if (mapId !== 'base_standard') {
    await a.page.getByLabel('Map preset').selectOption(mapId);
    await wait(() => clients.every(c => c.room.map_id === mapId), 'confirmed preset on both clients');
  }
  await a.page.getByRole('button', { name: 'Start Match', exact: true }).click();
  await wait(() => clients.every(c => c.match), 'start ' + mode);
  for (const c of clients) await c.page.locator('.game-shell').waitFor();
  privacy(clients);
  return clients;
}
async function action(clients, c, run, label, rejected = false) {
  const tick = clients[0].match.tick, count = c.sent.length;
  await run();
  await wait(() => c.sent.length > count, label + ' send');
  const request = c.sent[count];
  await wait(() => c.acks.some(a => a.cmd_id === request.cmd_id), label + ' ACK');
  const ack = c.acks.find(a => a.cmd_id === request.cmd_id);
  assert.equal(ack.applied, !rejected, label + ': ' + JSON.stringify(c.errors.at(-1)));
  if (rejected) clients.forEach(x => assert.equal(x.match.tick, tick, 'rejected tick'));
  else await wait(() => clients.every(x => x.match.tick > tick), label + ' snapshots');
  await c.page.waitForFunction(() => !document.querySelector('.board-command-surface[aria-busy="true"]'));
  await sleep(80); // Allow committed effects and legal-target reconciliation before the next mouse action.
  privacy(clients);
  return request.cmd;
}
async function invalidNext(c, cmd) { await c.page.evaluate(value => { window.__nextInvalidCommand = value; }, cmd); }
async function openDev(c, card) {
  await c.page.locator('.dev-mini-card').filter({ hasText: card }).click();
  const panel = c.page.getByRole('dialog', { name: 'Development cards', exact: true });
  await panel.waitFor();
  if (card) await panel.locator('.dev-card-choice').filter({ hasText: card }).click();
  return panel;
}
async function openTrade(c, players = false) {
  await c.page.locator('.resource-hand button[data-resource="wood"]').click();
  const panel = c.page.getByRole('dialog', { name: 'Trade tray', exact: true });
  await panel.waitFor();
  if (!players) await panel.getByLabel('Offer target').selectOption('bank');
  return panel;
}
async function open3d(c) {
  await c.page.getByRole('button', { name: '3D', exact: true }).click();
  await c.page.locator('canvas').waitFor();
  await c.page.waitForFunction(() => window.__scene?.getState().scene.children.length > 5);
}
const edgeId = e => [...e].sort((a, b) => a - b).join(',');
async function clickTarget(c, type, originalId) {
  const id = type === 'edge' ? edgeId(originalId) : originalId;
  await c.page.waitForFunction(({ type, id }) => {
    let found = false;
    window.__scene?.getState().scene.traverse(o => {
      const d = o.userData;
      if (type === 'vertex' && d.targetType === type && d.vertexId === id) found = true;
      if (type === 'edge' && d.targetType === type && d.edge.join(',') === id) found = true;
      if (type === 'tile' && d.terrain && d.tileIndex === id && d.legal) found = true;
    });
    return found;
  }, { type, id });
  const point = await c.page.evaluate(({ type, id }) => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    let target;
    scene.traverse(o => {
      const d = o.userData;
      if (type === 'vertex' && d.targetType === type && d.vertexId === id) target = o;
      if (type === 'edge' && d.targetType === type && d.edge.join(',') === id) target = o;
      if (type === 'tile' && d.terrain && d.tileIndex === id && d.legal) target = o.children[0];
    });
    if (!target) throw Error('Missing legal target ' + type + ' ' + id);
    const p = target.getWorldPosition(target.position.clone()); if (type === 'tile') p.y += .3; p.project(camera);
    const r = gl.domElement.getBoundingClientRect();
    return { x: r.x + (p.x + 1) * r.width / 2, y: r.y + (1 - p.y) * r.height / 2 };
  }, { type, id });
  await c.page.mouse.move(point.x, point.y); await c.page.mouse.click(point.x, point.y);
}
async function evidence(c, name) { await c.page.screenshot({ path: path.join(output, name + '.png'), fullPage: true }); }
async function layout(c) {
  for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }]) {
    await c.page.setViewportSize(size); await sleep(150);
    const dimensions = await c.page.evaluate(() => {
      const r = e => { const p = e.getBoundingClientRect(); return { x: p.x, y: p.y, right: p.right, bottom: p.bottom }; };
      return { width: innerWidth, height: innerHeight, scroll: document.documentElement.scrollWidth,
        hands: r(document.querySelector('.personal-hands')), dock: r(document.querySelector('.action-dock')),
        cards: [...document.querySelectorAll('.dev-mini-card')].map(r) };
    });
    assert(dimensions.scroll <= size.width, 'horizontal page overflow');
    assert(dimensions.hands.right <= dimensions.dock.x + 1, 'hand/action dock overlap');
    for (const card of dimensions.cards) assert(card.y >= 0 && card.bottom <= size.height, 'card outside viewport');
  }
  await c.page.setViewportSize({ width: 1280, height: 720 });
}
async function bank(clients, ratio) {
  const a = clients[0], panel = await openTrade(a), before = { ...own(a).res };
  for (let i = 1; i < ratio; i++) await a.page.locator('.resource-hand button[data-resource="wood"]').click();
  await panel.getByRole('button', { name: 'Want ore', exact: true }).click();
  assert.equal(await panel.getByLabel(`Trade ratio ${ratio}:1`).count(), 1);
  await evidence(a, 'bank-tray-' + ratio);
  if (ratio === 4) {
    await invalidNext(a, { type: 'trade_bank', give: 'wood', get: 'wood', get_qty: 1 });
    await action(clients, a, () => panel.getByRole('button', { name: 'Trade with bank' }).click(), 'invalid bank', true);
    assert.deepEqual(own(a).res, before);
    assert.equal(await panel.locator('button[data-resource="ore"]').getAttribute('data-count'), '1');
    assert(await panel.getByRole('alert').isVisible());
  }
  const cmd = await action(clients, a, () => panel.getByRole('button', { name: 'Trade with bank' }).click(), `bank ${ratio}:1`);
  assert.deepEqual(cmd, { type: 'trade_bank', give: 'wood', get: 'ore', get_qty: 1 });
  assert.equal(own(a).res.wood, before.wood - ratio); assert.equal(own(a).res.ore, before.ore + 1);
  await evidence(a, 'bank-' + ratio); assert.equal(await panel.count(), 0);
}
async function offer(clients) {
  const [a, b] = clients;
  const draft = async () => {
    const panel = await openTrade(a, true);
    await a.page.locator('.resource-hand button[data-resource="wood"]').click();
    await panel.getByRole('button', { name: 'Want ore', exact: true }).click();
    return panel;
  };
  let panel = await draft();
  await panel.getByLabel('Offer target').selectOption('1');
  const before = clients.map(c => ({ ...own(c).res }));
  await action(clients, a, () => panel.getByRole('button', { name: 'Send offer' }).click(), 'target offer');
  const incoming = b.page.getByRole('dialog', { name: 'Trade offers', exact: true });
  await incoming.waitFor(); await evidence(b, 'incoming-trade');
  await action(clients, b, () => incoming.getByRole('button', { name: 'Accept', exact: true }).click(), 'accept off-turn');
  assert.equal(own(a).res.wood, before[0].wood - 2); assert.equal(own(a).res.ore, before[0].ore + 1);
  assert.equal(own(b).res.wood, before[1].wood + 2); assert.equal(own(b).res.ore, before[1].ore - 1);
  assert.equal(a.match.state.trade_offers[0].status, 'accepted');
  panel = await draft();
  await action(clients, a, () => panel.getByRole('button', { name: 'Send offer' }).click(), 'broadcast offer');
  await action(clients, b, () => incoming.getByRole('button', { name: 'Reject', exact: true }).click(), 'reject broadcast');
  assert.equal(a.match.state.trade_offers.at(-1).status, 'declined');
  panel = await draft();
  await action(clients, a, () => panel.getByRole('button', { name: 'Send offer' }).click(), 'offer to cancel');
  await action(clients, a, () => a.page.getByRole('button', { name: 'Cancel offer', exact: true }).click(), 'cancel offer');
  assert.equal(a.match.state.trade_offers.at(-1).status, 'canceled');
  panel = await draft();
  await action(clients, a, () => panel.getByRole('button', { name: 'Send offer' }).click(), 'offer before end');
  await action(clients, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'end closes offers');
  assert.equal(a.match.state.trade_offers.at(-1).status, 'canceled');
  assert.equal(await incoming.count(), 0);
}
async function buy(clients) {
  const [a, b] = clients, before = { ...own(a).res };
  await action(clients, a, () => a.page.getByRole('button', { name: 'Dev Card', exact: true }).click(), 'buy card');
  assert.deepEqual(own(a).dev_cards, [{ type: 'knight', new: true }]);
  for (const r of ['ore', 'sheep', 'wheat']) assert.equal(own(a).res[r], before[r] - 1);
  const panel = await openDev(a, 'Knight');
  assert(await panel.getByRole('button', { name: 'Play Knight' }).isDisabled());
  assert((await panel.innerText()).includes('bought this turn'));
  // A malicious attempt uses a real consumed command, and must leave the new card/hand intact.
  const unchanged = JSON.stringify(a.match.state);
  await invalidNext(a, { type: 'play_dev', card: 'knight' });
  await panel.getByRole('button', { name: 'Close Development cards' }).click();
  await action(clients, a, () => a.page.getByRole('button', { name: 'Dev Card', exact: true }).click(), 'new-card rejection', true);
  assert.equal(JSON.stringify(a.match.state), unchanged);
  await action(clients, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'age card end');
  await action(clients, b, () => b.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'second player roll');
  await action(clients, b, () => b.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'next own turn');
  assert.equal(own(a).dev_cards[0].new, false);
  const next = await openDev(a, 'Knight');
  assert(await next.getByRole('button', { name: 'Play Knight' }).isEnabled(), 'older card playable before roll');
  await evidence(a, 'bought-card-aged');
}
async function knight(clients) {
  const a = clients[0]; await open3d(a);
  const panel = await openDev(a, 'Knight'), count = own(a).dev_cards.length;
  await action(clients, a, () => panel.getByRole('button', { name: 'Play Knight' }).click(), 'Knight before roll');
  assert.equal(a.match.state.pending_action, 'robber_move'); assert.equal(a.match.state.rolled, false);
  assert.equal(own(a).dev_cards.length, count - 1);
  const legal = a.match.state.legal;
  const tile = legal.robber_tiles.find(t => legal.robber_victims[t]?.length) ?? legal.robber_tiles[0];
  const many = legal.robber_victims[tile]?.length > 1;
  if (many) {
    const commands = a.sent.length;
    await clickTarget(a, 'tile', tile); await a.page.getByRole('dialog', { name: 'Choose player' }).waitFor();
    assert.equal(a.sent.length, commands, 'victim UI does not mutate state');
    const name = a.match.state.players.find(p => p.pid === legal.robber_victims[tile][0]).name;
    await action(clients, a, () => a.page.getByRole('dialog', { name: 'Choose player' }).getByRole('button', { name, exact: true }).click(), 'Knight victim');
  } else await action(clients, a, () => clickTarget(a, 'tile', tile), 'Knight robber');
  assert.equal(a.match.state.robber_tile, tile); assert.equal(a.match.state.pending_action, null);
  const dev = await openDev(a, 'Monopoly');
  assert(await dev.getByRole('button', { name: 'Play Monopoly' }).isDisabled());
  await dev.getByRole('button', { name: 'Close Development cards' }).click();
  await action(clients, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'roll after Knight');
  const again = await openDev(a, 'Monopoly'), unchanged = JSON.stringify(a.match.state);
  await invalidNext(a, { type: 'play_dev', card: 'monopoly', r: 'wood' });
  await again.getByRole('button', { name: 'Close Development cards' }).click();
  await action(clients, a, () => a.page.getByRole('button', { name: 'Dev Card', exact: true }).click(), 'second-card rejection', true);
  assert.equal(JSON.stringify(a.match.state), unchanged);
}
async function road(clients) {
  const a = clients[0]; await open3d(a); const before = { ...own(a).res };
  const panel = await openDev(a, 'Road Building');
  await action(clients, a, () => panel.getByRole('button', { name: 'Play Road Building' }).click(), 'Road Building');
  for (const step of [1, 2]) {
    assert.equal(a.match.state.free_roads['0'], 3 - step); assert.equal(a.match.state.legal.road_free, true);
    assert((await a.page.locator('.context-prompt').innerText()).includes(`Place road ${step} of 2`));
    await evidence(a, 'road-building-' + step);
    const edge = a.match.state.legal.roads[0]; assert(edge);
    const cmd = await action(clients, a, () => clickTarget(a, 'edge', edge), 'free road ' + step);
    assert.equal(cmd.free, true); assert.equal(a.match.state.occupied_e[edgeId(edge)], 0);
    assert.deepEqual(own(a).res, before);
  }
  assert.equal(a.match.state.free_roads['0'], 0); assert.equal(a.match.state.rolled, false);
}
async function plenty(clients) {
  const a = clients[0], panel = await openDev(a, 'Year of Plenty');
  assert(await panel.getByRole('button', { name: 'Play Year of Plenty' }).isDisabled());
  await panel.getByLabel('Choose resources wood', { exact: true }).fill('2');
  const before = JSON.stringify(a.match.state);
  await action(clients, a, () => panel.getByRole('button', { name: 'Play Year of Plenty' }).click(), 'limited bank rejects two wood', true);
  assert.equal(JSON.stringify(a.match.state), before); assert(await panel.getByRole('alert').isVisible());
  assert.equal(await panel.getByLabel('Choose resources wood', { exact: true }).inputValue(), '2');
  await panel.getByLabel('Choose resources wood', { exact: true }).fill('1');
  await panel.getByLabel('Choose resources ore', { exact: true }).fill('1');
  const hand = { ...own(a).res };
  await action(clients, a, () => panel.getByRole('button', { name: 'Play Year of Plenty' }).click(), 'corrected plenty');
  assert.equal(own(a).res.wood, hand.wood + 1); assert.equal(own(a).res.ore, hand.ore + 1);
  assert(!own(a).dev_cards.some(c => c.type === 'year_of_plenty'));
  await evidence(a, 'year-of-plenty');
}
async function monopoly(clients) {
  const a = clients[0], before = own(a).res.wood;
  const total = clients.slice(1).reduce((n, c) => n + own(c).res.wood, 0);
  const panel = await openDev(a, 'Monopoly');
  await panel.getByLabel('Monopoly resource').selectOption('wood');
  await action(clients, a, () => panel.getByRole('button', { name: 'Play Monopoly' }).click(), 'Monopoly');
  assert.equal(own(a).res.wood, before + total); clients.slice(1).forEach(c => assert.equal(own(c).res.wood, 0));
  assert.equal(a.match.state.dev_played_turn['0'], true); await evidence(a, 'monopoly');
}
async function passive(clients) {
  const a = clients[0];
  assert.equal(own(a).vp, 3); assert.equal(a.match.state.players[1].vp, 2); assert.equal(own(clients[1]).vp, 3);
  await layout(a); const panel = await openDev(a, 'Victory Point');
  assert.equal(await panel.getByRole('button', { name: 'Play Victory Point' }).count(), 0);
  await evidence(a, 'private-development-hand');
  await a.page.keyboard.press('Escape'); assert.equal(await panel.count(), 0);
}
async function victory(clients) {
  const a = clients[0]; await open3d(a);
  assert.equal(a.match.state.players[1].vp, 6); assert.equal(own(clients[1]).vp, 7);
  await action(clients, a, () => a.page.getByRole('button', { name: 'Dev Card', exact: true }).click(), 'winning VP buy');
  for (const c of clients) {
    assert.equal(c.match.state.game_over, true); assert.equal(c.match.state.winner_pid, 0);
    assert.equal(c.match.state.players[0].vp, 10); assert.equal(c.match.state.players[1].vp, 7);
    await c.page.getByRole('dialog', { name: 'Match results' }).waitFor();
    assert.equal(await c.page.getByRole('button', { name: 'Roll', exact: true }).count(), 0);
    assert.equal(await c.page.getByRole('button', { name: 'Build', exact: true }).count(), 0);
    assert.equal(await c.page.getByRole('button', { name: 'Trade', exact: true }).count(), 0);
    assert.equal(await c.page.getByRole('button', { name: 'End Turn', exact: true }).count(), 0);
  }
  privacy(clients); await evidence(a, 'match-results');
  // Deliberate raw post-game command; no later commands in this old match (rematch resets sequences).
  // Reject on the other client so the host's lost-rematch test starts without a stale error.
  const other = clients.at(-1), unchanged = JSON.stringify(other.match.state), seq = (other.sent.at(-1)?.seq ?? 0) + 1;
  await action(clients, other, () => other.page.evaluate(({ seq, match_id }) => window.__sockets.at(-1).send(JSON.stringify({
    type: 'cmd', cmd_id: 'post-game-check-' + crypto.randomUUID(), seq, match_id, cmd: { type: 'end_turn' },
  })), { seq, match_id: other.match.match_id }), 'post-game rejection', true);
  assert.equal(JSON.stringify(other.match.state), unchanged);
}
async function rematch(clients, disconnectedHost = false) {
  await victory(clients);
  let connected = clients;
  if (disconnectedHost) {
    await clients[0].context.close(); connected = clients.slice(1);
    await wait(() => connected.every(c => !c.room.players[0].connected), 'disconnected old host');
  }
  const starter = connected[0], old = starter.match.match_id;
  if (!disconnectedHost) {
    const tokens = starter.tokens.length;
    await starter.page.evaluate(() => { window.__dropNextRematch = true; });
    await starter.page.getByRole('button', { name: 'Rematch', exact: true }).click();
    await wait(() => starter.tokens.length > tokens, 'lost rematch reconnect');
    assert.equal(starter.match.match_id, old);
    await starter.page.waitForFunction(() => {
      const button = [...document.querySelectorAll('button')].find(b => b.textContent === 'Rematch');
      return button && !button.disabled;
    });
  }
  await starter.page.getByRole('button', { name: 'Rematch', exact: true }).click();
  await wait(() => connected.every(c => c.match.match_id === old + 1), 'rematch');
  connected.forEach((c, pid) => {
    assert.equal(c.match.tick, 0); assert.equal(c.match.state.phase, 'setup');
    assert.equal(c.match.state.players.length, connected.length); assert.equal(c.match.state.you_pid, pid);
    assert.equal(own(c).name, c.name); assert.equal(own(c).dev_cards.length, 0);
    assert.equal(c.match.state.game_over, false); assert.equal(c.tokens.at(-1).last_seq_applied, 0);
  });
  assert.equal(starter.room.host_pid, 0); privacy(connected);
  await open3d(starter);
  await action(connected, starter, () => clickTarget(starter, 'vertex', starter.match.state.legal.settlements[0]), 'first rematch placement');
  assert.equal(starter.sent.at(-1).seq, 1, 'sequence reset');
  const refreshed = connected.at(-1), roomCode = refreshed.room.room_code, pid = refreshed.match.state.you_pid;
  refreshed.match = null; await refreshed.page.reload({ waitUntil: 'networkidle' });
  await refreshed.page.getByLabel('Name', { exact: true }).fill(refreshed.name);
  await refreshed.page.getByLabel('Room code').fill(roomCode);
  await refreshed.page.getByRole('button', { name: 'Join', exact: true }).click();
  await wait(() => refreshed.match?.match_id === old + 1, 'refresh/reconnect');
  assert.equal(refreshed.match.state.you_pid, pid); assert.equal(own(refreshed).name, refreshed.name);
  assert.equal(refreshed.match.tick, starter.match.tick); privacy(connected);
}
async function exit(clients) {
  await victory(clients); const a = clients[0], b = clients[1], code = a.room.room_code;
  await a.page.getByRole('button', { name: 'Back to Lobby', exact: true }).click();
  await a.page.getByRole('button', { name: 'Host', exact: true }).waitFor();
  await wait(() => !b.room.players[0].connected, 'explicit leave broadcast');
  await sleep(700);
  assert.equal(await a.page.locator('.game-shell').count(), 0);
  assert.equal(await a.page.evaluate(() => window.__sockets.filter(s => s.readyState === 1).length), 0);
  // Existing reconnect cache is scoped to room/name; LobbyPage starts with its default name.
  await a.page.getByLabel('Name', { exact: true }).fill(a.name);
  await a.page.getByLabel('Room code').fill(code);
  await a.page.getByRole('button', { name: 'Join', exact: true }).click();
  await a.page.getByRole('dialog', { name: 'Match results' }).waitFor();
  assert.equal(a.match.state.you_pid, 0); assert.equal(own(a).name, a.name);
}
async function setup(clients) {
  for (const c of clients) await open3d(c);
  while (clients[0].match.state.phase === 'setup') {
    const c = clients[clients[0].match.state.turn], s = c.match.state;
    const settlement = s.setup_need === 'settlement';
    await action(clients, c, () => clickTarget(c, settlement ? 'vertex' : 'edge',
      settlement ? s.legal.settlements[0] : s.legal.roads[0]), 'natural setup');
  }
  assert.equal(clients[0].match.tick, 8);
  const a = clients[0];
  await action(clients, a, () => a.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'natural roll');
  assert.equal(a.match.state.rolled, true);
  if (a.match.state.pending_action === 'robber_move') {
    const legal = a.match.state.legal;
    const tile = legal.robber_tiles.find(t => !legal.robber_victims[t]?.length);
    assert.notEqual(tile, undefined);
    await action(clients, a, () => clickTarget(a, 'tile', tile), 'natural robber after seven');
  }
  const before = JSON.stringify(a.match), commands = a.sent.length;
  await a.page.getByRole('button', { name: '2D', exact: true }).click();
  assert.equal(await a.page.locator('svg[height]').count(), 1); await open3d(a);
  assert.equal(JSON.stringify(a.match), before); assert.equal(a.sent.length, commands);
  await action(clients, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'natural end turn');
  await evidence(a, 'setup-roll-2d-3d');
  await a.page.mouse.move(2, 2); await sleep(1300);
  const frame = await a.page.evaluate(() => window.__scene.getState().gl.info.render.frame);
  await sleep(400); assert.equal(await a.page.evaluate(() => window.__scene.getState().gl.info.render.frame), frame, 'demand rendering idle');
}

async function boardMetrics(c) {
  return c.page.evaluate(() => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    const rect = gl.domElement.getBoundingClientRect(), land = [], visible = [], tiles = [], ports = [], pieces = [];
    const hud = ['.personal-hands', '.action-dock', '.context-prompt'].map(selector => document.querySelector(selector).getBoundingClientRect());
    const project = p => { p.project(camera); return { x: rect.x + (p.x + 1) * rect.width / 2,
      y: rect.y + (1 - p.y) * rect.height / 2 }; };
    const meshCorners = root => root.traverse(mesh => {
      if (!mesh.isMesh || !mesh.visible) return;
      mesh.geometry.computeBoundingBox(); const box = mesh.geometry.boundingBox;
      for (const x of [box.min.x, box.max.x]) for (const y of [box.min.y, box.max.y]) for (const z of [box.min.z, box.max.z]) {
        const p = mesh.position.clone().set(x, y, z); mesh.localToWorld(p); visible.push(project(p));
      }
    });
    scene.traverse(o => {
      const d = o.userData;
      if (d.terrain) {
        tiles.push([d.tileIndex, d.terrain]); meshCorners(o);
        if (d.terrain !== 'sea') for (let i = 0; i < 6; i++) {
          const p = o.position.clone().set(Math.sin(i * Math.PI / 3) * .97, .26, Math.cos(i * Math.PI / 3) * .97);
          o.localToWorld(p); land.push(project(p));
        }
      }
      if (d.kind && d.edge) { ports.push({ edge: d.edge, vertices: o.children.filter(c => c.userData.portVertex !== undefined).map(c => c.userData.portVertex) }); meshCorners(o); }
      if ((d.piece || d.level) && !d.preview) { pieces.push({ piece: d.piece, edge: d.edge, vertex: d.vertexId, level: d.level }); meshCorners(o); }
    });
    const span = points => ({ left: Math.min(...points.map(p => p.x)), right: Math.max(...points.map(p => p.x)),
      top: Math.min(...points.map(p => p.y)), bottom: Math.max(...points.map(p => p.y)),
      width: Math.max(...points.map(p => p.x)) - Math.min(...points.map(p => p.x)),
      height: Math.max(...points.map(p => p.y)) - Math.min(...points.map(p => p.y)) });
    return { viewport: [innerWidth, innerHeight], canvas: [rect.width, rect.height],
      canvasBounds: { left: rect.left, top: rect.top, right: rect.right, bottom: rect.bottom },
      land: span(land), visible: span(visible), tiles, ports, pieces,
      occludedByHud: visible.filter(p => hud.some(r => p.x > r.left && p.x < r.right && p.y > r.top && p.y < r.bottom)).length,
      calls: gl.info.render.calls, triangles: gl.info.render.triangles, frame: gl.info.render.frame };
  });
}

async function directActions(clients) {
  const a = clients[0]; await open3d(a);
  assert.equal(await a.page.getByRole('button', { name: 'Ship', exact: true }).count(), 0);
  for (const label of ['Build', 'Trade']) assert.equal(await a.page.getByRole('button', { name: label, exact: true }).count(), 0);
  for (const label of ['Road', 'Settlement', 'City', 'Dev Card']) assert.equal(await a.page.getByRole('button', { name: label, exact: true }).count(), 1);
  const city = a.page.getByRole('button', { name: 'City', exact: true });
  await city.hover(); const preview = city.locator('..').getByRole('tooltip');
  assert.equal(await preview.getByLabel('ore ×3: owned').count(), 1); await evidence(a, 'city-cost');
  await action(clients, a, () => city.click().then(() => clickTarget(a, 'vertex', a.match.state.legal.cities[0])), 'direct city');
  assert.equal(await a.page.locator('.cost-action').filter({ has: a.page.getByRole('button', { name: 'City', exact: true }) })
    .getByLabel('ore ×3: missing').count(), 1);
  await a.page.getByRole('button', { name: 'Road', exact: true }).click();
  const edge = a.match.state.legal.roads[0];
  await action(clients, a, () => clickTarget(a, 'edge', edge), 'direct paid road');
  assert.equal(a.match.state.occupied_e[edgeId(edge)], 0);
  for (let i = 0; !a.match.state.legal.settlements.length && i < 2; i++) {
    const next = a.match.state.legal.roads.find(e => e.includes(edge[1])) ?? a.match.state.legal.roads[0];
    assert(next); await action(clients, a, () => clickTarget(a, 'edge', next), 'extend paid route');
  }
  assert(a.match.state.legal.settlements.length, 'prepared route reaches a server-legal paid settlement');
  await a.page.getByRole('button', { name: 'Settlement', exact: true }).click();
  const vertex = a.match.state.legal.settlements[0];
  await action(clients, a, () => clickTarget(a, 'vertex', vertex), 'direct paid settlement');
  assert.deepEqual(a.match.state.occupied_v[vertex], [0, 1]);
  const before = JSON.stringify(a.match.state), commands = a.sent.length;
  await a.page.locator('.resource-hand button[data-resource="sheep"]').click();
  const tray = a.page.getByRole('dialog', { name: 'Trade tray', exact: true });
  assert.equal(await tray.getAttribute('aria-modal'), 'false');
  await a.page.locator('.resource-hand button[data-resource="sheep"]').click();
  assert.equal(await tray.getByRole('button', { name: 'Remove give sheep' }).getAttribute('data-count'), '2');
  await tray.getByRole('button', { name: 'Remove give sheep' }).click();
  await tray.getByRole('button', { name: 'Want ore', exact: true }).click();
  await tray.getByRole('button', { name: 'Want ore', exact: true }).click();
  assert.equal(await tray.getByRole('button', { name: 'Want ore', exact: true }).getAttribute('data-count'), '2');
  await tray.getByRole('button', { name: 'Remove wanted ore' }).click();
  assert.equal(JSON.stringify(a.match.state), before); assert.equal(a.sent.length, commands);
  await evidence(a, 'resource-trade-tray'); await a.page.keyboard.press('Escape'); assert.equal(await tray.count(), 0);
  a.measurements = [];
  for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }]) {
    await a.page.setViewportSize(size); await a.page.getByRole('button', { name: 'Reset Camera' }).click();
    await a.page.mouse.move(1, 1); await sleep(200);
    const metrics = await boardMetrics(a); a.measurements.push(metrics);
    assert.deepEqual(metrics.tiles.sort((x, y) => x[0] - y[0]), a.match.state.tiles.map((t, i) => [i, t.terrain]));
    for (const port of metrics.ports) assert.deepEqual(port.vertices, port.edge);
    assert(metrics.visible.top >= metrics.canvasBounds.top && metrics.visible.bottom <= metrics.canvasBounds.bottom, 'board/ports/pieces clipped vertically');
    assert(metrics.visible.left >= metrics.canvasBounds.left && metrics.visible.right <= metrics.canvasBounds.right, 'board/ports/pieces clipped horizontally');
    assert.equal(metrics.occludedByHud, 0, 'permanent HUD obscures geometry');
    await evidence(a, 'base-' + size.width);
  }
  await layout(a);
  // Camera interaction and overlays must remain presentation-only.
  const current = JSON.stringify(a.match.state), sent = a.sent.length;
  const canvas = await a.page.locator('canvas').boundingBox();
  await a.page.mouse.move(canvas.x + canvas.width / 2, canvas.y + canvas.height / 2);
  await a.page.mouse.wheel(0, -80); await a.page.mouse.down();
  await a.page.mouse.move(canvas.x + canvas.width / 2 + 30, canvas.y + canvas.height / 2, { steps: 5 }); await a.page.mouse.up();
  await a.page.getByRole('button', { name: 'Reset Camera' }).click();
  assert.equal(JSON.stringify(a.match.state), current); assert.equal(a.sent.length, sent);
  await a.page.getByRole('button', { name: 'Event log', exact: true }).click();
  const log = a.page.getByRole('dialog', { name: 'Event log', exact: true });
  await log.getByText('Bank availability', { exact: true }).click();
  for (const resource of ['wood', 'brick', 'sheep', 'wheat', 'ore'])
    assert.equal(await log.getByLabel(`${resource}: ${a.match.state.bank_available[resource] ? 'available' : 'unavailable'}`).count(), 1);
  await evidence(a, 'log-bank-drawer'); await log.getByRole('button', { name: 'Close Event log' }).click();
}

async function diceUX(clients) {
  const [a, b] = clients; for (const c of clients) await open3d(c);
  const roll = async (c, reduced = false) => {
    await action(clients, c, () => c.page.getByRole('button', { name: 'Roll', exact: true }).click(), 'exact dice');
    clients.forEach(x => { assert.deepEqual(x.match.state.dice, [4, 5]); assert.equal(x.match.state.last_roll, 9); });
    for (const x of clients) {
      assert.equal(await x.page.getByRole('img', { name: 'Die 1: 4', exact: true }).count(), 1);
      assert.equal(await x.page.getByRole('img', { name: 'Die 2: 5', exact: true }).count(), 1);
    }
    const visual = await c.page.evaluate(() => {
      let roll; const faces = [];
      window.__scene.getState().scene.traverse(o => { if (o.userData.diceRoll) roll = o.userData.diceRoll;
        if (o.userData.serverFace) faces.push(o.userData.serverFace); });
      return { roll: roll ?? null, faces, hudBusy: document.querySelector('.dice-hud').getAttribute('aria-busy') };
    });
    if (reduced) { assert.equal(visual.roll, null); assert.equal(visual.hudBusy, 'false'); }
    else { assert.deepEqual(visual.faces, [4, 5]); assert(visual.roll.endsWith(':' + c.match.state.roll_count));
      await evidence(c, 'dice-rolling'); }
    await sleep(1300); await c.page.mouse.move(1, 1); await sleep(50);
    const frame = await c.page.evaluate(() => window.__scene.getState().gl.info.render.frame);
    await sleep(250); assert.equal(await c.page.evaluate(() => window.__scene.getState().gl.info.render.frame), frame);
    assert.equal(await c.page.locator('.dice-hud[aria-busy="true"]').count(), 0);
    const commands = c.sent.length; assert.equal(c.sent.at(-1).cmd.type, 'roll');
    await c.page.getByRole('button', { name: '2D', exact: true }).click(); await open3d(c);
    assert.equal(c.sent.length, commands);
    assert.equal(await c.page.locator('.dice-hud[aria-busy="true"]').count(), 0, 'renderer switch does not restart completed roll');
  };
  await roll(a); const first = a.match.state.roll_count;
  await action(clients, a, () => a.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'dice persists after end');
  assert.deepEqual(a.match.state.dice, [4, 5]); assert.equal(a.match.state.roll_count, first);
  await roll(b); assert.equal(b.match.state.roll_count, first + 1, 'same pair is a new roll');
  await action(clients, b, () => b.page.getByRole('button', { name: 'End Turn', exact: true }).click(), 'next dice turn');
  for (const c of clients) await c.page.emulateMedia({ reducedMotion: 'reduce' });
  await sleep(80); await roll(a, true); await evidence(a, 'dice-reduced-motion');
  const roomCode = a.room.room_code, counter = a.match.state.roll_count;
  a.match = null; await a.page.reload({ waitUntil: 'networkidle' });
  await a.page.getByLabel('Name', { exact: true }).fill(a.name);
  await a.page.getByLabel('Room code').fill(roomCode); await a.page.getByRole('button', { name: 'Join', exact: true }).click();
  await wait(() => a.match?.state.roll_count === counter, 'refresh keeps exact latest faces');
  assert.deepEqual(a.match.state.dice, [4, 5]); assert.equal(await a.page.locator('.dice-hud[aria-busy="true"]').count(), 0);
}

async function goldUX(clients) {
  const a = clients[0]; await open3d(a);
  clients.forEach(c => assert.equal(c.match.state.map_id, 'seafarers_gold_haven'));
  const ship = a.page.getByRole('button', { name: 'Ship', exact: true });
  assert.equal(await ship.count(), 1); assert(await ship.isEnabled()); await ship.hover();
  const cost = ship.locator('..').getByRole('tooltip');
  assert.equal(await cost.getByLabel('wood ×1: owned').count(), 1); assert.equal(await cost.getByLabel('sheep ×1: owned').count(), 1);
  const edge = a.match.state.legal.ships[0]; await ship.click();
  await action(clients, a, () => clickTarget(a, 'edge', edge), 'Gold Haven build ship');
  assert.equal(a.match.state.occupied_ships[edgeId(edge)], 0);
  await a.page.getByRole('button', { name: 'Move Ship', exact: true }).click();
  const source = a.match.state.legal.move_ship.sources[0], destination = a.match.state.legal.move_ship.targets[edgeId(source)][0];
  const commands = a.sent.length; await clickTarget(a, 'edge', source); assert.equal(a.sent.length, commands);
  await action(clients, a, () => clickTarget(a, 'edge', destination), 'Gold Haven move ship');
  assert.equal(a.match.state.occupied_ships[edgeId(source)], undefined); assert.equal(a.match.state.occupied_ships[edgeId(destination)], 0);
  const dev = await openDev(a, 'Knight'); await action(clients, a, () => dev.getByRole('button', { name: 'Play Knight' }).click(), 'Gold Haven Knight');
  await a.page.getByRole('button', { name: 'Pirate', exact: true }).click();
  const legal = a.match.state.legal, tile = legal.pirate_tiles.find(i => !legal.pirate_victims[i]?.length);
  assert.notEqual(tile, undefined); await action(clients, a, () => clickTarget(a, 'tile', tile), 'Gold Haven pirate');
  assert.equal(a.match.state.pirate_tile, tile); assert.equal(a.match.state.pending_action, null);
  a.measurements = [];
  for (const size of [{ width: 1920, height: 1080 }, { width: 1440, height: 900 }, { width: 1280, height: 720 }]) {
    await a.page.setViewportSize(size); await a.page.getByRole('button', { name: 'Reset Camera' }).click();
    await a.page.mouse.move(1, 1); await sleep(200);
    const metrics = await boardMetrics(a); a.measurements.push(metrics);
    assert(metrics.tiles.some(t => t[1] === 'sea') && metrics.tiles.some(t => t[1] === 'gold'));
    assert(metrics.pieces.some(p => p.piece === 'ship') && metrics.pieces.some(p => p.piece === 'pirate'));
    for (const port of metrics.ports) assert.deepEqual(port.vertices, port.edge);
    assert(metrics.visible.top >= metrics.canvasBounds.top && metrics.visible.bottom <= metrics.canvasBounds.bottom, 'Gold Haven clipped');
    assert.equal(metrics.occludedByHud, 0, 'Gold Haven HUD obscures geometry');
    await evidence(a, 'gold-haven-' + size.width);
  }
  await layout(a);
}
async function main() {
  await fs.mkdir(output, { recursive: true });
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = { date: new Date().toISOString(), origin, chrome: browser.version(), results: [] };
  const cases = [
    ['bank4', 2, c => bank(c, 4)], ['bank3', 2, c => bank(c, 3)], ['bank2', 2, c => bank(c, 2)],
    ['trade', 3, offer], ['buy', 2, buy], ['knight', 3, knight], ['road', 2, road],
    ['plenty', 2, plenty], ['monopoly', 3, monopoly], ['passive', 2, passive],
    ['results', 2, rematch], ['results', 3, c => rematch(c, true)], ['results', 2, exit],
    ['setup', 2, setup, true],
    ['direct', 2, directActions], ['dice', 2, diceUX], ['gold', 2, goldUX, false, 'seafarers_gold_haven'],
  ];
  try {
    for (const [mode, count, run, natural, mapId] of cases) {
      if (process.env.CATAN_E2E_CASE && mode !== process.env.CATAN_E2E_CASE) continue;
      let clients = [];
      const label = mode + '-' + count + '-' + run.name;
      try {
        clients = await room(browser, mode, count, natural, mapId); await run(clients);
        for (const c of clients) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
        const result = { label, passed: true, room: clients[0].room.room_code,
          commands: clients.flatMap(c => c.sent.map(m => m.cmd)), rejected: clients.flatMap(c => c.errors),
          measurements: clients[0].measurements };
        report.results.push(result); console.log(JSON.stringify({ label, passed: true, commands: result.commands.length, rejected: result.rejected.length }));
      } catch (error) {
        const live = clients.find(c => !c.page.isClosed());
        if (live) await evidence(live, 'failure-' + label);
        report.results.push({ label, passed: false, error: String(error), states: clients.map(c => c.match), errors: clients.map(c => c.errors) });
        throw error;
      } finally { for (const c of clients) await c.context.close(); }
    }
  } finally { await fs.writeFile(path.join(output, 'results.json'), JSON.stringify(report, null, 2)); await browser.close(); }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { room, setup };
