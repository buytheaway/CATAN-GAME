// Controlled same-Chrome A/B. The baseline reads exact committed UI blobs;
// neither checkout/reset nor production instrumentation is required.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, ready, measure, idleFrames } = require('./ships-visual.cjs');

const reference = 'f315519f0d06cf5bf131f9bc2247e82c1c3abc64';
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-buildings-visual-phase3'));
const order = ['before', 'after', 'after', 'before'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

async function fullyReady(page) {
  await ready(page);
  // Terrain and all three existing piece GLBs must be loaded on both sides.
  await page.waitForFunction(() => {
    let fallback = false;
    window.__scene.getState().scene.traverse(o => { fallback ||= !!o.userData.pieceFallback; });
    return !fallback;
  });
}

async function sceneSettings(page) {
  return page.evaluate(() => {
    const { gl, camera } = window.__scene.getState(), frame = window.__fogFixture.snapshot();
    const state = frame.state, canvas = gl.domElement, rect = canvas.getBoundingClientRect();
    return {
      // The fixture is synthetic/public. Compare its complete state so both
      // implementations render identical occupancy, Fog, targets and labels.
      publicState: state,
      scene: { tiles: state.tiles.length, hiddenTiles: state.tiles.filter(t => t.visibility === 'hidden').length,
        roads: Object.keys(state.occupied_e).length, ships: Object.keys(state.occupied_ships).length,
        settlements: Object.values(state.occupied_v).filter(v => v[1] === 1).length,
        cities: Object.values(state.occupied_v).filter(v => v[1] === 2).length },
      camera: { position: camera.position.toArray(), quaternion: camera.quaternion.toArray(),
        projection: camera.projectionMatrix.toArray(), near: camera.near, far: camera.far, fov: camera.fov },
      devicePixelRatio: window.devicePixelRatio, renderPixelRatio: gl.getPixelRatio(),
      canvas: [canvas.width, canvas.height], cssCanvas: [rect.width, rect.height],
      shadows: { enabled: gl.shadowMap.enabled, type: gl.shadowMap.type },
    };
  });
}

async function setMode(page, mode) {
  await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
  if (mode === 'static') {
    await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
    await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
    const construction = page.getByLabel('Construction effects', { exact: true });
    // The checkpoint predates this presentation preference.
    if (await construction.count()) await construction.selectOption('static');
  }
  await page.mouse.move(1, 1);
  await sleep(300);
}

function assertAmbient(frames, label) {
  assert(frames >= 9 && frames <= 15, `${label}: expected shared ~12 Hz idle clock, got ${frames} frames/s`);
}

function aggregate(samples) {
  const first = samples[0];
  return {
    samples,
    gpuMedianMs: samples.reduce((sum, value) => sum + value.gpuMedianMs, 0) / samples.length,
    gpuP95Ms: Math.max(...samples.map(value => value.gpuP95Ms)),
    cpuSubmitMedianMs: samples.reduce((sum, value) => sum + value.cpuSubmitMedianMs, 0) / samples.length,
    cpuSubmitP95Ms: Math.max(...samples.map(value => value.cpuSubmitP95Ms)),
    calls: first.calls, triangles: first.triangles, geometries: first.geometries, textures: first.textures,
  };
}

async function activity(page) {
  return page.evaluate(() => {
    const { gl } = window.__scene.getState();
    return { frames: gl.info.render.frame, commits: window.__sceneCommits,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
  });
}

async function verifyFiniteIdle(page, origin) {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto(origin + '/?demo=1&buildings=1&fixture=partial');
  await fullyReady(page);
  await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('motion');
  const before = await idleFrames(page); assertAmbient(before, 'ships alone before construction');
  await page.evaluate(() => window.__fogFixture.building('settlement'));
  await sleep(2000);
  const first = await activity(page), after = await idleFrames(page), last = await activity(page);
  assertAmbient(after, 'ships alone after finite construction');
  assert.equal(last.commits, first.commits, 'settled ship-only idle must not commit React scene updates');
  assert.equal(last.geometries, first.geometries, 'settled construction must not allocate idle geometries');
  assert.equal(last.textures, first.textures, 'settled construction must not allocate idle textures');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
  assert.equal(await idleFrames(page), 0, 'finite building feedback must return to demand idle with ambient effects still');
  return { shipOnlyBeforeFramesPerSecond: before, shipOnlyAfterFramesPerSecond: after,
    allStillFramesPerSecond: 0, noSceneCommitsOrResourceChurn: true };
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const report = { completed: false, reference,
    checkedAt: new Date().toISOString(), browser: null, measurements: {}, screenshots: [], errors: [],
    method: { order, viewport: [1440, 900], deviceScaleFactor: 1, warmRenders: 12,
      gpuSynchronousSamples: 60, cpuSubmissionSamples: 30,
      gpuTiming: 'gl.render(scene, camera) + WebGL finish; diagnostic samples, not sustained FPS',
      aggregation: 'mean of two medians; p95 is worse of the two runs',
      cpuLimit: 'WebGL submission includes driver/GPU stalls; not isolated CPU frame time',
      baseline: 'git show exact checkpoint web/src blobs into temporary esbuild bundle; current public e2e fixture shared',
      recording: 'no video encoding during any measurement' } };
  let before, after, browser;
  try {
    const repo = path.resolve(__dirname, '../..');
    assert.equal(execFileSync('git', ['rev-parse', reference], { cwd: repo, encoding: 'utf8' }).trim(), reference);
    // Bundles are independent; the same current e2e fixture is intentionally
    // outside the web/src sourceRef plugin and imports no new runtime module.
    before = await startDemo(0, reference); after = await startDemo();
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    report.browser = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    await context.addInitScript(observeScene);
    const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
    for (const fixture of ['partial', 'large']) for (const mode of ['normal', 'reduced', 'static']) {
      const key = (fixture === 'large' ? '50' : '7') + '-' + mode;
      const readings = { before: [], after: [] };
      let expected;
      // Sequential navigation leaves exactly one active measured page/Canvas.
      for (const [index, side] of order.entries()) {
        await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
        await page.goto((side === 'before' ? before : after).origin + '/?demo=1&buildings=1&fixture=' + fixture);
        await fullyReady(page); await setMode(page, mode);
        const settings = await sceneSettings(page);
        const publicStateHash = hash(settings.publicState); delete settings.publicState;
        const signature = { publicStateHash, ...settings };
        if (expected) assert.deepEqual(signature, expected, `${key}: public contents/camera/DPR/shadows changed between readings`);
        else expected = signature;
        const result = await measure(page);
        result.idleFramesPerSecond = await idleFrames(page);
        result.orderIndex = index;
        if (mode === 'normal') assertAmbient(result.idleFramesPerSecond, `${key} ${side}`);
        else assert.equal(result.idleFramesPerSecond, 0, `${key} ${side}: expected demand idle`);
        readings[side].push(result);
        if (readings[side].length === 1) {
          const file = path.join(output, `${side}-${key}.png`);
          await page.screenshot({ path: file }); report.screenshots.push(file);
        }
      }
      for (const metric of ['calls', 'triangles', 'geometries', 'textures', 'gpu', 'ships']) {
        const samples = [...readings.before, ...readings.after];
        for (const sample of samples) assert.equal(sample[metric], samples[0][metric], `${key}: steady ${metric} differs`);
      }
      for (const sample of [...readings.before, ...readings.after]) assert.deepEqual(sample.viewport, expected.canvas);
      report.measurements[key] = { before: aggregate(readings.before), after: aggregate(readings.after), settings: expected };
      console.log(`${key}: GPU median before/after ${report.measurements[key].before.gpuMedianMs.toFixed(2)}/${report.measurements[key].after.gpuMedianMs.toFixed(2)} ms`);
    }
    report.finiteIdle = await verifyFiniteIdle(page, after.origin);
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'paired-performance.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close();
    before?.server.close(); after?.server.close();
  }
}

if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { fullyReady, sceneSettings, aggregate };
