// Normal production React/executor/F1/receipts/PG with isolated prepared Fog visual fixtures.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18774';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-ships-live-' + Date.now());
const h = require('./game-actions.cjs'), live = require('./fog-live.cjs');
const output = process.env.CATAN_E2E_OUTPUT;
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
const report = { scope: 'prepared internal Fog ship fixtures; normal authority/PG; public admission disabled', checks: [], cases: [] };
function check(label) { report.checks.push(label); console.log('PASS ' + label); }
async function monitor(c) {
  await c.page.evaluate(() => {
    window.__shipObserved = { build: false, move: false, echo: false, fog: false };
    const end = performance.now() + 2500;
    const sample = () => {
      window.__scene?.getState().scene.traverse(o => {
        if (o.userData.shipVisual && o.userData.appearing && o.userData.shipEffect)
          window.__shipObserved[o.userData.shipEffect] = true;
        if (o.userData.shipDeparture && o.visible) window.__shipObserved.echo = true;
        if (o.userData.fogReveal && o.visible) window.__shipObserved.fog = true;
      });
      if (performance.now() < end) requestAnimationFrame(sample);
    }; requestAnimationFrame(sample);
  });
}
async function active(c) {
  return c.page.evaluate(() => {
    let n = 0; window.__scene?.getState().scene.traverse(o => {
      if (o.userData.shipVisual && o.userData.appearing || o.userData.shipDeparture && o.visible) n++;
    }); return n;
  });
}
async function caseRun(browser, entry, ref) {
  const cs = [];
  try {
    for (const pid of [0, 1]) { const c = await live.open(browser, entry, pid); cs.push(c); await h.open3d(c); }
    const actor = cs[0], moving = entry.route.type === 'move_ship';
    live.privacy(cs); assert.equal(await active(actor), 0);
    if (!moving) {
      await actor.page.getByRole('button', { name: 'Ship', exact: true }).click();
      const beforeRejected = cs.map(c => structuredClone(c.match.state));
      for (const c of cs) await monitor(c);
      await h.invalidNext(actor, { type: 'build_ship', eid: [-1, -2] });
      await h.action(cs, actor, () => h.clickTarget(actor, 'edge', entry.route.eid), 'rejected ship remains absent', true);
      await pause(120);
      for (let i = 0; i < cs.length; i++) {
        assert.deepEqual(cs[i].match.state, beforeRejected[i], 'rejection preserves each personal snapshot');
        assert(!Object.hasOwn(cs[i].match.state.occupied_ships, entry.route.eid.join(',')));
      }
      for (const c of cs) { const seen = await c.page.evaluate(() => window.__shipObserved); assert(!seen.build && !seen.move && !seen.echo); }
      check('rejected real ship command preserves both snapshots and triggers no construction');
    } else {
      await actor.page.getByRole('button', { name: 'Move Ship', exact: true }).click();
      await h.clickTarget(actor, 'edge', entry.route.from_eid);
    }
    for (const c of cs) await monitor(c);
    await h.action(cs, actor, () => h.clickTarget(actor, 'edge', moving ? entry.route.to_eid : entry.route.eid), entry.route.type);
    const accepted = actor.sent.at(-1); await pause(1500);
    live.privacy(cs);
    for (const c of cs) {
      const seen = await c.page.evaluate(() => window.__shipObserved);
      assert(moving ? seen.move && seen.echo : seen.build); assert(seen.fog); assert.equal(await active(c), 0);
    }
    const target = (moving ? entry.route.to_eid : entry.route.eid).join(',');
    assert.equal(actor.match.state.occupied_ships[target], 0);
    if (moving) assert.equal(actor.match.state.occupied_ships[entry.route.from_eid.join(',')], undefined);
    check(entry.route.type + ': both real clients animate only accepted state, with Fog discovery and private Gold');

    for (const c of cs) await monitor(c);
    const ackCount = actor.acks.length; await live.raw(actor, accepted);
    await h.wait(() => actor.acks.length > ackCount, 'duplicate durable receipt'); await pause(200);
    assert.equal(actor.acks.at(-1).duplicate, true);
    for (const c of cs) { assert.equal(await active(c), 0); const seen = await c.page.evaluate(() => window.__shipObserved);
      assert(!seen.build && !seen.move && !seen.echo); }
    check(entry.route.type + ': duplicate receipt never starts another animation');

    await live.refresh(cs); for (const c of cs) {
      // Default 3D is already mounted behind the mandatory Gold dialog.
      await c.page.waitForFunction(() => !!window.__scene?.getState().scene);
      assert.equal(await active(c), 0);
    }
    const pending = cs.map(c => c.match.state);
    for (const c of cs) c.expectedOutage = true;
    await live.stop(ref.current); for (const c of cs) c.match = null;
    ref.current = await live.start(['--ship-motion']);
    await h.wait(() => cs.every(c => c.match), 'restart owning ship clients');
    for (let i = 0; i < cs.length; i++) {
      cs[i].expectedOutage = false; assert.deepEqual(cs[i].match.state, pending[i]);
      assert.equal(await active(cs[i]), 0);
    }
    live.privacy(cs); check(entry.route.type + ': refresh/reconnect/PG restart restore exact state without replay');
    while (actor.match.state.pending_action === 'choose_gold') {
      const quantity = actor.match.state.pending_gold[actor.match.state.you_pid];
      await actor.page.getByLabel('Gold resource').selectOption('ore');
      await actor.page.getByLabel('Gold quantity').fill(String(quantity));
      await h.action(cs, actor, () => actor.page.getByRole('button', { name: 'Choose', exact: true }).click(), 'Gold after ship animation');
    }
    live.privacy(cs);
    await actor.page.screenshot({ path: path.join(output, entry.route.type + '.png') });
    for (const c of cs) { assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []); }
    report.cases.push({ type: entry.route.type, passed: true, unexpectedErrors: [],
      expectedRestartRefusals: cs.flatMap(c => c.expectedWarnings).length });
  } finally { for (const c of cs) await c.context.close(); }
}
(async () => {
  await fs.mkdir(output, { recursive: true }); const ref = { current: await live.start(['--ship-motion']) };
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
  try {
    const entries = JSON.parse(await fs.readFile(path.join(output, 'fixture-bindings.json'), 'utf8'));
    for (const type of ['build_ship', 'move_ship']) await caseRun(browser, entries.find(e => e.route.type === type), ref);
    report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close(); await live.stop(ref.current);
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
