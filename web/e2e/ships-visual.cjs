// Real Board3D, PUBLIC snapshots only. No trusted Fog recipe or live-server override.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const baseline = process.argv.includes('--baseline');
const measureOnly = process.argv.includes('--measure-only');
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ships-visual-phase2'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function observeScene() {
  let id = 0;
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, inject: () => ++id, checkDCE() {},
    onCommitFiberRoot(_, root) {
      const store = root.current?.stateNode?.containerInfo;
      if (store?.getState && store.getState().scene) { window.__scene = store;
        window.__sceneCommits = (window.__sceneCommits || 0) + 1; }
    }, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
  };
}
async function ready(page) {
  await page.waitForFunction(() => !!window.__scene?.getState().scene);
  await page.waitForFunction(() => {
    let pending = false; window.__scene.getState().scene.traverse(o => { if (o.userData.terrainFallback) pending = true; });
    return !pending;
  }); await sleep(1000);
}
async function measure(page) {
  return page.evaluate(async () => {
    const { gl, scene, camera } = window.__scene.getState(), gpu = gl.getContext();
    for (let i = 0; i < 12; i++) { gl.render(scene, camera); gpu.finish(); }
    const sync = [], submit = [];
    for (let i = 0; i < 60; i++) {
      const start = performance.now(); gl.render(scene, camera); gpu.finish(); sync.push(performance.now() - start);
      if (i % 10 === 9) await new Promise(requestAnimationFrame);
    }
    for (let i = 0; i < 30; i++) {
      await new Promise(requestAnimationFrame);
      const start = performance.now(); gl.render(scene, camera); submit.push(performance.now() - start);
    }
    sync.sort((a, b) => a - b); submit.sort((a, b) => a - b);
    const debug = gpu.getExtension('WEBGL_debug_renderer_info');
    let ships = 0; scene.traverse(o => { if (o.userData.piece === 'ship' && !o.userData.preview) ships++; });
    return { gpuMedianMs: sync[30], gpuP95Ms: sync[56], cpuSubmitMedianMs: submit[15], cpuSubmitP95Ms: submit[28],
      calls: gl.info.render.calls, triangles: gl.info.render.triangles, geometries: gl.info.memory.geometries,
      textures: gl.info.memory.textures, ships, viewport: [gl.domElement.width, gl.domElement.height],
      gpu: debug ? gpu.getParameter(debug.UNMASKED_RENDERER_WEBGL) : 'unavailable' };
  });
}
async function sceneInfo(page) {
  return page.evaluate(() => {
    const { scene, gl } = window.__scene.getState(), result = { ships: [], echoes: [], echoAnchors: [], fogReveals: 0,
      commits: window.__sceneCommits,
      frames: gl.info.render.frame, geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
    scene.traverse(o => {
      if (o.userData.piece === 'ship' && !o.userData.preview) {
        let pose; o.traverse(child => { if (child.userData.shipVisual) pose = { position: child.position.toArray(),
          rotation: child.rotation.toArray().slice(0, 3), scale: child.scale.toArray(), ...child.userData }; });
        result.ships.push({ edge: o.userData.edge.join(','), owner: o.userData.owner,
          position: o.position.toArray(), rotation: o.rotation.y, pose });
      }
      if (o.userData.shipDeparture && o.visible) { result.echoes.push(o.userData.fromEdge);
        result.echoAnchors.push({ position: o.parent.position.toArray(), rotation: o.parent.rotation.y }); }
      if (o.userData.fogReveal && o.visible) result.fogReveals++;
    }); return result;
  });
}
async function idleFrames(page) {
  await page.mouse.move(1, 1); await sleep(250); const first = await sceneInfo(page); await sleep(1000);
  return (await sceneInfo(page)).frames - first.frames;
}
async function effect(page, kind) {
  await page.waitForFunction(kind => {
    let active = false; window.__scene.getState().scene.traverse(o => {
      active ||= o.userData.shipVisual && o.userData.appearing && o.userData.shipEffect === kind;
    }); return active;
  }, kind);
}
function exactAnchor(ship, state, edge) {
  const [a, b] = edge.map(v => state.vertices[v]);
  const expected = [(a[0] + b[0]) / state.size / 2, .32, (a[1] + b[1]) / state.size / 2];
  assert(ship.position.every((v, i) => Math.abs(v - expected[i]) < 1e-8));
  assert(Math.abs(ship.rotation + Math.atan2(b[1] - a[1], b[0] - a[0])) < 1e-8);
  assert.equal(ship.pose.position[0], 0); assert.equal(ship.pose.position[2], 0); assert.equal(ship.pose.rotation[1], 0);
}
async function main() {
  if (baseline) {
    const cwd = path.resolve(__dirname, '../..');
    const head = spawnSync('git', ['rev-parse', '--short=7', 'HEAD'], { cwd, encoding: 'utf8' });
    const clean = spawnSync('git', ['diff', '--quiet', 'HEAD', '--', 'web/src/'], { cwd });
    assert(head.status === 0 && head.stdout.trim() === '608f14e' && clean.status === 0,
      'Baseline requires unchanged pre-ship runtime at 608f14e');
  }
  await fs.mkdir(output, { recursive: true });
  const demo = await startDemo(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = { baseline, measureOnly, completed: false, chrome: browser.version(), measurements: {}, checks: [], errors: [], screenshots: [] };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(observeScene); const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('console', msg => { if (msg.type() === 'error') report.errors.push(msg.text()); });
  const shot = async name => {
    const file = path.join(output, (baseline ? 'before-' : 'after-') + name + '.png');
    await page.screenshot({ path: file }); report.screenshots.push(file);
  };
  try {
    await page.goto(demo.origin + '/?demo=1&ships=1'); await ready(page);
    for (const large of [false, true]) {
      await page.evaluate(large => window.__fogFixture.load(large ? 'large' : 'partial'), large); await ready(page);
      for (const reduced of [false, true]) {
        await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' }); await sleep(300);
        const key = (large ? '50' : '7') + (reduced ? '-reduced' : '-normal');
        report.measurements[key] = await measure(page);
        report.measurements[key].idleFramesPerSecond = await idleFrames(page); await shot(key);
        if (reduced) assert.equal(report.measurements[key].idleFramesPerSecond, 0);
      }
    }
    if (measureOnly) {
      assert.deepEqual(report.errors, []); report.completed = true;
      report.checks.push('isolated performance-only run; acceptance recorded separately');
      console.log(JSON.stringify(report, null, 2)); return;
    }
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await page.evaluate(() => window.__fogFixture.load('partial')); await ready(page);
    let publicBefore = await page.evaluate(() => window.__fogFixture.snapshot());
    let target = publicBefore.state.legal.ships[0];
    await page.getByRole('button', { name: 'Construct ship', exact: true }).click();
    if (!baseline) {
      await effect(page, 'build'); const during = await sceneInfo(page);
      assert.equal(during.ships.length, 2); assert(during.fogReveals > 0);
      exactAnchor(during.ships.find(s => s.edge === target.join(',')), publicBefore.state, target);
      assert(during.ships.some(s => s.pose.shipEffect === 'build' && s.pose.scale[1] < 1));
    }
    await sleep(140); await shot('construction');
    await sleep(1000); await shot('constructed');
    if (!baseline) assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing && s.pose.scale.every(v => v === 1)));
    await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
    if (!baseline) {
      // A public edge list need not store endpoints in canonical key order.
      await page.evaluate(() => {
        const frame = window.__fogFixture.snapshot(), source = frame.state.legal.move_ship.sources[0].join(',');
        const edge = frame.state.edges.find(e => e.join(',') === source); edge.reverse(); frame.tick++;
        window.__fogFixture.publish(frame);
      }); await sleep(100);
    }
    const oldShip = (await sceneInfo(page)).ships[0];
    publicBefore = await page.evaluate(() => window.__fogFixture.snapshot()); target = publicBefore.state.legal.ships[0];
    await page.getByRole('button', { name: 'Move ship', exact: true }).click();
    if (!baseline) {
      await effect(page, 'move'); const during = await sceneInfo(page);
      assert.equal(during.ships.length, 1); assert.equal(during.echoes.length, 1);
      assert.deepEqual(during.echoes[0], publicBefore.state.legal.move_ship.sources[0]);
      assert.deepEqual(during.echoAnchors[0].position, oldShip.position);
      assert.equal(during.echoAnchors[0].rotation, oldShip.rotation);
      exactAnchor(during.ships[0], publicBefore.state, target);
    }
    await sleep(140); await shot('movement');
    await sleep(1000); await shot('moved');
    if (!baseline) {
      let current = await sceneInfo(page); assert.equal(current.echoes.length, 0);
      assert.equal(current.ships[0].pose.appearing, false); exactAnchor(current.ships[0], publicBefore.state, target);
      const accepted = await page.evaluate(() => window.__fogFixture.snapshot());
      await page.evaluate(frame => { window.__fogFixture.publish(frame); window.__fogFixture.reject(); }, accepted); await sleep(150);
      assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing));
      report.checks.push('confirmed construction/Fog reveal coexist; movement uses finite source echo and exact destination/orientation; duplicate/error do not replay');

      const raycasts = await page.evaluate(() => {
        let count = 0, safe = true;
        window.__scene.getState().scene.traverse(o => { if (!o.userData.shipVisual && !o.userData.shipDeparture) return;
          o.traverse(child => { if (!child.isMesh) return; const hits = []; count++;
            try { child.raycast({}, hits); safe &&= hits.length === 0; } catch { safe = false; } });
        }); return { count, safe };
      }); assert(raycasts.count >= 5 && raycasts.safe);
      await page.getByLabel('Fog effects').selectOption('still');
      const start = await sceneInfo(page); assert((await idleFrames(page)) <= 15);
      const changed = await sceneInfo(page);
      assert(changed.ships.some((s, i) => JSON.stringify(s.pose.rotation) !== JSON.stringify(start.ships[i].pose.rotation)));
      assert.equal(changed.geometries, start.geometries); assert.equal(changed.textures, start.textures);
      assert.equal(changed.commits, start.commits);
      await page.getByLabel('Ship effects').selectOption('static'); assert.equal(await idleFrames(page), 0);
      assert((await sceneInfo(page)).ships.every(s => s.pose.position.every(v => v === 0) && s.pose.rotation.every(v => v === 0)));
      report.checks.push('ship visuals never raycast; ambient rocking uses bounded shared clock/no resource churn; both static effects restore demand idle');

      await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
      await page.getByLabel('Ship effects').selectOption('motion');
      const beforeReject = await page.evaluate(() => window.__fogFixture.snapshot());
      await page.evaluate(() => window.__fogFixture.reject()); await sleep(100);
      assert.deepEqual(await page.evaluate(() => window.__fogFixture.snapshot()), beforeReject);
      assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing));
      await page.emulateMedia({ reducedMotion: 'reduce' });
      await page.getByRole('button', { name: 'Construct ship', exact: true }).click();
      await page.waitForFunction(() => Object.keys(window.__fogFixture.snapshot().state.occupied_ships).length === 2);
      await sleep(100); assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing && s.pose.scale.every(v => v === 1)));
      assert.equal(await idleFrames(page), 0);
      await page.emulateMedia({ reducedMotion: 'no-preference' }); await sleep(100);
      assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing));
      report.checks.push('rejection cannot introduce a ship; reduced-motion construction is immediate and preference restoration does not replay');

      await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
      await page.evaluate(() => window.__fogFixture.status('disconnected')); await sleep(50);
      await page.evaluate(() => window.__fogFixture.status('connected')); await sleep(50);
      await page.evaluate(() => window.__fogFixture.ship(true)); await sleep(100);
      assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing)); assert.equal((await sceneInfo(page)).echoes.length, 0);
      await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
      await page.getByRole('button', { name: '2D', exact: true }).click();
      await page.getByRole('button', { name: 'Construct ship', exact: true }).click(); await sleep(150);
      await page.getByRole('button', { name: '3D', exact: true }).click(); await sleep(100);
      assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing));
      await page.reload(); await ready(page); assert((await sceneInfo(page)).ships.every(s => !s.pose.appearing));
      report.checks.push('cached reconnect/fresh frame, SVG-to-3D and refresh establish baselines without old construction/movement');

      await page.getByRole('button', { name: 'Multiple ships', exact: true }).click(); await sleep(1000);
      current = await sceneInfo(page); assert(current.ships.length > 1); assert(current.ships.every(s => !s.pose.appearing));
      for (const size of [{ width: 1024, height: 768 }, { width: 1440, height: 900 }]) {
        await page.setViewportSize(size); await sleep(150); assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      await shot('fleet');
      report.checks.push('multiple ships preserve owners/anchors and settle; desktop viewport has no overflow');

      // Separate recording context: video encoding is excluded from performance measurements.
      const videoContext = await browser.newContext({ viewport: { width: 1440, height: 900 },
        recordVideo: { dir: output, size: { width: 1440, height: 900 } } });
      const videoPage = await videoContext.newPage(); await videoPage.goto(demo.origin + '/?demo=1&ships=1'); await sleep(1500);
      await videoPage.getByRole('button', { name: 'Construct ship', exact: true }).click(); await sleep(1300);
      await videoPage.getByRole('button', { name: 'Reset preview', exact: true }).click(); await sleep(300);
      await videoPage.getByRole('button', { name: 'Move ship', exact: true }).click(); await sleep(1500);
      const recording = videoPage.video(); await videoContext.close(); report.video = await recording.path();
    }
    assert.deepEqual(report.errors, []);
    report.checks.push('real ship public preview and same 7/50 scenes measured in normal/reduced modes');
    report.completed = true; console.log(JSON.stringify(report, null, 2));
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, measureOnly ? 'after-performance.json' : baseline ? 'before.json' : 'after.json'), JSON.stringify(report, null, 2));
    await browser.close(); demo.server.close();
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { observeScene, ready, measure, idleFrames };
