// Paired same-browser A/B, using committed UI blobs without touching the working tree.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, ready, measure, idleFrames } = require('./ships-visual.cjs');
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ships-visual-phase2'));
const reference = '608f14ed349f237a1ae51873864246fff40f9d6f';
(async () => {
  await fs.mkdir(output, { recursive: true });
  const before = await startDemo(0, reference), after = await startDemo();
  const browser = await chromium.launch({ channel: 'chrome', headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  await context.addInitScript(observeScene); const page = await context.newPage();
  const report = { completed: false, reference, browser: browser.version(), measurements: {}, errors: [] };
  page.on('pageerror', e => report.errors.push(e.message));
  try {
    for (const large of [false, true]) for (const reduced of [false, true]) {
      const key = (large ? '50' : '7') + (reduced ? '-reduced' : '-normal');
      const readings = { before: [], after: [] };
      await page.emulateMedia({ reducedMotion: reduced ? 'reduce' : 'no-preference' });
      for (const side of ['before', 'after', 'after', 'before']) {
        await page.goto((side === 'before' ? before : after).origin + '/?demo=1&ships=1&fixture=' + (large ? 'large' : 'partial'));
        await ready(page); const result = await measure(page);
        result.idleFramesPerSecond = await idleFrames(page); readings[side].push(result);
        if (reduced) assert.equal(result.idleFramesPerSecond, 0);
      }
      for (const side of ['before', 'after']) {
        const values = readings[side]; readings[side] = { samples: values,
          gpuMedianMs: values.reduce((sum, value) => sum + value.gpuMedianMs, 0) / values.length,
          gpuP95Ms: Math.max(...values.map(v => v.gpuP95Ms)),
          cpuSubmitMedianMs: values.reduce((sum, value) => sum + value.cpuSubmitMedianMs, 0) / values.length,
          calls: values[0].calls, triangles: values[0].triangles,
          geometries: values[0].geometries, textures: values[0].textures };
      }
      assert.equal(readings.before.calls, readings.after.calls); assert.equal(readings.before.triangles, readings.after.triangles);
      assert.deepEqual(readings.before.samples[0].viewport, readings.after.samples[0].viewport);
      assert.equal(readings.before.samples[0].gpu, readings.after.samples[0].gpu);
      report.measurements[key] = readings;
      console.log(key + ' GPU ms before/after ' + readings.before.gpuMedianMs.toFixed(2) + '/' + readings.after.gpuMedianMs.toFixed(2));
    }
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'paired-performance.json'), JSON.stringify(report, null, 2));
    await browser.close(); before.server.close(); after.server.close();
  }
})().catch(error => { console.error(error); process.exitCode = 1; });
