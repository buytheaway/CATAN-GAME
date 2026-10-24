// Real Board3D with PUBLIC synthetic frames; no backend, trusted Fog or GPU timing.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startReadability, reference } = require('./readability-demo.cjs');
const h = require('./ocean-support.cjs');

async function inspect(page) {
  return page.evaluate(() => {
    const { scene, gl } = window.__scene.getState(); scene.updateMatrixWorld(true);
    const result = { tiles: [], figures: [], frames: gl.info.render.frame,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures };
    scene.traverse(root => {
      if (root.userData.visibility && Number.isInteger(root.userData.tileIndex)) {
        const tile = { id: root.userData.tileIndex, visibility: root.userData.visibility, terrain: root.userData.terrain,
          position: root.position.toArray(), vegetation: [], assets: [], fallbacks: [], tokens: [], terrainRaycasts: true };
        root.traverse(node => {
          if (/^Hex_(?:Fields_Wheat_|Forest_Pine_|Pasture_Sheep_)/.test(node.name))
            tile.vegetation.push({ name: node.name, visible: node.visible });
          if (node.userData.terrainAsset) tile.assets.push(node.userData.terrainAsset);
          if (node.userData.terrainFallback) tile.fallbacks.push(node.userData.terrainFallback);
          if (node !== root && node.userData.number != null) tile.tokens.push({ number: node.userData.number, position: node.position.toArray() });
          if (node.userData.terrainAsset || node.userData.terrainFallback) node.traverse(mesh => {
            if (!mesh.isMesh) return; const hits = []; mesh.raycast({}, hits); tile.terrainRaycasts &&= hits.length === 0;
          });
        }); result.tiles.push(tile);
      }
      if (nodeFigure(root)) result.figures.push({ kind: root.userData.threatVisual,
        tile: root.userData.tileIndex, position: root.getWorldPosition(root.position.clone()).toArray(),
        moving: root.userData.moving, arriving: root.userData.arriving });
    });
    function nodeFigure(node) { return typeof node.userData.threatVisual === 'string'; }
    return result;
  });
}
const tileAt = (value, id) => { const tile = value.tiles.find(t => t.id === id); assert(tile, 'missing public tile ' + id); return tile; };
const hiddenVegetation = tile => tile.vegetation.filter(node => !node.visible).map(node => node.name);
function token(tile, x) {
  assert.equal(tile.tokens.length, 1); assert.equal(tile.tokens[0].position[0], x);
  assert.equal(tile.tokens[0].position[1], .305); assert.equal(tile.tokens[0].position[2], .18);
}
function anchor(value, state, id) {
  const figure = value.figures.find(f => f.kind === 'robber' && f.tile === id); assert(figure);
  const [x, z] = state.tiles[id].center.map(n => n / state.size);
  for (const [actual, expected] of figure.position.map((n, i) => [n, [x + .48, .26, z + .1][i]]))
    assert(Math.abs(actual - expected) < 1e-8, 'robber keeps its original authoritative tile anchor');
}
async function main() {
  const output = process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-readability-smoke-' + Date.now());
  await fs.mkdir(output, { recursive: true }); const file = path.join(output, 'browser-smoke.json');
  await fs.writeFile(file, '{}', { flag: 'wx' });
  const report = { completed: false, checkedAt: new Date().toISOString(), reference,
    scope: 'PUBLIC synthetic frames; actual renderer; no gameplay execution or GPU timing', checks: [], errors: [], expectedAssetErrors: [], screenshots: [], idle: {} };
  let demo, browser;
  const check = text => { report.checks.push(text); console.log('PASS ' + text); };
  const contexts = [];
  try {
    demo = await startReadability(0); report.bundleHashes = demo.bundleHashes;
    browser = await chromium.launch({ channel: 'chrome', headless: true }); report.chrome = browser.version();
    async function open(source = 'after', mode = 'static', scene = 'four-islands-4', fallback = false) {
      const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1,
        reducedMotion: mode === 'reduced' ? 'reduce' : 'no-preference' }); contexts.push(context);
      await context.addInitScript(h.observeScene);
      if (fallback) await context.route('**/models/terrain/fields.glb', route => route.fulfill({ status: 404, body: '' }));
      const page = await context.newPage(); page.on('pageerror', error => report.errors.push(error.message));
      page.on('console', message => {
        if (message.type() !== 'error') return;
        if (fallback && message.location().url.endsWith('/models/terrain/fields.glb') && /Failed to load resource/.test(message.text()))
          report.expectedAssetErrors.push(message.text());
        else report.errors.push(message.text());
      });
      await page.goto(demo.origin + '/preview?' + h.query(scene, source, 1, true, mode));
      await page.waitForFunction(() => window.__readabilityPreview?.ready || window.__readabilityPreview?.error);
      assert.equal(await page.evaluate(() => window.__readabilityPreview.error), undefined);
      if (!fallback) await h.ready(page);
      else {
        await page.waitForFunction(() => window.__readabilityPreview?.ready && window.__scene?.getState().scene);
        await page.waitForFunction(() => { let found = false; window.__scene.getState().scene.traverse(o => { found ||= o.userData.terrainFallback === 'fields'; }); return found; });
        await page.waitForTimeout(500);
      }
      return page;
    }
    async function shot(page, name) { const target = path.join(output, name + '.png'); await page.screenshot({ path: target }); report.screenshots.push(target); }
    const before = await open('before'), after = await open();
    const oldState = await before.evaluate(() => window.__fogFixture.snapshot());
    const state = await after.evaluate(() => window.__fogFixture.snapshot()); assert.deepEqual(state, oldState);
    assert.equal(state.state.robber_tile, 29); assert.equal(state.state.tiles[29].terrain, 'fields'); assert.equal(state.state.tiles[29].number, 12);
    const old = await inspect(before), current = await inspect(after);
    assert(hiddenVegetation(tileAt(current, 29)).length > 0); assert.equal(hiddenVegetation(tileAt(old, 29)).length, 0);
    for (const tile of current.tiles) {
      const original = tileAt(old, tile.id); assert.deepEqual(tile.position, original.position); assert.deepEqual(tile.assets, original.assets);
      if (tile.id !== 29) { assert.deepEqual(tile.vegetation, original.vegetation); assert.deepEqual(tile.tokens, original.tokens); }
      assert(tile.terrainRaycasts);
    }
    token(tileAt(old, 29), 0); token(tileAt(current, 29), -.2);
    assert.equal(tileAt(current, 29).tokens[0].number, 12); anchor(current, state.state, 29);
    check('FI4 tile29 Fields12: only occupied clone vegetation/print offset changes; values, other clones, anchors and ignored terrain raycasts stay intact');
    await shot(before, 'before-fi4-static'); await shot(after, 'after-fi4-static');

    const snapshot = await after.evaluate(() => window.__fogFixture.snapshot());
    await after.locator('canvas').hover({ position: { x: 450, y: 300 } });
    await after.locator('canvas').click({ position: { x: 450, y: 300 } });
    assert.deepEqual(await after.evaluate(() => window.__fogFixture.snapshot()), snapshot);
    assert.equal(await after.evaluate(() => window.__fogFixture.commands().length), 0);
    assert.deepEqual((await inspect(after)).tiles, current.tiles);
    check('ordinary hover/click with no legal action sends no command, changes no snapshot and preserves local clearance');
    report.idle.static = await h.idleFrames(after); assert.equal(report.idle.static, 0);
    await before.context().close(); await after.context().close();

    const moving = await open('after', 'normal');
    const target = await moving.evaluate(() => {
      const frame = window.__fogFixture.snapshot(), from = frame.state.robber_tile;
      const to = frame.state.tiles.findIndex((tile, id) => id !== from && tile.terrain === 'fields');
      frame.tick++; frame.state.robber_tile = to; frame.state.robbers = [to];
      frame.state.game_events = [{ id: 1, tick: frame.tick, at_ms: Date.now(), actor_pid: 0, type: 'move_robber', from_tile: from, tile: to }];
      window.__fogFixture.publish(frame); return { from, to };
    });
    await moving.waitForFunction(({ from, to }) => {
      let a, b; window.__scene.getState().scene.traverse(root => {
        if (!root.userData.visibility) return;
        root.traverse(node => { if (node !== root && node.userData.number != null) { if (root.userData.tileIndex === from) a = node.position.x; if (root.userData.tileIndex === to) b = node.position.x; } });
      }); return a === -.2 && b === -.2;
    }, target);
    const during = await inspect(moving); assert(hiddenVegetation(tileAt(during, target.from)).length); assert(hiddenVegetation(tileAt(during, target.to)).length);
    await moving.waitForTimeout(1100);
    const expired = await inspect(moving); assert.equal(hiddenVegetation(tileAt(expired, target.from)).length, 0); token(tileAt(expired, target.from), 0);
    assert(hiddenVegetation(tileAt(expired, target.to)).length); token(tileAt(expired, target.to), -.2);
    anchor(expired, (await moving.evaluate(() => window.__fogFixture.snapshot())).state, target.to);
    check('finite public move retains departure standing room/print until expiry, then restores old clone and exact final anchor');
    await shot(moving, 'after-fi4-normal-moved'); report.idle.normal = await h.idleFrames(moving); assert(report.idle.normal <= 20);
    await moving.context().close();

    const reduced = await open('after', 'reduced'); anchor(await inspect(reduced), state.state, 29);
    token(tileAt(await inspect(reduced), 29), -.2); report.idle.reduced = await h.idleFrames(reduced); assert.equal(report.idle.reduced, 0);
    await shot(reduced, 'after-fi4-reduced'); await reduced.context().close();
    check('static/reduced views retain readable final geometry with zero idle frames; normal retains bounded existing scene motion');

    const fog = await open('after', 'static', 'fog-before');
    await fog.evaluate(() => { const frame = window.__fogFixture.snapshot(); const hidden = frame.state.tiles.findIndex(t => t.visibility === 'hidden');
      frame.tick++; frame.state.robber_tile = hidden; frame.state.robbers = [hidden]; frame.state.game_events = []; window.__fogFixture.publish(frame); });
    await fog.waitForTimeout(200); const unknown = await inspect(fog);
    assert.equal(unknown.figures.filter(f => f.kind === 'robber').length, 0);
    for (const tile of unknown.tiles.filter(t => t.visibility === 'hidden')) { assert.equal(tile.assets.length, 0); assert.equal(tile.fallbacks.length, 0); assert.equal(tile.tokens.length, 0); assert.equal(tile.vegetation.length, 0); }
    assert(unknown.tiles.every(t => hiddenVegetation(t).length === 0));
    await shot(fog, 'after-fog-hidden'); await fog.context().close();
    check('hidden public Fog never constructs terrain, tokens or robber clearance/figures, even for a malformed hidden figure ID');

    const fallback = await open('after', 'static', 'four-islands-4', true); const flat = await inspect(fallback);
    assert.deepEqual(tileAt(flat, 29).fallbacks, ['fields']); token(tileAt(flat, 29), -.2); anchor(flat, state.state, 29);
    assert.equal(tileAt(flat, 29).vegetation.length, 0); assert(tileAt(flat, 29).terrainRaycasts);
    assert(tileAt(flat, 29).tokens[0].number === 12); await shot(fallback, 'after-fi4-fields-fallback'); await fallback.context().close();
    check('failed Fields GLB safely retains original ground, number, standing anchor and non-intercepting fallback');
    assert.deepEqual(report.errors, []); report.completed = true;
  } finally {
    for (const context of contexts) await context.close().catch(() => {});
    await browser?.close(); await demo?.close(); await fs.writeFile(file, JSON.stringify(report, null, 2));
  }
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
