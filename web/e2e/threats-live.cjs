// Three real owning profiles, production commands/COMMIT/receipts and raw privacy.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18778';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-threats-live-' + Date.now());
const h = require('./game-actions.cjs'), live = require('./fog-live.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const root = path.resolve(__dirname, '../..');
const manifestPath = path.join(output, 'threat-fixture-bindings.json'), auditPath = path.join(output, 'draw-audit.jsonl');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { completed: false, checks: [], cases: [],
  scope: 'seven prepared three-player fixtures; production authority/PG; exact internal Fog binding only',
  limits: ['not natural full matches', 'no live internal Fog rematch', 'synthetic controlled server RNG only in guarded subprocess'] };
function check(label) { report.checks.push(label); console.log('PASS ' + label); }

async function start() {
  const url = new URL(origin);
  assert.equal(url.hostname, '127.0.0.1'); assert(process.env.DATABASE_URL, 'Isolated PostgreSQL DATABASE_URL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const child = spawn(python, ['-B', '-X', 'utf8', '-m', 'tests.threat_visual_support',
    '--port', url.port, '--manifest', manifestPath, '--audit', auditPath], {
    cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, CATAN_ENABLE_TEST_TOOLS: '0', CATAN_FOG_BETA_ADMISSION: '0', CATAN_FOG_BETA_EMERGENCY_STOP: '0' },
  });
  // No manifest, credentials, private hands or database diagnostics are printed.
  child.stdout.resume(); child.stderr.resume();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Guarded threat fixture backend failed to start');
    try { const response = await fetch(origin + '/health'); if (response.ok && (await response.json()).ready) return child; } catch {}
    await pause(80);
  }
  child.kill(); throw Error('Threat fixture backend readiness timeout');
}
async function draws() {
  let lines;
  try { lines = (await fs.readFile(auditPath, 'utf8')).trim().split('\n').filter(Boolean); }
  catch (error) { if (error.code === 'ENOENT') return { roll_draw: 0, theft_draw: 0, recovery_without_gameplay: 0 }; throw error; }
  return lines.map(line => JSON.parse(line).kind).reduce((result, kind) => {
    assert(Object.hasOwn(result, kind)); result[kind]++; return result;
  }, { roll_draw: 0, theft_draw: 0, recovery_without_gameplay: 0 });
}

function observeThreats(milliseconds = 3000) {
  const generation = window.__threatMonitor = (window.__threatMonitor || 0) + 1;
  window.__threatObserved = { figures: [], theft: false, neutral: null, unsafeKeys: [] };
  const end = performance.now() + milliseconds;
  function sample() {
    if (window.__threatMonitor !== generation) return;
    const result = window.__threatObserved;
    window.__scene?.getState().scene.traverse(o => {
      if (o.userData.threatVisual && (o.userData.moving || o.userData.arriving)) {
        const kind = typeof o.userData.threatVisual === 'string' ? o.userData.threatVisual : o.userData.kind;
        if (!result.figures.includes(kind)) result.figures.push(kind);
      }
      if (o.userData.theftVisual && o.visible) {
        result.theft = true;
        result.unsafeKeys = [...new Set([...result.unsafeKeys, ...Object.keys(o.userData)
          .filter(key => /resource|assignment|recipe|hand|dev_cards|private|victory|^vp$|^res$/i.test(key))])];
        if (!result.neutral) {
          const meshes = [];
          o.traverse(m => {
            if (!m.isMesh) return;
            const materials = Array.isArray(m.material) ? m.material : [m.material];
            meshes.push({ geometry: m.geometry.type, vertices: m.geometry.attributes.position?.count,
              materials: materials.map(material => ({ type: material.type, color: material.color?.getHexString() })) });
          });
          result.neutral = meshes;
        }
      }
    });
    if (performance.now() < end) requestAnimationFrame(sample);
  }
  requestAnimationFrame(sample);
}
async function monitor(c, duration = 3000) { await c.page.evaluate(observeThreats, duration); }
async function active(c) {
  return c.page.evaluate(() => {
    let count = 0;
    window.__scene?.getState().scene.traverse(o => {
      if (o.userData.threatVisual && (o.userData.moving || o.userData.arriving)
        || o.userData.departureVisual && o.visible || o.userData.theftVisual && o.visible) count++;
    }); return count;
  });
}
async function noReplay(cs, label) {
  await pause(180);
  for (const c of cs) {
    assert.equal(await active(c), 0, label);
    const seen = await c.page.evaluate(() => window.__threatObserved);
    assert.deepEqual(seen.figures, [], label); assert.equal(seen.theft, false, label);
  }
}

async function clickMoveTile(c, tile) {
  const point = await c.page.evaluate(tile => {
    const { scene, camera, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    let target;
    scene.traverse(o => { if (o.userData.terrain && o.userData.tileIndex === tile && o.userData.legal) target = o; });
    if (!target) throw Error('Missing authoritative legal move tile');
    const center = target.children[0].getWorldPosition(target.position.clone()); center.y += .3;
    const rect = gl.domElement.getBoundingClientRect(); let coveredBy;
    // A server rejection notice may cover the projected center. Use an exposed
    // interior point in the same public hex, with ordinary browser mouse input.
    for (const [dx, dz] of [[0, 0], [-.3, 0], [.3, 0], [0, -.3], [0, .3],
      [-.7, 0], [.7, 0], [0, -.7], [0, .7], [-.6, -.4], [.6, -.4], [-.6, .4], [.6, .4]]) {
      const position = center.clone(); position.x += dx; position.z += dz; position.project(camera);
      const x = rect.x + (position.x + 1) * rect.width / 2, y = rect.y + (1 - position.y) * rect.height / 2;
      const top = document.elementFromPoint(x, y);
      if (top === gl.domElement) return { x, y, coveredBy };
      coveredBy ??= top?.className;
    }
    throw Error('No exposed interior point in the same legal hex');
  }, tile);
  if (point.coveredBy) {
    report.pointerAvoidance ||= [];
    report.pointerAvoidance.push({ tile, coveredBy: point.coveredBy });
  }
  await c.page.mouse.move(point.x, point.y); await c.page.mouse.click(point.x, point.y);
}

async function open(browser, entry, pid) {
  const c = await h.newClient(browser, ['Alice', 'Bob', 'Carol'][pid]);
  c.rawStates = []; c.expectedOutage = false; c.expectedWarnings = [];
  c.page.on('console', message => {
    if (c.expectedOutage && message.type() === 'error' && /WebSocket connection.*ERR_CONNECTION_REFUSED/.test(message.text())) {
      assert.equal(c.console.at(-1), message.text()); c.expectedWarnings.push(c.console.pop());
    }
  });
  c.page.on('websocket', socket => socket.on('framereceived', ({ payload }) => {
    const message = JSON.parse(String(payload)); if (message.type === 'match_state') c.rawStates.push(message);
  }));
  await c.context.addInitScript(observeThreats, 10000);
  await c.page.evaluate(({ code, proof, name, server }) => {
    localStorage.setItem('catan_recent_games', JSON.stringify({ version: 1, entries: [{ room_code: code,
      reconnect_token: proof, last_known_name: name, last_seen_at: Date.now(), server_url: server }] }));
    sessionStorage.setItem('catan_current_game', JSON.stringify({ room_code: code, last_known_name: name, server_url: server }));
  }, { code: entry.room_code, proof: entry.proofs[pid], name: c.name, server: origin.replace(/^http/, 'ws') + '/ws' });
  await c.page.reload({ waitUntil: 'networkidle' }); await h.wait(() => c.match, 'native three-seat reconnect');
  await c.page.locator('.game-shell').waitFor(); await h.open3d(c);
  assert.equal(c.match.state.you_pid, pid); assert.equal(c.room.ruleset_compatibility.status, 'compatible');
  return c;
}

function remember(cs, allowed) {
  for (const c of cs) {
    const self = h.own(c), pid = c.match.state.you_pid;
    allowed[pid].push({ res: structuredClone(self.res), dev_cards: structuredClone(self.dev_cards) });
  }
}
function privacy(cs, publicVp, fullVp, allowed) {
  h.privacy(cs);
  for (const c of cs) for (const message of c.rawStates) {
    const s = message.state, pid = s.you_pid;
    for (const key of ['seed', 'dev_deck', 'bank', 'ships_built_this_turn', 'ship_moved_this_turn']) assert(!Object.hasOwn(s, key));
    for (const tile of s.tiles) if (tile.visibility === 'hidden') { assert.equal(tile.terrain, 'fog'); assert.equal(tile.number, null); }
    assert(!/assignment_digest|initially_hidden|fog_pool|continuation|reward_ledger/.test(JSON.stringify(s)));
    for (const player of s.players) {
      assert.equal(player.vp, player.pid === pid ? fullVp[player.pid] : publicVp[player.pid], 'hidden VP is private in every raw frame');
      if (player.pid !== pid) assert(!Object.hasOwn(player, 'res') && !Object.hasOwn(player, 'dev_cards'));
      else {
        assert(allowed[pid].some(value => JSON.stringify(value.res) === JSON.stringify(player.res)), 'own exact raw hand is an expected committed hand');
        assert(allowed[pid].some(value => JSON.stringify(value.dev_cards) === JSON.stringify(player.dev_cards)), 'own exact raw development cards are expected');
      }
    }
    for (const event of s.game_events) if (event.type === 'theft') {
      assert.equal(event.actor_pid, 0); assert.equal(event.victim_pid, 1); assert.equal(event.quantity, 1);
      if (pid === 0 || pid === 1) assert.equal(event.resource, 'ore');
      else assert(!Object.hasOwn(event, 'resource'), 'eligible observer2 cannot read the selected victim1 resource');
    }
  }
}

async function runCase(browser, entry, processRef) {
  const cs = [], label = entry.figure + '-' + entry.trigger + '-' + entry.mode;
  try {
    for (const pid of [0, 1, 2]) cs.push(await open(browser, entry, pid));
    const actor = cs[0], allowed = [[], [], []]; remember(cs, allowed);
    const before = cs.map(c => structuredClone(h.own(c))), fullVp = before.map(() => entry.fog ? 2 : 3);
    const publicVp = before.map(() => entry.fog ? 1 : 2);
    const knownHands = [{ wood: 0, brick: 0, sheep: 0, wheat: 0, ore: 0 },
      { wood: 3, brick: 0, sheep: 0, wheat: 0, ore: 1 }, { wood: 0, brick: 2, sheep: 0, wheat: 0, ore: 0 }];
    for (let pid = 0; pid < 3; pid++) {
      assert.deepEqual(before[pid].res, knownHands[pid], 'initial private hand equals the known conserved fixture');
      assert.deepEqual(before[pid].dev_cards, [{ type: 'victory_point', new: false }, { type: 'knight', new: false }]);
      assert.equal(before[pid].vp, fullVp[pid]);
    }
    const expectedCards = before.map((player, pid) => player.dev_cards.filter(card =>
      !(pid === 0 && entry.trigger === 'knight' && card.type === 'knight')));
    const expectedHands = before.map(p => structuredClone(p.res));
    for (const c of cs) { assert.equal(await active(c), 0); await monitor(c); }
    const beforeDraw = await draws();
    await h.action(cs, actor, () => entry.trigger === 'seven'
      ? actor.page.getByRole('button', { name: 'Roll', exact: true }).click()
      : actor.page.locator('.dev-mini-card').filter({ hasText: 'Knight' }).click(), label + ' actual trigger');
    for (let pid = 0; pid < 3; pid++) {
      assert.deepEqual(h.own(cs[pid]).res, knownHands[pid], 'Seven/Knight cannot alter exact conserved hands');
      assert.deepEqual(h.own(cs[pid]).dev_cards, expectedCards[pid], 'only the actor plays its mature Knight');
    }
    remember(cs, allowed); privacy(cs, publicVp, fullVp, allowed);
    assert.equal(actor.match.state.pending_action, 'robber_move');
    if (entry.trigger === 'seven') assert.equal(actor.match.state.last_roll, 7);
    else assert.equal(h.own(actor).dev_cards.filter(card => card.type === 'knight').length, 0);
    const afterTrigger = await draws();
    assert.equal(afterTrigger.roll_draw, beforeDraw.roll_draw + (entry.trigger === 'seven' ? 1 : 0));
    assert.equal(afterTrigger.theft_draw, beforeDraw.theft_draw);
    await noReplay(cs, 'pending choice has no movement/theft');
    check(label + ': actual Seven/mature Knight creates pending choice without moving a figure or drawing theft');

    const targets = actor.match.state.legal[entry.figure + '_victims'][entry.route.tile];
    assert.deepEqual(targets, entry.mode === 'none' ? [] : [1, 2]);
    const executeMove = async () => {
      const dialog = actor.page.getByRole('dialog', { name: 'Choose player', exact: true });
      if (!await dialog.isVisible()) {
        const tool = actor.page.getByRole('button', { name: entry.figure === 'robber' ? 'Robber' : 'Pirate', exact: true });
        if (await tool.getAttribute('aria-pressed') !== 'true') await tool.click();
        const sent = actor.sent.length;
        await clickMoveTile(actor, entry.route.tile);
        if (targets.length > 1) {
          await dialog.waitFor(); assert.equal(actor.sent.length, sent, 'mandatory victim selection emits no premature move');
        }
      }
      if (targets.length > 1) await dialog.getByRole('button', { name: actor.match.state.players.find(p => p.pid === 1).name, exact: true }).click();
    };
    const rejected = cs.map(c => structuredClone(c.match.state));
    for (const c of cs) await monitor(c);
    await h.invalidNext(actor, { type: entry.route.type, tile: 99999, victim: 1 });
    await h.action(cs, actor, executeMove, label + ' invalid move', true);
    for (let i = 0; i < cs.length; i++) assert.deepEqual(cs[i].match.state, rejected[i], 'invalid intent preserves all THREE complete personal states');
    assert.deepEqual(await draws(), afterTrigger); await noReplay(cs, 'rejected move');
    check(label + ': mandatory victim/no-victim path and invalid move preserve all three snapshots, RNG and visuals');

    for (const c of cs) await monitor(c);
    await h.action(cs, actor, executeMove, label + ' accepted move');
    const accepted = actor.sent.at(-1); assert.deepEqual(accepted.cmd, entry.route);
    if (entry.mode !== 'none') { expectedHands[0].ore++; expectedHands[1].ore--; }
    for (let i = 0; i < cs.length; i++) {
      assert.deepEqual(h.own(cs[i]).res, expectedHands[i], 'exact private resource delta');
      assert.deepEqual(h.own(cs[i]).dev_cards, expectedCards[i], 'theft never changes private development cards');
    }
    remember(cs, allowed); privacy(cs, publicVp, fullVp, allowed);
    await pause(1500);
    const observations = [];
    for (const c of cs) {
      assert.equal(c.match.state[entry.figure + '_tile'], entry.route.tile);
      const seen = await c.page.evaluate(() => window.__threatObserved); observations.push(seen);
      if (entry.mode === 'offboard') assert.deepEqual(seen.figures, [], 'native offboard origin snaps without invented movement');
      else assert(seen.figures.includes(entry.figure), 'all three real clients observe committed figure feedback');
      assert.deepEqual(seen.unsafeKeys, []); assert.equal(seen.theft, entry.mode !== 'none');
      assert.equal(await active(c), 0, 'finite threat/theft cues settle');
    }
    if (entry.mode !== 'none') {
      assert(observations[0].neutral.length > 0);
      for (const seen of observations) assert.deepEqual(seen.neutral, observations[0].neutral, 'same neutral geometry/material colors for all viewers');
      const events = cs.map(c => c.match.state.game_events.findLast(event => event.type === 'theft'));
      assert(events.every(Boolean));
      for (const event of events) { const copy = { ...event }; delete copy.resource;
        const expected = { ...events[0] }; delete expected.resource; assert.deepEqual(copy, expected); }
    } else for (const c of cs) assert(!c.match.state.game_events.some(event => event.type === 'theft'));
    const afterMove = await draws(); assert.equal(afterMove.theft_draw, afterTrigger.theft_draw + (entry.mode === 'none' ? 0 : 1));
    check(label + ': accepted ' + (entry.mode === 'offboard' ? 'offboard snap/theft' : 'movement/theft')
      + ' is visible to all; ' + (entry.mode === 'none' ? 'no theft card/draw' : 'identical neutral card')
      + '; exact raw resource/hands/dev/hidden VP stay private');

    const duplicateStates = cs.map(c => structuredClone(c.match.state));
    for (const c of cs) await monitor(c);
    const ackCount = actor.acks.length; await live.raw(actor, accepted);
    await h.wait(() => actor.acks.length > ackCount, 'duplicate theft receipt');
    assert.equal(actor.acks.at(-1).duplicate, true); assert.equal(actor.acks.at(-1).applied, false);
    for (let i = 0; i < cs.length; i++) assert.deepEqual(cs[i].match.state, duplicateStates[i]);
    assert.deepEqual(await draws(), afterMove); await noReplay(cs, 'duplicate receipt');
    check(label + ': duplicate durable receipt preserves exact state and never redraws/replays');

    await live.refresh(cs); await noReplay(cs, 'refresh baseline');
    const pending = cs.map(c => structuredClone(c.match.state));
    for (const c of cs) { await monitor(c, 15000); c.expectedOutage = true; }
    await live.stop(processRef.current); for (const c of cs) c.match = null;
    processRef.current = await start(); await h.wait(() => cs.every(c => c.match), 'three-seat PostgreSQL recovery/reconnect');
    for (let i = 0; i < cs.length; i++) { cs[i].expectedOutage = false; assert.deepEqual(cs[i].match.state, pending[i]); }
    const afterRestart = await draws();
    assert.equal(afterRestart.roll_draw, afterMove.roll_draw); assert.equal(afterRestart.theft_draw, afterMove.theft_draw);
    assert.equal(afterRestart.recovery_without_gameplay, afterMove.recovery_without_gameplay + 1);
    const restoredAckCount = actor.acks.length; await live.raw(actor, accepted);
    await h.wait(() => actor.acks.length > restoredAckCount, 'restored duplicate receipt');
    assert.equal(actor.acks.at(-1).duplicate, true); assert.equal(actor.acks.at(-1).applied, false);
    for (let i = 0; i < cs.length; i++) assert.deepEqual(cs[i].match.state, pending[i]);
    assert.deepEqual(await draws(), afterRestart); await noReplay(cs, 'native recovery');
    privacy(cs, publicVp, fullVp, allowed);
    check(label + ': refresh/reconnect/PG restart and restored receipt preserve exact states without gameplay/draw/replay');
    for (const c of cs) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
    await actor.page.screenshot({ path: path.join(output, label + '.png') });
    report.cases.push({ figure: entry.figure, trigger: entry.trigger, mode: entry.mode, passed: true,
      rawFramesChecked: cs.map(c => c.rawStates.length), expectedRestartRefusals: cs.flatMap(c => c.expectedWarnings).length, unexpectedErrors: [] });
  } catch (error) {
    if (cs[0]) await cs[0].page.screenshot({ path: path.join(output, label + '-failure.png') });
    throw error;
  } finally { for (const c of cs) await c.context.close(); }
}

(async () => {
  await fs.mkdir(output, { recursive: true }); let browser;
  const processRef = { current: await start() };
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
    for (const file of ['threat-fixture-bindings.json', 'draw-audit.jsonl']) {
      const response = await fetch(origin + '/' + file), text = await response.text();
      assert(!text.includes('"proofs"') && !text.includes('"kind": "theft_draw"'));
      assert((response.headers.get('content-type') || '').includes('text/html'));
    }
    check('private manifest/RNG audit are not served; no fixture/RNG endpoint exists');
    const entries = JSON.parse(await fs.readFile(manifestPath, 'utf8')); assert.equal(entries.length, 7);
    for (const entry of entries) await runCase(browser, entry, processRef);
    report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close(); await live.stop(processRef.current);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
