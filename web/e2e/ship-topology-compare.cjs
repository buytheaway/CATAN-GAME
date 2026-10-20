// Same corrected 5B.1 GPU probe, original versus corrected GLB only.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { createHash } = require('node:crypto');
const { execFileSync } = require('node:child_process');
const { chromium } = require('playwright');
const { startComparison, reference } = require('./ship-topology-demo.cjs');
const { orders, summarize, samplePage, telemetry, stats } = require('./ship-art-gpu.cjs');
const { observeScene, idleFrames } = require('./ships-visual.cjs');
const { fullyReady, sceneSettings } = require('./buildings-compare.cjs');
const { artReady, shipInfo, staticMode } = require('./ship-art-visual.cjs');
const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ship-topology-gpu-' + Date.now());
const hash = bytes => createHash('sha256').update(bytes).digest('hex');
async function main() {
  const coldOnly = process.argv.includes('--cold-only');
  await fs.mkdir(output, { recursive: true }); const file = path.join(output, coldOnly ? 'cold-load.json' : 'paired-performance.json');
  await fs.writeFile(file, '{}', { flag: 'wx' });
  const before = execFileSync('git', ['show', reference + ':web/public/models/pieces/ship-pilot.glb']);
  const after = await fs.readFile(path.join(__dirname, '../public/models/pieces/ship-pilot.glb'));
  const order = orders().map(block => block.map(side => side === 'procedural' ? 'original' : 'corrected'));
  const smoke = process.argv.includes('--smoke');
  const report = { completed: false, reference, checkedAt: new Date().toISOString(), smoke, coldOnly, errors: [],
    assets: { original: { bytes: before.length, sha256: hash(before) }, corrected: { bytes: after.length, sha256: hash(after) } },
    method: { order, warmFrames: smoke ? 5 : 90, gpuFrames: smoke ? 4 : 120, wallFrames: smoke ? 4 : 60,
      probe: 'unchanged samplePage from ship-art-gpu.cjs; asynchronous GPU timer/disjoint, separate wall, full chronological raw frames, main plus shadows',
      loading: 'fresh context/HTTP cache disabled for EACH reading; both sides use identical readiness, compileAsync and paced warm-up',
      serving: 'both original/corrected GLB buffers are preloaded before startup and served by the same response branch',
      runtime: 'same current real Board3D bundle; original serves only the fixed public GLB from Git; corrected serves working asset',
      screenshots: 'captured separately by ship-topology-visual; no screenshots/video during measurements',
      limits: 'unlocked power/clocks, ambient normal phases evolve, other user applications remain; command-span microbenchmark, not exclusive GPU or sustained FPS' },
    measurements: {}, environment: { start: telemetry() } };
  const save = () => fs.writeFile(file, JSON.stringify(report, null, 2));
  const demo = await startComparison(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  report.chrome = browser.version();
  try {
    for (const fixture of ['partial', 'large']) for (const mode of ['normal', 'reduced', 'static']) {
      if (coldOnly && mode !== 'normal') continue;
      if (smoke && (fixture !== 'partial' || mode !== 'static')) continue;
      const key = (fixture === 'partial' ? '7' : '50') + '-' + mode;
      const result = report.measurements[key] = { readings: [], blocks: [] };
      for (const [block, sequence] of order.entries()) for (const [index, side] of sequence.entries()) {
        const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
        try {
          await context.addInitScript(observeScene); const page = await context.newPage();
          page.on('pageerror', e => report.errors.push(e.message));
          page.on('console', m => { if (m.type() === 'error') report.errors.push(m.text()); });
          const cdp = await context.newCDPSession(page); await cdp.send('Network.enable');
          await cdp.send('Network.setCacheDisabled', { cacheDisabled: true });
          await page.emulateMedia({ reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
          await page.goto(demo[side].origin + '/?demo=1&shipsart=1&fixture=' + fixture); await fullyReady(page);
          if (mode === 'static') await staticMode(page);
          await page.mouse.move(1, 1);
          const started = await page.evaluate(() => performance.now());
          await page.getByLabel('Ship model', { exact: true }).selectOption('glb');
          await page.waitForFunction(() => { let count = 0; window.__scene.getState().scene.traverse(o => {
            if (o.userData.shipModel === 'glb') count++; }); return count > 0; }, null, { polling: 'raf' });
          const cold = await page.evaluate(start => ({ selectionToDetectedMs: performance.now() - start,
            resource: performance.getEntriesByType('resource').filter(r => r.name.endsWith('/ship-pilot.glb'))
              .map(r => ({ duration: r.duration, encodedBodySize: r.encodedBodySize, transferSize: r.transferSize })) }), started);
          await artReady(page);
          const settings = await sceneSettings(page); settings.publicStateHash = hash(JSON.stringify(settings.publicState)); delete settings.publicState;
          if (result.settings) assert.deepEqual(settings, result.settings); else result.settings = settings;
          const details = await shipInfo(page);
          const inventory = await page.evaluate(() => {
            const { gl, scene } = window.__scene.getState(), gpu = gl.getContext(), ext = gpu.getExtension('WEBGL_debug_renderer_info');
            const materials = new Set(), geometries = new Set(); scene.traverse(o => { if (o.isMesh) {
              geometries.add(o.geometry.uuid); for (const m of Array.isArray(o.material) ? o.material : [o.material]) materials.add(m.uuid);
            } }); return { materials: materials.size, sceneGeometries: geometries.size,
              renderer: ext ? gpu.getParameter(ext.UNMASKED_RENDERER_WEBGL) : null, programs: gl.info.programs.length };
          });
          if (coldOnly) {
            result.readings.push({ side, block, index, cold, inventory }); await save();
            assert.equal(cold.resource.length, 1); assert.equal(cold.resource[0].encodedBodySize, report.assets[side].bytes);
            continue;
          }
          const beforeTelemetry = telemetry(), sample = await page.evaluate(samplePage, report.method);
          result.readings.push({ side, block, index, cold, inventory,
            shipMaterials: details.ships[0].materials, shipTriangles: details.ships[0].triangles,
            beforeTelemetry, afterTelemetry: telemetry(), ...sample }); await save();
          assert(!sample.failure, sample.failure); assert.deepEqual(sample.before, sample.after);
          assert(sample.gpuSamples.some(s => !s.disjoint && Number.isFinite(s.gpuMs)));
          assert.equal(cold.resource.length, 1); assert.equal(cold.resource[0].encodedBodySize, report.assets[side].bytes);
          const idle = await idleFrames(page); result.readings.at(-1).idleFramesPerSecond = idle;
          assert(mode === 'normal' ? idle >= 9 && idle <= 15 : idle === 0);
          assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
        } finally { await context.close(); }
      }
      if (coldOnly) {
        for (const side of ['original', 'corrected']) {
          const samples = result.readings.filter(r => r.side === side);
          result[side] = { fetchMs: stats(samples.map(r => r.cold.resource[0].duration)),
            selectionToDetectedMs: stats(samples.map(r => r.cold.selectionToDetectedMs)) };
        }
        console.log(`${key}: normalized cold fetch median ${result.original.fetchMs.median.toFixed(2)} -> ${result.corrected.fetchMs.median.toFixed(2)} ms`);
        await save(); continue;
      }
      for (const side of ['original', 'corrected']) result[side] = summarize(result.readings.filter(r => r.side === side));
      for (const block of [0, 1]) {
        const sides = Object.fromEntries(['original', 'corrected'].map(side => [side, summarize(result.readings.filter(r => r.block === block && r.side === side))]));
        result.blocks.push({ block, original: sides.original.gpu.median, corrected: sides.corrected.gpu.median,
          deltaMs: sides.corrected.gpu.median - sides.original.gpu.median });
      }
      console.log(`${key}: GPU ${result.original.gpu.median.toFixed(3)} -> ${result.corrected.gpu.median.toFixed(3)}; p95 ${result.original.gpu.p95.toFixed(3)} -> ${result.corrected.gpu.p95.toFixed(3)}`); await save();
    }
    report.environment.end = telemetry(); assert.deepEqual(report.errors, []); report.completed = true;
  } catch (e) { report.failure = e.stack; throw e; }
  finally { await save(); await browser.close(); demo.close(); }
  console.log('REPORT ' + file);
}
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
