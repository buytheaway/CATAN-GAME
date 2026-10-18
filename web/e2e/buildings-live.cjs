// Real owning clients/executor/COMMIT/receipts/F1/PG; prepared test-only Fog rooms.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18775';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-buildings-live-' + Date.now());
const h = require('./game-actions.cjs'), live = require('./fog-live.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const manifestPath = path.join(output, 'building-fixture-bindings.json');
const root = path.resolve(__dirname, '../..');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { completed: false, scope: 'prepared/funded internal Fog fixtures; normal authority and PG; public admission disabled',
  checks: [], cases: [], limits: ['not a natural full match', 'closed internal Fog rematch is not admitted'] };
function check(label) { report.checks.push(label); console.log('PASS ' + label); }

async function start() {
  const uri = new URL(origin);
  assert.equal(uri.hostname, '127.0.0.1');
  assert(process.env.DATABASE_URL, 'Isolated PostgreSQL DATABASE_URL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root,
    process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const child = spawn(python, ['-B', '-X', 'utf8', '-m', 'tests.building_visual_support',
    '--port', uri.port, '--manifest', manifestPath], {
    cwd: root, windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
    env: { ...process.env, CATAN_ENABLE_TEST_TOOLS: '0', CATAN_FOG_BETA_ADMISSION: '0', CATAN_FOG_BETA_EMERGENCY_STOP: '0' },
  });
  // The manifest and backend diagnostics can contain private fixture bindings.
  child.stdout.resume(); child.stderr.resume();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Guarded building fixture backend failed to start');
    try { const response = await fetch(origin + '/health'); if (response.ok && (await response.json()).ready) return child; } catch {}
    await pause(80);
  }
  child.kill(); throw Error('Building fixture backend readiness timeout');
}

function observeBuildingEffects(milliseconds = 2500) {
    const generation = window.__buildingMonitor = (window.__buildingMonitor || 0) + 1;
    window.__buildingObserved = { kinds: [], fog: false, echo: false, ship: false };
    const end = performance.now() + milliseconds;
    const sample = () => {
      if (window.__buildingMonitor !== generation) return;
      const result = window.__buildingObserved;
      window.__scene?.getState().scene.traverse(o => {
        if (o.userData.pieceVisual && o.userData.appearing && o.userData.construction
          && !result.kinds.includes(o.userData.construction)) result.kinds.push(o.userData.construction);
        if (o.userData.upgradeEcho && o.visible) result.echo = true;
        if (o.userData.fogReveal && o.visible) result.fog = true;
        if (o.userData.piece === 'ship' && !o.userData.preview) result.ship = true;
      });
      if (performance.now() < end) requestAnimationFrame(sample);
    }; requestAnimationFrame(sample);
}
async function monitor(c, milliseconds = 2500) {
  await c.page.evaluate(observeBuildingEffects, milliseconds);
}
async function active(c) {
  return c.page.evaluate(() => {
    let count = 0;
    window.__scene?.getState().scene.traverse(o => {
      if (o.userData.pieceVisual && o.userData.appearing || o.userData.upgradeEcho && o.visible) count++;
    }); return count;
  });
}
function assertOccupancy(c, command, accepted) {
  const state = c.match.state;
  if (command.type === 'place_road') {
    const key = [...command.eid].sort((a, b) => a - b).join(',');
    if (accepted) assert.equal(state.occupied_e[key], 0);
    else assert(!Object.hasOwn(state.occupied_e, key));
  } else if (command.type === 'place_settlement') {
    if (accepted) assert.deepEqual(state.occupied_v[command.vid], [0, 1]);
    else assert(!Object.hasOwn(state.occupied_v, command.vid));
  } else assert.deepEqual(state.occupied_v[command.vid], [0, accepted ? 2 : 1]);
}
async function noReplay(cs, label) {
  await pause(180);
  for (const c of cs) {
    assert.equal(await active(c), 0, label);
    const seen = await c.page.evaluate(() => window.__buildingObserved);
    assert.deepEqual(seen.kinds, [], label); assert.equal(seen.echo, false, label);
  }
}
async function resolveGold(cs, actor) {
  while (actor.match.state.pending_action === 'choose_gold') {
    const quantity = actor.match.state.pending_gold[actor.match.state.you_pid];
    await actor.page.getByLabel('Gold resource').selectOption('ore');
    await actor.page.getByLabel('Gold quantity').fill(String(quantity));
    await h.action(cs, actor, () => actor.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'Gold after road construction');
  }
}

async function runCase(browser, entry, processRef) {
  const cs = [], command = entry.route;
  const kind = { place_road: 'road', place_settlement: 'settlement', upgrade_city: 'upgrade' }[command.type];
  const button = { place_road: 'Road', place_settlement: 'Settlement', upgrade_city: 'City' }[command.type];
  const targetType = command.type === 'place_road' ? 'edge' : 'vertex';
  const target = command.type === 'place_road' ? command.eid : command.vid;
  try {
    for (const pid of [0, 1]) {
      const c = await live.open(browser, entry, pid); cs.push(c); await h.open3d(c);
      await c.context.addInitScript(observeBuildingEffects, 10000);
      await c.page.waitForFunction(() => {
        let present = false; window.__scene?.getState().scene.traverse(o => { present ||= !!o.userData.pieceVisual; }); return present;
      });
    }
    const actor = cs[0]; live.privacy(cs);
    for (const c of cs) { assert.equal(await active(c), 0); assertOccupancy(c, command, false); }
    await actor.page.getByRole('button', { name: button, exact: true }).click();
    const beforeRejected = cs.map(c => structuredClone(c.match.state));
    for (const c of cs) await monitor(c);
    const invalid = command.type === 'place_road' ? { type: command.type, eid: [-1, -2] } : { type: command.type, vid: -1 };
    await h.invalidNext(actor, invalid);
    await h.action(cs, actor, () => h.clickTarget(actor, targetType, target), 'invalid ' + command.type, true);
    for (let i = 0; i < cs.length; i++) {
      assert.deepEqual(cs[i].match.state, beforeRejected[i], 'rejection preserves BOTH personal snapshots');
      assertOccupancy(cs[i], command, false);
      const occupied = command.type === 'place_road' ? cs[i].match.state.occupied_e : cs[i].match.state.occupied_v;
      assert(!Object.hasOwn(occupied, command.type === 'place_road' ? '-2,-1' : '-1'));
    }
    await noReplay(cs, 'rejected construction');
    check(command.type + ': rejected intent preserves both complete personal states/targets and starts no construction');

    for (const c of cs) await monitor(c);
    await h.action(cs, actor, () => h.clickTarget(actor, targetType, target), command.type);
    const accepted = actor.sent.at(-1);
    assert.equal(actor.acks.find(ack => ack.cmd_id === accepted.cmd_id).applied, true);
    await pause(1200); live.privacy(cs);
    for (const c of cs) {
      assertOccupancy(c, command, true);
      const seen = await c.page.evaluate(() => window.__buildingObserved);
      assert(seen.kinds.includes(kind), 'both clients observe accepted ' + kind);
      assert(seen.ship, 'baseline real ship remains in combined scene');
      if (command.type === 'place_road') assert(seen.fog, 'real road construction coexists with Fog reveal');
      assert.equal(await active(c), 0, 'finite building effects settle');
    }
    check(command.type + ': applied ACK/committed state yields both-client finite ' + kind + ' with baseline ships' + (command.type === 'place_road' ? ' and real Fog/Gold' : ''));

    for (const c of cs) await monitor(c);
    const states = cs.map(c => structuredClone(c.match.state)), ackCount = actor.acks.length;
    await live.raw(actor, accepted);
    await h.wait(() => actor.acks.length > ackCount, 'duplicate building receipt');
    assert.equal(actor.acks.at(-1).duplicate, true);
    for (let i = 0; i < cs.length; i++) assert.deepEqual(cs[i].match.state, states[i]);
    await noReplay(cs, 'duplicate receipt');
    check(command.type + ': durable duplicate receipt preserves both states and never repeats construction');

    await live.refresh(cs);
    for (const c of cs) {
      await c.page.waitForFunction(() => !!window.__scene?.getState().scene);
    }
    await noReplay(cs, 'refresh baseline');
    const pending = cs.map(c => structuredClone(c.match.state));
    for (const c of cs) await monitor(c, 10000);
    for (const c of cs) c.expectedOutage = true;
    await live.stop(processRef.current); for (const c of cs) c.match = null;
    processRef.current = await start();
    await h.wait(() => cs.every(c => c.match), 'native building PostgreSQL reconnect');
    for (let i = 0; i < cs.length; i++) {
      cs[i].expectedOutage = false; assert.deepEqual(cs[i].match.state, pending[i]); assertOccupancy(cs[i], command, true);
    }
    await noReplay(cs, 'backend restart baseline'); live.privacy(cs);
    check(command.type + ': refresh/native reconnect/PostgreSQL restart restore exact states without replay');
    await resolveGold(cs, actor); live.privacy(cs);
    for (const c of cs) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
    await actor.page.screenshot({ path: path.join(output, command.type + '.png') });
    report.cases.push({ type: command.type, passed: true, expectedRestartRefusals: cs.flatMap(c => c.expectedWarnings).length,
      unexpectedErrors: [] });
  } finally { for (const c of cs) await c.context.close(); }
}

(async () => {
  await fs.mkdir(output, { recursive: true });
  const processRef = { current: await start() };
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
  try {
    const entries = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
    for (const type of ['place_road', 'place_settlement', 'upgrade_city']) {
      const entry = entries.find(e => e.route.type === type); assert(entry, 'Prepared building fixture missing');
      await runCase(browser, entry, processRef);
    }
    report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close(); await live.stop(processRef.current);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
