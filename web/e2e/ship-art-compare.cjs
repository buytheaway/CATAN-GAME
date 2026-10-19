// Paired checkpoint/prototype comparison without checkout, renderer probes or video.
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
const { artReady, shipInfo, staticMode } = require('./ship-art-visual.cjs');
const reference = '2d93c40caed5c5febfc88f49e1234fb7853d2db1';
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ship-art-pilot'));
const order = ['before', 'after', 'after', 'before'];
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const hash = value => createHash('sha256').update(JSON.stringify(value)).digest('hex');

async function mode(page, value) {
  await page.emulateMedia({ reducedMotion: value === 'reduced' ? 'reduce' : 'no-preference' });
  if (value === 'static') await staticMode(page);
  await page.mouse.move(1, 1); await sleep(300);
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const report = { completed: false, reference, checkedAt: new Date().toISOString(), browser: null,
    measurements: {}, screenshots: [], errors: [],
    method: { order, viewport: [1440, 900], deviceScaleFactor: 1, warmRenders: 12,
      gpuSynchronousSamples: 60, cpuSubmissionSamples: 30,
      gpuTiming: 'gl.render(scene, camera) + WebGL finish; diagnostic samples, not sustained FPS',
      aggregation: 'mean of two medians; p95 is worse of two runs; preserve all raw samples',
      cpuLimit: 'WebGL submission includes GPU/driver stalls and is not isolated CPU frame time',
      baseline: 'exact checkpoint web/src git blobs; identical current public e2e fixture shared outside web/src',
      asset: 'after explicitly selects GLB; before uses checkpoint procedural body; asset transfer excludes JS test bundles',
      recording: 'no recording during measurement',
      limitation: 'one desktop GPU; differences/noise do not prove improvement or mobile performance' } };
  let before, after, browser;
  try {
    assert.equal(execFileSync('git', ['rev-parse', reference], { encoding: 'utf8' }).trim(), reference);
    before = await startDemo(0, reference); after = await startDemo();
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.browser = browser.version();
    const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
    await context.addInitScript(observeScene); const page = await context.newPage();
    page.on('pageerror', error => report.errors.push(error.message));
    page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
    for (const fixture of ['partial', 'large']) for (const value of ['normal', 'reduced', 'static']) {
      const key = (fixture === 'partial' ? '7' : '50') + '-' + value;
      const readings = { before: [], after: [] }; let expected;
      for (const [orderIndex, side] of order.entries()) {
        await page.emulateMedia({ reducedMotion: value === 'reduced' ? 'reduce' : 'no-preference' });
        await page.goto((side === 'before' ? before : after).origin + '/?demo=1&shipsart=1&fixture=' + fixture);
        await fullyReady(page);
        if (side === 'after') { await page.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(page); }
        await mode(page, value);
        const settings = await sceneSettings(page), publicStateHash = hash(settings.publicState); delete settings.publicState;
        const signature = { publicStateHash, ...settings };
        if (expected) assert.deepEqual(signature, expected, `${key}: fixture/camera/DPR/shadows changed`); else expected = signature;
        const info = await shipInfo(page), result = await measure(page);
        result.idleFramesPerSecond = await idleFrames(page); result.orderIndex = orderIndex;
        result.shipBodyTriangles = info.ships.map(ship => ship.triangles);
        result.shipBodyMeshes = info.ships.map(ship => ship.meshes);
        result.assetTransfer = await page.evaluate(() => performance.getEntriesByType('resource')
          .filter(entry => entry.name.endsWith('/models/pieces/ship-pilot.glb'))
          .map(entry => ({ encodedBodySize: entry.encodedBodySize, decodedBodySize: entry.decodedBodySize, transferSize: entry.transferSize })));
        if (side === 'before') assert.deepEqual(result.assetTransfer, []);
        else { assert.equal(result.assetTransfer.length, 1); assert(result.assetTransfer[0].decodedBodySize > 0); }
        if (value === 'normal') assert(result.idleFramesPerSecond >= 9 && result.idleFramesPerSecond <= 15, `${key} ${side}: shared clock`);
        else assert.equal(result.idleFramesPerSecond, 0, `${key} ${side}: demand idle`);
        readings[side].push(result);
        if (readings[side].length === 1) {
          const file = path.join(output, `${side}-${key}.png`); await page.screenshot({ path: file }); report.screenshots.push(file);
        }
      }
      for (const side of ['before', 'after']) for (const metric of ['calls', 'triangles', 'geometries', 'textures', 'ships', 'gpu']) {
        for (const sample of readings[side]) assert.equal(sample[metric], readings[side][0][metric], `${key}: ${side} ${metric} is unstable`);
      }
      for (const sample of [...readings.before, ...readings.after]) {
        assert.equal(sample.gpu, readings.before[0].gpu); assert.equal(sample.ships, readings.before[0].ships);
        assert.deepEqual(sample.viewport, expected.canvas);
      }
      const a = aggregate(readings.before), b = aggregate(readings.after);
      report.measurements[key] = { before: a, after: b, settings: expected,
        delta: { calls: b.calls - a.calls, triangles: b.triangles - a.triangles,
          geometries: b.geometries - a.geometries, textures: b.textures - a.textures } };
      console.log(`${key}: GPU median ${a.gpuMedianMs.toFixed(2)} -> ${b.gpuMedianMs.toFixed(2)} ms; calls ${a.calls} -> ${b.calls}; triangles ${a.triangles} -> ${b.triangles}`);
    }
    await page.goto(after.origin + '/?demo=1&shipsart=1'); await fullyReady(page);
    await page.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(page);
    await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
    const first = await shipInfo(page), beforeFrames = await idleFrames(page), last = await shipInfo(page);
    assert.equal(last.commits, first.commits); assert.equal(last.geometries, first.geometries); assert.equal(last.textures, first.textures);
    await page.evaluate(() => window.__fogFixture.ship(true)); await sleep(1800);
    const afterFrames = await idleFrames(page); assert(beforeFrames >= 9 && beforeFrames <= 15); assert(afterFrames >= 9 && afterFrames <= 15);
    await staticMode(page); assert.equal(await idleFrames(page), 0);
    report.idle = { shipOnlyBeforeFramesPerSecond: beforeFrames, shipOnlyAfterFiniteMoveFramesPerSecond: afterFrames,
      allStillFramesPerSecond: 0, noIdleReactCommitsOrGeometryTextureChurn: true };
    const asset = await fs.readFile(path.resolve(__dirname, '../public/models/pieces/ship-pilot.glb'));
    report.asset = { path: 'web/public/models/pieces/ship-pilot.glb', bytes: asset.length,
      additionalTexturesBytes: 0, assetSha256: createHash('sha256').update(asset).digest('hex') };
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'paired-performance.json'), JSON.stringify(report, null, 2));
    if (browser) await browser.close(); before?.server.close(); after?.server.close();
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
