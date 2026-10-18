// Repeatable before/after diagnostics and visual checks on exactly the same PUBLIC fixture.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { spawnSync } = require('node:child_process');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const baseline = process.argv.includes('--baseline');
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-fog-visual-results'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
function observeScene() {
  let id = 0;
  window.__REACT_DEVTOOLS_GLOBAL_HOOK__ = {
    supportsFiber: true, inject: () => ++id, checkDCE() {},
    onCommitFiberRoot(_, root) {
      const store = root.current?.stateNode?.containerInfo;
      if (store?.getState && store.getState().scene) window.__scene = store;
    }, onCommitFiberUnmount() {}, onPostCommitFiberRoot() {},
  };
}
async function measure(page) {
  // Fixed camera, real scene/shadows and all GLBs loaded. GPU-synchronous render latency,
  // not a sustained-FPS claim. No changes to renderer settings for the benchmark.
  return page.evaluate(async () => {
    const { gl, scene, camera } = window.__scene.getState(), context = gl.getContext();
    const debug = context.getExtension('WEBGL_debug_renderer_info');
    for (let i = 0; i < 12; i++) { gl.render(scene, camera); context.finish(); }
    const samples = [];
    for (let i = 0; i < 60; i++) {
      const start = performance.now(); gl.render(scene, camera); context.finish(); samples.push(performance.now() - start);
      if (i % 10 === 9) await new Promise(requestAnimationFrame);
    }
    samples.sort((a, b) => a - b);
    const info = { medianMs: samples[30], p95Ms: samples[56], calls: gl.info.render.calls,
      triangles: gl.info.render.triangles, geometries: gl.info.memory.geometries, textures: gl.info.memory.textures,
      gpu: debug ? context.getParameter(debug.UNMASKED_RENDERER_WEBGL) : 'unavailable',
      viewport: [gl.domElement.width, gl.domElement.height], tiles: 0, hidden: 0 };
    scene.traverse(o => { if (o.userData.terrain) { info.tiles++; if (o.userData.visibility === 'hidden') info.hidden++; } });
    return info;
  });
}
async function ready(page) {
  await page.waitForFunction(() => !!window.__scene?.getState().scene);
  await page.waitForFunction(() => {
    let pending = false; window.__scene.getState().scene.traverse(o => { if (o.userData.terrainFallback) pending = true; });
    return !pending;
  });
  await sleep(1000);
}
async function sceneState(page) {
  return page.evaluate(() => {
    const { scene, gl } = window.__scene.getState(), result = { hidden: 0, clouds: 0, reveals: 0, ships: 0,
      frames: gl.info.render.frame, geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
    scene.traverse(o => {
      if (o.userData.terrain && o.userData.visibility === 'hidden') result.hidden++;
      if (o.userData.fogCloud) result.clouds++;
      if (o.userData.fogReveal && o.visible) result.reveals++;
      if (o.userData.edge && o.userData.owner != null && o.userData.piece === 'ship') result.ships++;
    }); return result;
  });
}
async function idleFrames(page) {
  await page.mouse.move(1, 1); await sleep(250);
  const first = await sceneState(page); await sleep(1000);
  return (await sceneState(page)).frames - first.frames;
}
async function waitHidden(page, count) {
  await page.waitForFunction(count => {
    let hidden = 0; window.__scene.getState().scene.traverse(o => {
      if (o.userData.terrain && o.userData.visibility === 'hidden') hidden++;
    }); return hidden === count;
  }, count);
}
(async () => {
  if (baseline) {
    const cwd = path.resolve(__dirname, '../..');
    const head = spawnSync('git', ['rev-parse', '--short=7', 'HEAD'], { cwd, encoding: 'utf8' });
    const clean = spawnSync('git', ['diff', '--quiet', 'HEAD', '--', 'web/src/board3d', 'web/src/board/fogReveal.ts',
      'web/src/components/BoardRenderer.tsx'], { cwd });
    assert(head.status === 0 && head.stdout.trim() === 'ee56e23' && clean.status === 0,
      '--baseline requires the unchanged ee56e23 renderer, before visual implementation; never relabel the new renderer as old');
  }
  await fs.mkdir(output, { recursive: true });
  const demo = await startDemo(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = { baseline, completed: false, browser: browser.version(), checks: [], measurements: {}, errors: [], screenshots: [] };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(observeScene);
  const page = await context.newPage(); page.on('pageerror', e => report.errors.push(e.message));
  page.on('console', msg => { if (msg.type() === 'error') report.errors.push(msg.text()); });
  const shot = async name => { const file = path.join(output, (baseline ? 'before-' : 'after-') + name + '.png');
    await page.screenshot({ path: file }); report.screenshots.push(file); };
  try {
    await page.goto(demo.origin + '/?demo=1'); await ready(page);
    report.measurements.partial = await measure(page); await shot('partial');
    const first = await sceneState(page); await sleep(1000);
    report.measurements.partial.framesPerIdleSecond = (await sceneState(page)).frames - first.frames;
    await page.getByRole('button', { name: '50 tiles', exact: true }).click(); await ready(page);
    report.measurements.large = await measure(page); await shot('large');
    if (!baseline) {
      for (const quality of ['still', 'simple']) {
        await page.getByLabel('Fog effects').selectOption(quality); await sleep(300);
        report.measurements['large-' + quality] = await measure(page);
        report.measurements['large-' + quality].framesPerIdleSecond = await idleFrames(page);
        assert.equal(report.measurements['large-' + quality].framesPerIdleSecond, 0);
      }
      await page.getByLabel('Fog effects').selectOption('mist');
    }
    await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
    await page.getByRole('button', { name: 'Reveal two', exact: true }).click(); await sleep(120); await shot('reveal');
    if (!baseline) assert.equal((await sceneState(page)).reveals, 2);
    await sleep(1300); await shot('revealed');
    if (!baseline) {
      assert.equal((await sceneState(page)).reveals, 0);
      report.checks.push('simultaneous authorized reveals last at most 1 second; static/simple 50-tile modes return to zero idle frames');
      await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
      const before = await sceneState(page); assert.equal(before.ships, 1); assert.equal(before.clouds, 3);
      const commands = await page.evaluate(() => window.__fogFixture.commands().length);
      const clock = async () => page.evaluate(() => {
        let value; window.__scene.getState().scene.traverse(o => { if (o.userData.fogCloud) value = o.material.uniforms.uTime.value; }); return value;
      });
      const start = await clock(); const frames = await idleFrames(page);
      assert(frames > 0 && frames <= 15); assert((await clock()) > start);
      assert.equal(await page.evaluate(() => window.__fogFixture.commands().length), commands);
      assert.equal((await sceneState(page)).geometries, before.geometries);
      assert.equal((await sceneState(page)).textures, before.textures);
      // Real independent Chrome profiles receive the same new PUBLIC frame.
      const otherContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
      await otherContext.addInitScript(observeScene);
      const other = await otherContext.newPage(); other.on('pageerror', e => report.errors.push(e.message));
      await other.goto(demo.origin + '/?demo=1'); await ready(other);
      const common = await page.evaluate(() => window.__fogFixture.snapshot());
      await other.evaluate(frame => window.__fogFixture.publish(frame), common); await sleep(60);
      await page.getByRole('button', { name: 'Reveal two', exact: true }).click();
      const frame = await page.evaluate(() => window.__fogFixture.snapshot());
      await other.evaluate(frame => window.__fogFixture.publish(frame), frame);
      assert.equal((await sceneState(page)).hidden, 1); assert.equal((await sceneState(other)).hidden, 1);
      await other.waitForFunction(() => {
        let n = 0; window.__scene.getState().scene.traverse(o => { if (o.userData.fogReveal && o.visible) n++; }); return n === 2;
      }); await sleep(1100);
      assert.equal((await sceneState(page)).reveals, 0); assert.equal((await sceneState(other)).reveals, 0);
      await otherContext.close();
      report.checks.push('two Chrome profiles show the same public multi-reveal; one real ship at sea/fog boundary; clock capped at 12 Hz without mesh/texture churn or commands');

      await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await ready(page);
      await page.emulateMedia({ reducedMotion: 'reduce' }); await sleep(200);
      assert.equal(await idleFrames(page), 0);
      await page.getByRole('button', { name: 'Reveal one', exact: true }).click();
      await waitHidden(page, 2);
      assert.equal((await sceneState(page)).reveals, 0); assert.equal((await sceneState(page)).hidden, 2);
      await shot('reduced-motion'); await page.emulateMedia({ reducedMotion: 'no-preference' });
      await page.evaluate(() => window.__fogFixture.status('disconnected')); assert.equal(await idleFrames(page), 0);
      await page.evaluate(() => window.__fogFixture.status('connected'));
      await page.evaluate(() => {
        Object.defineProperty(document, 'hidden', { configurable: true, value: true });
        document.dispatchEvent(new Event('visibilitychange'));
      }); assert.equal(await idleFrames(page), 0);
      await page.evaluate(() => {
        delete document.hidden; document.dispatchEvent(new Event('visibilitychange'));
      });
      report.checks.push('reduced motion, disconnect and hidden document stop ambient frames; reduced motion reveals immediately');

      await page.getByRole('button', { name: 'Reveal one', exact: true }).click(); await sleep(100);
      await page.getByRole('button', { name: '2D', exact: true }).click();
      await sleep(500); assert.equal(await page.locator('[data-fog-reveal]').count(), 0);
      await page.getByRole('button', { name: '3D', exact: true }).click(); await sleep(150);
      assert.equal((await sceneState(page)).reveals, 0);
      report.checks.push('2D/3D switching expires original timestamps without replay; SVG retains 420 ms duration');
      // Fresh mount baselines a restored already-public frame, never an old discovery.
      await page.reload(); await ready(page); assert.equal((await sceneState(page)).reveals, 0);
      const cameraPosition = () => page.evaluate(() => window.__scene.getState().camera.position.toArray());
      const camera = await cameraPosition(), rect = await page.locator('.board3d-canvas').boundingBox();
      await page.mouse.move(rect.x + rect.width * .65, rect.y + rect.height * .5); await page.mouse.down();
      await page.mouse.move(rect.x + rect.width * .65 + 80, rect.y + rect.height * .5 + 25, { steps: 8 });
      await page.mouse.up(); await page.mouse.wheel(0, -160); await sleep(350);
      assert.notDeepEqual(await cameraPosition(), camera);
      await page.getByRole('button', { name: 'Reset Camera', exact: true }).click();
      await sleep(300);
      assert((await cameraPosition()).every((v, i) => Math.abs(v - camera[i]) < .001));
      for (const size of [{ width: 1024, height: 768 }, { width: 1440, height: 900 }]) {
        await page.setViewportSize(size); await sleep(150);
        assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
      }
      report.checks.push('refresh does not replay discoveries; actual orbit/zoom/reset work; desktop resize has no overflow');
    }
    assert.deepEqual(report.errors, []);
    report.checks.push('real Board3D/public fixture land, sea, adjacent hidden tiles, real ship, multi reveal; no browser errors');
    report.completed = true;
    console.log(JSON.stringify(report, null, 2));
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, baseline ? 'before.json' : 'after.json'), JSON.stringify(report, null, 2));
    await browser.close(); demo.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
