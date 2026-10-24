const assert = require('node:assert/strict'), fs = require('node:fs/promises'), path = require('node:path');
const { chromium } = require('playwright');
const { startWater, reference } = require('./water-demo.cjs');
const { inventory } = require('./water-inventory.cjs');
const h = require('./ocean-support.cjs');
async function ready(page) {
  await page.waitForFunction(() => window.__waterPreview?.ready || window.__waterPreview?.error);
  assert.equal(await page.evaluate(() => window.__waterPreview.error), undefined); await h.ready(page);
}
async function focus(page, role) {
  if (role === 'corner') return h.frameCorner(page);
  return page.evaluate(role => {
    const { scene, camera, gl } = window.__scene.getState(), rect = gl.domElement.getBoundingClientRect(), candidates = [];
    scene.traverse(n => {
      const d = n.userData;
      if ((role === 'coast' && d.coastEdge) || (role === 'port' && d.portReadout)
        || (role === 'sea' && d.terrain === 'sea' && d.visibility === 'revealed')
        || (role === 'pirate' && d.piece === 'pirate')) {
        const world = n.getWorldPosition(n.position.clone()); world.y += .2;
        const p = world.clone().project(camera);
        if (Math.abs(p.x) < .85 && Math.abs(p.y) < .8) candidates.push({
          x: rect.x + (p.x + 1) * rect.width / 2, y: rect.y + (1 - p.y) * rect.height / 2,
          world: world.toArray(), score: Math.abs(p.x) + Math.abs(p.y) });
      }
    });
    return candidates.sort((a, b) => a.score - b.score)[0] || null;
  }, role);
}
async function main() {
  const baseline = process.argv.includes('--baseline'), demo = await startWater(); let browser;
  const report = { completed: false, reference, checkedAt: new Date().toISOString(), bundleHashes: demo.bundleHashes,
    captures: [], inventories: {}, errors: [] };
  try {
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
    const scenes = baseline ? ['base', 'new-shores-4', 'four-islands-4']
      : ['base', 'new-shores-3', 'new-shores-4', 'four-islands-3', 'four-islands-4', 'fog-before', 'fog-after'];
    for (const scene of scenes) for (const rings of baseline ? [1] : [1, 2]) {
      const cameras = {}; let signature, geometry;
      for (const source of baseline ? ['before'] : ['before', 'after']) {
        const context = await browser.newContext({ viewport: { width: 2560, height: 1440 }, deviceScaleFactor: 1, reducedMotion: 'reduce' });
        try {
          await context.addInitScript(h.observeScene); const page = await context.newPage();
          page.on('pageerror', e => report.errors.push(e.message));
          const query = h.query(scene, source, rings, true, 'static') + '&water=pilot';
          await page.goto(demo.origin + '/preview?' + query); await ready(page);
          const settings = await h.settings(page);
          if (signature) assert.deepEqual(settings, signature, 'identical native camera and public snapshot'); else signature = settings;
          const data = await inventory(page); report.inventories[scene + '-' + rings + '-' + source] = data;
          if (geometry) assert.equal(data.geometryHash, geometry, 'material pilot cannot alter geometry/IDs/visibility'); else geometry = data.geometryHash;
          for (const step of rings === 2 ? ['normal'] : ['normal', 'close', 'orbit']) {
            if (source === 'after') await h.useCamera(page, cameras[step]);
            else {
              const rect = await page.locator('canvas').boundingBox();
              if (step === 'close') { await page.mouse.move(rect.x + rect.width / 2, rect.y + rect.height / 2); await page.mouse.wheel(0, -500); }
              if (step === 'orbit') {
                await page.mouse.move(rect.x + rect.width * .5, rect.y + rect.height * .5); await page.mouse.down();
                await page.mouse.move(rect.x + rect.width * .66, rect.y + rect.height * .5, { steps: 20 }); await page.mouse.up();
              }
              await page.waitForTimeout(150); await page.mouse.move(1, 1); cameras[step] = (await h.settings(page)).camera;
            }
            const roles = rings === 2 ? ['overview', 'corner'] : step === 'normal' ? ['overview']
              : ['overview', 'corner', 'coast', 'port', ...(step === 'close' ? ['sea', 'pirate'] : [])];
            for (const role of roles) {
              const point = role === 'overview' ? null : await focus(page, role); if (role !== 'overview' && !point) continue;
              const clip = point ? { x: Math.max(0, Math.min(1960, point.x - 300)), y: Math.max(0, Math.min(840, point.y - 300)), width: 600, height: 600 } : undefined;
              const file = `${scene}-${rings}-${source}-${step}-${role}.png`;
              await page.screenshot({ path: path.join(demo.output, file), ...(clip ? { clip } : {}) });
              report.captures.push({ file, scene, rings, source, query, detail: step + ' / ' + role,
                camera: cameras[step], focus: point, sha256: h.hash(await fs.readFile(path.join(demo.output, file))) });
            }
          }
          assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
        } finally { await context.close(); }
      }
    }
    assert.deepEqual(report.errors, []); report.completed = true;
  } finally {
    await browser?.close(); await demo.close();
    await fs.writeFile(path.join(demo.output, 'capture-report.json'), JSON.stringify(report, null, 2), { flag: 'wx' });
  }
  console.log('WATER CAPTURES ' + demo.output + ' / ' + report.captures.length);
}
module.exports = { ready, focus };
if (require.main === module) main().catch(e => { console.error(e); process.exitCode = 1; });
