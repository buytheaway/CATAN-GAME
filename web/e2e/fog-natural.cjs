// Real Chrome replays a legally generated whole Fog match. No prepared midgame,
// grants, score edits, mocked frames or public Fog admission.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawn } = require('node:child_process');
const { chromium } = require('playwright');
process.env.CATAN_E2E_ORIGIN ||= 'http://127.0.0.1:18770';
process.env.CATAN_E2E_OUTPUT ||= path.join(os.tmpdir(), 'catan-fog-natural-browser-' + Date.now());
const h = require('./game-actions.cjs');
const fog = require('./fog-live.cjs');
const natural = require('./natural-full-matches.cjs');
const origin = process.env.CATAN_E2E_ORIGIN, output = process.env.CATAN_E2E_OUTPUT;
const manifestPath = path.join(output, 'private-bindings.json');
const root = path.resolve(__dirname, '../..');
const report = { naturalFullMatch: true, preparedMidgame: false, publicFog: false, checks: [] };
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));
function check(label) { report.checks.push(label); console.log('PASS ' + label); }

async function start() {
  assert.equal(new URL(origin).hostname, '127.0.0.1');
  assert(process.env.DATABASE_URL, 'Disposable localhost PostgreSQL DATABASE_URL required');
  const python = process.env.CATAN_E2E_PYTHON || path.join(root, process.platform === 'win32' ? '.venv/Scripts/python.exe' : '.venv/bin/python');
  const child = spawn(python, ['-B', '-X', 'utf8', '-m', 'tests.fog_natural_support', 'serve', '--manifest', manifestPath], {
    cwd: root, env: { ...process.env, CATAN_PORT: new URL(origin).port, CATAN_HOST: '127.0.0.1', CATAN_ENABLE_TEST_TOOLS: '0' },
    windowsHide: true, stdio: ['ignore', 'pipe', 'pipe'],
  });
  child.stdout.resume(); child.stderr.resume();
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    if (child.exitCode != null) throw Error('Guarded natural Fog backend failed to start');
    try { const r = await fetch(origin + '/health'); if (r.ok && (await r.json()).ready) return child; } catch {}
    await pause(100);
  }
  child.kill(); throw Error('Natural Fog startup timed out');
}
async function stop(child) {
  if (!child || child.exitCode != null) return;
  const done = new Promise(resolve => child.once('exit', resolve)); child.kill(); await done;
}
function synchronized(clients) { natural.synchronized(clients); fog.privacy(clients); }
async function verifyHud(clients) {
  for (const c of clients) {
    await c.page.waitForFunction(expected => {
      const points = [...document.querySelectorAll('.players-strip .player-counters strong')].map(n => n.textContent);
      const labels = [...document.querySelectorAll('.resource-hand button')].map(n => n.getAttribute('aria-label'));
      return JSON.stringify(points) === JSON.stringify(expected.points)
        && expected.resources.every(label => labels.includes(label)) && labels.length === 5;
    }, { points: c.match.state.players.map(p => `${p.vp} VP`),
      resources: Object.entries(h.own(c).res).map(([r, n]) => `Give ${r} (${n} owned)`) });
  }
}
async function open(browser, binding, pid) {
  const c = await h.newClient(browser, 'Fog Natural ' + (pid + 1));
  await c.page.addInitScript(() => {
    window.__seenFogSvg = [];
    const observe = () => new MutationObserver(records => {
      for (const record of records) for (const node of record.addedNodes) {
        if (node.matches?.('[data-fog-reveal]')) window.__seenFogSvg.push(node.getAttribute('data-fog-reveal'));
        node.querySelectorAll?.('[data-fog-reveal]').forEach(n => window.__seenFogSvg.push(n.getAttribute('data-fog-reveal')));
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
    if (document.documentElement) observe(); else document.addEventListener('DOMContentLoaded', observe, { once: true });
  });
  c.expectedOutage = false; c.expectedWarnings = [];
  c.page.on('console', m => {
    if (c.expectedOutage && m.type() === 'error' && /WebSocket connection.*ERR_CONNECTION_REFUSED/.test(m.text())) {
      assert.equal(c.console.at(-1), m.text()); c.expectedWarnings.push(c.console.pop());
    }
  });
  await c.page.evaluate(({ code, proof, server, name }) => {
    const entry = { room_code: code, reconnect_token: proof, server_url: server, last_known_name: name, last_seen_at: Date.now() };
    localStorage.setItem('catan_recent_games', JSON.stringify({ version: 1, entries: [entry] }));
    sessionStorage.setItem('catan_current_game', JSON.stringify({ room_code: code, server_url: server, last_known_name: name }));
  }, { code: binding.room_code, proof: binding.proofs[pid], name: c.name, server: origin.replace(/^http/, 'ws') + '/ws' });
  await c.page.reload({ waitUntil: 'networkidle' });
  await h.wait(() => c.room, 'owned unstarted Fog lobby');
  assert.equal(c.match, null);
  return c;
}
async function restart(clients, ref, label) {
  const saved = clients.map(c => c.match.state);
  for (const c of clients) c.expectedOutage = true;
  await stop(ref.current);
  for (const c of clients) c.match = null;
  ref.current = await start();
  await h.wait(() => clients.every(c => c.match), label);
  for (let i = 0; i < clients.length; i++) {
    clients[i].expectedOutage = false;
    assert.deepEqual(clients[i].match.state, saved[i]);
  }
  synchronized(clients); check(label);
}
async function uiCommand(clients, entry, label) {
  await fog.refresh(clients); // Actual controller learns the consumed wire sequence.
  const c = clients[entry.actor_pid];
  const cmd = entry.cmd;
  if (cmd.type === 'choose_gold') {
    await c.page.getByRole('dialog', { name: /Gold Choice/ }).waitFor();
    assert.equal(await clients[1 - entry.actor_pid].page.getByRole('dialog', { name: /Gold Choice/ }).count(), 0);
    await c.page.getByLabel('Gold resource').selectOption(cmd.res);
    await c.page.getByLabel('Gold quantity').fill(String(cmd.qty || 1));
    await h.action(clients, c, () => c.page.getByRole('button', { name: 'Choose', exact: true }).click(), label);
  } else if (cmd.type === 'place_road') {
    await c.page.getByRole('button', { name: '2D', exact: true }).click();
    const button = c.page.getByRole('button', { name: 'Road', exact: true });
    if (await button.isEnabled()) await button.click();
    const edge = [...cmd.eid].sort((a, b) => a - b).join(',');
    await h.action(clients, c, () => c.page.locator(`[data-target-edge="${edge}"]`).click(), label);
  } else if (cmd.type === 'build_ship') {
    await h.open3d(c);
    await c.page.evaluate(() => {
      window.__seenFog3D = false;
      let remaining = 120;
      const sample = () => {
        window.__scene?.getState().scene.traverse(o => {
          if (o.visible && o.userData.fogReveal && o.material?.opacity > 0) window.__seenFog3D = true;
        });
        if (--remaining > 0) requestAnimationFrame(sample);
      }; requestAnimationFrame(sample);
    });
    await c.page.getByRole('button', { name: 'Ship', exact: true }).click();
    await h.action(clients, c, () => h.clickTarget(c, 'edge', cmd.eid), label);
  } else await h.action(clients, c, () => c.page.getByRole('button', { name: 'Roll', exact: true }).click(), label);
  assert.equal(clients[0].match.tick, entry.tick);
  synchronized(clients);
}

async function run(browser, trace, ref) {
  const binding = JSON.parse(await fs.readFile(manifestPath, 'utf8'));
  const clients = [];
  try {
    for (const pid of [0, 1]) clients.push(await open(browser, binding, pid));
    const host = clients[0];
    assert(host.room.map_presets.every(p => !/fog/i.test(p.id)));
    assert.equal(host.room.map_id, trace.map_id);
    await host.page.getByRole('button', { name: 'Start Match', exact: true }).click();
    await h.wait(() => clients.every(c => c.match), 'real host Start Match through original dispatcher');
    assert.equal(Object.keys(host.match.state.occupied_v).length, 0);
    assert(host.match.state.tiles.some(t => t.visibility === 'hidden'));
    synchronized(clients);
    await verifyHud(clients);
    check('two owning browsers start from a fresh opening; public Fog preset is absent');
    await fog.renderer(host, 'natural-initial');
    report.checks.push('initial actual SVG/Board3D Fog geometry, GLBs, tokens and privacy');
    await h.open3d(clients[1]);
    let road = false, ship = false, roll = false, pendingRestart = false, refreshed = false, goldUI = false;
    for (let index = 0; index < trace.commands.length; index++) {
      const entry = trace.commands[index], before = clients[entry.actor_pid].match.state;
      const initialHidden = new Set(before.tiles.map((t, i) => t.visibility === 'hidden' ? i : -1).filter(i => i >= 0));
      const useUI = entry.cmd.type === 'choose_gold' || entry.cmd.type === 'place_road' && !road
        || entry.cmd.type === 'build_ship' && !ship || entry.cmd.type === 'roll' && !roll;
      if (entry.cmd.type === 'choose_gold' && !pendingRestart) {
        await restart(clients, ref, 'actual backend restart during naturally earned pending Gold');
        pendingRestart = true;
      }
      if (useUI) await uiCommand(clients, entry, 'natural real UI ' + entry.cmd.type);
      else await natural.command(clients, entry, index + 1);
      if (entry.cmd.type === 'choose_gold' && !goldUI) {
        check('actual entitled-only Gold UI resolves a naturally earned choice'); goldUI = true;
      }
      synchronized(clients);
      if (entry.cmd.type === 'choose_gold' || entry.cmd.type === 'upgrade_city'
          || before.players.some((p, i) => p.vp !== clients[entry.actor_pid].match.state.players[i].vp))
        await verifyHud(clients);
      const discovered = [...initialHidden].filter(i => host.match.state.tiles[i].visibility === 'revealed');
      if (discovered.length) {
        assert(['place_road', 'build_ship', 'move_ship'].includes(entry.cmd.type));
        if (entry.cmd.type === 'place_road') {
          if (!road) check('real SVG Road reveals only committed tiles and starts finite feedback');
          road = true;
          if (useUI) assert((await clients[entry.actor_pid].page.evaluate(() => window.__seenFogSvg)).length > 0);
        }
        if (entry.cmd.type === 'build_ship') {
          if (!ship) check('real Board3D Ship discovery synchronizes both public boards');
          ship = true;
          if (useUI) assert(await clients[entry.actor_pid].page.evaluate(() => window.__seenFog3D));
        }
        await pause(500);
        for (const c of clients) {
          assert.equal(await c.page.locator('[data-fog-reveal]').count(), 0);
          const active = await c.page.evaluate(() => {
            let n = 0; window.__scene?.getState().scene.traverse(o => { if (o.visible && o.userData.fogReveal) n++; }); return n;
          }); assert.equal(active, 0);
        }
      }
      if (entry.cmd.type === 'roll') roll = true;
      if (!refreshed && host.match.state.phase === 'main' && !host.match.state.pending_action && host.match.state.roll_count >= 3) {
        await fog.refresh(clients); await fog.renderer(host, 'natural-in-play');
        report.checks.push('in-play actual SVG/Board3D terrain, tokens, GLBs and uniform remaining Fog');
        check('all-client refresh preserves revealed terrain, private choices and authoritative HUD'); refreshed = true;
      }
      if ((index + 1) % 80 === 0) console.log('Progress ' + (index + 1) + ' accepted Fog actions');
    }
    assert(road && ship && roll && pendingRestart && refreshed);
    const final = host.match.state;
    await verifyHud(clients);
    assert(final.game_over && final.winner_pid === trace.result.winner_pid);
    assert.deepEqual(final.players.map(p => p.vp), trace.result.final_vp);
    assert(final.players.every(p => !p.special_vp));
    for (const c of clients) {
      const results = c.page.getByRole('dialog', { name: 'Match results', exact: true });
      await results.waitFor();
      assert.equal(await results.getByRole('list', { name: 'Final scores' }).locator('li').count(), 2);
      assert.equal(await results.getByRole('button', { name: 'Rematch', exact: true }).isDisabled(), c !== host);
      await c.page.screenshot({ path: path.join(output, 'natural-results-' + c.match.state.you_pid + '.png') });
    }
    check('natural production-funded victory and both real post-game score dialogs');
    check('actual VP HUD and resource-hand DOM match each recipient after score changes and Gold choices');
    await restart(clients, ref, 'finished Fog result survives actual PostgreSQL recovery');
    await fog.refresh(clients);
    const oldEpoch = host.match.match_id;
    await host.page.getByRole('dialog', { name: 'Match results', exact: true }).getByRole('button', { name: 'Rematch', exact: true }).click();
    await h.wait(() => clients.every(c => c.match.match_id === oldEpoch + 1 && c.match.tick === 0), 'real host rematch');
    synchronized(clients);
    await verifyHud(clients);
    for (const c of clients) {
      assert.equal(c.match.state.phase, 'setup');
      assert.deepEqual(c.match.state.occupied_v, {}); assert.deepEqual(c.match.state.occupied_ships, {});
      assert.equal(Object.keys(c.match.state.pending_gold).length, 0);
      assert(c.match.state.tiles.some(t => t.visibility === 'hidden'));
      assert.equal(await c.page.getByRole('dialog', { name: 'Match results', exact: true }).count(), 0);
      assert.deepEqual(c.jsErrors, []); assert.deepEqual(c.console, []);
    }
    check('real rematch starts fresh Fog visibility, empty pieces, zero VP and no old Gold choices');
    report.match = { players: 2, rolls: trace.actual_turns, actions: trace.player_actions,
      final_vp: trace.result.final_vp, discovery: trace.discovery,
      js_errors: [], unexpected_warnings: [], expected_restart_refusals: clients.flatMap(c => c.expectedWarnings).length };
  } finally { for (const c of clients) await c.context.close(); }
}
async function main() {
  assert(process.env.CATAN_NATURAL_TRACE, 'Generate the natural Fog transcript first');
  const trace = JSON.parse(await fs.readFile(process.env.CATAN_NATURAL_TRACE, 'utf8'));
  assert.equal(trace.format, 'catan-natural-fog-match-v1');
  await fs.mkdir(output, { recursive: true });
  const ref = { current: await start() };
  const browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
  try { await run(browser, trace, ref); }
  finally {
    await fs.writeFile(path.join(output, 'report.json'), JSON.stringify(report, null, 2));
    await browser.close(); await stop(ref.current);
  }
}
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
