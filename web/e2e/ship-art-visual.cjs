// Actual Board3D/public snapshots. No live-server overrides or private game data.
const assert = require('node:assert/strict');
const fs = require('node:fs/promises');
const path = require('node:path');
const os = require('node:os');
const { chromium } = require('playwright');
const { startDemo } = require('./fog-visual-demo.cjs');
const { observeScene, ready, idleFrames } = require('./ships-visual.cjs');
const { fullyReady } = require('./buildings-compare.cjs');
const output = path.resolve(process.env.CATAN_E2E_OUTPUT || path.join(os.tmpdir(), 'catan-ship-art-pilot'));
const sleep = ms => new Promise(resolve => setTimeout(resolve, ms));
const palette = ['ef4444', '3b82f6', '22c55e', 'f59e0b'];

async function artReady(page) {
  await fullyReady(page);
  await page.waitForFunction(() => {
    let ships = 0, assets = 0, fallback = false;
    window.__scene.getState().scene.traverse(o => {
      if (o.userData.piece === 'ship' && !o.userData.preview) ships++;
      if (o.userData.shipModel === 'glb') assets++;
      fallback ||= !!o.userData.shipAssetFallback;
    });
    return ships > 0 && assets >= ships && !fallback;
  });
}

async function shipInfo(page) {
  return page.evaluate(() => {
    const { scene, gl, camera } = window.__scene.getState(), ships = [], echoes = [], echoModels = [];
    let cities = 0, settlements = 0, fog = 0, raycasts = 0, raysIgnored = true;
    scene.updateMatrixWorld(true);
    scene.traverse(o => {
      if (o.userData.level === 2 && !o.userData.preview) cities++;
      if (o.userData.level === 1 && !o.userData.preview) settlements++;
      if (o.userData.fogVisual) fog++;
      if (o.userData.shipDeparture && o.visible) {
        echoes.push(o.userData.fromEdge);
        o.traverse(child => { if (child.userData.shipModel) echoModels.push(child.userData.shipModel); });
      }
      if (o.userData.piece !== 'ship' || o.userData.preview) return;
      const ship = { edge: o.userData.edge, owner: o.userData.owner, position: o.position.toArray(),
        yaw: o.rotation.y, models: [], materials: [], meshes: 0, triangles: 0, pose: null };
      o.traverse(child => {
        if (child.userData.shipVisual) ship.pose = { position: child.position.toArray(),
          rotation: child.rotation.toArray().slice(0, 3), scale: child.scale.toArray(), ...child.userData };
        if (child.userData.shipModel) ship.models.push({ model: child.userData.shipModel,
          fallback: !!child.userData.shipAssetFallback });
        if (!child.isMesh) return;
        ship.meshes++; ship.triangles += (child.geometry.index?.count ?? child.geometry.attributes.position.count) / 3;
        for (const material of Array.isArray(child.material) ? child.material : [child.material]) {
          ship.materials.push({ name: material.name, color: material.color?.getHexString(),
            opacity: material.opacity, transparent: material.transparent, uuid: material.uuid });
        }
        const hits = []; raycasts++;
        try { child.raycast({}, hits); raysIgnored &&= hits.length === 0; } catch { raysIgnored = false; }
      }); ships.push(ship);
    });
    return { ships, echoes, echoModels, cities, settlements, fog, raycasts, raysIgnored,
      geometries: gl.info.memory.geometries, textures: gl.info.memory.textures,
      commits: window.__sceneCommits, camera: camera.position.toArray(), frames: gl.info.render.frame };
  });
}

function anchors(info, state) {
  for (const ship of info.ships) {
    const [a, b] = ship.edge.map(vertex => state.vertices[vertex]);
    const wanted = [(a[0] + b[0]) / state.size / 2, .32, (a[1] + b[1]) / state.size / 2];
    assert(ship.position.every((value, index) => Math.abs(value - wanted[index]) < 1e-8));
    assert(Math.abs(ship.yaw + Math.atan2(b[1] - a[1], b[0] - a[0])) < 1e-8);
  }
}

async function staticMode(page) {
  await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
  await page.getByLabel('Ship effects', { exact: true }).selectOption('static');
  await page.getByLabel('Construction effects', { exact: true }).selectOption('static');
  await page.getByLabel('Robber & pirate effects', { exact: true }).selectOption('static');
  await sleep(250);
}

async function main() {
  await fs.mkdir(output, { recursive: true });
  const demo = await startDemo(), browser = await chromium.launch({ channel: 'chrome', headless: true });
  const report = { completed: false, browser: browser.version(), checkedAt: new Date().toISOString(),
    checks: [], errors: [], screenshots: [], assetResponses: [], modes: {} };
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  await context.addInitScript(observeScene); const page = await context.newPage();
  page.on('pageerror', error => report.errors.push(error.message));
  page.on('console', message => { if (message.type() === 'error') report.errors.push(message.text()); });
  page.on('response', response => {
    if (response.url().endsWith('/models/pieces/ship-pilot.glb')) report.assetResponses.push({ url: response.url(), status: response.status() });
  });
  const shot = async name => { const file = path.join(output, name + '.png');
    await page.screenshot({ path: file }); report.screenshots.push(file); };
  try {
    await page.goto(demo.origin + '/?demo=1&shipsart=1'); await fullyReady(page);
    assert.equal(await page.getByLabel('Ship model', { exact: true }).inputValue(), 'procedural');
    assert.equal(report.assetResponses.length, 0, 'procedural default must not request the pilot asset');
    let frame = await page.evaluate(() => window.__fogFixture.snapshot());
    let info = await shipInfo(page); assert.equal(info.ships.length, 4); anchors(info, frame.state);
    assert.equal(info.cities, 1); assert.equal(info.settlements, 1); assert(frame.state.ports.length > 0);
    assert(frame.state.tiles.some(tile => tile.visibility === 'hidden')); await shot('procedural-7-hex');
    const initialAnchors = info.ships.map(ship => ({ edge: ship.edge, owner: ship.owner, position: ship.position, yaw: ship.yaw }));
    await page.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(page);
    info = await shipInfo(page); anchors(info, frame.state);
    assert.deepEqual(info.ships.map(ship => ({ edge: ship.edge, owner: ship.owner, position: ship.position, yaw: ship.yaw })), initialAnchors);
    assert.equal(report.assetResponses.length, 1); assert.equal(report.assetResponses[0].status, 200);
    for (const ship of info.ships) {
      assert.deepEqual(ship.models, [{ model: 'glb', fallback: false }]);
      assert.equal(ship.meshes, 3);
      const material = ship.materials.find(item => item.name === 'PlayerColor');
      assert(material, 'pilot needs the named player color material'); assert.equal(material.color, palette[ship.owner]);
    }
    for (const name of ['HullWood', 'CanvasIvory']) {
      const materials = info.ships.map(ship => ship.materials.find(material => material.name === name));
      assert(materials.every(Boolean), `missing neutral material ${name}`);
      assert.equal(new Set(materials.map(material => material.color)).size, 1, `${name} must not inherit owner color`);
      assert.equal(new Set(materials.map(material => material.uuid)).size, 1, `${name} should reuse its neutral source material`);
    }
    assert(info.raycasts >= 12 && info.raysIgnored); await shot('glb-7-hex');
    report.modelDetails = info.ships; report.checks.push('default procedural/no asset transfer; explicit GLB choice; four player colors; exact anchors/yaw; three meshes and non-raycasting bodies; settlement/city/port/Fog coexist');

    // Real wheel controls, not an alternate camera transform or art-only renderer.
    const canvas = page.locator('canvas').first(), rect = await canvas.boundingBox();
    await page.mouse.move(rect.x + rect.width * .65, rect.y + rect.height * .5);
    const initialCamera = info.camera; await page.mouse.wheel(0, -500); await sleep(400);
    const close = await shipInfo(page); assert.notDeepEqual(close.camera, initialCamera); await shot('glb-close');
    await page.mouse.wheel(0, 950); await sleep(400); const far = await shipInfo(page);
    assert.notDeepEqual(far.camera, close.camera); await shot('glb-far');
    await page.getByRole('button', { name: 'Reset Camera', exact: true }).click(); await sleep(350);
    report.cameraDistances = { default: initialCamera, close: close.camera, far: far.camera };
    report.checks.push('normal camera, real wheel close/far and reset remain functional');

    await page.getByRole('button', { name: 'Construct ship', exact: true }).click();
    await page.waitForFunction(() => { let active = false; window.__scene.getState().scene.traverse(o => {
      active ||= !!(o.userData.shipVisual && o.userData.appearing && o.userData.shipEffect === 'build'); }); return active; });
    info = await shipInfo(page); assert.equal(info.ships.length, 5); assert(info.ships.some(ship => ship.pose.appearing));
    assert(info.ships.every(ship => ship.models[0]?.model === 'glb')); await shot('glb-construction'); await sleep(1200);
    info = await shipInfo(page); assert(info.ships.every(ship => !ship.pose.appearing && ship.pose.scale.every(value => value === 1)));
    await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await artReady(page);
    frame = await page.evaluate(() => window.__fogFixture.snapshot());
    await page.getByRole('button', { name: 'Move ship', exact: true }).click();
    await page.waitForFunction(() => { let active = false; window.__scene.getState().scene.traverse(o => {
      active ||= !!(o.userData.shipVisual && o.userData.appearing && o.userData.shipEffect === 'move'); }); return active; });
    info = await shipInfo(page); assert.equal(info.ships.length, 4); assert.equal(info.echoes.length, 1);
    assert.deepEqual(info.echoModels, ['glb'], 'source echo must use the selected pilot body too');
    await shot('glb-movement'); await sleep(1200); info = await shipInfo(page);
    assert.equal(info.echoes.length, 0); anchors(info, (await page.evaluate(() => window.__fogFixture.snapshot())).state);
    const accepted = await page.evaluate(() => window.__fogFixture.snapshot());
    await page.evaluate(frame => { window.__fogFixture.publish(frame); window.__fogFixture.reject(); }, accepted); await sleep(150);
    assert((await shipInfo(page)).ships.every(ship => !ship.pose.appearing));
    report.checks.push('same confirmed construction/movement wrappers and source echo; exact authoritative final anchors; duplicate/rejection do not replay');

    await page.getByRole('button', { name: 'Reset preview', exact: true }).click(); await artReady(page);
    await page.getByLabel('Fog effects', { exact: true }).selectOption('still');
    const first = await shipInfo(page), idle = await idleFrames(page), last = await shipInfo(page);
    assert(idle >= 9 && idle <= 15); assert.equal(last.commits, first.commits);
    assert.equal(last.geometries, first.geometries); assert.equal(last.textures, first.textures);
    assert(last.ships.some((ship, index) => JSON.stringify(ship.pose.rotation) !== JSON.stringify(first.ships[index].pose.rotation)));
    await staticMode(page); assert.equal(await idleFrames(page), 0); await shot('glb-static');
    report.modes.static = { idleFramesPerSecond: 0 }; report.modes.normal = { idleFramesPerSecond: idle, noIdleReactCommitsOrResourceChurn: true };
    await page.getByLabel('Ship effects', { exact: true }).selectOption('motion');
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await page.getByRole('button', { name: 'Construct ship', exact: true }).click(); await sleep(180);
    info = await shipInfo(page); assert(info.ships.every(ship => !ship.pose.appearing && ship.pose.scale.every(value => value === 1)));
    assert.equal(await idleFrames(page), 0); await shot('glb-reduced'); report.modes.reduced = { idleFramesPerSecond: 0 };
    await page.emulateMedia({ reducedMotion: 'no-preference' }); await sleep(150);
    assert((await shipInfo(page)).ships.every(ship => !ship.pose.appearing));
    report.checks.push('shared ~12 Hz ambient rocking without resource/React churn; Still/reduced demand idle; reduced construction immediate without replay');

    for (const model of ['procedural', 'glb', 'procedural', 'glb']) {
      await page.getByLabel('Ship model', { exact: true }).selectOption(model); await sleep(200);
      assert((await shipInfo(page)).ships.every(ship => !ship.pose.appearing));
    }
    assert.equal(report.assetResponses.length, 1, 'switches must reuse the loaded asset');
    await page.getByRole('button', { name: '2D', exact: true }).click();
    assert.equal(await page.locator('[data-renderer="2d"] > svg').count(), 1);
    assert.equal(await page.locator('canvas').count(), 0, 'SVG view must unmount the Three canvas');
    await page.getByRole('button', { name: '3D', exact: true }).click(); await artReady(page);
    assert((await shipInfo(page)).ships.every(ship => !ship.pose.appearing));
    await page.getByRole('button', { name: '50 tiles', exact: true }).click(); await artReady(page);
    info = await shipInfo(page); assert.equal(info.ships.length, 24); await shot('glb-50-hex');
    await page.getByLabel('Ship model', { exact: true }).selectOption('procedural'); await sleep(250); await shot('procedural-50-hex');
    for (const viewport of [{ width: 1024, height: 768 }, { width: 1440, height: 900 }]) {
      await page.setViewportSize(viewport); await sleep(150);
      assert(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth));
    }
    assert.equal((await page.evaluate(() => window.__fogFixture.commands())).length, 0);
    report.checks.push('model switches reuse asset and do not replay or send commands; SVG round trip; 24 ships/50 hexes; desktop resize');

    const fallbackContext = await browser.newContext({ viewport: { width: 1440, height: 900 } });
    await fallbackContext.addInitScript(observeScene); await fallbackContext.route('**/models/pieces/ship-pilot.glb', route => route.fulfill({ status: 404, body: '' }));
    const fallbackPage = await fallbackContext.newPage(), fallbackErrors = [];
    fallbackPage.on('pageerror', error => fallbackErrors.push(error.message));
    await fallbackPage.goto(demo.origin + '/?demo=1&shipsart=1'); await fullyReady(fallbackPage);
    await fallbackPage.getByLabel('Ship model', { exact: true }).selectOption('glb');
    await fallbackPage.waitForFunction(() => { let count = 0; window.__scene.getState().scene.traverse(o => {
      if (o.userData.shipAssetFallback) count++; }); return count >= 4; }); await sleep(350);
    const fallbackInfo = await shipInfo(fallbackPage); assert.equal(fallbackInfo.ships.length, 4);
    assert(fallbackInfo.ships.every(ship => ship.models[0]?.model === 'procedural' && ship.models[0]?.fallback));
    anchors(fallbackInfo, (await fallbackPage.evaluate(() => window.__fogFixture.snapshot())).state);
    assert.deepEqual(fallbackErrors, []); report.fallback = { status: 404, ships: fallbackInfo.ships.length, pageErrors: fallbackErrors };
    const fallbackShot = path.join(output, 'glb-404-fallback.png'); await fallbackPage.screenshot({ path: fallbackShot }); report.screenshots.push(fallbackShot);
    await fallbackContext.close(); report.checks.push('synthetic asset 404 safely falls back to procedural ships; anchors and application remain available');

    // Separate context excludes recording cost from every benchmark.
    const videoContext = await browser.newContext({ viewport: { width: 1440, height: 900 }, recordVideo: { dir: output, size: { width: 1440, height: 900 } } });
    await videoContext.addInitScript(observeScene); const videoPage = await videoContext.newPage();
    await videoPage.goto(demo.origin + '/?demo=1&shipsart=1'); await fullyReady(videoPage); await sleep(500);
    await videoPage.getByLabel('Ship model', { exact: true }).selectOption('glb'); await artReady(videoPage); await sleep(500);
    await videoPage.getByRole('button', { name: 'Construct ship', exact: true }).click(); await sleep(1300);
    await videoPage.getByRole('button', { name: 'Reset preview', exact: true }).click(); await sleep(300);
    await videoPage.getByRole('button', { name: 'Move ship', exact: true }).click(); await sleep(1300);
    await staticMode(videoPage); await sleep(700); const video = videoPage.video(); await videoContext.close(); report.video = await video.path();
    assert.deepEqual(report.errors, []); report.completed = true;
  } catch (error) { report.failure = error.stack; throw error; }
  finally {
    await fs.writeFile(path.join(output, 'acceptance.json'), JSON.stringify(report, null, 2));
    await browser.close(); demo.server.close();
  }
  console.log(JSON.stringify({ completed: report.completed, groups: report.checks.length, output, video: report.video }, null, 2));
}
if (require.main === module) main().catch(error => { console.error(error); process.exitCode = 1; });
module.exports = { artReady, shipInfo, staticMode };
