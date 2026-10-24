const assert = require('node:assert/strict'), fs = require('node:fs/promises'), path = require('node:path'), os = require('node:os');
const { chromium } = require('playwright');
const { startWater, reference } = require('./water-demo.cjs');
const { ready } = require('./water-capture.cjs');
const { inventory } = require('./water-inventory.cjs');
const { inspect, tileAt, token, anchor } = require('./readability-smoke.cjs');
const h = require('./ocean-support.cjs');
async function main() {
  const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-water-smoke-' + Date.now());
  await fs.mkdir(output, { recursive: true }); const file = path.join(output, 'browser-smoke.json');
  await fs.writeFile(file, '{}', { flag: 'wx' });
  const report = { completed: false, reference, checkedAt: new Date().toISOString(), checks: [], errors: [], idle: {}, screenshots: [] };
  const check = text => { report.checks.push(text); console.log('PASS ' + text); }; let demo, browser;
  try {
    demo = await startWater(); report.bundleHashes = demo.bundleHashes;
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
    async function open(scene = 'four-islands-4', water = 'pilot', mode = 'static', source = 'after', fallback = false) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
        reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' });
      await context.addInitScript(h.observeScene); const page = await context.newPage();
      page.on('pageerror', error => report.errors.push(error.message));
      if (fallback) await page.route('**/models/terrain/sea.glb', route => route.abort());
      await page.goto(demo.origin + '/preview?' + h.query(scene, source, 1, true, mode) + '&water=' + water);
      if (!fallback) await ready(page);
      else await page.waitForFunction(() => {
        if (!window.__waterPreview?.ready || !window.__scene) return false;
        let found = false; window.__scene.getState().scene.traverse(n => { if (n.userData.terrainFallback === 'sea') found = true; }); return found;
      });
      return page;
    }
    const old = await open('four-islands-4', 'current', 'static', 'before'), current = await open('four-islands-4', 'current');
    const a = await inventory(old), b = await inventory(current);
    assert.equal(b.geometryHash, a.geometryHash); assert.deepEqual(b.rows, a.rows); assert.deepEqual(b.renderer, a.renderer);
    assert.deepEqual(await h.settings(current), await h.settings(old)); await old.context().close(); await current.context().close();
    check('production-current matches exact committed5E.2 water, geometry, public state, native camera and renderer settings');

    const page = await open(), camera = (await h.settings(page)).camera, snapshot = await page.evaluate(() => window.__fogFixture.snapshot());
    const pilot = await inventory(page); assert(pilot.materials.some(m => m.name === 'HS_Water_Teal' && m.color === '31758a' && m.roughness === .88));
    for (let i = 0; i < 3; i++) {
      await page.getByLabel('Water appearance', { exact: true }).selectOption('current'); await page.mouse.move(1, 1); await page.waitForTimeout(150);
      const current = await inventory(page); assert.equal(current.geometryHash, pilot.geometryHash); assert.deepEqual(current.rows, a.rows);
      assert.deepEqual((await h.settings(page)).camera, camera);
      await page.getByLabel('Water appearance', { exact: true }).selectOption('pilot'); await page.mouse.move(1, 1); await page.waitForTimeout(150);
      const again = await inventory(page); assert.deepEqual(again.rows, pilot.rows); assert.equal(again.geometryHash, pilot.geometryHash);
      assert.deepEqual((await h.settings(page)).camera, camera);
    }
    assert.deepEqual(await page.evaluate(() => window.__fogFixture.snapshot()), snapshot);
    await page.waitForTimeout(500); const settledResources = await h.inventory(page);
    await page.getByLabel('Water appearance', { exact: true }).selectOption('current'); await page.getByLabel('Water appearance', { exact: true }).selectOption('pilot');
    await page.waitForTimeout(500); assert.deepEqual(await h.inventory(page), settledResources);
    check('live material switch/restoration changes only water appearance, preserves camera/state and has bounded warm resources');

    const targets = await page.evaluate(() => {
      let meshes = 0; const errors = []; window.__scene.getState().scene.traverse(root => {
        if (!(root.userData.decorativeOcean || root.userData.decorativeOceanHexes)) return;
        root.traverse(n => { if (!n.isMesh) return; meshes++; const hits = []; n.raycast({}, hits);
          if (hits.length || ['tileIndex', 'vertexId', 'edge', 'targetType'].some(key => key in n.userData)) errors.push(n.name); });
      }); return { meshes, errors };
    });
    assert(targets.meshes > 0); assert.deepEqual(targets.errors, []);
    const visual = await inspect(page); assert(visual.tiles.every(tile => tile.terrainRaycasts));
    await page.locator('canvas').click({ position: { x: 450, y: 300 } });
    assert.deepEqual(await page.evaluate(() => window.__fogFixture.commands()), []);
    assert.deepEqual(await page.evaluate(() => window.__fogFixture.snapshot()), snapshot);
    token(tileAt(visual, 29), -.2); anchor(visual, snapshot.state, 29);
    check('decorative water has no gameplay IDs/raycast hits; original tile targets, Fields12 robber anchor and token remain');

    await page.getByLabel('Ocean rings', { exact: true }).selectOption('2'); await page.waitForTimeout(150);
    assert((await h.footprint(page)).allInside); assert.equal((await h.inventory(page)).cells, '54');
    const canvas = await page.locator('canvas').boundingBox();
    await page.mouse.move(canvas.x + canvas.width * .5, canvas.y + canvas.height * .5); await page.mouse.wheel(0, -300);
    await page.mouse.down(); await page.mouse.move(canvas.x + canvas.width * .65, canvas.y + canvas.height * .5, { steps: 15 }); await page.mouse.up();
    await page.waitForTimeout(150); const orbited = (await h.settings(page)).camera;
    await page.getByLabel('Water appearance', { exact: true }).selectOption('current'); await page.waitForTimeout(100);
    assert.deepEqual((await h.settings(page)).camera, orbited);
    await page.getByLabel('Ocean frame', { exact: true }).selectOption('0'); await page.getByLabel('Ocean frame', { exact: true }).selectOption('1');
    await page.getByRole('button', { name: 'Reset Camera', exact: true }).click(); await page.waitForTimeout(200); assert((await h.footprint(page)).allInside);
    await page.setViewportSize({ width: 1280, height: 720 }); await page.waitForTimeout(200); assert((await h.footprint(page)).allInside);
    await page.getByLabel('Ocean rings', { exact: true }).selectOption('1'); await page.waitForTimeout(150);
    assert.equal((await h.inventory(page)).cells, '24'); assert((await h.footprint(page)).allInside);
    assert.equal(new URL(page.url()).searchParams.get('water'), 'current', 'ring/frame URL updates preserve live material choice');
    check('one/two-ring geometry and frame survive material switch, real orbit/zoom, reset and desktop resize');
    await page.context().close();

    const fog = await open('fog-before', 'pilot', 'normal'), beforeFog = await inspect(fog), fogCamera = (await h.settings(fog)).camera;
    for (const tile of beforeFog.tiles.filter(t => t.visibility === 'hidden')) assert.equal(tile.assets.length + tile.fallbacks.length + tile.tokens.length, 0);
    await fog.evaluate(() => {
      const f = window.__fogFixture.snapshot(); f.tick++; const tile = f.state.tiles.find(t => t.visibility === 'hidden');
      tile.visibility = 'revealed'; tile.terrain = 'sea'; tile.number = null; f.state.game_events = []; window.__fogFixture.publish(f);
    });
    await h.ready(fog); assert.deepEqual((await h.settings(fog)).camera, fogCamera);
    assert((await inventory(fog)).materials.some(m => m.name === 'HS_Water_Teal' && m.color === '31758a'));
    for (const tile of (await inspect(fog)).tiles.filter(t => t.visibility === 'hidden')) assert.equal(tile.assets.length + tile.tokens.length, 0);
    await fog.context().close(); check('unknown Fog contains no actual terrain/number; public Sea reveal uses pilot without camera reset or hidden inference');

    for (const mode of ['normal', 'reduced', 'static']) {
      const p = await open('four-islands-4', 'pilot', mode); report.idle[mode] = await h.idleFrames(p);
      if (mode !== 'normal') assert.equal(report.idle[mode], 0); else assert(report.idle[mode] <= 20);
      const file = path.join(output, 'water-fi4-' + mode + '.png'); await p.screenshot({ path: file }); report.screenshots.push(file);
      await p.context().close();
    }
    check('normal/reduced/static keep existing motion limits and zero reduced/static idle rendering');

    const play = await open('seven', 'pilot', 'normal');
    const rendered = await play.evaluate(() => window.__scene.getState().gl.info.render.frame);
    await play.getByRole('button', { name: 'Ship', exact: true }).click();
    await play.waitForFunction(previous => {
      const store = window.__scene?.getState(), edge = window.__fogFixture.snapshot().state.legal.ships[0]; let found = false;
      if (!store || store.gl.info.render.frame <= previous) return false;
      store.scene.traverse(n => { found ||= n.userData.targetType === 'edge' && n.userData.edge.join(',') === edge.join(','); }); return found;
    }, rendered);
    const point = await play.evaluate(() => {
      const e = window.__fogFixture.snapshot().state.legal.ships[0], { scene, camera, gl } = window.__scene.getState(); let target;
      scene.traverse(n => { if (n.userData.targetType === 'edge' && n.userData.edge.join(',') === e.join(',')) target = n; });
      if (!target) throw Error('Missing original legal ship target'); const p = target.getWorldPosition(target.position.clone()).project(camera), r = gl.domElement.getBoundingClientRect();
      return { x: r.x + (p.x + 1) * r.width / 2, y: r.y + (1 - p.y) * r.height / 2 };
    });
    await play.mouse.click(point.x, point.y); await play.waitForFunction(() => window.__fogFixture.commands().length === 1);
    await play.evaluate(() => { window.__fogFixture.ship(false); window.__fogFixture.settle(true); }); await play.reload(); await ready(play);
    const route = await play.evaluate(() => { const s = window.__fogFixture.snapshot().state; return { from: s.legal.move_ship.sources[0].join(','), to: s.legal.ships[0].join(',') }; });
    await play.evaluate(() => window.__fogFixture.ship(true)); await play.waitForTimeout(1000);
    assert(await play.evaluate(({ from, to }) => { const ships = window.__fogFixture.snapshot().state.occupied_ships; return !(from in ships) && ships[to] === 0; }, route));
    await play.evaluate(() => window.__fogFixture.threat('pirate')); await play.waitForTimeout(1000);
    const pirateState = await play.evaluate(() => window.__fogFixture.snapshot().state), pirate = (await inspect(play)).figures.find(f => f.kind === 'pirate');
    assert(pirate); const [x, z] = pirateState.tiles[pirateState.pirate_tile].center.map(n => n / pirateState.size);
    const pirateAnchor = await play.evaluate(() => { let value; window.__scene.getState().scene.traverse(n => {
      if (n.userData.piece === 'pirate') value = n.getWorldPosition(n.position.clone()).toArray();
    }); return value; });
    pirateAnchor.forEach((value, i) => assert(Math.abs(value - [x + .15, .29, z + .24][i]) < 1e-8));
    assert(!pirate.moving && !pirate.arriving);
    assert(Math.abs(pirate.position[0] - x - .15) < 1e-8 && Math.abs(pirate.position[2] - z - .24) < 1e-8);
    // Existing normal-mode ambient bob is ±.004, independently of water materials.
    assert(Math.abs(pirate.position[1] - .29) < .005);
    await play.getByLabel('Ship model', { exact: true }).selectOption('glb');
    await play.waitForFunction(() => { let found = false; window.__scene.getState().scene.traverse(n => { if (n.userData.shipModel === 'glb') found = true; }); return found; });
    await play.getByLabel('Ship model', { exact: true }).selectOption('procedural');
    check('real legal ship pointer, confirmed ship move, exact pirate endpoint and procedural/GLB option survive pilot');

    const publicState = await play.evaluate(() => window.__fogFixture.snapshot());
    await play.getByRole('button', { name: '2D', exact: true }).click(); await play.waitForSelector('[data-renderer="2d"] svg');
    assert.deepEqual(await play.evaluate(() => window.__fogFixture.snapshot()), publicState);
    await play.getByRole('button', { name: '3D', exact: true }).click();
    await play.waitForFunction(() => window.__scene?.getState().gl.domElement === document.querySelector('canvas')); await ready(play);
    await play.evaluate(() => window.__fogFixture.status('disconnected')); await play.waitForTimeout(40);
    await play.evaluate(() => window.__fogFixture.status('connected')); await play.waitForTimeout(40);
    await play.reload(); await ready(play); assert((await inspect(play)).figures.every(f => !f.moving && !f.arriving));
    await play.context().close(); check('SVG round-trip, reconnect presentation and reload remain quiet without historical movement replay');

    const fallback = await open('four-islands-4', 'pilot', 'static', 'after', true);
    const colors = await fallback.evaluate(() => { let result; window.__scene.getState().scene.traverse(n => {
      if (n.userData.terrainFallback === 'sea') result = n.children.find(c => c.isMesh)?.material.map(m => m.color.getHexString());
    }); return result; });
    assert.deepEqual(colors, ['31758a', '25586c']);
    assert((await inspect(fallback)).tiles.every(tile => tile.terrainRaycasts));
    await fallback.context().close(); check('intentional Sea GLB failure retains readable pilot procedural fallback and logical hit geometry');
    assert.deepEqual(report.errors, []); report.completed = true;
  } finally { await browser?.close(); await demo?.close(); await fs.writeFile(file, JSON.stringify(report, null, 2)); }
  console.log('WATER SMOKE ' + output);
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
