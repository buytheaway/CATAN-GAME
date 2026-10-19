// Benchmark-only correction for the 5A render+finish wall-time / missing raw samples.
// Production renderer, assets and animation implementations remain untouched.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');

const reference = '5a3902cd22e080c14d4b6b43c415ed8026297118';
function orders() {
  return [['procedural', 'glb', 'glb', 'procedural'], ['glb', 'procedural', 'procedural', 'glb']];
}
function stats(values) {
  assert(values.length && values.every(value => Number.isFinite(value) && value >= 0));
  const sorted = [...values].sort((a, b) => a - b);
  const quantile = p => sorted[Math.max(0, Math.ceil(sorted.length * p) - 1)];
  return { count: sorted.length, median: quantile(.5), p95: quantile(.95), min: sorted[0], max: sorted.at(-1) };
}
function summarize(readings) {
  const gpu = readings.flatMap(reading => reading.gpuSamples);
  const valid = gpu.filter(sample => !sample.disjoint && Number.isFinite(sample.gpuMs));
  const wall = readings.flatMap(reading => reading.wallSamples);
  return { gpu: valid.length ? stats(valid.map(sample => sample.gpuMs)) : null,
    invalidGpuSamples: gpu.length - valid.length, gpuSamples: gpu.length,
    submit: valid.length ? stats(valid.map(sample => sample.submitMs)) : null, wall: stats(wall.map(sample => sample.wallMs)),
    readingGpuMedians: readings.map(reading => {
      const values = reading.gpuSamples.filter(sample => !sample.disjoint && Number.isFinite(sample.gpuMs)).map(sample => sample.gpuMs);
      return values.length ? stats(values).median : null;
    }),
    calls: [...new Set(gpu.map(sample => sample.calls))], triangles: [...new Set(gpu.map(sample => sample.triangles))] };
}
function telemetry() {
  try {
    return { at: new Date().toISOString(), csv: execFileSync('nvidia-smi', [
      '--query-gpu=name,driver_version,pstate,temperature.gpu,power.draw,clocks.current.graphics,clocks.current.memory,utilization.gpu',
      '--format=csv,noheader'], { encoding: 'utf8', timeout: 5000 }).trim() };
  } catch (error) { return { at: new Date().toISOString(), unavailable: error.message }; }
}

// Executes only in the page: all temporal samples are retained in chronological order.
async function samplePage({ warmFrames, gpuFrames, wallFrames }) {
  const store = window.__scene, state = store.getState(), { gl, scene, camera } = state;
  const gpu = gl.getContext(), ext = gpu.getExtension('EXT_disjoint_timer_query_webgl2');
  if (!ext) throw Error('GPU timer unavailable; cannot label CPU wall timing as GPU timing');
  const frame = () => new Promise(requestAnimationFrame);
  const pause = () => new Promise(resolve => setTimeout(resolve, 0));
  const clock = performance.now();
  const resources = () => ({ programs: gl.info.programs.length, geometries: gl.info.memory.geometries, textures: gl.info.memory.textures });
  const result = { visibility: document.visibilityState, initial: resources(), warm: [], gpuSamples: [], wallSamples: [] };
  if (document.hidden) throw Error('Benchmark page is not visible');
  // Pause automatic R3F drawing only inside this external probe. SceneMotion and
  // its normal ship/Fog listeners still run; settled fixtures have no finite cues.
  const previousLoop = state.frameloop, previousAutoReset = gl.info.autoReset;
  state.setFrameloop('never');
  gl.info.autoReset = false; // explicit reset before each draw includes shadow + main passes
  try {
    const compileStart = performance.now(); await gl.compileAsync(scene, camera);
    result.compileAsyncMs = performance.now() - compileStart;
    for (let i = 0; i < warmFrames; i++) {
      await frame(); gpu.finish();
      gl.info.reset(); const start = performance.now(); gl.render(scene, camera); gpu.finish();
      result.warm.push({ index: i, at: start - clock, wallMs: performance.now() - start, programs: gl.info.programs.length });
    }
    result.before = resources();
    gpu.getParameter(ext.GPU_DISJOINT_EXT); // clear any historical disjoint status
    for (let i = 0; i < gpuFrames; i++) {
      await frame();
      const query = gpu.createQuery(), start = performance.now();
      let disjoint = false;
      try {
        gl.info.reset(); gpu.beginQuery(ext.TIME_ELAPSED_EXT, query);
        const submitStart = performance.now(); gl.render(scene, camera);
        const submitMs = performance.now() - submitStart;
        gpu.endQuery(ext.TIME_ELAPSED_EXT); gpu.flush();
        const calls = gl.info.render.calls, triangles = gl.info.render.triangles;
        while (!gpu.getQueryParameter(query, gpu.QUERY_RESULT_AVAILABLE)) {
          disjoint ||= gpu.getParameter(ext.GPU_DISJOINT_EXT);
          if (performance.now() - start > 5000) throw Error('GPU query timed out');
          await pause();
        }
        disjoint ||= gpu.getParameter(ext.GPU_DISJOINT_EXT);
        result.gpuSamples.push({ index: i, at: start - clock, disjoint,
          gpuMs: disjoint ? null : gpu.getQueryParameter(query, gpu.QUERY_RESULT) / 1e6,
          submitMs, queryReadyMs: performance.now() - start, calls, triangles });
      } finally { gpu.deleteQuery(query); }
    }
    // Separate CPU+driver synchronized wall-time diagnostic; drain queued work
    // OUTSIDE the measured span so a previous demand frame is not charged to it.
    for (let i = 0; i < wallFrames; i++) {
      await frame(); gpu.finish();
      gl.info.reset(); const start = performance.now(); gl.render(scene, camera); gpu.finish();
      result.wallSamples.push({ index: i, at: start - clock, wallMs: performance.now() - start });
    }
    result.after = resources(); result.durationMs = performance.now() - clock;
    if (document.hidden) throw Error('Benchmark page lost visibility');
    return result;
  } catch (error) {
    result.failure = error.stack; return result; // preserve partial timings on failure
  } finally { gl.info.autoReset = previousAutoReset; state.setFrameloop(previousLoop); state.invalidate(); }
}

async function main() {
  // Keep stats unit tests independent of the external browser tooling install.
  const { chromium } = require('playwright');
  const { startDemo } = require('./fog-visual-demo.cjs');
  const { observeScene, idleFrames } = require('./ships-visual.cjs');
  const { fullyReady, sceneSettings } = require('./buildings-compare.cjs');
  const { artReady, shipInfo, staticMode } = require('./ship-art-visual.cjs');
  const smoke = process.argv.includes('--smoke');
  const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ship-gpu-' + Date.now()));
  await fs.mkdir(output, { recursive: true });
  const reportPath = path.join(output, 'gpu-investigation.json');
  await fs.writeFile(reportPath, '{}', { flag: 'wx' }); // never overwrite a previous run
  const report = { completed: false, smoke, reference, checkedAt: new Date().toISOString(), errors: [],
    method: { order: orders(), warmFrames: smoke ? 5 : 90, gpuFrames: smoke ? 4 : 120, wallFrames: smoke ? 4 : 60,
      GPU: 'EXT_disjoint_timer_query_webgl2 TIME_ELAPSED_EXT nanoseconds; async availability/disjoint checks',
      wall: 'separate paced render+finish wall time with prior work drained outside span; not GPU time',
      pacing: 'one measured render per requestAnimationFrame; automatic R3F draws paused only in probe; existing ambient listeners continue',
      counters: 'info.autoReset=false with reset before render; counts include main AND shadow passes',
      cold: 'new page/context JS template cache; HTTP cache disabled; browser/driver shader cache NOT forcibly cleared; detection includes UI automation and may follow first draw; remaining compile wait is not isolated shader compilation cost',
      warm: 'compileAsync then equal paced warm frames before EVERY reading; both models preloaded once per case',
      summary: 'nearest-rank pooled median/p95; all frame data and per-reading/block comparisons retained',
      limits: 'one GPU; no clock/power lock; other user applications are not stopped; neither sustained FPS nor artistic approval' },
    measurements: {}, cold: [], screenshots: [], environment: { start: telemetry() } };
  let demo, browser;
  const save = () => fs.writeFile(reportPath, JSON.stringify(report, null, 2));
  try {
    assert.equal(execFileSync('git', ['rev-parse', reference], { encoding: 'utf8' }).trim(), reference);
    report.checkoutHead = execFileSync('git', ['rev-parse', 'HEAD'], { encoding: 'utf8' }).trim();
    report.runnerSha256 = createHash('sha256').update(await fs.readFile(__filename)).digest('hex');
    const asset = await fs.readFile(path.join(__dirname, '../public/models/pieces/ship-pilot.glb'));
    report.asset = { bytes: asset.length, sha256: createHash('sha256').update(asset).digest('hex') };
    assert.equal(report.asset.sha256, '07f4fe56c41de24d85f332ab5f7dafbeec176767f51df137a2c2a72d20e911f9');
    demo = await startDemo(0, reference);
    browser = await chromium.launch({ channel: 'chrome', headless: true });
    report.browser = browser.version();
    for (const fixture of ['partial', 'large']) for (const mode of ['normal', 'reduced', 'static']) {
      if (smoke && (fixture !== 'partial' || mode !== 'static')) continue;
      const key = (fixture === 'partial' ? '7' : '50') + '-' + mode;
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
      try {
        await context.addInitScript(observeScene);
        const page = await context.newPage(), cdp = await context.newCDPSession(page);
        await cdp.send('Network.enable'); await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
        page.on('pageerror', error => report.errors.push(error.message));
        page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
        await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
        await page.goto(demo.origin + '/?demo=1&shipsart=1&fixture=' + fixture); await fullyReady(page);
        if (mode === 'static') await staticMode(page);
        await page.mouse.move(1, 1);
        assert.equal(await page.getByLabel('Ship model', { exact: true }).inputValue(), 'procedural');
        const coldBefore = await page.evaluate(() => {
          const { gl } = window.__scene.getState(); return { start: performance.now(), programs: gl.info.programs.length,
            requests: performance.getEntriesByType('resource').filter(r => r.name.endsWith('/ship-pilot.glb')).length };
        });
        assert.equal(coldBefore.requests, 0);
        await page.getByLabel('Ship model', { exact: true }).selectOption('glb');
        await page.waitForFunction(() => {
          let glb = 0, ships = 0, fallback = false;
          window.__scene.getState().scene.traverse(o => {
            if (o.userData.piece === 'ship' && !o.userData.preview) ships++;
            if (o.userData.shipModel === 'glb') glb++;
            fallback ||= !!o.userData.shipAssetFallback;
          }); return ships > 0 && glb >= ships && !fallback;
        }, null, { polling: 'raf' });
        const cold = await page.evaluate(async before => {
          const { gl, scene, camera } = window.__scene.getState();
          const visibleAt = performance.now(), firstStart = performance.now(); gl.render(scene, camera); gl.getContext().finish();
          const firstRenderWallMs = performance.now() - firstStart, compileStart = performance.now();
          await gl.compileAsync(scene, camera);
          return { selectionToDetectedMs: visibleAt - before.start, firstObservedRenderFinishMs: firstRenderWallMs,
            compileAsyncAfterDetectionMs: performance.now() - compileStart, programsBefore: before.programs,
            programsAfter: gl.info.programs.length, resources: performance.getEntriesByType('resource')
              .filter(r => r.name.endsWith('/ship-pilot.glb')).map(r => ({ startTime: r.startTime, duration: r.duration,
                requestStart: r.requestStart, responseStart: r.responseStart, responseEnd: r.responseEnd,
                encodedBodySize: r.encodedBodySize, decodedBodySize: r.decodedBodySize, transferSize: r.transferSize })) };
        }, coldBefore);
        report.cold.push({ key, ...cold }); assert.equal(cold.resources.length, 1);
        await artReady(page);
        const signature = await sceneSettings(page);
        signature.publicStateHash = createHash('sha256').update(JSON.stringify(signature.publicState)).digest('hex');
        delete signature.publicState;
        const gpu = await page.evaluate(() => {
          const g = window.__scene.getState().gl.getContext(), d = g.getExtension('WEBGL_debug_renderer_info');
          const ext = g.getExtension('EXT_disjoint_timer_query_webgl2');
          return { renderer: d ? g.getParameter(d.UNMASKED_RENDERER_WEBGL) : null,
            timer: !!ext, queryBits: ext ? g.getQuery(ext.TIME_ELAPSED_EXT, ext.QUERY_COUNTER_BITS_EXT) : 0 };
        });
        assert(gpu.timer && gpu.queryBits > 0);
        const result = report.measurements[key] = { settings: signature, gpu, readings: [], blocks: [] };
        for (const [block, order] of orders().entries()) for (const [index, model] of order.entries()) {
          await page.getByLabel('Ship model', { exact: true }).selectOption(model);
          await page.waitForFunction(model => {
            let found = 0, wrong = false;
            window.__scene.getState().scene.traverse(o => { if (o.userData.shipModel) {
              found++; wrong ||= o.userData.shipModel !== model || !!o.userData.shipAssetFallback;
            } }); return found > 0 && !wrong;
          }, model, { polling: 'raf' });
          const beforeSettings = await sceneSettings(page);
          beforeSettings.publicStateHash = createHash('sha256').update(JSON.stringify(beforeSettings.publicState)).digest('hex');
          delete beforeSettings.publicState; assert.deepEqual(beforeSettings, signature);
          const info = await shipInfo(page), beforeTelemetry = telemetry();
          const sample = await page.evaluate(samplePage, report.method);
          const reading = { block, index, model, at: new Date().toISOString(), beforeTelemetry, afterTelemetry: telemetry(),
            pose: info.ships.map(s => ({ edge: s.edge, owner: s.owner, position: s.position, yaw: s.yaw, pose: s.pose })),
            ...sample };
          result.readings.push(reading);
          await save(); // preserve even a reading that fails a subsequent invariant
          assert(!sample.failure, sample.failure);
          assert(sample.gpuSamples.some(s => !s.disjoint && Number.isFinite(s.gpuMs)), 'No valid GPU query in this reading; raw invalid evidence retained');
          assert.deepEqual(sample.after, sample.before, 'steady sampling must not compile programs or allocate resources');
          // Expected differences are ship bodies only; every frame is retained, including invalid timers.
          assert.equal(new Set(sample.gpuSamples.map(s => s.calls)).size, 1);
          assert.equal(new Set(sample.gpuSamples.map(s => s.triangles)).size, 1);
          await save();
        }
        for (const model of ['procedural', 'glb']) result[model] = summarize(result.readings.filter(r => r.model === model));
        for (const block of [0, 1]) {
          const sides = Object.fromEntries(['procedural', 'glb'].map(model => [model,
            summarize(result.readings.filter(r => r.block === block && r.model === model))]));
          result.blocks.push({ block, proceduralGpuMedian: sides.procedural.gpu.median, glbGpuMedian: sides.glb.gpu.median,
            differenceMs: sides.glb.gpu.median - sides.procedural.gpu.median });
        }
        result.idleFramesPerSecond = await idleFrames(page);
        assert(mode === 'normal' ? result.idleFramesPerSecond >= 9 && result.idleFramesPerSecond <= 15 : result.idleFramesPerSecond === 0);
        result.assetRequestsAfterSwitches = await page.evaluate(() => performance.getEntriesByType('resource').filter(r => r.name.endsWith('/ship-pilot.glb')).length);
        assert.equal(result.assetRequestsAfterSwitches, 1);
        assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
        for (const model of ['procedural', 'glb']) {
          await page.getByLabel('Ship model', { exact: true }).selectOption(model);
          if (model === 'glb') await artReady(page);
          const file = path.join(output, `${key}-${model}.png`);
          await page.screenshot({ path: file }); report.screenshots.push(file);
        }
        if (fixture === 'partial' && mode === 'normal') {
          const rect = await page.locator('canvas').boundingBox(); await page.mouse.move(rect.x + rect.width * .65, rect.y + rect.height * .5);
          await page.mouse.wheel(0, -500); await page.waitForTimeout(400);
          const file = path.join(output, '7-glb-close.png'); await page.screenshot({ path: file }); report.screenshots.push(file);
        }
        console.log(`${key}: GPU ${result.procedural.gpu.median.toFixed(3)} -> ${result.glb.gpu.median.toFixed(3)} ms; p95 ${result.procedural.gpu.p95.toFixed(3)} -> ${result.glb.gpu.p95.toFixed(3)}; invalid ${result.procedural.invalidGpuSamples}/${result.glb.invalidGpuSamples}`);
        await save();
      } finally { await context.close(); }
    }
    report.environment.end = telemetry(); assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally { await save(); if (browser) await browser.close(); if (demo) await new Promise(resolve => demo.server.close(resolve)); }
  console.log('REPORT ' + reportPath);
}
module.exports = { orders, stats, summarize, samplePage };
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
