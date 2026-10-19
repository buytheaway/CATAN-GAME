// Controlled same-Chrome A/B against the exact published Phase 3 frontend.
// The public e2e fixture is shared; no checkout/reset or renderer probes.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, measure, idleFrames } = require('./ships-visual.cjs');
const { fullyReady, sceneSettings, aggregate } = require('./buildings-compare.cjs');

const reference = '93ee22574fd843e87e571e086367374851a47b12';
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-threats-visual-phase4'));
const order = ['before', 'after', 'after', 'before'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

async function selectIfPresent(page, label, value) {
  const control = page.getByLabel(label, { exact: true });
  if (await control.count()) await control.selectOption(value);
}

async function setMode(page, mode) {
  await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
  if (mode === 'static') {
    await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
    await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
    await selectIfPresent(page, 'Construction effects', 'static');
    // The checkpoint predates this presentation preference.
    await selectIfPresent(page, 'Robber & pirate effects', 'static');
  }
  await page.mouse.move(1, 1); await sleep(300);
}

function assertAmbient(frames, label) {
  assert(frames >= 9 && frames <= 15, `${label}: expected shared ~12 Hz idle clock, got ${frames} frames/s`);
}

async function activity(page) {
  return page.evaluate(() => {
    const { gl } = window.__scene.getState();
    return { commits: window.__sceneCommits, geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
  });
}

async function steadyIdle(page, label) {
  await page.mouse.move(1, 1); await sleep(300);
  const first = await activity(page), frames = await idleFrames(page), last = await activity(page);
  assert.equal(last.commits, first.commits, `${label}: idle must not commit React scene updates`);
  assert.equal(last.geometries, first.geometries, `${label}: idle geometry churn`);
  assert.equal(last.textures, first.textures, `${label}: idle texture churn`);
  return frames;
}

async function verifySharedIdle(page, origin) {
  await page.emulateMedia({ reducedMotion: 'no-preference' });
  await page.goto(origin + '/?demo=1&threats=1&fixture=partial'); await fullyReady(page);
  await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
  await selectIfPresent(page, 'Construction effects', 'static');
  await page.getByLabel('Robber & pirate effects', { exact: true }).selectOption('motion');
  const before = await steadyIdle(page, 'pirate alone before movement'); assertAmbient(before, 'pirate alone before movement');
  await page.evaluate(() => window.__fogFixture.threat('pirate', true));
  await sleep(2000);
  const after = await steadyIdle(page, 'pirate alone after finite movement/theft');
  assertAmbient(after, 'pirate alone after finite movement/theft');
  // Subscribing all three effects must share the existing clock, not multiply
  // the scene rate into 24/36 Hz. Measurements above use the same normal scene.
  await page.getByLabel('Fog effects', { exact: true }).selectOption('mist');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('motion');
  const combined = await steadyIdle(page, 'pirate + Fog + ships'); assertAmbient(combined, 'pirate + Fog + ships');
  await page.getByLabel('Robber & pirate effects', { exact: true }).selectOption('static');
  const existing = await steadyIdle(page, 'Fog + ships with threats still'); assertAmbient(existing, 'Fog + ships with threats still');
  await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
  assert.equal(await steadyIdle(page, 'all Still'), 0, 'finite threat effects must return to demand idle');
  await page.evaluate(() => window.__fogFixture.theft()); await sleep(2000);
  assert.equal(await steadyIdle(page, 'all Still after generic theft'), 0, 'static theft feedback must not start a clock');
  return { pirateOnlyBeforeFramesPerSecond: before, pirateOnlyAfterFramesPerSecond: after,
    pirateFogShipsFramesPerSecond: combined, fogShipsFramesPerSecond: existing,
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
      recording: 'no video encoding during any measurement',
      limitation: 'single desktop Chrome/GPU; timing variance does not establish an optimization or low-end/mobile performance' } };
  let before, after, browser;
  try {
    const repo = path.resolve(__dirname, '../..');
    assert.equal(execFileSync('git', ['rev-parse', reference], { cwd: repo, encoding: 'utf8' }).trim(), reference);
    // New fixture helpers stay outside web/src, so sourceRef loads only exact
    // checkpoint runtime modules while both sides receive identical public data.
    before = await startDemo(0, reference); after = await startDemo();
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.browser = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    await context.addInitScript(observeScene); const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
    for (const fixture of ['partial', 'large']) for (const mode of ['normal', 'reduced', 'static']) {
      const key = (fixture === 'large' ? '50' : '7') + '-' + mode;
      const readings = { before: [], after: [] }; let expected;
      // Exactly one active measured page/Canvas, with sequential navigation.
      for (const [index, side] of order.entries()) {
        await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
        await page.goto((side === 'before' ? before : after).origin + '/?demo=1&threats=1&fixture=' + fixture);
        await fullyReady(page); await setMode(page, mode);
        const settings = await sceneSettings(page);
        settings.scene.robbers = settings.publicState.robbers ?? [settings.publicState.robber_tile];
        settings.scene.pirateTile = settings.publicState.pirate_tile;
        const publicStateHash = hash(settings.publicState); delete settings.publicState;
        const signature = { publicStateHash, ...settings };
        if (expected) assert.deepEqual(signature, expected, `${key}: public contents/camera/DPR/shadows changed between readings`);
        else expected = signature;
        const result = await measure(page); result.idleFramesPerSecond = await idleFrames(page); result.orderIndex = index;
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
    report.sharedIdle = await verifySharedIdle(page, after.origin);
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'paired-performance.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close(); before?.server.close(); after?.server.close();
  }
}

if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { verifySharedIdle, steadyIdle };
